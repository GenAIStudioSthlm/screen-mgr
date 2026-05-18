#!/bin/bash
# Deploy local main → Pi (manual, run from WSL when a feature is complete).
#
# Steps:
#   1. Preflight: clean tree, no unpushed commits, on main
#   2. SSH to Pi, run scripts/pi-update.sh (git pull, conditional deps + restart)
#   3. POST /api/screens/reload-all so every connected display refreshes
#
# Pi host and admin URL can be overridden via env vars (useful if the LAN
# address changes or for a second Pi).

set -e

PI_HOST="${PI_HOST:-admin@192.168.2.65}"
ADMIN_URL="${ADMIN_URL:-http://192.168.2.65:8000}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
ylw()   { printf "\033[33m%s\033[0m\n" "$*"; }

# ---------- preflight ----------
echo "== preflight =="

if ! git diff-index --quiet HEAD --; then
    red "ERROR: working tree has uncommitted changes. Commit or stash first."
    git status --short
    exit 1
fi

git fetch origin --quiet
LOCAL="$(git rev-parse HEAD)"
REMOTE_MAIN="$(git rev-parse origin/main)"
AHEAD="$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)"
BEHIND="$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)"

if [ "$AHEAD" -gt 0 ]; then
    red "ERROR: local has $AHEAD unpushed commit(s). Run: git push"
    exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BRANCH" != "main" ]; then
    ylw "WARNING: current branch is '$BRANCH' but Pi tracks origin/main."
    ylw "         The Pi will deploy origin/main, not your branch."
fi

echo "  local HEAD : $LOCAL"
echo "  Pi target  : $REMOTE_MAIN"
[ "$BEHIND" -gt 0 ] && ylw "  (local is $BEHIND behind origin/main)"

# ---------- pi-update ----------
echo
echo "== pi-update on $PI_HOST =="
ssh -o ConnectTimeout=5 "$PI_HOST" 'bash /home/admin/screen-mgr/scripts/pi-update.sh'

# ---------- reload screens ----------
echo
echo "== reload-all =="
response="$(curl -s -X POST "$ADMIN_URL/api/screens/reload-all" || true)"
if [ -z "$response" ]; then
    ylw "WARNING: reload-all returned no response (admin may still be coming up)"
else
    echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
fi

echo
green "== deploy complete =="
