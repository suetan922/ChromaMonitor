from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..util import constants as C
from ..widgets import (
    BinaryView,
    ChannelHistogram,
    ColorWheelWidget,
    EdgeView,
    FocusPeakingView,
    GrayscaleView,
    SaliencyView,
    ScatterRasterWidget,
    SquintView,
    TernaryView,
    VectorScopeView,
)


def _build_single_view_container(view: QWidget) -> QWidget:
    # 単一ビュー向けの共通余白コンテナ。
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.addWidget(view, 1)
    return container


def _create_dock(
    main_window,
    title: str,
    object_name: str,
    content: QWidget,
    area: Qt.DockWidgetArea = Qt.RightDockWidgetArea,
) -> QDockWidget:
    # タイトル・ObjectName・初期配置をまとめて設定する。
    dock = QDockWidget(title, main_window)
    dock.setObjectName(object_name)
    dock.setWidget(content)
    dock.setAllowedAreas(Qt.AllDockWidgetAreas)
    main_window.addDockWidget(area, dock)
    return dock


def _connect_signal_ignoring_args(signal, callback) -> None:
    # シグナル引数の有無を気にせず callback を呼べるようにする。
    signal.connect(lambda *_args, cb=callback: cb())


def _configure_view_dock(main_window, dock: QDockWidget) -> None:
    # 各ドックの共通機能（移動/フロート/閉じる等）を設定する。
    dock.setFeatures(
        QDockWidget.DockWidgetMovable
        | QDockWidget.DockWidgetFloatable
        | QDockWidget.DockWidgetClosable
    )
    dock.setWindowFlag(Qt.WindowCloseButtonHint, True)
    dock.setWindowFlag(Qt.WindowSystemMenuHint, True)
    dock.setAllowedAreas(Qt.AllDockWidgetAreas)
    dock.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    dock.visibilityChanged.connect(main_window.update_placeholder)
    dock.visibilityChanged.connect(main_window.sync_window_menu_checks)

    for signal in (dock.visibilityChanged, dock.topLevelChanged, dock.dockLocationChanged):
        # 表示状態が変わるたびに自動保存/フィット/再バランスを予約する。
        _connect_signal_ignoring_args(signal, main_window._schedule_layout_autosave)
        _connect_signal_ignoring_args(signal, main_window._schedule_window_fit)
        _connect_signal_ignoring_args(signal, main_window._schedule_dock_rebalance)


