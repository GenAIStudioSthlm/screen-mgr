"""HTTP endpoints for the Audio view in /admin.

Currently a thin pass-through to the (stubbed) Audio MCP tools — every
call returns `{"stub": true, ...}` until a real backend (PulseAudio
via `pactl`) is wired. The view uses these endpoints so the swap to
real responses doesn't require touching the frontend.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse


router = APIRouter()


# All current handlers delegate to the same stub note. Replace each
# stub with a real `pactl` invocation when implementing for real.
_STUB_NOTE = (
    "Audio MCP is a stub. Wire to PulseAudio / pactl to implement. "
    "See mcps/audio/server.py — tool signatures are stable."
)


def _stub(name: str, **extras) -> dict:
    return {"stub": True, "endpoint": name, "note": _STUB_NOTE, **extras}


@router.get("/api/audio/sinks", response_class=JSONResponse)
async def list_sinks():
    return _stub("/api/audio/sinks", sinks=[])


@router.get("/api/audio/sources", response_class=JSONResponse)
async def list_sources():
    return _stub("/api/audio/sources", sources=[])


@router.get("/api/audio/volume", response_class=JSONResponse)
async def get_volume(sink_id: Optional[str] = None):
    return _stub("/api/audio/volume", sink_id=sink_id, volume_pct=None)


@router.post("/api/audio/volume", response_class=JSONResponse)
async def set_volume(payload: dict = Body(default={})):
    return _stub(
        "/api/audio/volume",
        sink_id=(payload or {}).get("sink_id"),
        volume_pct=(payload or {}).get("volume_pct"),
    )


@router.post("/api/audio/play_sound", response_class=JSONResponse)
async def play_sound(payload: dict = Body(default={})):
    return _stub(
        "/api/audio/play_sound",
        file_path=(payload or {}).get("file_path"),
        sink_id=(payload or {}).get("sink_id"),
    )
