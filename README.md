# screen-mgr — Studio control hub

FastAPI app that runs the GenAI Studio: drives the TV/projector screens
in the room, controls the Philips Hue lights, manages the LED matrix,
and exposes everything as **MCP servers** so any MCP client (Claude
Code, our own agents, future webhooks) can drive it.

Lives on `studiopi` (Raspberry Pi 4, Debian 12) at `http://studiopi:8000`.

## Quick start

```bash
python -m venv venv
source venv/bin/activate          # Linux/macOS  |  venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload
```

- Admin panel: `http://localhost:8000/admin`
- Per-screen view: `http://localhost:8000/screen/{id}` (1..8)
- MCP servers: `http://localhost:8000/mcp/<domain>/sse`

Deploy to the Pi: see [`docs/DEPLOY.md`](docs/DEPLOY.md).

## What it does

- **Screens** — 8 configured display stations (mix of mini-PCs and Pis
  running Chromium in kiosk mode). Each station can show a URL, video,
  picture, PDF, slideshow, text, the AI News feed, a screen-share room,
  or the studio logo. WebSocket-driven live reload.
- **Lights** — Philips Hue bridge integration with per-light, per-group,
  and per-scene control. The Studio room (group 81) and the Maker room
  (group 2) are the primary zones.
- **LED matrix** — the small information LED display next to the screens
  (`modules/rgbdisplay` — managed as a separate systemd unit).
- **Scenes** — saved "looks" that bundle a Hue scene + per-zone screen
  content overrides into a single apply action.
- **Modules registry** — every content type and backend service plugs
  in through a uniform contract. See [`docs/MODULES.md`](docs/MODULES.md).

## Admin panel (`/admin`)

Single-page app with four views in the left sidebar:

| View | What you do here |
|---|---|
| **Screens** | Pick what each station shows. Scenes dropdown applies a saved bundle. Reload-all button bounces every connected station. |
| **Lighting** | Per-light and per-group Hue controls; recall a bridge scene. |
| **LED screens** | Start/stop the LED matrix service. |
| **Modules** | Module registry — enable / disable / inspect each module. |

