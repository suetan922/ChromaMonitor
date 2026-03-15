"""ROI選択オーバーレイ。"""

from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..util.qt_helpers import screen_union_geometry

_MIN_SELECTION_SIZE = 10


class RoiSelector(QWidget):
    """画面上でドラッグ選択したROI矩形を返すオーバーレイ。"""

    roiSelected = Signal(QRect)  # 画面座標
    selectionCanceled = Signal()

    def __init__(
        self, bounds: Optional[QRect] = None, help_text: str = "", as_window: bool = False
    ):
        """描画範囲と説明文を受け取り選択オーバーレイを初期化する。"""
        super().__init__(None)
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        # 全画面選択時は Window として出し、マルチモニタ全域を覆えるようにする
        flags |= Qt.Window if bounds is None or as_window else Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._help_text = help_text

        self._bounds = bounds if bounds is not None else screen_union_geometry(available=False)
        self.setGeometry(self._bounds)

        self._dragging = False
        self._start_local = QPoint()
        self._end_local = QPoint()

    def _event_local_point(self, event) -> QPoint:
        """入力イベント座標をウィジェット内ローカル座標へ正規化する。"""
        # ペン入力環境ではグローバル座標のスケールがずれることがあるため、
        # ローカル座標を使い、ROI通知時だけグローバル座標へ変換する。
        if hasattr(event, "position"):
            p = event.position().toPoint()
        elif hasattr(event, "pos"):
            p = event.pos()
        else:
            p = QPoint()
        return self._clamp_local(p)

    def _clamp_local(self, p: QPoint) -> QPoint:
        """点座標をウィジェット矩形内へクリップする。"""
        r = self.rect()
        x = min(max(p.x(), r.left()), r.right())
        y = min(max(p.y(), r.top()), r.bottom())
        return QPoint(x, y)

    def _begin_selection(self, event) -> None:
        """ドラッグ選択の開始位置を記録する。"""
        self._dragging = True
        self._start_local = self._event_local_point(event)
        self._end_local = self._start_local
        self.update()
        self.setWindowOpacity(1.0)

    def _update_selection(self, event) -> bool:
        """ドラッグ中の終点を更新する。"""
        if not self._dragging:
            return False
        self._end_local = self._event_local_point(event)
        self.update()
        return True

    def _finish_selection(self, event) -> bool:
        """ドラッグ終了時にROIを確定またはキャンセルする。"""
        if not self._dragging or event.button() != Qt.LeftButton:
            return False
        self._dragging = False
        self._end_local = self._event_local_point(event)
        r_local = QRect(self._start_local, self._end_local).normalized()
        if r_local.width() >= _MIN_SELECTION_SIZE and r_local.height() >= _MIN_SELECTION_SIZE:
            tl = self.mapToGlobal(r_local.topLeft())
            br = self.mapToGlobal(r_local.bottomRight())
            self.roiSelected.emit(QRect(tl, br).normalized())
        else:
            self.selectionCanceled.emit()
        self.close()
        return True

    def mousePressEvent(self, e):
        """マウス左押下で選択開始する。"""
        if e.button() == Qt.LeftButton:
            self._begin_selection(e)

    def mouseMoveEvent(self, e):
        """マウス移動で選択矩形を更新する。"""
        self._update_selection(e)

    def mouseReleaseEvent(self, e):
        """マウス左解放で選択を確定する。"""
        self._finish_selection(e)

    def tabletPressEvent(self, e):
        """タブレット左押下で選択開始する。"""
        if e.button() == Qt.LeftButton:
            self._begin_selection(e)
            e.accept()
            return
        super().tabletPressEvent(e)

    def tabletMoveEvent(self, e):
        """タブレット移動で選択矩形を更新する。"""
        if self._update_selection(e):
            e.accept()
            return
        super().tabletMoveEvent(e)

    def tabletReleaseEvent(self, e):
        """タブレット左解放で選択を確定する。"""
        if self._finish_selection(e):
            e.accept()
            return
        super().tabletReleaseEvent(e)

    def keyPressEvent(self, e):
        """Esc入力で選択をキャンセルする。"""
        if e.key() == Qt.Key_Escape:
            self.selectionCanceled.emit()
            self.close()
            e.accept()
            return
        super().keyPressEvent(e)

    def showEvent(self, e):
        """表示時にフォーカスを取り、Esc入力を受け取りやすくする。"""
        super().showEvent(e)
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)

    def paintEvent(self, _):
        """オーバーレイ背景と選択矩形を描画する。"""
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.fillRect(self.rect(), QColor(0, 0, 0, 140))

            if self._bounds is not None:
                pen = QPen(QColor(255, 255, 255, 120), 1, Qt.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(self.rect().adjusted(1, 1, -2, -2))

            if self._help_text:
                p.setPen(QColor(255, 255, 255, 200))
                p.drawText(
                    self.rect().adjusted(12, 10, -12, -10),
                    Qt.AlignTop | Qt.AlignLeft,
                    self._help_text,
                )

            if self._dragging:
                r = QRect(self._start_local, self._end_local).normalized()

                p.setCompositionMode(QPainter.CompositionMode_Clear)
                p.fillRect(r, Qt.transparent)
                p.setCompositionMode(QPainter.CompositionMode_SourceOver)

                pen = QPen(QColor(0, 255, 200, 240), 2, Qt.SolidLine)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(r)
                p.setPen(QColor(255, 255, 255, 230))
                p.drawText(r.topLeft() + QPoint(6, -6), f"{r.width()} x {r.height()}")
            else:
                p.setPen(QColor(220, 220, 220, 220))
                p.drawText(self.rect(), Qt.AlignCenter, "左ドラッグで領域を選択\nEscでキャンセル")
        finally:
            p.end()
