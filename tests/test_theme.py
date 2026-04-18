"""theme の回帰テスト。"""

from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication, QListWidget, QLabel

from chroma_monitor.util.theme import refresh_widget_style

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_refresh_widget_style_handles_list_widgets() -> None:
    _app()
    widget = QListWidget()
    widget.addItem("one")

    refresh_widget_style(widget)
    refresh_widget_style(widget.viewport())

    assert widget.count() == 1


def test_refresh_widget_style_handles_basic_widgets() -> None:
    _app()
    label = QLabel("hello")

    refresh_widget_style(label)

    assert label.text() == "hello"
