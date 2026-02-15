import math
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, QRect, QPoint, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QImage, QPixmap, QGuiApplication
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QSizePolicy

from .util import constants as C
from .util.functions import (
    bgr_to_qpixmap,
    clamp_render_size,
    clamp_int,
    gray_to_qpixmap,
    resize_by_long_edge,
    rgb_to_qpixmap,
    safe_choice,
)


def _normalize_map(src: np.ndarray) -> np.ndarray:
    arr = np.asarray(src, dtype=np.float32)
    if arr.size == 0:
        return np.zeros((1, 1), dtype=np.float32)

    lo = float(np.percentile(arr, 1.0))
    hi = float(np.percentile(arr, 99.0))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo + 1e-6:
        lo = float(arr.min())
        hi = float(arr.max())
    if hi <= lo + 1e-6:
        return np.zeros_like(arr, dtype=np.float32)

    out = (arr - lo) / (hi - lo)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _apply_composition_guides(bgr: np.ndarray, guide: str) -> np.ndarray:
    if bgr is None or bgr.size == 0:
        return bgr
    if guide not in C.COMPOSITION_GUIDES[1:]:
        return bgr

    out = bgr.copy()
    h, w = out.shape[:2]
    if h < 2 or w < 2:
        return out

    # 以前より細めにして、サリエンシー本体の視認性を優先
    base_thick = max(1, int(round(min(w, h) / 520.0)))

    lines = []
    points = []

    if guide == C.COMPOSITION_GUIDE_THIRDS:
        x1, x2 = w // 3, (w * 2) // 3
        y1, y2 = h // 3, (h * 2) // 3
        lines.extend([
            ((x1, 0), (x1, h - 1)),
            ((x2, 0), (x2, h - 1)),
            ((0, y1), (w - 1, y1)),
            ((0, y2), (w - 1, y2)),
        ])
        # 三分割の注目点を補助表示
        points.extend([(x1, y1), (x1, y2), (x2, y1), (x2, y2)])
    elif guide == C.COMPOSITION_GUIDE_CENTER:
        cx, cy = w // 2, h // 2
        lines.extend([
            ((cx, 0), (cx, h - 1)),
            ((0, cy), (w - 1, cy)),
        ])
        points.append((cx, cy))
    elif guide == C.COMPOSITION_GUIDE_DIAGONAL:
        lines.extend([
            ((0, 0), (w - 1, h - 1)),
            ((0, h - 1), (w - 1, 0)),
        ])

    if not lines:
        return out

    # 先に細い主線マスクを作り、その外周だけを一括で縁取りする。
    # 交点で縁取り同士が重なって四角く見える問題を避けるため。
    core = np.zeros((h, w), dtype=np.uint8)
    for p1, p2 in lines:
        cv2.line(core, p1, p2, 255, base_thick, cv2.LINE_AA)

    if points:
        pr = max(1, base_thick - 1)
        for p in points:
            cv2.circle(core, p, pr, 255, -1, cv2.LINE_AA)

    ring = max(1, base_thick)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ring * 2 + 1, ring * 2 + 1))
    outline = cv2.subtract(cv2.dilate(core, kernel), core)

    out_f = out.astype(np.float32)
    outline_a = (outline.astype(np.float32) / 255.0)[:, :, None]
    core_a = (core.astype(np.float32) / 255.0)[:, :, None]
    out_f = out_f * (1.0 - outline_a)  # black outline
    white = np.array([245.0, 245.0, 245.0], dtype=np.float32).reshape(1, 1, 3)
    out_f = out_f * (1.0 - core_a) + white * core_a
    out = np.clip(out_f, 0, 255).astype(np.uint8)

    return out


class RoiSelector(QWidget):
    roiSelected = Signal(QRect)  # screen coords

    def __init__(self, bounds: Optional[QRect] = None, help_text: str = "", as_window: bool = False):
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
        ps = QGuiApplication.primaryScreen()
        if ps is not None:
            vg = ps.virtualGeometry()
            if vg.isValid() and vg.width() > 0 and vg.height() > 0:
                return vg
        screens = QGuiApplication.screens()
        if not screens:
            return QRect(0, 0, 1920, 1080)
        rect = screens[0].geometry()
        for screen in screens[1:]:
            rect = rect.united(screen.geometry())
        return rect

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
                p.drawText(self.rect().adjusted(12, 10, -12, -10), Qt.AlignTop | Qt.AlignLeft, self._help_text)

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


class ColorWheelWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(64, 64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._hist = np.zeros(180, dtype=np.float32)
        self._max = 1.0
        self._base_ratio = 0.33
        self._min_thickness_ratio = 0.06

    def update_hist(self, hist: np.ndarray):
        hist = hist.astype(np.float32)
        self._hist = hist
        self._max = float(hist.max()) if hist.size else 1.0
        if self._max <= 0:
            self._max = 1.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.fillRect(self.rect(), QColor(255, 255, 255, 255))

            rect = self.rect().adjusted(12, 12, -12, -12)
            cx, cy = rect.center().x(), rect.center().y()
            r = min(rect.width(), rect.height()) // 2

            p.setPen(Qt.NoPen)
            p.setBrush(QColor(235, 235, 235, 255))
            p.drawEllipse(QPoint(cx, cy), r, r)

            inner_r = int(r * self._base_ratio)
            p.setBrush(QColor(255, 255, 255, 255))
            p.drawEllipse(QPoint(cx, cy), inner_r, inner_r)

            ring_max = r - inner_r
            if ring_max <= 2:
                return

            # ヒストグラム風のリング帯を扇形で描画する
            # 角度を少し重ねて、見た目の切れ目を減らす
            base_thickness = max(2, int(ring_max * max(0.08, self._min_thickness_ratio)))
            step_deg = 2.0
            overlap_deg = 0.25
            for h in range(180):
                count = float(self._hist[h])
                norm = min(1.0, count / self._max) if self._max > 0 else 0.0
                thickness_ratio = self._min_thickness_ratio + (1.0 - self._min_thickness_ratio) * norm
                thickness = max(base_thickness, int(ring_max * thickness_ratio))
                outer_r = inner_r + thickness
                hue_deg = int((h / 180.0) * 360.0)
                c = QColor()
                c.setHsv(hue_deg, 255, 255)
                alpha = 90 if count <= 0 else 225
                c.setAlpha(alpha)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                start_deg = 90.0 - (h * step_deg) + overlap_deg
                span_deg = -(step_deg + overlap_deg * 2.0)
                p.drawPie(
                    int(cx - outer_r),
                    int(cy - outer_r),
                    int(outer_r * 2),
                    int(outer_r * 2),
                    int(start_deg * 16),
                    int(span_deg * 16),
                )
                # 内側を同角度で塗ってリング化
                p.setBrush(QColor(255, 255, 255, 255))
                p.drawPie(
                    int(cx - inner_r),
                    int(cy - inner_r),
                    int(inner_r * 2),
                    int(inner_r * 2),
                    int(start_deg * 16),
                    int(span_deg * 16),
                )

            # 内周の境界を整える
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 255))
            p.drawEllipse(QPoint(cx, cy), inner_r, inner_r)
        finally:
            p.end()


