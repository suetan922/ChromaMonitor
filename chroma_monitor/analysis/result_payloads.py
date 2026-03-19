"""解析系モジュール間で共有する payload 契約。"""

from typing import Optional, TypeAlias, TypedDict

import numpy as np

from .top_color_bars import TopColorBar

TopColorsPayload: TypeAlias = Optional[list[TopColorBar]]
CaptureRectPayload: TypeAlias = tuple[int, int, int, int] | None


class GraphDataPayload(TypedDict):
    """1フレーム分のグラフ計算結果。"""

    hist: Optional[np.ndarray]
    sv: Optional[np.ndarray]
    rgb: Optional[np.ndarray]
    h_hist: Optional[np.ndarray]
    s_hist: Optional[np.ndarray]
    v_hist: Optional[np.ndarray]
    top_colors: TopColorsPayload
    warm_ratio: float
    cool_ratio: float
    other_ratio: float


class ResultFramePayload(TypedDict):
    """解析結果と UI スナップショットで共有する基本フィールド。"""

    bgr_preview: Optional[np.ndarray]
    hist: Optional[np.ndarray]
    sv: Optional[np.ndarray]
    rgb: Optional[np.ndarray]
    h_plane: Optional[np.ndarray]
    s_plane: Optional[np.ndarray]
    v_plane: Optional[np.ndarray]
    h_hist: Optional[np.ndarray]
    s_hist: Optional[np.ndarray]
    v_hist: Optional[np.ndarray]
    top_colors: TopColorsPayload
    warm_ratio: float
    cool_ratio: float
    other_ratio: float
    dt_ms: float
    cap: CaptureRectPayload
    graph_update: bool


class AnalyzerResultPayload(ResultFramePayload):
    """UI 通知へ流す解析結果ペイロード。"""
