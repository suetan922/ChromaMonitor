"""ウィンドウ配置とドッキング挙動の補助処理。"""

import time

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QMainWindow,
    QSizePolicy,
    QToolBar,
    QWidget,
)

from ...util.debug_log import write_window_layout_debug_log
from ...util.qt_helpers import (
    blocked_signals,
    safe_window_handle,
    screen_union_geometry,
)
from .window_tabs import clear_force_dock_drop_active, sync_tabbed_dock_title_bars
from .window_topmost import (
    refresh_topmost_if_enabled,
    schedule_dock_on_top_refresh,
    sync_dock_on_top,
)

_REBALANCE_COLUMN_X_TOLERANCE_PX = 3
_REBALANCE_COLUMN_W_TOLERANCE_PX = 3
_REBALANCE_HEIGHT_CHANGE_THRESHOLD_PX = 2
_REBALANCE_CHAIN_TOUCH_TOLERANCE_PX = 2
_MAIN_WINDOW_FIT_MARGIN_PX = 0
_MAIN_WINDOW_MIN_W = 480
_MAIN_WINDOW_MIN_H = 360
_MAIN_WINDOW_COMPACT_MIN_W_FLOOR = 220
_MAIN_WINDOW_COMPACT_MIN_H_FLOOR = 1
_MAIN_WINDOW_MAX_W_FLOOR = 640
_MAIN_WINDOW_MAX_H_FLOOR = 420
_PLACEHOLDER_SHOW_MIN_W = 280
_PLACEHOLDER_SHOW_MIN_H = 90
_DIALOG_FIT_MARGIN_PX = 8
_DIALOG_MIN_W = 420
_DIALOG_MIN_H = 320
_TOPLEVEL_FIT_MARGIN_PX = 0
_TOPLEVEL_MIN_W = 160
_TOPLEVEL_MIN_H = 120
_TOPLEVEL_MAX_W_FLOOR = 240
_TOPLEVEL_MAX_H_FLOOR = 180
_DOCK_OPTIONS_BASE = QMainWindow.AnimatedDocks | QMainWindow.AllowTabbedDocks
_DOCK_OPTIONS_NESTED = _DOCK_OPTIONS_BASE | QMainWindow.AllowNestedDocks
_DOCK_DROP_ACTIVATION_MARGIN_RATIO = 0.16
_DOCK_DROP_ACTIVATION_MARGIN_MIN_PX = 96
_DOCK_DROP_ACTIVATION_MARGIN_MAX_PX = 360
_FLOATING_SCREEN_FIX_RETRY_MS = 120
_FLOATING_SIZE_REMEMBER_RETRY_MS = 120
_FLOATING_DEBUG_EVENT_THROTTLE_SEC = 0.06
_FLOATING_MOVE_DRAG_EDGE_MARGIN_PX = 12
_FLOATING_MOVE_DRAG_GUARD_RETRY_MS = 120
_DOCKABILITY_SYNC_DEBOUNCE_MS = 56


def _dock_debug_name(main_window, dock: QDockWidget) -> str:
    """デバッグログ向けドック識別子を返す。"""
    for name, mapped in getattr(main_window, "_dock_map", {}).items():
        if mapped is dock:
            return str(name)
    try:
        obj_name = str(dock.objectName())
    except Exception:
        obj_name = ""
    if obj_name:
        return obj_name
    return f"dock@{id(dock):x}"


def _debug_log_floating_dock_event(
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
        "dock": _dock_debug_name(main_window, dock),
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

    # screenChanged 直後はジオメトリ確定が遅れる場合があるため複数回試行する。
    for delay in (0, 70, 160):
        QTimer.singleShot(
            int(delay),
            lambda d=dock, fn=restore: fn(d, force=True),
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
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "notify_floating_move",
        throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
    )


def _remember_floating_dock_size(
    main_window,
    dock: QDockWidget,
    *,
    force: bool = False,
) -> None:
    """フローティングドックの現在サイズを記録する。"""
    if dock is None or not dock.isFloating():
        return
    if bool(getattr(dock, "_floating_size_restore_lock", False)):
        return
    size = dock.size()
    if size.width() <= 0 or size.height() <= 0:
        return
    remembered_w = max(int(dock.minimumWidth()), int(size.width()))
    remembered_h = max(int(dock.minimumHeight()), int(size.height()))
    dock._floating_logical_size = QSize(int(remembered_w), int(remembered_h))
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "remember_floating_size",
        throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        force=bool(force),
        remembered_w=int(remembered_w),
        remembered_h=int(remembered_h),
    )


def _restore_floating_dock_size_on_screen_change(
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

    _debug_log_floating_dock_event(
        main_window,
        dock,
        "restore_on_screen_change_begin",
        clear_pending=bool(clear_pending),
        keep_user_size=True,
    )
    dock._floating_size_restore_lock = True
    try:
        # mixed-DPI 画面跨ぎ時でも、ユーザーが設定した幅/高さは変更しない。
        fit_top_level_widget_to_desktop(
            main_window,
            dock,
            allow_resize=False,
        )
        sync_dock_on_top(main_window, dock)
        schedule_dock_on_top_refresh(main_window, dock, delay_ms=0)
        schedule_dock_on_top_refresh(main_window, dock, delay_ms=140)
        _schedule_force_restore_dock_snapshot(main_window, dock)
        _debug_log_floating_dock_event(
            main_window,
            dock,
            "restore_on_screen_change_done",
        )
    finally:
        dock._floating_size_restore_lock = False


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
    # 上辺中央はタイトルバー移動と重なるため、上辺は角のみリサイズ判定とする。
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
        dock._floating_move_drag_last_ts = 0.0
        return

    dock._floating_move_drag_active = False
    dock._floating_move_drag_size = None
    dock._floating_move_drag_last_ts = 0.0
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "floating_move_drag_guard_stop",
        reason=str(reason),
    )


def _stop_qtimer(timer) -> None:
    """有効な QTimer を停止する。"""
    if timer is None:
        return
    try:
        if timer.isActive():
            timer.stop()
    except Exception:
        pass


