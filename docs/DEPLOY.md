# Deploying screen-mgr to the Pi

Manual, one-command deploys from a developer machine (WSL on Windows) to the production Raspberry Pi (`studiopi`).

## At a glance

```
┌──────────────────────────┐
│ Dev machine (Windows)    │
│                          │
│  git commit              │
│  git push origin main    │
│  scripts/deploy.sh       │←── one command
└──────────┬───────────────┘
           │ ssh + curl
           ▼
┌──────────────────────────────────────────┐
│ studiopi  (admin hub, FastAPI/uvicorn)   │
│                                          │
│  scripts/pi-update.sh                    │
│   ├── git pull                           │
│   ├── if requirements.txt changed:       │
│   │     pip install + systemctl restart  │
│   │     (maintenance.py bridges :8000)   │
│   └── uvicorn --reload picks up the rest │
│                                          │
│  POST /api/screens/reload-all            │
│   └── WS → every connected station       │
└──────────┬───────────────────────────────┘
           │ WebSocket
           ▼
┌──────────────────────────┐
│ Stations 2/3 (Chromium)  │
│                          │
│  popup navigates to      │
│  /updating?return_to=…   │
│  → 10s countdown         │
│  → back to news/logo/…   │
└──────────────────────────┘
```

## One-time prerequisites (per developer)

The deploy runs from WSL because that's where SSH keys live and where `ssh` / `git` behave predictably.

```bash
# In WSL:
ssh-keygen -t ed25519 -C "studiopi-deploy" -f ~/.ssh/id_ed25519 -N ""
ssh-copy-id admin@<studiopi-ip>    # password: admin, one time only
ssh admin@<studiopi-ip> "echo connected"   # confirm passwordless
```

After that, `scripts/deploy.sh` works without prompting.

**Note on hostnames:** `studiopi.local` resolves from Windows (mDNS) but not from WSL, so the script defaults to the LAN IP. Override with env vars if it changes:

```bash
PI_HOST=admin@<new-ip> ADMIN_URL=http://<new-ip>:8000 wsl bash scripts/deploy.sh
```

## Daily flow

```bash
# Make changes, commit, push:
git add -A && git commit -m "..."
git push origin main

# Deploy (run from WSL):
wsl bash scripts/deploy.sh
```

That's it. The script:

1. **Preflight** — refuses to deploy if the working tree is dirty or there are unpushed commits.
2. **SSH to Pi**, runs `scripts/pi-update.sh`:
   - `git fetch`; exits early if already up-to-date.
   - `git pull --ff-only`.
   - Compares `sha256sum requirements.txt` before vs after.
     - **If unchanged:** does nothing — uvicorn `--reload` picks up Python / template / static changes by itself.
     - **If changed:** `venv/bin/pip install -r requirements.txt`, `systemctl stop screen-mgr`, runs `scripts/maintenance.py --duration 5` (serves the styled "be right back" page on `:8000`), then `systemctl start screen-mgr`. Polls `/admin` until it responds.
   - Appends `<timestamp> <commit-sha>` to `last_deploy.log`.
3. **Reload all connected screens** — `POST /api/screens/reload-all` broadcasts a WebSocket reload to every connected station.
4. Stations receive the WS message and their `screen.js` navigates the visible content popup to `/updating?return_to=<original-url>`. Page shows for 10 seconds, then auto-returns.

## What if I changed only Python or templates?

That's the common case. uvicorn runs with `--reload`, watching the project tree. As soon as `git pull` writes new files, uvicorn re-imports them within a second. No restart, no maintenance bridge — just `deploy.sh` → quick pull → instant `reload-all`.

## What if I changed `requirements.txt`?

The pi-update.sh detects this by hashing requirements.txt before and after, and only then does it stop the service, install deps, run the maintenance bridge, and start the service. Adds ~10-15s of downtime, bridged by a styled "screen-mgr is restarting" page on `:8000`.

## MCP servers (Phase 1+ of `TASKS/PLAN_AGENTIC.md`)

In-process FastMCP servers are mounted under `/mcp/<domain>` alongside `/api/*`. They're started by the same uvicorn instance — no extra processes, no extra systemd units. As of today:

| Domain | Mount point | Wraps |
|---|---|---|
| Lighting | `/mcp/lighting/sse` | `modules/hue/client.py` (Hue Bridge v1 CLIP API) |

Adds one dependency: `mcp>=1.2.0` (the official Anthropic MCP Python SDK). `pi-update.sh` installs it automatically the first time it ships.

**Smoke test from any LAN machine:**
```bash
curl -N http://studiopi:8000/mcp/lighting/sse
# Expect an SSE stream with an initial `event: endpoint` message and
# a session URL — proves the server is reachable. Ctrl-C to disconnect.
```

To call a tool you need an MCP client (the agents in Phases 2+ do this from Python). Any external Claude Code session can also be pointed at the SSE URL.

## What does the deploy script NOT do?

- It does not push for you. You commit + push, then deploy. By design — deploys mirror what's on `origin/main`.
- It does not auto-deploy on push. We considered "Pi polls origin every minute" and "GitHub Actions runner on Pi" but kept deploys explicit for now. See `TASKS/PLAN.md` §12.0.
- It does not run tests. Pre-deploy testing is on you.

## Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `ERROR: working tree has uncommitted changes` | Genuine local changes, or a stale git index (Windows/WSL cross-mount artifact) | Commit/stash; if it's the stale-index case the script's `git update-index --refresh` should have cleared it — re-run. |
| `ERROR: local has N unpushed commit(s)` | You forgot `git push` | Push, retry. |
| `bash: /home/admin/screen-mgr/scripts/pi-update.sh: No such file or directory` | First-ever deploy and the Pi hasn't pulled the deploy scripts yet | One-time bootstrap: `ssh admin@<pi> 'cd /home/admin/screen-mgr && git pull'`, then retry. |
| `notified: []` after deploy | Stations dropped during uvicorn `--reload` and reconnect happens after `reload-all` fired | Wait ~6s and call `curl -X POST .../api/screens/reload-all` again. Or trigger via admin "Update" buttons. |
| Stations stuck on cached old `screen.js` | Browser caching `screen.js` from before the dynamic-cache-bust landed | One hard refresh on the station fixes it permanently; future deploys auto-bust via `?v={{ app_version }}`. |

## Onboarding a new operator

A teammate that wants to deploy from their machine:

1. Generate their own SSH key in WSL (`ssh-keygen` snippet above).
2. `ssh-copy-id admin@<studiopi-ip>` (one-time, needs admin password).
3. Clone the repo, `chmod +x scripts/deploy.sh` (already executable in git but Windows can mangle this).
4. Run `wsl bash scripts/deploy.sh` to deploy.

The `screen` user on each display station has a shared password (`screen`) — that's for SSH into a station with the "ssh screen@<ip>" link in admin, not for deploys.
