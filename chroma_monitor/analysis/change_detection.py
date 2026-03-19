"""差分更新モード用の純粋計算補助。"""

from typing import Optional

import cv2
import numpy as np

from ..util.image_ops import resize_by_long_edge


def prepare_change_detection_channels(
    bgr: np.ndarray,
    *,
    detect_dim: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """差分判定用に縮小した HSV 各チャネルビューを返す。"""
    detect_bgr = resize_by_long_edge(bgr, int(detect_dim))
    detect_hsv = cv2.cvtColor(detect_bgr, cv2.COLOR_BGR2HSV)
    return detect_hsv[:, :, 0], detect_hsv[:, :, 1], detect_hsv[:, :, 2]


def compute_change_metric(
    dh: np.ndarray,
    ds: np.ndarray,
    dv: np.ndarray,
    *,
    prev_h: Optional[np.ndarray],
    prev_s: Optional[np.ndarray],
    prev_v: Optional[np.ndarray],
    hue_wrap_buf: Optional[np.ndarray],
) -> tuple[float, Optional[np.ndarray]]:
    """前回との差分量を1つのスカラー値へ集約し、再利用バッファも返す。"""
    if prev_h is None or prev_s is None or prev_v is None:
        return 0.0, hue_wrap_buf

    hue_diff = cv2.absdiff(dh, prev_h)
    hue_wrap = hue_wrap_buf
    if hue_wrap is None or hue_wrap.shape != hue_diff.shape:
        hue_wrap = np.empty_like(hue_diff)
    np.subtract(180, hue_diff, out=hue_wrap, casting="unsafe")
    np.minimum(hue_diff, hue_wrap, out=hue_diff)
    sat_diff = cv2.absdiff(ds, prev_s)
    val_diff = cv2.absdiff(dv, prev_v)
    metric = (
        float(cv2.mean(hue_diff)[0])
        + float(cv2.mean(sat_diff)[0]) * 0.5
        + float(cv2.mean(val_diff)[0]) * 0.5
    )
    return metric, hue_wrap
