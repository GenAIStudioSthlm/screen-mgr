# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Verified
- 2026-05-18: end-to-end deploy through `scripts/deploy.sh` exercised for the first time with Station 2 and Station 3 connected as screens #4 and #5.

### Added
- `scripts/deploy.sh` — dev-side WSL entry point. Preflight (clean tree, no unpushed commits), SSH to Pi to run `pi-update.sh`, then `POST /api/screens/reload-all` so every connected display refreshes itself.
- `scripts/pi-update.sh` — Pi-side script invoked over SSH by `deploy.sh`. Bails if already up to date; otherwise pulls main, restarts the service through the maintenance bridge only if `requirements.txt` changed, else lets uvicorn `--reload` do the work. Logs commit hash to `last_deploy.log`.
- `POST /api/screens/reload-all` (`routes/api_routes.py`) — broadcasts a WebSocket reload to every connected screen and returns JSON of `notified` / `skipped` lists.
- `scripts/start_screen_mgr.sh` — canonical wrapper that launches the screen-mgr FastAPI server inside a named GNU screen session. Idempotent: kills any existing session with the same name (and any straggler `uvicorn main:app` processes) before starting fresh. Mirrors the `start_display.sh` pattern.
- `scripts/systemd/screen-mgr.service` — systemd unit that calls `start_screen_mgr.sh` as user `admin`. `Type=oneshot` + `RemainAfterExit=yes` because `screen -dmS` detaches immediately.
- `scripts/systemd/rgbdisplay.service` — systemd unit that calls the existing `/home/admin/rpi-rgb-led-matrix/start_display.sh` as root (LED matrix needs GPIO).
- `scripts/maintenance.py` — standalone Python web server that serves a styled "screen-mgr restarting" page on configurable port for a configurable duration. Page auto-refreshes every 2s and sends `Cache-Control: no-store`, so connected browsers automatically return to the real admin once it comes back up. Designed to be called by the future deploy script to bridge the restart gap.

### Changed
- `.gitignore` — added explicit patterns for `.env`, `.env.*`, `*.key`, `*.pem`, `id_ed25519*`, `id_rsa*`, `authorized_keys` to harden against accidental secret commits.

### Fixed
- WebSocket handler now returns early when `ConnectionManager.connect()` rejects a connection, preventing the receive loop from running on a rejected socket (`routes/websocket_routes.py`)
- News presentation template no longer renders an empty `.p-bg`/`.p-overlay` when an article has no image (`templates/content/news_presentation.html`)
