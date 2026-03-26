"""input_widgets の回帰テスト。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMenu, QPushButton

from chroma_monitor.ui.input_widgets import SplitMenuToolButton
from chroma_monitor.util.theme import get_ui_theme
from chroma_monitor.util.theme_stylesheet import build_app_stylesheet


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_split_menu_tool_button_matches_run_button_height_and_reserves_menu_space() -> None:
    app = _app()
    app.setStyleSheet(build_app_stylesheet(get_ui_theme(None)))

    start_button = QPushButton("Start")
    start_button.setObjectName("runStartBtn")
    load_button = SplitMenuToolButton()
    load_button.setObjectName("fileLoadSplitButton")
    load_button.setText("ファイル読込")
    load_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
    load_button.setPopupMode(SplitMenuToolButton.MenuButtonPopup)
    load_button.setMenu(QMenu(load_button))

    for widget in (start_button, load_button):
        widget.ensurePolished()
    load_button.resize(load_button.sizeHint())

    text_width = load_button.fontMetrics().horizontalAdvance(load_button.text())
    menu_width = load_button._menu_button_rect().width()

    assert load_button.sizeHint().height() == start_button.sizeHint().height()
    assert load_button.minimumSizeHint().width() >= text_width + menu_width + 16
