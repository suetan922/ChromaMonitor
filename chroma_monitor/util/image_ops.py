"""画像処理系の共通関数。"""

import math
import weakref
from collections import OrderedDict

import cv2
import numpy as np

_MAX_RENDER_EDGE = 2048
_MAX_RENDER_AREA = _MAX_RENDER_EDGE * _MAX_RENDER_EDGE
_RESIZE_CACHE_MAX_ENTRIES = 12
_resize_cache: "OrderedDict[tuple, tuple[weakref.ReferenceType[np.ndarray], np.ndarray]]" = (
    OrderedDict()
)
_CVT_COLOR_CACHE_MAX_ENTRIES = 16
_cvt_color_cache: "OrderedDict[tuple, tuple[weakref.ReferenceType[np.ndarray], np.ndarray]]" = (
    OrderedDict()
)


def _array_identity_key(src: np.ndarray) -> tuple:
    """同一配列判定に使う軽量キーを返す。"""
    return (
        id(src),
        src.shape,
        src.strides,
        src.dtype.str,
    )


def resize_by_long_edge(
    img: np.ndarray, max_dim: int, interpolation: int = cv2.INTER_AREA
) -> np.ndarray:
    """画像を長辺基準で縮小する。"""
    if img is None:
        return img
    src = np.asarray(img)
    h, w = src.shape[:2]
    max_dim = int(max_dim)
    if max_dim <= 0 or max(h, w) <= max_dim:
        return src
    scale = max_dim / float(max(h, w))
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    if new_w == w and new_h == h:
        return src

    key = (
        _array_identity_key(src),
        int(max_dim),
        int(interpolation),
    )
    cached = _resize_cache.get(key)
    if cached is not None:
        src_ref, out = cached
        if src_ref() is src:
            _resize_cache.move_to_end(key, last=True)
            return out
        _resize_cache.pop(key, None)

    out = cv2.resize(src, (new_w, new_h), interpolation=interpolation)
    try:
        src_ref = weakref.ref(src)
    except TypeError:
        return out

    _resize_cache[key] = (src_ref, out)
    _resize_cache.move_to_end(key, last=True)
    if len(_resize_cache) > _RESIZE_CACHE_MAX_ENTRIES:
        _resize_cache.popitem(last=False)
    return out


def cvt_color_cached(img: np.ndarray, code: int) -> np.ndarray:
    """`cv2.cvtColor` を同一フレーム内でキャッシュして再利用する。"""
    if img is None:
        return img
    src = np.asarray(img)
    key = (
        _array_identity_key(src),
        int(code),
    )
    cached = _cvt_color_cache.get(key)
    if cached is not None:
        src_ref, out = cached
        if src_ref() is src:
            _cvt_color_cache.move_to_end(key, last=True)
            return out
        _cvt_color_cache.pop(key, None)

    out = cv2.cvtColor(src, int(code))
    try:
        src_ref = weakref.ref(src)
    except TypeError:
        return out

    _cvt_color_cache[key] = (src_ref, out)
    _cvt_color_cache.move_to_end(key, last=True)
    if len(_cvt_color_cache) > _CVT_COLOR_CACHE_MAX_ENTRIES:
        _cvt_color_cache.popitem(last=False)
    return out


def clear_cvt_color_cache() -> None:
    """`cvt_color_cached` の同一フレーム内キャッシュを破棄する。"""
    _cvt_color_cache.clear()


def clear_resize_cache() -> None:
    """`resize_by_long_edge` の同一フレーム内キャッシュを破棄する。"""
    _resize_cache.clear()


def clamp_render_size(width: int, height: int) -> tuple[int, int]:
    """描画用サイズを安全上限に収める。"""
    w = max(1, int(width))
    h = max(1, int(height))
    w = min(w, _MAX_RENDER_EDGE)
    h = min(h, _MAX_RENDER_EDGE)
    area = w * h
    if area > _MAX_RENDER_AREA:
        scale = math.sqrt(_MAX_RENDER_AREA / float(area))
        w = max(1, int(w * scale))
        h = max(1, int(h * scale))
    return w, h
