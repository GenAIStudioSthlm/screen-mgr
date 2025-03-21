from typing import Dict, List
from fastapi import WebSocket
from logger import logger
from screens import Screen, screen_manager


class ConnectionManager:
    def __init__(self):
        # Mapping from screen id to a list of websocket connections.
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, screen_id: str, websocket: WebSocket):
        try:
            screen_index = int(screen_id) - 1
            # if screen_index < 0 or screen_index >= len(screen_manager.screens):
            #    print(f"Screen ID {screen_id} out of range")
            #    print(len(screen_manager.screens))
            #    raise ValueError("Screen ID out of range")
            await websocket.accept()
            logger.info("Screen %s connected", screen_id)
            screen_manager.screens[screen_index].connected = True
            screen_manager.screens[screen_index].websocket = websocket
            screen_manager.print_screens()
            # return True

        except ValueError:
            logger.error("Invalid screen ID: %s", screen_id)
            return False

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
            "pdf": screen.pdf,
        }
        # connection = self.active_connections.get(str(screen.id), [])
        if screen.connected:
            logger.info("Notifying screen %i: %s", screen.id, message)
            await screen.websocket.send_json(message)
        else:
            logger.warning("No active connections for screen %i", screen.id)


connection_manager = ConnectionManager()
