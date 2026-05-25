"""Microphone discovery + control for the Audio MCP.

Sennheiser TeamConnect ceiling mics (TCC family, including the studio's
TCC M S W) advertise themselves on the LAN via mDNS using the
`_ssc-https._tcp` service type. Discovery is via `avahi-browse` (no
Python dep beyond what's installed); control is via Sennheiser's
**SSCv2** (Sound Control v2) HTTPS REST API on port 443 — base path
`/api`, HTTP Basic auth, realm "ssc".

Endpoint reality on the studio TCC M S W (firmware as of 2026-05):

  GET  /api/device/identity        no-auth → product / serial / vendor
  GET  /api/device/identification  no-auth → {"visual": bool}  (LED flash)
  PUT  /api/device/identification  AUTH    → write {"visual": true}
  GET  /api/device/state           AUTH    → full device state tree
  GET  /api/device/site            AUTH    → location / name
  GET  /api/ssc/schema             AUTH    → API schema dump
  GET  /api/audio/*                404 — audio paths live inside
                                   /api/device/state (auth-gated)

Authentication: HTTP Basic. Username `api`. Password is the
**device configuration password** set during commissioning via
Sennheiser Control Cockpit (Devices > {device} > Access > 3rd Party
Access > Edit > Secure). Override via env vars on the Pi:

  SENNHEISER_TCC_USERNAME=api          (default)
  SENNHEISER_TCC_PASSWORD=<from-control-cockpit>

Without a password set, this module still works for:
  - mDNS discovery
  - GET /api/device/identity (no-auth)
  - GET /api/device/identification (no-auth)
  - HTTPS reachability probe

…and degrades on the rest with a clear "auth required" error.

Spec refs:
  https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sscv2-specification-2.3.html
  https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/open-api-tc-ceiling-medium.html
"""

from __future__ import annotations

import json
import os
import subprocess
import time
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


def _static_mic_from_env() -> Optional[dict]:
    """If SENNHEISER_TCC_HOST is set in .env, return a mic dict without
    touching mDNS — pure point-to-point. Lets operators skip discovery
    on networks where browsing isn't appropriate."""
    host = os.environ.get("SENNHEISER_TCC_HOST", "").strip()
    if not host:
        return None
    return {
        "id": "tcc-static",
        "friendly_name": "TCC (static)",
        "hostname": host,
        "ip": host,
        "port": 443,
        "vendor": "Sennheiser",
        "model": "TeamConnect (TCC family)",
        "protocol": "ssc-https",
        "control_url": f"https://{host}",
        "source": "env (SENNHEISER_TCC_HOST)",
    }


def discover_microphones() -> list[dict]:
    """Return every TCC-family mic we can target.

    If `SENNHEISER_TCC_HOST` is set in .env, we return ONLY that mic
    and skip mDNS discovery entirely (point-to-point, no browsing).
    Otherwise we fall back to a narrow `_ssc-https._tcp` mDNS browse.

    Each entry carries the bits the SSC client needs (`ip`, optional
    `port`) plus presentation fields (`friendly_name`, `hostname`,
    `vendor`, `model`) so the admin UI can render it cleanly.
    """
    static = _static_mic_from_env()
    if static is not None:
        return [static]

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


def _ssc_auth() -> Optional[tuple[str, str]]:
    """HTTP Basic auth tuple from env vars, or None if no password set.

    `SENNHEISER_TCC_USERNAME` defaults to `api`; `SENNHEISER_TCC_PASSWORD`
    must be supplied (set during commissioning via Sennheiser Control
    Cockpit). Returning None signals "no auth configured" to callers so
    they can degrade with a clear error instead of sending bogus creds
    and getting back a generic 401.
    """
    pwd = os.environ.get("SENNHEISER_TCC_PASSWORD", "").strip()
    if not pwd:
        return None
    user = os.environ.get("SENNHEISER_TCC_USERNAME", "api").strip() or "api"
    return (user, pwd)


