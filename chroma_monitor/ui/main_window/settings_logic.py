"""設定の読み書きと反映ロジック。"""

from ...util import constants as C
from ...util.config import load_config, save_config
from ...util.functions import (
    blocked_signals,
    clamp_float,
    clamp_int,
    safe_choice,
    safe_int,
    set_checked_blocked,
)

_LEGACY_REMOVED_CONFIG_KEYS = (
    "graph_every",
    "preview_window",
)


def _cfg_int(cfg: dict, key: str, default: int, low: int, high: int) -> int:
    return clamp_int(safe_int(cfg.get(key, default), default), low, high)


def _cfg_float(
    cfg: dict,
    key: str,
    default: float,
    low: float | None = None,
    high: float | None = None,
) -> float:
    try:
        value = float(cfg.get(key, default))
    except Exception:
        value = float(default)
    if low is not None and high is not None:
        return clamp_float(value, low, high)
    return value


def _set_value_blocked(widget, value) -> None:
    with blocked_signals(widget):
        widget.setValue(value)


def _set_combobox_data_blocked(combo, data, default_data=None) -> int:
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
    _set_combobox_data_blocked(
        combo,
        safe_choice(raw_value, allowed, default),
        default_data=default,
    )


def _selected_combo_data(combo, allowed, default):
    return safe_choice(combo.currentData(), allowed, default)


def _set_visible_if(widget, visible: bool) -> None:
    if widget is not None:
        widget.setVisible(bool(visible))


