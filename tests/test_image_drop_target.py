"""image_drop_target の回帰テスト。"""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from chroma_monitor.views.image_drop_target import (
    DockAreaImageDropController,
    _apply_overlay_label_style,
    _extract_supported_drop_paths,
    dock_area_overlay_rect,
    dock_area_union_rect,
)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FakeDock:
    def __init__(self, rect: QRect, *, visible: bool = True, floating: bool = False) -> None:
        self._rect = QRect(rect)
        self._visible = bool(visible)
        self._floating = bool(floating)

    def isVisible(self) -> bool:
        return self._visible

    def isFloating(self) -> bool:
        return self._floating

    def geometry(self) -> QRect:
        return QRect(self._rect)


class _FakeOverlay:
    def __init__(self) -> None:
        self.styles: list[str] = []

    def setStyleSheet(self, stylesheet: str) -> None:
        self.styles.append(str(stylesheet))


class _FakeUrl:
    def __init__(self, path: str, *, local: bool = True) -> None:
        self._path = str(path)
        self._local = bool(local)

    def isLocalFile(self) -> bool:
        return self._local

    def toLocalFile(self) -> str:
        return self._path


class _FakeMimeData:
    def __init__(self, urls) -> None:
        self._urls = list(urls)

    def hasUrls(self) -> bool:
        return bool(self._urls)

    def urls(self):
        return list(self._urls)


def test_dock_area_union_rect_uses_visible_non_floating_docks_only() -> None:
    rect = dock_area_union_rect(
        (
            _FakeDock(QRect(10, 20, 100, 80)),
            _FakeDock(QRect(120, 30, 80, 120)),
            _FakeDock(QRect(0, 0, 400, 40), visible=False),
            _FakeDock(QRect(0, 0, 400, 400), floating=True),
        )
    )

    assert rect == QRect(10, 20, 190, 130)


def test_dock_area_overlay_rect_falls_back_when_no_visible_docks() -> None:
    fallback = QRect(16, 24, 320, 180)

    rect = dock_area_overlay_rect(
        (
            _FakeDock(QRect(10, 20, 100, 80), visible=False),
            _FakeDock(QRect(120, 30, 80, 120), floating=True),
        ),
        fallback,
    )

    assert rect == fallback


def test_dock_area_drop_controller_uses_central_widget_when_all_docks_hidden() -> None:
    app = _app()
    main_window = QMainWindow()
    main_window.resize(640, 480)
    central = QWidget()
    main_window.setCentralWidget(central)
    main_window.show()
    app.processEvents()

    controller = DockAreaImageDropController(
        main_window,
        dock_widgets=(),
        path_filter=lambda _path: True,
        can_drop_callback=lambda: True,
        drop_handler=lambda _paths: None,
    )

    assert central.acceptDrops() is True
    assert controller._dock_area_rect() == central.geometry()
    main_window.close()


def test_apply_overlay_label_style_skips_reapply_when_theme_is_unchanged() -> None:
    overlay = _FakeOverlay()

    style_key = _apply_overlay_label_style(overlay, theme_name=None, cached_key=None)
    repeated_key = _apply_overlay_label_style(overlay, theme_name=None, cached_key=style_key)

    assert repeated_key == style_key
    assert len(overlay.styles) == 1


def test_extract_supported_drop_paths_filters_duplicates_and_non_matching_files() -> None:
    mime_data = _FakeMimeData(
        (
            _FakeUrl("C:/images/a.png"),
            _FakeUrl("C:/images/a.png"),
            _FakeUrl("C:/images/b.jpg"),
            _FakeUrl("C:/images/remote.png", local=False),
        )
    )

    paths = _extract_supported_drop_paths(
        mime_data,
        lambda path: str(path).lower().endswith(".png"),
    )

    assert paths == ["C:/images/a.png"]
