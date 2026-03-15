"""設定UIから正規化済みの選択値を取り出す補助処理。"""

from ...util import constants as C
from ...util.qt_helpers import blocked_signals, rect_to_dict
from ...util.value_utils import clamp_float, clamp_int, safe_choice, safe_int


def _cfg_int(cfg: dict, key: str, default: int, low: int, high: int) -> int:
    """設定辞書から整数値を取り出し、範囲内へ丸めて返す。"""
    return clamp_int(safe_int(cfg.get(key, default), default), low, high)


def _cfg_float(
    cfg: dict,
    key: str,
    default: float,
    low: float | None = None,
    high: float | None = None,
) -> float:
    """設定辞書から浮動小数値を取り出し、必要なら範囲内へ丸める。"""
    try:
        value = float(cfg.get(key, default))
    except Exception:
        value = float(default)
    if low is not None and high is not None:
        return clamp_float(value, low, high)
    return value


def _set_value_blocked(widget, value) -> None:
    """シグナルを抑止して値を設定する。"""
    with blocked_signals(widget):
        widget.setValue(value)


def _set_combobox_data_blocked(combo, data, default_data=None) -> int:
    """シグナル抑止でコンボ選択値を設定し、選択インデックスを返す。"""
    # data -> default_data -> index0 の順でフォールバックする。
    index = combo.findData(data)
    if index < 0 and default_data is not None:
        index = combo.findData(default_data)
    if index < 0 and combo.count() > 0:
        index = 0
    if index >= 0:
        with blocked_signals(combo):
            combo.setCurrentIndex(int(index))
    return index


def _apply_combo_choice(combo, raw_value, allowed, default) -> None:
    """許容値へ正規化してコンボ選択へ反映する。"""
    _set_combobox_data_blocked(
        combo,
        safe_choice(raw_value, allowed, default),
        default_data=default,
    )


def _selected_combo_data(combo, allowed, default):
    """コンボ選択値を許容値へ正規化して返す。"""
    return safe_choice(combo.currentData(), allowed, default)


def _selected_checked(widget) -> bool:
    """チェック系ウィジェットの選択状態を返す。"""
    return bool(widget.isChecked())


def _selected_checked_attr(main_window, attr_name: str) -> bool:
    """チェック系属性名から選択状態を返す。"""
    return _selected_checked(getattr(main_window, attr_name))


def _selected_int_in_range(widget, low: int, high: int) -> int:
    """数値入力ウィジェット値を範囲内へ丸めて返す。"""
    return clamp_int(int(widget.value()), int(low), int(high))


def _selected_int_attr(main_window, attr_name: str, low: int, high: int) -> int:
    """数値入力属性名から範囲内整数値を返す。"""
    return _selected_int_in_range(getattr(main_window, attr_name), low, high)


def _selected_combo_attr(main_window, attr_name: str, allowed, default):
    """コンボ属性名から正規化済み選択値を返す。"""
    return _selected_combo_data(getattr(main_window, attr_name), allowed, default)


def _selected_capture_window_title(main_window) -> str:
    """現在選択されているキャプチャ対象ウィンドウ名を返す。"""
    combo = main_window.combo_win
    idx = int(combo.currentIndex())
    if idx < 0 or combo.itemData(idx) is None:
        return ""
    return str(combo.itemText(idx)).strip()


def _selected_capture_window_text(main_window) -> str:
    """現在のキャプチャ対象入力欄テキストを返す。"""
    return str(main_window.combo_win.currentText() or "").strip()


def _selected_capture_screen_roi_abs_logical(main_window):
    """現在の画面ROI(論理座標)を返す。"""
    roi_abs_native = getattr(main_window.worker, "roi_abs", None)
    if roi_abs_native is None:
        return None
    try:
        return main_window.worker._native_rect_to_logical(roi_abs_native)
    except Exception:
        return None


