from typing import Dict, List
from fastapi import WebSocket
from logger import logger
from screens import Screen, screen_manager


class ConnectionManager:
    def __init__(self):
        # Mapping from screen id to a list of websocket connections.
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, screen_id: str, websocket: WebSocket):
        await websocket.accept()
        logger.info("Screen %s connected", screen_id)

        # self.active_connections.setdefault(screen_id, []).append(websocket)
        screen_manager.screens[int(screen_id) - 1].connected = True
        screen_manager.screens[int(screen_id) - 1].websocket = websocket
        screen_manager.print_screens()

    def disconnect(self, screen_id: str):
        logger.warning("Screen %s disconnected", screen_id)
        # self.active_connections.get(screen_id, []).remove(websocket)
        screen_manager.screens[int(screen_id) - 1].connected = False

    async def notify_screen(self, screen: Screen):
        logger.info("Attempting to broadcast message to screen %i", screen.id)

        message = {
            "type": screen.type,
            "text": screen.text,
            "url": screen.url,
            "video": screen.video,
            "picture": screen.picture,
        }
        # connection = self.active_connections.get(str(screen.id), [])
        if screen.connected:
            logger.info("Notifying screen %i: %s", screen.id, message)
            await screen.websocket.send_json(message)
        if not self.active_connections.get(screen.id, []):
            logger.warning("No active connections for screen %i", screen.id)


connection_manager = ConnectionManager()
