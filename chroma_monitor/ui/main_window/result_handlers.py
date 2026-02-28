import cv2
import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

from ...analysis.frame_analysis import analyze_bgr_frame
from ...util import constants as C
from ...util.functions import (
    clamp_render_size,
    clear_cvt_color_cache,
    clear_resize_cache,
    is_widget_renderable,
)

_TOP_BAR_MIN_HEIGHT = 12
_TOP_BAR_TEXT_MIN_WIDTH = 240
_TOP_BAR_TEXT_MIN_SEGMENT_PX = 42
_SNAPSHOT_DOCK_COLOR = "dock_color"
_SNAPSHOT_DOCK_COLOR_BAND = "dock_color_band"
_SNAPSHOT_DOCK_SCATTER = "dock_scatter"
_SNAPSHOT_DOCK_HIST = "dock_hist"


def top_hue_bars(
    hist: np.ndarray | None,
) -> tuple[str, list[tuple[str, float, tuple[int, int, int]]]]:
    if hist is None:
        return C.TOP_COLORS_TITLE, []
    hist = np.asarray(hist, dtype=np.int64).reshape(-1)
    if hist.size != 180:
        fixed = np.zeros(180, dtype=np.int64)
        n = min(180, hist.size)
        if n > 0:
            fixed[:n] = hist[:n]
        hist = fixed
    total = float(hist.sum())
    if total <= 0:
        return C.TOP_COLORS_TITLE, []

    top_idx = np.argsort(hist)[::-1]
    bars: list[tuple[str, float, tuple[int, int, int]]] = []
    for idx in top_idx[: C.TOP_COLORS_COUNT]:
        count = hist[idx]
        if count <= 0:
            continue
        ratio = float(count) / total
        hsv = np.uint8([[[idx * 2, 255, 255]]])
        rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0]
        bars.append((f"H{idx}", ratio, (int(rgb[0]), int(rgb[1]), int(rgb[2]))))
    return C.TOP_COLORS_TITLE, bars


def _top_bar_item_ratio_color(item: tuple) -> tuple[float, tuple[int, int, int]]:
    if len(item) == 3:
        _, ratio, color = item
    else:
        ratio, color = item
    return float(ratio), tuple(int(c) for c in color)


def render_top_color_bar(
    bars: list[tuple], width: int = 300, height: int = C.TOP_COLOR_BAR_HEIGHT
) -> QPixmap:
    safe_w, safe_h = clamp_render_size(width, max(_TOP_BAR_MIN_HEIGHT, height))
    pm = QPixmap(safe_w, safe_h)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    try:
        painter.fillRect(QRect(0, 0, pm.width(), pm.height()), QColor(235, 235, 235))
        show_text = pm.width() >= _TOP_BAR_TEXT_MIN_WIDTH
        x = 0
        remaining = pm.width()
        for item in bars:
            ratio, color = _top_bar_item_ratio_color(item)
            w = int(round(pm.width() * ratio))
            w = max(1, min(w, remaining))
            painter.fillRect(QRect(x, 0, w, pm.height()), QColor(*color))
            if show_text and w >= _TOP_BAR_TEXT_MIN_SEGMENT_PX:
                pct = f"{ratio*100:.1f}%"
                painter.setPen(QColor(255, 255, 255) if sum(color) < 400 else QColor(40, 40, 40))
                painter.drawText(QRect(x + 2, 0, w - 4, pm.height()), Qt.AlignCenter, pct)
            x += w
            remaining = pm.width() - x
            if remaining <= 0:
                break
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
    finally:
        painter.end()
    return pm


def refresh_top_color_bar(main_window) -> None:
    # 表示対象がないときはバーを消してキャッシュキーも初期化する。
    bars = getattr(main_window, "_last_top_bars", None)
    if not bars:
        main_window._top_bar_render_key = None
        main_window.top_colors_bar.clear()
        return

    def _bar_key_item(item):
        if len(item) == 3:
            name, ratio, color = item
        else:
            name, ratio, color = "", item[0], item[1]
        return (
            str(name),
            round(float(ratio), 6),
            tuple(int(c) for c in color),
        )

    render_key = (
        int(main_window.top_colors_bar.width()),
        int(main_window.top_colors_bar.height()),
        tuple(_bar_key_item(item) for item in bars),
    )
    # 前回描画と同じ条件なら再レンダリングを省略する。
    if render_key == getattr(main_window, "_top_bar_render_key", None):
        return
    main_window._top_bar_render_key = render_key
    main_window.top_colors_bar.setPixmap(
        render_top_color_bar(
            bars,
            width=main_window.top_colors_bar.width(),
            height=main_window.top_colors_bar.height(),
        )
    )


