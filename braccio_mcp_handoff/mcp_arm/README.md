# Braccio MCP server (Phase 1 — control)

Exposes the Braccio arm to an AI (Claude) over MCP. It connects to the Arduino
firmware's WebSocket (`ws://robotarm.local:81`), owns the inverse kinematics
(ported from the web UI), and offers tools to command the arm.

## Setup

```sh
cd mcp_arm
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Test the kinematics and the arm connection (arm powered + on WiFi):

```sh
ARM_WS_URL=ws://robotarm.local:81 .venv/bin/python server.py --selftest
```

If `robotarm.local` doesn't resolve, use the arm's IP, e.g.
`ARM_WS_URL=ws://192.168.1.42:81`.

## Register with Claude Code

`.mcp.json` at the repo root already points here. After creating the venv,
restart Claude Code and approve the `braccio` MCP server; the tools appear as
`mcp__braccio__*`.

## Tools

- `get_pose` — joint angles + fingertip xyz (mm) + connection status
- `move_joints(base, shoulder, elbow, wrist_pitch, wrist_rot, gripper, speed?, wait?)`
- `move_xyz(x, y, z, approach?, wrist_rot?, gripper?, wait?, force?)` — IK move;
  reports `reachable` and won't move to unreachable targets unless `force=true`
- `set_gripper(value | action='open'|'close')` — gripper only (arm stays put)
- `set_speed(deg_per_s)` — 20–300
- `home()`
- `detect_color()` — dominant color of the object held to the webcam
  (`{color, hue, rgb, confidence, source}`); reads the vision server, falls back
  to a one-shot direct capture. Does not move the arm.
- `react_to_color(color?)` — detect (or take a given color) and run the matching
  gesture: **red**=wave, **green**=reach+grab, **blue**=home, **yellow**=nod.

### Perception + reasoning (the AI-enabled loop)

These let Claude *see* the scene, reason about it, act, and **visually self-correct** by
watching its own gripper — no hand-eye calibration needed. The camera must be framed so it
sees **both the objects and the arm's gripper**.

- `detect_objects()` — the whole scene as structured data for reasoning/target-picking:
  `{frame:[W,H], count, objects:[{track_id, object, color, det_score, bbox, center,
  center_norm:[u,v], area_frac}]}`. `center_norm` is in `[-1,1]`, `(0,0)` = frame centre,
  `+u` right / `+v` down. Does not move the arm.
- `look()` — returns the current annotated camera frame **as an image** so Claude can see
  the scene (and the gripper) and reason spatially. The visual-feedback half of the loop.
- `point_at(track_id? | u?, wait?)` — coarse horizontal aim: strikes an outstretched
  pointing pose and swings the base toward the target (a `track_id` from `detect_objects`,
  or a raw `u`). Approximate by design — refine with `look` + `nudge`.
- `nudge(joint, delta, wait?)` — relative single-joint tweak for fine correction
  (`nudge('base', -5)` to turn left, `nudge('wrist_pitch', 8)` to tip up).
- `pick_object(track_id? | object_name? | u?, v?, speed?)` — **autonomously grab an
  object** (the visual-servo grasp below, as one tool call; slow, 1–3 min). Returns the
  grasp diagnostics + a vision-based `verify.grasped` verdict. Aborts safely with a
  reason rather than close on a bad approach — the AI owns the retry loop.
- `verify_grasp(object_name?, prev_center_u?, prev_center_v?)` — re-detect and judge
  whether the last grab is holding (no force feedback exists; the camera is the truth).

**Typical AI loop:** `detect_objects` → `point_at(target)` → `look` (see the offset) →
`nudge` → `look` again. Claude judges the gripper-vs-target error by eye, so a rough camera
is fine.

Coordinates: millimetres, base pivot at the origin, **Z up**, **+X straight
forward** (base servo 90). Approach angle is degrees from horizontal
(`-90` = straight down). Link lengths in `arm.py` (`L0..L3`) are approximate —
tune them on the real arm for accuracy.

Tip: keep the web UI open while driving via MCP — the firmware broadcasts pose to
all clients, so the 3D/2D graphs mirror MCP-driven motion.

## Vision (YOLO object detection + color)

A YOLO model (Ultralytics) localizes objects anywhere in the frame, and for each
detection we sample the color from the object's own pixels (segmentation mask, else
the box crop) — far more robust than the old fixed center-ROI HSV vote, and it also
tells us *what* the object is. `vision_server.py` owns the webcam, runs **tracking**
(persistent IDs across frames), and serves a live annotated view so you can see and
tune detection **before** involving the arm. `detect_color` (and the fallback in
`vision.py`) share the same detector, so the browser view matches what the arm reacts to.

```sh
.venv/bin/python vision_server.py      # then open http://localhost:8000
```

- `GET /` — live MJPEG feed; each box is captioned `class color #id score`, plus a
  panel listing every detected object
