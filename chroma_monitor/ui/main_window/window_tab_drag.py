"""ドックタブの drag/detach 補助。"""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QTabBar

from .window_tab_sync import dock_for_tab_text, sync_tabbed_dock_title_bars

_TAB_DETACH_VERTICAL_DRAG_PX = 22
_TAB_DETACH_FORCE_DOCK_DROP_MS = 2800


def _sync_layout_dock_options(main_window) -> None:
    """レイアウト側のドックオプション同期を安全に呼び出す。"""
    sync = getattr(main_window, "_sync_all_floating_dock_dockability", None)
    if callable(sync):
        sync()


def _set_force_dock_drop_active(main_window, active: bool) -> None:
    """タブ切り離し直後のドックドロップ判定強制有効状態を更新する。"""
    enabled = bool(active)
    main_window._force_dock_drop_active = enabled

    timer = getattr(main_window, "_force_dock_drop_timer", None)
    if timer is None:
        timer = QTimer(main_window)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda mw=main_window: _set_force_dock_drop_active(mw, False))
        main_window._force_dock_drop_timer = timer

    if enabled:
        timer.start(_TAB_DETACH_FORCE_DOCK_DROP_MS)
    else:
        timer.stop()
    _sync_layout_dock_options(main_window)


def clear_force_dock_drop_active(main_window) -> None:
    """強制ドックドロップ有効状態を解除する。"""
    if bool(getattr(main_window, "_force_dock_drop_active", False)):
        _set_force_dock_drop_active(main_window, False)


def _global_pos_from_event(event):
    """イベントからグローバル座標を取得する。"""
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    if hasattr(event, "globalPos"):
        return event.globalPos()
    return None


def _event_pos(event):
    """イベントからローカル座標を取得する。"""
    if hasattr(event, "position"):
        return event.position().toPoint()
    if hasattr(event, "pos"):
        return event.pos()
    return None


def _active_tab_index_for_press(bar: QTabBar, event) -> int:
    """タブ押下イベントから対象タブインデックスを解決する。"""
    pos = _event_pos(event)
    index = bar.tabAt(pos) if pos is not None else -1
    if index < 0:
        index = bar.currentIndex()
    return int(index)


def _set_tab_drag_state(main_window, bar: QTabBar, index: int, event) -> None:
    """タブドラッグ状態を初期化して保存する。"""
    main_window._dock_tab_drag_state = {
        "bar": bar,
        "index": int(index),
        "text": bar.tabText(int(index)),
        "start_global": _global_pos_from_event(event),
        "triggered": False,
    }


def _handle_tab_drag_press(main_window, bar: QTabBar, event) -> bool:
    """タブドラッグの開始状態を処理する。"""
    if getattr(event, "button", lambda: None)() != Qt.LeftButton:
        return False
    index = _active_tab_index_for_press(bar, event)
    if index < 0:
        main_window._dock_tab_drag_state = None
        return False
    _set_tab_drag_state(main_window, bar, index, event)
    return False


def _float_dock_from_tab_drag(main_window, dock: QDockWidget, global_pos) -> None:
    """タブドラッグでドックをフローティング化する。"""
    if dock is None:
        return
    dock.setFloating(True)
    if global_pos is not None:
        frame = dock.frameGeometry()
        x = int(global_pos.x() - min(96, max(24, frame.width() // 2)))
        y = int(global_pos.y() - 12)
        dock.move(x, y)
    dock.raise_()
    dock.activateWindow()
    _sync_layout_dock_options(main_window)
    sync_tabbed_dock_title_bars(main_window)
    if hasattr(main_window, "_schedule_layout_autosave"):
        main_window._schedule_layout_autosave()


def _start_system_move_for_dock(dock: QDockWidget) -> bool:
    """フローティング化したドックにOS標準の移動操作を委譲する。"""
    if dock is None:
        return False
    try:
        window_handle = dock.windowHandle()
    except Exception:
        window_handle = None
    if window_handle is None or not hasattr(window_handle, "startSystemMove"):
        return False
    try:
        return bool(window_handle.startSystemMove())
    except Exception:
        return False


def _detach_dock_if_vertical_drag(main_window, bar: QTabBar, state: dict, event) -> bool:
    """縦方向ドラッグ時のみタブをドックから切り離す。"""
    current = _global_pos_from_event(event)
    start = state.get("start_global")
    if current is None or start is None:
        return False
    dx = int(current.x() - start.x())
    dy = int(current.y() - start.y())
    if abs(dy) < _TAB_DETACH_VERTICAL_DRAG_PX or abs(dy) <= abs(dx):
        return False
    dock = dock_for_tab_text(main_window, str(state.get("text", "")))
    if dock is None:
        return False
    state["triggered"] = True
    _set_force_dock_drop_active(main_window, True)
    _float_dock_from_tab_drag(main_window, dock, current)
    _start_system_move_for_dock(dock)
    main_window._dock_tab_drag_state = None
    return True


def _handle_tab_drag_move(main_window, bar: QTabBar, event) -> bool:
    """タブドラッグ中の切り離し判定を処理する。"""
    state = getattr(main_window, "_dock_tab_drag_state", None)
    if not isinstance(state, dict):
        return False
    if state.get("bar") is not bar:
        return False
    if state.get("triggered"):
        return False
    return _detach_dock_if_vertical_drag(main_window, bar, state, event)


def _handle_tab_drag_end(main_window, event_type) -> bool:
    """タブドラッグ終了時の状態リセットを処理する。"""
    state = getattr(main_window, "_dock_tab_drag_state", None)
    if isinstance(state, dict) and not state.get("triggered"):
        main_window._dock_tab_drag_state = None
    if event_type == QEvent.MouseButtonRelease:
        clear_force_dock_drop_active(main_window)
    return False


def handle_dock_tab_bar_event(main_window, bar: QTabBar, event) -> bool:
    """ドックタブバーイベントを監視する。"""
    event_type = event.type()
    if event_type == QEvent.MouseButtonPress:
        return _handle_tab_drag_press(main_window, bar, event)
    if event_type == QEvent.MouseMove:
        return _handle_tab_drag_move(main_window, bar, event)
    if event_type in (QEvent.MouseButtonRelease, QEvent.Leave):
        return _handle_tab_drag_end(main_window, event_type)
    return False
