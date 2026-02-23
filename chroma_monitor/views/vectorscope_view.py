"""Vectorscope image view."""

import math

import cv2
import numpy as np

from ..util import constants as C
from ..util.functions import bgr_to_qpixmap, clamp_int, resize_by_long_edge
from .base_image_view import BaseImageLabelView
from .image_math import normalize_map


class VectorScopeView(BaseImageLabelView):
    def __init__(self):
        super().__init__(
            "ベクトルスコープなし",
            style="background:#0d1015; border:1px solid #2c3440; color:#9aa7ba;",
        )
        self._show_skin_tone_line = C.DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE
        self._warn_threshold = C.DEFAULT_VECTORSCOPE_WARN_THRESHOLD
        self._last_high_sat_ratio = 0.0
        self._mask_cache: dict[int, np.ndarray] = {}
        self._bg_cache: dict[int, np.ndarray] = {}
        self._ref_vectors_cache = None

    def set_show_skin_tone_line(self, enabled: bool):
        self._show_skin_tone_line = bool(enabled)
        if self._last_bgr is not None:
            self.update_scope(self._last_bgr)

    def set_warn_threshold(self, value: int):
        self._warn_threshold = clamp_int(
            value, C.VECTORSCOPE_WARN_THRESHOLD_MIN, C.VECTORSCOPE_WARN_THRESHOLD_MAX
        )
        if self._last_bgr is not None:
            self.update_scope(self._last_bgr)

    def high_saturation_ratio(self) -> float:
        return float(self._last_high_sat_ratio)

    def _render_size(self) -> int:
        # 表示サイズに追従して描画解像度を上げ、拡大ぼけを抑える
        target = min(self.width(), self.height())
        target = clamp_int(target, max(160, C.VECTORSCOPE_SIZE), 640)
        return int(target)

    def _scope_geometry(self, size: int):
        # U/V 平面を中心原点へ投影するための幾何パラメータ。
        cx = (size - 1) // 2
        cy = (size - 1) // 2
        radius = max(8, int(round(size * float(C.VECTORSCOPE_SCOPE_RADIUS_RATIO))))
        full = max(1.0, float(C.VECTORSCOPE_CHROMA_FULL_SCALE))
        scale = radius / full
        return cx, cy, radius, scale

    def _scope_mask(self, size: int) -> np.ndarray:
        cached = self._mask_cache.get(int(size))
        if cached is not None:
            return cached
        cx, cy, radius, _ = self._scope_geometry(size)
        yy, xx = np.ogrid[:size, :size]
        mask = ((xx - cx) * (xx - cx) + (yy - cy) * (yy - cy)) <= (radius * radius)
        self._mask_cache[int(size)] = mask
        return mask

    def _angle_point(
        self, size: int, angle_deg: float, radius_ratio: float = 1.0
    ) -> tuple[int, int]:
        cx, cy, radius, _ = self._scope_geometry(size)
        angle = math.radians(float(angle_deg) % 360.0)
        rr = radius * float(radius_ratio)
        x = int(round(cx + math.cos(angle) * rr))
        y = int(round(cy - math.sin(angle) * rr))
        return x, y

    def _ref_angle_from_bgr(self, bgr_color: tuple[int, int, int]) -> float:
        ref = np.array([[bgr_color]], dtype=np.uint8)
        yuv = cv2.cvtColor(ref, cv2.COLOR_BGR2YUV)[0, 0]
        u = float(yuv[1]) - 128.0
        v = float(yuv[2]) - 128.0
        return (math.degrees(math.atan2(v, u)) + 360.0) % 360.0

    def _reference_vectors(self):
        # 色方位ラベル（R/Y/G/C/B/M）の参照ベクトルを返す。
        if self._ref_vectors_cache is not None:
            return self._ref_vectors_cache
        refs = (
            ("R", (0, 0, 255), (70, 70, 255)),
            ("Y", (0, 255, 255), (30, 220, 255)),
            ("G", (0, 255, 0), (70, 230, 120)),
            ("C", (255, 255, 0), (235, 220, 100)),
            ("B", (255, 0, 0), (255, 140, 90)),
            ("M", (255, 0, 255), (245, 110, 220)),
        )
        self._ref_vectors_cache = [
            (label, self._ref_angle_from_bgr(ref_bgr), color) for label, ref_bgr, color in refs
        ]
        return self._ref_vectors_cache

    def _background(self, size: int) -> np.ndarray:
        # グリッドは主信号を邪魔しないよう薄めに描く。
        cached = self._bg_cache.get(int(size))
        if cached is not None:
            return cached
        bg = np.full((size, size, 3), (8, 10, 13), dtype=np.uint8)
        cx, cy, radius, _ = self._scope_geometry(size)
        mask = self._scope_mask(size)
        bg[mask] = (12, 16, 22)
        cv2.rectangle(bg, (0, 0), (size - 1, size - 1), (28, 34, 42), 1, cv2.LINE_AA)

        # グリッドは控えめにして、信号を見やすくする
        for ratio in (0.25, 0.5, 0.75):
            rr = max(1, int(round(radius * ratio)))
            cv2.circle(bg, (cx, cy), rr, (42, 50, 60), 1, cv2.LINE_AA)
        cv2.circle(bg, (cx, cy), radius, (74, 86, 102), 1, cv2.LINE_AA)
        cv2.line(bg, (cx - radius, cy), (cx + radius, cy), (54, 62, 74), 1, cv2.LINE_AA)
        cv2.line(bg, (cx, cy - radius), (cx, cy + radius), (54, 62, 74), 1, cv2.LINE_AA)
        for _label, angle, _color in self._reference_vectors():
            px, py = self._angle_point(size, angle, 1.0)
            cv2.line(bg, (cx, cy), (px, py), (35, 42, 51), 1, cv2.LINE_AA)
        cv2.circle(bg, (cx, cy), 1, (120, 130, 142), -1, cv2.LINE_AA)
        self._bg_cache[int(size)] = bg
        return bg

    def _draw_saturation_guide(self, view: np.ndarray):
        # 現在しきい値の彩度リングを描画する。
        size = view.shape[0]
        cx, cy, radius, _ = self._scope_geometry(size)
        rr = max(2, int(round(radius * (self._warn_threshold / 100.0))))
        cv2.circle(view, (cx, cy), rr, (28, 36, 50), 2, cv2.LINE_AA)
        cv2.circle(view, (cx, cy), rr, (124, 142, 166), 1, cv2.LINE_AA)

    def _draw_color_direction_legend(self, view: np.ndarray):
        # R/Y/G/C/B/M の方位ラベルを外周に表示する。
        size = view.shape[0]
        for label, angle, color in self._reference_vectors():
            x, y = self._angle_point(size, angle, 1.0)
            tx, ty = self._angle_point(size, angle, 1.14)
            tx = clamp_int(tx, 2, size - 16)
            ty = clamp_int(ty, 10, size - 3)
            cv2.circle(view, (x, y), 2, color, -1, cv2.LINE_AA)
            cv2.putText(
                view, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (0, 0, 0), 2, cv2.LINE_AA
            )
            cv2.putText(
                view, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.34, color, 1, cv2.LINE_AA
            )

    def _draw_skin_tone_line(self, view: np.ndarray):
        if not self._show_skin_tone_line:
            return
        size = view.shape[0]
        cx, cy, radius, _ = self._scope_geometry(size)
        angle = math.radians(float(C.VECTORSCOPE_SKIN_LINE_ANGLE_DEG))
        p1 = (cx, cy)
        p2 = (
            int(round(cx + math.cos(angle) * radius)),
            int(round(cy - math.sin(angle) * radius)),
        )
        cv2.line(view, p1, p2, (30, 38, 52), 2, cv2.LINE_AA)
        cv2.line(view, p1, p2, (132, 166, 202), 1, cv2.LINE_AA)

    def update_scope(self, bgr: np.ndarray):
        if not self._set_last_bgr(bgr):
            self._last_high_sat_ratio = 0.0
            return

        # 計算量を抑えるため、入力を固定上限へ縮小してから解析する。
        src = resize_by_long_edge(bgr, C.ANALYZER_MAX_DIM)
        yuv = cv2.cvtColor(src, cv2.COLOR_BGR2YUV)
        u = yuv[:, :, 1].astype(np.float32) - 128.0
        v = yuv[:, :, 2].astype(np.float32) - 128.0

        size = max(64, self._render_size())
        cx, cy, _radius, scale = self._scope_geometry(size)
        scope_mask = self._scope_mask(size)
        xs = np.round(cx + u * scale).astype(np.int32)
        ys = np.round(cy - v * scale).astype(np.int32)
        valid = (xs >= 0) & (xs < size) & (ys >= 0) & (ys < size)
        if np.any(valid):
            inside = np.zeros_like(valid, dtype=bool)
            inside[valid] = scope_mask[ys[valid], xs[valid]]
            valid &= inside

        hist = np.zeros((size, size), dtype=np.float32)
        if np.any(valid):
            flat_idx = ys[valid] * size + xs[valid]
            hist = np.bincount(flat_idx, minlength=size * size).astype(np.float32).reshape(size, size)
        # 密度マップは対数正規化して暗部の情報を潰しにくくする。
        hist = cv2.GaussianBlur(hist, (0, 0), 1.0)
        density = normalize_map(np.log1p(hist))

        base = self._background(size).astype(np.float32)
        energy = np.power(density, 0.62)
        glow = cv2.GaussianBlur(energy, (0, 0), 1.3)
        layer = np.zeros((size, size, 3), dtype=np.float32)
        layer[:, :, 0] = 255.0 * glow * 0.90
        layer[:, :, 1] = 255.0 * glow * 0.95
        layer[:, :, 2] = 255.0 * energy * 0.88
        view_f = np.clip(base + layer, 0, 255)
        view_f[~scope_mask] = base[~scope_mask]

        # しきい値を超える高彩度域を控えめに警告する
        thr = float(self._warn_threshold) / 100.0 * float(C.VECTORSCOPE_CHROMA_FULL_SCALE)
        sat = np.sqrt(u * u + v * v)
        over = valid & (sat >= thr)
        if np.any(over):
            over_idx = ys[over] * size + xs[over]
            over_hist = np.bincount(over_idx, minlength=size * size).astype(np.float32).reshape(size, size)
            over_hist = cv2.GaussianBlur(over_hist, (0, 0), 1.0)
            over_density = normalize_map(np.log1p(over_hist))
            over_alpha = np.clip(over_density[:, :, None] * 0.55, 0.0, 0.55)
            warn_color = np.array(C.VECTORSCOPE_WARN_COLOR_BGR, dtype=np.float32).reshape(1, 1, 3)
            view_f = np.clip(view_f * (1.0 - over_alpha) + warn_color * over_alpha, 0, 255)

        view = view_f.astype(np.uint8)
        total_valid = int(np.count_nonzero(valid))
        over_count = int(np.count_nonzero(over))
        # 設定画面の警告表示で使うため比率を保持しておく。
        self._last_high_sat_ratio = (over_count * 100.0 / total_valid) if total_valid > 0 else 0.0

        self._draw_saturation_guide(view)
        self._draw_skin_tone_line(view)
        self._draw_color_direction_legend(view)

        pm = bgr_to_qpixmap(view, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rerender_on_resize(self.update_scope)
