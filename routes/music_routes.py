"""HTTP endpoints for the Music view in /admin.

Mirror the Music MCP tools — same `spotify_client.call(...)` wrapper —
but reachable from the browser without an SSE round-trip. Each endpoint
returns the same `{"ok": true, "data": ...}` / `{"error": "..."}` shape
the MCP tools do, so the frontend can render both branches uniformly.

Until Spotify is configured (env vars in .env), every endpoint returns
the friendly "spotify not configured" error — that's the UI's signal
to show the "configure Spotify" panel instead of player controls.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from mcps.music.spotify_client import call


router = APIRouter()


@router.get("/api/music/status", response_class=JSONResponse)
async def music_status():
    """Lightweight health check — does the spotify client wake up?
    Returns ``{"configured": bool, ...}`` so the UI can pick player
    vs. setup-instructions without firing a real Spotify call."""
    # Probe by trying to fetch devices — that's the cheapest call that
    # requires real auth. If it returns "not configured", we know we're
    # in stub mode.
    resp = call(lambda c: c.devices())
    return {
        "configured": "error" not in resp or resp.get("error") != "spotify not configured",
        "probe": resp,
    }


@router.get("/api/music/now_playing", response_class=JSONResponse)
async def now_playing():
    return call(lambda c: c.current_playback())


@router.get("/api/music/devices", response_class=JSONResponse)
async def devices():
    return call(lambda c: c.devices())


@router.get("/api/music/search", response_class=JSONResponse)
async def search(q: str, search_type: str = "track", limit: int = 5):
    limit = max(1, min(20, int(limit)))
    return call(lambda c: c.search(q=q, type=search_type, limit=limit))


@router.post("/api/music/play", response_class=JSONResponse)
async def play(payload: dict = Body(default={})):
    uri: Optional[str] = (payload or {}).get("uri")
    device_id: Optional[str] = (payload or {}).get("device_id")

    def _do(c):
        kwargs: dict = {}
        if device_id:
            kwargs["device_id"] = device_id
        if uri:
            if uri.startswith("spotify:track:"):
                kwargs["uris"] = [uri]
            else:
                kwargs["context_uri"] = uri
        c.start_playback(**kwargs)
        return {"started": True, "uri": uri, "device_id": device_id}

    return call(_do)


@router.post("/api/music/pause", response_class=JSONResponse)
async def pause(payload: dict = Body(default={})):
    device_id = (payload or {}).get("device_id")
    return call(lambda c: (c.pause_playback(device_id=device_id), {"paused": True})[1])


@router.post("/api/music/next", response_class=JSONResponse)
async def next_track(payload: dict = Body(default={})):
    device_id = (payload or {}).get("device_id")
    return call(lambda c: (c.next_track(device_id=device_id), {"skipped": "next"})[1])


@router.post("/api/music/previous", response_class=JSONResponse)
async def previous_track(payload: dict = Body(default={})):
    device_id = (payload or {}).get("device_id")
    return call(lambda c: (c.previous_track(device_id=device_id), {"skipped": "previous"})[1])


@router.post("/api/music/volume", response_class=JSONResponse)
async def set_volume(payload: dict = Body(default={})):
    vol = max(0, min(100, int((payload or {}).get("volume_pct", 50))))
    device_id = (payload or {}).get("device_id")
    return call(lambda c: (c.volume(vol, device_id=device_id), {"volume_pct": vol})[1])


@router.post("/api/music/speaker_test", response_class=JSONResponse)
async def speaker_test(payload: dict = Body(default={})):
    """Run the Music speaker test — same logic the MCP tool exposes."""
    from mcps.music.speaker_test import (
        DEFAULT_DEVICE_QUERY,
        DEFAULT_PLAY_SECONDS,
        DEFAULT_TRACK_QUERY,
        DEFAULT_VOLUME_PCT,
        run_speaker_test,
    )
    return await run_speaker_test(
        device_query=(payload or {}).get("device_query", DEFAULT_DEVICE_QUERY),
        volume_pct=(payload or {}).get("volume_pct", DEFAULT_VOLUME_PCT),
        track_query=(payload or {}).get("track_query", DEFAULT_TRACK_QUERY),
        play_seconds=(payload or {}).get("play_seconds", DEFAULT_PLAY_SECONDS),
    )


# ----------------------------------------------------------------------
# Music presets — one-click "play a mood" buttons.
# ----------------------------------------------------------------------


@router.get("/api/music/presets", response_class=JSONResponse)
async def list_music_presets():
    from mcps.music.presets import preset_manager
    return {"presets": [p.model_dump() for p in preset_manager.presets]}


@router.post("/api/music/presets/{preset_id}/play", response_class=JSONResponse)
async def play_music_preset(preset_id: str, payload: dict = Body(default={})):
    from mcps.music.presets import play_preset
    return await play_preset(
        preset_id=preset_id,
        device_query_override=(payload or {}).get("device_query"),
        volume_pct_override=(payload or {}).get("volume_pct"),
    )


# ----------------------------------------------------------------------
# Marantz — local-file playback via HEOS
# ----------------------------------------------------------------------


@router.get("/api/music/marantz/calibration", response_class=JSONResponse)
async def marantz_calibration():
    """Volume calibration table — surface to operators / UI so they
    know what numbers mean on this AVR."""
    from mcps.audio.safety import (
        SEMANTIC_VOLUMES, VOLUME_CALIBRATION, max_output_volume_pct,
    )
    return {
        "scale": "HEOS 0-100 (≈ dB attenuation on AVR master, NOT loudness %)",
        "calibration": [
            {"level": lvl, "feel": desc}
            for lvl, desc in sorted(VOLUME_CALIBRATION.items())
        ],
        "moods": SEMANTIC_VOLUMES,
        "hard_ceiling_pct": max_output_volume_pct(),
    }


@router.get("/api/music/marantz/sounds", response_class=JSONResponse)
async def marantz_sounds():
    from mcps.music.local_file import list_sounds
    return await list_sounds()


@router.get("/api/music/marantz/state", response_class=JSONResponse)
async def marantz_state():
    from mcps.music.local_file import get_marantz_state
    return await get_marantz_state()


@router.post("/api/music/marantz/play_local_file", response_class=JSONResponse)
async def marantz_play_local(payload: dict = Body(default={})):
    from mcps.music.local_file import play_local_file
    return await play_local_file(
        file_path=(payload or {}).get("file_path", ""),
        volume_pct=(payload or {}).get("volume_pct"),
        mood=(payload or {}).get("mood"),
        duration_seconds=(payload or {}).get("duration_seconds"),
    )


@router.post("/api/music/marantz/volume", response_class=JSONResponse)
async def marantz_volume(payload: dict = Body(default={})):
    from mcps.music.local_file import set_marantz_volume
    return await set_marantz_volume(
        volume_pct=(payload or {}).get("volume_pct"),
        mood=(payload or {}).get("mood"),
    )


@router.post("/api/music/marantz/pause", response_class=JSONResponse)
async def marantz_pause(payload: dict = Body(default={})):
    from mcps.music.local_file import pause_playback
    return await pause_playback()


@router.post("/api/music/marantz/resume", response_class=JSONResponse)
async def marantz_resume(payload: dict = Body(default={})):
    from mcps.music.local_file import resume_playback
    return await resume_playback()


@router.post("/api/music/marantz/stop", response_class=JSONResponse)
async def marantz_stop(payload: dict = Body(default={})):
    from mcps.music.local_file import stop_playback
    return await stop_playback()
