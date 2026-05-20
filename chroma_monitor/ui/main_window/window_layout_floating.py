"""フローティングドックの移動補助と最小限の状態同期。"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDockWidget

from .window_layout_geometry import fit_top_level_widget_to_desktop
from .window_topmost import schedule_dock_on_top_refresh, sync_dock_on_top


def debug_log_floating_dock_event(
    main_window,
    dock: QDockWidget | None,
    event: str,
    *,
    throttle_sec: float = 0.0,
    **fields,
) -> None:
    """互換用の空実装。"""
    _ = main_window, dock, event, throttle_sec, fields


def _schedule_force_restore_dock_snapshot(main_window, dock: QDockWidget) -> None:
    """跨ぎ補正後にドック内容を強制再描画して表示崩れを解消する。"""
    if dock is None or not dock.isFloating() or not dock.isVisible():
        return
    restore = getattr(main_window, "_restore_dock_from_snapshot", None)
    if not callable(restore):
        return
    for delay in (0, 70, 160):
        QTimer.singleShot(
            int(delay),
            lambda d=dock, fn=restore: fn(d, force=True),
        )


def notify_floating_dock_moved(main_window, dock: QDockWidget) -> None:
    """フローティングドックの移動通知を受け取る。"""
    _ = main_window, dock


def restore_floating_dock_size_on_screen_change(
    main_window,
    dock: QDockWidget,
    *,
    clear_pending: bool = True,
) -> None:
    """フローティングドックを利用可能領域内へ収め直す。"""
    if dock is None:
        return
    _ = clear_pending
    if not dock.isFloating() or not dock.isVisible():
        return
    if dock.windowState() & Qt.WindowMinimized:
        return

    fit_top_level_widget_to_desktop(
        main_window,
        dock,
        allow_resize=False,
    )
    sync_dock_on_top(main_window, dock)
    schedule_dock_on_top_refresh(main_window, dock, delay_ms=0)
    schedule_dock_on_top_refresh(main_window, dock, delay_ms=140)
    _schedule_force_restore_dock_snapshot(main_window, dock)


def _is_left_mouse_dragging() -> bool:
    """左ボタン押下ドラッグ中か判定する。"""
    app = QApplication.instance()
    return bool(app is not None and app.mouseButtons() & Qt.LeftButton)


def clear_floating_move_drag_state(
    main_window,
    dock: QDockWidget,
    *,
    reason: str,
) -> None:
    """移動/リサイズのドラッグ状態をクリアする。"""
    _ = main_window, reason
    if dock is None:
        return
    dock._floating_move_drag_active = False
    dock._floating_resize_drag_active = False


def clear_floating_runtime_state(
    main_window,
    dock: QDockWidget | None,
    *,
    reason: str,
) -> None:
    """フローティング補助状態を安全に初期化する。"""
    if dock is None:
        return
    clear_floating_move_drag_state(main_window, dock, reason=str(reason))


def update_floating_move_drag_state(
    main_window,
    dock: QDockWidget,
    *,
    from_move: bool,
    left_dragging: bool,
) -> None:
    """ドラッグ種別(移動/リサイズ)に応じて最小限の状態だけ更新する。"""
    _ = main_window
    if dock is None or not dock.isFloating() or not dock.isVisible():
        clear_floating_move_drag_state(main_window, dock, reason="hidden_or_not_floating")
        return
    if not left_dragging:
        clear_floating_move_drag_state(main_window, dock, reason="mouse_release")
        return
    if bool(from_move):
        dock._floating_move_drag_active = True
        dock._floating_resize_drag_active = False
        return
    if not bool(getattr(dock, "_floating_move_drag_active", False)):
        dock._floating_resize_drag_active = True


def ensure_floating_dock_screen_tracking(main_window, dock: QDockWidget) -> None:
    """互換用の空実装。"""
    _ = main_window, dock
