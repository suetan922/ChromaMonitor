"""ビュー描画に関する処理。"""

import math
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..util import constants as C
from ..util.functions import clamp_int, clamp_render_size, safe_choice

_SCATTER_HUE_FILTER_HALF_WIDTH = 10
_MUNSELL_HUE_LABELS = (
    "2.5R",
    "5R",
    "7.5R",
    "10R",
    "2.5YR",
    "5YR",
    "7.5YR",
    "10YR",
    "2.5Y",
    "5Y",
    "7.5Y",
    "10Y",
    "2.5GY",
    "5GY",
    "7.5GY",
    "10GY",
    "2.5G",
    "5G",
    "7.5G",
    "10G",
    "2.5BG",
    "5BG",
    "7.5BG",
    "10BG",
    "2.5B",
    "5B",
    "7.5B",
    "10B",
    "2.5PB",
    "5PB",
    "7.5PB",
    "10PB",
    "2.5P",
    "5P",
    "7.5P",
    "10P",
    "2.5RP",
    "5RP",
    "7.5RP",
    "10RP",
)
_MUNSELL_COLORS_RGB = (
    (218, 43, 97),
    (227, 32, 55),
    (228, 31, 32),
    (233, 108, 28),
    (237, 148, 20),
    (242, 172, 0),
    (246, 194, 0),
    (247, 200, 0),
    (241, 211, 2),
    (240, 220, 0),
    (241, 224, 0),
    (222, 217, 1),
    (200, 214, 35),
    (167, 198, 56),
    (112, 180, 62),
    (43, 169, 58),
    (0, 157, 81),
    (0, 161, 103),
    (0, 161, 125),
    (0, 156, 142),
    (0, 152, 156),
    (0, 148, 163),
    (2, 137, 159),
    (2, 135, 165),
    (0, 122, 163),
    (0, 110, 174),
    (1, 94, 169),
    (0, 76, 157),
    (7, 62, 149),
    (35, 39, 137),
    (54, 39, 138),
    (72, 39, 130),
    (64, 40, 131),
    (81, 40, 132),
    (116, 39, 137),
    (151, 27, 134),
    (173, 37, 136),
    (195, 38, 133),
    (202, 38, 133),
    (222, 35, 105),
)
_WHEEL_HARMONY_GUIDE_RADIUS_RATIO = 0.82
_WHEEL_HARMONY_GUIDE_DOT_RADIUS = 3
_WHEEL_HARMONY_GUIDE_RING_COLOR = QColor(123, 144, 173, 92)
_WHEEL_HARMONY_GUIDE_SPOKE_COLOR = QColor(39, 89, 170, 120)
_WHEEL_HARMONY_GUIDE_SHAPE_COLOR = QColor(30, 92, 194, 212)
_WHEEL_HARMONY_GUIDE_DOT_COLOR = QColor(30, 92, 194, 236)

def _build_hue180_to_munsell40_weights() -> np.ndarray:
    src_bins = 180
    dst_bins = len(_MUNSELL_HUE_LABELS)
    src_step = 360.0 / float(src_bins)  # 2 deg
    dst_step = 360.0 / float(dst_bins)  # 9 deg

    weights = np.zeros((dst_bins, src_bins), dtype=np.float32)
    for src_idx in range(src_bins):
        src_start = src_idx * src_step
        src_end = src_start + src_step
        pos = src_start
        while pos < src_end - 1e-9:
            dst_idx = int(math.floor(pos / dst_step)) % dst_bins
            dst_end = (math.floor(pos / dst_step) + 1.0) * dst_step
            overlap = min(src_end, dst_end) - pos
            if overlap <= 0.0:
                break
            weights[dst_idx, src_idx] += float(overlap / src_step)
            pos += overlap

    col_sum = np.sum(weights, axis=0, keepdims=True)
    col_sum[col_sum <= 0.0] = 1.0
    return (weights / col_sum).astype(np.float32)


HUE180_TO_MUNSELL40_WEIGHTS = _build_hue180_to_munsell40_weights()


