"""Device positions on the studio floor plan.

Where each physical device sits in the room — stations (screens),
Hue lights, the LED matrix display, the Marantz speaker amp, and
networked microphones — all stored as ``(x, y)`` coordinates in the
same 960×420 viewBox space the floor plan SVG uses.

Persisted to ``data/positions.json``. Each ``kind`` maps to a dict of
``device_id -> {x, y}``. Operators drag markers on the floor plan in
edit mode; each drop ``PUT``s a fresh coord — see
``routes/positions_routes.py``.

Schema:

    {
      "positions": {
        "station":    {"1": {"x": 120, "y": 220}, "2": {...}, ...},
        "light":      {"5": {"x": ..., "y": ...}, ...},
        "display":    {"rgbdisplay": {"x": ..., "y": ...}},
        "speaker":    {"marantz":    {"x": ..., "y": ...}},
        "microphone": {"GenAi-…":    {"x": ..., "y": ...}}
      }
    }

Empty buckets are fine; missing kinds simply mean "no devices of that
type placed yet". The frontend handles unplaced devices via a side
tray separate from this file's concerns.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from pydantic import BaseModel, Field, ValidationError


POSITIONS_FILE = Path("data/positions.json")

# Authoritative set of device kinds the floor plan understands.
# Adding a new kind: extend this set, then the frontend marker render
# loop picks it up via the per-kind icon/style map.
ALLOWED_KINDS: frozenset[str] = frozenset(
    {"station", "light", "display", "speaker", "microphone"}
)

# Floor plan viewBox bounds. Coords outside these are clamped on write.
VIEWBOX_WIDTH = 960
VIEWBOX_HEIGHT = 420


class Position(BaseModel):
    """A device's location in viewBox-normalised coords."""

    x: float = Field(..., ge=0, le=VIEWBOX_WIDTH)
    y: float = Field(..., ge=0, le=VIEWBOX_HEIGHT)


class PositionsState(BaseModel):
    """Top-level schema persisted to data/positions.json."""

    positions: Dict[str, Dict[str, Position]] = Field(default_factory=dict)


class PositionManager:
    """Load/save device positions. One instance per process; safe for
    concurrent reads (Python dict reads are atomic at the cpython
    level) and writes are funneled through `set_position` so the
    whole-file save is the only writer."""

    def __init__(self) -> None:
        self.state = PositionsState()

    def load(self) -> None:
        if not POSITIONS_FILE.exists():
            return
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.state = PositionsState(**raw)
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            print(f"[positions] could not load {POSITIONS_FILE}: {e}")
            self.state = PositionsState()

    def save(self) -> None:
        POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state.model_dump(), f, indent=2)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(value: float, hi: int) -> float:
        return max(0.0, min(float(hi), float(value)))

    def set_position(self, kind: str, item_id: str, x: float, y: float) -> Position:
        if kind not in ALLOWED_KINDS:
            raise ValueError(
                f"kind {kind!r} not allowed; expected one of {sorted(ALLOWED_KINDS)}"
            )
        pos = Position(
            x=self._clamp(x, VIEWBOX_WIDTH),
            y=self._clamp(y, VIEWBOX_HEIGHT),
        )
        bucket = self.state.positions.setdefault(kind, {})
        bucket[str(item_id)] = pos
        self.save()
        return pos

    def remove_position(self, kind: str, item_id: str) -> bool:
        bucket = self.state.positions.get(kind)
        if bucket and str(item_id) in bucket:
            del bucket[str(item_id)]
            self.save()
            return True
        return False

    def get(self, kind: str, item_id: str) -> Position | None:
        return (self.state.positions.get(kind) or {}).get(str(item_id))


position_manager = PositionManager()
position_manager.load()
