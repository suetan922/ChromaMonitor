"""ビュー描画に関する処理。"""

from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy

from ..util import constants as C

DEFAULT_IMAGE_VIEW_STYLE = "background:#111; border:1px solid #333; color:#AAA;"


class BaseImageLabelView(QLabel):

    def __init__(self, empty_text: str, style: str = DEFAULT_IMAGE_VIEW_STYLE):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        # 最小幅のみ固定し、最小高はドック共通値で制御する。
        self.setMinimumWidth(C.VIEW_MIN_SIZE)
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(style)
        self._empty_text = empty_text
        self._last_bgr: Optional[np.ndarray] = None
        self._last_resize_render_size: Optional[tuple[int, int]] = None
        self._resize_renderer: Optional[Callable[[np.ndarray], None]] = None

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, 0)

    def sizeHint(self):
        return QSize(240, 240)

    def _show_empty(self):
        self.setText(self._empty_text)

    def _set_last_bgr(self, bgr: Optional[np.ndarray]) -> bool:
        self._last_bgr = bgr
        if bgr is None or bgr.size == 0:
            self._last_resize_render_size = None
            self._show_empty()
            return False
        return True

    def set_resize_renderer(self, renderer: Optional[Callable[[np.ndarray], None]]) -> None:
        """サイズ変更時に再描画するレンダラを設定する。"""
        self._resize_renderer = renderer

    def _rerender_on_resize(self, renderer: Callable[[np.ndarray], None]) -> None:
        if self._last_bgr is None:
            return
        if not self.isVisible() or self.isHidden():
            return
        w, h = self.width(), self.height()
        if w <= 1 or h <= 1:
            return
        current_size = (int(w), int(h))
        if current_size == self._last_resize_render_size:
            return
        renderer(self._last_bgr)
        self._last_resize_render_size = current_size

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._resize_renderer is None:
            return
        self._rerender_on_resize(self._resize_renderer)
