"""領域プレビューウィンドウ。"""

from typing import Optional

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..util.qt_image import bgr_to_qpixmap


class _PreviewImageLabel(QLabel):
    """領域プレビュー画像用ラベル。"""

    def minimumSizeHint(self):
        """画像サイズに引っ張られない最小ヒントを返す。"""
        return QSize(0, 0)

    def sizeHint(self):
        """画像未表示時の標準ヒントを返す。"""
        return QSize(320, 200)


class PreviewWindow(QWidget):
    """選択ROIのプレビュー表示専用ウィンドウ。"""

    closed = Signal()

    def __init__(self):
        """プレビュー表示UIと内部キャッシュを初期化する。"""
        super().__init__()
        self.setWindowTitle("領域プレビュー")
        self.resize(640, 420)
        self._last_bgr: Optional[np.ndarray] = None
        self._last_render_key: Optional[tuple[int, int, int]] = None

        self.lbl = _PreviewImageLabel("領域プレビュー")
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setStyleSheet("background:#111; border:1px solid #333; color:#AAA;")
        # QLabel の pixmap sizeHint 肥大化でウィンドウ最小サイズが増えるのを防ぐ。
        self.lbl.setMinimumSize(0, 0)
        self.lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.lbl)

    def update_preview(self, bgr: np.ndarray):
        """現在のROI画像をラベルサイズに合わせて表示更新する。"""
        self._last_bgr = bgr
        max_w = max(1, int(self.lbl.width() - 10))
        max_h = max(1, int(self.lbl.height() - 10))
        render_key = (id(bgr), max_w, max_h)
        if render_key == self._last_render_key:
            return
        self._last_render_key = render_key
        pm = bgr_to_qpixmap(bgr, max_w=max_w, max_h=max_h)
        self.lbl.setPixmap(pm)

    def show_placeholder(self, text: str):
        """プレビュー画像をクリアし、案内テキストを表示する。"""
        self._last_bgr = None
        self._last_render_key = None
        self.lbl.clear()
        self.lbl.setText(str(text or "領域プレビュー"))

    def set_composition_guide(self, _guide: str):
        """プレビューでは構図ガイドを無効化する。"""
        # 領域プレビューにはガイドを重ねない方針
        return

    def resizeEvent(self, event):
        """リサイズ時に保持画像の再スケール表示を行う。"""
        super().resizeEvent(event)
        if event.size() == event.oldSize():
            return
        self._last_render_key = None
        if self._last_bgr is not None:
            self.update_preview(self._last_bgr)

    def closeEvent(self, e):
        """閉じられたことを通知して通常クローズ処理へ委譲する。"""
        self.closed.emit()
        super().closeEvent(e)
