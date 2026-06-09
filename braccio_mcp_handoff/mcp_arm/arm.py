"""
arm.py - WebSocket client + inverse/forward kinematics for the Braccio arm.

Talks to the Arduino firmware (robot_arm.ino) over its WebSocket protocol:
  outbound:  MOVE:b,s,e,wp,wr,g,stepDelay  | J:idx:val | STREAM:... | SPD:degPerSec
  inbound:   POS:b,s,e,wp,wr,g  (broadcast ~10 Hz while moving + once on settle)

Joint index order matches the firmware/web UI:
  [0]=base  [1]=shoulder  [2]=elbow  [3]=wrist pitch (vertical)  [4]=wrist rot  [5]=gripper

The IK/FK below is a faithful port of the browser code in index_html.h.
"""

import asyncio
import math

import websockets

# --- Link geometry (mm). Mirror index_html.h; tune on the real arm. -----------
L0, L1, L2, L3 = 71.5, 125.0, 125.0, 137.0
DEG = 180.0 / math.pi
RAD = math.pi / 180.0

# Servo limits, mirroring robot_arm.ino posMin/posMax (gripper closes to 130).
POS_MIN = [0, 15, 0, 0, 0, 10]
POS_MAX = [180, 165, 180, 180, 180, 130]
HOME = [90, 90, 90, 90, 90, 73]
JOINT_NAMES = ["base", "shoulder", "elbow", "wrist_pitch", "wrist_rot", "gripper"]


