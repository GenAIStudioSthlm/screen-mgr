import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from connections import connection_manager
from modules import registry
from modules.base import DisplayModule
from screens import screen_manager

router = APIRouter()

PICTURE_FOLDER = "static/pictures"
VIDEO_FOLDER = "static/videos"
PDF_FOLDER = "static/pdfs"


# ---------------------------------------------------------------------
# Get available pictures
# ---------------------------------------------------------------------
@router.get("/api/pictures", response_class=JSONResponse)
async def get_available_pictures():
    pictures = {}
    for root, dirs, files in os.walk(PICTURE_FOLDER):
        folder = os.path.relpath(root, PICTURE_FOLDER)
        folder = folder if folder != "." else "Root"
        pictures[folder] = [
            file
            for file in files
            if file.lower().endswith(("png", "jpg", "jpeg", "gif"))
        ]
    return {"pictures": pictures}


# ---------------------------------------------------------------------
# Get available videos
# ---------------------------------------------------------------------
@router.get("/api/videos", response_class=JSONResponse)
async def get_available_videos():
    if not os.path.isdir(VIDEO_FOLDER):
        return {"videos": []}
    return {
        "videos": sorted(
            f for f in os.listdir(VIDEO_FOLDER)
            if f.lower().endswith((".mp4", ".webm", ".mov", ".m4v"))
        )
    }


# ---------------------------------------------------------------------
# Get available PDFs
# ---------------------------------------------------------------------
@router.get("/api/pdfs", response_class=JSONResponse)
async def get_available_pdfs():
    if not os.path.isdir(PDF_FOLDER):
        return {"pdfs": []}
    return {
        "pdfs": sorted(
            f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")
        )
    }


# ---------------------------------------------------------------------
# Get available slideshows (picture subfolders)
# ---------------------------------------------------------------------
@router.get("/api/slideshows", response_class=JSONResponse)
async def get_available_slideshows():
    if not os.path.isdir(PICTURE_FOLDER):
        return {"slideshows": []}
    return {
        "slideshows": sorted(
            f for f in os.listdir(PICTURE_FOLDER)
            if os.path.isdir(os.path.join(PICTURE_FOLDER, f))
        )
    }


# ---------------------------------------------------------------------
# Get current screen content (screens.json)
# ---------------------------------------------------------------------
@router.get("/api/screens", response_class=JSONResponse)
async def get_screens():
    return {
        "screens": [
            screen.model_dump(exclude={"websocket"})
            for screen in screen_manager.screens
        ]
    }


# ---------------------------------------------------------------------
# Set content for a screen
# ---------------------------------------------------------------------
@router.post("/api/screens/{screen_id}/set_content", response_class=JSONResponse)
async def set_screen_content(
    screen_id: int, content_type: str = Form(...), content_value: str = Form(...)
):
    try:
        screen = next((s for s in screen_manager.screens if s.id == screen_id), None)
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")

        # Valid content types are the ids of currently-registered display modules.
        valid_types = {
            m.id for m in registry.list()
            if isinstance(m, DisplayModule) and registry.is_enabled(m.id)
        }
        if content_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid content type '{content_type}'. Valid: {sorted(valid_types)}",
            )

        # Update the screen's content based on the type
        screen.type = content_type
        if content_type == "text":
            screen.text = content_value
        elif content_type == "url":
            screen.url = content_value
        elif content_type == "video":
            screen.video = content_value
        elif content_type == "picture":
            screen.picture = content_value
        elif content_type == "pdf":
            screen.pdf = content_value
        elif content_type == "slideshow":
            screen.slideshow = content_value
        elif content_type == "news":
            # For news, content_value carries the display mode
            # (portrait / landscape / presentation) so the model's
            # pattern validator accepts the assignment.
            if content_value in {"portrait", "landscape", "presentation"}:
                screen.news_mode = content_value
        elif content_type == "screen_share":
            screen.screen_share = content_value
        # "default" needs no content_value — type alone routes to the studio logo

        # Save the updated screens to the file
        screen_manager.save_screens()
        await connection_manager.notify_screen(screen=screen)

        return {"message": f"Screen {screen_id} updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------
# Broadcast reload to every connected screen
# ---------------------------------------------------------------------
@router.post("/api/screens/reload-all", response_class=JSONResponse)
async def reload_all_screens():
    notified: list[int] = []
    skipped: list[dict] = []
    for screen in screen_manager.screens:
        if not screen.connected:
            skipped.append({"id": screen.id, "reason": "not connected"})
            continue
        try:
            await connection_manager.notify_screen(screen=screen)
            notified.append(screen.id)
        except Exception as e:
            skipped.append({"id": screen.id, "reason": str(e)})
    return {
        "notified": notified,
        "skipped": skipped,
        "total": len(screen_manager.screens),
    }


# ---------------------------------------------------------------------
# Upload a picture
# ---------------------------------------------------------------------
@router.post("/api/upload/picture", response_class=JSONResponse)
async def upload_picture(
    file: UploadFile = File(...),
    subfolder: str = Form(""),
):
    try:
        # Treat "Root" / "" the same — both mean the top-level pictures dir.
        # Sanitize subfolder: strip any path separators so we never escape
        # the pictures directory.
        sf = (subfolder or "").strip().strip("/\\")
        if sf.lower() == "root":
            sf = ""
        if any(part in ("..", "") for part in sf.split("/")) and sf:
            raise HTTPException(status_code=400, detail="Invalid subfolder")

        target_folder = os.path.join(PICTURE_FOLDER, sf) if sf else PICTURE_FOLDER
        os.makedirs(target_folder, exist_ok=True)

        file_path = os.path.join(target_folder, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())

        rel = (sf + "/" + file.filename) if sf else file.filename
        return {"message": f"Picture '{rel}' uploaded successfully", "path": rel}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------
# Upload a video
# ---------------------------------------------------------------------
@router.post("/api/upload/video", response_class=JSONResponse)
async def upload_video(file: UploadFile = File(...)):
    try:
        file_path = os.path.join(VIDEO_FOLDER, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        return {"message": f"Video '{file.filename}' uploaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------
# Upload a PDF
# ---------------------------------------------------------------------
@router.post("/api/upload/pdf", response_class=JSONResponse)
async def upload_pdf(file: UploadFile = File(...)):
    try:
        file_path = os.path.join(PDF_FOLDER, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        return {"message": f"PDF '{file.filename}' uploaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
