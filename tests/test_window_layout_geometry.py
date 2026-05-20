"""window_layout のダイアログ配置回帰テスト。"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt

from chroma_monitor.ui.main_window import window_layout


class _FakeLayout:
    def activate(self) -> None:
        return None


class _FakeDialog:
    def __init__(
        self,
        *,
        x: int = 0,
        y: int = 0,
        width: int = 760,
        height: int = 520,
        visible: bool = False,
        position_initialized: bool = False,
    ) -> None:
        self._x = int(x)
        self._y = int(y)
        self._width = int(width)
        self._height = int(height)
        self._visible = bool(visible)
        self._properties = {
            "_chroma_dialog_position_initialized": bool(position_initialized),
        }

    def ensurePolished(self) -> None:
        return None

    def layout(self):
        return _FakeLayout()

    def sizeHint(self) -> QSize:
        return QSize(self._width, self._height)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def size(self) -> QSize:
        return QSize(self._width, self._height)

    def width(self) -> int:
        return int(self._width)

    def height(self) -> int:
        return int(self._height)

    def resize(self, width: int, height: int) -> None:
        self._width = int(width)
        self._height = int(height)

    def isVisible(self) -> bool:
        return bool(self._visible)

    def frameGeometry(self) -> QRect:
        if self._visible:
            return QRect(self._x, self._y, self._width, self._height)
        return QRect(0, 0, 0, 0)

    def geometry(self) -> QRect:
        return QRect(self._x, self._y, self._width, self._height)

    def move(self, x: int, y: int) -> None:
        self._x = int(x)
        self._y = int(y)

    def setGeometry(self, rect: QRect) -> None:
        self._x = int(rect.x())
        self._y = int(rect.y())
        self._width = int(rect.width())
        self._height = int(rect.height())

    def isWindow(self) -> bool:
        return True

    def property(self, name: str):
        return self._properties.get(str(name))

    def setProperty(self, name: str, value) -> None:
        self._properties[str(name)] = value


class _FakeMainWindow:
    def __init__(self) -> None:
        self._frame = QRect(200, 150, 1000, 700)

    def frameGeometry(self) -> QRect:
        return QRect(self._frame)

    def isVisible(self) -> bool:
        return True


class _FakeTopLevelWidget(_FakeDialog):
    def windowState(self):
        return Qt.WindowStates()


class _FakeHiddenDialogNeedingNativeHandle(_FakeDialog):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.win_id_calls = 0

    def winId(self) -> int:
        self.win_id_calls += 1
        self._x = 0
        self._y = 0
        return 1


def test_fit_dialog_to_desktop_centers_hidden_dialog_without_frame_geometry(monkeypatch) -> None:
    avail = QRect(0, 0, 1600, 900)
    dialog = _FakeDialog()
    main_window = _FakeMainWindow()
    monkeypatch.setattr(
        window_layout,
        "_available_geometry_for_widget",
        lambda _mw, _widget=None: QRect(avail),
    )

    window_layout.fit_dialog_to_desktop(main_window, dialog, center_on_parent=True)

    assert dialog.geometry() == QRect(699, 499, 760, 520)
    assert dialog.property("_chroma_dialog_position_initialized") is False


def test_fit_dialog_to_desktop_recenters_initialized_hidden_dialog_without_frame_geometry(
    monkeypatch,
) -> None:
    avail = QRect(0, 0, 1600, 900)
    dialog = _FakeDialog(x=340, y=220, position_initialized=True)
    main_window = _FakeMainWindow()
    monkeypatch.setattr(
        window_layout,
        "_available_geometry_for_widget",
        lambda _mw, _widget=None: QRect(avail),
    )

    window_layout.fit_dialog_to_desktop(main_window, dialog, center_on_parent=False)

    assert dialog.geometry() == QRect(699, 499, 760, 520)


def test_fit_top_level_widget_to_desktop_uses_hidden_geometry_without_frame_geometry(
    monkeypatch,
) -> None:
    avail = QRect(0, 0, 1600, 900)
    widget = _FakeTopLevelWidget(x=340, y=220, width=420, height=320)
    main_window = _FakeMainWindow()

    def _screen_union_geometry(available=True):
        _ = available
        return QRect(avail)

    monkeypatch.setattr(
        window_layout,
        "_available_geometry_for_widget",
        lambda _mw, _widget=None: QRect(avail),
    )
    monkeypatch.setattr(
        window_layout,
        "screen_union_geometry",
        _screen_union_geometry,
    )

    window_layout.fit_top_level_widget_to_desktop(
        main_window,
        widget,
        allow_resize=False,
    )

    assert widget.geometry() == QRect(340, 220, 420, 320)


