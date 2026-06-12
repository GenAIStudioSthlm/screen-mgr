"""Seeded brand profiles (Phase 5).

Fixed Accenture + IKEA profiles for now — the brand.html builder + CRUD is
deferred. Applying a brand sets the studio's Hue lights to the brand palette
(primary on the Studio spots, secondary on the Maker/Wardrobe strips); the
zones' gradient screens then mimic those colours automatically.
"""

from __future__ import annotations

import colorsys

# Palettes from Madalena's design (control.html company swatches).
BRANDS: dict[str, dict] = {
    "accenture": {
        "id": "accenture",
        "name": "Accenture",
        "primary": "#A100FF",
        "secondary": "#7500C0",
    },
    "ikea": {
        "id": "ikea",
        "name": "IKEA",
        "primary": "#0058A3",
        "secondary": "#FFDA1A",
        # Per-zone on-brand screen content (folder-prefixed picture paths).
        # BEST-GUESS mapping (image filename -> original backend screen name ->
        # physical zone) — VERIFY with the operator, like the zone map.
        # Zones not listed fall back to a light-mimicking gradient.
        # Images on every zone screen EXCEPT the main one (Main Cloud = gradient),
        # orientation-matched (horizontal images on horizontal screens, the
        # vertical cloud images on the vertical cloud screens).
        "content": {
            "a": "IKEA/Screen_3.png",  # Main Cloud — horizontal big screen
            "b": "IKEA/Screen_2.png",  # Station 1 — horizontal
            "c": "IKEA/Screen_3.png",  # Station 2 — horizontal
            "d": "IKEA/Screen_2.png",  # Main Hall — horizontal
            "e": "IKEA/Cloud_1.jpg",   # Cloud R — vertical
            "f": "IKEA/Cloud_2.png",   # Cloud L — vertical
            "h": "IKEA/Screen_3.png",  # Station 3 — horizontal
        },
    },
}

# Hue group ids on this bridge: 81 = "Studio" (13 ceiling spots),
# 2 = "Maker" (4 light-strips, physically in the Wardrobe).
_STUDIO_GROUP = "81"
_MAKER_GROUP = "2"


def hex_to_hue_sat(hexstr: str) -> tuple[int, int]:
    """#RRGGBB -> Hue v1 (hue 0-65535, sat 0-254)."""
    h = hexstr.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    hh, ss, _ = colorsys.rgb_to_hsv(r, g, b)
    return int(hh * 65535), int(ss * 254)


def apply_lighting(brand: dict) -> dict:
    """Drive the real Hue lights to the brand palette. Best-effort."""
    from modules import registry

    mod = registry.get("hue")
    client = getattr(mod, "client", None) if mod else None
    if client is None:
        return {"ok": False, "error": "hue unavailable"}
    ph, ps = hex_to_hue_sat(brand["primary"])
    sh, ss = hex_to_hue_sat(brand["secondary"])
    client.set_group(_STUDIO_GROUP, {"on": True, "bri": 254, "hue": ph, "sat": ps})
    client.set_group(_MAKER_GROUP, {"on": True, "bri": 220, "hue": sh, "sat": ss})
    return {"ok": True, "studio": brand["primary"], "maker": brand["secondary"]}


async def apply_brand_full(brand_id: str) -> dict:
    """Apply a brand end-to-end: set the Hue lights to the palette, then switch
    every zone-mapped, connected screen to a light-mimicking gradient. Shared by
    the HTTP route and the MCP tool (chat/voice)."""
    brand = BRANDS.get((brand_id or "").lower())
    if not brand:
        return {"ok": False, "error": f"unknown brand '{brand_id}'",
                "available": list(BRANDS.keys())}

    lighting = apply_lighting(brand)

    from connections import connection_manager
    from screens import screen_manager
    from models.studio_map import load_map

    zmap = load_map().get("popup", {})
    content = brand.get("content", {})
    by_id = {s.id: s for s in screen_manager.screens}
    gradient_screens: list[int] = []
    picture_screens: list[int] = []

    # Per zone: show the brand's on-brand image where mapped, else a
    # light-mimicking gradient. Only touch connected screens.
    for zone, z in zmap.items():
        if zone.startswith("_") or not isinstance(z, dict):
            continue
        img = content.get(zone)
        for sid in (z.get("screens") or []):
            s = by_id.get(sid)
            if s is None:
                continue
            # Set content even on OFFLINE screens — they load their current
            # content when they reconnect (so zones whose display is briefly
            # off still come back on-brand).
            if img:
                s.type = "picture"
                s.picture = img
                picture_screens.append(sid)
            else:
                s.type = "gradient"
                s.text = "mimic|animated|100"  # track the new brand lighting
                gradient_screens.append(sid)
            if s.connected:
                await connection_manager.notify_screen(screen=s)
    if gradient_screens or picture_screens:
        screen_manager.save_screens()
    return {"ok": True, "brand": brand_id, "lighting": lighting,
            "screens_gradient": gradient_screens, "screens_picture": picture_screens}
