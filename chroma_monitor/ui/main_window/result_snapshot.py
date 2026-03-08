"""解析結果スナップショットの保持と各ドックへの復元処理。"""

import cv2
import numpy as np

from ...analysis.frame_analysis import (
    _compute_hsv_histograms,
    _compute_wheel_stats,
    _prepare_hsv8_and_bgr8,
    _sample_sv_and_rgb,
)
from ...util import constants as C
from ...util.image_ops import (
    clear_cvt_color_cache,
    clear_resize_cache,
    cvt_color_cached,
    resize_by_long_edge,
)
from ...util.qt_helpers import is_widget_renderable
from .result_color_band import (
    _color_band_sat_threshold_from_ui,
    _top_bars_chromatic_medoid,
    render_color_band_dock_from_snapshot,
)

_SNAPSHOT_DOCK_COLOR = "dock_color"
_SNAPSHOT_DOCK_COLOR_BAND = "dock_color_band"
_SNAPSHOT_DOCK_SCATTER = "dock_scatter"
_SNAPSHOT_DOCK_HIST = "dock_hist"

def _new_empty_result_snapshot() -> dict:
    """解析結果スナップショットの初期値を返す。"""
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
        "top_colors_full": None,
        "top_colors_filtered": None,
        "top_colors_key": None,
        "warm_ratio": 0.0,
        "cool_ratio": 0.0,
        "other_ratio": 0.0,
        "dt_ms": 0.0,
        "cap": None,
        "graph_update": False,
    }


def _ensure_snapshot_state(main_window) -> None:
    """スナップショット保持に必要な状態フィールドを初期化する。"""
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
    """新しい結果を既存スナップショットへ反映し、必要なら版数を進める。"""
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
        snap["top_colors_full"] = None
        snap["top_colors_filtered"] = None
        snap["top_colors_key"] = None
        snap["top_colors"] = res.get("top_colors")
        if res.get("hist") is not None:
            snap["hist"] = res.get("hist")
            snap["warm_ratio"] = float(res.get("warm_ratio", snap["warm_ratio"]))
            snap["cool_ratio"] = float(res.get("cool_ratio", snap["cool_ratio"]))
            snap["other_ratio"] = float(res.get("other_ratio", snap["other_ratio"]))
        for key in ("sv", "rgb", "h_plane", "s_plane", "v_plane", "h_hist", "s_hist", "v_hist"):
            value = res.get(key)
            if value is not None:
                snap[key] = value

    if bump_version:
        main_window._latest_result_version = int(main_window._latest_result_version) + 1
    main_window._latest_result_snapshot = snap
    return snap, int(main_window._latest_result_version)


def _dock_name_from_object(main_window, dock) -> str | None:
    """ドックオブジェクトから内部ドック名を逆引きする。"""
    dock_name_map = getattr(main_window, "_dock_name_by_object", None)
    if isinstance(dock_name_map, dict):
        return dock_name_map.get(dock)
    for name, mapped in getattr(main_window, "_dock_map", {}).items():
        if mapped is dock:
            return name
    return None


def _mark_docks_rendered(main_window, version: int, dock_names: set[str]) -> None:
    """指定ドック群を「version反映済み」として記録する。"""
    if not dock_names:
        return
    _ensure_snapshot_state(main_window)
    for name in dock_names:
        main_window._dock_rendered_version[name] = int(version)


def _render_color_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    """色相環ドックへスナップショットを反映する。"""
    hist = snapshot.get("hist")
    if hist is None or not is_widget_renderable(main_window.dock_color):
        return False
    main_window.wheel.update_hist(hist)
    return True


def _render_scatter_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    """散布図ドックへスナップショットを反映する。"""
    sv = snapshot.get("sv")
    rgb = snapshot.get("rgb")
    if sv is None or rgb is None or not is_widget_renderable(main_window.dock_scatter):
        return False
    main_window.scatter.update_scatter(sv, rgb)
    return True


def _has_hsv_channel_data(snapshot: dict, channel: str) -> bool:
    """指定HSVチャネルの描画に必要なデータがあるか判定する。"""
    return (
        snapshot.get(f"{channel}_hist") is not None
        or snapshot.get(f"{channel}_plane") is not None
    )


def _hsv_hist_fallback_flags(snapshot: dict) -> tuple[bool, bool, bool]:
    """不足しているHSVヒストグラムチャネルを判定する。"""
    need_h = not _has_hsv_channel_data(snapshot, "h")
    need_s = not _has_hsv_channel_data(snapshot, "s")
    need_v = not _has_hsv_channel_data(snapshot, "v")
    return need_h, need_s, need_v


