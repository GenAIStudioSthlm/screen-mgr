"""External modules — registered via a manifest URL the module hosts itself.

An external module is one whose implementation lives on a different machine
(or process). screen-mgr never executes its code; it just learns the module's
contract from a JSON manifest the module serves at a known URL, then talks
to it over HTTP.

Manifest shape (served by the external module owner):

    {
      "id":              "robot-panel",
      "name":            "Robot Control Panel",
      "description":     "Live status + drive control for the lab robot",
      "type":            ["display"],          // or ["service"]
      "version":         "0.2.0",
      "health_url":      "http://robotpi.local:8080/health",
      "screen_url_pattern": "http://robotpi.local:8080/screen/{screen_id}",
      // for service-type manifests:
      "start_url":       "http://robotpi.local:8080/start",
      "stop_url":        "http://robotpi.local:8080/stop"
    }

A manifest declaring multiple types yields the *first* matching class
(display wins over service). v2 can add a true hybrid; this keeps v1 simple.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from modules.base import DisplayModule, ServiceModule


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only — no httpx dep)
# ---------------------------------------------------------------------------

def fetch_manifest(url: str, timeout: float = 5.0) -> dict:
    """Fetch and JSON-parse the manifest at `url`. Raises on failure."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if getattr(response, "status", 200) >= 400:
            raise RuntimeError(f"Manifest at {url} returned status {response.status}")
        return json.load(response)


def _http_get_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= getattr(r, "status", 200) < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _http_post(url: str, timeout: float = 5.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            try:
                return {"ok": True, "response": json.loads(body)}
            except json.JSONDecodeError:
                return {"ok": True, "response": body}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": str(e)}
    except (urllib.error.URLError, OSError) as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Module classes
# ---------------------------------------------------------------------------

class _ExternalMixin:
    """Shared bits — manifest URL and HTTP-based health check."""

    def __init__(self, manifest_url: str, manifest: dict) -> None:
        self.manifest_url = manifest_url
        self.id = manifest["id"]
        self.name = manifest.get("name", self.id)
        self.description = manifest.get("description", "")
        self.version = manifest.get("version", "0.1.0")
        self._health_url: str | None = manifest.get("health_url")
        self._manifest = manifest

    def is_available(self) -> bool:
        # If the manifest doesn't expose a health URL, trust that registering
        # the manifest at all is signal enough. The admin can disable it.
        if not self._health_url:
            return True
        return _http_get_ok(self._health_url)

    def status(self) -> dict[str, Any]:
        return {
            "available": self.is_available(),
            "external": True,
            "manifest_url": self.manifest_url,
            "health_url": self._health_url,
        }


class ExternalDisplayModule(_ExternalMixin, DisplayModule):
    """Display module backed by a remote manifest URL."""

    def __init__(self, manifest_url: str, manifest: dict) -> None:
        _ExternalMixin.__init__(self, manifest_url, manifest)
        self._screen_url_pattern: str = manifest.get("screen_url_pattern", "")

    def get_screen_url(self, screen, base_url: str) -> str:
        return self._screen_url_pattern.format(
            screen_id=screen.id, screen_name=getattr(screen, "name", "")
        )


class ExternalServiceModule(_ExternalMixin, ServiceModule):
    """Service module backed by a remote manifest URL."""

    def __init__(self, manifest_url: str, manifest: dict) -> None:
        _ExternalMixin.__init__(self, manifest_url, manifest)
        self._start_url: str | None = manifest.get("start_url")
        self._stop_url: str | None = manifest.get("stop_url")

    def start(self) -> dict[str, Any]:
        if not self._start_url:
            return {"ok": False, "error": "manifest has no start_url"}
        return _http_post(self._start_url)

    def stop(self) -> dict[str, Any]:
        if not self._stop_url:
            return {"ok": False, "error": "manifest has no stop_url"}
        return _http_post(self._stop_url)


def build_external_module(manifest_url: str, manifest: dict):
    """Construct an Ext{Display,Service}Module from a manifest dict."""
    types = manifest.get("type") or ["display"]
    if "display" in types:
        return ExternalDisplayModule(manifest_url, manifest)
    if "service" in types:
        return ExternalServiceModule(manifest_url, manifest)
    raise ValueError(f"Manifest at {manifest_url} declares no usable type")
