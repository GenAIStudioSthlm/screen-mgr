"""Studio zone map helpers.

Resolves the design floor-plan zones (data/studio_zone_map.json) to real
backend screen ids and Hue light ids, and reads the *current* colour of a
zone's lights so a gradient screen can mimic the lighting. See the map file's
own _comment for why backend screen names can't be trusted.
"""

from __future__ import annotations

import colorsys
import json
from pathlib import Path

MAP_FILE = Path("data/studio_zone_map.json")


def load_map() -> dict:
    try:
        with open(MAP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def zone_for_screen(screen_id: int, plan: str = "popup") -> tuple[str | None, dict | None]:
    """Return (zone_key, zone_dict) for the zone that owns this screen id."""
    zones = load_map().get(plan, {})
    for key, z in zones.items():
        if key.startswith("_") or not isinstance(z, dict):
            continue
        if screen_id in (z.get("screens") or []):
            return key, z
    return None, None


# --- Hue light state -> CSS hex ------------------------------------------

def _gamma(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def _xy_to_hex(x: float, y: float, bri: int) -> str | None:
    """Philips' recommended CIE xy + brightness -> sRGB (Wide-gamut D65)."""
    if y <= 0:
        return None
    Y = max(bri, 1) / 254.0
    X = (Y / y) * x
    Z = (Y / y) * (1.0 - x - y)
    r = X * 1.656492 - Y * 0.354851 - Z * 0.255038
    g = -X * 0.707196 + Y * 1.655397 + Z * 0.036152
    b = X * 0.051713 - Y * 0.121364 + Z * 1.011530
    r, g, b = (_gamma(max(v, 0.0)) for v in (r, g, b))
    mx = max(r, g, b, 1e-6)
    if mx > 1:
        r, g, b = r / mx, g / mx, b / mx
    return "#%02x%02x%02x" % tuple(min(255, max(0, int(v * 255))) for v in (r, g, b))


def _hs_to_hex(hue: int, sat: int, bri: int) -> str:
    r, g, b = colorsys.hsv_to_rgb(
        (hue or 0) / 65535.0, (sat or 0) / 254.0, max(bri or 0, 1) / 254.0
    )
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def light_to_hex(state: dict) -> str | None:
    """Best-effort colour of a Hue light from its v1 state. None if off."""
    if not state or not state.get("on"):
        return None
    bri = state.get("bri", 254)
    if state.get("colormode") == "xy" and state.get("xy"):
        x, y = state["xy"]
        return _xy_to_hex(x, y, bri)
    if state.get("hue") is not None and state.get("sat") is not None:
        return _hs_to_hex(state["hue"], state["sat"], bri)
    # ct / dimmable-white: approximate a warm white.
    return "#ffefd9"


def _all_lights() -> dict:
    """Fetch every Hue light's state once ({} if unavailable)."""
    from modules import registry

    mod = registry.get("hue")
    client = getattr(mod, "client", None) if mod else None
    if client is None:
        return {}
    lights = client.get_lights()
    return lights if isinstance(lights, dict) and "error" not in lights else {}


def zone_light_hexes(zone: dict | None, lights: dict | None = None) -> list[str]:
    """Current colours of the zone's mapped lights (skips off/unknown).
    Pass a preloaded `lights` dict to avoid a bridge call per zone."""
    if not zone:
        return []
    if lights is None:
        lights = _all_lights()
    out: list[str] = []
    for lid in (zone.get("light_ids") or []):
        light = lights.get(str(lid)) or lights.get(lid)
        if not light:
            continue
        hexc = light_to_hex(light.get("state", {}))
        if hexc:
            out.append(hexc)
    return out


def studio_state(plan: str = "popup") -> dict:
    """All zones enriched with live light colours + real screen state, in one
    pass (single bridge fetch). The new /admin/studio UI polls this to mirror
    and drive the real room."""
    from screens import screen_manager

    zones_map = load_map().get(plan, {})
    lights = _all_lights()
    by_id = {s.id: s for s in screen_manager.screens}
    zones: dict = {}
    for key, z in zones_map.items():
        if key.startswith("_") or not isinstance(z, dict):
            continue
        screens = []
        for sid in (z.get("screens") or []):
            s = by_id.get(sid)
            if s is not None:
                screens.append({"id": s.id, "connected": s.connected, "type": s.type})
        zones[key] = {
            "name": z.get("name"),
            "orientation": z.get("orientation"),
            "light_ids": z.get("light_ids") or [],
            "colors": zone_light_hexes(z, lights),
            "screens": screens,
        }
    return {"plan": plan, "zones": zones}


def screen_gradient_spec(screen_id: int, plan: str = "popup") -> dict:
    """Everything a gradient screen needs: the zone, its live light colours,
    and display orientation."""
    key, zone = zone_for_screen(screen_id, plan)
    return {
        "screen_id": screen_id,
        "zone": key,
        "zone_name": (zone or {}).get("name"),
        "orientation": (zone or {}).get("orientation"),
        "colors": zone_light_hexes(zone),
    }
