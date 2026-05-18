import json
from typing import Any, Dict, List
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

    result = await connection_manager.connect(screen_id, websocket)
    if result is False:
        return

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


# Make sure this portion exists and is correct:

# ---------------------------------------------------------------------
# WebSocket endpoint for WebRTC signaling
# ---------------------------------------------------------------------
# Store rooms with their broadcaster and viewer connections
webrtc_rooms: Dict[str, Dict[str, Any]] = {}


@router.websocket("/ws-webrtc/{room_id}")
async def webrtc_endpoint(websocket: WebSocket, room_id: str):
    print(f"New WebRTC connection for room: {room_id}")
    await websocket.accept()

    # Initialize the room if it doesn't exist
    if room_id not in webrtc_rooms:
        webrtc_rooms[room_id] = {"broadcaster": None, "viewers": []}

    client_type = None

    try:
        # First message should specify if this is a broadcaster or viewer
        data = await websocket.receive_text()
        message = json.loads(data)

        if message.get("type") == "broadcaster":
            # Handle broadcaster connection
            client_type = "broadcaster"
            print(f"Broadcaster connected to room: {room_id}")
            # Disconnect old broadcaster if exists
            if webrtc_rooms[room_id]["broadcaster"]:
                try:
                    await webrtc_rooms[room_id]["broadcaster"].close()
                except Exception as e:
                    print(f"Error closing old broadcaster connection: {e}")

            webrtc_rooms[room_id]["broadcaster"] = websocket

            # Notify broadcaster about existing viewers
            if webrtc_rooms[room_id]["viewers"]:
                await websocket.send_json({"type": "viewer-connected"})

        elif message.get("type") == "viewer":
            # Handle viewer connection
            client_type = "viewer"
            print(f"Viewer connected to room: {room_id}")
            webrtc_rooms[room_id]["viewers"].append(websocket)

            # Notify broadcaster about new viewer
            if webrtc_rooms[room_id]["broadcaster"]:
                try:
                    await webrtc_rooms[room_id]["broadcaster"].send_json(
                        {"type": "viewer-connected"}
                    )
                except Exception as e:
                    print(f"Error notifying broadcaster: {e}")
                    webrtc_rooms[room_id]["broadcaster"] = None

        # Continue processing messages
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "offer" and webrtc_rooms[room_id]["viewers"]:
                # Forward offer from broadcaster to all viewers
                for viewer in list(webrtc_rooms[room_id]["viewers"]):
                    try:
                        await viewer.send_json(message)
                    except Exception as e:
                        print(f"Error sending offer to viewer: {e}")
                        if viewer in webrtc_rooms[room_id]["viewers"]:
                            webrtc_rooms[room_id]["viewers"].remove(viewer)

            elif (
                message.get("type") == "answer" and webrtc_rooms[room_id]["broadcaster"]
            ):
                # Forward answer from viewer to broadcaster
                try:
                    await webrtc_rooms[room_id]["broadcaster"].send_json(message)
                except Exception as e:
                    print(f"Error sending answer to broadcaster: {e}")
                    webrtc_rooms[room_id]["broadcaster"] = None

            elif message.get("type") == "ice-candidate":
                # Forward ICE candidates
                if client_type == "broadcaster":
                    # From broadcaster to viewers
                    for viewer in list(webrtc_rooms[room_id]["viewers"]):
                        try:
                            await viewer.send_json(message)
                        except Exception as e:
                            print(f"Error sending ICE candidate to viewer: {e}")
                            if viewer in webrtc_rooms[room_id]["viewers"]:
                                webrtc_rooms[room_id]["viewers"].remove(viewer)
                elif client_type == "viewer":
                    # From viewer to broadcaster
                    if webrtc_rooms[room_id]["broadcaster"]:
                        try:
                            await webrtc_rooms[room_id]["broadcaster"].send_json(
                                message
                            )
                        except Exception as e:
                            print(f"Error sending ICE candidate to broadcaster: {e}")
                            webrtc_rooms[room_id]["broadcaster"] = None

    except WebSocketDisconnect:
        print(f"WebRTC client disconnected from room: {room_id}")
        # Clean up connections
        if room_id in webrtc_rooms:
            if client_type == "broadcaster":
                webrtc_rooms[room_id]["broadcaster"] = None
                print(f"Broadcaster left room: {room_id}")
            elif (
                client_type == "viewer"
                and websocket in webrtc_rooms[room_id]["viewers"]
            ):
                webrtc_rooms[room_id]["viewers"].remove(websocket)
                print(
                    f"Viewer left room: {room_id}, {len(webrtc_rooms[room_id]['viewers'])} viewers remaining"
                )

            # Remove room if empty
            if (
                not webrtc_rooms[room_id]["broadcaster"]
                and not webrtc_rooms[room_id]["viewers"]
            ):
                webrtc_rooms.pop(room_id)
                print(f"Room {room_id} deleted (no participants)")

    except Exception as e:
        print(f"WebRTC WebSocket error: {e}")
