"""ヘルプメニューと更新確認の補助処理。"""

import json
import re

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QMenuBar

from ...util import constants as C


def _parse_version_tuple(text: str) -> tuple[int, ...] | None:
    parts = re.findall(r"\d+", str(text or ""))
    if not parts:
        return None
    return tuple(int(p) for p in parts[:4])


def _is_release_newer(current_version: str, latest_tag: str) -> bool:
    current = _parse_version_tuple(current_version)
    latest = _parse_version_tuple(latest_tag)
    if current is None or latest is None:
        return False
    n = max(len(current), len(latest))
    current = current + (0,) * (n - len(current))
    latest = latest + (0,) * (n - len(latest))
    return latest > current


def setup_help_menu(main_window, menu_bar: QMenuBar) -> None:
    main_window.help_menu = menu_bar.addMenu("ヘルプ")
    main_window.act_open_release_page = main_window.help_menu.addAction("更新情報を開く")
    main_window.act_open_release_page.setToolTip(f"リリースページを開く（現在: v{C.APP_VERSION}）")
    main_window.act_open_release_page.triggered.connect(main_window._open_release_page)
    main_window.act_version_info = main_window.help_menu.addAction(
        f"現在のバージョン: v{C.APP_VERSION}"
    )
    main_window.act_version_info.setEnabled(False)
    main_window.act_update_available = main_window.help_menu.addAction("")
    main_window.act_update_available.setEnabled(False)
    main_window.act_update_available.setVisible(False)


def start_release_check_once(main_window) -> None:
    if main_window._update_check_started:
        return
    main_window._update_check_started = True
    QTimer.singleShot(900, main_window._check_latest_release)


def check_latest_release(main_window) -> None:
    if main_window._update_reply is not None:
        return
    request = QNetworkRequest(QUrl(C.LATEST_RELEASE_API_URL))
    request.setRawHeader(b"Accept", b"application/vnd.github+json")
    request.setRawHeader(b"User-Agent", b"ChromaMonitor")
    if hasattr(request, "setTransferTimeout"):
        request.setTransferTimeout(int(C.UPDATE_CHECK_TIMEOUT_MS))
    main_window._update_reply = main_window._update_network.get(request)


def on_release_check_finished(main_window, reply: QNetworkReply) -> None:
    if reply is None:
        return
    try:
        if main_window._update_reply is not None and reply is not main_window._update_reply:
            return
        main_window._update_reply = None
        if reply.error() != QNetworkReply.NoError:
            return
        raw = bytes(reply.readAll())
        if not raw:
            return
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        latest_tag = str(payload.get("tag_name", "")).strip()
        latest_url = str(payload.get("html_url", "")).strip()
        if latest_url:
            main_window._release_page_url = latest_url
        if latest_tag and _is_release_newer(C.APP_VERSION, latest_tag):
            main_window.act_update_available.setText(f"新しいバージョンがあります: {latest_tag}")
            main_window.act_update_available.setVisible(True)
        else:
            main_window.act_update_available.setVisible(False)
    except Exception:
        main_window.act_update_available.setVisible(False)
    finally:
        reply.deleteLater()


def open_release_page(main_window) -> None:
    QDesktopServices.openUrl(QUrl(main_window._release_page_url))
