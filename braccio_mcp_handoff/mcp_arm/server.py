"""
server.py - MCP server exposing the Braccio arm as tools for an AI to drive.

Run as an MCP stdio server (default) or with --selftest to verify IK + connection.
Configured via env ARM_WS_URL (default ws://robotarm.local:81).
"""

import asyncio
import json
import os
import sys
import urllib.request
from typing import Optional

# Allow `import arm` when launched as a script.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP, Image
import arm as A
import handeye  # numpy-only calibration aim; no OpenCV, safe for the fast path
# NB: `vision` (OpenCV) is imported lazily inside the fallback path only, so the
# MCP server starts fast — the normal detect_color path just reads the vision
# server over HTTP and never touches OpenCV.

URL = os.environ.get("ARM_WS_URL", "ws://robotarm.local:81")
VISION_PORT = int(os.environ.get("ARM_VISION_PORT", "8000"))
VISION_URL = os.environ.get("ARM_VISION_URL", f"http://localhost:{VISION_PORT}/color")
FRAME_URL = os.environ.get("ARM_VISION_FRAME_URL", f"http://localhost:{VISION_PORT}/frame")

# Rough camera->base mapping for point_at's first guess. The visual loop
# (point_at -> look -> nudge) does the fine correction, so these only need to be
# in the right ballpark. CAM_FLIP is the sign: set -1 if the webcam image is mirrored.
CAM_FOV_DEG = float(os.environ.get("ARM_CAM_FOV_DEG", "55"))
CAM_FLIP = float(os.environ.get("ARM_CAM_FLIP", "1"))

client = A.ArmClient(URL)
mcp = FastMCP("braccio")


def _joints_dict(p):
    return {A.JOINT_NAMES[i]: p[i] for i in range(6)}


@mcp.tool()
async def get_pose() -> dict:
    """Current joint angles, fingertip position (mm, base at origin, Z up), and
    connection status."""
    await client.ensure()
    p = list(client.pose)
    return {"connected": client.connected, "joints": _joints_dict(p),
            "xyz": A.forward(p[0], p[1], p[2], p[3]), "raw": p}


@mcp.tool()
async def move_joints(base: int, shoulder: int, elbow: int, wrist_pitch: int,
                      wrist_rot: int, gripper: int, speed: Optional[int] = None,
                      wait: bool = True) -> dict:
    """Move all joints to absolute servo angles (degrees). Values are clamped to
    safe ranges. `speed` (deg/s, 20-300) is optional. Returns once settled."""
    await client.ensure()
    if speed is not None:
        await client.send(f"SPD:{int(A.clampv(speed, 20, 300))}")
    tgt = [int(A.clampv(v, A.POS_MIN[i], A.POS_MAX[i]))
           for i, v in enumerate([base, shoulder, elbow, wrist_pitch, wrist_rot, gripper])]
    await client.send("MOVE:" + ",".join(str(v) for v in tgt) + ",20")
    settled = await client.wait_settled(tgt) if wait else None
    return {"sent": _joints_dict(tgt), "settled": settled, "pose": list(client.pose)}


@mcp.tool()
async def move_xyz(x: float, y: float, z: float, approach: Optional[float] = None,
                   wrist_rot: Optional[int] = None, gripper: Optional[int] = None,
                   wait: bool = True, force: bool = False) -> dict:
    """Move the fingertip to (x,y,z) in mm (base at origin, Z up, +X forward) via
    inverse kinematics. `approach` is the hand angle from horizontal (-90 = straight
    down); omit it to auto-pick the angle. wrist_rot/gripper default to current.
    If the target is unreachable, nothing moves unless force=True (then it goes to
    the nearest clamped pose)."""
    await client.ensure()
    sol = A.solve_auto(x, y, z) if approach is None else A.solve_ik(x, y, z, approach)
    cur = list(client.pose)
    wr = cur[4] if wrist_rot is None else int(A.clampv(wrist_rot, A.POS_MIN[4], A.POS_MAX[4]))
    gr = cur[5] if gripper is None else int(A.clampv(gripper, A.POS_MIN[5], A.POS_MAX[5]))
    tgt = [sol["base"], sol["shoulder"], sol["elbow"], sol["wrist_pitch"], wr, gr]
    if not sol["reachable"] and not force:
        return {"reachable": False, "moved": False, "approach_used": sol["phi"],
                "would_send": _joints_dict(tgt),
                "note": "target out of reach; pass force=true to go to nearest pose"}
    await client.send("MOVE:" + ",".join(str(v) for v in tgt) + ",20")
    settled = await client.wait_settled(tgt) if wait else None
    return {"reachable": sol["reachable"], "moved": True, "approach_used": round(sol["phi"]),
            "joints": _joints_dict(tgt), "settled": settled, "pose": list(client.pose)}


