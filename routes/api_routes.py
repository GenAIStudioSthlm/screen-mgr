from fastapi import APIRouter, Form


router = APIRouter()


# Endpoint to update a screen's URL.
@router.post("/api/update")
async def update_screen(screen_id: str = Form(...), new_url: str = Form(...)):
    #    screen_manager.screens[screen_id] = new_url
    #    screen_manager.save_screens()
    #    await connection_manager.broadcast(
    #        screen_id, {"type": "refresh", "newContentUrl": new_url}
    #    )
    return {"message": "URL updated successfully"}
