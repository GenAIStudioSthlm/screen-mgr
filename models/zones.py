"""Zone model — physical area in the Studio.

A Zone bundles a Screen (optional), a Hue light group (optional), and
a position on the floor plan. The redesigned admin treats zones as the
primary unit of control; behind the scenes nothing about screens or
Hue changes.

The floor-plan polygon is in viewBox-normalised coordinates so the SVG
floor plan (Phase 3) can drop them in directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError


ZONES_FILE = Path("data/zones.json")


class Zone(BaseModel):
    id: str = Field(..., description="Stable slug, e.g. 'station-2', 'main-screen'")
    name: str = Field(..., description="Display name, mirrors Screen.name when applicable")
    screen_id: Optional[int] = Field(
        None, description="Foreign key to Screen.id (1..8); None if no screen lives in this zone"
    )
    light_group_id: Optional[str] = Field(
        None, description="Hue bridge group id (e.g. '81' for Studio); None if no lights"
    )
    polygon: List[Tuple[float, float]] = Field(
        default_factory=list,
        description="SVG points on the floor plan, viewBox-normalised (0..960 x 0..420 by convention)",
    )
    label_xy: Tuple[float, float] = Field(
        default=(0.0, 0.0),
        description="Where to render the zone label on the floor plan",
    )
    area_label: str = Field("—", description="Human-readable area, e.g. '28 m²' or '—'")


class ZoneManager:
    """Loads / saves zones from data/zones.json. Mirrors ScreenManager."""

    def __init__(self) -> None:
        self.zones: List[Zone] = []

    def load(self) -> None:
        if not ZONES_FILE.exists():
            self.zones = _seed_zones()
            self.save()
            return
        try:
            with open(ZONES_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.zones = [Zone(**z) for z in raw]
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            print(f"[zones] could not load {ZONES_FILE}: {e}")
            self.zones = _seed_zones()

    def save(self) -> None:
        ZONES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ZONES_FILE, "w", encoding="utf-8") as f:
            json.dump([z.model_dump() for z in self.zones], f, indent=2)

    def get(self, zone_id: str) -> Optional[Zone]:
        for z in self.zones:
            if z.id == zone_id:
                return z
        return None

    def by_screen(self, screen_id: int) -> Optional[Zone]:
        for z in self.zones:
            if z.screen_id == screen_id:
                return z
        return None


def _seed_zones() -> List[Zone]:
    """Initial layout: one zone per existing screen, arranged in a rough
    2x4 grid on a 960x420 viewBox. Phase 3 of the redesign will replace
    these placeholder polygons with the real Studio floor plan."""

    # 4 columns x 2 rows over a 960x420 viewBox = 240x210 cells, 12px margins.
    cells = [(i % 4, i // 4) for i in range(8)]   # (col, row)
    margin = 12
    cell_w = (960 - margin * 5) / 4
    cell_h = (420 - margin * 3) / 2

    # Names + Hue group hints mirror the user's existing screens.json defaults
    # (the names are also what appears today in /api/screens).
    seeds = [
        ("station-1", "Station 1", 1, None),
        ("station-2", "Station 2", 2, "81"),   # in the Studio Hue room
        ("station-3", "Station 3", 3, "81"),
        ("screen-2",  "Screen 2",  4, "81"),
        ("screen-3",  "Screen 3",  5, "81"),
        ("main-screen", "Main Screen", 6, "81"),
        ("screen-4",  "Screen 4",  7, None),
        ("screen-5",  "Screen 5",  8, None),
    ]

    zones: List[Zone] = []
    for (slug, name, screen_id, light_group_id), (col, row) in zip(seeds, cells):
        x = margin + col * (cell_w + margin)
        y = margin + row * (cell_h + margin)
        polygon = [
            (x, y),
            (x + cell_w, y),
            (x + cell_w, y + cell_h),
            (x, y + cell_h),
        ]
        label_xy = (x + cell_w / 2, y + cell_h / 2)
        zones.append(
            Zone(
                id=slug,
                name=name,
                screen_id=screen_id,
                light_group_id=light_group_id,
                polygon=polygon,
                label_xy=label_xy,
                area_label="—",
            )
        )
    return zones


zone_manager = ZoneManager()
zone_manager.load()
