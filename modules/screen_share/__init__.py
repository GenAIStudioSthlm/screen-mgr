"""screen_share module — WebRTC screen share viewer (experimental)."""

from modules.base import DisplayModule


class ScreenShareModule(DisplayModule):
    id = "screen_share"
    name = "Screen Share"
    description = "WebRTC viewer joining a shared room (experimental)."
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def get_screen_url(self, screen, base_url: str) -> str:
        room_id = (screen.screen_share or "").strip() or f"room-{screen.id}"
        return base_url + "screen-share/" + room_id
