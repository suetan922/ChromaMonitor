import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QRect, Qt, QThread, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .analyzer import HAS_WIN32, AnalyzerWorker, ImageFileAnalyzeWorker, list_windows
from .util import constants as C
from .util.config import load_config, save_config
from .util.functions import (
    blocked_signals,
    clamp_float,
    clamp_int,
    render_top_color_bar,
    safe_choice,
    screen_union_geometry,
    set_checked_blocked,
    set_combobox_data_blocked,
    set_current_index_blocked,
    set_value_blocked,
    top_hue_bars,
)
from .util.layout_state import apply_layout_state, capture_layout_state
from .widgets import (
    BinaryView,
    ChannelHistogram,
    ColorWheelWidget,
    EdgeView,
    FocusPeakingView,
    GrayscaleView,
    PreviewWindow,
    RoiSelector,
    SaliencyView,
    ScatterRasterWidget,
    SquintView,
    TernaryView,
    VectorScopeView,
)


def _make_labeled_row(label_text: str, widget: QWidget) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QLabel(label_text))
    layout.addWidget(widget, 1)
    return row


SETTINGS_PAGE_CAPTURE = 0
SETTINGS_PAGE_UPDATE = 1
SETTINGS_PAGE_SCATTER = 2
SETTINGS_PAGE_WHEEL = 3
SETTINGS_PAGE_IMAGE = 4
SETTINGS_PAGE_SALIENCY = 5
SETTINGS_PAGE_FOCUS = 6
SETTINGS_PAGE_SQUINT = 7
SETTINGS_PAGE_VECTORSCOPE = 8
SETTINGS_PAGE_LAYOUT = 9


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

        self._roi_selector = None
        self._roi_selectors = []

        self.worker = AnalyzerWorker()
        self.worker.resultReady.connect(self.on_result)
        self.worker.status.connect(self.on_status)
        self._image_thread = None
        self._image_worker = None
        self._image_progress = None

        # Controls
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
        self.spin_scatter_alpha = QDoubleSpinBox()
        self.spin_scatter_alpha.setRange(C.SCATTER_POINT_ALPHA_MIN, C.SCATTER_POINT_ALPHA_MAX)
        self.spin_scatter_alpha.setSingleStep(C.SCATTER_POINT_ALPHA_STEP)
        self.spin_scatter_alpha.setDecimals(2)
        self.spin_scatter_alpha.setValue(C.DEFAULT_SCATTER_POINT_ALPHA)
        self.spin_scatter_alpha.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_scatter_alpha.setMinimumWidth(110)
        self.spin_scatter_alpha.setMinimumHeight(28)
        self.spin_analysis_max_dim = QSpinBox()
        self.spin_analysis_max_dim.setRange(C.ANALYZER_MAX_DIM_MIN, C.ANALYZER_MAX_DIM_MAX)
        self.spin_analysis_max_dim.setSingleStep(C.ANALYZER_MAX_DIM_STEP)
        self.spin_analysis_max_dim.setValue(C.ANALYZER_MAX_DIM)
        self.spin_analysis_max_dim.setSuffix(" px")
        self.spin_analysis_max_dim.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin_analysis_max_dim.setMinimumWidth(110)
        self.spin_analysis_max_dim.setMinimumHeight(28)

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
        self.combo_binary_preset.addItem("自動（おすすめ）", C.BINARY_PRESET_AUTO)
        self.combo_binary_preset.addItem("白を増やす", C.BINARY_PRESET_MORE_WHITE)
        self.combo_binary_preset.addItem("黒を増やす", C.BINARY_PRESET_MORE_BLACK)
        self.combo_ternary_preset = QComboBox()
        self.combo_ternary_preset.addItem("標準（おすすめ）", C.TERNARY_PRESET_STANDARD)
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
        self._row_interval_settings = None
        self._row_diff_settings = None
        self._row_stable_settings = None
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
        self.spin_analysis_max_dim.valueChanged.connect(self.apply_analysis_resolution_settings)
        self.combo_scatter_shape.currentIndexChanged.connect(self.apply_scatter_settings)
        self.spin_scatter_alpha.valueChanged.connect(self.apply_scatter_settings)
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

        # Menu bar (ウィンドウ / 設定)
        mb = self.menuBar() if hasattr(self, "menuBar") else QMenuBar(self)
        win_menu = mb.addMenu("ウィンドウ")
        self.act_color = win_menu.addAction("カラーサークル")
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
        self.act_gray = win_menu.addAction("グレースケール")
        self.act_gray.setCheckable(True)
        self.act_gray.setChecked(True)
        self.act_gray.toggled.connect(lambda v: self.toggle_dock(self.dock_gray, v))
        self.act_edge = win_menu.addAction("エッジ検出")
        self.act_edge.setCheckable(True)
        self.act_edge.setChecked(True)
        self.act_edge.toggled.connect(lambda v: self.toggle_dock(self.dock_edge, v))
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
        self.act_binary = win_menu.addAction("2値化")
        self.act_binary.setCheckable(True)
        self.act_binary.setChecked(True)
        self.act_binary.toggled.connect(lambda v: self.toggle_dock(self.dock_binary, v))
        self.act_ternary = win_menu.addAction("3値化")
        self.act_ternary.setCheckable(True)
        self.act_ternary.setChecked(True)
        self.act_ternary.toggled.connect(lambda v: self.toggle_dock(self.dock_ternary, v))

        menu = mb.addMenu("設定")
        self.settings_action = menu.addAction("設定ウィンドウを開く")
        self.settings_action.triggered.connect(
            lambda: self.show_settings_window(SETTINGS_PAGE_CAPTURE)
        )

        layout_menu = mb.addMenu("レイアウト")
        self.presets_menu = layout_menu.addMenu("プリセットを適用")
        self.act_open_layout_settings = layout_menu.addAction("レイアウト設定を開く")
        self.act_open_layout_settings.triggered.connect(
            lambda: self.show_settings_window(SETTINGS_PAGE_LAYOUT)
        )

        # Toolbar for Start/Stop
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

        # Displays
        self.wheel = ColorWheelWidget()
        self.wheel.setStyleSheet("background:#FFFFFF; border:1px solid #CCC;")

        self.scatter = ScatterRasterWidget()

        # バケット幅を揃えて視覚的スケールを統一
        self.hist_h = ChannelHistogram("色相", 180, 179, C.H_COLOR, bucket=2)
        self.hist_s = ChannelHistogram("彩度", 256, 255, C.S_COLOR, bucket=2)
        self.hist_v = ChannelHistogram("明度", 256, 255, C.V_COLOR, bucket=2)

        self.preview_window = PreviewWindow()
        self.preview_window.closed.connect(self.on_preview_closed)

        self._last_top_bars = []
        self.lbl_top5_title = QLabel(C.TOP_COLORS_TITLE)
        self.lbl_top5_title.setStyleSheet("color:#111; font-size:12px; font-weight:600;")

        self.top_colors_bar = QLabel()
        self.top_colors_bar.setFixedHeight(C.TOP_COLOR_BAR_HEIGHT)
        self.top_colors_bar.setMinimumWidth(0)
        self.top_colors_bar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.top_colors_bar.setScaledContents(True)

        self.lbl_warmcool = QLabel("暖色: -   寒色: -   その他: -")
        self.lbl_warmcool.setStyleSheet("color:#111; font-size:12px;")
        self.lbl_warmcool.setWordWrap(True)
        self.lbl_warmcool.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        # ドックのネスティングを有効化（3段以上に自由配置できるように）
        self.setDockNestingEnabled(True)

        # View docks
        color_widget = QWidget()
        cw_l = QVBoxLayout(color_widget)
        cw_l.setContentsMargins(6, 6, 6, 6)
        cw_l.setSpacing(6)
        cw_l.addWidget(self.wheel, 1)
        cw_l.addWidget(self.lbl_top5_title)
        cw_l.addWidget(self.top_colors_bar)
        cw_l.addWidget(self.lbl_warmcool)
        color_dock = self._create_dock("カラーサークル", "dock_color", color_widget)

        scatter_container = self._build_single_view_container(self.scatter)
        scatter_dock = self._create_dock("S-V 散布図", "dock_scatter", scatter_container)

        hist_container = QWidget()
        hg_l = QHBoxLayout(hist_container)
        hg_l.setContentsMargins(8, 8, 8, 8)
        hg_l.setSpacing(10)
        hg_l.addWidget(self.hist_h)
        hg_l.addWidget(self.hist_s)
        hg_l.addWidget(self.hist_v)
        hist_dock = self._create_dock(
            "H/S/V ヒストグラム",
            "dock_hist",
            hist_container,
            area=Qt.BottomDockWidgetArea,
        )

        self.edge_view = EdgeView()
        edge_container = self._build_single_view_container(self.edge_view)
        edge_dock = self._create_dock("エッジ検出", "dock_edge", edge_container)

        self.gray_view = GrayscaleView()
        gray_container = self._build_single_view_container(self.gray_view)
        gray_dock = self._create_dock("グレースケール", "dock_gray", gray_container)

        self.binary_view = BinaryView()
        binary_container = self._build_single_view_container(self.binary_view)
        binary_dock = self._create_dock("2値化", "dock_binary", binary_container)

        self.ternary_view = TernaryView()
        ternary_container = self._build_single_view_container(self.ternary_view)
        ternary_dock = self._create_dock("3値化", "dock_ternary", ternary_container)

        self.saliency_view = SaliencyView()
        saliency_container = self._build_single_view_container(self.saliency_view)
        saliency_dock = self._create_dock("サリエンシーマップ", "dock_saliency", saliency_container)

        self.focus_peaking_view = FocusPeakingView()
        focus_container = self._build_single_view_container(self.focus_peaking_view)
        focus_dock = self._create_dock("フォーカスピーキング", "dock_focus", focus_container)

        self.squint_view = SquintView()
        squint_container = self._build_single_view_container(self.squint_view)
        squint_dock = self._create_dock("スクイント表示", "dock_squint", squint_container)

        self.vectorscope_view = VectorScopeView()
        vectorscope_container = QWidget()
        vs_l = QVBoxLayout(vectorscope_container)
        vs_l.setContentsMargins(6, 6, 6, 6)
        vs_l.setSpacing(6)
        vs_l.addWidget(self.vectorscope_view, 1)
        self.lbl_vectorscope_warning = QLabel("高彩度警告: 入力待ち")
        self.lbl_vectorscope_warning.setStyleSheet("color:#8b97a8;")
        vs_l.addWidget(self.lbl_vectorscope_warning, 0)
        vectorscope_dock = self._create_dock("ベクトルスコープ", "dock_vectorscope", vectorscope_container)

        self.setDockOptions(QMainWindow.AllowTabbedDocks | QMainWindow.AllowNestedDocks)

        # Central placeholder
        self.placeholder = QLabel("🖼️ ウィンドウメニューから表示したいビューを選択してください")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("color:#555; font-size:14px;")

        central = QWidget()
        central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        c_l = QVBoxLayout(central)
        c_l.setContentsMargins(0, 0, 0, 0)
        c_l.addWidget(self.placeholder, 1)
        self.setCentralWidget(central)
        self.central_container = central

        # Keep references for toggling
        self.dock_color = color_dock
        self.dock_scatter = scatter_dock
        self.dock_hist = hist_dock
        self.dock_edge = edge_dock
        self.dock_gray = gray_dock
        self.dock_binary = binary_dock
        self.dock_ternary = ternary_dock
        self.dock_saliency = saliency_dock
        self.dock_focus = focus_dock
        self.dock_squint = squint_dock
        self.dock_vectorscope = vectorscope_dock
        self._right_stack_order = [
            self.dock_scatter,
            self.dock_edge,
            self.dock_gray,
            self.dock_binary,
            self.dock_ternary,
            self.dock_saliency,
            self.dock_focus,
            self.dock_squint,
            self.dock_vectorscope,
        ]
        self._dock_map = {
            "dock_color": self.dock_color,
            "dock_scatter": self.dock_scatter,
            "dock_hist": self.dock_hist,
            "dock_edge": self.dock_edge,
            "dock_gray": self.dock_gray,
            "dock_binary": self.dock_binary,
            "dock_ternary": self.dock_ternary,
            "dock_saliency": self.dock_saliency,
            "dock_focus": self.dock_focus,
            "dock_squint": self.dock_squint,
            "dock_vectorscope": self.dock_vectorscope,
        }
        self._dock_actions = {
            "dock_color": self.act_color,
            "dock_scatter": self.act_scatter,
            "dock_hist": self.act_hist,
            "dock_edge": self.act_edge,
            "dock_gray": self.act_gray,
            "dock_binary": self.act_binary,
            "dock_ternary": self.act_ternary,
            "dock_saliency": self.act_saliency,
            "dock_focus": self.act_focus,
            "dock_squint": self.act_squint,
            "dock_vectorscope": self.act_vectorscope,
        }

        for d in (
            color_dock,
            scatter_dock,
            hist_dock,
            edge_dock,
            gray_dock,
            binary_dock,
            ternary_dock,
            saliency_dock,
            focus_dock,
            squint_dock,
            vectorscope_dock,
        ):
            d.setFeatures(
                QDockWidget.DockWidgetMovable
                | QDockWidget.DockWidgetFloatable
                | QDockWidget.DockWidgetClosable
            )
            d.setWindowFlag(Qt.WindowCloseButtonHint, True)
            d.setWindowFlag(Qt.WindowSystemMenuHint, True)
            d.setAllowedAreas(Qt.AllDockWidgetAreas)
            d.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)
            d.visibilityChanged.connect(self.update_placeholder)
            d.visibilityChanged.connect(self.sync_window_menu_checks)
            d.visibilityChanged.connect(lambda _v, self=self: self._schedule_layout_autosave())
            d.visibilityChanged.connect(lambda _v, self=self: self._schedule_window_fit())
            d.visibilityChanged.connect(lambda _v, self=self: self._schedule_dock_rebalance())
            d.topLevelChanged.connect(lambda _v, self=self: self._schedule_layout_autosave())
            d.topLevelChanged.connect(lambda _v, self=self: self._schedule_window_fit())
            d.topLevelChanged.connect(lambda _v, self=self: self._schedule_dock_rebalance())
            d.dockLocationChanged.connect(lambda _a, self=self: self._schedule_layout_autosave())
            d.dockLocationChanged.connect(lambda _a, self=self: self._schedule_window_fit())
            d.dockLocationChanged.connect(lambda _a, self=self: self._schedule_dock_rebalance())

        # 初期配置: 左にカラー、右側にビュー群、下にヒストグラム
        # ユーザーが自由に3段以上へ再配置できるよう、tabifyは行わない
        self.addDockWidget(Qt.LeftDockWidgetArea, color_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, scatter_dock)
        self.splitDockWidget(scatter_dock, edge_dock, Qt.Vertical)
        self.splitDockWidget(edge_dock, gray_dock, Qt.Vertical)
        self.splitDockWidget(gray_dock, binary_dock, Qt.Vertical)
        self.splitDockWidget(binary_dock, ternary_dock, Qt.Vertical)
        self.splitDockWidget(ternary_dock, saliency_dock, Qt.Vertical)
        self.splitDockWidget(saliency_dock, focus_dock, Qt.Vertical)
        self.splitDockWidget(focus_dock, squint_dock, Qt.Vertical)
        self.splitDockWidget(squint_dock, vectorscope_dock, Qt.Vertical)
        self.addDockWidget(Qt.BottomDockWidgetArea, hist_dock)
        self.resizeDocks([color_dock, scatter_dock, edge_dock], [700, 700, 700], Qt.Horizontal)
        self.resizeDocks(
            [
                scatter_dock,
                edge_dock,
                gray_dock,
                binary_dock,
                ternary_dock,
                saliency_dock,
                focus_dock,
                squint_dock,
                vectorscope_dock,
            ],
            [280, 200, 180, 170, 160, 180, 170, 170, 170],
            Qt.Vertical,
        )

        # Styling (theme)
        self._apply_ui_style()

        # Init
        self.worker.set_interval(self.spin_interval.value())
        self.worker.set_sample_points(self.spin_points.value())
        self.worker.set_max_dim(self.spin_analysis_max_dim.value())
        self.worker.set_wheel_sat_threshold(self.spin_wheel_sat_threshold.value())
        self.worker.set_graph_every(C.DEFAULT_GRAPH_EVERY)
        self.refresh_windows()
        self.load_settings()
        self._fit_window_to_desktop()
        self.sync_window_menu_checks()
        self.update_placeholder()
        self._layout_autosave_enabled = True
        self._schedule_layout_autosave()
        self._schedule_dock_rebalance()

    def _build_single_view_container(self, view: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(view, 1)
        return container

    def _create_dock(
        self,
        title: str,
        object_name: str,
        content: QWidget,
        area: Qt.DockWidgetArea = Qt.RightDockWidgetArea,
    ) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(object_name)
        dock.setWidget(content)
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.addDockWidget(area, dock)
        return dock

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

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_layout_autosave()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_layout_autosave()
        self._schedule_window_fit()

    def _desktop_available_geometry(self) -> QRect:
        return screen_union_geometry(available=True)

    def _fit_window_to_desktop(self):
        if self.isMaximized() or self.isFullScreen():
            return
        avail = self._desktop_available_geometry()
        if avail.width() <= 0 or avail.height() <= 0:
            return

        # 手動スナップ/半分配置時の「勝手に内側へズレる」挙動を避けるため余白を持たせない
        margin = 0
        max_w = max(640, avail.width() - margin * 2)
        max_h = max(420, avail.height() - margin * 2)

        frame = self.frameGeometry()
        target_w = min(max(480, frame.width()), max_w)
        target_h = min(max(360, frame.height()), max_h)
        if target_w != frame.width() or target_h != frame.height():
            self.resize(target_w, target_h)
            frame = self.frameGeometry()

        min_x = avail.left() + margin
        min_y = avail.top() + margin
        max_x = avail.right() - margin - frame.width() + 1
        max_y = avail.bottom() - margin - frame.height() + 1
        if max_x < min_x:
            max_x = min_x
        if max_y < min_y:
            max_y = min_y

        target_x = min(max(frame.x(), min_x), max_x)
        target_y = min(max(frame.y(), min_y), max_y)
        if target_x != frame.x() or target_y != frame.y():
            self.move(target_x, target_y)

    def _schedule_window_fit(self):
        if self.isMinimized() or self.isMaximized() or self.isFullScreen():
            return
        self._fit_window_timer.start()

    def _schedule_dock_rebalance(self):
        if self.isMinimized() or self.isMaximized() or self.isFullScreen():
            return
        self._dock_rebalance_timer.start()

    def _rebalance_dock_layout(self):
        # ドックの表示/非表示直後に分割比が壊れる場合があるため、
        # 右カラムの可視ドックへ安全なサイズを再適用してリサイズ可能状態を維持する。
        if not hasattr(self, "_right_stack_order"):
            return
        docks = [
            d
            for d in self._right_stack_order
            if d.isVisible()
            and not d.isFloating()
            and self.dockWidgetArea(d) == Qt.RightDockWidgetArea
        ]
        if len(docks) < 2:
            return
        sizes = [max(C.VIEW_MIN_SIZE, int(d.size().height())) for d in docks]
        if sum(sizes) <= 0:
            sizes = [1] * len(docks)
        self.resizeDocks(docks, sizes, Qt.Vertical)

    def _fit_dialog_to_desktop(self, dialog: QDialog, center_on_parent: bool = False):
        avail = self._desktop_available_geometry()
        if avail.width() <= 0 or avail.height() <= 0:
            return

        margin = 8
        max_w = max(420, avail.width() - margin * 2)
        max_h = max(320, avail.height() - margin * 2)
        target_w = min(max(420, dialog.width()), max_w)
        target_h = min(max(320, dialog.height()), max_h)
        if target_w != dialog.width() or target_h != dialog.height():
            dialog.resize(target_w, target_h)

        frame = dialog.frameGeometry()
        use_center = center_on_parent or not avail.intersects(frame)
        if use_center:
            base = self.frameGeometry().center() if self.isVisible() else avail.center()
            target_x = base.x() - frame.width() // 2
            target_y = base.y() - frame.height() // 2
        else:
            target_x = frame.x()
            target_y = frame.y()

        min_x = avail.left() + margin
        min_y = avail.top() + margin
        max_x = avail.right() - margin - frame.width() + 1
        max_y = avail.bottom() - margin - frame.height() + 1
        if max_x < min_x:
            max_x = min_x
        if max_y < min_y:
            max_y = min_y

        target_x = min(max(target_x, min_x), max_x)
        target_y = min(max(target_y, min_y), max_y)
        dialog.move(target_x, target_y)

    def _fit_top_level_widget_to_desktop(self, widget: QWidget):
        avail = self._desktop_available_geometry()
        if avail.width() <= 0 or avail.height() <= 0:
            return
        if widget.windowState() & Qt.WindowMinimized:
            return

        margin = 0
        max_w = max(240, avail.width() - margin * 2)
        max_h = max(180, avail.height() - margin * 2)

        frame = widget.frameGeometry()
        target_w = min(max(160, frame.width()), max_w)
        target_h = min(max(120, frame.height()), max_h)
        if target_w != frame.width() or target_h != frame.height():
            widget.resize(target_w, target_h)
            frame = widget.frameGeometry()

        min_x = avail.left() + margin
        min_y = avail.top() + margin
        max_x = avail.right() - margin - frame.width() + 1
        max_y = avail.bottom() - margin - frame.height() + 1
        if max_x < min_x:
            max_x = min_x
        if max_y < min_y:
            max_y = min_y

        target_x = min(max(frame.x(), min_x), max_x)
        target_y = min(max(frame.y(), min_y), max_y)
        if target_x != frame.x() or target_y != frame.y():
            widget.move(target_x, target_y)

    def _present_settings_window(self, center_on_parent: bool = False):
        if not hasattr(self, "_settings_window"):
            return
        win = self._settings_window
        self._fit_dialog_to_desktop(win, center_on_parent=center_on_parent)
        if win.windowState() & Qt.WindowMinimized:
            win.setWindowState((win.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
            win.showNormal()
        win.show()
        win.raise_()
        win.activateWindow()

    def on_status(self, s: str):
        self.lbl_status.setText(s)
        if getattr(self, "_last_top_bars", None):
            self.top_colors_bar.setPixmap(
                render_top_color_bar(
                    self._last_top_bars,
                    width=self.top_colors_bar.width(),
                    height=self.top_colors_bar.height(),
                )
            )

    def _is_image_analysis_running(self) -> bool:
        return self._image_thread is not None and self._image_thread.isRunning()

    def _set_image_analysis_busy(self, busy: bool):
        self.btn_load_image_bar.setEnabled(not busy)

    def _cleanup_image_analysis(self):
        if self._image_progress is not None:
            try:
                self._image_progress.close()
            except Exception:
                pass
            self._image_progress = None
        if self._image_thread is not None:
            try:
                self._image_thread.quit()
                self._image_thread.wait(1500)
            except Exception:
                pass
        self._image_worker = None
        self._image_thread = None
        self._set_image_analysis_busy(False)

    def _cancel_image_analysis(self):
        if self._image_worker is not None:
            try:
                self._image_worker.request_cancel()
            except Exception:
                pass

    def on_load_image(self):
        if self._is_image_analysis_running():
            self.on_status("画像解析を実行中です。キャンセルしてから再実行してください。")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "画像を読み込む",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All Files (*)",
        )
        if not file_path:
            return

        self.worker.stop()
        self.btn_stop_bar.setChecked(True)
        self.btn_start_bar.setChecked(False)

        worker = ImageFileAnalyzeWorker(
            path=file_path,
            sample_points=int(self.spin_points.value()),
            wheel_sat_threshold=self._selected_wheel_sat_threshold(),
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.progress.connect(self.on_image_analysis_progress)
        worker.finished.connect(self.on_image_analysis_finished)
        worker.failed.connect(self.on_image_analysis_failed)
        worker.canceled.connect(self.on_image_analysis_canceled)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.canceled.connect(thread.quit)
        thread.started.connect(worker.run)
        self._image_worker = worker
        self._image_thread = thread

        dlg = QProgressDialog("画像を解析中…", "キャンセル", 0, 100, self)
        dlg.setWindowTitle("画像解析")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        dlg.canceled.connect(self._cancel_image_analysis)
        self._image_progress = dlg
        self._set_image_analysis_busy(True)

        self.on_status(f"画像解析を開始: {Path(file_path).name}")
        thread.start()
        dlg.show()

    def on_image_analysis_progress(self, percent: int, text: str):
        if self._image_progress is not None:
            self._image_progress.setLabelText(text)
            self._image_progress.setValue(max(0, min(100, int(percent))))

    def on_image_analysis_finished(self, res: dict):
        self._cleanup_image_analysis()
        self.on_result(res)
        self.on_status(f"画像解析完了 ({res.get('dt_ms', 0.0):.1f} ms)")

    def on_image_analysis_failed(self, message: str):
        self._cleanup_image_analysis()
        self.on_status(message)
        QMessageBox.warning(self, "画像解析", message)

    def on_image_analysis_canceled(self):
        self._cleanup_image_analysis()
        self.on_status("画像解析をキャンセルしました")

    def on_start(self):
        if self._is_image_analysis_running():
            self.on_status("画像解析中です。キャンセル完了後にStartしてください。")
            return
        self.worker.start()
        self.btn_start_bar.setChecked(True)
        self.btn_stop_bar.setChecked(False)

    def on_stop(self):
        if self._is_image_analysis_running():
            self._cancel_image_analysis()
            self.on_status("画像解析のキャンセルを要求しました")
            return
        self.worker.stop()
        self.btn_stop_bar.setChecked(True)
        self.btn_start_bar.setChecked(False)

    def closeEvent(self, event):
        # メイン終了時に補助ウィンドウも確実に閉じる
        self.save_current_layout_to_config(silent=True)
        self._cancel_image_analysis()
        self._cleanup_image_analysis()
        self.worker.stop()
        try:
            if self.preview_window.isVisible():
                self.preview_window.close()
        except Exception:
            pass
        try:
            if hasattr(self, "_settings_window") and self._settings_window is not None:
                self._settings_window.close()
        except Exception:
            pass
        try:
            self._close_roi_selectors()
        except Exception:
            pass
        super().closeEvent(event)

    def refresh_windows(self):
        wins = list_windows() if HAS_WIN32 else []
        with blocked_signals(self.combo_win):
            self.combo_win.clear()
            self.combo_win.addItem("（未選択）", None)
            for hwnd, title in wins[: C.WINDOW_LIST_MAX_ITEMS]:
                self.combo_win.addItem(title, hwnd)
        if not HAS_WIN32:
            self.on_status("この環境ではウィンドウ選択は使えません（画面の領域選択を使用）")
        else:
            self.on_status(f"ウィンドウ {len(wins)} 件")
        self._sync_capture_source_ui()

    def _selected_capture_source(self) -> str:
        source = self.combo_capture_source.currentData()
        return safe_choice(source, C.CAPTURE_SOURCES, C.DEFAULT_CAPTURE_SOURCE)

    def _sync_capture_source_ui(self):
        is_window = self._selected_capture_source() == C.CAPTURE_SOURCE_WINDOW
        if self._row_target_settings is not None:
            self._row_target_settings.setVisible(is_window)
        self.btn_refresh.setVisible(is_window)
        self.btn_pick_roi_win.setVisible(is_window)
        self.btn_pick_roi_screen.setVisible(not is_window)

        can_window = is_window and HAS_WIN32
        self.btn_refresh.setEnabled(can_window)
        self.combo_win.setEnabled(can_window)
        self.btn_pick_roi_win.setEnabled(can_window)
        self.btn_pick_roi_screen.setEnabled(not is_window)

    def apply_capture_source(self, *_):
        self._apply_capture_source(save=True)

    def _apply_capture_source(self, save: bool):
        source = self._selected_capture_source()
        if source == C.CAPTURE_SOURCE_WINDOW and not HAS_WIN32:
            idx = self.combo_capture_source.findData(C.CAPTURE_SOURCE_SCREEN)
            if idx >= 0:
                set_current_index_blocked(self.combo_capture_source, idx)
            source = C.CAPTURE_SOURCE_SCREEN
            self.on_status("この環境では画面範囲モードを使用します")

        if source == C.CAPTURE_SOURCE_WINDOW:
            self.worker.set_roi_on_screen(None)
            # ウィンドウ取得時の初期ROIはウィンドウ全体に戻す
            self.worker.set_roi_in_window(None)
            hwnd = self.combo_win.currentData()
            # 未選択なら先頭の実ウィンドウを初期選択
            if hwnd is None and self.combo_win.count() > 1:
                set_current_index_blocked(self.combo_win, 1)
                hwnd = self.combo_win.currentData()
            self.worker.set_target_window(int(hwnd) if hwnd is not None else None)
        else:
            self.worker.set_target_window(None)
            self.worker.set_roi_in_window(None)
            set_current_index_blocked(self.combo_win, 0)

        self._sync_capture_source_ui()
        if self.chk_preview_window.isChecked():
            self._update_preview_snapshot()
        if save:
            self.save_settings()

    def on_window_changed(self, idx: int):
        if self._selected_capture_source() != C.CAPTURE_SOURCE_WINDOW:
            return
        if not HAS_WIN32:
            return
        hwnd = self.combo_win.currentData()
        if hwnd is None:
            self.worker.set_target_window(None)
            self.worker.set_roi_in_window(None)
            self.on_status("ターゲット未選択（画面領域を使います）")
            return
        # ウィンドウターゲットを選んだら、画面領域モードを解除（排他的）
        self.worker.set_target_window(int(hwnd))
        self.worker.set_roi_on_screen(None)
        self.worker.set_roi_in_window(None)
        rect = self.worker._get_window_rect(int(hwnd))
        if rect is None:
            self.on_status("ターゲット設定: 取得失敗")
            return
        self.on_status(
            f"ターゲット設定: {self.combo_win.currentText()}  ({rect.width()}x{rect.height()}) / 次にウィンドウ内領域を選択してください"
        )
        if self.chk_preview_window.isChecked():
            self._update_preview_snapshot()

    def _selected_mode(self) -> str:
        mode = self.combo_mode.currentData()
        return safe_choice(mode, C.UPDATE_MODES, C.DEFAULT_MODE)

    def _selected_wheel_mode(self) -> str:
        mode = self.combo_wheel_mode.currentData()
        return safe_choice(mode, C.WHEEL_MODES, C.DEFAULT_WHEEL_MODE)

    def _selected_wheel_sat_threshold(self) -> int:
        return clamp_int(
            self.spin_wheel_sat_threshold.value(),
            C.WHEEL_SAT_THRESHOLD_MIN,
            C.WHEEL_SAT_THRESHOLD_MAX,
        )

    def _apply_ui_style(self):
        app_style = """
            QMainWindow { background:#f3f4f6; }
            QWidget#centralWidget { background:#f3f4f6; }
            QLabel { color:#111; }
            QPushButton { background:#f7f8fb; border:1px solid #cdd1d6; padding:6px 12px; border-radius:4px; color:#111; }
            QPushButton:hover { border:1px solid #b6bac0; background:#eef0f3; }
            QPushButton:pressed { background:#e4e6ea; }
            QDoubleSpinBox, QSpinBox, QComboBox { background:#ffffff; border:1px solid #cdd1d6; padding:4px 6px; color:#111; border-radius:4px; }
            QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin:border; width:20px; }
            QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin:border; width:20px; }
            QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { padding:0; margin:0; }
            QCheckBox { color:#111; spacing:6px; }
            QCheckBox::indicator { width:16px; height:16px; border-radius:3px; border:1px solid #c0c4ca; background:#ffffff; }
            QCheckBox::indicator:checked { background:#4a90e2; border:1px solid #3578c8; }
            QDockWidget::title { background:#f9fafc; padding:4px 8px; border:1px solid #dfe3e8; border-radius:4px; }
            QToolBar { spacing:8px; border:none; background:#f3f4f6; padding:4px 8px; }
            QPushButton#runStartBtn, QPushButton#runStopBtn {
                font-weight:600; padding:6px 12px; border-radius:8px; min-width:72px;
                border:1px solid #c7ced7; color:#111827; background:#ffffff;
            }
            QPushButton#runStartBtn:checked { background:#16a34a; border:1px solid #15803d; color:#ffffff; }
            QPushButton#runStopBtn:checked { background:#dc2626; border:1px solid #b91c1c; color:#ffffff; }
        """
        dock_style = """
            QWidget { background: #FAFBFD; color:#111; }
            QGroupBox { background: #FAFBFD; color:#111; border:1px solid #D5D5D8; border-radius:6px; margin-top:8px; }
            QGroupBox::title { subcontrol-origin: margin; left:10px; padding:2px 8px 2px 8px; background:#FAFBFD; border-radius:4px; }
            QLabel { color:#111; }
        """

        self.setStyleSheet(app_style)
        for dock in (
            self.dock_color,
            self.dock_scatter,
            self.dock_hist,
            self.dock_edge,
            self.dock_gray,
            self.dock_binary,
            self.dock_ternary,
            self.dock_saliency,
            self.dock_focus,
            self.dock_squint,
            self.dock_vectorscope,
        ):
            w = dock.widget()
            if isinstance(w, QWidget):
                w.setStyleSheet(dock_style)

    def _sync_mode_dependent_rows(self):
        is_interval = self._selected_mode() == C.UPDATE_MODE_INTERVAL
        for row in (self._row_interval_settings,):
            if row is not None:
                row.setVisible(is_interval)
        for row in (
            self._row_diff_settings,
            self._row_stable_settings,
        ):
            if row is not None:
                row.setVisible(not is_interval)

    def _sync_squint_mode_rows(self):
        mode = self._selected_squint_mode()
        show_scale = mode in (C.SQUINT_MODE_SCALE, C.SQUINT_MODE_SCALE_BLUR)
        show_blur = mode in (C.SQUINT_MODE_BLUR, C.SQUINT_MODE_SCALE_BLUR)
        if self._row_squint_scale_settings is not None:
            self._row_squint_scale_settings.setVisible(show_scale)
        if self._row_squint_blur_settings is not None:
            self._row_squint_blur_settings.setVisible(show_blur)

    def apply_sample_points_settings(self, *_):
        self.worker.set_sample_points(int(self.spin_points.value()))
        self.save_settings()

    def apply_scatter_settings(self, *_):
        shape = safe_choice(
            self.combo_scatter_shape.currentData(), C.SCATTER_SHAPES, C.DEFAULT_SCATTER_SHAPE
        )
        self.scatter.set_shape(shape)
        self.scatter.set_point_alpha(float(self.spin_scatter_alpha.value()))
        self.save_settings()

    def apply_analysis_resolution_settings(self, *_):
        self.worker.set_max_dim(int(self.spin_analysis_max_dim.value()))
        self.save_settings()

    def apply_wheel_settings(self, *_):
        self.wheel.set_mode(self._selected_wheel_mode())
        self.worker.set_wheel_sat_threshold(self._selected_wheel_sat_threshold())
        self.save_settings()

    def _selected_binary_preset(self) -> str:
        preset = self.combo_binary_preset.currentData()
        return safe_choice(preset, C.BINARY_PRESETS, C.DEFAULT_BINARY_PRESET)

    def _selected_ternary_preset(self) -> str:
        preset = self.combo_ternary_preset.currentData()
        return safe_choice(preset, C.TERNARY_PRESETS, C.DEFAULT_TERNARY_PRESET)

    def _selected_composition_guide(self) -> str:
        guide = self.combo_composition_guide.currentData()
        return safe_choice(guide, C.COMPOSITION_GUIDES, C.DEFAULT_COMPOSITION_GUIDE)

    def _selected_focus_peak_color(self) -> str:
        color = self.combo_focus_peak_color.currentData()
        return safe_choice(color, C.FOCUS_PEAK_COLORS, C.DEFAULT_FOCUS_PEAK_COLOR)

    def _selected_squint_mode(self) -> str:
        mode = self.combo_squint_mode.currentData()
        return safe_choice(mode, C.SQUINT_MODES, C.DEFAULT_SQUINT_MODE)

    def apply_edge_settings(self, *_):
        self.edge_view.set_sensitivity(self.spin_edge_sensitivity.value())
        self.save_settings()

    def apply_binary_settings(self, *_):
        self.binary_view.set_preset(self._selected_binary_preset())
        self.save_settings()

    def apply_ternary_settings(self, *_):
        self.ternary_view.set_preset(self._selected_ternary_preset())
        self.save_settings()

    def apply_saliency_settings(self, *_):
        self.saliency_view.set_overlay_alpha(int(self.spin_saliency_alpha.value()))
        self.save_settings()

    def apply_composition_guide_settings(self, *_):
        guide = self._selected_composition_guide()
        self.saliency_view.set_composition_guide(guide)
        self.preview_window.set_composition_guide(guide)
        self.save_settings()

    def apply_focus_peaking_settings(self, *_):
        self.focus_peaking_view.set_sensitivity(int(self.spin_focus_peak_sensitivity.value()))
        self.focus_peaking_view.set_color(self._selected_focus_peak_color())
        self.focus_peaking_view.set_thickness(float(self.spin_focus_peak_thickness.value()))
        self.save_settings()

    def apply_squint_settings(self, *_):
        self.squint_view.set_mode(self._selected_squint_mode())
        self.squint_view.set_scale_percent(int(self.spin_squint_scale.value()))
        self.squint_view.set_blur_sigma(float(self.spin_squint_blur.value()))
        self._sync_squint_mode_rows()
        self.save_settings()

    def _update_vectorscope_warning_label(self):
        ratio = float(self.vectorscope_view.high_saturation_ratio())
        threshold = int(self.spin_vectorscope_warn_threshold.value())
        if ratio <= 0.001:
            self.lbl_vectorscope_warning.setText("高彩度警告: なし")
            self.lbl_vectorscope_warning.setStyleSheet("color:#8b97a8;")
        elif ratio < 5.0:
            self.lbl_vectorscope_warning.setText(
                f"高彩度警告: しきい値({threshold}%)超え {ratio:.1f}%"
            )
            self.lbl_vectorscope_warning.setStyleSheet("color:#b89c52;")
        else:
            self.lbl_vectorscope_warning.setText(
                f"高彩度警告: しきい値({threshold}%)超え {ratio:.1f}%"
            )
            self.lbl_vectorscope_warning.setStyleSheet("color:#d06b5d;")

    def apply_vectorscope_settings(self, *_):
        self.vectorscope_view.set_show_skin_tone_line(
            bool(self.chk_vectorscope_skin_line.isChecked())
        )
        self.vectorscope_view.set_warn_threshold(int(self.spin_vectorscope_warn_threshold.value()))
        self._update_vectorscope_warning_label()
        self.save_settings()

    def _update_preview_snapshot(self):
        if not self.chk_preview_window.isChecked():
            return
        if (
            self._selected_capture_source() == C.CAPTURE_SOURCE_WINDOW
            and self.worker.target_hwnd is None
        ):
            self.on_status("ターゲットウィンドウを選択してください")
            return
        bgr, _cap, err = self.worker.capture_once()
        if bgr is None:
            if err:
                self.on_status(err)
            return
        if not self.preview_window.isVisible():
            self.preview_window.show()
        self.preview_window.update_preview(bgr)

    def on_preview_toggled(self, checked: bool):
        if checked:
            self.preview_window.show()
            self._update_preview_snapshot()
            self.on_status("プレビュー表示")
        else:
            self.preview_window.hide()
            self.on_status("プレビュー非表示")
        self.save_settings()

    def on_preview_closed(self):
        if self.chk_preview_window.isChecked():
            set_checked_blocked(self.chk_preview_window, False)
        self.on_status("プレビュー非表示")

    def apply_mode_settings(self):
        mode = self._selected_mode()
        self.worker.set_mode(mode)
        self.worker.set_diff_threshold(self.spin_diff.value())
        self.worker.set_stable_frames(self.spin_stable.value())
        self._sync_mode_dependent_rows()
        self.save_settings()

    def load_settings(self):
        cfg = load_config()
        self.spin_interval.setValue(float(cfg.get(C.CFG_INTERVAL, C.DEFAULT_INTERVAL_SEC)))
        sample_points = clamp_int(
            cfg.get(C.CFG_SAMPLE_POINTS, C.DEFAULT_SAMPLE_POINTS),
            C.ANALYZER_MIN_SAMPLE_POINTS,
            C.ANALYZER_MAX_SAMPLE_POINTS,
        )
        set_value_blocked(self.spin_points, sample_points)
        self.worker.set_sample_points(sample_points)
        analysis_max_dim = clamp_int(
            cfg.get(C.CFG_ANALYZER_MAX_DIM, C.ANALYZER_MAX_DIM),
            C.ANALYZER_MAX_DIM_MIN,
            C.ANALYZER_MAX_DIM_MAX,
        )
        set_value_blocked(self.spin_analysis_max_dim, analysis_max_dim)
        self.worker.set_max_dim(analysis_max_dim)
        scatter_shape = str(cfg.get(C.CFG_SCATTER_SHAPE, C.DEFAULT_SCATTER_SHAPE))
        set_combobox_data_blocked(
            self.combo_scatter_shape,
            safe_choice(scatter_shape, C.SCATTER_SHAPES, C.DEFAULT_SCATTER_SHAPE),
            default_data=C.DEFAULT_SCATTER_SHAPE,
        )
        self.scatter.set_shape(
            safe_choice(scatter_shape, C.SCATTER_SHAPES, C.DEFAULT_SCATTER_SHAPE)
        )
        scatter_alpha = float(cfg.get(C.CFG_SCATTER_POINT_ALPHA, C.DEFAULT_SCATTER_POINT_ALPHA))
        scatter_alpha = clamp_float(
            scatter_alpha, C.SCATTER_POINT_ALPHA_MIN, C.SCATTER_POINT_ALPHA_MAX
        )
        set_value_blocked(self.spin_scatter_alpha, scatter_alpha)
        self.scatter.set_point_alpha(scatter_alpha)
        wheel_mode = str(cfg.get(C.CFG_WHEEL_MODE, C.DEFAULT_WHEEL_MODE))
        set_combobox_data_blocked(
            self.combo_wheel_mode,
            safe_choice(wheel_mode, C.WHEEL_MODES, C.DEFAULT_WHEEL_MODE),
            default_data=C.DEFAULT_WHEEL_MODE,
        )
        wheel_sat_threshold = clamp_int(
            cfg.get(C.CFG_WHEEL_SAT_THRESHOLD, C.DEFAULT_WHEEL_SAT_THRESHOLD),
            C.WHEEL_SAT_THRESHOLD_MIN,
            C.WHEEL_SAT_THRESHOLD_MAX,
        )
        set_value_blocked(self.spin_wheel_sat_threshold, wheel_sat_threshold)
        self.wheel.set_mode(self._selected_wheel_mode())
        self.worker.set_wheel_sat_threshold(wheel_sat_threshold)
        self.worker.set_graph_every(C.DEFAULT_GRAPH_EVERY)
        source = cfg.get(C.CFG_CAPTURE_SOURCE, C.DEFAULT_CAPTURE_SOURCE)
        set_combobox_data_blocked(
            self.combo_capture_source,
            safe_choice(source, C.CAPTURE_SOURCES, C.DEFAULT_CAPTURE_SOURCE),
            default_data=C.DEFAULT_CAPTURE_SOURCE,
        )
        self._apply_capture_source(save=False)
        guide = cfg.get(C.CFG_COMPOSITION_GUIDE, C.DEFAULT_COMPOSITION_GUIDE)
        set_combobox_data_blocked(
            self.combo_composition_guide,
            safe_choice(guide, C.COMPOSITION_GUIDES, C.DEFAULT_COMPOSITION_GUIDE),
            default_data=C.DEFAULT_COMPOSITION_GUIDE,
        )
        self.saliency_view.set_composition_guide(self._selected_composition_guide())
        self.preview_window.set_composition_guide(self._selected_composition_guide())

        preview_checked = bool(cfg.get(C.CFG_PREVIEW_WINDOW, C.DEFAULT_PREVIEW_WINDOW))
        set_checked_blocked(self.chk_preview_window, preview_checked)
        if preview_checked:
            self.preview_window.show()
            self._update_preview_snapshot()
        else:
            self.preview_window.hide()
        mode = cfg.get(C.CFG_MODE, C.DEFAULT_MODE)
        set_combobox_data_blocked(
            self.combo_mode,
            safe_choice(mode, C.UPDATE_MODES, C.DEFAULT_MODE),
            default_data=C.DEFAULT_MODE,
        )
        self.spin_diff.setValue(float(cfg.get(C.CFG_DIFF_THRESHOLD, C.DEFAULT_DIFF_THRESHOLD)))
        self.spin_stable.setValue(int(cfg.get(C.CFG_STABLE_FRAMES, C.DEFAULT_STABLE_FRAMES)))
        edge_sens = clamp_int(
            cfg.get(C.CFG_EDGE_SENSITIVITY, C.DEFAULT_EDGE_SENSITIVITY),
            C.EDGE_SENSITIVITY_MIN,
            C.EDGE_SENSITIVITY_MAX,
        )
        set_value_blocked(self.spin_edge_sensitivity, edge_sens)
        self.edge_view.set_sensitivity(edge_sens)

        binary_preset = cfg.get(C.CFG_BINARY_PRESET, C.DEFAULT_BINARY_PRESET)
        set_combobox_data_blocked(
            self.combo_binary_preset,
            safe_choice(binary_preset, C.BINARY_PRESETS, C.DEFAULT_BINARY_PRESET),
            default_data=C.DEFAULT_BINARY_PRESET,
        )
        self.binary_view.set_preset(self._selected_binary_preset())

        ternary_preset = cfg.get(C.CFG_TERNARY_PRESET, C.DEFAULT_TERNARY_PRESET)
        set_combobox_data_blocked(
            self.combo_ternary_preset,
            safe_choice(ternary_preset, C.TERNARY_PRESETS, C.DEFAULT_TERNARY_PRESET),
            default_data=C.DEFAULT_TERNARY_PRESET,
        )
        self.ternary_view.set_preset(self._selected_ternary_preset())

        saliency_alpha = clamp_int(
            cfg.get(C.CFG_SALIENCY_OVERLAY_ALPHA, C.DEFAULT_SALIENCY_OVERLAY_ALPHA),
            C.SALIENCY_ALPHA_MIN,
            C.SALIENCY_ALPHA_MAX,
        )
        set_value_blocked(self.spin_saliency_alpha, saliency_alpha)
        self.saliency_view.set_overlay_alpha(saliency_alpha)

        focus_sens = clamp_int(
            cfg.get(C.CFG_FOCUS_PEAK_SENSITIVITY, C.DEFAULT_FOCUS_PEAK_SENSITIVITY),
            C.FOCUS_PEAK_SENSITIVITY_MIN,
            C.FOCUS_PEAK_SENSITIVITY_MAX,
        )
        set_value_blocked(self.spin_focus_peak_sensitivity, focus_sens)

        focus_color = cfg.get(C.CFG_FOCUS_PEAK_COLOR, C.DEFAULT_FOCUS_PEAK_COLOR)
        set_combobox_data_blocked(
            self.combo_focus_peak_color,
            safe_choice(focus_color, C.FOCUS_PEAK_COLORS, C.DEFAULT_FOCUS_PEAK_COLOR),
            default_data=C.DEFAULT_FOCUS_PEAK_COLOR,
        )

        focus_thick = float(cfg.get(C.CFG_FOCUS_PEAK_THICKNESS, C.DEFAULT_FOCUS_PEAK_THICKNESS))
        focus_thick = clamp_float(
            focus_thick, C.FOCUS_PEAK_THICKNESS_MIN, C.FOCUS_PEAK_THICKNESS_MAX
        )
        set_value_blocked(self.spin_focus_peak_thickness, focus_thick)
        self.focus_peaking_view.set_sensitivity(focus_sens)
        self.focus_peaking_view.set_color(self._selected_focus_peak_color())
        self.focus_peaking_view.set_thickness(focus_thick)

        squint_mode = cfg.get(C.CFG_SQUINT_MODE, C.DEFAULT_SQUINT_MODE)
        set_combobox_data_blocked(
            self.combo_squint_mode,
            safe_choice(squint_mode, C.SQUINT_MODES, C.DEFAULT_SQUINT_MODE),
            default_data=C.DEFAULT_SQUINT_MODE,
        )
        squint_scale = clamp_int(
            cfg.get(C.CFG_SQUINT_SCALE_PERCENT, C.DEFAULT_SQUINT_SCALE_PERCENT),
            C.SQUINT_SCALE_PERCENT_MIN,
            C.SQUINT_SCALE_PERCENT_MAX,
        )
        set_value_blocked(self.spin_squint_scale, squint_scale)
        squint_blur = float(cfg.get(C.CFG_SQUINT_BLUR_SIGMA, C.DEFAULT_SQUINT_BLUR_SIGMA))
        squint_blur = clamp_float(squint_blur, C.SQUINT_BLUR_SIGMA_MIN, C.SQUINT_BLUR_SIGMA_MAX)
        set_value_blocked(self.spin_squint_blur, squint_blur)
        self.squint_view.set_mode(self._selected_squint_mode())
        self.squint_view.set_scale_percent(squint_scale)
        self.squint_view.set_blur_sigma(squint_blur)
        self._sync_squint_mode_rows()

        show_skin_line = bool(
            cfg.get(C.CFG_VECTORSCOPE_SHOW_SKIN_LINE, C.DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE)
        )
        set_checked_blocked(self.chk_vectorscope_skin_line, show_skin_line)
        warn_threshold = clamp_int(
            cfg.get(C.CFG_VECTORSCOPE_WARN_THRESHOLD, C.DEFAULT_VECTORSCOPE_WARN_THRESHOLD),
            C.VECTORSCOPE_WARN_THRESHOLD_MIN,
            C.VECTORSCOPE_WARN_THRESHOLD_MAX,
        )
        set_value_blocked(self.spin_vectorscope_warn_threshold, warn_threshold)
        self.vectorscope_view.set_show_skin_tone_line(show_skin_line)
        self.vectorscope_view.set_warn_threshold(warn_threshold)
        self._update_vectorscope_warning_label()

        self.apply_mode_settings()
        self.apply_layout_from_config(cfg)
        self.refresh_layout_preset_views()

    def save_settings(self, silent: bool = True):
        base = load_config()
        cfg = dict(base)
        cfg.pop("ui_theme", None)
        cfg.update(
            {
                C.CFG_INTERVAL: float(self.spin_interval.value()),
                C.CFG_SAMPLE_POINTS: int(self.spin_points.value()),
                C.CFG_ANALYZER_MAX_DIM: int(self.spin_analysis_max_dim.value()),
                C.CFG_CAPTURE_SOURCE: self._selected_capture_source(),
                C.CFG_SCATTER_SHAPE: safe_choice(
                    self.combo_scatter_shape.currentData(),
                    C.SCATTER_SHAPES,
                    C.DEFAULT_SCATTER_SHAPE,
                ),
                C.CFG_SCATTER_POINT_ALPHA: float(self.spin_scatter_alpha.value()),
                C.CFG_WHEEL_MODE: self._selected_wheel_mode(),
                C.CFG_WHEEL_SAT_THRESHOLD: self._selected_wheel_sat_threshold(),
                C.CFG_GRAPH_EVERY: C.DEFAULT_GRAPH_EVERY,
                C.CFG_PREVIEW_WINDOW: bool(self.chk_preview_window.isChecked()),
                C.CFG_MODE: self._selected_mode(),
                C.CFG_DIFF_THRESHOLD: float(self.spin_diff.value()),
                C.CFG_STABLE_FRAMES: int(self.spin_stable.value()),
                C.CFG_EDGE_SENSITIVITY: int(self.spin_edge_sensitivity.value()),
                C.CFG_BINARY_PRESET: self._selected_binary_preset(),
                C.CFG_TERNARY_PRESET: self._selected_ternary_preset(),
                C.CFG_SALIENCY_OVERLAY_ALPHA: int(self.spin_saliency_alpha.value()),
                C.CFG_COMPOSITION_GUIDE: self._selected_composition_guide(),
                C.CFG_FOCUS_PEAK_SENSITIVITY: int(self.spin_focus_peak_sensitivity.value()),
                C.CFG_FOCUS_PEAK_COLOR: self._selected_focus_peak_color(),
                C.CFG_FOCUS_PEAK_THICKNESS: float(self.spin_focus_peak_thickness.value()),
                C.CFG_SQUINT_MODE: self._selected_squint_mode(),
                C.CFG_SQUINT_SCALE_PERCENT: int(self.spin_squint_scale.value()),
                C.CFG_SQUINT_BLUR_SIGMA: float(self.spin_squint_blur.value()),
                C.CFG_VECTORSCOPE_SHOW_SKIN_LINE: bool(self.chk_vectorscope_skin_line.isChecked()),
                C.CFG_VECTORSCOPE_WARN_THRESHOLD: int(self.spin_vectorscope_warn_threshold.value()),
            }
        )
        save_config(cfg)
        if not silent:
            self.on_status("設定を保存しました")

    def sync_window_menu_checks(self, *_):
        for name, dock in self._dock_map.items():
            act = self._dock_actions.get(name)
            if act is None:
                continue
            set_checked_blocked(act, dock.isVisible())

    def _apply_default_view_layout(self):
        default_visible = {
            "dock_color": False,
            "dock_scatter": False,
            "dock_hist": False,
            "dock_edge": False,
            "dock_gray": False,
            "dock_binary": False,
            "dock_ternary": False,
            "dock_saliency": False,
            "dock_focus": False,
            "dock_squint": False,
            "dock_vectorscope": False,
        }
        for name, dock in self._dock_map.items():
            dock.setVisible(default_visible.get(name, False))
        self.sync_window_menu_checks()

    def save_current_layout_to_config(self, silent: bool = False):
        cfg = load_config()
        cfg[C.CFG_LAYOUT_CURRENT] = capture_layout_state(self, self._dock_map)
        save_config(cfg)
        if not silent:
            self.on_status("現在の配置を保存しました")
            self.refresh_layout_preset_views()

    def _schedule_layout_autosave(self):
        if not self._layout_autosave_enabled:
            return
        if self.isMinimized():
            return
        self._layout_save_timer.start()

    def apply_layout_from_config(self, cfg: dict):
        layout = cfg.get(C.CFG_LAYOUT_CURRENT, {})
        restored = apply_layout_state(self, self._dock_map, layout)
        if not restored:
            self._apply_default_view_layout()
        self.sync_window_menu_checks()
        self.update_placeholder()
        self._fit_window_to_desktop()
        self._schedule_layout_autosave()

    def refresh_layout_preset_views(self):
        cfg = load_config()
        presets = cfg.get(C.CFG_LAYOUT_PRESETS, {})
        if not isinstance(presets, dict):
            presets = {}

        current = self.combo_layout_presets.currentText()
        with blocked_signals(self.combo_layout_presets):
            self.combo_layout_presets.clear()
            for name in sorted(presets.keys()):
                self.combo_layout_presets.addItem(name)
            if current:
                idx = self.combo_layout_presets.findText(current)
                if idx >= 0:
                    self.combo_layout_presets.setCurrentIndex(idx)

        self.presets_menu.clear()
        if not presets:
            act = self.presets_menu.addAction("（プリセットなし）")
            act.setEnabled(False)
        else:
            for name in sorted(presets.keys()):
                act = self.presets_menu.addAction(name)
                act.triggered.connect(lambda _checked=False, n=name: self.apply_layout_preset(n))

    def apply_layout_preset(self, name: str):
        cfg = load_config()
        presets = cfg.get(C.CFG_LAYOUT_PRESETS, {})
        if not isinstance(presets, dict):
            return
        layout = presets.get(name)
        if not isinstance(layout, dict):
            return
        apply_layout_state(self, self._dock_map, layout)
        self.sync_window_menu_checks()
        self.update_placeholder()
        self._fit_window_to_desktop()
        self._schedule_layout_autosave()
        self.on_status(f"プリセット適用: {name}")

    def load_selected_layout_preset(self):
        name = self.combo_layout_presets.currentText().strip()
        if not name:
            return
        self.apply_layout_preset(name)

    def save_layout_preset(self):
        name = (
            self.edit_preset_name.text().strip() or self.combo_layout_presets.currentText().strip()
        )
        if not name:
            QMessageBox.information(self, "情報", "プリセット名を入力してください。")
            return
        cfg = load_config()
        presets = cfg.get(C.CFG_LAYOUT_PRESETS, {})
        if not isinstance(presets, dict):
            presets = {}
        presets[name] = capture_layout_state(self, self._dock_map)
        cfg[C.CFG_LAYOUT_PRESETS] = presets
        cfg[C.CFG_LAYOUT_CURRENT] = presets[name]
        save_config(cfg)
        self.refresh_layout_preset_views()
        self.combo_layout_presets.setCurrentText(name)
        self.on_status(f"プリセット保存: {name}")

    def delete_selected_layout_preset(self):
        name = self.combo_layout_presets.currentText().strip()
        if not name:
            return
        cfg = load_config()
        presets = cfg.get(C.CFG_LAYOUT_PRESETS, {})
        if not isinstance(presets, dict):
            return
        if name in presets:
            del presets[name]
            cfg[C.CFG_LAYOUT_PRESETS] = presets
            save_config(cfg)
            self.refresh_layout_preset_views()
            self.on_status(f"プリセット削除: {name}")

    def toggle_dock(self, dock: QDockWidget, visible: bool):
        if visible:
            if not dock.isFloating() and self.dockWidgetArea(dock) == Qt.NoDockWidgetArea:
                self.addDockWidget(Qt.RightDockWidgetArea, dock)
            dock.setVisible(True)
            if dock.isFloating():
                self._fit_top_level_widget_to_desktop(dock)
                dock.raise_()
                dock.activateWindow()
            else:
                dock.raise_()
        else:
            dock.setVisible(False)
        self.update_placeholder()
        self._schedule_layout_autosave()
        self._schedule_dock_rebalance()

    def update_placeholder(self):
        any_visible = any(d.isVisible() for d in self._dock_map.values())
        if any_visible:
            self.placeholder.hide()
            # 中央領域を極小化してドックに最大面積を割り当てる
            self.central_container.setMinimumSize(0, 0)
            self.central_container.setMaximumSize(0, 0)
            self.central_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        else:
            self.placeholder.show()
            self.central_container.setMaximumSize(16777215, 16777215)
            self.central_container.setMinimumSize(120, 120)
            self.central_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.central_container.updateGeometry()

    def show_settings_window(self, page_index: int = 0):
        self.refresh_layout_preset_views()
        created = False
        if not hasattr(self, "_settings_window"):
            created = True
            self._settings_window = QDialog(self)
            self._settings_window.setWindowTitle("設定")
            self._settings_window.setMinimumSize(680, 460)

            root = QHBoxLayout(self._settings_window)
            root.setContentsMargins(10, 10, 10, 10)
            root.setSpacing(10)

            nav = QListWidget()
            nav.setFixedWidth(170)
            nav.addItems(
                [
                    "キャプチャ",
                    "更新",
                    "カラーサークル",
                    "散布図",
                    "ベクトルスコープ",
                    "画像処理",
                    "フォーカスピーキング",
                    "スクイント表示",
                    "サリエンシー",
                    "レイアウト",
                ]
            )

            pages = QStackedWidget()

            page_capture = QWidget()
            lc = QVBoxLayout(page_capture)
            lc.setContentsMargins(8, 8, 8, 8)
            lc.setSpacing(10)
            lc.addWidget(_make_labeled_row("取得元", self.combo_capture_source))
            self._row_target_settings = _make_labeled_row("ターゲット", self.combo_win)
            lc.addWidget(self._row_target_settings)
            lc.addWidget(self.btn_refresh)
            lc.addWidget(self.btn_pick_roi_win)
            lc.addWidget(self.btn_pick_roi_screen)
            lc.addWidget(_make_labeled_row("解析解像度（長辺）", self.spin_analysis_max_dim))
            hint_analysis = QLabel(
                "ヒストグラム/散布図などの解析解像度です。高いほど精度が上がり、負荷も増えます。"
            )
            hint_analysis.setWordWrap(True)
            hint_analysis.setStyleSheet("color:#6b7280;")
            lc.addWidget(hint_analysis)
            lc.addWidget(self.chk_preview_window)
            lc.addStretch(1)
            pages.addWidget(page_capture)

            page_update = QWidget()
            lu = QVBoxLayout(page_update)
            lu.setContentsMargins(8, 8, 8, 8)
            lu.setSpacing(10)
            lu.addWidget(_make_labeled_row("更新モード", self.combo_mode))
            self._row_interval_settings = _make_labeled_row("更新間隔", self.spin_interval)
            lu.addWidget(self._row_interval_settings)
            self._row_diff_settings = _make_labeled_row("差分閾値", self.spin_diff)
            lu.addWidget(self._row_diff_settings)
            self._row_stable_settings = _make_labeled_row("安定フレーム", self.spin_stable)
            lu.addWidget(self._row_stable_settings)
            lu.addStretch(1)
            pages.addWidget(page_update)

            page_scatter = QWidget()
            ls = QVBoxLayout(page_scatter)
            ls.setContentsMargins(8, 8, 8, 8)
            ls.setSpacing(10)
            hint = QLabel("散布図のサンプル点数を設定します")
            hint.setStyleSheet("color:#6b7280;")
            ls.addWidget(hint)
            ls.addWidget(_make_labeled_row("表示形状", self.combo_scatter_shape))
            ls.addWidget(_make_labeled_row("散布点数", self.spin_points))
            ls.addWidget(_make_labeled_row("点の透明度", self.spin_scatter_alpha))
            ls.addStretch(1)
            pages.addWidget(page_scatter)

            page_wheel = QWidget()
            lw = QVBoxLayout(page_wheel)
            lw.setContentsMargins(8, 8, 8, 8)
            lw.setSpacing(10)
            hint_wheel = QLabel("カラーサークルの色相分類方式を設定します")
            hint_wheel.setStyleSheet("color:#6b7280;")
            lw.addWidget(hint_wheel)
            lw.addWidget(_make_labeled_row("表示方式", self.combo_wheel_mode))
            lw.addWidget(_make_labeled_row("彩度しきい値", self.spin_wheel_sat_threshold))
            hint_wheel_sat = QLabel(
                "この値未満の彩度はカラーサークル集計から除外します。0で最大限拾います。"
            )
            hint_wheel_sat.setWordWrap(True)
            hint_wheel_sat.setStyleSheet("color:#6b7280;")
            lw.addWidget(hint_wheel_sat)
            lw.addStretch(1)
            pages.addWidget(page_wheel)

            page_image = QWidget()
            li = QVBoxLayout(page_image)
            li.setContentsMargins(8, 8, 8, 8)
            li.setSpacing(10)
            li.addWidget(QLabel("エッジ・2値化・3値化の見え方を調整できます"))
            li.addWidget(_make_labeled_row("エッジ感度", self.spin_edge_sensitivity))
            li.addWidget(_make_labeled_row("2値化", self.combo_binary_preset))
            li.addWidget(_make_labeled_row("3値化", self.combo_ternary_preset))
            li.addStretch(1)
            pages.addWidget(page_image)

            page_saliency = QWidget()
            lsal = QVBoxLayout(page_saliency)
            lsal.setContentsMargins(8, 8, 8, 8)
            lsal.setSpacing(10)
            lsal.addWidget(QLabel("サリエンシーマップ（スペクトル残差）を調整します"))
            lsal.addWidget(_make_labeled_row("重ね具合", self.spin_saliency_alpha))
            lsal.addWidget(_make_labeled_row("構図ガイド", self.combo_composition_guide))
            hint_guide = QLabel(
                "補足: 三分割は交点に注目、中央クロスは中心確認、対角線は視線の流れ確認に使えます。"
            )
            hint_guide.setWordWrap(True)
            hint_guide.setStyleSheet("color:#6b7280;")
            lsal.addWidget(hint_guide)
            hint_gray = QLabel("表示は残差を見やすくするため、背景をグレースケール化しています。")
            hint_gray.setWordWrap(True)
            hint_gray.setStyleSheet("color:#6b7280;")
            lsal.addWidget(hint_gray)
            lsal.addStretch(1)
            pages.addWidget(page_saliency)

            page_focus = QWidget()
            lfocus = QVBoxLayout(page_focus)
            lfocus.setContentsMargins(8, 8, 8, 8)
            lfocus.setSpacing(10)
            lfocus.addWidget(QLabel("フォーカスピーキングを調整します"))
            lfocus.addWidget(_make_labeled_row("感度", self.spin_focus_peak_sensitivity))
            lfocus.addWidget(_make_labeled_row("色", self.combo_focus_peak_color))
            lfocus.addWidget(_make_labeled_row("線幅", self.spin_focus_peak_thickness))
            hint_focus = QLabel("補足: 線幅は小数点1桁で設定できます（例: 1.5px）。")
            hint_focus.setWordWrap(True)
            hint_focus.setStyleSheet("color:#6b7280;")
            lfocus.addWidget(hint_focus)
            lfocus.addStretch(1)
            pages.addWidget(page_focus)

            page_squint = QWidget()
            lsq = QVBoxLayout(page_squint)
            lsq.setContentsMargins(8, 8, 8, 8)
            lsq.setSpacing(10)
            lsq.addWidget(QLabel("スクイント表示を調整します"))
            lsq.addWidget(_make_labeled_row("モード", self.combo_squint_mode))
            self._row_squint_scale_settings = _make_labeled_row("縮小率", self.spin_squint_scale)
            lsq.addWidget(self._row_squint_scale_settings)
            self._row_squint_blur_settings = _make_labeled_row("ぼかし", self.spin_squint_blur)
            lsq.addWidget(self._row_squint_blur_settings)
            hint_squint = QLabel(
                "補足: モードに応じて縮小率/ぼかしの設定項目を自動で表示切替します。"
            )
            hint_squint.setWordWrap(True)
            hint_squint.setStyleSheet("color:#6b7280;")
            lsq.addWidget(hint_squint)
            lsq.addStretch(1)
            pages.addWidget(page_squint)

            page_vectorscope = QWidget()
            lvec = QVBoxLayout(page_vectorscope)
            lvec.setContentsMargins(8, 8, 8, 8)
            lvec.setSpacing(10)
            lvec.addWidget(QLabel("YUVベクトルスコープ表示を調整します"))
            lvec.addWidget(self.chk_vectorscope_skin_line)
            lvec.addWidget(
                _make_labeled_row("高彩度しきい値", self.spin_vectorscope_warn_threshold)
            )
            hint_vec = QLabel(
                "補足: R/Y/G/C/B/M の方位はカラーサークルと同じ角度に合わせています。"
            )
            hint_vec.setWordWrap(True)
            hint_vec.setStyleSheet("color:#6b7280;")
            lvec.addWidget(hint_vec)
            hint_sat = QLabel(
                "補足: 高彩度しきい値は絶対基準ではなく、用途に合わせて調整する目安値です。"
            )
            hint_sat.setWordWrap(True)
            hint_sat.setStyleSheet("color:#6b7280;")
            lvec.addWidget(hint_sat)
            lvec.addStretch(1)
            pages.addWidget(page_vectorscope)

            page_layout = QWidget()
            ll = QVBoxLayout(page_layout)
            ll.setContentsMargins(8, 8, 8, 8)
            ll.setSpacing(10)
            ll.addWidget(QLabel("現在の表示配置をプリセットとして保存できます"))
            ll.addWidget(_make_labeled_row("プリセット", self.combo_layout_presets))
            ll.addWidget(_make_labeled_row("新規名", self.edit_preset_name))
            row_btn = QHBoxLayout()
            row_btn.setContentsMargins(0, 0, 0, 0)
            row_btn.addWidget(self.btn_load_preset)
            row_btn.addWidget(self.btn_save_preset)
            row_btn.addWidget(self.btn_delete_preset)
            ll.addLayout(row_btn)
            ll.addStretch(1)
            pages.addWidget(page_layout)

            self._settings_nav_to_page = [
                SETTINGS_PAGE_CAPTURE,
                SETTINGS_PAGE_UPDATE,
                SETTINGS_PAGE_WHEEL,
                SETTINGS_PAGE_SCATTER,
                SETTINGS_PAGE_VECTORSCOPE,
                SETTINGS_PAGE_IMAGE,
                SETTINGS_PAGE_FOCUS,
                SETTINGS_PAGE_SQUINT,
                SETTINGS_PAGE_SALIENCY,
                SETTINGS_PAGE_LAYOUT,
            ]
            self._settings_page_to_nav = {p: i for i, p in enumerate(self._settings_nav_to_page)}

            def _on_nav_row_changed(row: int):
                if not hasattr(self, "_settings_nav_to_page"):
                    return
                if row < 0 or row >= len(self._settings_nav_to_page):
                    return
                pages.setCurrentIndex(int(self._settings_nav_to_page[row]))

            nav.currentRowChanged.connect(_on_nav_row_changed)
            nav.setCurrentRow(0)
            self._settings_nav = nav

            right = QWidget()
            right_l = QVBoxLayout(right)
            right_l.setContentsMargins(0, 0, 0, 0)
            right_l.setSpacing(8)
            right_l.addWidget(pages, 1)

            bottom = QHBoxLayout()
            bottom.addStretch(1)
            btn_close = QPushButton("閉じる")
            btn_close.clicked.connect(self._settings_window.close)
            bottom.addWidget(btn_close)
            right_l.addLayout(bottom)

            root.addWidget(nav)
            root.addWidget(right, 1)

        if hasattr(self, "_settings_nav"):
            page = max(0, min(SETTINGS_PAGE_LAYOUT, int(page_index)))
            nav_row = (
                self._settings_page_to_nav.get(page, 0)
                if hasattr(self, "_settings_page_to_nav")
                else 0
            )
            self._settings_nav.setCurrentRow(int(nav_row))

        self._sync_capture_source_ui()
        self._sync_mode_dependent_rows()
        self._sync_squint_mode_rows()
        if created:
            self._settings_window.resize(760, 520)
        self._present_settings_window(center_on_parent=created)

    def hide_settings_window(self):
        if hasattr(self, "_settings_window"):
            self._settings_window.hide()

    def _on_roi_selector_destroyed(self, selector):
        self._roi_selectors = [s for s in self._roi_selectors if s is not selector]
        if self._roi_selector is selector:
            self._roi_selector = self._roi_selectors[0] if self._roi_selectors else None

    def _close_roi_selectors(self):
        selectors = list(self._roi_selectors)
        if self._roi_selector is not None and self._roi_selector not in selectors:
            selectors.append(self._roi_selector)
        self._roi_selectors = []
        self._roi_selector = None
        for sel in selectors:
            try:
                sel.close()
            except Exception:
                pass

    def _open_multi_screen_roi_selectors(self, help_text: str, on_selected):
        self._close_roi_selectors()
        screens = [s for s in QGuiApplication.screens() if s is not None]
        if not screens:
            ps = QGuiApplication.primaryScreen()
            if ps is not None:
                screens = [ps]
        selectors = []
        for screen in screens:
            sel = RoiSelector(bounds=screen.geometry(), help_text=help_text, as_window=True)
            sel.roiSelected.connect(on_selected)
            sel.destroyed.connect(lambda _=None, s=sel: self._on_roi_selector_destroyed(s))
            sel.createWinId()
            handle = sel.windowHandle()
            if handle is not None:
                handle.setScreen(screen)
            selectors.append(sel)
        self._roi_selectors = selectors
        self._roi_selector = selectors[0] if selectors else None
        for sel in selectors:
            sel.show()
            sel.raise_()
            sel.activateWindow()

    def pick_roi_on_screen(self):
        if self._selected_capture_source() != C.CAPTURE_SOURCE_SCREEN:
            idx = self.combo_capture_source.findData(C.CAPTURE_SOURCE_SCREEN)
            if idx >= 0:
                self.combo_capture_source.setCurrentIndex(idx)
        help_text = "画面上で領域をドラッグ選択（Escでキャンセル）"
        self._open_multi_screen_roi_selectors(help_text, self.on_roi_screen_selected)
        self.on_status("画面領域選択中…")

    def on_roi_screen_selected(self, r: QRect):
        self._close_roi_selectors()
        # 画面領域モードに切り替え（ウィンドウターゲットは解除）
        self.worker.set_target_window(None)
        self.worker.set_roi_on_screen(r)
        self.worker.set_roi_in_window(None)
        set_current_index_blocked(self.combo_win, 0)
        self.on_status(f"画面領域: x={r.left()} y={r.top()} w={r.width()} h={r.height()}")
        self._update_preview_snapshot()

    def pick_roi_in_window(self):
        if self._selected_capture_source() != C.CAPTURE_SOURCE_WINDOW:
            idx = self.combo_capture_source.findData(C.CAPTURE_SOURCE_WINDOW)
            if idx >= 0:
                self.combo_capture_source.setCurrentIndex(idx)
        if not HAS_WIN32:
            QMessageBox.information(
                self,
                "情報",
                "この環境ではウィンドウ選択は使えません。\n画面の領域選択を使ってください。",
            )
            return
        hwnd = self.combo_win.currentData()
        if hwnd is None:
            QMessageBox.information(self, "情報", "まずターゲットウィンドウを選んでください。")
            return
        bounds_native = self.worker._get_window_rect(int(hwnd))
        if bounds_native is None:
            QMessageBox.warning(self, "警告", "ウィンドウ矩形の取得に失敗しました。")
            return
        help_text = "ターゲットウィンドウ付近で領域をドラッグ選択（ウィンドウ外は自動で切り詰め）"
        self._open_multi_screen_roi_selectors(
            help_text,
            lambda r, h=int(hwnd), wr=QRect(bounds_native): self.on_roi_window_selected(h, wr, r),
        )
        self.on_status("ウィンドウ内領域選択中…")

    def on_roi_window_selected(self, hwnd: int, wrect: QRect, roi_abs_logical: QRect):
        self._close_roi_selectors()
        roi_abs_native = self.worker._logical_rect_to_native(roi_abs_logical)
        hit = roi_abs_native.intersected(wrect)
        if hit.width() < 10 or hit.height() < 10:
            self.on_status(
                "選択領域がターゲットウィンドウに重なっていません。もう一度選択してください。"
            )
            return

        rel = QRect(hit.left() - wrect.left(), hit.top() - wrect.top(), hit.width(), hit.height())
        self.worker.set_target_window(hwnd)
        self.worker.set_roi_on_screen(None)
        self.worker.set_roi_in_window(rel)
        self.on_status(
            f"ウィンドウ領域: rel_x={rel.left()} rel_y={rel.top()} w={rel.width()} h={rel.height()}"
        )
        self._update_preview_snapshot()

    def on_result(self, res: dict):
        if self.preview_window.isVisible():
            self.preview_window.update_preview(res["bgr_preview"])

        if res["graph_update"]:
            if res["hist"] is not None and self.dock_color.isVisible():
                self.wheel.update_hist(res["hist"])
                # トップ5色は analyzer 側で実画素に基づいて計算済み
                bars = res.get("top_colors")
                if bars is None:
                    _, bars = top_hue_bars(res["hist"])
                self._last_top_bars = bars
                self.top_colors_bar.setPixmap(
                    render_top_color_bar(
                        bars or [],
                        width=self.top_colors_bar.width(),
                        height=self.top_colors_bar.height(),
                    )
                )
                self.lbl_warmcool.setText(
                    f"暖色: {res['warm_ratio']*100:.1f}%   寒色: {res['cool_ratio']*100:.1f}%   その他: {res.get('other_ratio',0)*100:.1f}%"
                )
            if res["sv"] is not None and res["rgb"] is not None and self.dock_scatter.isVisible():
                self.scatter.update_scatter(res["sv"], res["rgb"])
            if res.get("h_plane") is not None and self.dock_hist.isVisible():
                self.hist_h.update_from_values(res["h_plane"])
            if res.get("s_plane") is not None and self.dock_hist.isVisible():
                self.hist_s.update_from_values(res["s_plane"])
            if res.get("v_plane") is not None and self.dock_hist.isVisible():
                self.hist_v.update_from_values(res["v_plane"])
            if self.dock_edge.isVisible():
                self.edge_view.update_edge(res["bgr_preview"])
            if self.dock_gray.isVisible():
                self.gray_view.update_gray(res["bgr_preview"])
            if self.dock_binary.isVisible():
                self.binary_view.update_binary(res["bgr_preview"])
            if self.dock_ternary.isVisible():
                self.ternary_view.update_ternary(res["bgr_preview"])
            if self.dock_saliency.isVisible():
                self.saliency_view.update_saliency(res["bgr_preview"])
            if self.dock_focus.isVisible():
                self.focus_peaking_view.update_focus(res["bgr_preview"])
            if self.dock_squint.isVisible():
                self.squint_view.update_squint(res["bgr_preview"])
            if self.dock_vectorscope.isVisible():
                self.vectorscope_view.update_scope(res["bgr_preview"])
                self._update_vectorscope_warning_label()

        # 計測情報は非表示にする要求に合わせて更新しない


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
