"""設定の読み書きと反映ロジック。"""

from ...util import constants as C
from ...util.config import load_config, save_config
from ...util.qt_helpers import (
    blocked_signals,
    set_enabled_if,
    set_checked_blocked,
    set_visible_if,
)
from .settings_values import (
    _apply_combo_choice,
    _cfg_float,
    _cfg_int,
    _collect_settings_payload,
    _set_value_blocked,
    selected_analysis_max_dim,
    selected_analysis_resolution_mode,
    selected_binary_preset,
    selected_color_band_harmony_guide_enabled,
    selected_color_band_use_wheel_harmony,
    selected_color_band_use_wheel_sat_threshold,
    selected_composition_guide,
    selected_effective_color_band_sat_threshold,
    selected_focus_peak_color,
    selected_mode,
    selected_rgb_hist_mode,
    selected_scatter_hue_center,
    selected_scatter_hue_filter_enabled,
    selected_scatter_render_mode,
    selected_scatter_shape,
    selected_squint_mode,
    selected_ternary_preset,
    selected_wheel_harmony_guide_enabled,
    selected_wheel_harmony_guide_type,
    selected_wheel_mode,
    selected_wheel_sat_threshold,
)

_LEGACY_REMOVED_CONFIG_KEYS = (
    "graph_every",
    "preview_window",
)

def sync_mode_dependent_rows(main_window):
    """更新モードに応じて関連入力行の表示状態を切り替える。"""
    # 「一定間隔」では interval のみ表示し、
    # 「画面に動きがあったとき」では diff/stable とその補足を表示する。
    mode = selected_mode(main_window)
    is_interval = mode == C.UPDATE_MODE_INTERVAL
    is_change = mode == C.UPDATE_MODE_CHANGE
    set_visible_if(main_window._row_interval_settings, is_interval)
    for row in (
        main_window._row_diff_settings,
        main_window._row_stable_settings,
    ):
        set_visible_if(row, is_change)
    for hint in (
        getattr(main_window, "_hint_diff_settings", None),
        getattr(main_window, "_hint_stable_settings", None),
    ):
        set_visible_if(hint, is_change)


def sync_squint_mode_rows(main_window):
    """スクイントモードに応じて関連入力行の表示状態を切り替える。"""
    # モードに応じて不要な入力項目を隠し、誤設定を防ぐ。
    mode = selected_squint_mode(main_window)
    show_scale = mode in (C.SQUINT_MODE_SCALE, C.SQUINT_MODE_SCALE_BLUR)
    show_blur = mode in (C.SQUINT_MODE_BLUR, C.SQUINT_MODE_SCALE_BLUR)
    set_visible_if(main_window._row_squint_scale_settings, show_scale)
    set_visible_if(main_window._row_squint_blur_settings, show_blur)


def sync_analysis_resolution_rows(main_window):
    """解析解像度モードに応じて最大辺入力行の表示を切り替える。"""
    # 指定サイズ入力は custom モード時のみ表示する。
    custom_mode = (
        selected_analysis_resolution_mode(main_window) == C.ANALYSIS_RESOLUTION_MODE_CUSTOM
    )
    set_visible_if(main_window._row_analysis_max_dim_settings, custom_mode)
    set_visible_if(getattr(main_window, "_hint_analysis_max_dim_settings", None), custom_mode)


def sync_scatter_filter_controls(main_window):
    """散布図フィルターUIの有効/無効と表示値を同期する。"""
    # HueフィルターON時のみ中心色相スライダーを有効化する。
    enabled = selected_scatter_hue_filter_enabled(main_window)
    set_enabled_if(main_window.slider_scatter_hue_center, enabled)
    hue_center = selected_scatter_hue_center(main_window)
    main_window.lbl_scatter_hue_center.setText(f"H {hue_center}")
    set_enabled_if(main_window.lbl_scatter_hue_center, enabled)


def sync_color_band_controls(main_window):
    """配色比率設定UIの有効/無効状態を同期する。"""
    use_wheel_sat = selected_color_band_use_wheel_sat_threshold(main_window)
    set_enabled_if(main_window.spin_color_band_sat_threshold, not use_wheel_sat)
    use_wheel_harmony = selected_color_band_use_wheel_harmony(main_window)
    own_harmony_enabled = selected_color_band_harmony_guide_enabled(main_window)
    set_enabled_if(main_window.chk_color_band_harmony_guide, not use_wheel_harmony)
    set_enabled_if(
        main_window.combo_color_band_harmony_guide,
        (not use_wheel_harmony) and own_harmony_enabled
    )


