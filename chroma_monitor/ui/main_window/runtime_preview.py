"""プレビューウィンドウの更新とトグル処理。"""

from ...util.qt_helpers import set_checked_blocked
from .runtime_capture import capture_preflight_result
from .runtime_common import on_status
from .runtime_layout_pause import sync_worker_view_flags
from .window_topmost import present_top_level_widget


def _present_preview_window(main_window) -> None:
    """プレビューウィンドウを位置確定後に表示する。"""
    present_top_level_widget(
        main_window,
        main_window.preview_window,
        fit_before_show=lambda: main_window._fit_top_level_widget_to_desktop(
            main_window.preview_window,
            allow_resize=False,
        ),
        raise_window=False,
        activate_window=False,
    )


def update_preview_snapshot(main_window):
    """現在の取得設定でプレビューを1回更新する。"""
    if not main_window.chk_preview_window.isChecked():
        return
    if not main_window.preview_window.isVisible():
        _present_preview_window(main_window)
    preflight = capture_preflight_result(main_window)
    if not preflight.ready:
        message = str(preflight.message or "")
        main_window.preview_window.show_placeholder(message)
        on_status(main_window, message)
        return
    bgr, _, err = main_window.worker.capture_once()
    if bgr is None:
        main_window.preview_window.show_placeholder(err or "キャプチャ領域を選択してください")
        if err:
            on_status(main_window, err)
        return
    main_window.preview_window.update_preview(bgr)


def on_preview_toggled(main_window, checked: bool):
    """プレビューの有効状態を実ウィンドウへ反映する。"""
    if checked:
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
