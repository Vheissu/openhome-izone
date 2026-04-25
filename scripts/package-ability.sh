#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
PACKAGE="$DIST_DIR/openhome-izone-ability.zip"
TOP_LEVEL_DIR="openhome-izone-ability"
BUILD_DIR="$DIST_DIR/package"

mkdir -p "$DIST_DIR"
rm -rf "$BUILD_DIR" "$PACKAGE"
mkdir -p "$BUILD_DIR/$TOP_LEVEL_DIR"

cp "$ROOT_DIR/ability/__init__.py" "$BUILD_DIR/$TOP_LEVEL_DIR/"
cp "$ROOT_DIR/ability/README.md" "$BUILD_DIR/$TOP_LEVEL_DIR/"
cp "$ROOT_DIR/ability/main.py" "$BUILD_DIR/$TOP_LEVEL_DIR/"

(
  cd "$BUILD_DIR"
  zip -qr "$PACKAGE" "$TOP_LEVEL_DIR" -x "*/__pycache__/*" "*.pyc" "*.DS_Store"
)

echo "$PACKAGE"
