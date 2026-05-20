"""theme の回帰テスト。"""

from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication, QListWidget, QLabel

from chroma_monitor.util.theme import get_ui_theme, refresh_widget_style
from chroma_monitor.util.theme_stylesheet import build_app_stylesheet

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


def test_build_app_stylesheet_includes_dark_theme_selectors() -> None:
    dark = build_app_stylesheet(get_ui_theme("dark"))
    light = build_app_stylesheet(get_ui_theme("light"))
    dark_theme = get_ui_theme("dark")

    for token in (
        "#161A20",
        "#202631",
        "#242B36",
        "#E5E7EB",
        'QLabel[chromaRole="status"]',
        'QLabel[chromaRole="placeholder"]',
        'QLabel[chromaRole="vectorscopeWarning"]',
        'QLabel[chromaRole="detailText"]',
        'QLabel[chromaRole="detailTitle"]',
        'QLabel[chromaRole="infoLabel"]',
        'QListWidget[chromaRole="colorChipList"]',
        "QSlider#scatterHueSlider",
        "QLabel#scatterHueValue",
        "QToolButton#fileLoadSplitButton",
        "QToolButton#fileLoadSplitButton:focus",
        "QToolButton#fileLoadSplitButton:hover:focus",
        "QToolButton#fileLoadSplitButton:pressed:focus",
        "QToolButton#fileLoadSplitButton:open",
        "QToolButton#fileLoadSplitButton:open:focus",
        "QToolButton#fileLoadSplitButton::menu-button:open",
        "QTabBar::tab",
        "border-top-left-radius:0px;",
        "border-top-right-radius:0px;",
    ):
        assert token in dark

    focus_block = (
        "QToolButton#fileLoadSplitButton:focus {{\n"
        "            outline:none;\n"
        f"            background:{dark_theme.panel_alt_bg};\n"
        f"            border:1px solid {dark_theme.border_strong};\n"
        f"            color:{dark_theme.text_primary};\n"
        "        }}"
    )
    open_block = (
        "QToolButton#fileLoadSplitButton:open {{\n"
        "            outline:none;\n"
        f"            background:{dark_theme.button_pressed_bg};\n"
        f"            border:1px solid {dark_theme.border_strong};\n"
        f"            color:{dark_theme.text_primary};\n"
        "        }}"
    )
    assert focus_block in dark
    assert open_block in dark
    assert f"background:{dark_theme.accent};" not in focus_block
    assert f"background:{dark_theme.accent};" not in open_block
    assert "border-top-left-radius:4px;" not in dark
    assert "border-top-right-radius:4px;" not in dark
    assert dark != light
