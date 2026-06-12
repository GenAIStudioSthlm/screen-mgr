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


def _homography(path=None):
    """The table-plane homography H (arm table-XY -> pixel) from calibration.json, or None.
    This is the robust overhead model -- read per-call so a fresh calibration is picked up."""
    path = path or DEFAULT_CALIB
    if not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            d = json.load(fh)
    except Exception:
        return None
    return np.asarray(d["H"], float) if d.get("model") == "homography" else None


def project(P, x, y, z):
    """Arm-frame point (mm) -> predicted image pixel (u, v). Homography model (table plane,
    z ignored) -> cv2 pinhole -> linear P, in that order."""
    H = _homography()
    if H is not None:
        import cv2
        pp = cv2.perspectiveTransform(np.array([[[x, y]]], float), H)[0, 0]
        return float(pp[0]), float(pp[1])
    cam = _cv2_cam()
    if cam is not None:
        import cv2
        pp = cv2.projectPoints(np.array([[x, y, z]], float), cam["rvec"], cam["tvec"],
                               cam["K"], cam["dist"])[0]
        return float(pp[0, 0, 0]), float(pp[0, 0, 1])
    v = np.asarray(P) @ np.array([x, y, z, 1.0])
    return v[0] / v[2], v[1] / v[2]


def pixel_to_plane(P, u, v, z):
    """Back-project image pixel (u, v) onto the table -> (x, y) mm. Homography model: invert H
    (the stable overhead map -- z ignored, the plane is fixed). Else the cv2 ray-plane, else
    the linear DLT solve. This is what grasping uses to localise an on-table object."""
    H = _homography()
    if H is not None:
        import cv2
        xy = cv2.perspectiveTransform(np.array([[[float(u), float(v)]]], float),
                                      np.linalg.inv(H))[0, 0]
        return float(xy[0]), float(xy[1])
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

# --- Visual-servo grasp (calibration-FREE) tunables -------------------------------
# The servo learns the local image Jacobian online each grasp, so NOTHING here is
# environment-specific -- it re-derives the camera<->arm relationship every time and
# is immune to the camera being moved/bumped between grasps.
SERVO_Z = float(os.environ.get("ARM_SERVO_Z", "135"))             # height (mm) to servo at; well-conditioned pose where
#   the servo converges tightly (higher up the arm is over-extended and the servo stops converging). Above the object
#   so base rotation during alignment clears it (top-down view), then descend.
SERVO_PROBE_MM = float(os.environ.get("ARM_SERVO_PROBE", "30"))   # probe step (mm) to learn the Jacobian
SERVO_GAIN = float(os.environ.get("ARM_SERVO_GAIN", "0.4"))       # 0-1: fraction of the error to correct per iter
#   (damped: <1 so a slightly-underestimated Jacobian converges TO the target instead of overshooting
#    past it and oscillating side-to-side -- the true target is the midpoint of that oscillation)
SERVO_FINE_GAIN = float(os.environ.get("ARM_SERVO_FINE_GAIN", "0.6"))  # damped one-shot correction per descent stage
FINE_MIN_PX = float(os.environ.get("ARM_FINE_MIN_PX", "35"))      # only correct a descent stage if its error exceeds this
SERVO_TOL_PX = float(os.environ.get("ARM_SERVO_TOL", "12"))       # stop when gripper within this many px of target
CLAW_TOP_BAND = int(os.environ.get("ARM_CLAW_TOP_BAND", "30"))    # px band at the top of the red-motion = the claw
SERVO_MAX_ITERS = int(os.environ.get("ARM_SERVO_MAX_ITERS", "16"))  # damped gain + retreat-turn-extend cycles need room
SERVO_R_SAFE = float(os.environ.get("ARM_SERVO_R_SAFE", "210"))     # mm: yaw corrections only at/below this reach. An
#   extended sideways swing sweeps the gripper THROUGH a nearby object (live topple); past r_safe the servo RETREATS
#   radially first (head-on safe), turns retracted, then extends again.
SERVO_MAX_STEP = float(os.environ.get("ARM_SERVO_MAX_STEP", "70"))  # clamp per-iter Cartesian move (mm), anti-overshoot
SERVO_R_MIN = float(os.environ.get("ARM_SERVO_R_MIN", "130"))       # reach annulus the servo may command (mm): below
SERVO_R_MAX = float(os.environ.get("ARM_SERVO_R_MAX", "385"))       # ~130 the arm fouls itself; the upper cap keeps
#   the unanchored base shy of full stretch (true max reach 442). 385 confirmed live: 350 stopped the gripper just
#   short of a reachable grasp -- divergence still cannot push past the cap
APPROACH_PREF = float(os.environ.get("ARM_APPROACH_PREF", "0"))     # preferred hand angle (deg from
#   horizontal) for servo/grab moves. solve_auto points the hand along the shoulder->target line, which
#   TILTS UP ~10deg at full stretch -- the fingertip arrives but the jaw's wrap volume sits short of the
#   object (live: caught the bottle by the cap instead of the body). Horizontal keeps the jaw level.
SERVO_BROYDEN = float(os.environ.get("ARM_SERVO_BROYDEN", "0.8"))   # Broyden rank-1 Jacobian update weight
#   (0 disables): each servo step's commanded move vs OBSERVED pixel motion corrects J continuously, so a
#   mis-scaled probe (live failure: yaw response underestimated several-fold -> every step over-turned)
#   self-heals after one iteration instead of diverging.
OBJ_HEIGHT_MM = float(os.environ.get("ARM_OBJ_HEIGHT", "210"))      # assumed target height (0.5L bottle)
_VPICK_AIM_FRAC_ENV = os.environ.get("ARM_VPICK_AIM_FRAC", "")      # explicit bbox fraction override


def vpick_aim_frac():
    """Fraction down the detection bbox to aim at: the object's point AT THE SERVO HEIGHT.
    Aligning the gripper's pixel to the pixel of a 3D point at the gripper's OWN height has
    zero parallax for ANY camera placement; aiming higher or lower demands the fingertip
    under/overshoot the object by the height difference (live failure: aiming at the lower
    body overshot ~60mm PAST the bottle -- reach pinned at the limit, bottle plowed)."""
    if _VPICK_AIM_FRAC_ENV:
        return float(_VPICK_AIM_FRAC_ENV)
    return min(0.85, max(0.15, 1.0 - SERVO_Z / max(OBJ_HEIGHT_MM, 1.0)))
