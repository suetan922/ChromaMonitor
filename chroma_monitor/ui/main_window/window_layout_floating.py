"""フローティングドックの移動・サイズ追跡と mixed-DPI 補正。"""

import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QDockWidget

from ...util.debug_log import write_window_layout_debug_log
from ...util.qt_helpers import safe_window_handle
from .window_layout_common import (
    _FLOATING_DEBUG_EVENT_THROTTLE_SEC,
    _FLOATING_MOVE_DRAG_EDGE_MARGIN_PX,
    _FLOATING_MOVE_DRAG_GUARD_RETRY_MS,
    _FLOATING_SCREEN_FIX_RETRY_MS,
    dock_debug_name,
)
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
    """フローティングドック挙動のデバッグログを出力する。"""
    if dock is None:
        write_window_layout_debug_log(event, **fields)
        return

    now = time.monotonic()
    if throttle_sec > 0.0:
        last_map = getattr(dock, "_floating_debug_last_log_ts", None)
        if not isinstance(last_map, dict):
            last_map = {}
        try:
            last = float(last_map.get(event, 0.0))
        except Exception:
            last = 0.0
        if (now - last) < float(throttle_sec):
            return
        last_map[event] = now
        dock._floating_debug_last_log_ts = last_map

    try:
        geom = dock.geometry()
        geom_text = f"{int(geom.x())},{int(geom.y())},{int(geom.width())}x{int(geom.height())}"
    except Exception:
        geom_text = "?"
    try:
        frame = dock.frameGeometry()
        frame_text = f"{int(frame.x())},{int(frame.y())},{int(frame.width())}x{int(frame.height())}"
    except Exception:
        frame_text = "?"
    try:
        app = QApplication.instance()
        left_drag = bool(app is not None and app.mouseButtons() & Qt.LeftButton)
    except Exception:
        left_drag = False
    payload = {
        "dock": dock_debug_name(main_window, dock),
        "floating": bool(dock.isFloating()),
        "visible": bool(dock.isVisible()),
        "left_drag": left_drag,
        "geom": geom_text,
        "frame": frame_text,
        "screen_key": _floating_dock_screen_key(main_window, dock),
    }
    payload.update(fields)
    write_window_layout_debug_log(event, **payload)


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
            lambda mw=main_window, d=dock, fn=restore: fn(mw, d, force=True),
        )


def _floating_dock_screen_key(main_window, dock: QDockWidget):
    """フローティングドックが現在属しているスクリーン識別子を返す。"""
    screen = None
    win = safe_window_handle(dock)
    if win is not None:
        try:
            screen = win.screen()
        except Exception:
            screen = None
    if screen is None:
        try:
            screen = dock.screen()
        except Exception:
            screen = None
    if screen is None:
        try:
            screen = QGuiApplication.screenAt(dock.frameGeometry().center())
        except Exception:
            screen = None
    if screen is None:
        try:
            screen = main_window.screen()
        except Exception:
            screen = None
    if screen is None:
        return None
    rect = screen.geometry()
    return (
        str(screen.name()),
        int(rect.x()),
        int(rect.y()),
        int(rect.width()),
        int(rect.height()),
    )


def notify_floating_dock_moved(main_window, dock: QDockWidget) -> None:
    """フローティングドック移動中であることを記録する。"""
    if dock is None or not dock.isFloating():
        return
    debug_log_floating_dock_event(
        main_window,
        dock,
        "notify_floating_move",
        throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
    )


def restore_floating_dock_size_on_screen_change(
    main_window,
    dock: QDockWidget,
    *,
    clear_pending: bool = True,
) -> None:
    """画面移動後のフローティングドック位置と状態を補正する。"""
    if dock is None:
        return
    if clear_pending:
        dock._floating_screen_fix_pending = False
    if not dock.isFloating() or not dock.isVisible():
        return
    if dock.windowState() & Qt.WindowMinimized:
        return

    debug_log_floating_dock_event(
        main_window,
        dock,
        "restore_on_screen_change_begin",
        clear_pending=bool(clear_pending),
        keep_user_size=True,
    )
    fit_top_level_widget_to_desktop(
        main_window,
        dock,
        allow_resize=False,
    )
    sync_dock_on_top(main_window, dock)
    schedule_dock_on_top_refresh(main_window, dock, delay_ms=0)
    schedule_dock_on_top_refresh(main_window, dock, delay_ms=140)
    _schedule_force_restore_dock_snapshot(main_window, dock)
    debug_log_floating_dock_event(
        main_window,
        dock,
        "restore_on_screen_change_done",
    )


