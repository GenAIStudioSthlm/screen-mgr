# Admin page with form to update screen URLs.


from fastapi import (
    APIRouter,
)

from routes.admin_routes import router as admin_router
from routes.screen_routes import router as screen_router
from routes.websocket_routes import router as websocket_router
from routes.content_routes import router as content_router
from routes.api_routes import router as api_router
from routes.news_routes import router as news_admin_router
from routes.news_content_routes import router as news_content_router
from routes.modules_routes import router as modules_router
from modules.hue.routes import router as hue_router
from routes.admin_v2_routes import router as admin_v2_router
from routes.zones_routes import router as zones_router
from routes.scenes_routes import router as scenes_router
from routes.chat_routes import router as chat_router
from routes.audio_routes import router as audio_router
from routes.music_routes import router as music_router
from routes.positions_routes import router as positions_router


router = APIRouter()

router.include_router(admin_router)
router.include_router(screen_router)
router.include_router(websocket_router)
router.include_router(content_router)
router.include_router(api_router)
router.include_router(news_admin_router)
router.include_router(news_content_router)
router.include_router(modules_router)
router.include_router(hue_router)
router.include_router(admin_v2_router)
router.include_router(zones_router)
router.include_router(scenes_router)
router.include_router(chat_router)
router.include_router(audio_router)
router.include_router(music_router)
router.include_router(positions_router)
