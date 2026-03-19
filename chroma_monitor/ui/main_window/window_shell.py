"""MainWindow のメニュー、ツールバー、ドック初期化。"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMenuBar, QPushButton

from ...ui.input_widgets import add_checkable_action
from ...ui.view_docks import setup_view_docks
from ...util import constants as C
from ...views.preview import PreviewWindow

WINDOW_DOCK_MENU_ITEMS = (
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
    ("act_mirror", "反転表示", False, "dock_mirror"),
    ("act_focus", "フォーカスピーキング", True, "dock_focus"),
    ("act_squint", "スクイント表示", True, "dock_squint"),
    ("act_saliency", "サリエンシーマップ", True, "dock_saliency"),
)


def build_menu_bar(main_window, *, window_dock_menu_items=WINDOW_DOCK_MENU_ITEMS) -> None:
    """メニューバーと各アクションを構築する。"""
    mb = main_window.menuBar() if hasattr(main_window, "menuBar") else QMenuBar(main_window)
    win_menu = mb.addMenu("ウィンドウ")

    def _bind_dock_action(attr_name: str, title: str, default: bool, dock_attr: str):
        action = add_checkable_action(
            win_menu,
            title,
            default,
            lambda visible, name=dock_attr: main_window.toggle_dock(
                getattr(main_window, name),
                visible,
            ),
        )
        setattr(main_window, attr_name, action)

    for spec in window_dock_menu_items:
        _bind_dock_action(*spec)

    menu = mb.addMenu("設定")
    main_window.act_always_on_top = add_checkable_action(
        menu,
        "常に最前面に表示",
        C.DEFAULT_ALWAYS_ON_TOP,
        main_window.apply_always_on_top,
    )
    main_window.settings_action = menu.addAction("設定ウィンドウを開く")
    main_window.settings_action.triggered.connect(lambda: main_window.show_settings_window())

    layout_menu = mb.addMenu("レイアウト")
    main_window.presets_menu = layout_menu.addMenu("プリセットを適用")
    main_window.act_open_layout_settings = layout_menu.addAction("レイアウト設定を開く")
    main_window.act_open_layout_settings.triggered.connect(
        lambda: main_window.show_settings_window(C.SETTINGS_PAGE_LAYOUT)
    )
    main_window._setup_help_menu(mb)
    for popup in (
        win_menu,
        menu,
        layout_menu,
        main_window.presets_menu,
        getattr(main_window, "help_menu", None),
    ):
        ensure_menu_popup_width(main_window, popup)


def ensure_menu_popup_width(main_window, menu) -> None:
    """メニュー項目文言が見切れないようポップアップ最小幅を調整する。"""
    if menu is None:
        return

    def _sync_min_width() -> None:
        fm = menu.fontMetrics()
        max_text_width = 0
        for action in menu.actions():
            if action is None or action.isSeparator():
                continue
            text = str(action.text()).replace("&", "")
            if "\t" in text:
                text = text.split("\t", 1)[0]
            max_text_width = max(max_text_width, int(fm.horizontalAdvance(text)))
        target = max(180, int(max_text_width) + 96)
        menu.setMinimumWidth(target)

    _sync_min_width()
    menu.aboutToShow.connect(_sync_min_width)


def build_toolbar(main_window) -> None:
    """Start/Stop/画像読み込みのツールバーを構築する。"""
    toolbar = main_window.addToolBar("コントロール")
    toolbar.setObjectName("controlToolbar")
    toolbar.setMovable(False)
    main_window.btn_start_bar = QPushButton("Start")
    main_window.btn_stop_bar = QPushButton("Stop")
    main_window.btn_start_bar.setObjectName("runStartBtn")
    main_window.btn_stop_bar.setObjectName("runStopBtn")
    main_window.btn_start_bar.setCheckable(True)
    main_window.btn_stop_bar.setCheckable(True)
    main_window.btn_start_bar.clicked.connect(main_window.on_start)
    main_window.btn_stop_bar.clicked.connect(main_window.on_stop)
    main_window.btn_load_image_bar = QPushButton("画像読み込み")
    main_window.btn_load_image_bar.clicked.connect(main_window.on_load_image)
    toolbar.addWidget(main_window.btn_start_bar)
    toolbar.addWidget(main_window.btn_stop_bar)
    toolbar.addWidget(main_window.btn_load_image_bar)
    main_window.btn_stop_bar.setChecked(True)


def setup_preview_and_docks(main_window) -> None:
    """プレビューとドック群を構築し、関連イベントを接続する。"""
    main_window.preview_window = PreviewWindow()
    main_window.preview_window.closed.connect(main_window.on_preview_closed)
    setup_view_docks(main_window)
    if hasattr(main_window, "tabifiedDockWidgetActivated"):
        main_window.tabifiedDockWidgetActivated.connect(main_window._on_tabified_dock_activated)
    main_window.top_colors_bar.installEventFilter(main_window)
    if hasattr(main_window, "list_color_chips"):
        main_window.list_color_chips.currentRowChanged.connect(main_window._on_color_chip_selected)
    if hasattr(main_window.wheel, "harmonyGuideRotationChanged"):
        main_window.wheel.harmonyGuideRotationChanged.connect(
            main_window._on_wheel_harmony_rotation_changed
        )
    main_window.chk_scatter_hue_filter.toggled.connect(main_window.apply_scatter_settings)
    main_window.slider_scatter_hue_center.valueChanged.connect(main_window.apply_scatter_settings)
    main_window._sync_scatter_filter_controls()
    for dock in main_window._dock_map.values():
        dock.visibilityChanged.connect(
            lambda _visible, self=main_window: self._sync_worker_view_flags()
        )
        dock.topLevelChanged.connect(
            lambda visible, d=dock, self=main_window: self._on_dock_top_level_changed(
                d,
                bool(visible),
            )
        )
        dock.installEventFilter(main_window)
    main_window._sync_worker_view_flags()


def on_tabified_dock_activated(main_window, dock) -> None:
    """タブ切替直後の表示同期とスナップショット復元を行う。"""
    main_window._sync_tabbed_dock_title_bars()
    main_window._sync_worker_view_flags()
    if dock is None:
        return
    main_window._restore_dock_from_snapshot(dock)
    QTimer.singleShot(
        0,
        lambda d=dock, self=main_window: self._restore_dock_from_snapshot(d),
    )
    QTimer.singleShot(
        60,
        lambda d=dock, self=main_window: self._restore_dock_from_snapshot(d),
    )
