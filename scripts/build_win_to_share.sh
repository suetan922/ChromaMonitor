#!/usr/bin/env bash
set -euo pipefail

# Windows 版を PyInstaller でビルドして VMware 共有フォルダへ配置する。
REPO_DIR="/home/dev/dev/ChromaMonitor"
WINEPREFIX_PATH="${HOME}/.wine_test"
DIST_DIR="/tmp/dist_win"
WORK_DIR="/tmp/pyi_build"
SPEC_DIR="/tmp/pyi_spec"
SHARE_DIR="/mnt/hgfs/share"
APP_NAME="ChromaMonitor"

cd "${REPO_DIR}"

WINEPREFIX="${WINEPREFIX_PATH}" wine cmd /c \
  "cd /d Z:\home\dev\dev\ChromaMonitor && \
   python -m PyInstaller \
     --onedir \
     --noconsole \
     --clean \
     --noconfirm \
     --name ${APP_NAME} \
     --collect-all PySide6 \
     --collect-all shiboken6 \
     --distpath Z:\tmp\dist_win \
     --workpath Z:\tmp\pyi_build \
     --specpath Z:\tmp\pyi_spec \
     main.py"

sudo rm -rf "${SHARE_DIR}/${APP_NAME}"
sudo cp -a "${DIST_DIR}/${APP_NAME}" "${SHARE_DIR}/"

echo "Done: ${SHARE_DIR}/${APP_NAME}"
ls -la "${SHARE_DIR}/${APP_NAME}"