def apply_sample_points_settings(main_window, *_):
    """サンプル点数設定をワーカーへ反映する。"""
    # サンプル数は散布図サンプリング負荷に直結する設定。
    main_window.worker.set_sample_points(int(main_window.spin_points.value()))
    main_window._request_save_settings()


def apply_scatter_settings(main_window, *_):
    """散布図表示設定をビューへ反映する。"""
    # 散布図の形状・表示モード・色相フィルター条件をまとめて反映。
    main_window.scatter.set_shape(selected_scatter_shape(main_window))
    main_window.scatter.set_render_mode(selected_scatter_render_mode(main_window))
    main_window.scatter.set_hue_filter(
        selected_scatter_hue_filter_enabled(main_window),
        selected_scatter_hue_center(main_window),
    )
    sync_scatter_filter_controls(main_window)
    main_window._request_save_settings()


def apply_analysis_resolution_settings(main_window, *_args, save: bool = True):
    """解析解像度設定をワーカーへ反映する。"""
    # original は max_dim=0（縮小なし）で扱う。
    mode = selected_analysis_resolution_mode(main_window)
    max_dim = selected_analysis_max_dim(main_window)
    if mode == C.ANALYSIS_RESOLUTION_MODE_ORIGINAL:
        main_window.worker.set_max_dim(0)
    else:
        main_window.worker.set_max_dim(max_dim)
        # 正規化後の値を入力欄へ戻し、表示と内部値の差異をなくす。
        if int(main_window.edit_analysis_max_dim.value()) != int(max_dim):
            with blocked_signals(main_window.edit_analysis_max_dim):
                main_window.edit_analysis_max_dim.setValue(int(max_dim))
    sync_analysis_resolution_rows(main_window)
    if save:
        main_window._request_save_settings()


def apply_wheel_settings(main_window, *_):
    """色相環設定をビューとワーカーへ反映する。"""
    # 色相環表示方式と彩度しきい値を同時に反映。
    main_window.wheel.set_mode(selected_wheel_mode(main_window))
    main_window.worker.set_wheel_sat_threshold(selected_wheel_sat_threshold(main_window))
    guide_enabled = selected_wheel_harmony_guide_enabled(main_window)
    set_enabled_if(main_window.combo_wheel_harmony_guide, guide_enabled)
    main_window.wheel.set_harmony_guide_enabled(guide_enabled)
    main_window.wheel.set_harmony_guide_type(selected_wheel_harmony_guide_type(main_window))
    # チップ詳細の調和候補も即時更新する。
    if hasattr(main_window, "list_color_chips") and hasattr(main_window, "_on_color_chip_selected"):
        main_window._on_color_chip_selected(int(main_window.list_color_chips.currentRow()))
    if hasattr(main_window, "apply_color_band_settings"):
        main_window.apply_color_band_settings(save=False)
    main_window._request_save_settings()


def apply_color_band_settings(main_window, *_args, save: bool = True):
    """配色比率設定を反映し、必要なら表示を再計算する。"""
    sync_color_band_controls(main_window)
    main_window.worker.set_color_band_sat_threshold(
        selected_effective_color_band_sat_threshold(main_window)
    )
    snapshot = getattr(main_window, "_latest_result_snapshot", None)
    if isinstance(snapshot, dict):
        snapshot["top_colors"] = None
        snapshot["top_colors_full"] = None
        snapshot["top_colors_filtered"] = None
        snapshot["top_colors_key"] = None
        main_window._latest_result_snapshot = snapshot
    if hasattr(main_window, "_restore_dock_from_snapshot"):
        main_window._restore_dock_from_snapshot(getattr(main_window, "dock_color_band", None))
    if hasattr(main_window, "_on_color_chip_selected") and hasattr(main_window, "list_color_chips"):
        main_window._on_color_chip_selected(int(main_window.list_color_chips.currentRow()))
    if save:
        main_window._request_save_settings()


def on_wheel_harmony_rotation_changed(main_window, _rotation_deg: float):
    """色相環ガイド回転変更時に保存予約を行う。"""
    # 色相環ガイドの回転は設定へ永続化する。
    main_window._request_save_settings()


