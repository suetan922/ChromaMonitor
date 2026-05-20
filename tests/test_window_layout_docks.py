"""window_layout の DockOptions 同期テスト。"""

from __future__ import annotations

import os

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from chroma_monitor.ui.main_window import window_layout
from chroma_monitor.ui.main_window.window_layout import (
    _DOCK_OPTIONS_BASE,
    _DOCK_OPTIONS_NESTED,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FakeDock:
    def __init__(
        self,
        *,
        visible: bool = True,
        floating: bool = True,
        move_drag_active: bool = False,
    ) -> None:
        self._visible = bool(visible)
        self._floating = bool(floating)
        self._floating_move_drag_active = bool(move_drag_active)

    def isVisible(self) -> bool:
        return bool(self._visible)

    def isFloating(self) -> bool:
        return bool(self._floating)


class _FakeMainWindow:
    def __init__(self, *docks: _FakeDock) -> None:
        self._dock_map = {f"dock_{index}": dock for index, dock in enumerate(docks)}
        self._dock_options = _DOCK_OPTIONS_BASE
        self._set_options_calls = []
        self._force_dock_drop_active = False
        self._tabify_calls = []

    def dockOptions(self):
        return self._dock_options

    def setDockOptions(self, options) -> None:
        self._dock_options = options
        self._set_options_calls.append(options)

    def frameGeometry(self) -> QRect:
        return QRect(100, 100, 800, 600)

    def isVisible(self) -> bool:
        return True

    def tabifyDockWidget(self, anchor, dock) -> None:
        self._tabify_calls.append((anchor, dock, self._dock_options))


def test_sync_dock_options_uses_nested_without_visible_floating() -> None:
    main_window = _FakeMainWindow(_FakeDock(visible=False, floating=True))

    window_layout._sync_dock_options_by_floating_state(main_window)

    assert main_window.dockOptions() == _DOCK_OPTIONS_NESTED
    assert main_window._set_options_calls == [_DOCK_OPTIONS_NESTED]


def test_sync_dock_options_keeps_base_for_idle_visible_floating() -> None:
    main_window = _FakeMainWindow(_FakeDock(visible=True, floating=True))

    window_layout._sync_dock_options_by_floating_state(main_window)

    assert main_window.dockOptions() == _DOCK_OPTIONS_BASE
    assert main_window._set_options_calls == []


def test_sync_dock_options_uses_nested_when_drag_is_near_main_window(monkeypatch) -> None:
    monkeypatch.setattr(
        window_layout,
        "_is_dock_drop_active_near_main_window",
        lambda _mw, *, has_active_drag=None: True,
    )
    main_window = _FakeMainWindow(
        _FakeDock(visible=True, floating=True, move_drag_active=True)
    )

    window_layout._sync_dock_options_by_floating_state(main_window)

    assert main_window.dockOptions() == _DOCK_OPTIONS_NESTED
    assert main_window._set_options_calls == [_DOCK_OPTIONS_NESTED]


def test_sync_dock_options_uses_nested_when_force_drop_active() -> None:
    app = _app()
    main_window = _FakeMainWindow(_FakeDock(visible=True, floating=True))
    main_window._force_dock_drop_active = True

    window_layout._sync_dock_options_by_floating_state(main_window)

    assert main_window.dockOptions() == _DOCK_OPTIONS_NESTED
    assert main_window._set_options_calls == [_DOCK_OPTIONS_NESTED]
    app.processEvents()


def test_sync_dock_options_ignores_hidden_floating_drag_transition(monkeypatch) -> None:
    main_window = _FakeMainWindow(
        _FakeDock(visible=True, floating=True),
        _FakeDock(visible=False, floating=True),
    )
    monkeypatch.setattr(window_layout, "_is_left_mouse_dragging", lambda: True)

    window_layout._sync_dock_options_by_floating_state(main_window)

    assert main_window.dockOptions() == _DOCK_OPTIONS_BASE
    assert main_window._set_options_calls == []