def _is_left_mouse_dragging() -> bool:
    """左ボタン押下ドラッグ中か判定する。"""
    app = QApplication.instance()
    return bool(app is not None and app.mouseButtons() & Qt.LeftButton)


def _is_cursor_near_floating_frame_edge(
    dock: QDockWidget,
    *,
    margin_px: int = _FLOATING_MOVE_DRAG_EDGE_MARGIN_PX,
) -> bool:
    """カーソルがフローティング枠の端付近にあるか判定する。"""
    if dock is None or not dock.isFloating():
        return False
    try:
        frame = dock.frameGeometry()
        cursor = QCursor.pos()
    except Exception:
        return False
    if not frame.isValid():
        return False
    margin = int(margin_px)
    expanded = frame.adjusted(-margin, -margin, margin, margin)
    if not expanded.contains(cursor):
        return False
    dist_left = abs(cursor.x() - frame.left())
    dist_right = abs(frame.right() - cursor.x())
    dist_top = abs(cursor.y() - frame.top())
    dist_bottom = abs(frame.bottom() - cursor.y())
    in_vertical_span = (frame.top() - margin) <= cursor.y() <= (frame.bottom() + margin)
    in_horizontal_span = (frame.left() - margin) <= cursor.x() <= (frame.right() + margin)
    near_left = dist_left <= margin and in_vertical_span
    near_right = dist_right <= margin and in_vertical_span
    near_bottom = dist_bottom <= margin and in_horizontal_span
    near_top = dist_top <= margin and in_horizontal_span
    near_top_corner = near_top and (near_left or near_right)
    return bool(near_left or near_right or near_bottom or near_top_corner)


def _ensure_floating_move_drag_guard_timer(main_window, dock: QDockWidget):
    """移動ドラッグ固定の解除監視タイマーを取得する。"""
    timer = getattr(dock, "_floating_move_drag_guard_timer", None)
    if timer is None:
        timer = QTimer(dock)
        timer.setSingleShot(True)
        timer.timeout.connect(
            lambda mw=main_window, d=dock: _on_floating_move_drag_guard_timer(mw, d)
        )
        dock._floating_move_drag_guard_timer = timer
    return timer


def _stop_floating_move_drag_size_guard(
    main_window,
    dock: QDockWidget,
    *,
    reason: str,
) -> None:
    """移動ドラッグ中のサイズ固定を解除する。"""
    if dock is None:
        return
    timer = getattr(dock, "_floating_move_drag_guard_timer", None)
    if timer is not None and timer.isActive():
        timer.stop()
    if not bool(getattr(dock, "_floating_move_drag_active", False)):
        dock._floating_move_drag_size = None
        return

    dock._floating_move_drag_active = False
    dock._floating_move_drag_size = None
    debug_log_floating_dock_event(
        main_window,
        dock,
        "floating_move_drag_guard_stop",
        reason=str(reason),
    )


def _stop_qtimer(timer) -> None:
    """有効な `QTimer` を停止する。"""
    if timer is None:
        return
    try:
        if timer.isActive():
            timer.stop()
    except Exception:
        pass


def clear_floating_runtime_state(
    main_window,
    dock: QDockWidget | None,
    *,
    reason: str,
) -> None:
    """フローティング補助タイマー/状態を安全に初期化する。"""
    if dock is None:
        return
    _stop_qtimer(getattr(dock, "_floating_screen_fix_timer", None))
    _stop_qtimer(getattr(dock, "_floating_move_drag_guard_timer", None))
    dock._floating_screen_fix_pending = False
    clear_floating_move_drag_state(main_window, dock, reason=str(reason))


def clear_floating_move_drag_state(
    main_window,
    dock: QDockWidget,
    *,
    reason: str,
) -> None:
    """移動/リサイズのドラッグ状態をクリアする。"""
    if dock is None:
        return
    dock._floating_resize_drag_active = False
    dock._floating_last_resize_event_ts = 0.0
    _stop_floating_move_drag_size_guard(main_window, dock, reason=str(reason))


