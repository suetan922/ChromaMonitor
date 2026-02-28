"""画像変換・描画向けの共通関数。"""

from collections import OrderedDict
import math
import weakref
from typing import Tuple

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

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
        id(src),
        int(max_dim),
        int(interpolation),
        tuple(int(v) for v in src.shape),
        tuple(int(v) for v in src.strides),
        str(src.dtype),
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
        id(src),
        int(code),
        tuple(int(v) for v in src.shape),
        tuple(int(v) for v in src.strides),
        str(src.dtype),
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


def clamp_render_size(width: int, height: int) -> Tuple[int, int]:
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


def _scaled_qpixmap_from_qimage(qimg: QImage, max_w: int, max_h: int) -> QPixmap:
    pm = QPixmap.fromImage(qimg)
    max_w, max_h = clamp_render_size(max_w, max_h)
    return pm.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def rgb_to_qpixmap(rgb: np.ndarray, max_w: int, max_h: int) -> QPixmap:
    """NumPy の RGB 配列を `QPixmap` に変換する。"""
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
    return _scaled_qpixmap_from_qimage(qimg, max_w=max_w, max_h=max_h)


def bgr_to_qpixmap(bgr: np.ndarray, max_w: int = 560, max_h: int = 420) -> QPixmap:
    """NumPy の BGR 配列を `QPixmap` に変換する。"""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb_to_qpixmap(rgb, max_w=max_w, max_h=max_h)


def gray_to_qpixmap(gray: np.ndarray, max_w: int, max_h: int) -> QPixmap:
    """NumPy のグレースケール配列を `QPixmap` に変換する。"""
    gray = np.ascontiguousarray(gray)
    h, w = gray.shape[:2]
    qimg = QImage(gray.data, w, h, w, QImage.Format_Grayscale8)
    return _scaled_qpixmap_from_qimage(qimg, max_w=max_w, max_h=max_h)
