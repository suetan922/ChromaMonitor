"""canvas_preview_dialog の起動回帰テスト。"""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

from chroma_monitor.ui import canvas_preview_dialog
from chroma_monitor.util import constants as C
from chroma_monitor.util.theme import build_palette, get_ui_theme
from chroma_monitor.util.theme_stylesheet import build_app_stylesheet
from chroma_monitor.views.canvas_preview_constants import (
    CANVAS_PREVIEW_BACKGROUND_DARK,
    CANVAS_PREVIEW_BACKGROUND_LIGHT,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_canvas_preview_dialog_init_completes_and_logs_steps(monkeypatch) -> None:
    log_dir = os.path.join(os.getcwd(), ".tmp_canvas_preview_tests")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "canvas_preview_ui_debug.log")
    monkeypatch.setenv(C.DEBUG_UI_LOG_ENV, "1")
    monkeypatch.setenv(C.DEBUG_UI_LOG_PATH_ENV, str(log_path))
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {C.CFG_CANVAS_RATIO_PRESETS: []},
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = None
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="test",
        title="test.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()

    assert dialog.list_ratio_presets.count() > 0
    assert dialog.radio_landscape.isChecked() is True
    assert dialog.radio_portrait.isChecked() is False
    assert dialog.btn_background_light.isChecked() is True
    assert dialog.btn_background_dark.isChecked() is False
    assert dialog.slider_preview_zoom.value() == 100
    assert dialog.lbl_preview_zoom_value.text() == "100%"
    assert dialog.btn_preview_zoom_reset.text() == "100%"
    assert hasattr(dialog, "btn_preview_zoom_fit") is False
    assert dialog.preview_widget._image.isNull() is False
    assert hasattr(dialog, "btn_actual") is False
    assert "全体表示" not in {button.text() for button in dialog.findChildren(QPushButton)}
    assert dialog.isModal() is False
    assert dialog.isSizeGripEnabled() is True
    assert bool(dialog.windowFlags() & Qt.WindowMinimizeButtonHint)
    assert bool(dialog.windowFlags() & Qt.WindowMaximizeButtonHint)
    assert bool(dialog.windowFlags() & Qt.WindowCloseButtonHint)

    dialog.close()
    main_window.close()
    app.processEvents()

    with open(log_path, "r", encoding="utf-8") as handle:
        log_text = handle.read()
    assert "canvas_preview_apply_initial_state_step_ok" in log_text
    assert "stage='apply_fit_mode'" in log_text
    assert "canvas_preview_apply_initial_state_ok" in log_text


def test_canvas_preview_dialog_prefers_saved_background_tone(monkeypatch) -> None:
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {
            C.CFG_CANVAS_RATIO_PRESETS: [],
            C.CFG_CANVAS_PREVIEW_BACKGROUND_TONE: CANVAS_PREVIEW_BACKGROUND_LIGHT,
        },
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = C.UI_THEME_DARK
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="test",
        title="test.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()

    assert dialog._background_tone == CANVAS_PREVIEW_BACKGROUND_LIGHT
    assert dialog.btn_background_light.isChecked() is True
    assert dialog.btn_background_dark.isChecked() is False

    dialog.close()
    main_window.close()
    app.processEvents()


def test_canvas_preview_dialog_uses_dark_background_by_default_in_dark_theme(monkeypatch) -> None:
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {C.CFG_CANVAS_RATIO_PRESETS: []},
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = C.UI_THEME_DARK
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="test",
        title="test.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()

    assert dialog._background_tone == CANVAS_PREVIEW_BACKGROUND_DARK
    assert dialog.btn_background_light.isChecked() is False
    assert dialog.btn_background_dark.isChecked() is True

    dialog.close()
    main_window.close()
    app.processEvents()


def test_canvas_preview_dialog_uses_light_background_by_default_in_light_theme(monkeypatch) -> None:
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {C.CFG_CANVAS_RATIO_PRESETS: []},
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = C.UI_THEME_LIGHT
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="test",
        title="test.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()

    assert dialog._background_tone == CANVAS_PREVIEW_BACKGROUND_LIGHT
    assert dialog.btn_background_light.isChecked() is True
    assert dialog.btn_background_dark.isChecked() is False

    dialog.close()
    main_window.close()
    app.processEvents()


