# UI Rebuild — Functionality Preservation Checklist

**Purpose:** the redesign to Madalena's prototype must not drop any working functionality.
This is the regression contract: every capability the current `/admin/v2` has today, where it
lives now, where it lands in the rebuild, and a verify box to tick once confirmed working in the
new UI. Derived from the pre-rebuild inventory of `templates/admin/v2/` + backends.

Legend: ☐ not yet verified in new UI · ☑ verified working in new UI.

## Screens tab (content control)
- ☐ Per-zone screen content editor: type dropdown (news/text/url/video/picture/pdf/slideshow/
  screen_share/default) + type-specific inputs → `POST /api/screens/{id}/set_content`
- ☐ Media libraries: list videos / pdfs / slideshows / pictures (by subfolder) —
  `GET /api/videos|pdfs|slideshows|pictures`
- ☐ Uploads: picture (+ subfolder / new subfolder), video, pdf — `POST /api/upload/{kind}`
- ☐ Scenes dropdown apply — `POST /api/scenes/{id}/apply`
- ☐ Reload all — `POST /api/screens/reload-all`
- ☐ Fleet demo test (~20s) — `POST /api/screens/run_fleet_demo`
- ☐ Global screens list with connection dot + type pill + client_host — `GET /api/screens` (poll)
- ☐ Picture content_value MUST stay folder-prefixed (e.g. `IKEA/Cloud_2.png`)

## Lighting tab (Philips Hue)
- ☐ Bridge status (paired/available/IP) + pairing instructions — `GET /api/modules/hue`
- ☐ Per-zone group toggle + brightness (when zone has light_group_id)
- ☐ All rooms: per-room toggle + brightness — `PUT /api/modules/hue/groups/{id}`
- ☐ Hue scenes recall — `POST /api/modules/hue/scenes/{id}/recall`
- ☐ Individual lights: toggle + brightness + color picker (HSV→XY) — `PUT /api/modules/hue/lights/{id}`
- ☐ All on / all off — `POST /api/modules/hue/all/{on|off}`
- ☐ Startup test (~12s) — `POST /api/modules/hue/run_startup_test`

## Audio tab (merged Audio + Music — Phase 7)
- ☐ PulseAudio sinks: per-sink volume + mute — `GET /api/audio/sinks`, `POST /api/audio/volume|mute`
- ☐ PulseAudio sources list — `GET /api/audio/sources`
- ☐ Networked mics (Sennheiser SSC): mute/unmute + reachability test —
  `GET /api/audio/microphones`, `POST /api/audio/microphones/{id}/mute|test`
- ☐ Network audio streams (Dante/AES67 SAP) list — `GET /api/audio/streams`
- ☐ Spotify embedded player (iframe) + open-in-new-tab
- ☐ Marantz test (fade 20→50, play, auto-stop) + kill switch —
  `POST /api/music/marantz/play_local_file|stop`

## Robot tab
- ☐ Vision dashboard iframe (`http://192.168.2.104:8000/`) + open-in-new-tab fallback

## Agent chat (right panel)
- ☐ SSE streaming chat — `POST /api/chat` (events: token / tool_use / tool_result / error / done)
- ☐ Tool calls render as `→ tool(inputs)` + `✓ tool: summary`
- ☐ Text input (Enter send / Shift+Enter newline)
- ☐ Voice: MediaRecorder → `POST /api/transcribe` (Whisper) with Web-Speech fallback;
  health probe `GET /api/transcribe/health`; spacebar PTT + 🎤 hold
- ☐ Backend status pill (ready/stub)

## Floor plan + zones
- ☐ Zone select drives the per-zone editor (selection state)
- ☐ Zone connection/selection visual states
- ⚠ Device positioning (drag markers, place devices) — `GET/PUT /api/positions` →
  **moves to `/admin/ops` (Phase 8)**, must remain reachable

## Operator tools → `/admin/ops` (Phase 8) — must survive, not on main view
- ☐ Modules registry: enable/disable, start/stop service, add/remove external, refresh —
  `GET /api/modules`, `POST /api/modules/...`, `DELETE /api/modules/external/{id}`
- ☐ LED panels (rgbdisplay): enable/disable, start/stop, test pattern —
  `POST /api/modules/{id}/run_test_pattern`
- ☐ Device positioning UI (see above)

## Real-time (WebSocket) — keep wired
- ☐ Per-screen reload signal `WS /ws/{screen_id}`
- ☐ Admin screen-status updates `WS /ws-screen-status`
- ☐ WebRTC screen-share signaling `WS /ws-webrtc/{room_id}`

## New in rebuild (additive, not regressions)
- Gradient content type that mimics zone lighting (Phase 4)
- Light→zone mapping (Phase 3)
- Brand Profile dropdown — seeded Accenture + IKEA (Phase 5)
- Scene dropdown — per-zone gradient/lighting sets (Phase 6)
- Carousel tab switcher (Phase 1)

## Verification method (per the user: check functionality, not just pixels)
Run `uvicorn main:app --reload`, open `/admin`, and exercise each box against the **real**
endpoint (toggle a light, set screen content, run a test, send a chat message). Deploy to the Pi
(`192.168.2.65`) and confirm against real screens + Hue bridge + the phone vision server before
ticking the box.