def _apply_hsv_hist_fallback_from_bgr(snapshot: dict, bgr_preview) -> tuple[object, object, object]:
    """ヒストデータ欠損時に bgr からH/S/Vヒストグラムを補完する。"""
    h_hist = snapshot.get("h_hist")
    s_hist = snapshot.get("s_hist")
    v_hist = snapshot.get("v_hist")
    need_h_fallback, need_s_fallback, need_v_fallback = _hsv_hist_fallback_flags(snapshot)
    if (
        (need_h_fallback or need_s_fallback or need_v_fallback)
        and bgr_preview is not None
        and bgr_preview.size > 0
    ):
        try:
            hsv_full = cvt_color_cached(bgr_preview, cv2.COLOR_BGR2HSV)
            h_full = hsv_full[:, :, 0]
            s_full = hsv_full[:, :, 1]
            v_full = hsv_full[:, :, 2]
            if need_h_fallback:
                h_hist = np.bincount(h_full[s_full > 0].ravel(), minlength=180)[:180]
                snapshot["h_hist"] = h_hist
            if need_s_fallback:
                s_hist = np.bincount(s_full.ravel(), minlength=256)[:256]
                snapshot["s_hist"] = s_hist
            if need_v_fallback:
                v_hist = np.bincount(v_full.ravel(), minlength=256)[:256]
                snapshot["v_hist"] = v_hist
        except Exception:
            pass
    return h_hist, s_hist, v_hist


def _render_hist_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    """HSVヒストグラムドックへスナップショットを反映する。"""
    if not is_widget_renderable(main_window.dock_hist):
        return False
    bgr_preview = snapshot.get("bgr_preview")
    h_hist, s_hist, v_hist = _apply_hsv_hist_fallback_from_bgr(snapshot, bgr_preview)
    hist_pairs = (
        (main_window.hist_h, h_hist, snapshot.get("h_plane")),
        (main_window.hist_s, s_hist, snapshot.get("s_plane")),
        (main_window.hist_v, v_hist, snapshot.get("v_plane")),
    )
    for view, hist_values, plane_values in hist_pairs:
        if not _render_hist_channel(view, hist_values, plane_values):
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


def _render_hist_channel(hist_view, hist_values, plane_values) -> bool:
    """ヒストビュー1チャネル分を更新する。"""
    if hist_values is not None:
        hist_view.update_from_hist(hist_values)
        return True
    if plane_values is not None:
        hist_view.update_from_values(plane_values)
        return True
    return False


def _ensure_image_update_target_map(main_window) -> dict:
    """画像系ドック更新ターゲットの参照マップを返す。"""
    target_map = getattr(main_window, "_image_update_target_map", None)
    if isinstance(target_map, dict):
        return target_map
    target_map = {
        dock: (update_fn, after_fn)
        for dock, update_fn, after_fn in getattr(main_window, "_image_update_targets", ())
    }
    main_window._image_update_target_map = target_map
    return target_map


def _apply_image_update_target(
    main_window,
    target_dock,
    bgr_preview,
    *,
    target_map: dict | None = None,
) -> bool:
    """画像系ドック1つへ bgr フレームを反映する。"""
    if bgr_preview is None:
        return False
    if not is_widget_renderable(target_dock):
        return False
    dock_widget = target_dock.widget()
    if not is_widget_renderable(dock_widget):
        return False
    if target_map is None:
        target_map = _ensure_image_update_target_map(main_window)
    target = target_map.get(target_dock)
    if target is None:
        return False
    update_fn, after_fn = target
    update_fn(bgr_preview)
    if after_fn is not None:
        after_fn()
    return True


def _update_single_image_dock_from_frame(main_window, target_dock, bgr_preview) -> bool:
    """単一画像ドック更新の共通ラッパー。"""
    target_map = _ensure_image_update_target_map(main_window)
    return _apply_image_update_target(
        main_window,
        target_dock,
        bgr_preview,
        target_map=target_map,
    )


def update_image_docks_from_frame(main_window, bgr_preview) -> set[str]:
    """可視な画像系ドックへ現在フレームを反映し、更新済み名集合を返す。"""
    # 可視ドックだけ更新して不要な画像処理を避ける。
    if bgr_preview is None:
        return set()
    target_map = _ensure_image_update_target_map(main_window)
    updated_docks: set[str] = set()
    for dock, _update_fn, _after_fn in getattr(main_window, "_image_update_targets", ()):
        if not _apply_image_update_target(
            main_window,
            dock,
            bgr_preview,
            target_map=target_map,
        ):
            continue
        name = _dock_name_from_object(main_window, dock)
        if name is not None:
            updated_docks.add(name)
    return updated_docks


def _snapshot_has_graph_data_for_dock(snapshot: dict, dock_name: str) -> bool:
    """指定ドックに必要なグラフデータが snapshot 内に揃っているか判定する。"""
    if dock_name in (_SNAPSHOT_DOCK_COLOR, _SNAPSHOT_DOCK_COLOR_BAND):
        return snapshot.get("hist") is not None
    if dock_name == _SNAPSHOT_DOCK_SCATTER:
        return snapshot.get("sv") is not None and snapshot.get("rgb") is not None
    if dock_name == _SNAPSHOT_DOCK_HIST:
        return all(_has_hsv_channel_data(snapshot, ch) for ch in ("h", "s", "v"))
    return True


