"""色相環とS-V散布図の表示ビュー。"""

import math
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..util import constants as C
from ..util.image_ops import clamp_render_size
from ..util.value_utils import clamp_int, safe_choice

_SCATTER_HUE_FILTER_HALF_WIDTH = 10
_SCATTER_RESIZE_RECALC_DEBOUNCE_MS = 160
_SCATTER_RESIZE_TRANSFORM_MODE = Qt.FastTransformation
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
_WHEEL_THICKNESS_MODE_ABSOLUTE = "absolute"
_WHEEL_THICKNESS_MODE_RELATIVE_MAX = "relative_max"
# 色相環の太さ計算方式:
# - absolute: 各色相の絶対比率（count / total）で太さを決める
# - relative_max: 最大ビン基準（count / local_max）で太さを決める（既定）
_WHEEL_THICKNESS_MODE = _WHEEL_THICKNESS_MODE_RELATIVE_MAX

def _build_hue180_to_munsell40_weights() -> np.ndarray:
    """HSV180ビンをマンセル40色相へ再配分する重み行列を作る。"""
    src_bins = 180
    dst_bins = len(_MUNSELL_HUE_LABELS)
    src_step = 360.0 / float(src_bins)  # 2度
    dst_step = 360.0 / float(dst_bins)  # 9度

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
_MUNSELL_COLORS_Q = tuple(QColor(r, g, b, 255) for (r, g, b) in _MUNSELL_COLORS_RGB)
_HSV180_COLORS_Q = tuple(
    QColor.fromHsv(int((h / 180.0) * 360.0), 255, 255) for h in range(180)
)