def _new_empty_result_snapshot() -> dict:
    return {
        "bgr_preview": None,
        "hist": None,
        "sv": None,
        "rgb": None,
        "h_plane": None,
        "s_plane": None,
        "v_plane": None,
        "h_hist": None,
        "s_hist": None,
        "v_hist": None,
        "top_colors": None,
        "warm_ratio": 0.0,
        "cool_ratio": 0.0,
        "other_ratio": 0.0,
        "dt_ms": 0.0,
        "cap": None,
        "graph_update": False,
    }


def _ensure_snapshot_state(main_window) -> None:
    if not hasattr(main_window, "_latest_result_snapshot"):
        main_window._latest_result_snapshot = _new_empty_result_snapshot()
    if not hasattr(main_window, "_latest_result_version"):
        main_window._latest_result_version = 0
    if not hasattr(main_window, "_dock_rendered_version"):
        main_window._dock_rendered_version = {}


def _store_result_snapshot(
    main_window,
    res: dict,
    *,
    update_bgr: bool = True,
    bump_version: bool = True,
) -> tuple[dict, int]:
    _ensure_snapshot_state(main_window)
    snap = dict(main_window._latest_result_snapshot)

    if update_bgr:
        bgr_preview = res.get("bgr_preview")
        if bgr_preview is not None:
            snap["bgr_preview"] = bgr_preview
    if res.get("cap") is not None:
        snap["cap"] = res.get("cap")
    if res.get("dt_ms") is not None:
        snap["dt_ms"] = float(res.get("dt_ms", 0.0))

    if bool(res.get("graph_update")):
        if res.get("hist") is not None:
            snap["hist"] = res.get("hist")
            snap["warm_ratio"] = float(res.get("warm_ratio", snap["warm_ratio"]))
            snap["cool_ratio"] = float(res.get("cool_ratio", snap["cool_ratio"]))
            snap["other_ratio"] = float(res.get("other_ratio", snap["other_ratio"]))
        if res.get("top_colors") is not None:
            snap["top_colors"] = res.get("top_colors")
        for key in ("sv", "rgb", "h_plane", "s_plane", "v_plane", "h_hist", "s_hist", "v_hist"):
            value = res.get(key)
            if value is not None:
                snap[key] = value

    if bump_version:
        main_window._latest_result_version = int(main_window._latest_result_version) + 1
    main_window._latest_result_snapshot = snap
    return snap, int(main_window._latest_result_version)


def _dock_name_from_object(main_window, dock) -> str | None:
    dock_name_map = getattr(main_window, "_dock_name_by_object", None)
    if isinstance(dock_name_map, dict):
        return dock_name_map.get(dock)
    for name, mapped in getattr(main_window, "_dock_map", {}).items():
        if mapped is dock:
            return name
    return None


def _mark_docks_rendered(main_window, version: int, dock_names: set[str]) -> None:
    if not dock_names:
        return
    _ensure_snapshot_state(main_window)
    for name in dock_names:
        main_window._dock_rendered_version[name] = int(version)


def _render_color_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    hist = snapshot.get("hist")
    if hist is None or not is_widget_renderable(main_window.dock_color):
        return False
    main_window.wheel.update_hist(hist)
    return True


def _render_color_band_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    hist = snapshot.get("hist")
    if hist is None or not is_widget_renderable(getattr(main_window, "dock_color_band", None)):
        return False
    bars = snapshot.get("top_colors")
    if bars is None:
        _, bars = top_hue_bars(hist)
    main_window._last_top_bars = bars
    refresh_top_color_bar(main_window)
    main_window.lbl_warmcool.setText(
        "暖色: "
        f"{float(snapshot.get('warm_ratio', 0.0))*100:.1f}%   "
        f"寒色: {float(snapshot.get('cool_ratio', 0.0))*100:.1f}%   "
        f"その他: {float(snapshot.get('other_ratio', 0.0))*100:.1f}%"
    )
    return True


def _render_scatter_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    sv = snapshot.get("sv")
    rgb = snapshot.get("rgb")
    if sv is None or rgb is None or not is_widget_renderable(main_window.dock_scatter):
        return False
    main_window.scatter.update_scatter(sv, rgb)
    return True