SERVO_START = (float(os.environ.get("ARM_SERVO_START_X", "200")),
               float(os.environ.get("ARM_SERVO_START_Y", "0")))   # central reachable start (X,Y mm)
# Grab height (mm) for the servo: it aligns to the object's CENTER (mid-body) pixel, so it
# closes around the body here -- NOT the near-table 45mm of the base-pixel pick (that plows
# past a standing bottle and shoves it).
SERVO_GRAB_Z = float(os.environ.get("ARM_SERVO_GRAB_Z", "100"))
# The waggle localizer tracks the RED gripper body, but the white/black-shrinkwrap FINGERS reach
# this many mm FURTHER out along the tool axis. We stop the red point SHORT by this much so the
# fingers (not the red body) land on the object -- otherwise the fingers overshoot and knock it.
FINGER_REACH_OFFSET = float(os.environ.get("ARM_FINGER_REACH_OFFSET", "0"))   # legacy pixel-shift aim offset (off)
SERVO_DESCEND_STEPS = int(os.environ.get("ARM_SERVO_DESCEND_STEPS", "2"))  # intermediate measure-and-correct heights
#   while descending (only kick in when grab_z + MEASURE_CLEAR is below servo_z; the servo_z check always runs)
MEASURE_CLEAR = float(os.environ.get("ARM_SERVO_MEASURE_CLEAR", "40"))     # mm above grab_z: the LOWEST height the
#   wrist-waggle localizer may run at -- any lower and the open gripper sweeping about the tool axis can hit the object
TARGET_REFRESH_PX = float(os.environ.get("ARM_TARGET_REFRESH_PX", "60"))   # after alignment, snap the aim to the nearest
#   detection within this many px of the original target pixel (the servo phase often grazes/nudges the object)
FINGER_REACH_MM = float(os.environ.get("ARM_FINGER_REACH_MM", "30"))      # extra forward reach at the final grab
#   move: the marker midpoint sits at MID-FINGER, so aligning it on the object still leaves the object near the
#   fingertips; this pushes it deep into the jaw before closing (20 still gripped shallow; the past-target trim
#   and the head-on approach keep the extra depth from shoving the object)
CLAW_TIP_BAND = int(os.environ.get("ARM_CLAW_TIP_BAND", "25"))            # px band at the BOTTOM of the moving red = fingertips
SERVO_ABORT_PX = float(os.environ.get("ARM_SERVO_ABORT_PX", "45"))       # if a stage ends with error above this, abort
#   the grasp (don't grab from a diverged/non-converged alignment -- usually a bad Jacobian or a flaky vision server)
# Sideways (tangential, perpendicular-to-reach) bias of the grasp: the detected claw centre is a
# consistent sideways distance from the true finger-gap centre, so the SAME finger keeps catching
# the object. Shift the aim sideways by this many px to centre the gap. +/- picks the side; tune
# via ARM_FINGER_LATERAL_PX (e.g. 20 or -20) until the object sits between the fingers.
FINGER_LATERAL_PX = float(os.environ.get("ARM_FINGER_LATERAL_PX", "0"))


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


async def _move_xyz(client, x, y, z, speed, approach=None, gripper=None):
    """IK move the fingertip to (x,y,z). Returns True if reachable (else doesn't move).
    Default approach prefers APPROACH_PREF (horizontal jaw) over solve_auto's along-reach
    tilt, falling back to the nearest reachable angle.

    `gripper`: explicit gripper angle to hold during the move. Omitting it echoes
    client.pose[5], which is a RACE: if the POS broadcast after an open/close hasn't
    arrived yet, the move silently re-commands the STALE gripper value (live failure:
    the freshly-opened gripper closed itself mid-approach and stabbed the bottle)."""
    sol = A.solve_best(x, y, z, APPROACH_PREF) if approach is None else A.solve_ik(x, y, z, approach)
    if not sol["reachable"]:
        return False
    cur = list(client.pose)
    grip = cur[5] if gripper is None else int(A.clampv(gripper, A.POS_MIN[5], A.POS_MAX[5]))
    tgt = [sol["base"], sol["shoulder"], sol["elbow"], sol["wrist_pitch"], cur[4], grip]
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


# --- Static finger-marker localization (colored paper strips on the fingers) -----
# Preferred over the wrist-waggle localizer: a single frame, NOTHING moves -- so a
# measurement can never knock the object over (the waggle toppled the bottle when it
# measured right next to it), and it is ~10x faster per measurement.
FINGER_MARKERS = os.environ.get("ARM_FINGER_MARKERS", "1") not in ("0", "false", "no")
MARKER_A_HUE = tuple(int(v) for v in os.environ.get("ARM_MARKER_A_HUE", "55,95").split(","))   # green strip
MARKER_B_HUE = tuple(int(v) for v in os.environ.get("ARM_MARKER_B_HUE", "96,130").split(","))  # blue strip
MARKER_SAT_MIN = int(os.environ.get("ARM_MARKER_SAT_MIN", "110"))
MARKER_VAL_MIN = int(os.environ.get("ARM_MARKER_VAL_MIN", "60"))
MARKER_MIN_AREA = int(os.environ.get("ARM_MARKER_MIN_AREA", "60"))      # px^2 per strip blob
MARKER_MIN_ELONG = float(os.environ.get("ARM_MARKER_MIN_ELONG", "1.8"))  # strips are long+thin; this
#   rejects round same-hue objects (live: the bottle's BLUE CAP measured elongation 1.0 vs the
#   blue strip's 4.6 -- hue alone cannot tell them apart)
MARKER_MAX_GAP_PX = int(os.environ.get("ARM_MARKER_MAX_GAP", "150"))    # the two strips are on one
#   gripper: blobs further apart than this are not the finger pair
MARKER_RELAX_SAT = int(os.environ.get("ARM_MARKER_RELAX_SAT", "35"))    # rescue gates used when ONE
MARKER_RELAX_VAL = int(os.environ.get("ARM_MARKER_RELAX_VAL", "50"))    # strip is missing: re-scan for
#   it near the found one with these relaxed sat/val (direct warm sunlight desaturates blue)
# Marker measurements are far less noisy than the waggle differencing, so the servo can run
# MUCH tighter tolerances (live miss: a 13px ~ 20mm residual passed the waggle-sized gates,
# one finger contacted first and clipped the bottle out of the gap instead of wrapping it).
MARKER_TOL_PX = float(os.environ.get("ARM_MARKER_TOL_PX", "10"))        # align convergence (the marker
#   midpoint jitters ~+/-5px frame to frame; tighter than that and the servo hunts forever)
MARKER_FINE_MIN_PX = float(os.environ.get("ARM_MARKER_FINE_MIN", "9"))  # correct descent stages above this
MARKER_ABORT_PX = float(os.environ.get("ARM_MARKER_ABORT_PX", "20"))    # do-not-close gate

