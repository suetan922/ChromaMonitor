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
    QSlider,
    QSplitter,
    QTabWidget,
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

_H_COLOR = QColor(220, 90, 90)
_S_COLOR = QColor(90, 170, 90)
_V_COLOR = QColor(80, 140, 240)
_COLOR_BAND_WARMCOOL_BOTTOM_SPACING = 6
_SINGLE_VIEW_DOCK_SPECS = (
    # (dock_name, view_attr, view_factory, title, update_method, initial_height)
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


class UniformMinDockWidget(QDockWidget):
    """全ビューで共通の最小サイズヒントを返すドック。"""

    def minimumSizeHint(self):
        """ドック共通の最小サイズを返す。"""
        return QSize(C.VIEW_MIN_WIDTH, C.VIEW_MIN_HEIGHT)


class ZeroMinContainer(QWidget):
    """子要素に依存せず最小サイズを0で返すコンテナ。"""

    def minimumSizeHint(self):
        """縮小時に内部要素の最小ヒントを優先しないため0を返す。"""
        return QSize(0, 0)


def _build_single_view_container(view: QWidget) -> QWidget:
    """単一ビューを共通マージンで包むコンテナを作る。"""
    # 単一ビュー向けの共通余白コンテナ。
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.addWidget(view, 1)
    return container


def _create_info_label(text: str) -> QLabel:
    """配色詳細欄で使う共通スタイルの説明ラベルを作る。"""
    label = QLabel(text)
    label.setStyleSheet("color:#111; font-size:12px;")
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return label


def _create_dock(
    main_window,
    title: str,
    object_name: str,
    content: QWidget,
) -> QDockWidget:
    """指定内容のドックを生成して返す。"""
    # タイトル・ObjectName・コンテンツ設定までを担当し、
    # 実際の配置は setup_view_docks 側で一括して行う。
    dock = UniformMinDockWidget(title, main_window)
    dock.setObjectName(object_name)
    dock.setWidget(content)
    dock.setAllowedAreas(Qt.AllDockWidgetAreas)
    return dock


def _configure_view_dock(main_window, dock: QDockWidget) -> None:
    """各ドックへ共通機能と共通シグナル接続を設定する。"""
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

    def _on_visibility_changed(visible: bool, *, mw=main_window, d=dock) -> None:
        is_visible = bool(visible)
        if is_visible and getattr(d, "_attach_on_next_show", False):
            d._attach_on_next_show = False
        if is_visible:
            mw._restore_dock_from_snapshot(d)

    dock.visibilityChanged.connect(_on_visibility_changed)

    for signal in (dock.topLevelChanged, dock.dockLocationChanged):
        # 配置が変わったときだけ自動保存を予約する。
        signal.connect(lambda *_args, mw=main_window: mw._schedule_layout_autosave())
        signal.connect(main_window._sync_tabbed_dock_title_bars)


def _register_docks(
    main_window,
    dock_specs: list[tuple[str, QDockWidget, Qt.DockWidgetArea]],
) -> None:
    """ドック参照テーブルと既定エリア情報を一括登録する。"""
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
    """ドック名と対応アクションのマップを構築する。"""
    # act_<dock名> ルールで対応アクションを解決する。
    dock_actions = {}
    for dock_name in main_window._dock_map:
        suffix = dock_name[5:] if dock_name.startswith("dock_") else dock_name
        action = getattr(main_window, f"act_{suffix}", None)
        if action is not None:
            dock_actions[dock_name] = action
    return dock_actions


def _detach_initially_hidden_docks(main_window) -> None:
    """初期設定で非表示のドックをレイアウトツリーから外す。"""
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
    """解析ビュー一式のドックと初期レイアウトを構築する。"""
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
    main_window._last_top_bars_key = None
    main_window._color_detail_has_selection = False
    main_window._color_detail_merge_complement = False
    main_window._color_detail_show_info = True
    main_window.top_colors_bar = QLabel()
    # バーは常に見えるよう、固定高さ + 横方向のみ伸縮にする。
    main_window.top_colors_bar.setMinimumHeight(C.TOP_COLOR_BAR_HEIGHT)
    main_window.top_colors_bar.setMaximumHeight(C.TOP_COLOR_BAR_HEIGHT)
    main_window.top_colors_bar.setMinimumWidth(0)
    main_window.top_colors_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    main_window.top_colors_bar.setScaledContents(False)

    main_window.lbl_warmcool = QLabel("暖色: -   寒色: -   その他: -")
    main_window.lbl_warmcool.setStyleSheet(
        "color:#111; font-size:12px; background:transparent; border:none;"
    )
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

    main_window.lbl_color_harmony_info = _create_info_label("色彩調和")

    main_window.color_harmony_preview = QWidget()
    main_window.color_harmony_preview_layout = QHBoxLayout(main_window.color_harmony_preview)
    main_window.color_harmony_preview_layout.setContentsMargins(0, 0, 0, 0)
    main_window.color_harmony_preview_layout.setSpacing(6)
    main_window.color_harmony_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.lbl_color_complement_info = _create_info_label("補色")

    main_window.color_complement_preview = QWidget()
    main_window.color_complement_preview_layout = QHBoxLayout(main_window.color_complement_preview)
    main_window.color_complement_preview_layout.setContentsMargins(0, 0, 0, 0)
    main_window.color_complement_preview_layout.setSpacing(6)
    main_window.color_complement_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    main_window.lbl_color_methods_info = _create_info_label("配色手法")

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

    # 配色比率は内部要素が多いため、コンテナの最小ヒントを 0 にして
    # ドック共通最小サイズ定数でのみ下限を管理する。
    color_band_widget = ZeroMinContainer()
    cb_l = QVBoxLayout(color_band_widget)
    cb_l.setContentsMargins(6, 6, 6, 6)
    cb_l.setSpacing(4)
    cb_l.addWidget(main_window.top_colors_bar)
    cb_l.addWidget(main_window.lbl_warmcool)
    cb_l.addSpacing(_COLOR_BAND_WARMCOOL_BOTTOM_SPACING)
    cb_l.addWidget(main_window.color_band_splitter, 1)
    color_band_widget.setMinimumSize(0, 0)
    color_band_dock = _create_dock(
        main_window,
        "配色比率",
        "dock_color_band",
        color_band_widget,
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
    # 外出し/再ドック直後は散布図の再スケールを予約して見切れを防ぐ。
    scatter_dock.topLevelChanged.connect(lambda _v, w=main_window.scatter: w.request_layout_sync())
    scatter_dock.dockLocationChanged.connect(
        lambda _area, w=main_window.scatter: w.request_layout_sync()
    )

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
    )
    # 初期レイアウトから再表示したときは、色相環グループへ優先的にタブ合流させる。
    hist_dock._preferred_tab_anchor_name = "dock_color"

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
    )
    # RGBヒストグラムも色相環グループへ合流する。
    rgb_hist_dock._preferred_tab_anchor_name = "dock_color"

    def _init_single_view_dock(
        view_attr: str, view_factory: type[QWidget], *, title: str, object_name: str
    ) -> QDockWidget:
        """単一ビュー本体生成とドック生成をまとめて行う。"""
        view = view_factory()
        setattr(main_window, view_attr, view)
        return _create_dock(
            main_window,
            title,
            object_name,
            _build_single_view_container(view),
        )

    single_view_docks: dict[str, QDockWidget] = {}
    for dock_name, view_attr, view_factory, title, _update_method, _height in _SINGLE_VIEW_DOCK_SPECS:
        single_view_docks[dock_name] = _init_single_view_dock(
            view_attr,
            view_factory,
            title=title,
            object_name=dock_name,
        )

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
        main_window.setTabPosition(area, QTabWidget.South)

    main_window.placeholder = QLabel("ウィンドウメニューから表示したいビューを選択してください")
    main_window.placeholder.setAlignment(Qt.AlignCenter)
    main_window.placeholder.setWordWrap(True)
    main_window.placeholder.setMinimumSize(0, 0)
    main_window.placeholder.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    main_window.placeholder.setStyleSheet("color:#555; font-size:14px;")

    central = QWidget()
    central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    c_l = QVBoxLayout(central)
    c_l.setContentsMargins(0, 0, 0, 0)
    c_l.setSpacing(0)
    c_l.addWidget(main_window.placeholder, 1)
    main_window.setCentralWidget(central)
    main_window.central_container = central

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
    _register_docks(main_window, dock_specs)
    main_window._dock_actions = _build_dock_actions(main_window)
    # 画像入力を必要とするビューの更新ルールを一元管理する。
    single_updates = {
        dock_name: (
            single_view_docks[dock_name],
            getattr(getattr(main_window, view_attr), update_method),
            None,
        )
        for dock_name, view_attr, _view_factory, _title, update_method, _height in _SINGLE_VIEW_DOCK_SPECS
    }
    image_update_targets = [
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
    main_window._image_update_targets = image_update_targets

    for d in main_window._dock_map.values():
        _configure_view_dock(main_window, d)

    # 初期配置: 左にカラー、右側にビュー群、下にヒストグラム。
    # タブ固定を避け、自由な多段再配置を優先する。
    main_window.addDockWidget(Qt.LeftDockWidgetArea, color_dock)
    # 配色比率・ヒストグラムは色相環と同一グループで開き、単独枠として分離しない。
    main_window.tabifyDockWidget(color_dock, color_band_dock)
    main_window.tabifyDockWidget(color_dock, hist_dock)
    main_window.tabifyDockWidget(color_dock, rgb_hist_dock)
    color_dock.raise_()
    main_window.addDockWidget(Qt.RightDockWidgetArea, scatter_dock)
    right_chain = [single_view_docks[dock_name] for dock_name, *_rest in _SINGLE_VIEW_DOCK_SPECS]
    right_chain.append(vectorscope_dock)
    prev = scatter_dock
    for dock in right_chain:
        main_window.splitDockWidget(prev, dock, Qt.Vertical)
        prev = dock
    main_window.resizeDocks(
        [color_dock, scatter_dock, right_chain[0]],
        [700, 700, 700],
        Qt.Horizontal,
    )
    vertical_sizes = [280]
    vertical_sizes.extend(height for *_head, height in _SINGLE_VIEW_DOCK_SPECS)
    vertical_sizes.append(160)  # vectorscope
    main_window.resizeDocks([scatter_dock, *right_chain], vertical_sizes, Qt.Vertical)
    _detach_initially_hidden_docks(main_window)
    main_window._sync_tabbed_dock_title_bars()
