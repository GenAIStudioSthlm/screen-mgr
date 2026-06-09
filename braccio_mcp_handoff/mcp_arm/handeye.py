"""
handeye.py - use a hand-eye calibration to aim the arm at what the camera sees.

Loads whatever calibration.json calibrate.py produced for the CURRENT camera
placement (so it is portable: re-calibrate in a new room, this just works), and
turns a target image pixel into the joint pose whose gripper visually lands on
that pixel. NumPy-only (no OpenCV), so it is safe to import from the MCP server's
fast path.

Library:
  load_P(path=None)            -> 3x4 projection matrix (np.array) or None
  project(P, x, y, z)          -> (u, v) pixel for an arm-frame point (mm)
  aim_joints(P, u_px, v_px)    -> {base, shoulder, elbow, wrist_pitch, pred_px, err_px}

CLI (drives the arm; reads detections from the vision server /color):
  python handeye.py --pixel 439 256        # aim the gripper at a pixel
  python handeye.py --object bottle        # aim at a detected class by name
  python handeye.py --drinkable            # aim at the first drink-like object
  python handeye.py --object bottle --dry  # compute + print only, do not move
"""

import argparse
import asyncio
import json
import os
import urllib.request

import numpy as np

import arm as A

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CALIB = os.environ.get("ARM_CALIB_PATH",
                               os.environ.get("ARM_CALIB_OUT",
                                              os.path.join(_HERE, "calibration.json")))
VISION_PORT = int(os.environ.get("ARM_VISION_PORT", "8000"))
COLOR_URL = os.environ.get("ARM_VISION_URL", f"http://localhost:{VISION_PORT}/color")
WS_URL = os.environ.get("ARM_WS_URL", "ws://robotarm.local:81")

# Things a person can drink from -- used by --drinkable and "point at a drink".
DRINKABLE = {"bottle", "cup", "wine glass"}


def load_P(path=None):
    """The 3x4 projection matrix from calibration.json, or None if not calibrated."""
    path = path or DEFAULT_CALIB
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        data = json.load(fh)
    P = data.get("P")
    return np.asarray(P, float) if P is not None else None


def _cv2_cam(path=None):
    """The cv2 pinhole+distortion model from calibration.json, or None (then use the linear P).
    Read per-call (cheap) so a fresh calibration is picked up without restart."""
    path = path or DEFAULT_CALIB
    if not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            d = json.load(fh)
    except Exception:
        return None
    if d.get("model") != "cv2_pinhole":
        return None
    return {"K": np.asarray(d["K"], float), "dist": np.asarray(d["dist"], float),
            "rvec": np.asarray(d["rvec"], float), "tvec": np.asarray(d["tvec"], float),
            "R": np.asarray(d["R"], float)}


def project(P, x, y, z):
    """Arm-frame point (mm) -> predicted image pixel (u, v). Uses the cv2 model (with lens
    distortion) when available, else the linear projection matrix P."""
    cam = _cv2_cam()
    if cam is not None:
        import cv2
        pp = cv2.projectPoints(np.array([[x, y, z]], float), cam["rvec"], cam["tvec"],
                               cam["K"], cam["dist"])[0]
        return float(pp[0, 0, 0]), float(pp[0, 0, 1])
    v = np.asarray(P) @ np.array([x, y, z, 1.0])
    return v[0] / v[2], v[1] / v[2]


def pixel_to_plane(P, u, v, z):
    """Back-project image pixel (u, v) onto the arm-frame plane Z=z -> (x, y) mm. With the cv2
    model: undistort the pixel, cast the camera ray into the arm frame, intersect Z=z. Else
    solve the linear  s*[u,v,1]^T = P[x,y,z,1]^T. Depth-correct grasping from one camera."""
    cam = _cv2_cam()
    if cam is not None:
        import cv2
        n = cv2.undistortPoints(np.array([[[float(u), float(v)]]], float),
                                cam["K"], cam["dist"])[0, 0]
        d_cam = np.array([n[0], n[1], 1.0])
        R, t = cam["R"], cam["tvec"].reshape(3)
        C = -R.T @ t                       # camera centre in arm frame
        d_world = R.T @ d_cam              # ray direction in arm frame
        s = (z - C[2]) / d_world[2]
        p = C + s * d_world
        return float(p[0]), float(p[1])
    Pm = np.asarray(P, float)
    p1, p2, p3, p4 = Pm[:, 0], Pm[:, 1], Pm[:, 2], Pm[:, 3]
    Amat = np.column_stack([p1, p2, -np.array([u, v, 1.0])])  # unknowns: x, y, s
    b = -(z * p3 + p4)
    x, y, _s = np.linalg.solve(Amat, b)
    return float(x), float(y)


