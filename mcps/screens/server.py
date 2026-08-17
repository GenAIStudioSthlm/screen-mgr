"""Screens MCP server — exposes the display stations + scenes + media.

Lives in-process under the same uvicorn app as the rest of screen-mgr.
External MCP clients connect to /mcp/screens/sse over the SSE transport.

Tools wrap the existing Python managers directly (screen_manager,
scene_manager, registry) instead of re-routing through /api/* — same
in-process pattern as the Lighting MCP, one less hop, no HTTP roundtrip.
"""

from __future__ import annotations

import os
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from connections import connection_manager
from models.scenes import scene_manager
from modules import registry
from modules.base import DisplayModule
from screens import screen_manager

from mcps.screens.fleet_demo import run_fleet_demo as _run_fleet_demo
from mcps.screens.walkthrough import run_content_walkthrough as _run_walkthrough


# LAN-only deployment; see mcps/lighting/server.py for the rationale.
_TRANSPORT = TransportSecuritySettings(enable_dns_rebinding_protection=False)

server = FastMCP("screens", transport_security=_TRANSPORT)


# Where the upload routes already stash media. Kept in sync with
# routes/api_routes.py (PICTURE_FOLDER / VIDEO_FOLDER / PDF_FOLDER).
PICTURE_FOLDER = "static/pictures"
VIDEO_FOLDER = "static/videos"
PDF_FOLDER = "static/pdfs"

# Type-specific value field on the Screen model.
_CONTENT_VALUE_FIELD = {
    "text": "text",
    "url": "url",
    "video": "video",
    "picture": "picture",
    "pdf": "pdf",
    "slideshow": "slideshow",
    "screen_share": "screen_share",
}


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _enabled_display_module_ids() -> set[str]:
    """Display module ids the operator can currently target.

    Mirrors the validation in `routes/api_routes.py::set_screen_content`
    so the MCP tool refuses content types the HTTP route would also
    refuse."""
    return {
        m.id
        for m in registry.list()
        if isinstance(m, DisplayModule) and registry.is_enabled(m.id)
    }


def _find_screen(screen_id: int):
    return next((s for s in screen_manager.screens if s.id == screen_id), None)


def _list_dir(path: str, exts: tuple[str, ...]) -> list[str]:
    if not os.path.isdir(path):
        return []
    return sorted(
        f for f in os.listdir(path)
        if f.lower().endswith(exts) and os.path.isfile(os.path.join(path, f))
    )


def _list_subfolders(path: str) -> list[str]:
    if not os.path.isdir(path):
        return []
    return sorted(
        f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))
    )


# --------------------------------------------------------------------------
# Tools — read
# --------------------------------------------------------------------------


@server.tool()
def list_screens() -> dict:
    """List every display station with its current state.

    Each entry includes ``id`` (1-based, used by every other tool),
    ``name``, ``type`` (the current content type), the value of the
    type-specific field (e.g. ``url`` when type=='url'), ``connected``
    (WebSocket alive?), and ``client_host`` (last-known IP).
    """
    return {
        "screens": [
            screen.model_dump(exclude={"websocket"})
            for screen in screen_manager.screens
        ]
    }


@server.tool()
def list_scenes() -> dict:
    """List saved Studio scenes (NOT Hue bridge scenes — those live on
    the Lighting MCP as a separate `list_scenes`).

    Each Studio scene bundles an optional Hue scene id plus a set of
    per-zone screen-content overrides. Apply with `apply_scene(scene_id)`.
    """
    return {"scenes": [s.model_dump() for s in scene_manager.scenes]}


@server.tool()
def list_content_types() -> dict:
    """List the display-module content types currently enabled in the
    module registry. These are the valid values for the ``content_type``
    argument of `set_screen_content`.

    Typical ids: ``default``, ``text``, ``url``, ``video``, ``picture``,
    ``pdf``, ``slideshow``, ``news``, ``screen_share``.
    """
    enabled = sorted(_enabled_display_module_ids())
    return {"content_types": enabled}


