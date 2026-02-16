#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WINEPREFIX="${WINEPREFIX:-$HOME/.wine_test}"
WINEARCH="${WINEARCH:-win64}"
DIST_WIN_DIR="${DIST_WIN_DIR:-/tmp/dist_win}"
BUILD_WIN_DIR="${BUILD_WIN_DIR:-/tmp/pyi_build}"
SPEC_WIN_DIR="${SPEC_WIN_DIR:-/tmp/pyi_spec}"
OUTPUT_SHARE_DIR="${OUTPUT_SHARE_DIR:-/mnt/hgfs/share}"
OUTPUT_EXE_NAME="${OUTPUT_EXE_NAME:-chroma_monitor.exe}"

export WINEPREFIX
export WINEARCH

to_wine_z_path() {
  printf 'Z:%s' "$(printf '%s' "$1" | sed 's|/|\\\\|g')"
}

PROJECT_WIN_PATH="$(to_wine_z_path "$PROJECT_ROOT")"
DIST_WIN_PATH="$(to_wine_z_path "$DIST_WIN_DIR")"
BUILD_WIN_PATH="$(to_wine_z_path "$BUILD_WIN_DIR")"
SPEC_WIN_PATH="$(to_wine_z_path "$SPEC_WIN_DIR")"

mkdir -p "$DIST_WIN_DIR" "$BUILD_WIN_DIR" "$SPEC_WIN_DIR"

if ! wineboot -u >/dev/null 2>&1; then
  echo "Wine prefix initialization failed (WINEPREFIX=$WINEPREFIX)." >&2
  echo "Try recreating prefix: rm -rf \"$WINEPREFIX\" && WINEARCH=$WINEARCH WINEPREFIX=\"$WINEPREFIX\" wineboot -u" >&2
  exit 1
fi

wine cmd /c \
  "cd /d ${PROJECT_WIN_PATH} && python -m PyInstaller --onefile --noconsole --clean --noconfirm --name chroma_monitor --collect-all PySide6 --collect-all shiboken6 --distpath ${DIST_WIN_PATH} --workpath ${BUILD_WIN_PATH} --specpath ${SPEC_WIN_PATH} main.py"

echo "Built: $DIST_WIN_DIR/chroma_monitor.exe"

if mkdir -p "$OUTPUT_SHARE_DIR" >/dev/null 2>&1; then
  if cp "$DIST_WIN_DIR/chroma_monitor.exe" "$OUTPUT_SHARE_DIR/$OUTPUT_EXE_NAME" >/dev/null 2>&1; then
    echo "Copied: $OUTPUT_SHARE_DIR/$OUTPUT_EXE_NAME"
  else
    echo "Copy failed (no permission?): $OUTPUT_SHARE_DIR" >&2
    echo "Use: cp \"$DIST_WIN_DIR/chroma_monitor.exe\" <writable_path>" >&2
  fi
else
  echo "Output dir is not writable: $OUTPUT_SHARE_DIR" >&2
  echo "Use: cp \"$DIST_WIN_DIR/chroma_monitor.exe\" <writable_path>" >&2
fi
