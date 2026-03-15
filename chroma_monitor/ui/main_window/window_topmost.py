"""最前面表示と設定ウィンドウ前面化の補助処理。"""

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QWidget

from ...capture.win32_windows import HAS_WIN32
from ...util.debug_log import write_window_layout_debug_log
from ...util.qt_helpers import blocked_signals, safe_window_handle

_WIN_SWP_NOSIZE = 0x0001
_WIN_SWP_NOMOVE = 0x0002
_WIN_SWP_NOACTIVATE = 0x0010
_WIN_SWP_NOSENDCHANGING = 0x0400
_WIN_SWP_NOOWNERZORDER = 0x0200
_WIN_TOPMOST_FLAGS = (
    _WIN_SWP_NOMOVE
    | _WIN_SWP_NOSIZE
    | _WIN_SWP_NOACTIVATE
    | _WIN_SWP_NOSENDCHANGING
    | _WIN_SWP_NOOWNERZORDER
)
_WIN_HWND_TOPMOST = None
_WIN_HWND_NOTOPMOST = None

_win_set_window_pos = None
if HAS_WIN32:
    try:
        import ctypes
        from ctypes import wintypes

        _win_set_window_pos = ctypes.windll.user32.SetWindowPos
        _WIN_HWND_TOPMOST = wintypes.HWND(-1)
        _WIN_HWND_NOTOPMOST = wintypes.HWND(-2)
        _win_set_window_pos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
    except Exception:
        _win_set_window_pos = None


def _widget_debug_name(widget: QWidget | None) -> str | None:
    """ログ向けにウィジェット名を安全に取得する。"""
    if widget is None:
        return None
    try:
        name = str(widget.objectName())
    except Exception:
        name = ""
    if name:
        return name
    return f"{type(widget).__name__}@{id(widget):x}"


def is_always_on_top_enabled(main_window) -> bool:
    """常に最前面表示が有効かを返す。"""
    return bool(
        getattr(main_window, "act_always_on_top", None)
        and main_window.act_always_on_top.isChecked()
    )


def _set_native_window_topmost(widget: QWidget | None, enabled: bool) -> bool:
    """ネイティブAPIで最前面属性を設定する。"""
    if widget is None or _win_set_window_pos is None or not widget.isWindow():
        return False
    try:
        hwnd = int(widget.winId())
    except Exception:
        return False
    if hwnd <= 0:
        return False
    insert_after = _WIN_HWND_TOPMOST if bool(enabled) else _WIN_HWND_NOTOPMOST
    if insert_after is None:
        return False
    try:
        return bool(
            _win_set_window_pos(
                hwnd,
                insert_after,
                0,
                0,
                0,
                0,
                _WIN_TOPMOST_FLAGS,
            )
        )
    except Exception:
        return False


def _native_topmost_state_matches(widget: QWidget | None, desired: bool) -> bool:
    """直近で同一状態を同一HWNDへ適用済みか判定する。"""
    if widget is None:
        return False
    try:
        hwnd = int(widget.winId())
    except Exception:
        return False
    if hwnd <= 0:
        return False
    cached_state = getattr(widget, "_native_topmost_applied_state", None)
    cached_hwnd = int(getattr(widget, "_native_topmost_applied_hwnd", 0))
    return (
        (cached_state is not None) and bool(cached_state) == bool(desired) and cached_hwnd == hwnd
    )


def _set_native_window_topmost_if_needed(
    widget: QWidget | None,
    enabled: bool,
    *,
    force: bool = False,
) -> bool:
    """必要な場合のみネイティブ最前面APIを呼び出す。"""
    if widget is None or not widget.isWindow() or not widget.isVisible():
        return False
    desired = bool(enabled)
    if (not force) and _native_topmost_state_matches(widget, desired):
        write_window_layout_debug_log(
            "topmost_native_skip_cached",
            widget=_widget_debug_name(widget),
            desired=bool(desired),
        )
        return True
    ok = _set_native_window_topmost(widget, desired)
    if ok:
        try:
            widget._native_topmost_applied_state = desired
            widget._native_topmost_applied_hwnd = int(widget.winId())
        except Exception:
            pass
    write_window_layout_debug_log(
        "topmost_native_apply",
        widget=_widget_debug_name(widget),
        desired=bool(desired),
        force=bool(force),
        ok=bool(ok),
    )
    return ok


