"""Music presets — named one-click "play this mood" buttons.

Each preset bundles a search query (resolved against Spotify at
play-time), an optional explicit `spotify_uri` override, a target
device query (default `"marantz"`), and a default volume.

Persisted to `data/music_presets.json`; seeded with 3 starters
(Chill Vibes / Energy / Chaotic) on first run. Operators can edit
the JSON to tweak queries, add new presets, or change volumes
without touching code.

Shared by:
  - HTTP routes  /api/music/presets[/{id}/play]
  - MCP tools    list_presets, play_preset
  - Admin UI     Music view preset buttons
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

from mcps.audio.safety import cap_volume, max_output_volume_pct
from mcps.music.spotify_client import call


PRESETS_FILE = Path("data/music_presets.json")
DEFAULT_DEVICE_QUERY = "marantz"


class MusicPreset(BaseModel):
    """A named one-click playback preset."""

    id: str = Field(..., description="Stable slug, e.g. 'chill-vibes'")
    name: str = Field(..., description="Human label shown on the button")
    description: str = Field("", description="One-line subtitle")
    search_query: str = Field(
        "", description="Free-text Spotify search; first result is played"
    )
    search_type: str = Field(
        "playlist",
        description="One of track / album / artist / playlist (default playlist)",
    )
    spotify_uri: Optional[str] = Field(
        None,
        description="If set, played directly without a search (overrides search_query)",
    )
    device_query: str = Field(
        DEFAULT_DEVICE_QUERY,
        description="Spotify Connect device substring match, default 'marantz'",
    )
    default_volume_pct: int = Field(25, ge=0, le=100)
    icon: str = Field("", description="Optional emoji shown on the button")


class PresetManager:
    def __init__(self) -> None:
        self.presets: List[MusicPreset] = []

    def load(self) -> None:
        if not PRESETS_FILE.exists():
            self.presets = _seed_presets()
            self.save()
            return
        try:
            with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.presets = [MusicPreset(**p) for p in raw]
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            print(f"[music_presets] could not load {PRESETS_FILE}: {e}")
            self.presets = _seed_presets()

    def save(self) -> None:
        PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump([p.model_dump() for p in self.presets], f, indent=2)

    def get(self, preset_id: str) -> Optional[MusicPreset]:
        for p in self.presets:
            if p.id == preset_id:
                return p
        return None


def _seed_presets() -> List[MusicPreset]:
    """Three starter presets keyed to the studio's mood vocabulary."""
    return [
        MusicPreset(
            id="chill-vibes",
            name="Chill Vibes",
            description="Lo-Fi Girl beats to relax/study to",
            search_query="Lofi Girl beats to relax study to",
            search_type="playlist",
            default_volume_pct=20,
            icon="🌿",
        ),
        MusicPreset(
            id="energy",
            name="Energy",
            description="Northern House Rarities 1989-90-91-99",
            search_query="Northern House Rarities 1989",
            search_type="playlist",
            default_volume_pct=35,
            icon="⚡",
        ),
        MusicPreset(
            id="chaotic",
            name="Chaotic",
            description="Jazz fusion — Mahavishnu, Weather Report, Return to Forever",
            search_query="Jazz Fusion essentials",
            search_type="playlist",
            default_volume_pct=30,
            icon="🌀",
        ),
    ]


# ----------------------------------------------------------------------
# Playback flow
# ----------------------------------------------------------------------


def _find_device(devices_payload: dict, query: str) -> Optional[dict]:
    if not isinstance(devices_payload, dict):
        return None
    devices = devices_payload.get("devices") or []
    q = query.lower().strip()
    for d in devices:
        if (d.get("name") or "").lower() == q:
            return d
    for d in devices:
        if q in (d.get("name") or "").lower():
            return d
    return None


