"""text module — large responsive text centered on the screen."""

from urllib.parse import quote

from modules.base import DisplayModule


class TextModule(DisplayModule):
    id = "text"
    name = "Text"
    description = "Display a single text string centered and auto-sized to the screen."
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def get_screen_url(self, screen, base_url: str) -> str:
        return base_url + "responsive/" + quote(screen.text or "")