def _clear_floating_runtime_state(
    main_window,
    dock: QDockWidget | None,
    *,
    reason: str,
) -> None:
    """フローティング補助タイマー/状態を安全に初期化する。"""
    if dock is None:
        return
    _stop_qtimer(getattr(dock, "_floating_screen_fix_timer", None))
    _stop_qtimer(getattr(dock, "_floating_size_remember_timer", None))
    _stop_qtimer(getattr(dock, "_floating_move_drag_guard_timer", None))
    dock._floating_screen_fix_pending = False
    _clear_floating_move_drag_state(main_window, dock, reason=str(reason))


def _clear_floating_move_drag_state(
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
        _debug_log_floating_dock_event(
            main_window,
            dock,
            "floating_move_drag_guard_start",
            ref_w=int(size.width()),
            ref_h=int(size.height()),
        )
    dock._floating_move_drag_last_ts = float(time.monotonic())
    _ensure_floating_move_drag_guard_timer(main_window, dock).start(
        _FLOATING_MOVE_DRAG_GUARD_RETRY_MS
    )


def _on_floating_move_drag_guard_timer(main_window, dock: QDockWidget) -> None:
    """移動ドラッグ固定の解除タイミングを監視する。"""
    if dock is None:
        return
    if not bool(getattr(dock, "_floating_move_drag_active", False)):
        return
    if not dock.isFloating() or not dock.isVisible():
        _clear_floating_move_drag_state(main_window, dock, reason="hidden_or_not_floating")
        return
    if _is_left_mouse_dragging():
        _ensure_floating_move_drag_guard_timer(main_window, dock).start(
            _FLOATING_MOVE_DRAG_GUARD_RETRY_MS
        )
        return
    _clear_floating_move_drag_state(main_window, dock, reason="mouse_release")


def _enforce_move_drag_reference_size(dock: QDockWidget, *, near_edge: bool) -> None:
    """移動ドラッグ中に誤って変化したサイズを参照サイズへ戻す。"""
    if bool(near_edge):
        return
    ref = getattr(dock, "_floating_move_drag_size", None)
    if not isinstance(ref, QSize) or ref.width() <= 0 or ref.height() <= 0:
        return
    cur = dock.size()
    if cur == ref:
        return
    try:
        dock.resize(int(ref.width()), int(ref.height()))
    except Exception:
        return


def _start_resize_drag_for_floating_dock(main_window, dock: QDockWidget) -> None:
    """フローティングドックのリサイズドラッグ開始状態を記録する。"""
    dock._floating_resize_drag_active = True
    _stop_floating_move_drag_size_guard(main_window, dock, reason="resize_drag_start")
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "floating_resize_drag_start",
    )


def _recent_resize_event_exists(dock: QDockWidget, now_ts: float, *, window_sec: float) -> bool:
    """直近 window_sec 秒以内に resize イベントが記録されているか返す。"""
    last_resize_ts = float(getattr(dock, "_floating_last_resize_event_ts", 0.0) or 0.0)
    return (float(now_ts) - last_resize_ts) <= float(window_sec)


def _update_floating_move_drag_state(
    main_window,
    dock: QDockWidget,
    *,
    from_move: bool,
    left_dragging: bool,
    screen_fix_pending: bool,
) -> None:
    """ドラッグ種別(移動/リサイズ)に応じて固定ガード状態を更新する。"""
    if dock is None or not dock.isFloating() or not dock.isVisible():
        _clear_floating_move_drag_state(main_window, dock, reason="hidden_or_not_floating")
        return
    if not left_dragging:
        dock._floating_last_resize_event_ts = 0.0
        _clear_floating_move_drag_state(main_window, dock, reason="mouse_release")
        return

    now = float(time.monotonic())
    near_edge = _is_cursor_near_floating_frame_edge(dock)
    resize_active = bool(getattr(dock, "_floating_resize_drag_active", False))
    move_guard_active = bool(getattr(dock, "_floating_move_drag_active", False))

    if not bool(from_move):
        dock._floating_last_resize_event_ts = now
        if move_guard_active:
            _enforce_move_drag_reference_size(dock, near_edge=bool(near_edge))
        # エッジ外で発生した Resize は mixed-DPI 跨ぎ由来の揺れとして扱い、
        # 移動ドラッグを維持する。
        if not near_edge and not resize_active:
            return
        if not resize_active:
            _start_resize_drag_for_floating_dock(main_window, dock)
        return

    # 一度リサイズに入ったドラッグは、ボタンを離すまで移動扱いへ戻さない。
    if resize_active:
        return
    # 直近で Resize が来ている間は、移動ガードへ切り替えない。
    if _recent_resize_event_exists(dock, now, window_sec=0.28):
        return
    _start_floating_move_drag_size_guard(main_window, dock)


def _ensure_floating_size_remember_timer(main_window, dock: QDockWidget):
    """サイズ記録の遅延実行タイマーを取得する。"""
    timer = getattr(dock, "_floating_size_remember_timer", None)
    if timer is None:
        timer = QTimer(dock)
        timer.setSingleShot(True)
        timer.timeout.connect(
            lambda mw=main_window, d=dock: _on_floating_size_remember_timer(mw, d)
        )
        dock._floating_size_remember_timer = timer
    return timer


def _schedule_floating_dock_size_remember(
    main_window,
    dock: QDockWidget,
    *,
    reason: str,
) -> None:
    """フローティングドックのサイズ記録を安定後に予約する。"""
    if dock is None or not dock.isFloating() or not dock.isVisible():
        return
    _ensure_floating_size_remember_timer(main_window, dock).start(_FLOATING_SIZE_REMEMBER_RETRY_MS)
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "schedule_floating_size_remember",
        throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        reason=str(reason),
        retry_ms=int(_FLOATING_SIZE_REMEMBER_RETRY_MS),
    )


