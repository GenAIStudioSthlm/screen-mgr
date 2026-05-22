#!/usr/bin/env python3
"""LED Matrix test pattern — grid + 4-corner clock + center diamond.

Sibling to `led_clock.py` on the Pi (lives in /home/admin/rpi-rgb-led-matrix/).
Used by the studio admin's "Run test" button under Screens → LED panels.

Layout on the 128×64 chained matrix:

    +-------------------------------+
    |TIME              MON          |
    |HH:MM             MMM          |
    |                               |
    |              ◆               |     <- magenta diamond, dead center
    |                               |
    |DAY               YEAR         |
    |DD                YYYY         |
    +-------------------------------+

Plus a dim 16-px grid overlay covering the whole panel — proves every
column/row of every chained panel is alive.

Runs forever until the screen session is killed (start_display.sh's
restart hook). The optional --duration arg makes the script exit after
N seconds if you want to test standalone.

Hardware args (--rows / --pwm-bits / --pwm-lsb-nanoseconds /
--led-rgb-sequence) match start_display.sh so this script gets the
same matrix initialization as led_clock.py.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics  # type: ignore
except ImportError:
    print("FATAL: rgbmatrix not installed — install hzeller/rpi-rgb-led-matrix.")
    sys.exit(1)


# Centered-around-origin pixel list for a filled 9x9 diamond.
DIAMOND_PIXELS = [
    (0, -4),
    (-1, -3), (0, -3), (1, -3),
    (-2, -2), (-1, -2), (0, -2), (1, -2), (2, -2),
    (-3, -1), (-2, -1), (-1, -1), (0, -1), (1, -1), (2, -1), (3, -1),
    (-4, 0), (-3, 0), (-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0), (3, 0), (4, 0),
    (-3, 1), (-2, 1), (-1, 1), (0, 1), (1, 1), (2, 1), (3, 1),
    (-2, 2), (-1, 2), (0, 2), (1, 2), (2, 2),
    (-1, 3), (0, 3), (1, 3),
    (0, 4),
]


def find_font(name: str = "6x10.bdf") -> str:
    """Locate a bundled BDF font. Mirrors `led_clock.py`'s search path
    so we find fonts in the same place (typically
    `/root/hzeller-rpi-rgb-led-matrix/fonts/` when run via the systemd
    unit, since the library was cloned into root's home)."""
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    # When sudo'd, the *original* user's home; pure-root systemd runs
    # give us /root. Same logic the clock uses.
    sudo_user = os.environ.get("SUDO_USER", "")
    real_home = (
        os.path.expanduser(f"~{sudo_user}") if sudo_user
        else os.path.expanduser("~")
    )
    candidates = [
        os.path.join(parent, "hzeller-rpi-rgb-led-matrix", "fonts", name),
        os.path.join(parent, "rpi-rgb-led-matrix", "fonts", name),
        os.path.join(real_home, "hzeller-rpi-rgb-led-matrix", "fonts", name),
        os.path.join(real_home, "rpi-rgb-led-matrix", "fonts", name),
        f"/root/hzeller-rpi-rgb-led-matrix/fonts/{name}",
        f"/home/admin/hzeller-rpi-rgb-led-matrix/fonts/{name}",
        f"/home/pi/rpi-rgb-led-matrix/fonts/{name}",
        os.path.join(here, "fonts", name),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError(
        f"font {name!r} not found in any of: {candidates}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=64)
    ap.add_argument("--cols", type=int, default=64)
    ap.add_argument("--chain", type=int, default=2)
    ap.add_argument("--brightness", type=int, default=80)
    ap.add_argument("--pwm-bits", type=int, default=8)
    ap.add_argument("--pwm-lsb-nanoseconds", type=int, default=50)
    ap.add_argument("--led-rgb-sequence", default="RBG")
    ap.add_argument("--slowdown-gpio", type=int, default=4)
    ap.add_argument(
        "--duration",
        type=int,
        default=0,
        help="seconds to run before exiting; 0 = run forever",
    )
    args = ap.parse_args()

    options = RGBMatrixOptions()
    options.rows = args.rows
    options.cols = args.cols
    options.chain_length = args.chain
    options.parallel = 1
    options.hardware_mapping = "regular"
    options.brightness = args.brightness
    options.pwm_bits = args.pwm_bits
    options.pwm_lsb_nanoseconds = args.pwm_lsb_nanoseconds
    options.led_rgb_sequence = args.led_rgb_sequence
    options.gpio_slowdown = args.slowdown_gpio
    # Critical: matches led_clock.py. The library drops to user `daemon`
    # by default after init; with HUB75 wiring + Pi 4 that renders the
    # matrix blank. Keeping root throughout the script's lifetime is
    # what the clock does, and is required here too.
    options.drop_privileges = False

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()

    font = graphics.Font()
    font.LoadFont(find_font("6x10.bdf"))

    color_label = graphics.Color(120, 120, 120)
    color_value = graphics.Color(220, 220, 220)

    width = matrix.width
    height = matrix.height
    cx = width // 2
    cy = height // 2

    end_at = time.monotonic() + args.duration if args.duration > 0 else None

    while True:
        if end_at is not None and time.monotonic() >= end_at:
            break

        canvas.Clear()

        # ---------- sparse grid (dim) ----------
        # SetPixel is the cheapest primitive in this library; no DrawLine.
        for x in range(0, width, 16):
            for y in range(height):
                canvas.SetPixel(x, y, 18, 18, 30)
        for y in range(0, height, 16):
            for x in range(width):
                canvas.SetPixel(x, y, 18, 18, 30)

        # ---------- center diamond ----------
        for dx, dy in DIAMOND_PIXELS:
            canvas.SetPixel(cx + dx, cy + dy, 255, 80, 200)

        # ---------- four corner stamps ----------
        now = datetime.now()
        # 6x10 font: chars are ~6 wide, baseline at y means the bottom of
        # the character sits on row y. Top-line baseline ~9, bottom-line
        # baseline = height-2 keeps a 1-px margin.
        # Top-left — TIME
        graphics.DrawText(canvas, font, 2, 9, color_label, "TIME")
        graphics.DrawText(canvas, font, 2, 19, color_value, now.strftime("%H:%M"))
        # Top-right — MON
        right_x = width - 24  # "MMM" / "MON" ~ 4 chars * 6
        graphics.DrawText(canvas, font, right_x, 9, color_label, "MON")
        graphics.DrawText(canvas, font, right_x, 19, color_value, now.strftime("%b").upper())
        # Bottom-left — DAY
        graphics.DrawText(canvas, font, 2, height - 12, color_label, "DAY")
        graphics.DrawText(canvas, font, 2, height - 2, color_value, now.strftime("%d"))
        # Bottom-right — YEAR
        graphics.DrawText(canvas, font, right_x, height - 12, color_label, "YEAR")
        graphics.DrawText(canvas, font, right_x, height - 2, color_value, now.strftime("%Y"))

        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.5)

    return 0


if __name__ == "__main__":
    sys.exit(main())
