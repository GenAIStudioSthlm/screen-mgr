# Modules / Plugin Architecture

**Status:** Planning
**Branch:** TBD
**Created:** 2026-05-19

---

## Overview

A **module registry** layered on top of screen-mgr that turns every controllable thing — content sources, background services, future per-screen apps, external dashboards — into a uniform first-class object the admin panel can list, enable, monitor, and assign to screens.

Today's content types (`news`, `picture`, `pdf`, `slideshow`, ...) and the LED matrix service (`rgbdisplay`) are one-off implementations scattered across the codebase. Tomorrow we want to add things like a robot control panel, sensor readouts, or whatever colleagues build, without each addition being a unique surgery on `screen-mgr`. A module is the contract that lets that happen.

This is the foundation of the "extensible IoT-for-displays platform" direction we sketched in `TASKS/PLAN.md` and this session's chat.

---

## 1. Functional Requirements

### 1.1 What a module declares

Every module ships a manifest (Python class or JSON) declaring:

| Field | Purpose |
|---|---|
| `id` | Stable slug, e.g. `rgbdisplay`, `robot-panel`, `news` |
| `name` | Human-friendly title for the admin UI |
| `description` | Optional one-liner |
| `type` | `"display"` and/or `"service"` |
| `version` | Semver-ish, surfaced in admin |

### 1.2 What a module implements

- `is_available()` → `bool` (yes/no check, fast)
- `status()` → optional richer dict (pid, uptime, last error, etc.) for admin display
- **Display modules** additionally:
  - `get_screen_url(screen_id) -> str` — URL a screen should load to show this module's content
  - Optional: extra config fields surfaced as inputs in admin (e.g. news mode, slideshow folder)
- **Service modules** additionally:
  - `start()`, `stop()` — control the underlying process
  - Optional: per-action API endpoints (e.g. rgbdisplay: switch between clock and animation)

### 1.3 What the registry does

- Discovers modules at server startup by walking `modules/` (in-code) and reading `modules/external.json` (out-of-process modules).
- Exposes `/api/modules` (list + status) and `/api/modules/{id}/...` (per-module actions).
- Tracks an `enabled` flag per module persisted to `data/modules.json`.
- Pushes status updates over the existing admin WebSocket.

### 1.4 Out of scope (for now)

- **Dynamic install at runtime** from a URL/store. In-code modules require a code change; external modules require an entry in `external.json`. No hot-loading.
- **Sandboxing.** In-code modules run with full app privileges. Don't load untrusted code.
- **Per-module auth.** LAN-only posture continues. Add when we leave the LAN.
- **Module versioning / migration.** First version of a module is a fresh slate.

---

## 2. Mental model

```
┌─────────────────────────────────────────────────┐
│ studiopi  (admin)                               │
│                                                 │
│   ModuleRegistry                                │
│      ├─ rgbdisplay      [ServiceModule]         │
│      ├─ news            [Display + Service]     │
│      ├─ picture         [DisplayModule]         │
│      ├─ slideshow       [DisplayModule]         │
│      ├─ pdf             [DisplayModule]         │
│      ├─ video           [DisplayModule]         │
│      ├─ text            [DisplayModule]         │
│      ├─ url             [DisplayModule]         │
│      ├─ default         [DisplayModule]         │
│      ├─ screen_share    [DisplayModule]         │
│      ├─ screen_agent    [ServiceModule]   ← later
│      └─ robot_panel     [DisplayModule]   ← future, external
│                                                 │
│   Admin UI                                      │
│      ├─ Modules tab                             │
│      └─ Screens tab (dropdown reads modules)    │
└─────────────────────────────────────────────────┘
```

A `Screen.type` becomes "which display module is assigned" — the existing enum collapses into "any display module's id". Service modules are configured + monitored from the Modules tab but don't bind to a screen.

---

## 3. Admin UI mockups

### Modules tab

```
┌──────────────────────────────────────────────────────────┐
│  MODULES                                                 │
│                                                          │
│  ● rgbdisplay        Service   [ON]   ✓ running          │
│      [Start] [Stop] [Restart] [View logs]                │
│      Current: led_clock.py                               │
│                                                          │
│  ● news              Display   [ON]   ✓ 5 sources OK     │
│      Last fetch: 12 minutes ago                          │
│                                                          │
│  ● picture           Display   [ON]   ✓                  │
│  ● slideshow         Display   [ON]   ✓                  │
│  ● pdf               Display   [ON]   ✓                  │
│  ● video             Display   [ON]   ✓                  │
│  ● robot-panel       Display   [OFF]  ✗ host unreachable │
│      manifest_url: http://robotpi.local:8080/manifest    │
│                                                          │
│  ● screen-agent      Service   [ON]   ✓ 3/3 stations     │
│      [Relaunch all]                                      │
└──────────────────────────────────────────────────────────┘
```

