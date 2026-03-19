"""ウィンドウ配置とドッキング挙動の facade。"""

from .window_layout_docks import (
    on_dock_top_level_changed,
    schedule_floating_dock_dockability_sync,
    sync_all_floating_dock_dockability,
    toggle_dock,
    track_floating_dock_size,
    update_floating_dock_dockability,
)
from .window_layout_floating import notify_floating_dock_moved
from .window_layout_geometry import (
    desktop_available_geometry,
    fit_dialog_to_desktop,
    fit_top_level_widget_to_desktop,
    fit_window_to_desktop,
    schedule_window_fit,
    update_placeholder,
)
from .window_layout_rebalance import rebalance_dock_layout, schedule_dock_rebalance
from .window_layout_theme import apply_ui_style, sync_window_menu_checks

__all__ = [
    "apply_ui_style",
    "desktop_available_geometry",
    "fit_dialog_to_desktop",
    "fit_top_level_widget_to_desktop",
    "fit_window_to_desktop",
    "notify_floating_dock_moved",
    "on_dock_top_level_changed",
    "rebalance_dock_layout",
    "schedule_dock_rebalance",
    "schedule_floating_dock_dockability_sync",
    "schedule_window_fit",
    "sync_all_floating_dock_dockability",
    "sync_window_menu_checks",
    "toggle_dock",
    "track_floating_dock_size",
    "update_floating_dock_dockability",
    "update_placeholder",
]
