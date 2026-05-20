"""window_topmost の設定ウィンドウ表示回帰テスト。"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt

from chroma_monitor.ui.main_window import window_topmost


class _FakeSettingsWindow:
    def __init__(self, calls: list[str], *, visible: bool = False) -> None:
        self._calls = calls
        self._state = Qt.WindowStates()
        self._visible = bool(visible)

    def windowState(self):
        return self._state

    def setWindowState(self, state) -> None:
        self._state = state
        self._calls.append("setWindowState")

    def isVisible(self) -> bool:
        return bool(self._visible)

    def hide(self) -> None:
        self._visible = False

    def showNormal(self) -> None:
        self._visible = True
        self._calls.append("showNormal")

    def show(self) -> None:
        self._visible = True
        self._calls.append("show")

    def raise_(self) -> None:
        self._calls.append("raise")

    def activateWindow(self) -> None:
        self._calls.append("activate")


class _FakeRestoredWindow:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls
        self._geometry = QRect(0, 0, 100, 100)

    def isWindow(self) -> bool:
        return True

    def geometry(self) -> QRect:
        return QRect(self._geometry)

    def setGeometry(self, rect: QRect) -> None:
        self._geometry = QRect(rect)
        self._calls.append(f"setGeometry:{int(rect.x())},{int(rect.y())}")

    def show(self) -> None:
        self._calls.append("show")

    def raise_(self) -> None:
        self._calls.append("raise")

    def activateWindow(self) -> None:
        self._calls.append("activate")


def test_present_settings_window_fits_before_show(monkeypatch) -> None:
    calls: list[str] = []
    window = _FakeSettingsWindow(calls)

    class _FakeMainWindow:
        def __init__(self) -> None:
            self._settings_window = window

        def _fit_dialog_to_desktop(self, widget, center_on_parent: bool = False) -> None:
            assert widget is window
            calls.append(f"fit:{center_on_parent}")

    main_window = _FakeMainWindow()
    monkeypatch.setattr(window_topmost, "set_widget_on_top", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(window_topmost, "is_always_on_top_enabled", lambda _mw: False)

    window_topmost.present_settings_window(main_window, center_on_parent=True)

    assert calls == ["fit:True", "show", "raise", "activate"]


def test_present_settings_window_refits_before_hidden_redisplay(monkeypatch) -> None:
    calls: list[str] = []
    window = _FakeSettingsWindow(calls)

    class _FakeMainWindow:
        def __init__(self) -> None:
            self._settings_window = window

        def _fit_dialog_to_desktop(self, widget, center_on_parent: bool = False) -> None:
            assert widget is window
            calls.append(f"fit:{center_on_parent}")

    main_window = _FakeMainWindow()
    monkeypatch.setattr(window_topmost, "set_widget_on_top", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(window_topmost, "is_always_on_top_enabled", lambda _mw: False)

    window_topmost.present_settings_window(main_window, center_on_parent=True)
    window.hide()
    calls.clear()

    window_topmost.present_settings_window(main_window, center_on_parent=False)

    assert calls == ["fit:False", "show", "raise", "activate"]


def test_present_top_level_widget_reapplies_on_top_after_hidden_show(monkeypatch) -> None:
    calls: list[str] = []
    window = _FakeSettingsWindow(calls)
    monkeypatch.setattr(
        window_topmost,
        "set_widget_on_top",
        lambda _mw, _widget, enabled: calls.append(f"on_top:{enabled}"),
    )

    window_topmost.present_top_level_widget(
        object(),
        window,
        fit_before_show=lambda: calls.append("fit"),
        on_top=True,
    )

    assert calls == ["on_top:True", "fit", "show", "on_top:True", "raise", "activate"]


def test_restore_visibility_after_flag_change_restores_geometry_before_show(monkeypatch) -> None:
    calls: list[str] = []
    window = _FakeRestoredWindow(calls)
    monkeypatch.setattr(window_topmost, "HAS_WIN32", False)

    window_topmost._restore_visibility_after_flag_change(
        window,
        desired=False,
        was_active=False,
        saved_geometry=QRect(120, 140, 400, 300),
    )

    assert calls == ["show", "setGeometry:120,140"]
