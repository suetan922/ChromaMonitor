import threading
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import mss
import numpy as np
from PySide6.QtCore import QObject, QPoint, QRect, Signal
from PySide6.QtGui import QGuiApplication

from .analysis.frame_analysis import (
    _compute_top_colors,
    _compute_warm_cool_ratios,
    _compute_wheel_histogram,
    _sample_sv_and_rgb,
    analyze_bgr_frame,
)
from .capture.win32_windows import HAS_WIN32, ctypes_win_api, win32gui
from .util import constants as C
from .util.functions import clamp_int, resize_by_long_edge

_ctypes_win = ctypes_win_api
_EMPTY_GRAPH_DATA = {
    "hist": None,
    "sv": None,
    "rgb": None,
    "h_hist": None,
    "s_hist": None,
    "v_hist": None,
    "top_colors": None,
    "warm_ratio": 0.0,
    "cool_ratio": 0.0,
    "other_ratio": 0.0,
}


class ImageFileAnalyzeWorker(QObject):
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
        """Decode image bytes while preserving source depth/channels as much as possible."""
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
        if long_edge <= int(C.IMAGE_FILE_ANALYSIS_AUTO_MAX_DIM):
            return 0
        return int(C.IMAGE_FILE_ANALYSIS_AUTO_MAX_DIM)

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


@dataclass
class AnalyzerConfig:
    interval_sec: float = C.DEFAULT_INTERVAL_SEC
    sample_points: int = C.DEFAULT_SAMPLE_POINTS
    max_dim: int = C.ANALYZER_MAX_DIM
    wheel_sat_threshold: int = C.DEFAULT_WHEEL_SAT_THRESHOLD
    graph_every: int = C.ANALYZER_MIN_GRAPH_EVERY
    mode: str = C.DEFAULT_MODE
    diff_threshold: float = C.DEFAULT_DIFF_THRESHOLD
    stable_frames: int = C.DEFAULT_STABLE_FRAMES
    view_color: bool = True
    view_scatter: bool = True
    view_hsv_hist: bool = True
    view_image: bool = True
    want_preview: bool = False


