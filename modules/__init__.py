"""screen-mgr modules package.

Importing this package initialises the module registry and registers every
built-in module. Add new in-code modules by importing them here and calling
`registry.register(...)`.
"""

from modules.registry import registry, ModuleRegistry  # noqa: F401
from modules.base import Module, DisplayModule, ServiceModule  # noqa: F401

# --- built-in modules ---------------------------------------------------
# Order chosen to match the historical content-type dropdown order so the
# admin UI doesn't visually reshuffle when the dropdown becomes dynamic.

from modules.url import UrlModule
from modules.text import TextModule
from modules.video import VideoModule
from modules.picture import PictureModule
from modules.pdf import PdfModule
from modules.default import DefaultModule
from modules.slideshow import SlideshowModule
from modules.news import NewsModule
from modules.screen_share import ScreenShareModule
from modules.rgbdisplay import RGBDisplayModule
from modules.hue import HueModule

registry.register(UrlModule())
registry.register(TextModule())
registry.register(VideoModule())
registry.register(PictureModule())
registry.register(PdfModule())
registry.register(DefaultModule())
registry.register(SlideshowModule())
registry.register(NewsModule())
registry.register(ScreenShareModule())
registry.register(RGBDisplayModule())
registry.register(HueModule())

# --- external modules ---------------------------------------------------
# Pull each manifest configured in data/modules.json. Failures are
# logged inside load_external() and don't break startup.
registry.load_external()

__all__ = [
    "registry",
    "ModuleRegistry",
    "Module",
    "DisplayModule",
    "ServiceModule",
]
