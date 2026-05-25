# External Integration

How another service, agent, or human-on-a-laptop talks to **screen-mgr's
control surface** from outside the admin UI. This document is the
canonical answer when someone asks _"can we drive the studio from
{Slack bot / colleague's Claude Code / robot dashboard / cron job /
external orchestrator}?"_

## TL;DR — three surfaces, pick the one that fits

| Surface | URL | Wire format | When to use |
|---|---|---|---|
| **MCP servers** | `http://studiopi:8000/mcp/<domain>/sse` | Model Context Protocol over SSE — tool calls return JSON | Anything programmatic. Strongly typed tool list. Same API our own agents use. |
| **HTTP REST** | `http://studiopi:8000/api/*` | Plain JSON over HTTP | Quick scripts, dashboards, anything that already speaks REST. Same endpoints the admin UI uses. |
| **Agent chat** | `POST http://studiopi:8000/api/chat` (SSE back) | Natural-language messages → orchestrator + specialists | Conversational integrations — Slack bots, voice assistants, etc. **Blocked on Anthropic API key today**; surface + event shapes are stable. |

All three are **LAN-only** today (no public exposure, no auth tokens —
trust is "you're on the ComHem network"). Anything beyond the LAN needs
a reverse proxy + auth bolted on.

## The five MCP servers

Each one is in-process inside the screen-mgr uvicorn process, mounted at
its own path. They wrap the existing Python managers directly — no HTTP
roundtrip — and are usable by any MCP client (Claude Code, the official
[`mcp` Python SDK](https://pypi.org/project/mcp/), an external agent's
LLM, etc).

| Domain | Mount point | Tool count | What it controls |
|---|---|---|---|
| Lighting | `/mcp/lighting/sse` | 10 | Philips Hue bridge — lights, groups, scenes, all-on/off, startup test |
| Screens | `/mcp/screens/sse` | 10 | Display stations — set content, reload, apply scenes, fleet demo |
| Displays | `/mcp/displays/sse` | 7 | LED matrix — start/stop, status, grid test pattern |
| Audio | `/mcp/audio/sse` | 14 | PulseAudio sinks/sources/volume + Sennheiser mic discovery + Dante SAP listener |
| Music | `/mcp/music/sse` | 11 | Spotify Web API (transport, search, presets) — needs Path B OAuth |

For a complete tool table per server, see [`README.md`](../README.md)
or just call `list_tools()` on the MCP session (see the example below).

## Calling an MCP server from an external service

### Python — official `mcp` SDK

```python
import asyncio
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

async def turn_studio_lights_on():
    async with sse_client("http://studiopi:8000/mcp/lighting/sse") as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("available:", [t.name for t in tools.tools])

            # Tools take JSON-typed inputs; their schemas come from the
            # FastMCP `@server.tool()` decorator + Python type hints.
            result = await session.call_tool(
                "set_group",
                {"group_id": "81", "brightness_pct": 80, "kelvin": 3000},
            )
            print(result.content[0].text)

asyncio.run(turn_studio_lights_on())
```

### Anything else (raw SSE)

The MCP SSE transport is the standard MCP over Server-Sent Events. Any
language can implement it — the spec lives at
<https://modelcontextprotocol.io>. The fact that we use FastMCP on the
server side is an implementation detail; the wire protocol is the spec.

### Claude Code on a colleague's laptop

If a colleague has Claude Code installed and is on the ComHem LAN, they
can add our MCP servers via their MCP config:

```json
// ~/.config/claude/mcp.json (path varies; see Claude Code docs)
{
  "mcpServers": {
    "studio-lighting": {
      "url": "http://studiopi:8000/mcp/lighting/sse"
    },
    "studio-screens": {
      "url": "http://studiopi:8000/mcp/screens/sse"
    },
    "studio-audio": {
      "url": "http://studiopi:8000/mcp/audio/sse"
    }
  }
}
```

After restart, that colleague's Claude Code can call any of our tools.
This is the **cleanest path for ad-hoc external agent integration today**.

## The chat / orchestrator path

`POST /api/chat` is the natural-language door. Body shape:

```json
{
  "messages": [{"role": "user", "content": "set the studio to presentation mode"}],
  "session_id": "<your-uuid>"
}
```

Response is `text/event-stream`. Events:

| Event | Meaning |
|---|---|
| `token` | Streaming text token from the orchestrator's reply |
| `tool_use` | The orchestrator delegated to a specialist (e.g. `delegate_to_lighting`) |
| `tool_result` | A specialist completed and returned a summary |
| `error` | Something failed (auth, tool dispatch, model error) |
| `done` | Stream complete |

**Today the endpoint is a stub** — it always emits one `error` event
saying the orchestrator isn't wired (waiting on
`ANTHROPIC_API_KEY` in `/home/admin/screen-mgr/.env`). The shape and
SSE event names are stable, so external chat integrations can be built
against the final contract today and start working the moment the key
lands. See [`TASKS/PLAN_AGENTIC.md`](../TASKS/PLAN_AGENTIC.md) Phase 4.

### Worked example — external Slack bot

```python
import requests, json
def ask_studio(message: str, session_id: str):
    with requests.post(
        "http://studiopi:8000/api/chat",
        json={"session_id": session_id, "messages": [{"role": "user", "content": message}]},
        stream=True,
    ) as resp:
        event = None
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                event = None
                continue
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
                yield (event, data)
```

## HTTP REST surface

