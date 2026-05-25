"""HEOS CLI client for the Marantz Cinema 70s (and any HEOS-compatible
Denon/Marantz receiver that drives the studio's speakers).

HEOS is Denon/Marantz's network audio protocol. Plain-text JSON commands
over TCP/1255 on the receiver's IP. We use it to:

  - Set/get the receiver's master volume (mapped onto the HEOS 0–100 scale)
  - Play arbitrary HTTP audio URLs out the speakers (`player/play_stream`)
  - Pause / stop / resume
  - Inspect what's currently playing (source id, song metadata)

The Pi only ever talks to the **one** HEOS endpoint configured via
`MARANTZ_HEOS_HOST` / `MARANTZ_HEOS_PORT` env vars — never broadcasts,
never discovers, never enumerates. Point-to-point only.

Volume calibration (logged in `docs/SAFETY.md`):

    HEOS 10  → ~-60 dB    inaudible
    HEOS 25  → ~-45 dB    very low / whisper
    HEOS 50  → ~-25 dB    comfortable / regular listening
    HEOS 70  → ~-15 dB    loud — at our safety cap
    HEOS 100 →  ~ 0 dB    very loud — refused by `cap_volume`

The HEOS volume scale is essentially an attenuation in dB, **not**
perceived loudness percent. Don't think "50 % = half as loud"; think
"50 = comfortable, 70 = loud, anything above is shouting".
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional


DEFAULT_PORT = 1255
DEFAULT_TIMEOUT = 4.0


class HEOSNotConfigured(RuntimeError):
    """Raised when MARANTZ_HEOS_HOST isn't in .env.

    Caller catches this and returns a friendly error dict, mirroring
    the Spotify "not configured" degradation pattern."""


class HEOSError(RuntimeError):
    """Raised when the receiver replies with `result: fail`.

    The HEOS message field is included so the operator can see what
    the receiver actually complained about."""


def _endpoint() -> tuple[str, int]:
    host = os.environ.get("MARANTZ_HEOS_HOST", "").strip()
    if not host:
        raise HEOSNotConfigured(
            "MARANTZ_HEOS_HOST not set in .env — point-to-point HEOS "
            "to the Marantz can't run without an IP. See "
            "docs/EXTERNAL_INTEGRATION.md."
        )
    try:
        port = int(os.environ.get("MARANTZ_HEOS_PORT", DEFAULT_PORT))
    except ValueError:
        port = DEFAULT_PORT
    return host, port


class HEOSClient:
    """Async HEOS client. One persistent TCP connection per instance,
    protected by an asyncio.Lock so concurrent calls serialise (HEOS
    is a single-request-at-a-time protocol per connection).

    Lazy connect — first call opens the socket; subsequent calls reuse
    it. On failure we close + reset and next call reconnects.
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                 timeout: float = DEFAULT_TIMEOUT):
        if host is None or port is None:
            ep_host, ep_port = _endpoint()
            host = host or ep_host
            port = port or ep_port
        self.host = host
        self.port = port
        self.timeout = timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()
        # Cached player id from the first get_players call. HEOS player
        # ids are stable per device, so we only need this once.
        self._pid: Optional[int] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def _ensure_connected(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            return
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.timeout,
        )

    async def close(self) -> None:
        if self._writer is None:
            return
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        self._writer = None
        self._reader = None

    # ------------------------------------------------------------------
    # Raw command — used by every higher-level method
    # ------------------------------------------------------------------

    async def cmd(self, path: str, **params: Any) -> dict:
        """Send `heos://{path}?{params}` and return the parsed JSON response.

        Raises HEOSError on `result: fail`, propagates connection errors
        (after resetting the connection so the next call reconnects).
        """
        # Build params string. HEOS doesn't URL-encode values — paths
        # like URLs are passed as-is between `=` and the next `&` or EOL.
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        line = f"heos://{path}" + (f"?{qs}" if qs else "") + "\r\n"

        async with self._lock:
            try:
                await self._ensure_connected()
                assert self._writer is not None and self._reader is not None
                self._writer.write(line.encode())
                await self._writer.drain()
                raw = await asyncio.wait_for(
                    self._reader.readline(),
                    timeout=self.timeout,
                )
            except Exception:
                # Reset the connection on any failure so the next call
                # gets a fresh socket.
                await self.close()
                raise

        try:
            data = json.loads(raw.decode().strip())
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise HEOSError(f"non-JSON response: {raw[:200]!r}") from e

        heos = data.get("heos") or {}
        if heos.get("result") == "fail":
            raise HEOSError(
                f"HEOS {heos.get('command')}: {heos.get('message')!r}"
            )
        return data

    # ------------------------------------------------------------------
    # Player discovery — cached
    # ------------------------------------------------------------------

    async def pid(self) -> int:
        """Return the player id of the configured Marantz. The first
        call fetches it via `player/get_players` and caches; subsequent
        calls are free.

        If multiple players are visible (multi-HEOS setup), this picks
        the one whose IP matches the configured host."""
        if self._pid is not None:
            return self._pid
        resp = await self.cmd("player/get_players")
        players = resp.get("payload") or []
        if not players:
            raise HEOSError("get_players returned no players")
        # Prefer the player whose IP matches our endpoint host.
        match = next((p for p in players if p.get("ip") == self.host), None)
        target = match or players[0]
        if "pid" not in target:
            raise HEOSError(f"player has no pid: {target!r}")
        self._pid = int(target["pid"])
        return self._pid

    # ------------------------------------------------------------------
    # High-level convenience methods
    # ------------------------------------------------------------------

    async def get_now_playing(self) -> dict:
        pid = await self.pid()
        return await self.cmd("player/get_now_playing_media", pid=pid)

    async def get_play_state(self) -> str:
        pid = await self.pid()
        resp = await self.cmd("player/get_play_state", pid=pid)
        # message looks like "pid=...&state=play"
        msg = (resp.get("heos") or {}).get("message", "")
        for part in msg.split("&"):
            if part.startswith("state="):
                return part[6:]
        return "unknown"

    async def get_volume(self) -> int:
        pid = await self.pid()
        resp = await self.cmd("player/get_volume", pid=pid)
        msg = (resp.get("heos") or {}).get("message", "")
        for part in msg.split("&"):
            if part.startswith("level="):
                try:
                    return int(part[6:])
                except ValueError:
                    return -1
        return -1

    async def set_volume(self, level: int) -> dict:
        """Set HEOS volume (0-100). Caller is expected to have already
        passed `level` through `mcps.audio.safety.cap_volume`."""
        pid = await self.pid()
        return await self.cmd("player/set_volume", pid=pid, level=int(level))

    async def play_stream(self, url: str) -> dict:
        """Tell the Marantz to fetch + play the audio at `url`. The
        receiver pulls the file itself; we don't proxy bytes."""
        pid = await self.pid()
        return await self.cmd("player/play_stream", pid=pid, url=url)

    async def pause(self) -> dict:
        pid = await self.pid()
        return await self.cmd("player/set_play_state", pid=pid, state="pause")

    async def play(self) -> dict:
        pid = await self.pid()
        return await self.cmd("player/set_play_state", pid=pid, state="play")

    async def stop(self) -> dict:
        pid = await self.pid()
        return await self.cmd("player/set_play_state", pid=pid, state="stop")

    async def heart_beat(self) -> dict:
        return await self.cmd("system/heart_beat")

    async def player_info(self) -> dict:
        pid = await self.pid()
        return await self.cmd("player/get_player_info", pid=pid)


# Module-level singleton so callers don't each open their own connection.
# Initialised lazily — first `get_client()` call constructs it.
_client: Optional[HEOSClient] = None


def get_client() -> HEOSClient:
    """Return the process-wide HEOS client. Raises HEOSNotConfigured
    if MARANTZ_HEOS_HOST isn't set."""
    global _client
    if _client is None:
        _client = HEOSClient()
    return _client
