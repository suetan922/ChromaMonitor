"""設定ダイアログの各ページ構築 helper。"""

from PySide6.QtWidgets import QHBoxLayout, QStackedWidget

from .settings_dialog_layout import (
    add_hint_rows_settings_page,
    add_labeled_row,
    create_settings_page,
    make_hint_label,
    preferred_field_width,
)


def add_capture_settings_page(main_window, pages: QStackedWidget) -> None:
    """取得元と解析解像度ページを追加する。"""
    page_capture, capture_layout = create_settings_page()
    capture_field_width = preferred_field_width(main_window.combo_win)
    add_labeled_row(capture_layout, "取得元", main_window.combo_capture_source)
    main_window._row_target_settings = add_labeled_row(
        capture_layout,
        "ターゲット",
        main_window.combo_win,
        field_width=capture_field_width,
    )
    main_window._row_pick_roi_win_settings = add_labeled_row(
        capture_layout,
        "",
        main_window.btn_pick_roi_win,
        field_width=capture_field_width,
    )
    main_window._row_pick_roi_screen_settings = add_labeled_row(
        capture_layout,
        "",
        main_window.btn_pick_roi_screen,
        field_width=capture_field_width,
    )
    add_labeled_row(capture_layout, "解析解像度", main_window.combo_analysis_resolution_mode)
    main_window._row_analysis_max_dim_settings = add_labeled_row(
        capture_layout,
        "指定サイズ",
        main_window.edit_analysis_max_dim,
    )
    main_window._hint_analysis_max_dim_settings = make_hint_label(
        "指定サイズは、縦横比を保ったまま長辺が入力した値になるよう縮小して解析します。",
        word_wrap=True,
    )
    capture_layout.addWidget(main_window._hint_analysis_max_dim_settings)
    capture_layout.addWidget(main_window.chk_preview_window)
    capture_layout.addStretch(1)
    pages.addWidget(page_capture)


def add_update_settings_page(main_window, pages: QStackedWidget) -> None:
    """更新条件ページを追加する。"""
    page_update, update_layout = create_settings_page()
    add_labeled_row(update_layout, "更新モード", main_window.combo_mode)
    main_window._row_interval_settings = add_labeled_row(
        update_layout,
        "更新間隔",
        main_window.spin_interval,
    )
    main_window._row_diff_settings = add_labeled_row(
        update_layout,
        "差分閾値",
        main_window.spin_diff,
    )
    main_window._hint_diff_settings = make_hint_label(
        "値を下げるほど小さな変化にも反応し、上げるほど大きな変化のみで更新します。",
        word_wrap=True,
    )
    update_layout.addWidget(main_window._hint_diff_settings)
    main_window._row_stable_settings = add_labeled_row(
        update_layout,
        "安定フレーム",
        main_window.spin_stable,
    )
    main_window._hint_stable_settings = make_hint_label(
        "変化検知後、このフレーム数だけ安定した状態が続くと更新します。",
        word_wrap=True,
    )
    update_layout.addWidget(main_window._hint_stable_settings)
    update_layout.addStretch(1)
    pages.addWidget(page_update)


def add_color_analysis_pages(main_window, pages: QStackedWidget) -> None:
    """色相環、配色比率、散布図、ベクトルスコープ関連ページを追加する。"""
    page_wheel, wheel_layout = create_settings_page()
    wheel_layout.addWidget(make_hint_label("色相環の色相分類方式を設定します"))
    add_labeled_row(wheel_layout, "表示方式", main_window.combo_wheel_mode)
    add_labeled_row(wheel_layout, "彩度しきい値", main_window.spin_wheel_sat_threshold)
    wheel_layout.addWidget(
        make_hint_label(
            "色相環: 0 のときは無彩色も含みます。1 以上では「しきい値未満」を除外します。",
            word_wrap=True,
        )
    )
    wheel_layout.addWidget(main_window.chk_wheel_harmony_guide)
    add_labeled_row(wheel_layout, "色彩調和タイプ", main_window.combo_wheel_harmony_guide)
    wheel_layout.addWidget(make_hint_label("ガイド表示中は色相環内側を左ドラッグで回転できます。"))
    wheel_layout.addStretch(1)
    pages.addWidget(page_wheel)

    page_color_band, color_band_layout = create_settings_page()
    color_band_layout.addWidget(make_hint_label("配色比率の集計条件と配色候補表示を設定します"))
    color_band_layout.addWidget(main_window.chk_color_band_use_wheel_sat_threshold)
    add_labeled_row(
        color_band_layout,
        "彩度しきい値",
        main_window.spin_color_band_sat_threshold,
    )
    color_band_layout.addWidget(
        make_hint_label(
            "配色比率: 0 のときは無彩色を含みます。1 以上では「しきい値未満」を除外し、有彩色のみで割合を計算します。",
            word_wrap=True,
        )
    )
    color_band_layout.addWidget(main_window.chk_color_band_use_wheel_harmony)
    color_band_layout.addWidget(main_window.chk_color_band_harmony_guide)
    add_labeled_row(
        color_band_layout,
        "色彩調和タイプ",
        main_window.combo_color_band_harmony_guide,
    )
    color_band_layout.addStretch(1)
    pages.addWidget(page_color_band)

    add_hint_rows_settings_page(
        pages,
        hint="散布図のサンプル数を設定します",
        rows=[
            ("表示形状", main_window.combo_scatter_shape),
            ("表示モード", main_window.combo_scatter_render_mode),
            ("サンプル数", main_window.spin_points),
        ],
    )

    page_vectorscope, vectorscope_layout = create_settings_page()
    vectorscope_layout.addWidget(make_hint_label("YUVベクトルスコープ表示を調整します"))
    vectorscope_layout.addWidget(main_window.chk_vectorscope_skin_line)
    add_labeled_row(
        vectorscope_layout,
        "高彩度しきい値",
        main_window.spin_vectorscope_warn_threshold,
    )
    vectorscope_layout.addStretch(1)
    pages.addWidget(page_vectorscope)


