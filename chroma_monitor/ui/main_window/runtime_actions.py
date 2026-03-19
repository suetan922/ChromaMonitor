"""実行時アクションの facade。"""

from .runtime_capture import (
    apply_capture_source,
    on_window_changed,
    on_window_index_activated,
    on_window_popup_row_selected,
    on_window_text_activated,
    on_window_text_changed,
    on_window_text_committed,
    on_window_text_edited,
    refresh_windows,
    selected_capture_source,
    sync_capture_source_ui,
)
from .runtime_image_analysis import (
    cancel_image_analysis,
    close_event,
    on_image_analysis_canceled,
    on_image_analysis_failed,
    on_image_analysis_finished,
    on_image_analysis_progress,
    on_load_image,
    on_start,
    on_stop,
)
from .runtime_layout_pause import (
    begin_layout_interaction_pause,
    end_layout_interaction_pause,
    has_visible_image_dock,
    schedule_layout_interaction_resume,
    sync_worker_view_flags,
)
from .runtime_preview import on_preview_closed, on_preview_toggled, update_preview_snapshot
from .runtime_common import on_status

__all__ = [
    "apply_capture_source",
    "begin_layout_interaction_pause",
    "cancel_image_analysis",
    "close_event",
    "end_layout_interaction_pause",
    "has_visible_image_dock",
    "on_image_analysis_canceled",
    "on_image_analysis_failed",
    "on_image_analysis_finished",
    "on_image_analysis_progress",
    "on_load_image",
    "on_preview_closed",
    "on_preview_toggled",
    "on_start",
    "on_status",
    "on_stop",
    "on_window_changed",
    "on_window_index_activated",
    "on_window_popup_row_selected",
    "on_window_text_activated",
    "on_window_text_changed",
    "on_window_text_committed",
    "on_window_text_edited",
    "refresh_windows",
    "schedule_layout_interaction_resume",
    "selected_capture_source",
    "sync_capture_source_ui",
    "sync_worker_view_flags",
    "update_preview_snapshot",
]