def _iter_top_level_targets_for_topmost(main_window):
    """最前面同期対象となるトップレベルウィジェットを列挙する。"""
    yield main_window
    preview = getattr(main_window, "preview_window", None)
    if isinstance(preview, QWidget):
        yield preview
    settings = getattr(main_window, "_settings_window", None)
    if isinstance(settings, QWidget):
        yield settings
    for dock in getattr(main_window, "_dock_map", {}).values():
        if isinstance(dock, QDockWidget) and dock.isFloating():
            yield dock


def _refresh_native_topmost_windows(main_window) -> None:
    """可視中ウィンドウへネイティブ最前面属性を再適用する。"""
    if not is_always_on_top_enabled(main_window):
        return
    seen = set()
    for widget in _iter_top_level_targets_for_topmost(main_window):
        if widget is None:
            continue
        key = id(widget)
        if key in seen:
            continue
        seen.add(key)
        if widget.isVisible():
            _set_native_window_topmost_if_needed(widget, True, force=True)


def schedule_widget_on_top_refresh(
    main_window,
    widget: QWidget | None,
    *,
    delay_ms: int = 0,
) -> None:
    """次イベントループ以降に対象ウィジェットの最前面状態を再同期する。"""
    if widget is None:
        return
    seq = int(getattr(widget, "_on_top_refresh_seq", 0)) + 1
    widget._on_top_refresh_seq = seq

    def _apply(expected_seq: int = seq) -> None:
        if widget is None:
            return
        if int(getattr(widget, "_on_top_refresh_seq", 0)) != int(expected_seq):
            return
        try:
            desired = is_always_on_top_enabled(main_window)
            if isinstance(widget, QDockWidget):
                desired = desired and widget.isFloating()
            set_widget_on_top(main_window, widget, desired)
        except RuntimeError:
            return

    QTimer.singleShot(max(0, int(delay_ms)), _apply)


def schedule_dock_on_top_refresh(
    main_window, dock: QDockWidget | None, *, delay_ms: int = 0
) -> None:
    """次イベントループ以降にフローティングドックの最前面状態を再同期する。"""
    if dock is None:
        return
    schedule_widget_on_top_refresh(main_window, dock, delay_ms=delay_ms)


def _read_on_top_flag_state(widget: QWidget) -> tuple[bool, bool, object]:
    """ウィジェット本体と windowHandle の最前面フラグ状態を返す。"""
    widget_flag = bool(widget.windowFlags() & Qt.WindowStaysOnTopHint)
    win = safe_window_handle(widget)
    window_flag = bool(win.flags() & Qt.WindowStaysOnTopHint) if win is not None else widget_flag
    return widget_flag, window_flag, win


def _apply_qt_on_top_flags(
    widget: QWidget,
    *,
    desired: bool,
    widget_flag: bool,
    window_flag: bool,
    win,
) -> None:
    """Qt 側の最前面フラグ差分だけを適用する。"""
    if widget_flag != desired:
        widget.setWindowFlag(Qt.WindowStaysOnTopHint, desired)
    if win is not None and window_flag != desired:
        try:
            win.setFlag(Qt.WindowStaysOnTopHint, desired)
        except Exception:
            pass


def _restore_visibility_after_flag_change(
    widget: QWidget,
    *,
    desired: bool,
    was_active: bool,
    saved_geometry: QRect,
) -> None:
    """WindowFlag 切替後の表示状態を復元する。"""
    widget.show()
    if (
        widget.isWindow()
        and saved_geometry.isValid()
        and widget.geometry() != saved_geometry
        and not isinstance(widget, QDockWidget)
    ):
        widget.setGeometry(saved_geometry)
    if HAS_WIN32 and widget.isWindow():
        _set_native_window_topmost_if_needed(widget, desired, force=True)
    if desired or was_active:
        widget.raise_()
    if was_active:
        widget.activateWindow()


