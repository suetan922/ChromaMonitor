"""Preview window widget."""

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..util.functions import bgr_to_qpixmap


class PreviewWindow(QWidget):
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("領域プレビュー")
        self.resize(640, 420)
        self._last_bgr: Optional[np.ndarray] = None

        self.lbl = QLabel("領域プレビュー")
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setStyleSheet("background:#111; border:1px solid #333; color:#AAA;")

        l = QVBoxLayout(self)
        l.setContentsMargins(8, 8, 8, 8)
        l.addWidget(self.lbl)

    def update_preview(self, bgr: np.ndarray):
        self._last_bgr = bgr
        pm = bgr_to_qpixmap(bgr, max_w=self.lbl.width() - 10, max_h=self.lbl.height() - 10)
        self.lbl.setPixmap(pm)

    def set_composition_guide(self, guide: str):
        # 領域プレビューにはガイドを重ねない方針
        _ = guide

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_bgr is not None:
            self.update_preview(self._last_bgr)

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)
