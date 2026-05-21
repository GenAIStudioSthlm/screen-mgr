# Agentic Structure — Orchestrator + Specialist Subagents + MCP

**Status:** Planning
**Branch:** TBD (suggest `staging/agentic`)
**Created:** 2026-05-21

---

## Vision

Split studio control into three domain-specific MCP servers (Lighting, Screens, LED), each fronted by a Claude **specialist subagent** with its own skills library. A top-level **Studio orchestrator** receives natural-language input from the operator (via chat panel, browser voice, or room mic) and delegates to whichever specialists are needed — including for cross-domain commands like *"show the news on screen 2 and dim the studio lights"*.

The MCP servers are not just for our own agents — they're a stable, documented surface anyone with an MCP client (Claude Code, external scripts, future webhooks) can drive.

**Non-negotiable:** the existing button-driven `/admin` UI keeps working at every phase. The agents are *additional* control, not a replacement.

---

## 1. Architecture (target state)

```
┌──────────────────────────────────────────────────────────────┐
│  USER ENTRY POINTS                                           │
│                                                              │
│  /admin chat panel  │  Browser voice  │  Room mic (Pi)       │
│       │                    │                  │              │
│       └────────────┬───────┴─────────┬────────┘              │
│                    ▼                 ▼                       │
│              POST /api/chat   (SSE stream back)              │
└────────────────────┬─────────────────────────────────────────┘
                     │
              ┌──────▼─────────────────────────┐
              │  Studio Orchestrator           │
              │  (Claude Sonnet 4.6, server)   │
              │                                │
              │  Tools:                        │
              │    delegate_to_lighting(...)   │
              │    delegate_to_screens(...)    │
              │    delegate_to_led(...)        │
              │    ask_user(...)               │
              └─┬────────────┬────────────┬────┘
                │            │            │
       ┌────────▼──┐   ┌─────▼──────┐   ┌─▼──────────┐
       │ Lighting  │   │ Screens    │   │ LED        │
       │ Specialist│   │ Specialist │   │ Specialist │
       │           │   │            │   │            │
       │ + Skills  │   │ + Skills   │   │ + Skills   │
       │ + MCP     │   │ + MCP      │   │ + MCP      │
       └─────┬─────┘   └─────┬──────┘   └─────┬──────┘
             │               │                │
       ┌─────▼──────┐  ┌─────▼──────┐   ┌─────▼──────┐
       │ Lighting   │  │ Screens    │   │ LED        │
       │ MCP server │  │ MCP server │   │ MCP server │
       │ (FastMCP)  │  │ (FastMCP)  │   │ (FastMCP)  │
       └─────┬──────┘  └─────┬──────┘   └─────┬──────┘
             │               │                │
       wraps │         wraps │          wraps │
             ▼               ▼                ▼
       /api/modules/    /api/screens/    /api/modules/
       hue/*            /api/scenes/     rgbdisplay/*
                        /api/screens/
                        reload-all
```

**All four agents and all three MCP servers run in the same uvicorn process on studiopi.** No new systemd units, no new ports for MCP. The only new external dependency is the Anthropic API (egress) for the LLM calls.

---

## 2. Concept mapping

| Concept | What it is in this project |
|---|---|
| **MCP server** | A FastAPI router under `/mcp/<domain>` exposing tools per the Model Context Protocol spec (SSE transport). Each tool wraps existing REST endpoints. |
| **Specialist subagent** | A Python class around an Anthropic SDK call. Receives a focused brief from the orchestrator, has exactly one MCP server attached, plus a skills directory. |
| **Skill** | A markdown file with frontmatter (`name`, `description`, `when_to_use`) and a body of instructions. Loaded into the specialist's system prompt on demand (matches Claude Code skill semantics). |
| **Orchestrator** | A specialist itself, but its tools are `delegate_to_<specialist>` — it doesn't call MCP directly. Owns the user-facing conversation. |
| **Chat session** | A short-lived in-memory list of messages per browser tab. No long-term persistence in v1 — refresh wipes context. |
| **Voice** | Browser-side: Web Speech API → text → `/api/chat`. Room: a small Python daemon on the Pi (USB mic + push-to-talk button) → text → `/api/chat`. Voice never bypasses the chat path. |

