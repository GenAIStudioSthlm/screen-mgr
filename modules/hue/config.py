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


def save(bridge_ip: str, username: str, clientkey: str | None = None) -> None:
    HUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"bridge_ip": bridge_ip, "username": username}
    if clientkey:
        payload["clientkey"] = clientkey
    with open(HUE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def clear() -> None:
    if HUE_FILE.exists():
        HUE_FILE.unlink()
