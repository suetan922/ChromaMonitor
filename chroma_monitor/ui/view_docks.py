"""ビュー用ドックの構築処理。"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QSplitter,
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

_H_COLOR = QColor(220, 90, 90)
_S_COLOR = QColor(90, 170, 90)
_V_COLOR = QColor(80, 140, 240)


class UniformMinDockWidget(QDockWidget):

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_WIDTH, C.VIEW_MIN_HEIGHT)


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


def _clear_attach_on_show_flag(dock: QDockWidget, visible: bool) -> None:
    if visible and getattr(dock, "_attach_on_next_show", False):
        dock._attach_on_next_show = False


def _restore_from_snapshot_if_visible(main_window, dock: QDockWidget, visible: bool) -> None:
    if visible:
        main_window._restore_dock_from_snapshot(dock)


def _configure_view_dock(main_window, dock: QDockWidget) -> None:
    # 各ドックの共通機能（移動/フロート/閉じる等）を設定する。
    dock.setFeatures(
        QDockWidget.DockWidgetMovable
        | QDockWidget.DockWidgetFloatable
        | QDockWidget.DockWidgetClosable
    )
    dock.setAllowedAreas(Qt.AllDockWidgetAreas)
    dock.setMinimumSize(C.VIEW_MIN_WIDTH, C.VIEW_MIN_HEIGHT)

    dock.visibilityChanged.connect(main_window.update_placeholder)
    dock.visibilityChanged.connect(main_window.sync_window_menu_checks)
    dock.visibilityChanged.connect(main_window._sync_tabbed_dock_title_bars)
    dock.visibilityChanged.connect(
        lambda v, d=dock: _clear_attach_on_show_flag(d, bool(v))
    )
    dock.visibilityChanged.connect(
        lambda v, mw=main_window, d=dock: _restore_from_snapshot_if_visible(mw, d, bool(v))
    )

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
    main_window._dock_name_by_object = {}
    for name, dock, default_area in dock_specs:
        setattr(main_window, name, dock)
        main_window._dock_map[name] = dock
        main_window._dock_default_areas[name] = default_area
        main_window._dock_name_by_object[dock] = name


def _build_dock_actions(main_window) -> dict[str, object]:
    # act_<dock名> ルールで対応アクションを解決する。
    dock_actions = {}
    for dock_name in main_window._dock_map:
        suffix = dock_name[5:] if dock_name.startswith("dock_") else dock_name
        action = getattr(main_window, f"act_{suffix}", None)
        if action is not None:
            dock_actions[dock_name] = action
    return dock_actions


def _detach_initially_hidden_docks(main_window) -> None:
    # 既定で非表示のドックはレイアウトから外す。
    # 再表示時は toggle_dock 側の共通追加処理（エリア内タブ化）を使う。
    for name, dock in main_window._dock_map.items():
        action = main_window._dock_actions.get(name)
        if action is None or action.isChecked():
            continue
        if dock.isFloating():
            dock.setFloating(False)
        dock.setVisible(False)
        main_window.removeDockWidget(dock)
        dock._attach_on_next_show = True


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
    main_window.hist_h = ChannelHistogram("色相", 180, 179, _H_COLOR, bucket=2)
    main_window.hist_s = ChannelHistogram("彩度", 256, 255, _S_COLOR, bucket=2)
    main_window.hist_v = ChannelHistogram("明度", 256, 255, _V_COLOR, bucket=2)
    main_window.rgb_hist_view = RgbHistogramWidget()
    main_window.rgb_hist_view.set_display_mode(C.DEFAULT_RGB_HIST_MODE)

    main_window._last_top_bars = []
    main_window._top_bar_render_key = None
    main_window._color_detail_has_selection = False
    main_window._color_detail_merge_complement = False
    main_window._color_detail_show_info = True
    main_window.lbl_color_band_title = QLabel(C.TOP_COLORS_TITLE)
    main_window.lbl_color_band_title.setStyleSheet("color:#111; font-size:12px; font-weight:600;")
    main_window.lbl_color_band_title.setMinimumHeight(0)
    main_window.lbl_color_band_title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)

    main_window.top_colors_bar = QLabel()
    # バーは常に見えるよう、固定高さ + 横方向のみ伸縮にする。
    main_window.top_colors_bar.setMinimumHeight(C.TOP_COLOR_BAR_HEIGHT)
    main_window.top_colors_bar.setMaximumHeight(C.TOP_COLOR_BAR_HEIGHT)
    main_window.top_colors_bar.setMinimumWidth(0)
    main_window.top_colors_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    main_window.top_colors_bar.setScaledContents(False)

    main_window.lbl_warmcool = QLabel("暖色: -   寒色: -   その他: -")
    main_window.lbl_warmcool.setStyleSheet("color:#111; font-size:12px;")
    main_window.lbl_warmcool.setWordWrap(True)
    main_window.lbl_warmcool.setMinimumHeight(0)
    main_window.lbl_warmcool.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.list_color_chips = QListWidget()
    main_window.list_color_chips.setMinimumHeight(0)
    main_window.list_color_chips.setMinimumWidth(0)
    main_window.list_color_chips.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    main_window.list_color_chips.setSelectionMode(QAbstractItemView.SingleSelection)
    main_window.list_color_chips.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    main_window.list_color_chips.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    main_window.list_color_chips.setSpacing(2)
    main_window.list_color_chips.setStyleSheet(
        "QListWidget { background:#ffffff; border:1px solid #d6dbe4; border-radius:6px; }"
        "QListWidget::item { padding:2px 4px; }"
        "QListWidget::item:selected { border:1px solid #2563eb; }"
    )

    main_window.lbl_color_detail_title = QLabel("配色の参考情報")
    main_window.lbl_color_detail_title.setStyleSheet("color:#111; font-size:12px; font-weight:600;")
    main_window.lbl_color_detail_title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    main_window.lbl_color_detail_info = QLabel("一覧から色を選択してください。")
    main_window.lbl_color_detail_info.setStyleSheet("color:#111; font-size:12px;")
    main_window.lbl_color_detail_info.setWordWrap(True)
    main_window.lbl_color_detail_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.lbl_color_harmony_info = QLabel("色彩調和")
    main_window.lbl_color_harmony_info.setStyleSheet("color:#111; font-size:12px;")
    main_window.lbl_color_harmony_info.setWordWrap(True)
    main_window.lbl_color_harmony_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.color_harmony_preview = QWidget()
    main_window.color_harmony_preview_layout = QHBoxLayout(main_window.color_harmony_preview)
    main_window.color_harmony_preview_layout.setContentsMargins(0, 0, 0, 0)
    main_window.color_harmony_preview_layout.setSpacing(6)
    main_window.color_harmony_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.lbl_color_complement_info = QLabel("補色")
    main_window.lbl_color_complement_info.setStyleSheet("color:#111; font-size:12px;")
    main_window.lbl_color_complement_info.setWordWrap(True)
    main_window.lbl_color_complement_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.color_complement_preview = QWidget()
    main_window.color_complement_preview_layout = QHBoxLayout(main_window.color_complement_preview)
    main_window.color_complement_preview_layout.setContentsMargins(0, 0, 0, 0)
    main_window.color_complement_preview_layout.setSpacing(6)
    main_window.color_complement_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.lbl_color_methods_info = QLabel("配色手法")
    main_window.lbl_color_methods_info.setStyleSheet("color:#111; font-size:12px;")
    main_window.lbl_color_methods_info.setWordWrap(True)
    main_window.lbl_color_methods_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.color_methods_preview = QWidget()
    main_window.color_methods_preview_layout = QVBoxLayout(main_window.color_methods_preview)
    main_window.color_methods_preview_layout.setContentsMargins(0, 0, 0, 0)
    main_window.color_methods_preview_layout.setSpacing(6)
    main_window.color_methods_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # 詳細表示はカテゴリごとにグルーピングして、視認しやすい間隔を確保する。
    main_window.color_harmony_section = QWidget()
    harmony_section_l = QVBoxLayout(main_window.color_harmony_section)
    harmony_section_l.setContentsMargins(0, 8, 0, 0)
    harmony_section_l.setSpacing(3)
    harmony_section_l.addWidget(main_window.lbl_color_harmony_info)
    harmony_section_l.addWidget(main_window.color_harmony_preview)

    main_window.color_complement_section = QWidget()
    complement_section_l = QVBoxLayout(main_window.color_complement_section)
    complement_section_l.setContentsMargins(0, 8, 0, 0)
    complement_section_l.setSpacing(3)
    complement_section_l.addWidget(main_window.lbl_color_complement_info)
    complement_section_l.addWidget(main_window.color_complement_preview)

    main_window.color_methods_section = QWidget()
    methods_section_l = QVBoxLayout(main_window.color_methods_section)
    methods_section_l.setContentsMargins(0, 8, 0, 0)
    methods_section_l.setSpacing(3)
    methods_section_l.addWidget(main_window.lbl_color_methods_info)
    methods_section_l.addWidget(main_window.color_methods_preview)

    detail_panel = QWidget()
    detail_l = QVBoxLayout(detail_panel)
    detail_l.setContentsMargins(0, 0, 0, 0)
    detail_l.setSpacing(4)
    detail_l.addWidget(main_window.lbl_color_detail_title)
    detail_l.addWidget(main_window.lbl_color_detail_info)
    detail_l.addWidget(main_window.color_harmony_section)
    detail_l.addWidget(main_window.color_complement_section)
    detail_l.addWidget(main_window.color_methods_section)
    detail_l.addStretch(1)

    main_window.color_detail_scroll = QScrollArea()
    main_window.color_detail_scroll.setWidgetResizable(True)
    main_window.color_detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    main_window.color_detail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    main_window.color_detail_scroll.setWidget(detail_panel)
    main_window.color_detail_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    main_window.color_detail_scroll.setMinimumHeight(0)
    main_window.color_detail_scroll.setMinimumWidth(0)
    main_window.color_detail_scroll.setVisible(False)

    main_window.color_band_splitter = QSplitter(Qt.Vertical)
    main_window.color_band_splitter.setChildrenCollapsible(True)
    main_window.color_band_splitter.setMinimumSize(0, 0)
    main_window.color_band_splitter.addWidget(main_window.list_color_chips)
    main_window.color_band_splitter.addWidget(main_window.color_detail_scroll)
    main_window.color_band_splitter.setStretchFactor(0, 3)
    main_window.color_band_splitter.setStretchFactor(1, 2)
    main_window.color_band_splitter.setSizes([220, 180])
    main_window.color_band_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    color_widget = QWidget()
    cw_l = QVBoxLayout(color_widget)
    cw_l.setContentsMargins(2, 2, 2, 2)
    cw_l.setSpacing(2)
    cw_l.addWidget(main_window.wheel, 1)
    color_dock = _create_dock(main_window, "色相環", "dock_color", color_widget)

    # カラー割合は内部要素が多いため、コンテナの最小ヒントを 0 にして
    # ドック共通最小サイズ定数でのみ下限を管理する。
    color_band_widget = ZeroMinContainer()
    cb_l = QVBoxLayout(color_band_widget)
    cb_l.setContentsMargins(6, 6, 6, 6)
    cb_l.setSpacing(4)
    cb_l.addWidget(main_window.lbl_color_band_title)
    cb_l.addWidget(main_window.top_colors_bar)
    cb_l.addWidget(main_window.lbl_warmcool)
    cb_l.addWidget(main_window.color_band_splitter, 1)
    color_band_widget.setMinimumSize(0, 0)
    color_band_dock = _create_dock(
        main_window,
        "カラー割合",
        "dock_color_band",
        color_band_widget,
        area=Qt.LeftDockWidgetArea,
    )
    # 再表示時は色相環ドックへ優先的にタブ合流させる。
    color_band_dock._preferred_tab_anchor_name = "dock_color"

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
        area=Qt.RightDockWidgetArea,
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
            ("dock_color_band", color_band_dock, Qt.LeftDockWidgetArea),
            ("dock_scatter", scatter_dock, Qt.RightDockWidgetArea),
            ("dock_hist", hist_dock, Qt.BottomDockWidgetArea),
            ("dock_rgb_hist", rgb_hist_dock, Qt.RightDockWidgetArea),
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
    # カラー割合は色相環と同一グループで開き、単独枠として分離しない。
    main_window.tabifyDockWidget(color_dock, color_band_dock)
    color_dock.raise_()
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
    _detach_initially_hidden_docks(main_window)
    main_window._sync_tabbed_dock_title_bars()
