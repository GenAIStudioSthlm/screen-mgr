"""Scene model — a recallable bundle of room state.

A Scene is a saved "look" for the studio: optionally a Hue scene to
recall (off the bridge's 28 native scenes), plus per-zone screen-content
overrides. Applying a scene:

  1. (if `hue_scene_id` set) tells the Hue module to recall that bridge
     scene — all the lights move to it
  2. For each entry in `zone_overrides`, finds the zone's screen and
     updates its content (type + value)
  3. Broadcasts a WebSocket reload to every connected screen so they
     pick up the new content immediately

Persisted to data/scenes.json. Loaded at startup.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError


SCENES_FILE = Path("data/scenes.json")


class ZoneOverride(BaseModel):
    """Per-zone content override applied as part of a scene."""

    content_type: str = Field(
        ..., description="A DisplayModule id (news, default, picture, ...)"
    )
    content_value: str = Field(
        "", description="Type-specific value; ignored for 'default' and 'news'"
    )
    news_mode: Optional[str] = Field(
        None,
        description="Only meaningful when content_type=='news'; one of portrait/landscape/presentation",
    )


class Scene(BaseModel):
    id: str = Field(..., description="Stable slug, e.g. 'welcome', 'workshop'")
    name: str = Field(..., description="Human-friendly label")
    description: str = Field("", description="Optional one-liner")
    hue_scene_id: Optional[str] = Field(
        None,
        description="Hue bridge scene id to recall on apply, e.g. 'I3UXeWySH3WBLRb' (Stockholm City Hall)",
    )
    zone_overrides: Dict[str, ZoneOverride] = Field(
        default_factory=dict,
        description="Map of zone_id -> override applied to that zone's screen",
    )


class SceneManager:
    def __init__(self) -> None:
        self.scenes: List[Scene] = []

    def load(self) -> None:
        if not SCENES_FILE.exists():
            self.scenes = _seed_scenes()
            self.save()
            return
        try:
            with open(SCENES_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.scenes = [Scene(**s) for s in raw]
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            print(f"[scenes] could not load {SCENES_FILE}: {e}")
            self.scenes = _seed_scenes()

    def save(self) -> None:
        SCENES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SCENES_FILE, "w", encoding="utf-8") as f:
            json.dump([s.model_dump() for s in self.scenes], f, indent=2)

    def get(self, scene_id: str) -> Optional[Scene]:
        for s in self.scenes:
            if s.id == scene_id:
                return s
        return None


def _seed_scenes() -> List[Scene]:
    """Two starter scenes so the dropdown isn't empty on first run.
    Operators can edit / add their own via the admin UI in Phase 7."""
    return [
        Scene(
            id="studio-logo",
            name="Studio Logo",
            description="All web screens to the Studio logo; no Hue change.",
            hue_scene_id=None,
            zone_overrides={
                "station-2": ZoneOverride(content_type="default"),
                "station-3": ZoneOverride(content_type="default"),
                "screen-2": ZoneOverride(content_type="default"),
                "screen-3": ZoneOverride(content_type="default"),
                "main-screen": ZoneOverride(content_type="default"),
            },
        ),
        Scene(
            id="ai-news",
            name="AI News",
            description="All connected web screens cycle through the AI news feed.",
            hue_scene_id=None,
            zone_overrides={
                "station-2": ZoneOverride(content_type="news", news_mode="presentation"),
                "station-3": ZoneOverride(content_type="news", news_mode="landscape"),
                "screen-2": ZoneOverride(content_type="news", news_mode="landscape"),
                "screen-3": ZoneOverride(content_type="news", news_mode="landscape"),
                "main-screen": ZoneOverride(content_type="news", news_mode="presentation"),
            },
        ),
    ]


scene_manager = SceneManager()
scene_manager.load()