def _first_item_uri(search_payload: dict, search_type: str) -> Optional[tuple[str, str]]:
    """Find the first hit's URI + a human label."""
    key_map = {
        "track": "tracks",
        "album": "albums",
        "artist": "artists",
        "playlist": "playlists",
    }
    bucket = (search_payload or {}).get(key_map.get(search_type, "tracks")) or {}
    items = bucket.get("items") or []
    if not items:
        return None
    it = items[0]
    if not it or not it.get("uri"):
        return None
    label_parts = [it.get("name") or "?"]
    if search_type == "track":
        artists = ", ".join(a.get("name", "?") for a in (it.get("artists") or []))
        if artists:
            label_parts.append("— " + artists)
    elif search_type == "playlist":
        owner = (it.get("owner") or {}).get("display_name") or ""
        if owner:
            label_parts.append("(" + owner + ")")
    return (it["uri"], " ".join(label_parts))


async def play_preset(
    preset_id: str,
    device_query_override: Optional[str] = None,
    volume_pct_override: Optional[int] = None,
) -> dict:
    """Resolve `preset_id` → device + uri, set volume, start playback.

    Unlike `run_speaker_test`, this does NOT auto-pause — the preset
    keeps playing until the operator stops it (via Spotify or the
    Music view)."""
    preset = preset_manager.get(preset_id)
    if preset is None:
        return {"error": f"preset {preset_id!r} not found"}

    device_query = (device_query_override or preset.device_query).strip()
    requested_vol = (
        int(volume_pct_override)
        if volume_pct_override is not None
        else preset.default_volume_pct
    )
    volume_pct, vol_capped = cap_volume(requested_vol)

    result: dict = {
        "preset_id": preset.id,
        "preset_name": preset.name,
        "device_query": device_query,
        "volume_pct": volume_pct,
    }
    if vol_capped:
        result["volume_capped"] = True
        result["requested_pct"] = requested_vol
        result["ceiling_pct"] = max_output_volume_pct()

    # 1. Devices
    devices_resp = call(lambda c: c.devices())
    if "error" in devices_resp:
        result["error"] = devices_resp["error"]
        result["detail"] = devices_resp.get("detail")
        return result
    result["devices_visible"] = [
        {"id": d.get("id"), "name": d.get("name"), "type": d.get("type")}
        for d in (devices_resp.get("data") or {}).get("devices", [])
    ]
    device = _find_device(devices_resp.get("data") or {}, device_query)
    if device is None:
        result["error"] = f"no Spotify device matching {device_query!r}"
        result["hint"] = (
            "Open Spotify on the target speaker so it shows up as a "
            "Connect device, then retry."
        )
        return result
    result["device"] = {"id": device.get("id"), "name": device.get("name")}

    # 2. URI — explicit override wins over search.
    if preset.spotify_uri:
        target_uri = preset.spotify_uri
        target_label = "(explicit URI)"
    else:
        search_resp = call(
            lambda c: c.search(
                q=preset.search_query, type=preset.search_type, limit=1
            )
        )
        if "error" in search_resp:
            result["error"] = search_resp["error"]
            result["detail"] = search_resp.get("detail")
            return result
        hit = _first_item_uri(search_resp.get("data") or {}, preset.search_type)
        if hit is None:
            result["error"] = (
                f"Spotify returned no {preset.search_type} results for "
                f"{preset.search_query!r}"
            )
            return result
        target_uri, target_label = hit
    result["target"] = {"uri": target_uri, "label": target_label}

    # 3. Volume (best-effort — don't abort if it fails)
    vol_resp = call(
        lambda c: c.volume(volume_pct, device_id=device["id"])
    )
    if "error" in vol_resp:
        result["volume_error"] = vol_resp

    # 4. Play
    def _start(c):
        kwargs: dict = {"device_id": device["id"]}
        if target_uri.startswith("spotify:track:"):
            kwargs["uris"] = [target_uri]
        else:
            kwargs["context_uri"] = target_uri
        c.start_playback(**kwargs)
        return {"started": True}

    play_resp = call(_start)
    if "error" in play_resp:
        result["error"] = play_resp["error"]
        result["detail"] = play_resp.get("detail")
        return result

    result["playback_started"] = True
    return result


preset_manager = PresetManager()
preset_manager.load()
