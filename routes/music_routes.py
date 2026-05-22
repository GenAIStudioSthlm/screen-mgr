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
