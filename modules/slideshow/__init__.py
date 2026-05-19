"""slideshow module — rotate through a folder of pictures."""

from modules.base import DisplayModule


class SlideshowModule(DisplayModule):
    id = "slideshow"
    name = "Slideshow"
    description = "Rotate through all images in a chosen static/pictures/ subfolder."
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def get_screen_url(self, screen, base_url: str) -> str:
        return base_url + "slideshow/" + (screen.slideshow or "")
