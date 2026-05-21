# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Per-type content editor + inline uploads in the v2 Screens view** — the per-zone editor previously had a generic "value" text input that asked operators to type filenames. It now shows the same type-aware UI the legacy admin had: textarea for text, URL input (YouTube URLs continue to auto-embed via the url module's `/youtube/` wrapper), a select-of-existing-media for video/picture/pdf/slideshow, news-mode picker for news, room-id input for screen_share. Each media type has an inline upload widget; picture uploads accept an existing-or-new subfolder. After a successful upload the just-uploaded file becomes the selected value automatically.
- **`GET /api/videos`, `/api/pdfs`, `/api/slideshows`** — list available media for the new dropdowns. Mirrors the existing `/api/pictures` shape.
- **Merged `staging/admin-redesign` into `main`** — the redesign branch had been the live deploy target for two days. Merge is a clean fast-forward.

### Changed
- **`POST /api/upload/picture` accepts an optional `subfolder` form field** — sanitises the value and creates the subfolder under `static/pictures/` if needed. Lets the v2 Screens view drive picture uploads (and slideshow folder creation) directly without falling back to the legacy admin.
- **Cutover: `/admin` is the redesigned (formerly v2) admin** (Phase 8 of `TASKS/PLAN_REDESIGN.md`). Sidebar with Screens/Lighting/Modules views, SVG floor plan, scene dropdown, Hue + LED integration, Alpine-driven UI. The previous Tailwind-based admin moved to `/admin/legacy` (kept for one release cycle then removed). `/admin/v2` continues to alias to the new admin so any operator bookmarks still resolve.
- **`screen.js` does a full frame reload when the content URL changes**. The WS reload message now carries the screen's current content URL; `screen.js` compares to the cached `window.contentUrl` and `window.location.reload()`s the frame on mismatch — which both swaps the visible content and picks up any latest `screen.js`. Same-URL reloads still use the popup `/updating` countdown beat.
- **`/updating` self-heals stale `screen.js`** — its inline script now `window.opener.location.reload()`s the frame as soon as the popup opens, so older popup-only `screen.js` versions get bootstrapped onto the latest code automatically on the next reload-all.
- **Scenes dropdown moved out of the top bar** into the Screens view, sitting to the right of the "Reload all" button. The dropdown is contextual to the view it belongs to.
- **Polish pass on the v2 chrome** — dropped the "v2" suffix from `<title>` and the small grey chip next to "Studio" in the header (cutover is done, no v1 to disambiguate against on `/admin`); removed the diagnostic `[studio v2]` console.logs from `shell.js` and `modules.js`; promoted the zone slug in the Selected-zone sidebar card from a labelled field-row to a small monospaced subtitle; removed the now-redundant "legacy admin" link from the header (still reachable at `/admin/legacy` directly).

### Fixed
- **`POST /api/screens/{id}/set_content` was silently dropping `news_mode` and `screen_share` updates** — the type-dispatch only handled text/url/video/picture/pdf/slideshow. Now `type=news` writes `news_mode` (validated against the model's portrait/landscape/presentation pattern) and `type=screen_share` writes the `screen_share` field. Pre-existing bug uncovered while wiring the v2 News and Screen Share editors.

### Repo hygiene
- **Stopped tracking `.claude/`** — Claude Code's per-user `settings.local.json` (a tool-permission whitelist) had been committed accidentally. Widened the existing `.claude/logs` ignore to the whole directory and removed the file from history going forward.

### Verified
- 2026-05-18 (round 1): `scripts/deploy.sh` from WSL → preflight passed; Pi was already at latest, so pi-update did nothing; reload-all returned `notified: [4, 5]` and the two stations refreshed.
- 2026-05-18 (round 2): same flow but with a fresh commit on origin/main — exercises the pull + reload path.
- 2026-05-19: Module registry end-to-end — `rgbdisplay` module visible at `/api/modules`; admin Modules tab renders it with live status; `Stop` button darkens the LED matrix, `Start` brings it back. The IoT-for-displays foundation works.
- 2026-05-19: Philips Hue paired and live — `scripts/hue_pair.py` succeeded against bridge `192.168.2.196` (model BSB002); Lights admin tab populated from the live bridge with 17 lights, 2 rooms (Maker, Studio), 28 named scenes. All-on / All-off, per-room, per-scene, per-light controls all verified working end-to-end. (4 lightstrips currently unreachable, suspected wardrobe power-circuit; not a software issue.)
- 2026-05-21: Cutover live — `/admin` serves the redesigned UI; `/admin/legacy` retains v1. Scene-driven content swap verified end-to-end (apply scene → stations swap content via the new screen.js hard-reload-on-URL-change path bootstrapped through the self-healing `/updating` page).

### Added
- **Philips Hue module + Lights admin tab** — new `modules/hue/` (config, client, routes, ServiceModule) talks to the Hue Bridge over the LAN via CLIP v1. Discovered the bridge at `192.168.2.196` via `discovery.meethue.com` from studiopi. `modules/hue/routes.py` mounts `/api/modules/hue/{lights, groups, scenes, all/on, all/off, lights/{id}, groups/{id}, scenes/{id}/recall, config}`. `templates/admin/lights.html` is a new top-level "Lights" tab with master on/off, per-room toggles with brightness sliders, scene-recall buttons, and per-light on/off + brightness + HEX color picker (HSV→xy conversion in-page JS). Bridge credentials live in `data/hue.json` (gitignored). `scripts/hue_pair.py` does the one-shot button-press pairing dance. Until paired the Lights tab shows pairing instructions; after pairing it lights up.
- **`docs/MODULES.md`** — operator + author guide for the module/registry system: how to use the admin Modules tab, the 10 built-in modules, how to write an in-code module (two files, five minutes), the external-manifest spec, full API reference, troubleshooting table, and the "adding a new content type" walkthrough that's now trivial.
- **External module registration (phase 5 of `TASKS/PLAN_MODULES.md`)** — `modules/external.py` defines `ExternalDisplayModule` / `ExternalServiceModule` that wrap a JSON manifest hosted by another service. Manifests declare `id`, `name`, `type`, `health_url`, `screen_url_pattern` (display) or `start_url` / `stop_url` (service); the registry fetches them, validates, and registers the result like any in-code module. New endpoints: `POST /api/modules/external` (register by manifest URL), `DELETE /api/modules/external/{id}` (remove), `POST /api/modules/refresh` (re-fetch all), `GET /api/modules/external` (list configured entries). Persisted in `data/modules.json` under `external[]`. The Modules admin tab grows an "Add external module" form + Refresh button + a ✕ delete button beside each external row. Colleagues can now host a robot dashboard (or anything) elsewhere and plug it into screen-mgr without touching the repo.

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