def apply_rgb_hist_settings(main_window, *_):
    """RGBヒストグラム設定を反映する。"""
    main_window.rgb_hist_view.set_display_mode(selected_rgb_hist_mode(main_window))
    main_window._request_save_settings()


def apply_edge_settings(main_window, *_):
    """エッジビュー設定を反映する。"""
    main_window.edge_view.set_sensitivity(main_window.spin_edge_sensitivity.value())
    main_window._request_save_settings()


def apply_binary_settings(main_window, *_):
    """2値化ビュー設定を反映する。"""
    main_window.binary_view.set_preset(selected_binary_preset(main_window))
    main_window._request_save_settings()


def apply_ternary_settings(main_window, *_):
    """3値化ビュー設定を反映する。"""
    main_window.ternary_view.set_preset(selected_ternary_preset(main_window))
    main_window._request_save_settings()


def apply_saliency_settings(main_window, *_):
    """サリエンシ表示設定を反映する。"""
    main_window.saliency_view.set_overlay_alpha(int(main_window.spin_saliency_alpha.value()))
    main_window._request_save_settings()


def apply_composition_guide_settings(main_window, *_):
    """構図ガイド設定を関連ビューへ反映する。"""
    # サリエンシーとプレビューで同じ構図ガイドを使う。
    guide = selected_composition_guide(main_window)
    main_window.saliency_view.set_composition_guide(guide)
    main_window.preview_window.set_composition_guide(guide)
    main_window._request_save_settings()


def apply_focus_peaking_settings(main_window, *_):
    """フォーカスピーキング設定を反映する。"""
    main_window.focus_peaking_view.set_sensitivity(
        int(main_window.spin_focus_peak_sensitivity.value())
    )
    main_window.focus_peaking_view.set_color(selected_focus_peak_color(main_window))
    main_window.focus_peaking_view.set_thickness(
        float(main_window.spin_focus_peak_thickness.value())
    )
    main_window._request_save_settings()


def apply_squint_settings(main_window, *_):
    """スクイント表示設定を反映する。"""
    main_window.squint_view.set_mode(selected_squint_mode(main_window))
    main_window.squint_view.set_scale_percent(int(main_window.spin_squint_scale.value()))
    main_window.squint_view.set_blur_sigma(float(main_window.spin_squint_blur.value()))
    sync_squint_mode_rows(main_window)
    main_window._request_save_settings()


def update_vectorscope_warning_label(main_window):
    """ベクトルスコープ警告ラベルの文言と色を更新する。"""
    # 高彩度画素比率に応じて警告文言と色を切り替える。
    ratio = float(main_window.vectorscope_view.high_saturation_ratio())
    threshold = int(main_window.spin_vectorscope_warn_threshold.value())
    if ratio <= 0.001:
        text = "高彩度警告: なし"
        style = "color:#8b97a8;"
    else:
        text = f"高彩度警告: しきい値({threshold}%)超え {ratio:.1f}%"
        color = "#b89c52" if ratio < 5.0 else "#d06b5d"
        style = f"color:{color};"
    if main_window.lbl_vectorscope_warning.text() != text:
        main_window.lbl_vectorscope_warning.setText(text)
    if main_window.lbl_vectorscope_warning.styleSheet() != style:
        main_window.lbl_vectorscope_warning.setStyleSheet(style)


def apply_vectorscope_settings(main_window, *_):
    """ベクトルスコープ設定を反映する。"""
    main_window.vectorscope_view.set_show_skin_tone_line(
        bool(main_window.chk_vectorscope_skin_line.isChecked())
    )
    main_window.vectorscope_view.set_warn_threshold(
        int(main_window.spin_vectorscope_warn_threshold.value())
    )
    update_vectorscope_warning_label(main_window)
    main_window._request_save_settings()


def apply_mode_settings(main_window, *_args, save: bool = True):
    """更新モード設定をワーカーとUIへ反映する。"""
    # 更新モード切替と関連パラメータの反映を一箇所に集約。
    mode = selected_mode(main_window)
    main_window.worker.set_mode(mode)
    main_window.worker.set_diff_threshold(main_window.spin_diff.value())
    main_window.worker.set_stable_frames(main_window.spin_stable.value())
    sync_mode_dependent_rows(main_window)
    if save:
        main_window._request_save_settings()


