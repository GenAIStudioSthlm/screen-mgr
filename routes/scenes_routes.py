"""HTTP endpoints for the Scene model.

GET  /api/scenes              -> list all scenes
GET  /api/scenes/{scene_id}   -> detail
POST /api/scenes/{scene_id}/apply -> recall Hue scene + push per-zone screen content + reload-all
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from connections import connection_manager
from models.scenes import scene_manager
from models.zones import zone_manager
from modules import registry
from screens import screen_manager

router = APIRouter()


@router.get("/api/scenes", response_class=JSONResponse)
async def list_scenes():
    return {"scenes": [s.model_dump() for s in scene_manager.scenes]}


@router.get("/api/scenes/{scene_id}", response_class=JSONResponse)
async def get_scene(scene_id: str):
    s = scene_manager.get(scene_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return s.model_dump()


@router.post("/api/scenes/{scene_id}/apply", response_class=JSONResponse)
async def apply_scene(scene_id: str):
    """Apply a scene: recall Hue, push per-zone screen content, broadcast reload."""
    scene = scene_manager.get(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    result = {
        "scene_id": scene.id,
        "hue": None,
        "screens_updated": [],
        "screens_failed": [],
        "reloaded": [],
    }

    # 1. Recall Hue scene if specified
    if scene.hue_scene_id:
        hue_module = registry.get("hue")
        if hue_module is not None and getattr(hue_module, "client", None) is not None:
            try:
                result["hue"] = hue_module.client.recall_scene(scene.hue_scene_id)
            except Exception as e:
                result["hue"] = {"error": str(e)}
        else:
            result["hue"] = {"error": "hue module unavailable or unpaired"}

    # 2. Push per-zone screen overrides
    for zone_id, override in scene.zone_overrides.items():
        zone = zone_manager.get(zone_id)
        if zone is None or zone.screen_id is None:
            result["screens_failed"].append({"zone": zone_id, "reason": "no screen mapped"})
            continue
        idx = zone.screen_id - 1
        if not (0 <= idx < len(screen_manager.screens)):
            result["screens_failed"].append(
                {"zone": zone_id, "reason": f"screen #{zone.screen_id} out of range"}
            )
            continue
        screen = screen_manager.screens[idx]
        # Apply the override fields
        screen.type = override.content_type
        ct = override.content_type
        cv = override.content_value or ""
        if ct == "text":
            screen.text = cv
        elif ct == "url":
            screen.url = cv
        elif ct == "video":
            screen.video = cv
        elif ct == "picture":
            screen.picture = cv
        elif ct == "pdf":
            screen.pdf = cv
        elif ct == "slideshow":
            screen.slideshow = cv
        elif ct == "screen_share":
            screen.screen_share = cv
        if ct == "news" and override.news_mode:
            screen.news_mode = override.news_mode
        result["screens_updated"].append(
            {"zone": zone_id, "screen_id": screen.id, "type": ct}
        )

    if result["screens_updated"]:
        screen_manager.save_screens()

    # 3. Broadcast reload to every connected screen
    for screen in screen_manager.screens:
        if screen.connected:
            try:
                await connection_manager.notify_screen(screen=screen)
                result["reloaded"].append(screen.id)
            except Exception as e:
                result["screens_failed"].append(
                    {"zone": None, "screen_id": screen.id, "reason": str(e)}
                )

    return result
