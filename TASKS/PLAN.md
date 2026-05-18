# Dev → Pi Deployment Feature

**Status:** Planning
**Branch:** TBD
**Created:** 2026-05-18

---

## Overview

Provide a one-command path for shipping a completed feature from the developer machine (`C:\Projects\Studio\screen-mgr`) to the production Raspberry Pi on the local network, so live testing happens on the real hardware instead of localhost. The Pi already runs screen-mgr; the deploy must update the code, restart the service, and tell every connected screen to reload itself.

---

## 1. Functional Requirements

### 1.1 Trigger
- Deploy is **deliberate, not automatic** — invoked when a feature is complete and committed.
- Single command from the dev machine (e.g. `./deploy.ps1` or `make deploy`).
- No deployment on every save; no CI/CD pipeline yet.

### 1.2 Pre-flight checks (deploy script should refuse if any fail)
- Working tree is clean (no uncommitted changes).
- Current branch is pushed to `origin` and up to date.
- Pi is reachable over SSH.

### 1.3 Sync mechanism
- Pi has its own clone of the repo → use `git pull` rather than `rsync` (single source of truth = GitHub).
- Only changes that exist on `origin` end up on the Pi → discourages "works on my Pi but not in main" drift.

### 1.4 Service restart
- After pull, restart the FastAPI/uvicorn service on the Pi so Python code changes take effect.
- Mechanism depends on how uvicorn currently runs on the Pi — see Discovery (§6).

### 1.5 Screen reload broadcast
- After the service is back up, every WebSocket-connected screen must receive a `reload` message so it picks up new templates/static assets without manual intervention.
- This already exists in `connections.py` (`notify_screen`) but is currently triggered by admin updates. Need a way to invoke it for all screens after deploy — either:
  - An admin API endpoint that broadcasts reload to all screens, called by the deploy script after restart, OR
  - The service emits a reload-all on startup (simpler but reloads even on accidental restarts).

