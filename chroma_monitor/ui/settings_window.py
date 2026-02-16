from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..util import constants as C


def _make_labeled_row(label_text: str, widget: QWidget) -> QWidget:
    # 左ラベル + 右入力ウィジェットの共通行を作る。
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QLabel(label_text))
    layout.addWidget(widget, 1)
    return row


def _make_hint_label(text: str, *, word_wrap: bool = False) -> QLabel:
    # 補足説明の見た目を統一する。
    hint = QLabel(text)
    hint.setStyleSheet("color:#6b7280;")
    hint.setWordWrap(bool(word_wrap))
    return hint


def show_settings_window(main_window, page_index: int = 0):
    # 表示前にレイアウトプリセット一覧を最新化する。
    main_window.refresh_layout_preset_views()
    created = False
    if not hasattr(main_window, "_settings_window"):
        created = True
        # 設定ダイアログは初回のみ生成し、以後は再利用する。
        main_window._settings_window = QDialog(main_window)
        main_window._settings_window.setWindowTitle("設定")
        main_window._settings_window.setMinimumSize(680, 460)

        root = QHBoxLayout(main_window._settings_window)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        nav = QListWidget()
        nav.setFixedWidth(170)
        nav.addItems(
            [
                "キャプチャ",
                "更新",
                "色相リング",
                "散布図",
                "ベクトルスコープ",
                "エッジ/2値化/3値化",
                "フォーカスピーキング",
                "スクイント表示",
                "サリエンシー",
                "レイアウト",
            ]
        )

        pages = QStackedWidget()

        # --- キャプチャ設定ページ ---
        page_capture = QWidget()
        lc = QVBoxLayout(page_capture)
        lc.setContentsMargins(8, 8, 8, 8)
        lc.setSpacing(10)
        lc.addWidget(_make_labeled_row("取得元", main_window.combo_capture_source))
        main_window._row_target_settings = _make_labeled_row("ターゲット", main_window.combo_win)
        lc.addWidget(main_window._row_target_settings)
        lc.addWidget(main_window.btn_refresh)
        lc.addWidget(main_window.btn_pick_roi_win)
        lc.addWidget(main_window.btn_pick_roi_screen)
        lc.addWidget(_make_labeled_row("解析解像度", main_window.combo_analysis_resolution_mode))
        main_window._row_analysis_max_dim_settings = _make_labeled_row(
            "指定サイズ", main_window.edit_analysis_max_dim
        )
        lc.addWidget(main_window._row_analysis_max_dim_settings)
        lc.addWidget(
            _make_hint_label(
                "指定サイズは、縦横比を保ったまま長辺がこの値になるよう縮小して解析します。",
                word_wrap=True,
            )
        )
        lc.addWidget(main_window.chk_preview_window)
        lc.addStretch(1)
        pages.addWidget(page_capture)

        # --- 更新設定ページ ---
        page_update = QWidget()
        lu = QVBoxLayout(page_update)
        lu.setContentsMargins(8, 8, 8, 8)
        lu.setSpacing(10)
        lu.addWidget(_make_labeled_row("更新モード", main_window.combo_mode))
        main_window._row_interval_settings = _make_labeled_row(
            "更新間隔", main_window.spin_interval
        )
        lu.addWidget(main_window._row_interval_settings)
        main_window._row_diff_settings = _make_labeled_row("差分閾値", main_window.spin_diff)
        lu.addWidget(main_window._row_diff_settings)
        main_window._hint_diff_settings = _make_hint_label(
            "補足: 値を下げるほど小さな変化にも反応し、上げるほど大きな変化のみで更新します。",
            word_wrap=True,
        )
        lu.addWidget(main_window._hint_diff_settings)
        main_window._row_stable_settings = _make_labeled_row(
            "安定フレーム", main_window.spin_stable
        )
        lu.addWidget(main_window._row_stable_settings)
        main_window._hint_stable_settings = _make_hint_label(
            "補足: 変化検知後、このフレーム数だけ安定した状態が続くと更新します。",
            word_wrap=True,
        )
        lu.addWidget(main_window._hint_stable_settings)
        lu.addStretch(1)
        pages.addWidget(page_update)

        # --- 散布図設定ページ ---
        page_scatter = QWidget()
        ls = QVBoxLayout(page_scatter)
        ls.setContentsMargins(8, 8, 8, 8)
        ls.setSpacing(10)
        ls.addWidget(_make_hint_label("散布図のサンプル点数を設定します"))
        ls.addWidget(_make_labeled_row("表示形状", main_window.combo_scatter_shape))
        ls.addWidget(_make_labeled_row("散布点数", main_window.spin_points))
        ls.addStretch(1)
        pages.addWidget(page_scatter)

        # --- 色相リング設定ページ ---
        page_wheel = QWidget()
        lw = QVBoxLayout(page_wheel)
        lw.setContentsMargins(8, 8, 8, 8)
        lw.setSpacing(10)
        lw.addWidget(_make_hint_label("色相リングの色相分類方式を設定します"))
        lw.addWidget(_make_labeled_row("表示方式", main_window.combo_wheel_mode))
        lw.addWidget(_make_labeled_row("彩度しきい値", main_window.spin_wheel_sat_threshold))
        lw.addWidget(
            _make_hint_label(
                "この値未満の彩度は色相リング集計から除外します。0で最大限拾います。",
                word_wrap=True,
            )
        )
        lw.addStretch(1)
        pages.addWidget(page_wheel)

        # --- エッジ/2値/3値ページ ---
        page_image = QWidget()
        li = QVBoxLayout(page_image)
        li.setContentsMargins(8, 8, 8, 8)
        li.setSpacing(10)
        li.addWidget(QLabel("エッジ・2値化・3値化の見え方を調整できます"))
        li.addWidget(_make_labeled_row("エッジ感度", main_window.spin_edge_sensitivity))
        li.addWidget(_make_labeled_row("2値化", main_window.combo_binary_preset))
        li.addWidget(_make_labeled_row("3値化", main_window.combo_ternary_preset))
        li.addStretch(1)
        pages.addWidget(page_image)

        # --- サリエンシーページ ---
        page_saliency = QWidget()
        lsal = QVBoxLayout(page_saliency)
        lsal.setContentsMargins(8, 8, 8, 8)
        lsal.setSpacing(10)
        lsal.addWidget(QLabel("サリエンシーマップ（スペクトル残差）を調整します"))
        lsal.addWidget(_make_labeled_row("重ね具合", main_window.spin_saliency_alpha))
        lsal.addWidget(_make_labeled_row("構図ガイド", main_window.combo_composition_guide))
        lsal.addStretch(1)
        pages.addWidget(page_saliency)

        # --- フォーカスピーキングページ ---
        page_focus = QWidget()
        lfocus = QVBoxLayout(page_focus)
        lfocus.setContentsMargins(8, 8, 8, 8)
        lfocus.setSpacing(10)
        lfocus.addWidget(QLabel("フォーカスピーキングを調整します"))
        lfocus.addWidget(_make_labeled_row("感度", main_window.spin_focus_peak_sensitivity))
        lfocus.addWidget(_make_labeled_row("色", main_window.combo_focus_peak_color))
        lfocus.addWidget(_make_labeled_row("線幅", main_window.spin_focus_peak_thickness))
        lfocus.addStretch(1)
        pages.addWidget(page_focus)

        # --- スクイントページ ---
        page_squint = QWidget()
        lsq = QVBoxLayout(page_squint)
        lsq.setContentsMargins(8, 8, 8, 8)
        lsq.setSpacing(10)
        lsq.addWidget(QLabel("スクイント表示を調整します"))
        lsq.addWidget(_make_labeled_row("モード", main_window.combo_squint_mode))
        main_window._row_squint_scale_settings = _make_labeled_row(
            "縮小率", main_window.spin_squint_scale
        )
        lsq.addWidget(main_window._row_squint_scale_settings)
        main_window._row_squint_blur_settings = _make_labeled_row(
            "ぼかし", main_window.spin_squint_blur
        )
        lsq.addWidget(main_window._row_squint_blur_settings)
        lsq.addStretch(1)
        pages.addWidget(page_squint)

        # --- ベクトルスコープページ ---
        page_vectorscope = QWidget()
        lvec = QVBoxLayout(page_vectorscope)
        lvec.setContentsMargins(8, 8, 8, 8)
        lvec.setSpacing(10)
        lvec.addWidget(QLabel("YUVベクトルスコープ表示を調整します"))
        lvec.addWidget(main_window.chk_vectorscope_skin_line)
        lvec.addWidget(
            _make_labeled_row("高彩度しきい値", main_window.spin_vectorscope_warn_threshold)
        )
        lvec.addStretch(1)
        pages.addWidget(page_vectorscope)

        # --- レイアウトページ ---
        page_layout = QWidget()
        ll = QVBoxLayout(page_layout)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(10)
        ll.addWidget(QLabel("現在の表示配置をプリセットとして保存できます"))
        ll.addWidget(_make_labeled_row("プリセット", main_window.combo_layout_presets))
        ll.addWidget(_make_labeled_row("新規名", main_window.edit_preset_name))
        row_btn = QHBoxLayout()
        row_btn.setContentsMargins(0, 0, 0, 0)
        row_btn.addWidget(main_window.btn_load_preset)
        row_btn.addWidget(main_window.btn_save_preset)
        row_btn.addWidget(main_window.btn_delete_preset)
        ll.addLayout(row_btn)
        ll.addStretch(1)
        pages.addWidget(page_layout)

        main_window._settings_nav_to_page = [
            C.SETTINGS_PAGE_CAPTURE,
            C.SETTINGS_PAGE_UPDATE,
            C.SETTINGS_PAGE_WHEEL,
            C.SETTINGS_PAGE_SCATTER,
            C.SETTINGS_PAGE_VECTORSCOPE,
            C.SETTINGS_PAGE_IMAGE,
            C.SETTINGS_PAGE_FOCUS,
            C.SETTINGS_PAGE_SQUINT,
            C.SETTINGS_PAGE_SALIENCY,
            C.SETTINGS_PAGE_LAYOUT,
        ]
        main_window._settings_page_to_nav = {
            p: i for i, p in enumerate(main_window._settings_nav_to_page)
        }

        def _on_nav_row_changed(row: int):
            # ナビ選択行 -> 実ページindex を変換して表示する。
            if not hasattr(main_window, "_settings_nav_to_page"):
                return
            if row < 0 or row >= len(main_window._settings_nav_to_page):
                return
            pages.setCurrentIndex(int(main_window._settings_nav_to_page[row]))

        nav.currentRowChanged.connect(_on_nav_row_changed)
        nav.setCurrentRow(0)
        main_window._settings_nav = nav

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(8)
        right_l.addWidget(pages, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_close = QPushButton("閉じる")
        btn_close.clicked.connect(main_window._settings_window.close)
        bottom.addWidget(btn_close)
        right_l.addLayout(bottom)

        root.addWidget(nav)
        root.addWidget(right, 1)

    if hasattr(main_window, "_settings_nav"):
        # 外部からページ指定で開けるよう、行番号へ変換して選択する。
        page = max(0, min(C.SETTINGS_PAGE_LAYOUT, int(page_index)))
        nav_row = (
            main_window._settings_page_to_nav.get(page, 0)
            if hasattr(main_window, "_settings_page_to_nav")
            else 0
        )
        main_window._settings_nav.setCurrentRow(int(nav_row))

    main_window._sync_capture_source_ui()
    main_window._sync_analysis_resolution_rows()
    main_window._sync_mode_dependent_rows()
    main_window._sync_squint_mode_rows()
    if created:
        main_window._settings_window.resize(760, 520)
    main_window._present_settings_window(center_on_parent=created)


def hide_settings_window(main_window):
    # 破棄せず非表示にする（再表示を速くするため）。
    if hasattr(main_window, "_settings_window"):
        main_window._settings_window.hide()
