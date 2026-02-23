from typing import Callable, Optional

import cv2
import numpy as np

from ..util import constants as C
from ..util.functions import clamp_int, resize_by_long_edge


def _normalize_bgr_to_float01(bgr: np.ndarray) -> np.ndarray:
    """Normalize BGR image to float32 [0, 1]."""
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
            if 0.0 <= min_v and max_v <= 255.0:
                out = out / 255.0
            else:
                out = out / max(1.0, max_v)

    return np.clip(out, 0.0, 1.0)


def _prepare_hsv8_and_bgr8(
    bgr: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert any supported BGR depth to HSV 8-bit compatible planes and BGR8."""
    arr = np.asarray(bgr)
    if arr.dtype == np.uint8:
        hsv = cv2.cvtColor(arr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        return arr, h, s, v

    bgr_f = _normalize_bgr_to_float01(arr)
    hsv_f = cv2.cvtColor(bgr_f, cv2.COLOR_BGR2HSV)
    h = np.clip(np.round(hsv_f[:, :, 0] * 0.5), 0, 179).astype(np.uint8)
    s = np.clip(np.round(hsv_f[:, :, 1] * 255.0), 0, 255).astype(np.uint8)
    v = np.clip(np.round(hsv_f[:, :, 2] * 255.0), 0, 255).astype(np.uint8)
    bgr_u8 = np.clip(np.round(bgr_f * 255.0), 0, 255).astype(np.uint8)
    return bgr_u8, h, s, v


def _compute_wheel_histogram(h_wheel: np.ndarray) -> np.ndarray:
    # 色相環は 0..179 の180ビン固定で扱う。
    if h_wheel.size == 0:
        return np.zeros(180, dtype=np.int64)

    # 周期データ（色相）の端をまたぐ不連続を抑えるため、両端を複製して平滑化する。
    hist_raw = np.bincount(h_wheel.reshape(-1), minlength=180)
    kernel = np.array([1, 2, 3, 2, 1], dtype=np.float32)
    kernel = kernel / kernel.sum()
    hist_pad = np.concatenate([hist_raw[-2:], hist_raw, hist_raw[:2]]).astype(np.float32)
    hist_smooth = np.convolve(hist_pad, kernel, mode="valid")
    return hist_smooth.astype(np.int64)


def _compute_warm_cool_ratios(h_wheel: np.ndarray) -> tuple[float, float, float]:
    # 集計対象がない場合はゼロ比率で返す。
    if h_wheel.size == 0:
        return 0.0, 0.0, 0.0

    # Hue 0..179 を暖色/寒色/その他に大まか分類する。
    warm = np.logical_or(h_wheel < 30, h_wheel >= 150)
    cool = np.logical_and(h_wheel >= 75, h_wheel < 135)
    warm_count = float(warm.sum())
    cool_count = float(cool.sum())
    total_color = float(h_wheel.size)
    other_count = max(0.0, total_color - warm_count - cool_count)
    return warm_count / total_color, cool_count / total_color, other_count / total_color


def _compute_top_colors(
    bgr: np.ndarray, h_wheel: np.ndarray, wheel_mask: np.ndarray
) -> list[tuple[float, tuple[int, int, int]]]:
    # 戻り値は [(ratio, (r,g,b)), ...] 形式。
    top_colors: list[tuple[float, tuple[int, int, int]]] = []
    if not wheel_mask.any():
        return top_colors

    # Full-frame cvtColorを避け、必要画素のみRGB順で参照して負荷を下げる
    rgb_masked = bgr[wheel_mask][:, ::-1]
    seg_size = 10  # 2度/ビン *10 = 20度
    seg_idx = (h_wheel // seg_size).astype(np.int32)
    seg_counts = np.bincount(seg_idx, minlength=18)[:18]
    # セグメントごとのRGB総和を一括集計して、ループ内のマスク生成を避ける。
    sum_r = np.bincount(seg_idx, weights=rgb_masked[:, 0], minlength=18)[:18]
    sum_g = np.bincount(seg_idx, weights=rgb_masked[:, 1], minlength=18)[:18]
    sum_b = np.bincount(seg_idx, weights=rgb_masked[:, 2], minlength=18)[:18]
    order = np.argsort(seg_counts)[::-1]
    # 上位 C.TOP_COLORS_COUNT セグメントだけを表示用に抽出する。
    top5_idx = [i for i in order if seg_counts[i] > 0][: C.TOP_COLORS_COUNT]
    top_sum = float(seg_counts[top5_idx].sum()) if top5_idx else 0.0
    for seg in top5_idx:
        cnt = int(seg_counts[seg])
        if cnt <= 0:
            continue
        ratio = cnt / top_sum if top_sum > 0 else 0.0  # 上位5で正規化し合計100%に
        rgb_val = (
            int(sum_r[seg] / cnt),
            int(sum_g[seg] / cnt),
            int(sum_b[seg] / cnt),
        )
        top_colors.append((ratio, rgb_val))
    return top_colors


def _sample_sv_and_rgb(
    h: np.ndarray, s: np.ndarray, v: np.ndarray, bgr: np.ndarray, sample_points: int
) -> tuple[np.ndarray, np.ndarray]:
    # 散布図負荷を抑えるため、画素数が多いときはランダムサンプリングする。
    flat_h = h.reshape(-1)
    flat_s = s.reshape(-1)
    flat_v = v.reshape(-1)
    n = flat_s.size
    points = max(1, int(sample_points))
    k = min(points, n)
    if k < n:
        idx = np.random.randint(0, n, size=k, dtype=np.int32)
    else:
        idx = np.arange(n, dtype=np.int32)
    hsv = np.column_stack([flat_h[idx], flat_s[idx], flat_v[idx]])
    bgr_flat = bgr.reshape(-1, 3)
    rgb = np.ascontiguousarray(bgr_flat[idx][:, ::-1])
    return hsv, rgb


def analyze_bgr_frame(
    bgr: np.ndarray,
    sample_points: int,
    wheel_sat_threshold: int,
    max_dim: int = 0,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
) -> Optional[dict]:
    """1フレーム分を解析し、ライブ解析と同じペイロード形式で返す。

    入力は uint8 だけでなく uint16 / float も受け付ける。
    解析は互換のため HSV 8bit 相当へ正規化して処理する。
    """

    def _emit_progress(percent: int, text: str):
        # 進捗通知コールバックは任意指定なので None を許容する。
        if progress_cb is not None:
            progress_cb(int(percent), text)

    def _is_canceled() -> bool:
        # キャンセル判定は例外で処理を止めない方針。
        if cancel_cb is None:
            return False
        try:
            return bool(cancel_cb())
        except Exception:
            return False

    if bgr is None or bgr.size == 0:
        raise ValueError("empty frame")
    bgr_work = resize_by_long_edge(np.asarray(bgr), int(max_dim))

    _emit_progress(15, "HSVへ変換中…")
    if _is_canceled():
        return None
    bgr_u8, h, s, v = _prepare_hsv8_and_bgr8(bgr_work)

    # H/S/Vヒストグラム側は色相未定義(S=0)のみ除外
    hue_valid_mask = s > 0
    # 色相環側は設定可能な彩度しきい値で集計
    sat_th = clamp_int(wheel_sat_threshold, C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX)
    wheel_mask = s >= sat_th

    _emit_progress(30, "色相ヒストグラム集計中…")
    if _is_canceled():
        return None
    # h_masked は H ヒストグラム表示用、h_wheel は色相環表示用。
    h_masked = h[hue_valid_mask]
    h_wheel = h[wheel_mask]
    hist = _compute_wheel_histogram(h_wheel)
    warm_ratio, cool_ratio, other_ratio = _compute_warm_cool_ratios(h_wheel)
    h_hist = np.bincount(h_masked.reshape(-1), minlength=180)[:180].astype(np.int64)
    s_hist = np.bincount(s.reshape(-1), minlength=256)[:256].astype(np.int64)
    v_hist = np.bincount(v.reshape(-1), minlength=256)[:256].astype(np.int64)

    _emit_progress(45, "散布図サンプル生成中…")
    if _is_canceled():
        return None
    sv, rgb = _sample_sv_and_rgb(h, s, v, bgr_u8, sample_points)

    _emit_progress(65, "トップ色を計算中…")
    if _is_canceled():
        return None
    top_colors = _compute_top_colors(bgr_u8, h_wheel, wheel_mask)

    h_img, w_img = bgr_u8.shape[:2]
    _emit_progress(85, "結果を反映中…")
    if _is_canceled():
        return None
    # 呼び出し側と互換のキーを返す（UI側 on_result がこの形を前提にする）。
    return {
        "bgr_preview": bgr_u8,
        "hist": hist,
        "sv": sv,
        "rgb": rgb,
        # ヒストグラムを優先して返し、平面配列の転送を抑える。
        "h_plane": None,
        "s_plane": None,
        "v_plane": None,
        "h_hist": h_hist,
        "s_hist": s_hist,
        "v_hist": v_hist,
        "top_colors": top_colors,
        "warm_ratio": warm_ratio,
        "cool_ratio": cool_ratio,
        "other_ratio": other_ratio,
        "dt_ms": 0.0,  # caller fills actual timing
        "cap": (0, 0, int(w_img), int(h_img)),
        "graph_update": True,
    }
