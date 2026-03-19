"""設定UIの同期・適用ロジック。"""

from ...util import constants as C
from ...util.qt_helpers import (
    blocked_signals,
    set_enabled_if,
    set_visible_if,
)
from .settings_values import (
    selected_analysis_max_dim,
    selected_analysis_resolution_mode,
    selected_binary_preset,
    selected_color_band_harmony_guide_enabled,
    selected_color_band_use_wheel_harmony,
    selected_color_band_use_wheel_sat_threshold,
    selected_composition_guide,
    selected_diff_threshold,
    selected_edge_sensitivity,
    selected_effective_color_band_sat_threshold,
    selected_focus_peak_sensitivity,
    selected_focus_peak_thickness,
    selected_focus_peak_color,
    selected_mirror_mode,
    selected_mode,
    selected_rgb_hist_mode,
    selected_sample_points,
    selected_saliency_overlay_alpha,
    selected_scatter_hue_center,
    selected_scatter_hue_filter_enabled,
    selected_scatter_render_mode,
    selected_scatter_shape,
    selected_squint_blur_sigma,
    selected_squint_mode,
    selected_squint_scale_percent,
    selected_stable_frames,
    selected_ternary_preset,
    selected_ui_theme,
    selected_vectorscope_show_skin_line,
    selected_vectorscope_warn_threshold,
    selected_wheel_harmony_guide_enabled,
    selected_wheel_harmony_guide_type,
    selected_wheel_mode,
    selected_wheel_sat_threshold,
)


def _request_save_if(main_window, *, save: bool) -> None:
    """`save` が True のときだけ設定保存予約を行う。"""
    if save:
        main_window._request_save_settings()


def sync_mode_dependent_rows(main_window):
    """更新モードに応じて関連入力行の表示状態を切り替える。"""
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
    mode = selected_squint_mode(main_window)
    show_scale = mode in (C.SQUINT_MODE_SCALE, C.SQUINT_MODE_SCALE_BLUR)
    show_blur = mode in (C.SQUINT_MODE_BLUR, C.SQUINT_MODE_SCALE_BLUR)
    set_visible_if(main_window._row_squint_scale_settings, show_scale)
    set_visible_if(main_window._row_squint_blur_settings, show_blur)


def sync_analysis_resolution_rows(main_window):
    """解析解像度モードに応じて最大辺入力行の表示を切り替える。"""
    custom_mode = (
        selected_analysis_resolution_mode(main_window) == C.ANALYSIS_RESOLUTION_MODE_CUSTOM
    )
    set_visible_if(main_window._row_analysis_max_dim_settings, custom_mode)
    set_visible_if(getattr(main_window, "_hint_analysis_max_dim_settings", None), custom_mode)


def sync_scatter_filter_controls(main_window):
    """散布図フィルターUIの有効/無効と表示値を同期する。"""
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
        main_window.combo_color_band_harmony_guide, (not use_wheel_harmony) and own_harmony_enabled
    )


def _apply_scatter_view_from_ui(main_window) -> None:
    """散布図ビューへ現在UI値を反映する。"""
    main_window.scatter.set_shape(selected_scatter_shape(main_window))
    main_window.scatter.set_render_mode(selected_scatter_render_mode(main_window))
    main_window.scatter.set_hue_filter(
        selected_scatter_hue_filter_enabled(main_window),
        selected_scatter_hue_center(main_window),
    )
    sync_scatter_filter_controls(main_window)


def _invalidate_color_band_snapshot_cache(main_window) -> None:
    """配色比率再計算が必要なスナップショット項目を無効化する。"""
    snapshot = getattr(main_window, "_latest_result_snapshot", None)
    if not isinstance(snapshot, dict):
        return
    for key in ("top_colors", "top_colors_full", "top_colors_filtered", "top_colors_key"):
        snapshot[key] = None
    main_window._latest_result_snapshot = snapshot


def _refresh_color_band_related_views(main_window) -> None:
    """配色比率関連ビューを現在設定で再同期する。"""
    if hasattr(main_window, "_restore_dock_from_snapshot"):
        main_window._restore_dock_from_snapshot(getattr(main_window, "dock_color_band", None))
    if hasattr(main_window, "_on_color_chip_selected") and hasattr(main_window, "list_color_chips"):
        main_window._on_color_chip_selected(int(main_window.list_color_chips.currentRow()))


