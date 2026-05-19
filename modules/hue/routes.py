"""HTTP endpoints for the Philips Hue module.

Lives at /api/modules/hue/* so it cohabitates with the rest of the
module registry endpoints. The Lights admin tab consumes these.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

from modules import registry

router = APIRouter()


def _client():
    module = registry.get("hue")
    if module is None:
        raise HTTPException(status_code=503, detail="Hue module not registered")
    client = getattr(module, "client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Hue not paired — run `python3 scripts/hue_pair.py` on studiopi",
        )
    return client


@router.get("/api/modules/hue/lights", response_class=JSONResponse)
async def get_lights():
    return _client().get_lights()


@router.get("/api/modules/hue/groups", response_class=JSONResponse)
async def get_groups():
    return _client().get_groups()


@router.get("/api/modules/hue/scenes", response_class=JSONResponse)
async def get_scenes():
    return _client().get_scenes()


@router.get("/api/modules/hue/config", response_class=JSONResponse)
async def get_config():
    return _client().get_config()


@router.put("/api/modules/hue/lights/{light_id}", response_class=JSONResponse)
async def set_light(light_id: str, state: dict = Body(...)):
    return _client().set_light(light_id, state)


@router.put("/api/modules/hue/groups/{group_id}", response_class=JSONResponse)
async def set_group(group_id: str, action: dict = Body(...)):
    return _client().set_group(group_id, action)


@router.post("/api/modules/hue/scenes/{scene_id}/recall", response_class=JSONResponse)
async def recall_scene(scene_id: str):
    return _client().recall_scene(scene_id)


@router.post("/api/modules/hue/all/on", response_class=JSONResponse)
async def all_on():
    return _client().all_on()


@router.post("/api/modules/hue/all/off", response_class=JSONResponse)
async def all_off():
    return _client().all_off()
