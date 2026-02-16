import sys

from PySide6.QtCore import QEvent, QRect, QTimer
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenuBar,
    QPushButton,
    QSpinBox,
)

from .analyzer import AnalyzerWorker
from .capture.win32_windows import HAS_WIN32
from .ui.docks import setup_view_docks
from .ui.layout_presets import (
    apply_default_view_layout as apply_default_view_layout_ops,
)
from .ui.layout_presets import apply_layout_from_config as apply_layout_from_config_ops
from .ui.layout_presets import apply_layout_preset as apply_layout_preset_ops
from .ui.layout_presets import (
    delete_selected_layout_preset as delete_selected_layout_preset_ops,
)
from .ui.layout_presets import (
    load_selected_layout_preset as load_selected_layout_preset_ops,
)
from .ui.layout_presets import (
    refresh_layout_preset_views as refresh_layout_preset_views_ops,
)
from .ui.layout_presets import (
    save_current_layout_to_config as save_current_layout_to_config_ops,
)
from .ui.layout_presets import save_layout_preset as save_layout_preset_ops
from .ui.layout_presets import schedule_layout_autosave as schedule_layout_autosave_ops
from .ui.main_window import results as mw_results
from .ui.main_window import roi as mw_roi
from .ui.main_window import runtime as mw_runtime
from .ui.main_window import settings as mw_settings
from .ui.main_window import windowing as mw_windowing
from .ui.settings_window import hide_settings_window as hide_settings_dialog_window
from .ui.settings_window import show_settings_window as show_settings_dialog_window
from .util import constants as C
from .widgets import PreviewWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChromaMonitor")
        self.resize(1240, 760)
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
        self._dock_rebalance_timer.setInterval(60)
        self._dock_rebalance_timer.timeout.connect(self._rebalance_dock_layout)
        self._settings_save_timer = QTimer(self)
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(C.SETTINGS_SAVE_DEBOUNCE_MS)
        self._settings_save_timer.timeout.connect(self._flush_settings_save)
        self._settings_save_pending = False
        self._settings_load_in_progress = False
        self._startup_finished = False

        # ROI選択オーバーレイ（マルチモニタ対応）管理。
        self._roi_selector = None
        self._roi_selectors = []

        # キャプチャ解析ワーカー（ライブ）と画像解析ワーカー（単発）を分離して保持。
        self.worker = AnalyzerWorker()
        self.worker.resultReady.connect(self.on_result)
        self.worker.status.connect(self.on_status)
        self._image_thread = None
        self._image_worker = None
        self._image_progress = None

        # --- Controls: キャプチャ/解析設定 ---
        self.btn_refresh = QPushButton("ウィンドウ一覧更新")
        self.combo_win = QComboBox()
        self.btn_pick_roi_win = QPushButton("領域選択（ウィンドウ内）")
        self.btn_pick_roi_screen = QPushButton("領域選択（画面）")

        self.spin_interval = QDoubleSpinBox()
        self.spin_interval.setSuffix(" 秒")
        self.spin_interval.setDecimals(2)
        self.spin_interval.setRange(0.10, 10.00)
        self.spin_interval.setSingleStep(0.10)
        self.spin_interval.setValue(C.DEFAULT_INTERVAL_SEC)
        self.spin_interval.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_interval.setMinimumWidth(110)
        self.spin_interval.setMinimumHeight(28)

        self.spin_points = QSpinBox()
        self.spin_points.setRange(C.ANALYZER_MIN_SAMPLE_POINTS, C.ANALYZER_MAX_SAMPLE_POINTS)
        self.spin_points.setSingleStep(500)
        self.spin_points.setValue(C.DEFAULT_SAMPLE_POINTS)
        self.spin_points.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_points.setMinimumWidth(110)
        self.spin_points.setMinimumHeight(28)
        self.combo_analysis_resolution_mode = QComboBox()
        self.combo_analysis_resolution_mode.addItem(
            "オリジナルサイズ",
            C.ANALYSIS_RESOLUTION_MODE_ORIGINAL,
        )
        self.combo_analysis_resolution_mode.addItem(
            "指定サイズ",
            C.ANALYSIS_RESOLUTION_MODE_CUSTOM,
        )
        self.edit_analysis_max_dim = QLineEdit(str(C.ANALYZER_MAX_DIM))
        self.edit_analysis_max_dim.setValidator(
            QIntValidator(C.ANALYZER_MAX_DIM_MIN, C.ANALYZER_MAX_DIM_MAX, self)
        )
        self.edit_analysis_max_dim.setMinimumWidth(110)
        self.edit_analysis_max_dim.setMinimumHeight(28)
        self.edit_analysis_max_dim.setPlaceholderText(
            f"{C.ANALYZER_MAX_DIM_MIN}〜{C.ANALYZER_MAX_DIM_MAX}"
        )

        self.combo_capture_source = QComboBox()
        self.combo_capture_source.addItem("ウィンドウを選んで取得", C.CAPTURE_SOURCE_WINDOW)
        self.combo_capture_source.addItem("画面範囲を直接指定", C.CAPTURE_SOURCE_SCREEN)

        self.combo_scatter_shape = QComboBox()
        self.combo_scatter_shape.addItem("四角", C.SCATTER_SHAPE_SQUARE)
        self.combo_scatter_shape.addItem("三角", C.SCATTER_SHAPE_TRIANGLE)
        self.combo_wheel_mode = QComboBox()
        self.combo_wheel_mode.addItem("HSV 180ビン", C.WHEEL_MODE_HSV180)
        self.combo_wheel_mode.addItem("マンセル基準（40色相）", C.WHEEL_MODE_MUNSELL40)
        self.spin_wheel_sat_threshold = QSpinBox()
        self.spin_wheel_sat_threshold.setRange(C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX)
        self.spin_wheel_sat_threshold.setValue(C.DEFAULT_WHEEL_SAT_THRESHOLD)
        self.spin_wheel_sat_threshold.setSingleStep(1)
        self.spin_wheel_sat_threshold.setSuffix(" / 255")
        self.spin_wheel_sat_threshold.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_wheel_sat_threshold.setMinimumWidth(110)
        self.spin_wheel_sat_threshold.setMinimumHeight(28)

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("一定間隔で更新", C.UPDATE_MODE_INTERVAL)
        self.combo_mode.addItem("画面に動きがあったとき", C.UPDATE_MODE_CHANGE)
        self.spin_diff = QDoubleSpinBox()
        self.spin_diff.setRange(C.ANALYZER_MIN_DIFF_THRESHOLD, 50.0)
        self.spin_diff.setDecimals(1)
        self.spin_diff.setSingleStep(C.ANALYZER_MIN_DIFF_THRESHOLD)
        self.spin_diff.setValue(C.DEFAULT_DIFF_THRESHOLD)
        self.spin_diff.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_diff.setMinimumWidth(110)
        self.spin_diff.setMinimumHeight(28)
        self.spin_stable = QSpinBox()
        self.spin_stable.setRange(C.ANALYZER_MIN_STABLE_FRAMES, 20)
        self.spin_stable.setValue(C.DEFAULT_STABLE_FRAMES)
        self.spin_stable.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_stable.setMinimumWidth(110)
        self.spin_stable.setMinimumHeight(28)
        self.spin_edge_sensitivity = QSpinBox()
        self.spin_edge_sensitivity.setRange(C.EDGE_SENSITIVITY_MIN, C.EDGE_SENSITIVITY_MAX)
        self.spin_edge_sensitivity.setValue(C.DEFAULT_EDGE_SENSITIVITY)
        self.spin_edge_sensitivity.setSuffix(" / 100")
        self.spin_edge_sensitivity.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_edge_sensitivity.setMinimumWidth(130)
        self.spin_edge_sensitivity.setMinimumHeight(28)
        self.combo_binary_preset = QComboBox()
        self.combo_binary_preset.addItem("自動", C.BINARY_PRESET_AUTO)
        self.combo_binary_preset.addItem("白を増やす", C.BINARY_PRESET_MORE_WHITE)
        self.combo_binary_preset.addItem("黒を増やす", C.BINARY_PRESET_MORE_BLACK)
        self.combo_ternary_preset = QComboBox()
        self.combo_ternary_preset.addItem("標準", C.TERNARY_PRESET_STANDARD)
        self.combo_ternary_preset.addItem("やわらかめ", C.TERNARY_PRESET_SOFT)
        self.combo_ternary_preset.addItem("くっきり", C.TERNARY_PRESET_STRONG)
        self.spin_saliency_alpha = QSpinBox()
        self.spin_saliency_alpha.setRange(C.SALIENCY_ALPHA_MIN, C.SALIENCY_ALPHA_MAX)
        self.spin_saliency_alpha.setValue(C.DEFAULT_SALIENCY_OVERLAY_ALPHA)
        self.spin_saliency_alpha.setSuffix(" %")
        self.spin_saliency_alpha.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_saliency_alpha.setMinimumWidth(110)
        self.spin_saliency_alpha.setMinimumHeight(28)
        self.combo_composition_guide = QComboBox()
        self.combo_composition_guide.addItem("なし", C.COMPOSITION_GUIDE_NONE)
        self.combo_composition_guide.addItem("三分割", C.COMPOSITION_GUIDE_THIRDS)
        self.combo_composition_guide.addItem("中央クロス", C.COMPOSITION_GUIDE_CENTER)
        self.combo_composition_guide.addItem("対角線", C.COMPOSITION_GUIDE_DIAGONAL)
        self.spin_focus_peak_sensitivity = QSpinBox()
        self.spin_focus_peak_sensitivity.setRange(
            C.FOCUS_PEAK_SENSITIVITY_MIN, C.FOCUS_PEAK_SENSITIVITY_MAX
        )
        self.spin_focus_peak_sensitivity.setValue(C.DEFAULT_FOCUS_PEAK_SENSITIVITY)
        self.spin_focus_peak_sensitivity.setSuffix(" / 100")
        self.spin_focus_peak_sensitivity.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_focus_peak_sensitivity.setMinimumWidth(130)
        self.spin_focus_peak_sensitivity.setMinimumHeight(28)
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
        self.spin_focus_peak_thickness.setSingleStep(C.FOCUS_PEAK_THICKNESS_STEP)
        self.spin_focus_peak_thickness.setSuffix(" px")
        self.spin_focus_peak_thickness.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_focus_peak_thickness.setMinimumWidth(110)
        self.spin_focus_peak_thickness.setMinimumHeight(28)
        self.combo_squint_mode = QComboBox()
        self.combo_squint_mode.addItem("ぼかしのみ", C.SQUINT_MODE_BLUR)
        self.combo_squint_mode.addItem("縮小 → 拡大", C.SQUINT_MODE_SCALE)
        self.combo_squint_mode.addItem("縮小 → 拡大 + ぼかし", C.SQUINT_MODE_SCALE_BLUR)
        self.spin_squint_scale = QSpinBox()
        self.spin_squint_scale.setRange(C.SQUINT_SCALE_PERCENT_MIN, C.SQUINT_SCALE_PERCENT_MAX)
        self.spin_squint_scale.setValue(C.DEFAULT_SQUINT_SCALE_PERCENT)
        self.spin_squint_scale.setSuffix(" %")
        self.spin_squint_scale.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_squint_scale.setMinimumWidth(110)
        self.spin_squint_scale.setMinimumHeight(28)
        self.spin_squint_blur = QDoubleSpinBox()
        self.spin_squint_blur.setRange(C.SQUINT_BLUR_SIGMA_MIN, C.SQUINT_BLUR_SIGMA_MAX)
        self.spin_squint_blur.setValue(C.DEFAULT_SQUINT_BLUR_SIGMA)
        self.spin_squint_blur.setDecimals(1)
        self.spin_squint_blur.setSingleStep(C.SQUINT_BLUR_SIGMA_STEP)
        self.spin_squint_blur.setSuffix(" px")
        self.spin_squint_blur.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_squint_blur.setMinimumWidth(110)
        self.spin_squint_blur.setMinimumHeight(28)
        self.chk_vectorscope_skin_line = QCheckBox("スキントーンラインを表示")
        self.chk_vectorscope_skin_line.setChecked(C.DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE)
        self.spin_vectorscope_warn_threshold = QSpinBox()
        self.spin_vectorscope_warn_threshold.setRange(
            C.VECTORSCOPE_WARN_THRESHOLD_MIN,
            C.VECTORSCOPE_WARN_THRESHOLD_MAX,
        )
        self.spin_vectorscope_warn_threshold.setValue(C.DEFAULT_VECTORSCOPE_WARN_THRESHOLD)
        self.spin_vectorscope_warn_threshold.setSuffix(" %")
        self.spin_vectorscope_warn_threshold.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_vectorscope_warn_threshold.setMinimumWidth(110)
        self.spin_vectorscope_warn_threshold.setMinimumHeight(28)

        self.chk_preview_window = QCheckBox("領域プレビュー")
        self.chk_preview_window.setChecked(C.DEFAULT_PREVIEW_WINDOW)

        self.edit_preset_name = QLineEdit()
        self.edit_preset_name.setPlaceholderText("プリセット名")
        self.combo_layout_presets = QComboBox()
        self.btn_save_preset = QPushButton("プリセット保存")
        self.btn_load_preset = QPushButton("適用")
        self.btn_delete_preset = QPushButton("削除")
        self._row_target_settings = None
        self._row_analysis_max_dim_settings = None
        self._row_interval_settings = None
        self._row_diff_settings = None
        self._hint_diff_settings = None
        self._row_stable_settings = None
        self._hint_stable_settings = None
        self._row_squint_scale_settings = None
        self._row_squint_blur_settings = None

        self.lbl_status = QLabel("準備完了")
        self.lbl_status.setStyleSheet("color:#BBBBBB;")

        self.btn_refresh.clicked.connect(self.refresh_windows)
        self.combo_win.currentIndexChanged.connect(self.on_window_changed)
        self.btn_pick_roi_win.clicked.connect(self.pick_roi_in_window)
        self.btn_pick_roi_screen.clicked.connect(self.pick_roi_on_screen)
        self.combo_capture_source.currentIndexChanged.connect(self.apply_capture_source)
        self.spin_interval.valueChanged.connect(lambda v: self.worker.set_interval(float(v)))
        self.spin_points.valueChanged.connect(self.apply_sample_points_settings)
        self.combo_analysis_resolution_mode.currentIndexChanged.connect(
            self.apply_analysis_resolution_settings
        )
        self.edit_analysis_max_dim.editingFinished.connect(self.apply_analysis_resolution_settings)
        self.combo_scatter_shape.currentIndexChanged.connect(self.apply_scatter_settings)
        self.combo_wheel_mode.currentIndexChanged.connect(self.apply_wheel_settings)
        self.spin_wheel_sat_threshold.valueChanged.connect(self.apply_wheel_settings)
        self.combo_mode.currentIndexChanged.connect(lambda _: self.apply_mode_settings())
        self.spin_diff.valueChanged.connect(lambda _: self.apply_mode_settings())
        self.spin_stable.valueChanged.connect(lambda _: self.apply_mode_settings())
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

        # --- Menu bar (ウィンドウ / 設定 / レイアウト) ---
        mb = self.menuBar() if hasattr(self, "menuBar") else QMenuBar(self)
        win_menu = mb.addMenu("ウィンドウ")
        self.act_color = win_menu.addAction("色相リング")
        self.act_color.setCheckable(True)
        self.act_color.setChecked(True)
        self.act_color.toggled.connect(lambda v: self.toggle_dock(self.dock_color, v))
        self.act_hist = win_menu.addAction("H/S/V ヒストグラム")
        self.act_hist.setCheckable(True)
        self.act_hist.setChecked(True)
        self.act_hist.toggled.connect(lambda v: self.toggle_dock(self.dock_hist, v))
        self.act_scatter = win_menu.addAction("S-V 散布図")
        self.act_scatter.setCheckable(True)
        self.act_scatter.setChecked(True)
        self.act_scatter.toggled.connect(lambda v: self.toggle_dock(self.dock_scatter, v))
        self.act_vectorscope = win_menu.addAction("ベクトルスコープ")
        self.act_vectorscope.setCheckable(True)
        self.act_vectorscope.setChecked(True)
        self.act_vectorscope.toggled.connect(lambda v: self.toggle_dock(self.dock_vectorscope, v))
        self.act_edge = win_menu.addAction("エッジ検出")
        self.act_edge.setCheckable(True)
        self.act_edge.setChecked(True)
        self.act_edge.toggled.connect(lambda v: self.toggle_dock(self.dock_edge, v))
        self.act_binary = win_menu.addAction("2値化")
        self.act_binary.setCheckable(True)
        self.act_binary.setChecked(True)
        self.act_binary.toggled.connect(lambda v: self.toggle_dock(self.dock_binary, v))
        self.act_ternary = win_menu.addAction("3値化")
        self.act_ternary.setCheckable(True)
        self.act_ternary.setChecked(True)
        self.act_ternary.toggled.connect(lambda v: self.toggle_dock(self.dock_ternary, v))
        self.act_gray = win_menu.addAction("グレースケール")
        self.act_gray.setCheckable(True)
        self.act_gray.setChecked(True)
        self.act_gray.toggled.connect(lambda v: self.toggle_dock(self.dock_gray, v))
        self.act_focus = win_menu.addAction("フォーカスピーキング")
        self.act_focus.setCheckable(True)
        self.act_focus.setChecked(True)
        self.act_focus.toggled.connect(lambda v: self.toggle_dock(self.dock_focus, v))
        self.act_squint = win_menu.addAction("スクイント表示")
        self.act_squint.setCheckable(True)
        self.act_squint.setChecked(True)
        self.act_squint.toggled.connect(lambda v: self.toggle_dock(self.dock_squint, v))
        self.act_saliency = win_menu.addAction("サリエンシーマップ")
        self.act_saliency.setCheckable(True)
        self.act_saliency.setChecked(True)
        self.act_saliency.toggled.connect(lambda v: self.toggle_dock(self.dock_saliency, v))

        menu = mb.addMenu("設定")
        self.act_always_on_top = menu.addAction("常に最前面に表示")
        self.act_always_on_top.setCheckable(True)
        self.act_always_on_top.setChecked(C.DEFAULT_ALWAYS_ON_TOP)
        self.act_always_on_top.toggled.connect(self.apply_always_on_top)
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

        self.preview_window = PreviewWindow()
        self.preview_window.closed.connect(self.on_preview_closed)
        # 解析ビュー用ドック群を構築。
        setup_view_docks(self)
        self.top_colors_bar.installEventFilter(self)
        self.chk_scatter_hue_filter.toggled.connect(self.apply_scatter_settings)
        self.slider_scatter_hue_center.valueChanged.connect(self.apply_scatter_settings)
        self._sync_scatter_filter_controls()
        for d in self._dock_map.values():
            d.visibilityChanged.connect(lambda _v, self=self: self._sync_worker_view_flags())
            d.topLevelChanged.connect(lambda _v, dock=d, self=self: self._sync_dock_on_top(dock))
        self._sync_worker_view_flags()

        # --- Styling (theme) ---
        self._apply_ui_style()

        # --- Init ---
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
        self._fit_window_to_desktop()
        self.sync_window_menu_checks()
        self.update_placeholder()
        self._layout_autosave_enabled = True
        self._schedule_layout_autosave()
        self._schedule_dock_rebalance()

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
        if event.type() in (QEvent.LayoutRequest, QEvent.WindowStateChange):
            self._schedule_layout_autosave()
            self._schedule_window_fit()
        return super().event(event)

    def eventFilter(self, obj, event):
        if obj is getattr(self, "top_colors_bar", None) and event.type() == QEvent.Resize:
            self._refresh_top_color_bar()
        return super().eventFilter(obj, event)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_layout_autosave()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_layout_autosave()
        self._schedule_window_fit()

    def _fit_window_to_desktop(self):
        mw_windowing.fit_window_to_desktop(self)

    def _schedule_window_fit(self):
        mw_windowing.schedule_window_fit(self)

    def _schedule_dock_rebalance(self):
        mw_windowing.schedule_dock_rebalance(self)

    def _rebalance_dock_layout(self):
        mw_windowing.rebalance_dock_layout(self)

    def _is_always_on_top_enabled(self) -> bool:
        return mw_windowing.is_always_on_top_enabled(self)

    def _sync_dock_on_top(self, dock: QDockWidget):
        mw_windowing.sync_dock_on_top(self, dock)

    def apply_always_on_top(self, checked: bool, save: bool = True):
        mw_windowing.apply_always_on_top(self, checked, save=save)

    def _present_settings_window(self, center_on_parent: bool = False):
        mw_windowing.present_settings_window(self, center_on_parent=center_on_parent)

    def _refresh_top_color_bar(self):
        mw_results.refresh_top_color_bar(self)

    def on_status(self, s: str):
        mw_runtime.on_status(self, s)

    def _cancel_image_analysis(self):
        mw_runtime.cancel_image_analysis(self)

    def on_load_image(self):
        mw_runtime.on_load_image(self)

    def on_image_analysis_progress(self, percent: int, text: str):
        mw_runtime.on_image_analysis_progress(self, percent, text)

    def on_image_analysis_finished(self, res: dict):
        mw_runtime.on_image_analysis_finished(self, res)

    def on_image_analysis_failed(self, message: str):
        mw_runtime.on_image_analysis_failed(self, message)

    def on_image_analysis_canceled(self):
        mw_runtime.on_image_analysis_canceled(self)

    def on_start(self):
        mw_runtime.on_start(self)

    def on_stop(self):
        mw_runtime.on_stop(self)

    def closeEvent(self, event):
        mw_runtime.close_event(self, event)

    def refresh_windows(self):
        mw_runtime.refresh_windows(self)

    def _selected_capture_source(self) -> str:
        return mw_runtime.selected_capture_source(self)

    def _sync_capture_source_ui(self):
        mw_runtime.sync_capture_source_ui(self)

    def apply_capture_source(self, *_):
        mw_runtime.apply_capture_source(self)

    def _apply_capture_source(self, save: bool):
        mw_runtime._apply_capture_source(self, save=save)

    def on_window_changed(self, idx: int):
        mw_runtime.on_window_changed(self, idx)

    def _selected_wheel_sat_threshold(self) -> int:
        return mw_settings.selected_wheel_sat_threshold(self)

    def _apply_ui_style(self):
        mw_windowing.apply_ui_style(self)

    def _sync_mode_dependent_rows(self):
        mw_settings.sync_mode_dependent_rows(self)

    def _sync_squint_mode_rows(self):
        mw_settings.sync_squint_mode_rows(self)

    def _sync_analysis_resolution_rows(self):
        mw_settings.sync_analysis_resolution_rows(self)

    def _sync_worker_view_flags(self):
        mw_runtime.sync_worker_view_flags(self)

    def apply_sample_points_settings(self, *_):
        mw_settings.apply_sample_points_settings(self)

    def _sync_scatter_filter_controls(self):
        mw_settings.sync_scatter_filter_controls(self)

    def apply_scatter_settings(self, *_):
        mw_settings.apply_scatter_settings(self)

    def apply_analysis_resolution_settings(self, *_args, save: bool = True):
        mw_settings.apply_analysis_resolution_settings(self, save=save)

    def apply_wheel_settings(self, *_):
        mw_settings.apply_wheel_settings(self)

    def _selected_composition_guide(self) -> str:
        return mw_settings.selected_composition_guide(self)

    def apply_edge_settings(self, *_):
        mw_settings.apply_edge_settings(self)

    def apply_binary_settings(self, *_):
        mw_settings.apply_binary_settings(self)

    def apply_ternary_settings(self, *_):
        mw_settings.apply_ternary_settings(self)

    def apply_saliency_settings(self, *_):
        mw_settings.apply_saliency_settings(self)

    def apply_composition_guide_settings(self, *_):
        mw_settings.apply_composition_guide_settings(self)

    def apply_focus_peaking_settings(self, *_):
        mw_settings.apply_focus_peaking_settings(self)

    def apply_squint_settings(self, *_):
        mw_settings.apply_squint_settings(self)

    def _update_vectorscope_warning_label(self):
        mw_settings.update_vectorscope_warning_label(self)

    def apply_vectorscope_settings(self, *_):
        mw_settings.apply_vectorscope_settings(self)

    def _update_preview_snapshot(self):
        mw_runtime.update_preview_snapshot(self)

    def on_preview_toggled(self, checked: bool):
        mw_runtime.on_preview_toggled(self, checked)

    def on_preview_closed(self):
        mw_runtime.on_preview_closed(self)

    def apply_mode_settings(self, save: bool = True):
        mw_settings.apply_mode_settings(self, save=save)

    def load_settings(self):
        mw_settings.load_settings(self)

    def save_settings(self, silent: bool = True):
        mw_settings.save_settings(self, silent=silent)

    def sync_window_menu_checks(self, *_):
        mw_windowing.sync_window_menu_checks(self)

    def _apply_default_view_layout(self):
        apply_default_view_layout_ops(self)

    def save_current_layout_to_config(self, silent: bool = False):
        save_current_layout_to_config_ops(self, silent=silent)

    def _schedule_layout_autosave(self):
        schedule_layout_autosave_ops(self)

    def apply_layout_from_config(self, cfg: dict):
        apply_layout_from_config_ops(self, cfg)

    def refresh_layout_preset_views(self):
        refresh_layout_preset_views_ops(self)

    def apply_layout_preset(self, name: str):
        apply_layout_preset_ops(self, name)

    def load_selected_layout_preset(self):
        load_selected_layout_preset_ops(self)

    def save_layout_preset(self):
        save_layout_preset_ops(self)

    def delete_selected_layout_preset(self):
        delete_selected_layout_preset_ops(self)

    def toggle_dock(self, dock: QDockWidget, visible: bool):
        mw_windowing.toggle_dock(self, dock, visible)

    def update_placeholder(self):
        mw_windowing.update_placeholder(self)

    def show_settings_window(self, page_index: int = 0):
        show_settings_dialog_window(self, page_index=page_index)

    def hide_settings_window(self):
        hide_settings_dialog_window(self)

    def _close_roi_selectors(self):
        mw_roi.close_roi_selectors(self)

    def pick_roi_on_screen(self):
        mw_roi.pick_roi_on_screen(self)

    def on_roi_screen_selected(self, r: QRect):
        mw_roi.on_roi_screen_selected(self, r)

    def pick_roi_in_window(self):
        mw_roi.pick_roi_in_window(self)

    def on_roi_window_selected(self, hwnd: int, wrect: QRect, roi_abs_logical: QRect):
        mw_roi.on_roi_window_selected(self, hwnd, wrect, roi_abs_logical)

    def on_result(self, res: dict):
        mw_results.on_result(self, res)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