def _on_floating_size_remember_timer(main_window, dock: QDockWidget) -> None:
    """ドラッグ/補正が落ち着いたタイミングでサイズ記録を確定する。"""
    if dock is None:
        return
    if not dock.isFloating() or not dock.isVisible():
        return
    if _is_left_mouse_dragging() or bool(getattr(dock, "_floating_screen_fix_pending", False)):
        _debug_log_floating_dock_event(
            main_window,
            dock,
            "floating_size_remember_timer_retry",
            throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        )
        _ensure_floating_size_remember_timer(main_window, dock).start(
            _FLOATING_SIZE_REMEMBER_RETRY_MS
        )
        return
    if bool(getattr(dock, "_floating_size_restore_lock", False)):
        _ensure_floating_size_remember_timer(main_window, dock).start(
            _FLOATING_SIZE_REMEMBER_RETRY_MS
        )
        return
    if bool(getattr(dock, "_floating_move_drag_active", False)):
        _ensure_floating_size_remember_timer(main_window, dock).start(
            _FLOATING_SIZE_REMEMBER_RETRY_MS
        )
        return
    _remember_floating_dock_size(main_window, dock, force=True)


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
        _debug_log_floating_dock_event(
            main_window,
            dock,
            "screen_fix_timer_retry_dragging",
            throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        )
        _ensure_floating_screen_fix_timer(main_window, dock).start(_FLOATING_SCREEN_FIX_RETRY_MS)
        return
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "screen_fix_timer_apply",
        throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
    )
    _restore_floating_dock_size_on_screen_change(main_window, dock, clear_pending=True)


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
            _debug_log_floating_dock_event(
                main_window,
                dock,
                "schedule_screen_fix_skip_pending_dragging",
                throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
            )
            return
        _debug_log_floating_dock_event(
            main_window,
            dock,
            "schedule_screen_fix_flush_pending",
            throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        )
        _restore_floating_dock_size_on_screen_change(main_window, dock, clear_pending=True)
        return

    dock._floating_screen_fix_pending = True
    if left_dragging:
        timer.start(_FLOATING_SCREEN_FIX_RETRY_MS)
        _debug_log_floating_dock_event(
            main_window,
            dock,
            "schedule_screen_fix_deferred_dragging",
            retry_ms=int(_FLOATING_SCREEN_FIX_RETRY_MS),
        )
        return
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "schedule_screen_fix_now",
    )
    if timer.isActive():
        timer.stop()
    QTimer.singleShot(
        0, lambda mw=main_window, d=dock: _restore_floating_dock_size_on_screen_change(mw, d)
    )


def _ensure_floating_dock_screen_tracking(main_window, dock: QDockWidget) -> None:
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
        _debug_log_floating_dock_event(
            mw,
            d,
            "screen_changed",
        )
        left_dragging = _is_left_mouse_dragging()
        move_drag_active = bool(getattr(d, "_floating_move_drag_active", False))
        resize_drag_active = bool(getattr(d, "_floating_resize_drag_active", False))
        if resize_drag_active:
            # リサイズ中は screenChanged 補正を入れない(カーソルずれ/巨大化防止)。
            _debug_log_floating_dock_event(
                mw,
                d,
                "screen_changed_skip_resize_drag",
                throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
            )
            return
        if not left_dragging and not move_drag_active:
            # レイアウト適用/表示復帰などの非ドラッグ遷移では位置補正を行わない。
            _debug_log_floating_dock_event(
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


def _clamp_top_left_in_available(
    avail: QRect,
    frame: QRect,
    margin: int,
    x: int,
    y: int,
) -> tuple[int, int]:
    """矩形が利用可能領域に収まるよう左上座標を丸める。"""
    min_x = avail.left() + margin
    min_y = avail.top() + margin
    max_x = avail.right() - margin - frame.width() + 1
    max_y = avail.bottom() - margin - frame.height() + 1
    if max_x < min_x:
        max_x = min_x
    if max_y < min_y:
        max_y = min_y
    return min(max(int(x), min_x), max_x), min(max(int(y), min_y), max_y)


def update_floating_dock_dockability(
    main_window,
    dock: QDockWidget,
    *,
    sync_options: bool = True,
) -> None:
    """フローティングドックのドッキング許可状態を同期する。"""
    if dock is None:
        return
    # レイアウトは Qt 標準ドッキング挙動を優先する。
    if dock.allowedAreas() != Qt.AllDockWidgetAreas:
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
    if bool(sync_options):
        _sync_dock_options_by_floating_state(main_window)


def _dock_drop_activation_margin_px(main_window) -> int:
    """ドックドロップ判定に使う外周マージン(px)を返す。"""
    frame = main_window.frameGeometry()
    basis = max(1, min(int(frame.width()), int(frame.height())))
    scaled = int(round(float(basis) * _DOCK_DROP_ACTIVATION_MARGIN_RATIO))
    return max(
        _DOCK_DROP_ACTIVATION_MARGIN_MIN_PX,
        min(_DOCK_DROP_ACTIVATION_MARGIN_MAX_PX, scaled),
    )


def _dock_drop_zone_rect(main_window) -> QRect:
    """メインウィンドウ周辺のドロップ有効領域を返す。"""
    margin = _dock_drop_activation_margin_px(main_window)
    return main_window.frameGeometry().adjusted(
        -margin,
        -margin,
        margin,
        margin,
    )


def _floating_dock_intersects_drop_zone(main_window, zone: QRect) -> bool:
    """フローティングドックが指定領域へ接触しているか判定する。"""
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None or not dock.isVisible() or not dock.isFloating():
            continue
        try:
            frame = dock.frameGeometry()
        except Exception:
            continue
        if frame.isValid() and frame.intersects(zone):
            return True
    return False


def _floating_dock_state_flags(main_window) -> tuple[bool, bool]:
    """可視フローティング有無と移動ドラッグ有無を同時に返す。"""
    has_visible_floating = False
    has_active_move_drag = False
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None or not dock.isVisible() or not dock.isFloating():
            continue
        has_visible_floating = True
        if bool(getattr(dock, "_floating_move_drag_active", False)):
            has_active_move_drag = True
            break
    return bool(has_visible_floating), bool(has_active_move_drag)


def _is_dock_drop_active_near_main_window(
    main_window,
    *,
    has_active_drag: bool | None = None,
) -> bool:
    """メイン近傍でドックドラッグが発生中か判定する。"""
    app = QApplication.instance()
    if app is None:
        return False
    if bool(getattr(main_window, "_force_dock_drop_active", False)):
        return True
    if not (app.mouseButtons() & Qt.LeftButton):
        return False
    if not main_window.isVisible():
        return False
    if has_active_drag is None:
        _, has_active_drag = _floating_dock_state_flags(main_window)
    if not bool(has_active_drag):
        return False
    frame = _dock_drop_zone_rect(main_window)
    cursor_pos = QCursor.pos()
    if frame.contains(cursor_pos):
        return True
    return _floating_dock_intersects_drop_zone(main_window, frame)


def _sync_dock_options_by_floating_state(main_window) -> None:
    """ドックオプション(ネスト可否など)を現在状態に合わせて同期する。"""
    # 通常はフローティング中の外部左右上下ドロップを抑制し、中央タブ重ねを優先する。
    # ただしメイン近傍へドラッグ中はネストを一時許可し、上下左右のドロップ判定を広げる。
    has_visible_floating, has_active_drag = _floating_dock_state_flags(main_window)
    allow_nested_while_dragging = _is_dock_drop_active_near_main_window(
        main_window,
        has_active_drag=bool(has_active_drag),
    )
    desired = (
        _DOCK_OPTIONS_NESTED
        if (not has_visible_floating or allow_nested_while_dragging)
        else _DOCK_OPTIONS_BASE
    )
    if main_window.dockOptions() != desired:
        main_window.setDockOptions(desired)


def sync_all_floating_dock_dockability(main_window) -> None:
    """全ドックのフローティング/ドッキング関連設定を再同期する。"""
    for dock in getattr(main_window, "_dock_map", {}).values():
        update_floating_dock_dockability(main_window, dock, sync_options=False)
    _sync_dock_options_by_floating_state(main_window)
    sync_tabbed_dock_title_bars(main_window)


def _ensure_dockability_sync_timer(main_window) -> QTimer:
    """ドッカビリティ同期用デバウンスタイマーを取得する。"""
    timer = getattr(main_window, "_dockability_sync_timer", None)
    if timer is None:
        timer = QTimer(main_window)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda mw=main_window: sync_all_floating_dock_dockability(mw))
        main_window._dockability_sync_timer = timer
    return timer


