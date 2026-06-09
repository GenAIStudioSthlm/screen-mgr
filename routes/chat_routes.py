"""POST /api/chat — orchestrator chat endpoint.

SSE-streamed. Matches the contract from `TASKS/PLAN_AGENTIC.md` §6.1:

  event: token        Claude streaming text
  event: tool_use     An MCP tool call started
  event: tool_result  …finished, with a short summary
  event: error        Something failed
  event: done         Stream complete

Implementation: we shell out to the Claude Code CLI (`claude -p`) in
headless mode, authenticated by the operator's **subscription** via
`CLAUDE_CODE_OAUTH_TOKEN` (NOT a metered API key — we deliberately strip
`ANTHROPIC_API_KEY` from the subprocess env so it can't take precedence).
Claude talks to our in-process MCP servers (lighting / screens / displays
/ audio / music) over SSE at localhost:8000, so a typed/voiced request
like "warm up the lights for a meeting" turns straight into MCP tool
calls. The browser handles voice via the Web Speech API and feeds the
transcript through this same endpoint.

The CLI emits newline-delimited JSON (`--output-format stream-json`); we
translate each line into the SSE events the frontend already speaks.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse


router = APIRouter()


# --- Studio system prompt -------------------------------------------------
# Claude Code has DIRECT access to the MCP tools (mcp__<domain>__<tool>),
# so unlike the old in-process orchestrator there's no delegate_to_*
# indirection — it calls the domain tools itself. Keep replies terse:
# this is an operator console, not a chatbot.
_SYSTEM_PROMPT = (
    "You are the Studio control assistant for a live demo studio. The "
    "operator talks to you by text or voice from the admin panel. You "
    "control the room through MCP tools, grouped by domain:\n"
    "- lighting (Philips Hue): brightness, color, rooms, scenes, "
    "presentation/blackout/wake-up.\n"
    "- screens: the display fleet and what content they show.\n"
    "- displays: the LED panels and their test patterns.\n"
    "- audio: microphones and sinks.\n"
    "- music: Spotify / Marantz playback and the speaker test.\n\n"
    "Use the tools to actually carry out requests — don't just describe "
    "what you would do. If a request is ambiguous (which room? how "
    "bright?), ask ONE short clarifying question instead of guessing. "
    "For greetings or 'what can you do', answer briefly in plain text "
    "without calling a tool. Keep every reply to one or two short "
    "sentences — the operator is mid-demo."
)

# The five in-process MCP servers, reachable on localhost while the app
# runs. SSE transport — matches `main.py`'s `*.sse_app()` mounts.
_MCP_DOMAINS = ["lighting", "screens", "displays", "audio", "music"]
_ALLOWED_TOOLS = ",".join(f"mcp__{d}" for d in _MCP_DOMAINS)
# Belt-and-suspenders: explicitly forbid the built-in tools so the chat
# agent can never read/write the Pi's filesystem or run shell commands.
_DISALLOWED_TOOLS = (
    "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit"
)

# Hard ceiling so a misbehaving turn can't hang the SSE stream forever.
_TURN_TIMEOUT_S = 90.0
_MAX_TURNS = "12"


def _claude_bin() -> str:
    """Resolve the claude binary. The systemd service may not have
    ~/.local/bin on PATH, so fall back to the known native-install path."""
    override = os.environ.get("CLAUDE_BIN")
    if override:
        return override
    found = shutil.which("claude")
    if found:
        return found
    return os.path.expanduser("~/.local/bin/claude")


def _mcp_config_path() -> str:
    """Write (once) an --mcp-config pointing at our SSE MCP mounts and
    return its path. Lives in a dedicated work dir so the claude process
    has a neutral cwd (not the repo) for its session scratch files."""
    workdir = Path(tempfile.gettempdir()) / "studio-chat"
    workdir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "mcpServers": {
            d: {
                "type": "sse",
                "url": f"http://localhost:8000/mcp/{d}/sse",
            }
            for d in _MCP_DOMAINS
        }
    }
    path = workdir / "mcp.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


def _subprocess_env() -> dict:
    """Copy the env, force subscription auth: keep CLAUDE_CODE_OAUTH_TOKEN,
    strip ANTHROPIC_API_KEY (it would otherwise take precedence and bill
    the metered API). Ensure HOME/PATH are sane for a non-login service."""
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.setdefault("HOME", os.path.expanduser("~"))
    local_bin = os.path.expanduser("~/.local/bin")
    if local_bin not in env.get("PATH", ""):
        env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")
    return env


def _build_prompt(messages: list) -> str:
    """Flatten the chat history into a single prompt. v1 is stateless per
    turn (no --resume): we replay the conversation so follow-ups like
    "make it brighter" keep their context. Short studio chats make this
    cheap."""
    msgs = [m for m in messages if m.get("role") in ("user", "assistant")]
    if not msgs:
        return ""
    if len(msgs) == 1:
        return str(msgs[0].get("content", "")).strip()
    *history, last = msgs
    lines = ["Conversation so far:"]
    for m in history:
        who = "Operator" if m.get("role") == "user" else "Assistant"
        lines.append(f"{who}: {str(m.get('content', '')).strip()}")
    lines.append("")
    lines.append(f"Current operator request: {str(last.get('content', '')).strip()}")
    return "\n".join(lines)


def _short_tool(name: str) -> str:
    """`mcp__lighting__set_zone` → `lighting:set_zone` for display."""
    if name.startswith("mcp__"):
        return name[len("mcp__"):].replace("__", ":", 1)
    return name


def _summarize_tool_result(content) -> tuple[str, bool]:
    """Pull a short text summary + error flag out of a tool_result block's
    content (which is a string or a list of {type:text,text} parts)."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                parts.append(c.get("text") or json.dumps(c))
            else:
                parts.append(str(c))
        text = "\n".join(parts)
    else:
        text = str(content)
    text = text.strip()
    if len(text) > 240:
        text = text[:237] + "…"
    return text or "(ok)", False