def _find_mic(mic_id: str) -> Optional[dict]:
    for m in discover_microphones():
        if "error" in m:
            return None
        if m["id"] == mic_id or m["hostname"] == mic_id or m["ip"] == mic_id:
            return m
    return None


def _ssc_get(mic: dict, path: str, auth: Optional[tuple[str, str]] = None) -> dict:
    """One GET against an SSCv2 endpoint with friendly error wrapping."""
    url = _ssc_url(mic, path)
    try:
        r = requests.get(url, verify=False, timeout=SSC_TIMEOUT_S, auth=auth)
    except requests.RequestException as e:
        return {"error": "SSC GET failed", "url": url, "detail": repr(e)}
    if r.status_code == 401:
        return {"error": "auth required", "url": url, "http_status": 401}
    if r.status_code == 403:
        return {"error": "auth required (forbidden)", "url": url, "http_status": 403}
    if r.status_code >= 400:
        return {"error": f"HTTP {r.status_code}", "url": url, "body": r.text[:500]}
    try:
        return {"url": url, "data": r.json()}
    except ValueError:
        return {"error": "non-JSON response", "url": url, "body": r.text[:500]}


def get_microphone_state(mic_id: str) -> dict:
    """Fetch the SSCv2 state for a mic — what we can read with current
    auth config.

    Always works (no auth needed):
      - /api/device/identity         product, serial, vendor
      - /api/device/identification   {"visual": bool} — LED-flash state

    Requires SENNHEISER_TCC_PASSWORD env var:
      - /api/device/state            full device state tree
      - /api/device/site             location / name

    Each endpoint's response (or the per-endpoint error) is included
    so the operator can see what auth gates which surface.
    """
    mic = _find_mic(mic_id)
    if mic is None:
        return {"error": f"microphone {mic_id!r} not found via mDNS"}

    auth = _ssc_auth()
    out: dict[str, Any] = {
        "mic": mic,
        "auth_configured": auth is not None,
        "identity": _ssc_get(mic, "/api/device/identity"),
        "identification": _ssc_get(mic, "/api/device/identification"),
    }
    if auth is not None:
        out["site"] = _ssc_get(mic, "/api/device/site", auth=auth)
        out["state"] = _ssc_get(mic, "/api/device/state", auth=auth)
    else:
        out["auth_hint"] = (
            "Set SENNHEISER_TCC_PASSWORD in .env to unlock /api/device/state, "
            "/api/device/site, and mute control. Password comes from "
            "Sennheiser Control Cockpit: Devices > {device} > Access > "
            "3rd Party Access > Edit > Secure."
        )
    return out


def identify_microphone(mic_id: str, visual: bool = True) -> dict:
    """Toggle the LED-flash identification on a mic.

    PUT /api/device/identification with body {"visual": true|false}.
    Requires HTTP Basic auth (env vars). Returns 409 from the device
    if PUT is attempted without credentials — we surface that error
    pre-emptively when no password is configured.
    """
    mic = _find_mic(mic_id)
    if mic is None:
        return {"error": f"microphone {mic_id!r} not found via mDNS"}
    auth = _ssc_auth()
    if auth is None:
        return {
            "error": "auth required",
            "detail": (
                "PUT /api/device/identification needs Basic auth. Set "
                "SENNHEISER_TCC_PASSWORD in /home/admin/screen-mgr/.env "
                "(username defaults to 'api'). Password is set in "
                "Sennheiser Control Cockpit under 3rd Party Access > Secure."
            ),
        }
    url = _ssc_url(mic, "/api/device/identification")
    try:
        r = requests.put(
            url,
            data=json.dumps({"visual": bool(visual)}),
            headers={"Content-Type": "application/json"},
            verify=False,
            timeout=SSC_TIMEOUT_S,
            auth=auth,
        )
    except requests.RequestException as e:
        return {"error": "SSC PUT failed", "url": url, "detail": repr(e)}
    return {
        "mic_id": mic["id"],
        "ip": mic["ip"],
        "visual": bool(visual),
        "http_status": r.status_code,
        "ok": 200 <= r.status_code < 300,
        "body": (r.text[:500] if r.text else ""),
    }


