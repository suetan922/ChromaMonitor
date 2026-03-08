"""エッジ表示ビュー。"""

import cv2

from ..util import constants as C
from ..util.image_ops import (
    cvt_color_cached,
    gray_to_qpixmap,
    resize_by_long_edge,
)
from ..util.value_utils import clamp_int, normalized_ratio
from .base_image_view import BaseImageLabelView


class EdgeView(BaseImageLabelView):
    """エッジ強調表示ビュー。"""

    def __init__(self):
        """初期感度を設定してビューを初期化する。"""
        super().__init__("エッジ未検出")
        self._sensitivity = C.DEFAULT_EDGE_SENSITIVITY  # 1..100
        self.set_resize_renderer(self.update_edge)

    def set_sensitivity(self, value: int):
        """エッジ検出感度を更新する。"""
        self._sensitivity = clamp_int(value, C.EDGE_SENSITIVITY_MIN, C.EDGE_SENSITIVITY_MAX)
        if self._last_bgr is not None:
            self.update_edge(self._last_bgr)

    def update_edge(self, bgr):
        """入力フレームからエッジ画像を生成して表示する。"""
        if not self._set_last_bgr(bgr):
            return
        gray = cvt_color_cached(bgr, cv2.COLOR_BGR2GRAY)
        # Canny前に縮小して、毎フレーム更新でも重くなりにくくする。
        gray = resize_by_long_edge(gray, C.ANALYZER_MAX_DIM)
        # 感度が高いほど閾値を下げて、細かいエッジも拾う
        t = normalized_ratio(self._sensitivity, C.EDGE_SENSITIVITY_MIN, C.EDGE_SENSITIVITY_MAX)
        low = int(round(120 - 100 * t))
        high = int(round(240 - 160 * t))
        if high <= low:
            high = low + 1
        edges = cv2.Canny(gray, low, high)
        pm = gray_to_qpixmap(edges, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)
