"""設定UI状態から保存用 payload を組み立てる処理。"""

from ...util import constants as C
from ...util.qt_helpers import rect_to_dict
from .settings_selected_values import (
    selected_wheel_harmony_guide_rotation,
)
from .settings_value_specs import (
    ANALYSIS_MAX_DIM_SPEC,
    ANALYSIS_RESOLUTION_MODE_SPEC,
    BINARY_PRESET_SPEC,
    COLOR_BAND_HARMONY_GUIDE_ENABLED_SPEC,
    COLOR_BAND_HARMONY_GUIDE_TYPE_SPEC,
    COLOR_BAND_SAT_THRESHOLD_SPEC,
    COLOR_BAND_USE_WHEEL_HARMONY_SPEC,
    COLOR_BAND_USE_WHEEL_SAT_THRESHOLD_SPEC,
    COMPOSITION_GUIDE_SPEC,
    DIFF_THRESHOLD_SPEC,
    EDGE_SENSITIVITY_SPEC,
    FOCUS_PEAK_COLOR_SPEC,
    FOCUS_PEAK_SENSITIVITY_SPEC,
    FOCUS_PEAK_THICKNESS_SPEC,
    INTERVAL_SPEC,
    MIRROR_MODE_SPEC,
    MODE_SPEC,
    RGB_HIST_MODE_SPEC,
    SALIENCY_OVERLAY_ALPHA_SPEC,
    SAMPLE_POINTS_SPEC,
    SCATTER_HUE_CENTER_SPEC,
    SCATTER_HUE_FILTER_ENABLED_SPEC,
    SCATTER_RENDER_MODE_SPEC,
    SCATTER_SHAPE_SPEC,
    SQUINT_BLUR_SIGMA_SPEC,
    SQUINT_MODE_SPEC,
    SQUINT_SCALE_PERCENT_SPEC,
    STABLE_FRAMES_SPEC,
    TERNARY_PRESET_SPEC,
    UI_THEME_SPEC,
    VECTORSCOPE_SHOW_SKIN_LINE_SPEC,
    VECTORSCOPE_WARN_THRESHOLD_SPEC,
    WHEEL_HARMONY_GUIDE_ENABLED_SPEC,
    WHEEL_HARMONY_GUIDE_TYPE_SPEC,
    WHEEL_MODE_SPEC,
    WHEEL_SAT_THRESHOLD_SPEC,
    collect_settings_from_specs,
)

_SIMPLE_SETTINGS_PAYLOAD_SPECS = (
    INTERVAL_SPEC,
    SAMPLE_POINTS_SPEC,
    ANALYSIS_MAX_DIM_SPEC,
    ANALYSIS_RESOLUTION_MODE_SPEC,
    UI_THEME_SPEC,
    SCATTER_SHAPE_SPEC,
    SCATTER_RENDER_MODE_SPEC,
    SCATTER_HUE_FILTER_ENABLED_SPEC,
    SCATTER_HUE_CENTER_SPEC,
    WHEEL_MODE_SPEC,
    RGB_HIST_MODE_SPEC,
    MIRROR_MODE_SPEC,
    WHEEL_SAT_THRESHOLD_SPEC,
    WHEEL_HARMONY_GUIDE_ENABLED_SPEC,
    WHEEL_HARMONY_GUIDE_TYPE_SPEC,
    COLOR_BAND_USE_WHEEL_SAT_THRESHOLD_SPEC,
    COLOR_BAND_SAT_THRESHOLD_SPEC,
    COLOR_BAND_USE_WHEEL_HARMONY_SPEC,
    COLOR_BAND_HARMONY_GUIDE_ENABLED_SPEC,
    COLOR_BAND_HARMONY_GUIDE_TYPE_SPEC,
    MODE_SPEC,
    DIFF_THRESHOLD_SPEC,
    STABLE_FRAMES_SPEC,
    EDGE_SENSITIVITY_SPEC,
    BINARY_PRESET_SPEC,
    TERNARY_PRESET_SPEC,
    SALIENCY_OVERLAY_ALPHA_SPEC,
    COMPOSITION_GUIDE_SPEC,
    FOCUS_PEAK_SENSITIVITY_SPEC,
    FOCUS_PEAK_COLOR_SPEC,
    FOCUS_PEAK_THICKNESS_SPEC,
    SQUINT_MODE_SPEC,
    SQUINT_SCALE_PERCENT_SPEC,
    SQUINT_BLUR_SIGMA_SPEC,
    VECTORSCOPE_SHOW_SKIN_LINE_SPEC,
    VECTORSCOPE_WARN_THRESHOLD_SPEC,
)


def _selected_capture_window_title(main_window) -> str:
    """現在選択されているキャプチャ対象ウィンドウ名を返す。"""
    combo = main_window.combo_win
    index = int(combo.currentIndex())
    if index < 0 or combo.itemData(index) is None:
        return ""
    return str(combo.itemText(index)).strip()


def _selected_capture_window_text(main_window) -> str:
    """現在のキャプチャ対象入力欄テキストを返す。"""
    return str(main_window.combo_win.currentText() or "").strip()


def _selected_capture_screen_roi_abs_logical(main_window):
    """現在の画面ROI(論理座標)を返す。"""
    capture = main_window.worker.capture_selection()
    roi_abs_native = capture.roi_abs
    if roi_abs_native is None:
        return None
    try:
        return main_window.worker.native_rect_to_logical(roi_abs_native)
    except (AttributeError, TypeError, ValueError):
        return None


def selected_capture_settings_payload(main_window) -> dict:
    """キャプチャ対象の保存用ペイロードを返す。"""
    capture = main_window.worker.capture_selection()
    return {
        C.CFG_CAPTURE_SOURCE: main_window._selected_capture_source(),
        C.CFG_CAPTURE_WINDOW_TITLE: _selected_capture_window_title(main_window),
        C.CFG_CAPTURE_WINDOW_TEXT: _selected_capture_window_text(main_window),
        C.CFG_CAPTURE_WINDOW_ROI_REL: rect_to_dict(capture.roi_rel),
        C.CFG_CAPTURE_SCREEN_ROI_ABS: rect_to_dict(
            _selected_capture_screen_roi_abs_logical(main_window)
        ),
    }


def collect_settings_payload(main_window) -> dict:
    """現在UI状態から保存用設定辞書を組み立てる。"""
    return {
        **collect_settings_from_specs(main_window, _SIMPLE_SETTINGS_PAYLOAD_SPECS),
        **selected_capture_settings_payload(main_window),
        C.CFG_WHEEL_HARMONY_GUIDE_ROTATION: selected_wheel_harmony_guide_rotation(main_window),
        C.CFG_ALWAYS_ON_TOP: main_window._is_always_on_top_enabled(),
    }
