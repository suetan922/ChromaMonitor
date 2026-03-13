"""解析処理の補助関数。"""

from typing import Callable, Optional, TypeAlias

import cv2
import numpy as np

from ..util import constants as C
from ..util.image_ops import resize_by_long_edge
from ..util.value_utils import clamp_int

_WARM_HUE_LOW_END = 45
_WARM_HUE_HIGH_START = 150
_COOL_HUE_START = 60
_COOL_HUE_END = 135
_HUE_NAME_12 = (
    "赤",
    "橙",
    "黄",
    "黄緑",
    "緑",
    "青緑",
    "水",
    "青",
    "藍",
    "紫",
    "赤紫",
    "紅",
)
_TOP_COLOR_MEDOID_CANDIDATE_LIMIT = 64
_TOP_COLOR_MEDOID_MAX_PIXELS_PER_SEGMENT = 120_000
_SAMPLE_RGB_DIRECT_GATHER_THRESHOLD = 180_000
TopColorBar: TypeAlias = tuple[str, float, tuple[int, int, int]]
ProgressCb: TypeAlias = Optional[Callable[[int, str], None]]
CancelCb: TypeAlias = Optional[Callable[[], bool]]


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
            if 0.0 <= min_v and max_v <= 255.0:
                out = out / 255.0
            else:
                out = out / max(1.0, max_v)

    return np.clip(out, 0.0, 1.0)


