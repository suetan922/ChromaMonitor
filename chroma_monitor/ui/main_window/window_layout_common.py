"""`window_layout` 系モジュールで共有する定数と小物ヘルパー。"""

from PySide6.QtWidgets import QDockWidget, QMainWindow

_REBALANCE_COLUMN_X_TOLERANCE_PX = 3
_REBALANCE_COLUMN_W_TOLERANCE_PX = 3
_REBALANCE_HEIGHT_CHANGE_THRESHOLD_PX = 2
_REBALANCE_CHAIN_TOUCH_TOLERANCE_PX = 2
_MAIN_WINDOW_FIT_MARGIN_PX = 0
_MAIN_WINDOW_MIN_W = 480
_MAIN_WINDOW_MIN_H = 360
_MAIN_WINDOW_COMPACT_MIN_W_FLOOR = 220
_MAIN_WINDOW_COMPACT_MIN_H_FLOOR = 1
_MAIN_WINDOW_MAX_W_FLOOR = 640
_MAIN_WINDOW_MAX_H_FLOOR = 420
_PLACEHOLDER_SHOW_MIN_W = 280
_PLACEHOLDER_SHOW_MIN_H = 90
_DIALOG_FIT_MARGIN_PX = 8
_DIALOG_MIN_W = 420
_DIALOG_MIN_H = 320
_TOPLEVEL_FIT_MARGIN_PX = 0
_TOPLEVEL_MIN_W = 160
_TOPLEVEL_MIN_H = 120
_TOPLEVEL_MAX_W_FLOOR = 240
_TOPLEVEL_MAX_H_FLOOR = 180
_DOCK_OPTIONS_BASE = QMainWindow.AnimatedDocks | QMainWindow.AllowTabbedDocks
_DOCK_OPTIONS_NESTED = _DOCK_OPTIONS_BASE | QMainWindow.AllowNestedDocks
_DOCK_DROP_ACTIVATION_MARGIN_RATIO = 0.16
_DOCK_DROP_ACTIVATION_MARGIN_MIN_PX = 96
_DOCK_DROP_ACTIVATION_MARGIN_MAX_PX = 360
_FLOATING_SCREEN_FIX_RETRY_MS = 120
_FLOATING_DEBUG_EVENT_THROTTLE_SEC = 0.06
_FLOATING_MOVE_DRAG_EDGE_MARGIN_PX = 12
_FLOATING_MOVE_DRAG_GUARD_RETRY_MS = 120
_DOCKABILITY_SYNC_DEBOUNCE_MS = 56


def dock_debug_name(main_window, dock: QDockWidget | None) -> str:
    """デバッグログ向けドック識別子を返す。"""
    if dock is None:
        return "dock:none"
    for name, mapped in getattr(main_window, "_dock_map", {}).items():
        if mapped is dock:
            return str(name)
    try:
        obj_name = str(dock.objectName())
    except Exception:
        obj_name = ""
    if obj_name:
        return obj_name
    return f"dock@{id(dock):x}"


def dock_area_to_log_value(area) -> int | str:
    """`DockWidgetArea` をログ出力向けの安全な値へ変換する。"""
    try:
        return int(area)
    except Exception:
        try:
            return int(getattr(area, "value"))
        except Exception:
            return str(area)
