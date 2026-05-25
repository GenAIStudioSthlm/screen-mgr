"""Music speaker test — play a known full-spectrum track on a named
Spotify Connect device at a fixed volume, then pause.

Default target is the Bose speakers in the studio (visible to the
Spotify account as a Connect device on the studio's network). Default
track is Eagles — Hotel California, a standard audiophile reference
with clean low/mid/high content. Both overridable.

Sequence:
  1. Resolve the target device by case-insensitive substring match
     against `list_devices()`.
  2. Search Spotify for the track, pick the first result.
  3. Set volume on that device to `volume_pct`.
  4. Start playback of the track on that device.
  5. Sleep `play_seconds`.
  6. Pause.

Returns a summary dict at each step so a caller can tell exactly
where things went wrong if the studio speakers are off, the device
isn't visible, or the track query returns nothing.

Won't actually play anything until Spotify is configured — see
docs/DEPLOY.md → Spotify setup. Tools degrade with a clear
"spotify not configured" error via `mcps/music/spotify_client.call`.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from mcps.audio.safety import cap_volume, max_output_volume_pct
from mcps.music.spotify_client import call


DEFAULT_DEVICE_QUERY = "marantz"  # matches "MarantzCinema70s" via substring
DEFAULT_TRACK_QUERY = "Hotel California Eagles"
DEFAULT_VOLUME_PCT = 20
DEFAULT_PLAY_SECONDS = 20


def _find_device(devices_payload: dict, query: str) -> Optional[dict]:
    """Pick the first device whose name contains `query` (case-insensitive)."""
    if not isinstance(devices_payload, dict):
        return None
    devices = devices_payload.get("devices") or []
    q = query.lower().strip()
    # Exact match first.
    for d in devices:
        if (d.get("name") or "").lower() == q:
            return d
    # Substring match second.
    for d in devices:
        if q in (d.get("name") or "").lower():
            return d
    return None


def _first_track_uri(search_payload: dict) -> Optional[tuple[str, str]]:
    """Return (uri, label) of the first track result, or None."""
    tracks = ((search_payload or {}).get("tracks") or {}).get("items") or []
    if not tracks:
        return None
    t = tracks[0]
    uri = t.get("uri")
    label_parts = [t.get("name", "?")]
    artists = ", ".join(a.get("name", "?") for a in (t.get("artists") or []))
    if artists:
        label_parts.append("— " + artists)
    return (uri, " ".join(label_parts)) if uri else None


async def run_speaker_test(
    device_query: str = DEFAULT_DEVICE_QUERY,
    volume_pct: int = DEFAULT_VOLUME_PCT,
    track_query: str = DEFAULT_TRACK_QUERY,
    play_seconds: int = DEFAULT_PLAY_SECONDS,
) -> dict:
    """Play a track on a named Spotify Connect device, then pause."""
    volume_pct, vol_capped = cap_volume(volume_pct)
    play_seconds = max(1, min(120, int(play_seconds)))

    result: dict[str, Any] = {
        "device_query": device_query,
        "track_query": track_query,
        "volume_pct": volume_pct,
        "play_seconds": play_seconds,
    }
    if vol_capped:
        result["volume_capped"] = True
        result["ceiling_pct"] = max_output_volume_pct()

    # 1. Devices
    devices_resp = call(lambda c: c.devices())
    if "error" in devices_resp:
        result["error"] = devices_resp["error"]
        result["detail"] = devices_resp.get("detail")
        return result
    result["devices_visible"] = [
        {"id": d.get("id"), "name": d.get("name"), "type": d.get("type")}
        for d in (devices_resp.get("data") or {}).get("devices", [])
    ]
    device = _find_device(devices_resp.get("data") or {}, device_query)
    if device is None:
        result["error"] = f"no Spotify device matching {device_query!r}"
        result["hint"] = (
            "Open Spotify on the target speaker so it shows up as a "
            "Connect device, then retry."
        )
        return result
    result["device"] = {"id": device.get("id"), "name": device.get("name")}

    # 2. Track
    search_resp = call(
        lambda c: c.search(q=track_query, type="track", limit=1)
    )
    if "error" in search_resp:
        result["error"] = search_resp["error"]
        result["detail"] = search_resp.get("detail")
        return result
    track = _first_track_uri(search_resp.get("data") or {})
    if track is None:
        result["error"] = f"no Spotify track matching {track_query!r}"
        return result
    track_uri, track_label = track
    result["track"] = {"uri": track_uri, "label": track_label}

    # 3. Volume
    vol_resp = call(
        lambda c: c.volume(volume_pct, device_id=device["id"])
    )
    if "error" in vol_resp:
        result["volume_error"] = vol_resp
        # Don't abort — playback might still work; just note it.

    # 4. Play
    play_resp = call(
        lambda c: c.start_playback(device_id=device["id"], uris=[track_uri])
    )
    if "error" in play_resp:
        result["error"] = play_resp["error"]
        result["detail"] = play_resp.get("detail")
        return result
    result["playback_started"] = True

    # 5. Wait
    await asyncio.sleep(play_seconds)

    # 6. Pause
    pause_resp = call(lambda c: c.pause_playback(device_id=device["id"]))
    if "error" in pause_resp:
        result["pause_error"] = pause_resp
    else:
        result["paused"] = True

    return result
