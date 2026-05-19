# Admin Panel Redesign — Reinvention Studio UX Adoption

**Status:** Planning
**Branch:** `staging/admin-redesign` (to be created)
**Created:** 2026-05-19

---

## Vision

Adopt the Reinvention Studio's room-aware UX (zones, floor plan, brand-profile theming, scenes) on top of our **existing real infrastructure** (Hue Bridge, screen WebSockets, module registry, systemd-managed services). The Reinvention prototype is beautiful but entirely simulated — we have the opposite problem: working plumbing in a plain UI. The redesign mates the two.

**Non-negotiable:** no existing functionality is lost in the shift. The Modules tab, Lights tab, LED matrix control, screen content management, and deploy pipeline all keep working at every phase.

---

## 1. What we keep from screen-mgr today

| Feature | Status |
|---|---|
| Module registry + admin Modules tab | Stays as-is, just restyled |
| Lights tab + Hue Bridge integration | Stays, restyled, eventually folded into zone view |
| Screen WebSocket reload + `/updating` page | Stays, server-side untouched |
| Deploy pipeline (`scripts/deploy.sh`) | Stays |
| systemd auto-start (rgbdisplay + screen-mgr) | Stays |
| News module + content type modules | Stays |
| External-module registration (Phase 5 of `PLAN_MODULES.md`) | Stays |
| `rgbdisplay` module (LED matrix) | Stays — surfaced in Modules tab and also as a zone |
| The current admin at `/admin` | Stays live throughout the redesign on the existing branch |

## 2. What we adopt from Reinvention-AI

| Element | Notes |
|---|---|
| **Design tokens** (CSS custom properties) | dark + light themes, `--bg`/`--panel`/`--card`/`--border`/`--text*`/`--brand`. Stolen wholesale. |
| **Accenture purple** `#A100FF` as the brand accent | matches the studio's identity |
| Square corners (`border-radius: 0`) | consistent visual language |
| Graphik font (with fallbacks) | typography signature |
| 150ms ease-out animation curve | unified feel |
| **Floor plan SVG** approach | a 2D layout of the Studio with zones as polygons |
| **Zone model** (id, name, area, gradient, screen, light) | new abstraction over our existing screens |
| **Layout grid** — header / sidebar / main / right panel | adopted, right panel is empty in v1 (no agent yet) |
| Sidebar view toggle (Screens vs Lighting) | adopted, with one extra view (Modules) |
| Light/dark theme toggle | persisted in `localStorage` |

## 3. What we deliberately defer

| Deferred to | Why |
|---|---|
| **Chat agent panel** → Phase 6 | The right panel exists but stays empty/collapsible. Agent makes sense once we have a richer state model worth talking to. |
| **Voice control** → Phase 6 | Comes with the agent. |
| **Brand profiles** → Phase 7 | The concept maps to a non-trivial new data model and requires design work (per-brand gradient sets, scene defaults). Last in line. |
| **Scenes** (the Reinvention sense — zone→gradient maps) → Phase 5 | Useful but layered on top of zones. Comes after zones exist. |
| **Quick-actions chips** → Phase 6 | Tied to the agent panel. |

## 4. Concept mapping (their language ↔ ours)

| Reinvention-AI | screen-mgr | Note |
|---|---|---|
| **Zone** | bundle of: 1 Screen + N Hue lights + position on the floor plan | new abstraction; screens stay backing data |
| **Brand profile** | new model `data/brand_profiles/<id>.json` | Phase 7 |
| **Scene** | bundle of: Hue scene id + per-zone screen content + optional gradient/animation | Phase 5 |
| Light presets (warm/cool/blue) | shortcut buttons that call our Hue module | Phase 4 |
| Floor plan SVG | new `templates/admin/v2/floorplan.svg.html` | Phase 3 |
| Gradient animations on zones | optional v1 (CSS) | Phase 4 |
| Chat | _(deferred Phase 6)_ | — |
| Voice | _(deferred Phase 6)_ | — |

---

## 5. New data model

### 5.1 `Zone`

```python
@dataclass
class Zone:
    id: str                  # slug, e.g. "entrance", "workshop", "studio-main"
    name: str                # "Entrance"
    screen_id: int | None    # foreign key to Screen.id (1..8) — None if no screen there
    light_group_id: str | None  # Hue group id (e.g. "81" for Studio) — None for no lights
    polygon: list[tuple[float, float]]  # SVG points on the floor plan, viewBox-normalised
    label_xy: tuple[float, float]       # where to render the label
    area_label: str          # e.g. "28 m²" or "—"
```

