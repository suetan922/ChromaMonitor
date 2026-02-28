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
from .ui.main_window import help_actions as mw_help
from .ui.main_window import result_handlers as mw_results
from .ui.main_window import roi_handlers as mw_roi
from .ui.main_window import runtime_actions as mw_runtime
from .ui.main_window import settings_logic as mw_settings
from .ui.main_window import window_layout as mw_windowing
from .ui.settings_dialog import hide_settings_window as hide_settings_dialog_window
from .ui.settings_dialog import show_settings_window as show_settings_dialog_window
from .ui.view_docks import setup_view_docks
from .ui.input_widgets import (
    SelectAllLineEdit,
    SelectAllSpinBox,
    add_checkable_action,
    configure_numeric_input,
)
from .util import constants as C
from .views import PreviewWindow


_WINDOW_DOCK_MENU_ITEMS = (
    ("act_color", "色相環", True, "dock_color"),
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
_FOCUS_PEAK_THICKNESS_STEP = 0.1
_SQUINT_BLUR_SIGMA_STEP = 0.1


class MainWindow(QMainWindow):

    def __init__(self):
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
        self._settings_save_timer = QTimer(self)
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(_SETTINGS_SAVE_DEBOUNCE_MS)
        self._settings_save_timer.timeout.connect(self._flush_settings_save)
        self._settings_save_pending = False
        self._settings_load_in_progress = False
        self._startup_finished = False
        self._release_page_url = C.APP_RELEASES_URL
        self._update_check_started = False
        self._update_reply = None
        self._update_network = QNetworkAccessManager(self)
        self._update_network.finished.connect(self._on_release_check_finished)
        # ROI選択オーバーレイ（マルチモニタ対応）管理。
        self._roi_selectors = []

    def _init_analyzer_workers(self) -> None:
        # キャプチャ解析ワーカー（ライブ）と画像解析ワーカー（単発）を分離して保持。
        self.worker = AnalyzerWorker()
        self.worker.resultReady.connect(self.on_result)
        self.worker.status.connect(self.on_status)
        self._image_thread = None
        self._image_worker = None
        self._image_progress = None

    def _build_control_widgets(self) -> None:
        # --- Controls: キャプチャ/解析設定 ---
        self.btn_refresh = QPushButton("ウィンドウ一覧更新")
        self.combo_win = QComboBox()
        self.combo_win.setEditable(True)
        self.combo_win.setInsertPolicy(QComboBox.NoInsert)
        win_completer = QCompleter(self.combo_win.model(), self.combo_win)
        win_completer.setCaseSensitivity(Qt.CaseInsensitive)
        win_completer.setFilterMode(Qt.MatchContains)
        win_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.combo_win.setCompleter(win_completer)
        if self.combo_win.lineEdit() is not None:
            self.combo_win.lineEdit().setClearButtonEnabled(True)
        self.btn_pick_roi_win = QPushButton("領域選択（ウィンドウ内）")
        self.btn_pick_roi_screen = QPushButton("領域選択（画面）")

        self.spin_interval = QDoubleSpinBox()
        self.spin_interval.setSuffix(" 秒")
        self.spin_interval.setDecimals(2)
        self.spin_interval.setRange(0.10, 10.00)
        self.spin_interval.setSingleStep(0.10)
        self.spin_interval.setValue(C.DEFAULT_INTERVAL_SEC)
        configure_numeric_input(self.spin_interval)

        self.spin_points = SelectAllSpinBox()
        self.spin_points.setRange(C.ANALYZER_MIN_SAMPLE_POINTS, C.ANALYZER_MAX_SAMPLE_POINTS)
        self.spin_points.setSingleStep(500)
        self.spin_points.setValue(C.DEFAULT_SAMPLE_POINTS)
        configure_numeric_input(self.spin_points)
        self.combo_analysis_resolution_mode = QComboBox()
        self.combo_analysis_resolution_mode.addItem(
            "オリジナルサイズ",
            C.ANALYSIS_RESOLUTION_MODE_ORIGINAL,
        )
        self.combo_analysis_resolution_mode.addItem(
            "指定サイズ",
            C.ANALYSIS_RESOLUTION_MODE_CUSTOM,
        )
        self.edit_analysis_max_dim = SelectAllSpinBox()
        self.edit_analysis_max_dim.setRange(C.ANALYZER_MAX_DIM_MIN, C.ANALYZER_MAX_DIM_MAX)
        self.edit_analysis_max_dim.setSingleStep(10)
        self.edit_analysis_max_dim.setValue(C.ANALYZER_MAX_DIM)
        self.edit_analysis_max_dim.setSuffix(" px")
        configure_numeric_input(self.edit_analysis_max_dim)

        self.combo_capture_source = QComboBox()
        self.combo_capture_source.addItem("ウィンドウを選んで取得", C.CAPTURE_SOURCE_WINDOW)
        self.combo_capture_source.addItem("画面範囲を直接指定", C.CAPTURE_SOURCE_SCREEN)

        self.combo_scatter_shape = QComboBox()
        self.combo_scatter_shape.addItem("四角", C.SCATTER_SHAPE_SQUARE)
        self.combo_scatter_shape.addItem("三角", C.SCATTER_SHAPE_TRIANGLE)
        self.combo_scatter_render_mode = QComboBox()
        self.combo_scatter_render_mode.addItem(
            "色をそのまま",
            C.SCATTER_RENDER_MODE_DOMINANT,
        )
        self.combo_scatter_render_mode.addItem(
            "ヒートマップ",
            C.SCATTER_RENDER_MODE_HEATMAP,
        )
        self.combo_wheel_mode = QComboBox()
        self.combo_wheel_mode.addItem("HSV 180ビン", C.WHEEL_MODE_HSV180)
        self.combo_wheel_mode.addItem("マンセル基準（40色相）", C.WHEEL_MODE_MUNSELL40)
        self.combo_rgb_hist_mode = QComboBox()
        self.combo_rgb_hist_mode.addItem("横並び", C.RGB_HIST_MODE_SIDE_BY_SIDE)
        self.combo_rgb_hist_mode.addItem("重ね表示", C.RGB_HIST_MODE_OVERLAY)
        self.spin_wheel_sat_threshold = SelectAllSpinBox()
        self.spin_wheel_sat_threshold.setRange(C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX)
        self.spin_wheel_sat_threshold.setValue(C.DEFAULT_WHEEL_SAT_THRESHOLD)
        self.spin_wheel_sat_threshold.setSingleStep(1)
        self.spin_wheel_sat_threshold.setSuffix(" / 255")
        configure_numeric_input(self.spin_wheel_sat_threshold)

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("一定間隔で更新", C.UPDATE_MODE_INTERVAL)
        self.combo_mode.addItem("画面に動きがあったとき", C.UPDATE_MODE_CHANGE)
        self.spin_diff = QDoubleSpinBox()
        self.spin_diff.setRange(C.ANALYZER_MIN_DIFF_THRESHOLD, 50.0)
        self.spin_diff.setDecimals(1)
        self.spin_diff.setSingleStep(C.ANALYZER_MIN_DIFF_THRESHOLD)
        self.spin_diff.setValue(C.DEFAULT_DIFF_THRESHOLD)
        configure_numeric_input(self.spin_diff)
        self.spin_stable = SelectAllSpinBox()
        self.spin_stable.setRange(C.ANALYZER_MIN_STABLE_FRAMES, 20)
        self.spin_stable.setValue(C.DEFAULT_STABLE_FRAMES)
        configure_numeric_input(self.spin_stable)
        self.spin_edge_sensitivity = SelectAllSpinBox()
        self.spin_edge_sensitivity.setRange(C.EDGE_SENSITIVITY_MIN, C.EDGE_SENSITIVITY_MAX)
        self.spin_edge_sensitivity.setValue(C.DEFAULT_EDGE_SENSITIVITY)
        self.spin_edge_sensitivity.setSuffix(" / 100")
        configure_numeric_input(self.spin_edge_sensitivity, min_width=130)
        self.combo_binary_preset = QComboBox()
        self.combo_binary_preset.addItem("自動", C.BINARY_PRESET_AUTO)
        self.combo_binary_preset.addItem("白を増やす", C.BINARY_PRESET_MORE_WHITE)
        self.combo_binary_preset.addItem("黒を増やす", C.BINARY_PRESET_MORE_BLACK)
        self.combo_ternary_preset = QComboBox()
        self.combo_ternary_preset.addItem("標準", C.TERNARY_PRESET_STANDARD)
        self.combo_ternary_preset.addItem("やわらかめ", C.TERNARY_PRESET_SOFT)
        self.combo_ternary_preset.addItem("くっきり", C.TERNARY_PRESET_STRONG)
        self.spin_saliency_alpha = SelectAllSpinBox()
        self.spin_saliency_alpha.setRange(C.SALIENCY_ALPHA_MIN, C.SALIENCY_ALPHA_MAX)
        self.spin_saliency_alpha.setValue(C.DEFAULT_SALIENCY_OVERLAY_ALPHA)
        self.spin_saliency_alpha.setSuffix(" %")
        configure_numeric_input(self.spin_saliency_alpha)
        self.combo_composition_guide = QComboBox()
        self.combo_composition_guide.addItem("なし", C.COMPOSITION_GUIDE_NONE)
        self.combo_composition_guide.addItem("三分割", C.COMPOSITION_GUIDE_THIRDS)
        self.combo_composition_guide.addItem("中央クロス", C.COMPOSITION_GUIDE_CENTER)
        self.combo_composition_guide.addItem("対角線", C.COMPOSITION_GUIDE_DIAGONAL)
        self.spin_focus_peak_sensitivity = SelectAllSpinBox()
        self.spin_focus_peak_sensitivity.setRange(
            C.FOCUS_PEAK_SENSITIVITY_MIN, C.FOCUS_PEAK_SENSITIVITY_MAX
        )
        self.spin_focus_peak_sensitivity.setValue(C.DEFAULT_FOCUS_PEAK_SENSITIVITY)
        self.spin_focus_peak_sensitivity.setSuffix(" / 100")
        configure_numeric_input(self.spin_focus_peak_sensitivity, min_width=130)
        self.combo_focus_peak_color = QComboBox()
        self.combo_focus_peak_color.addItem("シアン", C.FOCUS_PEAK_COLOR_CYAN)
        self.combo_focus_peak_color.addItem("グリーン", C.FOCUS_PEAK_COLOR_GREEN)
        self.combo_focus_peak_color.addItem("イエロー", C.FOCUS_PEAK_COLOR_YELLOW)
        self.combo_focus_peak_color.addItem("レッド", C.FOCUS_PEAK_COLOR_RED)
        self.spin_focus_peak_thickness = QDoubleSpinBox()
        self.spin_focus_peak_thickness.setRange(
            C.FOCUS_PEAK_THICKNESS_MIN, C.FOCUS_PEAK_THICKNESS_MAX
        )
        self.spin_focus_peak_thickness.setValue(C.DEFAULT_FOCUS_PEAK_THICKNESS)
        self.spin_focus_peak_thickness.setDecimals(1)
        self.spin_focus_peak_thickness.setSingleStep(_FOCUS_PEAK_THICKNESS_STEP)
        self.spin_focus_peak_thickness.setSuffix(" px")
        configure_numeric_input(self.spin_focus_peak_thickness)
        self.combo_squint_mode = QComboBox()
        self.combo_squint_mode.addItem("ぼかしのみ", C.SQUINT_MODE_BLUR)
        self.combo_squint_mode.addItem("縮小 → 拡大", C.SQUINT_MODE_SCALE)
        self.combo_squint_mode.addItem("縮小 → 拡大 + ぼかし", C.SQUINT_MODE_SCALE_BLUR)
        self.spin_squint_scale = SelectAllSpinBox()
        self.spin_squint_scale.setRange(C.SQUINT_SCALE_PERCENT_MIN, C.SQUINT_SCALE_PERCENT_MAX)
        self.spin_squint_scale.setValue(C.DEFAULT_SQUINT_SCALE_PERCENT)
        self.spin_squint_scale.setSuffix(" %")
        configure_numeric_input(self.spin_squint_scale)
        self.spin_squint_blur = QDoubleSpinBox()
        self.spin_squint_blur.setRange(C.SQUINT_BLUR_SIGMA_MIN, C.SQUINT_BLUR_SIGMA_MAX)
        self.spin_squint_blur.setValue(C.DEFAULT_SQUINT_BLUR_SIGMA)
        self.spin_squint_blur.setDecimals(1)
        self.spin_squint_blur.setSingleStep(_SQUINT_BLUR_SIGMA_STEP)
        self.spin_squint_blur.setSuffix(" px")
        configure_numeric_input(self.spin_squint_blur)
        self.chk_vectorscope_skin_line = QCheckBox("スキントーンラインを表示")
        self.chk_vectorscope_skin_line.setChecked(C.DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE)
        self.spin_vectorscope_warn_threshold = SelectAllSpinBox()
        self.spin_vectorscope_warn_threshold.setRange(
            C.VECTORSCOPE_WARN_THRESHOLD_MIN,
            C.VECTORSCOPE_WARN_THRESHOLD_MAX,
        )
        self.spin_vectorscope_warn_threshold.setValue(C.DEFAULT_VECTORSCOPE_WARN_THRESHOLD)
        self.spin_vectorscope_warn_threshold.setSuffix(" %")
        configure_numeric_input(self.spin_vectorscope_warn_threshold)

        self.chk_preview_window = QCheckBox("領域プレビュー")
        self.chk_preview_window.setChecked(_DEFAULT_PREVIEW_WINDOW)

        self.edit_preset_name = SelectAllLineEdit()
        self.edit_preset_name.setPlaceholderText("プリセット名")
        self.combo_layout_presets = QComboBox()
        self.btn_save_preset = QPushButton("プリセット保存")
        self.btn_load_preset = QPushButton("適用")
        self.btn_delete_preset = QPushButton("削除")
        self._row_target_settings = None
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
        self.btn_refresh.clicked.connect(self.refresh_windows)
        self.combo_win.currentIndexChanged.connect(self.on_window_changed)
        if self.combo_win.lineEdit() is not None:
            self.combo_win.lineEdit().editingFinished.connect(self.on_window_text_committed)
        self.btn_pick_roi_win.clicked.connect(self.pick_roi_in_window)
        self.btn_pick_roi_screen.clicked.connect(self.pick_roi_on_screen)
        self.combo_capture_source.currentIndexChanged.connect(self.apply_capture_source)
        self.spin_interval.valueChanged.connect(lambda v: self.worker.set_interval(float(v)))
        self.spin_points.valueChanged.connect(self.apply_sample_points_settings)
        self.combo_analysis_resolution_mode.currentIndexChanged.connect(
            self.apply_analysis_resolution_settings
        )
        self.edit_analysis_max_dim.valueChanged.connect(self.apply_analysis_resolution_settings)
        self.combo_scatter_shape.currentIndexChanged.connect(self.apply_scatter_settings)
        self.combo_scatter_render_mode.currentIndexChanged.connect(self.apply_scatter_settings)
        self.combo_wheel_mode.currentIndexChanged.connect(self.apply_wheel_settings)
        self.combo_rgb_hist_mode.currentIndexChanged.connect(self.apply_rgb_hist_settings)
        self.spin_wheel_sat_threshold.valueChanged.connect(self.apply_wheel_settings)
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
        self.btn_save_preset.clicked.connect(self.save_layout_preset)
        self.btn_load_preset.clicked.connect(self.load_selected_layout_preset)
        self.btn_delete_preset.clicked.connect(self.delete_selected_layout_preset)

    def _build_menu_bar(self) -> None:
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
        self.preview_window = PreviewWindow()
        self.preview_window.closed.connect(self.on_preview_closed)
        # 解析ビュー用ドック群を構築。
        setup_view_docks(self)
        if hasattr(self, "tabifiedDockWidgetActivated"):
            self.tabifiedDockWidgetActivated.connect(self._sync_tabbed_dock_title_bars)
        self.top_colors_bar.installEventFilter(self)
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

    def _initialize_runtime_defaults(self) -> None:
        self.worker.set_interval(self.spin_interval.value())
        self.worker.set_sample_points(self.spin_points.value())
        self.apply_analysis_resolution_settings(save=False)
        self.worker.set_wheel_sat_threshold(self.spin_wheel_sat_threshold.value())
        self.worker.set_graph_every(C.DEFAULT_GRAPH_EVERY)
        QTimer.singleShot(0, self._finish_startup)

    def _finish_startup(self):
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
        self._fit_window_to_desktop()
        self.sync_window_menu_checks()
        self.update_placeholder()
        self._schedule_dock_rebalance()
        self._layout_autosave_enabled = True
        self._schedule_layout_autosave()
        self._start_release_check_once()
        # 起動直後のレイアウト収束後に、画面外へのはみ出しを最終補正する。
        QTimer.singleShot(260, self._fit_window_to_desktop)

    _setup_help_menu = mw_help.setup_help_menu
    _start_release_check_once = mw_help.start_release_check_once
    _check_latest_release = mw_help.check_latest_release
    _on_release_check_finished = mw_help.on_release_check_finished
    _open_release_page = mw_help.open_release_page

    def _request_save_settings(self):
        if self._settings_load_in_progress:
            return
        self._settings_save_pending = True
        self._settings_save_timer.start()

    def _flush_settings_save(self):
        if not self._settings_save_pending:
            return
        self._settings_save_pending = False
        self.save_settings()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._did_initial_screen_fit:
            self._did_initial_screen_fit = True
            self._fit_window_to_desktop()

    def event(self, event):
        if event.type() == QEvent.LayoutRequest:
            self._schedule_layout_autosave()
            self._schedule_dock_rebalance()
        elif event.type() == QEvent.WindowStateChange:
            self._schedule_layout_autosave()
            self._schedule_window_fit()
        return super().event(event)

    def eventFilter(self, obj, event):
        if obj is getattr(self, "top_colors_bar", None) and event.type() == QEvent.Resize:
            self._refresh_top_color_bar()
            return super().eventFilter(obj, event)
        if mw_windowing.is_dock_tab_bar(self, obj):
            if mw_windowing.handle_dock_tab_bar_event(self, obj, event):
                return True
            return super().eventFilter(obj, event)
        if obj in getattr(self, "_dock_map", {}).values():
            if event.type() in (QEvent.Move, QEvent.Show, QEvent.Resize):
                self._update_floating_dock_dockability(obj)
                if not obj.isFloating():
                    self._schedule_dock_rebalance()
        return super().eventFilter(obj, event)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._sync_all_floating_dock_dockability()
        self._schedule_layout_autosave()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_all_floating_dock_dockability()
        self._schedule_layout_autosave()
        self._schedule_window_fit()

    _fit_window_to_desktop = mw_windowing.fit_window_to_desktop
    _schedule_window_fit = mw_windowing.schedule_window_fit
    _is_always_on_top_enabled = mw_windowing.is_always_on_top_enabled
    _schedule_dock_rebalance = mw_windowing.schedule_dock_rebalance
    _rebalance_dock_layout = mw_windowing.rebalance_dock_layout
    _on_dock_top_level_changed = mw_windowing.on_dock_top_level_changed
    _update_floating_dock_dockability = mw_windowing.update_floating_dock_dockability
    _sync_all_floating_dock_dockability = mw_windowing.sync_all_floating_dock_dockability

    def _sync_tabbed_dock_title_bars(self, *_):
        mw_windowing.sync_tabbed_dock_title_bars(self)

    apply_always_on_top = mw_windowing.apply_always_on_top
    _present_settings_window = mw_windowing.present_settings_window
    _refresh_top_color_bar = mw_results.refresh_top_color_bar
    _restore_dock_from_snapshot = mw_results.restore_dock_from_snapshot
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
    _sync_worker_view_flags = mw_runtime.sync_worker_view_flags
    apply_sample_points_settings = mw_settings.apply_sample_points_settings
    _sync_scatter_filter_controls = mw_settings.sync_scatter_filter_controls
    apply_scatter_settings = mw_settings.apply_scatter_settings
    apply_analysis_resolution_settings = mw_settings.apply_analysis_resolution_settings
    apply_wheel_settings = mw_settings.apply_wheel_settings
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
    on_result = mw_results.on_result
