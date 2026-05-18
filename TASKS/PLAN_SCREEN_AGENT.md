# Cross-Platform Screen Agent

**Status:** Planning
**Branch:** TBD
**Created:** 2026-05-18

---

## Overview

A small **cross-platform Python service** running on every display station (whether it's a Raspberry Pi or a Windows mini PC) that exposes a few HTTP endpoints. The admin hub on `studiopi` can call those endpoints to:

- **Kill and re-launch** the station's browser in fullscreen kiosk mode, pointed at the correct `http://studiopi:8000/screen/<id>` URL.
- **Soft-reload** the current page without restarting the browser.
- **Report status** — current browser PID, URL, agent uptime, OS, screen-id assignment.

This is the operator's hand on every station: if a station hangs, goes blank, or drifts to the wrong URL, the admin clicks one button and the station heals itself.

---

## 1. Functional Requirements

### 1.1 What the agent does
- Run as a long-lived process on every station, started at boot.
- Listen on a station-local HTTP port (suggested `9091`).
- Manage the station's browser process (Chromium on Linux, Chrome or Edge on Windows).
- Tolerate restarts of itself, of the browser, of the network.

### 1.2 What the admin hub does
- Maintain a `stations.json` (or extend `Screen.client_host` already captured) mapping each connected screen to its station IP and agent port.
- Expose admin endpoints that fan out to the agents.
- Render a "Relaunch all content" button + per-station "Relaunch" buttons in the admin UI.

### 1.3 Non-goals (for now)
- No password/PIN screen unlock — agent doesn't try to defeat the screensaver. If the OS locks, an operator still walks to the station and types `0168`.
- No software update mechanism for the agent itself in v1 — push updates via SSH (same as `pi-update.sh` analog).

---

## 2. Architecture

```
┌────────────────────────────┐
│ studiopi  (admin hub)      │
│                            │
│  /api/screens/{id}/relaunch│
│  /api/screens/{id}/reload  │
│  /api/screens/relaunch-all │
│           │                │
│           │ HTTP POST      │
│           ▼                │
└───────────┼────────────────┘
            │
   ┌────────┼─────────┬─────────┐
   ▼        ▼         ▼         ▼
┌────────┐ ┌────────┐ ┌────────┐
│ Pi     │ │ Win PC │ │ Pi     │
│ :9091  │ │ :9091  │ │ :9091  │
│ agent  │ │ agent  │ │ agent  │
│  │     │ │  │     │ │  │     │
│  ▼     │ │  ▼     │ │  ▼     │
│Chromium│ │Chrome  │ │Chromium│
└────────┘ └────────┘ └────────┘
```

Same code, same endpoints, same port — heterogeneous OS underneath.

---

## 3. Agent endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/status` | — | `{hostname, os, agent_uptime_s, browser_pid, browser_url, screen_id}` |
| POST | `/relaunch` | — | `{ok: true, new_pid}` |
| POST | `/reload` | — | `{ok: true}` (soft refresh, no process restart) |
| POST | `/url` | `{url: "..."}` | `{ok: true}` (relaunch pointed at a different URL — used for ad-hoc steering) |

No auth in v1 — LAN-only, same posture as the rest of the system. Add a shared-secret header later if needed.

---

## 4. Admin-side endpoints (on studiopi)

| Method | Path | Action |
|---|---|---|
| POST | `/api/screens/{id}/relaunch` | Look up station IP for this screen, POST `http://<ip>:9091/relaunch`, return agent's response |
| POST | `/api/screens/relaunch-all` | Fan out to every connected station in parallel; return per-station success/error |
| POST | `/api/screens/{id}/reload` | Same as relaunch but `/reload` |

The admin UI gets two buttons per station (Relaunch / Reload) plus one global "Relaunch all" button.

---

## 5. File structure (new)

```
screen-mgr/
├── screen-agent/
│   ├── agent.py             # The cross-platform Python service
│   ├── config.example.json  # {screen_id, screen_mgr_url, browser_args}
│   ├── install_linux.sh     # one-shot installer for Pi stations
│   ├── install_windows.ps1  # one-shot installer for Windows stations
│   └── systemd/
│       └── screen-agent.service   # Linux user-service template
├── routes/
│   └── api_routes.py        # add /api/screens/{id}/relaunch etc.
└── templates/admin/
    └── screens.html         # add Relaunch + Reload buttons per station
```

`screen-agent/agent.py` uses **stdlib only** (`http.server`, `subprocess`, `platform`, `json`) — no pip deps required on stations. Same philosophy as `scripts/maintenance.py`.

---

## 6. OS-specific implementation notes

### 6.1 Linux Pi (e.g., `station2pi` at `.246`)
- Browser process: `chromium-browser`
- Start command (matching what's there today): `chromium-browser --force-renderer-accessibility --enable-remote-extensions --enable-pinch --start-fullscreen http://studiopi.local:8000/screen/<id>`
- Kill: `pkill -f chromium-browser` (the agent owns the new process)
- Env vars to preserve: `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`, `DISPLAY` (Wayfire on this station)
- Agent runs as `genai` (same user that owns the Chromium session). Installed as a **systemd user service** via `loginctl enable-linger genai`.

### 6.2 Windows mini PC (e.g., the one at `.211`)
- Browser process: `chrome.exe` or `msedge.exe` (need to discover)
- Start: `Start-Process` PowerShell or `subprocess.Popen` with `--start-fullscreen <url>`
- Kill: `taskkill /F /IM chrome.exe`
- Agent installation: **Windows Task Scheduler** at boot (`At system startup`, "Run whether user is logged on or not", with appropriate user). Alternatively as a Windows service via `nssm` if we want process supervision.
- Requires Python 3 installed (likely needs `winget install Python.Python.3.12` if absent).

### 6.3 Soft reload
- Linux X11: `xdotool key F5` on the right window
- Linux Wayland: harder — may have to send DevTools protocol over Chrome's debug port (`--remote-debugging-port=9222`)
- Windows: `SendKeys` or DevTools protocol
- Likely simplest universal: open browser with `--remote-debugging-port=9222`, use Chrome DevTools Protocol's `Page.reload` method. Same code on every OS.

---

## 7. Dependencies

- Python 3.10+ on each station (already on Pis; needs install on Windows mini PCs).
- No third-party libraries in v1 — stdlib `http.server` + `subprocess` are enough.
- Agent listens on `0.0.0.0:9091` — opens a firewall rule on Windows; Linux usually permissive on LAN.

---

## 8. Per-station audit (do tomorrow before coding)

For each station, document the canonical kiosk launch command, OS, browser binary, autostart mechanism:

- [ ] **Screen #2 "Station 2"** (`192.168.2.246`) — Pi 5 / Linux / Wayfire. Chromium command captured already. **Open: where is it launched from in `genai`'s autostart?** Need sudo or genai-SSH access to read `~/.config/lxsession/LXDE-pi/autostart` etc.
- [ ] **Screen #4 "Screen 2"** (`192.168.2.211`) — **Mini PC / Windows** (confirmed 2026-05-18 by sitting at it: HDMI 1 labeled "raspberry pi" but the box is actually a Windows mini PC). **Open: which browser? where's the kiosk shortcut?**
- [ ] **Screen #5 "Screen 3"** (`192.168.2.101`) — **Mini PC / Windows** (user confirmed). **Open: same as Screen #4 — Windows OpenSSH? agent install path?**
- [ ] **Other screens (1, 3, 6, 7, 8)** — never seen connected; do they exist or are they aspirational?

**Headcount of connected stations today: 2 × Windows mini PC + 1 × Linux Pi.** Cross-platform Python agent is the right architecture; Windows is actually the dominant station OS right now.

---

## 9. Implementation Phases

- [ ] **Phase 1: Per-station audit** — fill in §8. May involve walking to each station once.
- [ ] **Phase 2: agent.py prototype** — single Python file with the four endpoints. Test on dev machine first against a local Chrome.
- [ ] **Phase 3: Linux installer + systemd user-service** — `install_linux.sh` does: install Python deps (none), copy agent.py, register systemd user unit, `loginctl enable-linger`, start.
- [ ] **Phase 4: Deploy to Station 2 Pi (`.246`)** — first live install. Verify relaunch / reload work.
- [ ] **Phase 5: Windows installer + Task Scheduler** — `install_windows.ps1` for the mini PC. Likely needs to install Python first.
- [ ] **Phase 6: Deploy to Windows station (`.211`)** — second live install. Verify same endpoints, cross-OS UX matches.
- [ ] **Phase 7: Admin routes + UI** — `/api/screens/{id}/relaunch`, `/api/screens/relaunch-all`, buttons in `templates/admin/screens.html`.
- [ ] **Phase 8: Audit + roll out to remaining stations** — apply per OS.
- [ ] **Phase 9: Docs** — `docs/SCREEN_AGENT.md` operator guide + plug-in template for future stations.

---

## 10. Tomorrow's first move

The user is physically at the Windows station (`192.168.2.211`) often enough to do install work in-person. Concrete first steps when picking this up:

1. **At the Windows station:** `ipconfig`, `python --version` (install Python 3.12 if absent: `winget install Python.Python.3.12`). Confirm Chrome/Edge path. Note which user is logged in (`whoami`).
2. **From the dev machine:** decide whether to enable Windows OpenSSH server now (lets us SSH from WSL without walking to the station every time). 5-min setup.
3. **Sketch agent.py** with just `GET /status` working. Run it manually on the Windows station, hit it from dev with curl, verify reachability.
4. **Iterate** from there — `POST /relaunch` next, since that's the killer feature.

---

## 11. Open architecture questions

- **How does the agent know its own screen-id?** Options: (a) hardcoded in `config.json` per station; (b) agent reaches out to studiopi at startup and gets assigned; (c) studiopi pushes config via WS during deploy. (a) is simplest for v1.
- **Should the agent ALSO be the thing that connects WebSocket to studiopi**, replacing the in-browser screen.js WS? Big architectural decision — would unify the "is this station alive?" check on studiopi side. Probably not in v1; keep agent and browser-WS separate.
- **What if a station is on a corporate network behind a firewall?** Outbound HTTPS may be allowed but inbound to `:9091` may not. Plan B: agent polls studiopi for instructions (long-poll or WS). Defer.
- **Authentication.** Shared-secret header? mTLS? Per-station agent token issued by studiopi? Pick when we make it not-just-LAN.

---

## 12. Why this is worth doing

Today, fixing a broken station means **walking to it physically and rebooting the browser**. With the agent:

- "Updating" page renders correctly on every station (the agent can switch Chrome launch flags station-by-station from a central registry).
- "Relaunch all" is one button — useful after every deploy that touches templates/static.
- Operators can be remote.
- Stations become genuinely interchangeable: kill a mini PC, swap in a Pi, agent does the same job.
