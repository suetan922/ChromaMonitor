from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtNetwork import QNetworkAccessManager
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QLabel,
    QMainWindow,
    QMenuBar,
    QPushButton,
)

from .analyzer import AnalyzerWorker
from .capture.win32_windows import HAS_WIN32
from .ui import layout_presets as mw_layout_presets
from .ui.input_widgets import (
    RefreshOnInteractComboBox,
    SelectAllLineEdit,
    SelectAllSpinBox,
    add_checkable_action,
    configure_numeric_input,
)
from .ui.main_window import help_actions as mw_help
from .ui.main_window import result_color_band as mw_color_band
from .ui.main_window import result_snapshot as mw_snapshot
from .ui.main_window import roi_handlers as mw_roi
from .ui.main_window import runtime_actions as mw_runtime
from .ui.main_window import settings_logic as mw_settings
from .ui.main_window import window_layout as mw_windowing
from .ui.main_window import window_tabs as mw_tabs
from .ui.main_window import window_topmost as mw_topmost
from .ui.settings_dialog import hide_settings_window as hide_settings_dialog_window
from .ui.settings_dialog import show_settings_window as show_settings_dialog_window
from .ui.view_docks import setup_view_docks
from .util import constants as C
from .views.preview import PreviewWindow

_WINDOW_DOCK_MENU_ITEMS = (
    ("act_color", "色相環", True, "dock_color"),
    ("act_color_band", "配色比率", True, "dock_color_band"),
    ("act_hist", "H/S/V ヒストグラム", True, "dock_hist"),
    ("act_rgb_hist", "R/G/B ヒストグラム", False, "dock_rgb_hist"),
    ("act_scatter", "S-V 散布図", True, "dock_scatter"),
    ("act_vectorscope", "ベクトルスコープ", True, "dock_vectorscope"),
    ("act_edge", "エッジ検出", True, "dock_edge"),
    ("act_binary", "2値化", True, "dock_binary"),
    ("act_ternary", "3値化", True, "dock_ternary"),
    ("act_gray", "グレースケール", True, "dock_gray"),
    ("act_focus", "フォーカスピーキング", True, "dock_focus"),
    ("act_squint", "スクイント表示", True, "dock_squint"),
    ("act_saliency", "サリエンシーマップ", True, "dock_saliency"),
)
_DEFAULT_PREVIEW_WINDOW = False
_SETTINGS_SAVE_DEBOUNCE_MS = 220
_DOCK_REBALANCE_DEBOUNCE_MS = 36
_LAYOUT_INTERACTION_RESUME_DEBOUNCE_MS = 220
_FOCUS_PEAK_THICKNESS_STEP = 0.1
_SQUINT_BLUR_SIGMA_STEP = 0.1


