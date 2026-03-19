"""設定UIから正規化済みの選択値を取り出す処理。"""

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
    selected_setting_value,
)


def selected_interval(main_window) -> float:
    """更新間隔の入力値を返す。"""
    return float(selected_setting_value(main_window, INTERVAL_SPEC))


def selected_sample_points(main_window) -> int:
    """散布図サンプル点数の入力値を返す。"""
    return int(selected_setting_value(main_window, SAMPLE_POINTS_SPEC))


def selected_mode(main_window) -> str:
    """更新モードの選択値を返す。"""
    return str(selected_setting_value(main_window, MODE_SPEC))


def selected_diff_threshold(main_window) -> float:
    """差分更新モードのしきい値を返す。"""
    return float(selected_setting_value(main_window, DIFF_THRESHOLD_SPEC))


def selected_stable_frames(main_window) -> int:
    """差分更新モードの安定フレーム数を返す。"""
    return int(selected_setting_value(main_window, STABLE_FRAMES_SPEC))


def selected_ui_theme(main_window) -> str:
    """UIテーマの選択値を返す。"""
    return str(selected_setting_value(main_window, UI_THEME_SPEC))


def selected_wheel_mode(main_window) -> str:
    """色相環表示モードの選択値を返す。"""
    return str(selected_setting_value(main_window, WHEEL_MODE_SPEC))


def selected_rgb_hist_mode(main_window) -> str:
    """RGBヒストグラム表示モードの選択値を返す。"""
    return str(selected_setting_value(main_window, RGB_HIST_MODE_SPEC))


def selected_mirror_mode(main_window) -> str:
    """反転表示モードの選択値を返す。"""
    return str(selected_setting_value(main_window, MIRROR_MODE_SPEC))


def selected_analysis_resolution_mode(main_window) -> str:
    """解析解像度モードの選択値を返す。"""
    return str(selected_setting_value(main_window, ANALYSIS_RESOLUTION_MODE_SPEC))


def selected_analysis_max_dim(main_window) -> int:
    """解析最大辺(px)の入力値を範囲内で返す。"""
    return int(selected_setting_value(main_window, ANALYSIS_MAX_DIM_SPEC))


def selected_wheel_sat_threshold(main_window) -> int:
    """色相環用彩度しきい値を範囲内で返す。"""
    return int(selected_setting_value(main_window, WHEEL_SAT_THRESHOLD_SPEC))


def selected_wheel_harmony_guide_enabled(main_window) -> bool:
    """色相環の色彩調和ガイド表示状態を返す。"""
    return bool(selected_setting_value(main_window, WHEEL_HARMONY_GUIDE_ENABLED_SPEC))


def selected_wheel_harmony_guide_type(main_window) -> str:
    """色相環の色彩調和ガイド種別を返す。"""
    return str(selected_setting_value(main_window, WHEEL_HARMONY_GUIDE_TYPE_SPEC))


def selected_wheel_harmony_guide_rotation(main_window) -> float:
    """色相環ガイドの回転角度を返す。"""
    wheel = getattr(main_window, "wheel", None)
    if wheel is None or not hasattr(wheel, "harmony_guide_rotation"):
        return 0.0
    try:
        return float(wheel.harmony_guide_rotation())
    except (AttributeError, TypeError, ValueError):
        return 0.0


def selected_color_band_use_wheel_sat_threshold(main_window) -> bool:
    """配色比率が色相環の彩度しきい値を共有するか返す。"""
    return bool(selected_setting_value(main_window, COLOR_BAND_USE_WHEEL_SAT_THRESHOLD_SPEC))


def selected_color_band_sat_threshold(main_window) -> int:
    """配色比率専用の彩度しきい値を範囲内で返す。"""
    return int(selected_setting_value(main_window, COLOR_BAND_SAT_THRESHOLD_SPEC))


def selected_effective_color_band_sat_threshold(main_window) -> int:
    """配色比率で実際に適用される彩度しきい値を返す。"""
    if selected_color_band_use_wheel_sat_threshold(main_window):
        return selected_wheel_sat_threshold(main_window)
    return selected_color_band_sat_threshold(main_window)


def selected_effective_color_band_sat_threshold_safe(
    main_window,
    fallback: int = 0,
) -> int:
    """配色比率の実効彩度しきい値を安全に返す。"""
    try:
        return int(selected_effective_color_band_sat_threshold(main_window))
    except (AttributeError, TypeError, ValueError):
        return int(fallback)


