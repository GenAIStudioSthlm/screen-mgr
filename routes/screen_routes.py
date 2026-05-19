from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from modules import registry
from modules.base import DisplayModule
from modules.default import DefaultModule
from screens import screen_manager
from utils import APP_VERSION


templates = Jinja2Templates(directory="templates")
templates.env.globals["app_version"] = APP_VERSION
router = APIRouter()


# Fallback display module used when a screen's `type` doesn't match any
# registered DisplayModule.
_DEFAULT_DISPLAY: DisplayModule = DefaultModule()


def _resolve_display_module(screen_type: str) -> DisplayModule:
    module = registry.get(screen_type)
    if isinstance(module, DisplayModule) and registry.is_enabled(module.id):
        return module
    return _DEFAULT_DISPLAY


# ---------------------------------------------------------------------
# Screen page route: each screen accesses its unique page.
# ---------------------------------------------------------------------
@router.get("/screen/{screen_id}", response_class=HTMLResponse)
async def screen_page(request: Request, screen_id: str):
    print(f"Screen {screen_id} connected.")
    try:
        screen_index = int(screen_id) - 1
    except ValueError:
        return "Invalid screen ID."

    if screen_index < 0 or screen_index >= len(screen_manager.screens):
        return "Screen ID out of range."

    screen = screen_manager.screens[screen_index]
    base_url = str(request.base_url)  # e.g. 'http://192.168.2.65:8000/'

    module = _resolve_display_module(screen.type)
    content_url = module.get_screen_url(screen, base_url)

    print(f"Screen {screen_id} ({screen.type} -> {module.id}) content URL: {content_url}")
    return templates.TemplateResponse(
        "screen.html",
        {"request": request, "screen_id": screen_id, "content_url": content_url},
    )