class MainWindow(QMainWindow):
    """メインUIと解析ワーカー連携を統括するアプリ主画面。"""

    def __init__(self):
        """ウィンドウ状態・各種UI・シグナル接続を順に初期化する。"""
        super().__init__()
        self._init_window_runtime_state()
        self._init_analyzer_workers()

        self._build_control_widgets()
        self._connect_control_signals()

        self._build_menu_bar()
        self._build_toolbar()
        self._setup_preview_and_docks()

        # --- Styling (theme) ---
        self._apply_ui_style()

        # --- Init ---
        self._initialize_runtime_defaults()

    def _init_window_runtime_state(self) -> None:
        """ランタイム管理用フラグ・タイマー・ネットワーク状態を初期化する。"""
        self.setWindowTitle(C.APP_NAME)
        self.resize(1120, 700)
        self._did_initial_screen_fit = False
        self._layout_autosave_enabled = False
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(600)
        self._layout_save_timer.timeout.connect(
            lambda: self.save_current_layout_to_config(silent=True)
        )
        self._fit_window_timer = QTimer(self)
        self._fit_window_timer.setSingleShot(True)
        self._fit_window_timer.setInterval(80)
        self._fit_window_timer.timeout.connect(self._fit_window_to_desktop)
        self._dock_rebalance_timer = QTimer(self)
        self._dock_rebalance_timer.setSingleShot(True)
        self._dock_rebalance_timer.setInterval(_DOCK_REBALANCE_DEBOUNCE_MS)
        self._dock_rebalance_timer.timeout.connect(self._rebalance_dock_layout)
        self._dock_rebalance_running = False
        self._dock_geometry_snapshot = {}
        self._dock_rebalance_last_main_size = self.size()
        self._layout_interaction_pause_active = False
        self._layout_interaction_pause_reasons = set()
        self._layout_interaction_resume_timer = QTimer(self)
        self._layout_interaction_resume_timer.setSingleShot(True)
        self._layout_interaction_resume_timer.setInterval(_LAYOUT_INTERACTION_RESUME_DEBOUNCE_MS)
        self._layout_interaction_resume_timer.timeout.connect(self._end_layout_interaction_pause)
        self._settings_save_timer = QTimer(self)
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(_SETTINGS_SAVE_DEBOUNCE_MS)
        self._settings_save_timer.timeout.connect(self._flush_settings_save)
        self._settings_save_pending = False
        self._settings_load_in_progress = False
        self._startup_finished = False
        # 同一画面構成時は起動直後の位置補正を抑止する。
        self._startup_should_fit_window = True
        self._release_page_url = C.APP_RELEASES_URL
        self._update_check_started = False
        self._update_reply = None
        self._update_network = QNetworkAccessManager(self)
        self._update_network.finished.connect(self._on_release_check_finished)
        # ROI選択オーバーレイ（マルチモニタ対応）管理。
        self._roi_selectors = []

    def _init_analyzer_workers(self) -> None:
        """ライブ解析と画像解析のワーカー参照を初期化する。"""
        # キャプチャ解析ワーカー（ライブ）と画像解析ワーカー（単発）を分離して保持。
        self.worker = AnalyzerWorker()
        self.worker.resultReady.connect(self.on_result)
        self.worker.status.connect(self.on_status)
        self._image_thread = None
        self._image_worker = None
        self._image_progress = None

    @staticmethod
    def _set_widget_unit_label(widget, suffix: str) -> None:
        """設定ダイアログ表示用の単位ラベル文字列をウィジェットへ保持する。"""
        widget._chroma_unit_label_text = str(suffix).strip()

    @staticmethod
    def _populate_data_combo(combo: QComboBox, items) -> None:
        """`(label, data)` 形式の候補列でコンボを初期化する。"""
        combo.clear()
        for label, data in items:
            combo.addItem(label, data)

    @staticmethod
    def _build_int_spinbox(
        minimum: int,
        maximum: int,
        value: int,
        *,
        step: int = 1,
        suffix: str = "",
        min_width: int = 110,
        min_height: int = 28,
    ) -> SelectAllSpinBox:
        """共通設定済みの整数入力欄を生成する。"""
        spin = SelectAllSpinBox()
        spin.setRange(int(minimum), int(maximum))
        spin.setSingleStep(int(step))
        spin.setValue(int(value))
        if suffix:
            MainWindow._set_widget_unit_label(spin, suffix)
        configure_numeric_input(spin, min_width=min_width, min_height=min_height)
        return spin

    @staticmethod
    def _build_double_spinbox(
        minimum: float,
        maximum: float,
        value: float,
        *,
        decimals: int,
        step: float,
        suffix: str = "",
        min_width: int = 110,
        min_height: int = 28,
    ) -> QDoubleSpinBox:
        """共通設定済みの小数入力欄を生成する。"""
        spin = QDoubleSpinBox()
        spin.setRange(float(minimum), float(maximum))
        spin.setDecimals(int(decimals))
        spin.setSingleStep(float(step))
        spin.setValue(float(value))
        if suffix:
            MainWindow._set_widget_unit_label(spin, suffix)
        configure_numeric_input(spin, min_width=min_width, min_height=min_height)
        return spin

    def _populate_harmony_guide_combo(self, combo: QComboBox) -> None:
        """色彩調和ガイド用コンボへ候補を設定する。"""
        self._populate_data_combo(
            combo,
            (
                (C.WHEEL_HARMONY_GUIDE_LABELS[guide_type], guide_type)
                for guide_type in C.WHEEL_HARMONY_GUIDE_COMBO_ORDER
            ),
        )

    def _build_control_widgets(self) -> None:
        """設定・操作に使う入力ウィジェット群を生成する。"""
        # --- Controls: キャプチャ/解析設定 ---
        self.combo_win = RefreshOnInteractComboBox()
        self.combo_win.setEditable(True)
        self.combo_win.setInsertPolicy(QComboBox.NoInsert)
        self.combo_win.set_refresh_callback(lambda: self.refresh_windows(announce=False))
        win_completer = QCompleter(self.combo_win.model(), self.combo_win)
        win_completer.setCaseSensitivity(Qt.CaseInsensitive)
        win_completer.setFilterMode(Qt.MatchContains)
        win_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.combo_win.setCompleter(win_completer)
        if self.combo_win.lineEdit() is not None:
            self.combo_win.lineEdit().setClearButtonEnabled(True)
            self.combo_win.lineEdit().setPlaceholderText("例: CLIP STUDIO PAINT")
            self.combo_win.lineEdit().setToolTip(
                "入力例: CLIP STUDIO PAINT\nウィンドウ名の一部を入力して候補を絞り込めます。"
            )
        self.btn_pick_roi_win = QPushButton("領域選択（ウィンドウ内）")
        self.btn_pick_roi_screen = QPushButton("領域選択（画面）")

        self.spin_interval = self._build_double_spinbox(
            0.10,
            10.00,
            C.DEFAULT_INTERVAL_SEC,
            decimals=2,
            step=0.10,
            suffix=" 秒",
        )

        self.spin_points = self._build_int_spinbox(
            C.ANALYZER_MIN_SAMPLE_POINTS,
            C.ANALYZER_MAX_SAMPLE_POINTS,
            C.DEFAULT_SAMPLE_POINTS,
            step=500,
        )
        self.combo_analysis_resolution_mode = QComboBox()
        self._populate_data_combo(
            self.combo_analysis_resolution_mode,
            (
                ("オリジナルサイズ", C.ANALYSIS_RESOLUTION_MODE_ORIGINAL),
                ("指定サイズ", C.ANALYSIS_RESOLUTION_MODE_CUSTOM),
            ),
        )
        self.edit_analysis_max_dim = self._build_int_spinbox(
            C.ANALYZER_MAX_DIM_MIN,
            C.ANALYZER_MAX_DIM_MAX,
            C.ANALYZER_MAX_DIM,
            step=10,
            suffix=" px",
        )

        self.combo_capture_source = QComboBox()
        self._populate_data_combo(
            self.combo_capture_source,
            (
                ("ウィンドウを選んで取得", C.CAPTURE_SOURCE_WINDOW),
                ("画面範囲を直接指定", C.CAPTURE_SOURCE_SCREEN),
            ),
        )

        self.combo_scatter_shape = QComboBox()
        self._populate_data_combo(
            self.combo_scatter_shape,
            (
                ("四角", C.SCATTER_SHAPE_SQUARE),
                ("三角", C.SCATTER_SHAPE_TRIANGLE),
            ),
        )
        self.combo_scatter_render_mode = QComboBox()
        self._populate_data_combo(
            self.combo_scatter_render_mode,
            (
                ("色をそのまま", C.SCATTER_RENDER_MODE_DOMINANT),
                ("ヒートマップ", C.SCATTER_RENDER_MODE_HEATMAP),
            ),
        )
        self.combo_wheel_mode = QComboBox()
        self._populate_data_combo(
            self.combo_wheel_mode,
            (
                ("HSV 180ビン", C.WHEEL_MODE_HSV180),
                ("マンセル基準（40色相）", C.WHEEL_MODE_MUNSELL40),
            ),
        )

        self.chk_wheel_harmony_guide = QCheckBox("色彩調和ガイドを表示")
        self.chk_wheel_harmony_guide.setChecked(C.DEFAULT_WHEEL_HARMONY_GUIDE_ENABLED)
        self.combo_wheel_harmony_guide = QComboBox()
        self._populate_harmony_guide_combo(self.combo_wheel_harmony_guide)
        default_harmony_idx = self.combo_wheel_harmony_guide.findData(
            C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE
        )
        if default_harmony_idx >= 0:
            self.combo_wheel_harmony_guide.setCurrentIndex(default_harmony_idx)
        self.combo_wheel_harmony_guide.setEnabled(C.DEFAULT_WHEEL_HARMONY_GUIDE_ENABLED)
        self.combo_rgb_hist_mode = QComboBox()
        self._populate_data_combo(
            self.combo_rgb_hist_mode,
            (
                ("横並び", C.RGB_HIST_MODE_SIDE_BY_SIDE),
                ("重ね表示", C.RGB_HIST_MODE_OVERLAY),
            ),
        )
        self.spin_wheel_sat_threshold = self._build_int_spinbox(
            C.WHEEL_SAT_THRESHOLD_MIN,
            C.WHEEL_SAT_THRESHOLD_MAX,
            C.DEFAULT_WHEEL_SAT_THRESHOLD,
            suffix=" / 255",
        )
        self.chk_color_band_use_wheel_sat_threshold = QCheckBox("彩度しきい値を色相環と同じにする")
        self.chk_color_band_use_wheel_sat_threshold.setChecked(
            C.DEFAULT_COLOR_BAND_USE_WHEEL_SAT_THRESHOLD
        )
        self.spin_color_band_sat_threshold = self._build_int_spinbox(
            C.WHEEL_SAT_THRESHOLD_MIN,
            C.WHEEL_SAT_THRESHOLD_MAX,
            C.DEFAULT_COLOR_BAND_SAT_THRESHOLD,
            suffix=" / 255",
        )
        self.chk_color_band_use_wheel_harmony = QCheckBox("色彩調和を色相環と同じ設定にする")
        self.chk_color_band_use_wheel_harmony.setChecked(C.DEFAULT_COLOR_BAND_USE_WHEEL_HARMONY)
        self.chk_color_band_harmony_guide = QCheckBox("色彩調和を表示")
        self.chk_color_band_harmony_guide.setChecked(C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_ENABLED)
        self.combo_color_band_harmony_guide = QComboBox()
        self._populate_harmony_guide_combo(self.combo_color_band_harmony_guide)
        default_color_band_harmony_idx = self.combo_color_band_harmony_guide.findData(
            C.DEFAULT_COLOR_BAND_HARMONY_GUIDE_TYPE
        )
        if default_color_band_harmony_idx >= 0:
            self.combo_color_band_harmony_guide.setCurrentIndex(default_color_band_harmony_idx)
        self.spin_color_band_sat_threshold.setEnabled(
            not self.chk_color_band_use_wheel_sat_threshold.isChecked()
        )
        own_harmony_enabled = (
            not self.chk_color_band_use_wheel_harmony.isChecked()
            and self.chk_color_band_harmony_guide.isChecked()
        )
        self.chk_color_band_harmony_guide.setEnabled(
            not self.chk_color_band_use_wheel_harmony.isChecked()
        )
        self.combo_color_band_harmony_guide.setEnabled(own_harmony_enabled)

        self.combo_mode = QComboBox()
        self._populate_data_combo(
            self.combo_mode,
            (
                ("一定間隔で更新", C.UPDATE_MODE_INTERVAL),
                ("画面に動きがあったとき", C.UPDATE_MODE_CHANGE),
            ),
        )
        self.spin_diff = self._build_double_spinbox(
            C.ANALYZER_MIN_DIFF_THRESHOLD,
            50.0,
            C.DEFAULT_DIFF_THRESHOLD,
            decimals=1,
            step=C.ANALYZER_MIN_DIFF_THRESHOLD,
        )
        self.spin_stable = self._build_int_spinbox(
            C.ANALYZER_MIN_STABLE_FRAMES,
            20,
            C.DEFAULT_STABLE_FRAMES,
        )
        self.spin_edge_sensitivity = self._build_int_spinbox(
            C.EDGE_SENSITIVITY_MIN,
            C.EDGE_SENSITIVITY_MAX,
            C.DEFAULT_EDGE_SENSITIVITY,
            suffix=" / 100",
            min_width=130,
        )
        self.combo_binary_preset = QComboBox()
        self._populate_data_combo(
            self.combo_binary_preset,
            (
                ("自動", C.BINARY_PRESET_AUTO),
                ("白を増やす", C.BINARY_PRESET_MORE_WHITE),
                ("黒を増やす", C.BINARY_PRESET_MORE_BLACK),
            ),
        )
        self.combo_ternary_preset = QComboBox()
        self._populate_data_combo(
            self.combo_ternary_preset,
            (
                ("標準", C.TERNARY_PRESET_STANDARD),
                ("やわらかめ", C.TERNARY_PRESET_SOFT),
                ("くっきり", C.TERNARY_PRESET_STRONG),
            ),
        )
        self.spin_saliency_alpha = self._build_int_spinbox(
            C.SALIENCY_ALPHA_MIN,
            C.SALIENCY_ALPHA_MAX,
            C.DEFAULT_SALIENCY_OVERLAY_ALPHA,
            suffix=" %",
        )
        self.combo_composition_guide = QComboBox()
        self._populate_data_combo(
            self.combo_composition_guide,
            (
                ("なし", C.COMPOSITION_GUIDE_NONE),
                ("三分割", C.COMPOSITION_GUIDE_THIRDS),
                ("中央クロス", C.COMPOSITION_GUIDE_CENTER),
                ("対角線", C.COMPOSITION_GUIDE_DIAGONAL),
            ),
        )
        self.spin_focus_peak_sensitivity = self._build_int_spinbox(
            C.FOCUS_PEAK_SENSITIVITY_MIN,
            C.FOCUS_PEAK_SENSITIVITY_MAX,
            C.DEFAULT_FOCUS_PEAK_SENSITIVITY,
            suffix=" / 100",
            min_width=130,
        )
        self.combo_focus_peak_color = QComboBox()
        self._populate_data_combo(
            self.combo_focus_peak_color,
            (
                ("シアン", C.FOCUS_PEAK_COLOR_CYAN),
                ("グリーン", C.FOCUS_PEAK_COLOR_GREEN),
                ("イエロー", C.FOCUS_PEAK_COLOR_YELLOW),
                ("レッド", C.FOCUS_PEAK_COLOR_RED),
            ),
        )
        self.spin_focus_peak_thickness = self._build_double_spinbox(
            C.FOCUS_PEAK_THICKNESS_MIN,
            C.FOCUS_PEAK_THICKNESS_MAX,
            C.DEFAULT_FOCUS_PEAK_THICKNESS,
            decimals=1,
            step=_FOCUS_PEAK_THICKNESS_STEP,
            suffix=" px",
        )
        self.combo_squint_mode = QComboBox()
        self._populate_data_combo(
            self.combo_squint_mode,
            (
                ("ぼかしのみ", C.SQUINT_MODE_BLUR),
                ("縮小 → 拡大", C.SQUINT_MODE_SCALE),
                ("縮小 → 拡大 + ぼかし", C.SQUINT_MODE_SCALE_BLUR),
            ),
        )
        self.spin_squint_scale = self._build_int_spinbox(
            C.SQUINT_SCALE_PERCENT_MIN,
            C.SQUINT_SCALE_PERCENT_MAX,
            C.DEFAULT_SQUINT_SCALE_PERCENT,
            suffix=" %",
        )
        self.spin_squint_blur = self._build_double_spinbox(
            C.SQUINT_BLUR_SIGMA_MIN,
            C.SQUINT_BLUR_SIGMA_MAX,
            C.DEFAULT_SQUINT_BLUR_SIGMA,
            decimals=1,
            step=_SQUINT_BLUR_SIGMA_STEP,
            suffix=" px",
        )
        self.chk_vectorscope_skin_line = QCheckBox("スキントーンラインを表示")
        self.chk_vectorscope_skin_line.setChecked(C.DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE)
        self.spin_vectorscope_warn_threshold = self._build_int_spinbox(
            C.VECTORSCOPE_WARN_THRESHOLD_MIN,
            C.VECTORSCOPE_WARN_THRESHOLD_MAX,
            C.DEFAULT_VECTORSCOPE_WARN_THRESHOLD,
            suffix=" %",
        )

        self.chk_preview_window = QCheckBox("領域プレビュー")
        self.chk_preview_window.setChecked(_DEFAULT_PREVIEW_WINDOW)

        self.edit_preset_name = SelectAllLineEdit()
        self.edit_preset_name.setPlaceholderText("例: 作業レイアウトA")
        self.edit_preset_name.setToolTip(
            "入力例: 作業レイアウトA\n現在のドック配置をこの名前で保存します。"
        )
        self.combo_layout_presets = QComboBox()
        self.btn_save_preset = QPushButton("プリセット保存")
        self.btn_load_preset = QPushButton("適用")
        self.btn_delete_preset = QPushButton("削除")
        self._row_target_settings = None
        self._row_pick_roi_win_settings = None
        self._row_pick_roi_screen_settings = None
        self._row_analysis_max_dim_settings = None
        self._hint_analysis_max_dim_settings = None
        self._row_interval_settings = None
        self._row_diff_settings = None
        self._hint_diff_settings = None
        self._row_stable_settings = None
        self._hint_stable_settings = None
        self._row_squint_scale_settings = None
        self._row_squint_blur_settings = None

        self.lbl_status = QLabel("準備完了")
        self.lbl_status.setStyleSheet("color:#BBBBBB;")

    def _connect_control_signals(self) -> None:
        """操作ウィジェットと各種ハンドラのシグナル接続を行う。"""
        self._connect_capture_control_signals()
        self._connect_analysis_control_signals()
        self._connect_layout_preset_signals()

    def _connect_capture_control_signals(self) -> None:
        """取得元選択とROI操作のシグナルを接続する。"""
        self.combo_win.currentIndexChanged.connect(self.on_window_changed)
        if self.combo_win.lineEdit() is not None:
            self.combo_win.lineEdit().editingFinished.connect(self.on_window_text_committed)
        self.btn_pick_roi_win.clicked.connect(self.pick_roi_in_window)
        self.btn_pick_roi_screen.clicked.connect(self.pick_roi_on_screen)
        self.combo_capture_source.currentIndexChanged.connect(self.apply_capture_source)

    def _connect_analysis_control_signals(self) -> None:
        """解析設定とプレビュー制御のシグナルを接続する。"""
        self.spin_interval.valueChanged.connect(lambda v: self.worker.set_interval(float(v)))
        self.spin_points.valueChanged.connect(self.apply_sample_points_settings)
        self.combo_analysis_resolution_mode.currentIndexChanged.connect(
            self.apply_analysis_resolution_settings
        )
        self.edit_analysis_max_dim.valueChanged.connect(self.apply_analysis_resolution_settings)
        self.combo_scatter_shape.currentIndexChanged.connect(self.apply_scatter_settings)
        self.combo_scatter_render_mode.currentIndexChanged.connect(self.apply_scatter_settings)
        self.combo_wheel_mode.currentIndexChanged.connect(self.apply_wheel_settings)
        self.chk_wheel_harmony_guide.toggled.connect(self.apply_wheel_settings)
        self.combo_wheel_harmony_guide.currentIndexChanged.connect(self.apply_wheel_settings)
        self.combo_rgb_hist_mode.currentIndexChanged.connect(self.apply_rgb_hist_settings)
        self.spin_wheel_sat_threshold.valueChanged.connect(self.apply_wheel_settings)
        self.chk_color_band_use_wheel_sat_threshold.toggled.connect(self.apply_color_band_settings)
        self.spin_color_band_sat_threshold.valueChanged.connect(self.apply_color_band_settings)
        self.chk_color_band_use_wheel_harmony.toggled.connect(self.apply_color_band_settings)
        self.chk_color_band_harmony_guide.toggled.connect(self.apply_color_band_settings)
        self.combo_color_band_harmony_guide.currentIndexChanged.connect(
            self.apply_color_band_settings
        )
        self.combo_mode.currentIndexChanged.connect(self.apply_mode_settings)
        self.spin_diff.valueChanged.connect(self.apply_mode_settings)
        self.spin_stable.valueChanged.connect(self.apply_mode_settings)
        self.spin_edge_sensitivity.valueChanged.connect(self.apply_edge_settings)
        self.combo_binary_preset.currentIndexChanged.connect(self.apply_binary_settings)
        self.combo_ternary_preset.currentIndexChanged.connect(self.apply_ternary_settings)
        self.spin_saliency_alpha.valueChanged.connect(self.apply_saliency_settings)
        self.combo_composition_guide.currentIndexChanged.connect(
            self.apply_composition_guide_settings
        )
        self.spin_focus_peak_sensitivity.valueChanged.connect(self.apply_focus_peaking_settings)
        self.combo_focus_peak_color.currentIndexChanged.connect(self.apply_focus_peaking_settings)
        self.spin_focus_peak_thickness.valueChanged.connect(self.apply_focus_peaking_settings)
        self.combo_squint_mode.currentIndexChanged.connect(self.apply_squint_settings)
        self.spin_squint_scale.valueChanged.connect(self.apply_squint_settings)
        self.spin_squint_blur.valueChanged.connect(self.apply_squint_settings)
        self.chk_vectorscope_skin_line.toggled.connect(self.apply_vectorscope_settings)
        self.spin_vectorscope_warn_threshold.valueChanged.connect(self.apply_vectorscope_settings)
        self.chk_preview_window.toggled.connect(self.on_preview_toggled)

    def _connect_layout_preset_signals(self) -> None:
        """レイアウトプリセット操作のシグナルを接続する。"""
        self.btn_save_preset.clicked.connect(self.save_layout_preset)
        self.btn_load_preset.clicked.connect(self.load_selected_layout_preset)
        self.btn_delete_preset.clicked.connect(self.delete_selected_layout_preset)

    def _build_menu_bar(self) -> None:
        """メニューバーと各アクションを構築する。"""
        # --- Menu bar (ウィンドウ / 設定 / レイアウト) ---
        mb = self.menuBar() if hasattr(self, "menuBar") else QMenuBar(self)
        win_menu = mb.addMenu("ウィンドウ")

        def _bind_dock_action(attr_name: str, title: str, default: bool, dock_attr: str):
            action = add_checkable_action(
                win_menu,
                title,
                default,
                lambda visible, name=dock_attr: self.toggle_dock(getattr(self, name), visible),
            )
            setattr(self, attr_name, action)

        for spec in _WINDOW_DOCK_MENU_ITEMS:
            _bind_dock_action(*spec)

        menu = mb.addMenu("設定")
        self.act_always_on_top = add_checkable_action(
            menu,
            "常に最前面に表示",
            C.DEFAULT_ALWAYS_ON_TOP,
            self.apply_always_on_top,
        )
        self.settings_action = menu.addAction("設定ウィンドウを開く")
        self.settings_action.triggered.connect(
            lambda: self.show_settings_window(C.SETTINGS_PAGE_CAPTURE)
        )

        layout_menu = mb.addMenu("レイアウト")
        self.presets_menu = layout_menu.addMenu("プリセットを適用")
        self.act_open_layout_settings = layout_menu.addAction("レイアウト設定を開く")
        self.act_open_layout_settings.triggered.connect(
            lambda: self.show_settings_window(C.SETTINGS_PAGE_LAYOUT)
        )
        self._setup_help_menu(mb)

    def _build_toolbar(self) -> None:
        """Start/Stop/画像読み込みのツールバーを構築する。"""
        # --- Toolbar for Start/Stop ---
        tb = self.addToolBar("コントロール")
        tb.setObjectName("controlToolbar")
        tb.setMovable(False)
        self.btn_start_bar = QPushButton("Start")
        self.btn_stop_bar = QPushButton("Stop")
        self.btn_start_bar.setObjectName("runStartBtn")
        self.btn_stop_bar.setObjectName("runStopBtn")
        self.btn_start_bar.setCheckable(True)
        self.btn_stop_bar.setCheckable(True)
        self.btn_start_bar.clicked.connect(self.on_start)
        self.btn_stop_bar.clicked.connect(self.on_stop)
        self.btn_load_image_bar = QPushButton("画像読み込み")
        self.btn_load_image_bar.clicked.connect(self.on_load_image)
        tb.addWidget(self.btn_start_bar)
        tb.addWidget(self.btn_stop_bar)
        tb.addWidget(self.btn_load_image_bar)
        self.btn_stop_bar.setChecked(True)

    def _setup_preview_and_docks(self) -> None:
        """プレビューとドック群を構築し、関連イベントを接続する。"""
        self.preview_window = PreviewWindow()
        self.preview_window.closed.connect(self.on_preview_closed)
        # 解析ビュー用ドック群を構築。
        setup_view_docks(self)
        if hasattr(self, "tabifiedDockWidgetActivated"):
            self.tabifiedDockWidgetActivated.connect(self._on_tabified_dock_activated)
        self.top_colors_bar.installEventFilter(self)
        if hasattr(self, "list_color_chips"):
            self.list_color_chips.currentRowChanged.connect(self._on_color_chip_selected)
        if hasattr(self.wheel, "harmonyGuideRotationChanged"):
            self.wheel.harmonyGuideRotationChanged.connect(self._on_wheel_harmony_rotation_changed)
        self.chk_scatter_hue_filter.toggled.connect(self.apply_scatter_settings)
        self.slider_scatter_hue_center.valueChanged.connect(self.apply_scatter_settings)
        self._sync_scatter_filter_controls()
        for d in self._dock_map.values():
            d.visibilityChanged.connect(lambda _v, self=self: self._sync_worker_view_flags())
            d.topLevelChanged.connect(
                lambda v, dock=d, self=self: self._on_dock_top_level_changed(dock, bool(v))
            )
            d.installEventFilter(self)
        self._sync_worker_view_flags()

    def _on_tabified_dock_activated(self, dock) -> None:
        """タブ切替直後の表示同期とスナップショット復元を行う。"""
        # タブ切替時に表示フラグ再同期と表示復元を行い、更新取りこぼしを防ぐ。
        self._sync_tabbed_dock_title_bars()
        self._sync_worker_view_flags()
        if dock is None:
            return
        self._restore_dock_from_snapshot(dock)
        QTimer.singleShot(0, lambda d=dock, self=self: self._restore_dock_from_snapshot(d))
        QTimer.singleShot(60, lambda d=dock, self=self: self._restore_dock_from_snapshot(d))

    def _initialize_runtime_defaults(self) -> None:
        """起動直後のワーカー既定値をUI設定から反映する。"""
        self.worker.set_interval(self.spin_interval.value())
        self.worker.set_sample_points(self.spin_points.value())
        self.apply_analysis_resolution_settings(save=False)
        self.worker.set_wheel_sat_threshold(self.spin_wheel_sat_threshold.value())
        self.worker.set_graph_every(C.DEFAULT_GRAPH_EVERY)
        # 初回表示前に設定/レイアウトを反映して、表示後の位置ジャンプを避ける。
        self._finish_startup()

    def _finish_startup(self):
        """設定ロード後の初期描画同期と自動処理開始を行う。"""
        if self._startup_finished:
            return
        self._startup_finished = True
        self.load_settings()
        if (
            HAS_WIN32
            and self._selected_capture_source() == C.CAPTURE_SOURCE_WINDOW
            and self.combo_win.count() <= 1
        ):
            self.refresh_windows()
        for dock in self._dock_map.values():
            self._on_dock_top_level_changed(dock, dock.isFloating())
        self._sync_tabbed_dock_title_bars()
        self.sync_window_menu_checks()
        self.update_placeholder()
        self._schedule_dock_rebalance()
        self._layout_autosave_enabled = True
        self._schedule_layout_autosave()
        self._start_release_check_once()
        # 構成差分時のみ、起動直後に最終補正する。
        if bool(self._startup_should_fit_window):
            QTimer.singleShot(260, self._fit_window_to_desktop)

    _setup_help_menu = mw_help.setup_help_menu
    _start_release_check_once = mw_help.start_release_check_once
    _check_latest_release = mw_help.check_latest_release
    _on_release_check_finished = mw_help.on_release_check_finished
    _open_release_page = mw_help.open_release_page

    def _request_save_settings(self):
        """設定保存をデバウンス付きで予約する。"""
        if self._settings_load_in_progress:
            return
        self._settings_save_pending = True
        self._settings_save_timer.start()

    def _flush_settings_save(self):
        """保留中の設定保存を実行する。"""
        if not self._settings_save_pending:
            return
        self._settings_save_pending = False
        self.save_settings()

    def showEvent(self, event):
        """初回表示時に画面内へ収まるようウィンドウサイズを補正する。"""
        super().showEvent(event)
        if not self._did_initial_screen_fit:
            self._did_initial_screen_fit = True
            if bool(self._startup_should_fit_window):
                self._fit_window_to_desktop()

    def event(self, event):
        """レイアウト・表示状態変化イベントに応じて同期処理を行う。"""
        if event.type() == QEvent.LayoutRequest:
            self._schedule_layout_autosave()
            self._schedule_dock_rebalance()
        elif event.type() == QEvent.WindowStateChange:
            self._schedule_layout_autosave()
            self._schedule_window_fit()
            self._refresh_topmost_if_enabled()
        elif event.type() == QEvent.Show:
            self._refresh_topmost_if_enabled()
        return super().event(event)

    def _handle_top_colors_bar_resize_event(self, obj, event) -> bool:
        """配色比率バーのリサイズイベントを処理したか返す。"""
        if obj is getattr(self, "top_colors_bar", None) and event.type() == QEvent.Resize:
            self._refresh_top_color_bar()
            return True
        return False

    def _handle_color_band_layout_event(self, obj, event) -> None:
        """配色比率ドックの表示/サイズ変更イベントを処理する。"""
        if obj is getattr(self, "dock_color_band", None) and event.type() in (
            QEvent.Resize,
            QEvent.Show,
        ):
            self._update_color_band_compact_visibility()

    def _remember_last_docked_size(self, dock) -> None:
        """フロートでないドックの直近サイズを必要時のみ記録する。"""
        if bool(dock.isFloating()):
            return
        size = dock.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        try:
            is_tabbed = len(self.tabifiedDockWidgets(dock)) > 0
        except Exception:
            is_tabbed = False
        # タブ内の非アクティブ状態では高さが極端に小さく見えることがあるため、
        # その瞬間値は次回フロート基準へ学習しない。
        if (not is_tabbed) or int(size.height()) >= 96:
            dock._last_docked_size = (int(size.width()), int(size.height()))

    @staticmethod
    def _should_pause_for_dock_event(event_type, *, is_floating: bool) -> bool:
        """ドックイベントで解析一時停止を入れるべきかを返す。"""
        return bool(
            event_type == QEvent.Resize
            or (event_type in (QEvent.Move, QEvent.Show) and not bool(is_floating))
        )

    def _handle_floating_state_dock_event(self, dock, event_type) -> None:
        """フローティング状態に応じたドックイベント処理を行う。"""
        if not dock.isFloating():
            self._schedule_dock_rebalance()
            return
        if event_type == QEvent.Move:
            self._notify_floating_dock_moved(dock)
            self._track_floating_dock_size(dock, from_move=True)
            return
        if event_type == QEvent.Resize:
            self._track_floating_dock_size(dock, from_move=False)

    def _maybe_restore_dock_snapshot_after_event(self, dock, event_type) -> None:
        """表示/リサイズ後に必要ならドックスナップショットを復元する。"""
        if event_type not in (QEvent.Show, QEvent.Resize):
            return
        # 初回表示直後にサイズが確定してからスナップショット復元できるようにする。
        if not bool(getattr(self, "_layout_interaction_pause_active", False)):
            self._restore_dock_from_snapshot(dock)

    def _handle_dock_layout_event(self, dock, event_type) -> None:
        """共通ドックレイアウトイベントを処理する。"""
        self._remember_last_docked_size(dock)
        is_floating = bool(dock.isFloating())
        should_pause = self._should_pause_for_dock_event(event_type, is_floating=is_floating)
        if should_pause:
            self._begin_layout_interaction_pause("dock_layout")
        self._update_floating_dock_dockability(dock)
        self._handle_floating_state_dock_event(dock, event_type)
        self._maybe_restore_dock_snapshot_after_event(dock, event_type)
        if should_pause:
            self._schedule_layout_interaction_resume("dock_layout")

    def _is_managed_dock(self, obj) -> bool:
        """イベント対象が管理中ドックか判定する。"""
        return obj in getattr(self, "_dock_map", {}).values()

    def eventFilter(self, obj, event):
        """ドック/タブ/カラーバーの共通イベントを捕捉して処理する。"""
        if self._handle_top_colors_bar_resize_event(obj, event):
            return super().eventFilter(obj, event)
        self._handle_color_band_layout_event(obj, event)
        if mw_tabs.is_dock_tab_bar(self, obj):
            if mw_tabs.handle_dock_tab_bar_event(self, obj, event):
                return True
            return super().eventFilter(obj, event)
        if self._is_managed_dock(obj):
            event_type = event.type()
            if event_type in (QEvent.Move, QEvent.Show, QEvent.Resize):
                self._handle_dock_layout_event(obj, event_type)
        return super().eventFilter(obj, event)

    def moveEvent(self, event):
        """メイン移動時にフローティングドック状態と保存予約を更新する。"""
        super().moveEvent(event)
        self._sync_all_floating_dock_dockability()
        self._schedule_layout_autosave()

    def resizeEvent(self, event):
        """メインリサイズ時の一時停止制御とレイアウト同期を行う。"""
        self._begin_layout_interaction_pause("main_resize")
        super().resizeEvent(event)
        self._sync_all_floating_dock_dockability()
        self.update_placeholder()
        self._schedule_layout_autosave()
        self._schedule_layout_interaction_resume("main_resize")

    _fit_window_to_desktop = mw_windowing.fit_window_to_desktop
    _fit_dialog_to_desktop = mw_windowing.fit_dialog_to_desktop
    _schedule_window_fit = mw_windowing.schedule_window_fit
    _is_always_on_top_enabled = mw_topmost.is_always_on_top_enabled
    _schedule_dock_rebalance = mw_windowing.schedule_dock_rebalance
    _rebalance_dock_layout = mw_windowing.rebalance_dock_layout
    _on_dock_top_level_changed = mw_windowing.on_dock_top_level_changed
    _update_floating_dock_dockability = mw_windowing.update_floating_dock_dockability
    _sync_all_floating_dock_dockability = mw_windowing.sync_all_floating_dock_dockability
    _notify_floating_dock_moved = mw_windowing.notify_floating_dock_moved
    _track_floating_dock_size = mw_windowing.track_floating_dock_size

    def _sync_tabbed_dock_title_bars(self, *_):
        """タブ化状態に応じてドックのタイトルバー表示を同期する。"""
        mw_tabs.sync_tabbed_dock_title_bars(self)

    apply_always_on_top = mw_topmost.apply_always_on_top
    _refresh_topmost_if_enabled = mw_topmost.refresh_topmost_if_enabled
    _present_settings_window = mw_topmost.present_settings_window
    _refresh_top_color_bar = mw_color_band.refresh_top_color_bar
    _on_color_chip_selected = mw_color_band.on_color_chip_selected
    _on_wheel_harmony_rotation_changed = mw_settings.on_wheel_harmony_rotation_changed
    _update_color_band_compact_visibility = mw_color_band.update_color_band_compact_visibility
    _restore_dock_from_snapshot = mw_snapshot.restore_dock_from_snapshot
    on_status = mw_runtime.on_status
    _cancel_image_analysis = mw_runtime.cancel_image_analysis
    on_load_image = mw_runtime.on_load_image
    on_image_analysis_progress = mw_runtime.on_image_analysis_progress
    on_image_analysis_finished = mw_runtime.on_image_analysis_finished
    on_image_analysis_failed = mw_runtime.on_image_analysis_failed
    on_image_analysis_canceled = mw_runtime.on_image_analysis_canceled
    on_start = mw_runtime.on_start
    on_stop = mw_runtime.on_stop
    closeEvent = mw_runtime.close_event
    refresh_windows = mw_runtime.refresh_windows
    _selected_capture_source = mw_runtime.selected_capture_source
    _sync_capture_source_ui = mw_runtime.sync_capture_source_ui
    apply_capture_source = mw_runtime.apply_capture_source
    _apply_capture_source = mw_runtime._apply_capture_source
    on_window_changed = mw_runtime.on_window_changed
    on_window_text_committed = mw_runtime.on_window_text_committed
    _selected_wheel_sat_threshold = mw_settings.selected_wheel_sat_threshold
    _apply_ui_style = mw_windowing.apply_ui_style
    _sync_mode_dependent_rows = mw_settings.sync_mode_dependent_rows
    _sync_squint_mode_rows = mw_settings.sync_squint_mode_rows
    _sync_analysis_resolution_rows = mw_settings.sync_analysis_resolution_rows
    _sync_color_band_controls = mw_settings.sync_color_band_controls
    _sync_worker_view_flags = mw_runtime.sync_worker_view_flags
    _begin_layout_interaction_pause = mw_runtime.begin_layout_interaction_pause
    _schedule_layout_interaction_resume = mw_runtime.schedule_layout_interaction_resume
    _end_layout_interaction_pause = mw_runtime.end_layout_interaction_pause
    apply_sample_points_settings = mw_settings.apply_sample_points_settings
    _sync_scatter_filter_controls = mw_settings.sync_scatter_filter_controls
    apply_scatter_settings = mw_settings.apply_scatter_settings
    apply_analysis_resolution_settings = mw_settings.apply_analysis_resolution_settings
    apply_wheel_settings = mw_settings.apply_wheel_settings
    apply_color_band_settings = mw_settings.apply_color_band_settings
    apply_rgb_hist_settings = mw_settings.apply_rgb_hist_settings
    apply_edge_settings = mw_settings.apply_edge_settings
    apply_binary_settings = mw_settings.apply_binary_settings
    apply_ternary_settings = mw_settings.apply_ternary_settings
    apply_saliency_settings = mw_settings.apply_saliency_settings
    apply_composition_guide_settings = mw_settings.apply_composition_guide_settings
    apply_focus_peaking_settings = mw_settings.apply_focus_peaking_settings
    apply_squint_settings = mw_settings.apply_squint_settings
    _update_vectorscope_warning_label = mw_settings.update_vectorscope_warning_label
    apply_vectorscope_settings = mw_settings.apply_vectorscope_settings
    _update_preview_snapshot = mw_runtime.update_preview_snapshot
    on_preview_toggled = mw_runtime.on_preview_toggled
    on_preview_closed = mw_runtime.on_preview_closed
    apply_mode_settings = mw_settings.apply_mode_settings
    load_settings = mw_settings.load_settings
    save_settings = mw_settings.save_settings
    sync_window_menu_checks = mw_windowing.sync_window_menu_checks
    _apply_default_view_layout = mw_layout_presets.apply_default_view_layout
    save_current_layout_to_config = mw_layout_presets.save_current_layout_to_config
    _schedule_layout_autosave = mw_layout_presets.schedule_layout_autosave
    apply_layout_from_config = mw_layout_presets.apply_layout_from_config
    refresh_layout_preset_views = mw_layout_presets.refresh_layout_preset_views
    apply_layout_preset = mw_layout_presets.apply_layout_preset
    load_selected_layout_preset = mw_layout_presets.load_selected_layout_preset
    save_layout_preset = mw_layout_presets.save_layout_preset
    delete_selected_layout_preset = mw_layout_presets.delete_selected_layout_preset
    toggle_dock = mw_windowing.toggle_dock
    update_placeholder = mw_windowing.update_placeholder
    show_settings_window = show_settings_dialog_window
    hide_settings_window = hide_settings_dialog_window
    _close_roi_selectors = mw_roi.close_roi_selectors
    pick_roi_on_screen = mw_roi.pick_roi_on_screen
    on_roi_screen_selected = mw_roi.on_roi_screen_selected
    pick_roi_in_window = mw_roi.pick_roi_in_window
    on_roi_window_selected = mw_roi.on_roi_window_selected
    on_result = mw_snapshot.on_result