- `GET /color` — latest detection as JSON: top-level `{color, hue, rgb, confidence,
  object, track_id, frame, ...}` describe the primary (highest-score) object, and
  `objects` is the full list of `{track_id, object, color, hue, rgb, det_score, bbox,
  center, center_norm, area_frac}` (what `detect_objects` returns)
- `GET /frame` — the latest annotated frame as a single JPEG (what the `look` tool fetches)

The detection schema is backward-compatible: the old top-level `color/hue/rgb/confidence`
keys are still present (now describing the primary object).

**Model / tuning** (env vars):

- `ARM_YOLO_MODEL` (default `yolo11s-seg.pt`) — any Ultralytics model; `-seg` variants
  give per-object masks for cleaner color sampling. **Downloaded automatically on first
  run** (~20 MB, needs internet; cached afterward).
- `ARM_YOLO_CONF` (default `0.10`) — detection confidence threshold; deliberately low so
  marginal objects stay visible (the server's multiframe voting suppresses the noise);
  raise it if you get persistent spurious boxes.
- `ARM_YOLO_TRACKER` (default `tracker.yaml` next to `vision.py`) — BoT-SORT config tuned
  to give low-confidence objects track ids and keep them through ~90 frames of occlusion.
- `ARM_YOLO_DEVICE` (default auto) — `mps` on Apple Silicon, else `cpu`.
- `ARM_YOLO_MAX` (default `10`) — cap on reported detections.

Color-naming bins still live in `vision.py` as `COLOR_RANGES` (hue bins) with
`SAT_MIN` / `VAL_MIN` (background rejection) — edit and the live page updates.

**Aim mapping** (for `point_at`, in `server.py`): `ARM_CAM_FOV_DEG` (default `55`) is the
webcam's horizontal field of view, and `ARM_CAM_FLIP` (default `1`; set `-1` if the image
is mirrored) is the sign of the pixel→base-angle map. These only seed `point_at`'s first
guess — the `look`/`nudge` loop does the fine correction — so just get them in the right
ballpark. Tune once by pointing at a known object and checking the arm turns the right way.

Quick checks without the server:

```sh
.venv/bin/python vision.py --image path/to/photo.jpg   # detect on a still (no camera)
.venv/bin/python vision.py --test                      # one webcam capture
```

**macOS camera permission:** OpenCV's camera access is granted to the *app that
launches Python*, via System Settings → Privacy & Security → Camera. Newer
terminals (e.g. **Rio**) don't register with macOS TCC and can't get camera
access at all. If your terminal can't open the camera, launch `vision_server.py`
from **Terminal.app** or **iTerm2** (they prompt correctly) — it's a standalone
process, so the MCP server and Claude session can run anywhere and still read its
`/color` endpoint.

## AI-enabled demo

The point of the perception+reasoning tools is a **live, conversational demo where Claude
is the brain**: it understands what you ask, perceives the scene, decides what to do, and
self-corrects by watching its own gripper. Set up a **fixed camera** that sees both the
objects and the gripper, start `vision_server.py` (camera-permitted terminal), power the
arm, then talk to Claude:

1. **"What are you looking at?"** — Claude calls `detect_objects` + `look` and narrates the
   scene (what, where, colour). *Perception + grounding.*
2. **"Point at the thing I could drink from."** — Claude *reasons* that a cup/bottle qualifies
   (not a hardcoded match), `point_at`s it, `look`s, sees the gripper is off, `nudge`s, and
   `look`s again to confirm. *Reasoning + visual self-correction — the headline moment.*
3. **"Wave at the person."** — find the person, `point_at` to orient toward them, then the
   `react_to_color`-style wave gesture.
4. **"Show me you're curious / celebrate."** — Claude *improvises* a motion via `move_joints`
   — behaviour authored by the model, not a lookup table.

The contrast to sell: this isn't a fixed color→gesture script; the camera is Claude's eyes,
the tools are its hands, and the decisions are the model's.

## Autonomous grasp (visual servoing, no calibration)

`handeye.py --vpick` picks up a detected object hands-off:

```sh
ARM_WS_URL=ws://<arm-ip>:81 .venv/bin/python handeye.py --object bottle --vpick
```

It locates the gripper by two coloured paper strips taped on the fingers (green + blue),
learns the local image↔arm Jacobian online each grab (immune to the camera being moved),
visually servos the finger gap onto the object — turning only while retracted, so it can't
sweep sideways into it — then descends in measured stages, verifies, seats, closes, lifts.
It aborts with a reason rather than close on a bad approach. Setup requirements (finger
strips, camera placement) and tuning knobs are documented in `HANDOFF.md`; debug with
`ARM_VPICK_DEBUG=1` (per-step prints + `/tmp/vstep_*.jpg`).

## Roadmap
- Phase 3 (done): hand-eye — solved calibration-FREE by per-grab visual servoing (above);
  the calibrate.py DLT/homography path remains for the calibrated `point_at`/`--pick`.
- Phase 4 (done): autonomous pick, exposed over MCP as `pick_object` + `verify_grasp` —
  the AI runs the grab-verify-retry loop itself.
