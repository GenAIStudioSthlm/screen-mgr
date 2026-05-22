"""Displays MCP server — physical LED panels driven by ServiceModules.

Today there's one LED panel (`rgbdisplay`, the 32×64 matrix). When another
LED panel module registers, its id goes in `LED_MODULE_IDS` below and it
appears in `list_displays` automatically — same source-of-truth pattern
the admin UI's LED Screens panel uses (`led_screens.js`).

Mounted at /mcp/displays/sse. Wraps the module registry directly; no
HTTP roundtrip back through /api/modules/*.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from modules import registry
from modules.base import ServiceModule


# LAN-only — same rationale as the other MCP servers.
_TRANSPORT = TransportSecuritySettings(enable_dns_rebinding_protection=False)

server = FastMCP("displays", transport_security=_TRANSPORT)


# Module ids that count as "displays" (physical LED panels). Kept in
# sync with `static/javascript/v2/views/led_screens.js::LED_MODULE_IDS`
# so the admin UI and the MCP agree on what's a display.
LED_MODULE_IDS: list[str] = ["rgbdisplay"]


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _display_modules() -> list[ServiceModule]:
    """Return every registered ServiceModule whose id is a known LED panel."""
    out: list[ServiceModule] = []
    for m in registry.list():
        if m.id in LED_MODULE_IDS and isinstance(m, ServiceModule):
            out.append(m)
    return out


def _get(display_id: str) -> ServiceModule:
    """Resolve a display by id, or raise a RuntimeError that FastMCP turns
    into a tool error result."""
    if display_id not in LED_MODULE_IDS:
        raise RuntimeError(
            f"{display_id!r} is not a recognised LED display id "
            f"(known: {LED_MODULE_IDS}). Add it to LED_MODULE_IDS once "
            f"its module is registered."
        )
    module = registry.get(display_id)
    if module is None:
        raise RuntimeError(
            f"display module {display_id!r} not registered on this host"
        )
    if not isinstance(module, ServiceModule):
        raise RuntimeError(
            f"{display_id!r} is registered but is not a ServiceModule "
            f"(can't start/stop)"
        )
    return module


def _summarize(m: ServiceModule) -> dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "description": m.description,
        "version": m.version,
        "enabled": registry.is_enabled(m.id),
        "status": m.status(),
    }


# --------------------------------------------------------------------------
# Tools — read
# --------------------------------------------------------------------------


@server.tool()
def list_displays() -> dict:
    """List every registered LED display panel + its current status.

    Today the only entry is ``rgbdisplay`` (the 32×64 LED matrix on
    studiopi). Future LED panels join automatically when their module
    is registered and listed in the MCP's ``LED_MODULE_IDS``.

    Each entry: ``id`` (used by other tools), ``name``, ``description``,
    ``version``, ``enabled`` (registry flag), and ``status`` with the
    systemd ``active`` / ``enabled`` state."""
    return {"displays": [_summarize(m) for m in _display_modules()]}


@server.tool()
def get_display_status(display_id: str) -> dict:
    """Focused status for one display by id.

    Use after `start_display` / `stop_display` to confirm the unit
    actually transitioned, or as a cheap health probe."""
    m = _get(display_id)
    return _summarize(m)


# --------------------------------------------------------------------------
# Tools — write
# --------------------------------------------------------------------------


@server.tool()
def start_display(display_id: str) -> dict:
    """Start a display's backing systemd unit (e.g. bring the LED matrix
    up). Returns the unit's stdout/stderr and an ``ok`` flag."""
    return _get(display_id).start()


@server.tool()
def stop_display(display_id: str) -> dict:
    """Stop a display's backing systemd unit (darken the LED matrix).
    Returns the unit's stdout/stderr and an ``ok`` flag."""
    return _get(display_id).stop()


@server.tool()
def set_display_enabled(display_id: str, enabled: bool) -> dict:
    """Flip the registry's ``enabled`` flag for a display.

    Disabling doesn't stop the unit — it just hides the module from
    consumers that filter on enabled. Use start/stop for the actual
    systemd lifecycle."""
    _get(display_id)  # validates existence
    if enabled:
        registry.enable(display_id)
    else:
        registry.disable(display_id)
    return {"id": display_id, "enabled": registry.is_enabled(display_id)}


# --------------------------------------------------------------------------
# Tools — diagnostics
# --------------------------------------------------------------------------


@server.tool()
async def run_display_test(display_id: str) -> dict:
    """Lifecycle sanity test for a display: stop the unit, pause ~3s
    so an observer can see it dark, then start it back up. Returns
    before / after status snapshots so the caller can confirm both
    transitions landed.

    If the display is already inactive when the test runs, the stop
    step is a no-op and the test just exercises the start path."""
    m = _get(display_id)
    before = m.status()
    stop_result = await asyncio.to_thread(m.stop)
    await asyncio.sleep(3.0)
    mid = m.status()
    start_result = await asyncio.to_thread(m.start)
    # Give systemd a moment to flip is-active to "active".
    await asyncio.sleep(0.5)
    after = m.status()
    return {
        "id": display_id,
        "before": before,
        "stop_result": stop_result,
        "mid": mid,
        "start_result": start_result,
        "after": after,
    }


@server.tool()
async def run_grid_test_pattern(display_id: str, duration_seconds: int = 15) -> dict:
    """Run the grid + 4-corner-clock + center-diamond test pattern on
    the display for ~``duration_seconds`` (default 15, capped at 120),
    then revert to whatever was running before.

    Specifically: writes a mode marker, restarts the display unit so
    `start_display.sh` launches `led_test_pattern.py` instead of the
    default content; sleeps; writes the marker back and restarts again.

    Useful as a visible self-test of the matrix — confirms every panel
    + every pixel column/row is alive, and that text rendering works.
    Today only the ``rgbdisplay`` module supports this; other display
    modules will respond with an error."""
    m = _get(display_id)
    fn = getattr(m, "run_test_pattern", None)
    if fn is None:
        return {
            "error": f"display {display_id!r} does not support run_test_pattern",
        }
    return await fn(duration_seconds=duration_seconds)
