"""ドックへ影響させない追加テーマ適用補助。"""

from __future__ import annotations

def apply_additional_theme(main_window, theme_name: str | None = None):
    """010 の dock スタイル適用後に、非ドック要素へだけ追加テーマ反映する。"""
    from ...util import theme as ui_theme
    from .. import settings_dialog as settings_dialog_ui

    theme = ui_theme.get_ui_theme(theme_name or getattr(main_window, "_ui_theme_name", None))
    main_window._ui_theme = theme
    main_window._ui_theme_name = theme.name

    settings_dialog_ui.refresh_settings_nav_style(main_window)

    themed_widgets = (
        getattr(main_window, "preview_window", None),
        getattr(main_window, "_canvas_preview_window", None),
    )
    for widget in themed_widgets:
        if widget is not None and hasattr(widget, "set_theme"):
            widget.set_theme(theme)