Persisted to `data/zones.json`. Loaded at startup, exposed via `/api/zones`.

### 5.2 Theme persistence

Client-side `localStorage.studio-theme = "dark"|"light"`. CSS toggles via `html.light`.

### 5.3 `BrandProfile` (Phase 7, sketched only)

```python
@dataclass
class BrandProfile:
    id: str                  # "accenture", "ikea", "hm", or custom
    name: str
    accent_color: str        # CSS color, drives --brand
    default_scene: str       # Scene.id
    logo_url: str | None
    metadata: dict           # extensible
```

### 5.4 `Scene` (Phase 5)

```python
@dataclass
class Scene:
    id: str                  # "welcome", "workshop", "presentation", ...
    name: str
    hue_scene_id: str | None # one of the bridge's 28 native scenes
    zone_overrides: dict[str, dict]  # zone_id -> {screen_content_type, content_value, gradient, anim}
```

---

## 6. UI structure

### 6.1 Overall layout

```
┌──────────────────────────────────────────────────────────────┐
│ HEADER  48px                                                 │
│  [logo]  [clock]  [brand-profiles ▾]  [scenes ▾]    [☼/☾]    │
├──────────┬───────────────────────────────────────┬───────────┤
│ SIDEBAR  │ MAIN                                  │ CONTROLS  │
│ 260px    │                                       │ 300px     │
│          │   ┌─────────────────────────────┐     │ (empty in │
│ Views:   │   │                             │     │  v1 — chat│
│  Screens │   │   Floor plan SVG            │     │  panel    │
│  Lights  │   │   (clickable zones)         │     │  later)   │
│  Modules │   │                             │     │           │
│          │   └─────────────────────────────┘     │           │
│ Zone     │                                       │           │
│ editor   │   Selected zone preview               │           │
│ panel    │                                       │           │
│          │                                       │           │
│ [Save]   │                                       │           │
└──────────┴───────────────────────────────────────┴───────────┘
```

### 6.2 Sidebar views

- **Screens view** — list of zones; clicking a zone selects it; sidebar shows screen-id, current content, content-type dropdown, content fields. (Wraps the existing per-screen form per zone.)
- **Lights view** — same per-zone selection, sidebar shows Hue group toggles, brightness, color picker (subset of the existing Lights tab targeted at the selected zone).
- **Modules view** — collapsed version of today's Modules tab.

### 6.3 Header dropdowns

- **Brand profiles** — list of profiles, "Apply", "+ Add Profile" (Phase 7).
- **Scenes** — list of scenes, "Apply" (Phase 5).

In v1 both dropdowns can be present but mostly empty; they become useful in their respective phases.

---

## 7. Phased rollout

### Phase 1 — Design tokens + theme infrastructure
- Extract Reinvention's `--*` custom properties into `static/css/design-tokens.css`.
- Add light/dark theme toggle (vanilla JS, localStorage).
- Apply to the existing admin templates non-destructively: existing UI keeps working, just looks different. Header logo + theme toggle land here.
- **Verify:** Refresh `/admin`, see the new aesthetic, all existing buttons still work.

### Phase 2 — Zone model
- Add `Zone` Pydantic model + `data/zones.json`.
- Seed with one zone per existing screen (8 zones) + the LED matrix as a zone-less service.
- Expose `/api/zones`, `/api/zones/{id}`.
- No UI change yet.
- **Verify:** GET `/api/zones` returns 8 zones; each links to a screen.

### Phase 3 — Floor plan SVG
- New page `/admin/v2` (mounted alongside `/admin`).
- Renders a hand-drawn SVG of the studio with the 8 zones positioned. (User-supplied coordinates or rough guess to start.)
- Clicking a zone selects it; selected zone shows in a side panel with current screen content + assigned light group.
- Existing `/admin` continues to work.
- **Verify:** Visit `/admin/v2`, click each zone, see correct screen info in the panel.

### Phase 4 — Migrate existing controls into the new shell (modular)

**Architectural invariant (added 2026-05-19):** the v2 admin is **never** a single monolithic template. Each domain (Lights, Screens, LED Screens / rgbdisplay, Modules registry) gets its own self-contained view template + JS file. The shell only knows the list of views, not their internals.

