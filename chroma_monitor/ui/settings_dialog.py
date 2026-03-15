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
_SETTINGS_PAGE_WHEEL = 2
_SETTINGS_PAGE_COLOR_BAND = 3
_SETTINGS_PAGE_SCATTER = 4
_SETTINGS_PAGE_VECTORSCOPE = 5
_SETTINGS_PAGE_MIRROR = 6
_SETTINGS_PAGE_EDGE = 7
_SETTINGS_PAGE_BINARY = 8
_SETTINGS_PAGE_TERNARY = 10
_SETTINGS_PAGE_RGB_HIST = 11
_SETTINGS_PAGE_FOCUS = 12
_SETTINGS_PAGE_SQUINT = 13
_SETTINGS_PAGE_SALIENCY = 14
_SETTINGS_NAV_SPECS = (
    ("キャプチャ", C.SETTINGS_PAGE_CAPTURE),
    ("更新", _SETTINGS_PAGE_UPDATE),
    ("色相環", _SETTINGS_PAGE_WHEEL),
    ("配色比率", _SETTINGS_PAGE_COLOR_BAND),
    ("散布図", _SETTINGS_PAGE_SCATTER),
    ("ベクトルスコープ", _SETTINGS_PAGE_VECTORSCOPE),
    ("反転表示", _SETTINGS_PAGE_MIRROR),
    ("エッジ検出", _SETTINGS_PAGE_EDGE),
    ("2値化", _SETTINGS_PAGE_BINARY),
    ("3値化", _SETTINGS_PAGE_TERNARY),
    ("R/G/B ヒストグラム", _SETTINGS_PAGE_RGB_HIST),
    ("フォーカスピーキング", _SETTINGS_PAGE_FOCUS),
    ("スクイント表示", _SETTINGS_PAGE_SQUINT),
    ("サリエンシーマップ", _SETTINGS_PAGE_SALIENCY),
    ("レイアウト", C.SETTINGS_PAGE_LAYOUT),
)
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
    "反転方向",
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


def _wrap_setting_field(widget: QWidget, *, field_width: int | None = None) -> QWidget:
    """入力欄を左寄せのコンテナへ包み、必要なら単位ラベルも添える。"""
    field_width = (
        int(field_width) if field_width is not None else int(_preferred_field_width(widget))
    )
    field_width = max(80, min(_SETTINGS_FIELD_SLOT_WIDTH, field_width))
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


def _make_labeled_row(
    label_text: str,
    widget: QWidget,
    *,
    field_width: int | None = None,
) -> QWidget:
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
    layout.addWidget(_wrap_setting_field(widget, field_width=field_width), 0)
    row.setFixedWidth(_settings_label_width() + _SETTINGS_FIELD_GAP_PX + _SETTINGS_FIELD_SLOT_WIDTH)
    return row


def _add_labeled_row(
    layout: QVBoxLayout,
    label_text: str,
    field: QWidget,
    *,
    field_width: int | None = None,
) -> QWidget:
    """ラベル付き入力行を作成して左寄せ追加し、生成行を返す。"""
    row = _make_labeled_row(label_text, field, field_width=field_width)
    layout.addWidget(row, 0, Qt.AlignLeft | Qt.AlignTop)
    return row


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


def _add_hint_rows_settings_page(
    pages: QStackedWidget,
    *,
    hint: str,
    rows: list[tuple[str, QWidget] | tuple[str, QWidget, int]],
) -> list[QWidget]:
    """説明文 + 複数入力行で構成される設定ページを追加し、行を返す。"""
    page, layout = _create_settings_page()
    layout.addWidget(_make_hint_label(hint))
    created_rows: list[QWidget] = []
    for row in rows:
        if len(row) == 3:
            label_text, field, field_width = row
            created = _add_labeled_row(
                layout,
                str(label_text),
                field,
                field_width=int(field_width),
            )
        else:
            label_text, field = row
            created = _add_labeled_row(layout, str(label_text), field)
        created_rows.append(created)
    layout.addStretch(1)
    pages.addWidget(page)
    return created_rows


