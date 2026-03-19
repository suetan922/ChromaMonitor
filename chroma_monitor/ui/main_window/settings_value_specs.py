"""設定UIの単純な widget 値を spec で扱う共通定義。"""

from dataclasses import dataclass

from ...util import constants as C
from ...util.qt_helpers import set_checked_blocked
from ...util.value_utils import clamp_float
from .settings_value_common import (
    apply_combo_choice,
    cfg_float,
    cfg_int,
    selected_checked_attr,
    selected_combo_attr,
    selected_int_attr,
    set_value_blocked,
)


@dataclass(frozen=True, slots=True)
class ComboSettingSpec:
    """コンボボックス由来の設定値定義。"""

    attr_name: str
    cfg_key: str
    allowed: tuple[str, ...]
    default: str


@dataclass(frozen=True, slots=True)
class BoolSettingSpec:
    """チェック系ウィジェット由来の設定値定義。"""

    attr_name: str
    cfg_key: str
    default: bool


@dataclass(frozen=True, slots=True)
class IntSettingSpec:
    """整数入力ウィジェット由来の設定値定義。"""

    attr_name: str
    cfg_key: str
    default: int
    low: int
    high: int


@dataclass(frozen=True, slots=True)
class FloatSettingSpec:
    """浮動小数入力ウィジェット由来の設定値定義。"""

    attr_name: str
    cfg_key: str
    default: float
    low: float | None = None
    high: float | None = None


SettingSpec = ComboSettingSpec | BoolSettingSpec | IntSettingSpec | FloatSettingSpec
_INTERVAL_MIN_SEC = 0.10

