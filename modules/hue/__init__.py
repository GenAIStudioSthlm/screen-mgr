"""hue module — control the Philips Hue Bridge from the admin panel.

The bridge IP and API username live in `data/hue.json` (gitignored).
First-time pairing is a one-shot dance: press the physical button on the
Hue Bridge, then run `python3 scripts/hue_pair.py` on studiopi. Once
`data/hue.json` exists this module becomes available; before that it
reports `paired: false` and the Lights tab shows pairing instructions.

A ServiceModule:
- `is_available()` → bridge reachable AND we have credentials
- `start()`  → all lights on
- `stop()`   → all lights off

For the per-light / per-group / per-scene work, the module exposes a
HueClient via `.client` and `modules/hue/routes.py` mounts the rich API.
"""

from __future__ import annotations

from typing import Any

from modules.base import ServiceModule
from modules.hue.client import HueClient
from modules.hue.config import load as load_config


class HueModule(ServiceModule):
    id = "hue"
    name = "Philips Hue Lights"
    description = (
        "Control room lighting via the Hue Bridge on the LAN. "
        "Start = all lights on; Stop = all lights off."
    )
    version = "0.1.0"

    def __init__(self) -> None:
        self._client: HueClient | None = None

    def _refresh_client(self) -> HueClient | None:
        cfg = load_config()
        if not cfg:
            self._client = None
            return None
        # Re-create the client if config changed (e.g. re-pair).
        if (self._client is None
                or self._client.bridge_ip != cfg["bridge_ip"]
                or self._client.username != cfg["username"]):
            self._client = HueClient(cfg["bridge_ip"], cfg["username"])
        return self._client

    @property
    def client(self) -> HueClient | None:
        return self._refresh_client()

    def is_available(self) -> bool:
        c = self._refresh_client()
        if c is None:
            return False
        return c.is_alive()

    def status(self) -> dict[str, Any]:
        cfg = load_config()
        out: dict[str, Any] = {
            "available": False,
            "paired": cfg is not None,
        }
        if cfg:
            out["bridge_ip"] = cfg.get("bridge_ip")
            # Intentionally NOT returning the username — semi-sensitive.
            c = self._refresh_client()
            if c is not None:
                out["available"] = c.is_alive()
        return out

    def start(self) -> dict[str, Any]:
        c = self._refresh_client()
        if c is None:
            return {"ok": False, "error": "not paired — run scripts/hue_pair.py"}
        result = c.all_on()
        return {"ok": "error" not in (result if isinstance(result, dict) else {}), "result": result}

    def stop(self) -> dict[str, Any]:
        c = self._refresh_client()
        if c is None:
            return {"ok": False, "error": "not paired — run scripts/hue_pair.py"}
        result = c.all_off()
        return {"ok": "error" not in (result if isinstance(result, dict) else {}), "result": result}
