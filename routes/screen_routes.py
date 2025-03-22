from urllib.parse import quote
from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from screens import screen_manager


templates = Jinja2Templates(directory="templates")
router = APIRouter()


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

    screen = screen_manager.screens[screen_index]
    base_url = str(request.base_url)  # e.g., 'http://192.168.2.65:8000/'

    if screen.type == "text":
        content_url = base_url + f"responsive/{quote(screen.text)}"
    elif screen.type == "url":
        content_url = screen.url
    elif screen.type == "video":
        content_url = base_url + f"video/{screen.video}"
    elif screen.type == "picture":
        content_url = base_url + f"picture/{(screen.picture.replace('/', '%2F'))}"
    elif screen.type == "pdf":
        content_url = base_url + f"pdf/{screen.pdf}"
    elif screen.type == "slideshow":
        content_url = base_url + f"slideshow/{screen.slideshow}"
    else:
        content_url = base_url + f"default/{screen_id}"

    print(f"Screen {screen_id} connected with URL: {content_url}")
    return templates.TemplateResponse(
        "screen.html",
        {"request": request, "screen_id": screen_id, "content_url": content_url},
    )
