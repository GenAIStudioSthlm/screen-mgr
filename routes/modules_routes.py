"""HTTP endpoints for the module registry.

GET  /api/modules                       → list every registered module + status
GET  /api/modules/{id}                  → detail for one
POST /api/modules/{id}/enable           → flip enabled=True
POST /api/modules/{id}/disable          → flip enabled=False
POST /api/modules/{id}/start            → service modules only — run start()
POST /api/modules/{id}/stop             → service modules only — run stop()

POST /api/modules/external              → register a new external module by
                                          manifest URL (body: {manifest_url})
DELETE /api/modules/external/{id}       → remove an external module
POST /api/modules/refresh               → re-fetch every configured external
                                          manifest
GET  /api/modules/external              → list configured external entries
"""

from fastapi import APIRouter, Body, HTTPException
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


# ---------------------------------------------------------------------
# External modules — registered via a JSON manifest URL the module hosts.
# ---------------------------------------------------------------------

@router.get("/api/modules/external", response_class=JSONResponse)
async def list_external_modules():
    return {"external": registry.external_entries()}


@router.post("/api/modules/external", response_class=JSONResponse)
async def add_external_module(payload: dict = Body(...)):
    manifest_url = (payload or {}).get("manifest_url", "").strip()
    if not manifest_url:
        raise HTTPException(status_code=400, detail="manifest_url is required")
    try:
        info = registry.add_external(manifest_url)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not register manifest at {manifest_url}: {e}",
        )
    return info


@router.delete("/api/modules/external/{module_id}", response_class=JSONResponse)
async def remove_external_module(module_id: str):
    removed = registry.remove_external(module_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No such external module")
    return {"id": module_id, "removed": True}


@router.post("/api/modules/refresh", response_class=JSONResponse)
async def refresh_external_manifests():
    return {"results": registry.load_external()}
