"""画像ファイル単発解析ワーカー。"""

import threading
import time
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QObject, Signal

from .frame_analysis import analyze_bgr_frame

_IMAGE_FILE_ANALYSIS_AUTO_MAX_DIM = 3072


class ImageFileAnalyzeWorker(QObject):
    """画像読み込み解析を別スレッドで実行するワーカー。"""

    progress = Signal(int, str)
    finished = Signal(dict)
    failed = Signal(str)
    canceled = Signal()

    def __init__(self, path: str, sample_points: int, wheel_sat_threshold: int):
        super().__init__()
        self.path = str(path)
        self.sample_points = int(sample_points)
        self.wheel_sat_threshold = int(wheel_sat_threshold)
        self._cancel = threading.Event()

    def request_cancel(self):
        # キャンセルは排他不要のイベントフラグで通知する。
        self._cancel.set()

    def _is_canceled(self) -> bool:
        return self._cancel.is_set()

    def _emit_progress(self, percent: int, text: str):
        self.progress.emit(int(percent), text)

    @staticmethod
    def _decode_to_bgr_preserve_depth(buf: np.ndarray) -> Optional[np.ndarray]:
        img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        if img is None or img.size == 0:
            return None
        if img.ndim == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.ndim != 3:
            return None
        channels = int(img.shape[2])
        if channels == 3:
            return img
        if channels == 4:
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        if channels == 1:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        return None

    @staticmethod
    def _auto_analysis_max_dim(bgr: np.ndarray) -> int:
        # 画像読み込み時は高解像度を優先しつつ、極端な大画像のみ内部で上限を掛ける。
        if bgr is None or bgr.size == 0:
            return 0
        h, w = bgr.shape[:2]
        long_edge = max(int(h), int(w))
        if long_edge <= int(_IMAGE_FILE_ANALYSIS_AUTO_MAX_DIM):
            return 0
        return int(_IMAGE_FILE_ANALYSIS_AUTO_MAX_DIM)

    def run(self):
        try:
            # OpenCVの日本語パス対応のため、imdecode経路で読み込む。
            self._emit_progress(1, "画像を読み込み中…")
            if self._is_canceled():
                self.canceled.emit()
                return

            buf = np.fromfile(self.path, dtype=np.uint8)
            if buf.size == 0:
                self.failed.emit("画像ファイルを読み込めませんでした。")
                return
            bgr = self._decode_to_bgr_preserve_depth(buf)
            if bgr is None or bgr.size == 0:
                self.failed.emit("画像データのデコードに失敗しました。")
                return

            h_img, w_img = bgr.shape[:2]
            if np.issubdtype(bgr.dtype, np.integer):
                bit_depth = bgr.dtype.itemsize * 8
                self._emit_progress(8, f"解析準備中… ({w_img}x{h_img}, {bit_depth}bit)")
            else:
                self._emit_progress(8, f"解析準備中… ({w_img}x{h_img})")
            if self._is_canceled():
                self.canceled.emit()
                return

            auto_max_dim = self._auto_analysis_max_dim(bgr)
            if auto_max_dim > 0:
                self._emit_progress(
                    10,
                    f"大きい画像のため内部解析を長辺{auto_max_dim}pxに調整します…",
                )
                if self._is_canceled():
                    self.canceled.emit()
                    return

            t0 = time.perf_counter()
            res = analyze_bgr_frame(
                bgr=bgr,
                sample_points=self.sample_points,
                wheel_sat_threshold=self.wheel_sat_threshold,
                max_dim=auto_max_dim,
                progress_cb=self._emit_progress,
                cancel_cb=self._is_canceled,
            )
            if res is None:
                self.canceled.emit()
                return
            res["dt_ms"] = (time.perf_counter() - t0) * 1000.0

            self._emit_progress(100, "解析完了")
            if self._is_canceled():
                self.canceled.emit()
                return
            self.finished.emit(res)
        except Exception:
            self.failed.emit("画像解析に失敗しました。")