def _load_interval_and_analysis_settings(main_window, cfg: dict) -> None:
    """更新間隔・解析解像度関連設定を読み込む。"""
    interval = _cfg_float(cfg, C.CFG_INTERVAL, C.DEFAULT_INTERVAL_SEC)
    _set_value_blocked(main_window.spin_interval, interval)
    main_window.worker.set_interval(main_window.spin_interval.value())

    sample_points = _cfg_int(
        cfg,
        C.CFG_SAMPLE_POINTS,
        C.DEFAULT_SAMPLE_POINTS,
        C.ANALYZER_MIN_SAMPLE_POINTS,
        C.ANALYZER_MAX_SAMPLE_POINTS,
    )
    _set_value_blocked(main_window.spin_points, sample_points)
    main_window.worker.set_sample_points(sample_points)

    analysis_max_dim = _cfg_int(
        cfg,
        C.CFG_ANALYZER_MAX_DIM,
        C.ANALYZER_MAX_DIM,
        C.ANALYZER_MAX_DIM_MIN,
        C.ANALYZER_MAX_DIM_MAX,
    )
    _apply_combo_choice(
        main_window.combo_analysis_resolution_mode,
        cfg.get(C.CFG_ANALYSIS_RESOLUTION_MODE, C.DEFAULT_ANALYSIS_RESOLUTION_MODE),
        C.ANALYSIS_RESOLUTION_MODES,
        C.DEFAULT_ANALYSIS_RESOLUTION_MODE,
    )
    with blocked_signals(main_window.edit_analysis_max_dim):
        main_window.edit_analysis_max_dim.setValue(int(analysis_max_dim))
    apply_analysis_resolution_settings(main_window, save=False)


def _load_scatter_settings(main_window, cfg: dict) -> None:
    """散布図関連設定を読み込む。"""
    # 散布図設定はUIへ反映したうえで、現在UIが保持する正規化値を適用する。
    scatter_shape_raw = str(cfg.get(C.CFG_SCATTER_SHAPE, C.DEFAULT_SCATTER_SHAPE))
    scatter_render_mode_raw = str(cfg.get(C.CFG_SCATTER_RENDER_MODE, C.DEFAULT_SCATTER_RENDER_MODE))
    _apply_combo_choice(
        main_window.combo_scatter_shape,
        scatter_shape_raw,
        C.SCATTER_SHAPES,
        C.DEFAULT_SCATTER_SHAPE,
    )
    _apply_combo_choice(
        main_window.combo_scatter_render_mode,
        scatter_render_mode_raw,
        C.SCATTER_RENDER_MODES,
        C.DEFAULT_SCATTER_RENDER_MODE,
    )
    set_checked_blocked(
        main_window.chk_scatter_hue_filter,
        bool(
            cfg.get(
                C.CFG_SCATTER_HUE_FILTER_ENABLED,
                C.DEFAULT_SCATTER_HUE_FILTER_ENABLED,
            )
        ),
    )
    scatter_hue_center = _cfg_int(
        cfg,
        C.CFG_SCATTER_HUE_CENTER,
        C.DEFAULT_SCATTER_HUE_CENTER,
        C.SCATTER_HUE_MIN,
        C.SCATTER_HUE_MAX,
    )
    _set_value_blocked(main_window.slider_scatter_hue_center, scatter_hue_center)
    main_window.scatter.set_shape(selected_scatter_shape(main_window))
    main_window.scatter.set_render_mode(selected_scatter_render_mode(main_window))
    # フィルター状態は UI 側の現在値から再適用する。
    main_window.scatter.set_hue_filter(
        selected_scatter_hue_filter_enabled(main_window),
        selected_scatter_hue_center(main_window),
    )
    sync_scatter_filter_controls(main_window)


