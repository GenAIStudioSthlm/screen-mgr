"""Dante / AES67 stream discovery via SAP (Session Announcement Protocol).

Sennheiser TCC ceiling mics announce their Dante multicast audio
streams over SAP on `239.255.255.255:9875` — same well-known port
every AES67-compatible piece of pro audio gear uses. Each announcement
carries an SDP payload describing the multicast group, port, codec,
channels, and sample rate that other devices need to receive the
audio.

This module is a passive listener — we never transmit SAP. We just
join the SAP multicast group, read announcements for a few seconds,
and parse the SDP. Useful to:

  - Confirm a mic is actually pumping audio (vs. just being on the
    network — SSC discovery only proves the control plane is alive)
  - Surface the parameters a future GStreamer / FFmpeg receive
    pipeline will need (multicast group, port, payload type)
  - Document the studio's audio topology for the operator

Output of `discover_streams` is a flat list of stream dicts, each:

    {
      "source_ip": "192.168.2.219",     # who announced it
      "name": "LocalOut@TCCM-2bb2c2",   # session name from `s=`
      "multicast_group": "239.69.219.0", # from `c=`
      "port": 5004,                       # from `m=audio`
      "payload_type": 96,                 # from `m=`
      "codec": "L24",                     # from `a=rtpmap`
      "sample_rate": 48000,
      "channels": 64,
      "raw_sdp": "...",                   # full SDP text for debugging
    }

References:
  RFC 2974 (SAP), RFC 4566 (SDP), AES67-2018, RFC 3190 (L16/L24/L20 RTP).
"""

from __future__ import annotations

import re
import select
import socket
import struct
import time
from typing import Optional


SAP_GROUP = "239.255.255.255"
SAP_PORT = 9875

# Defensive read sizes — SAP packets are typically <500 bytes; cap at
# 4 KiB to handle implementations that pack more attributes.
SAP_MAX_PACKET = 4096
DEFAULT_LISTEN_SECONDS = 5.0


# ---------------------------------------------------------------------------
# SAP header parsing
# ---------------------------------------------------------------------------


def _parse_sap_header(data: bytes) -> Optional[dict]:
    """Parse the SAP header, return a dict with the SDP byte offset
    plus deletion-flag/source-ip metadata. None if malformed."""
    if len(data) < 8:
        return None
    flags = data[0]
    version = (flags >> 5) & 0x7
    if version != 1:
        # Future SAP versions — we still try, log gracefully.
        pass
    addr_type = (flags >> 4) & 0x1   # 0 = IPv4, 1 = IPv6
    deletion = (flags >> 2) & 0x1
    encrypted = (flags >> 1) & 0x1
    compressed = flags & 0x1
    auth_len = data[1]                # 32-bit words
    msg_id = (data[2] << 8) | data[3]

    addr_size = 16 if addr_type else 4
    if len(data) < 4 + addr_size:
        return None
    source_bytes = data[4:4 + addr_size]
    source_ip = (
        ".".join(str(b) for b in source_bytes)
        if addr_size == 4
        else ":".join(f"{a:02x}{b:02x}" for a, b in zip(source_bytes[0::2], source_bytes[1::2]))
    )

    # Skip the authentication block (auth_len 32-bit words)
    pos = 4 + addr_size + (auth_len * 4)
    if pos > len(data):
        return None

    # Optional payload-type field: NUL-terminated string. RFC 2974 §6
    # says the field is "optional" — if missing, payload is SDP. We
    # detect by checking whether the next bytes look like a MIME type.
    payload_type = "application/sdp"
    if pos < len(data):
        nul = data.find(b"\0", pos)
        if 0 <= nul - pos < 40:
            candidate = data[pos:nul]
            if b"/" in candidate:
                try:
                    payload_type = candidate.decode("ascii")
                    pos = nul + 1
                except UnicodeDecodeError:
                    pass

    return {
        "version": version,
        "deletion": bool(deletion),
        "encrypted": bool(encrypted),
        "compressed": bool(compressed),
        "msg_id": msg_id,
        "source_ip": source_ip,
        "payload_type": payload_type,
        "sdp_offset": pos,
    }


# ---------------------------------------------------------------------------
# SDP parsing (minimal — only what we need from AES67 announcements)
# ---------------------------------------------------------------------------


