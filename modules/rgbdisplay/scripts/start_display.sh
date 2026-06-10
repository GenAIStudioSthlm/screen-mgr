#!/bin/bash
# =============================================================================
#  start_display.sh — Start an LED matrix script in a screen session.
# =============================================================================
#
#  Looks for $SCRIPT_DIR/mode.txt to decide what to run:
#    (missing or "clock")  → led_clock.py        (default)
#    "test_pattern"        → led_test_pattern.py
#    "text"                → led_text.py         (reads text.txt/text_color.txt)
#
#  The screen-mgr admin's "Run test" button writes mode.txt and then
#  `sudo systemctl restart rgbdisplay.service`, which re-invokes this
#  script with the new mode.
#
#  Usage:
#    sudo ./start_display.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCREEN_NAME="rgbdisplay"
MODE_FILE="$SCRIPT_DIR/mode.txt"

mode="clock"
if [ -f "$MODE_FILE" ]; then
    mode=$(tr -d '[:space:]' < "$MODE_FILE")
fi

case "$mode" in
    test_pattern) target="led_test_pattern.py" ;;
    text)         target="led_text.py" ;;
    *)            target="led_clock.py" ;;
esac

# Kill any existing session
screen -S "$SCREEN_NAME" -X quit 2>/dev/null

# Wait for hardware to be ready (useful on boot)
sleep 2

# Disable sound module (prevents GPIO conflicts)
modprobe -r snd_bcm2835 2>/dev/null

# Start the chosen script in a detached screen session
screen -dmS "$SCREEN_NAME" python3 "$SCRIPT_DIR/$target" \
    --rows 64 \
    --pwm-bits 8 \
    --pwm-lsb-nanoseconds 50 \
    --led-rgb-sequence "RBG"

echo "LED display started ($target, mode=$mode) in screen session '$SCREEN_NAME'"
echo "  Attach: screen -r $SCREEN_NAME"
echo "  Stop:   screen -S $SCREEN_NAME -X quit"
