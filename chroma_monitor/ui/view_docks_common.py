"""ビュー用ドックの共通部品と共通設定。"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..util import constants as C

_GRAPH_REFRESH_DOCK_NAMES = frozenset(
    ("dock_color", "dock_color_band", "dock_scatter", "dock_hist")
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


def build_single_view_container(view: QWidget) -> QWidget:
    """単一ビューを共通マージンで包むコンテナを作る。"""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.addWidget(view, 1)
    return container


def create_info_label(text: str) -> QLabel:
    """配色詳細欄で使う共通スタイルの説明ラベルを作る。"""
    label = QLabel(text)
    label.setProperty("chromaRole", "infoLabel")
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return label


def create_dock(
    main_window,
    title: str,
    object_name: str,
    content: QWidget,
) -> QDockWidget:
    """指定内容のドックを生成して返す。"""
    dock = UniformMinDockWidget(title, main_window)
    dock.setObjectName(object_name)
    dock.setWidget(content)
    dock.setAllowedAreas(Qt.AllDockWidgetAreas)
    return dock


def configure_view_dock(main_window, dock: QDockWidget) -> None:
    """各ドックへ共通機能と共通シグナル接続を設定する。"""
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
        _handle_view_dock_visibility_changed(mw, d, bool(visible))

    dock.visibilityChanged.connect(_on_visibility_changed)

    for signal in (dock.topLevelChanged, dock.dockLocationChanged):
        signal.connect(lambda *_args, mw=main_window: mw._schedule_layout_autosave())
        signal.connect(main_window._sync_tabbed_dock_title_bars)


def register_docks(
    main_window,
    dock_specs: list[tuple[str, QDockWidget, Qt.DockWidgetArea]],
) -> None:
    """ドック参照テーブルと既定エリア情報を一括登録する。"""
    main_window._dock_map = {}
    main_window._dock_default_areas = {}
    main_window._dock_name_by_object = {}
    for name, dock, default_area in dock_specs:
        setattr(main_window, name, dock)
        main_window._dock_map[name] = dock
        main_window._dock_default_areas[name] = default_area
        main_window._dock_name_by_object[dock] = name


def build_dock_actions(main_window) -> dict[str, object]:
    """ドック名と対応アクションのマップを構築する。"""
    dock_actions = {}
    for dock_name in main_window._dock_map:
        suffix = dock_name[5:] if dock_name.startswith("dock_") else dock_name
        action = getattr(main_window, f"act_{suffix}", None)
        if action is not None:
            dock_actions[dock_name] = action
    return dock_actions


def _dock_name_from_object(main_window, dock) -> str | None:
    """Return the registered dock name for a dock widget."""
    dock_name_map = getattr(main_window, "_dock_name_by_object", None)
    if isinstance(dock_name_map, dict):
        dock_name = dock_name_map.get(dock)
        if dock_name is not None:
            return str(dock_name)
    for name, mapped in getattr(main_window, "_dock_map", {}).items():
        if mapped is dock:
            return str(name)
    return None


def _handle_view_dock_visibility_changed(main_window, dock, visible: bool) -> None:
    """Handle dock visibility in the order worker sync -> refresh -> restore."""
    is_visible = bool(visible)
    if is_visible and getattr(dock, "_attach_on_next_show", False):
        dock._attach_on_next_show = False
    main_window._sync_worker_view_flags()
    if not is_visible:
        return
    dock_name = _dock_name_from_object(main_window, dock)
    if dock_name in _GRAPH_REFRESH_DOCK_NAMES:
        request_graph_refresh_once = getattr(main_window.worker, "request_graph_refresh_once", None)
        if callable(request_graph_refresh_once):
            request_graph_refresh_once()
    main_window._restore_dock_from_snapshot(dock)


def detach_initially_hidden_docks(main_window) -> None:
    """初期設定で非表示のドックをレイアウトツリーから外す。"""
    for name, dock in main_window._dock_map.items():
        action = main_window._dock_actions.get(name)
        if action is None or action.isChecked():
            continue
        if dock.isFloating():
            dock.setFloating(False)
        dock.setVisible(False)
        main_window.removeDockWidget(dock)
        dock._attach_on_next_show = True
