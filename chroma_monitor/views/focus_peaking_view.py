"""フォーカスピーキング表示ビュー。"""

import cv2
import numpy as np

from ..util import constants as C
from ..util.image_ops import (
    bgr_to_qpixmap,
    cvt_color_cached,
    resize_by_long_edge,
)
from ..util.value_utils import (
    clamp_float,
    clamp_int,
    normalized_ratio,
    safe_choice,
)
from .base_image_view import BaseImageLabelView

_FOCUS_PEAK_COLOR_BGR = {
    "cyan": (255, 235, 0),
    "green": (0, 245, 120),
    "yellow": (0, 225, 255),
    "red": (60, 60, 255),
}


class FocusPeakingView(BaseImageLabelView):
    """高周波成分を強調表示するフォーカスピーキングビュー。"""

    def __init__(self):
        """既定感度・色・線幅でビューを初期化する。"""
        super().__init__("フォーカスピーキングなし")
        self._sensitivity = C.DEFAULT_FOCUS_PEAK_SENSITIVITY
        self._color = C.DEFAULT_FOCUS_PEAK_COLOR
        self._thickness = C.DEFAULT_FOCUS_PEAK_THICKNESS
        self.set_resize_renderer(self.update_focus)

    def set_sensitivity(self, value: int):
        """ピーキング感度を更新する。"""
        self._sensitivity = clamp_int(
            value, C.FOCUS_PEAK_SENSITIVITY_MIN, C.FOCUS_PEAK_SENSITIVITY_MAX
        )
        if self._last_bgr is not None:
            self.update_focus(self._last_bgr)

    def set_color(self, color: str):
        """ピーキング色を更新する。"""
        self._color = safe_choice(color, C.FOCUS_PEAK_COLORS, C.DEFAULT_FOCUS_PEAK_COLOR)
        if self._last_bgr is not None:
            self.update_focus(self._last_bgr)

    def set_thickness(self, value: float):
        """ピーキング線幅を更新する。"""
        self._thickness = clamp_float(value, C.FOCUS_PEAK_THICKNESS_MIN, C.FOCUS_PEAK_THICKNESS_MAX)
        if self._last_bgr is not None:
            self.update_focus(self._last_bgr)

    def _focus_mask(self, gray: np.ndarray) -> np.ndarray:
        """勾配強度に基づくピーキングマスクを生成する。"""
        # ノイズに引っ張られにくいよう軽くぼかしてから勾配を取る。
        blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
        gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        if not np.isfinite(mag).any():
            return np.zeros_like(gray, dtype=np.uint8)

        # 感度に応じて採用パーセンタイルを下げ、反応点を増やす。
        t = normalized_ratio(
            self._sensitivity,
            C.FOCUS_PEAK_SENSITIVITY_MIN,
            C.FOCUS_PEAK_SENSITIVITY_MAX,
        )
        percentile = 98.0 - 36.0 * t
        thr = float(np.percentile(mag, percentile))
        thr = max(thr, float(mag.mean()) * 0.45)
        mask = (mag >= thr).astype(np.uint8) * 255

        if self._thickness > 1.0:
            # 線幅指定が太い場合はマスクを膨張して見やすくする。
            k = max(1, int(round(self._thickness * 2.0 - 1.0)))
            if k % 2 == 0:
                k += 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
            mask = cv2.dilate(mask, kernel, iterations=1)
        return mask

    def update_focus(self, bgr: np.ndarray):
        """入力フレームをフォーカスピーキング表示へ更新する。"""
        if not self._set_last_bgr(bgr):
            return

        gray = cvt_color_cached(bgr, cv2.COLOR_BGR2GRAY)
        # 表示サイズに対して過剰に大きい入力は先に縮小して処理。
        gray = resize_by_long_edge(gray, C.ANALYZER_MAX_DIM)
        mask = self._focus_mask(gray)

        base = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR).astype(np.float32) * 0.72
        color = np.array(
            _FOCUS_PEAK_COLOR_BGR.get(self._color, _FOCUS_PEAK_COLOR_BGR[C.DEFAULT_FOCUS_PEAK_COLOR]),
            dtype=np.float32,
        ).reshape(1, 1, 3)
        sigma = max(0.5, 0.35 + float(self._thickness) * 0.45)
        # マスクをソフト化して、ピーク線のエッジを馴染ませる。
        soft = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (0, 0), sigma)[:, :, None]
        soft = np.clip(soft * max(0.35, float(self._thickness)), 0.0, 1.0)
        view = np.clip(base * (1.0 - soft) + color * soft, 0, 255).astype(np.uint8)

        pm = bgr_to_qpixmap(view, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)
