"""HTTP endpoints for the module registry.

GET  /api/modules               → list every registered module + status
GET  /api/modules/{id}          → detail for one
POST /api/modules/{id}/enable   → flip enabled=True
POST /api/modules/{id}/disable  → flip enabled=False
POST /api/modules/{id}/start    → service modules only — run start()
POST /api/modules/{id}/stop     → service modules only — run stop()
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from modules import registry

router = APIRouter()


def _module_payload(module) -> dict:
    return {**module.to_dict(), "enabled": registry.is_enabled(module.id)}


@router.get("/api/modules", response_class=JSONResponse)
async def list_modules():
    return {"modules": [_module_payload(m) for m in registry.list()]}


@router.get("/api/modules/{module_id}", response_class=JSONResponse)
async def get_module(module_id: str):
    m = registry.get(module_id)
    if not m:
        raise HTTPException(status_code=404, detail="Module not found")
    return _module_payload(m)


@router.post("/api/modules/{module_id}/enable", response_class=JSONResponse)
async def enable_module(module_id: str):
    if not registry.get(module_id):
        raise HTTPException(status_code=404, detail="Module not found")
    registry.enable(module_id)
    return {"id": module_id, "enabled": True}


@router.post("/api/modules/{module_id}/disable", response_class=JSONResponse)
async def disable_module(module_id: str):
    if not registry.get(module_id):
        raise HTTPException(status_code=404, detail="Module not found")
    registry.disable(module_id)
    return {"id": module_id, "enabled": False}


@router.post("/api/modules/{module_id}/start", response_class=JSONResponse)
async def start_module(module_id: str):
    m = registry.get(module_id)
    if not m:
        raise HTTPException(status_code=404, detail="Module not found")
    if "service" not in m.type:
        raise HTTPException(
            status_code=400, detail=f"{module_id} is not a service module"
        )
    return m.start()


@router.post("/api/modules/{module_id}/stop", response_class=JSONResponse)
async def stop_module(module_id: str):
    m = registry.get(module_id)
    if not m:
        raise HTTPException(status_code=404, detail="Module not found")
    if "service" not in m.type:
        raise HTTPException(
            status_code=400, detail=f"{module_id} is not a service module"
        )
    return m.stop()
