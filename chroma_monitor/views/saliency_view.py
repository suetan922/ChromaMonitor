"""ビュー描画に関する処理。"""

from typing import Optional

import cv2
import numpy as np

from ..util import constants as C
from ..util.functions import clamp_int, resize_by_long_edge, rgb_to_qpixmap, safe_choice
from .base_image_view import BaseImageLabelView
from .image_math import normalize_map


def _apply_composition_guides(bgr: np.ndarray, guide: str) -> np.ndarray:
    # ガイドは表示用オーバーレイなので、入力画像自体は破壊しない。
    if bgr is None or bgr.size == 0:
        return bgr
    if guide not in C.COMPOSITION_GUIDES[1:]:
        return bgr

    out = bgr.copy()
    h, w = out.shape[:2]
    if h < 2 or w < 2:
        return out

    # 線幅を細めにして、サリエンシー本体の視認性を優先する。
    base_thick = max(1, int(round(min(w, h) / 520.0)))

    lines = []
    points = []

    if guide == C.COMPOSITION_GUIDE_THIRDS:
        x1, x2 = w // 3, (w * 2) // 3
        y1, y2 = h // 3, (h * 2) // 3
        lines.extend(
            [
                ((x1, 0), (x1, h - 1)),
                ((x2, 0), (x2, h - 1)),
                ((0, y1), (w - 1, y1)),
                ((0, y2), (w - 1, y2)),
            ]
        )
        # 三分割の注目点を補助表示
        points.extend([(x1, y1), (x1, y2), (x2, y1), (x2, y2)])
    elif guide == C.COMPOSITION_GUIDE_CENTER:
        cx, cy = w // 2, h // 2
        lines.extend(
            [
                ((cx, 0), (cx, h - 1)),
                ((0, cy), (w - 1, cy)),
            ]
        )
        points.append((cx, cy))
    elif guide == C.COMPOSITION_GUIDE_DIAGONAL:
        lines.extend(
            [
                ((0, 0), (w - 1, h - 1)),
                ((0, h - 1), (w - 1, 0)),
            ]
        )

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


class SaliencyView(BaseImageLabelView):

    def __init__(self):
        super().__init__("サリエンシーなし")
        self._last_saliency: Optional[np.ndarray] = None
        self._last_overlay_bgra: Optional[np.ndarray] = None
        self._overlay_alpha = C.DEFAULT_SALIENCY_OVERLAY_ALPHA  # 0..100
        self._guide = C.DEFAULT_COMPOSITION_GUIDE  # none | thirds | center | diagonal
        self._sr_detector = None
        self._sr_detector_ready = False

    def set_overlay_alpha(self, value: int):
        # アルファ変更は直近フレームを再描画して即時反映する。
        self._overlay_alpha = clamp_int(value, C.SALIENCY_ALPHA_MIN, C.SALIENCY_ALPHA_MAX)
        if self._last_bgr is not None:
            self.update_saliency(self._last_bgr)

    def set_composition_guide(self, guide: str):
        # 無効値を避けるため safe_choice で正規化する。
        self._guide = safe_choice(guide, C.COMPOSITION_GUIDES, C.DEFAULT_COMPOSITION_GUIDE)
        if self._last_bgr is not None:
            self.update_saliency(self._last_bgr)

    def _compute_spectral_saliency_opencv(self, bgr: np.ndarray) -> Optional[np.ndarray]:
        # OpenCV contrib がある環境では SpectralResidual 実装を優先利用する。
        if not self._sr_detector_ready:
            self._sr_detector_ready = True
            try:
                if hasattr(cv2, "saliency") and hasattr(
                    cv2.saliency, "StaticSaliencySpectralResidual_create"
                ):
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
        # 互換経路: FFTベースでスペクトル残差を自前計算する。
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        h, w = gray.shape[:2]
        long_side = max(h, w)
        target_long = 192
        scale = min(1.0, float(target_long) / float(long_side))
        if scale < 1.0:
            # 解析用長辺を抑えて処理時間を安定させる。
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
        # OpenCV実装が使えない場合はFFT実装へフォールバック。
        sal = self._compute_spectral_saliency_opencv(bgr)
        if sal is None:
            sal = self._compute_spectral_saliency_fft(bgr)
        return normalize_map(sal)

    def _make_overlay_bgra(self, saliency: np.ndarray) -> np.ndarray:
        # サリエンシー強度を疑似カラー(BGR) + αチャンネルへ変換する。
        sal_u8 = np.clip(np.round(saliency * 255.0), 0, 255).astype(np.uint8)
        heat_bgr = cv2.applyColorMap(sal_u8, cv2.COLORMAP_JET)
        alpha = np.clip(np.round(saliency * (self._overlay_alpha / 100.0) * 255.0), 0, 255).astype(
            np.uint8
        )
        return np.dstack([heat_bgr, alpha])

    def _processing_long_edge(self) -> int:
        # 表示サイズ相当までで解析すれば、見た目を保ったまま負荷を抑えられる。
        target = max(1, self.width(), self.height())
        return clamp_int(target, 160, 960)

    def update_saliency(self, bgr: np.ndarray):
        if not self._set_last_bgr(bgr):
            return

        # サリエンシーは表示用のため、表示相当解像度で処理して負荷を削減する。
        proc_bgr = resize_by_long_edge(bgr, self._processing_long_edge())
        try:
            saliency = self._compute_saliency(proc_bgr)
        except Exception:
            # 稀な演算エラー時も描画不能にしない。
            saliency = normalize_map(self._compute_spectral_saliency_fft(proc_bgr))

        self._last_saliency = saliency
        self._last_overlay_bgra = self._make_overlay_bgra(saliency)

        overlay_bgr = self._last_overlay_bgra[:, :, :3].astype(np.float32)
        alpha = (self._last_overlay_bgra[:, :, 3].astype(np.float32) / 255.0)[:, :, None]
        # 元画像をグレースケール化して残差を見やすくする
        gray = cv2.cvtColor(proc_bgr, cv2.COLOR_BGR2GRAY)
        base = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR).astype(np.float32)
        view_bgr = np.clip(base * (1.0 - alpha) + overlay_bgr * alpha, 0, 255).astype(np.uint8)
        view_bgr = _apply_composition_guides(view_bgr, self._guide)

        view_rgb = cv2.cvtColor(view_bgr, cv2.COLOR_BGR2RGB)
        pm = rgb_to_qpixmap(view_rgb, max_w=self.width(), max_h=self.height())
        self.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rerender_on_resize(self.update_saliency)
