"""設定ファイルの読み込み・保存と初期反映。"""

from ...util import constants as C
from ...util.config import load_config, save_config
from ...util.qt_helpers import dict_to_rect, set_checked_blocked
from .settings_apply import (
    apply_analysis_resolution_settings,
    apply_binary_settings,
    apply_color_band_settings,
    apply_composition_guide_settings,
    apply_edge_settings,
    apply_focus_peaking_settings,
    apply_mirror_settings,
    apply_mode_settings,
    apply_rgb_hist_settings,
    apply_saliency_settings,
    apply_sample_points_settings,
    apply_scatter_settings,
    apply_squint_settings,
    apply_theme_settings,
    apply_ternary_settings,
    apply_vectorscope_settings,
    apply_wheel_settings,
)
from .settings_payload import collect_settings_payload
from .settings_selected_values import selected_interval
from .settings_value_common import cfg_float
from .settings_value_specs import (
    ALWAYS_ON_TOP_SPEC,
    ANALYSIS_MAX_DIM_SPEC,
    ANALYSIS_RESOLUTION_MODE_SPEC,
    BINARY_PRESET_SPEC,
    CAPTURE_SOURCE_SPEC,
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
    load_settings_from_specs,
)

_LEGACY_REMOVED_CONFIG_KEYS = (
    "graph_every",
    "preview_window",
)
_THEME_LOAD_SPECS = (UI_THEME_SPEC,)
_INTERVAL_ANALYSIS_LOAD_SPECS = (
    INTERVAL_SPEC,
    SAMPLE_POINTS_SPEC,
    ANALYSIS_MAX_DIM_SPEC,
    ANALYSIS_RESOLUTION_MODE_SPEC,
)
_SCATTER_LOAD_SPECS = (
    SCATTER_SHAPE_SPEC,
    SCATTER_RENDER_MODE_SPEC,
    SCATTER_HUE_FILTER_ENABLED_SPEC,
    SCATTER_HUE_CENTER_SPEC,
)
_WHEEL_LOAD_SPECS = (
    WHEEL_MODE_SPEC,
    RGB_HIST_MODE_SPEC,
    WHEEL_HARMONY_GUIDE_ENABLED_SPEC,
    WHEEL_HARMONY_GUIDE_TYPE_SPEC,
    WHEEL_SAT_THRESHOLD_SPEC,
)
_COLOR_BAND_LOAD_SPECS = (
    COLOR_BAND_USE_WHEEL_SAT_THRESHOLD_SPEC,
    COLOR_BAND_SAT_THRESHOLD_SPEC,
    COLOR_BAND_USE_WHEEL_HARMONY_SPEC,
    COLOR_BAND_HARMONY_GUIDE_ENABLED_SPEC,
    COLOR_BAND_HARMONY_GUIDE_TYPE_SPEC,
)
_UPDATE_MODE_LOAD_SPECS = (
    MODE_SPEC,
    DIFF_THRESHOLD_SPEC,
    STABLE_FRAMES_SPEC,
)
_FOCUS_PEAK_LOAD_SPECS = (
    FOCUS_PEAK_SENSITIVITY_SPEC,
    FOCUS_PEAK_COLOR_SPEC,
    FOCUS_PEAK_THICKNESS_SPEC,
)
_SQUINT_LOAD_SPECS = (
    SQUINT_MODE_SPEC,
    SQUINT_SCALE_PERCENT_SPEC,
    SQUINT_BLUR_SIGMA_SPEC,
)
_VECTORSCOPE_LOAD_SPECS = (
    VECTORSCOPE_SHOW_SKIN_LINE_SPEC,
    VECTORSCOPE_WARN_THRESHOLD_SPEC,
)


def _load_theme_settings(main_window, cfg: dict) -> None:
    """UIテーマ設定を読み込んで反映する。"""
    load_settings_from_specs(main_window, cfg, _THEME_LOAD_SPECS)
    apply_theme_settings(main_window, save=False)


def _load_interval_and_analysis_settings(main_window, cfg: dict) -> None:
    """更新間隔・解析解像度関連設定を読み込む。"""
    load_settings_from_specs(main_window, cfg, _INTERVAL_ANALYSIS_LOAD_SPECS)
    main_window.worker.set_interval(selected_interval(main_window))
    apply_sample_points_settings(main_window, save=False)
    apply_analysis_resolution_settings(main_window, save=False)


def _load_scatter_settings(main_window, cfg: dict) -> None:
    """散布図関連設定を読み込む。"""
    load_settings_from_specs(main_window, cfg, _SCATTER_LOAD_SPECS)
    apply_scatter_settings(main_window, save=False)


