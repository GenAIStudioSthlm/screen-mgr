# Braccio MCP — demo-room setup guide

This package contains the **Braccio arm MCP server** plus an **autonomous visual-servo
grasp**: a webcam-based pipeline that lets the arm find and pick up an object (e.g. a
bottle) with **no hand-eye calibration** — it re-learns the camera↔arm relationship on
every grab, so it is immune to the camera being moved or bumped. This guide gets the
software installed and validated **ahead of time** so it works the moment the arm arrives.

The MCP server is a standard **stdio** server, so it works with any MCP-capable host
(Claude Desktop, Claude Code, your own client, etc.).

---

## 1. Prerequisites

- **Python 3.10+** (`python3 --version`).
- **~1.5 GB free disk** for the virtual environment (it pulls in PyTorch + Ultralytics).
- **Internet** for the one-time `pip install` (the large dependencies download then cache).
  The YOLO model (`yolo11n-seg.pt`) is **bundled**; the better `yolo11s-seg.pt` (~20 MB,
  recommended for the demo) downloads automatically on first use.
- A **USB or built-in webcam**.
- **Two small strips of coloured paper/tape** — one **green**, one **blue** — taped along
  the top of the gripper's two fingers. These are the grasp system's eyes-on-the-gripper:
  it locates the jaw by these strips every measurement. Long + thin matters (the detector
  uses elongation to tell a strip from, say, a blue bottle cap); the exact hues are
  tunable (`ARM_MARKER_A_HUE` green default 55–95, `ARM_MARKER_B_HUE` blue default 96–130).
- **macOS camera permission**: OpenCV's camera access is granted to the *app that launches
  Python*. Launch the vision server from **Terminal.app** or **iTerm2** (they prompt
  correctly). Some newer terminals (e.g. Rio) can't get camera access at all.

---

## 2. Install ahead of time

From inside this folder:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Validate without the arm:

```sh
.venv/bin/python server.py --selftest    # IK checks pass offline; WS connect fails w/o arm
.venv/bin/python vision.py --test        # one webcam capture through the detector
```

---

## 3. Camera placement (matters a lot)

The camera must see **both the objects and the arm's gripper**. For the grasp to converge:

- **Good**: elevated front or diagonal view (~30–60° down), looking at the workspace from
  in front of or beside the arm.
- **Bad — grasp aborts with placement advice**: directly **behind the arm looking along
  its reach axis** (base-rotation and reach become visually indistinguishable).
- **Bad — detection fails**: directly **overhead** (YOLO cannot recognise a bottle seen
  straight down; it's just a circle with a cap).

No calibration is needed after moving the camera — the grasp re-learns the mapping each
run. The arm's base should be weighed down or held; it is top-heavy at full reach.

**Lighting**: avoid harsh direct sunlight on the workspace. Warm low sun washes the BLUE
finger strip out (the localizer has a rescue pass for this, but diffuse light is far more
reliable) and the glare + hard shadows also hurt YOLO's object detection. Indoor/diffuse
lighting, or just closing the blinds, is ideal.

---

## 4. Start the vision server

Owns the webcam, runs YOLO tracking with **multiframe voting** (stable detection of
marginal objects like transparent bottles), and serves the live view + endpoints:

```sh
ARM_YOLO_MODEL=yolo11s-seg.pt .venv/bin/python vision_server.py   # then open http://localhost:8000
```

- `GET /`        — live annotated feed + object list
- `GET /color`   — latest detections as JSON (`detect_objects` reads this)
- `GET /frame`   — annotated JPEG (the `look` tool)
- `GET /raw`     — un-annotated JPEG (the grasp's measurements)

---

## 5. Register the MCP server

Stdio MCP server; use **absolute paths**:

```json
{
  "mcpServers": {
    "braccio": {
      "command": "/abs/path/to/mcp_arm/.venv/bin/python",
      "args": ["/abs/path/to/mcp_arm/server.py"],
      "env": {
        "ARM_WS_URL": "ws://<arm-ip>:81",
        "ARM_VISION_PORT": "8000"
      }
    }
  }
}
```

Tools: `get_pose`, `move_joints`, `move_xyz`, `set_gripper`, `set_speed`, `home`,
`detect_color`, `detect_objects`, `look`, `point_at`, `nudge`, `react_to_color`, and the
headliners — **`pick_object`** (the autonomous grasp of §6 as a single tool call, with a
vision-based `verify.grasped` verdict) and **`verify_grasp`**. Ask the AI to "pick up the
bottle" and it can run the whole detect → pick → verify → retry loop itself.
See `README.md` for the full reference.

---

## 6. The autonomous grasp (CLI)

```sh
ARM_WS_URL=ws://<arm-ip>:81 .venv/bin/python handeye.py --object bottle --vpick
```

What it does: homes, opens the jaw, learns the local image Jacobian with two probe moves,
visually servos the finger-gap onto the object (turning only while retracted — it will
never sweep sideways into the object), descends in measured stages, verifies, seats the
object deep in the jaw, closes, lifts. It **aborts safely** (and says why) rather than
close on a bad approach. `--pixel U V` grabs an arbitrary point; `--drinkable` picks any
cup/bottle/glass. Add `ARM_VPICK_DEBUG=1` for per-step prints + `/tmp/vstep_*.jpg` frames
— the first thing to check when a grab misbehaves.

---

## 7. On-site checklist

1. **Network / find the arm.** The firmware's WiFi credentials are baked in for the
   *original* network; either find the arm's IP on your LAN (`ARM_WS_URL=ws://<ip>:81`)
   or reflash (`arduino_secrets.h` + `robot_arm.ino`). Note: prefer the raw IP — `.local`
   names resolve slowly in Python and can time out the connection.
   Confirm: `ARM_WS_URL=ws://<ip>:81 .venv/bin/python server.py --selftest`.
2. **Tape the finger strips on** (green + blue, §1) if they aren't already.
3. **Place the camera** per §3 and start the vision server (§4).
4. **Dry run**: stand a bottle ~20–35 cm from the base, check it appears at
   `http://localhost:8000`, then run the grasp (§6). Two or three trial grabs are enough
   to confirm the room works.

---

## 8. Environment variable reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `ARM_WS_URL` | `ws://robotarm.local:81` | Arm WebSocket — **set to the arm's IP** |
| `ARM_VISION_PORT` | `8000` | Vision server port |
| `ARM_CAM_INDEX` | `0` | Webcam device index |
| `ARM_YOLO_MODEL` | `yolo11n-seg.pt` | Detection model; **use `yolo11s-seg.pt` for the demo** |
| `ARM_YOLO_CONF` | `0.15` | Detection threshold (voting suppresses false positives) |
| `ARM_VISION_VOTE_WINDOW` | `8` | Frames in the detection-voting window |
| `ARM_MARKER_A_HUE` / `B_HUE` | `55,95` / `96,130` | Finger-strip hue bands (green / blue) |
| `ARM_SERVO_Z` | `135` | Height (mm) the servo aligns at |
| `ARM_SERVO_GRAB_Z` | `100` | Grab height (mm) — mid-body for a 0.5 L bottle |
| `ARM_OBJ_HEIGHT` | `210` | Assumed target height (mm), sets the aim point |
| `ARM_FINGER_REACH_MM` | `30` | How deep the object seats in the jaw before closing |
| `ARM_SERVO_R_MAX` | `385` | Reach safety cap (mm); true max ~442 |
| `ARM_VPICK_DEBUG` | unset | `1` = per-step prints + `/tmp/vstep_*.jpg` debug frames |

`README.md` has the complete tool docs and vision/tuning details.
