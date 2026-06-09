"""POST /api/chat — orchestrator chat endpoint.

SSE-streamed. Matches the contract from `TASKS/PLAN_AGENTIC.md` §6.1:

  event: token        Claude streaming text                (real impl)
  event: tool_use     A delegate_to_* call started         (real impl)
  event: tool_result  …finished, with a summary            (real impl)
  event: error        Something failed
  event: done         Stream complete

For now the endpoint is a STUB — it emits a single `error` event saying
the orchestrator isn't wired up yet (waiting on the .env API key on the
Pi, see PLAN_AGENTIC.md Phase 2/3) and then `done`. The route + the SSE
event shape are real, so the frontend JS can be written against the
final contract today.

When the orchestrator lands, swap the body of `_stream` for the real
Anthropic + delegate-to-specialist loop, keeping the same event names.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse


router = APIRouter()


# Single message that the frontend renders verbatim until we wire the
# real orchestrator. Keep it actionable — a developer reading the chat
# error should know exactly what to do next.
_NOT_IMPLEMENTED_MESSAGE = (
    "Chat orchestrator is not wired up yet. The /api/chat endpoint and "
    "the chat UI exist; the agent backend (Studio orchestrator + "
    "Lighting specialist) is code-complete but blocked on a real "
    "ANTHROPIC_API_KEY in /home/admin/screen-mgr/.env. See "
    "TASKS/PLAN_AGENTIC.md Phases 2-4 for the wiring."
)


def _sse(event: str, data: dict | None = None) -> str:
    """Format a single SSE event. data must serialise as JSON."""
    payload = json.dumps(data or {})
    return f"event: {event}\ndata: {payload}\n\n"


async def _stream(messages: list, session_id: str) -> AsyncIterator[str]:
    """The fake orchestrator loop. Real implementation will swap this
    for an Anthropic call streaming back tokens + tool events."""
    # Tiny delay so the UI gets to render the "thinking…" chip; otherwise
    # the error lands before the spinner ever appears.
    await asyncio.sleep(0.15)
    yield _sse(
        "error",
        {
            "message": _NOT_IMPLEMENTED_MESSAGE,
            "session_id": session_id,
            "echo": messages[-1] if messages else None,
        },
    )
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