def schedule_floating_dock_dockability_sync(
    main_window,
    *,
    delay_ms: int = _DOCKABILITY_SYNC_DEBOUNCE_MS,
) -> None:
    """全ドックのドッカビリティ同期をデバウンス実行する。"""
    _ensure_dockability_sync_timer(main_window).start(max(0, int(delay_ms)))


def on_dock_top_level_changed(main_window, dock: QDockWidget, floating: bool):
    """ドックのフローティング切替時に関連状態を更新する。"""
    # フローティング切替時に制約を同期する。
    if not floating:
        _clear_floating_runtime_state(main_window, dock, reason="dock_to_main")
        clear_force_dock_drop_active(main_window)
    update_floating_dock_dockability(main_window, dock)
    _sync_dock_options_by_floating_state(main_window)
    sync_tabbed_dock_title_bars(main_window)
    sync_dock_on_top(main_window, dock)
    if floating:
        _ensure_floating_dock_screen_tracking(main_window, dock)
        fit_top_level_widget_to_desktop(main_window, dock, allow_resize=False)
        _remember_floating_dock_size(main_window, dock)
        schedule_dock_on_top_refresh(main_window, dock, delay_ms=0)
        schedule_dock_on_top_refresh(main_window, dock, delay_ms=140)
    else:
        schedule_dock_rebalance(main_window)
    refresh_topmost_if_enabled(main_window)
    main_window._schedule_layout_autosave()


def track_floating_dock_size(
    main_window,
    dock: QDockWidget,
    *,
    from_move: bool = False,
) -> None:
    """フローティングドックのサイズ追跡を更新する。"""
    if dock is None or not dock.isFloating():
        _clear_floating_runtime_state(main_window, dock, reason="track_not_floating")
        return
    if not dock.isVisible():
        _clear_floating_runtime_state(main_window, dock, reason="track_hidden")
        return
    _ensure_floating_dock_screen_tracking(main_window, dock)
    left_dragging = _is_left_mouse_dragging()
    screen_fix_pending = bool(getattr(dock, "_floating_screen_fix_pending", False))
    _update_floating_move_drag_state(
        main_window,
        dock,
        from_move=bool(from_move),
        left_dragging=bool(left_dragging),
        screen_fix_pending=bool(screen_fix_pending),
    )
    move_drag_active = bool(getattr(dock, "_floating_move_drag_active", False))
    resize_drag_active = bool(getattr(dock, "_floating_resize_drag_active", False))
    suppress_remember = bool(left_dragging and move_drag_active and not resize_drag_active)
    remember_scheduled = False
    if (not bool(from_move)) and bool(resize_drag_active) and (not suppress_remember):
        reason = "resize_pending_fix" if screen_fix_pending else "resize"
        _schedule_floating_dock_size_remember(main_window, dock, reason=reason)
        remember_scheduled = True
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "track_floating_size_simple",
        throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        from_move=bool(from_move),
        move_drag_active=bool(move_drag_active),
        resize_drag_active=bool(resize_drag_active),
        suppress_remember=bool(suppress_remember),
        remember_scheduled=bool(remember_scheduled),
        left_dragging=bool(left_dragging),
        pending_screen_fix=bool(screen_fix_pending),
    )


def desktop_available_geometry(main_window) -> QRect:
    """メインウィンドウ基準の利用可能デスクトップ領域を返す。"""
    # 複数画面をまたぐ配置を不意に片側へ寄せないため、全画面Unionを使う。
    rect = screen_union_geometry(available=True)
    if rect.isValid() and rect.width() > 0 and rect.height() > 0:
        return rect
    return rect


def _available_geometry_for_widget(main_window, widget: QWidget | None = None) -> QRect:
    """対象ウィジェット基準の利用可能領域を返す。"""
    # 補正対象が実際に乗っているスクリーンを最優先し、混在DPIでの過大サイズ化を防ぐ。
    screen_candidates = []
    if widget is not None:
        try:
            ws = widget.screen()
            if ws is not None:
                screen_candidates.append(ws)
        except Exception:
            pass
        try:
            center = widget.frameGeometry().center()
            at_center = QGuiApplication.screenAt(center)
            if at_center is not None and at_center not in screen_candidates:
                screen_candidates.append(at_center)
        except Exception:
            pass
    try:
        ms = main_window.screen()
        if ms is not None and ms not in screen_candidates:
            screen_candidates.append(ms)
    except Exception:
        pass

    for screen in screen_candidates:
        rect = screen.availableGeometry()
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            return rect
    return screen_union_geometry(available=True)


