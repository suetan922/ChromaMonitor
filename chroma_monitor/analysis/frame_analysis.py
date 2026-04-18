"""解析処理の補助関数。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional, TypeAlias

import cv2
import numpy as np

from .result_payloads import AnalyzerResultPayload
from .scatter_sampling import sample_sv_and_rgb
from .top_color_bars import TopColorBar, compute_top_bars_from_prepared
from ..util import constants as C
from ..util.image_ops import resize_by_long_edge
from ..util.value_utils import clamp_int

_BGR_CHANNEL_COUNT = 3
_OPENCV_HUE_MAX = 179
_OPENCV_HUE_BINS = 180
_UINT8_MAX_FLOAT = 255.0
_UINT8_BINS = 256
_HUE_FLOAT_TO_OPENCV_SCALE = 0.5
_WARM_HUE_LOW_END = 45
_WARM_HUE_HIGH_START = 150
_COOL_HUE_START = 60
_COOL_HUE_END = 135
_ANALYZE_STEP_CONVERT_HSV = (15, "HSVへ変換中…")
_ANALYZE_STEP_WHEEL_HIST = (30, "色相ヒストグラム集計中…")
_ANALYZE_STEP_SCATTER = (45, "散布図サンプル生成中…")
_ANALYZE_STEP_FINISH_STATS = (65, "統計を仕上げ中…")
_ANALYZE_STEP_BUILD_RESULT = (85, "結果を反映中…")
ProgressCb: TypeAlias = Optional[Callable[[int, str], None]]
CancelCb: TypeAlias = Optional[Callable[[], bool]]


@dataclass(frozen=True, slots=True)
class PreparedAnalysisFrame:
    """解析用に前処理済みの BGR/HSV 各チャネル。"""

    bgr_u8: np.ndarray
    h: np.ndarray
    s: np.ndarray
    v: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisResultData:
    """UI 互換 payload 組み立て直前の集計結果。"""

    bgr_u8: np.ndarray
    hist: np.ndarray
    sv: np.ndarray
    rgb: np.ndarray
    h_hist: np.ndarray
    s_hist: np.ndarray
    v_hist: np.ndarray
    top_colors: list[TopColorBar] | None
    warm_ratio: float
    cool_ratio: float
    other_ratio: float


def _has_bgr_color_channels(arr: np.ndarray) -> bool:
    """配色計算に必要な BGR 3ch 配列かどうかを返す。"""
    return bool(
        arr.size > 0 and arr.ndim == _BGR_CHANNEL_COUNT and arr.shape[2] >= _BGR_CHANNEL_COUNT
    )


def _normalize_bgr_to_float01(bgr: np.ndarray) -> np.ndarray:
    """任意dtype/任意レンジのBGR配列を 0..1 の float32 に正規化する。"""
    arr = np.asarray(bgr)
    if arr.size == 0:
        return np.zeros((0, 0, 3), dtype=np.float32)

    if np.issubdtype(arr.dtype, np.integer):
        info = np.iinfo(arr.dtype)
        scale = float(info.max) if info.max > 0 else 1.0
        out = arr.astype(np.float32) / scale
    else:
        out = arr.astype(np.float32)
        finite = np.isfinite(out)
        if not finite.any():
            return np.zeros_like(out, dtype=np.float32)
        min_v = float(np.nanmin(out))
        max_v = float(np.nanmax(out))
        # 0..1 以外のfloat入力は代表的なレンジを推定して正規化する。
        if min_v < 0.0 or max_v > 1.0:
            if min_v >= 0.0 and max_v <= _UINT8_MAX_FLOAT:
                out = out / _UINT8_MAX_FLOAT
            else:
                out = out / max(1.0, max_v)

    return np.clip(out, 0.0, 1.0)


def prepare_hsv8_and_bgr8(
    bgr: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """入力画像から `uint8` の BGR/H/S/V を揃えて返す。"""
    arr = np.asarray(bgr)
    if arr.dtype == np.uint8:
        hsv = cv2.cvtColor(arr, cv2.COLOR_BGR2HSV)
        # split はチャネルごとの配列コピーが発生するため、ビュー参照で取り出す。
        h = hsv[:, :, 0]
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]
        return arr, h, s, v

    bgr_f = _normalize_bgr_to_float01(arr)
    hsv_f = cv2.cvtColor(bgr_f, cv2.COLOR_BGR2HSV)
    h = np.clip(np.round(hsv_f[:, :, 0] * _HUE_FLOAT_TO_OPENCV_SCALE), 0, _OPENCV_HUE_MAX).astype(
        np.uint8
    )
    s = np.clip(np.round(hsv_f[:, :, 1] * _UINT8_MAX_FLOAT), 0, _UINT8_MAX_FLOAT).astype(
        np.uint8
    )
    v = np.clip(np.round(hsv_f[:, :, 2] * _UINT8_MAX_FLOAT), 0, _UINT8_MAX_FLOAT).astype(
        np.uint8
    )
    bgr_u8 = np.clip(np.round(bgr_f * _UINT8_MAX_FLOAT), 0, _UINT8_MAX_FLOAT).astype(np.uint8)
    return bgr_u8, h, s, v


def compute_hsv_histograms(
    h: np.ndarray,
    s: np.ndarray,
    v: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """H/S/V のヒストグラムを集計する。"""
    # Hヒストグラムは従来どおり色相未定義(S=0)を除外する。
    h_mask = cv2.compare(s, 0, cv2.CMP_GT)
    h_hist = (
        cv2.calcHist([h], [0], h_mask, [_OPENCV_HUE_BINS], [0, _OPENCV_HUE_BINS])
        .reshape(_OPENCV_HUE_BINS)
        .astype(np.int64)
    )
    s_hist = cv2.calcHist([s], [0], None, [_UINT8_BINS], [0, _UINT8_BINS]).reshape(
        _UINT8_BINS
    ).astype(np.int64)
    v_hist = cv2.calcHist([v], [0], None, [_UINT8_BINS], [0, _UINT8_BINS]).reshape(
        _UINT8_BINS
    ).astype(np.int64)
    return h_hist, s_hist, v_hist


def compute_wheel_stats_from_hs(
    h: np.ndarray,
    s: np.ndarray,
    sat_threshold: int,
) -> tuple[np.ndarray, float, float, float]:
    """H/S チャネルから彩度しきい値付きで色相環統計を計算する。"""
    # h[s >= th] の一時配列を作らず、マスク付きヒストグラムで直接集計する。
    if h is None or s is None or h.size <= 0 or s.size <= 0:
        return np.zeros(180, dtype=np.int64), 0.0, 0.0, 0.0

    sat_th = clamp_int(sat_threshold, C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX)
    if sat_th <= C.WHEEL_SAT_THRESHOLD_MIN:
        mask = None
        total_color = float(h.size)
    else:
        mask = cv2.compare(s, int(sat_th) - 1, cv2.CMP_GT)
        total_color = float(cv2.countNonZero(mask))
        if total_color <= 0.0:
            return np.zeros(180, dtype=np.int64), 0.0, 0.0, 0.0

    hist_raw = cv2.calcHist([h], [0], mask, [180], [0, 180]).reshape(180).astype(np.int64)
    warm_count = float(
        hist_raw[:_WARM_HUE_LOW_END].sum() + hist_raw[_WARM_HUE_HIGH_START:180].sum()
    )
    cool_count = float(hist_raw[_COOL_HUE_START:_COOL_HUE_END].sum())
    other_count = max(0.0, total_color - warm_count - cool_count)
    return (
        hist_raw,
        warm_count / total_color,
        cool_count / total_color,
        other_count / total_color,
    )


def compute_top_bars_chromatic_medoid_from_hs(
    bgr_u8: np.ndarray | None,
    h: np.ndarray | None,
    s: np.ndarray | None,
    *,
    sat_threshold: int = 0,
    top_count: int = 8,
) -> list[TopColorBar]:
    """前計算済み H/S を使って配色比率上位色を計算する。"""
    if bgr_u8 is None or h is None or s is None:
        return []
    bgr_arr = np.asarray(bgr_u8)
    h_arr = np.asarray(h)
    s_arr = np.asarray(s)
    if bgr_arr.dtype != np.uint8 or h_arr.dtype != np.uint8 or s_arr.dtype != np.uint8:
        # 想定外dtypeは既存経路にフォールバックし、表示結果の互換性を優先する。
        return compute_top_bars_chromatic_medoid(
            bgr_arr,
            sat_threshold=sat_threshold,
            top_count=top_count,
        )
    return compute_top_bars_from_prepared(
        bgr_u8=bgr_arr,
        h=h_arr,
        s=s_arr,
        sat_threshold=sat_threshold,
        top_count=top_count,
    )


def compute_top_bars_chromatic_medoid(
    bgr_preview: np.ndarray | None,
    *,
    sat_threshold: int = 0,
    top_count: int = 8,
) -> list[TopColorBar]:
    """配色比率表示用の上位色を返す。

    Returns:
        [(色名, 割合(0..1), (R, G, B)), ...]
    """
    if bgr_preview is None:
        return []
    bgr = np.asarray(bgr_preview)
    if not _has_bgr_color_channels(bgr):
        return []

    bgr_u8, h, s, _v = prepare_hsv8_and_bgr8(bgr)
    return compute_top_bars_from_prepared(
        bgr_u8=bgr_u8,
        h=h,
        s=s,
        sat_threshold=sat_threshold,
        top_count=top_count,
    )


def _emit_progress_if_needed(
    progress_cb: ProgressCb,
    percent: int,
    text: str,
) -> None:
    """進捗コールバックが設定されている場合のみ通知する。"""
    if progress_cb is not None:
        progress_cb(int(percent), text)


def _is_canceled_safe(cancel_cb: CancelCb) -> bool:
    """キャンセルコールバックを安全に評価する。"""
    if cancel_cb is None:
        return False
    try:
        return bool(cancel_cb())
    except Exception:
        return False


def _emit_step_and_check_cancel(
    progress_cb: ProgressCb,
    cancel_cb: CancelCb,
    *,
    percent: int,
    text: str,
) -> bool:
    """進捗通知を行い、その直後にキャンセル要求を確認する。"""
    _emit_progress_if_needed(progress_cb, int(percent), str(text))
    return _is_canceled_safe(cancel_cb)


def _check_analysis_step(
    progress_cb: ProgressCb,
    cancel_cb: CancelCb,
    step: tuple[int, str],
) -> bool:
    """解析進捗1ステップを通知し、その直後にキャンセル要求を確認する。"""
    percent, text = step
    return _emit_step_and_check_cancel(
        progress_cb,
        cancel_cb,
        percent=int(percent),
        text=str(text),
    )


def _compute_optional_top_colors(
    bgr_u8: np.ndarray,
    h: np.ndarray,
    s: np.ndarray,
    color_band_sat_threshold: int | None,
) -> list[TopColorBar] | None:
    """配色比率が必要な場合だけ上位色を計算する。"""
    if color_band_sat_threshold is None:
        return None
    # 配色比率は必要時のみ計算。
    return compute_top_bars_chromatic_medoid_from_hs(
        bgr_u8,
        h,
        s,
        sat_threshold=int(color_band_sat_threshold),
        top_count=int(C.TOP_COLORS_COUNT),
    )


def _normalize_analysis_input(bgr: np.ndarray, max_dim: int) -> np.ndarray:
    """入力フレームを解析用サイズへ正規化する。"""
    return resize_by_long_edge(np.asarray(bgr), int(max_dim))


def _prepare_analysis_frame(bgr_work: np.ndarray) -> PreparedAnalysisFrame:
    """解析に必要な BGR/HSV 各チャネルを前計算する。"""
    bgr_u8, h, s, v = prepare_hsv8_and_bgr8(bgr_work)
    return PreparedAnalysisFrame(bgr_u8=bgr_u8, h=h, s=s, v=v)


def _compute_wheel_and_hsv_histograms(
    frame: PreparedAnalysisFrame,
    wheel_sat_threshold: int,
) -> tuple[np.ndarray, float, float, float, np.ndarray, np.ndarray, np.ndarray]:
    """色相環統計と H/S/V ヒストグラムをまとめて計算する。"""
    hist, warm_ratio, cool_ratio, other_ratio = compute_wheel_stats_from_hs(
        frame.h,
        frame.s,
        int(wheel_sat_threshold),
    )
    h_hist, s_hist, v_hist = compute_hsv_histograms(frame.h, frame.s, frame.v)
    return hist, warm_ratio, cool_ratio, other_ratio, h_hist, s_hist, v_hist


def _compute_scatter_samples(
    frame: PreparedAnalysisFrame,
    sample_points: int,
) -> tuple[np.ndarray, np.ndarray]:
    """散布図用の SV / RGB サンプルを返す。"""
    return sample_sv_and_rgb(frame.h, frame.s, frame.v, frame.bgr_u8, sample_points)


def _build_analysis_result(data: AnalysisResultData) -> AnalyzerResultPayload:
    """解析結果を UI 互換の辞書形式で構築する。"""
    h_img, w_img = data.bgr_u8.shape[:2]
    return {
        "bgr_preview": data.bgr_u8,
        "hist": data.hist,
        "sv": data.sv,
        "rgb": data.rgb,
        # ヒストグラムを優先して返し、平面配列の転送を抑える。
        "h_plane": None,
        "s_plane": None,
        "v_plane": None,
        "h_hist": data.h_hist,
        "s_hist": data.s_hist,
        "v_hist": data.v_hist,
        "top_colors": data.top_colors,
        "warm_ratio": data.warm_ratio,
        "cool_ratio": data.cool_ratio,
        "other_ratio": data.other_ratio,
        "dt_ms": 0.0,  # caller fills actual timing
        "cap": (0, 0, int(w_img), int(h_img)),
        "graph_update": True,
    }


def analyze_bgr_frame(
    bgr: np.ndarray,
    sample_points: int,
    wheel_sat_threshold: int,
    color_band_sat_threshold: int | None = None,
    max_dim: int = 0,
    progress_cb: ProgressCb = None,
    cancel_cb: CancelCb = None,
) -> Optional[AnalyzerResultPayload]:
    """1フレーム分の解析結果をUI連携用フォーマットで返す。"""

    # 空入力は早期エラー。
    if bgr is None or bgr.size == 0:
        raise ValueError("empty frame")
    # 設定サイズで前処理。
    bgr_work = _normalize_analysis_input(bgr, max_dim)

    if _check_analysis_step(progress_cb, cancel_cb, _ANALYZE_STEP_CONVERT_HSV):
        return None
    frame = _prepare_analysis_frame(bgr_work)

    if _check_analysis_step(progress_cb, cancel_cb, _ANALYZE_STEP_WHEEL_HIST):
        return None
    hist, warm_ratio, cool_ratio, other_ratio, h_hist, s_hist, v_hist = (
        _compute_wheel_and_hsv_histograms(frame, int(wheel_sat_threshold))
    )

    if _check_analysis_step(progress_cb, cancel_cb, _ANALYZE_STEP_SCATTER):
        return None
    sv, rgb = _compute_scatter_samples(frame, sample_points)

    if _check_analysis_step(progress_cb, cancel_cb, _ANALYZE_STEP_FINISH_STATS):
        return None
    top_colors = _compute_optional_top_colors(
        frame.bgr_u8,
        frame.h,
        frame.s,
        color_band_sat_threshold,
    )

    if _check_analysis_step(progress_cb, cancel_cb, _ANALYZE_STEP_BUILD_RESULT):
        return None
    # 呼び出し側と互換のキーを返す（UI側 on_result がこの形を前提にする）。
    return _build_analysis_result(
        AnalysisResultData(
            bgr_u8=frame.bgr_u8,
            hist=hist,
            sv=sv,
            rgb=rgb,
            h_hist=h_hist,
            s_hist=s_hist,
            v_hist=v_hist,
            top_colors=top_colors,
            warm_ratio=float(warm_ratio),
            cool_ratio=float(cool_ratio),
            other_ratio=float(other_ratio),
        )
    )


# Refactor 前の private helper 名を互換用に残す。
_prepare_hsv8_and_bgr8 = prepare_hsv8_and_bgr8
_compute_hsv_histograms = compute_hsv_histograms
_compute_wheel_stats_from_hs = compute_wheel_stats_from_hs
