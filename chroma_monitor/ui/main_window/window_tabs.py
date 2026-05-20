"""ドックタブ表示とタブUI補助処理。"""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QSizePolicy, QTabBar, QToolButton, QWidget

_HIDE_DOCK_TITLE_BAR_WHEN_TABBED = False
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


def _dock_title_set(main_window) -> set[str]:
    """管理中ドックのタイトル集合を返す。"""
    return {dock.windowTitle() for dock in getattr(main_window, "_dock_map", {}).values() if dock}


def _is_dock_related_tab_bar(main_window, bar: QTabBar, titles: set[str] | None = None) -> bool:
    """タブバーが本アプリ管理ドックに関連するか判定する。"""
    if titles is None:
        titles = _dock_title_set(main_window)
    if not titles:
        return False
    for i in range(bar.count()):
        if bar.tabText(i) in titles:
            return True
    return False


def _is_our_tab_close_button(widget) -> bool:
    """本モジュールが付与したタブ閉じるボタンか判定する。"""
    return isinstance(widget, QToolButton) and bool(
        getattr(widget, "_chroma_dock_tab_close_button", False)
    )


def _remove_tab_close_button(bar: QTabBar, idx: int) -> None:
    """指定タブの独自閉じるボタンを除去する。"""
    btn = bar.tabButton(int(idx), QTabBar.RightSide)
    if not _is_our_tab_close_button(btn):
        return
    bar.setTabButton(int(idx), QTabBar.RightSide, None)
    btn.deleteLater()


def _dock_for_tab_text(main_window, text: str) -> QDockWidget | None:
    """タブ文字列から可視タブ化ドックを逆引きする。"""
    if not text:
        return None
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None or not dock.isVisible() or dock.isFloating():
            continue
        if dock.windowTitle() != text:
            continue
        if len(main_window.tabifiedDockWidgets(dock)) <= 0:
            continue
        return dock
    return None


def _close_current_dock_tab(main_window, bar: QTabBar) -> None:
    """現在選択タブに対応するドックを閉じる。"""
    idx = int(bar.currentIndex())
    if idx < 0:
        return
    dock = _dock_for_tab_text(main_window, bar.tabText(idx))
    if dock is None:
        return
    main_window.toggle_dock(dock, False)


def _sync_dock_tab_close_button(main_window, bar: QTabBar, titles: set[str] | None = None) -> None:
    """タブ状態に応じて閉じるボタンの付与/除去を同期する。"""
    if not _is_dock_related_tab_bar(main_window, bar, titles) or bar.count() < 2:
        for i in range(bar.count()):
            _remove_tab_close_button(bar, i)
        return

    current = int(bar.currentIndex())
    if current < 0:
        for i in range(bar.count()):
            _remove_tab_close_button(bar, i)
        return

    for i in range(bar.count()):
        if i != current:
            _remove_tab_close_button(bar, i)

    existing = bar.tabButton(current, QTabBar.RightSide)
    if _is_our_tab_close_button(existing):
        return
    if isinstance(existing, QWidget):
        return

    btn = QToolButton(bar)
    btn._chroma_dock_tab_close_button = True
    btn.setText("x")
    btn.setToolTip("このタブを閉じる")
    btn.setAutoRaise(True)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedSize(16, 16)
    btn.setStyleSheet(
        "QToolButton { border:none; color:#6b7280; padding:0; font-size:13px; font-weight:700; }"
        "QToolButton:hover { color:#dc2626; }"
        "QToolButton:pressed { color:#b91c1c; }"
    )
    btn.clicked.connect(lambda _=False, mw=main_window, b=bar: _close_current_dock_tab(mw, b))
    bar.setTabButton(current, QTabBar.RightSide, btn)


def _sync_dock_tab_bar_event_filters(main_window) -> None:
    """関連タブバーのイベント監視と閉じるボタン同期を行う。"""
    titles = _dock_title_set(main_window)
    seen = []
    for bar in main_window.findChildren(QTabBar):
        try:
            bar.setMovable(True)
        except Exception:
            pass
        is_related = _is_dock_related_tab_bar(main_window, bar, titles)
        if not is_related:
            _sync_dock_tab_close_button(main_window, bar, titles)
            continue
        seen.append(bar)
        if not getattr(bar, "_chroma_dock_tab_filter_installed", False):
            bar.installEventFilter(main_window)
            bar._chroma_dock_tab_filter_installed = True
        if not getattr(bar, "_chroma_dock_tab_close_sync_connected", False):
            bar.currentChanged.connect(
                lambda _idx, mw=main_window, b=bar: _sync_dock_tab_close_button(
                    mw,
                    b,
                    _dock_title_set(mw),
                )
            )
            bar._chroma_dock_tab_close_sync_connected = True
        _sync_dock_tab_close_button(main_window, bar, titles)
    main_window._dock_tab_bars = tuple(seen)