def _selected_capture_settings_payload(main_window) -> dict:
    """キャプチャ対象の保存用ペイロードを返す。"""
    return {
        C.CFG_CAPTURE_SOURCE: main_window._selected_capture_source(),
        C.CFG_CAPTURE_WINDOW_TITLE: _selected_capture_window_title(main_window),
        C.CFG_CAPTURE_WINDOW_TEXT: _selected_capture_window_text(main_window),
        C.CFG_CAPTURE_WINDOW_ROI_REL: rect_to_dict(getattr(main_window.worker, "roi_rel", None)),
        C.CFG_CAPTURE_SCREEN_ROI_ABS: rect_to_dict(
            _selected_capture_screen_roi_abs_logical(main_window)
        ),
    }


def _collect_settings_payload(main_window) -> dict:
    """現在UI状態から保存用設定辞書を組み立てる。"""
    # UI状態から保存対象キーを再構築する。
    return {
        C.CFG_INTERVAL: float(main_window.spin_interval.value()),
        C.CFG_SAMPLE_POINTS: int(main_window.spin_points.value()),
        C.CFG_ANALYZER_MAX_DIM: selected_analysis_max_dim(main_window),
        C.CFG_ANALYSIS_RESOLUTION_MODE: selected_analysis_resolution_mode(main_window),
        **_selected_capture_settings_payload(main_window),
        C.CFG_SCATTER_SHAPE: selected_scatter_shape(main_window),
        C.CFG_SCATTER_RENDER_MODE: selected_scatter_render_mode(main_window),
        C.CFG_SCATTER_HUE_FILTER_ENABLED: selected_scatter_hue_filter_enabled(main_window),
        C.CFG_SCATTER_HUE_CENTER: selected_scatter_hue_center(main_window),
        C.CFG_WHEEL_MODE: selected_wheel_mode(main_window),
        C.CFG_RGB_HIST_MODE: selected_rgb_hist_mode(main_window),
        C.CFG_MIRROR_MODE: selected_mirror_mode(main_window),
        C.CFG_WHEEL_SAT_THRESHOLD: selected_wheel_sat_threshold(main_window),
        C.CFG_WHEEL_HARMONY_GUIDE_ENABLED: selected_wheel_harmony_guide_enabled(main_window),
        C.CFG_WHEEL_HARMONY_GUIDE_TYPE: selected_wheel_harmony_guide_type(main_window),
        C.CFG_WHEEL_HARMONY_GUIDE_ROTATION: selected_wheel_harmony_guide_rotation(main_window),
        C.CFG_COLOR_BAND_USE_WHEEL_SAT_THRESHOLD: selected_color_band_use_wheel_sat_threshold(
            main_window
        ),
        C.CFG_COLOR_BAND_SAT_THRESHOLD: selected_color_band_sat_threshold(main_window),
        C.CFG_COLOR_BAND_USE_WHEEL_HARMONY: selected_color_band_use_wheel_harmony(main_window),
        C.CFG_COLOR_BAND_HARMONY_GUIDE_ENABLED: selected_color_band_harmony_guide_enabled(
            main_window
        ),
        C.CFG_COLOR_BAND_HARMONY_GUIDE_TYPE: selected_color_band_harmony_guide_type(main_window),
        C.CFG_ALWAYS_ON_TOP: main_window._is_always_on_top_enabled(),
        C.CFG_MODE: selected_mode(main_window),
        C.CFG_DIFF_THRESHOLD: float(main_window.spin_diff.value()),
        C.CFG_STABLE_FRAMES: int(main_window.spin_stable.value()),
        C.CFG_EDGE_SENSITIVITY: int(main_window.spin_edge_sensitivity.value()),
        C.CFG_BINARY_PRESET: selected_binary_preset(main_window),
        C.CFG_TERNARY_PRESET: selected_ternary_preset(main_window),
        C.CFG_SALIENCY_OVERLAY_ALPHA: int(main_window.spin_saliency_alpha.value()),
        C.CFG_COMPOSITION_GUIDE: selected_composition_guide(main_window),
        C.CFG_FOCUS_PEAK_SENSITIVITY: int(main_window.spin_focus_peak_sensitivity.value()),
        C.CFG_FOCUS_PEAK_COLOR: selected_focus_peak_color(main_window),
        C.CFG_FOCUS_PEAK_THICKNESS: float(main_window.spin_focus_peak_thickness.value()),
        C.CFG_SQUINT_MODE: selected_squint_mode(main_window),
        C.CFG_SQUINT_SCALE_PERCENT: int(main_window.spin_squint_scale.value()),
        C.CFG_SQUINT_BLUR_SIGMA: float(main_window.spin_squint_blur.value()),
        C.CFG_VECTORSCOPE_SHOW_SKIN_LINE: bool(main_window.chk_vectorscope_skin_line.isChecked()),
        C.CFG_VECTORSCOPE_WARN_THRESHOLD: int(main_window.spin_vectorscope_warn_threshold.value()),
    }


