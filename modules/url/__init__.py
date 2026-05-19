"""url module — display any URL on the screen.

If the URL is a YouTube link, route through the local /youtube/ wrapper for
embed-friendly playback.
"""

from urllib.parse import quote

from modules.base import DisplayModule


class UrlModule(DisplayModule):
    id = "url"
    name = "Url"
    description = "Display any web URL on the screen. YouTube URLs are routed through an embed-friendly wrapper."
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def get_screen_url(self, screen, base_url: str) -> str:
        url = screen.url or ""
        if "youtube.com" in url or "youtu.be" in url:
            return base_url + "youtube/" + quote(url)
        return url
