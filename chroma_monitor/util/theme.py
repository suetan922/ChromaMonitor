"""アプリ全体のテーマ定義と共通スタイル補助。"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QAbstractItemView, QWidget

from .theme_definitions import UiTheme, get_ui_theme
from .theme_stylesheet import build_app_stylesheet


def qcolor(value: str, alpha: int | None = None) -> QColor:
    """16進色文字列から QColor を返す。"""
    color = QColor(str(value))
    if alpha is not None:
        color.setAlpha(int(alpha))
    return color


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """16進色文字列を RGB タプルへ変換する。"""
    color = qcolor(value)
    return (int(color.red()), int(color.green()), int(color.blue()))


def hex_to_bgr(value: str) -> tuple[int, int, int]:
    """16進色文字列を BGR タプルへ変換する。"""
    r, g, b = hex_to_rgb(value)
    return (b, g, r)


def refresh_widget_style(widget) -> None:
    """動的プロパティ変更後にスタイルを再評価する。"""
    if widget is None:
        return
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    # PySide6 on Windows can resolve QListWidget.update() to the item-view overload
    # instead of QWidget.update(), which raises `takes exactly one argument`.
    QWidget.update(widget)
    if isinstance(widget, QAbstractItemView):
        viewport = widget.viewport()
        if viewport is not None:
            QWidget.update(viewport)


def build_palette(theme: UiTheme) -> QPalette:
    """Qt全体へ流し込む基本パレットを生成する。"""
    palette = QPalette()
    palette.setColor(QPalette.Window, qcolor(theme.window_bg))
    palette.setColor(QPalette.WindowText, qcolor(theme.text_primary))
    palette.setColor(QPalette.Base, qcolor(theme.input_bg))
    palette.setColor(QPalette.AlternateBase, qcolor(theme.panel_alt_bg))
    palette.setColor(QPalette.ToolTipBase, qcolor(theme.menu_bg))
    palette.setColor(QPalette.ToolTipText, qcolor(theme.text_primary))
    palette.setColor(QPalette.Text, qcolor(theme.text_primary))
    palette.setColor(QPalette.Button, qcolor(theme.button_bg))
    palette.setColor(QPalette.ButtonText, qcolor(theme.text_primary))
    palette.setColor(QPalette.BrightText, qcolor(theme.text_inverse))
    palette.setColor(QPalette.Highlight, qcolor(theme.accent))
    palette.setColor(QPalette.HighlightedText, qcolor(theme.text_inverse))
    palette.setColor(QPalette.PlaceholderText, qcolor(theme.text_muted))

    palette.setColor(QPalette.Disabled, QPalette.WindowText, qcolor(theme.text_disabled))
    palette.setColor(QPalette.Disabled, QPalette.Text, qcolor(theme.text_disabled))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, qcolor(theme.text_disabled))
    palette.setColor(QPalette.Disabled, QPalette.Base, qcolor(theme.input_disabled_bg))
    palette.setColor(QPalette.Disabled, QPalette.Button, qcolor(theme.input_disabled_bg))
    return palette


__all__ = [
    "UiTheme",
    "build_app_stylesheet",
    "build_palette",
    "get_ui_theme",
    "hex_to_bgr",
    "hex_to_rgb",
    "qcolor",
    "refresh_widget_style",
]