INTERVAL_SPEC = FloatSettingSpec(
    "spin_interval",
    C.CFG_INTERVAL,
    C.DEFAULT_INTERVAL_SEC,
    _INTERVAL_MIN_SEC,
    10.0,
)
SAMPLE_POINTS_SPEC = IntSettingSpec(
    "spin_points",
    C.CFG_SAMPLE_POINTS,
    C.DEFAULT_SAMPLE_POINTS,
    C.ANALYZER_MIN_SAMPLE_POINTS,
    C.ANALYZER_MAX_SAMPLE_POINTS,
)
ANALYSIS_MAX_DIM_SPEC = IntSettingSpec(
    "edit_analysis_max_dim",
    C.CFG_ANALYZER_MAX_DIM,
    C.ANALYZER_MAX_DIM,
    C.ANALYZER_MAX_DIM_MIN,
    C.ANALYZER_MAX_DIM_MAX,
)
ANALYSIS_RESOLUTION_MODE_SPEC = ComboSettingSpec(
    "combo_analysis_resolution_mode",
    C.CFG_ANALYSIS_RESOLUTION_MODE,
    C.ANALYSIS_RESOLUTION_MODES,
    C.DEFAULT_ANALYSIS_RESOLUTION_MODE,
)
UI_THEME_SPEC = ComboSettingSpec(
    "combo_ui_theme",
    C.CFG_UI_THEME,
    C.UI_THEMES,
    C.DEFAULT_UI_THEME,
)
SCATTER_SHAPE_SPEC = ComboSettingSpec(
    "combo_scatter_shape",
    C.CFG_SCATTER_SHAPE,
    C.SCATTER_SHAPES,
    C.DEFAULT_SCATTER_SHAPE,
)
SCATTER_RENDER_MODE_SPEC = ComboSettingSpec(
    "combo_scatter_render_mode",
    C.CFG_SCATTER_RENDER_MODE,
    C.SCATTER_RENDER_MODES,
    C.DEFAULT_SCATTER_RENDER_MODE,
)
SCATTER_HUE_FILTER_ENABLED_SPEC = BoolSettingSpec(
    "chk_scatter_hue_filter",
    C.CFG_SCATTER_HUE_FILTER_ENABLED,
    C.DEFAULT_SCATTER_HUE_FILTER_ENABLED,
)
SCATTER_HUE_CENTER_SPEC = IntSettingSpec(
    "slider_scatter_hue_center",
    C.CFG_SCATTER_HUE_CENTER,
    C.DEFAULT_SCATTER_HUE_CENTER,
    C.SCATTER_HUE_MIN,
    C.SCATTER_HUE_MAX,
)
WHEEL_MODE_SPEC = ComboSettingSpec(
    "combo_wheel_mode",
    C.CFG_WHEEL_MODE,
    C.WHEEL_MODES,
    C.DEFAULT_WHEEL_MODE,
)
RGB_HIST_MODE_SPEC = ComboSettingSpec(
    "combo_rgb_hist_mode",
    C.CFG_RGB_HIST_MODE,
    C.RGB_HIST_MODES,
    C.DEFAULT_RGB_HIST_MODE,
)
MIRROR_MODE_SPEC = ComboSettingSpec(
    "combo_mirror_mode",
    C.CFG_MIRROR_MODE,
    C.MIRROR_MODES,
    C.DEFAULT_MIRROR_MODE,
)
WHEEL_SAT_THRESHOLD_SPEC = IntSettingSpec(
    "spin_wheel_sat_threshold",
    C.CFG_WHEEL_SAT_THRESHOLD,
    C.DEFAULT_WHEEL_SAT_THRESHOLD,
    C.WHEEL_SAT_THRESHOLD_MIN,
    C.WHEEL_SAT_THRESHOLD_MAX,
)
WHEEL_HARMONY_GUIDE_ENABLED_SPEC = BoolSettingSpec(
    "chk_wheel_harmony_guide",
    C.CFG_WHEEL_HARMONY_GUIDE_ENABLED,
    C.DEFAULT_WHEEL_HARMONY_GUIDE_ENABLED,
)
WHEEL_HARMONY_GUIDE_TYPE_SPEC = ComboSettingSpec(
    "combo_wheel_harmony_guide",
    C.CFG_WHEEL_HARMONY_GUIDE_TYPE,
    C.WHEEL_HARMONY_GUIDE_TYPES,
    C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE,
)
COLOR_BAND_USE_WHEEL_SAT_THRESHOLD_SPEC = BoolSettingSpec(
    "chk_color_band_use_wheel_sat_threshold",
    C.CFG_COLOR_BAND_USE_WHEEL_SAT_THRESHOLD,
    C.DEFAULT_COLOR_BAND_USE_WHEEL_SAT_THRESHOLD,
)
COLOR_BAND_SAT_THRESHOLD_SPEC = IntSettingSpec(
    "spin_color_band_sat_threshold",
    C.CFG_COLOR_BAND_SAT_THRESHOLD,
    C.DEFAULT_COLOR_BAND_SAT_THRESHOLD,
    C.WHEEL_SAT_THRESHOLD_MIN,
    C.WHEEL_SAT_THRESHOLD_MAX,
)
COLOR_BAND_USE_WHEEL_HARMONY_SPEC = BoolSettingSpec(
    "chk_color_band_use_wheel_harmony",
    C.CFG_COLOR_BAND_USE_WHEEL_HARMONY,
    C.DEFAULT_COLOR_BAND_USE_WHEEL_HARMONY,
)
COLOR_BAND_HARMONY_GUIDE_ENABLED_SPEC = BoolSettingSpec(
    "chk_color_band_harmony_guide",
    C.CFG_COLOR_BAND_HARMONY_GUIDE_ENABLED,
    C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_ENABLED,
)
COLOR_BAND_HARMONY_GUIDE_TYPE_SPEC = ComboSettingSpec(
    "combo_color_band_harmony_guide",
    C.CFG_COLOR_BAND_HARMONY_GUIDE_TYPE,
    C.WHEEL_HARMONY_GUIDE_TYPES,
    C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_TYPE,
)
CAPTURE_SOURCE_SPEC = ComboSettingSpec(
    "combo_capture_source",
    C.CFG_CAPTURE_SOURCE,
    C.CAPTURE_SOURCES,
    C.DEFAULT_CAPTURE_SOURCE,
)
EDGE_SENSITIVITY_SPEC = IntSettingSpec(
    "spin_edge_sensitivity",
    C.CFG_EDGE_SENSITIVITY,
    C.DEFAULT_EDGE_SENSITIVITY,
    C.EDGE_SENSITIVITY_MIN,
    C.EDGE_SENSITIVITY_MAX,
)
BINARY_PRESET_SPEC = ComboSettingSpec(
    "combo_binary_preset",
    C.CFG_BINARY_PRESET,
    C.BINARY_PRESETS,
    C.DEFAULT_BINARY_PRESET,
)
TERNARY_PRESET_SPEC = ComboSettingSpec(
    "combo_ternary_preset",
    C.CFG_TERNARY_PRESET,
    C.TERNARY_PRESETS,
    C.DEFAULT_TERNARY_PRESET,
)
SALIENCY_OVERLAY_ALPHA_SPEC = IntSettingSpec(
    "spin_saliency_alpha",
    C.CFG_SALIENCY_OVERLAY_ALPHA,
    C.DEFAULT_SALIENCY_OVERLAY_ALPHA,
    C.SALIENCY_ALPHA_MIN,
    C.SALIENCY_ALPHA_MAX,
)
COMPOSITION_GUIDE_SPEC = ComboSettingSpec(
    "combo_composition_guide",
    C.CFG_COMPOSITION_GUIDE,
    C.COMPOSITION_GUIDES,
    C.DEFAULT_COMPOSITION_GUIDE,
)
FOCUS_PEAK_SENSITIVITY_SPEC = IntSettingSpec(
    "spin_focus_peak_sensitivity",
    C.CFG_FOCUS_PEAK_SENSITIVITY,
    C.DEFAULT_FOCUS_PEAK_SENSITIVITY,
    C.FOCUS_PEAK_SENSITIVITY_MIN,
    C.FOCUS_PEAK_SENSITIVITY_MAX,
)
FOCUS_PEAK_COLOR_SPEC = ComboSettingSpec(
    "combo_focus_peak_color",
    C.CFG_FOCUS_PEAK_COLOR,
    C.FOCUS_PEAK_COLORS,
    C.DEFAULT_FOCUS_PEAK_COLOR,
)
FOCUS_PEAK_THICKNESS_SPEC = FloatSettingSpec(
    "spin_focus_peak_thickness",
    C.CFG_FOCUS_PEAK_THICKNESS,
    C.DEFAULT_FOCUS_PEAK_THICKNESS,
    C.FOCUS_PEAK_THICKNESS_MIN,
    C.FOCUS_PEAK_THICKNESS_MAX,
)
SQUINT_MODE_SPEC = ComboSettingSpec(
    "combo_squint_mode",
    C.CFG_SQUINT_MODE,
    C.SQUINT_MODES,
    C.DEFAULT_SQUINT_MODE,
)
SQUINT_SCALE_PERCENT_SPEC = IntSettingSpec(
    "spin_squint_scale",
    C.CFG_SQUINT_SCALE_PERCENT,
    C.DEFAULT_SQUINT_SCALE_PERCENT,
    C.SQUINT_SCALE_PERCENT_MIN,
    C.SQUINT_SCALE_PERCENT_MAX,
)
SQUINT_BLUR_SIGMA_SPEC = FloatSettingSpec(
    "spin_squint_blur",
    C.CFG_SQUINT_BLUR_SIGMA,
    C.DEFAULT_SQUINT_BLUR_SIGMA,
    C.SQUINT_BLUR_SIGMA_MIN,
    C.SQUINT_BLUR_SIGMA_MAX,
)
VECTORSCOPE_SHOW_SKIN_LINE_SPEC = BoolSettingSpec(
    "chk_vectorscope_skin_line",
    C.CFG_VECTORSCOPE_SHOW_SKIN_LINE,
    C.DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE,
)
VECTORSCOPE_WARN_THRESHOLD_SPEC = IntSettingSpec(
    "spin_vectorscope_warn_threshold",
    C.CFG_VECTORSCOPE_WARN_THRESHOLD,
    C.DEFAULT_VECTORSCOPE_WARN_THRESHOLD,
    C.VECTORSCOPE_WARN_THRESHOLD_MIN,
    C.VECTORSCOPE_WARN_THRESHOLD_MAX,
)
ALWAYS_ON_TOP_SPEC = BoolSettingSpec(
    "act_always_on_top",
    C.CFG_ALWAYS_ON_TOP,
    C.DEFAULT_ALWAYS_ON_TOP,
)
MODE_SPEC = ComboSettingSpec(
    "combo_mode",
    C.CFG_MODE,
    C.UPDATE_MODES,
    C.DEFAULT_MODE,
)
DIFF_THRESHOLD_SPEC = FloatSettingSpec(
    "spin_diff",
    C.CFG_DIFF_THRESHOLD,
    C.DEFAULT_DIFF_THRESHOLD,
    C.ANALYZER_MIN_DIFF_THRESHOLD,
    50.0,
)
STABLE_FRAMES_SPEC = IntSettingSpec(
    "spin_stable",
    C.CFG_STABLE_FRAMES,
    C.DEFAULT_STABLE_FRAMES,
    C.ANALYZER_MIN_STABLE_FRAMES,
    20,
)


