#!/bin/bash
# Pi-side deploy: fetch latest, pull if behind, conditionally install deps
# and restart the screen-mgr service through the maintenance bridge.
#
# Called by scripts/deploy.sh over SSH from the dev machine. Designed to be
# idempotent — re-running on an up-to-date repo is a no-op.

set -e

REPO_DIR="/home/admin/screen-mgr"
SERVICE="screen-mgr.service"

cd "$REPO_DIR"

BEFORE_SHA="$(git rev-parse HEAD)"
BEFORE_REQ_HASH="$(sha256sum requirements.txt | cut -d' ' -f1)"

echo "before: $BEFORE_SHA"

git fetch origin
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main)"

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "already at latest — nothing to deploy"
    exit 0
fi

git pull --ff-only
AFTER_SHA="$(git rev-parse HEAD)"
AFTER_REQ_HASH="$(sha256sum requirements.txt | cut -d' ' -f1)"
echo "after:  $AFTER_SHA"

if [ "$BEFORE_REQ_HASH" != "$AFTER_REQ_HASH" ]; then
    echo "requirements.txt changed — installing deps and restarting service"
    venv/bin/pip install -r requirements.txt
    sudo systemctl stop "$SERVICE"
    # Maintenance bridge — serves a friendly page on :8000 while uvicorn restarts
    python3 scripts/maintenance.py --duration 5
    sudo systemctl start "$SERVICE"
    # Wait until /admin responds before returning
    for _ in $(seq 1 15); do
        code="$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/admin || echo 000)"
        [ "$code" = "200" ] && break
        sleep 1
    done
else
    echo "no dep changes — uvicorn --reload will pick up new files"
    # Give --reload a moment to detect file changes before we hand back
    sleep 2
fi

echo "$(date -Iseconds) $AFTER_SHA" >> last_deploy.log
echo "deployed $AFTER_SHA"
