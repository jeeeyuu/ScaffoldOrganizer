#!/usr/bin/env bash
# make_ico.sh — Generate assets/icon.ico from a PNG source
# Works on: Linux, macOS, WSL, Git Bash (requires ImageMagick)
# Usage: ./scripts/make_ico.sh path/to/icon.png

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT="$PROJECT_ROOT/assets/icon.ico"

SOURCE_ICON="${1:-}"

if [[ -z "$SOURCE_ICON" ]]; then
  echo "Usage: $0 <source_icon.png>" >&2
  exit 1
fi

if [[ ! -f "$SOURCE_ICON" ]]; then
  echo "Error: source icon not found: $SOURCE_ICON" >&2
  exit 1
fi

# ImageMagick v7+: magick / v6: convert
if command -v magick &>/dev/null; then
  CMD="magick"
elif command -v convert &>/dev/null; then
  CMD="convert"
else
  echo "Error: ImageMagick is not installed. Install it first." >&2
  echo "  Ubuntu/Debian: sudo apt install imagemagick" >&2
  echo "  macOS:         brew install imagemagick" >&2
  echo "  Windows WSL:   sudo apt install imagemagick" >&2
  exit 1
fi

mkdir -p "$PROJECT_ROOT/assets"
$CMD "$SOURCE_ICON" \
  \( -clone 0 -resize 16x16 \) \
  \( -clone 0 -resize 32x32 \) \
  \( -clone 0 -resize 48x48 \) \
  \( -clone 0 -resize 64x64 \) \
  \( -clone 0 -resize 128x128 \) \
  \( -clone 0 -resize 256x256 \) \
  -delete 0 "$OUTPUT"
echo "Created $OUTPUT"
