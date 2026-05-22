"""Audio MCP server — STUB.

Stakes out the tool surface the orchestrator + future agents will use
to control studio audio (system playback sinks, microphones, sound
playback). Every tool returns ``{"stub": true, ...}`` until a real
backend is wired (PulseAudio via `pactl` is the planned choice).

When implementing for real, replace each tool body with calls into the
chosen backend (pactl/PipeWire/ALSA). The tool *names and signatures*
in this file are the API contract — keep them stable so the agent
prompts and skills written against them don't need to change.

Mounted at /mcp/audio/sse next to the other MCP servers.
"""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


_TRANSPORT = TransportSecuritySettings(enable_dns_rebinding_protection=False)
server = FastMCP("audio", transport_security=_TRANSPORT)


_STUB_NOTE = (
    "Audio MCP is a stub. Wire to PulseAudio / pactl (or ALSA) to "
    "implement. See mcps/audio/server.py — tool signatures are stable."
)


def _stub(name: str, **extras) -> dict:
    return {"stub": True, "tool": name, "note": _STUB_NOTE, **extras}


# --------------------------------------------------------------------------
# Tools — read
# --------------------------------------------------------------------------


@server.tool()
def list_audio_sinks() -> dict:
    """List system audio output devices (HDMI, USB DAC, headphones, ...).

    STUB — returns an empty list with a note. Real implementation:
    parse `pactl list short sinks`."""
    return _stub("list_audio_sinks", sinks=[])


@server.tool()
def list_audio_sources() -> dict:
    """List system audio input devices (microphones, line-in, ...).

    STUB — returns an empty list with a note. Real implementation:
    parse `pactl list short sources` and drop monitor-of-* sources."""
    return _stub("list_audio_sources", sources=[])


@server.tool()
def get_volume(sink_id: Optional[str] = None) -> dict:
    """Get current playback volume (0–100). ``sink_id=None`` means the
    default sink.

    STUB. Real impl: parse `pactl get-sink-volume <sink_id>`."""
    return _stub("get_volume", sink_id=sink_id, volume_pct=None)


@server.tool()
def is_muted(sink_id: Optional[str] = None) -> dict:
    """Mute state of a sink. STUB. Real impl: `pactl get-sink-mute <sink_id>`."""
    return _stub("is_muted", sink_id=sink_id, muted=None)


# --------------------------------------------------------------------------
# Tools — write
# --------------------------------------------------------------------------


@server.tool()
def set_volume(volume_pct: int, sink_id: Optional[str] = None) -> dict:
    """Set sink volume (0–100). STUB. Real impl: `pactl set-sink-volume`."""
    return _stub("set_volume", sink_id=sink_id, volume_pct=volume_pct)


@server.tool()
def mute(sink_id: Optional[str] = None) -> dict:
    """Mute a sink. STUB. Real impl: `pactl set-sink-mute <sink_id> 1`."""
    return _stub("mute", sink_id=sink_id)


@server.tool()
def unmute(sink_id: Optional[str] = None) -> dict:
    """Unmute a sink. STUB."""
    return _stub("unmute", sink_id=sink_id)


@server.tool()
def play_sound(file_path: str, sink_id: Optional[str] = None) -> dict:
    """Play a local sound file (.wav, .mp3, ...) on a sink.

    STUB. Real impl: spawn `paplay <file>` (or `aplay` for ALSA).
    Asynchronous in practice — return as soon as playback starts."""
    return _stub("play_sound", file_path=file_path, sink_id=sink_id)
