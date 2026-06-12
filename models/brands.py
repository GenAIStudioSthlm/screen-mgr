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
