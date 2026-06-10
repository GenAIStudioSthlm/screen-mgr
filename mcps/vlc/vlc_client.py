"""Thin async client for VLC's HTTP control interface (/requests/*).

The target VLC must run with its Web interface enabled:
    vlc --extraintf=http --http-host=0.0.0.0 --http-port=<port> --http-password=<pw>

Auth is HTTP Basic with an EMPTY username and the http-password. Config
via env (so we can re-point at any station without code changes):
    VLC_HOST      (default 127.0.0.1)
    VLC_PORT      (default 8080)
    VLC_PASSWORD  (the --http-password)
"""

from __future__ import annotations

import os

import httpx  # bundled via the anthropic SDK dependency


class VLCError(Exception):
    """Raised for unreachable VLC or auth failure — callers turn this into
    a clean tool-result error instead of crashing the MCP loop."""


def _cfg() -> tuple[str, str, str]:
    return (
        os.environ.get("VLC_HOST", "127.0.0.1"),
        os.environ.get("VLC_PORT", "8080"),
        os.environ.get("VLC_PASSWORD", ""),
    )


async def _get(path: str, params: dict | None = None) -> dict:
    host, port, pw = _cfg()
    url = f"http://{host}:{port}/requests/{path}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params or {}, auth=("", pw))
    except httpx.RequestError as e:
        raise VLCError(
            f"VLC unreachable at {host}:{port} — is the Web interface on and "
            f"reachable? ({e.__class__.__name__})"
        ) from e
    if r.status_code == 401:
        raise VLCError("VLC auth failed — check VLC_PASSWORD")
    r.raise_for_status()
    return r.json()


async def status(params: dict | None = None) -> dict:
    """GET /requests/status.json (optionally carrying a command)."""
    return await _get("status.json", params)


async def command(cmd: str, **params) -> dict:
    """Issue a status command (pl_play, pl_pause, in_play, volume, …).
    Returns the resulting status.json so callers can summarize state."""
    p = {"command": cmd}
    p.update({k: v for k, v in params.items() if v is not None})
    return await _get("status.json", p)


async def browse(uri: str) -> dict:
    """List a directory ON THE VLC HOST (uri like file:///C:/Videos)."""
    return await _get("browse.json", {"uri": uri})


async def playlist() -> dict:
    return await _get("playlist.json")
