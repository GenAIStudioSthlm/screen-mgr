from typing import Dict, List, Optional
from fastapi import WebSocket
from logger import logger
from screens import Screen, screen_manager


class ConnectionManager:
    def __init__(self):
        # Mapping from screen id to a list of websocket connections.
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # List of WebSocket connections for admin panel
        self.admin_connections: List[WebSocket] = []

    async def connect(self, screen_id: str, websocket: WebSocket):
        print(f"Connecting screen {screen_id}...")
        try:
            screen_index = int(screen_id) - 1

            if screen_index < 0 or screen_index >= len(screen_manager.screens):
                logger.error("Screen ID %s out of range (have %d screens)", screen_id, len(screen_manager.screens))
                await websocket.close(code=1008, reason="Invalid screen ID")
                return False

            if screen_manager.screens[screen_index].connected:
                logger.warning("Screen %s is already connected", screen_id)
                await websocket.close(code=1000, reason="Screen already connected")
                return False

            await websocket.accept()
            client_host = websocket.client.host if websocket.client else None
            logger.info("Screen %s connected from %s", screen_id, client_host)
            screen_manager.screens[screen_index].connected = True
            screen_manager.screens[screen_index].websocket = websocket
            screen_manager.screens[screen_index].client_host = client_host
            # screen_manager.print_screens()

            # Notify all admin clients about the new screen connection
            await self.broadcast_screen_status(screen_id, True, client_host)

        except ValueError:
            logger.error("Invalid screen ID: %s", screen_id)
            return False

    async def connect_admin(self, websocket: WebSocket):
        await websocket.accept()
        logger.info("Admin client connected")
        self.admin_connections.append(websocket)

        # Send initial status for all screens to the new admin client
        for screen in screen_manager.screens:
            await self.send_screen_status(
                websocket, str(screen.id), screen.connected, screen.client_host
            )

    def disconnect(self, screen_id: str):
        logger.warning("Screen %s disconnected", screen_id)
        screen_index = int(screen_id) - 1
        if 0 <= screen_index < len(screen_manager.screens):
            screen_manager.screens[screen_index].connected = False
            screen_manager.screens[screen_index].client_host = None
        else:
            logger.error("Screen ID %s out of range on disconnect", screen_id)
            return

        # Notify all admin clients
        # about the screen disconnection
        self.broadcast_screen_status_sync(screen_id, False)

    def disconnect_admin(self, websocket: WebSocket):
        logger.warning("Admin client disconnected")
        if websocket in self.admin_connections:
            self.admin_connections.remove(websocket)

    async def notify_screen(self, screen: Screen):
        logger.info("Attempting to broadcast message to screen %i", screen.id)

        # Compute the screen's CURRENT content URL via the module registry, so
        # the client doesn't have to trust its stale window.contentUrl from
        # when the frame first loaded. The URL we send is a path (leading
        # slash) for backend-served types and an absolute URL for external
        # ones (e.g. type=url). screen.js resolves to the full URL.
        content_url = None
        try:
            from modules import registry as _reg
            from modules.base import DisplayModule
            from modules.default import DefaultModule
            m = _reg.get(screen.type)
            if not isinstance(m, DisplayModule) or not _reg.is_enabled(m.id):
                m = DefaultModule()
            content_url = m.get_screen_url(screen, "/")
        except Exception as e:
            logger.warning("notify_screen: could not compute content_url: %s", e)

        message = {
            "type": "reload",
            "content_url": content_url,
        }
        if screen.connected:
            logger.info("Notifying screen %i: %s", screen.id, message)
            await screen.websocket.send_json(message)
        else:
            logger.warning("No active connections for screen %i", screen.id)

    async def send_screen_status(
        self, websocket: WebSocket, screen_id: str, connected: bool, client_host: Optional[str] = None
    ):
        """Send status update for a specific screen to a specific admin client"""
        message = {
            "type": "screen_status_update",
            "screen_id": screen_id,
            "connected": connected,
            "client_host": client_host,
        }
        await websocket.send_json(message)

    async def broadcast_screen_status(self, screen_id: str, connected: bool, client_host: Optional[str] = None):
        """Send screen status update to all connected admin clients"""
        message = {
            "type": "screen_status_update",
            "screen_id": screen_id,
            "connected": connected,
            "client_host": client_host,
        }

        # Use a list to avoid "dictionary changed size during iteration" errors
        clients_to_remove = []

        for client in self.admin_connections:
            try:
                await client.send_json(message)
            except Exception as e:
                logger.error("Error sending to admin client: %s", str(e))
                clients_to_remove.append(client)

        # Remove disconnected clients
        for client in clients_to_remove:
            if client in self.admin_connections:
                self.admin_connections.remove(client)

    def broadcast_screen_status_sync(self, screen_id: str, connected: bool):
        """Non-async version to be called from disconnect method"""
        import asyncio

        # Create event loop or use existing one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Schedule broadcast
        loop.create_task(self.broadcast_screen_status(screen_id, connected))


connection_manager = ConnectionManager()