def selected_mode(main_window) -> str:
    """更新モードの選択値を返す。"""
    # 未定義データが入っても安全に既定モードへフォールバックする。
    return _selected_combo_attr(main_window, "combo_mode", C.UPDATE_MODES, C.DEFAULT_MODE)


def selected_wheel_mode(main_window) -> str:
    """色相環表示モードの選択値を返す。"""
    return _selected_combo_attr(main_window, "combo_wheel_mode", C.WHEEL_MODES, C.DEFAULT_WHEEL_MODE)


def selected_rgb_hist_mode(main_window) -> str:
    """RGBヒストグラム表示モードの選択値を返す。"""
    return _selected_combo_attr(main_window, "combo_rgb_hist_mode", C.RGB_HIST_MODES, C.DEFAULT_RGB_HIST_MODE)


def selected_mirror_mode(main_window) -> str:
    """反転表示モードの選択値を返す。"""
    return _selected_combo_attr(main_window, "combo_mirror_mode", C.MIRROR_MODES, C.DEFAULT_MIRROR_MODE)


def selected_analysis_resolution_mode(main_window) -> str:
    """解析解像度モードの選択値を返す。"""
    return _selected_combo_attr(
        main_window,
        "combo_analysis_resolution_mode",
        C.ANALYSIS_RESOLUTION_MODES,
        C.DEFAULT_ANALYSIS_RESOLUTION_MODE,
    )


def selected_analysis_max_dim(main_window) -> int:
    """解析最大辺(px)の入力値を範囲内で返す。"""
    return _selected_int_attr(
        main_window,
        "edit_analysis_max_dim",
        C.ANALYZER_MAX_DIM_MIN,
        C.ANALYZER_MAX_DIM_MAX,
    )


def selected_wheel_sat_threshold(main_window) -> int:
    """色相環用彩度しきい値を範囲内で返す。"""
    return _selected_int_attr(
        main_window,
        "spin_wheel_sat_threshold",
        C.WHEEL_SAT_THRESHOLD_MIN,
        C.WHEEL_SAT_THRESHOLD_MAX,
    )


def selected_wheel_harmony_guide_enabled(main_window) -> bool:
    """色相環の色彩調和ガイド表示状態を返す。"""
    return _selected_checked_attr(main_window, "chk_wheel_harmony_guide")


def selected_wheel_harmony_guide_type(main_window) -> str:
    """色相環の色彩調和ガイド種別を返す。"""
    return _selected_combo_attr(
        main_window,
        "combo_wheel_harmony_guide",
        C.WHEEL_HARMONY_GUIDE_TYPES,
        C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE,
    )


def selected_wheel_harmony_guide_rotation(main_window) -> float:
    """色相環ガイドの回転角度を返す。"""
    wheel = getattr(main_window, "wheel", None)
    if wheel is None or not hasattr(wheel, "harmony_guide_rotation"):
        return 0.0
    try:
        return float(wheel.harmony_guide_rotation())
    except Exception:
        return 0.0


def selected_color_band_use_wheel_sat_threshold(main_window) -> bool:
    """配色比率が色相環の彩度しきい値を共有するか返す。"""
    return _selected_checked_attr(main_window, "chk_color_band_use_wheel_sat_threshold")


