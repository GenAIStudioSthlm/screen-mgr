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


# ---------------------------------------------------------------------
# Microphones — REAL (first non-stub Audio surface).
# Wraps mcps/audio/microphones.py. Shared with the MCP tools.
# ---------------------------------------------------------------------


@router.get("/api/audio/microphones", response_class=JSONResponse)
async def list_microphones():
    from mcps.audio.microphones import discover_microphones
    return {"microphones": discover_microphones()}


@router.get("/api/audio/microphones/{mic_id}/state", response_class=JSONResponse)
async def microphone_state(mic_id: str):
    from mcps.audio.microphones import get_microphone_state
    return get_microphone_state(mic_id)


@router.post("/api/audio/microphones/{mic_id}/mute", response_class=JSONResponse)
async def mute_microphone(mic_id: str, payload: dict = Body(default={})):
    from mcps.audio.microphones import set_microphone_mute
    muted = bool((payload or {}).get("muted", True))
    return set_microphone_mute(mic_id, muted)


@router.post("/api/audio/microphones/{mic_id}/test", response_class=JSONResponse)
async def test_microphone(mic_id: str, payload: dict = Body(default={})):
    """Mic reachability test — N HTTPS handshakes with timings."""
    from mcps.audio.microphones import run_mic_test
    probes = int((payload or {}).get("probes", 3))
    return run_mic_test(mic_id, probes=probes)


# ---------------------------------------------------------------------
# Dante / AES67 stream discovery (real).
# Listens passively to SAP on 239.255.255.255:9875.
# ---------------------------------------------------------------------


@router.get("/api/audio/streams", response_class=JSONResponse)
async def list_audio_streams(timeout: float = 5.0):
    """Discover network audio streams via SAP. `timeout` defaults to
    5s; clamped to [0.5, 30]."""
    from mcps.audio.streams import discover_streams
    t = max(0.5, min(30.0, float(timeout)))
    return {"streams": discover_streams(timeout=t)}
