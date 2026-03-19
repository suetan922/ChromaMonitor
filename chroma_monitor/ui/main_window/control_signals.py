"""MainWindow の control signal 配線補助。"""


def connect_control_signals(main_window) -> None:
    """操作ウィジェットと各種ハンドラのシグナル接続を行う。"""
    connect_capture_control_signals(main_window)
    connect_analysis_control_signals(main_window)
    connect_layout_preset_signals(main_window)


def connect_capture_control_signals(main_window) -> None:
    """取得元選択とROI操作のシグナルを接続する。"""
    main_window.combo_win.currentIndexChanged.connect(main_window.on_window_changed)
    main_window.combo_win.currentTextChanged.connect(main_window.on_window_text_changed)
    main_window.combo_win.activated.connect(main_window.on_window_index_activated)
    text_activated = getattr(main_window.combo_win, "textActivated", None)
    if text_activated is not None:
        text_activated.connect(main_window.on_window_text_activated)
    popup_view = main_window.combo_win.view()
    if popup_view is not None:
        popup_view.pressed.connect(main_window.on_window_popup_row_selected)
        popup_view.clicked.connect(main_window.on_window_popup_row_selected)
    if main_window.combo_win.lineEdit() is not None:
        main_window.combo_win.lineEdit().textEdited.connect(main_window.on_window_text_edited)
        main_window.combo_win.lineEdit().editingFinished.connect(main_window.on_window_text_committed)
    main_window.btn_pick_roi_win.clicked.connect(main_window.pick_roi_in_window)
    main_window.btn_pick_roi_screen.clicked.connect(main_window.pick_roi_on_screen)
    main_window.combo_capture_source.currentIndexChanged.connect(main_window.apply_capture_source)
    main_window.combo_ui_theme.currentIndexChanged.connect(main_window.apply_theme_settings)


def connect_analysis_control_signals(main_window) -> None:
    """解析設定とプレビュー制御のシグナルを接続する。"""
    main_window.spin_interval.valueChanged.connect(
        lambda v: main_window.worker.set_interval(float(v))
    )
    main_window.spin_points.valueChanged.connect(main_window.apply_sample_points_settings)
    main_window.combo_analysis_resolution_mode.currentIndexChanged.connect(
        main_window.apply_analysis_resolution_settings
    )
    main_window.edit_analysis_max_dim.valueChanged.connect(
        main_window.apply_analysis_resolution_settings
    )
    main_window.combo_scatter_shape.currentIndexChanged.connect(main_window.apply_scatter_settings)
    main_window.combo_scatter_render_mode.currentIndexChanged.connect(
        main_window.apply_scatter_settings
    )
    main_window.combo_wheel_mode.currentIndexChanged.connect(main_window.apply_wheel_settings)
    main_window.chk_wheel_harmony_guide.toggled.connect(main_window.apply_wheel_settings)
    main_window.combo_wheel_harmony_guide.currentIndexChanged.connect(
        main_window.apply_wheel_settings
    )
    main_window.combo_rgb_hist_mode.currentIndexChanged.connect(main_window.apply_rgb_hist_settings)
    main_window.combo_mirror_mode.currentIndexChanged.connect(main_window.apply_mirror_settings)
    main_window.spin_wheel_sat_threshold.valueChanged.connect(main_window.apply_wheel_settings)
    main_window.chk_color_band_use_wheel_sat_threshold.toggled.connect(
        main_window.apply_color_band_settings
    )
    main_window.spin_color_band_sat_threshold.valueChanged.connect(
        main_window.apply_color_band_settings
    )
    main_window.chk_color_band_use_wheel_harmony.toggled.connect(
        main_window.apply_color_band_settings
    )
    main_window.chk_color_band_harmony_guide.toggled.connect(main_window.apply_color_band_settings)
    main_window.combo_color_band_harmony_guide.currentIndexChanged.connect(
        main_window.apply_color_band_settings
    )
    main_window.combo_mode.currentIndexChanged.connect(main_window.apply_mode_settings)
    main_window.spin_diff.valueChanged.connect(main_window.apply_mode_settings)
    main_window.spin_stable.valueChanged.connect(main_window.apply_mode_settings)
    main_window.spin_edge_sensitivity.valueChanged.connect(main_window.apply_edge_settings)
    main_window.combo_binary_preset.currentIndexChanged.connect(main_window.apply_binary_settings)
    main_window.combo_ternary_preset.currentIndexChanged.connect(main_window.apply_ternary_settings)
    main_window.spin_saliency_alpha.valueChanged.connect(main_window.apply_saliency_settings)
    main_window.combo_composition_guide.currentIndexChanged.connect(
        main_window.apply_composition_guide_settings
    )
    main_window.spin_focus_peak_sensitivity.valueChanged.connect(
        main_window.apply_focus_peaking_settings
    )
    main_window.combo_focus_peak_color.currentIndexChanged.connect(
        main_window.apply_focus_peaking_settings
    )
    main_window.spin_focus_peak_thickness.valueChanged.connect(
        main_window.apply_focus_peaking_settings
    )
    main_window.combo_squint_mode.currentIndexChanged.connect(main_window.apply_squint_settings)
    main_window.spin_squint_scale.valueChanged.connect(main_window.apply_squint_settings)
    main_window.spin_squint_blur.valueChanged.connect(main_window.apply_squint_settings)
    main_window.chk_vectorscope_skin_line.toggled.connect(main_window.apply_vectorscope_settings)
    main_window.spin_vectorscope_warn_threshold.valueChanged.connect(
        main_window.apply_vectorscope_settings
    )
    main_window.chk_preview_window.toggled.connect(main_window.on_preview_toggled)


def connect_layout_preset_signals(main_window) -> None:
    """レイアウトプリセット操作のシグナルを接続する。"""
    main_window.btn_save_preset.clicked.connect(main_window.save_layout_preset)
    main_window.btn_load_preset.clicked.connect(main_window.load_selected_layout_preset)
    main_window.btn_delete_preset.clicked.connect(main_window.delete_selected_layout_preset)
