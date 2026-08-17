"""
calibrate.py - hand-eye calibration by MOVE-AND-DETECT.

The YOLO detector has no "robot arm" class, so the arm is invisible to detection.
This script finds it the way motion always reveals it: at each of a set of KNOWN arm
poses it waggles ONLY the gripper (open<->close) and frame-differences two raw frames.
Because forward kinematics for the fingertip does NOT depend on the gripper joint, the
arm stays put while the fingers move -- the diff blob is localized exactly at the
gripper, giving a clean pixel (u,v) for a 3D point we know from FK.

With >=6 non-coplanar (XYZ_arm -> pixel) correspondences we fit the full 3x4 camera
projection matrix P by DLT (Direct Linear Transform), then decompose it into intrinsics
K, rotation R and the camera position in the arm frame. That is the full 3D camera pose
-- enough to project any arm point to the image, and (with a target plane) to turn a
clicked pixel back into arm coordinates for grasping.

Prereqs:
  - vision_server.py running (owns the webcam, serves /raw)         -> ARM_VISION_PORT
  - the arm powered + reachable over WebSocket                      -> ARM_WS_URL

Run:   python calibrate.py                  # full sweep, writes calibration.json
       python calibrate.py --poses 8        # fewer poses (quicker)
       python calibrate.py --dry-run        # print the planned poses + FK, don't move
"""

import argparse
import asyncio
import json
import os
import time
import urllib.request

import cv2
import numpy as np

import arm as A

WS_URL = os.environ.get("ARM_WS_URL", "ws://robotarm.local:81")
VISION_PORT = int(os.environ.get("ARM_VISION_PORT", "8000"))
RAW_URL = os.environ.get("ARM_VISION_RAW_URL", f"http://localhost:{VISION_PORT}/raw")
OUT_PATH = os.environ.get("ARM_CALIB_OUT", os.path.join(os.path.dirname(__file__), "calibration.json"))

GRIP_OPEN = A.POS_MIN[5]      # 10
GRIP_CLOSED = A.POS_MAX[5]    # 130
DIFF_THRESH = int(os.environ.get("ARM_CALIB_DIFF_THRESH", "22"))   # per-pixel intensity change counted as "moved"
MIN_BLOB_AREA = int(os.environ.get("ARM_CALIB_MIN_BLOB", "120"))   # px^2; smaller diff blobs are noise, pose is skipped
# Gripper-waggle (fingers open/close) is a SMALL local motion; a big red blob that
# moved is background (e.g. a person shifting), not the gripper -- reject it.
MAX_BLOB_AREA = int(os.environ.get("ARM_CALIB_MAX_BLOB", "2500"))
# The gripper waggle is the largest, most CONCENTRATED red-motion. Warm clutter (wood floor,
# leather, a can) + inter-frame noise make small specks scattered across the frame; their
# centroid lands off the gripper. So keep only motion blobs within this radius (px) of the
# biggest blob -- the gripper cluster -- and reject the far scatter.
CLUSTER_RADIUS = int(os.environ.get("ARM_CALIB_CLUSTER_RADIUS", "90"))
SETTLE_S = 0.5               # let the camera/arm settle after an ARM move
# The gripper waggle (open<->close) is localized by frame-differencing two frames; the
# longer the gap between them, the more a moving person/background contaminates the diff.
# Gripper-only motion never wiggles the arm body, so we waggle it FAST regardless of the
# (possibly slow, anti-wiggle) arm-move speed -- keeping the two diffed frames close in time.
GRIP_WAGGLE_SPEED = int(os.environ.get("ARM_CALIB_GRIP_SPEED", "180"))   # deg/s
GRIP_SETTLE = float(os.environ.get("ARM_CALIB_GRIP_SETTLE", "0.3"))      # s, short on purpose
# Localization waggle: rotate the wrist (joint 4) between these two angles. This sweeps
# the open gripper symmetrically about the tool axis -> a big, clean red-motion blob
# centred on the FK fingertip. wrist_rot does NOT move the arm body (no base wobble) and
# does NOT change the FK tip, so the captured pixel still corresponds to the pose's tip.
WAGGLE_ROT_A = int(os.environ.get("ARM_CALIB_ROT_A", "60"))
WAGGLE_ROT_B = int(os.environ.get("ARM_CALIB_ROT_B", "120"))


