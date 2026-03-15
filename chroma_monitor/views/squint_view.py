"""スクイント表示ビュー。"""

import cv2
import numpy as np

from ..util import constants as C
from ..util.qt_image import bgr_to_qpixmap
from ..util.value_utils import clamp_float, clamp_int, safe_choice
from .base_image_view import BaseImageLabelView


class SquintView(BaseImageLabelView):
    """縮小/ぼかしで形状把握を補助するスクイント表示ビュー。"""

    def __init__(self):
        """既定モードとパラメータでビューを初期化する。"""
        super().__init__("スクイントなし")
        self._mode = C.DEFAULT_SQUINT_MODE
        self._scale_percent = C.DEFAULT_SQUINT_SCALE_PERCENT
        self._blur_sigma = C.DEFAULT_SQUINT_BLUR_SIGMA
        self.set_resize_renderer(self.update_squint)

    def set_mode(self, mode: str):
        """スクイント処理モードを更新する。"""
        next_mode = safe_choice(mode, C.SQUINT_MODES, C.DEFAULT_SQUINT_MODE)
        self._set_state_value("_mode", next_mode, self.update_squint)

    def set_scale_percent(self, value: int):
        """縮小率(%)を更新する。"""
        next_percent = clamp_int(value, C.SQUINT_SCALE_PERCENT_MIN, C.SQUINT_SCALE_PERCENT_MAX)
        self._set_state_value("_scale_percent", next_percent, self.update_squint)

    def set_blur_sigma(self, value: float):
        """ぼかし強度(sigma)を更新する。"""
        next_sigma = clamp_float(value, C.SQUINT_BLUR_SIGMA_MIN, C.SQUINT_BLUR_SIGMA_MAX)
        self._set_state_value("_blur_sigma", next_sigma, self.update_squint)

    def _apply_scale_up(self, bgr: np.ndarray) -> np.ndarray:
        """縮小後に再拡大してディテールを簡略化した画像を返す。"""
        # 一度縮小してから元サイズへ戻すことで、大きな形状だけを見やすくする。
        # _scale_percent は setter 側で常に範囲内へ正規化済み。
        ratio = float(self._scale_percent) / 100.0
        if ratio >= 0.999:
            return bgr.copy()
        h, w = bgr.shape[:2]
        sw = max(1, int(round(w * ratio)))
        sh = max(1, int(round(h * ratio)))
        small = cv2.resize(bgr, (sw, sh), interpolation=cv2.INTER_AREA)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    def _apply_blur(self, bgr: np.ndarray) -> np.ndarray:
        """ガウシアンぼかしを適用した画像を返す。"""
        # sigma が極小のときは元画像をそのまま返して無駄処理を避ける。
        # _blur_sigma は setter 側で常に範囲内へ正規化済み。
        sigma = float(self._blur_sigma)
        if sigma <= 0.001:
            return bgr
        return cv2.GaussianBlur(bgr, (0, 0), sigmaX=sigma, sigmaY=sigma)

    def update_squint(self, bgr: np.ndarray):
        """現在モードに応じたスクイント表示へ更新する。"""
        if not self._set_last_bgr(bgr):
            return

        src = bgr
        # _mode は setter 側で正規化済み。
        mode = self._mode
        if mode == C.SQUINT_MODE_BLUR:
            view = self._apply_blur(src)
        elif mode == C.SQUINT_MODE_SCALE:
            view = self._apply_scale_up(src)
        else:
            view = self._apply_blur(self._apply_scale_up(src))

        pm = bgr_to_qpixmap(view, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)
