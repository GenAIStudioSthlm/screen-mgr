# Admin page with form to update screen URLs.


from fastapi import (
    APIRouter,
)

from routes.admin_routes import router as admin_router
from routes.screen_routes import router as screen_router
from routes.websocket_routes import router as websocket_router
from routes.content_routes import router as content_router
from routes.api_routes import router as api_router


router = APIRouter()

router.include_router(admin_router)
router.include_router(screen_router)
router.include_router(websocket_router)
router.include_router(content_router)
router.include_router(api_router)
