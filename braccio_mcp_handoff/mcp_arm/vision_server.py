"""
vision_server.py - the single webcam owner + live browser view.

A background thread continuously captures frames, runs YOLO tracking
(vision.Detector.track -> objects with persistent IDs + sampled colour), and keeps
the latest annotated JPEG + result. Flask serves:
  GET /         a page with the live feed + the detected-object list
  GET /stream   MJPEG (multipart/x-mixed-replace) of the annotated feed
  GET /color    JSON of the latest detection  (the MCP detect_color reads this)
  GET /frame    latest annotated frame as a single JPEG  (the MCP look tool reads this)

Run:  python vision_server.py      then open http://localhost:8000
Env:  ARM_CAM_INDEX (default 0), ARM_VISION_PORT (default 8000),
      ARM_YOLO_MODEL (default yolo11n-seg.pt), ARM_YOLO_CONF (default 0.35)
"""

import logging
import os
import threading
import time
from collections import deque

import cv2
from flask import Flask, Response, jsonify

import vision as V

PORT = int(os.environ.get("ARM_VISION_PORT", "8000"))
# Multiframe voting: an object must appear in >= VOTE_MIN of the last VOTE_WINDOW frames
# (by track_id) to be reported. Marginal detections (e.g. a transparent bottle at ~0.1-0.3
# confidence) flicker in and out frame to frame; voting makes the reported list stable
# enough to target a grab, without raising the confidence threshold and losing the object.
# The window also bounds COASTING (see the loop): a voted object that drops out keeps its
# last bbox for up to VOTE_WINDOW frames, so 30 bridges multi-second detection dropouts.
VOTE_WINDOW = int(os.environ.get("ARM_VISION_VOTE_WINDOW", "30"))
VOTE_MIN = int(os.environ.get("ARM_VISION_VOTE_MIN", "2"))

app = Flask(__name__)

_lock = threading.Lock()
_state = {"jpeg": None, "raw_jpeg": None, "status": "starting",
          "result": {"color": "none", "confidence": 0.0,
                     "hue": None, "rgb": None, "objects": []}}
_running = True

_T0 = time.time()


def _log(msg):
    """Timestamped, flushed progress line so startup never looks stuck."""
    print(f"[vision +{time.time() - _T0:5.1f}s] {msg}", flush=True)


def _set_status(status):
    with _lock:
        _state["status"] = status


_latest_frame = None   # newest camera frame (BGR), shared capture -> detect


def _detect_loop():
    """Run YOLO tracking on the newest frame at whatever rate the model manages.
    Decoupled from capture so detection latency doesn't throttle /raw -- the marker
    servo needs FRESH raw frames or it measures pre-move gripper positions and learns
    a bad Jacobian (live failure: probe response measured at 7-26 px/unit instead of
    ~90, then the grab closed shallow or behind the object)."""
    global _latest_frame
    detector = V.Detector()
    _set_status("loading model")
    _log(f"loading {detector.model_name} - importing PyTorch (first run also downloads "
         f"the weights, ~20 MB for yolo11s-seg). This is the slow part, ~10-30s ...")
    t = time.time()
    dev = detector.load()
    _log(f"model loaded on '{dev}' in {time.time() - t:.1f}s.")

    _set_status("warming up")
    _log("warming up (compiling GPU kernels on the first inference) ...")
    t = time.time()
    detector.warmup()
    _log(f"warmup done in {time.time() - t:.1f}s.")

    _set_status("ready")
    _log(f"READY  ->  open http://localhost:{PORT}")

    history = deque(maxlen=VOTE_WINDOW)   # recent frames' track_id sets, for voting
    last_seen = {}                        # track_id -> (frame_idx, object dict)
    fidx = 0
    while _running:
        with _lock:
            frame = _latest_frame
        if frame is None:
            time.sleep(0.05)
            continue
        frame = frame.copy()              # capture keeps writing; detect on a snapshot
        result = detector.track(frame)
        # MULTIFRAME VOTE: report objects whose track_id appeared in >= VOTE_MIN of the
        # last VOTE_WINDOW frames. Also COAST: a voted object missing from just this
        # frame keeps its last bbox (flagged "coasted") -- marginal detections flicker,
        # and a grab target vanishing for one frame shouldn't drop it from the scene.
        fidx += 1
        cur = {o["track_id"]: o for o in result.get("objects", [])
               if o.get("track_id") is not None}
        for tid, o in cur.items():
            last_seen[tid] = (fidx, o)
        history.append(set(cur))
        votes = {}
        for ids in history:
            for tid in ids:
                votes[tid] = votes.get(tid, 0) + 1
        if len(history) >= VOTE_MIN:
            objs = [o for o in result.get("objects", [])
                    if o.get("track_id") is None
                    or votes.get(o["track_id"], 0) >= VOTE_MIN]
            for tid, n in votes.items():
                if n >= VOTE_MIN and tid not in cur and tid in last_seen:
                    seen_at, o = last_seen[tid]
                    if fidx - seen_at <= VOTE_WINDOW:
                        objs.append({**o, "coasted": fidx - seen_at})
            result["objects"] = objs
        if len(last_seen) > 64:           # prune stale ids
            last_seen = {t: v for t, v in last_seen.items()
                         if fidx - v[0] <= 4 * VOTE_WINDOW}
        V.annotate(frame, result)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with _lock:
                _state["jpeg"] = buf.tobytes()
                _state["result"] = result


