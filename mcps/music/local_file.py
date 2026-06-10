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
import time
from pathlib import Path
from typing import Optional


# How long to wait, after `play_stream`, for the AVR to actually report
# state=play before starting the user-requested duration countdown.
# Marantz/HEOS source-switching (e.g. from Spotify Connect → URL Stream)
# can take 1-2 s on the first call after another source was active;
# without this poll, short test windows lose most of their audible time
# to the source switch.
WARMUP_TIMEOUT_S = 3.0
WARMUP_POLL_S = 0.2

# Volume ramp / fade-in defaults. Jumping from silent → target level
# in one set_volume call is jarring for listeners and unsafe near
# speakers. We start playback at a quiet level, then walk the volume
# up to the requested target over a short window so the onset is a
# gentle fade-in instead of a slap.
DEFAULT_RAMP_SECONDS = 2.0
RAMP_STEP_S = 0.2          # one HEOS set_volume call every 200 ms
DEFAULT_RAMP_FROM = 20     # whisper-ish — audible enough to know "it's playing"

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


async def _ramp_volume(client, start: int, target: int, seconds: float) -> list[int]:
    """Walk the HEOS volume from `start` → `target` over `seconds`,
    one set_volume call per RAMP_STEP_S. Returns the levels actually
    sent (useful for telemetry / debugging).

    Skips the ramp entirely (one set_volume(target)) when start == target,
    when seconds < one step, or when start > target (we don't fade
    DOWN automatically — that's a separate operation)."""
    if seconds <= 0 or start >= target:
        await client.set_volume(target)
        return [target]
    steps = max(2, int(round(seconds / RAMP_STEP_S)))
    sent: list[int] = []
    for i in range(1, steps + 1):
        level = int(round(start + (target - start) * i / steps))
        await client.set_volume(level)
        sent.append(level)
        if i < steps:
            await asyncio.sleep(seconds / steps)
    return sent


