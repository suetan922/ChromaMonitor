"""canvas_preview_dialog の起動回帰テスト。"""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QSizePolicy

from chroma_monitor.ui import canvas_preview_dialog
from chroma_monitor.util import constants as C

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_canvas_preview_dialog_init_completes_and_logs_steps(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "canvas_preview_ui_debug.log"
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
    assert dialog.preview_widget._image.isNull() is False
    assert dialog.isModal() is False
    assert dialog.isSizeGripEnabled() is True
    assert bool(dialog.windowFlags() & Qt.WindowMinimizeButtonHint)
    assert bool(dialog.windowFlags() & Qt.WindowMaximizeButtonHint)
    assert bool(dialog.windowFlags() & Qt.WindowCloseButtonHint)

    dialog.close()
    main_window.close()
    app.processEvents()

    log_text = log_path.read_text(encoding="utf-8")
    assert "canvas_preview_apply_initial_state_step_ok" in log_text
    assert "stage='apply_fit_mode'" in log_text
    assert "canvas_preview_apply_initial_state_ok" in log_text


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