def selected_setting_value(main_window, spec: SettingSpec):
    """spec に対応する現在UI値を正規化して返す。"""
    if isinstance(spec, ComboSettingSpec):
        return selected_combo_attr(main_window, spec.attr_name, spec.allowed, spec.default)
    if isinstance(spec, BoolSettingSpec):
        return selected_checked_attr(main_window, spec.attr_name)
    if isinstance(spec, IntSettingSpec):
        return selected_int_attr(main_window, spec.attr_name, spec.low, spec.high)
    widget = getattr(main_window, spec.attr_name)
    value = float(widget.value())
    if spec.low is not None and spec.high is not None:
        return clamp_float(value, spec.low, spec.high)
    return value


def load_setting_value(main_window, cfg: dict, spec: SettingSpec) -> None:
    """設定辞書から spec 対応 widget へ値を復元する。"""
    widget = getattr(main_window, spec.attr_name)
    if isinstance(spec, ComboSettingSpec):
        apply_combo_choice(widget, cfg.get(spec.cfg_key, spec.default), spec.allowed, spec.default)
        return
    if isinstance(spec, BoolSettingSpec):
        set_checked_blocked(widget, bool(cfg.get(spec.cfg_key, spec.default)))
        return
    if isinstance(spec, IntSettingSpec):
        set_value_blocked(widget, cfg_int(cfg, spec.cfg_key, spec.default, spec.low, spec.high))
        return
    set_value_blocked(
        widget,
        cfg_float(cfg, spec.cfg_key, spec.default, spec.low, spec.high),
    )