def _collect_settings_payload(main_window) -> dict:
    # UI状態から保存対象キーを再構築する。
    return {
        C.CFG_INTERVAL: float(main_window.spin_interval.value()),
        C.CFG_SAMPLE_POINTS: int(main_window.spin_points.value()),
        C.CFG_ANALYZER_MAX_DIM: selected_analysis_max_dim(main_window),
        C.CFG_ANALYSIS_RESOLUTION_MODE: selected_analysis_resolution_mode(main_window),
        C.CFG_CAPTURE_SOURCE: main_window._selected_capture_source(),
        C.CFG_SCATTER_SHAPE: selected_scatter_shape(main_window),
        C.CFG_SCATTER_RENDER_MODE: selected_scatter_render_mode(main_window),
        C.CFG_SCATTER_HUE_FILTER_ENABLED: selected_scatter_hue_filter_enabled(main_window),
        C.CFG_SCATTER_HUE_CENTER: selected_scatter_hue_center(main_window),
        C.CFG_WHEEL_MODE: selected_wheel_mode(main_window),
        C.CFG_RGB_HIST_MODE: selected_rgb_hist_mode(main_window),
        C.CFG_WHEEL_SAT_THRESHOLD: selected_wheel_sat_threshold(main_window),
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
    # 未定義データが入っても安全に既定モードへフォールバックする。
    return _selected_combo_data(main_window.combo_mode, C.UPDATE_MODES, C.DEFAULT_MODE)


def selected_wheel_mode(main_window) -> str:
    return _selected_combo_data(main_window.combo_wheel_mode, C.WHEEL_MODES, C.DEFAULT_WHEEL_MODE)


def selected_rgb_hist_mode(main_window) -> str:
    return _selected_combo_data(
        main_window.combo_rgb_hist_mode,
        C.RGB_HIST_MODES,
        C.DEFAULT_RGB_HIST_MODE,
    )


def selected_analysis_resolution_mode(main_window) -> str:
    return _selected_combo_data(
        main_window.combo_analysis_resolution_mode,
        C.ANALYSIS_RESOLUTION_MODES,
        C.DEFAULT_ANALYSIS_RESOLUTION_MODE,
    )


def selected_analysis_max_dim(main_window) -> int:
    return clamp_int(
        int(main_window.edit_analysis_max_dim.value()),
        C.ANALYZER_MAX_DIM_MIN,
        C.ANALYZER_MAX_DIM_MAX,
    )


def selected_wheel_sat_threshold(main_window) -> int:
    return clamp_int(
        main_window.spin_wheel_sat_threshold.value(),
        C.WHEEL_SAT_THRESHOLD_MIN,
        C.WHEEL_SAT_THRESHOLD_MAX,
    )


def selected_scatter_hue_filter_enabled(main_window) -> bool:
    return bool(main_window.chk_scatter_hue_filter.isChecked())


def selected_scatter_hue_center(main_window) -> int:
    return clamp_int(
        main_window.slider_scatter_hue_center.value(),
        C.SCATTER_HUE_MIN,
        C.SCATTER_HUE_MAX,
    )


def selected_scatter_shape(main_window) -> str:
    return _selected_combo_data(
        main_window.combo_scatter_shape,
        C.SCATTER_SHAPES,
        C.DEFAULT_SCATTER_SHAPE,
    )


def selected_scatter_render_mode(main_window) -> str:
    return _selected_combo_data(
        main_window.combo_scatter_render_mode,
        C.SCATTER_RENDER_MODES,
        C.DEFAULT_SCATTER_RENDER_MODE,
    )


def selected_binary_preset(main_window) -> str:
    return _selected_combo_data(
        main_window.combo_binary_preset,
        C.BINARY_PRESETS,
        C.DEFAULT_BINARY_PRESET,
    )


def selected_ternary_preset(main_window) -> str:
    return _selected_combo_data(
        main_window.combo_ternary_preset,
        C.TERNARY_PRESETS,
        C.DEFAULT_TERNARY_PRESET,
    )


def selected_composition_guide(main_window) -> str:
    return _selected_combo_data(
        main_window.combo_composition_guide,
        C.COMPOSITION_GUIDES,
        C.DEFAULT_COMPOSITION_GUIDE,
    )


def selected_focus_peak_color(main_window) -> str:
    return _selected_combo_data(
        main_window.combo_focus_peak_color,
        C.FOCUS_PEAK_COLORS,
        C.DEFAULT_FOCUS_PEAK_COLOR,
    )


def selected_squint_mode(main_window) -> str:
    return _selected_combo_data(
        main_window.combo_squint_mode,
        C.SQUINT_MODES,
        C.DEFAULT_SQUINT_MODE,
    )


def sync_mode_dependent_rows(main_window):
    # 「一定間隔」では interval のみ表示し、
    # 「画面に動きがあったとき」では diff/stable とその補足を表示する。
    mode = selected_mode(main_window)
    is_interval = mode == C.UPDATE_MODE_INTERVAL
    is_change = mode == C.UPDATE_MODE_CHANGE
    _set_visible_if(main_window._row_interval_settings, is_interval)
    for row in (
        main_window._row_diff_settings,
        main_window._row_stable_settings,
    ):
        _set_visible_if(row, is_change)
    for hint in (
        getattr(main_window, "_hint_diff_settings", None),
        getattr(main_window, "_hint_stable_settings", None),
    ):
        _set_visible_if(hint, is_change)


def sync_squint_mode_rows(main_window):
    # モードに応じて不要な入力項目を隠し、誤設定を防ぐ。
    mode = selected_squint_mode(main_window)
    show_scale = mode in (C.SQUINT_MODE_SCALE, C.SQUINT_MODE_SCALE_BLUR)
    show_blur = mode in (C.SQUINT_MODE_BLUR, C.SQUINT_MODE_SCALE_BLUR)
    _set_visible_if(main_window._row_squint_scale_settings, show_scale)
    _set_visible_if(main_window._row_squint_blur_settings, show_blur)


def sync_analysis_resolution_rows(main_window):
    # 指定サイズ入力は custom モード時のみ表示する。
    custom_mode = (
        selected_analysis_resolution_mode(main_window) == C.ANALYSIS_RESOLUTION_MODE_CUSTOM
    )
    _set_visible_if(main_window._row_analysis_max_dim_settings, custom_mode)
    _set_visible_if(getattr(main_window, "_hint_analysis_max_dim_settings", None), custom_mode)


def sync_scatter_filter_controls(main_window):
    # HueフィルターON時のみ中心色相スライダーを有効化する。
    enabled = selected_scatter_hue_filter_enabled(main_window)
    main_window.slider_scatter_hue_center.setEnabled(enabled)
    hue_center = selected_scatter_hue_center(main_window)
    main_window.lbl_scatter_hue_center.setText(f"H {hue_center}")
    main_window.lbl_scatter_hue_center.setEnabled(enabled)


def apply_sample_points_settings(main_window, *_):
    # サンプル数は散布図サンプリング負荷に直結する設定。
    main_window.worker.set_sample_points(int(main_window.spin_points.value()))
    main_window._request_save_settings()


def apply_scatter_settings(main_window, *_):
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
    # 色相環表示方式と彩度しきい値を同時に反映。
    main_window.wheel.set_mode(selected_wheel_mode(main_window))
    main_window.worker.set_wheel_sat_threshold(selected_wheel_sat_threshold(main_window))
    main_window._request_save_settings()


def apply_rgb_hist_settings(main_window, *_):
    main_window.rgb_hist_view.set_display_mode(selected_rgb_hist_mode(main_window))
    main_window._request_save_settings()


def apply_edge_settings(main_window, *_):
    main_window.edge_view.set_sensitivity(main_window.spin_edge_sensitivity.value())
    main_window._request_save_settings()


def apply_binary_settings(main_window, *_):
    main_window.binary_view.set_preset(selected_binary_preset(main_window))
    main_window._request_save_settings()


def apply_ternary_settings(main_window, *_):
    main_window.ternary_view.set_preset(selected_ternary_preset(main_window))
    main_window._request_save_settings()


def apply_saliency_settings(main_window, *_):
    main_window.saliency_view.set_overlay_alpha(int(main_window.spin_saliency_alpha.value()))
    main_window._request_save_settings()


def apply_composition_guide_settings(main_window, *_):
    # サリエンシーとプレビューで同じ構図ガイドを使う。
    guide = selected_composition_guide(main_window)
    main_window.saliency_view.set_composition_guide(guide)
    main_window.preview_window.set_composition_guide(guide)
    main_window._request_save_settings()


def apply_focus_peaking_settings(main_window, *_):
    main_window.focus_peaking_view.set_sensitivity(
        int(main_window.spin_focus_peak_sensitivity.value())
    )
    main_window.focus_peaking_view.set_color(selected_focus_peak_color(main_window))
    main_window.focus_peaking_view.set_thickness(
        float(main_window.spin_focus_peak_thickness.value())
    )
    main_window._request_save_settings()


def apply_squint_settings(main_window, *_):
    main_window.squint_view.set_mode(selected_squint_mode(main_window))
    main_window.squint_view.set_scale_percent(int(main_window.spin_squint_scale.value()))
    main_window.squint_view.set_blur_sigma(float(main_window.spin_squint_blur.value()))
    sync_squint_mode_rows(main_window)
    main_window._request_save_settings()


def update_vectorscope_warning_label(main_window):
    # 高彩度画素比率に応じて警告文言と色を切り替える。
    ratio = float(main_window.vectorscope_view.high_saturation_ratio())
    threshold = int(main_window.spin_vectorscope_warn_threshold.value())
    if ratio <= 0.001:
        main_window.lbl_vectorscope_warning.setText("高彩度警告: なし")
        main_window.lbl_vectorscope_warning.setStyleSheet("color:#8b97a8;")
    else:
        main_window.lbl_vectorscope_warning.setText(
            f"高彩度警告: しきい値({threshold}%)超え {ratio:.1f}%"
        )
        color = "#b89c52" if ratio < 5.0 else "#d06b5d"
        main_window.lbl_vectorscope_warning.setStyleSheet(f"color:{color};")


def apply_vectorscope_settings(main_window, *_):
    main_window.vectorscope_view.set_show_skin_tone_line(
        bool(main_window.chk_vectorscope_skin_line.isChecked())
    )
    main_window.vectorscope_view.set_warn_threshold(
        int(main_window.spin_vectorscope_warn_threshold.value())
    )
    update_vectorscope_warning_label(main_window)
    main_window._request_save_settings()


def apply_mode_settings(main_window, save: bool = True):
    # 更新モード切替と関連パラメータの反映を一箇所に集約。
    mode = selected_mode(main_window)
    main_window.worker.set_mode(mode)
    main_window.worker.set_diff_threshold(main_window.spin_diff.value())
    main_window.worker.set_stable_frames(main_window.spin_stable.value())
    sync_mode_dependent_rows(main_window)
    if save:
        main_window._request_save_settings()


def load_settings(main_window):
    # 初期ロード中は保存トリガーを抑止する。
    cfg = load_config()
    main_window._settings_load_in_progress = True
    try:
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
        # 散布図形状は安全な候補値へ正規化してからUIへ反映。
        scatter_shape_raw = str(cfg.get(C.CFG_SCATTER_SHAPE, C.DEFAULT_SCATTER_SHAPE))
        scatter_shape = safe_choice(
            scatter_shape_raw,
            C.SCATTER_SHAPES,
            C.DEFAULT_SCATTER_SHAPE,
        )
        scatter_render_mode_raw = str(
            cfg.get(C.CFG_SCATTER_RENDER_MODE, C.DEFAULT_SCATTER_RENDER_MODE)
        )
        scatter_render_mode = safe_choice(
            scatter_render_mode_raw,
            C.SCATTER_RENDER_MODES,
            C.DEFAULT_SCATTER_RENDER_MODE,
        )
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
        main_window.scatter.set_shape(scatter_shape)
        main_window.scatter.set_render_mode(scatter_render_mode)
        # フィルター状態は UI 側の現在値から再適用する。
        main_window.scatter.set_hue_filter(
            selected_scatter_hue_filter_enabled(main_window),
            selected_scatter_hue_center(main_window),
        )
        sync_scatter_filter_controls(main_window)
        _apply_combo_choice(
            main_window.combo_wheel_mode,
            str(cfg.get(C.CFG_WHEEL_MODE, C.DEFAULT_WHEEL_MODE)),
            C.WHEEL_MODES,
            C.DEFAULT_WHEEL_MODE,
        )
        rgb_hist_mode_raw = cfg.get(C.CFG_RGB_HIST_MODE, C.DEFAULT_RGB_HIST_MODE)
        rgb_hist_mode = safe_choice(
            rgb_hist_mode_raw,
            C.RGB_HIST_MODES,
            C.DEFAULT_RGB_HIST_MODE,
        )
        _apply_combo_choice(
            main_window.combo_rgb_hist_mode,
            rgb_hist_mode_raw,
            C.RGB_HIST_MODES,
            C.DEFAULT_RGB_HIST_MODE,
        )
        main_window.rgb_hist_view.set_display_mode(rgb_hist_mode)
        wheel_sat_threshold = _cfg_int(
            cfg,
            C.CFG_WHEEL_SAT_THRESHOLD,
            C.DEFAULT_WHEEL_SAT_THRESHOLD,
            C.WHEEL_SAT_THRESHOLD_MIN,
            C.WHEEL_SAT_THRESHOLD_MAX,
        )
        _set_value_blocked(main_window.spin_wheel_sat_threshold, wheel_sat_threshold)
        main_window.wheel.set_mode(selected_wheel_mode(main_window))
        main_window.worker.set_wheel_sat_threshold(wheel_sat_threshold)
        main_window.worker.set_graph_every(C.DEFAULT_GRAPH_EVERY)
        _apply_combo_choice(
            main_window.combo_capture_source,
            cfg.get(C.CFG_CAPTURE_SOURCE, C.DEFAULT_CAPTURE_SOURCE),
            C.CAPTURE_SOURCES,
            C.DEFAULT_CAPTURE_SOURCE,
        )
        main_window._apply_capture_source(save=False)
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
            safe_int(
                cfg.get(C.CFG_STABLE_FRAMES, C.DEFAULT_STABLE_FRAMES), C.DEFAULT_STABLE_FRAMES
            ),
        )
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

        # 表示設定まで含めてロード完了後の状態を同期。
        apply_mode_settings(main_window, save=False)
        main_window.apply_layout_from_config(cfg)
        main_window.refresh_layout_preset_views()
        main_window._sync_worker_view_flags()
    finally:
        main_window._settings_load_in_progress = False


def save_settings(main_window, silent: bool = True):
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
