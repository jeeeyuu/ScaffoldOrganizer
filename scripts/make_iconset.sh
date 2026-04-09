#!/usr/bin/env bash
# make_iconset.sh — Generate icon.icns from a PNG source
# macOS : uses sips + iconutil (built-in)
# Linux/WSL: uses ImageMagick + png2icns (icnsutils)
#   Install: sudo apt install imagemagick icnsutils
# Usage: ./scripts/make_iconset.sh path/to/icon.png

set -euo pipefail

SOURCE_ICON="${1:-}"
ICONSET_DIR="icon.iconset"

if [[ -z "$SOURCE_ICON" ]]; then
  echo "Usage: $0 <source_icon.png>" >&2
  exit 1
fi

if [[ ! -f "$SOURCE_ICON" ]]; then
  echo "Error: source icon not found: $SOURCE_ICON" >&2
  exit 1
fi

# ── macOS (sips + iconutil) ──────────────────────────────────────────────────
if command -v sips &>/dev/null && command -v iconutil &>/dev/null; then
  rm -rf "$ICONSET_DIR"
  mkdir -p "$ICONSET_DIR"

  for size in 16 32 64 128 256 512 1024; do
    sips -z "$size" "$size" "$SOURCE_ICON" \
      --out "${ICONSET_DIR}/icon_${size}x${size}.png" >/dev/null
  done

  iconutil -c icns "$ICONSET_DIR" -o icon.icns
  echo "Created icon.icns (macOS)"
  exit 0
fi

# ── Linux / WSL (ImageMagick + png2icns) ────────────────────────────────────
if command -v magick &>/dev/null; then
  CMD="magick"
elif command -v convert &>/dev/null; then
  CMD="convert"
else
  echo "Error: ImageMagick is not installed." >&2
  echo "  sudo apt install imagemagick" >&2
  exit 1
fi

if ! command -v png2icns &>/dev/null; then
  echo "Error: png2icns is not installed." >&2
  echo "  sudo apt install icnsutils" >&2
  exit 1
fi

rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

for size in 16 32 48 128 256 512; do
  $CMD "$SOURCE_ICON" -resize "${size}x${size}" \
    "${ICONSET_DIR}/icon_${size}x${size}.png"
done

png2icns icon.icns \
  "${ICONSET_DIR}/icon_16x16.png" \
  "${ICONSET_DIR}/icon_32x32.png" \
  "${ICONSET_DIR}/icon_48x48.png" \
  "${ICONSET_DIR}/icon_128x128.png" \
  "${ICONSET_DIR}/icon_256x256.png" \
  "${ICONSET_DIR}/icon_512x512.png"

echo "Created icon.icns (Linux/WSL)"
