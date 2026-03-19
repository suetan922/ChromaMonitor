"""解析結果スナップショットの保持と各ドックへの復元処理。"""

from typing import cast

import cv2
import numpy as np

from ...analysis import live_graph_data
from ...analysis.result_payloads import AnalyzerResultPayload, ResultFramePayload
from ...analysis.frame_analysis import compute_hsv_histograms
from ...util.image_ops import (
    clear_cvt_color_cache,
    clear_resize_cache,
    cvt_color_cached,
    resize_by_long_edge,
)
from ...util.qt_helpers import is_widget_renderable
from .result_color_band import render_color_band_dock_from_snapshot
from .settings_values import selected_effective_color_band_sat_threshold_safe

_SNAPSHOT_DOCK_COLOR = "dock_color"
_SNAPSHOT_DOCK_COLOR_BAND = "dock_color_band"
_SNAPSHOT_DOCK_SCATTER = "dock_scatter"
_SNAPSHOT_DOCK_HIST = "dock_hist"
_GRAPH_COLOR_DOCKS = (_SNAPSHOT_DOCK_COLOR, _SNAPSHOT_DOCK_COLOR_BAND)
_GRAPH_DOCK_ORDER = (
    _SNAPSHOT_DOCK_COLOR,
    _SNAPSHOT_DOCK_COLOR_BAND,
    _SNAPSHOT_DOCK_SCATTER,
    _SNAPSHOT_DOCK_HIST,
)
_GRAPH_DOCK_REQUIREMENTS = {
    _SNAPSHOT_DOCK_COLOR: (True, False, False, False),
    _SNAPSHOT_DOCK_COLOR_BAND: (True, True, False, False),
    _SNAPSHOT_DOCK_SCATTER: (False, False, True, False),
    _SNAPSHOT_DOCK_HIST: (False, False, False, True),
}


class ResultSnapshot(ResultFramePayload):
    """各ドック復元で共有する最新結果スナップショット。"""

    top_colors_full: list[tuple] | None
    top_colors_filtered: list[tuple] | None
    top_colors_key: tuple | None


def _new_empty_result_snapshot() -> ResultSnapshot:
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
    res: AnalyzerResultPayload,
    *,
    update_bgr: bool = True,
    bump_version: bool = True,
) -> tuple[ResultSnapshot, int]:
    """新しい結果を既存スナップショットへ反映し、必要なら版数を進める。"""
    _ensure_snapshot_state(main_window)
    snap = cast(ResultSnapshot, dict(main_window._latest_result_snapshot))

    if update_bgr:
        # 生画像は必要なときだけ更新する。
        bgr_preview = res.get("bgr_preview")
        if bgr_preview is not None:
            snap["bgr_preview"] = bgr_preview
    if res.get("cap") is not None:
        snap["cap"] = res.get("cap")
    if res.get("dt_ms") is not None:
        snap["dt_ms"] = float(res.get("dt_ms", 0.0))

    if bool(res.get("graph_update")):
        # 再計算される派生値は毎回クリアする。
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


def _render_color_dock_from_snapshot(main_window, snapshot: ResultSnapshot) -> bool:
    """色相環ドックへスナップショットを反映する。"""
    hist = snapshot.get("hist")
    if hist is None or not is_widget_renderable(main_window.dock_color):
        return False
    main_window.wheel.update_hist(hist)
    return True


def _render_scatter_dock_from_snapshot(main_window, snapshot: ResultSnapshot) -> bool:
    """散布図ドックへスナップショットを反映する。"""
    sv = snapshot.get("sv")
    rgb = snapshot.get("rgb")
    if sv is None or rgb is None or not is_widget_renderable(main_window.dock_scatter):
        return False
    main_window.scatter.update_scatter(sv, rgb)
    return True


def _has_hsv_channel_data(snapshot: ResultSnapshot, channel: str) -> bool:
    """指定HSVチャネルの描画に必要なデータがあるか判定する。"""
    return (
        snapshot.get(f"{channel}_hist") is not None or snapshot.get(f"{channel}_plane") is not None
    )


def _hsv_hist_fallback_flags(snapshot: ResultSnapshot) -> tuple[bool, bool, bool]:
    """不足しているHSVヒストグラムチャネルを判定する。"""
    need_h = not _has_hsv_channel_data(snapshot, "h")
    need_s = not _has_hsv_channel_data(snapshot, "s")
    need_v = not _has_hsv_channel_data(snapshot, "v")
    return need_h, need_s, need_v


def _apply_hsv_hist_fallback_from_bgr(
    snapshot: ResultSnapshot,
    bgr_preview,
) -> tuple[object, object, object]:
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
            fallback_h, fallback_s, fallback_v = compute_hsv_histograms(h_full, s_full, v_full)
            if need_h_fallback:
                h_hist = fallback_h
                snapshot["h_hist"] = h_hist
            if need_s_fallback:
                s_hist = fallback_s
                snapshot["s_hist"] = s_hist
            if need_v_fallback:
                v_hist = fallback_v
                snapshot["v_hist"] = v_hist
        except (cv2.error, TypeError, ValueError):
            # 欠損補完に失敗しても既存の snapshot があればそちらを優先する。
            pass
    return h_hist, s_hist, v_hist


