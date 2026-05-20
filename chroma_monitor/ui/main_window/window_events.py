"""MainWindow のイベント入口とドック関連イベント補助。"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QMainWindow

from . import window_tabs as mw_tabs


def show_event(main_window, event):
    """初回表示時に画面内へ収まるようウィンドウサイズを補正する。"""
    QMainWindow.showEvent(main_window, event)
    if not main_window._did_initial_screen_fit:
        main_window._did_initial_screen_fit = True
        if bool(main_window._startup_should_fit_window):
            main_window._fit_window_to_desktop()


def window_event(main_window, event):
    """レイアウト・表示状態変化イベントに応じて同期処理を行う。"""
    if event.type() == QEvent.LayoutRequest:
        main_window._schedule_layout_autosave()
        main_window._schedule_dock_rebalance()
    elif event.type() == QEvent.WindowStateChange:
        main_window._schedule_layout_autosave()
        main_window._schedule_window_fit()
        main_window._refresh_topmost_if_enabled()
    elif event.type() == QEvent.Show:
        main_window._refresh_topmost_if_enabled()
    return QMainWindow.event(main_window, event)


def key_press_event(main_window, event):
    """Esc入力時に領域選択モードを優先的に解除する。"""
    if event.key() == Qt.Key_Escape and bool(getattr(main_window, "_roi_selectors", ())):
        main_window._cancel_roi_selection(announce=True)
        event.accept()
        return
    QMainWindow.keyPressEvent(main_window, event)


def handle_top_colors_bar_resize_event(main_window, obj, event) -> bool:
    """配色比率バーのリサイズイベントを処理したか返す。"""
    if obj is getattr(main_window, "top_colors_bar", None) and event.type() == QEvent.Resize:
        main_window._refresh_top_color_bar()
        return True
    return False


def handle_color_band_layout_event(main_window, obj, event) -> None:
    """配色比率ドックの表示/サイズ変更イベントを処理する。"""
    if obj is getattr(main_window, "dock_color_band", None) and event.type() in (
        QEvent.Resize,
        QEvent.Show,
    ):
        main_window._update_color_band_compact_visibility()


def handle_floating_state_dock_event(main_window, dock, event_type) -> None:
    """フローティング状態に応じたドックイベント処理を行う。"""
    if not dock.isFloating():
        main_window._schedule_dock_rebalance()
        return
    if event_type == QEvent.Move:
        main_window._notify_floating_dock_moved(dock)
        main_window._track_floating_dock_size(dock, from_move=True)
        return
    if event_type == QEvent.Resize:
        main_window._track_floating_dock_size(dock, from_move=False)


def maybe_restore_dock_snapshot_after_event(main_window, dock, event_type) -> None:
    """表示/リサイズ後に必要ならドックスナップショットを復元する。"""
    if event_type not in (QEvent.Show, QEvent.Resize):
        return
    if not bool(getattr(main_window, "_layout_interaction_pause_active", False)):
        main_window._restore_dock_from_snapshot(dock)


def remember_last_docked_size(main_window, dock) -> None:
    """フロートでないドックの直近サイズを必要時のみ記録する。"""
    _ = main_window
    if bool(dock.isFloating()):
        return
    size = dock.size()
    if size.width() <= 0 or size.height() <= 0:
        return
    try:
        is_tabbed = len(main_window.tabifiedDockWidgets(dock)) > 0
    except Exception:
        is_tabbed = False
    if (not is_tabbed) or int(size.height()) >= 96:
        dock._last_docked_size = (int(size.width()), int(size.height()))


def handle_dock_layout_event(main_window, dock, event_type) -> None:
    """共通ドックレイアウトイベントを処理する。"""
    remember_last_docked_size(main_window, dock)
    is_floating = bool(dock.isFloating())
    should_pause = bool(
        event_type == QEvent.Resize
        or (event_type in (QEvent.Move, QEvent.Show) and not is_floating)
    )
    if should_pause:
        main_window._begin_layout_interaction_pause("dock_layout")
    if event_type in (QEvent.Resize, QEvent.Move, QEvent.Show) and not is_floating:
        main_window._schedule_floating_dock_dockability_sync()
    else:
        main_window._update_floating_dock_dockability(dock)
    handle_floating_state_dock_event(main_window, dock, event_type)
    maybe_restore_dock_snapshot_after_event(main_window, dock, event_type)
    if should_pause:
        main_window._schedule_layout_interaction_resume("dock_layout")


def is_managed_dock(main_window, obj) -> bool:
    """イベント対象が管理中ドックか判定する。"""
    return obj in getattr(main_window, "_dock_map", {}).values()


def event_filter(main_window, obj, event):
    """ドック/タブ/カラーバーの共通イベントを捕捉して処理する。"""
    if handle_top_colors_bar_resize_event(main_window, obj, event):
        return QMainWindow.eventFilter(main_window, obj, event)
    handle_color_band_layout_event(main_window, obj, event)
    if mw_tabs.is_dock_tab_bar(main_window, obj):
        if mw_tabs.handle_dock_tab_bar_event(main_window, obj, event):
            return True
        return QMainWindow.eventFilter(main_window, obj, event)
    if is_managed_dock(main_window, obj):
        event_type = event.type()
        if event_type in (QEvent.Move, QEvent.Show, QEvent.Resize):
            handle_dock_layout_event(main_window, obj, event_type)
    return QMainWindow.eventFilter(main_window, obj, event)


def move_event(main_window, event):
    """メイン移動時にフローティングドック状態と保存予約を更新する。"""
    QMainWindow.moveEvent(main_window, event)
    main_window._schedule_floating_dock_dockability_sync()
    main_window._schedule_layout_autosave()


def resize_event(main_window, event):
    """メインリサイズ時の一時停止制御とレイアウト同期を行う。"""
    main_window._begin_layout_interaction_pause("main_resize")
    QMainWindow.resizeEvent(main_window, event)
    main_window._schedule_floating_dock_dockability_sync()
    main_window.update_placeholder()
    main_window._schedule_layout_autosave()
    main_window._schedule_layout_interaction_resume("main_resize")
