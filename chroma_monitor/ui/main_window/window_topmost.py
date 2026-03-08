"""最前面表示と設定ウィンドウ前面化の補助処理。"""

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QWidget

from ...capture.win32_windows import HAS_WIN32
from ...util.qt_helpers import blocked_signals

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


def _dock_window_handle(dock: QDockWidget):
    """ドックに対応する windowHandle を安全に取得する。"""
    try:
        return dock.windowHandle()
    except Exception:
        return None


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
            _set_native_window_topmost(widget, True)


def schedule_widget_on_top_refresh(
    main_window,
    widget: QWidget | None,
    *,
    delay_ms: int = 0,
) -> None:
    """次イベントループ以降に対象ウィジェットの最前面状態を再同期する。"""
    if widget is None:
        return

    def _apply() -> None:
        if widget is None:
            return
        try:
            desired = is_always_on_top_enabled(main_window)
            if isinstance(widget, QDockWidget):
                desired = desired and widget.isFloating()
            set_widget_on_top(main_window, widget, desired)
        except RuntimeError:
            return

    QTimer.singleShot(max(0, int(delay_ms)), _apply)


def schedule_dock_on_top_refresh(main_window, dock: QDockWidget | None, *, delay_ms: int = 0) -> None:
    """次イベントループ以降にフローティングドックの最前面状態を再同期する。"""
    if dock is None:
        return
    schedule_widget_on_top_refresh(main_window, dock, delay_ms=delay_ms)


def set_widget_on_top(_main_window, widget: QWidget | None, enabled: bool) -> None:
    """指定ウィジェットへ最前面属性を適用する。"""
    if widget is None:
        return
    desired = bool(enabled)
    if HAS_WIN32 and isinstance(widget, QDockWidget) and widget.isFloating():
        # フローティングドックで Qt の WindowFlag を頻繁に切り替えると、
        # 混在DPI環境でサイズ再計算ループが起きやすいため native API を優先する。
        if widget.isWindow() and widget.isVisible():
            _set_native_window_topmost(widget, desired)
            return
    current_widget_flag = bool(widget.windowFlags() & Qt.WindowStaysOnTopHint)
    win = _dock_window_handle(widget) if isinstance(widget, QDockWidget) else widget.windowHandle()
    current_window_flag = (
        bool(win.flags() & Qt.WindowStaysOnTopHint) if win is not None else current_widget_flag
    )
    if current_widget_flag == desired and current_window_flag == desired:
        if HAS_WIN32 and widget.isWindow() and widget.isVisible():
            _set_native_window_topmost(widget, desired)
        return
    was_visible = widget.isVisible()
    was_active = bool(widget.isActiveWindow())
    saved_geometry = QRect(widget.geometry()) if widget.isWindow() else QRect()
    if current_widget_flag != desired:
        widget.setWindowFlag(Qt.WindowStaysOnTopHint, desired)
    if win is not None and current_window_flag != desired:
        try:
            win.setFlag(Qt.WindowStaysOnTopHint, desired)
        except Exception:
            pass
    if was_visible:
        widget.show()
        if (
            widget.isWindow()
            and saved_geometry.isValid()
            and widget.geometry() != saved_geometry
            and not isinstance(widget, QDockWidget)
        ):
            widget.setGeometry(saved_geometry)
        if HAS_WIN32 and widget.isWindow():
            _set_native_window_topmost(widget, desired)
        if desired or was_active:
            widget.raise_()
        if was_active:
            widget.activateWindow()


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


def apply_always_on_top(main_window, checked: bool, save: bool = True):
    """常に最前面設定を切り替え、必要なら保存する。"""
    desired = bool(checked)
    current = is_always_on_top_enabled(main_window)
    if desired == current:
        sync_all_on_top_widgets(main_window)
        if desired:
            _refresh_native_topmost_windows(main_window)
        if save:
            main_window._request_save_settings()
        return

    with blocked_signals(main_window.act_always_on_top):
        main_window.act_always_on_top.setChecked(desired)
    if hasattr(main_window, "_dock_rebalance_timer"):
        main_window._dock_rebalance_timer.stop()
    sync_all_on_top_widgets(main_window)
    if desired:
        _refresh_native_topmost_windows(main_window)
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
