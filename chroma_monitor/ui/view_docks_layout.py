"""ビュー用ドックの初期レイアウト適用。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QSizePolicy, QTabWidget, QVBoxLayout, QWidget

from .view_docks_common import detach_initially_hidden_docks


def _build_placeholder_central(main_window) -> None:
    """placeholder と中央コンテナを構築する。"""
    main_window.placeholder = QLabel("ウィンドウメニューから表示したいビューを選択してください")
    main_window.placeholder.setAlignment(Qt.AlignCenter)
    main_window.placeholder.setWordWrap(True)
    main_window.placeholder.setMinimumSize(0, 0)
    main_window.placeholder.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    main_window.placeholder.setProperty("chromaRole", "placeholder")

    central = QWidget()
    central.setObjectName("centralWidget")
    central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    layout = QVBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(main_window.placeholder, 1)
    main_window.setCentralWidget(central)
    main_window.central_container = central


def _configure_dock_options(main_window) -> None:
    """メインウィンドウのドックオプションを設定する。"""
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


def _apply_initial_dock_layout(main_window) -> None:
    """初期表示用のドック配置を適用する。"""
    color_dock = main_window.dock_color
    scatter_dock = main_window.dock_scatter
    main_window.addDockWidget(Qt.LeftDockWidgetArea, color_dock)
    for dock_name in getattr(main_window, "_dock_initial_left_tab_names", ()):
        main_window.tabifyDockWidget(color_dock, main_window._dock_map[dock_name])
    color_dock.raise_()

    main_window.addDockWidget(Qt.RightDockWidgetArea, scatter_dock)
    right_chain = [
        main_window._dock_map[dock_name]
        for dock_name in getattr(main_window, "_dock_initial_right_chain_names", ())
    ]
    prev = scatter_dock
    for dock in right_chain:
        main_window.splitDockWidget(prev, dock, Qt.Vertical)
        prev = dock

    if right_chain:
        main_window.resizeDocks(
            [color_dock, scatter_dock, right_chain[0]],
            [700, 700, 700],
            Qt.Horizontal,
        )
        main_window.resizeDocks(
            [scatter_dock, *right_chain],
            getattr(main_window, "_dock_initial_vertical_sizes", [280]),
            Qt.Vertical,
        )


def setup_view_dock_layout(main_window) -> None:
    """placeholder と初期ドックレイアウトを構築する。"""
    _configure_dock_options(main_window)
    _build_placeholder_central(main_window)
    _apply_initial_dock_layout(main_window)
    detach_initially_hidden_docks(main_window)
    main_window._sync_tabbed_dock_title_bars()