The same endpoints `/admin` uses are open to any LAN client. Useful when
you don't want the MCP / SSE complexity. Highlights:

| Method + path | What |
|---|---|
| `GET /api/screens` | All 8 stations with state |
| `POST /api/screens/{id}/set_content` | Set type + value for one screen |
| `POST /api/screens/reload-all` | Reload every connected screen |
| `GET /api/scenes`, `POST /api/scenes/{id}/apply` | Scene listing + apply |
| `GET /api/modules/hue/lights`, `PUT .../{id}` | Hue control (legacy v1 surface) |
| `POST /api/modules/hue/run_startup_test` | Run the lighting startup test |
| `POST /api/screens/run_fleet_demo` | Run the fleet demo |
| `GET/POST /api/audio/{sinks,sources,volume,mute}` | PulseAudio control |
| `GET /api/audio/microphones`, `/{id}/state`, `/{id}/test`, `/{id}/identify` | Mic discovery + control |
| `GET /api/audio/streams?timeout=5` | SAP listener for Dante / AES67 streams |
| `GET /api/music/{status,presets,now_playing,devices}` + `POST /api/music/{play,pause,...}` | Music transport (needs Spotify config) |
| `POST /api/modules/external` | **Register a third-party content module by manifest URL** |

Every JSON payload returned is the same shape MCP tools return — both
paths share the underlying Python.

## External content modules (third-party display content)

The module registry accepts external manifest URLs. A third party can
host a JSON manifest and POST its URL to `/api/modules/external`; the
manifest describes a new content type or service. Once registered, the
admin Screens dropdown gains that content type and screens can show
its URL pattern. See [`docs/MODULES.md`](MODULES.md) — section _"The
external-manifest spec"_.

This is the right path when an external service wants screens to
**display** its content (a robot dashboard, a sensor readout, a
business KPI page). For **controlling** lights / mics / screens
from outside, use MCP or REST above.

## Acoustic-safety constraints (mandatory)

The studio has a ceiling mic above high-output speakers. Any external
service that writes audio volume or triggers playback **must respect
the safety ceiling** — see [`docs/SAFETY.md`](SAFETY.md) for the full
design. Practical impact for you:

- Every `set_volume` request (PulseAudio, Spotify) is clamped to
  `MAX_OUTPUT_VOLUME_PCT` (default 70). The response includes
  `"capped": true` + `"ceiling_pct"` when your request was clipped —
  surface that to your operator, don't silently retry at a higher value.
- Don't wire the TCC mic into a closed loop with the speakers (room
  voice → orchestrator → TTS / music → speakers) until SAFETY.md's
  Rule 2 (mute-mic-during-playback) is enforceable. That needs
  `SENNHEISER_TCC_PASSWORD` set on the Pi.

## Trust + security model

screen-mgr was built for a single trusted LAN (ComHem in the studio).
The current posture:

- **No authentication** on `/api/*`, `/mcp/<domain>/sse`, or `/api/chat`.
  Anyone on the LAN can call anything.
- **DNS-rebinding protection disabled** on MCP servers (otherwise the
  MCP library 'd block any non-localhost connection). Re-enable + pin
  `allowed_hosts` in `mcps/*/server.py` if the deployment changes.
- **Self-signed TLS** on devices like the TCC mic (we use `verify=False`).
- **Secrets in `/home/admin/screen-mgr/.env`** (gitignored): currently
  `ANTHROPIC_API_KEY`, optionally `SPOTIFY_*` + `SENNHEISER_TCC_PASSWORD`.

**If you need to expose any of this beyond the LAN**, the realistic
path is a reverse proxy (Caddy or nginx) doing TLS + bearer-token auth
in front of `:8000`. That's not built today; mention it explicitly in
any external-integration ticket so we add it before going live.

## Quick recipes — common asks

**"Can the agent on my laptop control your studio's lights?"**
→ Add `http://studiopi:8000/mcp/lighting/sse` to your MCP client. Done.
You're on the same LAN, you get the tools.

**"We want our internal status page to dim the studio for a meeting."**
→ `POST /api/modules/hue/groups/81 {"on": true, "bri": 100, "ct": 333}`
from the page. Or use the MCP `set_group` tool if you're already
speaking MCP.

**"We have an external agent that should answer voice questions about
the studio's state."** → Today: have it call our MCP servers' `list_*`
tools directly (no agent layer needed on our side). Future:
`POST /api/chat` once our `.env` key is set.

**"We have a screen worth of content to show — a dashboard our team
built."** → Host a manifest somewhere reachable from studiopi, POST the
URL to `/api/modules/external`. The Screens dropdown gains your content
type. See [`docs/MODULES.md`](MODULES.md) external-manifest spec.

## Open / planned

- **`/api/chat` real backend** — pending `.env` API key. Until then,
  natural-language integration paths fall back to "use MCP directly".
- **External auth** — no bearer tokens / OAuth client. If we ever need
  this, a small `routes/auth_routes.py` issuing per-client API keys is
  the minimal lift.
- **Webhook surface** — currently none. If external services need
  push-style notifications ("a screen disconnected", "a scene was
  applied"), a `POST /api/webhooks/register` would be the natural fit.

## See also

- [`README.md`](../README.md) — front door + per-MCP tool tables
- [`docs/MODULES.md`](MODULES.md) — module registry + external-manifest spec
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — runtime topology
- [`TASKS/PLAN_AGENTIC.md`](../TASKS/PLAN_AGENTIC.md) — agent + MCP plan, phase tracker, current blockers