def is_dock_tab_bar(main_window, obj) -> bool:
    """対象オブジェクトが管理対象ドックタブバーか判定する。"""
    if not isinstance(obj, QTabBar):
        return False
    bars = getattr(main_window, "_dock_tab_bars", ())
    return obj in bars


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
    idx = bar.tabAt(pos) if pos is not None else -1
    if idx < 0:
        idx = bar.currentIndex()
    return int(idx)


def _set_tab_drag_state(main_window, bar: QTabBar, idx: int, event) -> None:
    """タブドラッグ状態を初期化して保存する。"""
    main_window._dock_tab_drag_state = {
        "bar": bar,
        "index": int(idx),
        "text": bar.tabText(int(idx)),
        "start_global": _global_pos_from_event(event),
        "triggered": False,
    }


def _handle_tab_drag_press(main_window, bar: QTabBar, event) -> bool:
    """タブドラッグの開始状態を処理する。"""
    if getattr(event, "button", lambda: None)() != Qt.LeftButton:
        return False
    idx = _active_tab_index_for_press(bar, event)
    if idx < 0:
        main_window._dock_tab_drag_state = None
        return False
    _set_tab_drag_state(main_window, bar, idx, event)
    return False


def _detach_dock_if_vertical_drag(main_window, bar: QTabBar, state: dict, event) -> bool:
    """縦方向ドラッグ時のみタブをドックから切り離す。"""
    current = _global_pos_from_event(event)
    start = state.get("start_global")
    if current is None or start is None:
        return False
    dx = int(current.x() - start.x())
    dy = int(current.y() - start.y())
    # 横方向ドラッグはタブ並べ替えへ任せ、縦方向に引いたときだけ切り離す。
    if abs(dy) < _TAB_DETACH_VERTICAL_DRAG_PX or abs(dy) <= abs(dx):
        return False
    dock = _dock_for_tab_text(main_window, str(state.get("text", "")))
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
        win = dock.windowHandle()
    except Exception:
        win = None
    if win is None or not hasattr(win, "startSystemMove"):
        return False
    try:
        return bool(win.startSystemMove())
    except Exception:
        return False


def _hide_dock_title_bar_for_tabbed(dock: QDockWidget) -> None:
    """タブ化されたドックの掴み帯を非表示化する。"""
    if getattr(dock, "_tabbed_title_hidden", False):
        return
    prev_title = dock.titleBarWidget()
    dock._tabbed_prev_titlebar_widget = prev_title
    holder = QWidget(dock)
    holder.setFixedHeight(0)
    holder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    dock.setTitleBarWidget(holder)
    dock._tabbed_title_hidden = True


def _restore_dock_title_bar(dock: QDockWidget) -> None:
    """一時非表示化した掴み帯を復元する。"""
    if not getattr(dock, "_tabbed_title_hidden", False):
        return
    prev_title = getattr(dock, "_tabbed_prev_titlebar_widget", None)
    dock.setTitleBarWidget(prev_title if isinstance(prev_title, QWidget) else None)
    dock._tabbed_prev_titlebar_widget = None
    dock._tabbed_title_hidden = False


def _is_tabbed_dock(
    main_window,
    dock: QDockWidget,
    related_bars: tuple[QTabBar, ...] | None = None,
) -> bool:
    """対象ドックが現在タブ化されているか判定する。"""
    if dock is None or not dock.isVisible() or dock.isFloating():
        return False
    try:
        if len(main_window.tabifiedDockWidgets(dock)) > 0:
            return True
    except Exception:
        pass
    title = str(dock.windowTitle())
    if not title:
        return False
    if related_bars is None:
        titles = _dock_title_set(main_window)
        related_bars = tuple(
            bar
            for bar in main_window.findChildren(QTabBar)
            if bar.count() >= 2 and _is_dock_related_tab_bar(main_window, bar, titles)
        )
    for bar in related_bars:
        for i in range(bar.count()):
            if bar.tabText(i) == title:
                return True
    return False


def handle_dock_tab_bar_event(_main_window, _bar: QTabBar, _event) -> bool:
    """ドックタブバーイベントを監視する。"""
    et = _event.type()
    if et == QEvent.MouseButtonPress:
        return _handle_tab_drag_press(_main_window, _bar, _event)
    if et == QEvent.MouseMove:
        return _handle_tab_drag_move(_main_window, _bar, _event)
    if et in (QEvent.MouseButtonRelease, QEvent.Leave):
        return _handle_tab_drag_end(_main_window, et)
    return False


def sync_tabbed_dock_title_bars(main_window) -> None:
    """タブ化状態に応じて掴み帯表示とタブ同期を更新する。"""
    titles = _dock_title_set(main_window)
    related_bars = tuple(
        bar
        for bar in main_window.findChildren(QTabBar)
        if bar.count() >= 2 and _is_dock_related_tab_bar(main_window, bar, titles)
    )
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None:
            continue
        is_tabbed = _is_tabbed_dock(main_window, dock, related_bars)
        if is_tabbed and _HIDE_DOCK_TITLE_BAR_WHEN_TABBED:
            _hide_dock_title_bar_for_tabbed(dock)
        else:
            _restore_dock_title_bar(dock)
    _sync_dock_tab_bar_event_filters(main_window)