def selected_color_band_use_wheel_harmony(main_window) -> bool:
    """配色比率が色相環の調和設定を共有するか返す。"""
    return bool(selected_setting_value(main_window, COLOR_BAND_USE_WHEEL_HARMONY_SPEC))


def selected_color_band_harmony_guide_enabled(main_window) -> bool:
    """配色比率側の色彩調和ガイド表示状態を返す。"""
    return bool(selected_setting_value(main_window, COLOR_BAND_HARMONY_GUIDE_ENABLED_SPEC))


def selected_color_band_harmony_guide_type(main_window) -> str:
    """配色比率側の色彩調和ガイド種別を返す。"""
    return str(selected_setting_value(main_window, COLOR_BAND_HARMONY_GUIDE_TYPE_SPEC))


def selected_scatter_hue_filter_enabled(main_window) -> bool:
    """散布図の色相フィルター有効状態を返す。"""
    return bool(selected_setting_value(main_window, SCATTER_HUE_FILTER_ENABLED_SPEC))


def selected_scatter_hue_center(main_window) -> int:
    """散布図フィルター中心色相を範囲内で返す。"""
    return int(selected_setting_value(main_window, SCATTER_HUE_CENTER_SPEC))


def selected_scatter_shape(main_window) -> str:
    """散布図マーカー形状の選択値を返す。"""
    return str(selected_setting_value(main_window, SCATTER_SHAPE_SPEC))


def selected_scatter_render_mode(main_window) -> str:
    """散布図レンダリングモードの選択値を返す。"""
    return str(selected_setting_value(main_window, SCATTER_RENDER_MODE_SPEC))


def selected_binary_preset(main_window) -> str:
    """2値化プリセットの選択値を返す。"""
    return str(selected_setting_value(main_window, BINARY_PRESET_SPEC))


def selected_ternary_preset(main_window) -> str:
    """3値化プリセットの選択値を返す。"""
    return str(selected_setting_value(main_window, TERNARY_PRESET_SPEC))


def selected_composition_guide(main_window) -> str:
    """構図ガイド種別の選択値を返す。"""
    return str(selected_setting_value(main_window, COMPOSITION_GUIDE_SPEC))


def selected_focus_peak_sensitivity(main_window) -> int:
    """フォーカスピーキング感度を返す。"""
    return int(selected_setting_value(main_window, FOCUS_PEAK_SENSITIVITY_SPEC))


def selected_focus_peak_color(main_window) -> str:
    """フォーカスピーク色の選択値を返す。"""
    return str(selected_setting_value(main_window, FOCUS_PEAK_COLOR_SPEC))


def selected_focus_peak_thickness(main_window) -> float:
    """フォーカスピーキング線幅を返す。"""
    return float(selected_setting_value(main_window, FOCUS_PEAK_THICKNESS_SPEC))


def selected_squint_mode(main_window) -> str:
    """スクイント表示モードの選択値を返す。"""
    return str(selected_setting_value(main_window, SQUINT_MODE_SPEC))


def selected_squint_scale_percent(main_window) -> int:
    """スクイント縮小率を返す。"""
    return int(selected_setting_value(main_window, SQUINT_SCALE_PERCENT_SPEC))


def selected_squint_blur_sigma(main_window) -> float:
    """スクイントぼかし量を返す。"""
    return float(selected_setting_value(main_window, SQUINT_BLUR_SIGMA_SPEC))


def selected_edge_sensitivity(main_window) -> int:
    """エッジ検出感度を返す。"""
    return int(selected_setting_value(main_window, EDGE_SENSITIVITY_SPEC))


def selected_saliency_overlay_alpha(main_window) -> int:
    """サリエンシーの重ね具合を返す。"""
    return int(selected_setting_value(main_window, SALIENCY_OVERLAY_ALPHA_SPEC))


def selected_vectorscope_show_skin_line(main_window) -> bool:
    """ベクトルスコープのスキントーンライン表示有無を返す。"""
    return bool(selected_setting_value(main_window, VECTORSCOPE_SHOW_SKIN_LINE_SPEC))


def selected_vectorscope_warn_threshold(main_window) -> int:
    """ベクトルスコープ高彩度しきい値を返す。"""
    return int(selected_setting_value(main_window, VECTORSCOPE_WARN_THRESHOLD_SPEC))