def _compact_main_window_min_size(main_window) -> tuple[int, int]:
    """ドック0件時に必要となる最小クライアントサイズを返す。"""
    toolbar = main_window.findChild(QToolBar, "controlToolbar")
    toolbar_hint = toolbar.sizeHint() if toolbar is not None else QSize()
    menubar = main_window.menuBar() if hasattr(main_window, "menuBar") else None
    menubar_h = int(menubar.sizeHint().height()) if menubar is not None else 0
    min_w = max(
        _MAIN_WINDOW_COMPACT_MIN_W_FLOOR,
        int(toolbar_hint.width()) + 12,
    )
    min_h = max(
        _MAIN_WINDOW_COMPACT_MIN_H_FLOOR,
        int(toolbar_hint.height()) + menubar_h,
    )
    return int(min_w), int(min_h)


def _apply_main_window_minimum(main_window, has_visible_dock: bool) -> None:
    """ドック可視状態に応じてメインウィンドウの最小サイズを切り替える。"""
    if has_visible_dock:
        target_w, target_h = _MAIN_WINDOW_MIN_W, _MAIN_WINDOW_MIN_H
    else:
        target_w, target_h = _compact_main_window_min_size(main_window)
    if int(main_window.minimumWidth()) == int(target_w) and int(main_window.minimumHeight()) == int(
        target_h
    ):
        return
    main_window.setMinimumSize(int(target_w), int(target_h))


def fit_window_to_desktop(main_window):
    """メインウィンドウを利用可能領域内へ収める。"""
    # 最大化/フルスクリーン中は現在状態を維持する。
    if main_window.isMaximized() or main_window.isFullScreen():
        return
    avail = desktop_available_geometry(main_window)
    if avail.width() <= 0 or avail.height() <= 0:
        return

    # 手動スナップ/半分配置時の「勝手に内側へズレる」挙動を避けるため余白を持たせない
    margin = _MAIN_WINDOW_FIT_MARGIN_PX
    max_w = max(_MAIN_WINDOW_MAX_W_FLOOR, avail.width() - margin * 2)
    max_h = max(_MAIN_WINDOW_MAX_H_FLOOR, avail.height() - margin * 2)

    frame = main_window.frameGeometry()
    geom = main_window.geometry()
    extra_w = max(0, int(frame.width() - geom.width()))
    extra_h = max(0, int(frame.height() - geom.height()))
    max_client_w = max(_MAIN_WINDOW_MAX_W_FLOOR, max_w - extra_w)
    max_client_h = max(_MAIN_WINDOW_MAX_H_FLOOR, max_h - extra_h)
    min_client_w = max(1, int(main_window.minimumWidth()))
    min_client_h = max(1, int(main_window.minimumHeight()))
    target_client_w = min(max(min_client_w, int(geom.width())), max_client_w)
    target_client_h = min(max(min_client_h, int(geom.height())), max_client_h)
    if target_client_w != int(geom.width()) or target_client_h != int(geom.height()):
        main_window.resize(target_client_w, target_client_h)
        frame = main_window.frameGeometry()

    target_x, target_y = _clamp_top_left_in_available(
        avail,
        frame,
        margin,
        frame.x(),
        frame.y(),
    )
    if target_x != frame.x() or target_y != frame.y():
        main_window.move(target_x, target_y)


def schedule_window_fit(main_window):
    """メインウィンドウ位置/サイズ補正をタイマーで予約する。"""
    # 最小化中に無駄な再配置タイマーを動かさない。
    if main_window.isMinimized() or main_window.isMaximized() or main_window.isFullScreen():
        return
    main_window._fit_window_timer.start()


def _capture_dock_geometry_snapshot(main_window) -> dict[str, QRect]:
    """可視・ドック内ウィジェットの幾何情報を取得する。"""
    # 可視かつドック内にあるウィジェットだけを対象にする。
    snapshot: dict[str, QRect] = {}
    for name, dock in getattr(main_window, "_dock_map", {}).items():
        if dock is None or not dock.isVisible() or dock.isFloating():
            continue
        if main_window.dockWidgetArea(dock) == Qt.NoDockWidgetArea:
            continue
        geom = dock.geometry()
        if not geom.isValid() or geom.width() <= 0 or geom.height() <= 0:
            continue
        snapshot[name] = QRect(geom)
    return snapshot


def _dock_entries_from_snapshot(main_window, snapshot: dict[str, QRect]):
    """再配分計算用に (name, dock, geometry) エントリを抽出する。"""
    entries = []
    for name, geom in snapshot.items():
        dock = getattr(main_window, "_dock_map", {}).get(name)
        if dock is None:
            continue
        entries.append((name, dock, geom))
    entries.sort(key=lambda item: (item[2].x(), item[2].y()))
    return entries


def _group_entries_into_columns(entries):
    """X座標/幅が近いエントリを同一列としてグルーピングする。"""
    columns: list[dict] = []
    for entry in entries:
        geom = entry[2]
        attached = False
        for col in columns:
            if (
                abs(geom.x() - col["x"]) <= _REBALANCE_COLUMN_X_TOLERANCE_PX
                and abs(geom.width() - col["w"]) <= _REBALANCE_COLUMN_W_TOLERANCE_PX
            ):
                col["items"].append(entry)
                count = len(col["items"])
                col["x"] = int(round((col["x"] * (count - 1) + geom.x()) / float(count)))
                col["w"] = int(round((col["w"] * (count - 1) + geom.width()) / float(count)))
                attached = True
                break
        if not attached:
            columns.append({"x": geom.x(), "w": geom.width(), "items": [entry]})
    return columns


def _build_vertical_chain(items):
    """列内アイテムから上下連結チェーンを抽出する。"""
    sorted_items = sorted(items, key=lambda item: item[2].y())
    chain = []
    last_bottom = None
    for item in sorted_items:
        geom = item[2]
        if last_bottom is None or geom.y() >= (last_bottom - _REBALANCE_CHAIN_TOUCH_TOLERANCE_PX):
            chain.append(item)
            last_bottom = geom.bottom()
            continue
        # 重なっている（タブ等）場合は高さが大きい側を採用する。
        prev = chain[-1]
        if geom.height() > prev[2].height():
            chain[-1] = item
            last_bottom = geom.bottom()
    return chain


def _vertical_dock_chains(main_window, snapshot: dict[str, QRect]):
    """縦連結しているドック群をチェーン単位で抽出する。"""
    # X座標・幅が近いドックを同じ縦チェーンとして扱う。
    entries = _dock_entries_from_snapshot(main_window, snapshot)
    columns = _group_entries_into_columns(entries)
    chains = []
    for col in columns:
        chain = _build_vertical_chain(col["items"])
        if len(chain) >= 3:
            chains.append(chain)
    return chains