async def play_local_file(
    file_path: str,
    volume_pct: Optional[int] = None,
    mood: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    ramp_seconds: float = DEFAULT_RAMP_SECONDS,
    ramp_from: Optional[int] = None,
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

    # Compute ramp start: explicit param wins; otherwise pick something
    # audible-but-quiet for any target above whisper (so the listener
    # hears "playback started" but isn't slapped by full volume).
    if ramp_from is None:
        start_level = min(level, DEFAULT_RAMP_FROM) if level > DEFAULT_RAMP_FROM else level
    else:
        # Capped + clamped just like the target. Never starts higher
        # than the target.
        capped_from, _ = cap_volume(int(ramp_from))
        start_level = min(capped_from, level)

    try:
        # set_volume FIRST so when play_stream starts the level is already
        # at the (quiet) ramp-start, not whatever the AVR last had.
        await client.set_volume(start_level)
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
    result["ramp_from"] = start_level

    # 4. Warm-up poll — wait for the AVR to actually report state=play
    # before starting the duration countdown. Marantz/HEOS can take
    # 1-2 s switching sources (e.g. from Spotify Connect to URL Stream)
    # before audio is actually audible; without this poll a short test
    # window can be entirely consumed by source-switch silence.
    warmup_start = time.monotonic()
    became_playing = False
    while time.monotonic() - warmup_start < WARMUP_TIMEOUT_S:
        try:
            state = await client.get_play_state()
        except Exception:  # noqa: BLE001
            state = "unknown"
        if state == "play":
            became_playing = True
            break
        await asyncio.sleep(WARMUP_POLL_S)
    result["warmup_seconds"] = round(time.monotonic() - warmup_start, 2)
    result["warmup_became_playing"] = became_playing

    # 5. Volume ramp — walk from ramp_from → target over ramp_seconds.
    # Only ramps UP, never down (down jumps are safe and instant).
    ramp_clamped = max(0.0, min(15.0, float(ramp_seconds)))
    levels = await _ramp_volume(client, start_level, level, ramp_clamped)
    result["ramp_seconds"] = ramp_clamped
    result["ramp_levels"] = levels

    # 6. Optional auto-stop window — the user-requested duration is now
    # ACTUAL audible time AFTER the ramp completes.
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


# Internet-radio stations the Marantz can stream directly via HEOS
# play_stream — no account/login needed (unlike Spotify). Sveriges Radio
# public Icecast streams (http; some HEOS firmware is fussy about https).
RADIO_STATIONS = {
    "p1": ("Sveriges Radio P1 (news/talk)", "http://http-live.sr.se/p1-mp3-192"),
    "p2": ("Sveriges Radio P2 (classical/jazz)", "http://http-live.sr.se/p2-mp3-192"),
    "p3": ("Sveriges Radio P3 (pop/youth)", "http://http-live.sr.se/p3-mp3-192"),
    "p4": ("Sveriges Radio P4 Stockholm", "http://http-live.sr.se/p4stockholm-mp3-192"),
}


async def play_radio(
    station: str = "p3",
    volume_pct: Optional[int] = None,
    mood: Optional[str] = None,
    ramp_seconds: float = DEFAULT_RAMP_SECONDS,
    ramp_from: Optional[int] = None,
) -> dict:
    """Stream internet radio on the Marantz via HEOS. `station` is a key in
    RADIO_STATIONS or a raw http(s) stream URL. Same volume cap + fade-in as
    play_local_file; plays continuously until stopped."""
    key = (station or "").strip().lower()
    if key in RADIO_STATIONS:
        label, url = RADIO_STATIONS[key]
    elif key.startswith("http://") or key.startswith("https://"):
        label, url = "custom stream", station.strip()
    else:
        return {"error": "unknown station",
                "detail": f"use one of {list(RADIO_STATIONS)} or an http(s) URL"}

    if volume_pct is None and mood:
        requested = volume_for_mood(mood)
    elif volume_pct is None:
        requested = volume_for_mood("background")  # quiet but present
    else:
        requested = int(volume_pct)
    level, was_capped = cap_volume(requested)

    try:
        client = get_client()
    except HEOSNotConfigured as e:
        return {"error": "heos not configured", "detail": str(e)}

    if ramp_from is None:
        start_level = min(level, DEFAULT_RAMP_FROM) if level > DEFAULT_RAMP_FROM else level
    else:
        capped_from, _ = cap_volume(int(ramp_from))
        start_level = min(capped_from, level)

    result: dict = {"station": key, "label": label, "url": url, "volume_pct": level}
    if was_capped:
        result.update(volume_capped=True, requested_pct=requested,
                      ceiling_pct=max_output_volume_pct())
    try:
        await client.set_volume(start_level)
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
    result["ramp_from"] = start_level

    warmup_start = time.monotonic()
    became_playing = False
    while time.monotonic() - warmup_start < WARMUP_TIMEOUT_S:
        try:
            state = await client.get_play_state()
        except Exception:  # noqa: BLE001
            state = "unknown"
        if state == "play":
            became_playing = True
            break
        await asyncio.sleep(WARMUP_POLL_S)
    result["warmup_seconds"] = round(time.monotonic() - warmup_start, 2)
    result["warmup_became_playing"] = became_playing

    ramp_clamped = max(0.0, min(15.0, float(ramp_seconds)))
    result["ramp_levels"] = await _ramp_volume(client, start_level, level, ramp_clamped)
    result["ramp_seconds"] = ramp_clamped
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
                              mood: Optional[str] = None,
                              ramp_seconds: float = DEFAULT_RAMP_SECONDS) -> dict:
    """Standalone volume control. Same capping + mood mapping as
    play_local_file. UP changes are ramped (default 2 s) so the
    listener doesn't get a sudden loud step; DOWN changes are
    instant (always safe)."""
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
        current = await client.get_volume()
    except Exception:  # noqa: BLE001
        current = -1

    out: dict = {
        "ok": True,
        "from_pct": current if current >= 0 else None,
        "volume_pct": level,
        "calibration_hint": VOLUME_CALIBRATION.get(level),
    }
    ramp = max(0.0, min(15.0, float(ramp_seconds)))
    try:
        # Only ramp on volume UP; jumps DOWN are instant + safe.
        if current >= 0 and level > current and ramp > 0:
            levels = await _ramp_volume(client, current, level, ramp)
            out["ramp_seconds"] = ramp
            out["ramp_levels"] = levels
        else:
            await client.set_volume(level)
            out["ramp_seconds"] = 0
    except Exception as e:  # noqa: BLE001
        return {"error": "heos set_volume failed", "detail": repr(e)}
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
