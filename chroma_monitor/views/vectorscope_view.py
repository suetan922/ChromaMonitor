"""ベクトルスコープ表示ビュー。"""

import math

import cv2
import numpy as np

from ..util import constants as C
from ..util.image_ops import bgr_to_qpixmap, resize_by_long_edge
from ..util.value_utils import clamp_int
from .base_image_view import BaseImageLabelView
from .image_math import normalize_map

_VECTORSCOPE_SIZE = 256
_VECTORSCOPE_CHROMA_FULL_SCALE = 181.0
_VECTORSCOPE_SKIN_LINE_ANGLE_DEG = 123.0
_VECTORSCOPE_SCOPE_RADIUS_RATIO = 0.46
_VECTORSCOPE_WARN_COLOR_BGR = (32, 64, 250)


class VectorScopeView(BaseImageLabelView):
    """YUVベースのベクトルスコープ表示ビュー。"""

    def __init__(self):
        """表示設定と描画キャッシュを初期化する。"""
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
        self._red_raw_angle_deg = self._ref_angle_from_bgr((0, 0, 255))
        self._uv_transform = self._build_uv_transform()
        self.set_resize_renderer(self.update_scope)

    def _display_angle_from_raw(self, raw_angle_deg: float) -> float:
        """生のU/V角度を表示系の角度へ変換する。"""
        return (
            float(C.HUE_RED_REFERENCE_DEG)
            + float(C.HUE_DIRECTION_SIGN) * (float(raw_angle_deg) - self._red_raw_angle_deg)
        ) % 360.0

    def _build_uv_transform(self) -> tuple[float, float, float, float]:
        """赤基準・回転方向を反映したU/V変換行列を作る。"""
        ref = math.radians(float(C.HUE_RED_REFERENCE_DEG))
        raw = math.radians(float(self._red_raw_angle_deg))
        r_ref = np.array(
            [[math.cos(ref), -math.sin(ref)], [math.sin(ref), math.cos(ref)]], dtype=np.float32
        )
        r_neg_raw = np.array(
            [[math.cos(raw), math.sin(raw)], [-math.sin(raw), math.cos(raw)]], dtype=np.float32
        )
        if float(C.HUE_DIRECTION_SIGN) >= 0.0:
            m = r_ref @ r_neg_raw
        else:
            # 反転方向は x軸反転行列を挟んで表現する（赤基準は固定）。
            mirror_x = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.float32)
            m = r_ref @ mirror_x @ r_neg_raw
        return float(m[0, 0]), float(m[0, 1]), float(m[1, 0]), float(m[1, 1])

    def set_show_skin_tone_line(self, enabled: bool):
        """スキントーンライン表示の有効/無効を切り替える。"""
        self._show_skin_tone_line = bool(enabled)
        if self._last_bgr is not None:
            self.update_scope(self._last_bgr)

    def set_warn_threshold(self, value: int):
        """高彩度警告しきい値(%)を更新する。"""
        self._warn_threshold = clamp_int(
            value, C.VECTORSCOPE_WARN_THRESHOLD_MIN, C.VECTORSCOPE_WARN_THRESHOLD_MAX
        )
        if self._last_bgr is not None:
            self.update_scope(self._last_bgr)

    def high_saturation_ratio(self) -> float:
        """直近フレームでしきい値超過した画素比率(%)を返す。"""
        return float(self._last_high_sat_ratio)

    def _render_size(self) -> int:
        """現在表示サイズに基づく描画解像度を返す。"""
        # 表示サイズに追従して描画解像度を上げ、拡大ぼけを抑える
        target = min(self.width(), self.height())
        target = clamp_int(target, max(160, _VECTORSCOPE_SIZE), 640)
        return int(target)

    def _scope_geometry(self, size: int):
        """描画サイズに対する中心座標・半径・スケールを返す。"""
        # U/V 平面を中心原点へ投影するための幾何パラメータ。
        cx = (size - 1) // 2
        cy = (size - 1) // 2
        radius = max(8, int(round(size * float(_VECTORSCOPE_SCOPE_RADIUS_RATIO))))
        full = max(1.0, float(_VECTORSCOPE_CHROMA_FULL_SCALE))
        scale = radius / full
        return cx, cy, radius, scale

    def _scope_mask(self, size: int) -> np.ndarray:
        """スコープ円内判定マスクをサイズ別キャッシュ付きで返す。"""
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
        """角度と半径比から描画座標を求める。"""
        cx, cy, radius, _ = self._scope_geometry(size)
        angle = math.radians(float(angle_deg) % 360.0)
        rr = radius * float(radius_ratio)
        x = int(round(cx + math.cos(angle) * rr))
        y = int(round(cy - math.sin(angle) * rr))
        return x, y

    def _ref_angle_from_bgr(self, bgr_color: tuple[int, int, int]) -> float:
        """基準BGR色のU/V角度を算出する。"""
        ref = np.array([[bgr_color]], dtype=np.uint8)
        yuv = cv2.cvtColor(ref, cv2.COLOR_BGR2YUV)[0, 0]
        u = float(yuv[1]) - 128.0
        v = float(yuv[2]) - 128.0
        return (math.degrees(math.atan2(v, u)) + 360.0) % 360.0

    def _reference_vectors(self):
        """色方向ラベル用の基準角度セットを返す。"""
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
            (label, self._display_angle_from_raw(self._ref_angle_from_bgr(ref_bgr)), color)
            for label, ref_bgr, color in refs
        ]
        return self._ref_vectors_cache

    def _background(self, size: int) -> np.ndarray:
        """スコープ背景グリッドをサイズ別キャッシュ付きで返す。"""
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
        """高彩度しきい値リングを描画する。"""
        # 現在しきい値の彩度リングを描画する。
        size = view.shape[0]
        cx, cy, radius, _ = self._scope_geometry(size)
        rr = max(2, int(round(radius * (self._warn_threshold / 100.0))))
        cv2.circle(view, (cx, cy), rr, (28, 36, 50), 2, cv2.LINE_AA)
        cv2.circle(view, (cx, cy), rr, (124, 142, 166), 1, cv2.LINE_AA)

    def _draw_color_direction_legend(self, view: np.ndarray):
        """色方向ラベルと方位マーカーを描画する。"""
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
        """スキントーン方向ガイド線を描画する。"""
        if not self._show_skin_tone_line:
            return
        size = view.shape[0]
        cx, cy, _radius, _ = self._scope_geometry(size)
        p1 = (cx, cy)
        angle = self._display_angle_from_raw(_VECTORSCOPE_SKIN_LINE_ANGLE_DEG)
        p2 = self._angle_point(size, angle, 1.0)
        cv2.line(view, p1, p2, (30, 38, 52), 2, cv2.LINE_AA)
        cv2.line(view, p1, p2, (132, 166, 202), 1, cv2.LINE_AA)

    def update_scope(self, bgr: np.ndarray):
        """入力フレームをベクトルスコープ表示へ変換して描画する。"""
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
        m00, m01, m10, m11 = self._uv_transform
        u_disp = m00 * u + m01 * v
        v_disp = m10 * u + m11 * v
        xs = np.round(cx + u_disp * scale).astype(np.int32)
        ys = np.round(cy - v_disp * scale).astype(np.int32)
        valid = (xs >= 0) & (xs < size) & (ys >= 0) & (ys < size)
        valid_idx = np.flatnonzero(valid)
        flat_idx = None
        hist = np.zeros((size, size), dtype=np.float32)
        if valid_idx.size > 0:
            ys_flat = ys.reshape(-1)
            xs_flat = xs.reshape(-1)
            inside = scope_mask[ys_flat[valid_idx], xs_flat[valid_idx]]
            if np.any(inside):
                valid_idx = valid_idx[inside]
                ys_valid = ys_flat[valid_idx]
                xs_valid = xs_flat[valid_idx]
                flat_idx = ys_valid * size + xs_valid
                hist = (
                    np.bincount(flat_idx, minlength=size * size)
                    .astype(np.float32, copy=False)
                    .reshape(size, size)
                )
            else:
                valid_idx = np.empty((0,), dtype=np.int64)
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
        thr = float(self._warn_threshold) / 100.0 * float(_VECTORSCOPE_CHROMA_FULL_SCALE)
        total_valid = int(valid_idx.size)
        over_count = 0
        if total_valid > 0 and flat_idx is not None:
            u_flat = u.reshape(-1)
            v_flat = v.reshape(-1)
            sat_valid = np.sqrt(
                u_flat[valid_idx] * u_flat[valid_idx] + v_flat[valid_idx] * v_flat[valid_idx]
            )
            over_valid = sat_valid >= thr
            over_count = int(np.count_nonzero(over_valid))
            if over_count > 0:
                over_idx = flat_idx[over_valid]
            else:
                over_idx = None
        else:
            over_idx = None

        if over_idx is not None:
            over_hist = (
                np.bincount(over_idx, minlength=size * size).astype(np.float32).reshape(size, size)
            )
            over_hist = cv2.GaussianBlur(over_hist, (0, 0), 1.0)
            over_density = normalize_map(np.log1p(over_hist))
            over_alpha = np.clip(over_density[:, :, None] * 0.55, 0.0, 0.55)
            warn_color = np.array(_VECTORSCOPE_WARN_COLOR_BGR, dtype=np.float32).reshape(1, 1, 3)
            view_f = np.clip(view_f * (1.0 - over_alpha) + warn_color * over_alpha, 0, 255)

        view = view_f.astype(np.uint8)
        # 設定画面の警告表示で使うため比率を保持しておく。
        self._last_high_sat_ratio = (over_count * 100.0 / total_valid) if total_valid > 0 else 0.0

        self._draw_saturation_guide(view)
        self._draw_skin_tone_line(view)
        self._draw_color_direction_legend(view)

        pm = bgr_to_qpixmap(view, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)
