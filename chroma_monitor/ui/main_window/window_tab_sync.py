"""ドックタブの同期と close button 補助。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QSizePolicy, QTabBar, QToolButton, QWidget

_HIDE_DOCK_TITLE_BAR_WHEN_TABBED = False


def dock_title_set(main_window) -> set[str]:
    """管理中ドックのタイトル集合を返す。"""
    return {dock.windowTitle() for dock in getattr(main_window, "_dock_map", {}).values() if dock}


def is_dock_related_tab_bar(
    main_window,
    bar: QTabBar,
    titles: set[str] | None = None,
) -> bool:
    """タブバーが本アプリ管理ドックに関連するか判定する。"""
    if titles is None:
        titles = dock_title_set(main_window)
    if not titles:
        return False
    for index in range(bar.count()):
        if bar.tabText(index) in titles:
            return True
    return False


def _is_our_tab_close_button(widget) -> bool:
    """本モジュールが付与したタブ閉じるボタンか判定する。"""
    return isinstance(widget, QToolButton) and bool(
        getattr(widget, "_chroma_dock_tab_close_button", False)
    )


def _remove_tab_close_button(bar: QTabBar, index: int) -> None:
    """指定タブの独自閉じるボタンを除去する。"""
    button = bar.tabButton(int(index), QTabBar.RightSide)
    if not _is_our_tab_close_button(button):
        return
    bar.setTabButton(int(index), QTabBar.RightSide, None)
    button.deleteLater()


def dock_for_tab_text(main_window, text: str) -> QDockWidget | None:
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
    index = int(bar.currentIndex())
    if index < 0:
        return
    dock = dock_for_tab_text(main_window, bar.tabText(index))
    if dock is None:
        return
    main_window.toggle_dock(dock, False)


def _sync_dock_tab_close_button(
    main_window,
    bar: QTabBar,
    titles: set[str] | None = None,
) -> None:
    """タブ状態に応じて閉じるボタンの付与/除去を同期する。"""
    if not is_dock_related_tab_bar(main_window, bar, titles) or bar.count() < 2:
        for index in range(bar.count()):
            _remove_tab_close_button(bar, index)
        return

    current = int(bar.currentIndex())
    if current < 0:
        for index in range(bar.count()):
            _remove_tab_close_button(bar, index)
        return

    for index in range(bar.count()):
        if index != current:
            _remove_tab_close_button(bar, index)

    existing = bar.tabButton(current, QTabBar.RightSide)
    if _is_our_tab_close_button(existing):
        return
    if isinstance(existing, QWidget):
        return

    button = QToolButton(bar)
    button._chroma_dock_tab_close_button = True
    button.setText("x")
    button.setToolTip("このタブを閉じる")
    button.setAutoRaise(True)
    button.setCursor(Qt.PointingHandCursor)
    button.setFixedSize(16, 16)
    button.clicked.connect(lambda _=False, mw=main_window, b=bar: _close_current_dock_tab(mw, b))
    bar.setTabButton(current, QTabBar.RightSide, button)


def _sync_dock_tab_bar_event_filters(main_window) -> None:
    """関連タブバーのイベント監視と閉じるボタン同期を行う。"""
    titles = dock_title_set(main_window)
    seen = []
    for bar in main_window.findChildren(QTabBar):
        try:
            bar.setMovable(True)
        except Exception:
            pass
        is_related = is_dock_related_tab_bar(main_window, bar, titles)
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
                    dock_title_set(mw),
                )
            )
            bar._chroma_dock_tab_close_sync_connected = True
        _sync_dock_tab_close_button(main_window, bar, titles)
    main_window._dock_tab_bars = tuple(seen)


def is_dock_tab_bar(main_window, obj) -> bool:
    """対象オブジェクトが管理対象ドックタブバーか判定する。"""
    if not isinstance(obj, QTabBar):
        return False
    return obj in getattr(main_window, "_dock_tab_bars", ())


def _hide_dock_title_bar_for_tabbed(dock: QDockWidget) -> None:
    """タブ化されたドックの掴み帯を非表示化する。"""
    if getattr(dock, "_tabbed_title_hidden", False):
        return
    previous = dock.titleBarWidget()
    dock._tabbed_prev_titlebar_widget = previous
    holder = QWidget(dock)
    holder.setFixedHeight(0)
    holder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    dock.setTitleBarWidget(holder)
    dock._tabbed_title_hidden = True


def _restore_dock_title_bar(dock: QDockWidget) -> None:
    """一時非表示化した掴み帯を復元する。"""
    if not getattr(dock, "_tabbed_title_hidden", False):
        return
    previous = getattr(dock, "_tabbed_prev_titlebar_widget", None)
    dock.setTitleBarWidget(previous if isinstance(previous, QWidget) else None)
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
        titles = dock_title_set(main_window)
        related_bars = tuple(
            bar
            for bar in main_window.findChildren(QTabBar)
            if bar.count() >= 2 and is_dock_related_tab_bar(main_window, bar, titles)
        )
    for bar in related_bars:
        for index in range(bar.count()):
            if bar.tabText(index) == title:
                return True
    return False


def sync_tabbed_dock_title_bars(main_window) -> None:
    """タブ化状態に応じて掴み帯表示とタブ同期を更新する。"""
    titles = dock_title_set(main_window)
    related_bars = tuple(
        bar
        for bar in main_window.findChildren(QTabBar)
        if bar.count() >= 2 and is_dock_related_tab_bar(main_window, bar, titles)
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
