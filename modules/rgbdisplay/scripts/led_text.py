#!/usr/bin/env python3
"""LED Matrix text — render a short word/phrase (e.g. a client name like
"IKEA") centered on the 128×64 chained matrix.

Sibling to led_clock.py / led_test_pattern.py on the Pi
(/home/admin/rpi-rgb-led-matrix/). start_display.sh launches this when
mode.txt == "text".

Content is read from two sibling files (written by the rgbdisplay module):
  text.txt        — the string to show (default "STUDIO")
  text_color.txt  — "R,G,B" 0-255 (default 255,255,255)

Re-read every frame, so the module can update them and the panel follows
on the next tick. Matrix init args match led_clock.py / led_test_pattern.py
exactly (drop_privileges=False is required or the panel renders blank).
"""

from __future__ import annotations

import os
import sys
import time

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics  # type: ignore
except ImportError:
    print("FATAL: rgbmatrix not installed — install hzeller/rpi-rgb-led-matrix.")
    sys.exit(1)


HERE = os.path.dirname(os.path.abspath(__file__))


def find_font(name: str) -> str | None:
    """Same font search path as led_test_pattern.py."""
    parent = os.path.dirname(HERE)
    sudo_user = os.environ.get("SUDO_USER", "")
    real_home = (
        os.path.expanduser(f"~{sudo_user}") if sudo_user else os.path.expanduser("~")
    )
    candidates = [
        os.path.join(parent, "hzeller-rpi-rgb-led-matrix", "fonts", name),
        os.path.join(parent, "rpi-rgb-led-matrix", "fonts", name),
        os.path.join(real_home, "hzeller-rpi-rgb-led-matrix", "fonts", name),
        os.path.join(real_home, "rpi-rgb-led-matrix", "fonts", name),
        f"/root/hzeller-rpi-rgb-led-matrix/fonts/{name}",
        f"/home/admin/hzeller-rpi-rgb-led-matrix/fonts/{name}",
        f"/home/pi/rpi-rgb-led-matrix/fonts/{name}",
        os.path.join(HERE, "fonts", name),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def load_font() -> graphics.Font:
    """Prefer a big, readable font; fall back to smaller bundled ones."""
    for name in ("10x20.bdf", "9x18.bdf", "8x13B.bdf", "7x13.bdf", "6x10.bdf"):
        p = find_font(name)
        if p:
            f = graphics.Font()
            f.LoadFont(p)
            return f
    raise FileNotFoundError("no bundled BDF font found")


def _read(name: str, default: str) -> str:
    try:
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            return fh.read().strip() or default
    except OSError:
        return default


def read_text() -> str:
    return _read("text.txt", "STUDIO")[:32]


def read_color() -> tuple[int, int, int]:
    raw = _read("text_color.txt", "255,255,255")
    try:
        parts = [max(0, min(255, int(p))) for p in raw.split(",")[:3]]
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
    except ValueError:
        pass
    return 255, 255, 255


def text_width(font: graphics.Font, s: str) -> int:
    w = 0
    for ch in s:
        cw = font.CharacterWidth(ord(ch))
        w += cw if cw > 0 else 6
    return w


def main() -> int:
    options = RGBMatrixOptions()
    options.rows = 64
    options.cols = 64
    options.chain_length = 2
    options.parallel = 1
    options.hardware_mapping = "regular"
    options.brightness = 80
    options.pwm_bits = 8
    options.pwm_lsb_nanoseconds = 50
    options.led_rgb_sequence = "RBG"
    options.gpio_slowdown = 4
    options.drop_privileges = False

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()
    font = load_font()
    width, height = matrix.width, matrix.height
    # Vertical centering using the font's own metrics.
    y = (height - font.height) // 2 + font.baseline

    last: tuple[str, tuple[int, int, int]] | None = None
    x = 0
    color = graphics.Color(255, 255, 255)
    text = ""

    while True:
        t, c = read_text(), read_color()
        if last != (t, c):
            text, color = t, graphics.Color(*c)
            x = max(0, (width - text_width(font, t)) // 2)
            last = (t, c)
        canvas.Clear()
        graphics.DrawText(canvas, font, x, y, color, text)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
