"""Maintenance-mode page server for screen-mgr.

Serves a single styled page on every URL, so the admin panel / screen URLs
can return something friendly while the FastAPI service is restarting.

Used by the deploy script to bridge the gap between stopping the old
uvicorn and starting the new one. Can also be run standalone for ad-hoc
maintenance windows.

Examples:
    python3 scripts/maintenance.py                # :8000, until Ctrl+C
    python3 scripts/maintenance.py --duration 10  # :8000, auto-exit after 10s
    python3 scripts/maintenance.py --port 8080
"""

from __future__ import annotations

import argparse
import http.server
import socketserver
import threading

HTML = b"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="2">
<title>screen-mgr maintenance</title>
<style>
 html,body{height:100%;margin:0}
 body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
      display:flex;flex-direction:column;justify-content:center;align-items:center;
      background:#1a1a1a;color:#e0e0e0;gap:1em;text-align:center;padding:1em}
 h1{color:#ffaa00;font-size:clamp(2em,8vw,3.5em);margin:0;letter-spacing:0.04em}
 p{font-size:clamp(1em,3vw,1.4em);color:#888;margin:0}
 .dots::after{content:"...";animation:d 1.2s steps(4,end) infinite;
              display:inline-block;width:1.4em;text-align:left}
 @keyframes d{
  0%{content:""} 25%{content:"."} 50%{content:".."} 75%,100%{content:"..."}
 }
</style></head><body>
<h1>Maintenance</h1>
<p>screen-mgr is restarting<span class="dots"></span></p>
</body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, *_args):
        pass


def serve(port: int, duration: int) -> None:
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("0.0.0.0", port), _Handler)
    if duration > 0:
        threading.Timer(duration, lambda: (srv.shutdown(), srv.server_close())).start()
    suffix = f"for {duration}s" if duration > 0 else "(Ctrl+C to stop)"
    print(f"maintenance page on :{port} {suffix}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
        srv.server_close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--duration", type=int, default=0,
                   help="seconds to run before auto-exit; 0 = until killed")
    args = p.parse_args()
    serve(args.port, args.duration)


if __name__ == "__main__":
    main()
