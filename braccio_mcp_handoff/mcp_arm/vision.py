"""
vision.py - webcam capture + YOLO object detection with per-object color naming.

Pure perception, no arm dependency. Shared by:
  - vision_server.py  (live browser view; owns the webcam, runs tracking)
  - server.py         (MCP detect_color tool; reads the server, or falls back here)

A YOLO model localizes objects anywhere in the frame (no fixed centre ROI). For each
detection we sample colour from the object's *own* pixels -- the segmentation mask when
available, else the bounding-box crop -- and vote those pixels into a named colour bin.
This is far more robust than the old centre-crop HSV vote: the object can be anywhere,
background colour doesn't bleed in, and we also learn *what* the object is.

classify_frame() returns a dict that stays backward-compatible with the old caller
(top-level color/hue/rgb/confidence/roi describe the primary object) and adds object
identity, the `frame` size [W,H], and an `objects` list of every detection. Each object
carries bbox/center/center_norm (center_norm in [-1,1], (0,0)=frame centre) so callers
can map an object's screen position to arm motion.

The colour-naming hue ranges below are the tuning surface; the model + threshold are set
via ARM_YOLO_MODEL / ARM_YOLO_CONF.

CLI:  python vision.py --test           # one webcam capture, print result + snapshot
      python vision.py --image PATH     # classify a still image (no camera needed)
"""

import os
import sys

import cv2
import numpy as np

# --- Camera config (env-overridable) ------------------------------------------
CAM_INDEX = int(os.environ.get("ARM_CAM_INDEX", "0"))
SNAPSHOT = os.environ.get("ARM_CV_SNAPSHOT", "/tmp/arm_cv_last.jpg")
FRAME_W = int(os.environ.get("ARM_CAM_WIDTH", "640"))
FRAME_H = int(os.environ.get("ARM_CAM_HEIGHT", "480"))