def set_widget_on_top(_main_window, widget: QWidget | None, enabled: bool) -> None:
    """指定ウィジェットへ最前面属性を適用する。"""
    if widget is None:
        return
    desired = bool(enabled)
    if HAS_WIN32 and widget.isWindow() and widget.isVisible():
        # Windows では WindowFlag 切替で一瞬非表示になるため、可視トップレベルは
        # ネイティブ API のみで最前面状態を切り替える。
        _set_native_window_topmost_if_needed(widget, desired, force=False)
        return
    widget_flag, window_flag, win = _read_on_top_flag_state(widget)
    if widget_flag == desired and window_flag == desired:
        if HAS_WIN32 and widget.isWindow() and widget.isVisible():
            _set_native_window_topmost_if_needed(widget, desired, force=False)
        return
    was_visible = widget.isVisible()
    was_active = bool(widget.isActiveWindow())
    saved_geometry = QRect(widget.geometry()) if widget.isWindow() else QRect()
    _apply_qt_on_top_flags(
        widget,
        desired=desired,
        widget_flag=bool(widget_flag),
        window_flag=bool(window_flag),
        win=win,
    )
    if was_visible:
        _restore_visibility_after_flag_change(
            widget,
            desired=desired,
            was_active=bool(was_active),
            saved_geometry=saved_geometry,
        )


def sync_dock_on_top(main_window, dock: QDockWidget):
    """フローティングドックに最前面状態を反映する。"""
    if dock is None:
        return
    set_widget_on_top(
        main_window,
        dock,
        is_always_on_top_enabled(main_window) and dock.isFloating(),
    )


def sync_all_on_top_widgets(main_window):
    """全対象ウィンドウへ最前面状態を反映する。"""
    enabled = is_always_on_top_enabled(main_window)
    set_widget_on_top(main_window, main_window, enabled)
    if hasattr(main_window, "preview_window"):
        set_widget_on_top(main_window, main_window.preview_window, enabled)
    if hasattr(main_window, "_settings_window") and main_window._settings_window is not None:
        set_widget_on_top(main_window, main_window._settings_window, enabled)
    for dock in getattr(main_window, "_dock_map", {}).values():
        sync_dock_on_top(main_window, dock)


def refresh_topmost_if_enabled(main_window) -> None:
    """最前面有効時のみネイティブ最前面状態を再同期する。"""
    if not is_always_on_top_enabled(main_window):
        return
    _refresh_native_topmost_windows(main_window)


def _sync_on_top_widgets_after_toggle(main_window, *, desired: bool) -> None:
    """最前面切替後の全ウィンドウ状態を同期する。"""
    sync_all_on_top_widgets(main_window)
    if bool(desired):
        _refresh_native_topmost_windows(main_window)


def apply_always_on_top(main_window, checked: bool, save: bool = True):
    """常に最前面設定を切り替え、必要なら保存する。"""
    desired = bool(checked)
    current = is_always_on_top_enabled(main_window)
    write_window_layout_debug_log(
        "topmost_toggle_requested",
        desired=bool(desired),
        current=bool(current),
        save=bool(save),
    )
    if desired == current:
        _sync_on_top_widgets_after_toggle(main_window, desired=desired)
        if save:
            main_window._request_save_settings()
        return

    with blocked_signals(main_window.act_always_on_top):
        main_window.act_always_on_top.setChecked(desired)
    if hasattr(main_window, "_dock_rebalance_timer"):
        main_window._dock_rebalance_timer.stop()
    _sync_on_top_widgets_after_toggle(main_window, desired=desired)
    main_window._dock_geometry_snapshot = {}
    main_window._dock_rebalance_last_main_size = main_window.size()
    if save:
        main_window._request_save_settings()


def present_settings_window(main_window, center_on_parent: bool = False):
    """設定ウィンドウを補正付きで前面表示する。"""
    if not hasattr(main_window, "_settings_window"):
        return
    win = main_window._settings_window
    set_widget_on_top(main_window, win, is_always_on_top_enabled(main_window))
    main_window._fit_dialog_to_desktop(win, center_on_parent=center_on_parent)
    if win.windowState() & Qt.WindowMinimized:
        win.setWindowState((win.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        win.showNormal()
    win.show()
    win.raise_()
    win.activateWindow()