def _fk_grid(base, shoulder, elbow, wrist_pitch):
    """Vectorized forward kinematics (port of arm.forward) over joint-angle arrays."""
    rad = np.pi / 180.0
    yaw = (base - 90) * rad
    a1 = (180 - shoulder) * rad
    a2 = a1 + (90 - elbow) * rad
    a3 = a2 + (90 - wrist_pitch) * rad
    er = A.L1 * np.cos(a1)
    ez = A.L0 + A.L1 * np.sin(a1)
    wr = er + A.L2 * np.cos(a2)
    wz = ez + A.L2 * np.sin(a2)
    tr = wr + A.L3 * np.cos(a3)
    tz = wz + A.L3 * np.sin(a3)
    return tr * np.cos(yaw), tr * np.sin(yaw), tz


def aim_joints(P, u_px, v_px, wp_set=(60, 75, 90, 105, 120)):
    """Joint pose [base, shoulder, elbow, wrist_pitch] whose gripper tip projects
    closest to the target pixel (u_px, v_px) through P. Searches the safe joint
    ranges (vectorized), keeping only poses in front of the camera. Returns the
    pose plus the predicted pixel and its residual error so the caller can judge
    confidence -- generic to whatever calibration P is loaded."""
    bs = np.arange(A.POS_MIN[0], A.POS_MAX[0] + 1, 2)        # base
    ss = np.arange(max(40, A.POS_MIN[1]), A.POS_MAX[1] + 1, 4)  # shoulder
    es = np.arange(A.POS_MIN[2], A.POS_MAX[2] + 1, 6)        # elbow
    wps = np.asarray(wp_set)                                  # wrist pitch
    B, S, E, WP = np.meshgrid(bs, ss, es, wps, indexing="ij")
    X, Y, Z = _fk_grid(B, S, E, WP)
    den = P[2, 0] * X + P[2, 1] * Y + P[2, 2] * Z + P[2, 3]
    u = (P[0, 0] * X + P[0, 1] * Y + P[0, 2] * Z + P[0, 3]) / den
    v = (P[1, 0] * X + P[1, 1] * Y + P[1, 2] * Z + P[1, 3]) / den
    err = (u - u_px) ** 2 + (v - v_px) ** 2
    err = np.where(den > 0, err, np.inf)        # only poses in front of the camera
    i = np.unravel_index(np.argmin(err), err.shape)
    return {"base": int(B[i]), "shoulder": int(S[i]), "elbow": int(E[i]),
            "wrist_pitch": int(WP[i]), "pred_px": [float(u[i]), float(v[i])],
            "err_px": float(np.sqrt(err[i]))}


# --- Autonomous grasp ---------------------------------------------------------
# Tunables (env-overridable). table_z/grasp_offset also read from calibration.json.
RAW_URL = os.environ.get("ARM_VISION_RAW_URL", f"http://localhost:{VISION_PORT}/raw")
TABLE_Z_DEFAULT = float(os.environ.get("ARM_TABLE_Z", "35"))       # mm, tabletop in arm frame
GRASP_OFFSET_DEFAULT = float(os.environ.get("ARM_GRASP_OFFSET", "60"))  # mm, finger protrusion
# Tipped grasp (horizontal isn't reachable on this arm): descend with a FIXED approach angle
# (held constant so the gripper doesn't swing/knock the object), wrap, close, lift.
GRAB_HEIGHT = float(os.environ.get("ARM_GRAB_HEIGHT", "45"))       # mm above table = grasp height
PREGRASP_CLEAR = float(os.environ.get("ARM_PREGRASP_CLEAR", "70"))  # mm back along the tool axis
APPROACH_HIGH = float(os.environ.get("ARM_APPROACH_HIGH", "150"))   # mm above grasp for the high waypoint
LIFT_HEIGHT = float(os.environ.get("ARM_LIFT_HEIGHT", "130"))      # mm to lift after closing
GRIP_SPEED = int(os.environ.get("ARM_GRIP_SPEED", "200"))         # gripper open/close speed (fast,
#   decoupled from the slow arm speed -- gripper-only motion, so it fully opens before approaching)
REFINE_MAX_CORR = float(os.environ.get("ARM_REFINE_MAX_CORR", "120"))  # mm, ignore bigger "fixes"
# Constant lateral grasp compensation (calibrated once, then autonomous): the grasp lands
# with a consistent sideways bias (gripper mounting / residual), so shift perpendicular to reach.
GRASP_LATERAL = float(os.environ.get("ARM_GRASP_LATERAL", "0"))    # mm; + = toward the arm's LEFT


