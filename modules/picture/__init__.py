"""picture module — display a single image from static/pictures/."""

from modules.base import DisplayModule


class PictureModule(DisplayModule):
    id = "picture"
    name = "Picture"
    description = "Display a single uploaded image fullscreen."
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def get_screen_url(self, screen, base_url: str) -> str:
        return base_url + "picture/" + ((screen.picture or "").replace("/", "%2F"))