def _start_floating_move_drag_size_guard(main_window, dock: QDockWidget) -> None:
    """移動ドラッグ中はサイズを固定して誤リサイズを抑止する。"""
    if dock is None or not dock.isFloating() or not dock.isVisible():
        return
    size = dock.size()
    if size.width() <= 0 or size.height() <= 0:
        return
    if not bool(getattr(dock, "_floating_move_drag_active", False)):
        dock._floating_move_drag_active = True
        dock._floating_move_drag_size = QSize(int(size.width()), int(size.height()))
        debug_log_floating_dock_event(
            main_window,
            dock,
            "floating_move_drag_guard_start",
            ref_w=int(size.width()),
            ref_h=int(size.height()),
        )
    _ensure_floating_move_drag_guard_timer(main_window, dock).start(
        _FLOATING_MOVE_DRAG_GUARD_RETRY_MS
    )


def _on_floating_move_drag_guard_timer(main_window, dock: QDockWidget) -> None:
    """移動ドラッグ固定の解除タイミングを監視する。"""
    if dock is None or not bool(getattr(dock, "_floating_move_drag_active", False)):
        return
    if not dock.isFloating() or not dock.isVisible():
        clear_floating_move_drag_state(main_window, dock, reason="hidden_or_not_floating")
        return
    if _is_left_mouse_dragging():
        _ensure_floating_move_drag_guard_timer(main_window, dock).start(
            _FLOATING_MOVE_DRAG_GUARD_RETRY_MS
        )
        return
    clear_floating_move_drag_state(main_window, dock, reason="mouse_release")


def _enforce_move_drag_reference_size(dock: QDockWidget, *, near_edge: bool) -> None:
    """移動ドラッグ中に誤って変化したサイズを参照サイズへ戻す。"""
    if bool(near_edge):
        return
    ref = getattr(dock, "_floating_move_drag_size", None)
    if not isinstance(ref, QSize) or ref.width() <= 0 or ref.height() <= 0:
        return
    if dock.size() == ref:
        return
    try:
        dock.resize(int(ref.width()), int(ref.height()))
    except Exception:
        return


def _start_resize_drag_for_floating_dock(main_window, dock: QDockWidget) -> None:
    """フローティングドックのリサイズドラッグ開始状態を記録する。"""
    dock._floating_resize_drag_active = True
    _stop_floating_move_drag_size_guard(main_window, dock, reason="resize_drag_start")
    debug_log_floating_dock_event(
        main_window,
        dock,
        "floating_resize_drag_start",
    )


def _recent_resize_event_exists(dock: QDockWidget, now_ts: float, *, window_sec: float) -> bool:
    """直近 `window_sec` 秒以内に resize イベントが記録されているか返す。"""
    last_resize_ts = float(getattr(dock, "_floating_last_resize_event_ts", 0.0) or 0.0)
    return (float(now_ts) - last_resize_ts) <= float(window_sec)


def update_floating_move_drag_state(
    main_window,
    dock: QDockWidget,
    *,
    from_move: bool,
    left_dragging: bool,
) -> None:
    """ドラッグ種別(移動/リサイズ)に応じて固定ガード状態を更新する。"""
    if dock is None or not dock.isFloating() or not dock.isVisible():
        clear_floating_move_drag_state(main_window, dock, reason="hidden_or_not_floating")
        return
    if not left_dragging:
        dock._floating_last_resize_event_ts = 0.0
        clear_floating_move_drag_state(main_window, dock, reason="mouse_release")
        return

    now = float(time.monotonic())
    near_edge = _is_cursor_near_floating_frame_edge(dock)
    resize_active = bool(getattr(dock, "_floating_resize_drag_active", False))
    move_guard_active = bool(getattr(dock, "_floating_move_drag_active", False))

    if not bool(from_move):
        dock._floating_last_resize_event_ts = now
        if move_guard_active:
            _enforce_move_drag_reference_size(dock, near_edge=bool(near_edge))
        if not near_edge and not resize_active:
            return
        if not resize_active:
            _start_resize_drag_for_floating_dock(main_window, dock)
        return

    if resize_active:
        return
    if _recent_resize_event_exists(dock, now, window_sec=0.28):
        return
    _start_floating_move_drag_size_guard(main_window, dock)


def _ensure_floating_screen_fix_timer(main_window, dock: QDockWidget):
    """screenChanged 補正の遅延実行タイマーを取得する。"""
    timer = getattr(dock, "_floating_screen_fix_timer", None)
    if timer is None:
        timer = QTimer(dock)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda mw=main_window, d=dock: _on_floating_screen_fix_timer(mw, d))
        dock._floating_screen_fix_timer = timer
    return timer


