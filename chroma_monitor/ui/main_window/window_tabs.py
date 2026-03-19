"""ドックタブ表示とタブUI補助の facade。"""

from .window_tab_drag import clear_force_dock_drop_active, handle_dock_tab_bar_event
from .window_tab_sync import is_dock_tab_bar, sync_tabbed_dock_title_bars

__all__ = [
    "clear_force_dock_drop_active",
    "handle_dock_tab_bar_event",
    "is_dock_tab_bar",
    "sync_tabbed_dock_title_bars",
]
