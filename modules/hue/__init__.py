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

import time
from typing import Any

from modules.base import ServiceModule
from modules.hue.client import HueClient
from modules.hue.config import (
    load as load_config,
    save as save_config,
    discover_bridges,
)

# Don't hammer the cloud discovery service while the bridge is down.
_REDISCOVER_INTERVAL_S = 30.0


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
        self._last_rediscover = 0.0

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
        # Self-heal a changed DHCP address: if the bridge isn't reachable at
        # the stored IP, rediscover it by bridge id and patch the config.
        # (We can't set router reservations, so the IP can move under us.)
        if not self._client.is_alive():
            healed = self._try_rediscover(cfg)
            if healed is not None:
                self._client = healed
        elif not cfg.get("bridge_id"):
            # Opportunistically learn + persist the bridge id while reachable,
            # so future rediscovery can match the exact bridge.
            self._learn_bridge_id(cfg)
        return self._client

    def _learn_bridge_id(self, cfg: dict) -> None:
        try:
            conf = self._client.get_config() if self._client else {}
            bid = conf.get("bridgeid") if isinstance(conf, dict) else None
            if bid:
                save_config(cfg["bridge_ip"], cfg["username"],
                            cfg.get("clientkey"), bridge_id=bid)
        except Exception:
            pass

    def _try_rediscover(self, cfg: dict) -> HueClient | None:
        now = time.monotonic()
        if now - self._last_rediscover < _REDISCOVER_INTERVAL_S:
            return None
        self._last_rediscover = now
        bridges = discover_bridges()
        if not bridges:
            return None
        want = cfg.get("bridge_id")
        chosen = None
        for b in bridges:
            if want and str(b.get("id", "")).lower() == str(want).lower():
                chosen = b
                break
        if chosen is None and not want:
            chosen = bridges[0]  # no stored id yet — best effort
        if chosen is None:
            return None
        new_ip = chosen.get("internalipaddress")
        if not new_ip or new_ip == cfg["bridge_ip"]:
            return None
        candidate = HueClient(new_ip, cfg["username"])
        if not candidate.is_alive():
            return None
        save_config(new_ip, cfg["username"], cfg.get("clientkey"),
                    bridge_id=chosen.get("id") or cfg.get("bridge_id"))
        print(f"[hue] bridge moved {cfg['bridge_ip']} -> {new_ip}; config updated")
        return candidate

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