def _apply_composition_guide_to_views(main_window, guide: str) -> None:
    """構図ガイド設定を関連ビューへ反映する。"""
    main_window.saliency_view.set_composition_guide(guide)
    main_window.preview_window.set_composition_guide(guide)


def _apply_vectorscope_view_state(
    main_window,
    *,
    show_skin_line: bool,
    warn_threshold: int,
) -> None:
    """ベクトルスコープ表示設定をビューへ反映する。"""
    main_window.vectorscope_view.set_show_skin_tone_line(bool(show_skin_line))
    main_window.vectorscope_view.set_warn_threshold(int(warn_threshold))
    update_vectorscope_warning_label(main_window)


def apply_sample_points_settings(main_window, *_, save: bool = True):
    """サンプル点数設定をワーカーへ反映する。"""
    main_window.worker.set_sample_points(selected_sample_points(main_window))
    _request_save_if(main_window, save=save)


def apply_theme_settings(main_window, *_, save: bool = True):
    """UIテーマ設定をアプリ全体へ反映する。"""
    main_window._apply_ui_style(selected_ui_theme(main_window))
    _request_save_if(main_window, save=save)


def apply_scatter_settings(main_window, *_, save: bool = True):
    """散布図表示設定をビューへ反映する。"""
    _apply_scatter_view_from_ui(main_window)
    _request_save_if(main_window, save=save)


def apply_analysis_resolution_settings(main_window, *_args, save: bool = True):
    """解析解像度設定をワーカーへ反映する。"""
    mode = selected_analysis_resolution_mode(main_window)
    max_dim = selected_analysis_max_dim(main_window)
    if mode == C.ANALYSIS_RESOLUTION_MODE_ORIGINAL:
        main_window.worker.set_max_dim(0)
    else:
        main_window.worker.set_max_dim(max_dim)
        if int(main_window.edit_analysis_max_dim.value()) != int(max_dim):
            with blocked_signals(main_window.edit_analysis_max_dim):
                main_window.edit_analysis_max_dim.setValue(int(max_dim))
    sync_analysis_resolution_rows(main_window)
    _request_save_if(main_window, save=save)


def apply_wheel_settings(main_window, *_, save: bool = True, sync_color_band: bool = True):
    """色相環設定をビューとワーカーへ反映する。"""
    main_window.wheel.set_mode(selected_wheel_mode(main_window))
    main_window.worker.set_wheel_sat_threshold(selected_wheel_sat_threshold(main_window))
    guide_enabled = selected_wheel_harmony_guide_enabled(main_window)
    set_enabled_if(main_window.combo_wheel_harmony_guide, guide_enabled)
    main_window.wheel.set_harmony_guide_enabled(guide_enabled)
    main_window.wheel.set_harmony_guide_type(selected_wheel_harmony_guide_type(main_window))
    if hasattr(main_window, "list_color_chips") and hasattr(main_window, "_on_color_chip_selected"):
        main_window._on_color_chip_selected(int(main_window.list_color_chips.currentRow()))
    if sync_color_band and hasattr(main_window, "apply_color_band_settings"):
        main_window.apply_color_band_settings(save=False)
    _request_save_if(main_window, save=save)


def apply_color_band_settings(main_window, *_args, save: bool = True):
    """配色比率設定を反映し、必要なら表示を再計算する。"""
    sync_color_band_controls(main_window)
    main_window.worker.set_color_band_sat_threshold(
        selected_effective_color_band_sat_threshold(main_window)
    )
    _invalidate_color_band_snapshot_cache(main_window)
    _refresh_color_band_related_views(main_window)
    _request_save_if(main_window, save=save)


def on_wheel_harmony_rotation_changed(main_window, _rotation_deg: float):
    """色相環ガイド回転変更時に保存予約を行う。"""
    main_window._request_save_settings()


def apply_rgb_hist_settings(main_window, *_, save: bool = True):
    """RGBヒストグラム設定を反映する。"""
    main_window.rgb_hist_view.set_display_mode(selected_rgb_hist_mode(main_window))
    _request_save_if(main_window, save=save)


