"""MainWindow の control widget 構築補助。"""

from .control_widget_common import (
    build_double_spinbox,
    build_int_spinbox,
    populate_data_combo,
    populate_harmony_guide_combo,
    set_widget_unit_label,
)
from .control_widget_sections import (
    build_capture_controls,
    build_layout_controls,
    build_processing_controls,
    build_status_widgets,
    build_view_controls,
    initialize_settings_row_refs,
)

__all__ = [
    "build_control_widgets",
    "build_double_spinbox",
    "build_int_spinbox",
    "populate_data_combo",
    "populate_harmony_guide_combo",
    "set_widget_unit_label",
]


def build_control_widgets(
    main_window,
    *,
    default_preview_window: bool,
    focus_peak_thickness_step: float,
    squint_blur_sigma_step: float,
) -> None:
    """設定・操作に使う入力ウィジェット群を生成する。"""
    build_capture_controls(main_window, default_preview_window=default_preview_window)
    build_view_controls(main_window)
    build_processing_controls(
        main_window,
        focus_peak_thickness_step=focus_peak_thickness_step,
        squint_blur_sigma_step=squint_blur_sigma_step,
    )
    build_layout_controls(main_window)
    initialize_settings_row_refs(main_window)
    build_status_widgets(main_window)