_RTPMAP_RE = re.compile(
    r"^rtpmap:(?P<pt>\d+)\s+(?P<codec>[A-Za-z0-9]+)/(?P<rate>\d+)(?:/(?P<channels>\d+))?$"
)


def _parse_sdp(sdp: str) -> dict:
    """Pull out the fields AES67 announcements care about. Returns
    a partial dict — missing fields are simply absent."""
    out: dict = {"name": None, "multicast_group": None, "port": None}
    media = None
    attrs: list[str] = []

    for raw in sdp.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key == "s":
            out["name"] = value
        elif key == "o":
            out["origin"] = value
        elif key == "c":
            # e.g. "IN IP4 239.69.219.0/32"
            parts = value.split()
            if len(parts) >= 3:
                out["multicast_group"] = parts[2].split("/")[0]
        elif key == "m":
            # e.g. "audio 5004 RTP/AVP 96"
            parts = value.split()
            if len(parts) >= 4 and parts[0] == "audio":
                try:
                    out["port"] = int(parts[1])
                except ValueError:
                    pass
                out["proto"] = parts[2]
                try:
                    out["payload_type"] = int(parts[3])
                except ValueError:
                    out["payload_type"] = parts[3]
                media = "audio"
        elif key == "a" and media == "audio":
            attrs.append(value)

    # rtpmap → codec + rate + channels
    for a in attrs:
        m = _RTPMAP_RE.match(a)
        if m:
            out["codec"] = m.group("codec")
            try:
                out["sample_rate"] = int(m.group("rate"))
            except ValueError:
                pass
            if m.group("channels"):
                try:
                    out["channels"] = int(m.group("channels"))
                except ValueError:
                    pass
            break

    # ptime (packet time in ms) and a few common AES67 attrs
    for a in attrs:
        if a.startswith("ptime:"):
            try:
                out["ptime_ms"] = float(a.split(":", 1)[1])
            except ValueError:
                pass
        elif a.startswith("mediaclk:"):
            out["media_clock"] = a[len("mediaclk:"):]
        elif a.startswith("ts-refclk:"):
            out["ts_refclk"] = a[len("ts-refclk:"):]

    return out


# ---------------------------------------------------------------------------
# Listener
# ---------------------------------------------------------------------------


def _open_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # SO_REUSEPORT not available on all platforms — best-effort.
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    sock.bind(("", SAP_PORT))
    mreq = struct.pack(
        "4s4s",
        socket.inet_aton(SAP_GROUP),
        socket.inet_aton("0.0.0.0"),
    )
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    return sock


def discover_streams(timeout: float = DEFAULT_LISTEN_SECONDS) -> list[dict]:
    """Listen on SAP for `timeout` seconds, return one entry per
    unique stream announcement.

    Stream key for deduplication: (source_ip, msg_id) — the same
    announcer broadcasts the same SAP message repeatedly while a
    stream is active. We deduplicate so the result is one row per
    stream, not one row per packet.
    """
    try:
        sock = _open_socket()
    except OSError as e:
        return [{"_error": f"could not open SAP socket on port {SAP_PORT}: {e}"}]

    deadline = time.monotonic() + max(0.5, timeout)
    seen: dict[tuple[str, int], dict] = {}
    try:
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            ready, _, _ = select.select([sock], [], [], min(0.5, remaining))
            if not ready:
                continue
            data, _ = sock.recvfrom(SAP_MAX_PACKET)
            header = _parse_sap_header(data)
            if header is None or header["encrypted"] or header["compressed"]:
                continue
            if header["payload_type"] != "application/sdp":
                continue
            sdp_bytes = data[header["sdp_offset"]:]
            try:
                sdp_text = sdp_bytes.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            parsed = _parse_sdp(sdp_text)
            key = (header["source_ip"], header["msg_id"])
            seen[key] = {
                "source_ip": header["source_ip"],
                "deletion": header["deletion"],
                **parsed,
                "raw_sdp": sdp_text,
            }
    finally:
        try:
            mreq = struct.pack(
                "4s4s",
                socket.inet_aton(SAP_GROUP),
                socket.inet_aton("0.0.0.0"),
            )
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
        except OSError:
            pass
        sock.close()

    # Sort by source IP then name for stable output.
    return sorted(
        seen.values(),
        key=lambda s: (s.get("source_ip") or "", s.get("name") or ""),
    )
