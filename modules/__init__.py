"""screen-mgr modules package.

Importing this package initialises the module registry and registers every
built-in module. Add new in-code modules by importing them here and calling
`registry.register(...)`.
"""

from modules.registry import registry, ModuleRegistry  # noqa: F401
from modules.base import Module, DisplayModule, ServiceModule  # noqa: F401

# --- built-in modules ---------------------------------------------------
# Order matters only for log readability.

from modules.rgbdisplay import RGBDisplayModule

registry.register(RGBDisplayModule())

__all__ = [
    "registry",
    "ModuleRegistry",
    "Module",
    "DisplayModule",
    "ServiceModule",
]
