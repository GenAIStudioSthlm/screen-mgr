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

from mcps.audio.microphones import (
    discover_microphones as _discover_microphones,
    get_microphone_state as _get_microphone_state,
    run_mic_test as _run_mic_test,
    set_microphone_mute as _set_microphone_mute,
)
from mcps.audio import pactl_backend as _pa
from mcps.audio.streams import discover_streams as _discover_streams


_TRANSPORT = TransportSecuritySettings(enable_dns_rebinding_protection=False)
server = FastMCP("audio", transport_security=_TRANSPORT)


# --------------------------------------------------------------------------
# Tools — read (REAL — PulseAudio via pactl)
# --------------------------------------------------------------------------


@server.tool()
def list_audio_sinks() -> dict:
    """List system audio output devices (HDMI, USB DAC, the dummy
    sink when no hardware is wired).

    Each entry: ``index``, ``name`` (use with the other tools),
    ``description`` (human label), ``state`` (RUNNING / IDLE /
    SUSPENDED), ``volume_pct``, ``muted``, ``driver`` (PipeWire /
    ALSA), and ``sample_spec``. Also returns ``default_sink``.
    """
    return _pa.sink_summary()


@server.tool()
def list_audio_sources() -> dict:
    """List system audio input devices (microphones, line-in).

    Filters out ``.monitor`` sources by default — those are loopback
    taps from output sinks; not what you typically want to record
    from."""
    return _pa.source_summary()


@server.tool()
def get_volume(sink_id: Optional[str] = None) -> dict:
    """Current playback volume (0–100) for ``sink_id`` (default sink
    if None). Pass a name from `list_audio_sinks` or
    ``@DEFAULT_SINK@``."""
    return _pa.get_volume(sink_id)


@server.tool()
def is_muted(sink_id: Optional[str] = None) -> dict:
    """Mute state of a sink. Default sink if ``sink_id=None``."""
    return _pa.is_muted(sink_id)


# --------------------------------------------------------------------------
# Tools — write (REAL — PulseAudio via pactl)
# --------------------------------------------------------------------------


@server.tool()
def set_volume(volume_pct: int, sink_id: Optional[str] = None) -> dict:
    """Set sink volume (0–150, clamped). Above 100 = above unity gain,
    PulseAudio allows it. Default sink if ``sink_id=None``."""
    return _pa.set_volume(volume_pct, sink_id)


@server.tool()
def mute(sink_id: Optional[str] = None) -> dict:
    """Mute a sink."""
    return _pa.set_mute(sink_id, True)


@server.tool()
def unmute(sink_id: Optional[str] = None) -> dict:
    """Unmute a sink."""
    return _pa.set_mute(sink_id, False)


@server.tool()
def play_sound(file_path: str, sink_id: Optional[str] = None) -> dict:
    """Play a sound file from ``static/sounds/`` on the named sink (or
    default sink).

    ``file_path`` is relative to ``static/sounds/`` — absolute paths
    and ``..`` are refused, so the MCP can't be coerced into playing
    arbitrary files off the Pi. Drop .wav / .mp3 / .ogg files in
    that directory to make them playable.

    Fires `paplay` in the background, returns immediately with the
    child PID. The file's full duration plays out without blocking."""
    return _pa.play_sound(file_path, sink_id)


# --------------------------------------------------------------------------
# Tools — microphones (REAL — first non-stub of the Audio MCP)
# --------------------------------------------------------------------------


@server.tool()
def list_microphones() -> dict:
    """Discover networked microphones on the LAN.

    Uses mDNS (`_ssc-https._tcp`) to find Sennheiser TeamConnect
    ceiling mics — including the TCC M S W in the studio. Future
    revisions will also browse Dante (`_netaudio-*`), USB devices,
    and any other registered input-device modules.

    Each entry includes: ``id`` (use with the other mic tools),
    ``friendly_name``, ``hostname``, ``ip``, ``vendor``, ``model``,
    and ``control_url`` (the device's HTTPS admin page).
    """
    return {"microphones": _discover_microphones()}


@server.tool()
def get_microphone_state(mic_id: str) -> dict:
    """Fetch the full SSC state from a mic by id, hostname, or IP.

    Returns whatever the device exposes at ``/api/ssc/state`` — for
    Sennheiser TCC this is a deep JSON tree covering channel levels,
    mute, gain, identify, beam steering, etc. Useful for "what is
    this mic actually doing right now" diagnostics."""
    return _get_microphone_state(mic_id)


@server.tool()
def mute_microphone(mic_id: str) -> dict:
    """Mute a microphone via its SSC API (Sennheiser TCC family).
    Returns the HTTP status + any body the device returns."""
    return _set_microphone_mute(mic_id, True)


@server.tool()
def unmute_microphone(mic_id: str) -> dict:
    """Unmute a microphone via its SSC API."""
    return _set_microphone_mute(mic_id, False)


@server.tool()
def run_mic_test(mic_id: str, probes: int = 3) -> dict:
    """Reachability self-test for a microphone — runs N HTTPS
    handshakes against the device and reports per-probe status +
    latency. Useful "is this mic on the network and answering" check.

    Note: this is *not* the LED-flash test originally planned. The
    TCC's SSC REST endpoints return 404 on the current firmware;
    real LED flash / mute control needs SSC2 (JSON-RPC over
    WebSockets) implemented — tracked in PLAN_AGENTIC Phase 11."""
    return _run_mic_test(mic_id, probes=probes)


@server.tool()
def list_audio_streams(timeout_seconds: float = 5.0) -> dict:
    """Discover Dante / AES67 audio streams on the LAN by passively
    listening to SAP (Session Announcement Protocol) announcements
    for ``timeout_seconds`` (default 5s, capped at 30s).

    Each entry carries the SDP-derived parameters a downstream
    receiver needs to consume the stream: ``multicast_group``,
    ``port``, ``codec`` (typically ``L24`` or ``L16``),
    ``sample_rate``, ``channels``, ``payload_type``, plus the
    ``source_ip`` of the announcer.

    Use this to confirm a mic is actively producing audio (vs. just
    being on the network) and to grab the multicast group + port a
    GStreamer / FFmpeg pipeline will need."""
    timeout = max(0.5, min(30.0, float(timeout_seconds)))
    return {"streams": _discover_streams(timeout=timeout)}
