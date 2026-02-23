"""ビュー描画に関する処理。"""

import numpy as np


def normalize_map(src: np.ndarray) -> np.ndarray:
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
