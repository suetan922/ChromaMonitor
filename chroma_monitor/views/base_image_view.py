"""画像表示系ビューの共通基底クラス。"""

from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QLabel, QSizePolicy

from ..util import constants as C

DEFAULT_IMAGE_VIEW_STYLE = "background:#111; border:1px solid #333; color:#AAA;"
_RESIZE_RERENDER_DEBOUNCE_MS = 140
_RESIZE_TRANSFORM_MODE = Qt.FastTransformation


class BaseImageLabelView(QLabel):
    """画像系ビューの共通表示処理を持つ基底クラス。"""

    def __init__(self, empty_text: str, style: str = DEFAULT_IMAGE_VIEW_STYLE):
        """空表示文言とスタイルを受け取り共通状態を初期化する。"""
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        # 最小幅のみ固定し、最小高はドック共通値で制御する。
        self.setMinimumWidth(C.VIEW_MIN_WIDTH)
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(style)
        self._empty_text = empty_text
        self._last_bgr: Optional[np.ndarray] = None
        self._last_resize_render_size: Optional[tuple[int, int]] = None
        self._resize_renderer: Optional[Callable[[np.ndarray], None]] = None
        self._resize_rerender_timer = QTimer(self)
        self._resize_rerender_timer.setSingleShot(True)
        self._resize_rerender_timer.setInterval(_RESIZE_RERENDER_DEBOUNCE_MS)
        self._resize_rerender_timer.timeout.connect(self._rerender_after_resize_idle)

    def minimumSizeHint(self):
        """共通最小サイズヒントを返す。"""
        return QSize(C.VIEW_MIN_WIDTH, 0)

    def sizeHint(self):
        """標準サイズヒントを返す。"""
        return QSize(240, 240)

    def _set_last_bgr(self, bgr: Optional[np.ndarray]) -> bool:
        """最新フレームを保持し、有効入力かどうかを返す。"""
        self._last_bgr = bgr
        if bgr is None or bgr.size == 0:
            self._last_resize_render_size = None
            self.setText(self._empty_text)
            return False
        return True

    def _set_state_value(
        self,
        attr_name: str,
        next_value,
        rerender: Callable[[np.ndarray], None],
    ) -> bool:
        """状態値を更新し、変化時のみ再描画する。"""
        if getattr(self, attr_name) == next_value:
            return False
        setattr(self, attr_name, next_value)
        self._rerender_with_last_bgr(rerender)
        return True

    def set_resize_renderer(self, renderer: Optional[Callable[[np.ndarray], None]]) -> None:
        """サイズ変更時に再描画するレンダラを設定する。"""
        self._resize_renderer = renderer

    def _rerender_with_last_bgr(self, renderer: Callable[[np.ndarray], None]) -> None:
        """保持中フレームがある場合のみ指定レンダラで再描画する。"""
        if self._last_bgr is None:
            return
        renderer(self._last_bgr)

    def _rerender_on_resize(self, renderer: Callable[[np.ndarray], None]) -> None:
        """サイズ変化時に必要な場合のみ再レンダリングする。"""
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

    def _rescale_current_pixmap_for_resize(self) -> bool:
        """リサイズ中は既存Pixmapの再スケールのみで追従する。"""
        # リサイズ中は重い再計算を避け、現在画像の再スケールだけで追従する。
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return False
        w, h = int(self.width()), int(self.height())
        if w <= 1 or h <= 1:
            return False
        scaled = pm.scaled(w, h, Qt.KeepAspectRatio, _RESIZE_TRANSFORM_MODE)
        if scaled.isNull():
            return False
        self.setPixmap(scaled)
        return True

    def _rerender_after_resize_idle(self) -> None:
        """リサイズ停止後に最終品質で再描画する。"""
        renderer = self._resize_renderer
        if renderer is None:
            return
        self._rerender_on_resize(renderer)

    def _is_resize_interaction_active(self) -> bool:
        """リサイズ中のデバウンス待ち状態かを返す。"""
        return self._resize_rerender_timer.isActive()

    def resizeEvent(self, event):
        """リサイズ時に軽量追従描画と遅延再描画を実行する。"""
        super().resizeEvent(event)
        if self._resize_renderer is None:
            return
        if event.size() == event.oldSize():
            return
        if self._last_bgr is None:
            return
        self._rescale_current_pixmap_for_resize()
        self._resize_rerender_timer.start()
