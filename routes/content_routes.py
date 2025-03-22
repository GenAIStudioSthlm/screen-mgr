# Admin page with form to update screen URLs.
from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


templates = Jinja2Templates(directory="templates")
router = APIRouter()


# ---------------------------------------------------------------------
# Default content for the screens.
# ---------------------------------------------------------------------
@router.get("/default/{screen_id}", response_class=HTMLResponse)
async def default_screen_page(request: Request, screen_id: str):
    return templates.TemplateResponse(
        "content/screen.html",
        {"request": request, "screen_id": screen_id},
    )


# ---------------------------------------------------------------------
# Responsive text
# ---------------------------------------------------------------------
@router.get("/responsive/{text}", response_class=HTMLResponse)
async def responsive_text(request: Request, text: str):
    return templates.TemplateResponse(
        "content/responsive-text.html",
        {"request": request, "text": text},
    )


# ---------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------
@router.get("/video/{video}", response_class=HTMLResponse)
async def show_video(request: Request, video: str):
    return templates.TemplateResponse(
        "content/video.html",
        {"request": request, "video": video},
    )


# ---------------------------------------------------------------------
# Picture
# ---------------------------------------------------------------------
@router.get("/picture/{picture}", response_class=HTMLResponse)
async def show_picture(request: Request, picture: str):
    return templates.TemplateResponse(
        "content/picture.html",
        {"request": request, "picture": picture},
    )


@router.get("/pdf/{presentation}", response_class=HTMLResponse)
async def show_presentation(request: Request, presentation: str):
    return templates.TemplateResponse(
        "content/pdf.html",
        {"request": request, "presentation": presentation},
    )
