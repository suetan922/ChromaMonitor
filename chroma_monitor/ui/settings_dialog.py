"""モジュールの補助処理。"""

from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..util import constants as C

_SETTINGS_PAGE_UPDATE = 1
_SETTINGS_PAGE_SCATTER = 2
_SETTINGS_PAGE_WHEEL = 3
_SETTINGS_PAGE_IMAGE = 4
_SETTINGS_PAGE_SALIENCY = 5
_SETTINGS_PAGE_FOCUS = 6
_SETTINGS_PAGE_SQUINT = 7
_SETTINGS_PAGE_VECTORSCOPE = 8
_SETTINGS_PAGE_RGB_HIST = 10
_SETTINGS_PAGE_COLOR_BAND = 11
_SETTINGS_LABEL_TEXTS = (
    "取得元",
    "ターゲット",
    "解析解像度",
    "指定サイズ",
    "更新モード",
    "更新間隔",
    "差分閾値",
    "安定フレーム",
    "表示形状",
    "表示モード",
    "サンプル数",
    "表示方式",
    "彩度しきい値",
    "色彩調和タイプ",
    "エッジ感度",
    "2値化",
    "3値化",
    "重ね具合",
    "構図ガイド",
    "感度",
    "色",
    "線幅",
    "モード",
    "縮小率",
    "ぼかし",
    "高彩度しきい値",
    "プリセット",
    "新規名",
)
_SETTINGS_LABEL_MIN_WIDTH = 88
_SETTINGS_LABEL_MAX_WIDTH = 108
_SETTINGS_LABEL_PAD_PX = 4
_SETTINGS_FIELD_GAP_PX = 4
_SETTINGS_FIELD_SLOT_WIDTH = 460


@lru_cache(maxsize=1)
def _settings_label_width() -> int:
    """設定ラベル幅を最長ラベル基準で算出する。"""
    probe = QLabel()
    metrics = QFontMetrics(probe.font())
    longest = max(metrics.horizontalAdvance(text) for text in _SETTINGS_LABEL_TEXTS)
    target = int(longest + _SETTINGS_LABEL_PAD_PX)
    return max(_SETTINGS_LABEL_MIN_WIDTH, min(_SETTINGS_LABEL_MAX_WIDTH, target))


def _settings_row_width() -> int:
    """ラベル幅と入力欄スロット幅から1行の固定幅を返す。"""
    return int(_settings_label_width() + _SETTINGS_FIELD_GAP_PX + _SETTINGS_FIELD_SLOT_WIDTH)


def _preferred_field_width(widget: QWidget) -> int:
    """設定ダイアログ内で使う入力欄の妥当な表示幅を返す。"""
    width = max(
        int(widget.minimumWidth()),
        int(widget.minimumSizeHint().width()),
        int(widget.sizeHint().width()),
    )
    if isinstance(widget, QAbstractSpinBox):
        return max(120, min(180, width))
    if isinstance(widget, QLineEdit):
        return max(320, min(460, width))
    if isinstance(widget, QComboBox):
        minimum = 380 if widget.isEditable() else 220
        maximum = 460 if widget.isEditable() else 320
        return max(minimum, min(maximum, width))
    return max(220, min(460, width))


def _wrap_setting_field(widget: QWidget) -> QWidget:
    """入力欄を左寄せのコンテナへ包み、必要なら単位ラベルも添える。"""
    field_width = _preferred_field_width(widget)
    widget.setFixedWidth(int(field_width))

    policy = widget.sizePolicy()
    policy.setHorizontalPolicy(
        QSizePolicy.Fixed if isinstance(widget, QAbstractSpinBox) else QSizePolicy.Preferred
    )
    widget.setSizePolicy(policy)

    holder = QWidget()
    holder.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    holder_layout = QHBoxLayout(holder)
    holder_layout.setContentsMargins(0, 0, 0, 0)
    holder_layout.setSpacing(6)
    holder_layout.addWidget(widget, 0)

    unit_text = str(getattr(widget, "_chroma_unit_label_text", "")).strip()
    if unit_text:
        unit_label = QLabel(unit_text)
        unit_label.setStyleSheet("color:#4b5563;")
        unit_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        holder_layout.addWidget(unit_label, 0)

    holder_layout.addStretch(1)
    holder.setFixedWidth(_SETTINGS_FIELD_SLOT_WIDTH)
    return holder


