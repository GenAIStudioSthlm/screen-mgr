"""Lighting MCP server — exposes the Philips Hue Bridge as MCP tools.

Lives in-process under the same uvicorn app as the rest of screen-mgr.
External MCP clients (Claude Code, Anthropic SDK) connect to
http://<host>:8000/mcp/lighting/sse over the SSE transport. The
in-admin chat agent (Phase 2 onward) will attach to the same server.

Tools wrap the existing HueClient directly — no HTTP round-trip back
through /api/modules/hue/* — so latency stays at one bridge hop.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mcps.lighting.startup_test import run_startup_test as _run_startup_test
from modules import registry
from modules.hue.client import HueClient


# The MCP server lives behind the LAN-only studiopi firewall and is
# called by trusted clients (our own agents, Claude Code on the same
# LAN). DNS-rebinding protection exists to defeat browser-side attacks
# against localhost MCP servers, which doesn't match this deployment.
# Re-enable + pin allowed_hosts if this service is ever exposed publicly.
_TRANSPORT = TransportSecuritySettings(enable_dns_rebinding_protection=False)

server = FastMCP("lighting", transport_security=_TRANSPORT)


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _client() -> HueClient:
    """Resolve the live HueClient from the module registry. Raises a
    RuntimeError with an operator-facing message if the bridge isn't paired
    or the module isn't loaded; FastMCP turns this into a tool error result
    the calling agent can read and react to."""
    module = registry.get("hue")
    if module is None:
        raise RuntimeError("Hue module not registered in this server")
    client = getattr(module, "client", None)
    if client is None:
        raise RuntimeError(
            "Hue bridge not paired — run `python3 scripts/hue_pair.py` on studiopi"
        )
    return client


def _pct_to_bri(pct: int) -> int:
    """Brightness percent (0–100) → Hue bri byte (1–254). 0% maps to bri=1
    + on=False; values above 0 keep the lamp on."""
    pct = max(0, min(100, int(pct)))
    return max(1, round(pct * 254 / 100))


def _hex_to_xy(hex_str: str) -> tuple[float, float]:
    """Convert a #RRGGBB color to CIE xy chromaticity for the Hue API.

    Standard Hue formula: sRGB → linear RGB → CIE XYZ (Wide Gamut D65) → xy.
    """
    h = hex_str.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"color_hex must be #RRGGBB, got {hex_str!r}")
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    def _decode(c: float) -> float:
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92

    r, g, b = _decode(r), _decode(g), _decode(b)
    X = r * 0.664511 + g * 0.154324 + b * 0.162028
    Y = r * 0.283881 + g * 0.668433 + b * 0.047685
    Z = r * 0.000088 + g * 0.072310 + b * 0.986039
    total = X + Y + Z
    if total <= 0:
        return (0.0, 0.0)
    return (round(X / total, 4), round(Y / total, 4))


def _kelvin_to_ct(kelvin: int) -> int:
    """Color temperature in K → Hue mireds (ct). Hue accepts ~153 (6500K)
    to ~500 (2000K). Clamped to that range."""
    if kelvin <= 0:
        raise ValueError("kelvin must be > 0")
    ct = round(1_000_000 / kelvin)
    return max(153, min(500, ct))


def _build_state(
    on: bool | None,
    brightness_pct: int | None,
    color_hex: str | None,
    kelvin: int | None,
) -> dict[str, Any]:
    """Translate the semantic tool params into a Hue API state dict.
    Empty dict = no-op."""
    state: dict[str, Any] = {}
    if on is not None:
        state["on"] = bool(on)
    if brightness_pct is not None:
        bri = _pct_to_bri(brightness_pct)
        state["bri"] = bri
        # Bri 0 implicitly means off — let the caller's on flag still win,
        # but if they passed bri only and it's the floor, turn off too.
        if brightness_pct == 0 and on is None:
            state["on"] = False
        elif on is None:
            state["on"] = True
    if color_hex is not None:
        state["xy"] = list(_hex_to_xy(color_hex))
    if kelvin is not None:
        state["ct"] = _kelvin_to_ct(kelvin)
    return state


# --------------------------------------------------------------------------
# Tools — read
# --------------------------------------------------------------------------


@server.tool()
def list_lights() -> dict:
    """List every Hue light with its current state.

    Returns the raw Hue v1 lights map keyed by light id, e.g.
    ``{"1": {"name": "Maker Light", "state": {"on": true, "bri": 254, ...}, ...}}``.
    Use the light id (the dict key, a string) for set_light calls.
    """
    return _client().get_lights()


@server.tool()
def list_groups() -> dict:
    """List Hue groups (rooms / zones) and their members.

    Returns the raw Hue v1 groups map. Each group has ``name``, ``lights``
    (list of light ids), ``type`` ("Room", "Zone", …), and an aggregate
    ``state``/``action``. Use group ids for set_group calls.
    The Studio room is typically id "81" (Studio) and the Maker room
    is a separate id — check by name to be sure.
    """
    return _client().get_groups()


@server.tool()
def list_scenes() -> dict:
    """List Hue Bridge-defined scenes (the ones the user set up in the
    Hue app). Returns the raw scenes map keyed by scene id. Use the
    scene id with recall_scene to activate it."""
    return _client().get_scenes()


@server.tool()
def get_bridge_status() -> dict:
    """Return the Hue Bridge config + reachability.

    Includes bridge name, software version, and ip — does NOT include
    the API username (semi-sensitive). Useful for diagnostics when
    tools start failing."""
    cfg = _client().get_config()
    # Strip whitelist (contains usernames) just in case.
    if isinstance(cfg, dict):
        cfg = {k: v for k, v in cfg.items() if k != "whitelist"}
    return cfg


# --------------------------------------------------------------------------
# Tools — write
# --------------------------------------------------------------------------


@server.tool()
def set_light(
    light_id: str,
    on: bool | None = None,
    brightness_pct: int | None = None,
    color_hex: str | None = None,
    kelvin: int | None = None,
) -> dict:
    """Update a single Hue light by id.

    All state parameters are optional — pass only what should change.
    - ``on``: turn the light on or off.
    - ``brightness_pct``: 0–100. Setting 0 implicitly turns the light off
      unless ``on=True`` is also passed.
    - ``color_hex``: ``#RRGGBB`` (sRGB). Converted to CIE xy.
    - ``kelvin``: color temperature in K (e.g. 2700 for warm white,
      5500 for cool white). Range clamped to Hue's 2000–6500K window.

    Pass either ``color_hex`` OR ``kelvin``, not both — the Hue bridge
    will pick whichever it processed last. Returns the bridge's
    per-attribute success/error list verbatim."""
    state = _build_state(on, brightness_pct, color_hex, kelvin)
    if not state:
        return {"error": "no state parameters provided"}
    return _client().set_light(light_id, state)


@server.tool()
def set_group(
    group_id: str,
    on: bool | None = None,
    brightness_pct: int | None = None,
    color_hex: str | None = None,
    kelvin: int | None = None,
) -> dict:
    """Update every light in a Hue group (room / zone) in one call.

    Parameters mirror set_light. Group id "0" is the bridge's
    "all lights" special group — useful for whole-house operations
    but prefer all_on / all_off for readability.

    Brightness for a group sets all members to the same level; the
    bridge resolves the per-light bri scale internally."""
    state = _build_state(on, brightness_pct, color_hex, kelvin)
    if not state:
        return {"error": "no state parameters provided"}
    return _client().set_group(group_id, state)


@server.tool()
def recall_scene(scene_id: str) -> dict:
    """Activate a Hue scene by id. Scene ids come from list_scenes.

    The Hue Bridge applies the scene's per-light state to every light
    in the scene — typically faster and more reliable than fanning out
    per-light writes."""
    return _client().recall_scene(scene_id)


@server.tool()
def all_on() -> dict:
    """Turn on every light known to the bridge (group 0). Convenience
    alias for set_group("0", on=True)."""
    return _client().all_on()


@server.tool()
def all_off() -> dict:
    """Turn off every light known to the bridge (group 0). Convenience
    alias for set_group("0", on=False)."""
    return _client().all_off()


# --------------------------------------------------------------------------
# Tools — diagnostics
# --------------------------------------------------------------------------


@server.tool()
async def run_startup_test() -> dict:
    """Run the Studio lights startup sequence: rainbow walk + intensity
    test + settle.

    Takes ~12 seconds end-to-end:
      - Rainbow (~5s): each of the 13 Studio lights starts at a distinct
        hue around the color wheel, then the whole rainbow rotates one
        full turn at 80% brightness.
      - Intensity (~5s): the Studio group is driven through 10/80/40/80%
        brightness levels.
      - Settle: the room is left at 60% / 3000K warm white so it's usable.

    Useful as a one-shot health check that every light is reachable and
    can render colors + dim correctly. Safe to re-run; the only state it
    leaves behind is the final settle. Returns a summary of what ran.
    """
    return await _run_startup_test(_client())