def _read_mute(mic: dict) -> Optional[bool]:
    """Best-effort read of the current mute state from /api/ssc/state.
    Returns None if the field can't be located — different TCC firmware
    nests it differently."""
    url = _ssc_url(mic, "/api/ssc/state")
    try:
        r = requests.get(url, verify=False, timeout=SSC_TIMEOUT_S)
        if r.status_code >= 400:
            return None
        state = r.json()
    except (requests.RequestException, ValueError):
        return None
    # Try the common paths first.
    candidates = (state, state.get("audio") if isinstance(state, dict) else None)
    for blob in candidates:
        if isinstance(blob, dict):
            v = blob.get("mute")
            if isinstance(v, bool):
                return v
            if isinstance(v, dict) and isinstance(v.get("value"), bool):
                return v["value"]
    return None


def run_mic_test(mic_id: str, probes: int = 3, blink_seconds: float = 3.0) -> dict:
    """Self-test for a microphone.

    Two modes, chosen automatically:

    1. **LED-flash test** when SENNHEISER_TCC_PASSWORD is configured.
       PUT visual=true on /api/device/identification, sleep
       ``blink_seconds``, PUT visual=false. The TCC's LED ring
       flashes visibly the whole time.

    2. **Reachability probe** otherwise. Runs ``probes`` unauth
       HTTPS GETs against /api/device/identity and reports per-probe
       status + latency. Confirms LAN routing + the device's TLS
       listener even though the LED flash needs creds.
    """
    mic = _find_mic(mic_id)
    if mic is None:
        return {"error": f"microphone {mic_id!r} not found via mDNS"}

    if _ssc_auth() is not None:
        return _run_identify_test(mic, max(0.5, min(15.0, float(blink_seconds))))
    return _run_reachability_probe(mic, max(1, min(10, int(probes))))


def _run_identify_test(mic: dict, blink_seconds: float) -> dict:
    on = identify_microphone(mic["id"], visual=True)
    if on.get("error"):
        return {"mode": "identify", "ok": False, **on}
    time.sleep(blink_seconds)
    off = identify_microphone(mic["id"], visual=False)
    return {
        "mode": "identify",
        "mic_id": mic["id"],
        "ip": mic["ip"],
        "blink_seconds": blink_seconds,
        "ok": on.get("ok") and off.get("ok", False),
        "on": on,
        "off": off,
    }


def _run_reachability_probe(mic: dict, probes: int) -> dict:
    # Hit /api/device/identity — known-200 unauth endpoint, so a
    # successful probe gives both reachability AND a confirmed JSON
    # response (vs. the previous bare "/" probe that always 404'd).
    url = _ssc_url(mic, "/api/device/identity")
    samples: list[dict] = []
    for i in range(probes):
        t0 = time.monotonic()
        status: Optional[int] = None
        err: Optional[str] = None
        try:
            r = requests.get(url, verify=False, timeout=SSC_TIMEOUT_S)
            status = r.status_code
        except requests.RequestException as e:
            err = repr(e)
        elapsed_ms = (time.monotonic() - t0) * 1000
        samples.append({
            "probe": i + 1,
            "http_status": status,
            "latency_ms": round(elapsed_ms, 1),
            "error": err,
        })
        if i < probes - 1:
            time.sleep(0.2)
    ok = all(s["http_status"] == 200 for s in samples)
    return {
        "mode": "reachability",
        "mic_id": mic["id"],
        "ip": mic["ip"],
        "url": url,
        "probes": probes,
        "ok": ok,
        "samples": samples,
        "note": (
            "Reachability probe — SSCv2 identity endpoint. Set "
            "SENNHEISER_TCC_PASSWORD in .env to unlock the real "
            "LED-flash test."
        ),
    }


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
