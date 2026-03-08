"""アプリ起動処理。"""

import os
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .util import constants as C

_APP_ICON_REL_PATH = Path("assets/icons/chroma_monitor.ico")


def _single_instance_lock_path() -> str:
    """単一起動制御に使うロックファイルの保存先を返す。"""
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


def _app_resource_base_dir() -> Path:
    """実行形態に応じたリソース探索の基準ディレクトリを返す。"""
    # PyInstaller 実行時は _MEIPASS、開発実行時はリポジトリ直下を基準にする。
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        try:
            return Path(meipass)
        except Exception:
            pass
    return Path(__file__).resolve().parent.parent


def _load_app_icon() -> QIcon:
    """候補パスを順に探索してアプリアイコンを読み込む。"""
    base = _app_resource_base_dir()
    exe_dir = Path(sys.executable).resolve().parent
    candidates = (
        base / _APP_ICON_REL_PATH,
        exe_dir / _APP_ICON_REL_PATH,
        exe_dir / "chroma_monitor.ico",
        exe_dir / "ChromaMonitor.ico",
    )
    for path in candidates:
        try:
            if not path.is_file():
                continue
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
        except Exception:
            continue
    return QIcon()


def main() -> None:
    """アプリケーションを初期化し、メインウィンドウを起動する。"""
    # Qt6既定のPassThroughは混在DPI環境でWidgetsの描画/幾何が不安定になることがある。
    # 先にRoundを指定してQt5相当の丸めに寄せ、画面跨ぎ時の揺れを抑える。
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.Round
    )
    app = QApplication(sys.argv)
    app.setApplicationName(C.APP_NAME)
    app.setOrganizationName(C.APP_NAME)
    app_icon = _load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    lock = QLockFile(_single_instance_lock_path())
    if not lock.tryLock(0):
        # 二重起動は許可しない（既存インスタンスが動作中）。
        return

    w = MainWindow()
    if not app_icon.isNull():
        w.setWindowIcon(app_icon)
    w.show()
    code = app.exec()
    lock.unlock()
    sys.exit(code)