### 1.6 Feedback / safety
- Deploy script prints what it's doing at each step.
- Non-zero exit code on any failure; halts on first error.
- Logs the deployed commit hash on the Pi (so we can confirm what's running).

---

## 2. Workflow

```
┌─────────────────────────┐
│  Dev machine (Windows)  │
│                         │
│  1. git commit          │
│  2. git push origin     │
│  3. ./deploy.ps1        │
└──────────┬──────────────┘
           │ SSH
           ▼
┌─────────────────────────────────────┐
│  Raspberry Pi (prod)                │
│                                     │
│  4. git pull origin <branch>        │
│  5. (optional) pip install -r ...   │
│  6. systemctl restart screen-mgr    │
│  7. curl /api/admin/reload-all      │
└──────────┬──────────────────────────┘
           │ WebSocket broadcast
           ▼
┌─────────────────────────┐
│  Connected screens      │
│  → page.reload()        │
└─────────────────────────┘
```

---

## 3. Approach Options

| Option | Mechanism | Pros | Cons |
|--------|-----------|------|------|
| **A. Git pull (recommended)** | Dev pushes to GitHub; deploy script SSHes in and runs `git pull` + restart | Single source of truth; commit hash = deployed version; rollback is `git checkout <sha>` | Requires every deploy to be committed first |
| B. rsync over SSH | Sync working tree directly | Can ship uncommitted work-in-progress | Drift risk; no version record on Pi; needs careful exclude list |
| C. Bare git repo on Pi w/ post-receive hook | `git push pi main` triggers checkout + restart | Very tidy; one push does everything | More moving parts; another remote to manage; less common pattern |

**Recommendation:** Option A. Pairs naturally with the "feature complete = committed" trigger and uses infrastructure we already have (GitHub). Add it as a script in `scripts/` so it can evolve.

---

## 4. Data Model

No new data model needed. This feature is infra/scripts only.

---

## 5. New Routes & Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/admin/reload-all` | Broadcast WebSocket `reload` to every connected screen (called by deploy script after restart) |

Auth: needs at minimum a shared secret header — the admin panel is currently unauthenticated but invoking this from outside the network is a non-issue if it lives behind LAN-only SSH. Still, the endpoint itself is over HTTP so a token check is worth the 3 lines.

---

## 6. Pi State (Discovered 2026-05-18)

- [x] **SSH access**: `ssh admin@192.168.2.65` (mDNS `studiopi.local` works from Windows but not WSL — using IPv4). Key-based auth set up from WSL: `~/.ssh/id_ed25519`.
- [x] **Pi repo path**: `/home/admin/screen-mgr`
- [x] **Pi git remote**: **Not currently a git repo** — same situation we had on dev. Needs `git init` + remote + reset --mixed against `origin/main` (one-time setup, see Phase 1.5 below).
- [x] **How uvicorn runs**: Inside a detached GNU `screen` session named `screen-mgr`, started by:
  ```
  screen -dmS screen-mgr bash -c 'cd /home/admin/screen-mgr && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0'
  ```
  **Crucially: `--reload` flag means uvicorn auto-restarts on file changes** — no manual restart needed for most deploys. We only need a manual restart if `requirements.txt` or the venv itself changes.
- [x] **Python env**: venv at `/home/admin/screen-mgr/venv/` with Python 3.11.2. `pip` ops should run as `venv/bin/pip` (or with venv activated).
- [x] **Permissions**: `admin` owns the repo files. `sudo` is NOPASSWD for everything → no password friction.
- [x] **Port + URL**: `http://192.168.2.65:8000` (uvicorn bound to `0.0.0.0`). `studiopi.local:8000` also works from machines with mDNS.
- [ ] **Static DHCP reservation**: not yet — should reserve `192.168.2.65` on the router so the IP doesn't drift.

### Implications for the deploy script

Because uvicorn already runs with `--reload`, the deploy flow is **much simpler than originally planned**:

1. `git pull` on the Pi
2. If `requirements.txt` changed: `venv/bin/pip install -r requirements.txt` + restart `screen-mgr` screen session (`--reload` doesn't reinstall deps)
3. POST to `/api/admin/reload-all` to refresh connected screens

Step 2 is rare; most deploys will be step 1 + step 3.

### Screen-session conventions (validated 2026-05-18)

Each long-running service on the Pi is wrapped in a named GNU `screen` session:

| Session | User | Wrapper script | Start command |
|---|---|---|---|
| `screen-mgr` | `admin` | (none yet — TODO: create `start_screen_mgr.sh`) | `screen -dmS screen-mgr bash -c 'cd /home/admin/screen-mgr && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0'` |
| `rgbdisplay` | `root` (GPIO needs sudo) | `/home/admin/rpi-rgb-led-matrix/start_display.sh` | `screen -dmS rgbdisplay python3 /home/admin/rpi-rgb-led-matrix/led_clock.py --rows 64 --pwm-bits 8 --pwm-lsb-nanoseconds 50 --led-rgb-sequence RBG` |

**Stop pattern (universal):** `screen -S <name> -X quit` (prepend `sudo` if started as root).

**List pattern:** `screen -ls` lists the invoking user's sessions only. `sudo screen -ls` shows root's. The deploy/admin code must know which user owns each session.

**Tested end-to-end on 2026-05-18**: brought `rgbdisplay` up via `sudo bash start_display.sh`, confirmed in `sudo screen -ls`, brought down via `sudo screen -S rgbdisplay -X quit`. Visible from physical LED matrix.

### Auto-start gap (separate concern)

Nothing currently auto-starts on boot — neither `screen-mgr` nor `rgbdisplay`. Both rely on someone SSH'ing in and running the commands. After a reboot, the Pi is silent until someone notices. Fixing this is **out of scope for deploy** but should be a follow-up (likely systemd units or `@reboot` cron entries).

---

## 7. File Structure (new files)

```
screen-mgr/
├── scripts/
│   ├── deploy.ps1          # Main deploy entry (Windows PowerShell)
│   └── pi-update.sh        # Runs on the Pi: pulls, installs, restarts (invoked over SSH)
├── routes/
│   └── api_routes.py       # (existing) — add POST /api/admin/reload-all
└── docs/
    └── DEPLOY.md           # Operator-facing doc: prerequisites, how to run, troubleshooting
```

Optional: a `systemd/screen-mgr.service` file checked in, so the Pi's service definition is version-controlled too.

---

## 8. Dependencies

No new Python deps required.

Possible new tooling:
- OpenSSH client on dev machine (already present on Windows 11)
- `sshpass` not needed if we use key-based auth (we should)

---

## 9. Security Notes

- SSH key-based auth only, no password auth in scripts.
- `/api/admin/reload-all` should require a token (shared secret in env var on dev + Pi).
- Don't commit secrets — use `.env` (already in `.gitignore` presumably; verify).
- Pi service should run as a non-root user.

---

## 10. Implementation Phases

- [x] **Phase 1: Discovery** — Pi state documented in §6.
- [ ] **Phase 1.5: Make Pi's screen-mgr a git repo** — `git init` + remote + `reset --mixed origin/main`; review and stage any Pi-local files we want to keep (e.g. its `screens.json`); discard or commit the rest.
- [ ] **Phase 2: Reload-all endpoint** — Add `POST /api/admin/reload-all` (token-auth) that calls `connection_manager.notify_screen` for every connected screen. Test against local uvicorn first.
- [ ] **Phase 3: Pi-side script** — `scripts/pi-update.sh` (idempotent: `git pull`, diff `requirements.txt`, conditionally `pip install`, conditionally restart screen session, log deployed commit hash to `last_deploy.log`).
- [ ] **Phase 4: Dev-side script** — `scripts/deploy.sh` (run from WSL): pre-flight checks (clean tree, pushed to origin), SSH to Pi, run `pi-update.sh`, call reload-all, print result.
- [ ] **Phase 5: First end-to-end deploy** — Run the script for real with a trivial change; observe; fix anything.
- [ ] **Phase 6: Boot-time auto-start** — systemd units (or `@reboot` cron, TBD) for `screen-mgr` (admin) and `rgbdisplay` (root). Wrap the existing `screen -dmS …` invocations so the attach-to-debug workflow still works. Reboot the Pi to validate.
- [ ] **Phase 7: Documentation + onboarding** — `docs/DEPLOY.md` with prerequisites, "how a colleague gets set up to deploy" (their own SSH key), troubleshooting, reboot recovery.

---

## 11. Out of Scope (for now)

- Multi-Pi fleet deploys (we have one Pi).
- Rollback automation (manual `git checkout <sha> && restart` is acceptable for now).
- CI/CD from GitHub Actions.
- Blue-green / zero-downtime deploys (a 2–3 second restart is fine).
- Deploying uncommitted work — by design, you commit first.

---

## 12. Related Features Discovered (defer to separate plans)

### 12.0 Auto-deploy on push to main (paused 2026-05-18)

User explored "GitHub webhook / Pi polls / GitHub Actions runner" approaches and chose to **pause** them. For now, deploys stay manual through this Claude Code session. Three options for if/when this comes back:

- **A. Pi polls GitHub** — systemd timer + `git fetch && deploy-if-behind`; no inbound exposure; ~30–60s lag.
- **B. Self-hosted GitHub Actions runner on Pi** — per-deploy UI in GH; close to instant; extra process to manage.
- **C. GitHub webhook via tunnel (cloudflared / ngrok)** — instant; one more service to keep healthy; HMAC validation needed.

### 12.4 SSH-into-station button in admin (new, 2026-05-18)

User idea after seeing `ssh screen@<ip>` next to each connected station: a **button** that opens an SSH session straight from admin. Three implementation tiers, increasing in scope:

| Tier | UX | Effort |
|---|---|---|
| **A. Copy-to-clipboard** | Click → `ssh screen@<ip>` lands on clipboard, paste into terminal | ~10 min |
| **B. `ssh://` URL scheme** | Click → browser launches OS default SSH client. Works on Linux/macOS; Windows depends on putty/handler config. | ~15 min |
| **C. Web SSH terminal** | Click → modal opens xterm.js, prompts for password, backend bridges over WebSocket via paramiko. Real terminal in the browser. | Real feature — own plan |

User said "if you have the psw" — implies the operator enters the password themselves, so tier A or B is the natural starting point. Tier C is a bigger ambition worth its own plan if/when the team wants it.

### 12.1 Service control from admin UI ("Launch content on all screens")

**Idea:** Admin panel gains controls to start/stop named services running in `screen` sessions on the Pi (`screen-mgr` excluded for safety; `rgbdisplay` and any future services like `axolotl_anim` are good candidates). Because the admin panel runs **on the same Pi** as the services, it can `subprocess` directly — no SSH needed.

**Rough shape:**
- Registry of controllable services (name, wrapper script path, requires-sudo flag, display-friendly label)
- `POST /api/admin/services/{name}/start` → runs wrapper via `subprocess`
- `POST /api/admin/services/{name}/stop` → runs `screen -S <name> -X quit`
- `GET /api/admin/services` → status of each (parsing `screen -ls`)

**Promote to its own plan** (e.g. `TASKS/PLAN_SERVICE_CONTROL.md`) once the deploy feature is wrapped up.

### 12.3 Re-launch content on every display device → **PROMOTED to `TASKS/PLAN_SCREEN_AGENT.md` (2026-05-18)**

See dedicated plan: cross-platform Python agent (one codebase, runs on both Pi/Linux and Windows mini PC stations). Notes below kept for context.



**User goal:** A "Re-launch all content" button in the admin UI that, on every connected display device, **closes the existing browser and reopens it in fullscreen** on that device's assigned screen content URL. The maintenance page (§6, `scripts/maintenance.py`) is the boilerplate — same pattern of "small Python service that does one thing well per device" should be reused.

**Confirmed (2026-05-18):**
- Display devices = **other Raspberry Pis with Chromium** (kiosk mode). Confirmed Station 2 and Station 3 exist and are reachable on the LAN.
- Their addresses are **discoverable from the admin panel**: each station's screen view connects back over WebSocket at `/ws/{screen_id}`, and the `WebSocket.client.host` property on the server side exposes the client IP. The admin panel already tracks connection status; surfacing the IP just means storing `websocket.client.host` alongside `screen.connected` when the connection is established. No manual IP config needed.
- This means the screen-agent feature can auto-discover its targets from runtime state — admin clicks "Relaunch all", server fans out to whichever IPs are currently connected.

**Open questions:**
- **Auth model** between admin and display agents? (Probably token-on-LAN; same posture as the rest of the system today.)
- **What does the existing screen-view setup on a station look like?** Is Chromium launched by autostart? rc.local? Manual? Whatever they currently do is what the new agent needs to be able to kill and re-spawn.

**Likely shape:**
- **`screen-agent.py`** — tiny Python service running on each display device. Exposes endpoints like:
  - `POST /relaunch` → kills running Chromium, relaunches in kiosk mode pointed at the assigned screen URL
  - `POST /reload` → soft refresh of the current page (Ctrl-R equivalent, possibly via WebSocket from screen-mgr already)
  - `GET /status` → uptime, current URL, browser PID
- Modeled after `scripts/maintenance.py`: single-file, stdlib HTTP server, designed to be run by a small systemd unit on each display device.
- Admin server iterates configured displays and POSTs `/relaunch` to each in parallel; renders per-device status (success / unreachable / error).
- Admin UI: section listing each display with a per-device "Relaunch" button, plus a global "Relaunch all" button.

**Pre-work needed:**
- Inventory display devices (IPs/hostnames/auth).
- Decide kiosk launch command per device platform (Chromium: `chromium-browser --kiosk --noerrdialogs --disable-infobars <URL>`).
- One-time deployment of `screen-agent.py` + systemd unit to each device (same flow we just did for studiopi).

**Promote to its own plan** — `TASKS/PLAN_DISPLAY_AGENT.md` — once the deploy feature wraps.

### 12.2 ~~Boot-time auto-start~~ — Promoted to Phase 6 (2026-05-18)
