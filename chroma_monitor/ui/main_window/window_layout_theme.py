"""`window_layout` から分離したテーマ・表示補助。"""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QAbstractButton

from ...util.qt_helpers import blocked_signals


def apply_ui_style(main_window, theme_name: str | None = None):
    """アプリ全体スタイルと主要カスタムビューへテーマを反映する。"""
    from ...util import theme as ui_theme
    from .. import settings_dialog as settings_dialog_ui
    from . import result_color_band as color_band_ui
    from . import settings_logic as settings_ui

    theme = ui_theme.get_ui_theme(theme_name or getattr(main_window, "_ui_theme_name", None))
    main_window._ui_theme = theme
    main_window._ui_theme_name = theme.name

    app = QApplication.instance()
    if app is not None:
        app.setPalette(ui_theme.build_palette(theme))
        app.setStyleSheet(ui_theme.build_app_stylesheet(theme))

    settings_dialog_ui.refresh_settings_nav_style(main_window)
    retint_dock_title_button_icons(main_window, theme)
    QTimer.singleShot(
        0,
        lambda mw=main_window, th=theme: retint_dock_title_button_icons(mw, th),
    )

    themed_widgets = (
        getattr(main_window, "preview_window", None),
        getattr(main_window, "wheel", None),
        getattr(main_window, "scatter", None),
        getattr(main_window, "hist_h", None),
        getattr(main_window, "hist_s", None),
        getattr(main_window, "hist_v", None),
        getattr(main_window, "rgb_hist_view", None),
        getattr(main_window, "vectorscope_view", None),
        getattr(main_window, "_canvas_preview_window", None),
    )
    for widget in themed_widgets:
        if widget is not None and hasattr(widget, "set_theme"):
            widget.set_theme(theme)

    color_band_ui.apply_color_band_theme(main_window, theme)
    if hasattr(main_window, "_update_vectorscope_warning_label"):
        settings_ui.update_vectorscope_warning_label(main_window)


def _tinted_icon(icon: QIcon, *, color: QColor, size: QSize) -> QIcon:
    """既存アイコン形状を維持したまま指定色へ着色した `QIcon` を返す。"""
    pixmap = icon.pixmap(size)
    if pixmap.isNull():
        return QIcon(icon)
    tinted = QPixmap(pixmap.size())
    tinted.setDevicePixelRatio(pixmap.devicePixelRatio())
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()
    return QIcon(tinted)


def retint_dock_title_button_icons(main_window, theme) -> None:
    """ドックのフロート/閉じるボタンは形状を維持したまま色だけ更新する。"""
    tint = QColor(str(getattr(theme, "text_primary", "")))
    if not tint.isValid():
        return
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None:
            continue
        for button in dock.findChildren(QAbstractButton):
            name = str(button.objectName() or "")
            if name not in ("qt_dockwidget_floatbutton", "qt_dockwidget_closebutton"):
                continue
            base_icon = getattr(button, "_chroma_base_icon", None)
            if not isinstance(base_icon, QIcon) or base_icon.isNull():
                current_icon = button.icon()
                if current_icon.isNull():
                    continue
                base_icon = QIcon(current_icon)
                button._chroma_base_icon = base_icon
            icon_size = button.iconSize()
            if (not icon_size.isValid()) or int(icon_size.width()) <= 0 or int(icon_size.height()) <= 0:
                icon_size = QSize(12, 12)
            button.setIcon(_tinted_icon(base_icon, color=tint, size=icon_size))


def sync_window_menu_checks(main_window, *_):
    """ウィンドウメニューのチェック状態を実際の表示状態へ合わせる。"""
    for name, dock in main_window._dock_map.items():
        act = main_window._dock_actions.get(name)
        if act is None:
            continue
        with blocked_signals(act):
            act.setChecked(dock.isVisible())