def _load_wheel_and_capture_settings(main_window, cfg: dict) -> None:
    """色相環・配色比率・取得元設定を読み込む。"""
    _apply_combo_choice(
        main_window.combo_wheel_mode,
        str(cfg.get(C.CFG_WHEEL_MODE, C.DEFAULT_WHEEL_MODE)),
        C.WHEEL_MODES,
        C.DEFAULT_WHEEL_MODE,
    )

    rgb_hist_mode_raw = cfg.get(C.CFG_RGB_HIST_MODE, C.DEFAULT_RGB_HIST_MODE)
    _apply_combo_choice(
        main_window.combo_rgb_hist_mode,
        rgb_hist_mode_raw,
        C.RGB_HIST_MODES,
        C.DEFAULT_RGB_HIST_MODE,
    )
    main_window.rgb_hist_view.set_display_mode(selected_rgb_hist_mode(main_window))

    wheel_sat_threshold = _cfg_int(
        cfg,
        C.CFG_WHEEL_SAT_THRESHOLD,
        C.DEFAULT_WHEEL_SAT_THRESHOLD,
        C.WHEEL_SAT_THRESHOLD_MIN,
        C.WHEEL_SAT_THRESHOLD_MAX,
    )
    wheel_harmony_guide_enabled = bool(
        cfg.get(C.CFG_WHEEL_HARMONY_GUIDE_ENABLED, C.DEFAULT_WHEEL_HARMONY_GUIDE_ENABLED)
    )
    wheel_harmony_guide_type_raw = cfg.get(
        C.CFG_WHEEL_HARMONY_GUIDE_TYPE,
        C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE,
    )
    wheel_harmony_guide_rotation = _cfg_float(
        cfg,
        C.CFG_WHEEL_HARMONY_GUIDE_ROTATION,
        0.0,
    )
    set_checked_blocked(main_window.chk_wheel_harmony_guide, wheel_harmony_guide_enabled)
    _apply_combo_choice(
        main_window.combo_wheel_harmony_guide,
        wheel_harmony_guide_type_raw,
        C.WHEEL_HARMONY_GUIDE_TYPES,
        C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE,
    )
    set_enabled_if(main_window.combo_wheel_harmony_guide, wheel_harmony_guide_enabled)

    _set_value_blocked(main_window.spin_wheel_sat_threshold, wheel_sat_threshold)
    main_window.wheel.set_mode(selected_wheel_mode(main_window))
    main_window.wheel.set_harmony_guide_enabled(wheel_harmony_guide_enabled)
    main_window.wheel.set_harmony_guide_type(selected_wheel_harmony_guide_type(main_window))
    main_window.wheel.set_harmony_guide_rotation(wheel_harmony_guide_rotation)
    main_window.worker.set_wheel_sat_threshold(wheel_sat_threshold)
    main_window.worker.set_graph_every(C.DEFAULT_GRAPH_EVERY)

    color_band_use_wheel_sat = bool(
        cfg.get(
            C.CFG_COLOR_BAND_USE_WHEEL_SAT_THRESHOLD,
            C.DEFAULT_COLOR_BAND_USE_WHEEL_SAT_THRESHOLD,
        )
    )
    color_band_sat_threshold = _cfg_int(
        cfg,
        C.CFG_COLOR_BAND_SAT_THRESHOLD,
        C.DEFAULT_COLOR_BAND_SAT_THRESHOLD,
        C.WHEEL_SAT_THRESHOLD_MIN,
        C.WHEEL_SAT_THRESHOLD_MAX,
    )
    color_band_use_wheel_harmony = bool(
        cfg.get(
            C.CFG_COLOR_BAND_USE_WHEEL_HARMONY,
            C.DEFAULT_COLOR_BAND_USE_WHEEL_HARMONY,
        )
    )
    color_band_harmony_enabled = bool(
        cfg.get(
            C.CFG_COLOR_BAND_HARMONY_GUIDE_ENABLED,
            C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_ENABLED,
        )
    )
    color_band_harmony_type_raw = cfg.get(
        C.CFG_COLOR_BAND_HARMONY_GUIDE_TYPE,
        C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_TYPE,
    )
    set_checked_blocked(main_window.chk_color_band_use_wheel_sat_threshold, color_band_use_wheel_sat)
    _set_value_blocked(main_window.spin_color_band_sat_threshold, color_band_sat_threshold)
    set_checked_blocked(main_window.chk_color_band_use_wheel_harmony, color_band_use_wheel_harmony)
    set_checked_blocked(main_window.chk_color_band_harmony_guide, color_band_harmony_enabled)
    _apply_combo_choice(
        main_window.combo_color_band_harmony_guide,
        color_band_harmony_type_raw,
        C.WHEEL_HARMONY_GUIDE_TYPES,
        C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_TYPE,
    )
    apply_color_band_settings(main_window, save=False)

    _apply_combo_choice(
        main_window.combo_capture_source,
        cfg.get(C.CFG_CAPTURE_SOURCE, C.DEFAULT_CAPTURE_SOURCE),
        C.CAPTURE_SOURCES,
        C.DEFAULT_CAPTURE_SOURCE,
    )
    main_window._apply_capture_source(save=False)