### Screens tab — content-type dropdown becomes module picker

```
┌──────────────────────────────────────────────────────────┐
│ Screen 5 — Screen 3              ✓ Connected (192.168…)  │
│                                                          │
│   Content: [news       ▼]                                │
│           news, picture, slideshow, pdf, video, text,    │
│           url, default, robot-panel (if enabled)         │
│                                                          │
│   (module-specific config inputs render here)            │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Data Model

### 4.1 In-memory

```python
class Module:
    id: str
    name: str
    description: str = ""
    type: list[Literal["display", "service"]]
    version: str = "0.1.0"

    def is_available(self) -> bool: ...
    def status(self) -> dict: ...

class DisplayModule(Module):
    type = ["display"]
    def get_screen_url(self, screen_id: int) -> str: ...

class ServiceModule(Module):
    type = ["service"]
    def start(self): ...
    def stop(self): ...

class ModuleRegistry:
    modules: dict[str, Module]
    enabled: dict[str, bool]   # persisted in data/modules.json

    def discover(self) -> None: ...
    def get(self, id: str) -> Module: ...
    def list(self) -> list[Module]: ...
    def enable(self, id: str) -> None: ...
    def disable(self, id: str) -> None: ...
```

### 4.2 Persistence

`data/modules.json`:

```json
{
  "enabled": {
    "rgbdisplay": true,
    "news": true,
    "robot-panel": false
  },
  "external": [
    {
      "id": "robot-panel",
      "name": "Robot Control Panel",
      "manifest_url": "http://robotpi.local:8080/module.json"
    }
  ]
}
```

### 4.3 External module manifest (served by the module owner)

```json
{
  "id": "robot-panel",
  "name": "Robot Control Panel",
  "description": "Live status + drive control for the lab robot",
  "type": ["display"],
  "version": "0.2.0",
  "health_url": "http://robotpi.local:8080/health",
  "screen_url_pattern": "http://robotpi.local:8080/screen/{screen_id}",
  "config_fields": []
}
```

---

## 5. Routes & Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/modules` | List all registered modules + status |
| GET | `/api/modules/{id}` | Detail for one module |
| POST | `/api/modules/{id}/enable` | Toggle enabled=true |
| POST | `/api/modules/{id}/disable` | Toggle enabled=false |
| POST | `/api/modules/{id}/start` | Service modules only |
| POST | `/api/modules/{id}/stop` | Service modules only |
| POST | `/api/modules/{id}/action/{name}` | Module-defined custom actions |
| GET | `/admin/modules` | HTML view (Modules tab) |

WebSocket: extend the existing `/ws-screen-status` to also push `{"type": "module_status_update", "module_id": ..., "available": ..., "status": {...}}`.

---

## 6. File Structure

```
screen-mgr/
├── modules/
│   ├── __init__.py             # exports the registry singleton
│   ├── base.py                 # Module / DisplayModule / ServiceModule
│   ├── registry.py             # ModuleRegistry, discovery, persistence
│   ├── rgbdisplay/
│   │   ├── __init__.py         # class RGBDisplayModule
│   │   └── routes.py           # optional per-module API endpoints
│   ├── news/                   # wraps the existing news/ package
│   │   └── __init__.py
│   └── ...
├── routes/
│   └── modules_routes.py       # /api/modules/* and /admin/modules
├── templates/
│   └── admin/
│       └── modules.html        # Modules tab
└── data/
    └── modules.json            # enabled flags + external manifests
```

The existing `news/` package becomes a sibling import (or moves under `modules/news/`). Defer that migration to phase 3 so we don't churn working code.

---

## 7. Dependencies

No new pip packages required. Stdlib + the FastAPI/Pydantic we already use.

For external module health checks: `httpx` (already on the wishlist for the news feature) or stdlib `urllib.request` (we use that in `scripts/maintenance.py`).

---

## 8. Module Lifecycle

```
discover  ──► register  ──► enable? ──► is_available()? ──► render in admin
                                            ▲
                                            └──── background refresh (~30s) or push
```

- **Discovery**: at server startup, the registry walks `modules/` and loads each subpackage that exposes a `register(registry)` function.
- **Registration**: each module instantiates itself and calls `registry.add(self)`.
- **Enabled state**: read from `data/modules.json`. Disabled modules don't appear in the screens dropdown and don't run background checks.
- **Availability**: each module's `is_available()` is invoked on demand (admin opens the tab) and on a 30s background tick for cached status. Push to admin via WS.

---

## 9. The first three modules

### 9.1 `rgbdisplay` (service)

- `is_available()` → `True` if `/etc/systemd/system/rgbdisplay.service` exists; `status()` parses `systemctl is-active rgbdisplay.service` plus current sub-mode (clock vs other).
- `start()` → `sudo systemctl start rgbdisplay.service`
- `stop()` → `sudo systemctl stop rgbdisplay.service`
- Future actions: `action/switch?to=axolotl_anim` for the alternative scripts in `/home/admin/rpi-rgb-led-matrix/`.

