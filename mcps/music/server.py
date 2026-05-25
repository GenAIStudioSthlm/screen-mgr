"""Music MCP server — Spotify Web API via spotipy.

Mounted at /mcp/music/sse. Tools fail gracefully with
``{"error": "spotify not configured", ...}`` when env vars / spotipy
are missing — see `mcps/music/spotify_client.py` and the one-time
auth helper at `scripts/spotify_auth.py`.

Scopes used (granted by the user during the one-time auth):
  user-read-playback-state
  user-modify-playback-state
  user-read-currently-playing
"""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mcps.audio.safety import cap_volume, max_output_volume_pct
from mcps.music.spotify_client import call
from mcps.music.speaker_test import (
    DEFAULT_DEVICE_QUERY,
    DEFAULT_PLAY_SECONDS,
    DEFAULT_TRACK_QUERY,
    DEFAULT_VOLUME_PCT,
    run_speaker_test as _run_speaker_test,
)
from mcps.music.presets import (
    play_preset as _play_preset,
    preset_manager as _preset_manager,
)


_TRANSPORT = TransportSecuritySettings(enable_dns_rebinding_protection=False)
server = FastMCP("music", transport_security=_TRANSPORT)


# --------------------------------------------------------------------------
# Tools — read
# --------------------------------------------------------------------------


@server.tool()
def get_now_playing() -> dict:
    """What's currently playing — track, artist, album art, device,
    progress, paused/playing state. Returns Spotify's
    ``currently_playing`` payload (or ``{"data": null}`` when nothing
    is playing).
    """
    return call(lambda c: c.current_playback())


@server.tool()
def list_devices() -> dict:
    """List Spotify Connect devices visible to this account (phones,
    speakers, the desktop client, etc.). Each entry's ``id`` is what
    `play` and `set_volume` take as ``device_id``."""
    return call(lambda c: c.devices())


@server.tool()
def search(query: str, search_type: str = "track", limit: int = 5) -> dict:
    """Search Spotify's catalog.

    - ``query``: free-text search.
    - ``search_type``: one of ``track``, ``album``, ``artist``,
      ``playlist``. Default ``track``.
    - ``limit``: 1–20. Default 5.

    Returns the first ``limit`` results — each has a Spotify URI
    (``spotify:track:...``) that `play` accepts."""
    return call(lambda c: c.search(q=query, type=search_type, limit=max(1, min(20, limit))))


# --------------------------------------------------------------------------
# Tools — write
# --------------------------------------------------------------------------


@server.tool()
def play(uri: Optional[str] = None, device_id: Optional[str] = None) -> dict:
    """Start or resume playback.

    - ``uri``: optional Spotify URI to play (``spotify:track:...``,
      ``spotify:album:...``, ``spotify:playlist:...``). When omitted,
      resumes whatever was playing.
    - ``device_id``: optional id from `list_devices`. When omitted,
      uses the currently-active device.

    Returns ``{"ok": true}`` on success or a spotify-call-failed
    error (common: no active device — open Spotify on a speaker
    first)."""
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


@server.tool()
def pause(device_id: Optional[str] = None) -> dict:
    """Pause playback on the active device (or a specific one)."""
    def _do(c):
        c.pause_playback(device_id=device_id)
        return {"paused": True, "device_id": device_id}
    return call(_do)


@server.tool()
def next_track(device_id: Optional[str] = None) -> dict:
    """Skip to the next track."""
    def _do(c):
        c.next_track(device_id=device_id)
        return {"skipped": "next", "device_id": device_id}
    return call(_do)


@server.tool()
def previous_track(device_id: Optional[str] = None) -> dict:
    """Skip back to the previous track."""
    def _do(c):
        c.previous_track(device_id=device_id)
        return {"skipped": "previous", "device_id": device_id}
    return call(_do)


@server.tool()
def set_volume(volume_pct: int, device_id: Optional[str] = None) -> dict:
    """Set playback volume on the active or specified device. 0–100.

    Hard-capped at MAX_OUTPUT_VOLUME_PCT (default 70) to prevent
    acoustic feedback with the ceiling mic — see docs/SAFETY.md."""
    vol, capped = cap_volume(volume_pct)
    def _do(c):
        c.volume(vol, device_id=device_id)
        result = {"volume_pct": vol, "device_id": device_id}
        if capped:
            result["capped"] = True
            result["requested_pct"] = int(volume_pct)
            result["ceiling_pct"] = max_output_volume_pct()
        return result
    return call(_do)


# --------------------------------------------------------------------------
# Tools — diagnostics
# --------------------------------------------------------------------------


@server.tool()
async def run_speaker_test(
    device_query: str = DEFAULT_DEVICE_QUERY,
    volume_pct: int = DEFAULT_VOLUME_PCT,
    track_query: str = DEFAULT_TRACK_QUERY,
    play_seconds: int = DEFAULT_PLAY_SECONDS,
) -> dict:
    """Play a full-spectrum reference track on a named Spotify Connect
    device at a fixed volume, then pause.

    - ``device_query``: case-insensitive substring matched against the
      device names from `list_devices`. Default ``"bose"`` (the studio's
      Bose speakers).
    - ``volume_pct``: 0–100. Default 20.
    - ``track_query``: free-text Spotify search; first track result is
      used. Default ``"Hotel California Eagles"`` (a standard audiophile
      reference — clean lows from the kick drum, mids from the vocals,
      highs from the 12-string guitar).
    - ``play_seconds``: how long to play before pausing. 1–120. Default 20.

    Returns a per-step summary: which devices were visible, which device
    + track were matched, whether volume + play + pause all landed.

    Requires Spotify to be configured. Returns
    ``{"error": "spotify not configured", ...}`` if it isn't — see
    docs/DEPLOY.md → Spotify setup."""
    return await _run_speaker_test(
        device_query=device_query,
        volume_pct=volume_pct,
        track_query=track_query,
        play_seconds=play_seconds,
    )


@server.tool()
def list_presets() -> dict:
    """List the named music presets the operator can fire with one click.

    Each preset bundles a search query (resolved against Spotify at
    play-time), a target Spotify Connect device, and a default volume.
    Today's presets are seeded in `data/music_presets.json`:
    ``chill-vibes`` (Lo-Fi Girl), ``energy`` (Northern House Rarities),
    ``chaotic`` (jazz fusion)."""
    return {"presets": [p.model_dump() for p in _preset_manager.presets]}


@server.tool()
async def play_preset(
    preset_id: str,
    device_query: Optional[str] = None,
    volume_pct: Optional[int] = None,
) -> dict:
    """Play a named music preset on its target Spotify Connect device.

    - ``preset_id``: one of the ids from `list_presets`.
    - ``device_query``: optional — override the preset's default device
      (case-insensitive substring match against `list_devices`).
    - ``volume_pct``: optional — override the preset's default volume.

    Does NOT auto-pause — the preset keeps playing until the operator
    stops it (via Spotify or the Music view). Returns a per-step
    summary with what was matched + what played."""
    return await _play_preset(
        preset_id=preset_id,
        device_query_override=device_query,
        volume_pct_override=volume_pct,
    )
