#!/usr/bin/env python3
"""One-shot pairing helper for the Philips Hue Bridge.

Usage:
    1.  Walk to the Hue Bridge (the small white square that's usually
        plugged into the router).
    2.  Press the round button on top.
    3.  Within 30 seconds, run on studiopi:

            python3 scripts/hue_pair.py

        Optionally pass --ip to skip Philips's cloud discovery:

            python3 scripts/hue_pair.py --ip 192.168.2.196

Result: credentials are written to `data/hue.json`. The Hue module in
screen-mgr picks them up on next request (no server restart needed).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_FILE = Path("data/hue.json")


def discover_bridges(timeout: float = 5.0) -> list[str]:
    """Ask Philips's cloud service which Hue Bridges have called home from
    this LAN recently. Returns the bridges' internal IPs."""
    url = "https://discovery.meethue.com/"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = json.load(r)
    return [b["internalipaddress"] for b in data if "internalipaddress" in b]


def pair(bridge_ip: str, devicetype: str, timeout: float = 5.0) -> list:
    """POST /api with {devicetype}; bridge returns either an `error` (button
    not pressed) or a `success` with the new username."""
    url = f"http://{bridge_ip}/api"
    body = json.dumps({"devicetype": devicetype, "generateclientkey": True}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--ip", help="Bridge IP (skips Philips's cloud discovery)")
    p.add_argument(
        "--devicetype",
        default="screen-mgr#studiopi",
        help="Application identifier sent to the bridge (default: screen-mgr#studiopi)",
    )
    p.add_argument("--out", default=str(DEFAULT_FILE), help="Where to save credentials")
    args = p.parse_args()

    if args.ip:
        ips = [args.ip]
    else:
        print("discovering bridges via discovery.meethue.com...")
        try:
            ips = discover_bridges()
        except Exception as e:
            print(f"  discovery failed: {e}")
            return 1
        if not ips:
            print("  no bridges found")
            return 1
        print(f"  found: {ips}")

    out_path = Path(args.out)
    for ip in ips:
        print(f"\npairing with {ip} ...")
        try:
            response = pair(ip, args.devicetype)
        except urllib.error.URLError as e:
            print(f"  failed to reach bridge: {e}")
            continue

        if not response:
            print("  bridge returned an empty response")
            continue

        entry = response[0]
        if "error" in entry:
            err = entry["error"].get("description", "unknown error")
            print(f"  bridge said: {err}")
            print("  -> Press the bridge's link button and re-run within 30s.")
            continue

        success = entry.get("success", {})
        username = success.get("username")
        clientkey = success.get("clientkey")
        if not username:
            print(f"  unexpected response: {response}")
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"bridge_ip": ip, "username": username}
        if clientkey:
            payload["clientkey"] = clientkey
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"  paired. credentials saved to {out_path}")
        return 0

    print("\ncould not pair with any bridge")
    return 1


if __name__ == "__main__":
    sys.exit(main())
