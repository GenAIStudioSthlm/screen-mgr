"""Studio scenes (Phase 6) — per-zone lighting moods, ported from Madalena's
prototype (control.js LIGHT_PRESETS + LIGHT_SCENES).

A scene sets each mapped zone's Hue lights to a preset colour; the zones'
gradient screens then mimic the new lighting automatically. The 'accenture'
scene is special-cased to the Accenture brand look (purple) per the
"brand colours on lights" decision, rather than the prototype's cool-white.
"""

from __future__ import annotations

# Preset id -> representative colour (from the prototype's LIGHT_PRESETS).
LIGHT_PRESETS: dict[str, str] = {
    "warm": "#FF9B3E",
    "neutral": "#FFE5B4",
    "cool": "#C8DCFF",
    "blue": "#0058A3",
    "yellow": "#FFDA1A",
    # "off" handled specially (lights off)
}

# Scene -> per-zone preset (popup zones a-k only; reinvention-only zones dropped).
LIGHT_SCENES: dict[str, dict[str, str]] = {
    "welcome":      {"a": "warm",    "b": "neutral", "c": "neutral", "d": "off",  "e": "off",     "f": "warm",   "g": "off",  "h": "off",     "k": "off"},
    "workshop":     {"a": "blue",    "b": "blue",    "c": "blue",    "d": "blue", "e": "neutral", "f": "blue",   "g": "blue", "h": "neutral", "k": "blue"},
    "breakout":     {"a": "yellow",  "b": "blue",    "c": "blue",    "d": "yellow","e": "blue",   "f": "yellow", "g": "blue", "h": "off",     "k": "yellow"},
    "presentation": {"a": "neutral", "b": "cool",    "c": "cool",    "d": "cool", "e": "neutral", "f": "off",    "g": "off",  "h": "off",     "k": "off"},
    "afterhours":   {"a": "warm",    "b": "warm",    "c": "warm",    "d": "warm", "e": "warm",    "f": "warm",   "g": "warm", "h": "off",     "k": "warm"},
}

SCENE_LABELS = {
    "welcome": "Welcome", "workshop": "Workshop", "breakout": "Breakout Sessions",
    "presentation": "Presentation", "afterhours": "After Hours", "accenture": "Demo 12 June",
}


def list_scenes() -> list[dict]:
    out = [{"id": sid, "name": SCENE_LABELS.get(sid, sid)} for sid in LIGHT_SCENES]
    out.append({"id": "accenture", "name": SCENE_LABELS["accenture"]})
    return out


async def apply_scene_full(scene_id: str) -> dict:
    """Apply a studio scene: set each mapped zone's Hue lights to the scene's
    per-zone preset. Screens that are light-mimicking gradients follow."""
    sid = (scene_id or "").lower()
    if sid == "accenture":
        # Brand look (purple) rather than the prototype's cool-white scene.
        from models.brands import apply_brand_full
        return await apply_brand_full("accenture")

    scene = LIGHT_SCENES.get(sid)
    if not scene:
        return {"ok": False, "error": f"unknown scene '{scene_id}'",
                "available": [s["id"] for s in list_scenes()]}

    from modules import registry
    from models.brands import hex_to_hue_sat
    from models.studio_map import load_map

    mod = registry.get("hue")
    client = getattr(mod, "client", None) if mod else None
    if client is None:
        return {"ok": False, "error": "hue unavailable"}

    zmap = load_map().get("popup", {})
    applied: dict[str, str] = {}
    for zone, preset in scene.items():
        z = zmap.get(zone)
        if not isinstance(z, dict):
            continue
        for lid in (z.get("light_ids") or []):
            if preset == "off":
                client.set_light(str(lid), {"on": False})
            else:
                color = LIGHT_PRESETS.get(preset)
                if not color:
                    continue
                h, s = hex_to_hue_sat(color)
                client.set_light(str(lid), {"on": True, "bri": 254, "hue": h, "sat": s})
        applied[zone] = preset
    return {"ok": True, "scene": sid, "applied": applied}