def setup_view_docks(main_window) -> None:
    # 各解析ビューウィジェットを生成する。
    main_window.wheel = ColorWheelWidget()
    main_window.wheel.setStyleSheet("background:#FFFFFF; border:1px solid #CCC;")

    main_window.scatter = ScatterRasterWidget()
    main_window.chk_scatter_hue_filter = QCheckBox("色相フィルター")
    main_window.chk_scatter_hue_filter.setChecked(C.DEFAULT_SCATTER_HUE_FILTER_ENABLED)
    main_window.slider_scatter_hue_center = QSlider(Qt.Vertical)
    main_window.slider_scatter_hue_center.setRange(C.SCATTER_HUE_MIN, C.SCATTER_HUE_MAX)
    main_window.slider_scatter_hue_center.setSingleStep(1)
    main_window.slider_scatter_hue_center.setPageStep(10)
    main_window.slider_scatter_hue_center.setValue(C.DEFAULT_SCATTER_HUE_CENTER)
    main_window.slider_scatter_hue_center.setFixedWidth(30)
    main_window.slider_scatter_hue_center.setFixedHeight(220)
    main_window.slider_scatter_hue_center.setStyleSheet(
        "QSlider::groove:vertical {"
        "border: 1px solid #c4c9d4;"
        "width: 10px;"
        "margin: 7px 0;"
        "border-radius: 6px;"
        "background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        "stop:0 #ff0000, stop:0.16 #ff00ff, stop:0.33 #0000ff, stop:0.5 #00ffff,"
        "stop:0.66 #00ff00, stop:0.83 #ffff00, stop:1 #ff0000);"
        "}"
        "QSlider::handle:vertical {"
        "background: #f5f7fb;"
        "border: 1px solid #4e5565;"
        "width: 20px;"
        "height: 14px;"
        "margin: 0 -6px;"
        "border-radius: 7px;"
        "}"
    )
    main_window.lbl_scatter_hue_center = QLabel("H 0")
    main_window.lbl_scatter_hue_center.setAlignment(Qt.AlignCenter)
    main_window.lbl_scatter_hue_center.setStyleSheet("color:#334155; font-size:11px;")

    # バケット幅を揃えて視覚的スケールを統一
    main_window.hist_h = ChannelHistogram("色相", 180, 179, C.H_COLOR, bucket=2)
    main_window.hist_s = ChannelHistogram("彩度", 256, 255, C.S_COLOR, bucket=2)
    main_window.hist_v = ChannelHistogram("明度", 256, 255, C.V_COLOR, bucket=2)

    main_window._last_top_bars = []
    main_window._top_bar_render_key = None
    main_window.lbl_top5_title = QLabel(C.TOP_COLORS_TITLE)
    main_window.lbl_top5_title.setStyleSheet("color:#111; font-size:12px; font-weight:600;")

    main_window.top_colors_bar = QLabel()
    main_window.top_colors_bar.setFixedHeight(C.TOP_COLOR_BAR_HEIGHT)
    main_window.top_colors_bar.setMinimumWidth(0)
    main_window.top_colors_bar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
    main_window.top_colors_bar.setScaledContents(False)

    main_window.lbl_warmcool = QLabel("暖色: -   寒色: -   その他: -")
    main_window.lbl_warmcool.setStyleSheet("color:#111; font-size:12px;")
    main_window.lbl_warmcool.setWordWrap(True)
    main_window.lbl_warmcool.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    # ドックのネスティングを有効化（3段以上に自由配置できるように）
    main_window.setDockNestingEnabled(True)

    color_widget = QWidget()
    cw_l = QVBoxLayout(color_widget)
    cw_l.setContentsMargins(6, 6, 6, 6)
    cw_l.setSpacing(6)
    cw_l.addWidget(main_window.wheel, 1)
    cw_l.addWidget(main_window.lbl_top5_title)
    cw_l.addWidget(main_window.top_colors_bar)
    cw_l.addWidget(main_window.lbl_warmcool)
    color_dock = _create_dock(main_window, "色相リング", "dock_color", color_widget)

    scatter_container = QWidget()
    sc_l = QHBoxLayout(scatter_container)
    sc_l.setContentsMargins(6, 6, 6, 6)
    sc_l.setSpacing(8)
    sc_l.addWidget(main_window.scatter, 1)

    scatter_controls = QWidget()
    sctrl_l = QVBoxLayout(scatter_controls)
    sctrl_l.setContentsMargins(0, 0, 0, 0)
    sctrl_l.setSpacing(6)
    sctrl_l.addStretch(1)
    sctrl_l.addWidget(main_window.chk_scatter_hue_filter, 0, Qt.AlignHCenter)
    sctrl_l.addWidget(main_window.slider_scatter_hue_center, 0, Qt.AlignHCenter)
    sctrl_l.addWidget(main_window.lbl_scatter_hue_center, 0, Qt.AlignHCenter)
    sctrl_l.addStretch(1)
    sc_l.addWidget(scatter_controls, 0)
    scatter_dock = _create_dock(main_window, "S-V 散布図", "dock_scatter", scatter_container)

    hist_container = QWidget()
    hg_l = QHBoxLayout(hist_container)
    hg_l.setContentsMargins(8, 8, 8, 8)
    hg_l.setSpacing(10)
    hg_l.addWidget(main_window.hist_h)
    hg_l.addWidget(main_window.hist_s)
    hg_l.addWidget(main_window.hist_v)
    hist_dock = _create_dock(
        main_window,
        "H/S/V ヒストグラム",
        "dock_hist",
        hist_container,
        area=Qt.BottomDockWidgetArea,
    )

    main_window.edge_view = EdgeView()
    edge_container = _build_single_view_container(main_window.edge_view)
    edge_dock = _create_dock(main_window, "エッジ検出", "dock_edge", edge_container)

    main_window.gray_view = GrayscaleView()
    gray_container = _build_single_view_container(main_window.gray_view)
    gray_dock = _create_dock(main_window, "グレースケール", "dock_gray", gray_container)

    main_window.binary_view = BinaryView()
    binary_container = _build_single_view_container(main_window.binary_view)
    binary_dock = _create_dock(main_window, "2値化", "dock_binary", binary_container)

    main_window.ternary_view = TernaryView()
    ternary_container = _build_single_view_container(main_window.ternary_view)
    ternary_dock = _create_dock(main_window, "3値化", "dock_ternary", ternary_container)

    main_window.saliency_view = SaliencyView()
    saliency_container = _build_single_view_container(main_window.saliency_view)
    saliency_dock = _create_dock(
        main_window, "サリエンシーマップ", "dock_saliency", saliency_container
    )

    main_window.focus_peaking_view = FocusPeakingView()
    focus_container = _build_single_view_container(main_window.focus_peaking_view)
    focus_dock = _create_dock(main_window, "フォーカスピーキング", "dock_focus", focus_container)

    main_window.squint_view = SquintView()
    squint_container = _build_single_view_container(main_window.squint_view)
    squint_dock = _create_dock(main_window, "スクイント表示", "dock_squint", squint_container)

    main_window.vectorscope_view = VectorScopeView()
    vectorscope_container = QWidget()
    vs_l = QVBoxLayout(vectorscope_container)
    vs_l.setContentsMargins(6, 6, 6, 6)
    vs_l.setSpacing(6)
    vs_l.addWidget(main_window.vectorscope_view, 1)
    main_window.lbl_vectorscope_warning = QLabel("高彩度警告: 入力待ち")
    main_window.lbl_vectorscope_warning.setStyleSheet("color:#8b97a8;")
    vs_l.addWidget(main_window.lbl_vectorscope_warning, 0)
    vectorscope_dock = _create_dock(
        main_window, "ベクトルスコープ", "dock_vectorscope", vectorscope_container
    )

    main_window.setDockOptions(QMainWindow.AllowTabbedDocks | QMainWindow.AllowNestedDocks)

    main_window.placeholder = QLabel("🖼️ ウィンドウメニューから表示したいビューを選択してください")
    main_window.placeholder.setAlignment(Qt.AlignCenter)
    main_window.placeholder.setStyleSheet("color:#555; font-size:14px;")

    central = QWidget()
    central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    c_l = QVBoxLayout(central)
    c_l.setContentsMargins(0, 0, 0, 0)
    c_l.addWidget(main_window.placeholder, 1)
    main_window.setCentralWidget(central)
    main_window.central_container = central

    main_window.dock_color = color_dock
    main_window.dock_scatter = scatter_dock
    main_window.dock_hist = hist_dock
    main_window.dock_edge = edge_dock
    main_window.dock_gray = gray_dock
    main_window.dock_binary = binary_dock
    main_window.dock_ternary = ternary_dock
    main_window.dock_saliency = saliency_dock
    main_window.dock_focus = focus_dock
    main_window.dock_squint = squint_dock
    main_window.dock_vectorscope = vectorscope_dock
    main_window._right_stack_order = [
        main_window.dock_scatter,
        main_window.dock_edge,
        main_window.dock_gray,
        main_window.dock_binary,
        main_window.dock_ternary,
        main_window.dock_saliency,
        main_window.dock_focus,
        main_window.dock_squint,
        main_window.dock_vectorscope,
    ]
    main_window._dock_map = {
        "dock_color": main_window.dock_color,
        "dock_scatter": main_window.dock_scatter,
        "dock_hist": main_window.dock_hist,
        "dock_edge": main_window.dock_edge,
        "dock_gray": main_window.dock_gray,
        "dock_binary": main_window.dock_binary,
        "dock_ternary": main_window.dock_ternary,
        "dock_saliency": main_window.dock_saliency,
        "dock_focus": main_window.dock_focus,
        "dock_squint": main_window.dock_squint,
        "dock_vectorscope": main_window.dock_vectorscope,
    }
    main_window._dock_actions = {
        "dock_color": main_window.act_color,
        "dock_scatter": main_window.act_scatter,
        "dock_hist": main_window.act_hist,
        "dock_edge": main_window.act_edge,
        "dock_gray": main_window.act_gray,
        "dock_binary": main_window.act_binary,
        "dock_ternary": main_window.act_ternary,
        "dock_saliency": main_window.act_saliency,
        "dock_focus": main_window.act_focus,
        "dock_squint": main_window.act_squint,
        "dock_vectorscope": main_window.act_vectorscope,
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
        _configure_view_dock(main_window, d)

    # 初期配置: 左にカラー、右側にビュー群、下にヒストグラム
    # ユーザーが自由に3段以上へ再配置できるよう、tabifyは行わない
    main_window.addDockWidget(Qt.LeftDockWidgetArea, color_dock)
    main_window.addDockWidget(Qt.RightDockWidgetArea, scatter_dock)
    main_window.splitDockWidget(scatter_dock, edge_dock, Qt.Vertical)
    main_window.splitDockWidget(edge_dock, gray_dock, Qt.Vertical)
    main_window.splitDockWidget(gray_dock, binary_dock, Qt.Vertical)
    main_window.splitDockWidget(binary_dock, ternary_dock, Qt.Vertical)
    main_window.splitDockWidget(ternary_dock, saliency_dock, Qt.Vertical)
    main_window.splitDockWidget(saliency_dock, focus_dock, Qt.Vertical)
    main_window.splitDockWidget(focus_dock, squint_dock, Qt.Vertical)
    main_window.splitDockWidget(squint_dock, vectorscope_dock, Qt.Vertical)
    main_window.addDockWidget(Qt.BottomDockWidgetArea, hist_dock)
    main_window.resizeDocks([color_dock, scatter_dock, edge_dock], [700, 700, 700], Qt.Horizontal)
    main_window.resizeDocks(
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