def apply_mirror_settings(main_window, *_, save: bool = True):
    """反転表示設定を反映する。"""
    main_window.mirror_view.set_mode(selected_mirror_mode(main_window))
    _request_save_if(main_window, save=save)


def apply_edge_settings(main_window, *_, save: bool = True):
    """エッジビュー設定を反映する。"""
    main_window.edge_view.set_sensitivity(selected_edge_sensitivity(main_window))
    _request_save_if(main_window, save=save)


def apply_binary_settings(main_window, *_, save: bool = True):
    """2値化ビュー設定を反映する。"""
    main_window.binary_view.set_preset(selected_binary_preset(main_window))
    _request_save_if(main_window, save=save)


def apply_ternary_settings(main_window, *_, save: bool = True):
    """3値化ビュー設定を反映する。"""
    main_window.ternary_view.set_preset(selected_ternary_preset(main_window))
    _request_save_if(main_window, save=save)


def apply_saliency_settings(main_window, *_, save: bool = True):
    """サリエンシ表示設定を反映する。"""
    main_window.saliency_view.set_overlay_alpha(selected_saliency_overlay_alpha(main_window))
    _request_save_if(main_window, save=save)


def apply_composition_guide_settings(main_window, *_, save: bool = True):
    """構図ガイド設定を関連ビューへ反映する。"""
    guide = selected_composition_guide(main_window)
    _apply_composition_guide_to_views(main_window, guide)
    _request_save_if(main_window, save=save)


def apply_focus_peaking_settings(main_window, *_, save: bool = True):
    """フォーカスピーキング設定を反映する。"""
    main_window.focus_peaking_view.set_sensitivity(selected_focus_peak_sensitivity(main_window))
    main_window.focus_peaking_view.set_color(selected_focus_peak_color(main_window))
    main_window.focus_peaking_view.set_thickness(selected_focus_peak_thickness(main_window))
    _request_save_if(main_window, save=save)


def apply_squint_settings(main_window, *_, save: bool = True):
    """スクイント表示設定を反映する。"""
    main_window.squint_view.set_mode(selected_squint_mode(main_window))
    main_window.squint_view.set_scale_percent(selected_squint_scale_percent(main_window))
    main_window.squint_view.set_blur_sigma(selected_squint_blur_sigma(main_window))
    sync_squint_mode_rows(main_window)
    _request_save_if(main_window, save=save)


def update_vectorscope_warning_label(main_window):
    """ベクトルスコープ警告ラベルの文言と色を更新する。"""
    from ...util.theme import refresh_widget_style

    ratio = float(main_window.vectorscope_view.high_saturation_ratio())
    threshold = int(main_window.spin_vectorscope_warn_threshold.value())
    if ratio <= 0.001:
        text = "高彩度警告: なし"
        level = "muted"
    else:
        text = f"高彩度警告: しきい値({threshold}%)超え {ratio:.1f}%"
        level = "warn" if ratio < 5.0 else "alert"
    if main_window.lbl_vectorscope_warning.text() != text:
        main_window.lbl_vectorscope_warning.setText(text)
    if main_window.lbl_vectorscope_warning.property("chromaWarnLevel") != level:
        main_window.lbl_vectorscope_warning.setProperty("chromaWarnLevel", level)
        refresh_widget_style(main_window.lbl_vectorscope_warning)


def apply_vectorscope_settings(main_window, *_, save: bool = True):
    """ベクトルスコープ設定を反映する。"""
    _apply_vectorscope_view_state(
        main_window,
        show_skin_line=selected_vectorscope_show_skin_line(main_window),
        warn_threshold=selected_vectorscope_warn_threshold(main_window),
    )
    _request_save_if(main_window, save=save)


def apply_mode_settings(main_window, *_args, save: bool = True):
    """更新モード設定をワーカーとUIへ反映する。"""
    mode = selected_mode(main_window)
    main_window.worker.set_mode(mode)
    main_window.worker.set_diff_threshold(selected_diff_threshold(main_window))
    main_window.worker.set_stable_frames(selected_stable_frames(main_window))
    sync_mode_dependent_rows(main_window)
    _request_save_if(main_window, save=save)