def _render_hist_dock_from_snapshot(main_window, snapshot: ResultSnapshot) -> bool:
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


def _image_view_input_bgr(main_window, bgr_preview):
    """画像系ドック描画に使う入力フレームを解析解像度設定で正規化する。"""
    if bgr_preview is None:
        return None
    try:
        max_dim = int(getattr(main_window.worker.cfg, "max_dim", 0))
    except (AttributeError, TypeError, ValueError):
        max_dim = 0
    return resize_by_long_edge(np.asarray(bgr_preview), max_dim)


def _selected_wheel_sat_threshold(main_window) -> int:
    """現在 UI で有効な色相環彩度しきい値を安全に返す。"""
    selector = getattr(main_window, "_selected_wheel_sat_threshold", None)
    if selector is None:
        return 0
    try:
        return int(selector())
    except (TypeError, ValueError):
        return 0


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


def update_image_docks_from_frame(main_window, bgr_preview) -> set[str]:
    """可視な画像系ドックへ現在フレームを反映し、更新済み名集合を返す。"""
    # 可視ドックだけ更新して不要な画像処理を避ける。
    if bgr_preview is None:
        return set()
    bgr_input = _image_view_input_bgr(main_window, bgr_preview)
    if bgr_input is None:
        return set()
    target_map = _ensure_image_update_target_map(main_window)
    updated_docks: set[str] = set()
    for dock, _update_fn, _after_fn in getattr(main_window, "_image_update_targets", ()):
        if not _apply_image_update_target(
            main_window,
            dock,
            bgr_input,
            target_map=target_map,
        ):
            continue
        name = _dock_name_from_object(main_window, dock)
        if name is not None:
            updated_docks.add(name)
    return updated_docks


def _snapshot_has_graph_data_for_dock(snapshot: ResultSnapshot, dock_name: str) -> bool:
    """指定ドックに必要なグラフデータが snapshot 内に揃っているか判定する。"""
    if dock_name in _GRAPH_COLOR_DOCKS:
        return snapshot.get("hist") is not None
    if dock_name == _SNAPSHOT_DOCK_SCATTER:
        return snapshot.get("sv") is not None and snapshot.get("rgb") is not None
    if dock_name == _SNAPSHOT_DOCK_HIST:
        return all(_has_hsv_channel_data(snapshot, ch) for ch in ("h", "s", "v"))
    return True


def _is_worker_running(main_window) -> bool:
    """ライブ解析ワーカーが稼働中かを返す。"""
    thread = getattr(main_window.worker, "_thread", None)
    return bool(thread is not None and thread.is_alive())


def _ensure_snapshot_graph_data_for_dock(main_window, dock_name: str) -> bool:
    """停止中に不足したドック用グラフデータを都度補完する。"""
    _ensure_snapshot_state(main_window)
    snapshot = main_window._latest_result_snapshot
    # 既に足りていれば再計算しない。
    if _snapshot_has_graph_data_for_dock(snapshot, dock_name):
        return True
    # 稼働中はワーカーの更新を待つ。
    if _is_worker_running(main_window):
        return False

    bgr_preview = snapshot.get("bgr_preview")
    if bgr_preview is None:
        # 停止中は1回だけ手動キャプチャする。
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

    need_color, need_color_band, need_scatter, need_hsv_hist = _GRAPH_DOCK_REQUIREMENTS.get(
        dock_name, (False, False, False, False)
    )
    if not (need_color or need_color_band or need_scatter or need_hsv_hist):
        return True
    try:
        # 必要な項目だけ部分再計算。
        graph_res = live_graph_data.collect_graph_data(
            np.asarray(bgr_preview),
            live_graph_data.GraphDataConfig(
                sample_points=int(main_window.spin_points.value()),
                max_dim=int(getattr(main_window.worker.cfg, "max_dim", 0)),
                wheel_sat_threshold=_selected_wheel_sat_threshold(main_window),
                color_band_sat_threshold=selected_effective_color_band_sat_threshold_safe(
                    main_window
                ),
            ),
            need_color=need_color,
            need_color_band=need_color_band,
            need_scatter=need_scatter,
            need_hsv_hist=need_hsv_hist,
        )
    except (cv2.error, TypeError, ValueError):
        return False
    graph_res["graph_update"] = True
    _store_result_snapshot(main_window, graph_res, update_bgr=False, bump_version=True)
    return _snapshot_has_graph_data_for_dock(main_window._latest_result_snapshot, dock_name)