def schedule_dock_rebalance(main_window) -> None:
    """ドック再バランス処理をタイマーで予約する。"""
    if not hasattr(main_window, "_dock_rebalance_timer"):
        return
    if main_window.isMinimized():
        return
    main_window._dock_rebalance_timer.start()


def _update_rebalance_baseline(main_window, snapshot: dict[str, QRect], main_size: QSize) -> None:
    """次回比較用の再配分基準スナップショットを更新する。"""
    main_window._dock_geometry_snapshot = snapshot
    main_window._dock_rebalance_last_main_size = main_size


def _rebalance_pivot_info(changed: list[bool]) -> tuple[int, list[int]] | None:
    """変更フラグ列から再配分対象ペアと非隣接インデックスを求める。"""
    pivot = next((idx for idx in range(len(changed) - 1) if changed[idx]), None)
    if pivot is None:
        return None
    non_adjacent = [idx for idx in range(len(changed)) if idx not in (pivot, pivot + 1)]
    if not any(changed[idx] for idx in non_adjacent):
        return None
    return pivot, non_adjacent


def _rebalance_remaining_height(
    *,
    mins: list[int],
    targets: list[int],
    non_adjacent: list[int],
    total_height: int,
    pair_min: int,
) -> int | None:
    """非隣接分を固定した後、ペアへ割り当て可能な残り高さを返す。"""
    fixed_height = int(sum(targets[idx] for idx in non_adjacent))
    remain = int(total_height) - fixed_height
    if remain >= pair_min:
        return remain
    shortage = pair_min - remain
    for idx in reversed(non_adjacent):
        reducible = max(0, targets[idx] - mins[idx])
        take = min(reducible, shortage)
        targets[idx] -= take
        shortage -= take
        if shortage <= 0:
            break
    fixed_height = int(sum(targets[idx] for idx in non_adjacent))
    remain = int(total_height) - fixed_height
    if remain < pair_min:
        return None
    return remain


def _calculate_rebalance_targets_for_chain(chain, previous_snapshot: dict[str, QRect]):
    """1チェーン分の再配分先高さを計算し、必要時のみ返す。"""
    names = [item[0] for item in chain]
    docks = [item[1] for item in chain]
    if any(name not in previous_snapshot for name in names):
        return None

    cur_heights = [int(item[2].height()) for item in chain]
    prev_heights = [int(previous_snapshot[name].height()) for name in names]
    changed = [
        abs(c - p) >= _REBALANCE_HEIGHT_CHANGE_THRESHOLD_PX
        for c, p in zip(cur_heights, prev_heights)
    ]
    if sum(changed) < 3:
        return None

    pivot_info = _rebalance_pivot_info(changed)
    if pivot_info is None:
        return None
    pivot, non_adjacent = pivot_info

    mins = [max(1, int(dock.minimumHeight())) for dock in docks]
    targets = list(cur_heights)
    for idx in non_adjacent:
        targets[idx] = max(mins[idx], int(prev_heights[idx]))

    total_height = int(sum(cur_heights))
    pair_min = mins[pivot] + mins[pivot + 1]
    remain = _rebalance_remaining_height(
        mins=mins,
        targets=targets,
        non_adjacent=non_adjacent,
        total_height=total_height,
        pair_min=pair_min,
    )
    if remain is None:
        return None

    w0 = max(1, cur_heights[pivot])
    w1 = max(1, cur_heights[pivot + 1])
    pair0 = int(round(remain * (w0 / float(w0 + w1))))
    pair0 = max(mins[pivot], min(pair0, remain - mins[pivot + 1]))
    pair1 = remain - pair0
    targets[pivot] = pair0
    targets[pivot + 1] = pair1
    if targets == cur_heights:
        return None
    return docks, targets


def rebalance_dock_layout(main_window) -> None:
    """縦積みドックの高さ連動を抑えるための再配分を行う。"""
    # 3段以上の縦積みで、上側ハンドル操作時に下段まで連動する現象を抑える。
    if getattr(main_window, "_dock_rebalance_running", False):
        return

    current_snapshot = _capture_dock_geometry_snapshot(main_window)
    previous_snapshot = getattr(main_window, "_dock_geometry_snapshot", {})
    if len(current_snapshot) < 3:
        _update_rebalance_baseline(main_window, current_snapshot, main_window.size())
        return
    main_size = main_window.size()
    last_main_size = getattr(main_window, "_dock_rebalance_last_main_size", None)

    # メインウィンドウ自体のリサイズ時は補正せず、基準だけ更新する。
    if (
        not previous_snapshot
        or not current_snapshot
        or (last_main_size is not None and main_size != last_main_size)
    ):
        _update_rebalance_baseline(main_window, current_snapshot, main_size)
        return

    adjusted = False
    for chain in _vertical_dock_chains(main_window, current_snapshot):
        target = _calculate_rebalance_targets_for_chain(chain, previous_snapshot)
        if target is None:
            continue
        docks, targets = target

        main_window._dock_rebalance_running = True
        try:
            main_window.resizeDocks(docks, targets, Qt.Vertical)
        finally:
            main_window._dock_rebalance_running = False
        adjusted = True
        break

    if adjusted:
        current_snapshot = _capture_dock_geometry_snapshot(main_window)
    _update_rebalance_baseline(main_window, current_snapshot, main_size)


def fit_dialog_to_desktop(main_window, dialog: QDialog, center_on_parent: bool = False):
    """ダイアログを利用可能領域内へ収めて表示位置を補正する。"""
    # 設定ダイアログが画面外に出ないよう位置/サイズを補正する。
    avail = _available_geometry_for_widget(main_window, dialog)
    if avail.width() <= 0 or avail.height() <= 0:
        return

    margin = _DIALOG_FIT_MARGIN_PX
    max_w = max(_DIALOG_MIN_W, avail.width() - margin * 2)
    max_h = max(_DIALOG_MIN_H, avail.height() - margin * 2)
    target_w = min(max(_DIALOG_MIN_W, dialog.width()), max_w)
    target_h = min(max(_DIALOG_MIN_H, dialog.height()), max_h)
    if target_w != dialog.width() or target_h != dialog.height():
        dialog.resize(target_w, target_h)

    frame = dialog.frameGeometry()
    use_center = center_on_parent or not avail.intersects(frame)
    if use_center:
        base = main_window.frameGeometry().center() if main_window.isVisible() else avail.center()
        target_x = base.x() - frame.width() // 2
        target_y = base.y() - frame.height() // 2
    else:
        target_x = frame.x()
        target_y = frame.y()

    target_x, target_y = _clamp_top_left_in_available(
        avail,
        frame,
        margin,
        target_x,
        target_y,
    )
    dialog.move(target_x, target_y)


