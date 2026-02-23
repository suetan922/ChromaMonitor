"""ビュー描画に関する処理。"""

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from ..util import constants as C
from ..util.functions import clamp_int, resize_by_long_edge, safe_choice
from .base_image_view import BaseImageLabelView

_MAX_RENDER_EDGE = 2048
_MAX_RENDER_AREA = _MAX_RENDER_EDGE * _MAX_RENDER_EDGE


def _gray_to_qpixmap(gray: np.ndarray, max_w: int, max_h: int) -> QPixmap:
    # グレースケール配列の軽量変換経路。
    gray = np.ascontiguousarray(gray)
    h, w = gray.shape[:2]
    qimg = QImage(gray.data, w, h, w, QImage.Format_Grayscale8)
    pm = QPixmap.fromImage(qimg)
    safe_w = max(1, min(int(max_w), _MAX_RENDER_EDGE))
    safe_h = max(1, min(int(max_h), _MAX_RENDER_EDGE))
    area = safe_w * safe_h
    if area > _MAX_RENDER_AREA:
        scale = (_MAX_RENDER_AREA / float(area)) ** 0.5
        safe_w = max(1, int(safe_w * scale))
        safe_h = max(1, int(safe_h * scale))
    return pm.scaled(safe_w, safe_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class GrayscaleView(BaseImageLabelView):

    def __init__(self):
        super().__init__("グレースケールなし")

    def update_gray(self, bgr: np.ndarray):
        if not self._set_last_bgr(bgr):
            return
        # グレースケールは元解像度のまま表示し、見た目の忠実度を優先する。
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        pm = _gray_to_qpixmap(gray, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rerender_on_resize(self.update_gray)


class BinaryView(BaseImageLabelView):

    def __init__(self):
        super().__init__("2値化なし")
        self._preset = C.DEFAULT_BINARY_PRESET  # auto | more_white | more_black

    def set_preset(self, preset: str):
        self._preset = safe_choice(preset, C.BINARY_PRESETS, C.DEFAULT_BINARY_PRESET)
        if self._last_bgr is not None:
            self.update_binary(self._last_bgr)

    def update_binary(self, bgr: np.ndarray):
        if not self._set_last_bgr(bgr):
            return
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        # 固定上限で縮小して処理量を抑える（表示時に再スケールされる）。
        gray = resize_by_long_edge(gray, C.ANALYZER_MAX_DIM)

        # Otsu を基準にプリセット分だけ閾値をシフトする。
        otsu_thr, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        shift = 0
        if self._preset == C.BINARY_PRESET_MORE_WHITE:
            shift = -20
        elif self._preset == C.BINARY_PRESET_MORE_BLACK:
            shift = 20
        thr = clamp_int(round(float(otsu_thr) + shift), 0, 255)
        _thr, binary = cv2.threshold(gray, thr, 255, cv2.THRESH_BINARY)
        pm = _gray_to_qpixmap(binary, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rerender_on_resize(self.update_binary)


class TernaryView(BaseImageLabelView):

    def __init__(self):
        super().__init__("3値化なし")
        self._preset = C.DEFAULT_TERNARY_PRESET  # standard | soft | strong

    def set_preset(self, preset: str):
        self._preset = safe_choice(preset, C.TERNARY_PRESETS, C.DEFAULT_TERNARY_PRESET)
        if self._last_bgr is not None:
            self.update_ternary(self._last_bgr)

    def update_ternary(self, bgr: np.ndarray):
        if not self._set_last_bgr(bgr):
            return
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        # 3値化計算は縮小画像で実施し、リアルタイム性を維持する。
        gray = resize_by_long_edge(gray, C.ANALYZER_MAX_DIM)

        # 輝度分布の分位点で 0/127/255 の3階調へ分割する。
        flat = gray.reshape(-1).astype(np.float32)
        p1, p2 = 33.3, 66.6
        if self._preset == C.TERNARY_PRESET_SOFT:
            p1, p2 = 25.0, 75.0
        elif self._preset == C.TERNARY_PRESET_STRONG:
            p1, p2 = 40.0, 60.0
        t1, t2 = np.percentile(flat, [p1, p2])
        if t2 <= t1:
            # 例外的に分位点が崩れた場合は平均値基準へフォールバック。
            mean = float(flat.mean()) if flat.size else 127.0
            t1 = max(0.0, mean - 32.0)
            t2 = min(255.0, mean + 32.0)

        ternary = np.zeros_like(gray, dtype=np.uint8)
        ternary[gray >= t1] = 127
        ternary[gray >= t2] = 255

        pm = _gray_to_qpixmap(ternary, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rerender_on_resize(self.update_ternary)
