"""Base classes every screen-mgr module derives from.

A *module* is anything the admin can wire to a screen or control as a
service: today's news/picture/slideshow content types, the rgbdisplay LED
matrix, future things like a robot-control panel. Each module declares
itself with a manifest (the class attributes below) and implements a few
methods the registry calls.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Module(ABC):
    """Base class. Concrete modules subclass `DisplayModule`, `ServiceModule`,
    or both."""

    id: str = ""
    name: str = ""
    description: str = ""
    version: str = "0.1.0"
    # Filled in by subclasses; a module can be both "display" and "service".
    type: list[str] = []

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap yes/no check. Should not block more than a second or two.
        Called on demand and on a background refresh tick."""
        ...

    def status(self) -> dict[str, Any]:
        """Optional richer status (process state, last error, version of
        underlying tool, etc.). Default just exposes `available`."""
        return {"available": self.is_available()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "type": list(self.type),
            "available": self.is_available(),
            "status": self.status(),
        }


class DisplayModule(Module):
    """A module that provides content for screens to render. Its `id` matches
    a value of `Screen.type` — the screens-tab dropdown is built dynamically
    from the registered display modules."""

    type = ["display"]

    @abstractmethod
    def get_screen_url(self, screen, base_url: str) -> str:
        """URL a screen should load to render this module's content.

        `screen` is the Screen object so the module can read per-screen
        fields (text, url, video, picture, pdf, slideshow, news_mode, ...).
        `base_url` is the request's base URL (e.g. 'http://192.168.2.65:8000/')
        so the module can return either an absolute backend path or an
        external URL.
        """
        ...


class ServiceModule(Module):
    """A module representing a backend service the admin can start/stop.
    Doesn't bind to a screen on its own (though a module can derive from
    both and be both)."""

    type = ["service"]

    @abstractmethod
    def start(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def stop(self) -> dict[str, Any]:
        ...