class ScatterRasterWidget(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#FFFFFF; border:none; color:#222;")
        self._last_pm: Optional[QPixmap] = None
        self._square_limit = True
        self._last_sv: Optional[np.ndarray] = None
        self._last_rgb: Optional[np.ndarray] = None
        self._shape = "square"  # square | triangle
        self._show_scatter_frame_only()

    def set_shape(self, shape: str):
        self._shape = "triangle" if shape == "triangle" else "square"
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
        else:
            self._show_scatter_frame_only()

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    def sizeHint(self):
        return QSize(300, 300)

    def _draw_scatter_frame(self, pm: QPixmap):
        painter = QPainter(pm)
        if not painter.isActive():
            return
        try:
            pen = QPen(QColor(95, 105, 118, 185), max(1, int(pm.width() * 0.0045)))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            inset = pen.width() // 2
            if self._shape == "triangle":
                p_white = QPoint(inset, inset)
                p_black = QPoint(inset, pm.height() - 1 - inset)
                p_hue = QPoint(pm.width() - 1 - inset, pm.height() // 2)
                painter.drawLine(p_white, p_black)
                painter.drawLine(p_black, p_hue)
                painter.drawLine(p_hue, p_white)
            else:
                rw = pm.width() - 1 - inset * 2
                rh = pm.height() - 1 - inset * 2
                if rw > 0 and rh > 0:
                    painter.drawRect(inset, inset, rw, rh)
        finally:
            painter.end()

    def _make_scatter_pixmap(self, img: np.ndarray) -> Optional[QPixmap]:
        img = np.flipud(img).copy()
        qimg = QImage(img.data, 256, 256, 256 * 4, QImage.Format_RGBA8888).copy()
        base_side = min(self.width(), self.height()) if self._square_limit else max(self.width(), self.height())
        target_side, _ = clamp_render_size(base_side, base_side)
        pm = QPixmap.fromImage(qimg).scaled(target_side, target_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if pm.isNull():
            return None
        self._draw_scatter_frame(pm)
        return pm

    def _show_scatter_frame_only(self):
        img = np.zeros((256, 256, 4), dtype=np.uint8)
        pm = self._make_scatter_pixmap(img)
        if pm is not None:
            self._last_pm = pm
            self.setText("")
            self.setPixmap(pm)
        else:
            self.setText("散布図（S-V）")

    def update_scatter(self, sv: np.ndarray, rgb: np.ndarray):
        img = np.zeros((256, 256, 4), dtype=np.uint8)
        self._last_sv = sv
        self._last_rgb = rgb
        if sv is None or rgb is None or sv.size == 0 or rgb.size == 0:
            self._show_scatter_frame_only()
            return

        def paint_points(x: np.ndarray, y: np.ndarray, colors: np.ndarray):
            a = np.full((len(x),), 160, dtype=np.uint8)
            for dy in (0, 1):
                for dx in (0, 1):
                    yy = np.clip(y + dy, 0, 255)
                    xx = np.clip(x + dx, 0, 255)
                    img[yy, xx, 0:3] = colors
                    img[yy, xx, 3] = a

        try:
            sv_arr = np.asarray(sv)
            rgb_arr = np.asarray(rgb)
            if sv_arr.ndim != 2 or sv_arr.shape[1] < 2 or rgb_arr.ndim != 2 or rgb_arr.shape[1] < 3:
                self._show_scatter_frame_only()
                return

            n = min(int(sv_arr.shape[0]), int(rgb_arr.shape[0]))
            if n <= 0:
                self._show_scatter_frame_only()
                return

            s = np.clip(sv_arr[:n, 0].astype(np.int32), 0, 255)
            v = np.clip(sv_arr[:n, 1].astype(np.int32), 0, 255)
            rgb_u8 = np.clip(rgb_arr[:n, :3], 0, 255).astype(np.uint8, copy=False)

            if self._shape == "triangle":
                # 右向きHSV三角: 左上=白, 左下=黒, 右中=純色
                prod = s * v
                x = np.clip(prod // 255, 0, 255).astype(np.int32)
                y = np.clip(v - (prod // 510), 0, 255).astype(np.int32)
                paint_points(x, y, rgb_u8)
            else:
                paint_points(s, v, rgb_u8)
        except Exception:
            # 描画エラー時は四角モードへフォールバックして継続
            self._shape = "square"
            try:
                sv_arr = np.asarray(sv)
                rgb_arr = np.asarray(rgb)
                n = min(int(sv_arr.shape[0]), int(rgb_arr.shape[0]))
                if n <= 0:
                    self._show_scatter_frame_only()
                    return
                s = np.clip(sv_arr[:n, 0].astype(np.int32), 0, 255)
                v = np.clip(sv_arr[:n, 1].astype(np.int32), 0, 255)
                rgb_u8 = np.clip(rgb_arr[:n, :3], 0, 255).astype(np.uint8, copy=False)
                paint_points(s, v, rgb_u8)
            except Exception:
                self._show_scatter_frame_only()
                return

        pm = self._make_scatter_pixmap(img)
        if pm is None:
            self._show_scatter_frame_only()
            return

        self._last_pm = pm
        self.setText("")
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
        else:
            self._show_scatter_frame_only()


class ChannelHistogram(QWidget):
    def __init__(self, title: str, bins: int, max_value: int, color: QColor, bucket: int = 4):
        super().__init__()
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._title = title
        self._bins = bins
        self._max_value = max_value
        self._color = color
        self._bucket = max(1, bucket)
        self._hist = np.zeros(bins, dtype=np.int64)
        self._mean = 0.0
        self._std = 0.0
        self._total = 0

    def update_from_values(self, values: np.ndarray):
        flat = values.reshape(-1).astype(np.int32)
        flat = np.clip(flat, 0, self._max_value)
        hist = np.bincount(flat, minlength=self._bins)[: self._bins]
        self._hist = hist
        total = int(hist.sum())
        self._total = total
        if total > 0:
            idx = np.arange(self._bins, dtype=np.float64)
            mean = float((idx * hist).sum() / total)
            var = float((((idx - mean) ** 2) * hist).sum() / total)
            self._mean = mean
            self._std = math.sqrt(var)
        else:
            self._mean = self._std = 0.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.fillRect(self.rect(), QColor(255, 255, 255, 255))

            title_rect = self.rect().adjusted(10, 6, -10, -6)
            p.setPen(QColor(30, 30, 30))
            p.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop, self._title)

            if self._total == 0:
                p.setPen(QColor(120, 120, 120))
                p.drawText(self.rect(), Qt.AlignCenter, "データなし")
                return

            plot = self.rect().adjusted(12, 26, -12, -44)
            if plot.width() <= 10 or plot.height() <= 10:
                return

            max_y = int(self._hist.max())
            if max_y <= 0:
                max_y = 1

            p.setPen(QColor(225, 225, 225))
            for i in range(1, 5):
                y = plot.top() + int(plot.height() * i / 5)
                p.drawLine(plot.left(), y, plot.right(), y)

            p.setPen(QColor(180, 180, 180))
            p.drawLine(plot.left(), plot.top(), plot.left(), plot.bottom())
            p.drawLine(plot.left(), plot.bottom(), plot.right(), plot.bottom())

            bucket = self._bucket
            bins = self._hist
            if self._bins % bucket == 0:
                bins = bins.reshape(-1, bucket).sum(axis=1)
            n_bins = len(bins)
            bin_w = plot.width() / float(n_bins)
            plot_h = max(1, plot.height() - 1)
            for i, val in enumerate(bins):
                h = min(plot_h, int(plot_h * (val / max_y)))
                x = plot.left() + int(i * bin_w)
                w = max(1, int(bin_w) - 1)
                y = plot.bottom() - h
                c = QColor(self._color)
                c.setAlpha(200)
                p.fillRect(QRect(x, y, w, h), c)

            p.setPen(QColor(30, 30, 30))
            axis_rect = QRect(plot.left(), plot.bottom() + 4, plot.width(), 14)
            p.drawText(axis_rect, Qt.AlignLeft | Qt.AlignVCenter, "0")
            p.drawText(axis_rect, Qt.AlignRight | Qt.AlignVCenter, str(self._max_value))

            stats = f"平均 {self._mean:.1f} / 標準偏差 {self._std:.1f}"
            p.drawText(QRect(plot.left(), plot.bottom() + 20, plot.width(), 18), Qt.AlignCenter | Qt.AlignVCenter, stats)
        finally:
            p.end()


class EdgeView(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#111; border:1px solid #333; color:#AAA;")
        self._last_bgr: Optional[np.ndarray] = None
        self._sensitivity = C.DEFAULT_EDGE_SENSITIVITY  # 1..100

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    def sizeHint(self):
        return QSize(240, 240)

    def set_sensitivity(self, value: int):
        self._sensitivity = clamp_int(value, C.EDGE_SENSITIVITY_MIN, C.EDGE_SENSITIVITY_MAX)
        if self._last_bgr is not None:
            self.update_edge(self._last_bgr)

    def update_edge(self, bgr: np.ndarray):
        self._last_bgr = bgr
        if bgr.size == 0:
            self.setText("エッジ未検出")
            return
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = resize_by_long_edge(gray, C.ANALYZER_MAX_DIM)
        # 感度が高いほど閾値を下げて、細かいエッジも拾う
        span = max(1, C.EDGE_SENSITIVITY_MAX - C.EDGE_SENSITIVITY_MIN)
        t = (self._sensitivity - C.EDGE_SENSITIVITY_MIN) / span
        low = int(round(120 - 100 * t))
        high = int(round(240 - 160 * t))
        if high <= low:
            high = low + 1
        edges = cv2.Canny(gray, low, high)
        edges_rgb = cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB)
        pm = rgb_to_qpixmap(edges_rgb, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_bgr is not None:
            self.update_edge(self._last_bgr)


class GrayscaleView(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#111; border:1px solid #333; color:#AAA;")
        self._last_bgr: Optional[np.ndarray] = None

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    def sizeHint(self):
        return QSize(240, 240)

    def update_gray(self, bgr: np.ndarray):
        self._last_bgr = bgr
        if bgr.size == 0:
            self.setText("グレースケールなし")
            return
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        pm = gray_to_qpixmap(gray, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_bgr is not None:
            self.update_gray(self._last_bgr)


class BinaryView(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#111; border:1px solid #333; color:#AAA;")
        self._last_bgr: Optional[np.ndarray] = None
        self._preset = C.DEFAULT_BINARY_PRESET  # auto | more_white | more_black

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    def sizeHint(self):
        return QSize(240, 240)

    def set_preset(self, preset: str):
        self._preset = safe_choice(preset, C.BINARY_PRESETS, C.DEFAULT_BINARY_PRESET)
        if self._last_bgr is not None:
            self.update_binary(self._last_bgr)

    def update_binary(self, bgr: np.ndarray):
        self._last_bgr = bgr
        if bgr.size == 0:
            self.setText("2値化なし")
            return
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = resize_by_long_edge(gray, C.ANALYZER_MAX_DIM)

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_bgr is not None:
            self.update_binary(self._last_bgr)


class TernaryView(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#111; border:1px solid #333; color:#AAA;")
        self._last_bgr: Optional[np.ndarray] = None
        self._preset = C.DEFAULT_TERNARY_PRESET  # standard | soft | strong

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    def sizeHint(self):
        return QSize(240, 240)

    def set_preset(self, preset: str):
        self._preset = safe_choice(preset, C.TERNARY_PRESETS, C.DEFAULT_TERNARY_PRESET)
        if self._last_bgr is not None:
            self.update_ternary(self._last_bgr)

    def update_ternary(self, bgr: np.ndarray):
        self._last_bgr = bgr
        if bgr.size == 0:
            self.setText("3値化なし")
            return
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = resize_by_long_edge(gray, C.ANALYZER_MAX_DIM)

        flat = gray.reshape(-1).astype(np.float32)
        p1, p2 = 33.3, 66.6
        if self._preset == C.TERNARY_PRESET_SOFT:
            p1, p2 = 25.0, 75.0
        elif self._preset == C.TERNARY_PRESET_STRONG:
            p1, p2 = 40.0, 60.0
        t1, t2 = np.percentile(flat, [p1, p2])
        if t2 <= t1:
            mean = float(flat.mean()) if flat.size else 127.0
            t1 = max(0.0, mean - 32.0)
            t2 = min(255.0, mean + 32.0)

        ternary = np.zeros_like(gray, dtype=np.uint8)
        ternary[gray >= t1] = 127
        ternary[gray >= t2] = 255

        pm = gray_to_qpixmap(ternary, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_bgr is not None:
            self.update_ternary(self._last_bgr)


class SaliencyView(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#111; border:1px solid #333; color:#AAA;")
        self._last_bgr: Optional[np.ndarray] = None
        self._last_saliency: Optional[np.ndarray] = None
        self._last_overlay_rgba: Optional[np.ndarray] = None
        self._overlay_alpha = C.DEFAULT_SALIENCY_OVERLAY_ALPHA  # 0..100
        self._guide = C.DEFAULT_COMPOSITION_GUIDE  # none | thirds | center | diagonal
        self._sr_detector = None
        self._sr_detector_ready = False

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    def sizeHint(self):
        return QSize(240, 240)

    def set_overlay_alpha(self, value: int):
        self._overlay_alpha = clamp_int(value, C.SALIENCY_ALPHA_MIN, C.SALIENCY_ALPHA_MAX)
        if self._last_bgr is not None:
            self.update_saliency(self._last_bgr)

    def set_composition_guide(self, guide: str):
        self._guide = safe_choice(guide, C.COMPOSITION_GUIDES, C.DEFAULT_COMPOSITION_GUIDE)
        if self._last_bgr is not None:
            self.update_saliency(self._last_bgr)

    def saliency_map(self) -> Optional[np.ndarray]:
        if self._last_saliency is None:
            return None
        return self._last_saliency.copy()

    def overlay_rgba(self) -> Optional[np.ndarray]:
        if self._last_overlay_rgba is None:
            return None
        return self._last_overlay_rgba.copy()

    def _compute_spectral_saliency_opencv(self, bgr: np.ndarray) -> Optional[np.ndarray]:
        if not self._sr_detector_ready:
            self._sr_detector_ready = True
            try:
                if hasattr(cv2, "saliency") and hasattr(cv2.saliency, "StaticSaliencySpectralResidual_create"):
                    self._sr_detector = cv2.saliency.StaticSaliencySpectralResidual_create()
            except Exception:
                self._sr_detector = None

        if self._sr_detector is None:
            return None

        try:
            ok, sal = self._sr_detector.computeSaliency(bgr)
            if not ok or sal is None:
                return None
            arr = np.asarray(sal, dtype=np.float32)
            if arr.ndim == 3:
                arr = arr[:, :, 0]
            if arr.shape != bgr.shape[:2]:
                arr = cv2.resize(arr, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_CUBIC)
            return arr
        except Exception:
            return None

    def _compute_spectral_saliency_fft(self, bgr: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        h, w = gray.shape[:2]
        long_side = max(h, w)
        target_long = 192
        scale = min(1.0, float(target_long) / float(long_side))
        if scale < 1.0:
            rw = max(16, int(round(w * scale)))
            rh = max(16, int(round(h * scale)))
            src = cv2.resize(gray, (rw, rh), interpolation=cv2.INTER_AREA)
        else:
            src = gray

        fft = np.fft.fft2(src)
        log_amp = np.log(np.abs(fft) + 1e-8)
        phase = np.angle(fft)
        smooth = cv2.blur(log_amp, (3, 3))
        residual = log_amp - smooth
        spec = np.exp(residual + 1j * phase)
        sal = np.abs(np.fft.ifft2(spec)) ** 2
        sal = cv2.GaussianBlur(sal.astype(np.float32), (0, 0), 2.0)
        if sal.shape != (h, w):
            sal = cv2.resize(sal, (w, h), interpolation=cv2.INTER_CUBIC)
        return sal.astype(np.float32)

    def _compute_saliency(self, bgr: np.ndarray) -> np.ndarray:
        sal = self._compute_spectral_saliency_opencv(bgr)
        if sal is None:
            sal = self._compute_spectral_saliency_fft(bgr)
        return _normalize_map(sal)

    def _make_overlay_rgba(self, saliency: np.ndarray) -> np.ndarray:
        sal_u8 = np.clip(np.round(saliency * 255.0), 0, 255).astype(np.uint8)
        heat_bgr = cv2.applyColorMap(sal_u8, cv2.COLORMAP_JET)
        heat_rgb = cv2.cvtColor(heat_bgr, cv2.COLOR_BGR2RGB)
        alpha = np.clip(np.round(saliency * (self._overlay_alpha / 100.0) * 255.0), 0, 255).astype(np.uint8)
        return np.dstack([heat_rgb, alpha])

    def update_saliency(self, bgr: np.ndarray):
        self._last_bgr = bgr
        if bgr.size == 0:
            self.setText("サリエンシーなし")
            return

        try:
            saliency = self._compute_saliency(bgr)
        except Exception:
            saliency = _normalize_map(self._compute_spectral_saliency_fft(bgr))

        self._last_saliency = saliency
        self._last_overlay_rgba = self._make_overlay_rgba(saliency)

        overlay_bgr = cv2.cvtColor(self._last_overlay_rgba[:, :, :3], cv2.COLOR_RGB2BGR).astype(np.float32)
        alpha = (self._last_overlay_rgba[:, :, 3].astype(np.float32) / 255.0)[:, :, None]
        # 元画像をグレースケール化して残差を見やすくする
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        base = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR).astype(np.float32)
        view_bgr = np.clip(base * (1.0 - alpha) + overlay_bgr * alpha, 0, 255).astype(np.uint8)
        view_bgr = _apply_composition_guides(view_bgr, self._guide)

        view_rgb = cv2.cvtColor(view_bgr, cv2.COLOR_BGR2RGB)
        pm = rgb_to_qpixmap(view_rgb, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_bgr is not None:
            self.update_saliency(self._last_bgr)


class FocusPeakingView(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#111; border:1px solid #333; color:#AAA;")
        self._last_bgr: Optional[np.ndarray] = None
        self._sensitivity = C.DEFAULT_FOCUS_PEAK_SENSITIVITY
        self._color = C.DEFAULT_FOCUS_PEAK_COLOR
        self._thickness = C.DEFAULT_FOCUS_PEAK_THICKNESS

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    def sizeHint(self):
        return QSize(240, 240)

    def set_sensitivity(self, value: int):
        self._sensitivity = clamp_int(value, C.FOCUS_PEAK_SENSITIVITY_MIN, C.FOCUS_PEAK_SENSITIVITY_MAX)
        if self._last_bgr is not None:
            self.update_focus(self._last_bgr)

    def set_color(self, color: str):
        self._color = safe_choice(color, C.FOCUS_PEAK_COLORS, C.DEFAULT_FOCUS_PEAK_COLOR)
        if self._last_bgr is not None:
            self.update_focus(self._last_bgr)

    def set_thickness(self, value: float):
        self._thickness = max(C.FOCUS_PEAK_THICKNESS_MIN, min(C.FOCUS_PEAK_THICKNESS_MAX, float(value)))
        if self._last_bgr is not None:
            self.update_focus(self._last_bgr)

    def _focus_mask(self, gray: np.ndarray) -> np.ndarray:
        blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
        gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        if not np.isfinite(mag).any():
            return np.zeros_like(gray, dtype=np.uint8)

        span = max(1, C.FOCUS_PEAK_SENSITIVITY_MAX - C.FOCUS_PEAK_SENSITIVITY_MIN)
        t = (self._sensitivity - C.FOCUS_PEAK_SENSITIVITY_MIN) / span
        percentile = 98.0 - 36.0 * t
        thr = float(np.percentile(mag, percentile))
        thr = max(thr, float(mag.mean()) * 0.45)
        mask = (mag >= thr).astype(np.uint8) * 255

        if self._thickness > 1.0:
            k = max(1, int(round(self._thickness * 2.0 - 1.0)))
            if k % 2 == 0:
                k += 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
            mask = cv2.dilate(mask, kernel, iterations=1)
        return mask

    def update_focus(self, bgr: np.ndarray):
        self._last_bgr = bgr
        if bgr.size == 0:
            self.setText("フォーカスピーキングなし")
            return

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = resize_by_long_edge(gray, C.ANALYZER_MAX_DIM)
        mask = self._focus_mask(gray)

        base = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR).astype(np.float32) * 0.72
        color = np.array(
            C.FOCUS_PEAK_COLOR_BGR.get(self._color, C.FOCUS_PEAK_COLOR_BGR[C.DEFAULT_FOCUS_PEAK_COLOR]),
            dtype=np.float32,
        ).reshape(1, 1, 3)
        sigma = max(0.5, 0.35 + float(self._thickness) * 0.45)
        soft = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (0, 0), sigma)[:, :, None]
        soft = np.clip(soft * max(0.35, float(self._thickness)), 0.0, 1.0)
        view = np.clip(base * (1.0 - soft) + color * soft, 0, 255).astype(np.uint8)

        pm = bgr_to_qpixmap(view, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_bgr is not None:
            self.update_focus(self._last_bgr)


class SquintView(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#111; border:1px solid #333; color:#AAA;")
        self._last_bgr: Optional[np.ndarray] = None
        self._mode = C.DEFAULT_SQUINT_MODE
        self._scale_percent = C.DEFAULT_SQUINT_SCALE_PERCENT
        self._blur_sigma = C.DEFAULT_SQUINT_BLUR_SIGMA

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    def sizeHint(self):
        return QSize(240, 240)

    def set_mode(self, mode: str):
        self._mode = safe_choice(mode, C.SQUINT_MODES, C.DEFAULT_SQUINT_MODE)
        if self._last_bgr is not None:
            self.update_squint(self._last_bgr)

    def set_scale_percent(self, value: int):
        self._scale_percent = clamp_int(value, C.SQUINT_SCALE_PERCENT_MIN, C.SQUINT_SCALE_PERCENT_MAX)
        if self._last_bgr is not None:
            self.update_squint(self._last_bgr)

    def set_blur_sigma(self, value: float):
        self._blur_sigma = max(C.SQUINT_BLUR_SIGMA_MIN, min(C.SQUINT_BLUR_SIGMA_MAX, float(value)))
        if self._last_bgr is not None:
            self.update_squint(self._last_bgr)

    def _apply_scale_up(self, bgr: np.ndarray) -> np.ndarray:
        ratio = max(C.SQUINT_SCALE_PERCENT_MIN, min(C.SQUINT_SCALE_PERCENT_MAX, int(self._scale_percent))) / 100.0
        if ratio >= 0.999:
            return bgr.copy()
        h, w = bgr.shape[:2]
        sw = max(1, int(round(w * ratio)))
        sh = max(1, int(round(h * ratio)))
        small = cv2.resize(bgr, (sw, sh), interpolation=cv2.INTER_AREA)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    def _apply_blur(self, bgr: np.ndarray) -> np.ndarray:
        sigma = max(C.SQUINT_BLUR_SIGMA_MIN, min(C.SQUINT_BLUR_SIGMA_MAX, float(self._blur_sigma)))
        if sigma <= 0.001:
            return bgr
        return cv2.GaussianBlur(bgr, (0, 0), sigmaX=sigma, sigmaY=sigma)

    def update_squint(self, bgr: np.ndarray):
        self._last_bgr = bgr
        if bgr.size == 0:
            self.setText("スクイントなし")
            return

        src = resize_by_long_edge(bgr, C.ANALYZER_MAX_DIM)
        mode = safe_choice(self._mode, C.SQUINT_MODES, C.DEFAULT_SQUINT_MODE)
        if mode == C.SQUINT_MODE_BLUR:
            view = self._apply_blur(src)
        elif mode == C.SQUINT_MODE_SCALE:
            view = self._apply_scale_up(src)
        else:
            view = self._apply_blur(self._apply_scale_up(src))

        pm = bgr_to_qpixmap(view, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_bgr is not None:
            self.update_squint(self._last_bgr)


class VectorScopeView(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#111; border:1px solid #333; color:#AAA;")
        self._last_bgr: Optional[np.ndarray] = None
        self._show_skin_tone_line = C.DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, C.VIEW_MIN_SIZE)

    def sizeHint(self):
        return QSize(240, 240)

    def set_show_skin_tone_line(self, enabled: bool):
        self._show_skin_tone_line = bool(enabled)
        if self._last_bgr is not None:
            self.update_scope(self._last_bgr)

    def _background(self, size: int) -> np.ndarray:
        bg = np.full((size, size, 3), 10, dtype=np.uint8)
        cx = (size - 1) // 2
        cy = (size - 1) // 2
        radius = max(8, int(round(size * 0.46)))
        cv2.rectangle(bg, (0, 0), (size - 1, size - 1), (26, 26, 26), 1, cv2.LINE_AA)
        for ratio in (0.25, 0.5, 0.75, 1.0):
            rr = max(1, int(round(radius * ratio)))
            cv2.circle(bg, (cx, cy), rr, (40, 40, 40), 1, cv2.LINE_AA)
        cv2.line(bg, (cx, 0), (cx, size - 1), (52, 52, 52), 1, cv2.LINE_AA)
        cv2.line(bg, (0, cy), (size - 1, cy), (52, 52, 52), 1, cv2.LINE_AA)
        cv2.circle(bg, (cx, cy), 1, (105, 105, 105), -1, cv2.LINE_AA)
        return bg

    def _draw_skin_tone_line(self, view: np.ndarray):
        if not self._show_skin_tone_line:
            return
        size = view.shape[0]
        cx = (size - 1) // 2
        cy = (size - 1) // 2
        radius = max(8, int(round(size * 0.46)))
        angle = math.radians(float(C.VECTORSCOPE_SKIN_LINE_ANGLE_DEG))
        r1 = int(round(radius * float(C.VECTORSCOPE_SKIN_LINE_INNER_RATIO)))
        r2 = int(round(radius * float(C.VECTORSCOPE_SKIN_LINE_OUTER_RATIO)))
        p1 = (
            int(round(cx + math.cos(angle) * r1)),
            int(round(cy - math.sin(angle) * r1)),
        )
        p2 = (
            int(round(cx + math.cos(angle) * r2)),
            int(round(cy - math.sin(angle) * r2)),
        )
        cv2.line(view, p1, p2, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.line(view, p1, p2, (20, 170, 255), 1, cv2.LINE_AA)

    def update_scope(self, bgr: np.ndarray):
        self._last_bgr = bgr
        if bgr.size == 0:
            self.setText("ベクトルスコープなし")
            return

        src = resize_by_long_edge(bgr, C.ANALYZER_MAX_DIM)
        yuv = cv2.cvtColor(src, cv2.COLOR_BGR2YUV)
        u = yuv[:, :, 1].astype(np.float32)
        v = yuv[:, :, 2].astype(np.float32)

        size = max(64, int(C.VECTORSCOPE_SIZE))
        scale = (size - 1) / 255.0
        xs = np.clip(np.round(u * scale), 0, size - 1).astype(np.int32)
        ys = np.clip(np.round((255.0 - v) * scale), 0, size - 1).astype(np.int32)

        hist = np.zeros((size, size), dtype=np.float32)
        np.add.at(hist, (ys.ravel(), xs.ravel()), 1.0)
        hist = cv2.GaussianBlur(hist, (0, 0), 0.8)
        density = _normalize_map(np.log1p(hist))

        heat_u8 = np.clip(np.round(density * 255.0), 0, 255).astype(np.uint8)
        colormap = cv2.COLORMAP_TURBO if hasattr(cv2, "COLORMAP_TURBO") else cv2.COLORMAP_JET
        heat = cv2.applyColorMap(heat_u8, colormap)
        base = self._background(size).astype(np.float32)
        alpha = np.clip(density[:, :, None] * 1.25, 0.0, 1.0)
        view = np.clip(base * (1.0 - alpha) + heat.astype(np.float32) * alpha, 0, 255).astype(np.uint8)
        self._draw_skin_tone_line(view)

        pm = bgr_to_qpixmap(view, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._last_bgr is not None:
            self.update_scope(self._last_bgr)


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
