#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
PACKAGE="$DIST_DIR/openhome-izone-ability.zip"

mkdir -p "$DIST_DIR"
rm -f "$PACKAGE"

(
  cd "$ROOT_DIR/ability"
  zip -qr "$PACKAGE" . -x "__pycache__/*" "*.pyc"
)

echo "$PACKAGE"