@mcp.tool()
async def set_gripper(value: Optional[int] = None, action: Optional[str] = None,
                      wait: bool = True) -> dict:
    """Open/close the gripper only (the arm stays put). Use action 'open'/'close'
    or an explicit value (10=open .. 130=closed)."""
    await client.ensure()
    if action == "open":
        v = A.POS_MIN[5]
    elif action == "close":
        v = A.POS_MAX[5]
    elif value is not None:
        v = int(A.clampv(value, A.POS_MIN[5], A.POS_MAX[5]))
    else:
        return {"error": "provide value (10-130) or action 'open'/'close'"}
    await client.send(f"J:5:{v}")
    settled = None
    if wait:
        tgt = list(client.pose)
        tgt[5] = v
        settled = await client.wait_settled(tgt)
    return {"gripper": v, "settled": settled}


@mcp.tool()
async def set_speed(deg_per_s: int) -> dict:
    """Set arm move speed (degrees/second, 20-300)."""
    await client.ensure()
    s = int(A.clampv(deg_per_s, 20, 300))
    await client.send(f"SPD:{s}")
    return {"speed": s}


@mcp.tool()
async def home(wait: bool = True) -> dict:
    """Move the arm to the home pose (all joints 90, gripper 73)."""
    await client.ensure()
    await client.send("MOVE:90,90,90,90,90,73,20")
    settled = await client.wait_settled(A.HOME) if wait else None
    return {"settled": settled, "pose": list(client.pose)}


# --- Vision: color detection + per-color reactions ---------------------------

