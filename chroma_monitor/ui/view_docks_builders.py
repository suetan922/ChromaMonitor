"""ビュー用ドックの個別ビュー生成とドック生成。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..util import constants as C
from ..views.color_scatter import ColorWheelWidget, ScatterRasterWidget
from ..views.edge_view import EdgeView
from ..views.focus_peaking_view import FocusPeakingView
from ..views.histogram import ChannelHistogram, RgbHistogramWidget
from ..views.mirror_view import MirrorView
from ..views.saliency_view import SaliencyView
from ..views.squint_view import SquintView
from ..views.tonal_views import BinaryView, GrayscaleView, TernaryView
from ..views.vectorscope_view import VectorScopeView
from .view_docks_common import (
    ZeroMinContainer,
    build_dock_actions,
    build_single_view_container,
    configure_view_dock,
    create_dock,
    create_info_label,
    register_docks,
)

_H_COLOR = QColor(220, 90, 90)
_S_COLOR = QColor(90, 170, 90)
_V_COLOR = QColor(80, 140, 240)
_COLOR_BAND_WARMCOOL_BOTTOM_SPACING = 6
_SINGLE_VIEW_DOCK_SPECS = (
    ("dock_edge", "edge_view", EdgeView, "エッジ検出", "update_edge", 190),
    ("dock_gray", "gray_view", GrayscaleView, "グレースケール", "update_gray", 170),
    ("dock_mirror", "mirror_view", MirrorView, "反転表示", "update_mirror", 170),
    ("dock_binary", "binary_view", BinaryView, "2値化", "update_binary", 160),
    ("dock_ternary", "ternary_view", TernaryView, "3値化", "update_ternary", 170),
    ("dock_saliency", "saliency_view", SaliencyView, "サリエンシーマップ", "update_saliency", 170),
    (
        "dock_focus",
        "focus_peaking_view",
        FocusPeakingView,
        "フォーカスピーキング",
        "update_focus",
        170,
    ),
    ("dock_squint", "squint_view", SquintView, "スクイント表示", "update_squint", 160),
)


def _build_color_band_detail_widgets(main_window) -> None:
    """配色比率ドック内の詳細表示ウィジェットを生成する。"""
    main_window._last_top_bars = []
    main_window._top_bar_render_key = None
    main_window._last_top_bars_key = None
    main_window._color_detail_state = None
    main_window.top_colors_bar = QLabel()
    main_window.top_colors_bar.setMinimumHeight(C.TOP_COLOR_BAR_HEIGHT)
    main_window.top_colors_bar.setMaximumHeight(C.TOP_COLOR_BAR_HEIGHT)
    main_window.top_colors_bar.setMinimumWidth(0)
    main_window.top_colors_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    main_window.top_colors_bar.setScaledContents(False)

    main_window.lbl_warmcool = QLabel("暖色: -   寒色: -   その他: -")
    main_window.lbl_warmcool.setProperty("chromaRole", "detailText")
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
    main_window.list_color_chips.setProperty("chromaRole", "colorChipList")

    main_window.lbl_color_detail_title = QLabel("配色の参考情報")
    main_window.lbl_color_detail_title.setProperty("chromaRole", "detailTitle")
    main_window.lbl_color_detail_title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    main_window.lbl_color_detail_info = QLabel("一覧から色を選択してください。")
    main_window.lbl_color_detail_info.setProperty("chromaRole", "detailText")
    main_window.lbl_color_detail_info.setWordWrap(True)
    main_window.lbl_color_detail_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.lbl_color_harmony_info = create_info_label("色彩調和")
    main_window.color_harmony_preview = QWidget()
    main_window.color_harmony_preview_layout = QHBoxLayout(main_window.color_harmony_preview)
    main_window.color_harmony_preview_layout.setContentsMargins(0, 0, 0, 0)
    main_window.color_harmony_preview_layout.setSpacing(6)
    main_window.color_harmony_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.lbl_color_complement_info = create_info_label("補色")
    main_window.color_complement_preview = QWidget()
    main_window.color_complement_preview_layout = QHBoxLayout(main_window.color_complement_preview)
    main_window.color_complement_preview_layout.setContentsMargins(0, 0, 0, 0)
    main_window.color_complement_preview_layout.setSpacing(6)
    main_window.color_complement_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.lbl_color_methods_info = create_info_label("配色手法")
    main_window.color_methods_preview = QWidget()
    main_window.color_methods_preview_layout = QVBoxLayout(main_window.color_methods_preview)
    main_window.color_methods_preview_layout.setContentsMargins(0, 0, 0, 0)
    main_window.color_methods_preview_layout.setSpacing(6)
    main_window.color_methods_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

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


def _build_color_and_histogram_docks(main_window) -> tuple[QDockWidget, QDockWidget, QDockWidget, QDockWidget]:
    """色相環、配色比率、ヒストグラム系ドックを生成する。"""
    main_window.wheel = ColorWheelWidget()
    main_window.hist_h = ChannelHistogram("色相", 180, 179, _H_COLOR, bucket=2)
    main_window.hist_s = ChannelHistogram("彩度", 256, 255, _S_COLOR, bucket=2)
    main_window.hist_v = ChannelHistogram("明度", 256, 255, _V_COLOR, bucket=2)
    main_window.rgb_hist_view = RgbHistogramWidget()
    main_window.rgb_hist_view.set_display_mode(C.DEFAULT_RGB_HIST_MODE)
    _build_color_band_detail_widgets(main_window)

    color_widget = QWidget()
    color_layout = QVBoxLayout(color_widget)
    color_layout.setContentsMargins(2, 2, 2, 2)
    color_layout.setSpacing(2)
    color_layout.addWidget(main_window.wheel, 1)
    color_dock = create_dock(main_window, "色相環", "dock_color", color_widget)

    color_band_widget = ZeroMinContainer()
    color_band_layout = QVBoxLayout(color_band_widget)
    color_band_layout.setContentsMargins(6, 6, 6, 6)
    color_band_layout.setSpacing(4)
    color_band_layout.addWidget(main_window.top_colors_bar)
    color_band_layout.addWidget(main_window.lbl_warmcool)
    color_band_layout.addSpacing(_COLOR_BAND_WARMCOOL_BOTTOM_SPACING)
    color_band_layout.addWidget(main_window.color_band_splitter, 1)
    color_band_widget.setMinimumSize(0, 0)
    color_band_dock = create_dock(
        main_window,
        "配色比率",
        "dock_color_band",
        color_band_widget,
    )
    color_band_dock._preferred_tab_anchor_name = "dock_color"

    hist_container = QWidget()
    hist_layout = QHBoxLayout(hist_container)
    hist_layout.setContentsMargins(4, 4, 4, 4)
    hist_layout.setSpacing(10)
    hist_layout.addWidget(main_window.hist_h, 1)
    hist_layout.addWidget(main_window.hist_s, 1)
    hist_layout.addWidget(main_window.hist_v, 1)
    hist_dock = create_dock(main_window, "H/S/V ヒストグラム", "dock_hist", hist_container)
    hist_dock._preferred_tab_anchor_name = "dock_color"

    rgb_hist_container = QWidget()
    rgb_hist_layout = QVBoxLayout(rgb_hist_container)
    rgb_hist_layout.setContentsMargins(4, 4, 4, 4)
    rgb_hist_layout.setSpacing(0)
    rgb_hist_layout.addWidget(main_window.rgb_hist_view, 1)
    rgb_hist_dock = create_dock(
        main_window,
        "R/G/B ヒストグラム",
        "dock_rgb_hist",
        rgb_hist_container,
    )
    rgb_hist_dock._preferred_tab_anchor_name = "dock_color"
    return color_dock, color_band_dock, hist_dock, rgb_hist_dock


def _build_scatter_dock(main_window) -> QDockWidget:
    """散布図ドックとその操作部を生成する。"""
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
    main_window.slider_scatter_hue_center.setObjectName("scatterHueSlider")
    main_window.lbl_scatter_hue_center = QLabel("H 0")
    main_window.lbl_scatter_hue_center.setObjectName("scatterHueValue")
    main_window.lbl_scatter_hue_center.setAlignment(Qt.AlignCenter)
    main_window.lbl_scatter_hue_center.setMinimumHeight(0)
    main_window.lbl_scatter_hue_center.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    scatter_container = QWidget()
    scatter_layout = QHBoxLayout(scatter_container)
    scatter_layout.setContentsMargins(6, 6, 6, 6)
    scatter_layout.setSpacing(8)
    scatter_layout.addWidget(main_window.scatter, 1)

    scatter_controls = ZeroMinContainer()
    scatter_controls.setMinimumHeight(0)
    scatter_controls.setMinimumWidth(34)
    scatter_controls.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
    controls_layout = QVBoxLayout(scatter_controls)
    controls_layout.setContentsMargins(0, 0, 0, 0)
    controls_layout.setSpacing(4)
    controls_layout.addStretch(2)
    controls_layout.addWidget(main_window.chk_scatter_hue_filter, 0, Qt.AlignHCenter)
    controls_layout.addWidget(main_window.slider_scatter_hue_center, 6, Qt.AlignHCenter)
    controls_layout.addWidget(main_window.lbl_scatter_hue_center, 0, Qt.AlignHCenter)
    controls_layout.addStretch(2)
    scatter_layout.addWidget(scatter_controls, 0)

    scatter_dock = create_dock(main_window, "S-V 散布図", "dock_scatter", scatter_container)
    scatter_dock.topLevelChanged.connect(lambda _visible, w=main_window.scatter: w.request_layout_sync())
    scatter_dock.dockLocationChanged.connect(
        lambda _area, w=main_window.scatter: w.request_layout_sync()
    )
    return scatter_dock


def _build_single_view_docks(main_window) -> dict[str, QDockWidget]:
    """単独ビュー系ドックをまとめて生成する。"""

    def _init_single_view_dock(
        view_attr: str,
        view_factory: type[QWidget],
        *,
        title: str,
        object_name: str,
    ) -> QDockWidget:
        view = view_factory()
        setattr(main_window, view_attr, view)
        return create_dock(
            main_window,
            title,
            object_name,
            build_single_view_container(view),
        )

    docks: dict[str, QDockWidget] = {}
    for dock_name, view_attr, view_factory, title, _update_method, _height in _SINGLE_VIEW_DOCK_SPECS:
        docks[dock_name] = _init_single_view_dock(
            view_attr,
            view_factory,
            title=title,
            object_name=dock_name,
        )
    return docks


def _build_vectorscope_dock(main_window) -> QDockWidget:
    """ベクトルスコープドックを生成する。"""
    main_window.vectorscope_view = VectorScopeView()
    vectorscope_container = QWidget()
    vectorscope_layout = QVBoxLayout(vectorscope_container)
    vectorscope_layout.setContentsMargins(6, 6, 6, 6)
    vectorscope_layout.setSpacing(2)
    vectorscope_layout.addWidget(main_window.vectorscope_view, 1)
    main_window.lbl_vectorscope_warning = QLabel("高彩度警告: 入力待ち")
    main_window.lbl_vectorscope_warning.setProperty("chromaRole", "vectorscopeWarning")
    main_window.lbl_vectorscope_warning.setProperty("chromaWarnLevel", "muted")
    main_window.lbl_vectorscope_warning.setMinimumHeight(0)
    main_window.lbl_vectorscope_warning.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
    vectorscope_layout.addWidget(main_window.lbl_vectorscope_warning, 0)
    return create_dock(
        main_window,
        "ベクトルスコープ",
        "dock_vectorscope",
        vectorscope_container,
    )


def _configure_update_targets(main_window, single_view_docks: dict[str, QDockWidget]) -> None:
    """画像更新対象ビュー一覧を構築する。"""
    single_updates = {
        dock_name: (
            single_view_docks[dock_name],
            getattr(getattr(main_window, view_attr), update_method),
            None,
        )
        for dock_name, view_attr, _view_factory, _title, update_method, _height in _SINGLE_VIEW_DOCK_SPECS
    }
    main_window._image_update_targets = [
        single_updates["dock_edge"],
        single_updates["dock_gray"],
        single_updates["dock_mirror"],
        single_updates["dock_binary"],
        single_updates["dock_ternary"],
        (main_window.dock_rgb_hist, main_window.rgb_hist_view.update_from_bgr, None),
        single_updates["dock_saliency"],
        single_updates["dock_focus"],
        single_updates["dock_squint"],
        (
            main_window.dock_vectorscope,
            main_window.vectorscope_view.update_scope,
            main_window._update_vectorscope_warning_label,
        ),
    ]


def _set_initial_layout_metadata(main_window) -> None:
    """初期ドック配置で使う順序とサイズ情報を保存する。"""
    main_window._dock_initial_left_tab_names = ("dock_color_band", "dock_hist", "dock_rgb_hist")
    main_window._dock_initial_right_chain_names = tuple(
        dock_name for dock_name, *_rest in _SINGLE_VIEW_DOCK_SPECS
    ) + ("dock_vectorscope",)
    main_window._dock_initial_vertical_sizes = [280]
    main_window._dock_initial_vertical_sizes.extend(
        height for *_head, height in _SINGLE_VIEW_DOCK_SPECS
    )
    main_window._dock_initial_vertical_sizes.append(160)


def build_view_docks(main_window) -> None:
    """解析ビュー一式のドックと更新対象情報を構築する。"""
    color_dock, color_band_dock, hist_dock, rgb_hist_dock = _build_color_and_histogram_docks(
        main_window
    )
    scatter_dock = _build_scatter_dock(main_window)
    single_view_docks = _build_single_view_docks(main_window)
    vectorscope_dock = _build_vectorscope_dock(main_window)

    dock_specs = [
        ("dock_color", color_dock, Qt.LeftDockWidgetArea),
        ("dock_color_band", color_band_dock, Qt.LeftDockWidgetArea),
        ("dock_scatter", scatter_dock, Qt.RightDockWidgetArea),
        ("dock_hist", hist_dock, Qt.LeftDockWidgetArea),
        ("dock_rgb_hist", rgb_hist_dock, Qt.LeftDockWidgetArea),
    ]
    dock_specs.extend(
        (dock_name, single_view_docks[dock_name], Qt.RightDockWidgetArea)
        for dock_name, *_rest in _SINGLE_VIEW_DOCK_SPECS
    )
    dock_specs.append(("dock_vectorscope", vectorscope_dock, Qt.RightDockWidgetArea))

    register_docks(main_window, dock_specs)
    main_window._dock_actions = build_dock_actions(main_window)
    _configure_update_targets(main_window, single_view_docks)
    _set_initial_layout_metadata(main_window)

    for dock in main_window._dock_map.values():
        configure_view_dock(main_window, dock)
