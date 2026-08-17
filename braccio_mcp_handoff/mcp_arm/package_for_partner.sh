#!/usr/bin/env bash
#
# Build a clean, portable zip of the Braccio MCP server to hand to a partner.
#
# Ships the source + bundled YOLO model + docs. Deliberately EXCLUDES:
#   - .venv/          (1.1 GB, machine-specific absolute paths — partner recreates it)
#   - __pycache__/    (stale bytecode)
#   - calibration.json + calib_debug/  (room-specific to the original camera placement)
#   - mcp_arm/        (a stale nested snapshot from an earlier handoff)
#   - *.zip           (don't nest old packages inside the new one)
#   - .DS_Store       (macOS cruft)
#
# Usage:  ./package_for_partner.sh  [output.zip]
# Run from inside the mcp_arm/ directory.

set -euo pipefail

cd "$(dirname "$0")"

OUT="${1:-braccio_mcp_handoff.zip}"
# Make the output path absolute so we can zip from the parent dir.
case "$OUT" in
  /*) : ;;
  *)  OUT="$PWD/$OUT" ;;
esac

if [ ! -f yolo11n-seg.pt ]; then
  echo "WARNING: yolo11n-seg.pt not found — the package will require an internet" >&2
  echo "         download on first run. Continuing anyway." >&2
fi

rm -f "$OUT"

# Zip from the parent so the archive contains a top-level mcp_arm/ folder.
cd ..
zip -r "$OUT" mcp_arm \
  -x 'mcp_arm/.venv/*' \
     'mcp_arm/__pycache__/*' \
     'mcp_arm/calib_debug/*' \
     'mcp_arm/calibration.json' \
     'mcp_arm/mcp_arm/*' \
     'mcp_arm/*.zip' \
     'mcp_arm/*.DS_Store' \
     'mcp_arm/.DS_Store'

echo
echo "Built: $OUT"
echo "Contents:"
unzip -l "$OUT"