def _apply_hsv_hist_fallback_from_bgr(snapshot: dict, bgr_preview) -> tuple[object, object, object]:
    h_hist = snapshot.get("h_hist")
    s_hist = snapshot.get("s_hist")
    v_hist = snapshot.get("v_hist")
    h_plane = snapshot.get("h_plane")
    s_plane = snapshot.get("s_plane")
    v_plane = snapshot.get("v_plane")
    need_h_fallback = h_hist is None and h_plane is None
    need_s_fallback = s_hist is None and s_plane is None
    need_v_fallback = v_hist is None and v_plane is None
    if (
        (need_h_fallback or need_s_fallback or need_v_fallback)
        and bgr_preview is not None
        and bgr_preview.size > 0
    ):
        try:
            h_full, s_full, v_full = cv2.split(cv2.cvtColor(bgr_preview, cv2.COLOR_BGR2HSV))
            if need_h_fallback:
                h_hist = np.bincount(h_full[s_full > 0].ravel(), minlength=180)[:180].astype(
                    np.int64
                )
                snapshot["h_hist"] = h_hist
            if need_s_fallback:
                s_hist = np.bincount(s_full.ravel(), minlength=256)[:256].astype(np.int64)
                snapshot["s_hist"] = s_hist
            if need_v_fallback:
                v_hist = np.bincount(v_full.ravel(), minlength=256)[:256].astype(np.int64)
                snapshot["v_hist"] = v_hist
        except Exception:
            pass
    return h_hist, s_hist, v_hist


def _render_hist_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    if not is_widget_renderable(main_window.dock_hist):
        return False
    bgr_preview = snapshot.get("bgr_preview")
    h_hist, s_hist, v_hist = _apply_hsv_hist_fallback_from_bgr(snapshot, bgr_preview)
    h_plane = snapshot.get("h_plane")
    s_plane = snapshot.get("s_plane")
    v_plane = snapshot.get("v_plane")

    if h_hist is not None:
        main_window.hist_h.update_from_hist(h_hist)
    elif h_plane is not None:
        main_window.hist_h.update_from_values(h_plane)
    else:
        return False
    if s_hist is not None:
        main_window.hist_s.update_from_hist(s_hist)
    elif s_plane is not None:
        main_window.hist_s.update_from_values(s_plane)
    else:
        return False
    if v_hist is not None:
        main_window.hist_v.update_from_hist(v_hist)
    elif v_plane is not None:
        main_window.hist_v.update_from_values(v_plane)
    else:
        return False

    # H/S/V のY軸上限を揃えて、チャネル間の相対比較をしやすくする。
    shared_max_y = max(
        int(main_window.hist_h.bucketed_max()),
        int(main_window.hist_s.bucketed_max()),
        int(main_window.hist_v.bucketed_max()),
    )
    for hist_view in (main_window.hist_h, main_window.hist_s, main_window.hist_v):
        hist_view.set_shared_max_y(shared_max_y if shared_max_y > 0 else None)
    return True


def _update_single_image_dock_from_frame(main_window, target_dock, bgr_preview) -> bool:
    if bgr_preview is None:
        return False
    if not is_widget_renderable(target_dock):
        return False
    dock_widget = target_dock.widget()
    if not is_widget_renderable(dock_widget):
        return False
    for dock, update_fn, after_fn in getattr(main_window, "_image_update_targets", ()):
        if dock is not target_dock:
            continue
        update_fn(bgr_preview)
        if after_fn is not None:
            after_fn()
        return True
    return False


def update_image_docks_from_frame(main_window, bgr_preview) -> set[str]:
    # 可視ドックだけ更新して不要な画像処理を避ける。
    if bgr_preview is None:
        return set()
    updated_docks: set[str] = set()
    for dock, update_fn, after_fn in getattr(main_window, "_image_update_targets", ()):
        if not is_widget_renderable(dock):
            continue
        dock_widget = dock.widget()
        if not is_widget_renderable(dock_widget):
            continue
        update_fn(bgr_preview)
        if after_fn is not None:
            after_fn()
        name = _dock_name_from_object(main_window, dock)
        if name is not None:
            updated_docks.add(name)
    return updated_docks


def _snapshot_has_graph_data_for_dock(snapshot: dict, dock_name: str) -> bool:
    if dock_name in (_SNAPSHOT_DOCK_COLOR, _SNAPSHOT_DOCK_COLOR_BAND):
        return snapshot.get("hist") is not None
    if dock_name == _SNAPSHOT_DOCK_SCATTER:
        return snapshot.get("sv") is not None and snapshot.get("rgb") is not None
    if dock_name == _SNAPSHOT_DOCK_HIST:
        has_h = snapshot.get("h_hist") is not None or snapshot.get("h_plane") is not None
        has_s = snapshot.get("s_hist") is not None or snapshot.get("s_plane") is not None
        has_v = snapshot.get("v_hist") is not None or snapshot.get("v_plane") is not None
        return has_h and has_s and has_v
    return True


def _is_worker_running(main_window) -> bool:
    thread = getattr(main_window.worker, "_thread", None)
    return bool(thread is not None and thread.is_alive())


