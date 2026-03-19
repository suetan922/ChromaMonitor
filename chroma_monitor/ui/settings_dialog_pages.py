"""設定ダイアログ各ページの構築処理。"""

from PySide6.QtWidgets import QStackedWidget

from .settings_dialog_page_sections import (
    add_app_settings_page,
    add_capture_settings_page,
    add_color_analysis_pages,
    add_image_processing_pages,
    add_image_view_tuning_pages,
    add_layout_settings_page,
    add_legacy_and_app_pages,
    add_update_settings_page,
)


def build_settings_pages(main_window, pages: QStackedWidget) -> None:
    """設定ダイアログ内の各設定ページを順番どおりに構築する。"""
    add_capture_settings_page(main_window, pages)
    add_update_settings_page(main_window, pages)
    add_color_analysis_pages(main_window, pages)
    add_image_processing_pages(main_window, pages)
    add_layout_settings_page(main_window, pages)
    add_legacy_and_app_pages(main_window, pages)
    add_image_view_tuning_pages(main_window, pages)
    add_app_settings_page(main_window, pages)
