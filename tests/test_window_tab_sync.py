"""window_tabs の dock tab bar 同期テスト。"""

from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication, QMainWindow, QTabBar

from chroma_monitor.ui.main_window import window_tabs

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FakeDock:
    def __init__(self, title: str) -> None:
        self._title = str(title)

    def windowTitle(self) -> str:
        return self._title

    def isVisible(self) -> bool:
        return True

    def isFloating(self) -> bool:
        return False


class _FakeMainWindow(QMainWindow):
    def __init__(self, bar: QTabBar) -> None:
        super().__init__()
        self._dock_map = {"dock_a": _FakeDock("A"), "dock_b": _FakeDock("B")}
        self._dock_tab_bars = ()
        self._force_dock_drop_active = False
        self._bar = bar

    def findChildren(self, cls):
        if cls is QTabBar:
            return [self._bar]
        return []

    def tabifiedDockWidgets(self, _dock):
        return [object()]


def test_sync_tabbed_dock_title_bars_keeps_dock_tabs_movable_for_detach() -> None:
    app = _app()
    bar = QTabBar()
    bar.addTab("A")
    bar.addTab("B")
    bar.setMovable(True)
    main_window = _FakeMainWindow(bar)

    window_tabs.sync_tabbed_dock_title_bars(main_window)

    assert bar.isMovable() is True
    assert main_window._dock_tab_bars == (bar,)

    bar.close()
    app.processEvents()
