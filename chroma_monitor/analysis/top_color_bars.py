"""配色比率バー計算で共有する純粋ロジック。"""

from collections.abc import Callable

import numpy as np

from ..util.color_utils import HUE_NAME_12

TopColorBar = tuple[str, float, tuple[int, int, int]]
_TOP_COLOR_MEDOID_CANDIDATE_LIMIT = 64
_TOP_COLOR_MEDOID_MAX_PIXELS_PER_SEGMENT = 120_000


def _medoid_rgb_from_pixels(rgb_pixels: np.ndarray) -> tuple[int, int, int]:
    """画素集合から「実在色」の代表RGB(近似メドイド)を返す。"""
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
    all_centers = np.stack([ur, ug, ub], axis=1).astype(np.int16) * 8 + 4
    all_weights = counts.astype(np.int32)

    candidate_count = min(int(_TOP_COLOR_MEDOID_CANDIDATE_LIMIT), int(unique_codes.size))
    if candidate_count < unique_codes.size:
        candidate_idx = np.argpartition(counts, -candidate_count)[-candidate_count:]
    else:
        candidate_idx = np.arange(unique_codes.size, dtype=np.int32)
    cand_centers = all_centers[candidate_idx]

    diff = np.abs(cand_centers[:, None, :] - all_centers[None, :, :]).sum(axis=2, dtype=np.int32)
    scores = diff @ all_weights
    best_local = int(np.argmin(scores))
    best_idx = int(candidate_idx[best_local])
    best_code = int(unique_codes[best_idx])
    best_center = all_centers[best_idx].astype(np.float32)

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
    return (((h_u16 * 2) // 30) % 12).astype(np.uint8, copy=False)


def compute_top_bars_from_prepared(
    *,
    bgr_u8: np.ndarray,
    h: np.ndarray,
    s: np.ndarray,
    sat_threshold: int,
    top_count: int,
) -> list[TopColorBar]:
    """前計算済み BGR/H/S から配色比率上位色を返す。"""
    if bgr_u8.ndim != 3 or bgr_u8.shape[2] < 3 or bgr_u8.size == 0:
        return []
    h_flat = h.reshape(-1)
    s_flat = s.reshape(-1)
    if h_flat.size == 0 or h_flat.size != s_flat.size:
        return []

    bgr_all = bgr_u8[:, :, :3].reshape(-1, 3)
    if bgr_all.shape[0] != h_flat.size:
        return []
    rgb_all = bgr_all[:, ::-1]
    sat_th = int(max(0, min(255, int(sat_threshold))))
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
                "無彩色"
                if int(idx) == int(achro)
                else HUE_NAME_12[int(idx) % len(HUE_NAME_12)]
            ),
        )

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
        label_for_idx=lambda idx: HUE_NAME_12[int(idx) % len(HUE_NAME_12)],
    )
