"""/admin/v2 routes — the redesigned admin panel scaffolding.

Phase 1 of `TASKS/PLAN_REDESIGN.md` ships a preview page that demonstrates
the design tokens, theme toggle, and basic atoms. Later phases extend
this file with the zone-based admin (floor plan, sidebar views, etc.)
while the existing /admin keeps working.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from utils import APP_VERSION


templates = Jinja2Templates(directory="templates")
templates.env.globals["app_version"] = APP_VERSION

router = APIRouter()


# Cutover (2026-05-21): the redesigned admin is now the primary at /admin.
# /admin/v2 is kept as an alias for one cycle. /admin/legacy still serves the
# original Tailwind-based admin in case operators need to fall back.

@router.get("/admin", response_class=HTMLResponse)
async def admin_index(request: Request):
    return templates.TemplateResponse(
        "admin/v2/index.html",
        {"request": request},
    )


@router.get("/admin/v2", response_class=HTMLResponse)
async def admin_v2_alias(request: Request):
    """Alias kept for one release cycle so anyone bookmarked here still lands."""
    return templates.TemplateResponse(
        "admin/v2/index.html",
        {"request": request},
    )


@router.get("/admin/v2/preview", response_class=HTMLResponse)
async def admin_v2_preview(request: Request):
    """Phase 1 token preview — kept around for design-system reference."""
    return templates.TemplateResponse(
        "admin/v2/preview.html",
        {"request": request},
    )
