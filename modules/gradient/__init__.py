"""gradient module — an animated brand gradient that mimics a zone's lighting.

The screen renders a full-screen animated gradient whose colours are derived
from the *current* colour of the Hue lights mapped to that screen's zone
(data/studio_zone_map.json). The renderer polls so the screen tracks the
lights live. This is the Reinvention Studio's default visual content type.
"""

from modules.base import DisplayModule


class GradientModule(DisplayModule):
    id = "gradient"
    name = "Gradient"
    description = "Animated brand gradient that mimics the zone's lighting."
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def get_screen_url(self, screen, base_url: str) -> str:
        # The renderer resolves the zone + live light colours by screen id.
        return base_url + "gradient/" + str(screen.id)
