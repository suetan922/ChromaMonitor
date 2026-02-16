"""Window/layout behavior helpers for MainWindow."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QDialog, QDockWidget, QSizePolicy, QWidget

from ...util import constants as C
from ...util.functions import blocked_signals, screen_union_geometry


def desktop_available_geometry(main_window) -> QRect:
    # 利用可能領域（タスクバー除外）を統合矩形で取得する。
    return screen_union_geometry(available=True)


def fit_window_to_desktop(main_window):
    # 最大化/フルスクリーン時はユーザー操作を優先して何もしない。
    if main_window.isMaximized() or main_window.isFullScreen():
        return
    avail = desktop_available_geometry(main_window)
    if avail.width() <= 0 or avail.height() <= 0:
        return

    # 手動スナップ/半分配置時の「勝手に内側へズレる」挙動を避けるため余白を持たせない
    margin = 0
    max_w = max(640, avail.width() - margin * 2)
    max_h = max(420, avail.height() - margin * 2)

    frame = main_window.frameGeometry()
    target_w = min(max(480, frame.width()), max_w)
    target_h = min(max(360, frame.height()), max_h)
    if target_w != frame.width() or target_h != frame.height():
        main_window.resize(target_w, target_h)
        frame = main_window.frameGeometry()

    min_x = avail.left() + margin
    min_y = avail.top() + margin
    max_x = avail.right() - margin - frame.width() + 1
    max_y = avail.bottom() - margin - frame.height() + 1
    if max_x < min_x:
        max_x = min_x
    if max_y < min_y:
        max_y = min_y

    target_x = min(max(frame.x(), min_x), max_x)
    target_y = min(max(frame.y(), min_y), max_y)
    if target_x != frame.x() or target_y != frame.y():
        main_window.move(target_x, target_y)


def schedule_window_fit(main_window):
    # 最小化中に無駄な再配置タイマーを動かさない。
    if main_window.isMinimized() or main_window.isMaximized() or main_window.isFullScreen():
        return
    main_window._fit_window_timer.start()


def schedule_dock_rebalance(main_window):
    # 画面状態が安定しているときだけ再バランス処理を予約する。
    if main_window.isMinimized() or main_window.isMaximized() or main_window.isFullScreen():
        return
    main_window._dock_rebalance_timer.start()


def rebalance_dock_layout(main_window):
    # ドックの表示/非表示直後に分割比が壊れる場合があるため、
    # 右カラムの可視ドックへ安全なサイズを再適用してリサイズ可能状態を維持する。
    if not hasattr(main_window, "_right_stack_order"):
        return
    docks = [
        d
        for d in main_window._right_stack_order
        if d.isVisible()
        and not d.isFloating()
        and main_window.dockWidgetArea(d) == Qt.RightDockWidgetArea
    ]
    if len(docks) < 2:
        return
    sizes = [max(C.VIEW_MIN_SIZE, int(d.size().height())) for d in docks]
    if sum(sizes) <= 0:
        sizes = [1] * len(docks)
    main_window.resizeDocks(docks, sizes, Qt.Vertical)


def fit_dialog_to_desktop(main_window, dialog: QDialog, center_on_parent: bool = False):
    # 設定ダイアログが画面外に出ないよう位置/サイズを補正する。
    avail = desktop_available_geometry(main_window)
    if avail.width() <= 0 or avail.height() <= 0:
        return

    margin = 8
    max_w = max(420, avail.width() - margin * 2)
    max_h = max(320, avail.height() - margin * 2)
    target_w = min(max(420, dialog.width()), max_w)
    target_h = min(max(320, dialog.height()), max_h)
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

    min_x = avail.left() + margin
    min_y = avail.top() + margin
    max_x = avail.right() - margin - frame.width() + 1
    max_y = avail.bottom() - margin - frame.height() + 1
    if max_x < min_x:
        max_x = min_x
    if max_y < min_y:
        max_y = min_y

    target_x = min(max(target_x, min_x), max_x)
    target_y = min(max(target_y, min_y), max_y)
    dialog.move(target_x, target_y)


def fit_top_level_widget_to_desktop(main_window, widget: QWidget):
    # フローティングドックなどのトップレベルウィジェットを画面内に収める。
    avail = desktop_available_geometry(main_window)
    if avail.width() <= 0 or avail.height() <= 0:
        return
    if widget.windowState() & Qt.WindowMinimized:
        return

    margin = 0
    max_w = max(240, avail.width() - margin * 2)
    max_h = max(180, avail.height() - margin * 2)

    frame = widget.frameGeometry()
    target_w = min(max(160, frame.width()), max_w)
    target_h = min(max(120, frame.height()), max_h)
    if target_w != frame.width() or target_h != frame.height():
        widget.resize(target_w, target_h)
        frame = widget.frameGeometry()

    min_x = avail.left() + margin
    min_y = avail.top() + margin
    max_x = avail.right() - margin - frame.width() + 1
    max_y = avail.bottom() - margin - frame.height() + 1
    if max_x < min_x:
        max_x = min_x
    if max_y < min_y:
        max_y = min_y

    target_x = min(max(frame.x(), min_x), max_x)
    target_y = min(max(frame.y(), min_y), max_y)
    if target_x != frame.x() or target_y != frame.y():
        widget.move(target_x, target_y)


def is_always_on_top_enabled(main_window) -> bool:
    # アクション未生成のタイミングでも安全に False を返す。
    return bool(
        getattr(main_window, "act_always_on_top", None)
        and main_window.act_always_on_top.isChecked()
    )


def set_widget_on_top(_main_window, widget: QWidget | None, enabled: bool) -> None:
    # WindowStaysOnTopHint は表示中に切り替えると再showが必要になる。
    if widget is None:
        return
    desired = bool(enabled)
    current = bool(widget.windowFlags() & Qt.WindowStaysOnTopHint)
    if current == desired:
        return
    was_visible = widget.isVisible()
    widget.setWindowFlag(Qt.WindowStaysOnTopHint, desired)
    if was_visible:
        widget.show()
        widget.raise_()


def sync_dock_on_top(main_window, dock: QDockWidget):
    # ドックはフローティング時のみ最前面設定を適用する。
    set_widget_on_top(
        main_window,
        dock,
        is_always_on_top_enabled(main_window) and dock.isFloating(),
    )


def sync_all_on_top_widgets(main_window):
    # メイン/設定/プレビュー/フローティングドックへ最前面状態を反映する。
    enabled = is_always_on_top_enabled(main_window)
    set_widget_on_top(main_window, main_window, enabled)
    if hasattr(main_window, "preview_window"):
        set_widget_on_top(main_window, main_window.preview_window, enabled)
    if hasattr(main_window, "_settings_window") and main_window._settings_window is not None:
        set_widget_on_top(main_window, main_window._settings_window, enabled)
    for dock in getattr(main_window, "_dock_map", {}).values():
        sync_dock_on_top(main_window, dock)


def apply_always_on_top(main_window, checked: bool, save: bool = True):
    # ループ発火を避けるため setChecked はシグナルをブロックして行う。
    with blocked_signals(main_window.act_always_on_top):
        main_window.act_always_on_top.setChecked(bool(checked))
    sync_all_on_top_widgets(main_window)
    if save:
        main_window._request_save_settings()


def present_settings_window(main_window, center_on_parent: bool = False):
    # 設定ウィンドウの表示は位置補正・最前面同期・最小化解除を一括処理する。
    if not hasattr(main_window, "_settings_window"):
        return
    win = main_window._settings_window
    set_widget_on_top(main_window, win, is_always_on_top_enabled(main_window))
    fit_dialog_to_desktop(main_window, win, center_on_parent=center_on_parent)
    if win.windowState() & Qt.WindowMinimized:
        win.setWindowState((win.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        win.showNormal()
    win.show()
    win.raise_()
    win.activateWindow()


def apply_ui_style(main_window):
    # アプリ全体とドック内ウィジェットでスタイルを分けて適用する。
    app_style = """
        QMainWindow { background:#f3f4f6; }
        QWidget#centralWidget { background:#f3f4f6; }
        QLabel { color:#111; }
        QPushButton { background:#f7f8fb; border:1px solid #cdd1d6; padding:6px 12px; border-radius:4px; color:#111; }
        QPushButton:hover { border:1px solid #b6bac0; background:#eef0f3; }
        QPushButton:pressed { background:#e4e6ea; }
        QComboBox { background:#ffffff; border:1px solid #cdd1d6; padding:4px 6px; color:#111; border-radius:4px; }
        QDoubleSpinBox, QSpinBox {
            background:#ffffff; border:1px solid #cdd1d6; color:#111; border-radius:4px;
            padding:4px 24px 4px 6px;
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
        QCheckBox { color:#111; spacing:6px; }
        QCheckBox::indicator { width:16px; height:16px; border-radius:3px; border:1px solid #c0c4ca; background:#ffffff; }
        QCheckBox::indicator:checked { background:#4a90e2; border:1px solid #3578c8; }
        QDockWidget::title { background:#f9fafc; padding:4px 8px; border:1px solid #dfe3e8; border-radius:4px; }
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
    for dock in (
        main_window.dock_color,
        main_window.dock_scatter,
        main_window.dock_hist,
        main_window.dock_edge,
        main_window.dock_gray,
        main_window.dock_binary,
        main_window.dock_ternary,
        main_window.dock_saliency,
        main_window.dock_focus,
        main_window.dock_squint,
        main_window.dock_vectorscope,
    ):
        widget = dock.widget()
        if isinstance(widget, QWidget):
            widget.setStyleSheet(dock_style)


def sync_window_menu_checks(main_window, *_):
    # ドック実表示状態とメニューのチェック状態を同期する。
    for name, dock in main_window._dock_map.items():
        act = main_window._dock_actions.get(name)
        if act is None:
            continue
        with blocked_signals(act):
            act.setChecked(dock.isVisible())


def toggle_dock(main_window, dock: QDockWidget, visible: bool):
    # 閉じる/表示の両操作後に placeholder とレイアウト保存タイマーを更新する。
    if visible:
        if not dock.isFloating() and main_window.dockWidgetArea(dock) == Qt.NoDockWidgetArea:
            main_window.addDockWidget(Qt.RightDockWidgetArea, dock)
        dock.setVisible(True)
        if dock.isFloating():
            fit_top_level_widget_to_desktop(main_window, dock)
            dock.raise_()
            dock.activateWindow()
        else:
            dock.raise_()
    else:
        dock.setVisible(False)
    update_placeholder(main_window)
    main_window._schedule_layout_autosave()
    main_window._schedule_dock_rebalance()


def update_placeholder(main_window):
    # 全ドック非表示時のみ中央プレースホルダを見せる。
    any_visible = any(dock.isVisible() for dock in main_window._dock_map.values())
    if any_visible:
        main_window.placeholder.hide()
        # 中央領域を極小化してドックに最大面積を割り当てる
        main_window.central_container.setMinimumSize(0, 0)
        main_window.central_container.setMaximumSize(0, 0)
        main_window.central_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    else:
        main_window.placeholder.show()
        main_window.central_container.setMaximumSize(16777215, 16777215)
        main_window.central_container.setMinimumSize(120, 120)
        main_window.central_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    main_window.central_container.updateGeometry()
