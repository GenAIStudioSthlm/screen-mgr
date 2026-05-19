"""default module — the Studio logo placeholder."""

from modules.base import DisplayModule


class DefaultModule(DisplayModule):
    id = "default"
    name = "Studio logo"
    description = "Studio branding shown when no other content is assigned."
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def get_screen_url(self, screen, base_url: str) -> str:
        return base_url + "default/" + str(screen.id)
