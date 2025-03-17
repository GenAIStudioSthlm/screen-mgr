import logging
import sys
import json
from typing import Dict, List
import uvicorn
from fastapi import (
    FastAPI,
    Form,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()
# Mount a static folder (optional)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# File to store screen URLs
SCREENS_FILE = "screens.json"


# Load URLs for each screen from file
def load_screens() -> Dict[str, str]:
    try:
        with open(SCREENS_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {
            "screen1": "https://www.accenture.com/",
            "screen2": "https://www.figma.com/deck/d2k3EQKYNZmEA8wgqlDifH",
            "screen3": "",
            "screen4": "",
            "screen5": "",
        }


# Save URLs for each screen to file
def save_screens(screens: Dict[str, str]):
    with open(SCREENS_FILE, "w") as file:
        json.dump(screens, file, indent=4)


# Initialize screens dictionary
screens = load_screens()


class ConnectionManager:
    def __init__(self):
        # Mapping from screen id to a list of websocket connections.
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, screen_id: str, websocket: WebSocket):
        await websocket.accept()
        logger.info("Screen %s connected", screen_id)
        self.active_connections.setdefault(screen_id, []).append(websocket)

    def disconnect(self, screen_id: str, websocket: WebSocket):
        self.active_connections.get(screen_id, []).remove(websocket)

    async def broadcast(self, screen_id: str, message: dict):
        for connection in self.active_connections.get(screen_id, []):
            logger.info("Broadcasting new URL to screen %s: %s", screen_id, message)
            await connection.send_json(message)
        if not self.active_connections.get(screen_id, []):
            logger.warning("No active connections for screen %s", screen_id)


manager = ConnectionManager()


def get_default_content_url(base_url: str, screen_id: str) -> str:
    content_url = str(base_url) + f"default/{screen_id}"
    return content_url


# Admin page with form to update screen URLs.
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(
        "admin.html", {"request": request, "screens": screens}
    )


@app.post("/admin/update")
async def update_screens(
    request: Request,
    screen1: str = Form(...),
    screen2: str = Form(...),
    screen3: str = Form(...),
    screen4: str = Form(...),
    screen5: str = Form(...),
):
    logger.info("Base url: %s", request.base_url)

    screens["screen1"] = (
        screen1 if screen1 else str(request.base_url) + "default/screen1"
    )
    screens["screen2"] = (
        screen2 if screen2 else str(request.base_url) + "default/screen2"
    )
    screens["screen3"] = (
        screen3 if screen3 else str(request.base_url) + "default/screen3"
    )
    screens["screen4"] = (
        screen4 if screen4 else str(request.base_url) + "default/screen4"
    )
    screens["screen5"] = (
        screen5 if screen5 else str(request.base_url) + "default/screen5"
    )

    # Save updated URLs to file
    save_screens(screens)

    # Notify each screen with its new URL.
    for screen_id, url in screens.items():
        await manager.broadcast(screen_id, {"type": "refresh", "newContentUrl": url})
    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------------------------------------------------
# Screen page route: each screen accesses its unique page.
# ---------------------------------------------------------------------
@app.get("/screen/{screen_id}", response_class=HTMLResponse)
async def screen_page(request: Request, screen_id: str):
    print(f"Screen {screen_id} connected.")
    print(screens)
    content_url = screens.get(screen_id, "http://default-url.com")
    if not content_url:
        base_url = str(request.base_url)  # e.g., 'http://192.168.2.65:8000/'
        content_url = base_url + f"default/{screen_id}"
    print(f"Screen {screen_id} connected with URL: {content_url}")
    return templates.TemplateResponse(
        "screen.html",
        {"request": request, "screen_id": screen_id, "content_url": content_url},
    )


# ---------------------------------------------------------------------
# Default content for the screens.
# ---------------------------------------------------------------------
@app.get("/default/{screen_id}", response_class=HTMLResponse)
async def default_screen_page(request: Request, screen_id: str):
    return templates.TemplateResponse(
        "default/screen.html",
        {"request": request, "screen_id": screen_id},
    )


# ---------------------------------------------------------------------
# WebSocket endpoint for each screen.
# ---------------------------------------------------------------------
@app.websocket("/ws/{screen_id}")
async def websocket_endpoint(websocket: WebSocket, screen_id: str):
    await manager.connect(screen_id, websocket)
    try:
        while True:
            # Keep the connection alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(screen_id, websocket)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