def _load_composition_and_window_flags(main_window, cfg: dict) -> None:
    """構図ガイド・最前面など表示関連設定を読み込む。"""
    _apply_combo_choice(
        main_window.combo_composition_guide,
        cfg.get(C.CFG_COMPOSITION_GUIDE, C.DEFAULT_COMPOSITION_GUIDE),
        C.COMPOSITION_GUIDES,
        C.DEFAULT_COMPOSITION_GUIDE,
    )
    composition_guide = selected_composition_guide(main_window)
    main_window.saliency_view.set_composition_guide(composition_guide)
    main_window.preview_window.set_composition_guide(composition_guide)

    # 領域プレビューは起動時の表示復元対象外にする（常に非表示開始）。
    set_checked_blocked(main_window.chk_preview_window, False)
    main_window.preview_window.hide()

    always_on_top = bool(cfg.get(C.CFG_ALWAYS_ON_TOP, C.DEFAULT_ALWAYS_ON_TOP))
    set_checked_blocked(main_window.act_always_on_top, always_on_top)
    main_window.apply_always_on_top(always_on_top, save=False)


def _load_update_mode_settings(main_window, cfg: dict) -> None:
    """更新モード関連設定を読み込む。"""
    _apply_combo_choice(
        main_window.combo_mode,
        cfg.get(C.CFG_MODE, C.DEFAULT_MODE),
        C.UPDATE_MODES,
        C.DEFAULT_MODE,
    )
    _set_value_blocked(
        main_window.spin_diff,
        _cfg_float(cfg, C.CFG_DIFF_THRESHOLD, C.DEFAULT_DIFF_THRESHOLD),
    )
    _set_value_blocked(
        main_window.spin_stable,
        _cfg_int(
            cfg,
            C.CFG_STABLE_FRAMES,
            C.DEFAULT_STABLE_FRAMES,
            C.ANALYZER_MIN_STABLE_FRAMES,
            20,
        ),
    )


def _load_image_view_settings(main_window, cfg: dict) -> None:
    """画像系ビュー設定を読み込む。"""
    edge_sens = _cfg_int(
        cfg,
        C.CFG_EDGE_SENSITIVITY,
        C.DEFAULT_EDGE_SENSITIVITY,
        C.EDGE_SENSITIVITY_MIN,
        C.EDGE_SENSITIVITY_MAX,
    )
    _set_value_blocked(main_window.spin_edge_sensitivity, edge_sens)
    main_window.edge_view.set_sensitivity(edge_sens)

    _apply_combo_choice(
        main_window.combo_binary_preset,
        cfg.get(C.CFG_BINARY_PRESET, C.DEFAULT_BINARY_PRESET),
        C.BINARY_PRESETS,
        C.DEFAULT_BINARY_PRESET,
    )
    main_window.binary_view.set_preset(selected_binary_preset(main_window))

    _apply_combo_choice(
        main_window.combo_ternary_preset,
        cfg.get(C.CFG_TERNARY_PRESET, C.DEFAULT_TERNARY_PRESET),
        C.TERNARY_PRESETS,
        C.DEFAULT_TERNARY_PRESET,
    )
    main_window.ternary_view.set_preset(selected_ternary_preset(main_window))

    saliency_alpha = _cfg_int(
        cfg,
        C.CFG_SALIENCY_OVERLAY_ALPHA,
        C.DEFAULT_SALIENCY_OVERLAY_ALPHA,
        C.SALIENCY_ALPHA_MIN,
        C.SALIENCY_ALPHA_MAX,
    )
    _set_value_blocked(main_window.spin_saliency_alpha, saliency_alpha)
    main_window.saliency_view.set_overlay_alpha(saliency_alpha)

    focus_sens = _cfg_int(
        cfg,
        C.CFG_FOCUS_PEAK_SENSITIVITY,
        C.DEFAULT_FOCUS_PEAK_SENSITIVITY,
        C.FOCUS_PEAK_SENSITIVITY_MIN,
        C.FOCUS_PEAK_SENSITIVITY_MAX,
    )
    _set_value_blocked(main_window.spin_focus_peak_sensitivity, focus_sens)
    _apply_combo_choice(
        main_window.combo_focus_peak_color,
        cfg.get(C.CFG_FOCUS_PEAK_COLOR, C.DEFAULT_FOCUS_PEAK_COLOR),
        C.FOCUS_PEAK_COLORS,
        C.DEFAULT_FOCUS_PEAK_COLOR,
    )
    focus_thick = _cfg_float(
        cfg,
        C.CFG_FOCUS_PEAK_THICKNESS,
        C.DEFAULT_FOCUS_PEAK_THICKNESS,
        C.FOCUS_PEAK_THICKNESS_MIN,
        C.FOCUS_PEAK_THICKNESS_MAX,
    )
    _set_value_blocked(main_window.spin_focus_peak_thickness, focus_thick)
    main_window.focus_peaking_view.set_sensitivity(focus_sens)
    main_window.focus_peaking_view.set_color(selected_focus_peak_color(main_window))
    main_window.focus_peaking_view.set_thickness(focus_thick)

    _apply_combo_choice(
        main_window.combo_squint_mode,
        cfg.get(C.CFG_SQUINT_MODE, C.DEFAULT_SQUINT_MODE),
        C.SQUINT_MODES,
        C.DEFAULT_SQUINT_MODE,
    )
    squint_scale = _cfg_int(
        cfg,
        C.CFG_SQUINT_SCALE_PERCENT,
        C.DEFAULT_SQUINT_SCALE_PERCENT,
        C.SQUINT_SCALE_PERCENT_MIN,
        C.SQUINT_SCALE_PERCENT_MAX,
    )
    _set_value_blocked(main_window.spin_squint_scale, squint_scale)
    squint_blur = _cfg_float(
        cfg,
        C.CFG_SQUINT_BLUR_SIGMA,
        C.DEFAULT_SQUINT_BLUR_SIGMA,
        C.SQUINT_BLUR_SIGMA_MIN,
        C.SQUINT_BLUR_SIGMA_MAX,
    )
    _set_value_blocked(main_window.spin_squint_blur, squint_blur)
    main_window.squint_view.set_mode(selected_squint_mode(main_window))
    main_window.squint_view.set_scale_percent(squint_scale)
    main_window.squint_view.set_blur_sigma(squint_blur)
    sync_squint_mode_rows(main_window)