```
templates/admin/v2/
├── index.html              # shell: header, grid, sidebar nav, floor plan, right panel
├── partials/
│   └── floorplan.html      # SVG floor plan — included by the shell
└── views/
    ├── screens.html        # per-zone screen content management
    ├── lighting.html       # Hue controls (reuses /api/modules/hue/*)
    ├── led_screens.html    # rgbdisplay + any future LED outputs
    └── modules.html        # registry overview (port of today's Modules tab)

static/js/v2/
├── shell.js                # Alpine app for the layout, zone selection, theme
└── views/
    ├── screens.js
    ├── lighting.js
    ├── led_screens.js
    └── modules.js
```

Per-view rules:

- **Self-contained Alpine scope.** A view manages its own state, fetches its own endpoints, and never reaches into shell internals beyond reading the currently selected zone.
- **One file per view, both for the template and the JS.** Add a new domain = add two files + one sidebar nav entry. No edits to the shell.
- **Reuses existing backend endpoints.** No backend rewrite in this phase; the heavy lifting is in `/api/zones`, `/api/modules/*`, `/api/screens`, `/api/modules/hue/*`.

### Phase 4-bis — Modules as consumable primitives (architectural insight, 2026-05-19)

The simple in-code modules (`url`, `text`, `picture`, `video`, `pdf`, `slideshow`) are not just admin-facing content types — they are **reusable primitives** other modules can compose. A future "Robot Control Panel" might fetch live telemetry and have its own UI built out of:

- `text.get_screen_url(virtual_screen("Temperature: 23°C"), base_url)` for a number readout
- `picture.get_screen_url(virtual_screen("robot.png"), base_url)` for a status diagram
- Custom HTML for the parts that don't fit a primitive

The existing `DisplayModule.get_screen_url(screen, base_url)` contract already makes this possible. To formalize:

- A compound module can call `registry.get(primitive_id).get_screen_url(...)` with a lightweight Screen-like object (just `id`/`name` plus whichever content fields the primitive reads).
- Phase 4-bis adds a `registry.compose(primitive_id, **fields)` helper that builds the Screen-like wrapper, so callers don't have to know which fields each primitive expects.

This means: when we build the screen-agent (Phase 6 of `TASKS/PLAN_SCREEN_AGENT.md`) and the robot panel module, **they reuse** these primitives rather than reinventing renderers. Same vocabulary across the system.

**Future primitives we'll want** (each is a short `modules/<name>/__init__.py` + a renderer template, registered like the others):

- `json` — display a structured payload (pretty-printed, optionally tree-rendered). Sourced from a URL, file, or inline.
- `csv` — render rows as a table; headers + body styling.
- `markdown` — server-rendered MD, useful for status pages, runbooks, dashboards.
- `iframe` — embed any external page (different from `url` which steers the whole screen).
- `chart` — render a chart from a `csv` or `json` source. Composes the simpler primitives.

Adding any of these = one folder + one register line, no surgery to the rest of the system.

**Verify:** every action available today is available in `/admin/v2` too — set content, upload media, start/stop modules, control lights — each driven by its dedicated view.

### Phase 4-ter — Unified content / data storage (architectural note, 2026-05-19)

Today's persistence is **scattered**:

- `data/screens.json` — Screen configs
- `data/zones.json` — Zone configs (new in Phase 2)
- `data/modules.json` — module enabled flags + external manifest entries
- `data/hue.json` — Hue bridge credentials
- `news/*.json` — news sources, articles, playlists
- `static/pictures/<folder>/<file>` — uploaded images
- `static/videos/<file>` — uploaded videos
- `static/pdfs/<file>` — uploaded PDFs
- per-module storage that any new module would invent again

This works at today's scale but leaks responsibility: every new module reinvents its own JSON-on-disk scheme; uploads land in different folders; nothing has a single source of truth for "what content is on this Pi".

**Proposed layer** (its own plan when we get there): a single `storage/` API that every module reads/writes through. Two surface concepts:

| Surface | What it stores | How it's accessed |
|---|---|---|
| **Data** (small structured records) | JSON, CSV, markdown, module configs | `storage.put_data(namespace, key, value)`, `storage.get_data(namespace, key)`, `storage.list_data(namespace)` |
| **Content** (binary blobs) | Images, videos, PDFs, audio, any large file | `storage.put_content(namespace, name, bytes_or_stream)`, `storage.get_content(namespace, name)`, `storage.get_content_url(namespace, name)` |