def _make_labeled_row(label_text: str, widget: QWidget) -> QWidget:
    """左ラベルと入力ウィジェットを並べた設定行を作る。"""
    # 左ラベル + 右入力ウィジェットの共通行を作る。
    row = QWidget()
    row.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(_SETTINGS_FIELD_GAP_PX)
    label = QLabel(label_text)
    label.setFixedWidth(_settings_label_width())
    label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    layout.addWidget(label, 0)
    layout.addWidget(_wrap_setting_field(widget), 0)
    row.setFixedWidth(_settings_row_width())
    return row


def _add_left_aligned_widget(layout: QVBoxLayout, widget: QWidget) -> None:
    """設定ページ上へ左寄せでウィジェットを追加する。"""
    layout.addWidget(widget, 0, Qt.AlignLeft | Qt.AlignTop)


def _make_hint_label(text: str, *, word_wrap: bool = False) -> QLabel:
    """設定説明向けの補助ラベルを作る。"""
    # 補足説明の見た目を統一する。
    hint = QLabel(text)
    hint.setStyleSheet("color:#6b7280;")
    hint.setWordWrap(bool(word_wrap))
    return hint


def _create_settings_page(spacing: int = 10) -> tuple[QWidget, QVBoxLayout]:
    """設定ページのルートウィジェットと縦レイアウトを作る。"""
    # 設定ページの余白と行間を統一する。
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(int(spacing))
    layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    return page, layout