def clampv(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


# --- Inverse kinematics (port of solveIK in index_html.h) ---------------------
def solve_ik(x, y, z, phi_deg, elbow_up=True):
    """Target fingertip (x,y,z) mm, approach angle phi_deg from horizontal
    (-90 = straight down). Returns servo angles + geometric link angles."""
    phi = phi_deg * RAD
    reachable = True

    yaw = math.atan2(y, x)
    base = 90 + yaw * DEG                      # servo 90 -> +X (straight forward)
    if base < 0 or base > 180:
        reachable = False
    base = clampv(base, 0, 180)

    r = math.hypot(x, y)
    Wr = r - L3 * math.cos(phi)                # wrist pivot in the (r,z) plane
    Wz = z - L3 * math.sin(phi)
    dr, dz = Wr, Wz - L0
    D = math.hypot(dr, dz)
    reach_max, reach_min = L1 + L2, abs(L1 - L2)
    if D > reach_max:
        s = reach_max / D
        Wr, dr, dz = s * Wr, s * Wr, s * dz
        Wz, D = L0 + dz, reach_max
        reachable = False
    elif D < reach_min and D > 1e-6:
        s = reach_min / D
        Wr, dr, dz = s * Wr, s * Wr, s * dz
        Wz, D = L0 + dz, reach_min
        reachable = False

    beta = math.atan2(dz, dr)
    cos_elbow = clampv((L1 * L1 + L2 * L2 - D * D) / (2 * L1 * L2), -1, 1)
    elbow_interior = math.acos(cos_elbow)
    cos_alpha = clampv((L1 * L1 + D * D - L2 * L2) / (2 * L1 * D), -1, 1)
    alpha = math.acos(cos_alpha)

    sign = 1 if elbow_up else -1
    A1 = beta + sign * alpha                   # upper arm absolute angle
    A2 = A1 + sign * (elbow_interior - math.pi)
    A3 = phi

    shoulder = 180 - A1 * DEG
    elbow = 90 - (A2 - A1) * DEG
    wrist_pit = 90 - (A3 - A2) * DEG
    if shoulder < 15 or shoulder > 165:
        reachable = False
    if elbow < 0 or elbow > 180:
        reachable = False
    if wrist_pit < 0 or wrist_pit > 180:
        reachable = False

    return {
        "reachable": reachable,
        "base": int(round(clampv(base, 0, 180))),
        "shoulder": int(round(clampv(shoulder, 15, 165))),
        "elbow": int(round(clampv(elbow, 0, 180))),
        "wrist_pitch": int(round(clampv(wrist_pit, 0, 180))),
        "A1": A1, "A2": A2, "A3": A3, "yaw": yaw, "phi": phi_deg,
    }


def solve_best(x, y, z, phi_pref):
    """Scan approach angles, pick the reachable one closest to phi_pref."""
    best, best_cost = None, 1e9
    phi = -90
    while phi <= 90:
        s = solve_ik(x, y, z, phi)
        if s["reachable"]:
            cost = abs(phi - phi_pref)
            if cost < best_cost:
                best_cost, best = cost, s
                best["phi"] = phi
        phi += 3
    if best is not None:
        return best
    fphi = clampv(round(phi_pref), -90, 90)          # nothing reachable: best effort
    fb = solve_ik(x, y, z, fphi)
    fb["phi"] = fphi
    return fb


def solve_auto(x, y, z):
    """Auto approach: prefer pointing along the reach direction."""
    return solve_best(x, y, z, math.atan2(z - L0, math.hypot(x, y)) * DEG)


# --- Forward kinematics (port of forward()/renderArm in index_html.h) ---------
def forward(base, shoulder, elbow, wrist_pitch):
    """Servo angles -> fingertip position (mm)."""
    yaw = (base - 90) * RAD
    A1 = (180 - shoulder) * RAD
    A2 = A1 + (90 - elbow) * RAD
    A3 = A2 + (90 - wrist_pitch) * RAD
    Er, Ez = L1 * math.cos(A1), L0 + L1 * math.sin(A1)
    Wr, Wz = Er + L2 * math.cos(A2), Ez + L2 * math.sin(A2)
    Tr, Tz = Wr + L3 * math.cos(A3), Wz + L3 * math.sin(A3)
    return {"x": Tr * math.cos(yaw), "y": Tr * math.sin(yaw), "z": Tz}


# --- WebSocket client ---------------------------------------------------------
class ArmClient:
    def __init__(self, url):
        self.url = url
        self.ws = None
        self.pose = list(HOME)
        self.connected = False

    async def connect(self):
        self.ws = await websockets.connect(self.url, ping_interval=20, max_queue=8)
        self.connected = True
        asyncio.create_task(self._reader())

    async def _reader(self):
        try:
            async for msg in self.ws:
                if isinstance(msg, (bytes, bytearray)):
                    msg = msg.decode("utf-8", "ignore")
                if msg.startswith("POS:"):
                    parts = msg[4:].split(",")
                    if len(parts) == 6:
                        try:
                            self.pose = [int(p) for p in parts]
                        except ValueError:
                            pass
        except Exception:
            pass
        finally:
            self.connected = False

    async def ensure(self):
        """(Re)connect if needed."""
        if not self.connected or self.ws is None:
            await self.connect()

    async def send(self, cmd):
        await self.ensure()
        try:
            await self.ws.send(cmd)
        except Exception:
            self.connected = False
            await self.ensure()
            await self.ws.send(cmd)

    async def wait_settled(self, target=None, timeout=8.0, tol=2, stable=0.6):
        """Block until the arm actually finishes moving. Returns True when the
        pose reaches `target` (within `tol`) OR the pose has been unchanged for
        `stable` seconds (genuinely stopped/stalled). The long stable window is
        the key: the firmware only broadcasts pose at ~10 Hz, so a short window
        could mistake two slow updates mid-move for "settled" and read a stale
        position. `stable` seconds of no change means the arm has really stopped."""
        loop = asyncio.get_event_loop()
        start = loop.time()
        last = None
        last_change = start
        while loop.time() - start < timeout:
            await asyncio.sleep(0.05)
            cur = list(self.pose)
            now = loop.time()
            if target is not None and all(abs(cur[i] - target[i]) <= tol for i in range(6)):
                return True
            if cur != last:
                last, last_change = cur, now
            elif now - last_change >= stable:
                return True
        return False
