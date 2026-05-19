"""video module — full-screen looped MP4 from static/videos/."""

from modules.base import DisplayModule


class VideoModule(DisplayModule):
    id = "video"
    name = "Video"
    description = "Play an uploaded MP4 video fullscreen and looped."
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def get_screen_url(self, screen, base_url: str) -> str:
        return base_url + "video/" + (screen.video or "")
