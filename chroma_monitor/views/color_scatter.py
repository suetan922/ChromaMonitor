"""色相環とS-V散布図の表示ビュー。"""

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..util import constants as C
from ..util.image_ops import clamp_render_size
from ..util.theme import UiTheme, get_ui_theme, qcolor
from ..util.value_utils import clamp_int, safe_choice
from .color_scatter_constants import (
    HSV180_COLORS_Q,
    HUE180_TO_MUNSELL40_WEIGHTS,
    MUNSELL_COLORS_Q,
    MUNSELL_HUE_LABELS,
    SCATTER_HUE_FILTER_HALF_WIDTH,
    SCATTER_LAYOUT_SYNC_DEBOUNCE_MS,
    SCATTER_RESIZE_RECALC_DEBOUNCE_MS,
    WHEEL_HARMONY_GUIDE_DOT_RADIUS,
    WHEEL_HARMONY_GUIDE_RADIUS_RATIO,
    WHEEL_THICKNESS_MODE,
    WHEEL_THICKNESS_MODE_ABSOLUTE,
    WHEEL_THICKNESS_MODE_RELATIVE_MAX,
)
from .color_scatter_math import (
    ScatterRenderConfig,
    build_scatter_image,
    build_square_fallback_scatter_image,
    guide_points,
    guide_radius,
    munsell_hist,
    normalize_rotation_deg,
    normalize_signed_delta_deg,
    point_angle_deg,
    scatter_render_mode_needs_rgb,
)

