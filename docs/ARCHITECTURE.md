# screen-mgr Architecture

How the pieces fit, and the conventions a new "service" should follow to plug in.

## The picture

```
┌──────────────────────────────────────────────┐
│ studiopi  (admin hub + content origin)       │
│                                              │
│  systemd  ─►  screen-mgr.service             │
│                  │                           │
│                  ▼                           │
│              screen mgr 'screen-mgr'         │
│                  │                           │
│                  ▼                           │
│          uvicorn  (FastAPI on :8000)         │
│             │       │        │               │
│             ▼       ▼        ▼               │
│           /admin  /api    /ws/{id}           │
│                                              │
│  systemd  ─►  rgbdisplay.service             │
│                  │                           │
│                  ▼                           │
│              screen mgr 'rgbdisplay'         │
│                  │                           │
│                  ▼                           │
│          python led_clock.py (root, GPIO)    │
└──────────────┬───────────────────────────────┘
               │ WebSocket
        ┌──────┴────────────────┐
        ▼                       ▼
 ┌──────────────────┐   ┌──────────────────┐
 │ Station 2 (Pi)   │   │ Station 3 (Pi)   │
 │ Chromium kiosk   │   │ Chromium kiosk   │
 │ → /screen/4      │   │ → /screen/5      │
 │   ↳ popup to     │   │   ↳ popup to     │
 │     /news/…      │   │     /news/…      │
 └──────────────────┘   └──────────────────┘
```

## Two roles of Raspberry Pi

| Role | Host | User | Runs | Authoritative? |
|---|---|---|---|---|
| **Admin hub** | `studiopi.local` | `admin` (key auth) | FastAPI + admin UI + WebSocket hub; LED matrix | Yes — the single source of truth for screen state |
| **Display station** | `mainscreen.local` (and others) | `screen` (password=`screen`) | Chromium in kiosk mode pointed at `studiopi:8000/screen/<id>` | No — pulls content from the hub |

Stations are dumb displays. The hub owns the state. State propagates via WebSocket reload messages.

## The microservice pattern

Every long-running process on either Pi follows the same three-piece pattern:

1. **A launcher script** (`scripts/start_*.sh` or similar) — owns the exact invocation of the process. Idempotent: kill any existing session with the same name, then start fresh.
2. **A named GNU `screen` session** — wraps the process so a human can attach for live logs.
3. **A systemd unit** (`scripts/systemd/*.service`) that calls the launcher. `Type=oneshot`, `RemainAfterExit=yes` because `screen -dmS` detaches immediately.

The units in `scripts/systemd/` are symlinked into `/etc/systemd/system/` on the Pi, so editing them in the repo and `git pull`-ing applies the changes (after `systemctl daemon-reload`).

### Why this trio?

- **Launcher script** is the single source of truth for "what command starts this service". Humans and systemd use the same entrypoint.
- **screen session** lets an operator `screen -r <name>` and see real-time stdout — invaluable when debugging from a serial console or SSH.
- **systemd unit** handles boot-time startup and the `systemctl start/stop/restart` lifecycle.

## Existing services (today)

| Service | Pi | Launcher | systemd unit | Screen session name | User |
|---|---|---|---|---|---|
| `screen-mgr` | studiopi | `scripts/start_screen_mgr.sh` | `scripts/systemd/screen-mgr.service` | `screen-mgr` | `admin` |
| `rgbdisplay` (LED matrix clock) | studiopi | `/home/admin/rpi-rgb-led-matrix/start_display.sh` | `scripts/systemd/rgbdisplay.service` | `rgbdisplay` | `root` (GPIO) |
| Maintenance bridge (transient) | studiopi | `scripts/maintenance.py` | n/a — spawned inline by `pi-update.sh` during deploys with deps changes | n/a | `admin` |

## Communication patterns

