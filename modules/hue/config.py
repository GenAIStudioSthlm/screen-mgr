"""Persistence for Hue bridge credentials.

Stored in `data/hue.json` (already gitignored as part of `data/`):

    {
      "bridge_ip": "192.168.2.196",
      "username":  "<long-token-from-pairing>",
      "clientkey": "<v2-stream-key-if-issued>"     // optional
    }

Treat the username as semi-sensitive — it grants full LAN control of the
lights. Don't surface it in /api responses; only the IP is shown to admin.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

HUE_FILE = Path("data/hue.json")


def load() -> dict | None:
    if not HUE_FILE.exists():
        return None
    try:
        with open(HUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("bridge_ip") or not data.get("username"):
            return None
        return data
    except (OSError, json.JSONDecodeError) as e:
        print(f"[hue] could not read {HUE_FILE}: {e}")
        return None


def save(bridge_ip: str, username: str, clientkey: str | None = None,
         bridge_id: str | None = None) -> None:
    HUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Preserve any existing fields we aren't explicitly overwriting.
    existing = {}
    if HUE_FILE.exists():
        try:
            existing = json.load(open(HUE_FILE, "r", encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    payload = {**existing, "bridge_ip": bridge_ip, "username": username}
    if clientkey:
        payload["clientkey"] = clientkey
    if bridge_id:
        payload["bridge_id"] = bridge_id
    with open(HUE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def update_ip(bridge_ip: str) -> None:
    """Patch only the stored bridge IP (used by auto-rediscovery)."""
    cfg = load()
    if not cfg:
        return
    save(bridge_ip, cfg["username"], cfg.get("clientkey"), cfg.get("bridge_id"))


def discover_bridges(timeout: float = 4.0) -> list[dict]:
    """Best-effort bridge discovery via Philips' cloud service. Returns a list
    of {"id", "internalipaddress", ...}; [] on any failure. Used to self-heal
    when the bridge's DHCP address changes (we can't set router reservations)."""
    try:
        req = urllib.request.Request(
            "https://discovery.meethue.com/",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[hue] discovery failed: {e}")
        return []


def clear() -> None:
    if HUE_FILE.exists():
        HUE_FILE.unlink()