---

## 3. Repo layout (target)

```
mcps/                         # new top-level package
  __init__.py
  base.py                    # shared FastMCP plumbing, auth, error mapping
  lighting/
    __init__.py
    server.py                # FastMCP server: tools wrap /api/modules/hue/*
    tools.py                 # tool definitions (list_lights, set_brightness, …)
    skills/
      presentation-mode.md
      blackout.md
      wake-up.md
      …
  screens/
    server.py
    tools.py
    skills/
      show-news-everywhere.md
      apply-scene.md
      …
  led/
    server.py
    tools.py
    skills/
      rainbow.md
      off.md
      …

agents/                      # new top-level package
  __init__.py
  base.py                    # Anthropic client setup, message-loop helper
  skills.py                  # loader: read mcps/<domain>/skills/*.md
  studio_orchestrator.py
  lighting_specialist.py
  screens_specialist.py
  led_specialist.py

routes/
  chat_routes.py             # POST /api/chat (SSE back), GET /api/chat/voice-token
  mcp_routes.py              # mounts MCP servers at /mcp/lighting, /mcp/screens, /mcp/led

scripts/
  voice_daemon.py            # Pi room mic → /api/chat (future phase)

templates/admin/v2/
  views/chat.html            # right-panel chat UI (Alpine)
static/javascript/v2/views/
  chat.js                    # SSE client, voice capture, skill chips

docs/
  AGENTIC.md                 # operator + author guide (lives in docs/ once stable)
```

The existing `modules/` system stays untouched. MCP servers are a parallel exposure layer — they call the same HTTP endpoints (or, where it makes sense, the same Python module APIs directly) without duplicating logic.

---

## 4. MCP tool sketch (per server)

### 4.1 Lighting MCP (`mcps/lighting/`)

| Tool | Wraps | Purpose |
|---|---|---|
| `list_lights` | `GET /api/modules/hue/lights` | Inventory + on/off/brightness/color |
| `list_groups` | `GET /api/modules/hue/groups` | Rooms (Maker, Studio, …) with members |
| `list_scenes` | `GET /api/modules/hue/scenes` | Bridge-defined scenes by name |
| `set_light` | `PUT /api/modules/hue/lights/{id}` | on, brightness (0–100), hex color |
| `set_group` | `PUT /api/modules/hue/groups/{id}` | on, brightness for all lights in a room |
| `recall_scene` | `POST /api/modules/hue/scenes/{id}/recall` | Activate a named scene |
| `all_on` / `all_off` | `POST /api/modules/hue/all/{on,off}` | Master kill / wake |
| `get_bridge_status` | `GET /api/modules/hue/config` | For diagnostics |

### 4.2 Screens MCP (`mcps/screens/`)

| Tool | Wraps | Purpose |
|---|---|---|
| `list_screens` | `GET /api/screens` | Inventory + connection state |
| `set_screen_content` | `POST /api/screens/{id}/set_content` | type + value |
| `reload_screen` | `POST /api/screens/{id}/reload` *(new)* | Force one station to reload |
| `reload_all` | `POST /api/screens/reload-all` | Bounce every connected station |
| `list_scenes` | `GET /api/scenes` | Saved scene presets |
| `apply_scene` | `POST /api/scenes/{id}/apply` | Multi-screen + Hue scene in one call |
| `list_media` | `GET /api/{videos,pictures,pdfs,slideshows}` | What can be shown |
| `list_modules` | filter `GET /api/modules` to display modules | What content types exist right now |

### 4.3 LED MCP (`mcps/led/`)

| Tool | Wraps | Purpose |
|---|---|---|
| `get_status` | `GET /api/modules/rgbdisplay` | Available + active + enabled |
| `start` | `POST /api/modules/rgbdisplay/start` | Bring the matrix up |
| `stop` | `POST /api/modules/rgbdisplay/stop` | Darken the matrix |
| `set_animation` | *(new)* `POST /api/modules/rgbdisplay/animation` | Pick a named pattern (depends on rgbdisplay capabilities — TBD) |

