"""rgbdisplay module — wraps the existing rgbdisplay.service systemd unit
that drives the 32x64 LED matrix.

Surfaces the unit's state (active/inactive/missing) to the admin and lets
the admin start/stop it from the Modules tab without SSHing into the Pi.
"""

from __future__ import annotations

import subprocess
from typing import Any

from modules.base import ServiceModule

UNIT = "rgbdisplay.service"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, capture_output=True, text=True, timeout=5, check=False
    )


class RGBDisplayModule(ServiceModule):
    id = "rgbdisplay"
    name = "RGB LED Matrix"
    description = (
        "32x64 LED matrix on studiopi. Default content is led_clock.py; "
        "managed via the rgbdisplay.service systemd unit."
    )
    version = "0.1.0"

    # --- availability + status -----------------------------------------

    def is_available(self) -> bool:
        """True iff the systemd unit is installed on this host (regardless
        of whether it's running). Lets the admin still see a stopped LED
        matrix as 'a thing that exists you could turn on'."""
        try:
            r = _run("systemctl", "list-unit-files", UNIT, "--no-legend")
        except (FileNotFoundError, subprocess.SubprocessError):
            return False
        return UNIT in r.stdout

    def status(self) -> dict[str, Any]:
        try:
            active = _run("systemctl", "is-active", UNIT).stdout.strip()
            enabled = _run("systemctl", "is-enabled", UNIT).stdout.strip()
        except (FileNotFoundError, subprocess.SubprocessError) as e:
            return {"available": False, "error": str(e)}
        return {
            "available": self.is_available(),
            "active": active,    # "active" | "inactive" | "failed" | "unknown"
            "enabled": enabled,  # "enabled" | "disabled" | "static" | ...
        }

    # --- lifecycle ------------------------------------------------------

    def start(self) -> dict[str, Any]:
        r = _run("sudo", "systemctl", "start", UNIT)
        return {
            "ok": r.returncode == 0,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
        }

    def stop(self) -> dict[str, Any]:
        r = _run("sudo", "systemctl", "stop", UNIT)
        return {
            "ok": r.returncode == 0,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
        }
