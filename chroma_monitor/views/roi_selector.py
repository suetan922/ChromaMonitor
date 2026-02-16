"""ROI selection overlay widget."""

from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..util.functions import screen_union_geometry


class RoiSelector(QWidget):
    roiSelected = Signal(QRect)  # screen coords

    def __init__(
        self, bounds: Optional[QRect] = None, help_text: str = "", as_window: bool = False
    ):
        super().__init__(None)
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        # 全画面選択時は Window として出し、マルチモニタ全域を覆えるようにする
        flags |= Qt.Window if bounds is None or as_window else Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._help_text = help_text

        self._bounds = bounds if bounds is not None else self._all_screens_geometry()
        self.setGeometry(self._bounds)

        self._dragging = False
        self._start_local = QPoint()
        self._end_local = QPoint()

    def _all_screens_geometry(self) -> QRect:
        return screen_union_geometry(available=False)

    def _event_local_point(self, event) -> QPoint:
        # Pen displays may report globalPosition with a different scale.
        # Use widget-local coordinates and map to global only when emitting ROI.
        if hasattr(event, "position"):
            p = event.position().toPoint()
        elif hasattr(event, "pos"):
            p = event.pos()
        else:
            p = QPoint()
        return self._clamp_local(p)

    def _clamp_local(self, p: QPoint) -> QPoint:
        r = self.rect()
        x = min(max(p.x(), r.left()), r.right())
        y = min(max(p.y(), r.top()), r.bottom())
        return QPoint(x, y)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._start_local = self._event_local_point(e)
            self._end_local = self._start_local
            self.update()
            self.setWindowOpacity(1.0)

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._end_local = self._event_local_point(e)
            self.update()

    def mouseReleaseEvent(self, e):
        if self._dragging and e.button() == Qt.LeftButton:
            self._dragging = False
            self._end_local = self._event_local_point(e)
            r_local = QRect(self._start_local, self._end_local).normalized()
            if r_local.width() >= 10 and r_local.height() >= 10:
                tl = self.mapToGlobal(r_local.topLeft())
                br = self.mapToGlobal(r_local.bottomRight())
                self.roiSelected.emit(QRect(tl, br).normalized())
            self.close()

    def tabletPressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._start_local = self._event_local_point(e)
            self._end_local = self._start_local
            self.update()
            self.setWindowOpacity(1.0)
            e.accept()
            return
        super().tabletPressEvent(e)

    def tabletMoveEvent(self, e):
        if self._dragging:
            self._end_local = self._event_local_point(e)
            self.update()
            e.accept()
            return
        super().tabletMoveEvent(e)

    def tabletReleaseEvent(self, e):
        if self._dragging and e.button() == Qt.LeftButton:
            self._dragging = False
            self._end_local = self._event_local_point(e)
            r_local = QRect(self._start_local, self._end_local).normalized()
            if r_local.width() >= 10 and r_local.height() >= 10:
                tl = self.mapToGlobal(r_local.topLeft())
                br = self.mapToGlobal(r_local.bottomRight())
                self.roiSelected.emit(QRect(tl, br).normalized())
            self.close()
            e.accept()
            return
        super().tabletReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()

    def paintEvent(self, _):
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
