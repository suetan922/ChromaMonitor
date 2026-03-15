"""Qt向けの画像変換ヘルパー。"""

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from .image_ops import clamp_render_size

_QIMAGE_FORMAT_BGR888 = getattr(QImage, "Format_BGR888", None)


def _scaled_qpixmap_from_qimage(qimg: QImage, max_w: int, max_h: int) -> QPixmap:
    """`QImage` を安全サイズへ等比スケーリングして `QPixmap` 化する。"""
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
    bgr = np.ascontiguousarray(bgr)
    if (
        _QIMAGE_FORMAT_BGR888 is not None
        and bgr.ndim == 3
        and bgr.shape[2] == 3
        and bgr.dtype == np.uint8
    ):
        h, w = bgr.shape[:2]
        qimg = QImage(bgr.data, w, h, w * 3, _QIMAGE_FORMAT_BGR888)
        return _scaled_qpixmap_from_qimage(qimg, max_w=max_w, max_h=max_h)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb_to_qpixmap(rgb, max_w=max_w, max_h=max_h)


def gray_to_qpixmap(gray: np.ndarray, max_w: int, max_h: int) -> QPixmap:
    """NumPy のグレースケール配列を `QPixmap` に変換する。"""
    gray = np.ascontiguousarray(gray)
    h, w = gray.shape[:2]
    qimg = QImage(gray.data, w, h, w, QImage.Format_Grayscale8)
    return _scaled_qpixmap_from_qimage(qimg, max_w=max_w, max_h=max_h)