class ColorWheelWidget(QWidget):
    harmonyGuideRotationChanged = Signal(float)

    def __init__(self):
        super().__init__()
        # 最小幅のみ固定し、最小高はドック共通値で制御する。
        self.setMinimumWidth(C.VIEW_MIN_SIZE)
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._hist = np.zeros(180, dtype=np.float32)
        self._mode = C.DEFAULT_WHEEL_MODE
        self._base_ratio = 0.33
        self._min_thickness_ratio = 0.06
        self._guide_enabled = bool(C.DEFAULT_WHEEL_HARMONY_GUIDE_ENABLED)
        self._guide_type = safe_choice(
            C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE,
            C.WHEEL_HARMONY_GUIDE_TYPES,
            C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE,
        )
        self._guide_rotation_deg = 0.0
        self._guide_drag_active = False
        self._guide_drag_start_angle = 0.0
        self._guide_drag_start_rotation = 0.0

    def update_hist(self, hist: np.ndarray):
        # 受け取ったヒストグラムを描画向けに float32 化して保持する。
        self._hist = np.asarray(hist, dtype=np.float32)
        self.update()

    def set_mode(self, mode: str):
        self._mode = safe_choice(mode, C.WHEEL_MODES, C.DEFAULT_WHEEL_MODE)
        self.update()

    def set_harmony_guide_enabled(self, enabled: bool):
        self._guide_enabled = bool(enabled)
        self.update()

    def set_harmony_guide_type(self, guide_type: str):
        self._guide_type = safe_choice(
            guide_type,
            C.WHEEL_HARMONY_GUIDE_TYPES,
            C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE,
        )
        self.update()

    def set_harmony_guide_rotation(self, rotation_deg: float):
        normalized = self._normalize_rotation_deg(rotation_deg)
        if abs(normalized - float(self._guide_rotation_deg)) < 1e-6:
            return
        self._guide_rotation_deg = normalized
        self.harmonyGuideRotationChanged.emit(float(self._guide_rotation_deg))
        self.update()

    def harmony_guide_rotation(self) -> float:
        return float(self._guide_rotation_deg)

    def _munsell_hist(self) -> np.ndarray:
        # 180ビン色相を重み行列で 40 色相へ再サンプリングする。
        src = np.asarray(self._hist, dtype=np.float32)
        if src.size != 180:
            return np.zeros(len(_MUNSELL_HUE_LABELS), dtype=np.float32)
        return (HUE180_TO_MUNSELL40_WEIGHTS @ src).astype(np.float32)

    def _wheel_bins(self):
        # 表示モードに応じて「集計値」と「塗り色」を切り替える。
        mode = safe_choice(self._mode, C.WHEEL_MODES, C.DEFAULT_WHEEL_MODE)
        if mode == C.WHEEL_MODE_MUNSELL40:
            counts = self._munsell_hist()
            colors = [QColor(r, g, b, 255) for (r, g, b) in _MUNSELL_COLORS_RGB]
            return counts, colors

        counts = np.asarray(self._hist, dtype=np.float32)
        colors = []
        for h in range(180):
            hue_deg = int((h / 180.0) * 360.0)
            c = QColor()
            c.setHsv(hue_deg, 255, 255)
            colors.append(c)
        return counts, colors

    def _wheel_geometry(self) -> tuple[int, int, int, int]:
        rect = self.rect().adjusted(12, 12, -12, -12)
        cx, cy = rect.center().x(), rect.center().y()
        r = min(rect.width(), rect.height()) // 2
        inner_r = int(r * self._base_ratio)
        return cx, cy, r, inner_r

    @staticmethod
    def _normalize_signed_delta_deg(delta_deg: float) -> float:
        normalized = (float(delta_deg) + 180.0) % 360.0 - 180.0
        return normalized

    @staticmethod
    def _normalize_rotation_deg(rotation_deg: float) -> float:
        return (float(rotation_deg) + 180.0) % 360.0 - 180.0

    def _hue_offset_to_angle_deg(self, hue_deg: float) -> float:
        return (
            float(C.HUE_RED_REFERENCE_DEG)
            + float(self._guide_rotation_deg)
            + float(C.HUE_DIRECTION_SIGN) * float(hue_deg)
        ) % 360.0

    def _guide_points(self, cx: int, cy: int, inner_r: int) -> list[QPoint]:
        offsets = C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG.get(self._guide_type)
        if not offsets:
            return []
        guide_r = max(8, int(round(inner_r * _WHEEL_HARMONY_GUIDE_RADIUS_RATIO)))
        points = []
        for deg in offsets:
            angle = math.radians(self._hue_offset_to_angle_deg(deg))
            x = int(round(cx + math.cos(angle) * guide_r))
            y = int(round(cy - math.sin(angle) * guide_r))
            points.append(QPoint(x, y))
        return points

    def _draw_harmony_guide(self, painter: QPainter, cx: int, cy: int, inner_r: int) -> None:
        if not self._guide_enabled:
            return
        if self._guide_type == C.WHEEL_HARMONY_GUIDE_NONE:
            return
        points = self._guide_points(cx, cy, inner_r)
        if not points:
            return

        guide_r = max(8, int(round(inner_r * _WHEEL_HARMONY_GUIDE_RADIUS_RATIO)))
        painter.setPen(QPen(_WHEEL_HARMONY_GUIDE_RING_COLOR, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPoint(cx, cy), guide_r, guide_r)

        painter.setPen(QPen(_WHEEL_HARMONY_GUIDE_SPOKE_COLOR, 1))
        for pt in points:
            painter.drawLine(cx, cy, pt.x(), pt.y())

        painter.setPen(QPen(_WHEEL_HARMONY_GUIDE_SHAPE_COLOR, 2))
        if len(points) == 1:
            painter.drawLine(cx, cy, points[0].x(), points[0].y())
        elif len(points) == 2:
            painter.drawLine(points[0], points[1])
        else:
            sorted_points = sorted(
                points,
                key=lambda pt: (math.atan2(cy - pt.y(), pt.x() - cx) + math.tau) % math.tau,
            )
            for i in range(len(sorted_points)):
                painter.drawLine(sorted_points[i], sorted_points[(i + 1) % len(sorted_points)])

        painter.setPen(Qt.NoPen)
        painter.setBrush(_WHEEL_HARMONY_GUIDE_DOT_COLOR)
        for pt in points:
            painter.drawEllipse(pt, _WHEEL_HARMONY_GUIDE_DOT_RADIUS, _WHEEL_HARMONY_GUIDE_DOT_RADIUS)

    @staticmethod
    def _point_angle_deg(px: int, py: int, cx: int, cy: int) -> float:
        # 画面座標(下向き+Y)を数学座標へ変換して角度化する。
        return math.degrees(math.atan2(float(cy - py), float(px - cx))) % 360.0

    def _is_guide_drag_enabled(self) -> bool:
        return bool(
            self._guide_enabled
            and self._guide_type != C.WHEEL_HARMONY_GUIDE_NONE
            and self._guide_type in C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_guide_drag_enabled():
            cx, cy, _r, inner_r = self._wheel_geometry()
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            dx = int(pos.x()) - int(cx)
            dy = int(pos.y()) - int(cy)
            if dx * dx + dy * dy <= int(inner_r * inner_r):
                self._guide_drag_active = True
                self._guide_drag_start_angle = self._point_angle_deg(pos.x(), pos.y(), cx, cy)
                self._guide_drag_start_rotation = float(self._guide_rotation_deg)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._guide_drag_active:
            cx, cy, _r, _inner_r = self._wheel_geometry()
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            current_angle = self._point_angle_deg(pos.x(), pos.y(), cx, cy)
            delta = self._normalize_signed_delta_deg(current_angle - self._guide_drag_start_angle)
            self.set_harmony_guide_rotation(self._guide_drag_start_rotation + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._guide_drag_active:
            self._guide_drag_active = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, _):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.fillRect(self.rect(), QColor(255, 255, 255, 255))

            cx, cy, r, inner_r = self._wheel_geometry()

            p.setPen(Qt.NoPen)
            # 黄色系でも輪郭が埋もれにくいよう、土台グレーを少し暗くする。
            p.setBrush(QColor(220, 220, 220, 255))
            p.drawEllipse(QPoint(cx, cy), r, r)

            p.setBrush(QColor(255, 255, 255, 255))
            p.drawEllipse(QPoint(cx, cy), inner_r, inner_r)

            ring_max = r - inner_r
            if ring_max <= 2:
                return

            # ヒストグラム風のリング帯を扇形で描画する。
            # まず全色相の薄いベースリングを描き、その上に実測分のみ重ねる。
            base_thickness = max(2, int(round(ring_max * self._min_thickness_ratio)))
            counts, colors = self._wheel_bins()
            n_bins = max(1, int(len(counts)))
            step_deg = 360.0 / float(n_bins)
            overlap_deg = 0.0
            local_max = float(np.max(counts)) if counts.size else 0.0
            if local_max <= 0.0:
                local_max = 1.0

            # 色相分布の有無に関わらず、全色相の位置を把握できるよう薄い基準リングを残す。
            base_outer_r = inner_r + base_thickness
            for h in range(n_bins):
                c = QColor(colors[h])
                c.setAlpha(32)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                center_deg = (
                    float(C.HUE_RED_REFERENCE_DEG)
                    + float(C.HUE_DIRECTION_SIGN) * (h * step_deg)
                ) % 360.0
                start_deg = center_deg - (step_deg / 2.0) - overlap_deg
                span_deg = step_deg + overlap_deg * 2.0
                p.drawPie(
                    int(cx - base_outer_r),
                    int(cy - base_outer_r),
                    int(base_outer_r * 2),
                    int(base_outer_r * 2),
                    int(start_deg * 16),
                    int(span_deg * 16),
                )
                p.setBrush(QColor(255, 255, 255, 255))
                p.drawPie(
                    int(cx - inner_r),
                    int(cy - inner_r),
                    int(inner_r * 2),
                    int(inner_r * 2),
                    int(start_deg * 16),
                    int(span_deg * 16),
                )

            for h in range(n_bins):
                count = float(counts[h])
                if count <= 0.0:
                    continue
                norm = min(1.0, count / local_max)
                thickness_ratio = (
                    self._min_thickness_ratio + (1.0 - self._min_thickness_ratio) * norm
                )
                thickness = max(base_thickness, int(round(ring_max * thickness_ratio)))
                outer_r = inner_r + thickness
                c = QColor(colors[h])
                c.setAlpha(225)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                center_deg = (
                    float(C.HUE_RED_REFERENCE_DEG)
                    + float(C.HUE_DIRECTION_SIGN) * (h * step_deg)
                ) % 360.0
                start_deg = center_deg - (step_deg / 2.0) - overlap_deg
                span_deg = step_deg + overlap_deg * 2.0
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
            self._draw_harmony_guide(p, cx, cy, inner_r)
        finally:
            p.end()


class ScatterRasterWidget(QLabel):

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        # 最小幅のみ固定し、最小高はドック共通値で制御する。
        self.setMinimumWidth(C.VIEW_MIN_SIZE)
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#FFFFFF; border:none; color:#222;")
        self._square_limit = True
        self._last_sv: Optional[np.ndarray] = None
        self._last_rgb: Optional[np.ndarray] = None
        self._shape = C.SCATTER_SHAPE_SQUARE
        self._render_mode = C.DEFAULT_SCATTER_RENDER_MODE
        self._hue_filter_enabled = bool(C.DEFAULT_SCATTER_HUE_FILTER_ENABLED)
        self._hue_center = clamp_int(
            C.DEFAULT_SCATTER_HUE_CENTER, C.SCATTER_HUE_MIN, C.SCATTER_HUE_MAX
        )
        self._show_scatter_frame_only()

    def set_shape(self, shape: str):
        # 不正値は四角モードへ寄せる。
        self._shape = (
            C.SCATTER_SHAPE_TRIANGLE
            if shape == C.SCATTER_SHAPE_TRIANGLE
            else C.SCATTER_SHAPE_SQUARE
        )
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
        else:
            self._show_scatter_frame_only()

    def set_render_mode(self, mode: str):
        self._render_mode = safe_choice(
            mode,
            C.SCATTER_RENDER_MODES,
            C.DEFAULT_SCATTER_RENDER_MODE,
        )
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
        else:
            self._show_scatter_frame_only()

    def set_hue_filter(self, enabled: bool, center: int):
        # フィルター条件変更は直近データを再描画して即時反映する。
        self._hue_filter_enabled = bool(enabled)
        self._hue_center = clamp_int(center, C.SCATTER_HUE_MIN, C.SCATTER_HUE_MAX)
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
        else:
            self._show_scatter_frame_only()

    def minimumSizeHint(self):
        return QSize(C.VIEW_MIN_SIZE, 0)

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
            if self._shape == C.SCATTER_SHAPE_TRIANGLE:
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
        # NumPy(RGBA) -> QPixmap 変換と表示サイズへのスケーリングを行う。
        img = np.flipud(img).copy()
        qimg = QImage(img.data, 256, 256, 256 * 4, QImage.Format_RGBA8888).copy()
        base_side = (
            min(self.width(), self.height())
            if self._square_limit
            else max(self.width(), self.height())
        )
        target_side, _ = clamp_render_size(base_side, base_side)
        pm = QPixmap.fromImage(qimg).scaled(
            target_side, target_side, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        if pm.isNull():
            return None
        self._draw_scatter_frame(pm)
        return pm

    def _show_scatter_frame_only(self):
        # 入力データが無いときは枠だけ描画して待機状態を示す。
        img = np.zeros((256, 256, 4), dtype=np.uint8)
        pm = self._make_scatter_pixmap(img)
        if pm is not None:
            self.setText("")
            self.setPixmap(pm)
        else:
            self.setText("散布図（S-V）")

    def _compute_scatter_xy(self, sv_arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        # sv_arr は [S, V] の2列を想定（0..255）。
        s = np.clip(sv_arr[:, 0].astype(np.int32), 0, 255)
        v = np.clip(sv_arr[:, 1].astype(np.int32), 0, 255)
        if self._shape == C.SCATTER_SHAPE_TRIANGLE:
            # 右向きHSV三角: 左上=白, 左下=黒, 右中=純色
            prod = s * v
            x = np.clip(prod // 255, 0, 255).astype(np.int32)
            y = np.clip(v - (prod // 510), 0, 255).astype(np.int32)
            return x, y
        return s, v

    def _extract_hue_from_rgb(self, rgb_u8: np.ndarray) -> np.ndarray:
        # Hue情報が無い入力形式向けに RGB から Hue を逆算する。
        if rgb_u8.size == 0:
            return np.empty((0,), dtype=np.int16)
        bgr = rgb_u8[:, ::-1].reshape((-1, 1, 3))
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        return hsv[:, 0, 0].astype(np.int16, copy=False)

    def _apply_hue_filter_mask(self, h_arr: np.ndarray) -> np.ndarray:
        # Hue円環の距離（0/179またぎを含む最短距離）で判定する。
        if h_arr.size == 0:
            return np.zeros((0,), dtype=bool)
        center = int(self._hue_center)
        diff = np.abs(h_arr.astype(np.int16, copy=False) - center)
        wrap = 180 - diff
        dist = np.minimum(diff, wrap)
        return dist <= int(_SCATTER_HUE_FILTER_HALF_WIDTH)

    def _render_scatter_dominant(
        self, x: np.ndarray, y: np.ndarray, rgb_u8: np.ndarray
    ) -> np.ndarray:
        # 同一セルに複数色が重なる場合は「最頻色（同数なら後勝ち）」を採用する。
        out = np.zeros((256 * 256, 4), dtype=np.uint8)
        if x.size == 0 or y.size == 0 or rgb_u8.size == 0:
            return out.reshape((256, 256, 4))

        flat_chunks = []
        rgb_chunks = []
        for dy in (0, 1):
            yy = np.clip(y + dy, 0, 255)
            for dx in (0, 1):
                xx = np.clip(x + dx, 0, 255)
                flat_chunks.append((yy << 8) + xx)
                rgb_chunks.append(rgb_u8)

        flat_idx = np.concatenate(flat_chunks, axis=0).astype(np.uint32, copy=False)
        rgb_rep = np.concatenate(rgb_chunks, axis=0).astype(np.uint8, copy=False)
        color_key = (
            (rgb_rep[:, 0].astype(np.uint32) << 16)
            | (rgb_rep[:, 1].astype(np.uint32) << 8)
            | rgb_rep[:, 2].astype(np.uint32)
        )
        pair_key = (flat_idx.astype(np.uint64) << 24) | color_key.astype(np.uint64)
        if pair_key.size == 0:
            return out.reshape((256, 256, 4))

        order = np.argsort(pair_key, kind="mergesort")
        pair_sorted = pair_key[order]
        run_start = np.concatenate(
            ([0], np.flatnonzero(np.diff(pair_sorted) != 0).astype(np.int64) + 1)
        )
        run_end = np.concatenate((run_start[1:], [pair_sorted.size]))
        pair_unique = pair_sorted[run_start]
        run_counts = (run_end - run_start).astype(np.int32, copy=False)
        run_last_pos = order[run_end - 1]

        pixel_idx = (pair_unique >> 24).astype(np.int32, copy=False)
        color_unique = (pair_unique & 0xFFFFFF).astype(np.uint32, copy=False)
        pix_start = np.concatenate(
            ([0], np.flatnonzero(np.diff(pixel_idx) != 0).astype(np.int64) + 1)
        )
        pix_end = np.concatenate((pix_start[1:], [pixel_idx.size]))

        for ps, pe in zip(pix_start, pix_end):
            seg_counts = run_counts[ps:pe]
            if seg_counts.size == 0:
                continue
            best_count = int(seg_counts.max())
            tied_rel = np.flatnonzero(seg_counts == best_count)
            if tied_rel.size == 1:
                best = ps + int(tied_rel[0])
            else:
                seg_last = run_last_pos[ps:pe]
                best = ps + int(tied_rel[np.argmax(seg_last[tied_rel])])

            dst = int(pixel_idx[best])
            color = int(color_unique[best])
            out[dst, 0] = (color >> 16) & 0xFF
            out[dst, 1] = (color >> 8) & 0xFF
            out[dst, 2] = color & 0xFF
            out[dst, 3] = 255
        return out.reshape((256, 256, 4))

    def _render_scatter_heatmap(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        out = np.zeros((256, 256, 4), dtype=np.uint8)
        if x.size == 0 or y.size == 0:
            return out

        # 4近傍の重み付けは flat index をまとめて作って bincount で一括集計する。
        flat_chunks = []
        for dy in (0, 1):
            yy = np.clip(y + dy, 0, 255)
            for dx in (0, 1):
                xx = np.clip(x + dx, 0, 255)
                flat_chunks.append((yy << 8) + xx)
        flat_idx = np.concatenate(flat_chunks, axis=0).astype(np.int32, copy=False)
        density = np.bincount(flat_idx, minlength=256 * 256).astype(np.float32, copy=False)

        density_img = density.reshape((256, 256))
        if float(density_img.max()) <= 0.0:
            return out

        # 密度むらを見やすくするため、軽く平滑化して対数圧縮する。
        smooth = cv2.GaussianBlur(density_img, (0, 0), sigmaX=1.2, sigmaY=1.2)
        tone = np.log1p(smooth)
        peak = float(tone.max())
        if peak <= 0.0:
            return out
        norm = np.clip(tone / peak, 0.0, 1.0)
        gray = np.clip(norm * 255.0, 0.0, 255.0).astype(np.uint8)
        cmap = getattr(cv2, "COLORMAP_TURBO", cv2.COLORMAP_JET)
        heat_bgr = cv2.applyColorMap(gray, cmap)

        out[:, :, 0:3] = heat_bgr[:, :, ::-1]
        alpha = np.clip(np.power(norm, 0.55) * 255.0, 0.0, 255.0).astype(np.uint8)
        alpha[norm < 0.02] = 0
        out[:, :, 3] = alpha
        return out

    def update_scatter(self, sv: np.ndarray, rgb: np.ndarray):
        self._last_sv = sv
        self._last_rgb = rgb
        if sv is None or rgb is None or sv.size == 0 or rgb.size == 0:
            self._show_scatter_frame_only()
            return

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

            rgb_view = rgb_arr[:n, :3]
            if rgb_view.dtype == np.uint8:
                rgb_u8 = np.ascontiguousarray(rgb_view)
            else:
                rgb_u8 = np.clip(rgb_view, 0, 255).astype(np.uint8, copy=False)
            if sv_arr.shape[1] >= 3:
                # [H,S,V] 形式なら Hue を直接利用する。
                h_arr = np.clip(
                    sv_arr[:n, 0].astype(np.int16),
                    C.SCATTER_HUE_MIN,
                    C.SCATTER_HUE_MAX,
                )
                sv_used = sv_arr[:n, 1:3]
            else:
                # [S,V] 形式なら必要時のみ RGB から Hue を復元する。
                h_arr = self._extract_hue_from_rgb(rgb_u8) if self._hue_filter_enabled else None
                sv_used = sv_arr[:n, :2]

            if self._hue_filter_enabled:
                if h_arr is None or h_arr.size == 0:
                    self._show_scatter_frame_only()
                    return
                keep = self._apply_hue_filter_mask(h_arr)
                if not np.any(keep):
                    self._show_scatter_frame_only()
                    return
                sv_used = sv_used[keep]
                rgb_u8 = rgb_u8[keep]
                if sv_used.size == 0 or rgb_u8.size == 0:
                    self._show_scatter_frame_only()
                    return

            x, y = self._compute_scatter_xy(sv_used)
            render_mode = safe_choice(
                self._render_mode,
                C.SCATTER_RENDER_MODES,
                C.DEFAULT_SCATTER_RENDER_MODE,
            )
            if render_mode == C.SCATTER_RENDER_MODE_HEATMAP:
                img = self._render_scatter_heatmap(x, y)
            else:
                img = self._render_scatter_dominant(x, y, rgb_u8)
        except Exception:
            # 描画エラー時は四角モードへフォールバックして継続
            self._shape = C.SCATTER_SHAPE_SQUARE
            self._render_mode = C.SCATTER_RENDER_MODE_DOMINANT
            try:
                sv_arr = np.asarray(sv)
                rgb_arr = np.asarray(rgb)
                n = min(int(sv_arr.shape[0]), int(rgb_arr.shape[0]))
                if n <= 0:
                    self._show_scatter_frame_only()
                    return
                if sv_arr.ndim != 2 or sv_arr.shape[1] < 2:
                    self._show_scatter_frame_only()
                    return
                sv_used = sv_arr[:n, 1:3] if sv_arr.shape[1] >= 3 else sv_arr[:n, :2]
                rgb_view = rgb_arr[:n, :3]
                if rgb_view.dtype == np.uint8:
                    rgb_u8 = np.ascontiguousarray(rgb_view)
                else:
                    rgb_u8 = np.clip(rgb_view, 0, 255).astype(np.uint8, copy=False)
                x, y = self._compute_scatter_xy(sv_used)
                img = self._render_scatter_dominant(x, y, rgb_u8)
            except Exception:
                self._show_scatter_frame_only()
                return

        pm = self._make_scatter_pixmap(img)
        if pm is None:
            self._show_scatter_frame_only()
            return

        self.setText("")
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size() == event.oldSize():
            return
        if not self.isVisible() or self.isHidden():
            return
        if self.width() <= 1 or self.height() <= 1:
            return
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
        else:
            self._show_scatter_frame_only()