_MARKER_MODE = None   # per-grab sticky choice: True=markers, False=waggle (set on 1st measurement)
_MARKER_OFF = {}      # per-grab: gap offset from each strip (0=A/green, 1=B/blue), learned
#   from every full-pair reading -- lets ONE visible strip stand in when the object occludes
#   the other right at the grasp (live: 'gripper lost' with the gripper 17px from done)
_LAST_GAP = None      # last gap estimate, to pick the nearest candidate in single-strip mode


def locate_finger_markers(frame):
    """Grasp-gap pixel from the green and blue finger strips, or None.
    Strips = sufficiently-ELONGATED blobs per hue band (rejects the round blue bottle cap);
    full pair = the closest cross-colour pair -> midpoint (and remember each strip's offset
    to the gap). If only ONE strip is visible -- the object occludes the other near the
    grasp -- fall back to that strip plus its remembered offset."""
    import cv2
    global _LAST_GAP
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    def strip_cands(band, sat_min, val_min, min_area, region=None):
        m = cv2.inRange(hsv, (band[0], sat_min, val_min), (band[1], 255, 255))
        if region is not None:                              # restrict to a window (x0,y0,x1,y1)
            x0, y0, x1, y1 = region
            box = np.zeros_like(m)
            box[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = 255
            m = cv2.bitwise_and(m, box)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cs = []
        for c in cnts:
            if cv2.contourArea(c) < min_area:
                continue
            (_, _), (w, h), _ = cv2.minAreaRect(c)
            if max(w, h) / max(min(w, h), 1e-6) < MARKER_MIN_ELONG:
                continue                                    # round blob: cap/ball, not a strip
            mm = cv2.moments(c)
            if mm["m00"]:
                cs.append((mm["m10"] / mm["m00"], mm["m01"] / mm["m00"]))
        return cs

    bands = (MARKER_A_HUE, MARKER_B_HUE)
    cands = [strip_cands(band, MARKER_SAT_MIN, MARKER_VAL_MIN, MARKER_MIN_AREA)
             for band in bands]
    # SUNLIGHT RESCUE: warm direct light collapses the BLUE strip's saturation (live dry
    # run: blue measured sat ~46 against the 110 gate while green held 139 -- warm light
    # carries little blue, so the strip goes dark and grey). If exactly one band came up
    # empty, re-scan it with relaxed gates but ONLY near a strip we DID find -- elongation
    # + proximity keep bluish floor shadows from qualifying.
    if bool(cands[0]) != bool(cands[1]):
        i_found = 0 if cands[0] else 1
        fx, fy = cands[i_found][0]
        g = MARKER_MAX_GAP_PX
        cands[1 - i_found] = strip_cands(
            bands[1 - i_found], MARKER_RELAX_SAT, MARKER_RELAX_VAL,
            max(25, MARKER_MIN_AREA // 2),
            region=(int(fx - g), int(fy - g), int(fx + g), int(fy + g)))
    a, b = cands
    if a and b:
        best, best_d2, pair = None, MARKER_MAX_GAP_PX ** 2, None
        for ax, ay in a:
            for bx, by in b:
                d2 = (ax - bx) ** 2 + (ay - by) ** 2
                if d2 <= best_d2:
                    best, best_d2 = ((ax + bx) / 2.0, (ay + by) / 2.0), d2
                    pair = ((ax, ay), (bx, by))
        if best is not None:
            _MARKER_OFF[0] = (best[0] - pair[0][0], best[1] - pair[0][1])
            _MARKER_OFF[1] = (best[0] - pair[1][0], best[1] - pair[1][1])
            _LAST_GAP = best
            return best
    # single-strip fallback: one colour visible (or no valid pair) + a learned offset
    for idx, cs in ((0, a), (1, b)):
        if cs and idx in _MARKER_OFF:
            if _LAST_GAP is not None:                       # nearest to the last gap estimate
                cx, cy = min(cs, key=lambda c: (c[0] - _LAST_GAP[0]) ** 2 +
                                               (c[1] - _LAST_GAP[1]) ** 2)
            else:
                cx, cy = cs[0]
            off = _MARKER_OFF[idx]
            _LAST_GAP = (cx + off[0], cy + off[1])
            return _LAST_GAP
    return None


async def _measure_gripper_pixel(client, settle=0.3, reads=3):
    """MEASURE the gripper's GRASP POINT in the image.

    Preferred: STATIC finger markers -- the strip midpoint IS the grasp gap; one frame,
    nothing moves. Decided on the FIRST measurement of a grab and then STICKY: if markers
    were working and momentarily vanish we return None rather than silently waggling right
    next to the object (which is what toppled the bottle). Rigs without markers fall back
    to the original wrist-rotation waggle + frame-difference localizer below.
    Returns (u, v) or None. wrist_rot doesn't move the arm body."""
    global _MARKER_MODE
    import asyncio
    if FINGER_MARKERS and _MARKER_MODE in (None, True):
        pts = []
        for _ in range(3):                     # 3 reads -> median rejects single-frame jitter
            await asyncio.sleep(0.15)          # let the vision loop publish a post-move frame
            try:
                loc = locate_finger_markers(grab_raw_frame())
            except Exception:
                loc = None
            if loc:
                pts.append(loc)
        if pts:
            _MARKER_MODE = True
            return (float(np.median([p[0] for p in pts])),
                    float(np.median([p[1] for p in pts])))
        if _MARKER_MODE is True:
            return None                        # markers were working: do NOT start waggling
        _MARKER_MODE = False                   # no markers on this rig: use the waggle

    # Waggle fallback: rotate the wrist and frame-difference (the can/clutter are static so
    # they drop out). We take the BOTTOM edge of the moving red = the fingertips: in this
    # reaching-down view the claw is the lowest part of the gripper, that's where the grasp
    # happens, AND it's robust to the waggle occasionally catching the wrist (which is HIGHER,
    # so the bottom edge ignores it -- the area-weighted centroid did not, which made the servo
    # chase the wrist and overshoot). Median over `reads` reads rejects flicker.
    import calibrate as C
    C.MAX_BLOB_AREA = max(C.MAX_BLOB_AREA, 20000)   # the rotation sweep is a big blob
    us, vs = [], []
    for _ in range(reads):
        await _set_joint(client, 4, C.WAGGLE_ROT_A, GRIP_SPEED)
        await asyncio.sleep(settle)
        fa = grab_raw_frame()
        await _set_joint(client, 4, C.WAGGLE_ROT_B, GRIP_SPEED)
        await asyncio.sleep(settle)
        fb = grab_raw_frame()
        await _set_joint(client, 4, 90, GRIP_SPEED)     # restore wrist_rot
        loc = C.locate_gripper(fa, fb)
        if not loc:
            continue
        ys, xs = np.nonzero(loc[3])                     # loc[3] = motion-cluster mask
        if len(ys) == 0:
            continue
        sel = ys >= ys.max() - CLAW_TIP_BAND            # bottom band = fingertips
        us.append(float(xs[sel].mean())); vs.append(float(ys[sel].mean()))
    if not us:
        return None
    return (float(np.median(us)), float(np.median(vs)))


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
    global _MARKER_MODE, _LAST_GAP
    _MARKER_MODE, _LAST_GAP = None, None   # re-decide markers-vs-waggle for this grab
    _MARKER_OFF.clear()                    # re-learn the strip->gap offsets fresh
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

    grip = [A.POS_MIN[5]]                   # explicit gripper per move (see _move_xyz race note)

    async def go(x, y, z):                  # hold the fixed tilt; fall back to auto if needed
        return (await _move_xyz(client, x, y, z, speed, approach=appr, gripper=grip[0])
                or await _move_xyz(client, x, y, z, speed, gripper=grip[0]))

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
    grip[0] = A.POS_MAX[5]                                            # moves now hold the close
    await go(Xt, Yt, gz + LIFT_HEIGHT)                                # lift
    diag["ok"] = True
    return diag


async def visual_pick(client, obj_uv, speed=50, servo_z=None, grab_z=None,
                      probe=None, gain=None, tol_px=None, max_iters=None):
    """Calibration-FREE grasp by VISUAL SERVOING. No calibration.json is read.

    Each grasp the arm (re)learns the local image Jacobian online -- how a Cartesian
    X/Y move shifts the gripper's pixel (found by the wrist-rotation waggle localizer,
    the proven-reliable detector) -- then uses its inverse to drive the gripper's pixel
    onto the object's pixel, iterating a few times. Then it REFRESHES the target pixel
    (the servo phase may have nudged the object), descends from above in measured stages
    -- re-checking the gripper pixel and applying small damped corrections while it is
    still safe to waggle -- and only closes if the final measured error is small (else it
    ABORTS rather than plow the object). Because the image<->arm map is re-derived every
    grasp, this is immune to the camera being moved/bumped or lighting changes between
    grasps.

    obj_uv : (u, v) target pixel (the object's center). Returns a diag dict."""
    import numpy as np
    global _MARKER_MODE, _LAST_GAP
    _MARKER_MODE, _LAST_GAP = None, None   # re-decide markers-vs-waggle for this grab
    _MARKER_OFF.clear()                    # re-learn the strip->gap offsets fresh
    servo_z = SERVO_Z if servo_z is None else servo_z
    grab_z = SERVO_GRAB_Z if grab_z is None else grab_z
    probe = SERVO_PROBE_MM if probe is None else probe
    gain = SERVO_GAIN if gain is None else gain
    tol_px = SERVO_TOL_PX if tol_px is None else tol_px
    max_iters = SERVO_MAX_ITERS if max_iters is None else max_iters
    tu0, tv0 = float(obj_uv[0]), float(obj_uv[1])    # raw target pixel (kept for the post-align refresh)
    diag = {"ok": False, "obj_px": (round(tu0), round(tv0)), "servo_z": servo_z}

    grip = [A.POS_MIN[5]]      # the gripper value EVERY arm move re-asserts (open until the
    #   close). Echoing client.pose[5] instead is a race that re-closed a freshly-opened
    #   gripper mid-approach when the open's POS broadcast lagged -- and stabbed the bottle.

    async def go(x, y, z, approach=None):
        return await _move_xyz(client, x, y, z, speed, approach=approach, gripper=grip[0])

    import calibrate as C
    await C.go_home(client, speed)                                   # always start from a known HOME
    await _set_grip(client, A.POS_MIN[5], GRIP_SPEED)                 # open fully (fast)
    X, Y = SERVO_START
    if not await go(X, Y, servo_z):
        diag["error"] = f"start pose ({X:.0f},{Y:.0f},{servo_z:.0f}) unreachable"
        return diag

    # We control the arm in POLAR coords (base yaw, radial reach r), NOT Cartesian X/Y, because
    # base-yaw maps to horizontal image motion and reach to vertical -- and, crucially, turning at
    # a FIXED small r is a retracted arc that stays INSIDE any object further out (so the big base
    # swing can't sweep the gripper sideways through it -- the "swings at bottle height, moves it"
    # failure). Cartesian Y-moves secretly grow the reach and defeat that.
    yaw0 = float(np.arctan2(Y, X))
    r0 = float(np.hypot(X, Y))

    async def go_polar(yaw, r, z, approach=None):
        return await go(float(r * np.cos(yaw)), float(r * np.sin(yaw)), z, approach)

    # --- the local image Jacobian  J2 = d[u,v] / d[yaw, r]  (one yaw probe, one reach probe).
    #     A closure because the map is only LOCALLY valid: far from where it was learned the
    #     real response drifts (live run: the yaw response flipped sign by yaw~27deg), so the
    #     servo re-learns it AT THE CURRENT POSE when steering starts making the error worse. ---
    dyaw_probe = float(np.deg2rad(8))
    Jh = {}                                # holds J2 / J2inv / sin; refreshed by learn_J

    async def learn_J(yaw, r, z):
        """(Re)learn J2 at (yaw, r, z); returns an error string or None. Leaves the arm back
        at (yaw, r, z) and Jh updated."""
        g0 = await _measure_gripper_pixel(client)
        if g0 is None:
            return "gripper not seen (check framing/lighting/red-gate)"
        if not await go_polar(yaw + dyaw_probe, r, z):
            return "yaw-probe pose unreachable"
        gyaw = await _measure_gripper_pixel(client)
        if not await go_polar(yaw, r + probe, z):
            return "reach-probe pose unreachable"
        gr = await _measure_gripper_pixel(client)
        await go_polar(yaw, r, z)
        if gyaw is None or gr is None:
            return "gripper lost during probe moves"
        J2 = np.array([[(gyaw[0] - g0[0]) / dyaw_probe, (gr[0] - g0[0]) / probe],
                       [(gyaw[1] - g0[1]) / dyaw_probe, (gr[1] - g0[1]) / probe]])
        diag["J"] = J2.tolist()
        if abs(float(np.linalg.det(J2))) < 1e-9:
            return f"degenerate Jacobian (gripper barely moved in image): {J2.tolist()}"
        # Viewpoint conditioning: if the two columns are nearly PARALLEL in the image,
        # base-rotation and reach are visually indistinguishable from this camera angle -- the
        # inverse is garbage and servoing it walks the arm the wrong way out to a tip-over pose
        # (seen live: camera behind the arm looking along the reach axis).
        c0, c1 = J2[:, 0], J2[:, 1]
        sin_cols = abs(float(c0[0] * c1[1] - c0[1] * c1[0])) / max(
            float(np.linalg.norm(c0) * np.linalg.norm(c1)), 1e-9)
        diag["jacobian_sin"] = round(sin_cols, 3)
        if sin_cols < 0.35:
            return (
                f"degenerate camera viewpoint: base-rotation and reach move the gripper along "
                f"nearly the same image direction (|sin|={sin_cols:.2f} < 0.35), so the servo "
                f"cannot steer. Move the camera to view the workspace from the side or above -- "
                f"not along the arm's reach axis -- and retry (no recalibration needed).")
        Jh["J2"], Jh["J2inv"] = J2, np.linalg.inv(J2)
        return None

    fail = await learn_J(yaw0, r0, servo_z)
    if fail and "degenerate" in fail:
        fail = await learn_J(yaw0, r0, servo_z)   # one probe was misread (live: |sin| 0.02 from a
        #   camera that measured 0.8-0.99 all day) -- re-probe once before trusting a degenerate J
    if fail:
        diag["error"] = fail
        return diag
    diag["measure"] = "markers" if _MARKER_MODE else "waggle"
    if FINGER_MARKERS and not _MARKER_MODE:
        diag["measure_note"] = ("finger markers are enabled but were NOT detected at the first "
                                "measurement -- fell back to the wrist-waggle localizer (slower, "
                                "and it can knock the object). Check the strips and lighting "
                                "(harsh direct sunlight washes out the blue strip; see HANDOFF).")
    # marker measurements are low-noise: run the tight tolerances (the waggle-sized gates let a
    # ~20mm residual through, and the close clipped the bottle out of the gap)
    fine_min, abort_px = FINE_MIN_PX, SERVO_ABORT_PX
    if _MARKER_MODE:
        tol_px = min(tol_px, MARKER_TOL_PX)
        fine_min, abort_px = MARKER_FINE_MIN_PX, MARKER_ABORT_PX
    relearns = [2]                         # mid-servo re-learn budget for the whole grab

    # Aim the RED point SHORT of the object by the finger length: the white fingers reach
    # FINGER_REACH_OFFSET mm further out, so shift the target pixel radially INWARD (by that many
    # mm worth of the reach-column image displacement). Now the fingers -- not the red body --
    # land on the object, instead of overshooting and knocking it over. Sideways, shift along
    # the TANGENTIAL image direction (the yaw column = how the gripper slides sideways when the
    # base rotates) by FINGER_LATERAL_PX to centre the finger gap. A function because the target
    # pixel can be refreshed after alignment and the offsets must be re-applied.
    def aim_from(u, v):
        J2 = Jh["J2"]
        au = u - FINGER_REACH_OFFSET * float(J2[0, 1])
        av = v - FINGER_REACH_OFFSET * float(J2[1, 1])
        if FINGER_LATERAL_PX:
            tu, tv = float(J2[0, 0]), float(J2[1, 0])
            tn = (tu * tu + tv * tv) ** 0.5
            if tn > 1e-6:
                au += FINGER_LATERAL_PX * tu / tn
                av += FINGER_LATERAL_PX * tv / tn
        return au, av

    ou, ov = aim_from(tu0, tv0)
    diag["aim_px"] = (round(ou), round(ov))

    _DBG = bool(os.environ.get("ARM_VPICK_DEBUG"))
    _dbg = [0]

    async def servo(yaw, r, z, approach, max_it, turn_only=False, reach_only=False):
        """Drive the gripper's pixel onto (ou,ov) in polar space at fixed height z.
        turn_only:  rotate the base only (r held) -- a retracted arc to aim the bearing.
        reach_only: extend/retract along the fixed bearing only (no base rotation) -- a radial
                    approach that comes at the object head-on and CANNOT sweep sideways into it.
        Returns (yaw, r, err, it)."""
        err, it = float("inf"), 0
        best_err, worse = float("inf"), 0
        prev_q, prev_g, prev_retreat = None, None, False
        for it in range(max_it):
            g = await _measure_gripper_pixel(client)
            if g is None:
                return yaw, r, None, it
            # BROYDEN rank-1 update: correct J by what the LAST step actually did in the image
            # (commanded dq vs observed dg). The probe-learned J is local and can be badly
            # mis-scaled (live: yaw column ~5x too small -> every step over-turned); this
            # self-heals it within an iteration. Yaw is scaled to ~tangential mm so both
            # coordinates update on comparable footing; the update is rejected if it would
            # degrade J to near-singular.
            if prev_q is not None and SERVO_BROYDEN > 0:
                S = max(r0, 1.0)
                dq = np.array([(yaw - prev_q[0]) * S, r - prev_q[1]])
                nq = float(dq @ dq)
                if nq > 1e-6:
                    Js = np.column_stack([Jh["J2"][:, 0] / S, Jh["J2"][:, 1]])
                    dg = np.array([g[0] - prev_g[0], g[1] - prev_g[1]])
                    Js = Js + SERVO_BROYDEN * np.outer(dg - Js @ dq, dq) / nq
                    Jn = np.column_stack([Js[:, 0] * S, Js[:, 1]])
                    c0, c1 = Jn[:, 0], Jn[:, 1]
                    s = abs(float(c0[0] * c1[1] - c0[1] * c1[0])) / max(
                        float(np.linalg.norm(c0) * np.linalg.norm(c1)), 1e-9)
                    if s >= 0.2 and abs(float(np.linalg.det(Jn))) > 1e-9:
                        Jh["J2"], Jh["J2inv"] = Jn, np.linalg.inv(Jn)
            prev_q, prev_g = (yaw, r), g
            eu, ev = ou - g[0], ov - g[1]
            err = abs(eu) if turn_only else (abs(ev) if reach_only else float(np.hypot(eu, ev)))
            if _DBG:
                import cv2
                _dbg[0] += 1
                tag = "turn" if turn_only else ("reach" if reach_only else "full")
                fr = grab_raw_frame()
                cv2.circle(fr, (int(g[0]), int(g[1])), 8, (0, 0, 255), 3)     # gripper fingertip = red
                cv2.circle(fr, (int(ou), int(ov)), 7, (0, 255, 0), 2)         # target = green
                cv2.putText(fr, f"{_dbg[0]:02d} {tag} it{it} err={err:.0f}", (8, 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                cv2.imwrite(f"/tmp/vstep_{_dbg[0]:02d}.jpg", fr)
                print(f"  [{_dbg[0]:02d}] {tag} it{it} g=({g[0]:.0f},{g[1]:.0f}) tgt=({ou:.0f},{ov:.0f}) "
                      f"err={err:.0f} yaw={np.rad2deg(yaw):.0f} r={r:.0f}")
            if err < tol_px:
                break
            # DIVERGENCE GUARD: a correct move reduces the error. If moves make it WORSE the
            # Jacobian has gone stale (it is only locally valid -- the live yaw response flipped
            # sign by ~27deg of base swing). RE-LEARN it at the current pose (budgeted) and keep
            # servoing; only give up once the budget is spent. A deliberate RETREAT grows the
            # pixel error on purpose -- exempt it.
            if err > best_err + 4.0 and not prev_retreat:
                # A single marker misread can fake a divergence (live: 10px -> 41px for one
                # frame, and the resulting re-learn threw away a converged approach). CONFIRM
                # a worse reading with a fresh measurement before acting on it.
                g2 = await _measure_gripper_pixel(client)
                if g2 is not None:
                    eu2, ev2 = ou - g2[0], ov - g2[1]
                    err2 = abs(eu2) if turn_only else (
                        abs(ev2) if reach_only else float(np.hypot(eu2, ev2)))
                    if err2 < err - 4.0:
                        g, eu, ev, err = g2, eu2, ev2, err2     # first reading was the outlier
                        prev_g = g                              # don't feed the outlier to Broyden
            if err > best_err + 4.0 and not prev_retreat:
                worse += 1
                if worse >= 2:
                    if relearns[0] <= 0:
                        break
                    relearns[0] -= 1
                    if r > SERVO_R_SAFE + 10:     # the re-probe YAWS: retract first so the
                        #   probe arc cannot sweep through the nearby object
                        if await go_polar(yaw, SERVO_R_SAFE, z):
                            r = SERVO_R_SAFE
                    if await learn_J(yaw, r, z) is not None:
                        break              # re-probe failed: stop on the old (stale) state
                    best_err, worse = float("inf"), 0
                    prev_q, prev_g = None, None   # J is fresh: don't Broyden-correct across it
                    continue               # fresh local map: re-measure and steer again
            else:
                worse = 0
            best_err = min(best_err, err)
            J2, J2inv = Jh["J2"], Jh["J2inv"]
            # For a DECOUPLED move (yaw-only or reach-only) use the DIRECT diagonal term, NOT the
            # coupled inverse: J2inv@[eu,ev] gives a (yaw,reach) pair that only achieves [eu,ev] if
            # BOTH are applied; dropping one and keeping the other sends it the wrong way when the
            # cross-terms are large (this was the persistent wrong-way turn). Full move uses J2inv.
            if turn_only:
                dyaw = gain * eu / J2[0, 0] if abs(J2[0, 0]) > 1e-6 else 0.0   # du/dyaw
                dr = 0.0
            elif reach_only:
                dyaw = 0.0
                dr = gain * ev / J2[1, 1] if abs(J2[1, 1]) > 1e-6 else 0.0      # dv/dr
            else:
                d = gain * (J2inv @ np.array([eu, ev]))
                dyaw, dr = float(d[0]), float(d[1])
            # direction-PRESERVING clamp: scale the whole step so both limits hold. Clamping each
            # component independently mangles the step's direction when the solve is large (an
            # ill-conditioned Jacobian produces huge raw steps), which steers the wrong way.
            scale = min(1.0, np.deg2rad(12) / max(abs(dyaw), 1e-9),
                        SERVO_MAX_STEP / max(abs(dr), 1e-9))
            dyaw, dr = dyaw * scale, dr * scale
            # NEVER yaw while extended: a sideways correction at reach sweeps the gripper
            # THROUGH a nearby object (the live topple). Allowed yaw shrinks as the arm extends
            # past SERVO_R_SAFE; if more turn is needed than allowed, RETREAT radially this
            # iteration instead (pure pull-back is head-on safe), turn retracted, extend again.
            # PAST-THE-TARGET guard: project the gripper's offset from the target onto the
            # reach direction (the J reach column). Positive = the jaw is already at/past the
            # object radially -- further extension only shoves the palm through it (live
            # topple: reach ran to the limit chasing a LATERAL error while already arrived).
            cr = J2[:, 1]
            crn = float(np.hypot(cr[0], cr[1]))
            if crn > 1e-9:
                past = ((g[0] - ou) * cr[0] + (g[1] - ov) * cr[1]) / crn
                if past > 2.0:
                    dr = min(dr, 0.0)
            ext = max(0.0, r - SERVO_R_SAFE)
            yaw_cap = float(np.deg2rad(12.0)) * max(0.05, 1.0 - ext / 80.0)
            # Retreat only when the TANGENTIAL pixel error itself is large (the bearing is
            # genuinely wrong). The coupled solve also asks for yaw to help the reach axis --
            # gating on the raw dyaw demand made the servo back out with a perfect bearing,
            # come in again, and limit-cycle until it hit max iterations (live failure).
            cy = J2[:, 0]
            e_t = abs(float(cy[0] * eu + cy[1] * ev)) / max(float(np.hypot(cy[0], cy[1])), 1e-9)
            retreat = (e_t > max(2.0 * tol_px, 14.0)) and abs(dyaw) > yaw_cap and ext > 10.0
            if retreat:
                dyaw, dr = 0.0, -min(ext, SERVO_MAX_STEP)
                best_err, worse = float("inf"), 0   # retreating resets the convergence baseline
            else:
                dyaw = float(np.clip(dyaw, -yaw_cap, yaw_cap))
            dr = float(np.clip(dr, SERVO_R_MIN - r, SERVO_R_MAX - r))  # hard annulus: never
            #   let divergence over-extend the unanchored arm toward a tip-over pose
            prev_retreat = retreat
            moved = False
            for _ in range(4):                                        # largest REACHABLE fraction
                if await go_polar(yaw + dyaw, r + dr, z, approach):
                    yaw, r, moved = yaw + dyaw, r + dr, True
                    break
                dyaw, dr = dyaw * 0.5, dr * 0.5
            if not moved:
                break
        return yaw, r, err, it

    yaw, r = yaw0, r0

    # --- ALIGN: single FULL coupled servo at servo_z (above the object, so any base rotation is
    #     clear of it -- then we descend straight down). The full inverse J2inv@[eu,ev] correctly
    #     SPLITS each pixel error between base-rotation and reach. This is essential because the
    #     reach direction is DIAGONAL in the image (extending the arm moves the gripper down AND
    #     sideways), so a horizontal error is NOT purely a bearing error -- the decoupled
    #     turn-then-reach over-rotated trying to zero it with the base alone. ---
    yaw, r, err, it = await servo(yaw, r, servo_z, None, max_iters)
    if err is None:
        diag["error"] = "gripper lost during alignment"; return diag
    diag["align_err_px"], diag["align_iters"] = round(err), it
    diag["bearing_deg"] = round(float(np.rad2deg(yaw)))
    if err > abort_px:
        diag["error"] = (f"alignment did not converge ({err:.0f}px) -- bad Jacobian / unstable "
                         f"detection (is the vision server healthy?). Aborting, not grabbing.")
        return diag

    # --- TARGET REFRESH: the servo phase can graze/nudge the object, so re-read the scene and
    #     snap the aim to the object's CURRENT pixel (nearest detection to the original one).
    #     Without this the descent aims at the stale pre-servo position. ---
    diag["target_refreshed"] = False
    refresh_moved = 0.0
    try:
        objs = _read_objects().get("objects", []) or []
        near = [(float(np.hypot(vpick_pixel(o)[0] - tu0, vpick_pixel(o)[1] - tv0)), o)
                for o in objs]
        near = [(dn, o) for dn, o in near if dn <= TARGET_REFRESH_PX]
        if near:
            dn, o = min(near, key=lambda t: t[0])
            diag["target_refreshed"] = True
            if dn > 1.0:
                tu0, tv0 = vpick_pixel(o)
                nu, nv = aim_from(tu0, tv0)
                refresh_moved = float(np.hypot(nu - ou, nv - ov))
                ou, ov = nu, nv
                diag.update(refreshed_px=(round(tu0), round(tv0)), aim_px=(round(ou), round(ov)))
    except Exception:
        pass                                              # vision hiccup: keep the aligned aim
    if refresh_moved > tol_px:                            # re-align onto the moved target
        yaw, r, err, it = await servo(yaw, r, servo_z, None, max_iters)
        if err is None:
            diag["error"] = "gripper lost during re-alignment"; return diag
        diag["realign_err_px"], diag["realign_iters"] = round(err), it
        if err > abort_px:
            diag["error"] = (f"re-alignment did not converge ({err:.0f}px) after the target "
                             f"moved {refresh_moved:.0f}px -- aborting, not grabbing.")
            return diag

    # --- VERIFIED DESCENT (replaces the blind open-loop grab). Re-open the gripper, then step
    #     toward the grab height re-MEASURING at each stage and applying at most ONE damped
    #     correction (SERVO_FINE_GAIN) per stage. Every measurement stays at or above
    #     measure_floor = grab_z + MEASURE_CLEAR -- low enough to matter, high enough that the
    #     wrist waggle cannot hit the object (re-measuring AT grab height is what made the old
    #     fine-correction wild, and the waggle there would whack the object). With the default
    #     geometry (servo_z 135, grab_z 100) only the servo_z check runs; intermediate stages
    #     kick in automatically whenever the gap allows. The LAST measurement gates the close:
    #     above SERVO_ABORT_PX we ABORT instead of closing blind on a drifted approach. ---
    await _set_grip(client, A.POS_MIN[5], GRIP_SPEED)     # RE-OPEN fully (fast) right before the
    #   approach -- it opened minutes ago at the start and can drift, so it must be wide open NOW.
    # marker measurements move NOTHING, so they may run essentially at grab height; the
    # MEASURE_CLEAR safety floor only protects the waggle's swept volume.
    measure_floor = grab_z + (8.0 if _MARKER_MODE else MEASURE_CLEAR)
    zs = [float(servo_z)]
    if SERVO_DESCEND_STEPS > 0 and measure_floor < servo_z - 1.0:
        zs += [float(z) for z in np.linspace(servo_z, measure_floor, SERVO_DESCEND_STEPS + 1)[1:]]
    stages, z_now, err_last, g_last = [], float(servo_z), err, None
    steer_ok, prev_e, prev_corrected = True, None, False
    for z in zs:
        if z != z_now and not await go_polar(yaw, r, z):
            stages.append({"z": round(z), "err_px": None, "corrected": False,
                           "note": "stage pose unreachable, skipped"})
            continue
        z_now = z
        g = await _measure_gripper_pixel(client)
        if g is None:
            stages.append({"z": round(z), "err_px": None, "corrected": False,
                           "note": "gripper not seen"})
            continue
        eu, ev = ou - g[0], ov - g[1]
        e = float(np.hypot(eu, ev))
        if _DBG:
            import cv2
            _dbg[0] += 1
            fr = grab_raw_frame()
            cv2.circle(fr, (int(g[0]), int(g[1])), 8, (0, 0, 255), 3)
            cv2.circle(fr, (int(ou), int(ov)), 7, (0, 255, 0), 2)
            cv2.putText(fr, f"{_dbg[0]:02d} desc z{z:.0f} err={e:.0f}", (8, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.imwrite(f"/tmp/vstep_{_dbg[0]:02d}.jpg", fr)
            print(f"  [{_dbg[0]:02d}] desc z={z:.0f} g=({g[0]:.0f},{g[1]:.0f}) tgt=({ou:.0f},{ov:.0f}) "
                  f"err={e:.0f} yaw={np.rad2deg(yaw):.0f} r={r:.0f}")
        # steering guard: if the PREVIOUS stage's correction made the error worse, the servo_z
        # Jacobian is unreliable down here -- stop steering (measurements still gate the close).
        if prev_corrected and prev_e is not None and e > prev_e + 4.0:
            steer_ok = False
        corrected, dyaw, dr = False, 0.0, 0.0
        if steer_ok and e > fine_min:
            # REACH-ONLY correction (least-squares projection of the pixel error onto the reach
            # column): NEVER yaw down here right next to the object -- the sideways sweep is the
            # topple. Tangential residual was already zeroed while retracted; a head-on reach
            # correction at worst nudges the object straight back.
            cr = Jh["J2"][:, 1]
            nr2 = float(cr @ cr)
            dyaw = 0.0
            dr = 0.0 if nr2 < 1e-9 else float(SERVO_FINE_GAIN * (cr[0] * eu + cr[1] * ev) / nr2)
            dr = float(np.clip(dr, max(-SERVO_MAX_STEP, SERVO_R_MIN - r),
                               min(SERVO_MAX_STEP, SERVO_R_MAX - r)))
            for _ in range(3):                            # largest reachable fraction
                if await go_polar(yaw + dyaw, r + dr, z):
                    yaw, r, corrected = yaw + dyaw, r + dr, True
                    break
                dyaw, dr = dyaw * 0.5, dr * 0.5
        stages.append({"z": round(z), "err_px": round(e), "corrected": corrected,
                       "dyaw_deg": round(float(np.rad2deg(dyaw)), 1), "dr_mm": round(dr, 1)})
        prev_e, prev_corrected, err_last, g_last = e, corrected, e, g
    if stages and stages[-1].get("corrected"):            # the stored error predates that correction
        g = await _measure_gripper_pixel(client)
        if g is not None:
            err_last, g_last = float(np.hypot(ou - g[0], ov - g[1])), g
            stages.append({"z": round(z_now), "err_px": round(err_last), "corrected": False,
                           "note": "post-correction check"})
    diag["descent"], diag["final_err_px"] = stages, round(err_last)
    if err_last > abort_px:
        diag["error"] = (f"descent did not converge ({err_last:.0f}px > {abort_px:.0f}px "
                         f"at z={z_now:.0f}) -- aborting before the close so a drifted approach "
                         f"can't plow the object.")
        return diag

    # --- FINAL approach (open-loop, but now verified just above): move forward along the aimed
    #     bearing and down to the grab height in one move -- the remaining drop is below
    #     measure_floor where the waggle may not run, so it is necessarily unmeasured.
    #     FINGER_REACH_MM = how far forward past the aligned fingertip the fingers travel,
    #     TRIMMED by however far the jaw already sits past the target along the reach direction
    #     (px -> mm via the reach column), so the seat can never shove the palm into the object. ---
    extend = FINGER_REACH_MM
    cr = Jh["J2"][:, 1]
    nr2 = float(cr @ cr)
    if g_last is not None and nr2 > 1e-9:
        past_mm = float(((g_last[0] - ou) * cr[0] + (g_last[1] - ov) * cr[1]) / nr2)
        if past_mm > 0:
            extend = max(0.0, extend - past_mm)
            diag["seat_trim_mm"] = round(past_mm, 1)
    moved = False
    for _ in range(6):                                               # back off the forward reach until reachable
        r_grab = r + extend
        X, Y = float(r_grab * np.cos(yaw)), float(r_grab * np.sin(yaw))
        appr = A.solve_best(X, Y, grab_z, APPROACH_PREF)["phi"]   # level jaw at the grab
        if await go(X, Y, grab_z, approach=appr) or await go(X, Y, grab_z):
            moved = True
            break
        extend -= 15.0
    if not moved:
        diag["error"] = f"grasp pose ({X:.0f},{Y:.0f},{grab_z:.0f}) unreachable"; return diag
    diag["grasp_xy"], diag["extend_mm"] = (round(X), round(Y)), round(extend)

    await _set_grip(client, A.POS_MAX[5], GRIP_SPEED)                 # close (fast, firm) -- NO waggle now
    grip[0] = A.POS_MAX[5]                                            # moves now hold the close (lift!)
    await go(X, Y, grab_z + LIFT_HEIGHT)                             # lift
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



def choose_object_retry(object_name=None, drinkable=False, tries=12, gap=0.35):
    """choose_object with retries: marginal detections (transparent bottle at ~0.2-0.3
    confidence) flicker out of /color for moments at a time -- a single read randomly
    misses a target that is plainly there. Samples until the object appears."""
    import time
    for i in range(tries):
        obj = choose_object(_read_objects(), object_name, drinkable)
        if obj is not None:
            return obj
        time.sleep(gap)
    return None


def base_pixel(obj):
    """Bottom-centre of a detection's bbox -- where the object meets the table."""
    x, y, w, h = obj["bbox"]
    return x + w / 2.0, y + h


def vpick_pixel(obj):
    """Aim pixel for the visual servo: the object's point at the SERVO HEIGHT (see
    vpick_aim_frac) -- the only pixel the gripper can align to without parallax."""
    x, y, w, h = obj["bbox"]
    return x + w / 2.0, y + vpick_aim_frac() * h


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
    if getattr(args, "vpick", False):
        # calibration-FREE visual-servo grasp -- does not need calibration.json
        if args.pixel:
            ou, ov = args.pixel[0], args.pixel[1]
            label = f"pixel ({ou:.0f},{ov:.0f})"
        else:
            obj = choose_object_retry(args.object, args.drinkable)
            if obj is None:
                raise SystemExit("no matching object in view (check the vision server / target).")
            ou, ov = vpick_pixel(obj)        # lower body, not center (height parallax)
            label = f'{obj["object"]} #{obj.get("track_id")}'
        print(f"visual-servo grabbing {label}  object pixel=({ou:.0f},{ov:.0f})  (no calibration)")
        if args.dry:
            print("  (--dry: not moving)")
            return
        client = A.ArmClient(WS_URL)
        await asyncio.wait_for(client.connect(), 6)
        await asyncio.sleep(0.6)
        res = await visual_pick(client, (ou, ov), speed=args.speed)
        print(f"  result: {res}")
        return

    P = load_P(args.calib)
    if P is None:
        raise SystemExit(f"no calibration at {args.calib or DEFAULT_CALIB}. "
                         f"Run calibrate.py first (per room).")

    if args.pick:
        # autonomous grasp: aim at the object's BASE pixel, then pick()
        if args.pixel:
            u, v, label = args.pixel[0], args.pixel[1], f"pixel ({args.pixel[0]},{args.pixel[1]})"
        else:
            obj = choose_object_retry(args.object, args.drinkable)
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
    ap.add_argument("--vpick", action="store_true",
                    help="calibration-FREE visual-servo grasp (learns image motion online each grab)")
    ap.add_argument("--dry", action="store_true", help="compute + print only, do not move")
    asyncio.run(_main(ap.parse_args()))