def fit_top_level_widget_to_desktop(
    main_window,
    widget: QWidget,
    *,
    allow_resize: bool = True,
    allow_move: bool = True,
):
    """トップレベルウィジェットを利用可能領域内へ収める。"""
    # フローティングドックなどのトップレベルウィジェットを画面内に収める。
    avail = _available_geometry_for_widget(main_window, widget)
    if avail.width() <= 0 or avail.height() <= 0:
        return
    if widget.windowState() & Qt.WindowMinimized:
        return

    margin = _TOPLEVEL_FIT_MARGIN_PX
    frame = widget.frameGeometry()
    if allow_resize:
        max_w = max(_TOPLEVEL_MAX_W_FLOOR, avail.width() - margin * 2)
        max_h = max(_TOPLEVEL_MAX_H_FLOOR, avail.height() - margin * 2)

        geom = widget.geometry()
        extra_w = max(0, int(frame.width() - geom.width()))
        extra_h = max(0, int(frame.height() - geom.height()))
        max_client_w = max(_TOPLEVEL_MAX_W_FLOOR, max_w - extra_w)
        max_client_h = max(_TOPLEVEL_MAX_H_FLOOR, max_h - extra_h)
        target_client_w = min(max(_TOPLEVEL_MIN_W, int(geom.width())), max_client_w)
        target_client_h = min(max(_TOPLEVEL_MIN_H, int(geom.height())), max_client_h)
        if target_client_w != int(geom.width()) or target_client_h != int(geom.height()):
            widget.resize(target_client_w, target_client_h)
            frame = widget.frameGeometry()

    if allow_move:
        move_avail = screen_union_geometry(available=True)
        if not move_avail.isValid() or move_avail.width() <= 0 or move_avail.height() <= 0:
            move_avail = avail
        target_x, target_y = _clamp_top_left_in_available(
            move_avail,
            frame,
            margin,
            frame.x(),
            frame.y(),
        )
        if target_x != frame.x() or target_y != frame.y():
            widget.move(target_x, target_y)


def apply_ui_style(main_window):
    """アプリ全体スタイルとドック内スタイルを適用する。"""
    # アプリ全体とドック内ウィジェットでスタイルを分けて適用する。
    from ...util import theme as ui_theme
    from .. import settings_dialog as settings_dialog_ui

    theme = ui_theme.get_ui_theme(getattr(main_window, "_ui_theme_name", None))
    main_window._ui_theme = theme
    main_window._ui_theme_name = theme.name

    app = QApplication.instance()
    if app is not None:
        app.setPalette(ui_theme.build_palette(theme))
        app.setStyleSheet(ui_theme.build_app_stylesheet(theme))

    settings_dialog_ui.refresh_settings_nav_style(main_window)

    themed_widgets = (
        getattr(main_window, "preview_window", None),
        getattr(main_window, "wheel", None),
        getattr(main_window, "scatter", None),
        getattr(main_window, "hist_h", None),
        getattr(main_window, "hist_s", None),
        getattr(main_window, "hist_v", None),
        getattr(main_window, "rgb_hist_view", None),
        getattr(main_window, "vectorscope_view", None),
        getattr(main_window, "_canvas_preview_window", None),
    )
    for widget in themed_widgets:
        if widget is not None and hasattr(widget, "set_theme"):
            widget.set_theme(theme)

    polish_targets = [
        main_window,
        main_window.centralWidget(),
        getattr(main_window, "_settings_window", None),
        getattr(main_window, "btn_load_image_bar", None),
        getattr(main_window, "lbl_status", None),
        getattr(main_window, "placeholder", None),
        getattr(main_window, "list_color_chips", None),
        getattr(main_window, "lbl_warmcool", None),
        getattr(main_window, "lbl_color_detail_title", None),
        getattr(main_window, "lbl_color_detail_info", None),
        getattr(main_window, "lbl_vectorscope_warning", None),
        getattr(main_window, "slider_scatter_hue_center", None),
        getattr(main_window, "lbl_scatter_hue_center", None),
    ]
    menu_bar = main_window.menuBar()
    if menu_bar is not None:
        polish_targets.append(menu_bar)
    for toolbar in main_window.findChildren(QToolBar):
        polish_targets.append(toolbar)
    for widget in polish_targets:
        if isinstance(widget, QWidget):
            ui_theme.refresh_widget_style(widget)


def sync_window_menu_checks(main_window, *_):
    """ウィンドウメニューのチェック状態を実際の表示状態へ合わせる。"""
    # ドック実表示状態とメニューのチェック状態を同期する。
    for name, dock in main_window._dock_map.items():
        act = main_window._dock_actions.get(name)
        if act is None:
            continue
        with blocked_signals(act):
            act.setChecked(dock.isVisible())


def _default_area_for_dock(main_window, dock: QDockWidget):
    """ドックの既定エリアを返す。"""
    area = Qt.RightDockWidgetArea
    for name, mapped in getattr(main_window, "_dock_map", {}).items():
        if mapped is dock:
            area = getattr(main_window, "_dock_default_areas", {}).get(name, area)
            break
    return area


def _visible_docks_in_area(main_window, area):
    """指定エリアにある可視ドック一覧を返す。"""
    docks = []
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None:
            continue
        if not dock.isVisible() or dock.isFloating():
            continue
        if main_window.dockWidgetArea(dock) != area:
            continue
        docks.append(dock)
    return docks


def _visible_docked_docks(main_window, *, exclude: QDockWidget | None = None):
    """現在ドック内にある可視ドック一覧を返す。"""
    docks = []
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None or dock is exclude:
            continue
        if not dock.isVisible() or dock.isFloating():
            continue
        if main_window.dockWidgetArea(dock) == Qt.NoDockWidgetArea:
            continue
        docks.append(dock)
    return docks


