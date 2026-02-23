"""Window/layout behavior helpers for MainWindow."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QDialog, QDockWidget, QSizePolicy, QWidget

from ...util.functions import blocked_signals, screen_union_geometry

_REBALANCE_COLUMN_X_TOLERANCE_PX = 3
_REBALANCE_COLUMN_W_TOLERANCE_PX = 3
_REBALANCE_HEIGHT_CHANGE_THRESHOLD_PX = 2
_REBALANCE_CHAIN_TOUCH_TOLERANCE_PX = 2
_MAIN_WINDOW_FIT_MARGIN_PX = 0
_MAIN_WINDOW_MIN_W = 480
_MAIN_WINDOW_MIN_H = 360
_MAIN_WINDOW_MAX_W_FLOOR = 640
_MAIN_WINDOW_MAX_H_FLOOR = 420
_DIALOG_FIT_MARGIN_PX = 8
_DIALOG_MIN_W = 420
_DIALOG_MIN_H = 320
_TOPLEVEL_FIT_MARGIN_PX = 0
_TOPLEVEL_MIN_W = 160
_TOPLEVEL_MIN_H = 120
_TOPLEVEL_MAX_W_FLOOR = 240
_TOPLEVEL_MAX_H_FLOOR = 180


def _clamp_top_left_in_available(
    avail: QRect,
    frame: QRect,
    margin: int,
    x: int,
    y: int,
) -> tuple[int, int]:
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
    # レイアウトは Qt 標準ドッキング挙動を優先する。
    if dock.allowedAreas() != Qt.AllDockWidgetAreas:
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)


def sync_all_floating_dock_dockability(main_window) -> None:
    for dock in getattr(main_window, "_dock_map", {}).values():
        update_floating_dock_dockability(main_window, dock)


def on_dock_top_level_changed(main_window, dock: QDockWidget, floating: bool):
    # フローティング切替時に制約を同期する。
    update_floating_dock_dockability(main_window, dock)
    sync_dock_on_top(main_window, dock)
    if floating:
        fit_top_level_widget_to_desktop(main_window, dock)
    else:
        schedule_dock_rebalance(main_window)
    main_window._schedule_layout_autosave()


def desktop_available_geometry(main_window) -> QRect:
    # 基本は現在スクリーンを優先し、取得不可時のみ全画面統合へフォールバックする。
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


def fit_window_to_desktop(main_window):
    # 最大化/フルスクリーン時はユーザー操作を優先して何もしない。
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
    target_client_w = min(max(_MAIN_WINDOW_MIN_W, int(geom.width())), max_client_w)
    target_client_h = min(max(_MAIN_WINDOW_MIN_H, int(geom.height())), max_client_h)
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
    # 最小化中に無駄な再配置タイマーを動かさない。
    if main_window.isMinimized() or main_window.isMaximized() or main_window.isFullScreen():
        return
    main_window._fit_window_timer.start()


def _capture_dock_geometry_snapshot(main_window) -> dict[str, QRect]:
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
    if not hasattr(main_window, "_dock_rebalance_timer"):
        return
    if main_window.isMinimized():
        return
    main_window._dock_rebalance_timer.start()


def rebalance_dock_layout(main_window) -> None:
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
    # 設定ダイアログが画面外に出ないよう位置/サイズを補正する。
    avail = desktop_available_geometry(main_window)
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


def fit_top_level_widget_to_desktop(main_window, widget: QWidget):
    # フローティングドックなどのトップレベルウィジェットを画面内に収める。
    avail = desktop_available_geometry(main_window)
    if avail.width() <= 0 or avail.height() <= 0:
        return
    if widget.windowState() & Qt.WindowMinimized:
        return

    margin = _TOPLEVEL_FIT_MARGIN_PX
    max_w = max(_TOPLEVEL_MAX_W_FLOOR, avail.width() - margin * 2)
    max_h = max(_TOPLEVEL_MAX_H_FLOOR, avail.height() - margin * 2)

    frame = widget.frameGeometry()
    target_w = min(max(_TOPLEVEL_MIN_W, frame.width()), max_w)
    target_h = min(max(_TOPLEVEL_MIN_H, frame.height()), max_h)
    if target_w != frame.width() or target_h != frame.height():
        widget.resize(target_w, target_h)
        frame = widget.frameGeometry()

    target_x, target_y = _clamp_top_left_in_available(
        avail,
        frame,
        margin,
        frame.x(),
        frame.y(),
    )
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
    saved_geometry = QRect(widget.geometry()) if widget.isWindow() else QRect()
    widget.setWindowFlag(Qt.WindowStaysOnTopHint, desired)
    if was_visible:
        widget.show()
        if widget.isWindow():
            widget.setGeometry(saved_geometry)
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
    # 最前面切替では Qt がドック分割比を再計算することがあるため、
    # 事前状態を保存して即復元し、ドック内サイズの劣化を防ぐ。
    dock_state = main_window.saveState()
    # 切替直後に古いスナップショット基準で再バランスされるのを防ぐ。
    if hasattr(main_window, "_dock_rebalance_timer"):
        main_window._dock_rebalance_timer.stop()
    sync_all_on_top_widgets(main_window)
    if not dock_state.isEmpty():
        try:
            main_window.restoreState(dock_state)
        except Exception:
            pass
    main_window._dock_geometry_snapshot = {}
    main_window._dock_rebalance_last_main_size = main_window.size()
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
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None:
            continue
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


def _default_area_for_dock(main_window, dock: QDockWidget):
    area = Qt.RightDockWidgetArea
    for name, mapped in getattr(main_window, "_dock_map", {}).items():
        if mapped is dock:
            area = getattr(main_window, "_dock_default_areas", {}).get(name, area)
            break
    return area


def _visible_docks_in_area(main_window, area):
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


def _attach_dock_to_area_group(main_window, dock: QDockWidget, area) -> None:
    anchors = [d for d in _visible_docks_in_area(main_window, area) if d is not dock]
    main_window.addDockWidget(area, dock)
    if anchors:
        # Adobe/DaVinci系と同様、同一エリア追加はまずタブ化してレイアウト崩れを防ぐ。
        main_window.tabifyDockWidget(anchors[0], dock)


def toggle_dock(main_window, dock: QDockWidget, visible: bool):
    # 閉じる/表示の両操作後に placeholder とレイアウト保存タイマーを更新する。
    if visible:
        if dock.isFloating():
            dock.setFloating(False)
        if main_window.dockWidgetArea(dock) == Qt.NoDockWidgetArea:
            area = _default_area_for_dock(main_window, dock)
            _attach_dock_to_area_group(main_window, dock, area)
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
    schedule_dock_rebalance(main_window)
    main_window._schedule_layout_autosave()


def update_placeholder(main_window):
    # 全ドック非表示時のみ中央プレースホルダを見せる。
    # ドック表示中は中央ウィジェットを隠し、左右ドック間の余白を作らない。
    any_visible = any(dock.isVisible() for dock in main_window._dock_map.values())
    main_window.central_container.setMaximumSize(16777215, 16777215)
    if any_visible:
        main_window.placeholder.hide()
        main_window.central_container.hide()
    else:
        main_window.placeholder.show()
        main_window.central_container.show()
        main_window.central_container.setMinimumSize(120, 120)
        main_window.central_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    main_window.central_container.updateGeometry()
