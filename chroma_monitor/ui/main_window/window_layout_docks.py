"""ドック表示切替・ドッカビリティ同期・フローティング連携。"""

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QDockWidget

from ...util.debug_log import write_window_layout_debug_log
from .window_layout_common import (
    _DOCK_DROP_ACTIVATION_MARGIN_MAX_PX,
    _DOCK_DROP_ACTIVATION_MARGIN_MIN_PX,
    _DOCK_DROP_ACTIVATION_MARGIN_RATIO,
    _DOCK_OPTIONS_BASE,
    _DOCK_OPTIONS_NESTED,
    _DOCKABILITY_SYNC_DEBOUNCE_MS,
    dock_area_to_log_value,
    dock_debug_name,
)
from .window_layout_floating import (
    _is_left_mouse_dragging,
    clear_floating_runtime_state,
    debug_log_floating_dock_event,
    ensure_floating_dock_screen_tracking,
    update_floating_move_drag_state,
)
from .window_layout_geometry import fit_top_level_widget_to_desktop, update_placeholder
from .window_layout_rebalance import schedule_dock_rebalance
from .window_layout_theme import retint_dock_title_button_icons
from .window_tabs import clear_force_dock_drop_active, sync_tabbed_dock_title_bars
from .window_topmost import (
    refresh_topmost_if_enabled,
    schedule_dock_on_top_refresh,
    sync_dock_on_top,
)


def update_floating_dock_dockability(
    main_window,
    dock: QDockWidget,
    *,
    sync_options: bool = True,
) -> None:
    """フローティングドックのドッキング許可状態を同期する。"""
    if dock is None:
        return
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
    if not floating:
        clear_floating_runtime_state(main_window, dock, reason="dock_to_main")
        clear_force_dock_drop_active(main_window)
    update_floating_dock_dockability(main_window, dock)
    _sync_dock_options_by_floating_state(main_window)
    sync_tabbed_dock_title_bars(main_window)
    retint_dock_title_button_icons(main_window, getattr(main_window, "_ui_theme", None))
    QTimer.singleShot(
        0,
        lambda mw=main_window, th=getattr(main_window, "_ui_theme", None): retint_dock_title_button_icons(
            mw, th
        ),
    )
    sync_dock_on_top(main_window, dock)
    if floating:
        ensure_floating_dock_screen_tracking(main_window, dock)
        fit_top_level_widget_to_desktop(main_window, dock, allow_resize=False)
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
        clear_floating_runtime_state(main_window, dock, reason="track_not_floating")
        return
    if not dock.isVisible():
        clear_floating_runtime_state(main_window, dock, reason="track_hidden")
        return
    ensure_floating_dock_screen_tracking(main_window, dock)
    left_dragging = _is_left_mouse_dragging()
    screen_fix_pending = bool(getattr(dock, "_floating_screen_fix_pending", False))
    update_floating_move_drag_state(
        main_window,
        dock,
        from_move=bool(from_move),
        left_dragging=bool(left_dragging),
    )
    move_drag_active = bool(getattr(dock, "_floating_move_drag_active", False))
    resize_drag_active = bool(getattr(dock, "_floating_resize_drag_active", False))
    debug_log_floating_dock_event(
        main_window,
        dock,
        "track_floating_size_simple",
        throttle_sec=0.06,
        from_move=bool(from_move),
        move_drag_active=bool(move_drag_active),
        resize_drag_active=bool(resize_drag_active),
        left_dragging=bool(left_dragging),
        pending_screen_fix=bool(screen_fix_pending),
    )


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
        if dock is None or not dock.isVisible() or dock.isFloating():
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
        main_window.tabifyDockWidget(anchor, dock)
    write_window_layout_debug_log(
        "dock_attach_to_group",
        dock=dock_debug_name(main_window, dock),
        requested_area=dock_area_to_log_value(area),
        target_area=dock_area_to_log_value(target_area),
        anchor=dock_debug_name(main_window, anchor) if anchor is not None else None,
        reason=str(reason),
    )


def toggle_dock(main_window, dock: QDockWidget, visible: bool):
    """ドックの表示/非表示を切り替え、関連状態を再同期する。"""
    if visible:
        was_hidden = dock.isHidden()
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
                _attach_dock_to_area_group(main_window, dock, area)
                dock._attach_on_next_show = False
                dock.setVisible(True)
                recovered_attach = True
            current_area = main_window.dockWidgetArea(dock)
            write_window_layout_debug_log(
                "dock_toggle_show",
                dock=dock_debug_name(main_window, dock),
                was_hidden=bool(was_hidden),
                needs_attach=bool(needs_attach),
                recovered_attach=bool(recovered_attach),
                requested_area=dock_area_to_log_value(area),
                current_area=dock_area_to_log_value(current_area),
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