def _resolve_restore_target_dock_name(main_window, dock, *, force: bool = False) -> str | None:
    """復元対象ドック名を検証し、復元不要なら None を返す。"""
    if dock is None or not dock.isVisible():
        return None
    dock_name = _dock_name_from_object(main_window, dock)
    if dock_name is None:
        return None

    _ensure_snapshot_state(main_window)
    snapshot_version = int(main_window._latest_result_version)
    if bool(force):
        # 跨ぎ/再配置後の描画崩れ復旧では、同一versionでも再描画を許可する。
        # ただし未取得状態(version=0)では復元対象が無いため通常通り終了する。
        if snapshot_version <= 0:
            return None
        return str(dock_name)
    if snapshot_version <= 0:
        return None
    rendered_version = int(main_window._dock_rendered_version.get(dock_name, 0))
    if rendered_version == snapshot_version:
        return None
    return str(dock_name)


def _ensure_graph_snapshot_for_restore(main_window, dock_name: str) -> bool:
    """グラフ系ドック復元に必要なスナップショット補完を行う。"""
    if dock_name not in _GRAPH_DOCK_ORDER:
        return True
    return bool(_ensure_snapshot_graph_data_for_dock(main_window, dock_name))


def _render_graph_dock_by_name(
    main_window,
    dock_name: str,
    snapshot: ResultSnapshot,
) -> bool | None:
    """グラフ系ドック名なら描画し、非グラフ系なら None を返す。"""
    if dock_name == _SNAPSHOT_DOCK_COLOR:
        return bool(_render_color_dock_from_snapshot(main_window, snapshot))
    if dock_name == _SNAPSHOT_DOCK_COLOR_BAND:
        return bool(render_color_band_dock_from_snapshot(main_window, snapshot))
    if dock_name == _SNAPSHOT_DOCK_SCATTER:
        return bool(_render_scatter_dock_from_snapshot(main_window, snapshot))
    if dock_name == _SNAPSHOT_DOCK_HIST:
        return bool(_render_hist_dock_from_snapshot(main_window, snapshot))
    return None


def _render_dock_from_snapshot_by_name(
    main_window,
    dock_name: str,
    dock,
    snapshot: ResultSnapshot,
) -> bool:
    """ドック名に対応する復元描画を実行し、更新成否を返す。"""
    graph_updated = _render_graph_dock_by_name(main_window, dock_name, snapshot)
    if graph_updated is not None:
        return bool(graph_updated)
    return bool(
        _apply_image_update_target(
            main_window,
            dock,
            _image_view_input_bgr(main_window, snapshot.get("bgr_preview")),
            target_map=_ensure_image_update_target_map(main_window),
        )
    )


def _render_all_graph_docks(main_window, snapshot: ResultSnapshot) -> set[str]:
    """グラフ系ドックを順番に描画し、更新済み名を返す。"""
    rendered: set[str] = set()
    # 依存関係が弱い順で描画する。
    for dock_name in _GRAPH_DOCK_ORDER:
        updated = _render_graph_dock_by_name(main_window, dock_name, snapshot)
        if updated:
            # 成功したドックだけ記録。
            rendered.add(dock_name)
    return rendered


def restore_dock_from_snapshot(main_window, dock, *, force: bool = False) -> None:
    """ドック表示時に必要な内容を最新スナップショットから復元する。"""
    dock_name = _resolve_restore_target_dock_name(main_window, dock, force=bool(force))
    if dock_name is None:
        return
    if not _ensure_graph_snapshot_for_restore(main_window, dock_name):
        return

    snapshot = main_window._latest_result_snapshot
    updated = _render_dock_from_snapshot_by_name(main_window, dock_name, dock, snapshot)
    if updated:
        _mark_docks_rendered(main_window, int(main_window._latest_result_version), {dock_name})


def on_result(main_window, res: AnalyzerResultPayload):
    """ワーカー結果を受け取り、可視ドックへ反映して状態を更新する。"""
    # 例外時でも未消費フラグを解除するため、finallyで必ず後処理する。
    try:
        snapshot, snapshot_version = _store_result_snapshot(main_window, res)
        rendered_docks: set[str] = set()
        bgr_preview = res.get("bgr_preview")
        if main_window.preview_window.isVisible() and bgr_preview is not None:
            main_window.preview_window.update_preview(bgr_preview)

        # graph_update=False ならグラフ再描画は行わない。
        if res["graph_update"]:
            rendered_docks.update(_render_all_graph_docks(main_window, snapshot))

        # 画像系ドックは常に可視分だけ更新する。
        rendered_docks.update(update_image_docks_from_frame(main_window, bgr_preview))
        _mark_docks_rendered(main_window, snapshot_version, rendered_docks)
    finally:
        # 同一フレーム内で使った縮小キャッシュを破棄して次フレームへ持ち越さない。
        clear_cvt_color_cache()
        clear_resize_cache()
        main_window.worker.mark_result_consumed()
