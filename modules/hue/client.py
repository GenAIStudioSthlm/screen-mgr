"""Minimal HTTP client for the Philips Hue Bridge v1 CLIP API.

Uses urllib (stdlib) instead of pulling in a third-party library — keeps
the dependency surface narrow, same pattern as `modules/external.py`.

The Hue Bridge runs CLIP v1 on plain HTTP (port 80). It also runs CLIP v2
on HTTPS with a self-signed cert (port 443); for our admin UI we don't
need streaming so v1 is plenty.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class HueClient:
    """Thin v1 CLIP API client. All methods return parsed JSON; errors are
    returned as `{"error": "..."}` dicts (never raised), so callers can
    treat the wire as best-effort."""

    def __init__(self, bridge_ip: str, username: str, timeout: float = 5.0) -> None:
        self.bridge_ip = bridge_ip
        self.username = username
        self._timeout = timeout
        self._base = f"http://{bridge_ip}/api/{username}"

    # ---- low-level ----

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = self._base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                raw = r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.reason}"}
        except (urllib.error.URLError, OSError) as e:
            return {"error": f"network: {e}"}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"error": "non-json response", "raw": raw[:200]}

    # ---- read ----

    def get_lights(self) -> dict:
        return self._request("GET", "/lights")

    def get_groups(self) -> dict:
        return self._request("GET", "/groups")

    def get_scenes(self) -> dict:
        return self._request("GET", "/scenes")

    def get_config(self) -> dict:
        return self._request("GET", "/config")

    # ---- write ----

    def set_light(self, light_id: str, state: dict) -> Any:
        return self._request("PUT", f"/lights/{light_id}/state", state)

    def set_group(self, group_id: str, action: dict) -> Any:
        return self._request("PUT", f"/groups/{group_id}/action", action)

    def recall_scene(self, scene_id: str) -> Any:
        # group 0 = all lights; "scene" key triggers a recall.
        return self.set_group("0", {"scene": scene_id})

    def all_on(self) -> Any:
        return self.set_group("0", {"on": True})

    def all_off(self) -> Any:
        return self.set_group("0", {"on": False})

    # ---- liveness ----

    def is_alive(self) -> bool:
        """Cheap health check that doesn't require valid auth."""
        url = f"http://{self.bridge_ip}/api/0/config"
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return getattr(r, "status", 200) < 400
        except Exception:
            return False
