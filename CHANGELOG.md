# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Verified
- 2026-05-18 (round 1): `scripts/deploy.sh` from WSL → preflight passed; Pi was already at latest, so pi-update did nothing; reload-all returned `notified: [4, 5]` and the two stations refreshed.
- 2026-05-18 (round 2): same flow but with a fresh commit on origin/main — exercises the pull + reload path.
- 2026-05-19: Module registry end-to-end — `rgbdisplay` module visible at `/api/modules`; admin Modules tab renders it with live status; `Stop` button darkens the LED matrix, `Start` brings it back. The IoT-for-displays foundation works.

### Changed
- **Content types are now registered display modules (phase 4 of `TASKS/PLAN_MODULES.md`)**. Each former hard-coded type (`url`, `text`, `video`, `picture`, `pdf`, `slideshow`, `news`, `screen_share`, `default`) is a thin `modules/<id>/__init__.py` DisplayModule wrapper around the existing per-type URL logic. `routes/screen_routes.py` resolves content via `registry.get(screen.type).get_screen_url(screen, base_url)` instead of an if/elif chain — falls back to the `default` module if the type isn't a registered display module. The admin screens-tab dropdown is now generated from the registry's display modules (sorted by registration order). `/api/screens/{id}/set_content` validates against the live registry, not a hardcoded list. Adding a new content type now means: drop a folder under `modules/`, register it, done.

### Added
- **Modules admin tab (phase 3 of `TASKS/PLAN_MODULES.md`)** — `templates/admin/modules.html` rendering the registry, with availability badge, enabled toggle, and Start/Stop buttons for service modules. Polls `/api/modules` every 5s for live status; shows the last action outcome inline. Tab added between Screen Share and AI News in the main admin nav.
- **Module registry (phase 1+2 of `TASKS/PLAN_MODULES.md`)** — `modules/` package containing `Module` / `DisplayModule` / `ServiceModule` base classes plus a `ModuleRegistry` singleton that built-in modules self-register with at import time. Enabled state persists to `data/modules.json`.
- **`rgbdisplay` as the inaugural Module** — `modules/rgbdisplay/` wraps the existing `rgbdisplay.service` systemd unit on studiopi. Surfaces `available` / `active` / `enabled` status via `systemctl is-active|is-enabled`, and `start()` / `stop()` shell out to `sudo systemctl` (admin user has NOPASSWD on the Pi).
- HTTP endpoints `/api/modules`, `/api/modules/{id}`, `/api/modules/{id}/{enable,disable,start,stop}` — wired through the new `routes/modules_routes.py` and included in the composite router.
- `docs/DEPLOY.md` — operator-facing guide for the dev-to-Pi deploy flow (SSH key setup, daily workflow, what `deploy.sh` / `pi-update.sh` do, troubleshooting, teammate onboarding).
- `docs/ARCHITECTURE.md` — system spec covering the two roles of Raspberry Pi (admin hub vs display station), the launcher-script + screen-session + systemd-unit microservice pattern, communication channels, and a template for plugging in a new service. Frames the extensible-system direction.
- Auto-cache-bust for static assets via `utils.APP_VERSION` (short git SHA). Templates use `?v={{ app_version }}` so every deploy invalidates browser caches on connected stations automatically.
- `GET /admin/ssh.bat?host=<ip>` — admin downloads a `.bat` that runs `wsl ssh screen@<host>` and pauses. The "ssh screen@<ip>" hint beside each connected station is now a one-click launcher to a CMD session.
- Admin panel now shows the **client IP** of each connected station next to its name. `Screen.client_host` is populated from `websocket.client.host` on connect, surfaced through the `screen_status_update` WebSocket message and the `/api/screens` response, and rendered in `templates/admin/screens.html`. Foundation for future remote-control of stations (SSH/agent deployment).
- `GET /updating` (`routes/content_routes.py` + `templates/content/updating.html`) — transient page shown on screens during deploys. Maintenance-styled with a 10s countdown, then auto-redirects to `?return_to=<url>`. Makes the deploy/refresh loop visible to viewers instead of a silent flash.
- `static/javascript/screen.js` now sends the visible content popup to `/updating?return_to=<original>` on WebSocket reload, falling back to a full frame reload if the popup is gone. The "Updating" feature uses the same visual language as `scripts/maintenance.py`.
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
