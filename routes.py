# Admin page with form to update screen URLs.
import json
import os
from fastapi import (
    APIRouter,
    File,
    Form,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from screens import screen_manager
from connections import connection_manager


templates = Jinja2Templates(directory="templates")
router = APIRouter()

VIDEO_FOLDER = "static/videos"
os.makedirs(VIDEO_FOLDER, exist_ok=True)
PICTURE_FOLDER = "static/pictures"
os.makedirs(PICTURE_FOLDER, exist_ok=True)


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "screens": screen_manager.screens,
            "videos": os.listdir(VIDEO_FOLDER),
            "pictures": os.listdir(PICTURE_FOLDER),
        },
    )


@router.post("/admin/update")
async def update_screens(
    request: Request,
):
    form_data = await request.form()
    form_data_dict = dict(form_data)
    print("Form data received:")
    print(json.dumps(form_data_dict, indent=4))

    print("Current screen data:")
    screen_manager.print_screens()  # Print current screen data

    for index in range(5):
        screen_manager.screens[index].type = form_data_dict[f"screen{index + 1}_type"]
        screen_manager.screens[index].url = form_data_dict[f"screen{index + 1}_url"]
        screen_manager.screens[index].text = form_data_dict[f"screen{index + 1}_text"]
        screen_manager.screens[index].video = form_data_dict[f"screen{index + 1}_video"]
        screen_manager.screens[index].picture = form_data_dict[
            f"screen{index + 1}_picture"
        ]

    print("Updated screen data:")
    screen_manager.print_screens()  # Print updated screen data
    # Save updated screen data to file

    # Save updated URLs to file
    screen_manager.save_screens()

    print("Notifying screens of URL updates...")
    # Notify each screen with its new URL.
    for screen in screen_manager.screens:
        if form_data_dict["update"] == "all" or form_data_dict["update"] == (
            "screen" + str(screen.id)
        ):
            await connection_manager.notify_screen(screen=screen)

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------------------------------------------------
# Screen page route: each screen accesses its unique page.
# ---------------------------------------------------------------------
@router.get("/screen/{screen_id}", response_class=HTMLResponse)
async def screen_page(request: Request, screen_id: int):
    print(f"Screen {screen_id} connected.")
    screen = screen_manager.screens[screen_id - 1]
    base_url = str(request.base_url)  # e.g., 'http://192.168.2.65:8000/'

    if screen.type == "text":
        content_url = base_url + f"responsive/{screen.text}"
    elif screen.type == "url":
        content_url = screen.url
    elif screen.type == "video":
        content_url = base_url + f"video/{screen.video}"
    elif screen.type == "picture":
        content_url = base_url + f"picture/{screen.picture}"
    else:
        content_url = base_url + f"default/{screen_id}"

    print(f"Screen {screen_id} connected with URL: {content_url}")
    return templates.TemplateResponse(
        "screen.html",
        {"request": request, "screen_id": screen_id, "content_url": content_url},
    )


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


# ---------------------------------------------------------------------
# WebSocket endpoint for each screen.
# ---------------------------------------------------------------------
@router.websocket("/ws/{screen_id}")
async def websocket_endpoint(websocket: WebSocket, screen_id: str):
    await connection_manager.connect(screen_id, websocket)
    try:
        while True:
            # Keep the connection alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(screen_id)


# Endpoint to update a screen's URL.
@router.post("/update")
async def update_screen(screen_id: str = Form(...), new_url: str = Form(...)):
    #    screen_manager.screens[screen_id] = new_url
    #    screen_manager.save_screens()
    #    await connection_manager.broadcast(
    #        screen_id, {"type": "refresh", "newContentUrl": new_url}
    #    )
    return {"message": "URL updated successfully"}


@router.post("/admin/upload_video")
async def upload_video(video_file: UploadFile = File(...)):
    # Ensure the uploaded file is an MP4
    if not video_file.filename.endswith(".mp4"):
        return {"error": "Only MP4 files are allowed."}

    # Save the file to the static folder
    file_path = os.path.join(VIDEO_FOLDER, video_file.filename)
    with open(file_path, "wb") as f:
        f.write(await video_file.read())

    print(f"Uploaded file saved to {file_path}")
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/upload_picture")
async def upload_picture(picture_file: UploadFile = File(...)):
    # Ensure the uploaded file is a PNG, GIF, or JPG
    if not (
        picture_file.filename.endswith(".png")
        or picture_file.filename.endswith(".gif")
        or picture_file.filename.endswith(".jpg")
        or picture_file.filename.endswith(".jpeg")
    ):
        return {"error": "Only PNG, GIF, JPG, and JPEG files are allowed."}

    # Save the file to the static folder
    file_path = os.path.join(PICTURE_FOLDER, picture_file.filename)
    with open(file_path, "wb") as f:
        f.write(await picture_file.read())

    print(f"Uploaded file saved to {file_path}")
    return RedirectResponse(url="/admin", status_code=303)
