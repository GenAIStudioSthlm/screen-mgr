"""HTTP endpoints for the Scene model.

GET  /api/scenes              -> list all scenes
GET  /api/scenes/{scene_id}   -> detail
POST /api/scenes/{scene_id}/apply -> recall Hue scene + push per-zone screen content + reload-all

The actual apply logic lives in `SceneManager.apply()` so the Screens MCP
tool can reuse it without going through HTTP.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from models.scenes import scene_manager

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
    try:
        return await scene_manager.apply(scene_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Scene not found")
