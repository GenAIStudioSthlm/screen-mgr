"""HTTP endpoints for floor-plan device positions.

The floor plan SVG in /admin reads positions from these endpoints to
render markers, and writes them back as the operator drags markers in
edit mode. Coords are in the 960×420 viewBox space the SVG uses;
out-of-range values are clamped server-side.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

from models.positions import ALLOWED_KINDS, position_manager


router = APIRouter()


@router.get("/api/positions", response_class=JSONResponse)
async def get_positions():
    """Return the full positions state. Empty kinds (or empty whole
    state) are valid — the frontend handles "no positions yet"."""
    return position_manager.state.model_dump()


@router.put("/api/positions/{kind}/{item_id}", response_class=JSONResponse)
async def set_position(kind: str, item_id: str, payload: dict = Body(...)):
    """Update one device's coords.

    Body: ``{"x": <float>, "y": <float>}``. ``kind`` must be one of
    the allowed set; the manager clamps coords to the viewBox
    bounds before saving.
    """
    if kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {sorted(ALLOWED_KINDS)}",
        )
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    try:
        x = float(payload["x"])
        y = float(payload["y"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail='body requires numeric "x" and "y"'
        )
    pos = position_manager.set_position(kind, item_id, x, y)
    return {"kind": kind, "id": item_id, "x": pos.x, "y": pos.y}


@router.delete("/api/positions/{kind}/{item_id}", response_class=JSONResponse)
async def delete_position(kind: str, item_id: str):
    """Remove a device's position (e.g. when it's retired). 404 if it
    wasn't placed in the first place."""
    if kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {sorted(ALLOWED_KINDS)}",
        )
    removed = position_manager.remove_position(kind, item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="no position for that device")
    return {"removed": True}
