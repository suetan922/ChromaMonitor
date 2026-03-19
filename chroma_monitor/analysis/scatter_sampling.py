"""散布図サンプル抽出で共有する純粋ロジック。"""

import threading

import numpy as np

_SAMPLE_RGB_DIRECT_GATHER_THRESHOLD = 180_000
_RNG_LOCAL = threading.local()


def _thread_local_rng() -> np.random.Generator:
    """現在スレッド専用の乱数生成器を返す。"""
    rng = getattr(_RNG_LOCAL, "rng", None)
    if rng is None:
        rng = np.random.default_rng()
        _RNG_LOCAL.rng = rng
    return rng


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


def sample_sv_and_rgb(
    h: np.ndarray,
    s: np.ndarray,
    v: np.ndarray,
    bgr: np.ndarray,
    sample_points: int,
) -> tuple[np.ndarray, np.ndarray]:
    """散布図表示用に HSV/RGB のサンプル点列を生成する。"""
    flat_h = h.reshape(-1)
    flat_s = s.reshape(-1)
    flat_v = v.reshape(-1)
    n = flat_s.size
    points = max(1, int(sample_points))
    k = min(points, n)
    bgr_flat = bgr.reshape(-1, 3)
    if k < n:
        idx = _thread_local_rng().integers(0, n, size=k, dtype=np.int32)
        hsv = _gather_hsv_by_indices(flat_h, flat_s, flat_v, idx)
        rgb = _gather_rgb_from_bgr_indices(bgr_flat, idx)
        return hsv, rgb

    hsv = np.empty((n, 3), dtype=np.uint8)
    hsv[:, 0] = flat_h
    hsv[:, 1] = flat_s
    hsv[:, 2] = flat_v
    return hsv, _convert_bgr_flat_to_rgb(bgr_flat)