# --- Calibration pose set -----------------------------------------------------
def make_poses(n):
    """[base, shoulder, elbow, wrist_pitch] poses spanning a real 3D VOLUME, so the
    correspondences are non-coplanar and well-conditioned (a flat sheet of points, or
    duplicates, makes the DLT solve degenerate).

    We sample target fingertip XYZ on a grid -- reach r, height z, and yaw direction --
    and solve IK for each, keeping only reachable, distinct joint solutions. Using the
    achieved FK tip (computed in the loop) as the 3D point means IK clamping can't
    corrupt the geometry. wrist_rot is held at 90; gripper is set during the waggle."""
    reaches = [170.0, 230.0, 290.0]          # mm out from the base axis
    # heights kept clear of the table: the open gripper rotates during localization, so
    # the lowest level must not let the fingers sweep the tabletop. Still spans depth
    # (which an overhead camera reads as height) for a well-conditioned solve.
    heights = [115.0, 185.0, 255.0, 320.0]   # mm above the table (Z)
    # Moderate yaw sweep. NOTE: widening this (or lowering `heights`) destabilizes the raw DLT
    # into a near-degenerate solve whose back-projection blows up -- this compact range is the
    # configuration that stays physical. Full-table coverage needs a checkerboard-based intrinsic
    # calibration (cv2.calibrateCamera over many planar views), not wider single-view DLT.
    yaws_deg = [-25.0, -12.0, 0.0, 12.0, 25.0]
    seen, poses = set(), []
    for z in heights:
        for r in reaches:
            for yd in yaws_deg:
                th = np.radians(yd)
                x, y = r * np.cos(th), r * np.sin(th)
                sol = A.solve_auto(x, y, z)
                if not sol["reachable"]:
                    continue
                key = (sol["base"], sol["shoulder"], sol["elbow"], sol["wrist_pitch"])
                if key in seen:
                    continue
                seen.add(key)
                poses.append(list(key))
    # deterministic, well-spread subset when n < len
    if n < len(poses):
        idx = np.linspace(0, len(poses) - 1, n).round().astype(int)
        poses = [poses[k] for k in sorted(set(idx))]
    return poses


