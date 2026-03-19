"""設定ダイアログの表示制御。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..util import constants as C
from .settings_dialog_pages import build_settings_pages
from .settings_dialog_specs import (
    SETTINGS_NAV_ROW_HEIGHT,
    SETTINGS_NAV_SPECS,
    SETTINGS_PAGE_BINARY,
    SETTINGS_PAGE_TERNARY,
)


def _select_requested_settings_page(main_window, page_index: int | None) -> None:
    """指定ページ番号をナビ行へ変換して選択状態を更新する。"""
    if not hasattr(main_window, "_settings_nav"):
        return

    # 外部からページ指定で開けるよう、行番号へ変換して選択する。
    max_page = C.SETTINGS_PAGE_LAYOUT
    if hasattr(main_window, "_settings_nav_to_page") and main_window._settings_nav_to_page:
        max_page = int(max(main_window._settings_nav_to_page))
    requested_page = (
        getattr(main_window, "_settings_last_page", C.SETTINGS_PAGE_CAPTURE)
        if page_index is None
        else page_index
    )
    page = max(0, min(max_page, int(requested_page)))
    nav_row = (
        main_window._settings_page_to_nav.get(page, 0)
        if hasattr(main_window, "_settings_page_to_nav")
        else 0
    )
    main_window._settings_nav.setCurrentRow(int(nav_row))


def _refresh_settings_nav_layout(main_window) -> None:
    """設定ナビの行高さを固定して、重なりやサイズ揺れを防ぐ。"""
    if not hasattr(main_window, "_settings_nav"):
        return
    nav = main_window._settings_nav
    for index in range(int(nav.count())):
        item = nav.item(index)
        if item is None:
            continue
        hint = item.sizeHint()
        if int(hint.height()) == SETTINGS_NAV_ROW_HEIGHT:
            continue
        hint.setHeight(SETTINGS_NAV_ROW_HEIGHT)
        item.setSizeHint(hint)
    nav.doItemsLayout()
    nav.viewport().update()


def refresh_settings_nav_style(main_window) -> None:
    """テーマ変更後に設定ナビのフォントと行レイアウトを再同期する。"""
    if not hasattr(main_window, "_settings_nav"):
        return
    base_font = getattr(main_window, "_settings_nav_base_font", None)
    if base_font is not None:
        main_window._settings_nav.setFont(QFont(base_font))
    _refresh_settings_nav_layout(main_window)


def _configure_settings_page_mapping(main_window) -> None:
    """ページ番号とナビ行番号の対応表を初期化する。"""
    main_window._settings_nav_to_page = [page for _label, page in SETTINGS_NAV_SPECS]
    main_window._settings_page_to_nav = {
        page: index for index, page in enumerate(main_window._settings_nav_to_page)
    }
    if SETTINGS_PAGE_BINARY in main_window._settings_page_to_nav:
        main_window._settings_page_to_nav[SETTINGS_PAGE_TERNARY] = int(
            main_window._settings_page_to_nav[SETTINGS_PAGE_BINARY]
        )


def show_settings_window(main_window, page_index: int | None = None):
    """設定ダイアログを生成または再利用して指定ページを表示する。"""
    # 表示前にレイアウトプリセット一覧を最新化する。
    main_window.refresh_layout_preset_views()
    created = False
    if not hasattr(main_window, "_settings_window"):
        created = True
        # 設定ダイアログは初回のみ生成し、以後は再利用する。
        main_window._settings_window = QDialog(main_window)
        main_window._settings_window.setWindowTitle("設定")
        main_window._settings_window.setMinimumSize(680, 460)

        root = QHBoxLayout(main_window._settings_window)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        nav = QListWidget()
        nav.setFixedWidth(170)
        nav.setProperty("chromaRole", "settingsNav")
        nav.setFocusPolicy(Qt.NoFocus)
        nav.setUniformItemSizes(True)
        nav.setSpacing(1)
        nav.addItems([label for label, _page in SETTINGS_NAV_SPECS])
        main_window._settings_nav_base_font = QFont(nav.font())

        pages = QStackedWidget()
        build_settings_pages(main_window, pages)
        _configure_settings_page_mapping(main_window)

        def _on_nav_row_changed(row: int):
            """ナビゲーション選択に対応するページを表示する。"""
            # ナビ選択行 -> 実ページindex を変換して表示する。
            if not hasattr(main_window, "_settings_nav_to_page"):
                return
            if row < 0 or row >= len(main_window._settings_nav_to_page):
                return
            page = int(main_window._settings_nav_to_page[row])
            pages.setCurrentIndex(page)
            main_window._settings_last_page = page

        nav.currentRowChanged.connect(_on_nav_row_changed)
        nav.setCurrentRow(0)
        main_window._settings_nav = nav
        refresh_settings_nav_style(main_window)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(8)
        right_l.addWidget(pages, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_close = QPushButton("閉じる")
        btn_close.clicked.connect(main_window._settings_window.close)
        bottom.addWidget(btn_close)
        right_l.addLayout(bottom)

        root.addWidget(nav)
        root.addWidget(right, 1)

    refresh_settings_nav_style(main_window)
    _select_requested_settings_page(main_window, page_index)

    main_window._sync_capture_source_ui()
    main_window._sync_analysis_resolution_rows()
    main_window._sync_mode_dependent_rows()
    main_window._sync_squint_mode_rows()
    if hasattr(main_window, "_sync_color_band_controls"):
        main_window._sync_color_band_controls()
    if created:
        main_window._settings_window.resize(760, 520)
    main_window._present_settings_window(center_on_parent=created)


def hide_settings_window(main_window):
    """設定ダイアログを破棄せずに非表示へ切り替える。"""
    # 破棄せず非表示にする（再表示を速くするため）。
    if hasattr(main_window, "_settings_window"):
        main_window._settings_window.hide()