def _load_vectorscope_settings(main_window, cfg: dict) -> None:
    """ベクトルスコープ設定を読み込む。"""
    show_skin_line = bool(
        cfg.get(C.CFG_VECTORSCOPE_SHOW_SKIN_LINE, C.DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE)
    )
    set_checked_blocked(main_window.chk_vectorscope_skin_line, show_skin_line)
    warn_threshold = _cfg_int(
        cfg,
        C.CFG_VECTORSCOPE_WARN_THRESHOLD,
        C.DEFAULT_VECTORSCOPE_WARN_THRESHOLD,
        C.VECTORSCOPE_WARN_THRESHOLD_MIN,
        C.VECTORSCOPE_WARN_THRESHOLD_MAX,
    )
    _set_value_blocked(main_window.spin_vectorscope_warn_threshold, warn_threshold)
    main_window.vectorscope_view.set_show_skin_tone_line(show_skin_line)
    main_window.vectorscope_view.set_warn_threshold(warn_threshold)
    update_vectorscope_warning_label(main_window)


def _finalize_loaded_settings(main_window, cfg: dict) -> None:
    """設定読み込み後の最終反映と同期処理を行う。"""
    # 表示設定まで含めてロード完了後の状態を同期。
    apply_mode_settings(main_window, save=False)
    main_window.apply_layout_from_config(cfg)
    main_window.refresh_layout_preset_views()
    main_window._sync_worker_view_flags()


def load_settings(main_window):
    """設定ファイルを読み込み、UIと各ビューへ適用する。"""
    # 初期ロード中は保存トリガーを抑止する。
    cfg = load_config()
    main_window._settings_load_in_progress = True
    try:
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
    cfg.pop("ui_theme", None)
    # 廃止済みキーは保存時に除去して設定ファイルをクリーンに保つ。
    for key in _LEGACY_REMOVED_CONFIG_KEYS:
        cfg.pop(key, None)
    cfg.update(_collect_settings_payload(main_window))
    # 差分がなければファイル書き込みをスキップする。
    if cfg == base:
        return
    save_config(cfg)
    if not silent:
        main_window.on_status("設定を保存しました")