# --- Raw frame grab -----------------------------------------------------------
def grab_raw(timeout=3.0):
    """Fetch + decode the latest UN-annotated frame from the vision server."""
    with urllib.request.urlopen(RAW_URL, timeout=timeout) as r:
        buf = np.frombuffer(r.read(), dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("vision server returned a frame that failed to decode")
    return img


def median_frame(n=3, gap=0.08):
    """Median of n consecutive raw frames -> suppresses sensor noise / flicker."""
    frames = []
    for _ in range(n):
        frames.append(grab_raw())
        time.sleep(gap)
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def red_mask(frame):
    """Mask of the arm's red/orange plastic. The Braccio is vividly red while the
    rest of the scene (person, walls, counter) is not -- this gates out background
    motion (e.g. a person shifting) that would otherwise dominate the frame-diff."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lo1 = cv2.inRange(hsv, (0, 90, 60), (14, 255, 255))     # red..orange
    lo2 = cv2.inRange(hsv, (168, 90, 60), (179, 255, 255))  # red wrap past 180
    return cv2.bitwise_or(lo1, lo2)


def locate_gripper(frame_a, frame_b):
    """Pixel (u,v) of the gripper from a localization waggle. We rotate the wrist
    (`wrist_rot`) between two frames, which sweeps the gripper symmetrically about the
    tool axis -- the axis that passes through the FK fingertip. So the AREA-WEIGHTED
    CENTROID of ALL the red motion lands on that axis = the tip pixel (taking only the
    largest blob would land on one finger, off-axis). Red-gating + a per-blob size band
    reject the static background and stray specks. Returns (u, v, area, mask) or None."""
    d = cv2.absdiff(frame_a, frame_b)
    g = cv2.cvtColor(d, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (5, 5), 0)
    _, th = cv2.threshold(g, DIFF_THRESH, 255, cv2.THRESH_BINARY)
    # keep only motion on the red arm (red present in either waggle frame)
    red = cv2.bitwise_or(red_mask(frame_a), red_mask(frame_b))
    red = cv2.dilate(red, np.ones((7, 7), np.uint8), iterations=1)  # tolerate edges
    th = cv2.bitwise_and(th, red)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    th = cv2.dilate(th, np.ones((5, 5), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # keep red-motion blobs in the gripper's plausible size band (reject noise specks
    # and any huge background blob), then take the centroid of ALL of them together.
    cands = [c for c in cnts if MIN_BLOB_AREA <= cv2.contourArea(c) <= MAX_BLOB_AREA]
    if not cands:
        return None
    # Anchor on the biggest red-motion blob (the gripper's waggle) and keep only blobs CLUSTERED
    # near it -- this rejects the scattered specks from warm clutter + inter-frame noise that
    # would otherwise drag the centroid off the gripper into empty space.
    def _cen(c):
        m = cv2.moments(c)
        return (m["m10"] / m["m00"], m["m01"] / m["m00"]) if m["m00"] else (-1e9, -1e9)
    bx, by = _cen(max(cands, key=cv2.contourArea))
    cluster = [c for c in cands
               if (_cen(c)[0] - bx) ** 2 + (_cen(c)[1] - by) ** 2 <= CLUSTER_RADIUS ** 2]
    mask = np.zeros(th.shape, np.uint8)
    cv2.drawContours(mask, cluster, -1, 255, -1)
    M = cv2.moments(mask, binaryImage=True)
    if M["m00"] == 0:
        return None
    area = float(M["m00"])
    return (M["m10"] / M["m00"], M["m01"] / M["m00"], area, mask)


# --- DLT projection-matrix fit ------------------------------------------------
def _normalize_2d(pts):
    """Isotropic (Hartley) normalization: centroid->origin, mean dist->sqrt(2)."""
    m = pts.mean(axis=0)
    d = np.sqrt(((pts - m) ** 2).sum(axis=1)).mean()
    s = np.sqrt(2) / d if d > 0 else 1.0
    T = np.array([[s, 0, -s * m[0]], [0, s, -s * m[1]], [0, 0, 1]])
    ph = np.hstack([pts, np.ones((len(pts), 1))])
    return (T @ ph.T).T[:, :2], T


def _normalize_3d(pts):
    m = pts.mean(axis=0)
    d = np.sqrt(((pts - m) ** 2).sum(axis=1)).mean()
    s = np.sqrt(3) / d if d > 0 else 1.0
    U = np.array([[s, 0, 0, -s * m[0]], [0, s, 0, -s * m[1]],
                  [0, 0, s, -s * m[2]], [0, 0, 0, 1]])
    ph = np.hstack([pts, np.ones((len(pts), 1))])
    return (U @ ph.T).T[:, :3], U


def fit_projection(points3d, points2d):
    """Estimate the 3x4 camera matrix P with X_pix ~ P [X Y Z 1]^T (DLT, normalized)."""
    P3 = np.asarray(points3d, float)
    P2 = np.asarray(points2d, float)
    n2, T = _normalize_2d(P2)
    n3, U = _normalize_3d(P3)
    rows = []
    for (X, Y, Z), (u, v) in zip(n3, n2):
        rows.append([X, Y, Z, 1, 0, 0, 0, 0, -u * X, -u * Y, -u * Z, -u])
        rows.append([0, 0, 0, 0, X, Y, Z, 1, -v * X, -v * Y, -v * Z, -v])
    _, _, Vt = np.linalg.svd(np.asarray(rows))
    Pn = Vt[-1].reshape(3, 4)
    P = np.linalg.inv(T) @ Pn @ U      # un-normalize
    return P / P[2, 3]                 # fix scale so the last translation term = 1


def reproject_errors(P, points3d, points2d):
    ph = np.hstack([np.asarray(points3d, float), np.ones((len(points3d), 1))])
    proj = (P @ ph.T).T
    proj = proj[:, :2] / proj[:, 2:3]
    return np.sqrt(((proj - np.asarray(points2d, float)) ** 2).sum(axis=1))


def fit_projection_robust(points3d, points2d, min_keep=8, max_drop=None):
    """Fit P, then iteratively drop the single worst-reprojecting correspondence and
    refit, while points remain and the worst residual is an outlier (> 3x median).
    Move-and-detect occasionally mislocates a pose (background red, weak motion); one
    bad point wrecks a least-squares projective fit, so trimming is essential.
    Returns (P, kept_indices)."""
    p3 = np.asarray(points3d, float)
    p2 = np.asarray(points2d, float)
    keep = list(range(len(p3)))
    max_drop = len(p3) - min_keep if max_drop is None else max_drop
    P = fit_projection(p3[keep], p2[keep])
    for _ in range(max(0, max_drop)):
        errs = reproject_errors(P, p3[keep], p2[keep])
        w = int(np.argmax(errs))
        if len(keep) <= min_keep or errs[w] <= 3.0 * np.median(errs):
            break
        keep.pop(w)
        P = fit_projection(p3[keep], p2[keep])
    return P, keep


def normalize_sign(P, points3d):
    """P and -P encode the same projection; pick the sign that puts the sampled
    points IN FRONT of the camera (positive homogeneous depth), so the K/R
    decomposition yields physical (positive-focal) intrinsics."""
    ph = np.hstack([np.asarray(points3d, float), np.ones((len(points3d), 1))])
    depth = (P @ ph.T)[2]
    return -P if np.median(depth) < 0 else P


def decompose(P):
    """P -> intrinsics K, rotation R, camera centre C (in arm-frame mm). Flips the
    residual axis signs so K has a positive diagonal while preserving P = K[R|t]."""
    K, R, t_h = cv2.decomposeProjectionMatrix(P)[:3]
    K = K / K[2, 2]
    S = np.diag(np.sign(np.diag(K)))   # +/-1 per axis; S @ S = I
    K, R = K @ S, S @ R
    C = (t_h[:3] / t_h[3]).flatten()
    return K, R, C


# --- Arm driving --------------------------------------------------------------
async def move_to(client, base, shoulder, elbow, wrist_pitch, gripper, speed=120):
    tgt = [int(A.clampv(v, A.POS_MIN[i], A.POS_MAX[i])) for i, v in
           enumerate([base, shoulder, elbow, wrist_pitch, 90, gripper])]
    await client.send(f"SPD:{speed}")
    await client.send("MOVE:" + ",".join(str(v) for v in tgt) + ",20")
    await client.wait_settled(tgt)
    return tgt


async def go_home(client, speed):
    """Return to HOME at a controlled (slow) speed. The gripper waggle leaves SPD fast,
    so we MUST re-set a slow speed here -- otherwise the final home move whips the
    unanchored arm and can tip it over at the last second."""
    await client.send(f"SPD:{int(A.clampv(speed, 20, 300))}")
    await client.send("MOVE:" + ",".join(str(v) for v in A.HOME) + ",20")
    await client.wait_settled(A.HOME)


async def set_grip(client, value, speed=None):
    await set_joint(client, 5, value, speed=speed)


async def set_joint(client, idx, value, speed=None):
    """Move a single joint (fast, decoupled from arm speed when `speed` given). Used for
    the gripper and for the wrist-rotation localization waggle -- neither moves the base."""
    if speed is not None:
        await client.send(f"SPD:{int(A.clampv(speed, 20, 300))}")
    v = int(A.clampv(value, A.POS_MIN[idx], A.POS_MAX[idx]))
    await client.send(f"J:{idx}:{v}")
    tgt = list(client.pose)
    tgt[idx] = v
    await client.wait_settled(tgt, timeout=4.0)


async def run(args):
    poses = make_poses(args.poses)
    speed, settle = args.speed, args.settle
    print(f"planned {len(poses)} calibration poses (gripper-waggle move-and-detect); "
          f"speed={speed} deg/s, settle={settle}s\n")
    if args.delay and not args.dry_run:
        # give the operator time to step OUT of the camera view: the gripper's
        # finger-waggle is a small motion, and a person moving in frame swamps it.
        for s in range(args.delay, 0, -1):
            print(f"  starting in {s}s -- step out of the camera view ...", flush=True)
            await asyncio.sleep(1)

    if args.dry_run:
        for i, (b, s, e, wp) in enumerate(poses):
            xyz = A.forward(b, s, e, wp)
            print(f"  pose {i:2d}  joints[b,s,e,wp]={[b,s,e,wp]}  "
                  f"tip(mm)=({xyz['x']:7.1f},{xyz['y']:7.1f},{xyz['z']:7.1f})")
        print("\n(dry run -- no movement, no camera)")
        return

    debug_dir = os.path.join(os.path.dirname(OUT_PATH), "calib_debug")
    os.makedirs(debug_dir, exist_ok=True)

    client = A.ArmClient(WS_URL)
    await asyncio.wait_for(client.connect(), 6)
    await asyncio.sleep(0.8)
    print(f"connected to {WS_URL}; pose={client.pose}\n")

    pts3d, pts2d, records = [], [], []
    for i, (b, s, e, wp) in enumerate(poses):
        xyz = A.forward(b, s, e, wp)
        # gripper open so the wrist-rotation waggle sweeps a wide red arc
        await move_to(client, b, s, e, wp, GRIP_OPEN, speed=speed)
        await asyncio.sleep(settle)              # damp arm wiggle before capturing
        await set_joint(client, 4, WAGGLE_ROT_A, speed=GRIP_WAGGLE_SPEED)
        await asyncio.sleep(GRIP_SETTLE)
        f_a = median_frame()
        await set_joint(client, 4, WAGGLE_ROT_B, speed=GRIP_WAGGLE_SPEED)  # fast: short diff gap
        await asyncio.sleep(GRIP_SETTLE)
        f_b = median_frame()

        loc = locate_gripper(f_a, f_b)
        tag = f"pose{i:02d}"
        if loc is None:
            print(f"  {tag}  tip(mm)=({xyz['x']:7.1f},{xyz['y']:7.1f},{xyz['z']:7.1f})  "
                  f"-> no gripper motion found (out of frame?), SKIP")
            cv2.imwrite(os.path.join(debug_dir, f"{tag}_skip_a.jpg"), f_a)
            cv2.imwrite(os.path.join(debug_dir, f"{tag}_skip_b.jpg"), f_b)
            continue
        u, v, area, mask = loc
        pts3d.append([xyz["x"], xyz["y"], xyz["z"]])
        pts2d.append([u, v])
        records.append({"pose": [b, s, e, wp], "xyz": [xyz["x"], xyz["y"], xyz["z"]],
                        "pixel": [u, v], "blob_area": area})
        print(f"  {tag}  tip(mm)=({xyz['x']:7.1f},{xyz['y']:7.1f},{xyz['z']:7.1f})  "
              f"-> pixel=({u:6.1f},{v:6.1f})  area={int(area)}")
        # save an overlay (waggle frame + detected gripper point) for inspection
        ov = f_b.copy()
        cv2.circle(ov, (int(u), int(v)), 8, (0, 255, 0), 2)
        cv2.circle(ov, (int(u), int(v)), 2, (0, 255, 0), -1)
        cv2.imwrite(os.path.join(debug_dir, f"{tag}_overlay.jpg"), ov)

    await go_home(client, speed)   # slow return so the unanchored base isn't thrown off

    print(f"\ncollected {len(pts3d)} usable correspondences "
          f"(of {len(poses)} poses); need >=6 for DLT.")
    img_size = [int(grab_raw().shape[1]), int(grab_raw().shape[0])]
    solve_and_report(pts3d, pts2d, records, img_size)
    print(f"debug overlays in {debug_dir}/")


# --- Table-plane homography calibration (the robust model for an overhead view) ---------
HOMOG_Z = float(os.environ.get("ARM_HOMOG_Z", "80"))   # table-plane height to calibrate at


def table_grid():
    """(X,Y) targets spanning the reachable table at the grab height (HOMOG_Z)."""
    reaches = [150.0, 195.0, 240.0, 285.0]
    yaws = [-40.0, -27.0, -14.0, 0.0, 14.0, 27.0, 40.0]
    out = []
    for r in reaches:
        for yd in yaws:
            th = np.radians(yd)
            x, y = r * np.cos(th), r * np.sin(th)
            if A.solve_auto(x, y, HOMOG_Z)["reachable"]:
                out.append((x, y))
    return out


async def run_homography(args):
    """Calibrate a 2D table-plane HOMOGRAPHY (image <-> table at z=HOMOG_Z). Sweep the gripper
    across the reachable table at the grab height, waggle-detect each pixel, fit H. Stable for an
    overhead view (no depth ambiguity, unlike the 3D DLT) and accurate for on-table objects."""
    targets = table_grid()
    speed, settle = args.speed, args.settle
    print(f"homography calibration: {len(targets)} table points at z={HOMOG_Z:.0f}, "
          f"speed={speed} settle={settle}\n")
    if args.delay:
        for s in range(args.delay, 0, -1):
            print(f"  starting in {s}s -- clear the table ...", flush=True)
            await asyncio.sleep(1)

    client = A.ArmClient(WS_URL)
    await asyncio.wait_for(client.connect(), 6)
    await asyncio.sleep(0.8)

    XY, PX, records = [], [], []
    for i, (tx, ty) in enumerate(targets):
        sol = A.solve_auto(tx, ty, HOMOG_Z)
        await move_to(client, sol["base"], sol["shoulder"], sol["elbow"], sol["wrist_pitch"],
                      GRIP_OPEN, speed=speed)
        await asyncio.sleep(settle)
        await set_joint(client, 4, WAGGLE_ROT_A, speed=GRIP_WAGGLE_SPEED)
        await asyncio.sleep(GRIP_SETTLE)
        fa = median_frame()
        await set_joint(client, 4, WAGGLE_ROT_B, speed=GRIP_WAGGLE_SPEED)
        await asyncio.sleep(GRIP_SETTLE)
        fb = median_frame()
        await set_joint(client, 4, 90, speed=GRIP_WAGGLE_SPEED)
        loc = locate_gripper(fa, fb)
        fk = A.forward(sol["base"], sol["shoulder"], sol["elbow"], sol["wrist_pitch"])
        if loc is None:
            print(f"  h{i:02d} table=({fk['x']:6.0f},{fk['y']:6.0f})  -> no detection, SKIP")
            continue
        XY.append([fk["x"], fk["y"]])
        PX.append([loc[0], loc[1]])
        records.append({"xy": [fk["x"], fk["y"]], "pixel": [loc[0], loc[1]]})
        print(f"  h{i:02d} table=({fk['x']:6.0f},{fk['y']:6.0f})  -> pixel=({loc[0]:6.0f},{loc[1]:6.0f})")
    await go_home(client, speed)

    if len(XY) < 6:
        print(f"\nonly {len(XY)} points detected -- need >=6. Re-run with the table clear.")
        return
    XY = np.array(XY, np.float64)
    PX = np.array(PX, np.float64)
    H, inliers = cv2.findHomography(XY, PX, cv2.RANSAC, 4.0)
    proj = cv2.perspectiveTransform(XY.reshape(-1, 1, 2), H).reshape(-1, 2)
    errs_px = np.sqrt(((proj - PX) ** 2).sum(1))
    back = cv2.perspectiveTransform(PX.reshape(-1, 1, 2), np.linalg.inv(H)).reshape(-1, 2)
    errs_mm = np.sqrt(((back - XY) ** 2).sum(1))
    print(f"\n=== table-plane homography ===")
    print(f"used {int(inliers.sum())}/{len(XY)} inliers")
    print(f"reprojection px     median={np.median(errs_px):.1f}  max={errs_px.max():.1f}")
    print(f"back-projection mm  median={np.median(errs_mm):.1f}  max={errs_mm.max():.1f}  "
          f"(this is what grasping uses)")

    out = {"model": "homography",
           "image_size": [int(grab_raw().shape[1]), int(grab_raw().shape[0])],
           "H": H.tolist(), "homog_z": HOMOG_Z,
           "backproj_err_mm": {"median": float(np.median(errs_mm)), "max": float(errs_mm.max())},
           "num_points": len(XY), "correspondences": records}
    if os.path.exists(OUT_PATH):
        try:
            prev = json.load(open(OUT_PATH))
            for k in ("table_z_mm", "grasp_offset_mm", "grasp_lateral_mm"):
                if k in prev:
                    out[k] = prev[k]
        except Exception:
            pass
    with open(OUT_PATH, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nsaved {OUT_PATH}")


def fit_pnp(pts3d, pts2d, image_size):
    """STABLE camera fit: fix the principal point at the image centre, SEARCH the focal length,
    and solve the pose with cv2.solvePnP at each focal -- pick the focal with the lowest
    reprojection. Unlike raw DLT / single-view calibrateCamera (which degenerate to a near-
    orthographic camera on this weak-perspective overhead view), solvePnP with a fixed K can't
    collapse, so back-projection stays physical. Returns (K, rvec, tvec, focal, mean_err_px)."""
    w, h = image_size
    obj = np.ascontiguousarray(np.asarray(pts3d, np.float64))
    img = np.ascontiguousarray(np.asarray(pts2d, np.float64))
    best = None
    for f in range(220, 1400, 10):
        K = np.array([[float(f), 0, w / 2.0], [0, float(f), h / 2.0], [0, 0, 1.0]])
        ok, rvec, tvec = cv2.solvePnP(obj, img, K, None, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            continue
        proj = cv2.projectPoints(obj, rvec, tvec, K, None)[0].reshape(-1, 2)
        err = float(np.sqrt(((proj - img) ** 2).sum(axis=1)).mean())
        if best is None or err < best[0]:
            best = (err, float(f), K, rvec, tvec)
    return best[2], best[3], best[4], best[1], best[0]


def solve_and_report(pts3d, pts2d, records, image_size):
    """Robustly fit the camera (focal search + solvePnP), report quality, save calibration.json."""
    if len(pts3d) < 6:
        print("NOT ENOUGH points to solve (need >=6). Inspect calib_debug/ overlays "
              "and re-run with the workspace clear and the arm steady.")
        return None

    # DLT robust pass only to DROP outlier correspondences (reprojection-based)
    _Pd, keep = fit_projection_robust(pts3d, pts2d, min_keep=max(6, len(pts3d) - 4))
    dropped = sorted(set(range(len(pts3d))) - set(keep))
    p3 = [pts3d[i] for i in keep]
    p2 = [pts2d[i] for i in keep]

    K, rvec, tvec, focal, _ = fit_pnp(p3, p2, image_size)
    R, _ = cv2.Rodrigues(rvec)
    C = -R.T @ tvec.reshape(3)
    proj = cv2.projectPoints(np.asarray(p3, np.float64), rvec, tvec, K, None)[0].reshape(-1, 2)
    errs = np.sqrt(((proj - np.asarray(p2, float)) ** 2).sum(axis=1))
    P = K @ np.hstack([R, tvec.reshape(3, 1)])
    P = P / P[2, 3]

    print("\n=== calibration result (focal-search + solvePnP) ===")
    print(f"used {len(keep)}/{len(pts3d)} points"
          + (f" (dropped outliers: {dropped})" if dropped else ""))
    print(f"reprojection error  mean={errs.mean():.2f}px  median={np.median(errs):.2f}px  "
          f"max={errs.max():.2f}px")
    print(f"focal length (px)  {focal:.0f}   principal point  ({K[0,2]:.0f},{K[1,2]:.0f})")
    print(f"camera position in arm frame (mm)  x={C[0]:.0f}  y={C[1]:.0f}  z={C[2]:.0f}")
    if np.median(errs) > 8.0:
        print("\n  WARNING: high reprojection error -> calibration may be unreliable.")

    out = {
        "model": "cv2_pinhole",
        "image_size": image_size,
        "K": K.tolist(), "dist": [0.0, 0.0, 0.0, 0.0, 0.0],
        "rvec": rvec.flatten().tolist(), "tvec": tvec.flatten().tolist(),
        "R": R.tolist(), "P": P.tolist(),
        "camera_xyz_arm_mm": C.tolist(),
        "reproj_err_px": {"mean": float(errs.mean()), "median": float(np.median(errs)),
                          "max": float(errs.max())},
        "num_points_used": len(keep), "num_points_total": len(pts3d),
        "dropped_outliers": dropped,
        "correspondences": records,
    }
    # preserve grasp tuning (table height + finger offsets) across recalibration so it isn't
    # silently wiped -- these are set once by the grasp-offset calibration / --measure-table
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH) as fh:
                prev = json.load(fh)
            for k in ("table_z_mm", "grasp_offset_mm", "grasp_lateral_mm"):
                if k in prev:
                    out[k] = prev[k]
        except Exception:
            pass
    with open(OUT_PATH, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nsaved {OUT_PATH}")
    return out


def project(P, xyz):
    """Arm XYZ (mm) -> predicted pixel (u, v) via the calibrated projection matrix."""
    x = np.asarray(P) @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
    return x[0] / x[2], x[1] / x[2]


async def verify():
    """Held-out check: move to fresh poses NOT in the calibration set, predict the
    gripper pixel from P, locate it by move-and-detect, and report the error."""
    with open(OUT_PATH) as fh:
        P = np.array(json.load(fh)["P"])
    # fresh test targets (mm), interleaved with the calibration grid, not on it
    targets = [(200, 0, 110), (190, -60, 190), (250, 40, 270), (180, 30, 130)]
    test_poses = []
    for x, y, z in targets:
        s = A.solve_auto(x, y, z)
        if s["reachable"]:
            test_poses.append([s["base"], s["shoulder"], s["elbow"], s["wrist_pitch"]])

    debug_dir = os.path.join(os.path.dirname(OUT_PATH), "calib_debug")
    os.makedirs(debug_dir, exist_ok=True)
    client = A.ArmClient(WS_URL)
    await asyncio.wait_for(client.connect(), 6)
    await asyncio.sleep(0.8)
    print(f"verifying {len(test_poses)} held-out poses (predicted vs detected pixel)\n")

    errs = []
    for i, (b, s, e, wp) in enumerate(test_poses):
        xyz = A.forward(b, s, e, wp)
        pu, pv = project(P, [xyz["x"], xyz["y"], xyz["z"]])
        await move_to(client, b, s, e, wp, GRIP_OPEN, speed=60)  # gentle (unanchored arm)
        await asyncio.sleep(SETTLE_S)
        await set_joint(client, 4, WAGGLE_ROT_A, speed=GRIP_WAGGLE_SPEED)
        await asyncio.sleep(GRIP_SETTLE)
        f_a = median_frame()
        await set_joint(client, 4, WAGGLE_ROT_B, speed=GRIP_WAGGLE_SPEED)  # fast: short diff gap
        await asyncio.sleep(GRIP_SETTLE)
        f_b = median_frame()
        loc = locate_gripper(f_a, f_b)
        if loc is None:
            print(f"  test{i}  predicted=({pu:6.1f},{pv:6.1f})  detected=NONE (out of view)")
            continue
        du, dv, _, _ = loc
        err = ((pu - du) ** 2 + (pv - dv) ** 2) ** 0.5
        errs.append(err)
        print(f"  test{i}  tip=({xyz['x']:6.1f},{xyz['y']:6.1f},{xyz['z']:6.1f})  "
              f"predicted=({pu:6.1f},{pv:6.1f})  detected=({du:6.1f},{dv:6.1f})  err={err:5.1f}px")
        ov = f_b.copy()
        cv2.circle(ov, (int(pu), int(pv)), 10, (0, 0, 255), 2)    # predicted = red
        cv2.circle(ov, (int(du), int(dv)), 6, (0, 255, 0), -1)    # detected  = green
        cv2.imwrite(os.path.join(debug_dir, f"verify{i}_pred_vs_detected.jpg"), ov)

    await go_home(client, 40)   # slow return so the unanchored base isn't thrown off
    if errs:
        print(f"\nheld-out pixel error: mean={np.mean(errs):.1f}px  max={np.max(errs):.1f}px")
        print("(red circle = predicted from calibration, green dot = actually detected)")


def refit():
    """Re-solve from the correspondences already in calibration.json (no arm/camera)."""
    with open(OUT_PATH) as fh:
        data = json.load(fh)
    recs = data["correspondences"]
    pts3d = [r["xyz"] for r in recs]
    pts2d = [r["pixel"] for r in recs]
    print(f"re-fitting from {len(recs)} saved correspondences in {OUT_PATH}\n")
    solve_and_report(pts3d, pts2d, recs, data.get("image_size", [640, 480]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", type=int, default=20, help="number of calibration poses")
    ap.add_argument("--speed", type=int, default=120,
                    help="arm move speed deg/s (lower = less wiggle on an unanchored arm)")
    ap.add_argument("--settle", type=float, default=SETTLE_S,
                    help="seconds to wait after a move before capturing (raise if it wiggles)")
    ap.add_argument("--delay", type=int, default=0,
                    help="countdown seconds before the sweep, to step out of the camera view")
    ap.add_argument("--dry-run", action="store_true", help="print poses+FK, no movement")
    ap.add_argument("--refit", action="store_true",
                    help="re-solve from saved calibration.json (no arm/camera)")
    ap.add_argument("--verify", action="store_true",
                    help="held-out check: predict vs detect gripper at fresh poses")
    ap.add_argument("--homography", action="store_true",
                    help="calibrate a 2D table-plane homography (the robust overhead model)")
    args = ap.parse_args()
    if args.refit:
        refit()
    elif args.verify:
        asyncio.run(verify())
    elif args.homography:
        asyncio.run(run_homography(args))
    else:
        asyncio.run(run(args))