def _capture_loop():
    """Own the camera and keep /raw fresh at camera rate; detection runs in its own
    thread on the newest frame. Draining the camera at full rate also keeps OpenCV's
    frame buffer from backing up (a slow read loop serves stale frames). /raw serves
    the un-annotated frame for the marker servo and calibrate.py frame-differencing,
    so boxes don't pollute it."""
    global _latest_frame
    cap = None
    try:
        _set_status("opening camera")
        _log(f"opening camera {V.CAM_INDEX} ...")
        cap = V.open_camera()
        if not cap.isOpened():
            _set_status("error: camera")
            _log(f"ERROR: could not open camera {V.CAM_INDEX}. Is it free, and is camera "
                 f"permission granted to this terminal? (System Settings > Privacy > Camera)")
            return
        ok, frame = cap.read()
        if not ok or frame is None:
            _set_status("error: camera")
            _log("ERROR: camera opened but returned no frame.")
            return
        _log(f"camera open ({frame.shape[1]}x{frame.shape[0]}).")

        threading.Thread(target=_detect_loop, daemon=True).start()

        while _running:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue
            ok_raw, raw_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            with _lock:
                _latest_frame = frame
                if ok_raw:
                    _state["raw_jpeg"] = raw_buf.tobytes()
    finally:
        if cap is not None:
            cap.release()
        _log("camera released")


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Arm vision</title>
<style>
  body{background:#111;color:#eee;font-family:system-ui,sans-serif;text-align:center;margin:0;padding:20px}
  img{max-width:90vw;border:1px solid #333;border-radius:8px}
  #count{font-size:20px;margin-top:14px;color:#bbb}
  #objs{list-style:none;padding:0;margin:12px auto 0;max-width:520px;text-align:left}
  #objs li{display:flex;align-items:center;gap:10px;padding:8px 12px;margin:6px 0;
           background:#1b1b1b;border:1px solid #2a2a2a;border-radius:8px;
           font-size:18px;font-variant-numeric:tabular-nums}
  .dot{display:inline-block;width:18px;height:18px;border-radius:50%;
       border:1px solid #555;flex:0 0 auto}
  .cls{font-weight:600}
  .id{color:#888}
  .meta{margin-left:auto;color:#888;font-size:14px}
  .empty{color:#777}
</style></head>
<body>
  <h2>Robot arm &mdash; object detection (YOLO)</h2>
  <img src="/stream" alt="camera feed">
  <div id="count">starting up&hellip;</div>
  <ul id="objs"></ul>
<script>
  const STARTING = {starting:'starting up', 'opening camera':'opening camera',
    'loading model':'loading model (importing PyTorch / downloading weights)',
    'warming up':'warming up the model'};
  function row(o){
    const id = (o.track_id!=null) ? ('#'+o.track_id) : '';
    const rgb = o.rgb ? 'rgb('+o.rgb.join(',')+')' : '#333';
    return '<li><span class="dot" style="background:'+rgb+'"></span>'
      + '<span class="cls">'+o.object+'</span>'
      + '<span>'+o.color+'</span>'
      + '<span class="id">'+id+'</span>'
      + '<span class="meta">'+(o.det_score*100).toFixed(0)+'%</span></li>';
  }
  async function poll(){
    try{
      const r = await fetch('/color'); const d = await r.json();
      const count = document.getElementById('count');
      const list = document.getElementById('objs');
      if (d.status && d.status !== 'ready'){
        count.textContent = (STARTING[d.status] || d.status) + '…';
        list.innerHTML = '';
        return;
      }
      const objs = d.objects || [];
      count.textContent =
        objs.length ? (objs.length+' object'+(objs.length>1?'s':'')+' detected') : 'no objects';
      list.innerHTML =
        objs.length ? objs.map(row).join('')
                    : '<li class="empty">hold an object up to the camera</li>';
    }catch(e){}
  }
  setInterval(poll, 250); poll();
</script>
</body></html>"""


@app.route("/")
def index():
    return PAGE


@app.route("/color")
def color():
    with _lock:
        return jsonify({**_state["result"], "status": _state["status"]})


@app.route("/frame")
def frame():
    """Latest annotated frame as a single JPEG (what the MCP `look` tool fetches)."""
    with _lock:
        jpeg = _state["jpeg"]
    if jpeg is None:
        return ("no frame yet", 503)
    return Response(jpeg, mimetype="image/jpeg")


@app.route("/raw")
def raw():
    """Latest UN-annotated frame as a single JPEG (no detection boxes drawn).
    Used by calibrate.py for clean move-and-detect frame-differencing."""
    with _lock:
        jpeg = _state["raw_jpeg"]
    if jpeg is None:
        return ("no frame yet", 503)
    return Response(jpeg, mimetype="image/jpeg")


def _mjpeg():
    boundary = b"--frame"
    while True:
        with _lock:
            jpeg = _state["jpeg"]
        if jpeg is None:
            time.sleep(0.05)
            continue
        yield (boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
        time.sleep(0.04)  # ~25 fps cap


@app.route("/stream")
def stream():
    return Response(_mjpeg(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    # Quiet Werkzeug's per-request logging (the /stream + /color polls would spam it);
    # our own _log() lines carry the useful startup progress.
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    _log(f"starting vision server (camera {V.CAM_INDEX}, model {V.YOLO_MODEL}) ...")
    _log("the browser page will say 'starting up' until the model is warmed up.")
    t = threading.Thread(target=_capture_loop, daemon=True)
    t.start()
    try:
        app.run(host="0.0.0.0", port=PORT, threaded=True)
    finally:
        _running = False