def selected_color_band_sat_threshold(main_window) -> int:
    """配色比率専用の彩度しきい値を範囲内で返す。"""
    return _selected_int_attr(
        main_window,
        "spin_color_band_sat_threshold",
        C.WHEEL_SAT_THRESHOLD_MIN,
        C.WHEEL_SAT_THRESHOLD_MAX,
    )


def selected_effective_color_band_sat_threshold(main_window) -> int:
    """配色比率で実際に適用される彩度しきい値を返す。"""
    # 「色相環と同じ」設定時は色相環しきい値を使う。
    if selected_color_band_use_wheel_sat_threshold(main_window):
        return selected_wheel_sat_threshold(main_window)
    return selected_color_band_sat_threshold(main_window)


def selected_color_band_use_wheel_harmony(main_window) -> bool:
    """配色比率が色相環の調和設定を共有するか返す。"""
    return _selected_checked_attr(main_window, "chk_color_band_use_wheel_harmony")


def selected_color_band_harmony_guide_enabled(main_window) -> bool:
    """配色比率側の色彩調和ガイド表示状態を返す。"""
    return _selected_checked_attr(main_window, "chk_color_band_harmony_guide")


def selected_color_band_harmony_guide_type(main_window) -> str:
    """配色比率側の色彩調和ガイド種別を返す。"""
    return _selected_combo_attr(
        main_window,
        "combo_color_band_harmony_guide",
        C.WHEEL_HARMONY_GUIDE_TYPES,
        C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_TYPE,
    )


def selected_scatter_hue_filter_enabled(main_window) -> bool:
    """散布図の色相フィルター有効状態を返す。"""
    return _selected_checked_attr(main_window, "chk_scatter_hue_filter")


def selected_scatter_hue_center(main_window) -> int:
    """散布図フィルター中心色相を範囲内で返す。"""
    return _selected_int_attr(
        main_window,
        "slider_scatter_hue_center",
        C.SCATTER_HUE_MIN,
        C.SCATTER_HUE_MAX,
    )


def selected_scatter_shape(main_window) -> str:
    """散布図マーカー形状の選択値を返す。"""
    return _selected_combo_attr(
        main_window,
        "combo_scatter_shape",
        C.SCATTER_SHAPES,
        C.DEFAULT_SCATTER_SHAPE,
    )


def selected_scatter_render_mode(main_window) -> str:
    """散布図レンダリングモードの選択値を返す。"""
    return _selected_combo_attr(
        main_window,
        "combo_scatter_render_mode",
        C.SCATTER_RENDER_MODES,
        C.DEFAULT_SCATTER_RENDER_MODE,
    )


def selected_binary_preset(main_window) -> str:
    """2値化プリセットの選択値を返す。"""
    return _selected_combo_attr(
        main_window,
        "combo_binary_preset",
        C.BINARY_PRESETS,
        C.DEFAULT_BINARY_PRESET,
    )


def selected_ternary_preset(main_window) -> str:
    """3値化プリセットの選択値を返す。"""
    return _selected_combo_attr(
        main_window,
        "combo_ternary_preset",
        C.TERNARY_PRESETS,
        C.DEFAULT_TERNARY_PRESET,
    )


def selected_composition_guide(main_window) -> str:
    """構図ガイド種別の選択値を返す。"""
    return _selected_combo_attr(
        main_window,
        "combo_composition_guide",
        C.COMPOSITION_GUIDES,
        C.DEFAULT_COMPOSITION_GUIDE,
    )


def selected_focus_peak_color(main_window) -> str:
    """フォーカスピーク色の選択値を返す。"""
    return _selected_combo_attr(
        main_window,
        "combo_focus_peak_color",
        C.FOCUS_PEAK_COLORS,
        C.DEFAULT_FOCUS_PEAK_COLOR,
    )


def selected_squint_mode(main_window) -> str:
    """スクイント表示モードの選択値を返す。"""
    return _selected_combo_attr(
        main_window,
        "combo_squint_mode",
        C.SQUINT_MODES,
        C.DEFAULT_SQUINT_MODE,
    )