def add_image_processing_pages(main_window, pages: QStackedWidget) -> None:
    """画像加工系 view の設定ページを追加する。"""
    add_hint_rows_settings_page(
        pages,
        hint="反転表示の方向を設定します",
        rows=[("反転方向", main_window.combo_mirror_mode)],
    )
    add_hint_rows_settings_page(
        pages,
        hint="エッジ検出の見え方を調整します",
        rows=[("エッジ感度", main_window.spin_edge_sensitivity)],
    )
    add_hint_rows_settings_page(
        pages,
        hint="2値化/3値化表示の方式を設定します",
        rows=[
            ("2値化", main_window.combo_binary_preset),
            ("3値化", main_window.combo_ternary_preset),
        ],
    )


def add_image_view_tuning_pages(main_window, pages: QStackedWidget) -> None:
    """ヒストグラム/フォーカス/スクイント/サリエンシー設定ページを追加する。"""
    add_hint_rows_settings_page(
        pages,
        hint="R/G/Bヒストグラムの表示方式を切り替えます",
        rows=[("表示方式", main_window.combo_rgb_hist_mode)],
    )
    add_hint_rows_settings_page(
        pages,
        hint="フォーカスピーキングを調整します",
        rows=[
            ("感度", main_window.spin_focus_peak_sensitivity),
            ("色", main_window.combo_focus_peak_color),
            ("線幅", main_window.spin_focus_peak_thickness),
        ],
    )

    squint_rows = add_hint_rows_settings_page(
        pages,
        hint="スクイント表示を調整します",
        rows=[
            ("モード", main_window.combo_squint_mode),
            ("縮小率", main_window.spin_squint_scale),
            ("ぼかし", main_window.spin_squint_blur),
        ],
    )
    main_window._row_squint_scale_settings = squint_rows[1]
    main_window._row_squint_blur_settings = squint_rows[2]

    add_hint_rows_settings_page(
        pages,
        hint="サリエンシーマップ（スペクトル残差）を調整します",
        rows=[
            ("重ね具合", main_window.spin_saliency_alpha),
            ("構図ガイド", main_window.combo_composition_guide),
        ],
    )


def add_layout_settings_page(main_window, pages: QStackedWidget) -> None:
    """レイアウト保存ページを追加する。"""
    page_layout, layout_settings = create_settings_page()
    layout_settings.addWidget(make_hint_label("現在の表示配置をプリセットとして保存できます"))
    layout_field_width = max(
        preferred_field_width(main_window.combo_layout_presets),
        preferred_field_width(main_window.edit_preset_name),
    )
    add_labeled_row(
        layout_settings,
        "プリセット",
        main_window.combo_layout_presets,
        field_width=layout_field_width,
    )
    add_labeled_row(
        layout_settings,
        "新規名",
        main_window.edit_preset_name,
        field_width=layout_field_width,
    )
    row_btn = QHBoxLayout()
    row_btn.setContentsMargins(0, 0, 0, 0)
    row_btn.addWidget(main_window.btn_load_preset)
    row_btn.addWidget(main_window.btn_save_preset)
    row_btn.addWidget(main_window.btn_delete_preset)
    layout_settings.addLayout(row_btn)
    layout_settings.addStretch(1)
    pages.addWidget(page_layout)


def add_legacy_and_app_pages(main_window, pages: QStackedWidget) -> None:
    """互換用 legacy ページを追加する。"""
    _ = main_window
    page_ternary_legacy, ternary_legacy_layout = create_settings_page()
    ternary_legacy_layout.addWidget(
        make_hint_label("3値化設定は「2値化/3値化」へ統合しました。")
    )
    ternary_legacy_layout.addStretch(1)
    pages.addWidget(page_ternary_legacy)


def add_app_settings_page(main_window, pages: QStackedWidget) -> None:
    """アプリ全体の設定ページを追加する。"""
    add_hint_rows_settings_page(
        pages,
        hint="アプリ全体で使う配色テーマを切り替えます",
        rows=[("テーマ", main_window.combo_ui_theme)],
    )
