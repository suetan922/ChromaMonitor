"""1フレーム分のキャプチャ矩形解決と切り出し補助。"""

from collections.abc import Callable
from typing import Optional

import cv2
import mss
import numpy as np
from PySide6.QtCore import QRect


def compute_capture_rect(
    *,
    target_hwnd: Optional[int],
    roi_rel: Optional[QRect],
    roi_abs: Optional[QRect],
    get_window_rect_fn: Callable[[int], Optional[QRect]],
) -> Optional[QRect]:
    """現在設定から実キャプチャに使う矩形を解決する。"""
    if target_hwnd is not None:
        wrect = get_window_rect_fn(target_hwnd)
        if wrect is None:
            return None
        if roi_rel is None:
            return wrect
        return QRect(
            wrect.left() + roi_rel.left(),
            wrect.top() + roi_rel.top(),
            roi_rel.width(),
            roi_rel.height(),
        )
    return roi_abs


def capture_target_window_region(
    *,
    target_hwnd: Optional[int],
    roi_rel: Optional[QRect],
    get_window_rect_fn: Callable[[int], Optional[QRect]],
    capture_window_bgr_fn: Callable[[int], Optional[np.ndarray]],
) -> tuple[Optional[np.ndarray], Optional[QRect]]:
    """対象ウィンドウ画像から ROI 相当領域を切り出して返す。"""
    if target_hwnd is None:
        return None, None
    wrect = get_window_rect_fn(target_hwnd)
    if wrect is None:
        return None, None
    full = capture_window_bgr_fn(target_hwnd)
    if full is None:
        return None, None

    if roi_rel is None:
        return full, wrect

    full_h, full_w = full.shape[:2]
    ww = max(1, int(wrect.width()))
    wh = max(1, int(wrect.height()))
    sx = float(full_w) / float(ww)
    sy = float(full_h) / float(wh)
    x = max(0, int(round(float(roi_rel.left()) * sx)))
    y = max(0, int(round(float(roi_rel.top()) * sy)))
    w = max(1, int(round(float(roi_rel.width()) * sx)))
    h = max(1, int(round(float(roi_rel.height()) * sy)))
    if x + w > full_w:
        w = max(1, full_w - x)
    if y + h > full_h:
        h = max(1, full_h - y)
    if w <= 1 or h <= 1:
        return None, None
    crop = full[y : y + h, x : x + w]
    cap = QRect(
        wrect.left() + int(roi_rel.left()),
        wrect.top() + int(roi_rel.top()),
        int(roi_rel.width()),
        int(roi_rel.height()),
    )
    return crop, cap


def capture_screen_region(
    sct,
    cap: Optional[QRect],
) -> tuple[Optional[np.ndarray], Optional[QRect], Optional[str]]:
    """画面領域キャプチャを実行し、画像と実キャプチャ矩形を返す。"""
    vmon = sct.monitors[0]
    if cap is None:
        return None, None, "キャプチャ領域を選択してください"

    left = max(cap.left(), vmon["left"])
    top = max(cap.top(), vmon["top"])
    right = min(cap.left() + cap.width(), vmon["left"] + vmon["width"])
    bottom = min(cap.top() + cap.height(), vmon["top"] + vmon["height"])
    width = right - left
    height = bottom - top
    if width <= 1 or height <= 1:
        return None, None, "領域が画面外です（範囲を選び直してください）"

    monitor = {
        "left": int(left),
        "top": int(top),
        "width": int(width),
        "height": int(height),
    }
    try:
        img = np.asarray(sct.grab(monitor), dtype=np.uint8)
    except mss.exception.ScreenShotError:
        return None, None, "画面キャプチャに失敗しました（権限/表示/Wayland設定を確認）"
    bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return bgr, QRect(int(left), int(top), int(width), int(height)), None