def _graph_requirements_for_dock(dock_name: str) -> tuple[bool, bool, bool, bool]:
    """ドック種別から必要なグラフ計算種別を返す。"""
    need_color = dock_name in (_SNAPSHOT_DOCK_COLOR, _SNAPSHOT_DOCK_COLOR_BAND)
    need_color_band = dock_name == _SNAPSHOT_DOCK_COLOR_BAND
    need_scatter = dock_name == _SNAPSHOT_DOCK_SCATTER
    need_hsv_hist = dock_name == _SNAPSHOT_DOCK_HIST
    return need_color, need_color_band, need_scatter, need_hsv_hist


def _compute_graph_subset_from_bgr(
    main_window,
    bgr_preview,
    *,
    need_color: bool,
    need_color_band: bool,
    need_scatter: bool,
    need_hsv_hist: bool,
) -> dict:
    """必要な項目だけを解析し、snapshot更新用の辞書を返す。"""
    bgr_small = resize_by_long_edge(np.asarray(bgr_preview), int(main_window.worker.cfg.max_dim))
    bgr_u8, h, s, v = _prepare_hsv8_and_bgr8(bgr_small)

    out = {
        "hist": None,
        "top_colors": None,
        "sv": None,
        "rgb": None,
        "h_hist": None,
        "s_hist": None,
        "v_hist": None,
        "warm_ratio": 0.0,
        "cool_ratio": 0.0,
        "other_ratio": 0.0,
    }

    if need_hsv_hist:
        h_hist, s_hist, v_hist = _compute_hsv_histograms(h, s, v)
        out["h_hist"] = h_hist
        out["s_hist"] = s_hist
        out["v_hist"] = v_hist

    if need_color:
        sat_th = int(main_window._selected_wheel_sat_threshold())
        sat_th = int(np.clip(sat_th, C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX))
        h_wheel = h[s >= sat_th]
        hist, warm_ratio, cool_ratio, other_ratio = _compute_wheel_stats(h_wheel)
        out["hist"] = hist
        out["warm_ratio"] = float(warm_ratio)
        out["cool_ratio"] = float(cool_ratio)
        out["other_ratio"] = float(other_ratio)

    if need_scatter:
        sv, rgb = _sample_sv_and_rgb(h, s, v, bgr_u8, int(main_window.spin_points.value()))
        out["sv"] = sv
        out["rgb"] = rgb
    if need_color_band:
        # ライブ解析と同様に、配色比率は解析解像度（max_dim適用後）で算出する。
        out["top_colors"] = _top_bars_chromatic_medoid(
            bgr_u8,
            sat_threshold=_color_band_sat_threshold_from_ui(main_window),
        )

    return out


def _is_worker_running(main_window) -> bool:
    """ライブ解析ワーカーが稼働中かを返す。"""
    thread = getattr(main_window.worker, "_thread", None)
    return bool(thread is not None and thread.is_alive())


def _ensure_snapshot_graph_data_for_dock(main_window, dock_name: str) -> bool:
    """停止中に不足したドック用グラフデータを都度補完する。"""
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

    need_color, need_color_band, need_scatter, need_hsv_hist = _graph_requirements_for_dock(
        dock_name
    )
    if not (need_color or need_color_band or need_scatter or need_hsv_hist):
        return True
    try:
        graph_res = _compute_graph_subset_from_bgr(
            main_window,
            bgr_preview,
            need_color=need_color,
            need_color_band=need_color_band,
            need_scatter=need_scatter,
            need_hsv_hist=need_hsv_hist,
        )
    except Exception:
        return False
    graph_res["graph_update"] = True
    _store_result_snapshot(main_window, graph_res, update_bgr=False, bump_version=True)
    return _snapshot_has_graph_data_for_dock(main_window._latest_result_snapshot, dock_name)


def restore_dock_from_snapshot(main_window, dock) -> None:
    """ドック表示時に必要な内容を最新スナップショットから復元する。"""
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
        updated = render_color_band_dock_from_snapshot(main_window, snapshot)
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
    """ワーカー結果を受け取り、可視ドックへ反映して状態を更新する。"""
    # 例外時でも未消費フラグを解除するため、finallyで必ず後処理する。
    try:
        snapshot, snapshot_version = _store_result_snapshot(main_window, res)
        rendered_docks: set[str] = set()
        bgr_preview = res.get("bgr_preview")
        if main_window.preview_window.isVisible() and bgr_preview is not None:
            main_window.preview_window.update_preview(bgr_preview)

        # graph_update が False の場合は、グラフ系ビュー更新をスキップする。
        if res["graph_update"]:
            if _render_color_dock_from_snapshot(main_window, snapshot):
                rendered_docks.add(_SNAPSHOT_DOCK_COLOR)
            if render_color_band_dock_from_snapshot(main_window, snapshot):
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