_SCATTER_RESIZE_TRANSFORM_MODE = Qt.FastTransformation


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
        self._theme = get_ui_theme()

    def set_theme(self, theme: UiTheme) -> None:
        """テーマ色を更新して再描画する。"""
        self._theme = theme
        self.update()

    def _set_state_and_update(self, attr_name: str, next_value) -> bool:
        """状態値を更新し、変化時のみ再描画する。"""
        if getattr(self, attr_name) == next_value:
            return False
        setattr(self, attr_name, next_value)
        self.update()
        return True

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
        self._set_state_and_update("_mode", normalized)

    def set_harmony_guide_enabled(self, enabled: bool):
        """色彩調和ガイド表示の有効/無効を切り替える。"""
        next_enabled = bool(enabled)
        self._set_state_and_update("_guide_enabled", next_enabled)

    def set_harmony_guide_type(self, guide_type: str):
        """色彩調和ガイド種別を更新する。"""
        normalized = safe_choice(
            guide_type,
            C.WHEEL_HARMONY_GUIDE_TYPES,
            C.DEFAULT_WHEEL_HARMONY_GUIDE_TYPE,
        )
        self._set_state_and_update("_guide_type", normalized)

    def set_harmony_guide_rotation(self, rotation_deg: float):
        """色彩調和ガイドの回転角を設定する。"""
        normalized = normalize_rotation_deg(rotation_deg)
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
        return munsell_hist(
            self._hist,
            HUE180_TO_MUNSELL40_WEIGHTS,
            dst_bins=len(MUNSELL_HUE_LABELS),
        )

    def _wheel_bins(self):
        """現在モードで描画に使うビン値と色配列を返す。"""
        # 表示モードに応じて「集計値」と「塗り色」を切り替える。
        mode = safe_choice(self._mode, C.WHEEL_MODES, C.DEFAULT_WHEEL_MODE)
        if mode == C.WHEEL_MODE_MUNSELL40:
            counts = self._munsell_hist()
            return counts, MUNSELL_COLORS_Q

        counts = np.asarray(self._hist, dtype=np.float32)
        return counts, HSV180_COLORS_Q

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
            WHEEL_THICKNESS_MODE,
            (WHEEL_THICKNESS_MODE_ABSOLUTE, WHEEL_THICKNESS_MODE_RELATIVE_MAX),
            WHEEL_THICKNESS_MODE_ABSOLUTE,
        )
        if mode == WHEEL_THICKNESS_MODE_RELATIVE_MAX:
            denom = max(1.0, float(local_max))
            return max(0.0, min(1.0, float(count) / denom))
        denom = max(1.0, float(total_count))
        return max(0.0, min(1.0, float(count) / denom))

    def _draw_harmony_guide(self, painter: QPainter, cx: int, cy: int, inner_r: int) -> None:
        """色彩調和ガイドのリング・線・頂点を描画する。"""
        if not self._guide_enabled:
            return
        if self._guide_type == C.WHEEL_HARMONY_GUIDE_NONE:
            return
        points = [
            QPoint(x, y)
            for (x, y) in guide_points(
                cx,
                cy,
                inner_r,
                guide_type=self._guide_type,
                guide_rotation_deg=self._guide_rotation_deg,
                guide_offsets_deg=C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG,
                radius_ratio=WHEEL_HARMONY_GUIDE_RADIUS_RATIO,
                red_reference_deg=C.HUE_RED_REFERENCE_DEG,
                direction_sign=C.HUE_DIRECTION_SIGN,
            )
        ]
        if not points:
            return

        guide_r = guide_radius(inner_r, radius_ratio=WHEEL_HARMONY_GUIDE_RADIUS_RATIO)
        painter.setPen(QPen(qcolor(self._theme.text_muted, 92), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPoint(cx, cy), guide_r, guide_r)

        painter.setPen(QPen(qcolor(self._theme.accent, 120), 1))
        for pt in points:
            painter.drawLine(cx, cy, pt.x(), pt.y())

        painter.setPen(QPen(qcolor(self._theme.accent, 212), 2))
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
        painter.setBrush(qcolor(self._theme.accent, 236))
        for pt in points:
            painter.drawEllipse(
                pt, WHEEL_HARMONY_GUIDE_DOT_RADIUS, WHEEL_HARMONY_GUIDE_DOT_RADIUS
            )

    def mousePressEvent(self, event):
        """内周クリック時はガイド回転ドラッグを開始する。"""
        if (
            event.button() == Qt.LeftButton
            and self._guide_enabled
            and self._guide_type != C.WHEEL_HARMONY_GUIDE_NONE
            and self._guide_type in C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG
        ):
            cx, cy, _r, inner_r = self._wheel_geometry()
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            dx = int(pos.x()) - int(cx)
            dy = int(pos.y()) - int(cy)
            if dx * dx + dy * dy <= int(inner_r * inner_r):
                self._guide_drag_active = True
                self._guide_drag_start_angle = point_angle_deg(pos.x(), pos.y(), cx, cy)
                self._guide_drag_start_rotation = float(self._guide_rotation_deg)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """ガイド回転ドラッグ中の角度更新を行う。"""
        if self._guide_drag_active:
            cx, cy, _r, _inner_r = self._wheel_geometry()
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            current_angle = point_angle_deg(pos.x(), pos.y(), cx, cy)
            delta = normalize_signed_delta_deg(current_angle - self._guide_drag_start_angle)
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
            p.fillRect(self.rect(), qcolor(self._theme.wheel_canvas_bg))

            cx, cy, r, inner_r = self._wheel_geometry()

            p.setPen(Qt.NoPen)
            # 黄色系でも輪郭が埋もれにくいよう、土台グレーを少し暗くする。
            p.setBrush(qcolor(self._theme.wheel_outer_bg))
            p.drawEllipse(QPoint(cx, cy), r, r)

            p.setBrush(qcolor(self._theme.wheel_inner_bg))
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
                    float(C.HUE_RED_REFERENCE_DEG) + float(C.HUE_DIRECTION_SIGN) * (h * step_deg)
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
                p.setBrush(qcolor(self._theme.wheel_inner_bg))
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
                    float(C.HUE_RED_REFERENCE_DEG) + float(C.HUE_DIRECTION_SIGN) * (h * step_deg)
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
                p.setBrush(qcolor(self._theme.wheel_inner_bg))
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
            p.setBrush(qcolor(self._theme.wheel_inner_bg))
            p.drawEllipse(QPoint(cx, cy), inner_r, inner_r)
            p.setPen(QPen(qcolor(self._theme.border), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
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
        self.setProperty("chromaViewRole", "scatter")
        self._square_limit = True
        self._last_sv: Optional[np.ndarray] = None
        self._last_rgb: Optional[np.ndarray] = None
        self._scatter_base_pm: Optional[QPixmap] = None
        self._theme = get_ui_theme()
        self._resize_recalc_timer = QTimer(self)
        self._resize_recalc_timer.setSingleShot(True)
        self._resize_recalc_timer.setInterval(SCATTER_RESIZE_RECALC_DEBOUNCE_MS)
        self._resize_recalc_timer.timeout.connect(self._rerender_after_resize_idle)
        self._layout_sync_timer = QTimer(self)
        self._layout_sync_timer.setSingleShot(True)
        self._layout_sync_timer.setInterval(SCATTER_LAYOUT_SYNC_DEBOUNCE_MS)
        self._layout_sync_timer.timeout.connect(self._sync_after_layout_change)
        self._shape = C.SCATTER_SHAPE_SQUARE
        self._render_mode = C.DEFAULT_SCATTER_RENDER_MODE
        self._need_rgb_for_render = scatter_render_mode_needs_rgb(self._render_mode)
        self._hue_filter_enabled = bool(C.DEFAULT_SCATTER_HUE_FILTER_ENABLED)
        self._hue_center = clamp_int(
            C.DEFAULT_SCATTER_HUE_CENTER, C.SCATTER_HUE_MIN, C.SCATTER_HUE_MAX
        )
        self._show_scatter_frame_only()

    def set_theme(self, theme: UiTheme) -> None:
        """散布図フレーム色と背景色を更新する。"""
        self._theme = theme
        self._rerender_or_show_frame()

    def _rerender_or_show_frame(self) -> None:
        """直近データがあれば再描画し、なければ枠のみ表示する。"""
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
            return
        self._show_scatter_frame_only()

    def _can_render_current_geometry(self) -> bool:
        """現在の可視状態とサイズで描画可能かを返す。"""
        if not self.isVisible() or self.isHidden():
            return False
        if self.width() <= 1 or self.height() <= 1:
            return False
        return True

    def request_layout_sync(self):
        """外部レイアウト変更後に散布図表示のサイズ同期を予約する。"""
        self._layout_sync_timer.start()

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
        self._rerender_or_show_frame()

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
        self._need_rgb_for_render = scatter_render_mode_needs_rgb(self._render_mode)
        self._rerender_or_show_frame()

    def set_hue_filter(self, enabled: bool, center: int):
        """色相フィルターの有効状態と中心色相を更新する。"""
        # フィルター条件変更は直近データを再描画して即時反映する。
        next_enabled = bool(enabled)
        next_center = clamp_int(center, C.SCATTER_HUE_MIN, C.SCATTER_HUE_MAX)
        if self._hue_filter_enabled == next_enabled and self._hue_center == next_center:
            return
        self._hue_filter_enabled = next_enabled
        self._hue_center = next_center
        self._rerender_or_show_frame()

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
            pen = QPen(qcolor(self._theme.scatter_frame, 185), max(1, int(pm.width() * 0.0045)))
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
        if not self._can_render_current_geometry():
            return
        # 散布図のベース画像(256x256)はサイズ非依存なので、まずは再計算せず高品質リスケールだけ行う。
        if self._present_scatter_from_base(smooth=True):
            return
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)

    def _sync_after_layout_change(self):
        """レイアウト変更後に現在サイズへ再スケールして見切れを防ぐ。"""
        if not self._can_render_current_geometry():
            return
        if self._present_scatter_from_base(smooth=False):
            self._resize_recalc_timer.start()
            return
        if self._last_sv is not None and self._last_rgb is not None:
            self.update_scatter(self._last_sv, self._last_rgb)
            return
        self._show_scatter_frame_only()

    def _scatter_render_config(self) -> ScatterRenderConfig:
        """現在UI状態から散布図ラスタ生成設定を返す。"""
        return ScatterRenderConfig(
            triangle_mode=(self._shape == C.SCATTER_SHAPE_TRIANGLE),
            render_mode=self._render_mode,
            need_rgb_for_render=bool(self._need_rgb_for_render),
            hue_filter_enabled=bool(self._hue_filter_enabled),
            hue_center=int(self._hue_center),
            hue_half_width=int(SCATTER_HUE_FILTER_HALF_WIDTH),
        )

    def _set_safe_fallback_render_mode(self) -> None:
        """例外時に安全側の描画モードへ切り替える。"""
        self._shape = C.SCATTER_SHAPE_SQUARE
        self._render_mode = C.SCATTER_RENDER_MODE_DOMINANT
        self._need_rgb_for_render = True

    def update_scatter(self, sv: np.ndarray, rgb: np.ndarray):
        """S/V・RGBサンプルから散布図表示を更新する。"""
        self._last_sv = sv
        self._last_rgb = rgb
        if sv is None or rgb is None or sv.size == 0 or rgb.size == 0:
            self._show_scatter_frame_only()
            return

        try:
            img = build_scatter_image(
                sv,
                rgb,
                config=self._scatter_render_config(),
            )
            if img is None:
                self._show_scatter_frame_only()
                return
        except (RuntimeError, TypeError, ValueError, IndexError):
            # 描画エラー時は四角モードへフォールバックして継続
            self._set_safe_fallback_render_mode()
            try:
                img = build_square_fallback_scatter_image(sv, rgb)
                if img is None:
                    self._show_scatter_frame_only()
                    return
            except (RuntimeError, TypeError, ValueError, IndexError):
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
        if not self._can_render_current_geometry():
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

    def showEvent(self, event):
        """表示開始時にレイアウト同期を予約する。"""
        super().showEvent(event)
        self.request_layout_sync()

    def event(self, event):
        """レイアウト要求時に散布図サイズ同期を予約する。"""
        handled = super().event(event)
        et = event.type()
        if et in (QEvent.LayoutRequest, QEvent.ShowToParent, QEvent.ParentChange):
            self.request_layout_sync()
        return handled
