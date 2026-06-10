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

from mcps.audio.safety import (
    SEMANTIC_VOLUMES,
    VOLUME_CALIBRATION,
    cap_volume,
    max_output_volume_pct,
)
from mcps.music.spotify_client import call
from mcps.music import local_file as _local_file
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
    ramp_seconds: Optional[float] = None,
    ramp_from: Optional[int] = None,
) -> dict:
    """Play a named music preset on its target Spotify Connect device.

    A preset bundles two orthogonal things: **what** to play (the
    vibe — chill / energy / chaotic / whatever the operator added),
    and **how it sounds when it starts** (the target volume + fade-in
    ramp). Genre and volume are separate concerns.

    - ``preset_id``: one of the ids from `list_presets`.
    - ``device_query``: override the preset's default Connect device.
    - ``volume_pct``: override the preset's target volume (HEOS
      calibration scale — 35 background, 50 comfortable, 65 loud,
      70 cap).
    - ``ramp_seconds``: override the preset's fade-in window
      (default 2 s; max 15 s; 0 disables the ramp).
    - ``ramp_from``: override the preset's ramp start level
      (default ~20 — whisper-quiet).

    Does NOT auto-pause — the preset keeps playing until the operator
    stops it. The result dict includes the ramp levels actually sent
    so you can see the gradient."""
    return await _play_preset(
        preset_id=preset_id,
        device_query_override=device_query,
        volume_pct_override=volume_pct,
        ramp_seconds_override=ramp_seconds,
        ramp_from_override=ramp_from,
    )


# --------------------------------------------------------------------------
# Tools — Marantz via HEOS (local-file + transport)
#
# Volume calibration on the studio's Marantz + Bose chain (2026-05-25):
#   10  inaudible            (~-60 dB master)
#   25  whisper / very low
#   35  background music
#   50  comfortable listening
#   65  loud — near max
#   70  HARD CAP refused above this
#
# The HEOS volume scale is essentially an attenuation in dB, NOT
# perceived loudness percent. The semantic mood names below map to
# safe defaults so an agent can pick "background" instead of guessing.
# --------------------------------------------------------------------------


@server.tool()
def get_volume_calibration() -> dict:
    """Return the volume calibration table for the Marantz + Bose chain.

    Pair each HEOS volume integer with the human-readable level it
    sounds like, plus the named "moods" agents can pass to
    `play_local_file(mood=...)` and `set_marantz_volume(mood=...)`.

    Use this to pick a sensible volume for the operator's intent —
    e.g. for a 'play me some background music' request, the mood is
    "background" (volume 35), well below the 'comfortable' default of
    50 and far below the 70 hard cap.
    """
    return {
        "scale": "HEOS 0-100 (≈ dB attenuation on the AVR's master volume — NOT perceived loudness %)",
        "calibration": [
            {"level": lvl, "feel": desc} for lvl, desc in sorted(VOLUME_CALIBRATION.items())
        ],
        "moods": SEMANTIC_VOLUMES,
        "hard_ceiling_pct": max_output_volume_pct(),
        "safety_doc": "docs/SAFETY.md",
    }


@server.tool()
async def list_sounds() -> dict:
    """List local audio files available for `play_local_file`.

    Files live under ``static/sounds/`` on the Pi. Drop .mp3 / .wav /
    .flac / .ogg / .m4a / .aac files there to make them playable.
    Names returned here are the ``file_path`` argument to
    `play_local_file`.
    """
    return await _local_file.list_sounds()


@server.tool()
async def play_local_file(
    file_path: str,
    volume_pct: Optional[int] = None,
    mood: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    ramp_seconds: float = 2.0,
    ramp_from: Optional[int] = None,
) -> dict:
    """Play a local audio file on the Marantz (which drives the studio's
    Bose speakers) via HEOS. Marantz fetches the file directly from
    the Pi's /static/sounds/ mount over HTTP.

    Arguments:
      file_path: name from `list_sounds` (path relative to static/sounds/).
      volume_pct: explicit HEOS level 0-100. Capped at 70 by safety.
      mood: alternative to volume_pct — one of
            "inaudible" (10), "whisper" (25), "background" (35),
            "comfortable" (50), "loud" (65), "max" (70). If both are
            given, volume_pct wins. Default mood is "whisper" — quiet
            but audible.
      duration_seconds: if set, auto-stop after N seconds. Otherwise
                       plays to end of file. Clamped to [0.5, 300].
      ramp_seconds: fade-in duration (default 2 s, max 15 s). Playback
                   starts quiet and ramps to the target volume — avoids
                   slapping listeners with a sudden loud onset. Set to
                   0 to disable the ramp and start at full target.
      ramp_from: starting level for the ramp. Default picks a quiet
                 audible level (~20) so the listener hears playback
                 has started without it being loud.

    Returns the URL fetched, the effective volume, calibration hint,
    warm-up timing, the ramp levels actually sent, and (if used) the
    auto-stop window.
    """
    return await _local_file.play_local_file(
        file_path=file_path,
        volume_pct=volume_pct,
        mood=mood,
        duration_seconds=duration_seconds,
        ramp_seconds=ramp_seconds,
        ramp_from=ramp_from,
    )


@server.tool()
async def play_radio(
    station: str = "p3",
    volume_pct: Optional[int] = None,
    mood: Optional[str] = None,
    ramp_seconds: float = 2.0,
    ramp_from: Optional[int] = None,
) -> dict:
    """Stream internet radio on the Marantz via HEOS — NO account or login
    needed (use this when Spotify isn't configured). Reliable background
    audio.

    station: one of
      - "p3" (Sveriges Radio P3, pop/youth — good default for background)
      - "p1" (news/talk), "p2" (classical/jazz), "p4" (P4 Stockholm)
      - or a raw http(s) stream URL.
    volume_pct / mood: same calibration + 70 cap as play_local_file; default
      mood is "background" (~35). Fades in. Plays until stopped
      (marantz_stop / pause)."""
    return await _local_file.play_radio(
        station=station, volume_pct=volume_pct, mood=mood,
        ramp_seconds=ramp_seconds, ramp_from=ramp_from,
    )


@server.tool()
async def set_marantz_volume(
    volume_pct: Optional[int] = None,
    mood: Optional[str] = None,
    ramp_seconds: float = 2.0,
) -> dict:
    """Set the Marantz volume independently of playback.

    Same calibration + capping as `play_local_file`. Use ``mood`` for
    a semantic choice ("background", "comfortable", "loud") or
    ``volume_pct`` for an explicit number.

    Volume UP changes are ramped (default 2 s) to avoid sudden loud
    steps; volume DOWN changes are instant (always safe to drop).
    Set ramp_seconds=0 to make UP changes instant too."""
    return await _local_file.set_marantz_volume(
        volume_pct=volume_pct, mood=mood, ramp_seconds=ramp_seconds,
    )


@server.tool()
async def get_marantz_state() -> dict:
    """Snapshot the Marantz: play state, current volume, now-playing
    metadata. Useful as a health probe (confirms HEOS reachable +
    auth working) and to see what's currently playing."""
    return await _local_file.get_marantz_state()


@server.tool()
async def marantz_pause() -> dict:
    """Pause whatever is playing on the Marantz."""
    return await _local_file.pause_playback()


@server.tool()
async def marantz_resume() -> dict:
    """Resume playback on the Marantz."""
    return await _local_file.resume_playback()


@server.tool()
async def marantz_stop() -> dict:
    """Stop playback on the Marantz."""
    return await _local_file.stop_playback()
