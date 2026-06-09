# Braccio MCP — partner setup guide

This package contains the **Braccio arm MCP server**. It exposes the robot arm and a
webcam-based vision pipeline to an AI assistant over [MCP](https://modelcontextprotocol.io).
The physical arm will be delivered separately — this guide gets the software installed and
validated **ahead of time** so it works the moment the arm arrives.

The MCP server is a standard **stdio** server, so it works with any MCP-capable host
(Claude Desktop, Claude Code, your own client, etc.), not just the original setup.

---

## 1. Prerequisites

- **Python 3.10+** (`python3 --version`).
- **~1.5 GB free disk** for the virtual environment (it pulls in PyTorch + Ultralytics).
- **Internet** for the one-time `pip install` (the large dependencies download then cache).
  The YOLO model (`yolo11n-seg.pt`) is **bundled in this package**, so no model download is
  needed.
- A **USB or built-in webcam**.
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

That's the whole install. Everything below uses `.venv/bin/python`.

---

## 3. Validate now (no arm required)

You can confirm the install is healthy before the arm shows up:

```sh
# Inverse-kinematics self-test + WebSocket probe.
# IK checks pass offline; the WebSocket connect will fail with no arm — that's expected.
.venv/bin/python server.py --selftest

# One webcam capture through the YOLO detector (uses the bundled model, no download).
.venv/bin/python vision.py --test
```

If both run without import/camera errors, the software side is ready.

---

## 4. Start the vision server

The vision server owns the webcam and serves detections + an annotated live view. Run it in
its own (camera-permitted) terminal:

```sh
.venv/bin/python vision_server.py      # then open http://localhost:8000
```

- `GET /`        — live MJPEG feed with labelled detection boxes
- `GET /color`   — latest detection as JSON
- `GET /frame`   — latest annotated frame as a single JPEG (what the `look` tool fetches)

The MCP server reads this server's HTTP endpoints, so it can run anywhere on the same
machine. If the vision server is down, `detect_color` falls back to a one-shot direct
capture.

---

## 5. Register the MCP server with your AI host

This is a stdio MCP server. The exact config file/format depends on your host, but the
essentials are always **command + args + env**. Use **absolute paths** for your machine:

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

Once registered, the tools appear under the `braccio` server (`get_pose`, `move_joints`,
`move_xyz`, `set_gripper`, `home`, `detect_color`, `detect_objects`, `look`, `point_at`,
`nudge`, `react_to_color`). See `README.md` for the full tool reference and the intended
perceive → reason → act → self-correct loop.

---

## 6. On-site checklist (when the arm arrives)

1. **Network / find the arm.** The arm's firmware has WiFi credentials baked in for the
   *original* network, so it will **not** auto-join yours and `robotarm.local` likely won't
   resolve. Either:
   - find the arm's IP on your LAN and set `ARM_WS_URL=ws://<arm-ip>:81`, **or**
   - reflash the firmware (`arduino_secrets.h` + `robot_arm.ino`) with your WiFi SSID/password.

   Confirm the connection: `ARM_WS_URL=ws://<arm-ip>:81 .venv/bin/python server.py --selftest`.

2. **Re-run hand-eye calibration** for your camera + table placement (the shipped setup has
   **no** calibration file — it's specific to where the camera sits):
   ```sh
   .venv/bin/python calibrate.py        # regenerates calibration.json
   ```
   Until calibration exists, `point_at` uses a rough field-of-view guess and relies on the
   visual `look` + `nudge` loop — still functional, just less precise.

3. **Tune the aim mapping** if `point_at` turns the wrong way: set `ARM_CAM_FLIP=-1` if your
   webcam image is mirrored, and adjust `ARM_CAM_FOV_DEG` to your camera's horizontal field
   of view (default 55).

---

## 7. Environment variable reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `ARM_WS_URL` | `ws://robotarm.local:81` | Arm WebSocket URL — **set to the arm's IP** |
| `ARM_VISION_PORT` | `8000` | Vision server port |
| `ARM_VISION_URL` | `http://localhost:8000/color` | Detection JSON endpoint |
| `ARM_VISION_FRAME_URL` | `http://localhost:8000/frame` | Annotated frame endpoint (`look`) |
| `ARM_CAM_INDEX` | `0` | Webcam device index |
| `ARM_CAM_WIDTH` / `ARM_CAM_HEIGHT` | `640` / `480` | Capture resolution |
| `ARM_CAM_FOV_DEG` | `55` | Webcam horizontal FOV (seeds `point_at`) |
| `ARM_CAM_FLIP` | `1` | Pixel→base-angle sign; `-1` if image is mirrored |
| `ARM_YOLO_MODEL` | `yolo11n-seg.pt` | Detection model (bundled) |
| `ARM_YOLO_CONF` | `0.35` | Detection confidence threshold |
| `ARM_YOLO_DEVICE` | auto | `mps` on Apple Silicon, else `cpu` |
| `ARM_CALIB_PATH` | `./calibration.json` | Calibration file to load |

`README.md` has the complete tool docs, vision/tuning details, and the demo script.
