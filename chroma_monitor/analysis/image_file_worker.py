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

    def __init__(
        self,
        path: str,
        sample_points: int,
        wheel_sat_threshold: int,
        color_band_sat_threshold: int,
    ):
        """解析対象画像と解析パラメータを保持してワーカーを初期化する。"""
        super().__init__()
        self.path = str(path)
        self.sample_points = int(sample_points)
        self.wheel_sat_threshold = int(wheel_sat_threshold)
        self.color_band_sat_threshold = int(color_band_sat_threshold)
        self._cancel = threading.Event()

    def request_cancel(self):
        """実行中ジョブへキャンセル要求を通知する。"""
        # キャンセルは排他不要のイベントフラグで通知する。
        self._cancel.set()

    def _is_canceled(self) -> bool:
        """キャンセル要求が入っているかを返す。"""
        return self._cancel.is_set()

    def _emit_progress(self, percent: int, text: str):
        """進捗通知シグナルを送出する。"""
        self.progress.emit(int(percent), text)

    def _emit_canceled(self) -> None:
        """キャンセル完了シグナルを送出する。"""
        self.canceled.emit()

    def _is_canceled_and_emit(self) -> bool:
        """キャンセル要求を検出したら通知し、True を返す。"""
        if not self._is_canceled():
            return False
        self._emit_canceled()
        return True

    def _load_input_bgr(self) -> np.ndarray | None:
        """入力ファイルを読み込み、BGR配列へデコードして返す。"""
        self._emit_progress(1, "画像を読み込み中…")
        if self._is_canceled_and_emit():
            return None

        # OpenCVの日本語パス対応のため、imdecode経路で読み込む。
        buf = np.fromfile(self.path, dtype=np.uint8)
        if buf.size == 0:
            self.failed.emit("画像ファイルを読み込めませんでした。")
            return None
        bgr = self._decode_to_bgr_preserve_depth(buf)
        if bgr is None or bgr.size == 0:
            self.failed.emit("画像データのデコードに失敗しました。")
            return None
        return bgr

    def _emit_input_info_progress(self, bgr: np.ndarray) -> None:
        """入力画像の寸法/ビット深度情報を進捗表示へ反映する。"""
        h_img, w_img = bgr.shape[:2]
        if np.issubdtype(bgr.dtype, np.integer):
            bit_depth = bgr.dtype.itemsize * 8
            self._emit_progress(8, f"解析準備中… ({w_img}x{h_img}, {bit_depth}bit)")
            return
        self._emit_progress(8, f"解析準備中… ({w_img}x{h_img})")

    def _resolve_auto_max_dim(self, bgr: np.ndarray) -> int | None:
        """自動解析長辺を決定し、必要なら進捗へ通知する。"""
        auto_max_dim = self._auto_analysis_max_dim(bgr)
        if auto_max_dim > 0:
            self._emit_progress(
                10,
                f"大きい画像のため内部解析を長辺{auto_max_dim}pxに調整します…",
            )
            if self._is_canceled_and_emit():
                return None
        return int(auto_max_dim)

    def _analyze_loaded_bgr(self, bgr: np.ndarray, *, auto_max_dim: int) -> dict | None:
        """読み込み済みBGR画像を解析して結果辞書を返す。"""
        t0 = time.perf_counter()
        res = analyze_bgr_frame(
            bgr=bgr,
            sample_points=self.sample_points,
            wheel_sat_threshold=self.wheel_sat_threshold,
            color_band_sat_threshold=self.color_band_sat_threshold,
            max_dim=int(auto_max_dim),
            progress_cb=self._emit_progress,
            cancel_cb=self._is_canceled,
        )
        if res is None:
            self._emit_canceled()
            return None
        res["dt_ms"] = (time.perf_counter() - t0) * 1000.0
        return res

    @staticmethod
    def _decode_to_bgr_preserve_depth(buf: np.ndarray) -> Optional[np.ndarray]:
        """デコード結果をBGR 3chへ正規化して返す。"""
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
        """画像サイズに応じて自動縮小の長辺上限を決定する。"""
        # 画像読み込み時は高解像度を優先しつつ、極端な大画像のみ内部で上限を掛ける。
        if bgr is None or bgr.size == 0:
            return 0
        h, w = bgr.shape[:2]
        long_edge = max(int(h), int(w))
        if long_edge <= int(_IMAGE_FILE_ANALYSIS_AUTO_MAX_DIM):
            return 0
        return int(_IMAGE_FILE_ANALYSIS_AUTO_MAX_DIM)

    def run(self):
        """画像読み込みから解析実行までの単発ジョブを処理する。"""
        try:
            bgr = self._load_input_bgr()
            if bgr is None:
                return

            self._emit_input_info_progress(bgr)
            if self._is_canceled_and_emit():
                return

            auto_max_dim = self._resolve_auto_max_dim(bgr)
            if auto_max_dim is None:
                return
            res = self._analyze_loaded_bgr(bgr, auto_max_dim=auto_max_dim)
            if res is None:
                return

            self._emit_progress(100, "解析完了")
            if self._is_canceled_and_emit():
                return
            self.finished.emit(res)
        except Exception:
            self.failed.emit("画像解析に失敗しました。")
