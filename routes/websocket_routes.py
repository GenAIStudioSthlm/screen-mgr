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
    print(f"(/ws/{screen_id}) Screen {screen_id} connected to WebSocket")

    await connection_manager.connect(screen_id, websocket)

    try:
        while True:
            # Keep the connection alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(screen_id)


# ---------------------------------------------------------------------
# WebSocket endpoint for admin screen status updates
# ---------------------------------------------------------------------
@router.websocket("/ws-screen-status")
async def screen_status_endpoint(websocket: WebSocket):
    print("Admin connected to screen status WebSocket")

    await connection_manager.connect_admin(websocket)

    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect_admin(websocket)