LED is the **smallest** MCP surface today (start/stop is it). If we want richer LED control via the agent, we likely need to extend the `rgbdisplay` module first — out of scope for the first milestone.

---

## 5. Skill format

Skills are markdown with frontmatter. Each skill is a reusable instruction fragment the specialist can pull in. Lifted from Claude Code's skill convention so the format is familiar.

```markdown
---
name: presentation-mode
description: Dim the Studio room lights to a warm, focused presentation level
when_to_use: User asks for "presentation mode", "demo lights", "dim for a meeting", or similar
---

To set up presentation mode:

1. Find the Studio room group via `list_groups`
2. If a scene named "Presentation" exists, recall it via `recall_scene`
3. Otherwise: `set_group` for the Studio group with brightness 30, warm white (#ffd9a8)
4. Confirm with the user briefly: "Studio dimmed to presentation mode."

Do not touch the Maker room or any other zone.
```

The specialist loads all skill descriptions into its system prompt at startup. When a relevant request comes in, it pulls the full skill body via an internal `load_skill(name)` tool call (avoids ballooning system prompt over time).

---

## 6. Conversation protocol (chat backend)

### 6.1 `POST /api/chat`

Body: `{ "messages": [...], "session_id": "browser-tab-uuid" }`
Response: `text/event-stream` (SSE)

Events:
- `event: token` — Claude streaming text
- `event: tool_use` — `{ "tool": "delegate_to_lighting", "input": {...} }` (for UI feedback)
- `event: tool_result` — `{ "tool": "...", "ok": true, "summary": "..." }`
- `event: done` — final state
- `event: error` — `{ "message": "..." }`

The orchestrator runs server-side. Specialist subagents are awaited inside the orchestrator's tool calls — each `delegate_to_*` opens a brief sub-conversation with that specialist, runs its MCP tools, and returns a summary string back to the orchestrator.

### 6.2 Sessions

In-memory dict `{ session_id: [messages] }`, capped at N messages per session. Cleared on server restart. v1 has no cross-tab sharing and no persistence — refresh = new context. Persisting conversations is a Phase B item.

### 6.3 Voice from browser

`chat.js` listens for a push-to-talk key (spacebar) or button. Uses `window.SpeechRecognition` (Webkit) to get final transcripts. Final transcript is sent as a user message into `/api/chat`. No audio ever leaves the browser.

### 6.4 Voice from room (Pi mic)

Future phase. A small Python daemon on the Pi:
- Captures from a USB mic via `sounddevice` or `pyaudio`.
- Push-to-talk via GPIO button OR wake-word via `openWakeWord` (lightweight, offline).
- Streams chunks to a local Whisper instance (`faster-whisper`) → text.
- POSTs the text to `/api/chat` with `session_id: "room-default"` (or per-button-press).

Out of scope for Phase 1 — explicitly called out so we don't over-design the chat backend.

---

## 7. Why in-process FastMCP?

- **One process, one set of logs, one restart.** Matches the current operational story.
- **Zero new network surface.** MCP traffic stays inside uvicorn's request/response cycle; auth is the same as the rest of `/api/*`.
- **Module registry stays the source of truth.** Tools can call Python module methods directly when convenient, not just HTTP endpoints.
- **External MCP clients still work.** Claude Code on a laptop can connect to `http://studiopi:8000/mcp/lighting` over SSE just as easily as if it were a separate process.

Split into per-server processes only if we hit one of these:
- A specific MCP server needs different deploy cadence (unlikely)
- A specific MCP server crashes or hangs the others (mitigate with timeouts first)
- We want different auth/network access per server (future)

---

## 8. Phases

Each phase is a small, deployable increment. Status checkboxes get ticked as we land.

