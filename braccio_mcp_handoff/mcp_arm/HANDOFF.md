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
  The default YOLO model (`yolo11s-seg.pt`, ~20 MB) downloads automatically on first use;
  the smaller bundled `yolo11n-seg.pt` works offline (`ARM_YOLO_MODEL=yolo11n-seg.pt`).
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
- **Bad — servo can't converge**: too **shallow a down-tilt** or too **far away**. At a
  near-level view some arm direction always points along the camera axis and becomes
  invisible; from too far, every mm of motion is under a pixel. Think "CCTV over a
  checkout counter": ~45° down, close enough that the target object is ~1/5 of the frame
  height. Each grab reports `jacobian_sin` in its diagnostics — it must be ≥ 0.35 to
  steer at all, and 0.6+ is where grabs get reliable.

No calibration is needed after moving the camera — the grasp re-learns the mapping each
run. The arm's base should be weighed down or held; it is top-heavy at full reach.
Keep the object within ~350 mm of the base: at full stretch the arm sags under its own
weight and the grab height the servo believes in no longer matches reality.

**Lighting**: avoid harsh direct sunlight on the workspace. Warm low sun washes the BLUE
finger strip out (the localizer has a rescue pass for this, but diffuse light is far more
reliable) and the glare + hard shadows also hurt YOLO's object detection. Indoor/diffuse
lighting, or just closing the blinds, is ideal.

---

## 4. Start the vision server

Owns the webcam, runs YOLO tracking with **multiframe voting** (stable detection of
marginal objects like transparent bottles), and serves the live view + endpoints:

```sh
.venv/bin/python vision_server.py   # then open http://localhost:8000
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
        "ARM_VISION_PORT": "8000",
        "ARM_TARGET_REFRESH_PX": "0",
        "ARM_OBJ_HEIGHT": "165"
      }
    }
  }
}
```

The two extra env values are the field-tested settings from the 2026-06-12 debugging
session (grabbing a ~16.5 cm slim can): `ARM_TARGET_REFRESH_PX=0` locks the aim to the
pre-grab detection pixel — with long coasting (`ARM_VISION_VOTE_WINDOW=30`) the
post-alignment refresh could snap to a stale bbox and abort; `ARM_OBJ_HEIGHT` must match
the real target height or the servo aims past/short of it (the default assumes a 21 cm
bottle). Set `ARM_OBJ_HEIGHT` to your object's height in mm.

Tools: `get_pose`, `move_joints`, `move_xyz`, `set_gripper`, `set_speed`, `home`,
`detect_color`, `detect_objects`, `look`, `point_at`, `nudge`, `react_to_color`, and the
headliners — **`pick_object`** (the autonomous grasp of §6 as a single tool call, with a
vision-based `verify.grasped` verdict) and **`verify_grasp`**. Ask the AI to "pick up the
bottle" and it can run the whole detect → pick → verify → retry loop itself.
See `README.md` for the full reference.

### Vision server on a separate machine

The MCP server is a pure HTTP **client** of the vision server — they do not need to share
a machine. Run the vision server wherever the **webcam is plugged in**; it binds
`0.0.0.0`, so its dashboard and endpoints are reachable across the LAN. Point the MCP
host at it by adding three URLs to the `env` block above:

```json
"ARM_VISION_URL":       "http://<vision-host-ip>:8000/color",
"ARM_VISION_FRAME_URL": "http://<vision-host-ip>:8000/frame",
"ARM_VISION_RAW_URL":   "http://<vision-host-ip>:8000/raw"
```

**Verify from any browser on the network**: open `http://<vision-host-ip>:8000/` — the
live annotated feed plus the detected-object list. (`/color` shows the raw JSON.) Find the
host's IP with `ipconfig getifaddr en0` (macOS) or `hostname -I` (Linux) — and re-check it
at the venue; DHCP hands out different addresses on different networks.

Notes:
- The MCP host still needs its own venv (the grasp decodes camera frames locally with
  OpenCV) but needs **no camera**, and YOLO never loads there while the vision server is
  reachable.
- macOS firewall (if enabled) pops an "allow incoming connections?" dialog for Python the
  first time the vision server starts — click Allow. No port rules needed.
- **Venue Wi-Fi warning**: guest/corporate networks often have *client isolation*, which
  silently blocks device-to-device traffic — that kills both the vision HTTP **and** the
  arm's WebSocket, and nothing on your machines can fix it. The robust setup is your own
  network: a phone hotspot or travel router that the arm, the vision host, and the MCP
  host all join (and confirm all three are on the same subnet).

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
| `ARM_VISION_URL` | `http://localhost:8000/color` | Detection JSON endpoint (set to the vision host) |
| `ARM_VISION_FRAME_URL` | `http://localhost:8000/frame` | Annotated frame endpoint (`look`) |
| `ARM_VISION_RAW_URL` | `http://localhost:8000/raw` | Clean frame endpoint (the grasp's measurements) |
| `ARM_CAM_INDEX` | `0` | Webcam device index |
| `ARM_YOLO_MODEL` | `yolo11s-seg.pt` | Detection model (`yolo11n-seg.pt` is bundled for offline) |
| `ARM_YOLO_CONF` | `0.10` | Detection threshold (voting suppresses false positives) |
| `ARM_YOLO_TRACKER` | `tracker.yaml` | BoT-SORT config (low-conf tracks, 90-frame occlusion buffer) |
| `ARM_VISION_VOTE_WINDOW` | `30` | Frames in the detection-voting window (also the coast horizon) |
| `ARM_MARKER_A_HUE` / `B_HUE` | `55,95` / `96,130` | Finger-strip hue bands (green / blue) |
| `ARM_SERVO_Z` | `135` | Height (mm) the servo aligns at |
| `ARM_SERVO_GRAB_Z` | `100` | Grab height (mm) — mid-body for a 0.5 L bottle |
| `ARM_OBJ_HEIGHT` | `210` | Assumed target height (mm), sets the aim point — **set to your object's real height** (a wrong value makes the grab plow past or close short of the object) |
| `ARM_TARGET_REFRESH_PX` | `60` | Post-alignment aim refresh radius; `0` (recommended) locks the aim to the pre-grab pixel — coasted detections can feed the refresh stale positions |
| `ARM_MARKER_STABLE_PX` | `2.5` | Marker reads must agree across two consecutive frames within this many px (rejects mid-motion/ringing measurements that corrupt the learned Jacobian) |
| `ARM_MARKER_STABLE_TRIES` | `12` | Read budget (~2 s) to find a stable pair before falling back to a median |
| `ARM_FINGER_REACH_MM` | `30` | How deep the object seats in the jaw before closing |
| `ARM_SERVO_R_MAX` | `385` | Reach safety cap (mm); true max ~442 |
| `ARM_VPICK_DEBUG` | unset | `1` = per-step prints + `/tmp/vstep_*.jpg` debug frames |

`README.md` has the complete tool docs and vision/tuning details.
