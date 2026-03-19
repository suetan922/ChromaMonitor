"""実行時アクション群で共有する補助処理。"""

from PySide6.QtCore import QTimer


def safe_call(func, *args, **kwargs) -> bool:
    """例外を握りつぶして関数を呼び、成功可否を返す。"""
    try:
        func(*args, **kwargs)
        return True
    except Exception:
        return False


def safe_is_visible(widget) -> bool:
    """`isVisible` を安全に評価する。"""
    if widget is None:
        return False
    try:
        return bool(widget.isVisible())
    except Exception:
        return False


def set_run_toggle_state(main_window, running: bool) -> None:
    """Start/Stop のトグル表示状態を同期する。"""
    main_window.btn_start_bar.setChecked(bool(running))
    main_window.btn_stop_bar.setChecked(not bool(running))


def on_status(main_window, text: str):
    """ステータスラベルを更新する。"""
    main_window.lbl_status.setText(text)


def safe_close_widget(widget, *, only_if_visible: bool = False) -> None:
    """例外を握りつぶして安全にウィジェットを閉じる。"""
    if widget is None:
        return
    if only_if_visible and not safe_is_visible(widget):
        return
    safe_call(widget.close)


def restore_visible_docks_from_snapshot(main_window) -> None:
    """可視ドックを最新スナップショットで再描画する。"""
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None or not safe_is_visible(dock):
            continue
        safe_call(main_window._restore_dock_from_snapshot, dock)


def schedule_snapshot_restore(main_window, *delays_ms: int) -> None:
    """遅延タイミングを指定してスナップショット復元を予約する。"""
    for delay in delays_ms:
        QTimer.singleShot(
            int(delay),
            lambda mw=main_window: restore_visible_docks_from_snapshot(mw),
        )