### Phase 1 — Lighting MCP server (in-process) — IN PROGRESS
- [x] Add `mcps` package with `lighting/` directory (skipped `base.py` per YAGNI — pull it out when the second server lands)
- [x] `mcps/lighting/server.py` — FastMCP server exposing 9 tools (list_lights / list_groups / list_scenes / get_bridge_status / set_light / set_group / recall_scene / all_on / all_off)
- [x] Mounted on the existing FastAPI app in `main.py` at `/mcp/lighting` (skipped a separate `routes/mcp_routes.py` — MCP servers are ASGI apps, not FastAPI routers; mounting belongs next to other `app.mount` calls)
- [x] Add `mcp>=1.2.0` to `requirements.txt` (anthropic dep deferred to Phase 2 when the agent lands)
- [ ] Smoke test from `curl`: `curl -N http://studiopi:8000/mcp/lighting/sse` returns SSE stream
- [x] Document the new dependency + endpoint in `docs/DEPLOY.md`

### Phase 2 — Lighting specialist subagent
- [ ] `agents/base.py` — Anthropic client, message-loop helper, tool-result formatter
- [ ] `agents/skills.py` — markdown skill loader (parse frontmatter, list/load by name)
- [ ] `agents/lighting_specialist.py` — wraps the lighting MCP server, with skills dir
- [ ] Seed `mcps/lighting/skills/` with 3 skills: `presentation-mode`, `blackout`, `wake-up`
- [ ] Add `.env` support (Anthropic API key) — gitignored, document setup in DEPLOY.md
- [ ] Standalone CLI smoke test: `python -m agents.lighting_specialist "dim the studio"` → it dims

### Phase 3 — Studio orchestrator (Lighting-only first)
- [ ] `agents/studio_orchestrator.py` — Claude Sonnet, tools: `delegate_to_lighting`, `ask_user`
- [ ] When a user message arrives, orchestrator decides if it's lighting-related; delegates if so
- [ ] CLI smoke test: `python -m agents.studio_orchestrator "warm up the studio for a meeting"`

### Phase 4 — Chat panel in `/admin` right pane
- [ ] `routes/chat_routes.py` — `POST /api/chat` with SSE response
- [ ] `templates/admin/v2/views/chat.html` + `static/javascript/v2/views/chat.js`
- [ ] Right panel switches from "Reserved for chat agent" to the actual chat
- [ ] Visual chips for tool use ("delegating to Lighting…" → ✓ summary)
- [ ] Wire to existing `studioShell` view-toggle (chat is always visible in the right panel, not a view)

### Phase 5 — Browser voice (push-to-talk)
- [ ] `chat.js` listens for spacebar (configurable) → Web Speech API
- [ ] Live transcript shown in chat input; final transcript sent on key-up
- [ ] Fallback message if browser lacks SpeechRecognition
- [ ] Mic permission UX: clear ask on first push-to-talk

### Phase 6 — Screens MCP + specialist (copy-paste pattern)
- [ ] Repeat Phase 1+2 for Screens (tools per §4.2, skills for common patterns)
- [ ] Orchestrator gains `delegate_to_screens` tool

### Phase 7 — LED MCP + specialist (smallest)
- [ ] Repeat for LED. Likely also extends the `rgbdisplay` module to expose more than start/stop.

### Phase 8 — Room voice (Pi mic, push-to-talk)
- [ ] `scripts/voice_daemon.py` — sounddevice + GPIO + faster-whisper
- [ ] systemd unit on the Pi (mirror the rgbdisplay unit pattern)
- [ ] Posts to `/api/chat` with `session_id: "room"` and a clear visual indicator in the chat panel that "room voice spoke"

### Phase 9 — Polish + docs
- [ ] `docs/AGENTIC.md` — operator + author guide (how to add a new skill, how to add a new MCP tool, how to extend an MCP server)
- [ ] Conversation persistence (Phase B optional)
- [ ] Wake-word in room voice (Phase B optional)

---

## 9. Tech choices