| From | To | Channel | Purpose |
|---|---|---|---|
| Dev machine | studiopi | `ssh` (key auth) | Deploy (`scripts/deploy.sh` → `scripts/pi-update.sh`) |
| Admin UI | studiopi backend | HTTP | Content CRUD, `/api/screens/...`, `/admin/update` |
| Stations | studiopi backend | WebSocket `/ws/{id}` | Receive reload messages |
| studiopi backend | Stations | WebSocket | Push reload (via `connection_manager.notify_screen`) |
| Admin UI | studiopi backend | WebSocket `/ws-screen-status` | Live connection status of all stations |
| Operator | Station | `ssh screen@<ip>` (password auth) | Debug a stuck station; "ssh.bat" link in admin downloads a launcher |

Identity of stations is captured server-side via `WebSocket.client.host` on connect and surfaced in `/api/screens` and the admin UI.

## How a new service plugs in

Use this template for anything that wants to be a managed, deployable, boot-resilient service.

1. **Write the launcher** at `scripts/start_<name>.sh`:

   ```bash
   #!/bin/bash
   set -e
   SCREEN_NAME="<name>"
   screen -S "$SCREEN_NAME" -X quit 2>/dev/null || true
   # ... wait for resources to free if needed ...
   screen -dmS "$SCREEN_NAME" <command that runs your process>
   ```

   Mark it executable with `git update-index --chmod=+x` so the Pi gets the bit.

2. **Write the unit** at `scripts/systemd/<name>.service`:

   ```ini
   [Unit]
   Description=<name> — <one-line summary>
   After=network.target
   [Service]
   Type=oneshot
   RemainAfterExit=yes
   User=admin       # or root if it needs GPIO/sudo
   ExecStart=/bin/bash /home/admin/screen-mgr/scripts/start_<name>.sh
   ExecStop=/usr/bin/screen -S <name> -X quit
   [Install]
   WantedBy=multi-user.target
   ```

3. **Install on the Pi** (one-time per environment):

   ```bash
   sudo ln -sf /home/admin/screen-mgr/scripts/systemd/<name>.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now <name>.service
   ```

4. **If the service exposes HTTP**, add a route file in `routes/<name>_routes.py` and include it from `routes/routes.py`. Templates that need it can use `{{ app_version }}` for cache-busting.

5. **If it's an external service (on a station, not on studiopi)** — it still follows the same pattern but lives on the station, deployed there. Use `ssh screen@<station>` to install.

## Planned services (in `TASKS/PLAN.md`)

| Candidate | Where it lives | Job |
|---|---|---|
| `screen-agent` | Each station | `POST /relaunch` → kill Chromium, restart in kiosk pointed at the correct screen URL. Heals a stuck station without physical access. |
| `rgbdisplay-control` | studiopi | Admin endpoints to start/stop/swap LED matrix content (`led_clock.py`, `axolotl_anim.py`, …). |
| `news-fetcher` | studiopi | Scheduled RSS pulls (already partially built in `news/`). Will become its own systemd unit driven by APScheduler. |
| `deploy-agent` | studiopi | Wraps `pi-update.sh` behind `POST /admin/redeploy`. Opens the door to auto-deploy on `main` push if/when we want it (paused per §12.0). |

## Conventions

- **No secrets in git.** SSH keys live in `~/.ssh`, never in the repo. See `.gitignore` for the secret-shaped patterns.
- **Plain markdown specs**, ASCII mockups instead of screenshots. Lives in `docs/` once stable; `TASKS/` while drafting.
- **Cache-bust static assets via `{{ app_version }}`** — the short git SHA from `utils.APP_VERSION`. Don't hardcode versions.
- **Maintenance windows are visible.** `scripts/maintenance.py` bridges full-restart gaps; `GET /updating` overlays during normal reloads. We do not silently flash the displays.
- **Always one source of truth.** GitHub `main` is what's deployed; the Pi's screen-mgr is a tracking clone, never edited in place.

## Open architecture questions

- **How do stations get onboarded?** Today it's manual (kiosk Chromium pointed at `studiopi:8000/screen/<id>`). The screen-agent should ship a per-station systemd unit that brings up the kiosk on boot — same template as studiopi's services.
- **Where does configuration live for multi-Pi growth?** Today each station's identity is just a screen-id assigned by the admin. With the screen-agent, we might want a `stations.json` analogous to `screens.json`.
- **What's the failure model when studiopi is down?** Stations show a connection-lost indicator. We have not yet decided if stations should cache their last content or go blank.
