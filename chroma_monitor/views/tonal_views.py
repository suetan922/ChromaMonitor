"""グレースケール/2値化/3値化ビュー。"""

import cv2
import numpy as np

from ..util import constants as C
from ..util.image_ops import cvt_color_cached
from ..util.qt_image import gray_to_qpixmap
from ..util.value_utils import clamp_int, safe_choice
from .base_image_view import BaseImageLabelView


class GrayscaleView(BaseImageLabelView):
    """グレースケール表示ビュー。"""

    def __init__(self):
        """ビューを初期化し、リサイズ時レンダラを設定する。"""
        super().__init__("グレースケールなし")
        self.set_resize_renderer(self.update_gray)

    def update_gray(self, bgr: np.ndarray):
        """入力フレームをグレースケール化して表示する。"""
        if not self._set_last_bgr(bgr):
            return
        # グレースケールは元解像度のまま表示し、見た目の忠実度を優先する。
        gray = cvt_color_cached(bgr, cv2.COLOR_BGR2GRAY)
        pm = gray_to_qpixmap(gray, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)


class BinaryView(BaseImageLabelView):
    """2値化表示ビュー。"""

    def __init__(self):
        """既定プリセットで2値化ビューを初期化する。"""
        super().__init__("2値化なし")
        self._preset = C.DEFAULT_BINARY_PRESET  # auto | more_white | more_black
        self.set_resize_renderer(self.update_binary)

    def set_preset(self, preset: str):
        """2値化プリセットを更新する。"""
        next_preset = safe_choice(preset, C.BINARY_PRESETS, C.DEFAULT_BINARY_PRESET)
        self._set_state_value("_preset", next_preset, self.update_binary)

    def update_binary(self, bgr: np.ndarray):
        """入力フレームを2値化して表示する。"""
        if not self._set_last_bgr(bgr):
            return
        gray = cvt_color_cached(bgr, cv2.COLOR_BGR2GRAY)

        # Otsu を基準にプリセット分だけ閾値をシフトする。
        otsu_thr, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        shift = 0
        if self._preset == C.BINARY_PRESET_MORE_WHITE:
            shift = -20
        elif self._preset == C.BINARY_PRESET_MORE_BLACK:
            shift = 20
        thr = clamp_int(round(float(otsu_thr) + shift), 0, 255)
        _thr, binary = cv2.threshold(gray, thr, 255, cv2.THRESH_BINARY)
        pm = gray_to_qpixmap(binary, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)


class TernaryView(BaseImageLabelView):
    """3値化表示ビュー。"""

    def __init__(self):
        """既定プリセットで3値化ビューを初期化する。"""
        super().__init__("3値化なし")
        self._preset = C.DEFAULT_TERNARY_PRESET  # standard | soft | strong
        self.set_resize_renderer(self.update_ternary)

    def set_preset(self, preset: str):
        """3値化プリセットを更新する。"""
        next_preset = safe_choice(preset, C.TERNARY_PRESETS, C.DEFAULT_TERNARY_PRESET)
        self._set_state_value("_preset", next_preset, self.update_ternary)

    def update_ternary(self, bgr: np.ndarray):
        """入力フレームを3値化して表示する。"""
        if not self._set_last_bgr(bgr):
            return
        gray = cvt_color_cached(bgr, cv2.COLOR_BGR2GRAY)

        # 輝度分布の分位点で 0/127/255 の3階調へ分割する。
        # uint8 のまま扱って不要なメモリコピーを避ける。
        flat = gray.reshape(-1)
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

        pm = gray_to_qpixmap(ternary, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)
