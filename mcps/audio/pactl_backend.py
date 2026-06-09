"""PulseAudio backend for the Audio MCP — shells to `pactl` / `paplay`.

studiopi runs PipeWire with the pulse-compat shim, so `pactl` works
exactly as it would against PulseAudio proper. We use the human
inventory commands (`pactl list sinks`, `pactl list sources`), parse
the block format, and fan out to `get-sink-volume` / `get-sink-mute`
for per-sink state.

Tool signatures match the stubs in `mcps/audio/server.py` so swapping
the import path is the only change at the call site.

play_sound is path-restricted to `static/sounds/` so the MCP can't be
coerced into spawning `paplay /etc/something`. Drop .wav / .mp3 /
.ogg files in that directory to make them playable.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from mcps.audio.safety import cap_volume, max_output_volume_pct


PACTL = "pactl"
PAPLAY = "paplay"
DEFAULT_TIMEOUT = 4.0

# Where play_sound can read from. Files outside this dir are refused.
SOUNDS_DIR = (Path(__file__).resolve().parents[2] / "static" / "sounds").resolve()


# ----------------------------------------------------------------------
# Shell helpers
# ----------------------------------------------------------------------


def _audio_env() -> dict[str, str]:
    """Make sure pactl can find the user's PipeWire-pulse socket even
    when screen-mgr runs from a systemd service with `Environment=`
    empty. Sets XDG_RUNTIME_DIR to /run/user/<uid> if missing — that's
    where the PulseAudio Unix socket lives."""
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return env


def _run(*args: str, timeout: float = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=_audio_env(),
    )


class PactlMissing(RuntimeError):
    """pactl isn't installed or isn't on PATH."""


def _pactl(*args: str, timeout: float = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    try:
        return _run(PACTL, *args, timeout=timeout)
    except FileNotFoundError as e:
        raise PactlMissing(
            "pactl not found on PATH. Install pulseaudio-utils "
            "(`sudo apt install pulseaudio-utils`) or run inside a "
            "PipeWire-pulse session."
        ) from e


# ----------------------------------------------------------------------
# `pactl list sinks` parser
# ----------------------------------------------------------------------


_SINK_HEADER_RE = re.compile(r"^Sink\s*#(\d+)\s*$")
_SOURCE_HEADER_RE = re.compile(r"^Source\s*#(\d+)\s*$")
_VOLUME_PCT_RE = re.compile(r"(\d+)\s*%")


def _parse_blocks(text: str, header_re: re.Pattern) -> list[dict]:
    """Parse the multi-line block format `pactl list sinks` / `list
    sources` emits. Each block starts with `Sink #N` / `Source #N`."""
    blocks: list[dict] = []
    current: Optional[dict] = None

    for line in text.splitlines():
        m = header_re.match(line)
        if m:
            if current is not None:
                blocks.append(current)
            current = {"index": int(m.group(1)), "_props": {}}
            continue
        if current is None:
            continue
        if line.startswith("\t") or line.startswith(" "):
            key, _, val = line.strip().partition(":")
            key = key.strip()
            val = val.strip()
            if not key:
                continue
            # Some fields appear once (Name, Description, State, Mute).
            # We only record the first occurrence — properties listed
            # later (Volume, Channel Volumes, Channel Map …) we read
            # at their first hit too which is what we want.
            if key not in current["_props"]:
                current["_props"][key] = val
    if current is not None:
        blocks.append(current)

    out: list[dict] = []
    for b in blocks:
        props = b.pop("_props")
        b["name"] = props.get("Name", "")
        b["description"] = props.get("Description", "")
        b["driver"] = props.get("Driver", "")
        b["state"] = props.get("State", "")
        b["sample_spec"] = props.get("Sample Specification", "")
        # Mute: "no" / "yes"
        mute = props.get("Mute", "").lower()
        b["muted"] = mute == "yes" if mute in ("yes", "no") else None
        # Volume — first percentage we see in the Volume line
        vol_line = props.get("Volume", "")
        m = _VOLUME_PCT_RE.search(vol_line)
        b["volume_pct"] = int(m.group(1)) if m else None
        out.append(b)
    return out


# ----------------------------------------------------------------------
# Read tools
# ----------------------------------------------------------------------


def list_sinks() -> list[dict]:
    r = _pactl("list", "sinks")
    if r.returncode != 0:
        return [{"_error": f"pactl list sinks: {r.stderr.strip() or r.returncode}"}]
    return _parse_blocks(r.stdout, _SINK_HEADER_RE)


def list_sources(include_monitors: bool = False) -> list[dict]:
    r = _pactl("list", "sources")
    if r.returncode != 0:
        return [{"_error": f"pactl list sources: {r.stderr.strip() or r.returncode}"}]
    sources = _parse_blocks(r.stdout, _SOURCE_HEADER_RE)
    if include_monitors:
        return sources
    # Filter out `.monitor` sources — those are loopback taps from
    # output sinks and clutter the UI for "where can I record from?"
    return [s for s in sources if not s["name"].endswith(".monitor")]


def get_default_sink() -> Optional[str]:
    r = _pactl("get-default-sink")
    name = r.stdout.strip()
    return name or None


def get_volume(sink_id: Optional[str] = None) -> dict:
    target = sink_id or "@DEFAULT_SINK@"
    r = _pactl("get-sink-volume", target)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or f"pactl exit {r.returncode}", "sink_id": target}
    m = _VOLUME_PCT_RE.search(r.stdout)
    pct = int(m.group(1)) if m else None
    return {"sink_id": target, "volume_pct": pct, "raw": r.stdout.strip()}


def is_muted(sink_id: Optional[str] = None) -> dict:
    target = sink_id or "@DEFAULT_SINK@"
    r = _pactl("get-sink-mute", target)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or f"pactl exit {r.returncode}", "sink_id": target}
    # "Mute: yes" or "Mute: no"
    flag = r.stdout.strip().lower().endswith("yes")
    return {"sink_id": target, "muted": flag}


# ----------------------------------------------------------------------
# Write tools
# ----------------------------------------------------------------------


def set_volume(volume_pct: int, sink_id: Optional[str] = None) -> dict:
    # Hard ceiling — never above the safety cap. Above-unity (>100 %) is
    # explicitly NOT allowed regardless of pactl's support, to avoid
    # acoustic-feedback risk with the ceiling mic. See mcps/audio/safety.py
    # + docs/SAFETY.md.
    pct, capped = cap_volume(volume_pct)
    target = sink_id or "@DEFAULT_SINK@"
    r = _pactl("set-sink-volume", target, f"{pct}%")
    out: dict = {
        "sink_id": target,
        "volume_pct": pct,
        "ok": r.returncode == 0,
        "stderr": r.stderr.strip(),
    }
    if capped:
        out["capped"] = True
        out["requested_pct"] = int(volume_pct)
        out["ceiling_pct"] = max_output_volume_pct()
        out["note"] = (
            "Volume request exceeded the safety ceiling and was clamped. "
            "Override MAX_OUTPUT_VOLUME_PCT in .env only after reviewing "
            "docs/SAFETY.md."
        )
    return out


def set_mute(sink_id: Optional[str], muted: bool) -> dict:
    target = sink_id or "@DEFAULT_SINK@"
    r = _pactl("set-sink-mute", target, "1" if muted else "0")
    return {
        "sink_id": target,
        "muted": muted,
        "ok": r.returncode == 0,
        "stderr": r.stderr.strip(),
    }


# ----------------------------------------------------------------------
# Play sound (path-restricted to static/sounds/)
# ----------------------------------------------------------------------


def _resolve_sound_path(rel_path: str) -> Path:
    """Resolve a relative path inside SOUNDS_DIR. Refuses absolute
    paths and anything that escapes SOUNDS_DIR via `..`."""
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    candidate = Path(rel_path.lstrip("/"))
    if candidate.is_absolute():
        raise ValueError("absolute paths not allowed")
    full = (SOUNDS_DIR / candidate).resolve()
    try:
        full.relative_to(SOUNDS_DIR)
    except ValueError:
        raise ValueError(f"path {rel_path!r} escapes {SOUNDS_DIR}") from None
    if not full.is_file():
        raise FileNotFoundError(f"{rel_path!r} not found under static/sounds/")
    return full


def play_sound(file_path: str, sink_id: Optional[str] = None) -> dict:
    """Play a sound file from `static/sounds/` on the named sink (or
    default sink). Fires `paplay` in the background and returns
    immediately — long files don't block the MCP."""
    try:
        full = _resolve_sound_path(file_path)
    except (ValueError, FileNotFoundError) as e:
        return {"error": "invalid sound path", "detail": str(e)}

    args = [PAPLAY]
    if sink_id:
        args += ["--device", sink_id]
    args.append(str(full))

    try:
        # Spawn detached so we don't sit on the file's duration.
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=_audio_env(),
        )
    except FileNotFoundError:
        return {"error": "paplay not installed (pulseaudio-utils)"}

    return {
        "file_path": str(full.relative_to(SOUNDS_DIR)),
        "sink_id": sink_id,
        "pid": proc.pid,
        "started": True,
    }


# ----------------------------------------------------------------------
# Summary helper for the MCP's `list_audio_sinks` etc.
# ----------------------------------------------------------------------


def sink_summary() -> dict:
    """One call that returns sinks + default — what the MCP tool
    returns to keep payload sizes small."""
    try:
        sinks = list_sinks()
        default = get_default_sink()
    except PactlMissing as e:
        return {"error": str(e), "sinks": []}
    return {"default_sink": default, "sinks": sinks}


def source_summary(include_monitors: bool = False) -> dict:
    try:
        sources = list_sources(include_monitors=include_monitors)
    except PactlMissing as e:
        return {"error": str(e), "sources": []}
    return {"sources": sources}
