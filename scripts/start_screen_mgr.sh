#!/bin/bash
# Launch the screen-mgr FastAPI server in a named GNU screen session.
#
# Mirrors the rpi-rgb-led-matrix/start_display.sh pattern. Called by humans
# and by scripts/systemd/screen-mgr.service. Idempotent: kills any existing
# session with the same name before starting a fresh one.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCREEN_NAME="screen-mgr"

# Kill any existing session and wait for the port to free up
screen -S "$SCREEN_NAME" -X quit 2>/dev/null || true
for _ in 1 2 3 4 5; do
    if ! pgrep -f "uvicorn main:app" >/dev/null; then
        break
    fi
    sleep 1
done
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1

# Start fresh
screen -dmS "$SCREEN_NAME" bash -c "cd '$APP_DIR' && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0"

echo "$SCREEN_NAME started"
echo "  Attach: screen -r $SCREEN_NAME"
echo "  Stop:   screen -S $SCREEN_NAME -X quit"