class AnalyzerWorker(QObject):
    resultReady = Signal(dict)
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self.cfg = AnalyzerConfig()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # UIスレッドが処理しきれないとキューが肥大化するため、未処理フレームは1件までに制限
        self._result_inflight = threading.Event()

        self.target_hwnd: Optional[int] = None
        self.roi_rel: Optional[QRect] = None
        self.roi_abs: Optional[QRect] = None  # set later
        self._frame = 0

        # changeトリガーモード用の履歴
        self._prev_h: Optional[np.ndarray] = None
        self._prev_s: Optional[np.ndarray] = None
        self._prev_v: Optional[np.ndarray] = None
        self._stable_frames: int = 0
        self._was_stable: bool = False
        self._cooldown_until: float = 0.0
        self._force_emit_once: bool = False

    def _reset_change_state(self, emit_once: bool = False):
        # changeモードの履歴を初期化する。
        self._prev_h = None
        self._prev_s = None
        self._prev_v = None
        self._stable_frames = 0
        self._was_stable = False
        self._cooldown_until = 0.0
        if emit_once:
            self._force_emit_once = True

    def start(self):
        # 既に稼働中なら二重起動しない。
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._result_inflight.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.status.emit("計測開始")

    def stop(self):
        # 停止要求は次ループで反映される。
        self._stop.set()
        self._result_inflight.clear()
        self.status.emit("停止")

    def mark_result_consumed(self):
        self._result_inflight.clear()

    def set_interval(self, sec: float):
        self.cfg.interval_sec = max(C.ANALYZER_MIN_INTERVAL_SEC, float(sec))

    def set_sample_points(self, n: int):
        self.cfg.sample_points = clamp_int(
            n, C.ANALYZER_MIN_SAMPLE_POINTS, C.ANALYZER_MAX_SAMPLE_POINTS
        )

    def set_max_dim(self, n: int):
        n = int(n)
        if n <= 0:
            # 0 はオリジナル解像度（縮小なし）として扱う
            self.cfg.max_dim = 0
            return
        self.cfg.max_dim = clamp_int(n, C.ANALYZER_MAX_DIM_MIN, C.ANALYZER_MAX_DIM_MAX)

    def set_wheel_sat_threshold(self, n: int):
        self.cfg.wheel_sat_threshold = clamp_int(
            n, C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX
        )

    def set_graph_every(self, n: int):
        self.cfg.graph_every = max(C.ANALYZER_MIN_GRAPH_EVERY, int(n))

    def set_mode(self, mode: str):
        self.cfg.mode = mode if mode in C.UPDATE_MODES else C.DEFAULT_MODE
        # モード切替時は差分検知用の状態をリセット
        self._reset_change_state()

    def set_diff_threshold(self, th: float):
        self.cfg.diff_threshold = max(C.ANALYZER_MIN_DIFF_THRESHOLD, float(th))

    def set_stable_frames(self, n: int):
        self.cfg.stable_frames = max(C.ANALYZER_MIN_STABLE_FRAMES, int(n))

    def set_view_flags(
        self,
        color: Optional[bool] = None,
        scatter: Optional[bool] = None,
        hsv_hist: Optional[bool] = None,
        image: Optional[bool] = None,
        preview: Optional[bool] = None,
    ):
        if color is not None:
            self.cfg.view_color = bool(color)
        if scatter is not None:
            self.cfg.view_scatter = bool(scatter)
        if hsv_hist is not None:
            self.cfg.view_hsv_hist = bool(hsv_hist)
        if image is not None:
            self.cfg.view_image = bool(image)
        if preview is not None:
            self.cfg.want_preview = bool(preview)

    def set_target_window(self, hwnd: Optional[int]):
        # 取得対象切替時は差分履歴を捨てて誤判定を避ける。
        self.target_hwnd = hwnd
        self._reset_change_state(emit_once=True)

    def set_roi_in_window(self, roi_rel: Optional[QRect]):
        self.roi_rel = roi_rel
        self._reset_change_state(emit_once=True)

    def set_roi_on_screen(self, roi_abs: Optional[QRect]):
        if roi_abs is None:
            self.roi_abs = None
            self._reset_change_state(emit_once=True)
            return
        # Qtの論理座標からmssが扱う物理座標へ変換して保持する
        self.roi_abs = self._logical_rect_to_native(roi_abs)
        self._reset_change_state(emit_once=True)

    def _get_window_rect(self, hwnd: int) -> Optional[QRect]:
        if not HAS_WIN32:
            return None
        try:
            left = top = right = bottom = None
            if win32gui:
                try:
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                except Exception:
                    pass
            if (left is None or right is None or bottom is None) and _ctypes_win:
                import ctypes
                from ctypes import wintypes

                rect = wintypes.RECT()
                if not _ctypes_win["GetWindowRect"](hwnd, ctypes.byref(rect)):
                    return None
                left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            if left is None or top is None or right is None or bottom is None:
                return None
            if right - left <= 0 or bottom - top <= 0:
                return None
            return QRect(left, top, right - left, bottom - top)
        except Exception:
            return None

    def _is_window_minimized(self, hwnd: int) -> bool:
        if not HAS_WIN32:
            return False
        try:
            if win32gui:
                return win32gui.IsIconic(hwnd)
            if _ctypes_win:
                return bool(_ctypes_win["IsIconic"](hwnd))
            return False
        except Exception:
            return False

    def _build_screen_monitor_map(self):
        # Qt画面情報（論理座標）と mss 画面情報（物理座標）を近似マッチングする。
        qt_screens = QGuiApplication.screens()
        if not qt_screens:
            return {}

        try:
            with mss.mss() as sct:
                native_monitors = [m for m in sct.monitors[1:]]
        except Exception:
            native_monitors = []

        if not native_monitors:
            return {}

        qt_infos = []
        for screen in qt_screens:
            g = screen.geometry()
            qt_infos.append(
                {
                    "screen": screen,
                    "rect": g,
                    "dpr": max(0.5, float(screen.devicePixelRatio())),
                }
            )

        q_left = min(info["rect"].left() for info in qt_infos)
        q_top = min(info["rect"].top() for info in qt_infos)
        q_right = max(info["rect"].left() + info["rect"].width() for info in qt_infos)
        q_bottom = max(info["rect"].top() + info["rect"].height() for info in qt_infos)
        q_w = max(1.0, float(q_right - q_left))
        q_h = max(1.0, float(q_bottom - q_top))

        m_left = min(m["left"] for m in native_monitors)
        m_top = min(m["top"] for m in native_monitors)
        m_right = max(m["left"] + m["width"] for m in native_monitors)
        m_bottom = max(m["top"] + m["height"] for m in native_monitors)
        m_w = max(1.0, float(m_right - m_left))
        m_h = max(1.0, float(m_bottom - m_top))

        pairs = []
        for qi, q in enumerate(qt_infos):
            qrect = q["rect"]
            qw = max(1.0, float(qrect.width()))
            qh = max(1.0, float(qrect.height()))
            qcx = qrect.left() + qw * 0.5
            qcy = qrect.top() + qh * 0.5
            qx_norm = (qcx - q_left) / q_w
            qy_norm = (qcy - q_top) / q_h
            for mi, mon in enumerate(native_monitors):
                sx = float(mon["width"]) / qw
                sy = float(mon["height"]) / qh
                mcx = mon["left"] + mon["width"] * 0.5
                mcy = mon["top"] + mon["height"] * 0.5
                mx_norm = (mcx - m_left) / m_w
                my_norm = (mcy - m_top) / m_h

                score = (
                    abs(sx - sy) * 300.0
                    + abs(sx - q["dpr"]) * 80.0
                    + abs(sy - q["dpr"]) * 80.0
                    + abs(qx_norm - mx_norm) * 60.0
                    + abs(qy_norm - my_norm) * 60.0
                )
                pairs.append((score, qi, mi))

        pairs.sort(key=lambda x: x[0])
        used_q = set()
        used_m = set()
        mapping = {}
        for _score, qi, mi in pairs:
            if qi in used_q or mi in used_m:
                continue
            used_q.add(qi)
            used_m.add(mi)
            mapping[qt_infos[qi]["screen"]] = native_monitors[mi]

        # 万一マッチしなかった画面は index 順で補完
        for i, info in enumerate(qt_infos):
            if info["screen"] in mapping:
                continue
            fallback = native_monitors[min(i, len(native_monitors) - 1)]
            mapping[info["screen"]] = fallback
        return mapping

    def _logical_point_to_native(self, x: float, y: float, mapping) -> tuple[float, float]:
        # 入力点がどの screen に属するかを判定して物理座標へ変換する。
        screen = QGuiApplication.screenAt(QPoint(int(round(x)), int(round(y))))
        if screen is None:
            screens = QGuiApplication.screens()
            screen = screens[0] if screens else None
        mon = mapping.get(screen) if screen is not None else None
        if screen is None or mon is None:
            return float(x), float(y)

        g = screen.geometry()
        gw = max(1.0, float(g.width()))
        gh = max(1.0, float(g.height()))
        sx = float(mon["width"]) / gw
        sy = float(mon["height"]) / gh
        nx = float(mon["left"]) + (float(x) - float(g.left())) * sx
        ny = float(mon["top"]) + (float(y) - float(g.top())) * sy
        return nx, ny

    def _native_point_to_logical(self, x: float, y: float, mapping) -> tuple[float, float]:
        # 物理座標点を、対応するQt画面の論理座標へ逆変換する。
        target_screen = None
        target_mon = None
        for screen, mon in mapping.items():
            left = float(mon["left"])
            top = float(mon["top"])
            right = left + float(mon["width"])
            bottom = top + float(mon["height"])
            if left <= float(x) < right and top <= float(y) < bottom:
                target_screen = screen
                target_mon = mon
                break

        if target_screen is None or target_mon is None:
            # どのモニタにも含まれないときは中心距離が最短のモニタを使う。
            best = None
            best_dist = None
            for screen, mon in mapping.items():
                cx = float(mon["left"]) + float(mon["width"]) * 0.5
                cy = float(mon["top"]) + float(mon["height"]) * 0.5
                dist = (float(x) - cx) ** 2 + (float(y) - cy) ** 2
                if best is None or (best_dist is not None and dist < best_dist):
                    best = (screen, mon)
                    best_dist = dist
            if best is None:
                return float(x), float(y)
            target_screen, target_mon = best

        g = target_screen.geometry()
        mw = max(1.0, float(target_mon["width"]))
        mh = max(1.0, float(target_mon["height"]))
        lx = float(g.left()) + (float(x) - float(target_mon["left"])) * (float(g.width()) / mw)
        ly = float(g.top()) + (float(y) - float(target_mon["top"])) * (float(g.height()) / mh)
        return lx, ly

    def _logical_rect_to_native(self, rect: QRect) -> QRect:
        # 論理矩形の四隅を物理座標へ写像して新しい矩形を作る。
        mapping = self._build_screen_monitor_map()
        if not mapping:
            return QRect(rect)

        x1, y1 = self._logical_point_to_native(float(rect.left()), float(rect.top()), mapping)
        x2, y2 = self._logical_point_to_native(
            float(rect.left() + rect.width()),
            float(rect.top() + rect.height()),
            mapping,
        )
        left = int(round(min(x1, x2)))
        top = int(round(min(y1, y2)))
        width = max(1, int(round(abs(x2 - x1))))
        height = max(1, int(round(abs(y2 - y1))))
        return QRect(left, top, width, height)

    def _native_rect_to_logical(self, rect: QRect) -> QRect:
        # 物理矩形の四隅を論理座標へ写像する（ROI選択UI境界の表示用途）。
        mapping = self._build_screen_monitor_map()
        if not mapping:
            return QRect(rect)

        x1, y1 = self._native_point_to_logical(float(rect.left()), float(rect.top()), mapping)
        x2, y2 = self._native_point_to_logical(
            float(rect.left() + rect.width()),
            float(rect.top() + rect.height()),
            mapping,
        )
        left = int(round(min(x1, x2)))
        top = int(round(min(y1, y2)))
        width = max(1, int(round(abs(x2 - x1))))
        height = max(1, int(round(abs(y2 - y1))))
        return QRect(left, top, width, height)

    def _compute_capture_rect(self) -> Optional[QRect]:
        # window モードでは roi_rel を window 座標系として解決する。
        if self.target_hwnd is not None:
            wrect = self._get_window_rect(self.target_hwnd)
            if wrect is None:
                return None
            if self.roi_rel is None:
                # ウィンドウ取得時にROI未指定ならウィンドウ全体を初期領域にする
                return wrect
            return QRect(
                wrect.left() + self.roi_rel.left(),
                wrect.top() + self.roi_rel.top(),
                self.roi_rel.width(),
                self.roi_rel.height(),
            )
        return self.roi_abs

    def _capture_window_bgr(self, hwnd: int) -> Optional[np.ndarray]:
        """Capture selected window content with PrintWindow (ignores overlap in many apps)."""
        if not HAS_WIN32:
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD),
                    ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            class BITMAPINFO(ctypes.Structure):
                _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

            BI_RGB = 0
            DIB_RGB_COLORS = 0
            PW_RENDERFULLCONTENT = 0x00000002

            wrect = self._get_window_rect(hwnd)
            if wrect is None:
                return None
            width = int(wrect.width())
            height = int(wrect.height())
            if width <= 1 or height <= 1:
                return None

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            hwnd_dc = user32.GetWindowDC(hwnd)
            if not hwnd_dc:
                return None
            mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            if not mem_dc:
                user32.ReleaseDC(hwnd, hwnd_dc)
                return None

            h_bitmap = None
            old_obj = None
            try:
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = width
                bmi.bmiHeader.biHeight = -height  # top-down
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = BI_RGB

                bits = ctypes.c_void_p()
                h_bitmap = gdi32.CreateDIBSection(
                    mem_dc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0
                )
                if not h_bitmap or not bits:
                    return None

                old_obj = gdi32.SelectObject(mem_dc, h_bitmap)
                ok = user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)
                if not ok:
                    ok = user32.PrintWindow(hwnd, mem_dc, 0)
                    if not ok:
                        return None

                size = width * height * 4
                buf = (ctypes.c_ubyte * size).from_address(bits.value)
                bgra = np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 4)).copy()
                return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)
            finally:
                if old_obj:
                    gdi32.SelectObject(mem_dc, old_obj)
                if h_bitmap:
                    gdi32.DeleteObject(h_bitmap)
                gdi32.DeleteDC(mem_dc)
                user32.ReleaseDC(hwnd, hwnd_dc)
        except Exception:
            return None

    def _capture_target_window_region(self) -> tuple[Optional[np.ndarray], Optional[QRect]]:
        if not HAS_WIN32 or self.target_hwnd is None:
            return None, None
        wrect = self._get_window_rect(self.target_hwnd)
        if wrect is None:
            return None, None
        full = self._capture_window_bgr(self.target_hwnd)
        if full is None:
            return None, None

        if self.roi_rel is None:
            return full, wrect

        # roi_rel はウィンドウ矩形座標系で保持し、実キャプチャ解像度との差はここで吸収する。
        full_h, full_w = full.shape[:2]
        ww = max(1, int(wrect.width()))
        wh = max(1, int(wrect.height()))
        sx = float(full_w) / float(ww)
        sy = float(full_h) / float(wh)
        x = max(0, int(round(float(self.roi_rel.left()) * sx)))
        y = max(0, int(round(float(self.roi_rel.top()) * sy)))
        w = max(1, int(round(float(self.roi_rel.width()) * sx)))
        h = max(1, int(round(float(self.roi_rel.height()) * sy)))
        if x + w > full_w:
            w = max(1, full_w - x)
        if y + h > full_h:
            h = max(1, full_h - y)
        if w <= 1 or h <= 1:
            return None, None
        crop = full[y : y + h, x : x + w]
        cap = QRect(
            wrect.left() + int(self.roi_rel.left()),
            wrect.top() + int(self.roi_rel.top()),
            int(self.roi_rel.width()),
            int(self.roi_rel.height()),
        )
        return crop, cap

    def _capture_screen_region(
        self, sct, cap: Optional[QRect]
    ) -> tuple[Optional[np.ndarray], Optional[QRect], Optional[str]]:
        vmon = sct.monitors[0]
        if cap is None:
            # 初回は画面中央に既定ROIを自動生成する。
            cw, ch = C.DEFAULT_ROI_SIZE
            cx = vmon["left"] + vmon["width"] // 2
            cy = vmon["top"] + vmon["height"] // 2
            cap = QRect(cx - cw // 2, cy - ch // 2, cw, ch)
            self.roi_abs = cap

        left = max(cap.left(), vmon["left"])
        top = max(cap.top(), vmon["top"])
        right = min(cap.left() + cap.width(), vmon["left"] + vmon["width"])
        bottom = min(cap.top() + cap.height(), vmon["top"] + vmon["height"])
        width = right - left
        height = bottom - top
        if width <= 1 or height <= 1:
            return None, None, "領域が画面外です（範囲を選び直してください）"

        mon = {
            "left": int(left),
            "top": int(top),
            "width": int(width),
            "height": int(height),
        }
        try:
            img = np.array(sct.grab(mon))
        except mss.exception.ScreenShotError:
            return None, None, "画面キャプチャに失敗しました（権限/表示/Wayland設定を確認）"
        bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return bgr, QRect(int(left), int(top), int(width), int(height)), None

    def capture_once(self) -> tuple[Optional[np.ndarray], Optional[QRect], Optional[str]]:
        """Capture one frame for preview without starting worker loop."""
        try:
            if self.target_hwnd is not None and HAS_WIN32:
                if self._is_window_minimized(self.target_hwnd):
                    return (
                        None,
                        None,
                        "ターゲットウィンドウが最小化されています（色を取得できません）",
                    )
                bgr, cap = self._capture_target_window_region()
                if bgr is None or cap is None:
                    return None, None, "選択ウィンドウのキャプチャに失敗しました"
                return bgr, cap, None

            with mss.mss() as sct:
                return self._capture_screen_region(sct, self._compute_capture_rect())
        except Exception:
            return None, None, "プレビュー取得に失敗しました"

    def _compute_change_metric(self, dh: np.ndarray, ds: np.ndarray, dv: np.ndarray) -> float:
        # 8bit配列同士の差分は cv2.absdiff で計算して一時配列の型変換を減らす。
        prev_h = self._prev_h
        prev_s = self._prev_s
        prev_v = self._prev_v
        if prev_h is None or prev_s is None or prev_v is None:
            return 0.0

        hue_diff = cv2.absdiff(dh, prev_h)
        hue_diff = np.minimum(hue_diff, 180 - hue_diff)
        sat_diff = cv2.absdiff(ds, prev_s)
        val_diff = cv2.absdiff(dv, prev_v)
        return (
            float(np.mean(hue_diff))
            + float(np.mean(sat_diff)) * 0.5
            + float(np.mean(val_diff)) * 0.5
        )

    def _should_emit_in_change_mode(self, bgr: np.ndarray, now: float) -> bool:
        # 差分判定は軽量化のため専用縮小サイズで行う。
        detect_bgr = resize_by_long_edge(bgr, C.ANALYZER_CHANGE_DETECT_DIM)
        detect_hsv = cv2.cvtColor(detect_bgr, cv2.COLOR_BGR2HSV)
        dh, ds, dv = cv2.split(detect_hsv)

        emit_now = now >= self._cooldown_until
        if (
            self._prev_h is None
            or self._prev_s is None
            or self._prev_v is None
            or self._prev_h.shape != dh.shape
            or self._prev_s.shape != ds.shape
            or self._prev_v.shape != dv.shape
        ):
            emit_now = False
            self._stable_frames = 0
            self._was_stable = False
        else:
            metric = self._compute_change_metric(dh, ds, dv)
            if metric < self.cfg.diff_threshold:
                self._stable_frames += 1
            else:
                self._stable_frames = 0
                self._was_stable = False
            emit_now = self._stable_frames >= self.cfg.stable_frames and not self._was_stable
            if emit_now:
                self._was_stable = True

        self._prev_h = dh
        self._prev_s = ds
        self._prev_v = dv
        if self._force_emit_once:
            self._force_emit_once = False
            emit_now = True
        return emit_now

    def _collect_graph_data(
        self,
        bgr: np.ndarray,
        need_color: bool,
        need_scatter: bool,
        need_hsv_hist: bool,
    ) -> dict:
        # 設定された解析上限（max_dim）で縮小してから重い集計を行う。
        bgr_small = resize_by_long_edge(bgr, self.cfg.max_dim)
        hsv = cv2.cvtColor(bgr_small, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)

        h_hist = None
        s_hist = None
        v_hist = None
        if need_hsv_hist:
            # H/S/Vヒストグラム側は従来どおり色相未定義(S=0)のみ除外
            hue_valid = s > 0
            h_hist = np.bincount(h[hue_valid].reshape(-1), minlength=180)[:180].astype(np.int64)
            # S/Vヒストグラムは全画素表示
            s_hist = np.bincount(s.reshape(-1), minlength=256)[:256].astype(np.int64)
            v_hist = np.bincount(v.reshape(-1), minlength=256)[:256].astype(np.int64)

        hist = None
        top_colors = None
        warm_ratio = 0.0
        cool_ratio = 0.0
        other_ratio = 0.0
        if need_color:
            sat_th = clamp_int(
                self.cfg.wheel_sat_threshold,
                C.WHEEL_SAT_THRESHOLD_MIN,
                C.WHEEL_SAT_THRESHOLD_MAX,
            )
            wheel_mask = s >= sat_th
            h_wheel = h[wheel_mask]
            hist = _compute_wheel_histogram(h_wheel)
            warm_ratio, cool_ratio, other_ratio = _compute_warm_cool_ratios(h_wheel)
            top_colors = _compute_top_colors(bgr_small, h_wheel, wheel_mask)

        sv = None
        rgb = None
        if need_scatter:
            sv, rgb = _sample_sv_and_rgb(h, s, v, bgr_small, self.cfg.sample_points)

        return {
            "hist": hist,
            "sv": sv,
            "rgb": rgb,
            "h_hist": h_hist,
            "s_hist": s_hist,
            "v_hist": v_hist,
            "top_colors": top_colors,
            "warm_ratio": warm_ratio,
            "cool_ratio": cool_ratio,
            "other_ratio": other_ratio,
        }

    def _run(self):
        # mss は with 内で使い回し、毎フレーム初期化コストを避ける。
        with mss.mss() as sct:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                cap: Optional[QRect] = None
                bgr: Optional[np.ndarray] = None

                # ウィンドウ取得モードでは、ROI未指定時もウィンドウ全体を直接キャプチャする
                # （画面領域選択とは排他的に扱う）
                if self.target_hwnd is not None and HAS_WIN32:
                    if self._is_window_minimized(self.target_hwnd):
                        self.status.emit(
                            "ターゲットウィンドウが最小化されています（色を取得できません）"
                        )
                        time.sleep(0.5)
                        continue
                    bgr, cap = self._capture_target_window_region()
                    if bgr is None or cap is None:
                        self.status.emit("選択ウィンドウのキャプチャに失敗しました")
                        time.sleep(0.3)
                        continue
                else:
                    bgr, cap, err = self._capture_screen_region(sct, self._compute_capture_rect())
                    if bgr is None or cap is None:
                        if err:
                            self.status.emit(err)
                            time.sleep(0.3 if err.startswith("領域が画面外") else 0.5)
                        else:
                            time.sleep(0.5)
                        continue

                if bgr is None or cap is None:
                    time.sleep(0.2)
                    continue

                need_color = bool(self.cfg.view_color)
                need_scatter = bool(self.cfg.view_scatter)
                need_hsv_hist = bool(self.cfg.view_hsv_hist)
                need_graph_data = need_color or need_scatter or need_hsv_hist
                need_image = bool(self.cfg.view_image)
                need_preview = bool(self.cfg.want_preview)
                need_bgr_emit = need_image or need_preview

                emit_now = True
                graph_update = False
                if self.cfg.mode == C.UPDATE_MODE_CHANGE:
                    emit_now = self._should_emit_in_change_mode(bgr, now=time.perf_counter())
                    # changeモードで発火したときは全ビューを同じタイミングで更新
                    graph_update = emit_now
                else:
                    # intervalモードでは graph_every 間隔でグラフ更新する。
                    self._frame += 1
                    graph_update = self._frame % self.cfg.graph_every == 0

                dt_ms = (time.perf_counter() - t0) * 1000.0
                graph_data = _EMPTY_GRAPH_DATA

                if emit_now and graph_update and need_graph_data:
                    graph_data = self._collect_graph_data(
                        bgr,
                        need_color=need_color,
                        need_scatter=need_scatter,
                        need_hsv_hist=need_hsv_hist,
                    )

                if emit_now:
                    should_emit_payload = need_bgr_emit or (graph_update and need_graph_data)
                    if should_emit_payload and not self._result_inflight.is_set():
                        # UI側が未消費の間は次結果を積まず、キュー膨張を防ぐ。
                        self._result_inflight.set()
                        self.resultReady.emit(
                            {
                                "bgr_preview": bgr if need_bgr_emit else None,
                                "hist": graph_data["hist"] if graph_update else None,
                                "sv": graph_data["sv"] if graph_update else None,
                                "rgb": graph_data["rgb"] if graph_update else None,
                                # ヒストグラムを返すため平面データは送らない。
                                "h_plane": None,
                                "s_plane": None,
                                "v_plane": None,
                                "h_hist": graph_data["h_hist"] if graph_update else None,
                                "s_hist": graph_data["s_hist"] if graph_update else None,
                                "v_hist": graph_data["v_hist"] if graph_update else None,
                                "top_colors": graph_data["top_colors"] if graph_update else None,
                                "warm_ratio": graph_data["warm_ratio"],
                                "cool_ratio": graph_data["cool_ratio"],
                                "other_ratio": graph_data["other_ratio"],
                                "dt_ms": dt_ms,
                                "cap": (cap.left(), cap.top(), cap.width(), cap.height()),
                                "graph_update": graph_update,
                            }
                        )
                        if self.cfg.mode == C.UPDATE_MODE_CHANGE:
                            # 連続発火を抑える短いクールダウン
                            self._cooldown_until = (
                                time.perf_counter() + C.ANALYZER_CHANGE_COOLDOWN_SEC
                            )

                loop_interval = (
                    self.cfg.interval_sec
                    if self.cfg.mode == C.UPDATE_MODE_INTERVAL
                    else C.ANALYZER_CHANGE_POLL_SEC
                )
                remain = loop_interval - (time.perf_counter() - t0)
                if remain > 0:
                    time.sleep(remain)
