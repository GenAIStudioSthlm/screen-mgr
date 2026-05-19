"""news module — AI news content in one of three modes."""

from modules.base import DisplayModule


class NewsModule(DisplayModule):
    id = "news"
    name = "AI News"
    description = "Curated AI news feed in portrait, landscape, or presentation mode."
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def get_screen_url(self, screen, base_url: str) -> str:
        mode = screen.news_mode or "landscape"
        return base_url + "news/" + mode
