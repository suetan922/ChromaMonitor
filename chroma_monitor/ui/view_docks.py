"""ビュー用ドックの構築処理。"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..util import constants as C
from ..views import (
    BinaryView,
    ChannelHistogram,
    ColorWheelWidget,
    EdgeView,
    FocusPeakingView,
    GrayscaleView,
    RgbHistogramWidget,
    SaliencyView,
    ScatterRasterWidget,
    SquintView,
    TernaryView,
    VectorScopeView,
)


class UniformMinDockWidget(QDockWidget):

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)


class ZeroMinContainer(QWidget):

    def minimumSizeHint(self):
        return QSize(0, 0)


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
    dock = UniformMinDockWidget(title, main_window)
    dock.setObjectName(object_name)
    dock.setWidget(content)
    dock.setAllowedAreas(Qt.AllDockWidgetAreas)
    main_window.addDockWidget(area, dock)
    return dock


def _configure_view_dock(main_window, dock: QDockWidget) -> None:
    # 各ドックの共通機能（移動/フロート/閉じる等）を設定する。
    dock.setFeatures(
        QDockWidget.DockWidgetMovable
        | QDockWidget.DockWidgetFloatable
        | QDockWidget.DockWidgetClosable
    )
    dock.setAllowedAreas(Qt.AllDockWidgetAreas)
    dock.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    dock.visibilityChanged.connect(main_window.update_placeholder)
    dock.visibilityChanged.connect(main_window.sync_window_menu_checks)
    dock.visibilityChanged.connect(main_window._sync_tabbed_dock_title_bars)

    for signal in (dock.topLevelChanged, dock.dockLocationChanged):
        # 配置が変わったときだけ自動保存を予約する。
        signal.connect(lambda *_args, mw=main_window: mw._schedule_layout_autosave())
        signal.connect(main_window._sync_tabbed_dock_title_bars)


def _register_docks(
    main_window,
    dock_specs: list[tuple[str, QDockWidget, Qt.DockWidgetArea]],
) -> None:
    # dock_* 属性 / _dock_map / 既定エリアを同時に構築して重複管理を避ける。
    main_window._dock_map = {}
    main_window._dock_default_areas = {}
    for name, dock, default_area in dock_specs:
        setattr(main_window, name, dock)
        main_window._dock_map[name] = dock
        main_window._dock_default_areas[name] = default_area


def _build_dock_actions(main_window) -> dict[str, object]:
    # act_<dock名> ルールで対応アクションを解決する。
    dock_actions = {}
    for dock_name in main_window._dock_map:
        suffix = dock_name[5:] if dock_name.startswith("dock_") else dock_name
        action = getattr(main_window, f"act_{suffix}", None)
        if action is not None:
            dock_actions[dock_name] = action
    return dock_actions


def setup_view_docks(main_window) -> None:
    # 各解析ビューウィジェットを生成する。
    main_window.wheel = ColorWheelWidget()
    main_window.wheel.setStyleSheet("background:#FFFFFF; border:1px solid #CCC;")

    main_window.scatter = ScatterRasterWidget()
    main_window.chk_scatter_hue_filter = QCheckBox("色相フィルター")
    main_window.chk_scatter_hue_filter.setChecked(C.DEFAULT_SCATTER_HUE_FILTER_ENABLED)
    main_window.chk_scatter_hue_filter.setMinimumHeight(0)
    main_window.chk_scatter_hue_filter.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    main_window.slider_scatter_hue_center = QSlider(Qt.Vertical)
    main_window.slider_scatter_hue_center.setRange(C.SCATTER_HUE_MIN, C.SCATTER_HUE_MAX)
    main_window.slider_scatter_hue_center.setSingleStep(1)
    main_window.slider_scatter_hue_center.setPageStep(10)
    main_window.slider_scatter_hue_center.setValue(C.DEFAULT_SCATTER_HUE_CENTER)
    main_window.slider_scatter_hue_center.setFixedWidth(32)
    main_window.slider_scatter_hue_center.setMinimumHeight(0)
    main_window.slider_scatter_hue_center.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
    main_window.slider_scatter_hue_center.setStyleSheet(
        "QSlider::groove:vertical {"
        "border: 1px solid #c4c9d4;"
        "width: 10px;"
        "margin: 8px 0;"
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
        "margin: 0 -5px;"
        "border-radius: 7px;"
        "}"
    )
    main_window.lbl_scatter_hue_center = QLabel("H 0")
    main_window.lbl_scatter_hue_center.setAlignment(Qt.AlignCenter)
    main_window.lbl_scatter_hue_center.setStyleSheet("color:#334155; font-size:11px;")
    main_window.lbl_scatter_hue_center.setMinimumHeight(0)
    main_window.lbl_scatter_hue_center.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    # バケット幅を揃えて視覚的スケールを統一
    main_window.hist_h = ChannelHistogram("色相", 180, 179, C.H_COLOR, bucket=2)
    main_window.hist_s = ChannelHistogram("彩度", 256, 255, C.S_COLOR, bucket=2)
    main_window.hist_v = ChannelHistogram("明度", 256, 255, C.V_COLOR, bucket=2)
    main_window.rgb_hist_view = RgbHistogramWidget()
    main_window.rgb_hist_view.set_display_mode(C.DEFAULT_RGB_HIST_MODE)

    main_window._last_top_bars = []
    main_window._top_bar_render_key = None
    main_window.lbl_top5_title = QLabel(C.TOP_COLORS_TITLE)
    main_window.lbl_top5_title.setStyleSheet("color:#111; font-size:12px; font-weight:600;")
    main_window.lbl_top5_title.setMinimumHeight(0)
    main_window.lbl_top5_title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)

    main_window.top_colors_bar = QLabel()
    main_window.top_colors_bar.setMinimumHeight(0)
    main_window.top_colors_bar.setMaximumHeight(C.TOP_COLOR_BAR_HEIGHT)
    main_window.top_colors_bar.setMinimumWidth(0)
    main_window.top_colors_bar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    main_window.top_colors_bar.setScaledContents(False)

    main_window.lbl_warmcool = QLabel("暖色: -   寒色: -   その他: -")
    main_window.lbl_warmcool.setStyleSheet("color:#111; font-size:12px;")
    main_window.lbl_warmcool.setWordWrap(True)
    main_window.lbl_warmcool.setMinimumHeight(0)
    main_window.lbl_warmcool.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

    color_widget = QWidget()
    cw_l = QVBoxLayout(color_widget)
    cw_l.setContentsMargins(2, 2, 2, 2)
    cw_l.setSpacing(2)
    cw_l.addWidget(main_window.wheel, 1)
    cw_l.addWidget(main_window.lbl_top5_title)
    cw_l.addWidget(main_window.top_colors_bar)
    cw_l.addWidget(main_window.lbl_warmcool)
    color_dock = _create_dock(main_window, "色相環", "dock_color", color_widget)

    scatter_container = QWidget()
    sc_l = QHBoxLayout(scatter_container)
    sc_l.setContentsMargins(6, 6, 6, 6)
    sc_l.setSpacing(8)
    sc_l.addWidget(main_window.scatter, 1)

    scatter_controls = ZeroMinContainer()
    scatter_controls.setMinimumHeight(0)
    scatter_controls.setMinimumWidth(34)
    scatter_controls.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
    sctrl_l = QVBoxLayout(scatter_controls)
    sctrl_l.setContentsMargins(0, 0, 0, 0)
    sctrl_l.setSpacing(4)
    # 余白:スライダー:余白 を 2:6:2 にして、縦領域の約6割をスライダーへ配分する。
    sctrl_l.addStretch(2)
    sctrl_l.addWidget(main_window.chk_scatter_hue_filter, 0, Qt.AlignHCenter)
    sctrl_l.addWidget(main_window.slider_scatter_hue_center, 6, Qt.AlignHCenter)
    sctrl_l.addWidget(main_window.lbl_scatter_hue_center, 0, Qt.AlignHCenter)
    sctrl_l.addStretch(2)
    sc_l.addWidget(scatter_controls, 0)
    scatter_dock = _create_dock(main_window, "S-V 散布図", "dock_scatter", scatter_container)

    hist_container = QWidget()
    hg_l = QHBoxLayout(hist_container)
    hg_l.setContentsMargins(4, 4, 4, 4)
    hg_l.setSpacing(10)
    # 3チャネルを等比で並べ、片側だけ極端に潰れるのを防ぐ。
    hg_l.addWidget(main_window.hist_h, 1)
    hg_l.addWidget(main_window.hist_s, 1)
    hg_l.addWidget(main_window.hist_v, 1)
    hist_dock = _create_dock(
        main_window,
        "H/S/V ヒストグラム",
        "dock_hist",
        hist_container,
        area=Qt.BottomDockWidgetArea,
    )

    rgb_hist_container = QWidget()
    rg_l = QVBoxLayout(rgb_hist_container)
    rg_l.setContentsMargins(4, 4, 4, 4)
    rg_l.setSpacing(0)
    rg_l.addWidget(main_window.rgb_hist_view, 1)
    rgb_hist_dock = _create_dock(
        main_window,
        "R/G/B ヒストグラム",
        "dock_rgb_hist",
        rgb_hist_container,
        area=Qt.BottomDockWidgetArea,
    )
    rgb_hist_dock.setVisible(False)

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
    vs_l.setSpacing(2)
    vs_l.addWidget(main_window.vectorscope_view, 1)
    main_window.lbl_vectorscope_warning = QLabel("高彩度警告: 入力待ち")
    main_window.lbl_vectorscope_warning.setStyleSheet("color:#8b97a8;")
    main_window.lbl_vectorscope_warning.setMinimumHeight(0)
    main_window.lbl_vectorscope_warning.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
    vs_l.addWidget(main_window.lbl_vectorscope_warning, 0)
    vectorscope_dock = _create_dock(
        main_window, "ベクトルスコープ", "dock_vectorscope", vectorscope_container
    )

    main_window.setDockOptions(
        QMainWindow.AnimatedDocks | QMainWindow.AllowTabbedDocks | QMainWindow.AllowNestedDocks
    )
    for area in (
        Qt.LeftDockWidgetArea,
        Qt.RightDockWidgetArea,
        Qt.TopDockWidgetArea,
        Qt.BottomDockWidgetArea,
    ):
        main_window.setTabPosition(area, QTabWidget.North)

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

    _register_docks(
        main_window,
        [
            ("dock_color", color_dock, Qt.LeftDockWidgetArea),
            ("dock_scatter", scatter_dock, Qt.RightDockWidgetArea),
            ("dock_hist", hist_dock, Qt.BottomDockWidgetArea),
            ("dock_rgb_hist", rgb_hist_dock, Qt.BottomDockWidgetArea),
            ("dock_edge", edge_dock, Qt.RightDockWidgetArea),
            ("dock_gray", gray_dock, Qt.RightDockWidgetArea),
            ("dock_binary", binary_dock, Qt.RightDockWidgetArea),
            ("dock_ternary", ternary_dock, Qt.RightDockWidgetArea),
            ("dock_saliency", saliency_dock, Qt.RightDockWidgetArea),
            ("dock_focus", focus_dock, Qt.RightDockWidgetArea),
            ("dock_squint", squint_dock, Qt.RightDockWidgetArea),
            ("dock_vectorscope", vectorscope_dock, Qt.RightDockWidgetArea),
        ],
    )
    main_window._dock_actions = _build_dock_actions(main_window)
    # 画像入力を必要とするビューの更新ルールを一元管理する。
    main_window._image_update_targets = [
        (main_window.dock_edge, main_window.edge_view.update_edge, None),
        (main_window.dock_gray, main_window.gray_view.update_gray, None),
        (main_window.dock_binary, main_window.binary_view.update_binary, None),
        (main_window.dock_ternary, main_window.ternary_view.update_ternary, None),
        (main_window.dock_rgb_hist, main_window.rgb_hist_view.update_from_bgr, None),
        (main_window.dock_saliency, main_window.saliency_view.update_saliency, None),
        (main_window.dock_focus, main_window.focus_peaking_view.update_focus, None),
        (main_window.dock_squint, main_window.squint_view.update_squint, None),
        (
            main_window.dock_vectorscope,
            main_window.vectorscope_view.update_scope,
            main_window._update_vectorscope_warning_label,
        ),
    ]

    for d in main_window._dock_map.values():
        _configure_view_dock(main_window, d)

    # 初期配置: 左にカラー、右側にビュー群、下にヒストグラム。
    # タブ固定を避け、自由な多段再配置を優先する。
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
    main_window.addDockWidget(Qt.BottomDockWidgetArea, rgb_hist_dock)
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
    main_window._sync_tabbed_dock_title_bars()
