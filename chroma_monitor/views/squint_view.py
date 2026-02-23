"""ビュー描画に関する処理。"""

import cv2
import numpy as np

from ..util import constants as C
from ..util.functions import (
    bgr_to_qpixmap,
    clamp_float,
    clamp_int,
    resize_by_long_edge,
    safe_choice,
)
from .base_image_view import BaseImageLabelView


class SquintView(BaseImageLabelView):

    def __init__(self):
        super().__init__("スクイントなし")
        self._mode = C.DEFAULT_SQUINT_MODE
        self._scale_percent = C.DEFAULT_SQUINT_SCALE_PERCENT
        self._blur_sigma = C.DEFAULT_SQUINT_BLUR_SIGMA

    def set_mode(self, mode: str):
        self._mode = safe_choice(mode, C.SQUINT_MODES, C.DEFAULT_SQUINT_MODE)
        if self._last_bgr is not None:
            self.update_squint(self._last_bgr)

    def set_scale_percent(self, value: int):
        self._scale_percent = clamp_int(
            value, C.SQUINT_SCALE_PERCENT_MIN, C.SQUINT_SCALE_PERCENT_MAX
        )
        if self._last_bgr is not None:
            self.update_squint(self._last_bgr)

    def set_blur_sigma(self, value: float):
        self._blur_sigma = clamp_float(value, C.SQUINT_BLUR_SIGMA_MIN, C.SQUINT_BLUR_SIGMA_MAX)
        if self._last_bgr is not None:
            self.update_squint(self._last_bgr)

    def _apply_scale_up(self, bgr: np.ndarray) -> np.ndarray:
        # 一度縮小してから元サイズへ戻すことで、大きな形状だけを見やすくする。
        ratio = (
            clamp_int(self._scale_percent, C.SQUINT_SCALE_PERCENT_MIN, C.SQUINT_SCALE_PERCENT_MAX)
            / 100.0
        )
        if ratio >= 0.999:
            return bgr.copy()
        h, w = bgr.shape[:2]
        sw = max(1, int(round(w * ratio)))
        sh = max(1, int(round(h * ratio)))
        small = cv2.resize(bgr, (sw, sh), interpolation=cv2.INTER_AREA)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    def _apply_blur(self, bgr: np.ndarray) -> np.ndarray:
        # sigma が極小のときは元画像をそのまま返して無駄処理を避ける。
        sigma = clamp_float(self._blur_sigma, C.SQUINT_BLUR_SIGMA_MIN, C.SQUINT_BLUR_SIGMA_MAX)
        if sigma <= 0.001:
            return bgr
        return cv2.GaussianBlur(bgr, (0, 0), sigmaX=sigma, sigmaY=sigma)

    def update_squint(self, bgr: np.ndarray):
        if not self._set_last_bgr(bgr):
            return

        # 入力を固定上限へ縮小してリアルタイム性を確保する。
        src = resize_by_long_edge(bgr, C.ANALYZER_MAX_DIM)
        mode = safe_choice(self._mode, C.SQUINT_MODES, C.DEFAULT_SQUINT_MODE)
        if mode == C.SQUINT_MODE_BLUR:
            view = self._apply_blur(src)
        elif mode == C.SQUINT_MODE_SCALE:
            view = self._apply_scale_up(src)
        else:
            view = self._apply_blur(self._apply_scale_up(src))

        pm = bgr_to_qpixmap(view, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rerender_on_resize(self.update_squint)