def _prepare_hsv8_and_bgr8(
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
    h = np.clip(np.round(hsv_f[:, :, 0] * 0.5), 0, 179).astype(np.uint8)
    s = np.clip(np.round(hsv_f[:, :, 1] * 255.0), 0, 255).astype(np.uint8)
    v = np.clip(np.round(hsv_f[:, :, 2] * 255.0), 0, 255).astype(np.uint8)
    bgr_u8 = np.clip(np.round(bgr_f * 255.0), 0, 255).astype(np.uint8)
    return bgr_u8, h, s, v


def _compute_hsv_histograms(
    h: np.ndarray,
    s: np.ndarray,
    v: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """H/S/V のヒストグラムを集計する。"""
    # Hヒストグラムは従来どおり色相未定義(S=0)を除外する。
    h_mask = cv2.compare(s, 0, cv2.CMP_GT)
    h_hist = cv2.calcHist([h], [0], h_mask, [180], [0, 180]).reshape(180).astype(np.int64)
    s_hist = cv2.calcHist([s], [0], None, [256], [0, 256]).reshape(256).astype(np.int64)
    v_hist = cv2.calcHist([v], [0], None, [256], [0, 256]).reshape(256).astype(np.int64)
    return h_hist, s_hist, v_hist


def _compute_wheel_stats(h_wheel: np.ndarray) -> tuple[np.ndarray, float, float, float]:
    """色相環ヒストグラムと暖色/寒色/その他の比率を同時に計算する。"""
    # 色相環ヒストグラムと暖寒比率を同じ raw ヒストグラムから計算して走査回数を減らす。
    # 色相の広がりを抑えるため、色相環表示には平滑化を入れない。
    if h_wheel.size == 0:
        return np.zeros(180, dtype=np.int64), 0.0, 0.0, 0.0

    hist_raw = cv2.calcHist([h_wheel], [0], None, [180], [0, 180]).reshape(180).astype(np.int64)

    total_color = float(h_wheel.size)
    # OpenCV Hue(0..179)基準:
    # 暖色 = 0..44 (0..88deg) + 150..179 (300..358deg)
    # 寒色 = 60..134 (120..268deg)
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


def _medoid_rgb_from_pixels(rgb_pixels: np.ndarray) -> tuple[int, int, int]:
    """画素集合から「実在色」の代表RGB(近似メドイド)を返す。"""
    # 実在色から代表色を選ぶため、量子化色空間で近似メドイドを求める。
    arr = np.asarray(rgb_pixels, dtype=np.uint8)
    if arr.ndim != 2 or arr.shape[0] <= 0 or arr.shape[1] < 3:
        return (0, 0, 0)
    if arr.shape[0] == 1:
        return (int(arr[0, 0]), int(arr[0, 1]), int(arr[0, 2]))

    q = np.right_shift(arr.astype(np.uint16), 3)
    packed = (q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]
    unique_codes, counts = np.unique(packed, return_counts=True)
    if unique_codes.size <= 0:
        return (int(arr[0, 0]), int(arr[0, 1]), int(arr[0, 2]))

    ur = np.right_shift(unique_codes, 10) & 31
    ug = np.right_shift(unique_codes, 5) & 31
    ub = unique_codes & 31
    all_centers = np.stack([ur, ug, ub], axis=1).astype(np.float32) * 8.0 + 4.0
    all_weights = counts.astype(np.float32)

    candidate_count = min(int(_TOP_COLOR_MEDOID_CANDIDATE_LIMIT), int(unique_codes.size))
    if candidate_count < unique_codes.size:
        candidate_idx = np.argpartition(counts, -candidate_count)[-candidate_count:]
    else:
        candidate_idx = np.arange(unique_codes.size, dtype=np.int32)
    cand_centers = all_centers[candidate_idx]

    diff = np.abs(cand_centers[:, None, :] - all_centers[None, :, :]).sum(axis=2)
    scores = diff @ all_weights
    best_local = int(np.argmin(scores))
    best_idx = int(candidate_idx[best_local])
    best_code = int(unique_codes[best_idx])
    best_center = all_centers[best_idx]

    members = arr[packed == best_code]
    if members.size <= 0:
        members = arr
    d2 = ((members.astype(np.float32) - best_center) ** 2).sum(axis=1)
    rep = members[int(np.argmin(d2))]
    return (int(rep[0]), int(rep[1]), int(rep[2]))


def _sample_segment_pixels_for_medoid(
    rgb_all: np.ndarray,
    seg: np.ndarray,
    seg_idx: int,
    max_pixels: int,
) -> np.ndarray:
    """指定セグメントの画素をメドイド用に上限数まで間引いて返す。"""
    max_pick = int(max_pixels)
    if max_pick <= 0:
        return np.empty((0, 3), dtype=np.uint8)
    seg_idx_i = int(seg_idx)

    # まず粗い間引きグリッドで候補を拾い、十分に取れたら全走査を回避する。
    total = int(seg.size)
    coarse_step = max(1, total // (max_pick * 3))
    if coarse_step > 1:
        coarse_pick = np.flatnonzero(seg[::coarse_step] == seg_idx_i)
        if coarse_pick.size >= max(64, max_pick // 4):
            pick = coarse_pick * coarse_step
            if pick.size > max_pick:
                stride = max(1, int(pick.size) // max_pick)
                pick = pick[::stride]
                if pick.size > max_pick:
                    pick = pick[:max_pick]
            return rgb_all[pick]

    pick = np.flatnonzero(seg == seg_idx_i)
    if pick.size <= 0:
        return np.empty((0, 3), dtype=np.uint8)
    if pick.size > max_pick:
        step = max(1, int(pick.size) // max_pick)
        pick = pick[::step]
        if pick.size > max_pick:
            pick = pick[:max_pick]
    return rgb_all[pick]


def _build_top_color_bars(
    *,
    counts: np.ndarray,
    seg: np.ndarray,
    rgb_source: np.ndarray,
    max_count: int,
    label_for_idx: Callable[[int], str],
) -> list[TopColorBar]:
    """集計済みセグメント情報から上位色バー配列を構築する。"""
    total = int(np.asarray(counts, dtype=np.int64).sum())
    if total <= 0:
        return []
    order = np.argsort(counts)[::-1]
    bars: list[TopColorBar] = []
    for idx in order:
        seg_idx = int(idx)
        cnt = int(counts[seg_idx])
        if cnt <= 0:
            continue
        ratio = float(cnt) / float(total)
        members = _sample_segment_pixels_for_medoid(
            rgb_source,
            seg,
            seg_idx,
            _TOP_COLOR_MEDOID_MAX_PIXELS_PER_SEGMENT,
        )
        rgb = _medoid_rgb_from_pixels(members)
        bars.append((label_for_idx(seg_idx), ratio, rgb))
        if len(bars) >= int(max_count):
            break
    return bars


def _segment_hue_to_12bin(h_u16: np.ndarray) -> np.ndarray:
    """Hue(0..179) を 12 区分インデックスへ変換する。"""
    # 30度刻み (360/12)。OpenCV Hue は 0..179 なので *2 して割る。
    return (((h_u16 * 2) // 30) % 12).astype(np.uint8, copy=False)


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
    if bgr.ndim != 3 or bgr.shape[2] < 3 or bgr.size == 0:
        return []

    bgr_u8, h, s, _v = _prepare_hsv8_and_bgr8(bgr)
    h_flat = h.reshape(-1)
    s_flat = s.reshape(-1)
    if h_flat.size == 0:
        return []

    sat_th = int(max(0, min(255, int(sat_threshold))))
    bgr_all = bgr_u8.reshape(-1, 3)
    rgb_all = bgr_all[:, ::-1]
    max_count = max(1, int(top_count))

    if sat_th <= 0:
        achro_bin = 12
        seg = np.full(h_flat.shape, achro_bin, dtype=np.uint8)
        chroma_mask = s_flat > 0
        h_chroma = h_flat[chroma_mask].astype(np.uint16, copy=False)
        seg[chroma_mask] = _segment_hue_to_12bin(h_chroma)
        counts = np.bincount(seg, minlength=13)[:13]
        return _build_top_color_bars(
            counts=counts,
            seg=seg,
            rgb_source=rgb_all,
            max_count=max_count,
            label_for_idx=lambda idx, achro=achro_bin: (
                "無彩色" if int(idx) == int(achro) else _HUE_NAME_12[int(idx) % 12]
            ),
        )

    # 色相環と同じく「しきい値未満を除外」するため、しきい値ちょうどは含める。
    chroma_mask = s_flat >= sat_th
    if not np.any(chroma_mask):
        return []

    h_chroma = h_flat[chroma_mask].astype(np.uint16, copy=False)
    seg = _segment_hue_to_12bin(h_chroma)
    counts = np.bincount(seg, minlength=12)[:12]
    rgb_chroma = rgb_all[chroma_mask]
    return _build_top_color_bars(
        counts=counts,
        seg=seg,
        rgb_source=rgb_chroma,
        max_count=max_count,
        label_for_idx=lambda idx: _HUE_NAME_12[int(idx) % 12],
    )


def _gather_hsv_by_indices(
    flat_h: np.ndarray,
    flat_s: np.ndarray,
    flat_v: np.ndarray,
    idx: np.ndarray,
) -> np.ndarray:
    """平坦化済み H/S/V からインデックス指定でサンプルを集める。"""
    k = int(idx.size)
    hsv = np.empty((k, 3), dtype=np.uint8)
    np.take(flat_h, idx, out=hsv[:, 0])
    np.take(flat_s, idx, out=hsv[:, 1])
    np.take(flat_v, idx, out=hsv[:, 2])
    return hsv


def _gather_rgb_from_bgr_indices(bgr_flat: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """平坦化済み BGR からインデックス指定で RGB サンプルを集める。"""
    k = int(idx.size)
    rgb = np.empty((k, 3), dtype=np.uint8)
    # 低サンプル時は axis=0 まとめ取得が速く、高サンプル時はチャネル直取得が有利。
    if k >= _SAMPLE_RGB_DIRECT_GATHER_THRESHOLD:
        np.take(bgr_flat[:, 2], idx, out=rgb[:, 0])
        np.take(bgr_flat[:, 1], idx, out=rgb[:, 1])
        np.take(bgr_flat[:, 0], idx, out=rgb[:, 2])
        return rgb

    bgr_sel = np.empty((k, 3), dtype=np.uint8)
    np.take(bgr_flat, idx, axis=0, out=bgr_sel)
    rgb[:, 0] = bgr_sel[:, 2]
    rgb[:, 1] = bgr_sel[:, 1]
    rgb[:, 2] = bgr_sel[:, 0]
    return rgb


def _convert_bgr_flat_to_rgb(bgr_flat: np.ndarray) -> np.ndarray:
    """平坦化済み BGR 配列を同サイズの RGB 配列へ変換する。"""
    rgb = np.empty_like(bgr_flat)
    rgb[:, 0] = bgr_flat[:, 2]
    rgb[:, 1] = bgr_flat[:, 1]
    rgb[:, 2] = bgr_flat[:, 0]
    return rgb


def _sample_sv_and_rgb(
    h: np.ndarray, s: np.ndarray, v: np.ndarray, bgr: np.ndarray, sample_points: int
) -> tuple[np.ndarray, np.ndarray]:
    """散布図表示用に HSV/RGB のサンプル点列を生成する。"""
    # 散布図負荷を抑えるため、画素数が多いときはランダムサンプリングする。
    flat_h = h.reshape(-1)
    flat_s = s.reshape(-1)
    flat_v = v.reshape(-1)
    n = flat_s.size
    points = max(1, int(sample_points))
    k = min(points, n)
    bgr_flat = bgr.reshape(-1, 3)
    if k < n:
        idx = np.random.randint(0, n, size=k, dtype=np.int32)
        hsv = _gather_hsv_by_indices(flat_h, flat_s, flat_v, idx)
        rgb = _gather_rgb_from_bgr_indices(bgr_flat, idx)
    else:
        hsv = np.empty((n, 3), dtype=np.uint8)
        hsv[:, 0] = flat_h
        hsv[:, 1] = flat_s
        hsv[:, 2] = flat_v
        rgb = _convert_bgr_flat_to_rgb(bgr_flat)
    return hsv, rgb


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


def _build_analysis_result(
    *,
    bgr_u8: np.ndarray,
    hist: np.ndarray,
    sv: np.ndarray,
    rgb: np.ndarray,
    h_hist: np.ndarray,
    s_hist: np.ndarray,
    v_hist: np.ndarray,
    top_colors: list[TopColorBar] | None,
    warm_ratio: float,
    cool_ratio: float,
    other_ratio: float,
) -> dict:
    """解析結果を UI 互換の辞書形式で構築する。"""
    h_img, w_img = bgr_u8.shape[:2]
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


def analyze_bgr_frame(
    bgr: np.ndarray,
    sample_points: int,
    wheel_sat_threshold: int,
    color_band_sat_threshold: int | None = None,
    max_dim: int = 0,
    progress_cb: ProgressCb = None,
    cancel_cb: CancelCb = None,
) -> Optional[dict]:
    """1フレーム分の解析結果をUI連携用フォーマットで返す。"""

    # 空入力は早期エラー。
    if bgr is None or bgr.size == 0:
        raise ValueError("empty frame")
    # 設定サイズで前処理。
    bgr_work = resize_by_long_edge(np.asarray(bgr), int(max_dim))

    if _emit_step_and_check_cancel(
        progress_cb,
        cancel_cb,
        percent=15,
        text="HSVへ変換中…",
    ):
        return None
    bgr_u8, h, s, v = _prepare_hsv8_and_bgr8(bgr_work)

    # 色相環側の彩度しきい値。
    sat_th = clamp_int(wheel_sat_threshold, C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX)
    wheel_mask = s >= sat_th

    if _emit_step_and_check_cancel(
        progress_cb,
        cancel_cb,
        percent=30,
        text="色相ヒストグラム集計中…",
    ):
        return None
    # h_wheel は色相環表示用。
    h_wheel = h[wheel_mask]
    hist, warm_ratio, cool_ratio, other_ratio = _compute_wheel_stats(h_wheel)
    h_hist, s_hist, v_hist = _compute_hsv_histograms(h, s, v)

    if _emit_step_and_check_cancel(
        progress_cb,
        cancel_cb,
        percent=45,
        text="散布図サンプル生成中…",
    ):
        return None
    sv, rgb = _sample_sv_and_rgb(h, s, v, bgr_u8, sample_points)

    if _emit_step_and_check_cancel(
        progress_cb,
        cancel_cb,
        percent=65,
        text="統計を仕上げ中…",
    ):
        return None
    top_colors = None
    if color_band_sat_threshold is not None:
        # 配色比率は必要時のみ計算。
        top_colors = compute_top_bars_chromatic_medoid(
            bgr_u8,
            sat_threshold=int(color_band_sat_threshold),
            top_count=int(C.TOP_COLORS_COUNT),
        )

    if _emit_step_and_check_cancel(
        progress_cb,
        cancel_cb,
        percent=85,
        text="結果を反映中…",
    ):
        return None
    # 呼び出し側と互換のキーを返す（UI側 on_result がこの形を前提にする）。
    return _build_analysis_result(
        bgr_u8=bgr_u8,
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
