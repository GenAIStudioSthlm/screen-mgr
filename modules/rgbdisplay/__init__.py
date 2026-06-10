"""rgbdisplay module — wraps the existing rgbdisplay.service systemd unit
that drives the 128×64 (2×64×64 chained) LED matrix.

Surfaces the unit's state (active/inactive/missing) to the admin and lets
the admin start/stop it from the Modules tab without SSHing into the Pi.

Also drives the grid-test-pattern variant via a mode-marker file:
`start_display.sh` reads `mode.txt` from its own dir to pick which Python
script to launch (`led_clock.py` for "clock", `led_test_pattern.py` for
"test_pattern"). `run_test_pattern()` toggles the file and restarts the
unit so the matrix swaps content without any extra systemd plumbing.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from modules.base import ServiceModule

UNIT = "rgbdisplay.service"

# Where start_display.sh + led_clock.py + led_test_pattern.py live on
# the Pi. The mode marker file is read by start_display.sh on each
# launch.
_DISPLAY_DIR = Path("/home/admin/rpi-rgb-led-matrix")
_MODE_FILE = _DISPLAY_DIR / "mode.txt"
# Content files read by led_text.py when mode == "text".
_TEXT_FILE = _DISPLAY_DIR / "text.txt"
_TEXT_COLOR_FILE = _DISPLAY_DIR / "text_color.txt"


def _hex_to_rgb(color_hex: str) -> tuple[int, int, int] | None:
    """'#RRGGBB' (or 'RRGGBB') → (r, g, b), or None if unparseable."""
    s = (color_hex or "").strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return None


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, capture_output=True, text=True, timeout=10, check=False
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

    # --- content variant (mode-marker file) ----------------------------

    def _set_mode(self, mode: str) -> None:
        """Write the mode marker so start_display.sh picks the right
        Python script on the next launch."""
        _MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MODE_FILE.write_text(mode + "\n", encoding="utf-8")

    def _restart(self) -> subprocess.CompletedProcess[str]:
        """systemctl restart — kills the old screen session and re-runs
        start_display.sh, which reads the fresh mode marker."""
        return _run("sudo", "systemctl", "restart", UNIT)

    async def show_text(self, text: str, color_hex: str | None = None) -> dict[str, Any]:
        """Show a short word/phrase (e.g. a client name like "IKEA") on the
        matrix in an optional #RRGGBB color. Writes the content files, sets
        mode=text, and restarts the unit so `start_display.sh` launches
        `led_text.py`. Persists until changed or reverted (unlike the
        auto-reverting test pattern)."""
        safe = (text or "").strip()[:32] or "STUDIO"
        _DISPLAY_DIR.mkdir(parents=True, exist_ok=True)
        _TEXT_FILE.write_text(safe + "\n", encoding="utf-8")
        rgb = _hex_to_rgb(color_hex) if color_hex else None
        if rgb:
            _TEXT_COLOR_FILE.write_text(f"{rgb[0]},{rgb[1]},{rgb[2]}\n", encoding="utf-8")
        self._set_mode("text")
        r = await asyncio.to_thread(self._restart)
        return {
            "ok": r.returncode == 0,
            "text": safe,
            "color_hex": color_hex if rgb else None,
            "mode": "text",
            "stderr": r.stderr.strip(),
            "final_status": self.status(),
        }

    async def run_test_pattern(self, duration_seconds: int = 15) -> dict[str, Any]:
        """Show the grid test pattern for ~`duration_seconds`, then
        revert to the clock.

        Flow:
          1. Write mode=test_pattern, restart the unit. start_display.sh
             launches `led_test_pattern.py`.
          2. Sleep `duration_seconds`.
          3. Write mode=clock, restart the unit. Clock comes back.

        Returns a dict with per-step results so the caller can verify
        each transition. Async so the FastAPI / MCP tool path doesn't
        block uvicorn's event loop during the wait."""
        if duration_seconds < 1:
            duration_seconds = 1
        elif duration_seconds > 120:
            duration_seconds = 120  # cap so an agent typo can't park us in test mode

        self._set_mode("test_pattern")
        start = await asyncio.to_thread(self._restart)

        await asyncio.sleep(duration_seconds)

        self._set_mode("clock")
        revert = await asyncio.to_thread(self._restart)

        return {
            "ok": start.returncode == 0 and revert.returncode == 0,
            "duration_seconds": duration_seconds,
            "start_test": {
                "ok": start.returncode == 0,
                "stderr": start.stderr.strip(),
            },
            "revert_to_clock": {
                "ok": revert.returncode == 0,
                "stderr": revert.stderr.strip(),
            },
            "final_status": self.status(),
        }
