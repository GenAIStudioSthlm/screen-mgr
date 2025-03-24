# Admin page with form to update screen URLs.
import os
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
@router.get("/picture/{folder}/{picture}", response_class=HTMLResponse)
async def show_picture(request: Request, folder: str, picture: str):
    print(f"Picture URL: {folder}")
    print(f"Picture URL: {picture}")

    if folder == "Root":
        url = picture
    else:
        url = f"{folder}/{picture}"

    return templates.TemplateResponse(
        "content/picture.html",
        {"request": request, "picture": url},  # Decode the URL-encoded slashes
    )


@router.get("/pdf/{presentation}", response_class=HTMLResponse)
async def show_presentation(request: Request, presentation: str):
    return templates.TemplateResponse(
        "content/pdf.html",
        {"request": request, "presentation": presentation},
    )


@router.get("/slideshow/{folder}", response_class=HTMLResponse)
async def show_slideshow(request: Request, folder: str):
    # Get the list of pictures in the specified folder
    slideshow_folder = os.path.join("static/pictures", folder)
    pictures = [
        file
        for file in os.listdir(slideshow_folder)
        if file.lower().endswith(("png", "jpg", "jpeg", "gif"))
    ]

    return templates.TemplateResponse(
        "content/slideshow.html",
        {"request": request, "folder": folder, "pictures": pictures},
    )
    
# ---------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------
@router.get("/youtube/{url:path}", response_class=HTMLResponse)
async def show_youtube(request: Request, url: str):
    # Decode URL if necessary
    decoded_url = url.replace('%3A', ':').replace('%2F', '/')
    return templates.TemplateResponse(
        "content/youtube.html",
        {"request": request, "video_url": decoded_url},
    )