def test_builtin_preset_can_save_name_only_and_user_preset_can_edit_all(monkeypatch) -> None:
    saved_configs: list[dict] = []
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {
            C.CFG_CANVAS_RATIO_PRESETS: [
                {
                    "id": "user_custom_scope",
                    "name": "カスタム比率",
                    "ratio_w": 2.39,
                    "ratio_h": 1.0,
                }
            ]
        },
    )
    monkeypatch.setattr(
        canvas_preview_dialog,
        "save_config",
        lambda cfg: saved_configs.append(dict(cfg)),
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = None
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="test",
        title="test.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()

    assert dialog.edit_preset_name.isEnabled() is True
    assert dialog.btn_save_preset.isEnabled() is True
    assert dialog.spin_preset_ratio_w.isEnabled() is False
    assert dialog.spin_preset_ratio_h.isEnabled() is False
    assert dialog.btn_delete_preset.isEnabled() is False
    assert (
        dialog.btn_delete_preset.toolTip()
        == canvas_preview_dialog._BUILTIN_PRESET_DELETE_TOOLTIP
    )
    assert "標準プリセットは削除できません" not in {
        label.text() for label in dialog.findChildren(QLabel)
    }
    assert all(
        not label.text().startswith("元画像:")
        for label in dialog.findChildren(QLabel)
    )

    dialog.edit_preset_name.setText("定番")
    dialog.btn_save_preset.click()
    app.processEvents()

    assert saved_configs
    saved_payload = saved_configs[-1][C.CFG_CANVAS_RATIO_PRESETS]
    saved_builtin = next(item for item in saved_payload if item["id"] == "standard_4_3")
    assert saved_builtin["name"] == "定番"
    assert "ratio_w" not in saved_builtin
    assert "ratio_h" not in saved_builtin
    assert dialog._current_preset().ratio_w == 4.0
    assert dialog._current_preset().ratio_h == 3.0

    user_index = next(
        index
        for index, preset in enumerate(dialog._visible_presets())
        if preset.preset_id == "user_custom_scope"
    )
    dialog.list_ratio_presets.setCurrentRow(user_index)
    app.processEvents()

    assert dialog.edit_preset_name.isEnabled() is True
    assert dialog.btn_save_preset.isEnabled() is True
    assert dialog.btn_save_preset.toolTip() == ""
    assert dialog.spin_preset_ratio_w.isEnabled() is True
    assert dialog.spin_preset_ratio_h.isEnabled() is True
    assert dialog.btn_delete_preset.isEnabled() is True
    assert dialog.btn_delete_preset.toolTip() == ""

    dialog.close()
    main_window.close()
    app.processEvents()


def test_canvas_preview_dialog_uses_generic_export_filename(monkeypatch) -> None:
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {C.CFG_CANVAS_RATIO_PRESETS: []},
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = None
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="loaded image",
        title="読み込み画像.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()

    assert dialog._suggest_output_path(".png") == "canvas_preview.png"

    dialog.close()
    main_window.close()
    app.processEvents()


def test_canvas_preview_dialog_center_and_individual_resets_keep_roles_separate(monkeypatch) -> None:
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {C.CFG_CANVAS_RATIO_PRESETS: []},
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = C.UI_THEME_LIGHT
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="test",
        title="test.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()

    display_layout = dialog.btn_fit.parentWidget().layout()
    assert isinstance(display_layout, QVBoxLayout)
    assert display_layout.indexOf(dialog.btn_fit) == 0
    assert display_layout.indexOf(dialog.btn_fill) == 1
    assert display_layout.indexOf(dialog.btn_center) == 2
    assert dialog.btn_fit.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding
    assert dialog.btn_fill.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding
    assert dialog.btn_center.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding

    expected_reset_tooltips = {
        dialog.btn_reset_offset_x: "X位置を初期値に戻す",
        dialog.btn_reset_offset_y: "Y位置を初期値に戻す",
        dialog.btn_reset_scale: "拡大率を初期値に戻す",
    }
    for button, tooltip in expected_reset_tooltips.items():
        assert isinstance(button, QToolButton)
        assert button.text() == ""
        assert button.toolTip() == tooltip
        assert button.accessibleName() == tooltip
        assert button.icon().isNull() is False
        assert button.iconSize().width() == 28
        assert button.iconSize().height() == 28
        assert button.minimumSizeHint().width() >= 20
        assert button.icon().pixmap(button.iconSize()).isNull() is False

    dialog._set_transform(offset_x=24.0, offset_y=-18.0, scale=1.7)
    app.processEvents()
    dialog.btn_center.click()
    app.processEvents()
    assert dialog._transform.offset_x == 0.0
    assert dialog._transform.offset_y == 0.0
    assert dialog._transform.scale == 1.7

    dialog._set_transform(offset_x=24.0, offset_y=-18.0, scale=1.7)
    app.processEvents()
    dialog.btn_reset_offset_x.click()
    app.processEvents()
    assert dialog._transform.offset_x == 0.0
    assert dialog._transform.offset_y == -18.0
    assert dialog._transform.scale == 1.7

    dialog._set_transform(offset_x=24.0, offset_y=-18.0, scale=1.7)
    app.processEvents()
    dialog.btn_reset_offset_y.click()
    app.processEvents()
    assert dialog._transform.offset_x == 24.0
    assert dialog._transform.offset_y == 0.0
    assert dialog._transform.scale == 1.7

    dialog._set_transform(offset_x=24.0, offset_y=-18.0, scale=1.7)
    app.processEvents()
    dialog.btn_reset_scale.click()
    app.processEvents()
    assert dialog._transform.offset_x == 24.0
    assert dialog._transform.offset_y == -18.0
    assert dialog._transform.scale == 1.0

    dialog.close()
    main_window.close()
    app.processEvents()


def test_reset_icon_from_palette_returns_icons_for_light_and_dark_themes(monkeypatch) -> None:
    canvas_preview_dialog._clear_reset_icon_caches()
    source = QPixmap(24, 24)
    source.fill(Qt.white)
    monkeypatch.setattr(
        canvas_preview_dialog,
        "_load_reset_icon_source_pixmap",
        lambda: source,
    )

    app = _app()
    for theme_name in (C.UI_THEME_LIGHT, C.UI_THEME_DARK):
        app.setPalette(build_palette(get_ui_theme(theme_name)))
        button = QToolButton()
        button.ensurePolished()
        icon = canvas_preview_dialog._reset_icon_from_palette(button)

        assert isinstance(icon, QIcon)
        assert icon.isNull() is False
        assert icon.pixmap(canvas_preview_dialog._RESET_ICON_SIZE).isNull() is False
        assert (
            icon.pixmap(
                canvas_preview_dialog._RESET_ICON_SIZE,
                QIcon.Disabled,
                QIcon.Off,
            ).isNull()
            is False
        )
    canvas_preview_dialog._clear_reset_icon_caches()


def test_source_alpha_bounding_rect_ignores_transparent_padding() -> None:
    source = QPixmap(64, 64)
    source.fill(Qt.transparent)
    painter = QPainter(source)
    try:
        painter.fillRect(20, 18, 24, 28, Qt.white)
    finally:
        painter.end()

    rect = canvas_preview_dialog._source_alpha_bounding_rect(source)

    assert rect.isValid() is True
    assert rect.x() == 20
    assert rect.y() == 18
    assert rect.width() == 24
    assert rect.height() == 28


def test_tinted_icon_pixmap_keeps_reset_icon_visibly_large_after_crop() -> None:
    source = QPixmap(64, 64)
    source.fill(Qt.transparent)
    painter = QPainter(source)
    try:
        painter.fillRect(20, 18, 24, 28, Qt.white)
    finally:
        painter.end()

    tinted = canvas_preview_dialog._tinted_icon_pixmap(
        source,
        QColor("white"),
        size=canvas_preview_dialog._RESET_ICON_SIZE,
        device_pixel_ratio=1.0,
    )
    bbox = canvas_preview_dialog._source_alpha_bounding_rect(tinted)

    assert tinted.isNull() is False
    assert bbox.isValid() is True
    assert bbox.width() >= 20
    assert bbox.height() >= 20


def test_reset_icon_from_palette_falls_back_to_qstyle_reload_icon_when_asset_missing() -> None:
    canvas_preview_dialog._clear_reset_icon_caches()
    app = _app()
    button = QToolButton()
    button.ensurePolished()

    original_paths = canvas_preview_dialog._reset_icon_asset_paths
    try:
        canvas_preview_dialog._reset_icon_asset_paths = lambda: ()
        pixmap = canvas_preview_dialog._reset_icon_pixmap(
            button.palette().color(button.foregroundRole()),
            size=canvas_preview_dialog._RESET_ICON_SIZE,
            device_pixel_ratio=float(button.devicePixelRatioF()),
            widget=button,
        )
        icon = canvas_preview_dialog._reset_icon_from_palette(button)
    finally:
        canvas_preview_dialog._reset_icon_asset_paths = original_paths

    assert isinstance(pixmap, QPixmap)
    assert pixmap.isNull() is False
    assert isinstance(icon, QIcon)
    assert icon.isNull() is False
    assert icon.pixmap(canvas_preview_dialog._RESET_ICON_SIZE).isNull() is False
    canvas_preview_dialog._clear_reset_icon_caches()


def test_canvas_preview_dialog_background_toggle_persists_selection(monkeypatch) -> None:
    saved_configs: list[dict] = []
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {C.CFG_CANVAS_RATIO_PRESETS: []},
    )
    monkeypatch.setattr(
        canvas_preview_dialog,
        "save_config",
        lambda cfg: saved_configs.append(dict(cfg)),
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = C.UI_THEME_DARK
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="test",
        title="test.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()
    dialog.btn_background_light.click()
    app.processEvents()

    assert saved_configs
    assert (
        saved_configs[-1][C.CFG_CANVAS_PREVIEW_BACKGROUND_TONE]
        == CANVAS_PREVIEW_BACKGROUND_LIGHT
    )

    dialog.close()
    main_window.close()
    app.processEvents()


def test_canvas_preview_dialog_dark_stylesheet_defines_radio_indicator_states() -> None:
    stylesheet = build_app_stylesheet(get_ui_theme(C.UI_THEME_DARK))

    assert "QRadioButton::indicator:unchecked" in stylesheet
    assert "QRadioButton::indicator:checked" in stylesheet
    assert "QRadioButton::indicator:disabled" in stylesheet
    assert "qradialgradient" in stylesheet
    assert "QRadioButton::indicator:unchecked:hover" in stylesheet


def test_app_stylesheet_uses_attached_baseline_tab_bar_style() -> None:
    stylesheet = build_app_stylesheet(get_ui_theme(C.UI_THEME_DARK))

    assert 'QTabBar[chromaDockTabBar="true"]::tab' not in stylesheet
    assert "QTabBar::tab:bottom" not in stylesheet
    assert "border-top-left-radius:4px" in stylesheet
    assert "border-top-right-radius:4px" in stylesheet


def test_canvas_preview_dialog_uses_single_ratio_list_and_wrapping_info_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {C.CFG_CANVAS_RATIO_PRESETS: []},
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = None
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="test",
        title="test.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()

    left_holder = dialog.layout().itemAt(0).widget()
    left_layout = left_holder.layout()
    assert left_layout.stretch(0) == 1
    assert left_layout.stretch(1) == 0
    assert hasattr(dialog, "list_ratio_presets") is True
    assert hasattr(dialog, "list_builtin_presets") is False
    assert hasattr(dialog, "list_user_presets") is False
    assert dialog.list_ratio_presets.sizePolicy().verticalPolicy() == QSizePolicy.Expanding
    assert dialog.lbl_info_source_size.text() == "160 x 120 px"
    assert dialog.lbl_info_margin.wordWrap() is True
    assert dialog.lbl_info_crop.wordWrap() is True
    assert dialog.lbl_info_margin.hasHeightForWidth() is True
    assert dialog.lbl_info_crop.hasHeightForWidth() is True
    assert dialog.lbl_info_margin.sizePolicy().verticalPolicy() != QSizePolicy.Fixed
    assert dialog.lbl_info_crop.sizePolicy().verticalPolicy() != QSizePolicy.Fixed
    assert dialog.lbl_info_margin.maximumHeight() > dialog.lbl_info_margin.fontMetrics().height()
    assert dialog.lbl_info_crop.maximumHeight() > dialog.lbl_info_crop.fontMetrics().height()
    assert {"W", "H"} <= {label.text() for label in dialog.findChildren(QLabel)}
    assert "元画像サイズ" in {
        label.text() for label in dialog.findChildren(QLabel)
    }

    dialog.close()
    main_window.close()
    app.processEvents()


def test_canvas_preview_dialog_new_user_preset_starts_editable_and_keeps_fixed_ratio_label(
    monkeypatch,
) -> None:
    saved_payloads: list[dict] = []
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {C.CFG_CANVAS_RATIO_PRESETS: []},
    )
    monkeypatch.setattr(
        canvas_preview_dialog,
        "save_config",
        lambda cfg: saved_payloads.append(dict(cfg)),
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = None
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="test",
        title="test.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()

    assert len(dialog._saved_user_presets()) == 0
    initial_count = dialog.list_ratio_presets.count()

    dialog.btn_add_preset.click()
    app.processEvents()

    assert dialog._draft_preset is not None
    assert len(dialog._saved_user_presets()) == 0
    assert dialog.list_ratio_presets.count() == initial_count + 1
    assert dialog.edit_preset_name.isEnabled() is True
    assert dialog.spin_preset_ratio_w.isEnabled() is True
    assert dialog.spin_preset_ratio_h.isEnabled() is True
    assert saved_payloads == []

    dialog.edit_preset_name.setText("縦長")
    dialog.spin_preset_ratio_w.setValue(4.0)
    dialog.spin_preset_ratio_h.setValue(5.0)
    dialog.btn_save_preset.click()
    app.processEvents()

    assert dialog._draft_preset is None
    assert len(dialog._saved_user_presets()) == 1
    assert len(saved_payloads) == 1
    assert dialog.list_ratio_presets.currentItem().text() == "縦長"

    landscape_canvas = dialog._current_canvas_pixels()
    dialog.radio_portrait.setChecked(True)
    app.processEvents()
    portrait_canvas = dialog._current_canvas_pixels()

    assert dialog.list_ratio_presets.currentItem().text() == "縦長"
    assert portrait_canvas == (128, 160)
    assert landscape_canvas == (160, 128)

    dialog.close()
    main_window.close()
    app.processEvents()


def test_canvas_preview_dialog_uses_same_label_rule_for_builtin_special_and_user_presets(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        canvas_preview_dialog,
        "load_config",
        lambda: {
            C.CFG_CANVAS_RATIO_PRESETS: [
                {
                    "id": "user_custom_scope",
                    "name": "シネマ",
                    "ratio_w": 2.39,
                    "ratio_h": 1.0,
                }
            ]
        },
    )

    app = _app()
    main_window = QMainWindow()
    main_window._ui_theme_name = None
    snapshot = canvas_preview_dialog.CanvasPreviewSnapshot(
        bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        source_label="test",
        title="test.png",
    )

    dialog = canvas_preview_dialog.CanvasPreviewDialog(main_window, snapshot)
    app.processEvents()

    visible_labels = {
        preset.preset_id: dialog.list_ratio_presets.item(index).text()
        for index, preset in enumerate(dialog._visible_presets())
    }

    assert visible_labels["standard_4_3"] == "4:3"
    assert visible_labels["standard_golden_ratio"] == "黄金比"
    assert visible_labels["standard_silver_ratio"] == "白銀比"
    assert visible_labels["user_custom_scope"] == "シネマ"
    assert all("|" not in text for text in visible_labels.values())
    assert all("φ" not in text for text in visible_labels.values())
    assert all("√2:1" not in text for text in visible_labels.values())

    dialog.close()
    main_window.close()
    app.processEvents()