**Permissions:** requires `screen-mgr`'s admin user to `systemctl` the `rgbdisplay.service` without a password. Add a tight `/etc/sudoers.d/screen-mgr` entry:

```
admin ALL=(root) NOPASSWD: /bin/systemctl start rgbdisplay.service, /bin/systemctl stop rgbdisplay.service, /bin/systemctl restart rgbdisplay.service, /bin/systemctl is-active rgbdisplay.service
```

### 9.2 `news` (display + service)

- Display: existing `news/` package provides the per-screen URLs (`/news/portrait`, `/news/landscape`, `/news/presentation`); module wraps that.
- Service: future RSS fetcher runs as a background task. `is_available()` cheap network ping to sources.

### 9.3 `screen-agent` (service, post-§12.3)

- The cross-platform Python agent on each station, surfaced through the registry. `is_available()` aggregates per-station agent reachability. `status()` returns per-station detail (PID, browser URL, uptime).
- Custom action: `action/relaunch-all` fans out to every connected station.

---

## 10. Implementation Phases

- [ ] **Phase 1: Registry skeleton** — `modules/base.py`, `modules/registry.py`, `/api/modules`. No modules yet. Just the plumbing.
- [ ] **Phase 2: `rgbdisplay` as first module** — moves the LED control out of "just a systemd unit we restart manually" and into the admin UI. Includes the sudoers entry on studiopi.
- [ ] **Phase 3: Admin Modules tab** — `templates/admin/modules.html` rendering the registry. Live status via WebSocket extension. Start/stop buttons for `rgbdisplay`.
- [ ] **Phase 4: Wrap existing content types as display modules** — `news`, `picture`, `slideshow`, `pdf`, `video`, `text`, `url`, `default`, `screen_share` each get a thin `modules/<x>/` wrapper. Screens tab dropdown becomes module-driven. Backward-compatible with `Screen.type` strings.
- [ ] **Phase 5: External-module manifest registration** — `data/modules.json` gets `external` list; registry fetches manifests at startup and on demand; admin can add/remove entries.
- [ ] **Phase 6: `screen-agent` as a registered module** — closes the loop with `TASKS/PLAN_SCREEN_AGENT.md`. Admin tab gets "Relaunch all" and per-station relaunch buttons.
- [ ] **Phase 7: Documentation** — `docs/MODULES.md` operator guide + module authoring template.

---

## 11. Decisions captured in this plan

- **In-code first.** Modules are Python packages in `modules/` in v1. External modules (separate processes / different machines) come later via JSON manifests. Don't try to do hot-loaded plugin install in v1.
- **`Screen.type` stays a string slug.** Display modules' `id` matches the slug. No schema migration needed; admin dropdown is just populated dynamically.
- **Availability is a `bool` + optional `status` dict.** Don't over-typecheck. Modules can put anything in `status` for the UI to render.
- **Persistence is JSON, not a database.** Matches `screens.json`, `news/*.json` already in the project.
- **No auth on module endpoints.** LAN-only. Will revisit when we have non-trivial external modules.

---

## 12. Open questions

- **How does a module declare custom admin-UI fields?** (e.g. news's "mode: portrait|landscape|presentation"). Options: (a) hardcoded in `templates/admin/screens.html` per content_type, like today; (b) module provides a Jinja partial; (c) module declares fields in JSON, registry renders. Defer past phase 4.
- **What if two modules claim the same screen-id slug?** First wins, log a warning. Strict mode later.
- **Should disabled modules' historical screen assignments persist or reset?** Lean: persist; if the module re-enables, the screen renders again with no surprises.
- **Will the screen-agent module talk to its stations over MQTT eventually?** Yes likely; the agent module's transport is its private business — the registry contract stays HTTP-shaped.

---

## 13. Why this is the right shape

- **Minimal new vocabulary.** Module / availability / enable. Three concepts.
- **Composable.** Today's news, slideshow, etc. fit the pattern. So does rgbdisplay. So does the future robot panel.
- **Doesn't replace anything wholesale.** We add the registry alongside; existing routes keep working until phase 4 quietly moves them.
- **Makes "is this thing reachable?" a first-class question** — which is exactly what an IoT/MDM platform owes its operators.

---

## 14. Tomorrow's first move (when we pick this up)

1. Land **phase 1** as one commit: `modules/__init__.py`, `modules/base.py`, `modules/registry.py`, `/api/modules` GET endpoint returning empty list. Deploy. Confirm endpoint reachable.
2. Land **phase 2** as next commit: `modules/rgbdisplay/` + sudoers config + admin start/stop API. Deploy. Curl-test start/stop on the LED matrix.
3. Land **phase 3** next: Modules tab in admin. Visual verification.

Each phase is a single deploy. Each is independently useful.