def _preferred_visible_tab_anchor(main_window, dock: QDockWidget) -> QDockWidget | None:
    """ドック追加時の優先タブアンカーを返す。"""
    anchor_name = str(getattr(dock, "_preferred_tab_anchor_name", "")).strip()
    if not anchor_name:
        return None
    anchor = getattr(main_window, anchor_name, None)
    if not isinstance(anchor, QDockWidget) or anchor is dock:
        return None
    if not anchor.isVisible() or anchor.isFloating():
        return None
    if main_window.dockWidgetArea(anchor) == Qt.NoDockWidgetArea:
        return None
    return anchor


def _dock_area_to_log_value(area) -> int | str:
    """DockWidgetArea をログ出力向けの安全な値へ変換する。"""
    try:
        return int(area)
    except Exception:
        try:
            return int(getattr(area, "value"))
        except Exception:
            return str(area)


def _resolve_dock_attach_target(main_window, dock: QDockWidget, default_area):
    """ドック追加時の統一アンカー/エリアを返す。"""
    preferred_anchor = _preferred_visible_tab_anchor(main_window, dock)
    if preferred_anchor is not None:
        return preferred_anchor, main_window.dockWidgetArea(preferred_anchor), "preferred_anchor"

    same_area_anchors = [
        d for d in _visible_docks_in_area(main_window, default_area) if d is not dock
    ]
    if same_area_anchors:
        return same_area_anchors[0], default_area, "same_area_anchor"

    fallback_anchors = _visible_docked_docks(main_window, exclude=dock)
    if fallback_anchors:
        anchor = fallback_anchors[0]
        return anchor, main_window.dockWidgetArea(anchor), "fallback_visible_anchor"

    return None, default_area, "no_anchor"


def _attach_dock_to_area_group(main_window, dock: QDockWidget, area) -> None:
    """ドックを指定エリアへ追加し、必要なら既存タブへ合流させる。"""
    anchor, target_area, reason = _resolve_dock_attach_target(main_window, dock, area)
    main_window.addDockWidget(target_area, dock)
    if anchor is not None:
        # Adobe/DaVinci系と同様、追加時は既存タブへ合流しレイアウト崩れを防ぐ。
        main_window.tabifyDockWidget(anchor, dock)
    write_window_layout_debug_log(
        "dock_attach_to_group",
        dock=_dock_debug_name(main_window, dock),
        requested_area=_dock_area_to_log_value(area),
        target_area=_dock_area_to_log_value(target_area),
        anchor=_dock_debug_name(main_window, anchor) if anchor is not None else None,
        reason=str(reason),
    )


def toggle_dock(main_window, dock: QDockWidget, visible: bool):
    """ドックの表示/非表示を切り替え、関連状態を再同期する。"""
    # 閉じる/表示の両操作後に placeholder とレイアウト保存タイマーを更新する。
    if visible:
        was_hidden = dock.isHidden()
        # 非表示前がフローティングなら、ドックへ戻さず同じ形態で再表示する。
        if dock.isFloating():
            dock.setVisible(True)
            sync_dock_on_top(main_window, dock)
            fit_top_level_widget_to_desktop(main_window, dock, allow_resize=False)
            schedule_dock_on_top_refresh(main_window, dock, delay_ms=0)
            schedule_dock_on_top_refresh(main_window, dock, delay_ms=140)
            dock.raise_()
            dock.activateWindow()
        else:
            area = _default_area_for_dock(main_window, dock)
            attach_on_next_show = bool(getattr(dock, "_attach_on_next_show", False))
            needs_attach = bool(
                attach_on_next_show or main_window.dockWidgetArea(dock) == Qt.NoDockWidgetArea
            )
            if needs_attach:
                _attach_dock_to_area_group(main_window, dock, area)
                dock._attach_on_next_show = False
            dock.setVisible(True)
            recovered_attach = False
            if not dock.isVisible():
                # まれに非表示復帰でレイアウト木から外れたままになるケースを救済する。
                _attach_dock_to_area_group(main_window, dock, area)
                dock._attach_on_next_show = False
                dock.setVisible(True)
                recovered_attach = True
            current_area = main_window.dockWidgetArea(dock)
            write_window_layout_debug_log(
                "dock_toggle_show",
                dock=_dock_debug_name(main_window, dock),
                was_hidden=bool(was_hidden),
                needs_attach=bool(needs_attach),
                recovered_attach=bool(recovered_attach),
                requested_area=_dock_area_to_log_value(area),
                current_area=_dock_area_to_log_value(current_area),
                visible=bool(dock.isVisible()),
            )
            dock.raise_()
    else:
        dock.setVisible(False)
    _sync_dock_options_by_floating_state(main_window)
    sync_tabbed_dock_title_bars(main_window)
    update_placeholder(main_window)
    schedule_dock_rebalance(main_window)
    main_window._schedule_layout_autosave()


def update_placeholder(main_window):
    """可視ドック有無に応じて中央プレースホルダ表示を切り替える。"""
    # ドック内に可視ビューがないときのみ中央プレースホルダを見せる。
    # ドック内にビューがある間は中央ウィジェットを隠し、余白を作らない。
    any_visible = any(
        dock.isVisible()
        and not dock.isFloating()
        and main_window.dockWidgetArea(dock) != Qt.NoDockWidgetArea
        for dock in main_window._dock_map.values()
    )
    _apply_main_window_minimum(main_window, any_visible)
    main_window.central_container.setMaximumSize(16777215, 16777215)
    main_window.central_container.setMinimumSize(0, 0)
    if any_visible:
        main_window.placeholder.hide()
        main_window.central_container.hide()
    else:
        # ドックがないときは中央に案内文を表示する。
        # ウィンドウを最小まで縮めた場合は中央領域が潰れて見えなくなってもよい。
        central_size = main_window.central_container.size()
        should_show_placeholder = (
            int(central_size.width()) >= _PLACEHOLDER_SHOW_MIN_W
            and int(central_size.height()) >= _PLACEHOLDER_SHOW_MIN_H
        )
        if should_show_placeholder:
            main_window.placeholder.show()
        else:
            main_window.placeholder.hide()
        main_window.central_container.show()
        main_window.central_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    main_window.central_container.updateGeometry()
