"""スクイント表示の純粋計算 helper。"""

import cv2
import numpy as np

from ..util import constants as C
from ..util.image_ops import clamp_render_size
from ..util.value_utils import clamp_float, clamp_int, safe_choice


def fit_image_to_bounds(
    width: int,
    height: int,
    *,
    max_width: int,
    max_height: int,
) -> tuple[int, int]:
    """画像を表示領域へ収める描画サイズを返す。"""
    src_w = max(1, int(width))
    src_h = max(1, int(height))
    bound_w, bound_h = clamp_render_size(max_width, max_height)
    scale = min(bound_w / float(src_w), bound_h / float(src_h))
    return (
        max(1, int(round(src_w * scale))),
        max(1, int(round(src_h * scale))),
    )


def _resize_image(img: np.ndarray, width: int, height: int) -> np.ndarray:
    """拡大縮小方向に応じた補間で画像サイズを変更する。"""
    src = np.asarray(img)
    dst_w = max(1, int(width))
    dst_h = max(1, int(height))
    src_h, src_w = src.shape[:2]
    if src_w == dst_w and src_h == dst_h:
        return src
    shrinking = dst_w < src_w or dst_h < src_h
    interpolation = cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR
    return cv2.resize(src, (dst_w, dst_h), interpolation=interpolation)


def _apply_scale_step(img: np.ndarray, *, scale_percent: int) -> np.ndarray:
    """描画サイズ基準の縮小 -> 再拡大を適用する。"""
    src = np.asarray(img)
    ratio = float(
        clamp_int(scale_percent, C.SQUINT_SCALE_PERCENT_MIN, C.SQUINT_SCALE_PERCENT_MAX)
    ) / 100.0
    if ratio >= 0.999:
        return src.copy()
    src_h, src_w = src.shape[:2]
    small_w = max(1, int(round(src_w * ratio)))
    small_h = max(1, int(round(src_h * ratio)))
    if small_w == src_w and small_h == src_h:
        return src.copy()
    small = cv2.resize(src, (small_w, small_h), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (src_w, src_h), interpolation=cv2.INTER_LINEAR)


def _apply_blur_step(img: np.ndarray, *, blur_sigma: float) -> np.ndarray:
    """描画サイズ基準のガウシアンぼかしを適用する。"""
    sigma = clamp_float(blur_sigma, C.SQUINT_BLUR_SIGMA_MIN, C.SQUINT_BLUR_SIGMA_MAX)
    if sigma <= 0.001:
        return np.asarray(img)
    return cv2.GaussianBlur(np.asarray(img), (0, 0), sigmaX=sigma, sigmaY=sigma)


def render_squint_frame(
    bgr: np.ndarray,
    *,
    mode: str,
    scale_percent: int,
    blur_sigma: float,
    target_width: int,
    target_height: int,
) -> np.ndarray:
    """現在の表示サイズ基準でスクイント描画用フレームを返す。"""
    src = np.asarray(bgr)
    render_w, render_h = fit_image_to_bounds(
        int(src.shape[1]),
        int(src.shape[0]),
        max_width=target_width,
        max_height=target_height,
    )
    base = _resize_image(src, render_w, render_h)

    squint_mode = safe_choice(mode, C.SQUINT_MODES, C.DEFAULT_SQUINT_MODE)
    if squint_mode == C.SQUINT_MODE_BLUR:
        return _apply_blur_step(base, blur_sigma=blur_sigma)
    if squint_mode == C.SQUINT_MODE_SCALE:
        return _apply_scale_step(base, scale_percent=scale_percent)
    return _apply_blur_step(
        _apply_scale_step(base, scale_percent=scale_percent),
        blur_sigma=blur_sigma,
    )
