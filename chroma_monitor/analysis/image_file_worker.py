"""画像ファイル単発解析ワーカー。"""

import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal

from .frame_analysis import analyze_bgr_frame
from ..util.image_inputs import load_image_path_to_bgr


class ImageFileAnalyzeWorker(QObject):
    """画像読み込み解析を別スレッドで実行するワーカー。"""

    progress = Signal(int, str)
    finished = Signal(dict)
    failed = Signal(str)
    canceled = Signal()

    def __init__(
        self,
        path: str | None,
        sample_points: int,
        wheel_sat_threshold: int,
        color_band_sat_threshold: int,
        max_dim: int,
        source_bgr: np.ndarray | None = None,
    ):
        """解析対象画像と解析パラメータを保持してワーカーを初期化する。"""
        super().__init__()
        self.path = "" if path is None else str(path)
        self.sample_points = int(sample_points)
        self.wheel_sat_threshold = int(wheel_sat_threshold)
        self.color_band_sat_threshold = int(color_band_sat_threshold)
        self.max_dim = int(max_dim)
        self.source_bgr = None if source_bgr is None else np.ascontiguousarray(source_bgr)
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

        if self.source_bgr is not None:
            bgr = np.ascontiguousarray(self.source_bgr)
            if bgr.size == 0:
                self.failed.emit("画像データの取得に失敗しました。")
                return None
            return bgr

        bgr = load_image_path_to_bgr(self.path)
        if bgr is None or bgr.size == 0:
            self.failed.emit("画像ファイルを読み込めませんでした。")
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

    def _analyze_loaded_bgr(self, bgr: np.ndarray, *, max_dim: int) -> dict | None:
        """読み込み済みBGR画像を解析して結果辞書を返す。"""
        t0 = time.perf_counter()
        res = analyze_bgr_frame(
            bgr=bgr,
            sample_points=self.sample_points,
            wheel_sat_threshold=self.wheel_sat_threshold,
            color_band_sat_threshold=self.color_band_sat_threshold,
            max_dim=int(max_dim),
            progress_cb=self._emit_progress,
            cancel_cb=self._is_canceled,
        )
        if res is None:
            self._emit_canceled()
            return None
        res["dt_ms"] = (time.perf_counter() - t0) * 1000.0
        return res

    def run(self):
        """画像読み込みから解析実行までの単発ジョブを処理する。"""
        try:
            bgr = self._load_input_bgr()
            if bgr is None:
                return

            self._emit_input_info_progress(bgr)
            if self._is_canceled_and_emit():
                return

            analysis_max_dim = int(self.max_dim)
            if analysis_max_dim > 0:
                self._emit_progress(10, f"解析解像度: 長辺 {analysis_max_dim}px")
            else:
                self._emit_progress(10, "解析解像度: オリジナル")
            if self._is_canceled_and_emit():
                return
            res = self._analyze_loaded_bgr(bgr, max_dim=analysis_max_dim)
            if res is None:
                return

            self._emit_progress(100, "解析完了")
            if self._is_canceled_and_emit():
                return
            self.finished.emit(res)
        except Exception:
            self.failed.emit("画像解析に失敗しました。")
