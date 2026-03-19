"""プレビューウィンドウの更新とトグル処理。"""

from ...util import constants as C
from ...util.qt_helpers import set_checked_blocked
from .runtime_capture import selected_capture_source
from .runtime_common import on_status
from .runtime_layout_pause import sync_worker_view_flags


def update_preview_snapshot(main_window):
    """現在の取得設定でプレビューを1回更新する。"""
    if not main_window.chk_preview_window.isChecked():
        return
    capture = main_window.worker.capture_selection()
    if (
        selected_capture_source(main_window) == C.CAPTURE_SOURCE_WINDOW
        and capture.target_hwnd is None
    ):
        message = "ターゲットウィンドウを選択してください"
        main_window.preview_window.show_placeholder(message)
        on_status(main_window, message)
        return
    bgr, _, err = main_window.worker.capture_once()
    if bgr is None:
        main_window.preview_window.show_placeholder(err or "キャプチャ領域を選択してください")
        if err:
            on_status(main_window, err)
        return
    if not main_window.preview_window.isVisible():
        main_window.preview_window.show()
    main_window.preview_window.update_preview(bgr)


def on_preview_toggled(main_window, checked: bool):
    """プレビューの有効状態を実ウィンドウへ反映する。"""
    if checked:
        main_window.preview_window.show()
        update_preview_snapshot(main_window)
        on_status(main_window, "プレビュー表示")
    else:
        main_window.preview_window.hide()
        on_status(main_window, "プレビュー非表示")
    sync_worker_view_flags(main_window)
    main_window._request_save_settings()


def on_preview_closed(main_window):
    """プレビューウィンドウの手動クローズをチェック状態へ反映する。"""
    if main_window.chk_preview_window.isChecked():
        set_checked_blocked(main_window.chk_preview_window, False)
    sync_worker_view_flags(main_window)
    on_status(main_window, "プレビュー非表示")