class ColorWheelWidget(QWidget):
    """色相分布をリング状に可視化する色相環ウィジェット。"""
    harmonyGuideRotationChanged = Signal(float)

    def __init__(self):
        """色相環表示と色彩調和ガイド状態を初期化する。"""
        super().__init__()
        # 最小幅のみ固定し、最小高はドック共通値で制御する。
        self.setMinimumWidth(C.VIEW_MIN_WIDTH)
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
        """色相ヒストグラムを更新して再描画する。"""
        # 受け取ったヒストグラムを描画向けに float32 化して保持する。
        next_hist = np.asarray(hist, dtype=np.float32)
        if self._hist.shape == next_hist.shape and np.array_equal(self._hist, next_hist):
            return
        self._hist = next_hist
        self.update()

    def set_mode(self, mode: str):
        """色相環の表示方式を更新する。"""
        normalized = safe_choice(mode, C.WHEEL_MODES, C.DEFAULT_WHEEL_MODE)
        if self._mode == normalized:
            return
        self._mode = normalized
        self.update()

    def set_harmony_guide_enabled(self, enabled: bool):
        """色彩調和ガイド表示の有効/無効を切り替える。"""
        next_enabled = bool(enabled)
        if self._guide_enabled == next_enabled:
            return
        self._guide_enabled = next_enabled
        self.update()

    def set_harmony_guide_type(self, guide_type: str):
        """色彩調和ガイド種別を更新する。"""
        normalized = safe_choice(
            guide_type,
            C.WHEEL_HARMONY_GUIDE_TYPES,
            C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE,
        )
        if self._guide_type == normalized:
            return
        self._guide_type = normalized
        self.update()

    def set_harmony_guide_rotation(self, rotation_deg: float):
        """色彩調和ガイドの回転角を設定する。"""
        normalized = self._normalize_rotation_deg(rotation_deg)
        if abs(normalized - float(self._guide_rotation_deg)) < 1e-6:
            return
        self._guide_rotation_deg = normalized
        self.harmonyGuideRotationChanged.emit(float(self._guide_rotation_deg))
        self.update()

    def harmony_guide_rotation(self) -> float:
        """現在の色彩調和ガイド回転角を返す。"""
        return float(self._guide_rotation_deg)

    def _munsell_hist(self) -> np.ndarray:
        """HSV180ビンからマンセル40色相の集計値を返す。"""
        # 180ビン色相を重み行列で 40 色相へ再サンプリングする。
        src = np.asarray(self._hist, dtype=np.float32)
        if src.size != 180:
            return np.zeros(len(_MUNSELL_HUE_LABELS), dtype=np.float32)
        return (HUE180_TO_MUNSELL40_WEIGHTS @ src).astype(np.float32)

    def _wheel_bins(self):
        """現在モードで描画に使うビン値と色配列を返す。"""
        # 表示モードに応じて「集計値」と「塗り色」を切り替える。
        mode = safe_choice(self._mode, C.WHEEL_MODES, C.DEFAULT_WHEEL_MODE)
        if mode == C.WHEEL_MODE_MUNSELL40:
            counts = self._munsell_hist()
            return counts, _MUNSELL_COLORS_Q

        counts = np.asarray(self._hist, dtype=np.float32)
        return counts, _HSV180_COLORS_Q

    def _wheel_geometry(self) -> tuple[int, int, int, int]:
        """色相環描画の中心座標と半径情報を返す。"""
        rect = self.rect().adjusted(12, 12, -12, -12)
        cx, cy = rect.center().x(), rect.center().y()
        r = min(rect.width(), rect.height()) // 2
        inner_r = int(r * self._base_ratio)
        return cx, cy, r, inner_r

    @staticmethod
    def _thickness_norm(count: float, *, local_max: float, total_count: float) -> float:
        """色相ビン値をリング太さ比率(0..1)へ正規化する。"""
        mode = safe_choice(
            _WHEEL_THICKNESS_MODE,
            (_WHEEL_THICKNESS_MODE_ABSOLUTE, _WHEEL_THICKNESS_MODE_RELATIVE_MAX),
            _WHEEL_THICKNESS_MODE_ABSOLUTE,
        )
        if mode == _WHEEL_THICKNESS_MODE_RELATIVE_MAX:
            denom = max(1.0, float(local_max))
            return max(0.0, min(1.0, float(count) / denom))
        denom = max(1.0, float(total_count))
        return max(0.0, min(1.0, float(count) / denom))

    @staticmethod
    def _normalize_signed_delta_deg(delta_deg: float) -> float:
        """角度差を -180..180 の範囲へ正規化する。"""
        normalized = (float(delta_deg) + 180.0) % 360.0 - 180.0
        return normalized

    @staticmethod
    def _normalize_rotation_deg(rotation_deg: float) -> float:
        """回転角を -180..180 の範囲へ正規化する。"""
        return (float(rotation_deg) + 180.0) % 360.0 - 180.0

    def _hue_offset_to_angle_deg(self, hue_deg: float) -> float:
        """色相オフセットを画面上の絶対角度へ変換する。"""
        return (
            float(C.HUE_RED_REFERENCE_DEG)
            + float(self._guide_rotation_deg)
            + float(C.HUE_DIRECTION_SIGN) * float(hue_deg)
        ) % 360.0

    def _guide_points(self, cx: int, cy: int, inner_r: int) -> list[QPoint]:
        """現在ガイド種別に対応する頂点座標群を返す。"""
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
        """色彩調和ガイドのリング・線・頂点を描画する。"""
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
        """中心基準の点座標から角度(度)を算出する。"""
        # 画面座標(下向き+Y)を数学座標へ変換して角度化する。
        return math.degrees(math.atan2(float(cy - py), float(px - cx))) % 360.0

    def _is_guide_drag_enabled(self) -> bool:
        """ガイド回転ドラッグが有効かを返す。"""
        return bool(
            self._guide_enabled
            and self._guide_type != C.WHEEL_HARMONY_GUIDE_NONE
            and self._guide_type in C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG
        )

    def mousePressEvent(self, event):
        """内周クリック時はガイド回転ドラッグを開始する。"""
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
        """ガイド回転ドラッグ中の角度更新を行う。"""
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
        """ガイド回転ドラッグを終了する。"""
        if event.button() == Qt.LeftButton and self._guide_drag_active:
            self._guide_drag_active = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, _):
        """色相環本体と色彩調和ガイドを描画する。"""
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
            total_count = float(np.sum(counts)) if counts.size else 0.0
            if total_count <= 0.0:
                total_count = 1.0

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
                norm = self._thickness_norm(
                    count,
                    local_max=local_max,
                    total_count=total_count,
                )
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
    """S-V散布図をラスター描画するウィジェット。"""

    def __init__(self):
        """散布図表示状態と再描画用キャッシュを初期化する。"""
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        # 最小幅のみ固定し、最小高はドック共通値で制御する。
        self.setMinimumWidth(C.VIEW_MIN_WIDTH)
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#FFFFFF; border:none; color:#222;")
        self._square_limit = True
        self._last_sv: Optional[np.ndarray] = None
        self._last_rgb: Optional[np.ndarray] = None
        self._scatter_base_pm: Optional[QPixmap] = None
        self._resize_recalc_timer = QTimer(self)
        self._resize_recalc_timer.setSingleShot(True)
        self._resize_recalc_timer.setInterval(_SCATTER_RESIZE_RECALC_DEBOUNCE_MS)
        self._resize_recalc_timer.timeout.connect(self._rerender_after_resize_idle)
        self._shape = C.SCATTER_SHAPE_SQUARE
        self._render_mode = C.DEFAULT_SCATTER_RENDER_MODE
        self._hue_filter_enabled = bool(C.DEFAULT_SCATTER_HUE_FILTER_ENABLED)
        self._hue_center = clamp_int(
            C.DEFAULT_SCATTER_HUE_CENTER, C.SCATTER_HUE_MIN, C.SCATTER_HUE_MAX
        )
        self._show_scatter_frame_only()

    def set_shape(self, shape: str):
        """散布図の表示形状(四角/三角)を切り替える。"""
        # 不正値は四角モードへ寄せる。
        next_shape = (
            C.SCATTER_SHAPE_TRIANGLE
            if shape == C.SCATTER_SHAPE_TRIANGLE
            else C.SCATTER_SHAPE_SQUARE
        )
        if self._shape == next_shape:
            return
        self._shape = next_shape
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
        else:
            self._show_scatter_frame_only()

    def set_render_mode(self, mode: str):
        """散布図の描画方式(代表色/ヒートマップ)を切り替える。"""
        normalized = safe_choice(
            mode,
            C.SCATTER_RENDER_MODES,
            C.DEFAULT_SCATTER_RENDER_MODE,
        )
        if self._render_mode == normalized:
            return
        self._render_mode = normalized
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
        else:
            self._show_scatter_frame_only()

    def set_hue_filter(self, enabled: bool, center: int):
        """色相フィルターの有効状態と中心色相を更新する。"""
        # フィルター条件変更は直近データを再描画して即時反映する。
        next_enabled = bool(enabled)
        next_center = clamp_int(center, C.SCATTER_HUE_MIN, C.SCATTER_HUE_MAX)
        if self._hue_filter_enabled == next_enabled and self._hue_center == next_center:
            return
        self._hue_filter_enabled = next_enabled
        self._hue_center = next_center
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
        else:
            self._show_scatter_frame_only()

    def minimumSizeHint(self):
        """散布図ビューの最小サイズヒントを返す。"""
        return QSize(C.VIEW_MIN_WIDTH, 0)

    def sizeHint(self):
        """散布図ビューの標準サイズヒントを返す。"""
        return QSize(300, 300)

    def _draw_scatter_frame(self, pm: QPixmap):
        """散布図の外枠ガイドをPixmap上へ描画する。"""
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

    def _cache_scatter_base_pixmap(self, img: np.ndarray) -> bool:
        """散布図ベース画像をQPixmap化してキャッシュする。"""
        # 点群計算結果(256x256 RGBA)をQPixmap化して保持する。
        img = np.flipud(img).copy()
        qimg = QImage(img.data, 256, 256, 256 * 4, QImage.Format_RGBA8888).copy()
        pm = QPixmap.fromImage(qimg)
        if pm.isNull():
            self._scatter_base_pm = None
            return False
        self._scatter_base_pm = pm
        return True

    def _present_scatter_from_base(self, *, smooth: bool = True) -> bool:
        """キャッシュ済み散布図を現在サイズへスケール表示する。"""
        # 保持済みのベース画像を表示サイズへスケールして描画する。
        base_pm = self._scatter_base_pm
        if base_pm is None or base_pm.isNull():
            return False
        base_side = (
            min(self.width(), self.height())
            if self._square_limit
            else max(self.width(), self.height())
        )
        target_side, _ = clamp_render_size(base_side, base_side)
        transform_mode = Qt.SmoothTransformation if smooth else _SCATTER_RESIZE_TRANSFORM_MODE
        pm = base_pm.scaled(target_side, target_side, Qt.KeepAspectRatio, transform_mode)
        if pm.isNull():
            return False
        self._draw_scatter_frame(pm)
        self.setText("")
        self.setPixmap(pm)
        return True

    def _show_scatter_frame_only(self):
        """データ未入力時の空フレーム表示へ切り替える。"""
        # 入力データが無いときは枠だけ描画して待機状態を示す。
        img = np.zeros((256, 256, 4), dtype=np.uint8)
        if not self._cache_scatter_base_pixmap(img) or not self._present_scatter_from_base():
            self.setText("散布図（S-V）")

    def _rerender_after_resize_idle(self):
        """リサイズ停止後に高品質再描画へ戻す。"""
        # リサイズ停止後に1回だけ通常描画へ戻す。
        if not self.isVisible() or self.isHidden():
            return
        if self.width() <= 1 or self.height() <= 1:
            return
        # 散布図のベース画像(256x256)はサイズ非依存なので、まずは再計算せず高品質リスケールだけ行う。
        if self._present_scatter_from_base(smooth=True):
            return
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)

    def _compute_scatter_xy(self, sv_arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """S/V配列を散布図座標(x,y)へ変換する。"""
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

    @staticmethod
    def _to_rgb_u8(rgb_arr: np.ndarray, n: int) -> np.ndarray:
        """RGB配列を先頭n件のuint8連続配列へ正規化する。"""
        rgb_view = rgb_arr[:n, :3]
        if rgb_view.dtype == np.uint8:
            return np.ascontiguousarray(rgb_view)
        return np.clip(rgb_view, 0, 255).astype(np.uint8, copy=False)

    @staticmethod
    def _four_neighborhood_flat_indices(
        x: np.ndarray,
        y: np.ndarray,
        *,
        triangle_mode: bool = False,
        dtype: np.dtype = np.int32,
    ) -> np.ndarray:
        """(x, y) の4近傍セルを 256x256 画像のflat indexで返す。"""
        n = int(x.size)
        if n <= 0:
            return np.empty((0,), dtype=dtype)
        xx0 = np.clip(x, 0, 255)
        xx1 = np.clip(x + 1, 0, 255)
        yy0 = np.clip(y, 0, 255)
        yy1 = np.clip(y + 1, 0, 255)

        if triangle_mode:
            # 三角モードでは各近傍点を三角形内へ投影して、外側へのはみ出しを防ぐ。
            y0f = yy0.astype(np.float32)
            y1f = yy1.astype(np.float32)
            x_max0 = np.where(
                yy0 <= 128,
                y0f * (255.0 / 128.0),
                (255.0 - y0f) * (255.0 / 127.0),
            )
            x_max1 = np.where(
                yy1 <= 128,
                y1f * (255.0 / 128.0),
                (255.0 - y1f) * (255.0 / 127.0),
            )
            x_max0_i = np.clip(np.floor(x_max0).astype(np.int32), 0, 255)
            x_max1_i = np.clip(np.floor(x_max1).astype(np.int32), 0, 255)
            xx0_y0 = np.minimum(xx0, x_max0_i)
            xx1_y0 = np.minimum(xx1, x_max0_i)
            xx0_y1 = np.minimum(xx0, x_max1_i)
            xx1_y1 = np.minimum(xx1, x_max1_i)
        else:
            xx0_y0 = xx0
            xx1_y0 = xx1
            xx0_y1 = xx0
            xx1_y1 = xx1

        out = np.empty((n * 4,), dtype=np.int32)
        out[0:n] = (yy0 << 8) + xx0_y0
        out[n : 2 * n] = (yy0 << 8) + xx1_y0
        out[2 * n : 3 * n] = (yy1 << 8) + xx0_y1
        out[3 * n : 4 * n] = (yy1 << 8) + xx1_y1
        return out.astype(dtype, copy=False)

    def _extract_hue_from_rgb(self, rgb_u8: np.ndarray) -> np.ndarray:
        """RGB配列から色相(H)を推定して返す。"""
        # 色相情報が無い入力形式向けに RGB から色相を推定する。
        if rgb_u8.size == 0:
            return np.empty((0,), dtype=np.int16)
        bgr = rgb_u8[:, ::-1].reshape((-1, 1, 3))
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        return hsv[:, 0, 0].astype(np.int16, copy=False)

    def _apply_hue_filter_mask(self, h_arr: np.ndarray) -> np.ndarray:
        """中心色相からの円環距離でフィルターマスクを生成する。"""
        # 色相円環の距離（0/179またぎを含む最短距離）で判定する。
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
        """同一セルの最頻色で散布図ラスタを生成する。"""
        # 同一セルに複数色が重なる場合は「最頻色（同数なら後勝ち）」を採用する。
        out = np.zeros((256 * 256, 4), dtype=np.uint8)
        if x.size == 0 or y.size == 0 or rgb_u8.size == 0:
            return out.reshape((256, 256, 4))

        flat_idx = self._four_neighborhood_flat_indices(
            x,
            y,
            triangle_mode=(self._shape == C.SCATTER_SHAPE_TRIANGLE),
            dtype=np.uint32,
        )
        # RGBチャンネルを4倍複製する代わりに、color_keyのみを複製してコピー量を抑える。
        color_key_base = (
            (rgb_u8[:, 0].astype(np.uint32) << 16)
            | (rgb_u8[:, 1].astype(np.uint32) << 8)
            | rgb_u8[:, 2].astype(np.uint32)
        )
        color_key = np.tile(color_key_base, 4)
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
        if pixel_idx.size <= 0:
            return out.reshape((256, 256, 4))

        # 「最頻色（同数は後勝ち）」をベクトル化して選ぶ。
        # キー: (pixel_idx, run_counts, run_last_pos) を昇順で並べ、pixelごとの末尾を採用。
        candidate_order = np.lexsort((run_last_pos, run_counts, pixel_idx))
        if candidate_order.size <= 0:
            return out.reshape((256, 256, 4))

        pixel_sorted = pixel_idx[candidate_order]
        group_start = np.concatenate(
            ([0], np.flatnonzero(np.diff(pixel_sorted) != 0).astype(np.int64) + 1)
        )
        group_end = np.concatenate((group_start[1:], [candidate_order.size]))
        best_rows = candidate_order[group_end - 1]

        best_pixels = pixel_idx[best_rows]
        best_colors = color_unique[best_rows]
        out[best_pixels, 0] = ((best_colors >> 16) & 0xFF).astype(np.uint8, copy=False)
        out[best_pixels, 1] = ((best_colors >> 8) & 0xFF).astype(np.uint8, copy=False)
        out[best_pixels, 2] = (best_colors & 0xFF).astype(np.uint8, copy=False)
        out[best_pixels, 3] = 255
        return out.reshape((256, 256, 4))

    def _render_scatter_heatmap(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """密度ヒートマップ方式で散布図ラスタを生成する。"""
        out = np.zeros((256, 256, 4), dtype=np.uint8)
        if x.size == 0 or y.size == 0:
            return out

        # 4近傍の重み付けは flat index をまとめて作って bincount で一括集計する。
        flat_idx = self._four_neighborhood_flat_indices(
            x,
            y,
            triangle_mode=(self._shape == C.SCATTER_SHAPE_TRIANGLE),
        )
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
        """S/V・RGBサンプルから散布図表示を更新する。"""
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

            rgb_u8 = self._to_rgb_u8(rgb_arr, n)
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
                rgb_u8 = self._to_rgb_u8(rgb_arr, n)
                x, y = self._compute_scatter_xy(sv_used)
                img = self._render_scatter_dominant(x, y, rgb_u8)
            except Exception:
                self._show_scatter_frame_only()
                return

        if not self._cache_scatter_base_pixmap(img):
            self._show_scatter_frame_only()
            return
        if not self._present_scatter_from_base():
            self._show_scatter_frame_only()
            return
        self._resize_recalc_timer.stop()

    def resizeEvent(self, event):
        """リサイズ中は軽量スケール描画、停止後に再描画を予約する。"""
        super().resizeEvent(event)
        if event.size() == event.oldSize():
            return
        if not self.isVisible() or self.isHidden():
            return
        if self.width() <= 1 or self.height() <= 1:
            return
        # リサイズ時は点群再集計せず、キャッシュ済みベース画像の再スケールだけ行う。
        if self._present_scatter_from_base(smooth=False):
            self._resize_recalc_timer.start()
            return
        if self._last_sv is not None and self._last_rgb is not None:
            # キャッシュが無い初回のみ再計算する。
            self.update_scatter(self._last_sv, self._last_rgb)
        else:
            self._show_scatter_frame_only()
