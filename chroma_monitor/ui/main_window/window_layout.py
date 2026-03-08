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
from ...util.qt_helpers import blocked_signals, screen_union_geometry
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
_FLOATING_SIZE_REMEMBER_RESUME_MS = 1200
_FLOATING_DEBUG_EVENT_THROTTLE_SEC = 0.06


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
        frame_text = (
            f"{int(frame.x())},{int(frame.y())},{int(frame.width())}x{int(frame.height())}"
        )
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


def _dock_window_handle(dock: QDockWidget):
    """ドックに対応する windowHandle を安全に取得する。"""
    try:
        return dock.windowHandle()
    except Exception:
        return None


def _floating_dock_screen_key(main_window, dock: QDockWidget):
    """フローティングドックが現在属しているスクリーン識別子を返す。"""
    screen = None
    win = _dock_window_handle(dock)
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
    if bool(getattr(dock, "_floating_suspend_size_remember", False)):
        return
    if bool(getattr(dock, "_floating_size_restore_lock", False)):
        return
    size = dock.size()
    if size.width() <= 0 or size.height() <= 0:
        return
    dock._floating_logical_size = QSize(int(size.width()), int(size.height()))
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "remember_floating_size",
        throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        force=bool(force),
        remembered_w=int(size.width()),
        remembered_h=int(size.height()),
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

    remembered = getattr(dock, "_floating_logical_size", None)
    if isinstance(remembered, QSize) and remembered.width() > 0 and remembered.height() > 0:
        target_w = max(int(dock.minimumWidth()), int(remembered.width()))
        target_h = max(int(dock.minimumHeight()), int(remembered.height()))
    else:
        size = dock.size()
        target_w = max(int(dock.minimumWidth()), int(size.width()))
        target_h = max(int(dock.minimumHeight()), int(size.height()))

    _debug_log_floating_dock_event(
        main_window,
        dock,
        "restore_on_screen_change_begin",
        clear_pending=bool(clear_pending),
        target_w=int(target_w),
        target_h=int(target_h),
    )
    dock._floating_size_restore_lock = True
    try:
        if dock.width() != target_w or dock.height() != target_h:
            dock.resize(int(target_w), int(target_h))
        fit_top_level_widget_to_desktop(main_window, dock)
        sync_dock_on_top(main_window, dock)
        schedule_dock_on_top_refresh(main_window, dock, delay_ms=0)
        schedule_dock_on_top_refresh(main_window, dock, delay_ms=140)
        _debug_log_floating_dock_event(
            main_window,
            dock,
            "restore_on_screen_change_done",
        )
    finally:
        dock._floating_size_restore_lock = False
        # 画面跨ぎ直後はOS/Qt由来の一時リサイズが発生しうるため、
        # ここでは記録を更新せず、短時間だけ再記録を抑止する。
        dock._floating_suspend_size_remember = True
        QTimer.singleShot(
            _FLOATING_SIZE_REMEMBER_RESUME_MS,
            lambda d=dock: setattr(d, "_floating_suspend_size_remember", False),
        )


def _schedule_floating_dock_screen_fix(main_window, dock: QDockWidget) -> None:
    """フローティングドック画面移動補正を次イベントループで予約する。"""
    if dock is None or not dock.isFloating():
        return
    if bool(getattr(dock, "_floating_screen_fix_pending", False)):
        _debug_log_floating_dock_event(
            main_window,
            dock,
            "schedule_screen_fix_skip_pending",
            throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        )
        return
    dock._floating_suspend_size_remember = True
    dock._floating_screen_fix_pending = True
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "schedule_screen_fix",
    )
    QTimer.singleShot(
        0,
        lambda mw=main_window, d=dock: _restore_floating_dock_size_on_screen_change(mw, d),
    )


def _ensure_floating_dock_screen_tracking(main_window, dock: QDockWidget) -> None:
    """フローティングドックの screenChanged 監視を現在ハンドルへ接続する。"""
    if dock is None:
        return
    win = _dock_window_handle(dock)
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


def update_floating_dock_dockability(main_window, dock: QDockWidget) -> None:
    """フローティングドックのドッキング許可状態を同期する。"""
    # レイアウトは Qt 標準ドッキング挙動を優先する。
    if dock.allowedAreas() != Qt.AllDockWidgetAreas:
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
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


def _is_dock_drop_active_near_main_window(main_window) -> bool:
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
    frame = _dock_drop_zone_rect(main_window)
    cursor_pos = QCursor.pos()
    if frame.contains(cursor_pos):
        return True
    return _floating_dock_intersects_drop_zone(main_window, frame)


def _sync_dock_options_by_floating_state(main_window) -> None:
    """ドックオプション(ネスト可否など)を現在状態に合わせて同期する。"""
    # 通常はフローティング中の外部左右上下ドロップを抑制し、中央タブ重ねを優先する。
    # ただしメイン近傍へドラッグ中はネストを一時許可し、上下左右のドロップ判定を広げる。
    has_visible_floating = any(
        dock.isVisible() and dock.isFloating()
        for dock in getattr(main_window, "_dock_map", {}).values()
    )
    allow_nested_while_dragging = _is_dock_drop_active_near_main_window(main_window)
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
        update_floating_dock_dockability(main_window, dock)
    _sync_dock_options_by_floating_state(main_window)
    sync_tabbed_dock_title_bars(main_window)