def _load_wheel_and_capture_settings(main_window, cfg: dict) -> None:
    """色相環・配色比率・取得元設定を読み込む。"""
    load_settings_from_specs(main_window, cfg, _WHEEL_LOAD_SPECS)
    apply_rgb_hist_settings(main_window, save=False)
    wheel_harmony_guide_rotation = cfg_float(
        cfg,
        C.CFG_WHEEL_HARMONY_GUIDE_ROTATION,
        0.0,
    )
    apply_wheel_settings(main_window, save=False, sync_color_band=False)
    main_window.wheel.set_harmony_guide_rotation(wheel_harmony_guide_rotation)
    main_window.worker.set_graph_every(C.DEFAULT_GRAPH_EVERY)
    load_settings_from_specs(main_window, cfg, _COLOR_BAND_LOAD_SPECS)
    apply_color_band_settings(main_window, save=False)
    load_settings_from_specs(main_window, cfg, (CAPTURE_SOURCE_SPEC,))
    capture_window_title = str(cfg.get(C.CFG_CAPTURE_WINDOW_TITLE, "") or "").strip()
    capture_window_text = str(
        cfg.get(C.CFG_CAPTURE_WINDOW_TEXT, capture_window_title) or ""
    ).strip()
    capture_window_roi_rel = dict_to_rect(cfg.get(C.CFG_CAPTURE_WINDOW_ROI_REL))
    capture_screen_roi_abs = dict_to_rect(cfg.get(C.CFG_CAPTURE_SCREEN_ROI_ABS))
    main_window.apply_capture_source(
        save=False,
        restore_window_title=capture_window_title,
        restore_window_text=capture_window_text,
        restore_window_roi_rel=capture_window_roi_rel,
        restore_screen_roi_abs=capture_screen_roi_abs,
    )


def _load_composition_and_window_flags(main_window, cfg: dict) -> None:
    """構図ガイド・最前面など表示関連設定を読み込む。"""
    load_settings_from_specs(main_window, cfg, (COMPOSITION_GUIDE_SPEC,))
    apply_composition_guide_settings(main_window, save=False)

    set_checked_blocked(main_window.chk_preview_window, False)
    main_window.preview_window.hide()

    load_settings_from_specs(main_window, cfg, (ALWAYS_ON_TOP_SPEC,))
    main_window.apply_always_on_top(bool(main_window.act_always_on_top.isChecked()), save=False)


def _load_update_mode_settings(main_window, cfg: dict) -> None:
    """更新モード関連設定を読み込む。"""
    load_settings_from_specs(main_window, cfg, _UPDATE_MODE_LOAD_SPECS)


def _load_image_view_settings(main_window, cfg: dict) -> None:
    """画像系ビュー設定を読み込む。"""
    load_settings_from_specs(main_window, cfg, (EDGE_SENSITIVITY_SPEC,))
    apply_edge_settings(main_window, save=False)
    load_settings_from_specs(main_window, cfg, (MIRROR_MODE_SPEC,))
    apply_mirror_settings(main_window, save=False)

    load_settings_from_specs(main_window, cfg, (BINARY_PRESET_SPEC,))
    apply_binary_settings(main_window, save=False)

    load_settings_from_specs(main_window, cfg, (TERNARY_PRESET_SPEC,))
    apply_ternary_settings(main_window, save=False)

    load_settings_from_specs(main_window, cfg, (SALIENCY_OVERLAY_ALPHA_SPEC,))
    apply_saliency_settings(main_window, save=False)

    load_settings_from_specs(main_window, cfg, _FOCUS_PEAK_LOAD_SPECS)
    apply_focus_peaking_settings(main_window, save=False)

    load_settings_from_specs(main_window, cfg, _SQUINT_LOAD_SPECS)
    apply_squint_settings(main_window, save=False)


def _load_vectorscope_settings(main_window, cfg: dict) -> None:
    """ベクトルスコープ設定を読み込む。"""
    load_settings_from_specs(main_window, cfg, _VECTORSCOPE_LOAD_SPECS)
    apply_vectorscope_settings(main_window, save=False)


def _finalize_loaded_settings(main_window, cfg: dict) -> None:
    """設定読み込み後の最終反映と同期処理を行う。"""
    apply_mode_settings(main_window, save=False)
    main_window.apply_layout_from_config(cfg)
    main_window.refresh_layout_preset_views()
    main_window._sync_worker_view_flags()


def load_settings(main_window):
    """設定ファイルを読み込み、UIと各ビューへ適用する。"""
    cfg = load_config()
    main_window._settings_load_in_progress = True
    try:
        _load_theme_settings(main_window, cfg)
        _load_interval_and_analysis_settings(main_window, cfg)
        _load_scatter_settings(main_window, cfg)
        _load_wheel_and_capture_settings(main_window, cfg)
        _load_composition_and_window_flags(main_window, cfg)
        _load_update_mode_settings(main_window, cfg)
        _load_image_view_settings(main_window, cfg)
        _load_vectorscope_settings(main_window, cfg)
        _finalize_loaded_settings(main_window, cfg)
    finally:
        main_window._settings_load_in_progress = False


def save_settings(main_window, silent: bool = True):
    """現在UI状態を設定ファイルへ保存する。"""
    if main_window._settings_load_in_progress:
        return
    base = load_config()
    cfg = dict(base)
    for key in _LEGACY_REMOVED_CONFIG_KEYS:
        cfg.pop(key, None)
    cfg.update(collect_settings_payload(main_window))
    if cfg == base:
        return
    save_config(cfg)
    if not silent:
        main_window.on_status("設定を保存しました")
