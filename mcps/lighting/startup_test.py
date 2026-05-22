"""Studio lighting startup sequence — rainbow walk + intensity test.

Shared logic for the MCP tool (`run_startup_test` in server.py) and the
CLI script (`scripts/lights_startup_test.py`). Talks to the HueClient
directly so it can run in-process from the MCP server without looping
back through SSE.

The Studio room (group 81) is the target; all 13 lights are exercised.

Approx timings (tunable via the constants below):
  - Rainbow: ~5s  (6 frames × ~0.83s, 60° hue step per frame)
  - Intensity: ~5s (4 levels × ~1.25s)
  - Settle: snapshot write — leaves the room at 60% / 3000K

The function is async so the MCP server's event loop stays responsive;
HueClient calls are sync HTTP and are wrapped with `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import colorsys
from typing import Any


GROUP_ID = "81"  # Studio room

# Rainbow phase
RAINBOW_FRAMES = 6
RAINBOW_TARGET_SECONDS = 5.0
RAINBOW_INTRA_LIGHT_DELAY = 0.04  # ~25 cmd/s burst — Hue tolerates short bursts above 10/s
RAINBOW_INTENSITY_PCT = 80

# Intensity phase
BRI_SEQUENCE = [10, 80, 40, 80]
INTENSITY_TARGET_SECONDS = 5.0

# Final resting state
FINAL_BRIGHTNESS_PCT = 60
FINAL_KELVIN = 3000


def _pct_to_bri(pct: int) -> int:
    pct = max(0, min(100, int(pct)))
    return max(1, round(pct * 254 / 100))


def _kelvin_to_ct(kelvin: int) -> int:
    ct = round(1_000_000 / max(1, kelvin))
    return max(153, min(500, ct))


def _hsv_xy(h_deg: float, s: float = 1.0, v: float = 1.0) -> tuple[float, float]:
    """HSV → CIE xy via sRGB → linear RGB → XYZ (same formula as the
    MCP `set_light(color_hex=...)` path, just skipping the hex string)."""
    r, g, b = colorsys.hsv_to_rgb((h_deg % 360) / 360.0, s, v)

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


async def _rainbow(client: Any, lights: list[str]) -> dict:
    n = len(lights)
    light_offset_deg = 360.0 / n
    hue_step_per_frame = 360.0 / RAINBOW_FRAMES
    intra_frame_writes = n * RAINBOW_INTRA_LIGHT_DELAY
    per_frame_budget = RAINBOW_TARGET_SECONDS / RAINBOW_FRAMES
    frame_tail = max(0.0, per_frame_budget - intra_frame_writes)

    for frame in range(RAINBOW_FRAMES):
        for i, light_id in enumerate(lights):
            hue_deg = (i * light_offset_deg + frame * hue_step_per_frame) % 360
            xy = _hsv_xy(hue_deg)
            state = {
                "on": True,
                "bri": _pct_to_bri(RAINBOW_INTENSITY_PCT),
                "xy": list(xy),
            }
            await asyncio.to_thread(client.set_light, str(light_id), state)
            await asyncio.sleep(RAINBOW_INTRA_LIGHT_DELAY)
        if frame_tail > 0:
            await asyncio.sleep(frame_tail)

    return {
        "frames": RAINBOW_FRAMES,
        "hue_step_deg": hue_step_per_frame,
        "lights": n,
    }


async def _intensity(client: Any) -> dict:
    pause = INTENSITY_TARGET_SECONDS / max(1, len(BRI_SEQUENCE))
    for pct in BRI_SEQUENCE:
        await asyncio.to_thread(
            client.set_group, GROUP_ID, {"bri": _pct_to_bri(pct), "on": True}
        )
        await asyncio.sleep(pause)
    return {"levels_pct": list(BRI_SEQUENCE), "pause_between_s": pause}


async def _settle(client: Any) -> dict:
    state = {
        "on": True,
        "bri": _pct_to_bri(FINAL_BRIGHTNESS_PCT),
        "ct": _kelvin_to_ct(FINAL_KELVIN),
    }
    await asyncio.to_thread(client.set_group, GROUP_ID, state)
    return {"brightness_pct": FINAL_BRIGHTNESS_PCT, "kelvin": FINAL_KELVIN}


async def run_startup_test(client: Any) -> dict:
    """Run rainbow → intensity sweep → settle on the Studio group.

    Returns a small summary dict describing what ran. Raises if the
    Studio group has no lights (e.g. the bridge is misconfigured)."""
    groups = await asyncio.to_thread(client.get_groups)
    lights = groups.get(GROUP_ID, {}).get("lights") or []
    if not lights:
        raise RuntimeError(
            f"Studio group {GROUP_ID} has no lights — cannot run startup test"
        )

    rainbow = await _rainbow(client, lights)
    intensity = await _intensity(client)
    settled = await _settle(client)

    return {
        "group_id": GROUP_ID,
        "rainbow": rainbow,
        "intensity": intensity,
        "settled_at": settled,
    }