def on_dock_top_level_changed(main_window, dock: QDockWidget, floating: bool):
    """ドックのフローティング切替時に関連状態を更新する。"""
    # フローティング切替時に制約を同期する。
    if not floating:
        clear_force_dock_drop_active(main_window)
    update_floating_dock_dockability(main_window, dock)
    _sync_dock_options_by_floating_state(main_window)
    sync_tabbed_dock_title_bars(main_window)
    sync_dock_on_top(main_window, dock)
    if floating:
        _ensure_floating_dock_screen_tracking(main_window, dock)
        fit_top_level_widget_to_desktop(main_window, dock)
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
        return
    if not dock.isVisible():
        return
    _ensure_floating_dock_screen_tracking(main_window, dock)
    _remember_floating_dock_size(main_window, dock)
    _debug_log_floating_dock_event(
        main_window,
        dock,
        "track_floating_size_simple",
        throttle_sec=_FLOATING_DEBUG_EVENT_THROTTLE_SEC,
        from_move=bool(from_move),
    )


def desktop_available_geometry(main_window) -> QRect:
    """メインウィンドウ基準の利用可能デスクトップ領域を返す。"""
    # 基本は現在スクリーンを優先し、取得不可時のみ全画面統合へフォールバックする。
    try:
        center_screen = QGuiApplication.screenAt(main_window.frameGeometry().center())
    except Exception:
        center_screen = None
    if center_screen is not None:
        rect = center_screen.availableGeometry()
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            return rect
    screen = None
    try:
        screen = main_window.screen()
    except Exception:
        screen = None
    if screen is not None:
        rect = screen.availableGeometry()
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            return rect
    return screen_union_geometry(available=True)


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
    if (
        int(main_window.minimumWidth()) == int(target_w)
        and int(main_window.minimumHeight()) == int(target_h)
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


def _vertical_dock_chains(main_window, snapshot: dict[str, QRect]):
    """縦連結しているドック群をチェーン単位で抽出する。"""
    # X座標・幅が近いドックを同じ縦チェーンとして扱う。
    entries = []
    for name, geom in snapshot.items():
        dock = getattr(main_window, "_dock_map", {}).get(name)
        if dock is None:
            continue
        entries.append((name, dock, geom))
    entries.sort(key=lambda item: (item[2].x(), item[2].y()))

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

    chains = []
    for col in columns:
        sorted_items = sorted(col["items"], key=lambda item: item[2].y())
        chain = []
        last_bottom = None
        for item in sorted_items:
            geom = item[2]
            if last_bottom is None or geom.y() >= (
                last_bottom - _REBALANCE_CHAIN_TOUCH_TOLERANCE_PX
            ):
                chain.append(item)
                last_bottom = geom.bottom()
                continue
            # 重なっている（タブ等）場合は高さが大きい側を採用する。
            prev = chain[-1]
            if geom.height() > prev[2].height():
                chain[-1] = item
                last_bottom = geom.bottom()
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


def rebalance_dock_layout(main_window) -> None:
    """縦積みドックの高さ連動を抑えるための再配分を行う。"""
    # 3段以上の縦積みで、上側ハンドル操作時に下段まで連動する現象を抑える。
    if getattr(main_window, "_dock_rebalance_running", False):
        return

    current_snapshot = _capture_dock_geometry_snapshot(main_window)
    previous_snapshot = getattr(main_window, "_dock_geometry_snapshot", {})
    if len(current_snapshot) < 3:
        main_window._dock_geometry_snapshot = current_snapshot
        main_window._dock_rebalance_last_main_size = main_window.size()
        return
    main_size = main_window.size()
    last_main_size = getattr(main_window, "_dock_rebalance_last_main_size", None)

    # メインウィンドウ自体のリサイズ時は補正せず、基準だけ更新する。
    if (
        not previous_snapshot
        or not current_snapshot
        or (last_main_size is not None and main_size != last_main_size)
    ):
        main_window._dock_geometry_snapshot = current_snapshot
        main_window._dock_rebalance_last_main_size = main_size
        return

    adjusted = False
    for chain in _vertical_dock_chains(main_window, current_snapshot):
        names = [item[0] for item in chain]
        docks = [item[1] for item in chain]
        if any(name not in previous_snapshot for name in names):
            continue

        cur_heights = [int(item[2].height()) for item in chain]
        prev_heights = [int(previous_snapshot[name].height()) for name in names]
        changed = [
            abs(c - p) >= _REBALANCE_HEIGHT_CHANGE_THRESHOLD_PX
            for c, p in zip(cur_heights, prev_heights)
        ]
        if sum(changed) < 3:
            continue

        pivot = next((idx for idx in range(len(changed) - 1) if changed[idx]), None)
        if pivot is None:
            continue
        non_adjacent = [idx for idx in range(len(changed)) if idx not in (pivot, pivot + 1)]
        if not any(changed[idx] for idx in non_adjacent):
            continue

        mins = [max(1, int(dock.minimumHeight())) for dock in docks]
        targets = list(cur_heights)
        for idx in non_adjacent:
            targets[idx] = max(mins[idx], int(prev_heights[idx]))

        total_height = int(sum(cur_heights))
        fixed_height = int(sum(targets[idx] for idx in non_adjacent))
        remain = total_height - fixed_height
        pair_min = mins[pivot] + mins[pivot + 1]
        if remain < pair_min:
            shortage = pair_min - remain
            for idx in reversed(non_adjacent):
                reducible = max(0, targets[idx] - mins[idx])
                take = min(reducible, shortage)
                targets[idx] -= take
                shortage -= take
                if shortage <= 0:
                    break
            fixed_height = int(sum(targets[idx] for idx in non_adjacent))
            remain = total_height - fixed_height
            if remain < pair_min:
                continue

        w0 = max(1, cur_heights[pivot])
        w1 = max(1, cur_heights[pivot + 1])
        pair0 = int(round(remain * (w0 / float(w0 + w1))))
        pair0 = max(mins[pivot], min(pair0, remain - mins[pivot + 1]))
        pair1 = remain - pair0
        targets[pivot] = pair0
        targets[pivot + 1] = pair1
        if targets == cur_heights:
            continue

        main_window._dock_rebalance_running = True
        try:
            main_window.resizeDocks(docks, targets, Qt.Vertical)
        finally:
            main_window._dock_rebalance_running = False
        adjusted = True
        break

    if adjusted:
        current_snapshot = _capture_dock_geometry_snapshot(main_window)
    main_window._dock_geometry_snapshot = current_snapshot
    main_window._dock_rebalance_last_main_size = main_size


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
    app_style = """
        QMainWindow { background:#f3f4f6; }
        QWidget#centralWidget { background:#f3f4f6; }
        QLabel { color:#111; }
        QPushButton { background:#f7f8fb; border:1px solid #cdd1d6; padding:6px 12px; border-radius:4px; color:#111; }
        QPushButton:hover { border:1px solid #b6bac0; background:#eef0f3; }
        QPushButton:pressed { background:#e4e6ea; }
        QComboBox { background:#ffffff; border:1px solid #cdd1d6; padding:4px 6px; color:#111; border-radius:4px; }
        QComboBox:disabled { background:#eceff3; border:1px solid #d6dbe2; color:#8a9099; }
        QDoubleSpinBox, QSpinBox {
            background:#ffffff; border:1px solid #cdd1d6; color:#111; border-radius:4px;
            padding:4px 24px 4px 6px;
        }
        QDoubleSpinBox:disabled, QSpinBox:disabled {
            background:#eceff3; border:1px solid #d6dbe2; color:#8a9099;
        }
        QSpinBox::up-button, QDoubleSpinBox::up-button {
            subcontrol-origin:border;
            width:20px;
        }
        QSpinBox::down-button, QDoubleSpinBox::down-button {
            subcontrol-origin:border;
            width:20px;
        }
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
            width:9px;
            height:9px;
        }
        QCheckBox { color:#111; spacing:7px; }
        QCheckBox::indicator { width:18px; height:18px; }
        QDockWidget::title {
            background:#f9fafc;
            padding:4px 8px;
            border:1px solid #dfe3e8;
            border-radius:4px;
        }
        QToolBar { spacing:8px; border:none; background:#f3f4f6; padding:4px 8px; }
        QPushButton#runStartBtn, QPushButton#runStopBtn {
            font-weight:600; padding:6px 12px; border-radius:8px; min-width:72px;
            border:1px solid #c7ced7; color:#111827; background:#ffffff;
        }
        QPushButton#runStartBtn:checked { background:#16a34a; border:1px solid #15803d; color:#ffffff; }
        QPushButton#runStopBtn:checked { background:#dc2626; border:1px solid #b91c1c; color:#ffffff; }
    """
    dock_style = """
        QWidget { background: #FAFBFD; color:#111; }
        QGroupBox { background: #FAFBFD; color:#111; border:1px solid #D5D5D8; border-radius:6px; margin-top:8px; }
        QGroupBox::title { subcontrol-origin: margin; left:10px; padding:2px 8px 2px 8px; background:#FAFBFD; border-radius:4px; }
        QLabel { color:#111; }
    """

    main_window.setStyleSheet(app_style)
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None:
            continue
        widget = dock.widget()
        if isinstance(widget, QWidget):
            widget.setStyleSheet(dock_style)


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

    same_area_anchors = [d for d in _visible_docks_in_area(main_window, default_area) if d is not dock]
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
            fit_top_level_widget_to_desktop(main_window, dock)
            schedule_dock_on_top_refresh(main_window, dock, delay_ms=0)
            schedule_dock_on_top_refresh(main_window, dock, delay_ms=140)
            dock.raise_()
            dock.activateWindow()
        else:
            area = _default_area_for_dock(main_window, dock)
            attach_on_next_show = bool(getattr(dock, "_attach_on_next_show", False))
            needs_attach = bool(
                attach_on_next_show
                or main_window.dockWidgetArea(dock) == Qt.NoDockWidgetArea
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