def _sse(event: str, data: dict | None = None) -> str:
    """Format a single SSE event. data must serialise as JSON."""
    payload = json.dumps(data or {})
    return f"event: {event}\ndata: {payload}\n\n"


async def _stream(messages: list, session_id: str) -> AsyncIterator[str]:
    """Run `claude -p` and translate its stream-json output into SSE.

    We track tool_use ids → names so a later tool_result can be labelled,
    and emit text/tool events in the order Claude produces them."""
    prompt = _build_prompt(messages)
    if not prompt:
        yield _sse("error", {"message": "empty message", "session_id": session_id})
        yield _sse("done", {"session_id": session_id})
        return

    args = [
        _claude_bin(),
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",  # required by the CLI when output-format is stream-json
        "--mcp-config", _mcp_config_path(),
        "--allowedTools", _ALLOWED_TOOLS,
        "--disallowedTools", _DISALLOWED_TOOLS,
        "--append-system-prompt", _SYSTEM_PROMPT,
        "--max-turns", _MAX_TURNS,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_subprocess_env(),
            cwd=str(Path(tempfile.gettempdir()) / "studio-chat"),
            limit=2 ** 20,  # tool results can exceed the default 64KB line cap
        )
    except FileNotFoundError:
        yield _sse(
            "error",
            {
                "message": (
                    "claude CLI not found on the server "
                    f"(looked for {_claude_bin()!r})."
                ),
                "session_id": session_id,
            },
        )
        yield _sse("done", {"session_id": session_id})
        return

    tool_names: dict[str, str] = {}  # tool_use_id → short name
    deadline = asyncio.get_event_loop().time() + _TURN_TIMEOUT_S
    saw_result = False

    try:
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                raise
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip non-JSON noise

            kind = obj.get("type")

            if kind == "assistant":
                for block in obj.get("message", {}).get("content", []):
                    btype = block.get("type")
                    if btype == "text":
                        text = block.get("text", "")
                        if text:
                            yield _sse("token", {"text": text})
                    elif btype == "tool_use":
                        short = _short_tool(block.get("name", "?"))
                        tool_names[block.get("id", "")] = short
                        yield _sse(
                            "tool_use",
                            {"tool": short, "input": block.get("input", {})},
                        )

            elif kind == "user":
                # Tool results come back as a user message of tool_result blocks.
                for block in obj.get("message", {}).get("content", []):
                    if block.get("type") != "tool_result":
                        continue
                    name = tool_names.get(block.get("tool_use_id", ""), "tool")
                    summary, _ = _summarize_tool_result(block.get("content"))
                    yield _sse(
                        "tool_result",
                        {
                            "tool": name,
                            "summary": summary,
                            "is_error": bool(block.get("is_error")),
                        },
                    )

            elif kind == "result":
                saw_result = True
                if obj.get("is_error") or obj.get("subtype") not in (None, "success"):
                    yield _sse(
                        "error",
                        {
                            "message": obj.get("result")
                            or f"claude ended with {obj.get('subtype')}",
                            "session_id": session_id,
                        },
                    )

        await proc.wait()
        if not saw_result and proc.returncode not in (0, None):
            err = (await proc.stderr.read()).decode("utf-8", errors="replace")
            yield _sse(
                "error",
                {
                    "message": f"claude exited {proc.returncode}: {err[:300]}",
                    "session_id": session_id,
                },
            )

    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        yield _sse(
            "error",
            {
                "message": f"timed out after {int(_TURN_TIMEOUT_S)}s",
                "session_id": session_id,
            },
        )
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        yield _sse("done", {"session_id": session_id})


@router.post("/api/chat")
async def chat(payload: dict = Body(...)):
    """Stream chat events to the browser.

    Body: ``{"messages": [{role, content}, ...], "session_id": "..."}``.
    """
    messages = payload.get("messages") or []
    session_id = (payload.get("session_id") or "default").strip()
    return StreamingResponse(
        _stream(messages, session_id),
        media_type="text/event-stream",
        # Disable buffering at any reverse proxy in front of us.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