def _calib_value(key, default, path=None):
    path = path or DEFAULT_CALIB
    if os.path.exists(path):
        try:
            with open(path) as fh:
                v = json.load(fh).get(key)
            if v is not None:
                return float(v)
        except Exception:
            pass
    return default


def load_table_z(path=None):
    """Tabletop height (mm, arm frame). From calibration.json (table_z_mm) or env/default."""
    return _calib_value("table_z_mm", TABLE_Z_DEFAULT, path)


def load_grasp_offset(path=None):
    """Finger-protrusion offset (mm) along the reach direction: how far past the FK tip the
    grasp point is (also absorbs the calibration's local reach bias). From calibration.json
    (grasp_offset_mm) or env/default. Calibrate via a known-good grasp (place bottle in the
    open claw, back-project its pixel, diff vs the grasp fingertip)."""
    return _calib_value("grasp_offset_mm", GRASP_OFFSET_DEFAULT, path)


def load_grasp_lateral(path=None):
    """Lateral grasp offset (mm) perpendicular to reach (+ = arm's left). Fixes the consistent
    left/right bias. From calibration.json (grasp_lateral_mm) or env/default."""
    return _calib_value("grasp_lateral_mm", GRASP_LATERAL, path)


def grab_raw_frame(timeout=3.0):
    """Latest UN-annotated camera frame as a BGR image (for finger detection)."""
    import cv2  # lazy: keep handeye importable without OpenCV (MCP fast path)
    with urllib.request.urlopen(RAW_URL, timeout=timeout) as r:
        buf = np.frombuffer(r.read(), dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def locate_fingers(frame):
    """Gap-centre pixel (u,v) between the gripper's two dark (black shrink-tube) fingers,
    or None. We look for dark blobs inside/near the red gripper region and take the midpoint
    of the two largest -- that midpoint is the real grasp point. Defensive: None if it can't
    confidently find two fingers, so the caller just skips the refine."""
    import cv2                 # lazy
    import calibrate as C      # lazy: reuse the same red gripper mask as calibration
    region = cv2.dilate(C.red_mask(frame), np.ones((35, 35), np.uint8), iterations=1)
    val = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[:, :, 2]
    dark = ((val < 75).astype(np.uint8) * 255)
    dark = cv2.bitwise_and(dark, region)            # dark pixels on/around the gripper
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs = sorted((c for c in cnts if cv2.contourArea(c) >= 20),
                   key=cv2.contourArea, reverse=True)[:2]
    if len(blobs) < 2:
        return None
    cents = []
    for c in blobs:
        m = cv2.moments(c)
        if m["m00"] == 0:
            return None
        cents.append((m["m10"] / m["m00"], m["m01"] / m["m00"]))
    return ((cents[0][0] + cents[1][0]) / 2.0, (cents[0][1] + cents[1][1]) / 2.0)


def grab_target(P, table_z, grasp_offset, u, v, grab_h=GRAB_HEIGHT, lateral=0.0):
    """Coarse grasp geometry. Back-project the object's base pixel onto the table -> (X,Y);
    pull the FK-tip target back toward the base by `grasp_offset` along the reach direction (so
    the protruding fingers, not the solid centre, land on the object) and shift by `lateral`
    perpendicular to the reach (fixes a constant left/right bias). The visual refine corrects
    any residual. Returns dict with obj_xy, grasp_xy, grab_z, yaw."""
    import math
    X, Y = pixel_to_plane(P, u, v, table_z)
    yaw = math.atan2(Y, X)
    rx, ry = math.cos(yaw), math.sin(yaw)          # reach (radial) unit vector
    lx, ly = -math.sin(yaw), math.cos(yaw)         # arm-left (perpendicular) unit vector
    return {"obj_xy": (X, Y), "yaw": yaw, "grab_z": table_z + grab_h,
            "grasp_xy": (X - grasp_offset * rx + lateral * lx,
                         Y - grasp_offset * ry + lateral * ly)}


async def _move_xyz(client, x, y, z, speed, approach=None):
    """IK move the fingertip to (x,y,z). Returns True if reachable (else doesn't move)."""
    sol = A.solve_auto(x, y, z) if approach is None else A.solve_ik(x, y, z, approach)
    if not sol["reachable"]:
        return False
    cur = list(client.pose)
    tgt = [sol["base"], sol["shoulder"], sol["elbow"], sol["wrist_pitch"], cur[4], cur[5]]
    tgt = [int(A.clampv(t, A.POS_MIN[i], A.POS_MAX[i])) for i, t in enumerate(tgt)]
    await client.send(f"SPD:{int(A.clampv(speed, 20, 300))}")
    await client.send("MOVE:" + ",".join(str(t) for t in tgt) + ",20")
    await client.wait_settled(tgt)
    return True


async def _set_joint(client, idx, value, speed):
    """Move a single joint (fast; doesn't move the arm body). Used for gripper + wrist waggle."""
    await client.send(f"SPD:{int(A.clampv(speed, 20, 300))}")
    v = int(A.clampv(value, A.POS_MIN[idx], A.POS_MAX[idx]))
    await client.send(f"J:{idx}:{v}")
    tgt = list(client.pose)
    tgt[idx] = v
    await client.wait_settled(tgt, timeout=4.0)


async def _set_grip(client, value, speed=120):
    await _set_joint(client, 5, value, speed)


async def _measure_gripper_pixel(client, settle=0.3):
    """MEASURE the gripper's actual image pixel by rotating the wrist and frame-differencing --
    the SAME proven-reliable detection the calibration uses (area-weighted centroid of the
    red-motion). Returns (u, v) or None. wrist_rot doesn't move the arm body."""
    import asyncio
    import calibrate as C
    C.MAX_BLOB_AREA = max(C.MAX_BLOB_AREA, 20000)   # the rotation sweep is a big blob
    await _set_joint(client, 4, C.WAGGLE_ROT_A, GRIP_SPEED)
    await asyncio.sleep(settle)
    fa = grab_raw_frame()
    await _set_joint(client, 4, C.WAGGLE_ROT_B, GRIP_SPEED)
    await asyncio.sleep(settle)
    fb = grab_raw_frame()
    await _set_joint(client, 4, 90, GRIP_SPEED)     # restore wrist_rot
    loc = C.locate_gripper(fa, fb)
    return (loc[0], loc[1]) if loc else None


def _refine_correction(P, gap_z, table_z, obj_u, obj_v):
    """One visual finger-refine: detect the finger gap, back-project it (at the gripper's
    current height gap_z) and the object base pixel (at table_z), return the (dx,dy) mm that
    moves the gap onto the object -- computed purely in calibration coords (no manual sign,
    so no left/right inversion). None if fingers not found or the correction looks implausible."""
    import math
    try:
        gap = locate_fingers(grab_raw_frame())
    except Exception:
        return None
    if gap is None:
        return None
    gx, gy = pixel_to_plane(P, gap[0], gap[1], gap_z)
    ox, oy = pixel_to_plane(P, obj_u, obj_v, table_z)
    dx, dy = ox - gx, oy - gy
    if math.hypot(dx, dy) > REFINE_MAX_CORR:
        return None
    return dx, dy


async def pick(client, P, u, v, table_z=None, grasp_offset=None, refine=True, speed=50):
    """Autonomous tipped grasp of the object whose base pixel is (u,v). Comes FROM ABOVE along
    the tool axis (lateral aiming up high, then a diagonal descent at a fixed tilt). With
    refine=True it first MEASURES the gripper's true position with a wrist-rotation waggle (the
    calibration's reliable detection) and corrects the grasp by the LOCAL calibration bias -- so
    it grabs anywhere, not just where the offset was hand-calibrated. Sequence: open ->
    [measure + correct] -> pre-grasp up-and-behind -> diagonal descend -> close -> lift."""
    import math
    table_z = load_table_z() if table_z is None else table_z
    grasp_offset = load_grasp_offset() if grasp_offset is None else grasp_offset
    t = grab_target(P, table_z, grasp_offset, u, v, lateral=load_grasp_lateral())
    Xt, Yt = t["grasp_xy"]
    gz, yaw = t["grab_z"], t["yaw"]
    diag = {"obj_xy": t["obj_xy"], "grasp_xy": (round(Xt, 1), round(Yt, 1)),
            "refined": False, "ok": False}

    sol = A.solve_auto(Xt, Yt, gz)
    if not sol["reachable"]:
        diag["error"] = "grasp unreachable"
        return diag
    appr = sol["phi"]                       # fixed approach tilt, held all the way down
    diag["approach"] = appr
    phi = math.radians(appr)
    tx, ty, tz = math.cos(phi) * math.cos(yaw), math.cos(phi) * math.sin(yaw), math.sin(phi)

    async def go(x, y, z):                  # hold the fixed tilt; fall back to auto if needed
        return (await _move_xyz(client, x, y, z, speed, approach=appr)
                or await _move_xyz(client, x, y, z, speed))

    def pre_of(gx, gy):                     # pre-grasp = back along the tool axis (up-and-behind)
        return (gx - PREGRASP_CLEAR * tx, gy - PREGRASP_CLEAR * ty, gz - PREGRASP_CLEAR * tz)

    await _set_grip(client, A.POS_MIN[5], GRIP_SPEED)                 # open fully (fast)

    if refine:
        # measure the gripper's TRUE position high above the grasp, correct the local bias
        mz = gz + APPROACH_HIGH
        await go(Xt, Yt, mz)
        gpx = await _measure_gripper_pixel(client)
        if gpx is not None:
            gx, gy = pixel_to_plane(P, gpx[0], gpx[1], mz)   # where the gripper actually is
            ex, ey = gx - Xt, gy - Yt                        # local calibration bias
            if math.hypot(ex, ey) <= REFINE_MAX_CORR:
                Xt, Yt = Xt - ex, Yt - ey                    # command grasp - bias
                diag.update(refined=True, bias=(round(ex, 1), round(ey, 1)),
                            grasp_xy=(round(Xt, 1), round(Yt, 1)))

    px, py, pz = pre_of(Xt, Yt)
    await go(px, py, gz + APPROACH_HIGH)                              # high, behind (aim up high)
    if not await go(px, py, pz):                                     # down to up-and-behind object
        diag["error"] = "pre-grasp unreachable"
        return diag
    if not await go(Xt, Yt, gz):                                     # diagonal descent along tilt
        diag["error"] = "grasp pose unreachable"
        return diag
    await _set_grip(client, A.POS_MAX[5], GRIP_SPEED)                 # close (fast, firm)
    await go(Xt, Yt, gz + LIFT_HEIGHT)                                # lift
    diag["ok"] = True
    return diag


# --- CLI: read a detection, compute the aim pose, drive the arm ---------------
def _read_objects(timeout=2.0):
    with urllib.request.urlopen(COLOR_URL, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def choose_object(scene, object_name=None, drinkable=False):
    """The chosen detection dict (by class name, drink-like, or best score), or None."""
    objs = scene.get("objects", []) or []
    if object_name:
        objs = [o for o in objs if o["object"].lower() == object_name.lower()]
    elif drinkable:
        objs = [o for o in objs if o["object"].lower() in DRINKABLE]
    return max(objs, key=lambda o: o["det_score"]) if objs else None


def base_pixel(obj):
    """Bottom-centre of a detection's bbox -- where the object meets the table."""
    x, y, w, h = obj["bbox"]
    return x + w / 2.0, y + h


def pick_target(scene, object_name=None, drinkable=False):
    """Choose a detection's center pixel: a named class, the best drink-like object,
    or the highest-confidence object. Returns (cx, cy, label) or None."""
    objs = scene.get("objects", []) or []
    if not objs:
        return None
    if object_name:
        objs = [o for o in objs if o["object"].lower() == object_name.lower()]
    elif drinkable:
        objs = [o for o in objs if o["object"].lower() in DRINKABLE]
    if not objs:
        return None
    o = max(objs, key=lambda o: o["det_score"])
    cx, cy = o["center"]
    return cx, cy, f'{o["object"]} #{o.get("track_id")}'


async def _drive(joints, speed=90):
    client = A.ArmClient(WS_URL)
    await asyncio.wait_for(client.connect(), 6)
    await asyncio.sleep(0.6)
    cur = list(client.pose)
    tgt = [joints["base"], joints["shoulder"], joints["elbow"],
           joints["wrist_pitch"], cur[4], cur[5]]              # keep wrist_rot + gripper
    tgt = [int(A.clampv(v, A.POS_MIN[i], A.POS_MAX[i])) for i, v in enumerate(tgt)]
    await client.send(f"SPD:{speed}")
    await client.send("MOVE:" + ",".join(str(v) for v in tgt) + ",20")
    await client.wait_settled(tgt)
    return tgt


async def _main(args):
    P = load_P(args.calib)
    if P is None:
        raise SystemExit(f"no calibration at {args.calib or DEFAULT_CALIB}. "
                         f"Run calibrate.py first (per room).")

    if args.pick:
        # autonomous grasp: aim at the object's BASE pixel, then pick()
        if args.pixel:
            u, v, label = args.pixel[0], args.pixel[1], f"pixel ({args.pixel[0]},{args.pixel[1]})"
        else:
            obj = choose_object(_read_objects(), args.object, args.drinkable)
            if obj is None:
                raise SystemExit("no matching object in view.")
            u, v = base_pixel(obj)
            label = f'{obj["object"]} #{obj.get("track_id")}'
        print(f"picking {label}  base pixel=({u:.0f},{v:.0f})  "
              f"table_z={load_table_z():.0f}  grasp_offset={load_grasp_offset():.0f}")
        if args.dry:
            t = grab_target(P, load_table_z(), load_grasp_offset(), u, v)
            print(f"  obj_xy={tuple(round(c) for c in t['obj_xy'])}  "
                  f"grasp_xy={tuple(round(c) for c in t['grasp_xy'])}  (--dry: not moving)")
            return
        client = A.ArmClient(WS_URL)
        await asyncio.wait_for(client.connect(), 6)
        await asyncio.sleep(0.6)
        res = await pick(client, P, u, v, speed=args.speed)
        print(f"  result: {res}")
        return

    if args.pixel:
        cx, cy, label = args.pixel[0], args.pixel[1], f"pixel ({args.pixel[0]},{args.pixel[1]})"
    else:
        scene = _read_objects()
        tgt = pick_target(scene, args.object, args.drinkable)
        if tgt is None:
            raise SystemExit("no matching object in view (check the vision server / target).")
        cx, cy, label = tgt
    joints = aim_joints(P, cx, cy)
    print(f"aiming at {label} @ pixel ({cx:.0f},{cy:.0f})")
    print(f"  pose base={joints['base']} shoulder={joints['shoulder']} "
          f"elbow={joints['elbow']} wrist_pitch={joints['wrist_pitch']}")
    print(f"  predicted gripper pixel ({joints['pred_px'][0]:.0f},{joints['pred_px'][1]:.0f}) "
          f"-> residual {joints['err_px']:.0f}px")
    if args.dry:
        print("  (--dry: not moving)")
        return
    sent = await _drive(joints, speed=args.speed)
    print(f"  moved: {sent}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Aim the arm at what the camera sees.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pixel", type=float, nargs=2, metavar=("U", "V"), help="target pixel")
    g.add_argument("--object", type=str, help="detected class name to aim at (e.g. bottle)")
    g.add_argument("--drinkable", action="store_true", help="aim at the first drink-like object")
    ap.add_argument("--calib", type=str, default=None, help="calibration.json path")
    ap.add_argument("--speed", type=int, default=90, help="move speed deg/s")
    ap.add_argument("--pick", action="store_true",
                    help="autonomously grab the target (back-project + finger-refine + lift)")
    ap.add_argument("--dry", action="store_true", help="compute + print only, do not move")
    asyncio.run(_main(ap.parse_args()))
