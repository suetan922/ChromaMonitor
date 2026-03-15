"""反転表示ビュー。"""

import cv2
import numpy as np

from ..util import constants as C
from ..util.qt_image import bgr_to_qpixmap
from ..util.value_utils import safe_choice
from .base_image_view import BaseImageLabelView


class MirrorView(BaseImageLabelView):
    """入力フレームを指定方向に反転して表示するビュー。"""

    def __init__(self):
        """既定モードで反転表示ビューを初期化する。"""
        super().__init__("反転表示なし")
        self._mode = C.DEFAULT_MIRROR_MODE
        self.set_resize_renderer(self.update_mirror)

    def set_mode(self, mode: str) -> None:
        """反転方向モードを更新する。"""
        next_mode = safe_choice(mode, C.MIRROR_MODES, C.DEFAULT_MIRROR_MODE)
        self._set_state_value("_mode", next_mode, self.update_mirror)

    def _flip_code(self) -> int:
        """OpenCV の flip code を現在モードから返す。"""
        if self._mode == C.MIRROR_MODE_VERTICAL:
            return 0
        if self._mode == C.MIRROR_MODE_BOTH:
            return -1
        return 1

    def update_mirror(self, bgr: np.ndarray) -> None:
        """入力フレームを反転して表示する。"""
        if not self._set_last_bgr(bgr):
            return
        flipped = cv2.flip(bgr, self._flip_code())
        pm = bgr_to_qpixmap(flipped, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)
