"""スクイント表示ビュー。"""

import numpy as np

from ..util import constants as C
from ..util.qt_image import bgr_to_qpixmap
from ..util.value_utils import clamp_float, clamp_int, safe_choice
from .base_image_view import BaseImageLabelView
from .squint_math import render_squint_frame


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

    def update_squint(self, bgr: np.ndarray):
        """現在モードに応じたスクイント表示へ更新する。"""
        if not self._set_last_bgr(bgr):
            return

        view = render_squint_frame(
            bgr,
            mode=self._mode,
            scale_percent=self._scale_percent,
            blur_sigma=self._blur_sigma,
            target_width=self.width(),
            target_height=self.height(),
        )
        pm = bgr_to_qpixmap(view, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)
