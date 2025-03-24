from fastapi import APIRouter, HTTPException, Form, UploadFile, File
from fastapi.responses import JSONResponse
import os
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

        if content_type not in ["text", "url", "video", "picture", "pdf", "slideshow"]:
            raise HTTPException(status_code=400, detail="Invalid content type")

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

        # Save the updated screens to the file
        screen_manager.save_screens()

        return {"message": f"Screen {screen_id} updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------
# Upload a picture
# ---------------------------------------------------------------------
@router.post("/api/upload/picture", response_class=JSONResponse)
async def upload_picture(file: UploadFile = File(...)):
    try:
        file_path = os.path.join(PICTURE_FOLDER, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        return {"message": f"Picture '{file.filename}' uploaded successfully"}
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
