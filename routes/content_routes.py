# Admin page with form to update screen URLs.
import os
from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from utils import APP_VERSION


templates = Jinja2Templates(directory="templates")
templates.env.globals["app_version"] = APP_VERSION
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
# Updating page (transient — shown to screens during deploys, then
# auto-redirects back to the original content URL via ?return_to=).
# ---------------------------------------------------------------------
@router.get("/updating", response_class=HTMLResponse)
async def updating_page(request: Request):
    return templates.TemplateResponse(
        "content/updating.html",
        {"request": request},
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
    decoded_url = url.replace("%3A", ":").replace("%2F", "/")
    return templates.TemplateResponse(
        "content/youtube.html",
        {"request": request, "video_url": decoded_url},
    )


# Add this function to routes/content_routes.py
@router.get("/screen-share/{room_id}", response_class=HTMLResponse)
async def screen_share(request: Request, room_id: str):
    return templates.TemplateResponse(
        "content/screen_share.html",
        {"request": request, "room_id": room_id},
    )


# ---------------------------------------------------------------------
# Gradient — animated brand gradient that mimics the zone's lighting.
# The page renders an initial gradient and then polls the JSON endpoint
# so the screen tracks its zone's Hue lights live.
# ---------------------------------------------------------------------
@router.get("/gradient/{screen_id}", response_class=HTMLResponse)
async def show_gradient(request: Request, screen_id: int):
    from models.studio_map import screen_gradient_spec

    spec = screen_gradient_spec(screen_id)
    return templates.TemplateResponse(
        "content/gradient.html",
        {"request": request, **spec},
    )


@router.get("/api/studio/screen/{screen_id}/gradient")
async def api_screen_gradient(screen_id: int):
    """Live gradient spec (zone + current light colours) for polling."""
    from fastapi.responses import JSONResponse
    from models.studio_map import screen_gradient_spec

    return JSONResponse(screen_gradient_spec(screen_id))


@router.get("/api/studio/state")
async def api_studio_state(plan: str = "popup"):
    """All zones with live light colours + real screen state, in one call.
    The /admin/studio floor plan polls this to mirror the real room."""
    from fastapi.responses import JSONResponse
    from models.studio_map import studio_state

    return JSONResponse(studio_state(plan))


@router.get("/api/studio/brands")
async def api_studio_brands():
    from fastapi.responses import JSONResponse
    from models.brands import BRANDS

    return JSONResponse({"brands": list(BRANDS.values())})


@router.post("/api/studio/brand/{brand_id}/apply")
async def api_studio_apply_brand(brand_id: str):
    """Apply a brand: set the studio lights to the palette and switch the
    zones' connected screens to the gradient content type (so they mimic the
    new lighting). Shared logic lives in models.brands.apply_brand_full."""
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from models.brands import apply_brand_full

    result = await apply_brand_full(brand_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "unknown brand"))
    return JSONResponse(result)


@router.post("/api/studio/brand/{brand_id}/save")
async def api_studio_save_brand(brand_id: str):
    """Capture the CURRENT studio state (per-zone light colours + screen content)
    and persist it as this brand's profile, so live tweaks become the default."""
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from models.brands import save_brand_profile

    result = save_brand_profile(brand_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "unknown brand"))
    return JSONResponse(result)
