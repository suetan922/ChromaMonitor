"""ライブ解析ワーカーから分離した graph/result 組み立て補助。"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .result_payloads import AnalyzerResultPayload, GraphDataPayload
from .frame_analysis import (
    compute_hsv_histograms,
    compute_wheel_stats_from_hs,
    compute_top_bars_chromatic_medoid,
    compute_top_bars_chromatic_medoid_from_hs,
    prepare_hsv8_and_bgr8,
    sample_sv_and_rgb,
)
from ..util import constants as C
from ..util.image_ops import resize_by_long_edge


@dataclass(frozen=True, slots=True)
class GraphDataConfig:
    """グラフ系集計で使う設定値の最小セット。"""

    sample_points: int
    max_dim: int
    wheel_sat_threshold: int
    color_band_sat_threshold: int


def extract_hsv_channels(
    bgr: np.ndarray,
    *,
    enabled: bool,
) -> tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    """必要時のみ HSV を生成し、チャネルビューを返す。"""
    if not enabled:
        return None, None, None
    _bgr_u8, h, s, v = prepare_hsv8_and_bgr8(bgr)
    return h, s, v


def optional_hsv_histograms(
    *,
    enabled: bool,
    h: Optional[np.ndarray],
    s: Optional[np.ndarray],
    v: Optional[np.ndarray],
) -> tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    """HSVヒストグラムが必要なときだけ集計結果を返す。"""
    if not enabled or h is None or s is None or v is None:
        return None, None, None
    return compute_hsv_histograms(h, s, v)


def optional_wheel_stats(
    *,
    enabled: bool,
    h: Optional[np.ndarray],
    s: Optional[np.ndarray],
    wheel_sat_threshold: int,
) -> tuple[Optional[np.ndarray], float, float, float]:
    """色相環ヒストグラムと暖寒比率を必要時のみ計算する。"""
    if not enabled or h is None or s is None:
        return None, 0.0, 0.0, 0.0
    return compute_wheel_stats_from_hs(h, s, int(wheel_sat_threshold))


def optional_scatter_samples(
    *,
    enabled: bool,
    h: Optional[np.ndarray],
    s: Optional[np.ndarray],
    v: Optional[np.ndarray],
    bgr: np.ndarray,
    sample_points: int,
) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """散布図サンプルが必要なときだけ SV/RGB を生成する。"""
    if not enabled or h is None or s is None or v is None:
        return None, None
    return sample_sv_and_rgb(h, s, v, bgr, sample_points)


def optional_top_colors(
    *,
    enabled: bool,
    bgr: np.ndarray,
    h: Optional[np.ndarray],
    s: Optional[np.ndarray],
    color_band_sat_threshold: int,
):
    """配色比率の代表色を必要時のみ計算する。"""
    if not enabled:
        return None
    if h is not None and s is not None:
        return compute_top_bars_chromatic_medoid_from_hs(
            bgr,
            h,
            s,
            sat_threshold=int(color_band_sat_threshold),
            top_count=int(C.TOP_COLORS_COUNT),
        )
    return compute_top_bars_chromatic_medoid(
        bgr,
        sat_threshold=int(color_band_sat_threshold),
        top_count=int(C.TOP_COLORS_COUNT),
    )


def collect_graph_data(
    bgr: np.ndarray,
    cfg,
    *,
    need_color: bool,
    need_color_band: bool,
    need_scatter: bool,
    need_hsv_hist: bool,
) -> GraphDataPayload:
    """現在フレームから要求されたグラフ項目だけを計算する。"""
    bgr_small = resize_by_long_edge(bgr, cfg.max_dim)
    need_hsv_channels = need_hsv_hist or need_color or need_scatter or need_color_band
    h, s, v = extract_hsv_channels(bgr_small, enabled=need_hsv_channels)
    h_hist, s_hist, v_hist = optional_hsv_histograms(
        enabled=need_hsv_hist,
        h=h,
        s=s,
        v=v,
    )
    hist, warm_ratio, cool_ratio, other_ratio = optional_wheel_stats(
        enabled=need_color,
        h=h,
        s=s,
        wheel_sat_threshold=int(cfg.wheel_sat_threshold),
    )
    sv, rgb = optional_scatter_samples(
        enabled=need_scatter,
        h=h,
        s=s,
        v=v,
        bgr=bgr_small,
        sample_points=int(cfg.sample_points),
    )
    top_colors = optional_top_colors(
        enabled=need_color_band,
        bgr=bgr_small,
        h=h,
        s=s,
        color_band_sat_threshold=int(cfg.color_band_sat_threshold),
    )

    return {
        "hist": hist,
        "sv": sv,
        "rgb": rgb,
        "h_hist": h_hist,
        "s_hist": s_hist,
        "v_hist": v_hist,
        "top_colors": top_colors,
        "warm_ratio": warm_ratio,
        "cool_ratio": cool_ratio,
        "other_ratio": other_ratio,
    }


def view_requirements(cfg) -> tuple[bool, bool, bool, bool, bool, bool]:
    """現在設定からビュー更新要件フラグを返す。"""
    need_color = cfg.view_color
    need_color_band = cfg.view_color_band
    need_scatter = cfg.view_scatter
    need_hsv_hist = cfg.view_hsv_hist
    need_graph_data = need_color or need_color_band or need_scatter or need_hsv_hist
    need_bgr_emit = cfg.view_image or cfg.want_preview
    return (
        need_color,
        need_color_band,
        need_scatter,
        need_hsv_hist,
        need_graph_data,
        need_bgr_emit,
    )


def build_result_payload(
    *,
    bgr: np.ndarray,
    cap,
    graph_data: GraphDataPayload,
    graph_update: bool,
    need_bgr_emit: bool,
    dt_ms: float,
) -> AnalyzerResultPayload:
    """UI通知用ペイロードを組み立てる。"""
    return {
        "bgr_preview": bgr if need_bgr_emit else None,
        "hist": graph_data["hist"] if graph_update else None,
        "sv": graph_data["sv"] if graph_update else None,
        "rgb": graph_data["rgb"] if graph_update else None,
        "h_plane": None,
        "s_plane": None,
        "v_plane": None,
        "h_hist": graph_data["h_hist"] if graph_update else None,
        "s_hist": graph_data["s_hist"] if graph_update else None,
        "v_hist": graph_data["v_hist"] if graph_update else None,
        "top_colors": graph_data["top_colors"] if graph_update else None,
        "warm_ratio": graph_data["warm_ratio"],
        "cool_ratio": graph_data["cool_ratio"],
        "other_ratio": graph_data["other_ratio"],
        "dt_ms": float(dt_ms),
        "cap": (cap.left(), cap.top(), cap.width(), cap.height()),
        "graph_update": bool(graph_update),
    }
