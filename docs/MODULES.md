# Modules

How content sources and backend services plug into screen-mgr through the **module registry**, and how to write your own.

## What is a module

A **Module** is anything the admin panel can wire to a screen or control as a service. The same uniform contract covers:

- The 9 built-in content types (`url`, `text`, `video`, `picture`, `pdf`, `slideshow`, `news`, `screen_share`, `default`)
- The LED matrix service (`rgbdisplay`)
- Anything new you or a colleague writes (a robot dashboard, a sensor readout, another LED display, etc.)

Every module declares:

| Field | Purpose |
|---|---|
| `id` | Stable slug — also the value of `Screen.type` for display modules |
| `name` | Human-friendly label in the admin |
| `description` | One-liner |
| `version` | Semver-ish, surfaced in the Modules tab |
| `type` | `["display"]`, `["service"]`, or both |

Every module implements:

- `is_available() -> bool` — fast yes/no health check
- `status() -> dict` — optional richer detail (process state, last error, etc.)

Display modules additionally implement:
- `get_screen_url(screen, base_url) -> str` — URL the screen should load

Service modules additionally implement:
- `start() -> dict`, `stop() -> dict`

## Two ways modules get into the registry

1. **In-code** — a Python package under `modules/<id>/` that registers itself at server startup (see [Writing an in-code module](#writing-an-in-code-module)).
2. **External manifest** — a JSON file hosted by another service. Drop the URL into the admin panel's "Add external module" form and it's fetched, validated, registered. The external module's actual logic runs wherever it lives; screen-mgr only knows the contract from the manifest (see [Writing an external module](#writing-an-external-module)).

## Operator guide — using the Modules tab

Visit `http://studiopi.local:8000/admin` and click the **Modules** tab.

You'll see one row per registered module:

```
RGB LED Matrix                                       available  [ENABLED]
rgbdisplay · v0.1.0 · service
32x64 LED matrix on studiopi...
[Start] [Stop]   active: active · boot: enabled
```

What you can do:

- **Toggle ENABLED/DISABLED** — disabled modules don't appear in the screen content-type dropdown and don't run background availability checks. Persisted to `data/modules.json`.
- **Start / Stop** (service modules only) — for `rgbdisplay`, these run `sudo systemctl start|stop rgbdisplay.service` under the hood. Visual change on the LED matrix within a second.
- **Add external module** — paste a manifest URL, click **Register**. The manifest is fetched, validated, registered. Appears in the same list with a purple `external` badge. Removable with the ✕ button.
- **Refresh externals** — re-fetches every configured external manifest. Useful after restarting a remote service to flip its availability badge back to green.

## Built-in modules (today)

| id | type | What it shows |
|---|---|---|
| `url` | display | Any URL (YouTube auto-routed through embed wrapper) |
| `text` | display | Big centered responsive text from `Screen.text` |
| `video` | display | MP4 from `static/videos/` |
| `picture` | display | Image from `static/pictures/<folder>/` |
| `pdf` | display | PDF from `static/pdfs/` |
| `slideshow` | display | All images in a `static/pictures/<folder>` cycled |
| `news` | display | AI news in `portrait` / `landscape` / `presentation` mode |
| `screen_share` | display | Experimental WebRTC viewer |
| `default` | display | Studio logo placeholder |
| `rgbdisplay` | service | LED matrix clock — start/stop via systemd |

Disabling a display module hides it from the screens-tab dropdown but doesn't break any screen currently assigned that type — the route renderer falls back to `default`.

## Writing an in-code module

Two files. Five minutes.

**1. `modules/<id>/__init__.py`** — the module class:

```python
from modules.base import DisplayModule

class WeatherModule(DisplayModule):
    id = "weather"
    name = "Weather"
    description = "Local weather conditions from OpenWeatherMap."
    version = "0.1.0"

    def is_available(self):
        return True  # add a real check if you want

    def get_screen_url(self, screen, base_url):
        # Could embed an external API URL, or a local route you also added.
        city = (screen.text or "Stockholm").strip()
        return f"https://wttr.in/{city}?format=2&_=fullscreen"
```

For a **service module**, derive from `ServiceModule` instead and implement `start()` / `stop()` returning `{"ok": bool, ...}`.

**2. `modules/__init__.py`** — one-line registration:

```python
from modules.weather import WeatherModule
registry.register(WeatherModule())
```

Deploy. The module appears in the Modules tab and (for display modules) in the screens dropdown. No other changes needed.

## Writing an external module

Host a JSON manifest at a URL screen-mgr can reach over the LAN.

**Display module manifest:**

```json
{
  "id": "robot-panel",
  "name": "Robot Control Panel",
  "description": "Live status + drive control for the lab robot",
  "type": ["display"],
  "version": "0.2.0",
  "health_url": "http://robotpi.local:8080/health",
  "screen_url_pattern": "http://robotpi.local:8080/screen/{screen_id}"
}
```

**Service module manifest:**

```json
{
  "id": "co2-fan",
  "name": "Cleanroom CO2 Fan",
  "type": ["service"],
  "version": "0.1.0",
  "health_url": "http://co2pi.local:8090/health",
  "start_url": "http://co2pi.local:8090/start",
  "stop_url": "http://co2pi.local:8090/stop"
}
```

Then in the admin's **Modules** tab → "Add external module" → paste the manifest URL → **Register**. Done.

What screen-mgr does:
- Fetches and JSON-parses the manifest (timeout 5s).
- Wraps it in `ExternalDisplayModule` or `ExternalServiceModule`.
- Caches the manifest_url in `data/modules.json` so it persists across restarts.
- On each `is_available()` call, GETs the manifest's `health_url` (timeout 3s); if it returns 200, the module is green.
- For service modules, `Start` POSTs to `start_url`; `Stop` POSTs to `stop_url`.

A manifest that becomes unreachable doesn't get unregistered — it stays in the list with a red badge until you fix it or remove it. That's by design (intermittent network shouldn't lose your config).

## API reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/modules` | List all modules with status |
| GET | `/api/modules/external` | List configured external entries |
| GET | `/api/modules/{id}` | Detail for one module |
| POST | `/api/modules/{id}/enable` | Mark enabled |
| POST | `/api/modules/{id}/disable` | Mark disabled |
| POST | `/api/modules/{id}/start` | Service modules only |
| POST | `/api/modules/{id}/stop` | Service modules only |
| POST | `/api/modules/external` | Body: `{manifest_url}` — register external |
| DELETE | `/api/modules/external/{id}` | Unregister and remove from config |
| POST | `/api/modules/refresh` | Re-fetch every external manifest |

No auth — LAN-only posture (same as the rest of the admin).

## Persistence

Two facts persist to `data/modules.json`:

- `enabled`: `{module_id: bool}` — whose disabled flags survive restarts
- `external`: `[{id, manifest_url}, ...]` — which external manifests to re-fetch on startup

`data/modules.json` is gitignored (per-host runtime state, not config-as-code).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Module shows as `unavailable` (red badge) | `is_available()` returned False — for built-ins that's rare; for external modules it's the `health_url` failing | Confirm the manifest server is up. Check Network. Hit `health_url` directly with curl. |
| External module registered but `available: false` right away | Health URL never responded 200 | Verify the URL works from the Pi (`ssh admin@studiopi.local 'curl <health_url>'`) — LAN paths matter |
| `start`/`stop` returns `{ok: false}` for `rgbdisplay` | sudo password required (admin's NOPASSWD lost) | `sudo -n -l` on the Pi; restore NOPASSWD if needed |
| `GET /api/modules/external` returns 404 | Old build before the route-ordering fix | Pull latest; ensure `/api/modules/external` routes are declared before `/api/modules/{id}` |
| Module disappears after server restart | `data/modules.json` not preserved (wiped?) | Check the file; for in-code modules, registration is in `modules/__init__.py` and survives anyway |
| Manifest registration says "could not register" | URL unreachable, returned non-JSON, or missing `id` field | Hit the URL with curl; should return valid JSON with at least `id`, `name`, `type` |

## Adding a new content type

Was a big surgery before: edit `screen_routes.py`, edit `api_routes.py`'s validation list, edit `admin/screens.html`'s `<option>` list, add a content route. **Now:**

1. Add `modules/<id>/__init__.py` with a `DisplayModule` subclass implementing `get_screen_url`.
2. Add the import + registration line in `modules/__init__.py`.
3. Deploy.

That's it. The screens dropdown picks it up dynamically, `set_content` accepts the new id, screen-routing dispatches to it.