def show_settings_window(main_window, page_index: int = 0):
    """設定ダイアログを生成または再利用して指定ページを表示する。"""
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
                "色相環",
                "配色比率",
                "散布図",
                "ベクトルスコープ",
                "エッジ/2値化/3値化",
                "RGBヒストグラム",
                "フォーカスピーキング",
                "スクイント表示",
                "サリエンシー",
                "レイアウト",
            ]
        )

        pages = QStackedWidget()

        # --- キャプチャ設定ページ ---
        page_capture, lc = _create_settings_page()
        _add_left_aligned_widget(lc, _make_labeled_row("取得元", main_window.combo_capture_source))
        main_window._row_target_settings = _make_labeled_row("ターゲット", main_window.combo_win)
        _add_left_aligned_widget(lc, main_window._row_target_settings)
        lc.addWidget(main_window.btn_pick_roi_win)
        lc.addWidget(main_window.btn_pick_roi_screen)
        _add_left_aligned_widget(
            lc,
            _make_labeled_row("解析解像度", main_window.combo_analysis_resolution_mode),
        )
        main_window._row_analysis_max_dim_settings = _make_labeled_row(
            "指定サイズ", main_window.edit_analysis_max_dim
        )
        _add_left_aligned_widget(lc, main_window._row_analysis_max_dim_settings)
        main_window._hint_analysis_max_dim_settings = _make_hint_label(
            "指定サイズは、縦横比を保ったまま長辺が入力した値になるよう縮小して解析します。",
            word_wrap=True,
        )
        lc.addWidget(main_window._hint_analysis_max_dim_settings)
        lc.addWidget(main_window.chk_preview_window)
        lc.addStretch(1)
        pages.addWidget(page_capture)

        # --- 更新設定ページ ---
        page_update, lu = _create_settings_page()
        _add_left_aligned_widget(lu, _make_labeled_row("更新モード", main_window.combo_mode))
        main_window._row_interval_settings = _make_labeled_row(
            "更新間隔", main_window.spin_interval
        )
        _add_left_aligned_widget(lu, main_window._row_interval_settings)
        main_window._row_diff_settings = _make_labeled_row("差分閾値", main_window.spin_diff)
        _add_left_aligned_widget(lu, main_window._row_diff_settings)
        main_window._hint_diff_settings = _make_hint_label(
            "値を下げるほど小さな変化にも反応し、上げるほど大きな変化のみで更新します。",
            word_wrap=True,
        )
        lu.addWidget(main_window._hint_diff_settings)
        main_window._row_stable_settings = _make_labeled_row(
            "安定フレーム", main_window.spin_stable
        )
        _add_left_aligned_widget(lu, main_window._row_stable_settings)
        main_window._hint_stable_settings = _make_hint_label(
            "変化検知後、このフレーム数だけ安定した状態が続くと更新します。",
            word_wrap=True,
        )
        lu.addWidget(main_window._hint_stable_settings)
        lu.addStretch(1)
        pages.addWidget(page_update)

        # --- 散布図設定ページ ---
        page_scatter, ls = _create_settings_page()
        ls.addWidget(_make_hint_label("散布図のサンプル数を設定します"))
        _add_left_aligned_widget(ls, _make_labeled_row("表示形状", main_window.combo_scatter_shape))
        _add_left_aligned_widget(ls, _make_labeled_row("表示モード", main_window.combo_scatter_render_mode))
        _add_left_aligned_widget(ls, _make_labeled_row("サンプル数", main_window.spin_points))
        ls.addStretch(1)
        pages.addWidget(page_scatter)

        # --- 色相環設定ページ ---
        page_wheel, lw = _create_settings_page()
        lw.addWidget(_make_hint_label("色相環の色相分類方式を設定します"))
        _add_left_aligned_widget(lw, _make_labeled_row("表示方式", main_window.combo_wheel_mode))
        _add_left_aligned_widget(lw, _make_labeled_row("彩度しきい値", main_window.spin_wheel_sat_threshold))
        lw.addWidget(
            _make_hint_label(
                "色相環: 0 のときは無彩色も含みます。1 以上では「しきい値未満」を除外します。",
                word_wrap=True,
            )
        )
        lw.addWidget(main_window.chk_wheel_harmony_guide)
        _add_left_aligned_widget(
            lw,
            _make_labeled_row("色彩調和タイプ", main_window.combo_wheel_harmony_guide),
        )
        lw.addWidget(_make_hint_label("ガイド表示中は色相環内側を左ドラッグで回転できます。"))
        lw.addStretch(1)
        pages.addWidget(page_wheel)

        # --- エッジ/2値/3値ページ ---
        page_image, li = _create_settings_page()
        li.addWidget(QLabel("エッジ・2値化・3値化の見え方を調整できます"))
        _add_left_aligned_widget(li, _make_labeled_row("エッジ感度", main_window.spin_edge_sensitivity))
        _add_left_aligned_widget(li, _make_labeled_row("2値化", main_window.combo_binary_preset))
        _add_left_aligned_widget(li, _make_labeled_row("3値化", main_window.combo_ternary_preset))
        li.addStretch(1)
        pages.addWidget(page_image)

        # --- サリエンシーページ ---
        page_saliency, lsal = _create_settings_page()
        lsal.addWidget(QLabel("サリエンシーマップ（スペクトル残差）を調整します"))
        _add_left_aligned_widget(lsal, _make_labeled_row("重ね具合", main_window.spin_saliency_alpha))
        _add_left_aligned_widget(lsal, _make_labeled_row("構図ガイド", main_window.combo_composition_guide))
        lsal.addStretch(1)
        pages.addWidget(page_saliency)

        # --- フォーカスピーキングページ ---
        page_focus, lfocus = _create_settings_page()
        lfocus.addWidget(QLabel("フォーカスピーキングを調整します"))
        _add_left_aligned_widget(lfocus, _make_labeled_row("感度", main_window.spin_focus_peak_sensitivity))
        _add_left_aligned_widget(lfocus, _make_labeled_row("色", main_window.combo_focus_peak_color))
        _add_left_aligned_widget(lfocus, _make_labeled_row("線幅", main_window.spin_focus_peak_thickness))
        lfocus.addStretch(1)
        pages.addWidget(page_focus)

        # --- スクイントページ ---
        page_squint, lsq = _create_settings_page()
        lsq.addWidget(QLabel("スクイント表示を調整します"))
        _add_left_aligned_widget(lsq, _make_labeled_row("モード", main_window.combo_squint_mode))
        main_window._row_squint_scale_settings = _make_labeled_row(
            "縮小率", main_window.spin_squint_scale
        )
        _add_left_aligned_widget(lsq, main_window._row_squint_scale_settings)
        main_window._row_squint_blur_settings = _make_labeled_row(
            "ぼかし", main_window.spin_squint_blur
        )
        _add_left_aligned_widget(lsq, main_window._row_squint_blur_settings)
        lsq.addStretch(1)
        pages.addWidget(page_squint)

        # --- ベクトルスコープページ ---
        page_vectorscope, lvec = _create_settings_page()
        lvec.addWidget(QLabel("YUVベクトルスコープ表示を調整します"))
        lvec.addWidget(main_window.chk_vectorscope_skin_line)
        _add_left_aligned_widget(
            lvec,
            _make_labeled_row("高彩度しきい値", main_window.spin_vectorscope_warn_threshold),
        )
        lvec.addStretch(1)
        pages.addWidget(page_vectorscope)

        # --- レイアウトページ ---
        page_layout, ll = _create_settings_page()
        ll.addWidget(QLabel("現在の表示配置をプリセットとして保存できます"))
        _add_left_aligned_widget(ll, _make_labeled_row("プリセット", main_window.combo_layout_presets))
        _add_left_aligned_widget(ll, _make_labeled_row("新規名", main_window.edit_preset_name))
        row_btn = QHBoxLayout()
        row_btn.setContentsMargins(0, 0, 0, 0)
        row_btn.addWidget(main_window.btn_load_preset)
        row_btn.addWidget(main_window.btn_save_preset)
        row_btn.addWidget(main_window.btn_delete_preset)
        ll.addLayout(row_btn)
        ll.addStretch(1)
        pages.addWidget(page_layout)

        # --- RGBヒストグラムページ ---
        page_rgb_hist, lrgb = _create_settings_page()
        lrgb.addWidget(QLabel("R/G/Bヒストグラムの表示方式を切り替えます"))
        _add_left_aligned_widget(lrgb, _make_labeled_row("表示方式", main_window.combo_rgb_hist_mode))
        lrgb.addStretch(1)
        pages.addWidget(page_rgb_hist)

        # --- 配色比率設定ページ ---
        page_color_band, lcb = _create_settings_page()
        lcb.addWidget(_make_hint_label("配色比率の集計条件と配色候補表示を設定します"))
        lcb.addWidget(main_window.chk_color_band_use_wheel_sat_threshold)
        _add_left_aligned_widget(
            lcb,
            _make_labeled_row("彩度しきい値", main_window.spin_color_band_sat_threshold),
        )
        lcb.addWidget(
            _make_hint_label(
                "配色比率: 0 のときは無彩色を含みます。1 以上では「しきい値未満」を除外し、有彩色のみで割合を計算します。",
                word_wrap=True,
            )
        )
        lcb.addWidget(main_window.chk_color_band_use_wheel_harmony)
        lcb.addWidget(main_window.chk_color_band_harmony_guide)
        _add_left_aligned_widget(
            lcb,
            _make_labeled_row("色彩調和タイプ", main_window.combo_color_band_harmony_guide),
        )
        lcb.addStretch(1)
        pages.addWidget(page_color_band)

        main_window._settings_nav_to_page = [
            C.SETTINGS_PAGE_CAPTURE,
            _SETTINGS_PAGE_UPDATE,
            _SETTINGS_PAGE_WHEEL,
            _SETTINGS_PAGE_COLOR_BAND,
            _SETTINGS_PAGE_SCATTER,
            _SETTINGS_PAGE_VECTORSCOPE,
            _SETTINGS_PAGE_IMAGE,
            _SETTINGS_PAGE_RGB_HIST,
            _SETTINGS_PAGE_FOCUS,
            _SETTINGS_PAGE_SQUINT,
            _SETTINGS_PAGE_SALIENCY,
            C.SETTINGS_PAGE_LAYOUT,
        ]
        main_window._settings_page_to_nav = {
            p: i for i, p in enumerate(main_window._settings_nav_to_page)
        }

        def _on_nav_row_changed(row: int):
            """ナビゲーション選択に対応するページを表示する。"""
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
        max_page = C.SETTINGS_PAGE_LAYOUT
        if hasattr(main_window, "_settings_nav_to_page") and main_window._settings_nav_to_page:
            max_page = int(max(main_window._settings_nav_to_page))
        page = max(0, min(max_page, int(page_index)))
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
    if hasattr(main_window, "_sync_color_band_controls"):
        main_window._sync_color_band_controls()
    if created:
        main_window._settings_window.resize(760, 520)
    main_window._present_settings_window(center_on_parent=created)


def hide_settings_window(main_window):
    """設定ダイアログを破棄せずに非表示へ切り替える。"""
    # 破棄せず非表示にする（再表示を速くするため）。
    if hasattr(main_window, "_settings_window"):
        main_window._settings_window.hide()