Backing store starts as filesystem (today's pattern, just unified under `storage/<namespace>/...`) and can evolve to SQLite for data + content-addressable storage for blobs without changing the API. Each module gets its own namespace (`modules.hue.config`, `modules.news.articles`, `screens.uploads`, etc.).

**Why this matters for the redesign:**
- A `json`/`csv` consumable module can read content from `storage.get_data(...)` rather than fetching a URL — turns "data on the Pi" into first-class addressable content.
- Backup / migration / share-with-another-Pi becomes one operation against `storage/` rather than `data/` + `static/*` + per-module trees.
- Future Brand Profiles (Phase 7) and Scenes (Phase 5) can reference content by `storage://` URI rather than per-feature paths.

**Promote to its own plan** (e.g. `TASKS/PLAN_STORAGE.md`) before implementation. Not blocking Phase 4 — that finishes first.

### Phase 5 — Scene model
- Add `Scene` model + `data/scenes.json`.
- Each scene bundles: optional Hue scene id, per-zone screen content overrides.
- Header **Scenes** dropdown populated; "Apply" triggers a scene.
- **Verify:** Create a "Welcome" scene that turns Hue scene "Stockholm City Hall" on and sets two screens to the Studio Logo; apply it, observe.

### Phase 6 — Chat agent + voice (defer until something to talk to)
- Right panel returns. Either Claude API integration (real NLU) or a rule-based state machine.
- Voice via Web Speech API.
- Quick actions chip "Start Studio Setup".
- **Verify:** "Apply Welcome scene", "set Workshop screen to news".

### Phase 7 — Brand profiles
- Add `BrandProfile` model + `data/brand_profiles/<id>.json`.
- Header dropdown populated.
- Selecting a profile re-themes `--brand` and pre-loads the default scene.
- "+ Add Profile" workflow (UI for creating profiles).
- Migration of existing screen content per profile.
- **Verify:** Swap from Accenture to a custom profile mid-day, see the room change.

### Phase 8 — Cutover and cleanup
- `/admin/v2` graduates to `/admin`.
- Old `/admin` becomes `/admin/legacy` for one release cycle, then removed.
- Update `docs/MODULES.md` and `docs/ARCHITECTURE.md`.

---

## 8. Branch strategy

- Create `staging/admin-redesign` from current `main`.
- All redesign work commits land on the branch.
- `main` continues to receive small fixes / feature-additions that get periodically merged into `staging/admin-redesign`.
- Each phase merges to `staging/admin-redesign` cleanly and stays unpushed-to-main until cutover (Phase 8).
- `scripts/deploy.sh` deploys whichever branch is checked out on the Pi — for testing the redesign, we'd switch the Pi temporarily, otherwise the Pi stays on `main`.

---

## 9. File structure (new)

```
screen-mgr/
├── static/
│   └── css/
│       └── design-tokens.css      # Phase 1
├── templates/
│   └── admin/
│       └── v2/                    # Phase 3+
│           ├── shell.html          # main layout
│           ├── floorplan.html      # SVG floor plan partial
│           ├── sidebar_screens.html
│           ├── sidebar_lighting.html
│           └── sidebar_modules.html
├── routes/
│   └── admin_v2_routes.py         # /admin/v2 routes — Phase 3+
├── models/                        # split out for redesign
│   ├── zones.py                   # Phase 2
│   ├── scenes.py                  # Phase 5
│   └── brand_profiles.py          # Phase 7
└── data/
    ├── zones.json                 # Phase 2
    ├── scenes.json                # Phase 5
    └── brand_profiles/            # Phase 7
        └── <id>.json
```

---

## 10. Open questions

- **Studio floor-plan accuracy.** Do we have a real architectural drawing of the room, or do we approximate zone positions? Affects Phase 3.
- **Which screens map to which zones?** Today: screens 1-8 have names like "Station 1", "Station 2", "Screen 2", "Main Screen". Do we have a physical mapping (which screen is on which wall)?
- **Light group → zone mapping.** The Hue bridge has 2 rooms today ("Maker", "Studio"). Are these our zones, or are zones finer-grained than rooms?
- **Should the v2 admin reuse Jinja templates, or move to client-side rendering?** Reinvention-AI is single-page vanilla JS. Our current admin is server-rendered Jinja + Alpine sprinkles. v2 could go either way; defer decision until Phase 3.
- **Floor-plan canvas vs SVG.** They use SVG. Canvas would allow richer effects (gradient animations matching screens) but is harder to make accessible. Lean SVG.
- **The 28 Hue scenes already exist.** Do they become our `Scene` model directly, or are our scenes a meta-layer on top of them? Lean: meta-layer (so scenes also dictate screen content, not just lights).

---

## 10.5. Gotchas we hit (and how to avoid)

Captured 2026-05-19 after a long debug session on Phase 4. These are non-obvious; future-you (and any colleague picking up the redesign) will thank past-you.

### 10.5.1 Alpine 3 + the microtask race

**Symptom:** Cascading `Uncaught ReferenceError: studioShell is not defined` (and every property after it — `view`, `zones`, `selected`, ...). Page renders the static HTML and CSS but Alpine bindings are dead.

**Root cause:** Alpine 3's `cdn.min.js` ends with a `queueMicrotask(() => { document.dispatchEvent(new Event('alpine:init')); Alpine.start(); })`. Microtasks **drain between deferred scripts**, not after all of them. So if `alpine.min.js` comes before any factory script in document order, the sequence is:

1. `alpine.min.js` task runs → schedules microtask
2. Microtask drains: `alpine:init` fires, `Alpine.start()` walks the DOM
3. *Then* the next deferred script (which would have set `window.studioShell`) runs — too late.

**Fix:** **Load every `window.X` factory script BEFORE alpine in document order.** Currently:

```html
<script defer src="...studio-theme.js?...">
<script defer src="...v2/shell.js?...">
<script defer src="...v2/views/screens.js?...">
<script defer src="...v2/views/lighting.js?...">
<script defer src="...v2/views/led_screens.js?...">
<script defer src="...v2/views/modules.js?...">
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.13.5/dist/cdn.min.js"></script>  <!-- LAST -->
```

Adding a new view = add its `<script defer>` to `<head>` *before* the alpine line. **Do not** put view `<script>` tags inside the per-view templates — they'd end up in body, after alpine's microtask has already drained.

The factories also register themselves on `alpine:init` via `Alpine.data()`, but that path is dormant: it only takes effect if Alpine *re-walks* the DOM (which it doesn't on its own).

### 10.5.2 `$root.X` is the element, not the data

**Symptom:** Inside a child x-data scope, `$root.selected` is always undefined, even when the parent scope has `selected: ...`.

**Root cause:** `$root` returns the closest x-data **element**, not its data object. Property access on the element returns DOM properties.

**Fix:** Use the bare property name — Alpine 3's scope chain walks up through parent x-data scopes for any name the child doesn't define. Just write `selected`, not `$root.selected`.

### 10.5.3 Cache-bust requires uvicorn restart

**Symptom:** New JS landed but browser still serves old version. `?v={{ app_version }}` URL doesn't change because uvicorn `--reload` only triggers on `.py` files.

**Fix:** `scripts/pi-update.sh` now `touch utils.py` after every successful `git pull`, forcing uvicorn to reload and refresh `APP_VERSION` even for HTML/CSS/JS-only deploys.

### 10.5.4 Endpoint-blocker browser extensions

**Symptom:** Static JS files never load, but no 404 in Network tab — the requests just don't happen.

**Cause:** Edge/Chrome extensions like Volentio JSD (corporate JS-blockers) silently prevent script execution on unfamiliar hostnames.

**Fix:** Whitelist `studiopi.local` (and any other Pi the team works against) in the blocker's site list. If you ship to colleagues, mention this in `docs/DEPLOY.md`.

---

## 11. Why this is the right shape

- **Phased.** Each phase ships independently useful value. Bailing after Phase 1 already leaves the admin meaningfully better.
- **Non-destructive.** Existing `/admin` stays live; the new UI is built alongside.
- **Real underneath.** Where Reinvention-AI fakes everything, we substitute real hardware integrations.
- **Concept hierarchy is sound.** Zone → Scene → Brand Profile mirrors the room's real layering: physical → preset → branded experience.
- **Defers the speculative parts.** Chat/voice/brand-profile UX needs design iteration; we don't gate visual progress on it.
