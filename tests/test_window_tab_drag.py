"""window_tabs の標準 dock drag 維持テスト。"""

from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QMainWindow, QTabBar

from chroma_monitor.ui.main_window import window_tabs

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FakeMoveEvent:
    def __init__(self, global_pos: QPoint) -> None:
        self._global_pos = QPoint(global_pos)

    def globalPos(self) -> QPoint:
        return QPoint(self._global_pos)


class _FakeDock:
    def __init__(self) -> None:
        self.floating_values = []
        self.moves = []
        self.raised = False
        self.activated = False

    def setFloating(self, floating: bool) -> None:
        self.floating_values.append(bool(floating))

    def frameGeometry(self) -> QRect:
        return QRect(0, 0, 240, 160)

    def move(self, x_pos: int, y_pos: int) -> None:
        self.moves.append((int(x_pos), int(y_pos)))

    def raise_(self) -> None:
        self.raised = True

    def activateWindow(self) -> None:
        self.activated = True


def test_tab_vertical_drag_floats_dock_and_consumes_event(monkeypatch) -> None:
    app = _app()
    main_window = QMainWindow()
    main_window._force_dock_drop_active = False
    main_window._sync_all_floating_dock_dockability = lambda: None
    main_window._schedule_layout_autosave = lambda: None
    bar = QTabBar()
    dock = _FakeDock()
    system_move_calls = []
    monkeypatch.setattr(window_tabs, "_dock_for_tab_text", lambda _mw, _text: dock)
    monkeypatch.setattr(window_tabs, "sync_tabbed_dock_title_bars", lambda _mw: None)
    monkeypatch.setattr(
        window_tabs,
        "_start_system_move_for_dock",
        lambda target: system_move_calls.append(target) or True,
    )
    state = {
        "bar": bar,
        "index": 0,
        "text": "dock",
        "start_global": QPoint(100, 100),
        "triggered": False,
    }

    consumed = window_tabs._detach_dock_if_vertical_drag(
        main_window,
        bar,
        state,
        _FakeMoveEvent(QPoint(103, 150)),
    )

    assert consumed is True
    assert state["triggered"] is True
    assert main_window._force_dock_drop_active is True
    assert dock.floating_values == [True]
    assert dock.moves == [(7, 138)]
    assert dock.raised is True
    assert dock.activated is True
    assert system_move_calls == [dock]
    assert main_window._dock_tab_drag_state is None

    window_tabs.clear_force_dock_drop_active(main_window)
    bar.close()
    main_window.close()
    app.processEvents()


def test_tab_release_after_vertical_drag_only_clears_force_drop() -> None:
    app = _app()
    main_window = QMainWindow()
    main_window._force_dock_drop_active = True
    main_window._sync_all_floating_dock_dockability = lambda: None
    main_window._dock_tab_drag_state = {
        "bar": QTabBar(),
        "index": 0,
        "text": "dock",
        "start_global": QPoint(100, 100),
        "triggered": True,
    }

    consumed = window_tabs._handle_tab_drag_end(
        main_window,
        window_tabs.QEvent.MouseButtonRelease,
    )

    assert consumed is False
    assert main_window._force_dock_drop_active is False

    main_window._dock_tab_drag_state["bar"].close()
    main_window.close()
    app.processEvents()