def _select_requested_settings_page(main_window, page_index: int | None) -> None:
    """指定ページ番号をナビ行へ変換して選択状態を更新する。"""
    if not hasattr(main_window, "_settings_nav"):
        return

    # 外部からページ指定で開けるよう、行番号へ変換して選択する。
    max_page = C.SETTINGS_PAGE_LAYOUT
    if hasattr(main_window, "_settings_nav_to_page") and main_window._settings_nav_to_page:
        max_page = int(max(main_window._settings_nav_to_page))
    requested_page = (
        getattr(main_window, "_settings_last_page", C.SETTINGS_PAGE_CAPTURE)
        if page_index is None
        else page_index
    )
    page = max(0, min(max_page, int(requested_page)))
    nav_row = (
        main_window._settings_page_to_nav.get(page, 0)
        if hasattr(main_window, "_settings_page_to_nav")
        else 0
    )
    main_window._settings_nav.setCurrentRow(int(nav_row))


def show_settings_window(main_window, page_index: int | None = None):
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
        nav.addItems([label for label, _page in _SETTINGS_NAV_SPECS])

        pages = QStackedWidget()

        # --- キャプチャ設定ページ ---
        page_capture, lc = _create_settings_page()
        capture_field_width = _preferred_field_width(main_window.combo_win)
        _add_labeled_row(lc, "取得元", main_window.combo_capture_source)
        main_window._row_target_settings = _add_labeled_row(
            lc,
            "ターゲット",
            main_window.combo_win,
            field_width=capture_field_width,
        )
        # 領域選択行は行コンテナ単位で表示切替し、余白崩れを防ぐ。
        main_window._row_pick_roi_win_settings = _add_labeled_row(
            lc,
            "",
            main_window.btn_pick_roi_win,
            field_width=capture_field_width,
        )
        main_window._row_pick_roi_screen_settings = _add_labeled_row(
            lc,
            "",
            main_window.btn_pick_roi_screen,
            field_width=capture_field_width,
        )
        _add_labeled_row(lc, "解析解像度", main_window.combo_analysis_resolution_mode)
        main_window._row_analysis_max_dim_settings = _add_labeled_row(
            lc,
            "指定サイズ",
            main_window.edit_analysis_max_dim,
        )
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
        _add_labeled_row(lu, "更新モード", main_window.combo_mode)
        main_window._row_interval_settings = _add_labeled_row(
            lu,
            "更新間隔",
            main_window.spin_interval,
        )
        main_window._row_diff_settings = _add_labeled_row(lu, "差分閾値", main_window.spin_diff)
        main_window._hint_diff_settings = _make_hint_label(
            "値を下げるほど小さな変化にも反応し、上げるほど大きな変化のみで更新します。",
            word_wrap=True,
        )
        lu.addWidget(main_window._hint_diff_settings)
        main_window._row_stable_settings = _add_labeled_row(
            lu,
            "安定フレーム",
            main_window.spin_stable,
        )
        main_window._hint_stable_settings = _make_hint_label(
            "変化検知後、このフレーム数だけ安定した状態が続くと更新します。",
            word_wrap=True,
        )
        lu.addWidget(main_window._hint_stable_settings)
        lu.addStretch(1)
        pages.addWidget(page_update)

        # --- 色相環設定ページ ---
        page_wheel, lw = _create_settings_page()
        lw.addWidget(_make_hint_label("色相環の色相分類方式を設定します"))
        _add_labeled_row(lw, "表示方式", main_window.combo_wheel_mode)
        _add_labeled_row(lw, "彩度しきい値", main_window.spin_wheel_sat_threshold)
        lw.addWidget(
            _make_hint_label(
                "色相環: 0 のときは無彩色も含みます。1 以上では「しきい値未満」を除外します。",
                word_wrap=True,
            )
        )
        lw.addWidget(main_window.chk_wheel_harmony_guide)
        _add_labeled_row(lw, "色彩調和タイプ", main_window.combo_wheel_harmony_guide)
        lw.addWidget(_make_hint_label("ガイド表示中は色相環内側を左ドラッグで回転できます。"))
        lw.addStretch(1)
        pages.addWidget(page_wheel)

        # --- 配色比率設定ページ ---
        page_color_band, lcb = _create_settings_page()
        lcb.addWidget(_make_hint_label("配色比率の集計条件と配色候補表示を設定します"))
        lcb.addWidget(main_window.chk_color_band_use_wheel_sat_threshold)
        _add_labeled_row(lcb, "彩度しきい値", main_window.spin_color_band_sat_threshold)
        lcb.addWidget(
            _make_hint_label(
                "配色比率: 0 のときは無彩色を含みます。1 以上では「しきい値未満」を除外し、有彩色のみで割合を計算します。",
                word_wrap=True,
            )
        )
        lcb.addWidget(main_window.chk_color_band_use_wheel_harmony)
        lcb.addWidget(main_window.chk_color_band_harmony_guide)
        _add_labeled_row(lcb, "色彩調和タイプ", main_window.combo_color_band_harmony_guide)
        lcb.addStretch(1)
        pages.addWidget(page_color_band)

        # --- 散布図設定ページ ---
        _add_hint_rows_settings_page(
            pages,
            hint="散布図のサンプル数を設定します",
            rows=[
                ("表示形状", main_window.combo_scatter_shape),
                ("表示モード", main_window.combo_scatter_render_mode),
                ("サンプル数", main_window.spin_points),
            ],
        )

        # --- ベクトルスコープページ ---
        page_vectorscope, lvec = _create_settings_page()
        lvec.addWidget(_make_hint_label("YUVベクトルスコープ表示を調整します"))
        lvec.addWidget(main_window.chk_vectorscope_skin_line)
        _add_labeled_row(lvec, "高彩度しきい値", main_window.spin_vectorscope_warn_threshold)
        lvec.addStretch(1)
        pages.addWidget(page_vectorscope)

        # --- 反転表示ページ ---
        _add_hint_rows_settings_page(
            pages,
            hint="反転表示の方向を設定します",
            rows=[("反転方向", main_window.combo_mirror_mode)],
        )

        # --- エッジ検出ページ ---
        _add_hint_rows_settings_page(
            pages,
            hint="エッジ検出の見え方を調整します",
            rows=[("エッジ感度", main_window.spin_edge_sensitivity)],
        )

        # --- 2値化ページ ---
        _add_hint_rows_settings_page(
            pages,
            hint="2値化表示の方式を設定します",
            rows=[("2値化", main_window.combo_binary_preset)],
        )

        # --- レイアウトページ ---
        page_layout, ll = _create_settings_page()
        ll.addWidget(_make_hint_label("現在の表示配置をプリセットとして保存できます"))
        # 「プリセット」と「新規名」は同じ入力幅に固定して視線移動を減らす。
        layout_field_width = max(
            _preferred_field_width(main_window.combo_layout_presets),
            _preferred_field_width(main_window.edit_preset_name),
        )
        _add_labeled_row(
            ll,
            "プリセット",
            main_window.combo_layout_presets,
            field_width=layout_field_width,
        )
        _add_labeled_row(
            ll,
            "新規名",
            main_window.edit_preset_name,
            field_width=layout_field_width,
        )
        row_btn = QHBoxLayout()
        row_btn.setContentsMargins(0, 0, 0, 0)
        row_btn.addWidget(main_window.btn_load_preset)
        row_btn.addWidget(main_window.btn_save_preset)
        row_btn.addWidget(main_window.btn_delete_preset)
        ll.addLayout(row_btn)
        ll.addStretch(1)
        pages.addWidget(page_layout)

        # --- 3値化ページ ---
        _add_hint_rows_settings_page(
            pages,
            hint="3値化表示の方式を設定します",
            rows=[("3値化", main_window.combo_ternary_preset)],
        )

        # --- RGBヒストグラムページ ---
        _add_hint_rows_settings_page(
            pages,
            hint="R/G/Bヒストグラムの表示方式を切り替えます",
            rows=[("表示方式", main_window.combo_rgb_hist_mode)],
        )

        # --- フォーカスピーキングページ ---
        _add_hint_rows_settings_page(
            pages,
            hint="フォーカスピーキングを調整します",
            rows=[
                ("感度", main_window.spin_focus_peak_sensitivity),
                ("色", main_window.combo_focus_peak_color),
                ("線幅", main_window.spin_focus_peak_thickness),
            ],
        )

        # --- スクイントページ ---
        squint_rows = _add_hint_rows_settings_page(
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

        # --- サリエンシーページ ---
        _add_hint_rows_settings_page(
            pages,
            hint="サリエンシーマップ（スペクトル残差）を調整します",
            rows=[
                ("重ね具合", main_window.spin_saliency_alpha),
                ("構図ガイド", main_window.combo_composition_guide),
            ],
        )

        main_window._settings_nav_to_page = [page for _label, page in _SETTINGS_NAV_SPECS]
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
            page = int(main_window._settings_nav_to_page[row])
            pages.setCurrentIndex(page)
            main_window._settings_last_page = page

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

    _select_requested_settings_page(main_window, page_index)

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