@server.tool()
def list_media() -> dict:
    """List every piece of media available on disk for the screens.

    Returns a dict with four keys: ``pictures`` (flat list of files in
    static/pictures/), ``videos``, ``pdfs``, and ``slideshows``
    (subfolders of static/pictures/ — each is a sequence of images).

    Use these values for the ``content_value`` argument of
    `set_screen_content`.
    """
    return {
        "pictures": _list_dir(PICTURE_FOLDER, (".png", ".jpg", ".jpeg", ".gif")),
        "videos": _list_dir(VIDEO_FOLDER, (".mp4", ".webm", ".mov", ".m4v")),
        "pdfs": _list_dir(PDF_FOLDER, (".pdf",)),
        "slideshows": _list_subfolders(PICTURE_FOLDER),
    }


# --------------------------------------------------------------------------
# Tools — write
# --------------------------------------------------------------------------


@server.tool()
async def set_screen_content(
    screen_id: int, content_type: str, content_value: str = ""
) -> dict:
    """Set what a screen is showing.

    - ``screen_id``: the 1-based id from `list_screens`.
    - ``content_type``: one of the values from `list_content_types`
      (e.g. ``url``, ``picture``, ``video``, ``pdf``, ``news``, ``default``).
    - ``content_value``: the type-specific value:
        - ``text`` → the string to display
        - ``url`` → full URL (including https://; works for YouTube embed URLs too)
        - ``video`` / ``pdf`` → filename from `list_media`
        - ``picture`` → **folder-prefixed** path ``<folder>/<file>`` from
          `list_media` (e.g. ``IKEA/Cloud_2.png`` for a subfolder, or
          ``Root/logo.png`` for a top-level file). A BARE filename renders
          blank ("not found") — the folder is required.
        - ``slideshow`` → folder name from `list_media`
        - ``screen_share`` → room id string
        - ``news`` → display mode: ``portrait``, ``landscape``, or ``presentation``
        - ``default`` → ignored (the studio logo doesn't take a value)

    Persists the new state to screens.json and tells the screen to
    reload via its WebSocket (if connected). Returns a small summary.
    """
    screen = _find_screen(screen_id)
    if screen is None:
        return {"error": f"screen_id {screen_id} not found"}

    valid_types = _enabled_display_module_ids()
    if content_type not in valid_types:
        return {
            "error": f"invalid content_type '{content_type}'",
            "valid": sorted(valid_types),
        }

    screen.type = content_type
    field = _CONTENT_VALUE_FIELD.get(content_type)
    if field is not None:
        setattr(screen, field, content_value or "")
    if content_type == "news" and content_value in {"portrait", "landscape", "presentation"}:
        screen.news_mode = content_value
    # "default" needs no value — type alone routes to the studio logo.

    screen_manager.save_screens()

    notified = False
    notify_error: Optional[str] = None
    if screen.connected:
        try:
            await connection_manager.notify_screen(screen=screen)
            notified = True
        except Exception as e:  # noqa: BLE001
            notify_error = str(e)

    return {
        "screen_id": screen.id,
        "type": screen.type,
        "value": getattr(screen, field, None) if field else None,
        "notified": notified,
        "notify_error": notify_error,
    }


@server.tool()
async def reload_screen(screen_id: int) -> dict:
    """Force a single screen to reload its current content over WebSocket.

    Useful after fixing a stuck client, or to bounce one station without
    touching the others. Returns ``{"notified": false, "reason": ...}``
    if the screen has no live WebSocket connection."""
    screen = _find_screen(screen_id)
    if screen is None:
        return {"error": f"screen_id {screen_id} not found"}
    if not screen.connected:
        return {"screen_id": screen_id, "notified": False, "reason": "not connected"}
    try:
        await connection_manager.notify_screen(screen=screen)
    except Exception as e:  # noqa: BLE001
        return {"screen_id": screen_id, "notified": False, "reason": str(e)}
    return {"screen_id": screen_id, "notified": True}


@server.tool()
async def reload_all_screens() -> dict:
    """Bounce every connected screen — broadcasts a reload over each
    live WebSocket so all stations pick up their current content
    fresh. Disconnected screens are listed under ``skipped``."""
    notified: list[int] = []
    skipped: list[dict] = []
    for screen in screen_manager.screens:
        if not screen.connected:
            skipped.append({"id": screen.id, "reason": "not connected"})
            continue
        try:
            await connection_manager.notify_screen(screen=screen)
            notified.append(screen.id)
        except Exception as e:  # noqa: BLE001
            skipped.append({"id": screen.id, "reason": str(e)})
    return {
        "notified": notified,
        "skipped": skipped,
        "total": len(screen_manager.screens),
    }


