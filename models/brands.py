"""Seeded brand profiles (Phase 5).

Fixed Accenture + IKEA profiles for now — the brand.html builder + CRUD is
deferred. Applying a brand sets the studio's Hue lights to the brand palette
(primary on the Studio spots, secondary on the Maker/Wardrobe strips); the
zones' gradient screens then mimic those colours automatically.
"""

from __future__ import annotations

import colorsys
import json
from pathlib import Path

# Saved overrides captured from the live studio (per-zone lights + content).
# Merged over the seeded BRANDS below, so operator tweaks become the default.
_OVERRIDES_FILE = Path("data/brand_profiles.json")

# Palettes from Madalena's design (control.html company swatches).
BRANDS: dict[str, dict] = {
    "accenture": {
        "id": "accenture",
        "name": "Accenture",
        "primary": "#A100FF",
        "secondary": "#7500C0",
        "video": "http://192.168.2.65:8000/static/videos/ACN_Main_screen.mp4",
        # Accenture logo on every zone screen (orientation-matched logo card on
        # white). The one screen playing video is the separate VLC display, not
        # a screen-mgr screen, so all web screens get the logo.
        "content": {
            "a": "Accenture/logo_h.png",  # Main Cloud — horizontal
            "b": "Accenture/logo_h.png",  # Station 1 — horizontal
            "c": "Accenture/logo_h.png",  # Station 2 — horizontal
            "d": "Accenture/logo_h.png",  # Main Hall — horizontal
            "e": "Accenture/logo_v.png",  # Cloud R — vertical
            "f": "Accenture/logo_v.png",  # Cloud L — vertical
            "h": "Accenture/logo_v.png",  # Station 3 — vertical
        },
    },
    "ikea": {
        "id": "ikea",
        "name": "IKEA",
        "primary": "#0058A3",
        "secondary": "#FFDA1A",
        # Brand video played on the VLC screen, sourced from the Pi (backup
        # media library). VLC streams it over HTTP.
        "video": "http://192.168.2.65:8000/static/videos/IKEA_Main_screen.mov",
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
            "h": "IKEA/Wardrobe.jpg",  # Station 3 — vertical
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


# --- persistence (seeded BRANDS + saved overrides) -----------------------

def load_overrides() -> dict:
    try:
        with open(_OVERRIDES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_overrides(data: dict) -> None:
    _OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_OVERRIDES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_brands() -> dict:
    """Seeded BRANDS merged with saved overrides. An override's keys (lights /
    content / colours) win over the seed, so saved tweaks are the new default."""
    merged = {bid: dict(b) for bid, b in BRANDS.items()}
    for bid, ov in load_overrides().items():
        base = dict(merged.get(bid, {"id": bid, "name": bid.title()}))
        base.update({k: v for k, v in (ov or {}).items() if v is not None})
        merged[bid] = base
    return merged


def get_brand(brand_id: str) -> dict | None:
    return load_brands().get((brand_id or "").strip().lower())


def apply_zone_lights(lights_map: dict) -> dict:
    """Set each zone's mapped Hue lights to a saved per-zone colour."""
    from modules import registry
    from models.studio_map import load_map

    mod = registry.get("hue")
    client = getattr(mod, "client", None) if mod else None
    if client is None:
        return {"ok": False, "error": "hue unavailable"}
    zmap = load_map().get("popup", {})
    applied: dict = {}
    for zone, hexc in (lights_map or {}).items():
        z = zmap.get(zone)
        if not isinstance(z, dict) or not hexc:
            continue
        hh, ss = hex_to_hue_sat(hexc)
        for lid in (z.get("light_ids") or []):
            client.set_light(str(lid), {"on": True, "bri": 254, "hue": hh, "sat": ss})
        applied[zone] = hexc
    return {"ok": True, "zone_lights": applied}


def save_brand_profile(brand_id: str) -> dict:
    """Capture the CURRENT studio state (per-zone light colour + per-zone screen
    content) and persist it as this brand's profile, so live tweaks become the
    brand default. Stored in data/brand_profiles.json (merged over the seed)."""
    bid = (brand_id or "").strip().lower()
    if bid not in load_brands():
        return {"ok": False, "error": f"unknown brand '{brand_id}'",
                "available": list(load_brands().keys())}
    from models.studio_map import load_map, zone_light_hexes, _all_lights
    from screens import screen_manager

    zmap = load_map().get("popup", {})
    lights_all = _all_lights()
    by_id = {s.id: s for s in screen_manager.screens}
    lights: dict = {}
    content: dict = {}
    for zone, z in zmap.items():
        if zone.startswith("_") or not isinstance(z, dict):
            continue
        hexes = zone_light_hexes(z, lights_all)
        if hexes:
            lights[zone] = hexes[0]
        for sid in (z.get("screens") or []):
            s = by_id.get(sid)
            if s is not None and s.type == "picture" and s.picture:
                content[zone] = s.picture
                break
    ov = load_overrides()
    entry = dict(ov.get(bid, {}))
    entry["lights"] = lights
    entry["content"] = content
    ov[bid] = entry
    _save_overrides(ov)
    return {"ok": True, "brand": bid, "lights": lights, "content": content}


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
    brand = get_brand(brand_id)
    if not brand:
        return {"ok": False, "error": f"unknown brand '{brand_id}'",
                "available": list(load_brands().keys())}

    # If a saved profile captured per-zone light colours, restore those;
    # otherwise use the seed's primary/secondary group palette.
    if brand.get("lights"):
        lighting = apply_zone_lights(brand["lights"])
    else:
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
    if gradient_screens or picture_screens:
        # Persist FIRST, then tell screens to reload — otherwise a reload can
        # race ahead of the save and re-show stale content (seen on screen F).
        screen_manager.save_screens()
        for sid in (picture_screens + gradient_screens):
            s = by_id.get(sid)
            if s is not None and s.connected:
                await connection_manager.notify_screen(screen=s)

    # Play the brand video on the VLC screen (sourced from the Pi backup
    # media library). Best-effort — VLC may be down/unreachable.
    video = brand.get("video")
    vlc_result = None
    if video:
        try:
            from mcps.vlc import vlc_client
            await vlc_client.command("in_play", input=video)
            vlc_result = {"ok": True, "playing": video}
        except Exception as e:
            vlc_result = {"ok": False, "error": str(e)}

    return {"ok": True, "brand": brand_id, "lighting": lighting,
            "screens_gradient": gradient_screens, "screens_picture": picture_screens,
            "video": vlc_result}