def _read_vision_server(timeout=1.5):
    with urllib.request.urlopen(VISION_URL, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


async def _detect():
    """Latest color: prefer the running vision server (matches the browser view),
    else fall back to a one-shot direct camera capture."""
    try:
        res = await asyncio.to_thread(_read_vision_server)
        res["source"] = "vision_server"
        return res
    except Exception:
        try:
            import vision as V  # lazy: OpenCV only loads if the server is down
            res = await asyncio.to_thread(V.detect_once)
            res["source"] = "direct_capture"
            return res
        except Exception as e:
            return {"color": "none", "confidence": 0.0, "error": str(e),
                    "note": "vision server not reachable and direct capture failed"}


@mcp.tool()
async def detect_color() -> dict:
    """Detect the dominant color of the object held up to the webcam. Reads the
    running vision server (so it matches the live browser view at
    http://localhost:8000); if that server isn't running, falls back to a
    one-shot direct camera capture. Returns {color, hue, rgb, confidence,
    source}. Does not move the arm."""
    return await _detect()


@mcp.tool()
async def detect_objects() -> dict:
    """The full scene the camera sees, for reasoning about what's there and picking a
    target. Returns {frame:[W,H], count, objects:[...]} where each object has
    {track_id, object (class name), color, det_score, bbox:[x,y,w,h], center:[cx,cy],
    center_norm:[u,v], area_frac}. `center_norm` is normalized to [-1,1] with (0,0) at the
    frame centre, +u to the right and +v down -- feed an object's `u` to `point_at`.
    Does not move the arm. Reads the running vision server."""
    res = await _detect()
    objects = res.get("objects", []) or []
    return {"frame": res.get("frame"), "count": len(objects), "objects": objects,
            "source": res.get("source")}


def _read_frame_bytes(timeout=2.0):
    with urllib.request.urlopen(FRAME_URL, timeout=timeout) as r:
        return r.read()


@mcp.tool()
async def look() -> Image:
    """Return the current camera frame (annotated with detection boxes) as an image so you
    can SEE the scene -- including the arm's own gripper -- and reason about it visually.
    Use this to check where the gripper ended up versus a target and to self-correct: a
    typical loop is detect_objects -> point_at -> look -> nudge -> look. Requires the vision
    server to be running. Does not move the arm."""
    jpeg = await asyncio.to_thread(_read_frame_bytes)
    return Image(data=jpeg, format="jpeg")


# Outstretched "presenting" pose (shoulder/elbow/wrist) used when pointing, so the
# gripper extends forward into the scene; only the base swings to aim horizontally.
_POINT_POSE = [90, 55, 70, 90, 90, A.HOME[5]]


@mcp.tool()
async def point_at(track_id: Optional[int] = None, u: Optional[float] = None,
                   wait: bool = True) -> dict:
    """Aim the gripper at a target. Give either a `track_id` from detect_objects
    (preferred) or a raw `u` in [-1,1] (object's horizontal screen position, 0=centre).

    If a hand-eye calibration exists (calibration.json from calibrate.py) AND a target
    pixel is available (the track_id path), this solves for the pose whose gripper
    *projects onto the target pixel* -- an accurate aim in both axes. Otherwise it falls
    back to a rough base-only FOV guess (approximate; follow up with `look` + `nudge`).
    Returns the method used, the pose, and (calibrated path) the residual pixel error."""
    await client.ensure()
    P = handeye.load_P()
    target_px = None
    if track_id is not None:
        scene = await _detect()
        match = next((o for o in scene.get("objects", [])
                      if o.get("track_id") == track_id), None)
        if match is None:
            return {"error": f"track_id {track_id} not in view", "scene": scene.get("objects")}
        target_px = match["center"]
        if u is None:
            u = match["center_norm"][0]

    # Calibrated aim: need a full pixel (track_id) and a loaded calibration.
    if target_px is not None and P is not None:
        aim = handeye.aim_joints(P, float(target_px[0]), float(target_px[1]))
        cur = list(client.pose)
        tgt = [aim["base"], aim["shoulder"], aim["elbow"], aim["wrist_pitch"], cur[4], cur[5]]
        pose = await _move(tgt, speed=120, wait=wait)
        return {"method": "calibration", "track_id": track_id, "target_px": target_px,
                "predicted_px": [round(v, 1) for v in aim["pred_px"]],
                "residual_px": round(aim["err_px"], 1), "pose": pose,
                "note": "calibrated aim: gripper projected onto the target pixel"}

    # Fallback: rough base-only swing from the horizontal position.
    if u is None:
        return {"error": "pass track_id (preferred) or u"}
    u = max(-1.0, min(1.0, float(u)))
    base = A.clampv(round(90 - CAM_FLIP * u * (CAM_FOV_DEG / 2.0)), A.POS_MIN[0], A.POS_MAX[0])
    tgt = [int(base)] + _POINT_POSE[1:]
    pose = await _move(tgt, speed=140, wait=wait)
    return {"method": "fov_guess", "u": round(u, 3), "base": int(base), "track_id": track_id,
            "pose": pose, "note": "no calibration (or no pixel): approximate aim; "
                                  "use look + nudge, or run calibrate.py for accurate aim"}


@mcp.tool()
async def nudge(joint: str, delta: int, wait: bool = True) -> dict:
    """Relative single-joint adjustment for fine correction while watching via `look`
    (e.g. nudge('base', -5) to turn left, nudge('wrist_pitch', 8) to tip the hand up).
    `joint` is one of base, shoulder, elbow, wrist_pitch, wrist_rot, gripper; `delta` is
    degrees (+/-). Returns the resulting pose."""
    await client.ensure()
    if joint not in A.JOINT_NAMES:
        return {"error": f"unknown joint {joint!r}", "joints": A.JOINT_NAMES}
    i = A.JOINT_NAMES.index(joint)
    tgt = list(client.pose)
    tgt[i] = int(A.clampv(tgt[i] + delta, A.POS_MIN[i], A.POS_MAX[i]))
    pose = await _move(tgt, wait=wait)
    return {"joint": joint, "delta": delta, "value": tgt[i], "pose": pose}


async def _move(tgt, speed=None, wait=True):
    """Send a coordinated MOVE to a clamped 6-joint target (optionally set speed)."""
    if speed is not None:
        await client.send(f"SPD:{int(A.clampv(speed, 20, 300))}")
    t = [int(A.clampv(v, A.POS_MIN[i], A.POS_MAX[i])) for i, v in enumerate(tgt)]
    await client.send("MOVE:" + ",".join(str(v) for v in t) + ",20")
    if wait:
        await client.wait_settled(t)
    return t


# --- Autonomous grasp (visual servoing; no calibration needed) -----------------

async def _verify_grasp_scene(object_name, prev_center, radius_px=70):
    """Vision-only grasp check. The firmware reports COMMANDED servo angles (not measured),
    so there is no proprioceptive grip feedback -- the camera is the only truth."""
    scene = await _detect()
    objs = scene.get("objects", []) or []
    if object_name:
        objs = [o for o in objs if (o.get("object") or "").lower() == object_name.lower()]
    if prev_center is None:
        return {"grasped": None, "scene": scene.get("objects"),
                "note": "no pre-grasp position to compare against -- judge with look()"}
    still = [o for o in objs
             if o.get("center")
             and (o["center"][0] - prev_center[0]) ** 2
             + (o["center"][1] - prev_center[1]) ** 2 <= radius_px ** 2]
    if still:
        return {"grasped": False, "still_there": still, "scene": scene.get("objects"),
                "evidence": f"a matching object is still detected within {radius_px}px of "
                            f"its pre-grasp position {list(prev_center)}"}
    return {"grasped": True, "scene": scene.get("objects"),
            "evidence": f"no matching object remains near its pre-grasp position "
                        f"{list(prev_center)} (lifted, or occluded by the gripper). "
                        f"Confirm with look() if it matters."}


@mcp.tool()
async def pick_object(track_id: Optional[int] = None, object_name: Optional[str] = None,
                      u: Optional[float] = None, v: Optional[float] = None,
                      speed: int = 50) -> dict:
    """Autonomously PICK UP an object by visual servoing -- the full grab: aim, approach,
    verify, close, lift. SLOW (1-3 minutes) and moves the arm extensively; tell the user
    before calling. Target by `track_id` from detect_objects (preferred), by `object_name`
    (a detected class, e.g. 'bottle'), or by a raw pixel (u, v).

    Needs the vision server running AND the two coloured marker strips on the gripper
    fingers (see HANDOFF.md). No hand-eye calibration needed: the camera<->arm map is
    re-learned every grab, so a moved camera is fine.

    Returns the grasp diagnostics. On success it includes `verify.grasped` (vision-based;
    there is no force feedback on this arm). It ABORTS safely with an `error` explaining
    why rather than close on a bad approach -- the retry loop is YOURS: if grasped is
    false/null or it aborted, `look()`, re-run detect_objects, and call again (each
    attempt starts by homing, so no cleanup needed between tries)."""
    await client.ensure()
    try:
        # the vision server specifically (not _detect()'s direct-capture fallback, which
        # would pointlessly load YOLO here): the grasp needs its /raw endpoint anyway
        scene = await asyncio.to_thread(_read_vision_server)
    except Exception:
        return {"error": "vision server not reachable -- pick_object requires it (it serves "
                         "/raw for the gripper localizer). Start vision_server.py and retry."}
    match, label, prev_center = None, None, None
    if track_id is not None:
        match = next((o for o in scene.get("objects", [])
                      if o.get("track_id") == track_id), None)
        if match is None:
            return {"error": f"track_id {track_id} not in view (ids churn when the arm "
                             f"occludes things -- re-run detect_objects)",
                    "scene": scene.get("objects")}
    elif object_name:
        match = handeye.choose_object(scene, object_name=object_name)
        if match is None:
            return {"error": f"no {object_name!r} detected", "scene": scene.get("objects")}
    if match is not None:
        target_px = handeye.vpick_pixel(match)       # the object's point at servo height
        prev_center = match.get("center")
        label = f'{match.get("object")} #{match.get("track_id")}'
        object_name = object_name or match.get("object")
    elif u is not None and v is not None:
        target_px = (float(u), float(v))
        prev_center = [int(u), int(v)]
        label = f"pixel ({u:.0f},{v:.0f})"
    else:
        return {"error": "pass track_id (preferred), object_name, or a raw pixel (u, v)"}
    res = await handeye.visual_pick(client, target_px,
                                    speed=int(A.clampv(speed, 20, 200)))
    res["target"] = label
    if res.get("ok"):
        res["verify"] = await _verify_grasp_scene(object_name, prev_center)
    return res


@mcp.tool()
async def verify_grasp(object_name: Optional[str] = None,
                       prev_center_u: Optional[float] = None,
                       prev_center_v: Optional[float] = None) -> dict:
    """Vision-based check of whether the last grasp is holding: re-detects the scene and
    compares against the object's pre-grasp position (pass the `center` you saw in
    detect_objects before picking). grasped=false means a matching object still sits where
    it was (the grab missed); true means it is gone from there (lifted -- or occluded);
    null means not enough information, judge with look(). Does not move the arm."""
    prev = None
    if prev_center_u is not None and prev_center_v is not None:
        prev = (float(prev_center_u), float(prev_center_v))
    return await _verify_grasp_scene(object_name, prev)


async def _gesture_wave():
    """red -> raise arm and waggle the wrist rotation a few times."""
    p = list(client.pose)
    await _move([p[0], 70, 60, 90, 90, p[5]], speed=180)
    for v in (140, 40, 140, 40, 90):
        await client.send(f"J:4:{v}")
        await asyncio.sleep(0.45)
    return "wave"


async def _gesture_nod():
    """yellow -> raise arm and nod the wrist pitch up/down."""
    p = list(client.pose)
    await _move([p[0], 80, 90, 90, p[4], p[5]], speed=180)
    for v in (130, 55, 130, 55, 90):
        await client.send(f"J:3:{v}")
        await asyncio.sleep(0.45)
    return "nod"


async def _gesture_reach():
    """green -> reach forward via IK, close then open the gripper, return home."""
    sol = A.solve_auto(200, 0, 40)
    await _move([sol["base"], sol["shoulder"], sol["elbow"], sol["wrist_pitch"],
                 90, A.POS_MIN[5]], speed=140)
    await client.send(f"J:5:{A.POS_MAX[5]}")   # close
    await asyncio.sleep(0.8)
    await client.send(f"J:5:{A.POS_MIN[5]}")   # open
    await asyncio.sleep(0.8)
    await _move(A.HOME, speed=140)
    return "reach_grab"


async def _gesture_home():
    """blue -> return to the home pose."""
    await _move(A.HOME, speed=140)
    return "home"


GESTURES = {"red": _gesture_wave, "green": _gesture_reach,
            "blue": _gesture_home, "yellow": _gesture_nod}


@mcp.tool()
async def react_to_color(color: Optional[str] = None) -> dict:
    """Detect the held color (or use the `color` you pass) and run the matching
    gesture: red=wave, green=reach+grab, blue=home, yellow=nod. Any other color
    (or 'none') does nothing. Returns the detection, the color, and the action
    performed."""
    await client.ensure()
    detected = None
    if color is None:
        detected = await _detect()
        color = detected.get("color", "none")
    fn = GESTURES.get(color)
    if fn is None:
        return {"detected": detected, "color": color, "action": "none",
                "note": "no gesture mapped for this color"}
    action = await fn()
    return {"detected": detected, "color": color, "action": action,
            "pose": list(client.pose)}


async def _selftest():
    print("=== IK / FK round-trip ===")
    for (x, y, z) in [(150, 0, 100), (0, 150, 150), (120, -80, 60), (250, 0, 60)]:
        s = A.solve_auto(x, y, z)
        fk = A.forward(s["base"], s["shoulder"], s["elbow"], s["wrist_pitch"])
        err = ((fk["x"] - x) ** 2 + (fk["y"] - y) ** 2 + (fk["z"] - z) ** 2) ** 0.5
        print(f"  target=({x:>4},{y:>4},{z:>4}) reachable={s['reachable']!s:>5} "
              f"approach={s['phi']:>4} joints={[s['base'],s['shoulder'],s['elbow'],s['wrist_pitch']]} "
              f"FK_err={err:5.1f}mm")
    print("=== connection ===")
    try:
        await asyncio.wait_for(client.connect(), 5)
        await asyncio.sleep(1.0)
        print(f"  connected to {URL}; pose={client.pose}")
    except Exception as e:
        print(f"  could not connect to {URL}: {e!r} (arm powered + on WiFi?)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        asyncio.run(_selftest())
    else:
        mcp.run()
