from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)

from connections import connection_manager

router = APIRouter()


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
