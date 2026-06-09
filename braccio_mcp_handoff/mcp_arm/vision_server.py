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

import cv2
from flask import Flask, Response, jsonify

import vision as V

PORT = int(os.environ.get("ARM_VISION_PORT", "8000"))

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


def _capture_loop():
    """Own the camera, load + warm up the model, then keep the latest JPEG + detection fresh.
    Each slow step (camera open, PyTorch import + weights, GPU warmup) prints progress."""
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

        detector = V.Detector()
        _set_status("loading model")
        _log(f"loading {detector.model_name} - importing PyTorch (first run also downloads "
             f"~6 MB weights). This is the slow part, ~10-30s ...")
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

        while _running:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue
            result = detector.track(frame)
            # Encode the RAW frame before annotation -- /raw serves this for
            # frame-differencing (calibrate.py move-and-detect), so detection
            # boxes don't pollute the diff.
            ok_raw, raw_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            V.annotate(frame, result)
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                with _lock:
                    _state["jpeg"] = buf.tobytes()
                    if ok_raw:
                        _state["raw_jpeg"] = raw_buf.tobytes()
                    _state["result"] = result
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