def _on_floating_screen_fix_timer(main_window, dock: QDockWidget) -> None:
    """ドラッグ終了待ち後に画面跨ぎ補正を適用する。"""
    if dock is None:
        return
    if not dock.isFloating() or not dock.isVisible():
        dock._floating_screen_fix_pending = False
        return
    if _is_left_mouse_dragging():
        debug_log_floating_dock_event(
            main_window,
            dock,
            "screen_fix_timer_retry_dragging",
            throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        )
        _ensure_floating_screen_fix_timer(main_window, dock).start(_FLOATING_SCREEN_FIX_RETRY_MS)
        return
    debug_log_floating_dock_event(
        main_window,
        dock,
        "screen_fix_timer_apply",
        throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
    )
    restore_floating_dock_size_on_screen_change(main_window, dock, clear_pending=True)


def _schedule_floating_dock_screen_fix(main_window, dock: QDockWidget) -> None:
    """フローティングドック画面移動補正を次イベントループで予約する。"""
    if dock is None or not dock.isFloating():
        return
    pending = bool(getattr(dock, "_floating_screen_fix_pending", False))
    left_dragging = _is_left_mouse_dragging()
    timer = _ensure_floating_screen_fix_timer(main_window, dock)

    if pending:
        if left_dragging:
            if not timer.isActive():
                timer.start(_FLOATING_SCREEN_FIX_RETRY_MS)
            debug_log_floating_dock_event(
                main_window,
                dock,
                "schedule_screen_fix_skip_pending_dragging",
                throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
            )
            return
        debug_log_floating_dock_event(
            main_window,
            dock,
            "schedule_screen_fix_flush_pending",
            throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        )
        restore_floating_dock_size_on_screen_change(main_window, dock, clear_pending=True)
        return

    dock._floating_screen_fix_pending = True
    if left_dragging:
        timer.start(_FLOATING_SCREEN_FIX_RETRY_MS)
        debug_log_floating_dock_event(
            main_window,
            dock,
            "schedule_screen_fix_deferred_dragging",
            retry_ms=int(_FLOATING_SCREEN_FIX_RETRY_MS),
        )
        return
    debug_log_floating_dock_event(
        main_window,
        dock,
        "schedule_screen_fix_now",
    )
    if timer.isActive():
        timer.stop()
    QTimer.singleShot(
        0,
        lambda mw=main_window, d=dock: restore_floating_dock_size_on_screen_change(mw, d),
    )


def ensure_floating_dock_screen_tracking(main_window, dock: QDockWidget) -> None:
    """フローティングドックの screenChanged 監視を現在ハンドルへ接続する。"""
    if dock is None:
        return
    win = safe_window_handle(dock)
    if win is None:
        return
    tracked_handle = getattr(dock, "_floating_screen_tracking_handle", None)
    if bool(getattr(dock, "_floating_screen_tracking_connected", False)) and tracked_handle is win:
        return

    prev_handle = tracked_handle
    prev_slot = getattr(dock, "_floating_screen_changed_slot", None)
    if prev_handle is not None and prev_slot is not None and prev_handle is not win:
        try:
            prev_handle.screenChanged.disconnect(prev_slot)
        except Exception:
            pass

    def _on_screen_changed(_screen, mw=main_window, d=dock):
        debug_log_floating_dock_event(
            mw,
            d,
            "screen_changed",
        )
        left_dragging = _is_left_mouse_dragging()
        move_drag_active = bool(getattr(d, "_floating_move_drag_active", False))
        resize_drag_active = bool(getattr(d, "_floating_resize_drag_active", False))
        if resize_drag_active:
            debug_log_floating_dock_event(
                mw,
                d,
                "screen_changed_skip_resize_drag",
                throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
            )
            return
        if not left_dragging and not move_drag_active:
            debug_log_floating_dock_event(
                mw,
                d,
                "screen_changed_skip_non_drag",
                throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
            )
            return
        _schedule_floating_dock_screen_fix(mw, d)

    try:
        win.screenChanged.connect(_on_screen_changed)
    except Exception:
        return
    dock._floating_screen_tracking_connected = True
    dock._floating_screen_tracking_handle = win
    dock._floating_screen_changed_slot = _on_screen_changed