| Choice | Pick | Reason |
|---|---|---|
| MCP Python library | `mcp` (official, SSE transport) | First-party, FastMCP helpers, SSE matches our uvicorn world |
| LLM model — orchestrator | `claude-sonnet-4-6` | Fast, capable enough for routing |
| LLM model — specialists | `claude-sonnet-4-6` | Same; reconsider per specialist if one needs deeper reasoning |
| Voice (browser) | `window.SpeechRecognition` (Web Speech API) | No backend dep, works in Chrome/Edge — our station browsers |
| Voice (room) | `faster-whisper` + push-to-talk | Local, no audio leaves LAN |
| Wake-word (optional) | `openWakeWord` | Lightweight, offline |
| Secrets | `.env` on the Pi, `python-dotenv` | Matches existing no-secrets-in-git rule |
| Streaming | SSE (server-side events) | Already in our toolkit (`/updating` page uses it conceptually) |

---

## 10. Risks + open questions

### 10.1 Risks

| Risk | Mitigation |
|---|---|
| Anthropic API egress cost | Orchestrator + specialist = 2+ round trips per user msg. Cap context length, use Sonnet (not Opus), monitor monthly. |
| Latency from Pi → Anthropic | SSE streaming makes it feel fast even at 800ms TTFB. Show "thinking…" chip. |
| Orchestrator hallucinating delegations | Tight tool descriptions, explicit "if unsure ask the user" instruction, no `delegate_to_unknown` tool. |
| Skill drift vs MCP tool changes | Skills reference tool names by string. Add a smoke test that loads each skill and asserts every named tool exists in the MCP server. |
| `.env` accidentally committed | Already gitignored; add a pre-commit check (or rely on the no-secrets memory). |
| Voice false triggers (wake-word) | Phase 8+ concern — start with push-to-talk only. |
| MCP servers crashing each other (in-process) | Set per-tool timeouts. If we see real crashes, split into processes. |
| Chat session state lost on uvicorn reload | Acceptable for v1 — sessions are short. Phase B: persist to `data/chat_sessions.json`. |

### 10.2 Open questions (revisit after Phase 1)

- **Skill format:** markdown-with-frontmatter is the bet — easy to author, version-controllable, IDE-friendly. Alternative is YAML or pure Python. Reassess once we have 5+ real skills.
- **Tool granularity:** is `set_light(id, on=True, brightness=70, color="#ffd9a8")` better, or three separate tools? Bet on the bundled form for fewer round trips, reconsider if the model misuses it.
- **Conversation persistence:** keep in-memory for v1. Decide on persistence after we know how operators actually use it.
- **Per-room session isolation:** one `session_id: "room"` per push-to-talk vs continuous? Pick after Phase 4 chat panel is live.
- **External MCP exposure beyond LAN:** for now, MCP is LAN-only. If someone wants Slack-driven control, that's a separate auth conversation.

---

## 11. What this replaces / doesn't

| Today | After |
|---|---|
| Apply Scene button in /admin | Still works. Agent can also do it. |
| Lights tab toggles + sliders | Still works. Agent can also do it. |
| Modules tab Start/Stop | Still works. LED agent can also do it. |
| `/api/*` REST API | Untouched. MCP wraps it. |
| `modules/` registry | Untouched. Source of truth. |
| `screens.json` / `data/scenes.json` / `data/hue.json` | Untouched. |

**Nothing existing breaks.** The agent layer is purely additive.

---

## 12. First-milestone definition of done

The first milestone is Phase 1 + 2 + 3 + 4 + 5 (Lighting end-to-end with chat panel and browser voice).

Done means:
1. I can open `/admin`, see a chat panel in the right column.
2. I can type *"warm up the studio for a meeting"* — orchestrator decides this is lighting, delegates to the Lighting specialist, which recalls the "Presentation" scene (or sets group brightness if no such scene exists) and reports back.
3. I can hold spacebar and say the same thing — transcript appears, request executes.
4. The Modules / Lights / Screens admin UI still works exactly as it did before.
5. `.env` with `ANTHROPIC_API_KEY=...` is set on the Pi (and only on the Pi).
6. `docs/AGENTIC.md` exists with a "how to add a skill" recipe.

Phases 6–9 follow once this shape is approved by use.
