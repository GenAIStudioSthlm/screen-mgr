"""HTTP endpoints for Zone — the redesigned admin's primary noun.

GET  /api/zones           → list every zone with its current screen + light state
GET  /api/zones/{zone_id} → detail for one zone
PUT  /api/zones/{zone_id} → update screen_id / light_group_id / polygon / label / area
"""

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

from connections import connection_manager  # noqa: F401  (placeholder for later phases)
from models.zones import zone_manager
from screens import screen_manager

router = APIRouter()


def _zone_payload(zone) -> dict:
    """Hydrate a zone with the live screen + Hue summary so the floor plan
    has everything it needs in one request."""
    payload = zone.model_dump()

    if zone.screen_id is not None:
        idx = zone.screen_id - 1
        if 0 <= idx < len(screen_manager.screens):
            s = screen_manager.screens[idx]
            payload["screen"] = {
                "id": s.id,
                "name": s.name,
                "type": s.type,
                "connected": s.connected,
                "client_host": getattr(s, "client_host", None),
            }

    # light group info is filled in by the client when it fetches /api/modules/hue/groups
    return payload


@router.get("/api/zones", response_class=JSONResponse)
async def list_zones():
    return {"zones": [_zone_payload(z) for z in zone_manager.zones]}


@router.get("/api/zones/{zone_id}", response_class=JSONResponse)
async def get_zone(zone_id: str):
    z = zone_manager.get(zone_id)
    if z is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    return _zone_payload(z)


@router.put("/api/zones/{zone_id}", response_class=JSONResponse)
async def update_zone(zone_id: str, patch: dict = Body(...)):
    z = zone_manager.get(zone_id)
    if z is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Whitelist the editable fields for now — id is immutable.
    editable = {"name", "screen_id", "light_group_id", "polygon", "label_xy", "area_label"}
    changed = False
    for k, v in (patch or {}).items():
        if k not in editable:
            continue
        setattr(z, k, v)
        changed = True

    if changed:
        zone_manager.save()
    return _zone_payload(z)
