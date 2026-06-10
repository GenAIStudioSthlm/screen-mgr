"""VLC MCP server — control a remote VLC instance over its HTTP interface.

Lives in-process under the same uvicorn app; Claude Code / the chat agent
connect at http://<host>:8000/mcp/vlc/sse. The tools call the target VLC's
Web interface (see vlc_client.py) — so the video files stay on the VLC
host; the Pi just tells VLC which local path / URL to play.

Config via env: VLC_HOST / VLC_PORT / VLC_PASSWORD (the player), and
VLC_MEDIA_DIR (default folder for list_media).
"""

from __future__ import annotations

import os
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mcps.vlc import vlc_client as V


# LAN-only, trusted clients — same rationale as the other studio MCPs.
_TRANSPORT = TransportSecuritySettings(enable_dns_rebinding_protection=False)
server = FastMCP("vlc", transport_security=_TRANSPORT)

_MEDIA_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm", ".mpg", ".mpeg",
    ".wmv", ".flv", ".ts", ".m2ts", ".mp3", ".flac", ".wav", ".m4a", ".ogg",
}


def _to_uri(target: str) -> str:
    """A play target → a URI VLC accepts. Pass-through for anything that's
    already a URI (file://, http://, rtsp://, …); otherwise treat it as a
    path on the VLC host and build a file:// URI (Windows or POSIX)."""
    t = (target or "").strip()
    if "://" in t:
        return t
    p = t.replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p  # file:///C:/Videos/x.mp4
    return "file://" + quote(p)


async def _safe(coro) -> dict:
    try:
        return await coro
    except V.VLCError as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001 — surface to the model, don't crash
        return {"error": "vlc call failed", "detail": repr(e)}


def _summarize(st: dict) -> dict:
    """Pull a compact view out of VLC's verbose status.json."""
    if not isinstance(st, dict) or "error" in st:
        return st
    meta = {}
    info = st.get("information")
    if isinstance(info, dict):
        cat = info.get("category")
        if isinstance(cat, dict):
            meta = cat.get("meta") or {}
    vol = st.get("volume")
    return {
        "state": st.get("state"),
        "volume_pct": round(vol / 256 * 100) if isinstance(vol, (int, float)) else None,
        "now_playing": meta.get("filename") or meta.get("title"),
        "length_s": st.get("length"),
        "time_s": st.get("time"),
        "fullscreen": bool(st.get("fullscreen")),
    }


@server.tool()
async def get_status() -> dict:
    """Current VLC state: playing/paused/stopped, volume %, now-playing
    title, position, and fullscreen flag."""
    return _summarize(await _safe(V.status()))


@server.tool()
async def list_media(folder: str = "") -> dict:
    """List playable media in a folder ON THE VLC HOST machine.

    `folder` is a path on that machine (e.g. "C:/Videos" or "/home/me/clips");
    defaults to the VLC_MEDIA_DIR env var. Returns ``files`` (each with a
    ``uri`` to hand straight to `play`) and ``subfolders`` for drilling in."""
    folder = folder or os.environ.get("VLC_MEDIA_DIR", "")
    if not folder:
        return {"error": "no folder given and VLC_MEDIA_DIR not set"}
    res = await _safe(V.browse(_to_uri(folder)))
    if "error" in res:
        return res
    files, dirs = [], []
    for e in res.get("element", []) or []:
        name = e.get("name")
        if name in (".", ".."):
            continue
        if e.get("type") == "dir":
            dirs.append({"name": name, "path": e.get("path"), "uri": e.get("uri")})
        elif os.path.splitext(name or "")[1].lower() in _MEDIA_EXTS:
            files.append({"name": name, "uri": e.get("uri")})
    return {"folder": folder, "files": files, "subfolders": dirs}


@server.tool()
async def play(target: str, fresh: bool = True) -> dict:
    """Play a media file or stream on VLC.

    `target`: a ``uri`` from list_media (file://…), a path on the VLC host,
    or an http(s)/rtsp stream URL. `fresh=True` clears the current playlist
    first so only this item plays."""
    uri = _to_uri(target)
    if fresh:
        await _safe(V.command("pl_empty"))
    res = await _safe(V.command("in_play", input=uri))
    if isinstance(res, dict) and "error" in res:
        return res
    return {"playing": uri, **_summarize(res)}


@server.tool()
async def enqueue(target: str) -> dict:
    """Add a file/stream to the playlist without interrupting playback."""
    res = await _safe(V.command("in_enqueue", input=_to_uri(target)))
    return res if "error" in res else {"enqueued": _to_uri(target)}


@server.tool()
async def pause() -> dict:
    """Toggle pause / resume."""
    return _summarize(await _safe(V.command("pl_pause")))


@server.tool()
async def stop() -> dict:
    """Stop playback."""
    return _summarize(await _safe(V.command("pl_stop")))


@server.tool()
async def next_item() -> dict:
    """Skip to the next playlist item."""
    return _summarize(await _safe(V.command("pl_next")))


@server.tool()
async def previous_item() -> dict:
    """Go to the previous playlist item."""
    return _summarize(await _safe(V.command("pl_previous")))


@server.tool()
async def set_volume(percent: int) -> dict:
    """Set VLC volume, 0–125 % (VLC's 256 = 100 %)."""
    pct = max(0, min(125, int(percent)))
    res = await _safe(V.command("volume", val=round(pct / 100 * 256)))
    return res if "error" in res else {"volume_pct": pct}


@server.tool()
async def toggle_fullscreen() -> dict:
    """Toggle VLC fullscreen on the player's screen."""
    return _summarize(await _safe(V.command("fullscreen")))
