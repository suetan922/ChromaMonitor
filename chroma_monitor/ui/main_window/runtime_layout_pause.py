"""レイアウト操作時の解析一時停止と worker 可視フラグ同期。"""

from ...util.qt_helpers import is_widget_renderable
from .runtime_common import restore_visible_docks_from_snapshot

_WORKER_VIEW_FLAGS_DISABLED = {
    "color": False,
    "color_band": False,
    "scatter": False,
    "hsv_hist": False,
    "image": False,
    "preview": False,
}


def _set_worker_view_flags_if_changed(
    main_window,
    *,
    color: bool,
    color_band: bool,
    scatter: bool,
    hsv_hist: bool,
    image: bool,
    preview: bool,
) -> None:
    """ビュー可視状態が変わったときだけ worker の解析フラグを更新する。"""
    state = (
        bool(color),
        bool(color_band),
        bool(scatter),
        bool(hsv_hist),
        bool(image),
        bool(preview),
    )
    if state == getattr(main_window, "_worker_view_flags_state", None):
        return
    main_window._worker_view_flags_state = state
    main_window.worker.set_view_flags(
        color=state[0],
        color_band=state[1],
        scatter=state[2],
        hsv_hist=state[3],
        image=state[4],
        preview=state[5],
    )


def has_visible_image_dock(main_window) -> bool:
    """画像系ドックが1つ以上可視なら True を返す。"""
    targets = getattr(main_window, "_image_update_targets", ())
    return any(
        is_widget_renderable(dock) and is_widget_renderable(dock.widget()) for dock, *_ in targets
    )


def sync_worker_view_flags(main_window):
    """現在UI可視状態に応じた worker 側の解析対象を同期する。"""
    if bool(getattr(main_window, "_layout_interaction_pause_active", False)):
        _set_worker_view_flags_if_changed(main_window, **_WORKER_VIEW_FLAGS_DISABLED)
        return

    color_band_visible = bool(
        getattr(main_window, "dock_color_band", None) is not None
        and main_window.dock_color_band.isVisible()
    )
    color_visible = bool(main_window.dock_color.isVisible() or color_band_visible)
    _set_worker_view_flags_if_changed(
        main_window,
        color=color_visible,
        color_band=color_band_visible,
        scatter=bool(main_window.dock_scatter.isVisible()),
        hsv_hist=bool(main_window.dock_hist.isVisible()),
        image=bool(has_visible_image_dock(main_window) or color_band_visible),
        preview=bool(main_window.chk_preview_window.isChecked()),
    )


def begin_layout_interaction_pause(main_window, reason: str = "layout") -> None:
    """レイアウト操作中の解析一時停止を開始する。"""
    reasons = getattr(main_window, "_layout_interaction_pause_reasons", None)
    if isinstance(reasons, set):
        reasons.add(str(reason))

    timer = getattr(main_window, "_layout_interaction_resume_timer", None)
    if timer is not None:
        timer.stop()

    if bool(getattr(main_window, "_layout_interaction_pause_active", False)):
        return

    main_window._layout_interaction_pause_active = True
    _set_worker_view_flags_if_changed(main_window, **_WORKER_VIEW_FLAGS_DISABLED)


def schedule_layout_interaction_resume(main_window, reason: str = "layout") -> None:
    """レイアウト操作停止後の解析再開をタイマーで予約する。"""
    reasons = getattr(main_window, "_layout_interaction_pause_reasons", None)
    if isinstance(reasons, set):
        reasons.discard(str(reason))

    timer = getattr(main_window, "_layout_interaction_resume_timer", None)
    if timer is None:
        end_layout_interaction_pause(main_window)
        return
    timer.start()


def end_layout_interaction_pause(main_window) -> None:
    """解析一時停止を解除し、可視ドックの再描画を行う。"""
    if not bool(getattr(main_window, "_layout_interaction_pause_active", False)):
        return

    timer = getattr(main_window, "_layout_interaction_resume_timer", None)
    if timer is not None:
        timer.stop()

    main_window._layout_interaction_pause_active = False
    reasons = getattr(main_window, "_layout_interaction_pause_reasons", None)
    if isinstance(reasons, set):
        reasons.clear()

    sync_worker_view_flags(main_window)
    restore_visible_docks_from_snapshot(main_window)
