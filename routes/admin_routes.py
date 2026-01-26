# Admin page with form to update screen URLs.
import json
import os
from fastapi import (
    APIRouter,
    File,
    Form,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from screens import screen_manager
from connections import connection_manager
from utils import delete_file


templates = Jinja2Templates(directory="templates")
router = APIRouter()

VIDEO_FOLDER = "static/videos"
os.makedirs(VIDEO_FOLDER, exist_ok=True)
PICTURE_FOLDER = "static/pictures"
os.makedirs(PICTURE_FOLDER, exist_ok=True)
PDF_FOLDER = "static/pdfs"
os.makedirs(PDF_FOLDER, exist_ok=True)


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    picture_subfolders = [
        f
        for f in os.listdir(PICTURE_FOLDER)
        if os.path.isdir(os.path.join(PICTURE_FOLDER, f))
    ]

    # Dictionary to store folders and their pictures
    uploaded_pictures = {}

    # Walk through the directory and its subfolders
    for root, dirs, files in os.walk(PICTURE_FOLDER):
        # Get the relative folder name
        folder = os.path.relpath(root, PICTURE_FOLDER)
        folder = folder if folder != "." else "Root"

        # Filter image files and add them to the dictionary
        pictures = [
            file
            for file in files
            if file.lower().endswith(("png", "jpg", "jpeg", "gif"))
        ]
        if pictures:
            uploaded_pictures[folder] = pictures

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "screens": screen_manager.screens,
            "videos": os.listdir(VIDEO_FOLDER),
            "pictures": os.listdir(PICTURE_FOLDER),
            "pdfs": os.listdir(PDF_FOLDER),
            "picture_subfolders": picture_subfolders,
            "uploaded_pictures": uploaded_pictures,
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

    for index in range(6):
        print(f"Updating screen {index + 1}...")
        screen_manager.screens[index].type = form_data_dict[f"screen{index + 1}_type"]
        screen_manager.screens[index].url = form_data_dict[f"screen{index + 1}_url"]
        screen_manager.screens[index].text = form_data_dict[f"screen{index + 1}_text"]
        screen_manager.screens[index].video = form_data_dict[f"screen{index + 1}_video"]

        # Sanitize the picture value to ensure it doesn't cause issues
        picture_value = form_data_dict[f"screen{index + 1}_picture"]
        if "/" in picture_value:
            picture_value = picture_value.replace(
                "/", os.sep
            )  # Replace '/' with the OS-specific separator
        screen_manager.screens[index].picture = picture_value
        screen_manager.screens[index].pdf = form_data_dict[f"screen{index + 1}_pdf"]
        screen_manager.screens[index].slideshow = form_data_dict[
            f"screen{index + 1}_slideshow"
        ]
        screen_manager.screens[index].news_mode = form_data_dict.get(
            f"screen{index + 1}_news_mode", "landscape"
        )

    # ---------------------------------------------------------
    # check if some screen whould overwrite all other screens
    # ---------------------------------------------------------
    if form_data_dict["update"].endswith("_all"):
        # get screen id to use
        screen_id = form_data_dict["update"].split("_")[0].replace("screen", "")
        screen_index = int(screen_id) - 1
        # set all other screens to the same values
        for index in range(6):
            if index != screen_index:
                screen_manager.screens[index].type = form_data_dict[
                    f"screen{screen_id}_type"
                ]
                screen_manager.screens[index].url = form_data_dict[
                    f"screen{screen_id}_url"
                ]
                screen_manager.screens[index].text = form_data_dict[
                    f"screen{screen_id}_text"
                ]
                screen_manager.screens[index].video = form_data_dict[
                    f"screen{screen_id}_video"
                ]
                screen_manager.screens[index].picture = form_data_dict[
                    f"screen{screen_id}_picture"
                ]
                screen_manager.screens[index].pdf = form_data_dict[
                    f"screen{screen_id}_pdf"
                ]
                screen_manager.screens[index].slideshow = form_data_dict[
                    f"screen{screen_id}_slideshow"
                ]
                screen_manager.screens[index].news_mode = form_data_dict.get(
                    f"screen{screen_id}_news_mode", "landscape"
                )

    print("Updated screen data:")
    screen_manager.print_screens()  # Print updated screen data
    # Save updated screen data to file

    # Save updated URLs to file
    screen_manager.save_screens()

    print("Notifying screens of URL updates...")
    # Notify each screen with its new URL.
    for screen in screen_manager.screens:
        if form_data_dict["update"].endswith("_all") or form_data_dict["update"] == (
            "screen" + str(screen.id)
        ):
            await connection_manager.notify_screen(screen=screen)

    return RedirectResponse(url="/admin", status_code=303)


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
    return RedirectResponse(url="/admin#videos", status_code=303)


@router.post("/admin/upload_picture")
async def upload_picture(
    picture_file: UploadFile = File(...),
    subfolder: str = Form(""),
    new_subfolder: str = Form(""),
):
    # Determine the target folder
    target_folder = PICTURE_FOLDER
    if new_subfolder:
        target_folder = os.path.join(PICTURE_FOLDER, new_subfolder)
    elif subfolder:
        target_folder = os.path.join(PICTURE_FOLDER, subfolder)

    # Ensure the target folder exists
    os.makedirs(target_folder, exist_ok=True)

    # Ensure the uploaded file is a valid image
    if not (
        picture_file.filename.endswith(".png")
        or picture_file.filename.endswith(".gif")
        or picture_file.filename.endswith(".jpg")
        or picture_file.filename.endswith(".jpeg")
    ):
        return {"error": "Only PNG, GIF, JPG, and JPEG files are allowed."}

    # Save the file to the target folder
    file_path = os.path.join(target_folder, picture_file.filename)
    with open(file_path, "wb") as f:
        f.write(await picture_file.read())

    print(f"Uploaded file saved to {file_path}")
    return RedirectResponse(url="/admin#pictures", status_code=303)


@router.post("/admin/upload_pdf")
async def upload_pdf(pdf_file: UploadFile = File(...)):
    # Ensure the uploaded file is a PDF
    if not pdf_file.filename.endswith(".pdf"):
        return {"error": "Only PDF files are allowed."}

    # Save the file to the static folder
    file_path = os.path.join(PDF_FOLDER, pdf_file.filename)
    with open(file_path, "wb") as f:
        f.write(await pdf_file.read())

    print(f"Uploaded file saved to {file_path}")
    return RedirectResponse(url="/admin#pdfs", status_code=303)


# Add this new route after the upload_pdf route
@router.post("/admin/delete_picture")
async def delete_picture(picture_filename: str = Form(...)):
    """Delete a Picture file."""
    file_path = os.path.join(PICTURE_FOLDER, picture_filename.replace("Root/", ""))
    print(f"Deleting picture: {file_path}")
    result = delete_file(file_path)
    if result.get("error"):
        return result
  
    return RedirectResponse(url="/admin#pictures", status_code=303)


@router.post("/admin/delete_pdf")
async def delete_pdf(pdf_filename: str = Form(...)):
    file_path = os.path.join(PDF_FOLDER, pdf_filename)
    result = delete_file(file_path)
    if result.get("error"):
        return result

    return RedirectResponse(url="/admin#pdfs", status_code=303)

@router.post("/admin/delete_video")
async def delete_video(video_filename: str = Form(...)):  
    
    file_path = os.path.join(VIDEO_FOLDER, video_filename)
    result = delete_file(file_path)
    if result.get("error"):
        return result

    return RedirectResponse(url="/admin#videos", status_code=303)      