The right column hosts the **agent chat panel** — text input + push-to-talk
voice (hold the 🎤 button or hold `Space` when the textarea isn't focused).
The frontend is real and SSE-driven; the backend (`POST /api/chat`) is
currently a stub that replies with a clear "not implemented" error
until the `.env` API key on the Pi is set. See
[`TASKS/PLAN_AGENTIC.md`](TASKS/PLAN_AGENTIC.md) Phases 2-4.

The original Tailwind-based admin still lives at `/admin/legacy` as a
fallback for one release cycle (cutover was 2026-05-21).

## MCP servers

Every domain that the admin can drive is also exposed as an MCP server,
mounted in-process under `/mcp/<domain>/sse` (SSE transport). The
servers wrap the same Python managers the HTTP routes call — no extra
hop, no duplicated logic. LAN-only deployment (DNS-rebinding protection
disabled; see `mcps/lighting/server.py` for the rationale and the
re-enable path if this ever goes public).

### Lighting MCP — `/mcp/lighting/sse`

Wraps the Hue Bridge via `modules.hue.client.HueClient`.

| Tool | Purpose |
|---|---|
| `list_lights` | Every light with current on/off/brightness/color state. |
| `list_groups` | Hue rooms / zones with members. Studio = group `81`, Maker = group `2`. |
| `list_scenes` | Bridge-defined Hue scenes. |
| `get_bridge_status` | Bridge config + reachability for diagnostics. |
| `set_light` | Update one light by id (on/brightness_pct/color_hex/kelvin). |
| `set_group` | Update every light in a group in one call. |
| `recall_scene` | Activate a bridge scene by id. |
| `all_on` / `all_off` | Whole-house master switch (group 0). |
| `run_startup_test` | Self-test: rainbow walk across all Studio lights + 10/80/40/80% intensity sweep + settle to 60% / 3000K. ~12s total. |

CLI: `python scripts/lights_startup_test.py`

### Screens MCP — `/mcp/screens/sse`

Wraps `screen_manager`, `scene_manager`, and the module registry.

| Tool | Purpose |
|---|---|
| `list_screens` | Every station with id, name, type, current content, connected, client_host. |
| `list_scenes` | Saved Studio scenes (different from Hue scenes — these bundle Hue + screens). |
| `list_content_types` | Display-module ids currently enabled (valid for `set_screen_content`). |
| `list_media` | Files in `static/{pictures,videos,pdfs}` + slideshow subfolders. |
| `set_screen_content` | Set type + value on a screen; persists and notifies over WS. |
| `reload_screen` | Force-reload a single screen via WebSocket. |
| `reload_all_screens` | Broadcast reload to every connected screen. |
| `apply_scene` | Apply a saved scene (Hue recall + per-zone content + reload). |
| `run_content_walkthrough` | Self-test: cycle one target screen through picture → url → YouTube → pdf → news → default. ~24s. |
| `run_fleet_demo` | Self-test: drive every connected screen through url web → url YouTube → default → settle on the AI News scene. ~17s + settle. |

CLIs:
- `python scripts/screens_walkthrough_test.py [screen_id]`
- `python scripts/screens_fleet_demo.py [screen_id ...]`

### Displays MCP — `/mcp/displays/sse`

Wraps every registered LED panel ServiceModule. Today there's one
(`rgbdisplay`); future panels join automatically once their id is in
`mcps/displays/server.py::LED_MODULE_IDS` and a module is registered.

| Tool | Purpose |
|---|---|
| `list_displays` | Every registered LED display + status (systemd active/enabled, registry enabled). |
| `get_display_status` | Focused status for one display by id. |
| `start_display` | Start the backing systemd unit. |
| `stop_display` | Stop the backing systemd unit. |
| `set_display_enabled` | Flip the registry enabled flag (doesn't touch systemd). |
| `run_display_test` | Lifecycle sanity test: stop → 3s pause → start, with before/mid/after status snapshots. |

### Audio MCP — `/mcp/audio/sse` _(stub)_

API surface for system audio (sinks, sources, volume, mute, sound
playback). Tools currently return `{"stub": true, ...}` — wire to
PulseAudio (`pactl`) when implementing for real. The tool *signatures*
are the API contract; keep them stable.

| Tool | Purpose |
|---|---|
| `list_audio_sinks` / `list_audio_sources` | Output devices / input mics. |
| `get_volume` / `set_volume` | Sink volume 0–100. |
| `is_muted` / `mute` / `unmute` | Mute state for a sink. |
| `play_sound` | Play a local sound file on a sink. |

### Music MCP — `/mcp/music/sse`

Real Spotify Web API integration via `spotipy`. Tools return a friendly
`{"error": "spotify not configured", ...}` until you complete the
one-time OAuth setup (see [`docs/DEPLOY.md`](docs/DEPLOY.md) → Spotify).

| Tool | Purpose |
|---|---|
| `get_now_playing` | Track + device + progress + paused/playing. |
| `list_devices` | Spotify Connect devices on the account. |
| `search` | Search tracks / albums / artists / playlists. |
| `play` | Start / resume on a device, optionally with a URI. |
| `pause` / `next_track` / `previous_track` | Standard transport. |
| `set_volume` | Device volume 0–100. |

Scopes the MCP requests during auth: `user-read-playback-state
user-modify-playback-state user-read-currently-playing`.

## Agent layer

The MCP servers are the data plane; on top of them sits a small Claude
agent layer (`agents/`):

- **Specialists** — one per domain. Each one wraps a single MCP server
  plus a markdown-frontmatter **skills** library. `LightingSpecialist`
  is implemented.
- **Studio orchestrator** — receives operator messages, routes them to
  specialists via `delegate_to_*` tools, or asks the operator a
  clarifying question. Implemented for Lighting only so far.

Both are **code-complete but blocked** on the `.env` API key on the Pi
(see [`TASKS/PLAN_AGENTIC.md`](TASKS/PLAN_AGENTIC.md) §10). Drop a
real `ANTHROPIC_API_KEY` into `/home/admin/screen-mgr/.env` to unblock.

The chat panel (Phase 4) and browser-voice (Phase 5) wire the agents
into the admin UI; not started yet.

## Project layout

```
main.py                 FastAPI entry — mounts routes + MCP servers
routes/                 HTTP / WebSocket endpoints
  admin_v2_routes.py    /admin (the redesigned panel)
  api_routes.py         /api/screens, /api/pictures, ...
  scenes_routes.py      /api/scenes, /api/scenes/{id}/apply
  ...
models/
  scenes.py             Scene model + SceneManager (.apply lives here)
  zones.py              Zone model (floor-plan polygon + screen + lights)
screens.py              Screen model + ScreenManager
connections.py          WebSocket ConnectionManager
modules/                Plug-in registry — content types + services
  hue/                  Philips Hue integration
  news/                 AI news fetcher
  rgbdisplay/           LED matrix
  ... (one per content type)
mcps/                   MCP servers (in-process FastMCP)
  lighting/             Hue Bridge MCP
  screens/              Stations + scenes + media MCP
agents/                 Claude-driven specialists + orchestrator
  base.py               Specialist + MCP loop
  lighting_specialist.py
  studio_orchestrator.py
  skills.py             Markdown-frontmatter skill loader
scripts/                Operational + self-test scripts
  hue_pair.py           One-time Hue Bridge pairing
  lights_startup_test.py
  screens_walkthrough_test.py
  screens_fleet_demo.py
data/                   Persisted state (scenes.json, zones.json, hue.json)
static/                 JS / CSS / media (pictures, videos, pdfs)
templates/              Jinja2 templates (admin/v2/, content/, screen.html, ...)
docs/                   Deeper documentation (see below)
TASKS/                  Active planning docs
```

## Deeper docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the pieces fit on the Pi, and the contract a new service follows.
- [`docs/MODULES.md`](docs/MODULES.md) — module registry contract, how to write a module.
- [`docs/DEPLOY.md`](docs/DEPLOY.md) — manual deploy from a developer machine to studiopi.
- [`docs/TESTING_WORKFLOW.md`](docs/TESTING_WORKFLOW.md) — local + on-Pi testing recipes.
- [`docs/NEWS_FLOW_SPEC.md`](docs/NEWS_FLOW_SPEC.md) — the AI News pipeline.
- [`TASKS/PLAN_AGENTIC.md`](TASKS/PLAN_AGENTIC.md) — the MCP + agent build plan and phase tracker.

## Stations on the LAN

The display stations are a mix of Raspberry Pis and Windows mini-PCs,
all on the same LAN as `studiopi`. Each runs Chromium in kiosk mode
pointed at `http://studiopi:8000/screen/{id}`. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the topology diagram.

## Notes

- The repo only commits source / config — `data/` state, uploaded
  media, and `.env` files are gitignored.
- Never commit secrets. SSH keys live on the developer's WSL, not in
  the repo; API keys live in `.env` on the Pi only.
- `uvicorn --reload` is fine for dev and is what the systemd unit uses.
  Do not run a separate build step — there's nothing to build.
