"""Microphone discovery + control for the Audio MCP.

The first real (non-stub) part of the Audio domain. Sennheiser TeamConnect
ceiling mics (TCC family, including the TCC M S W we have in the studio)
advertise themselves on the LAN via mDNS using the `_ssc-https._tcp`
service type. We discover them with `avahi-browse` (no Python dependency
beyond what's already installed) and control them via the Sennheiser
**SSC** (Sound Control) HTTPS REST API on port 443.

Why avahi-browse and not the `zeroconf` Python package: avahi is already
installed on Debian (we already used it to find the studio's TCC M),
and shelling out avoids a new dep + threading model.

Scope today:
  - Discover any `_ssc-https._tcp` (Sennheiser SSC) endpoint on the LAN.
    Other mic protocols (Dante AES67, USB) come later as separate
    `_discover_*` helpers.
  - Probe each mic for live state via `GET /api/ssc/state` — works
    against the TCC family. Self-signed cert → verify=False.
  - Set mute state via the same path.

The SSC endpoints below are best-effort against firmware seen in the
field; if a unit returns a different path the probe surfaces the HTTP
status verbatim so it's easy to diagnose. Mute spec docs:
  https://www.sennheiser.com/en-de/support-and-software/teamconnect-ceiling-medium
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Optional

import requests
import urllib3


# Suppress the "self-signed cert" warning — the TCC ships a per-unit
# cert that no public CA chains to. We pin the host instead (via mDNS
# discovery on a trusted LAN).
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# mDNS service type Sennheiser uses for the TCC family + most pro
# audio gear that speaks Sennheiser Sound Control over HTTPS.
SSC_SERVICE_TYPE = "_ssc-https._tcp"
DISCOVERY_TIMEOUT_S = 6.0

# Per-device timeout for SSC API calls. The TCC is on the LAN so this
# is generous; tighten if it ever blocks the MCP loop.
SSC_TIMEOUT_S = 4.0


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _avahi_browse(service_type: str, timeout: float) -> list[dict]:
    """Run `avahi-browse -rtpl <service>` and parse the entries.

    Output is `=` resolution rows in semicolon-delimited fields:
      = ; iface ; proto ; name ; type ; domain ; hostname ; ip ; port ; txt
    """
    try:
        proc = subprocess.run(
            [
                "avahi-browse",
                "-r",       # resolve
                "-t",       # terminate after one sweep
                "-p",       # parseable output
                "-l",       # only local (skip wide-area DNS-SD)
                service_type,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return [{"_error": "avahi-browse not installed on this host"}]
    except subprocess.TimeoutExpired:
        return [{"_error": f"avahi-browse {service_type} timed out"}]

    entries: list[dict] = []
    for line in proc.stdout.splitlines():
        if not line.startswith("="):
            continue
        parts = line.split(";")
        if len(parts) < 9:
            continue
        proto = parts[2]
        if proto != "IPv4":  # skip IPv6 dupes — TCC announces both
            continue
        ip = parts[7]
        port_raw = parts[8] if len(parts) > 8 else ""
        try:
            port = int(port_raw)
        except ValueError:
            port = None
        entries.append(
            {
                "friendly_name": parts[3],
                "service_type": parts[4],
                "hostname": parts[6],
                "ip": ip,
                "port": port,
                "txt": parts[9] if len(parts) > 9 else "",
            }
        )
    return entries


def discover_microphones() -> list[dict]:
    """Return every mDNS-announced mic we can see on the local network.

    Each entry carries the bits the SSC client needs (`ip`, optional
    `port`) plus presentation fields (`friendly_name`, `hostname`,
    `vendor`, `model`) so the admin UI can render it cleanly.
    """
    raw = _avahi_browse(SSC_SERVICE_TYPE, DISCOVERY_TIMEOUT_S)
    mics: list[dict] = []
    errors: list[str] = []
    for entry in raw:
        if "_error" in entry:
            errors.append(entry["_error"])
            continue
        hostname = entry.get("hostname") or ""
        # Sennheiser TCC family advertises as `TCCM-<MAC suffix>.local`
        # or `TCCSmall-...local`. Tag those explicitly so the agent
        # knows what control surface to expect.
        model = "Unknown SSC device"
        vendor = "Unknown"
        if hostname.upper().startswith("TCCM-"):
            vendor, model = "Sennheiser", "TeamConnect Ceiling Medium"
        elif hostname.upper().startswith("TCC"):
            vendor, model = "Sennheiser", "TeamConnect (TCC family)"
        elif entry["friendly_name"].lower().startswith(("genai-", "studio-")):
            # Friendly name set by the studio's network admin.
            vendor, model = "Sennheiser", "TeamConnect (TCC family)"

        mics.append(
            {
                "id": entry["friendly_name"] or hostname,
                "friendly_name": entry["friendly_name"],
                "hostname": hostname,
                "ip": entry["ip"],
                "port": entry.get("port") or 443,
                "vendor": vendor,
                "model": model,
                "protocol": "ssc-https",
                "control_url": f"https://{entry['ip']}",
            }
        )
    if errors:
        return [{"error": errors[0]}]
    return mics


# ---------------------------------------------------------------------------
# SSC control
# ---------------------------------------------------------------------------


def _ssc_url(mic: dict, path: str) -> str:
    port = mic.get("port") or 443
    host = mic.get("ip") or mic.get("hostname")
    suffix = "" if port == 443 else f":{port}"
    return f"https://{host}{suffix}{path}"


def _find_mic(mic_id: str) -> Optional[dict]:
    for m in discover_microphones():
        if "error" in m:
            return None
        if m["id"] == mic_id or m["hostname"] == mic_id or m["ip"] == mic_id:
            return m
    return None


def get_microphone_state(mic_id: str) -> dict:
    """Fetch the full SSC state from a mic by id / hostname / ip.

    Returns whatever the device returns at `/api/ssc/state` (a deep
    JSON object on TCC firmware) so the operator can inspect anything
    — channel levels, mute, identify, etc."""
    mic = _find_mic(mic_id)
    if mic is None:
        return {"error": f"microphone {mic_id!r} not found via mDNS"}
    url = _ssc_url(mic, "/api/ssc/state")
    try:
        r = requests.get(url, verify=False, timeout=SSC_TIMEOUT_S)
    except requests.RequestException as e:
        return {"error": "SSC GET failed", "url": url, "detail": repr(e)}
    if r.status_code >= 400:
        return {
            "error": f"SSC GET {r.status_code}",
            "url": url,
            "body": r.text[:500],
        }
    try:
        return {"mic": mic, "state": r.json()}
    except ValueError:
        return {"error": "SSC returned non-JSON", "url": url, "body": r.text[:500]}


def set_microphone_mute(mic_id: str, muted: bool) -> dict:
    """Set mute via SSC. Spec: PUT /api/ssc/state/audio/mute with a
    bool body. Tested against TCC firmware; some older units use a
    nested JSON object — if PUT fails, the response is surfaced so we
    can adjust the path."""
    mic = _find_mic(mic_id)
    if mic is None:
        return {"error": f"microphone {mic_id!r} not found via mDNS"}
    url = _ssc_url(mic, "/api/ssc/state/audio/mute")
    try:
        r = requests.put(
            url,
            data=json.dumps(bool(muted)),
            headers={"Content-Type": "application/json"},
            verify=False,
            timeout=SSC_TIMEOUT_S,
        )
    except requests.RequestException as e:
        return {"error": "SSC PUT failed", "url": url, "detail": repr(e)}
    return {
        "mic_id": mic["id"],
        "ip": mic["ip"],
        "muted": bool(muted),
        "http_status": r.status_code,
        "body": (r.text[:500] if r.text else ""),
    }
