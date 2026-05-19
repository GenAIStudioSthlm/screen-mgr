"""pdf module — show an uploaded PDF as a paginated viewer."""

from modules.base import DisplayModule


class PdfModule(DisplayModule):
    id = "pdf"
    name = "PDF"
    description = "Display an uploaded PDF document with a paginated viewer."
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def get_screen_url(self, screen, base_url: str) -> str:
        return base_url + "pdf/" + (screen.pdf or "")
