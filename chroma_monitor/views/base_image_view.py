"""Shared base class for image label views."""

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

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, 0)

    def sizeHint(self):
        return QSize(240, 240)

    def _show_empty(self):
        self.setText(self._empty_text)

    def _set_last_bgr(self, bgr: Optional[np.ndarray]) -> bool:
        self._last_bgr = bgr
        if bgr is None or bgr.size == 0:
            self._show_empty()
            return False
        return True

    def _rerender_on_resize(self, renderer: Callable[[np.ndarray], None]) -> None:
        if self._last_bgr is not None:
            renderer(self._last_bgr)