@server.tool()
def list_brands() -> dict:
    """List the studio brand profiles that can be applied (id + name + colours).

    Use the id with `apply_brand`."""
    from models.brands import BRANDS
    return {"brands": list(BRANDS.values())}


@server.tool()
async def apply_brand(brand_id: str) -> dict:
    """Apply a studio brand profile across the room. `brand_id` is one of the
    ids from `list_brands` (e.g. "accenture", "ikea").

    Sets the Hue lights to the brand palette (primary on the Studio spots,
    secondary on the Maker/Wardrobe strips) and switches every connected,
    zone-mapped screen to a light-mimicking gradient — so the screens glow the
    brand colours. Say e.g. "set the brand to Accenture" / "make it IKEA"."""
    from models.brands import apply_brand_full
    return await apply_brand_full(brand_id)


@server.tool()
def save_brand(brand_id: str) -> dict:
    """Save the CURRENT studio state as a brand profile (brand_id 'ikea' or
    'accenture'). Captures each zone's current light colour AND screen content
    and persists them, so live tweaks (e.g. after changing zone lights) become
    the brand default. Use after the operator says "save this as the IKEA
    profile" / "update the Accenture profile"."""
    from models.brands import save_brand_profile
    return save_brand_profile(brand_id)


@server.tool()
async def apply_scene(scene_id: str) -> dict:
    """Apply a saved Studio scene by id.

    A scene bundles (1) an optional Hue scene to recall on the bridge,
    (2) per-zone screen content overrides, and (3) a reload broadcast
    to every connected screen. Returns a per-step result dict.

    Use `list_scenes` to find scene ids."""
    try:
        return await scene_manager.apply(scene_id)
    except KeyError:
        return {"error": f"scene_id {scene_id!r} not found"}


# --------------------------------------------------------------------------
# Tools — diagnostics
# --------------------------------------------------------------------------


@server.tool()
async def run_content_walkthrough(
    screen_id: Optional[int] = None,
    state_pause_seconds: float = 4.0,
) -> dict:
    """Cycle a target screen through every major content type as a
    visible self-test — picture → url (web page) → url (YouTube) → pdf
    → news → default settle. Records the actual content set at each
    step so a caller can verify what landed.

    - ``screen_id``: 1-based id; defaults to the first connected screen,
      or screen 1 if none are connected.
    - ``state_pause_seconds``: how long to leave each state on-screen.
      Default 4.0 makes the full sequence ~24s.

    The screen is left at ``default`` (studio logo) when done so the
    test doesn't strand it mid-walkthrough."""
    return await _run_walkthrough(
        target_screen_id=screen_id,
        state_pause_seconds=state_pause_seconds,
    )


@server.tool()
async def run_fleet_demo(
    target_screen_ids: Optional[list[int]] = None,
    state_pause_seconds: float = 4.0,
    settle_scene_id: str = "ai-news",
) -> dict:
    """Cycle every available screen through 3 content modes in unison,
    then settle the whole fleet on a saved scene.

    Sequence (~17s at 4s/step):
      1. URL (web) — all targets → https://example.com
      2. URL (YouTube) — all targets → a YouTube embed
      3. Default — all targets → the studio logo
      Settle → `apply_scene(settle_scene_id)` (default "ai-news")

    Target selection:
      - ``target_screen_ids`` if provided
      - else every screen with a live WebSocket
      - else (no one connected) every configured screen — keeps the
        data layer exercised; the response's ``target_source`` field
        says which branch was taken.

    Use to verify the fleet end-to-end: per-screen writes, the saved
    scene apply path (Hue + screens + reload), and the WebSocket
    reload broadcast all in one ~20s run.
    """
    return await _run_fleet_demo(
        target_screen_ids=target_screen_ids,
        state_pause_seconds=state_pause_seconds,
        settle_scene_id=settle_scene_id,
    )