def _ensure_snapshot_graph_data_for_dock(main_window, dock_name: str) -> bool:
    _ensure_snapshot_state(main_window)
    snapshot = main_window._latest_result_snapshot
    if _snapshot_has_graph_data_for_dock(snapshot, dock_name):
        return True
    if _is_worker_running(main_window):
        return False

    bgr_preview = snapshot.get("bgr_preview")
    if bgr_preview is None:
        bgr_preview, cap, err = main_window.worker.capture_once()
        if bgr_preview is None:
            if err:
                main_window.on_status(err)
            return False
        snapshot, _ = _store_result_snapshot(
            main_window,
            {"bgr_preview": bgr_preview, "cap": cap, "graph_update": False},
            update_bgr=True,
            bump_version=True,
        )

    try:
        graph_res = analyze_bgr_frame(
            bgr=bgr_preview,
            sample_points=int(main_window.spin_points.value()),
            wheel_sat_threshold=main_window._selected_wheel_sat_threshold(),
            max_dim=int(main_window.worker.cfg.max_dim),
        )
    except Exception:
        return False
    if graph_res is None:
        return False
    graph_res["graph_update"] = True
    _store_result_snapshot(main_window, graph_res, update_bgr=False, bump_version=True)
    return _snapshot_has_graph_data_for_dock(main_window._latest_result_snapshot, dock_name)


def restore_dock_from_snapshot(main_window, dock) -> None:
    if dock is None or not dock.isVisible():
        return
    dock_name = _dock_name_from_object(main_window, dock)
    if dock_name is None:
        return

    _ensure_snapshot_state(main_window)
    snapshot_version = int(main_window._latest_result_version)
    if snapshot_version <= 0:
        return
    rendered_version = int(main_window._dock_rendered_version.get(dock_name, 0))
    if rendered_version == snapshot_version:
        return

    if dock_name in (
        _SNAPSHOT_DOCK_COLOR,
        _SNAPSHOT_DOCK_COLOR_BAND,
        _SNAPSHOT_DOCK_SCATTER,
        _SNAPSHOT_DOCK_HIST,
    ):
        if not _ensure_snapshot_graph_data_for_dock(main_window, dock_name):
            return

    snapshot = main_window._latest_result_snapshot
    updated = False
    if dock_name == _SNAPSHOT_DOCK_COLOR:
        updated = _render_color_dock_from_snapshot(main_window, snapshot)
    elif dock_name == _SNAPSHOT_DOCK_COLOR_BAND:
        updated = _render_color_band_dock_from_snapshot(main_window, snapshot)
    elif dock_name == _SNAPSHOT_DOCK_SCATTER:
        updated = _render_scatter_dock_from_snapshot(main_window, snapshot)
    elif dock_name == _SNAPSHOT_DOCK_HIST:
        updated = _render_hist_dock_from_snapshot(main_window, snapshot)
    else:
        updated = _update_single_image_dock_from_frame(
            main_window,
            dock,
            snapshot.get("bgr_preview"),
        )

    if updated:
        _mark_docks_rendered(main_window, int(main_window._latest_result_version), {dock_name})


def on_result(main_window, res: dict):
    # 例外時でも inflight フラグを解除するため finally で終端する。
    try:
        snapshot, snapshot_version = _store_result_snapshot(main_window, res)
        rendered_docks: set[str] = set()
        bgr_preview = res.get("bgr_preview")
        if main_window.preview_window.isVisible() and bgr_preview is not None:
            main_window.preview_window.update_preview(bgr_preview)

        # graph_update が False のときはグラフ系更新をスキップする。
        if res["graph_update"]:
            if _render_color_dock_from_snapshot(main_window, snapshot):
                rendered_docks.add(_SNAPSHOT_DOCK_COLOR)
            if _render_color_band_dock_from_snapshot(main_window, snapshot):
                rendered_docks.add(_SNAPSHOT_DOCK_COLOR_BAND)
            if _render_scatter_dock_from_snapshot(main_window, snapshot):
                rendered_docks.add(_SNAPSHOT_DOCK_SCATTER)
            if _render_hist_dock_from_snapshot(main_window, snapshot):
                rendered_docks.add(_SNAPSHOT_DOCK_HIST)

        rendered_docks.update(update_image_docks_from_frame(main_window, bgr_preview))
        _mark_docks_rendered(main_window, snapshot_version, rendered_docks)
    finally:
        # 同一フレーム内で使った縮小キャッシュを破棄して次フレームへ持ち越さない。
        clear_cvt_color_cache()
        clear_resize_cache()
        main_window.worker.mark_result_consumed()
