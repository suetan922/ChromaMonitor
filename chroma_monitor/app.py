"""アプリ起動処理。"""

import os
import sys

from PySide6.QtCore import QLockFile, QStandardPaths
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def _single_instance_lock_path() -> str:
    # 起動ロックは書き込み可能ディレクトリを順に探して配置する。
    candidates = [
        QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation),
        QStandardPaths.writableLocation(QStandardPaths.TempLocation),
        os.getcwd(),
    ]
    for base in candidates:
        if not base:
            continue
        try:
            os.makedirs(base, exist_ok=True)
            return os.path.join(base, "chroma_monitor_single_instance.lock")
        except Exception:
            continue
    return os.path.join(os.getcwd(), "chroma_monitor_single_instance.lock")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ChromaMonitor")
    app.setOrganizationName("ChromaMonitor")

    lock = QLockFile(_single_instance_lock_path())
    if not lock.tryLock(0):
        # 二重起動は許可しない（既存インスタンスが動作中）。
        return

    w = MainWindow()
    w.show()
    code = app.exec()
    lock.unlock()
    sys.exit(code)