# --- YOLO config --------------------------------------------------------------
YOLO_MODEL = os.environ.get("ARM_YOLO_MODEL", "yolo11s-seg.pt")  # small seg, ~20 MB
YOLO_CONF = float(os.environ.get("ARM_YOLO_CONF", "0.10"))       # detection threshold -- low on purpose:
#   the vision server's multiframe voting suppresses one-frame false positives, and marginal
#   objects (transparent bottle, pink can) only score ~0.1-0.3 (0.15 still dropped frames)
YOLO_DEVICE = os.environ.get("ARM_YOLO_DEVICE", "")              # "", "mps", "cpu" ("" = auto)
YOLO_IMGSZ = int(os.environ.get("ARM_YOLO_IMGSZ", "640"))        # inference size; lower = faster
MAX_OBJECTS = int(os.environ.get("ARM_YOLO_MAX", "10"))          # cap reported detections
# Tracker config: project botsort yaml tuned for low-conf objects + long occlusion
# (the arm sweeping over the scene); see tracker.yaml for the why.
YOLO_TRACKER = os.environ.get(
    "ARM_YOLO_TRACKER", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker.yaml"))

# --- Colour naming (tuning surface) -------------------------------------------
SAT_MIN = 60           # pixels below this saturation are "grey" -> ignored
VAL_MIN = 50           # pixels below this value are "dark" -> ignored
MIN_COLOR_FRAC = 0.05  # need this fraction of object pixels colourful, else "none"

# Named colours by OpenCV hue (H in 0..179). Red wraps the 0/179 seam.
COLOR_RANGES = [
    ("red",    [(0, 10), (170, 179)]),
    ("orange", [(11, 20)]),
    ("yellow", [(21, 33)]),
    ("green",  [(34, 85)]),
    ("cyan",   [(86, 95)]),
    ("blue",   [(96, 130)]),
    ("purple", [(131, 169)]),
]

# BGR used to draw each colour label on the annotated feed.
DISPLAY_BGR = {
    "red": (0, 0, 255), "orange": (0, 128, 255), "yellow": (0, 255, 255),
    "green": (0, 255, 0), "cyan": (255, 255, 0), "blue": (255, 0, 0),
    "purple": (255, 0, 255), "none": (200, 200, 200),
}


def open_camera(index=None):
    """Open the webcam (caller must release). Sets a modest resolution."""
    cap = cv2.VideoCapture(CAM_INDEX if index is None else index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    return cap


def name_color(pixels_bgr):
    """Name the dominant colour of a set of BGR pixels (an object's own pixels).

    `pixels_bgr` is an (N, 3) uint8 array. Greyish/dark pixels are discarded, the rest
    are voted into COLOR_RANGES. Returns (color, hue, rgb) or ("none", None, None) when
    too few pixels are colourful.
    """
    if pixels_bgr is None or len(pixels_bgr) == 0:
        return "none", None, None
    px = np.ascontiguousarray(pixels_bgr.reshape(-1, 1, 3).astype(np.uint8))
    hsv = cv2.cvtColor(px, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    H, S, V = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    colorful = (S >= SAT_MIN) & (V >= VAL_MIN)
    if int(colorful.sum()) < max(1, MIN_COLOR_FRAC * len(H)):
        return "none", None, None

    Hc = H[colorful]
    colorful_px = pixels_bgr[colorful]
    best_name, best_mask, best_count = None, None, 0
    for name, ranges in COLOR_RANGES:
        m = np.zeros_like(Hc, dtype=bool)
        for lo, hi in ranges:
            m |= (Hc >= lo) & (Hc <= hi)
        c = int(m.sum())
        if c > best_count:
            best_name, best_mask, best_count = name, m, c

    if best_name is None or best_count == 0:
        return "none", None, None
    sel = colorful_px[best_mask]               # M x 3, BGR
    mean_bgr = sel.mean(axis=0)
    hue = int(np.median(Hc[best_mask]))
    rgb = [int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0])]
    return best_name, hue, rgb


def _object_pixels(frame, x1, y1, x2, y2, mask):
    """BGR pixels belonging to one detection: mask pixels if available, else box crop."""
    if mask is not None:
        h, w = frame.shape[:2]
        if mask.shape != (h, w):
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
        sel = mask.astype(bool)
        pixels = frame[sel]
        if len(pixels):
            return pixels
    return frame[y1:y2, x1:x2].reshape(-1, 3)


def _empty_result(frame=None):
    fw, fh = (frame.shape[1], frame.shape[0]) if frame is not None else (None, None)
    return {"color": "none", "hue": None, "rgb": None, "confidence": 0.0,
            "object": None, "det_score": 0.0, "track_id": None,
            "roi": None, "region_frac": None, "frame": [fw, fh], "objects": []}


def _build_result(frame, r):
    """Turn an ultralytics Results object into our detection dict (schema in module doc)."""
    h, w = frame.shape[:2]
    boxes = getattr(r, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return _empty_result(frame)

    masks = getattr(r, "masks", None)
    mask_data = masks.data.cpu().numpy() if masks is not None else None
    names = r.names
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    clss = boxes.cls.cpu().numpy().astype(int)
    ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else None

    objects = []
    for i in range(len(xyxy)):
        x1, y1, x2, y2 = xyxy[i].astype(int)
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(w, int(x2)), min(h, int(y2))
        if x2 <= x1 or y2 <= y1:
            continue
        mask = mask_data[i] if mask_data is not None else None
        color, hue, rgb = name_color(_object_pixels(frame, x1, y1, x2, y2, mask))
        bw, bh = x2 - x1, y2 - y1
        cx, cy = x1 + bw / 2.0, y1 + bh / 2.0
        objects.append({
            "track_id": int(ids[i]) if ids is not None else None,
            "object": names.get(int(clss[i]), str(int(clss[i]))),
            "color": color, "hue": hue, "rgb": rgb,
            "det_score": round(float(confs[i]), 3),
            "bbox": [x1, y1, bw, bh],
            "center": [int(cx), int(cy)],
            # normalized to [-1, 1]; (0, 0) = frame centre, +u = right, +v = down
            "center_norm": [round((cx - w / 2.0) / (w / 2.0), 3),
                            round((cy - h / 2.0) / (h / 2.0), 3)],
            "area_frac": round(bw * bh / float(w * h), 3),
        })

    if not objects:
        return _empty_result(frame)
    objects.sort(key=lambda o: o["det_score"], reverse=True)
    objects = objects[:MAX_OBJECTS]

    p = objects[0]  # primary = highest detection score
    return {"color": p["color"], "hue": p["hue"], "rgb": p["rgb"],
            "confidence": p["det_score"], "object": p["object"],
            "det_score": p["det_score"], "track_id": p["track_id"],
            "roi": p["bbox"], "region_frac": None, "frame": [w, h],
            "objects": objects}


class Detector:
    """Lazily-loaded YOLO model. detect() is one-shot; track() keeps IDs across frames."""

    def __init__(self, model=None, conf=None, device=None):
        self.model_name = model or YOLO_MODEL
        self.conf = YOLO_CONF if conf is None else conf
        self.device = YOLO_DEVICE if device is None else device
        self._model = None

    def _ensure(self):
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(self.model_name)
            if not self.device:
                import torch
                self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        return self._model

    def load(self):
        """Eagerly import torch + load the weights (the slow one-time cost). Returns device."""
        self._ensure()
        return self.device

    def warmup(self):
        """Run one inference on a blank frame so the first real frame doesn't pay the
        kernel-compilation cost (the MPS first-call stall). Returns device."""
        m = self._ensure()
        dummy = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)
        m.predict(dummy, conf=self.conf, device=self.device, imgsz=YOLO_IMGSZ,
                  retina_masks=True, verbose=False)
        return self.device

    def detect(self, frame):
        """One-shot detection (no tracking IDs). Used by the MCP fallback path."""
        m = self._ensure()
        r = m.predict(frame, conf=self.conf, device=self.device, imgsz=YOLO_IMGSZ,
                      retina_masks=True, verbose=False)[0]
        return _build_result(frame, r)

    def track(self, frame):
        """Detection with persistent track IDs across frames (the server loop)."""
        m = self._ensure()
        r = m.track(frame, conf=self.conf, device=self.device, imgsz=YOLO_IMGSZ,
                    retina_masks=True, persist=True, verbose=False,
                    tracker=YOLO_TRACKER)[0]
        return _build_result(frame, r)


_detector = None


def get_detector():
    """Process-wide singleton so the model loads once."""
    global _detector
    if _detector is None:
        _detector = Detector()
    return _detector


def classify_frame(frame):
    """One-shot detect + colour-name every object in `frame` (a BGR image)."""
    return get_detector().detect(frame)


def annotate(frame, result):
    """Draw every detection's box + `class color #id score` caption onto `frame`."""
    objects = result.get("objects", [])
    if not objects:
        cv2.putText(frame, "no objects", (12, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (200, 200, 200), 2, cv2.LINE_AA)
        return frame
    for o in objects:
        x, y, bw, bh = o["bbox"]
        bgr = DISPLAY_BGR.get(o["color"], (200, 200, 200))
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), bgr, 2)
        idtxt = f"#{o['track_id']} " if o.get("track_id") is not None else ""
        label = f"{o['object']} {o['color']} {idtxt}{o['det_score']:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        ly = max(th + 6, y - 6)
        cv2.rectangle(frame, (x, ly - th - 6), (x + tw + 6, ly + 2), (0, 0, 0), -1)
        cv2.putText(frame, label, (x + 3, ly - 2), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, bgr, 1, cv2.LINE_AA)
    return frame


def capture_once(index=None, warmup=5):
    """Open the camera, discard a few warmup frames, return one BGR frame."""
    cap = open_camera(index)
    if not cap.isOpened():
        raise RuntimeError(f"could not open camera index {CAM_INDEX if index is None else index}")
    frame = None
    try:
        for _ in range(max(1, warmup)):
            ok, frame = cap.read()
        if frame is None or not ok:
            raise RuntimeError("camera opened but returned no frame")
    finally:
        cap.release()
    return frame


def detect_once(index=None):
    """One-shot capture + detect (used as the MCP fallback path)."""
    return classify_frame(capture_once(index))


if __name__ == "__main__":
    if "--image" in sys.argv:
        path = sys.argv[sys.argv.index("--image") + 1]
        frame = cv2.imread(path)
        if frame is None:
            raise SystemExit(f"could not read image: {path}")
    elif "--test" in sys.argv:
        frame = capture_once()
    else:
        raise SystemExit("usage: python vision.py --test | --image PATH")

    res = classify_frame(frame)
    cv2.imwrite(SNAPSHOT, annotate(frame.copy(), res))
    import json
    print(json.dumps(res, indent=2))
    print(f"annotated snapshot saved to {SNAPSHOT}")
