"""MainWindow control widget の責務別 builder。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QCompleter, QLabel, QPushButton

from ...util import constants as C
from ..input_widgets import RefreshOnInteractComboBox, SelectAllLineEdit
from .control_widget_common import (
    build_double_spinbox,
    build_int_spinbox,
    populate_data_combo,
    populate_harmony_guide_combo,
)


def _assign_data_combo(main_window, attr_name: str, items) -> QComboBox:
    """項目付きコンボボックスを生成して属性へ保存する。"""
    combo = QComboBox()
    populate_data_combo(combo, items)
    setattr(main_window, attr_name, combo)
    return combo


def _assign_int_spinbox(main_window, attr_name: str, minimum: int, maximum: int, value: int, **kwargs):
    """整数スピンボックスを生成して属性へ保存する。"""
    spin = build_int_spinbox(minimum, maximum, value, **kwargs)
    setattr(main_window, attr_name, spin)
    return spin


def _assign_double_spinbox(
    main_window,
    attr_name: str,
    minimum: float,
    maximum: float,
    value: float,
    **kwargs,
):
    """実数スピンボックスを生成して属性へ保存する。"""
    spin = build_double_spinbox(minimum, maximum, value, **kwargs)
    setattr(main_window, attr_name, spin)
    return spin


def _assign_checkbox(main_window, attr_name: str, label: str, checked: bool) -> QCheckBox:
    """チェックボックスを生成して属性へ保存する。"""
    checkbox = QCheckBox(label)
    checkbox.setChecked(bool(checked))
    setattr(main_window, attr_name, checkbox)
    return checkbox


def _set_combo_current_data_if_found(combo: QComboBox, value) -> None:
    """`findData()` で見つかったときだけ現在値を更新する。"""
    idx = combo.findData(value)
    if idx >= 0:
        combo.setCurrentIndex(idx)


def _assign_harmony_guide_combo(
    main_window,
    attr_name: str,
    *,
    checked: bool,
    default_type: str,
) -> QComboBox:
    """色彩調和ガイド用コンボを生成して属性へ保存する。"""
    combo = QComboBox()
    populate_harmony_guide_combo(combo)
    _set_combo_current_data_if_found(combo, default_type)
    combo.setEnabled(bool(checked))
    setattr(main_window, attr_name, combo)
    return combo


def build_capture_controls(main_window, *, default_preview_window: bool) -> None:
    """取得元選択と解析前段の control 群を生成する。"""
    main_window.combo_win = RefreshOnInteractComboBox()
    main_window.combo_win.setEditable(True)
    main_window.combo_win.setInsertPolicy(QComboBox.NoInsert)
    main_window.combo_win.set_refresh_callback(
        lambda force=False: main_window.refresh_windows(announce=False, force=bool(force))
    )
    win_completer = QCompleter(main_window.combo_win.model(), main_window.combo_win)
    win_completer.setCaseSensitivity(Qt.CaseInsensitive)
    win_completer.setFilterMode(Qt.MatchContains)
    win_completer.setCompletionMode(QCompleter.PopupCompletion)
    main_window.combo_win.setCompleter(win_completer)
    if main_window.combo_win.view() is not None:
        main_window.combo_win.view().setProperty("chromaRole", "comboPopup")
    if win_completer.popup() is not None:
        win_completer.popup().setProperty("chromaRole", "comboPopup")
    if main_window.combo_win.lineEdit() is not None:
        main_window.combo_win.lineEdit().setClearButtonEnabled(True)
        main_window.combo_win.lineEdit().setPlaceholderText("ウィンドウ名を入力")
        main_window.combo_win.lineEdit().setToolTip(
            "ウィンドウ名の一部を入力して候補を絞り込めます。"
        )

    main_window.btn_pick_roi_win = QPushButton("領域選択（ウィンドウ内）")
    main_window.btn_pick_roi_screen = QPushButton("領域選択（画面）")
    for btn in (main_window.btn_pick_roi_win, main_window.btn_pick_roi_screen):
        btn.setAutoDefault(False)
        btn.setDefault(False)

    _assign_data_combo(
        main_window,
        "combo_capture_source",
        (
            ("ウィンドウを選んで取得", C.CAPTURE_SOURCE_WINDOW),
            ("画面範囲を直接指定", C.CAPTURE_SOURCE_SCREEN),
        ),
    )
    _assign_data_combo(
        main_window,
        "combo_analysis_resolution_mode",
        (
            ("オリジナルサイズ", C.ANALYSIS_RESOLUTION_MODE_ORIGINAL),
            ("指定サイズ", C.ANALYSIS_RESOLUTION_MODE_CUSTOM),
        ),
    )
    _assign_int_spinbox(
        main_window,
        "edit_analysis_max_dim",
        C.ANALYZER_MAX_DIM_MIN,
        C.ANALYZER_MAX_DIM_MAX,
        C.ANALYZER_MAX_DIM,
        step=10,
        suffix=" px",
    )
    _assign_checkbox(
        main_window,
        "chk_preview_window",
        "領域プレビュー",
        bool(default_preview_window),
    )


def build_view_controls(main_window) -> None:
    """各ビューの表示条件やテーマに関する control 群を生成する。"""
    _assign_int_spinbox(
        main_window,
        "spin_points",
        C.ANALYZER_MIN_SAMPLE_POINTS,
        C.ANALYZER_MAX_SAMPLE_POINTS,
        C.DEFAULT_SAMPLE_POINTS,
        step=500,
    )
    _assign_data_combo(
        main_window,
        "combo_ui_theme",
        ((C.UI_THEME_LABELS[name], name) for name in C.UI_THEMES),
    )
    _assign_data_combo(
        main_window,
        "combo_scatter_shape",
        (
            ("四角", C.SCATTER_SHAPE_SQUARE),
            ("三角", C.SCATTER_SHAPE_TRIANGLE),
        ),
    )
    _assign_data_combo(
        main_window,
        "combo_scatter_render_mode",
        (
            ("色をそのまま", C.SCATTER_RENDER_MODE_DOMINANT),
            ("ヒートマップ", C.SCATTER_RENDER_MODE_HEATMAP),
        ),
    )
    _assign_data_combo(
        main_window,
        "combo_wheel_mode",
        (
            ("HSV 180ビン", C.WHEEL_MODE_HSV180),
            ("マンセル基準（40色相）", C.WHEEL_MODE_MUNSELL40),
        ),
    )
    _assign_checkbox(
        main_window,
        "chk_wheel_harmony_guide",
        "色彩調和ガイドを表示",
        C.DEFAULT_WHEEL_HARMONY_GUIDE_ENABLED,
    )
    _assign_harmony_guide_combo(
        main_window,
        "combo_wheel_harmony_guide",
        checked=C.DEFAULT_WHEEL_HARMONY_GUIDE_ENABLED,
        default_type=C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE,
    )

    _assign_data_combo(
        main_window,
        "combo_rgb_hist_mode",
        (
            ("横並び", C.RGB_HIST_MODE_SIDE_BY_SIDE),
            ("重ね表示", C.RGB_HIST_MODE_OVERLAY),
        ),
    )
    _assign_data_combo(
        main_window,
        "combo_mirror_mode",
        (
            ("左右", C.MIRROR_MODE_HORIZONTAL),
            ("上下", C.MIRROR_MODE_VERTICAL),
            ("上下左右", C.MIRROR_MODE_BOTH),
        ),
    )
    _assign_int_spinbox(
        main_window,
        "spin_wheel_sat_threshold",
        C.WHEEL_SAT_THRESHOLD_MIN,
        C.WHEEL_SAT_THRESHOLD_MAX,
        C.DEFAULT_WHEEL_SAT_THRESHOLD,
        suffix=" / 255",
    )
    _assign_checkbox(
        main_window,
        "chk_color_band_use_wheel_sat_threshold",
        "彩度しきい値を色相環と同じにする",
        C.DEFAULT_COLOR_BAND_USE_WHEEL_SAT_THRESHOLD,
    )
    _assign_int_spinbox(
        main_window,
        "spin_color_band_sat_threshold",
        C.WHEEL_SAT_THRESHOLD_MIN,
        C.WHEEL_SAT_THRESHOLD_MAX,
        C.DEFAULT_COLOR_BAND_SAT_THRESHOLD,
        suffix=" / 255",
    )
    _assign_checkbox(
        main_window,
        "chk_color_band_use_wheel_harmony",
        "色彩調和を色相環と同じ設定にする",
        C.DEFAULT_COLOR_BAND_USE_WHEEL_HARMONY,
    )
    _assign_checkbox(
        main_window,
        "chk_color_band_harmony_guide",
        "色彩調和を表示",
        C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_ENABLED,
    )
    _assign_harmony_guide_combo(
        main_window,
        "combo_color_band_harmony_guide",
        checked=C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_ENABLED,
        default_type=C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_TYPE,
    )
    main_window.spin_color_band_sat_threshold.setEnabled(
        not main_window.chk_color_band_use_wheel_sat_threshold.isChecked()
    )
    own_harmony_enabled = (
        not main_window.chk_color_band_use_wheel_harmony.isChecked()
        and main_window.chk_color_band_harmony_guide.isChecked()
    )
    main_window.chk_color_band_harmony_guide.setEnabled(
        not main_window.chk_color_band_use_wheel_harmony.isChecked()
    )
    main_window.combo_color_band_harmony_guide.setEnabled(own_harmony_enabled)


def build_processing_controls(
    main_window,
    *,
    focus_peak_thickness_step: float,
    squint_blur_sigma_step: float,
) -> None:
    """更新条件や各解析 view の微調整 control 群を生成する。"""
    _assign_double_spinbox(
        main_window,
        "spin_interval",
        0.10,
        10.00,
        C.DEFAULT_INTERVAL_SEC,
        decimals=1,
        step=0.10,
        suffix=" 秒",
    )
    _assign_data_combo(
        main_window,
        "combo_mode",
        (
            ("一定間隔で更新", C.UPDATE_MODE_INTERVAL),
            ("画面に動きがあったとき", C.UPDATE_MODE_CHANGE),
        ),
    )
    _assign_double_spinbox(
        main_window,
        "spin_diff",
        C.ANALYZER_MIN_DIFF_THRESHOLD,
        50.0,
        C.DEFAULT_DIFF_THRESHOLD,
        decimals=2,
        step=0.01,
    )
    _assign_int_spinbox(
        main_window,
        "spin_stable",
        C.ANALYZER_MIN_STABLE_FRAMES,
        20,
        C.DEFAULT_STABLE_FRAMES,
    )
    _assign_int_spinbox(
        main_window,
        "spin_edge_sensitivity",
        C.EDGE_SENSITIVITY_MIN,
        C.EDGE_SENSITIVITY_MAX,
        C.DEFAULT_EDGE_SENSITIVITY,
        suffix=" / 100",
        min_width=130,
    )
    _assign_data_combo(
        main_window,
        "combo_binary_preset",
        (
            ("自動", C.BINARY_PRESET_AUTO),
            ("白を増やす", C.BINARY_PRESET_MORE_WHITE),
            ("黒を増やす", C.BINARY_PRESET_MORE_BLACK),
        ),
    )
    _assign_data_combo(
        main_window,
        "combo_ternary_preset",
        (
            ("標準", C.TERNARY_PRESET_STANDARD),
            ("やわらかめ", C.TERNARY_PRESET_SOFT),
            ("くっきり", C.TERNARY_PRESET_STRONG),
        ),
    )
    _assign_int_spinbox(
        main_window,
        "spin_saliency_alpha",
        C.SALIENCY_ALPHA_MIN,
        C.SALIENCY_ALPHA_MAX,
        C.DEFAULT_SALIENCY_OVERLAY_ALPHA,
        suffix=" %",
    )
    _assign_data_combo(
        main_window,
        "combo_composition_guide",
        (
            ("なし", C.COMPOSITION_GUIDE_NONE),
            ("三分割", C.COMPOSITION_GUIDE_THIRDS),
            ("中央クロス", C.COMPOSITION_GUIDE_CENTER),
            ("対角線", C.COMPOSITION_GUIDE_DIAGONAL),
        ),
    )
    _assign_int_spinbox(
        main_window,
        "spin_focus_peak_sensitivity",
        C.FOCUS_PEAK_SENSITIVITY_MIN,
        C.FOCUS_PEAK_SENSITIVITY_MAX,
        C.DEFAULT_FOCUS_PEAK_SENSITIVITY,
        suffix=" / 100",
        min_width=130,
    )
    _assign_data_combo(
        main_window,
        "combo_focus_peak_color",
        (
            ("シアン", C.FOCUS_PEAK_COLOR_CYAN),
            ("グリーン", C.FOCUS_PEAK_COLOR_GREEN),
            ("イエロー", C.FOCUS_PEAK_COLOR_YELLOW),
            ("レッド", C.FOCUS_PEAK_COLOR_RED),
        ),
    )
    _assign_double_spinbox(
        main_window,
        "spin_focus_peak_thickness",
        C.FOCUS_PEAK_THICKNESS_MIN,
        C.FOCUS_PEAK_THICKNESS_MAX,
        C.DEFAULT_FOCUS_PEAK_THICKNESS,
        decimals=1,
        step=focus_peak_thickness_step,
        suffix=" px",
    )
    _assign_data_combo(
        main_window,
        "combo_squint_mode",
        (
            ("ぼかしのみ", C.SQUINT_MODE_BLUR),
            ("縮小 → 拡大", C.SQUINT_MODE_SCALE),
            ("縮小 → 拡大 + ぼかし", C.SQUINT_MODE_SCALE_BLUR),
        ),
    )
    _assign_int_spinbox(
        main_window,
        "spin_squint_scale",
        C.SQUINT_SCALE_PERCENT_MIN,
        C.SQUINT_SCALE_PERCENT_MAX,
        C.DEFAULT_SQUINT_SCALE_PERCENT,
        suffix=" %",
    )
    _assign_double_spinbox(
        main_window,
        "spin_squint_blur",
        C.SQUINT_BLUR_SIGMA_MIN,
        C.SQUINT_BLUR_SIGMA_MAX,
        C.DEFAULT_SQUINT_BLUR_SIGMA,
        decimals=1,
        step=squint_blur_sigma_step,
        suffix=" px",
    )
    _assign_checkbox(
        main_window,
        "chk_vectorscope_skin_line",
        "スキントーンラインを表示",
        C.DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE,
    )
    _assign_int_spinbox(
        main_window,
        "spin_vectorscope_warn_threshold",
        C.VECTORSCOPE_WARN_THRESHOLD_MIN,
        C.VECTORSCOPE_WARN_THRESHOLD_MAX,
        C.DEFAULT_VECTORSCOPE_WARN_THRESHOLD,
        suffix=" %",
    )


def build_layout_controls(main_window) -> None:
    """レイアウトプリセット関連 control と状態参照を生成する。"""
    main_window.edit_preset_name = SelectAllLineEdit()
    main_window.edit_preset_name.setPlaceholderText("例: 作業レイアウトA")
    main_window.edit_preset_name.setToolTip(
        "入力例: 作業レイアウトA\n現在のドック配置をこの名前で保存します。"
    )
    main_window.combo_layout_presets = QComboBox()
    if main_window.combo_layout_presets.view() is not None:
        main_window.combo_layout_presets.view().setProperty("chromaRole", "comboPopup")
    main_window.btn_save_preset = QPushButton("プリセット保存")
    main_window.btn_load_preset = QPushButton("適用")
    main_window.btn_delete_preset = QPushButton("削除")


def initialize_settings_row_refs(main_window) -> None:
    """設定ダイアログ連携で後から埋める行参照を初期化する。"""
    main_window._row_target_settings = None
    main_window._row_pick_roi_win_settings = None
    main_window._row_pick_roi_screen_settings = None
    main_window._row_analysis_max_dim_settings = None
    main_window._hint_analysis_max_dim_settings = None
    main_window._row_interval_settings = None
    main_window._row_diff_settings = None
    main_window._hint_diff_settings = None
    main_window._row_stable_settings = None
    main_window._hint_stable_settings = None
    main_window._row_squint_scale_settings = None
    main_window._row_squint_blur_settings = None


def build_status_widgets(main_window) -> None:
    """下部ステータス表示を生成する。"""
    main_window.lbl_status = QLabel("準備完了")
    main_window.lbl_status.setProperty("chromaRole", "status")