def load_settings_from_specs(main_window, cfg: dict, specs: tuple[SettingSpec, ...]) -> None:
    """spec 群を順番に設定辞書から widget へ復元する。"""
    for spec in specs:
        load_setting_value(main_window, cfg, spec)


def collect_settings_from_specs(main_window, specs: tuple[SettingSpec, ...]) -> dict:
    """spec 群に対応する現在UI値を保存用辞書として返す。"""
    return {spec.cfg_key: selected_setting_value(main_window, spec) for spec in specs}


__all__ = [
    "ALWAYS_ON_TOP_SPEC",
    "ANALYSIS_MAX_DIM_SPEC",
    "ANALYSIS_RESOLUTION_MODE_SPEC",
    "BINARY_PRESET_SPEC",
    "BoolSettingSpec",
    "CAPTURE_SOURCE_SPEC",
    "COLOR_BAND_HARMONY_GUIDE_ENABLED_SPEC",
    "COLOR_BAND_HARMONY_GUIDE_TYPE_SPEC",
    "COLOR_BAND_SAT_THRESHOLD_SPEC",
    "COLOR_BAND_USE_WHEEL_HARMONY_SPEC",
    "COLOR_BAND_USE_WHEEL_SAT_THRESHOLD_SPEC",
    "COMPOSITION_GUIDE_SPEC",
    "ComboSettingSpec",
    "DIFF_THRESHOLD_SPEC",
    "EDGE_SENSITIVITY_SPEC",
    "FloatSettingSpec",
    "FOCUS_PEAK_COLOR_SPEC",
    "FOCUS_PEAK_SENSITIVITY_SPEC",
    "FOCUS_PEAK_THICKNESS_SPEC",
    "INTERVAL_SPEC",
    "IntSettingSpec",
    "MIRROR_MODE_SPEC",
    "MODE_SPEC",
    "RGB_HIST_MODE_SPEC",
    "SALIENCY_OVERLAY_ALPHA_SPEC",
    "SAMPLE_POINTS_SPEC",
    "SCATTER_HUE_CENTER_SPEC",
    "SCATTER_HUE_FILTER_ENABLED_SPEC",
    "SCATTER_RENDER_MODE_SPEC",
    "SCATTER_SHAPE_SPEC",
    "SQUINT_BLUR_SIGMA_SPEC",
    "SQUINT_MODE_SPEC",
    "SQUINT_SCALE_PERCENT_SPEC",
    "STABLE_FRAMES_SPEC",
    "SettingSpec",
    "TERNARY_PRESET_SPEC",
    "UI_THEME_SPEC",
    "VECTORSCOPE_SHOW_SKIN_LINE_SPEC",
    "VECTORSCOPE_WARN_THRESHOLD_SPEC",
    "WHEEL_HARMONY_GUIDE_ENABLED_SPEC",
    "WHEEL_HARMONY_GUIDE_TYPE_SPEC",
    "WHEEL_MODE_SPEC",
    "WHEEL_SAT_THRESHOLD_SPEC",
    "collect_settings_from_specs",
    "load_setting_value",
    "load_settings_from_specs",
    "selected_setting_value",
]
