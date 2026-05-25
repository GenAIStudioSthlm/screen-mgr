"""Local-file playback on the Marantz via HEOS.

End-to-end flow:

  1. Operator drops `static/sounds/foo.mp3` on the Pi.
  2. Music MCP tool `play_local_file("foo.mp3", mood="background")` (or
     explicit `volume_pct=35`).
  3. We path-validate `foo.mp3` (refuse anything outside static/sounds/).
  4. Resolve the URL the Marantz will fetch:
     `http://{HOST_IP}:8000/static/sounds/foo.mp3`.
  5. Cap the volume (default mood "whisper" = 25; hard ceiling 70).
  6. HEOS `set_volume` → `play_stream` → optional auto-stop after N s.

Path restriction (`static/sounds/`) mirrors `pactl_backend.play_sound`
so neither MCP tool can be coerced into playing arbitrary files off
the Pi. Drop .mp3 / .wav / .flac / .ogg / .m4a files in that directory
to make them playable.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from mcps.audio.safety import (
    SAFE_TEST_VOLUME_PCT,
    VOLUME_CALIBRATION,
    cap_volume,
    max_output_volume_pct,
    volume_for_mood,
)
from mcps.music.heos_client import HEOSError, HEOSNotConfigured, get_client


# Where allowed audio files live. Anything outside this dir is refused
# at the URL-resolution stage.
SOUNDS_DIR = (Path(__file__).resolve().parents[2] / "static" / "sounds").resolve()

# The host:port the Marantz will hit to GET the file. Default to the Pi's
# LAN IP if not overridden — kept in env so dev-environment runs against
# a different host don't break.
DEFAULT_HOST_URL = "http://192.168.2.65:8000"


def _host_url() -> str:
    return (os.environ.get("STATIC_HOST_URL") or DEFAULT_HOST_URL).rstrip("/")


def _resolve_sound_path(rel_path: str) -> Path:
    """Reject absolute paths and `..` traversal; require the file to
    exist under SOUNDS_DIR. Returns the absolute Path on success."""
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    candidate = Path(rel_path.lstrip("/"))
    if candidate.is_absolute():
        raise ValueError("absolute paths not allowed")
    full = (SOUNDS_DIR / candidate).resolve()
    try:
        full.relative_to(SOUNDS_DIR)
    except ValueError:
        raise ValueError(f"path {rel_path!r} escapes static/sounds/") from None
    if not full.is_file():
        raise FileNotFoundError(f"{rel_path!r} not found under static/sounds/")
    return full


def _build_url(file_path: Path) -> str:
    rel = file_path.relative_to(SOUNDS_DIR)
    return f"{_host_url()}/static/sounds/{rel.as_posix()}"


async def play_local_file(
    file_path: str,
    volume_pct: Optional[int] = None,
    mood: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> dict:
    """Play a local audio file on the Marantz at a safe volume.

    Arguments:
      file_path: relative path under static/sounds/ on the Pi.
      volume_pct: explicit HEOS level 0-100. Capped at
                  MAX_OUTPUT_VOLUME_PCT (default 70).
      mood: instead of an explicit number, pick a semantic level —
            "inaudible" / "whisper" / "background" / "comfortable"
            / "loud" / "max". See VOLUME_CALIBRATION for what each
            sounds like on this AVR. If both volume_pct and mood are
            given, volume_pct wins.
      duration_seconds: if given, auto-stop after N seconds (clamped
                        to [0.5, 300]). Otherwise plays to end of file
                        and HEOS handles natural termination.

    Returns a per-step summary dict including what was actually
    played, the URL the Marantz fetched, the effective volume, and
    whether the volume was capped.
    """
    # 1. Validate path + build URL
    try:
        full_path = _resolve_sound_path(file_path)
    except (ValueError, FileNotFoundError) as e:
        return {"error": "invalid sound path", "detail": str(e)}
    url = _build_url(full_path)

    # 2. Resolve volume
    if volume_pct is None and mood:
        requested = volume_for_mood(mood)
    elif volume_pct is None:
        requested = SAFE_TEST_VOLUME_PCT
    else:
        requested = int(volume_pct)
    level, was_capped = cap_volume(requested)

    # 3. Connect to HEOS + drive playback
    try:
        client = get_client()
    except HEOSNotConfigured as e:
        return {"error": "heos not configured", "detail": str(e)}

    result: dict = {
        "file": str(full_path.relative_to(SOUNDS_DIR)),
        "url": url,
        "volume_pct": level,
        "mood": mood if (volume_pct is None and mood) else None,
        "calibration_hint": VOLUME_CALIBRATION.get(level)
        or next((VOLUME_CALIBRATION[k] for k in sorted(VOLUME_CALIBRATION) if k >= level), None),
    }
    if was_capped:
        result["volume_capped"] = True
        result["requested_pct"] = requested
        result["ceiling_pct"] = max_output_volume_pct()

    try:
        # set_volume FIRST so when play_stream starts the level is already safe
        await client.set_volume(level)
        await client.play_stream(url)
    except HEOSError as e:
        result["error"] = "heos call failed"
        result["detail"] = str(e)
        return result
    except Exception as e:  # noqa: BLE001
        result["error"] = "heos connection failed"
        result["detail"] = repr(e)
        return result

    result["playback_started"] = True

    # 4. Optional auto-stop window
    if duration_seconds is not None:
        wait = max(0.5, min(300.0, float(duration_seconds)))
        result["duration_seconds"] = wait
        await asyncio.sleep(wait)
        try:
            await client.stop()
            result["auto_stopped"] = True
        except Exception as e:  # noqa: BLE001
            result["stop_error"] = repr(e)

    return result


async def stop_playback() -> dict:
    """Stop whatever is currently playing on the Marantz."""
    try:
        client = get_client()
    except HEOSNotConfigured as e:
        return {"error": "heos not configured", "detail": str(e)}
    try:
        await client.stop()
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"error": "heos stop failed", "detail": repr(e)}


async def pause_playback() -> dict:
    try:
        client = get_client()
    except HEOSNotConfigured as e:
        return {"error": "heos not configured", "detail": str(e)}
    try:
        await client.pause()
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"error": "heos pause failed", "detail": repr(e)}


async def resume_playback() -> dict:
    try:
        client = get_client()
    except HEOSNotConfigured as e:
        return {"error": "heos not configured", "detail": str(e)}
    try:
        await client.play()
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"error": "heos play failed", "detail": repr(e)}


async def set_marantz_volume(volume_pct: Optional[int] = None,
                              mood: Optional[str] = None) -> dict:
    """Standalone volume control. Same capping + mood mapping as
    play_local_file."""
    if volume_pct is None and mood:
        requested = volume_for_mood(mood)
    elif volume_pct is None:
        requested = SAFE_TEST_VOLUME_PCT
    else:
        requested = int(volume_pct)
    level, was_capped = cap_volume(requested)
    try:
        client = get_client()
    except HEOSNotConfigured as e:
        return {"error": "heos not configured", "detail": str(e)}
    try:
        await client.set_volume(level)
    except Exception as e:  # noqa: BLE001
        return {"error": "heos set_volume failed", "detail": repr(e)}
    out: dict = {
        "ok": True,
        "volume_pct": level,
        "calibration_hint": VOLUME_CALIBRATION.get(level),
    }
    if was_capped:
        out["volume_capped"] = True
        out["requested_pct"] = requested
        out["ceiling_pct"] = max_output_volume_pct()
    return out


async def get_marantz_state() -> dict:
    """Snapshot the Marantz: play state + volume + now-playing."""
    try:
        client = get_client()
    except HEOSNotConfigured as e:
        return {"error": "heos not configured", "detail": str(e)}
    try:
        state = await client.get_play_state()
        volume = await client.get_volume()
        now = await client.get_now_playing()
        return {
            "ok": True,
            "play_state": state,
            "volume_pct": volume,
            "now_playing": now.get("payload", {}),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": "heos state failed", "detail": repr(e)}


async def list_sounds() -> dict:
    """List files available under static/sounds/ on the Pi."""
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    exts = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}
    files = []
    for f in sorted(SOUNDS_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in exts:
            files.append({
                "name": f.name,
                "size_bytes": f.stat().st_size,
            })
    return {"sounds_dir": str(SOUNDS_DIR), "files": files}
