# Windows window enumeration（pywin32 が無い場合は ctypes で代替）
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import mss
import numpy as np
from PySide6.QtCore import QObject, QPoint, QRect, Signal
from PySide6.QtGui import QGuiApplication

from .util import constants as C
from .util.functions import clamp_int, resize_by_long_edge

HAS_WIN32 = sys.platform.startswith("win")

_ctypes_win = None
if HAS_WIN32:
    try:
        import win32gui  # type: ignore
    except Exception:
        win32gui = None
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            _ctypes_win = {
                "EnumWindows": user32.EnumWindows,
                "IsWindowVisible": user32.IsWindowVisible,
                "GetWindowTextW": user32.GetWindowTextW,
                "GetWindowTextLengthW": user32.GetWindowTextLengthW,
                "GetWindowRect": user32.GetWindowRect,
                "IsIconic": user32.IsIconic,
            }
            # argtypes を設定して不正呼び出しを防ぐ
            _ctypes_win["EnumWindows"].argtypes = [
                ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM),
                wintypes.LPARAM,
            ]
            _ctypes_win["IsWindowVisible"].argtypes = [wintypes.HWND]
            _ctypes_win["GetWindowTextW"].argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            _ctypes_win["GetWindowTextLengthW"].argtypes = [wintypes.HWND]
            _ctypes_win["GetWindowRect"].argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            _ctypes_win["IsIconic"].argtypes = [wintypes.HWND]
        except Exception:
            HAS_WIN32 = False


def list_windows():
    """Return list of (hwnd, title) for visible top-level windows."""
    if not HAS_WIN32:
        return []
    out = []
    if win32gui:

        def enum_proc(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title or not title.strip():
                return
            out.append((hwnd, title))

        win32gui.EnumWindows(enum_proc, None)
    elif _ctypes_win:
        import ctypes
        from ctypes import wintypes

        EnumWindows = _ctypes_win["EnumWindows"]
        IsWindowVisible = _ctypes_win["IsWindowVisible"]
        GetWindowTextLengthW = _ctypes_win["GetWindowTextLengthW"]
        GetWindowTextW = _ctypes_win["GetWindowTextW"]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def enum_proc(hwnd, lparam):
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if title and title.strip():
                out.append((hwnd, title))
            return True

        EnumWindows(enum_proc, 0)

    out.sort(key=lambda x: x[1].lower())
    return out


def _compute_wheel_histogram(h_wheel: np.ndarray) -> np.ndarray:
    if h_wheel.size == 0:
        return np.zeros(180, dtype=np.int64)

    hist_raw = np.bincount(h_wheel.reshape(-1), minlength=180)
    kernel = np.array([1, 2, 3, 2, 1], dtype=np.float32)
    kernel = kernel / kernel.sum()
    hist_pad = np.concatenate([hist_raw[-2:], hist_raw, hist_raw[:2]]).astype(np.float32)
    hist_smooth = np.convolve(hist_pad, kernel, mode="valid")
    return hist_smooth.astype(np.int64)


def _compute_warm_cool_ratios(h_wheel: np.ndarray) -> tuple[float, float, float]:
    if h_wheel.size == 0:
        return 0.0, 0.0, 0.0

    warm = np.logical_or(h_wheel < 30, h_wheel >= 150)
    cool = np.logical_and(h_wheel >= 75, h_wheel < 135)
    warm_count = float(warm.sum())
    cool_count = float(cool.sum())
    total_color = float(h_wheel.size)
    other_count = max(0.0, total_color - warm_count - cool_count)
    return warm_count / total_color, cool_count / total_color, other_count / total_color


def _compute_top_colors(bgr: np.ndarray, h_wheel: np.ndarray, wheel_mask: np.ndarray) -> list[tuple[float, tuple[int, int, int]]]:
    top_colors: list[tuple[float, tuple[int, int, int]]] = []
    if not wheel_mask.any():
        return top_colors

    rgb_full = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rgb_masked = rgb_full[wheel_mask]
    seg_size = 10  # 2度/ビン *10 = 20度
    seg_idx = (h_wheel // seg_size).astype(np.int32)
    seg_counts = np.bincount(seg_idx, minlength=18)[:18]
    order = np.argsort(seg_counts)[::-1]
    top5_idx = [i for i in order if seg_counts[i] > 0][:C.TOP_COLORS_COUNT]
    top_sum = float(seg_counts[top5_idx].sum()) if top5_idx else 0.0
    for seg in top5_idx:
        cnt = int(seg_counts[seg])
        if cnt <= 0:
            continue
        ratio = cnt / top_sum if top_sum > 0 else 0.0  # 上位5で正規化し合計100%に
        mask_seg = seg_idx == seg
        sel = rgb_masked[mask_seg]
        if sel.size == 0:
            hue_center = int((seg * seg_size + seg_size / 2) * 2)
            hsv_val = np.uint8([[[hue_center, 255, 255]]])
            rgb_val = cv2.cvtColor(hsv_val, cv2.COLOR_HSV2RGB)[0, 0]
        else:
            rgb_val = np.mean(sel, axis=0).astype(np.uint8)
        top_colors.append((ratio, (int(rgb_val[0]), int(rgb_val[1]), int(rgb_val[2]))))
    return top_colors


def _sample_sv_and_rgb(s: np.ndarray, v: np.ndarray, bgr: np.ndarray, sample_points: int) -> tuple[np.ndarray, np.ndarray]:
    flat_s = s.reshape(-1)
    flat_v = v.reshape(-1)
    n = flat_s.size
    points = max(1, int(sample_points))
    k = min(points, n)
    if k < n:
        idx = np.random.randint(0, n, size=k, dtype=np.int32)
    else:
        idx = np.arange(n, dtype=np.int32)
    sv = np.column_stack([flat_s[idx], flat_v[idx]])
    rgb_flat = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).reshape(-1, 3)
    rgb = rgb_flat[idx]
    return sv, rgb


def _analyze_bgr_frame(
    bgr: np.ndarray,
    sample_points: int,
    wheel_sat_threshold: int,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
) -> Optional[dict]:
    """Analyze one BGR frame and return the same payload shape as live capture."""

    def _emit_progress(percent: int, text: str):
        if progress_cb is not None:
            progress_cb(int(percent), text)

    def _is_canceled() -> bool:
        if cancel_cb is None:
            return False
        try:
            return bool(cancel_cb())
        except Exception:
            return False

    if bgr is None or bgr.size == 0:
        raise ValueError("empty frame")

    _emit_progress(15, "HSVへ変換中…")
    if _is_canceled():
        return None
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    # H/S/Vヒストグラム側は色相未定義(S=0)のみ除外
    hue_valid_mask = s > 0
    # カラーサークル側は設定可能な彩度しきい値で集計
    sat_th = clamp_int(wheel_sat_threshold, C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX)
    wheel_mask = s >= sat_th

    _emit_progress(30, "色相ヒストグラム集計中…")
    if _is_canceled():
        return None
    h_masked = h[hue_valid_mask]
    h_wheel = h[wheel_mask]
    hist = _compute_wheel_histogram(h_wheel)
    warm_ratio, cool_ratio, other_ratio = _compute_warm_cool_ratios(h_wheel)

    h_std = float(np.std(h))
    s_std = float(np.std(s))
    v_std = float(np.std(v))

    _emit_progress(45, "散布図サンプル生成中…")
    if _is_canceled():
        return None
    sv, rgb = _sample_sv_and_rgb(s, v, bgr, sample_points)

    _emit_progress(65, "トップ色を計算中…")
    if _is_canceled():
        return None
    top_colors = _compute_top_colors(bgr, h_wheel, wheel_mask)

    h_img, w_img = bgr.shape[:2]
    _emit_progress(85, "結果を反映中…")
    if _is_canceled():
        return None
    return {
        "bgr_preview": bgr,
        "hist": hist,
        "sv": sv,
        "rgb": rgb,
        "h_plane": h_masked,
        "s_plane": s,
        "v_plane": v,
        "top_colors": top_colors,
        "h_std": h_std,
        "s_std": s_std,
        "v_std": v_std,
        "warm_ratio": warm_ratio,
        "cool_ratio": cool_ratio,
        "other_ratio": other_ratio,
        "dt_ms": 0.0,  # caller fills actual timing
        "cap": (0, 0, int(w_img), int(h_img)),
        "graph_update": True,
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
        self._cancel.set()

    def _is_canceled(self) -> bool:
        return self._cancel.is_set()

    def _emit_progress(self, percent: int, text: str):
        self.progress.emit(int(percent), text)

    def run(self):
        try:
            self._emit_progress(1, "画像を読み込み中…")
            if self._is_canceled():
                self.canceled.emit()
                return

            buf = np.fromfile(self.path, dtype=np.uint8)
            if buf.size == 0:
                self.failed.emit("画像ファイルを読み込めませんでした。")
                return
            bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if bgr is None or bgr.size == 0:
                self.failed.emit("画像データのデコードに失敗しました。")
                return

            h_img, w_img = bgr.shape[:2]
            self._emit_progress(8, f"解析準備中… ({w_img}x{h_img})")
            if self._is_canceled():
                self.canceled.emit()
                return

            t0 = time.perf_counter()
            res = _analyze_bgr_frame(
                bgr=bgr,
                sample_points=self.sample_points,
                wheel_sat_threshold=self.wheel_sat_threshold,
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


class AnalyzerWorker(QObject):
    resultReady = Signal(dict)
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self.cfg = AnalyzerConfig()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

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

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.status.emit("計測開始")

    def stop(self):
        self._stop.set()
        self.status.emit("停止")

    def set_interval(self, sec: float):
        self.cfg.interval_sec = max(C.ANALYZER_MIN_INTERVAL_SEC, float(sec))

    def set_sample_points(self, n: int):
        self.cfg.sample_points = clamp_int(
            n, C.ANALYZER_MIN_SAMPLE_POINTS, C.ANALYZER_MAX_SAMPLE_POINTS
        )

    def set_max_dim(self, n: int):
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
        self._prev_h = None
        self._prev_s = None
        self._prev_v = None
        self._stable_frames = 0
        self._was_stable = False
        self._cooldown_until = 0.0

    def set_diff_threshold(self, th: float):
        self.cfg.diff_threshold = max(C.ANALYZER_MIN_DIFF_THRESHOLD, float(th))

    def set_stable_frames(self, n: int):
        self.cfg.stable_frames = max(C.ANALYZER_MIN_STABLE_FRAMES, int(n))

    def set_target_window(self, hwnd: Optional[int]):
        self.target_hwnd = hwnd

    def set_roi_in_window(self, roi_rel: Optional[QRect]):
        self.roi_rel = roi_rel

    def set_roi_on_screen(self, roi_abs: Optional[QRect]):
        if roi_abs is None:
            self.roi_abs = None
            return
        # Qtの論理座標からmssが扱う物理座標へ変換して保持する
        self.roi_abs = self._logical_rect_to_native(roi_abs)

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

    def _logical_rect_to_native(self, rect: QRect) -> QRect:
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

    def _compute_capture_rect(self) -> Optional[QRect]:
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

            cap = self._compute_capture_rect()
            with mss.mss() as sct:
                vmon = sct.monitors[0]
                if cap is None:
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
        except Exception:
            return None, None, "プレビュー取得に失敗しました"

    def _run(self):
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
                    cap = self._compute_capture_rect()
                    vmon = sct.monitors[0]
                    if cap is None:
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
                        self.status.emit("領域が画面外です（範囲を選び直してください）")
                        time.sleep(0.3)
                        continue

                    mon = {
                        "left": int(left),
                        "top": int(top),
                        "width": int(width),
                        "height": int(height),
                    }
                    try:
                        img = np.array(sct.grab(mon))
                    except mss.exception.ScreenShotError:
                        self.status.emit(
                            "画面キャプチャに失敗しました（権限/表示/Wayland設定を確認）"
                        )
                        time.sleep(0.5)
                        continue
                    bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                if bgr is None or cap is None:
                    time.sleep(0.2)
                    continue

                bgr_small = resize_by_long_edge(bgr, self.cfg.max_dim)

                hsv = cv2.cvtColor(bgr_small, cv2.COLOR_BGR2HSV)
                h, s, v = cv2.split(hsv)
                # H/S/Vヒストグラム側は従来どおり色相未定義(S=0)のみ除外
                hue_valid_mask = s > 0
                # カラーサークル側は設定可能な彩度しきい値で集計
                sat_th = clamp_int(
                    self.cfg.wheel_sat_threshold,
                    C.WHEEL_SAT_THRESHOLD_MIN,
                    C.WHEEL_SAT_THRESHOLD_MAX,
                )
                wheel_mask = s >= sat_th

                h_std = float(np.std(h))
                s_std = float(np.std(s))
                v_std = float(np.std(v))

                h_masked = h[hue_valid_mask]
                h_wheel = h[wheel_mask]
                hist = _compute_wheel_histogram(h_wheel)
                warm_ratio, cool_ratio, other_ratio = _compute_warm_cool_ratios(h_wheel)
                sv, rgb = _sample_sv_and_rgb(s, v, bgr_small, self.cfg.sample_points)

                dt_ms = (time.perf_counter() - t0) * 1000.0
                self._frame += 1
                graph_update = self._frame % self.cfg.graph_every == 0

                emit_now = True
                if self.cfg.mode == C.UPDATE_MODE_CHANGE:
                    if time.perf_counter() < self._cooldown_until:
                        emit_now = False
                    if self._prev_h is None:
                        emit_now = False
                    else:
                        hue_diff = np.abs(h.astype(np.int16) - self._prev_h.astype(np.int16))
                        hue_diff = np.minimum(hue_diff, 180 - hue_diff)
                        metric = (
                            float(np.mean(hue_diff))
                            + float(
                                np.mean(np.abs(s.astype(np.int16) - self._prev_s.astype(np.int16)))
                            )
                            * 0.5
                            + float(
                                np.mean(np.abs(v.astype(np.int16) - self._prev_v.astype(np.int16)))
                            )
                            * 0.5
                        )
                        if metric < self.cfg.diff_threshold:
                            self._stable_frames += 1
                        else:
                            self._stable_frames = 0
                            self._was_stable = False
                        emit_now = (
                            self._stable_frames >= self.cfg.stable_frames and not self._was_stable
                        )
                        if emit_now:
                            self._was_stable = True
                    self._prev_h = h
                    self._prev_s = s
                    self._prev_v = v

                # changeモードで発火したときは全ビューを同じタイミングで更新
                if self.cfg.mode == C.UPDATE_MODE_CHANGE and emit_now:
                    graph_update = True

                if emit_now:
                    top_colors = _compute_top_colors(bgr_small, h_wheel, wheel_mask)

                    self.resultReady.emit(
                        {
                            "bgr_preview": bgr,
                            "hist": hist if graph_update else None,
                            "sv": sv if graph_update else None,
                            "rgb": rgb if graph_update else None,
                            "h_plane": h_masked if graph_update else None,
                            # S/Vヒストグラムは全画素を表示し、低彩度(0付近)も確認できるようにする
                            "s_plane": s if graph_update else None,
                            "v_plane": v if graph_update else None,
                            "top_colors": top_colors if graph_update else None,
                            "h_std": h_std,
                            "s_std": s_std,
                            "v_std": v_std,
                            "warm_ratio": warm_ratio,
                            "cool_ratio": cool_ratio,
                            "other_ratio": other_ratio,
                            "dt_ms": dt_ms,
                            "cap": (cap.left(), cap.top(), cap.width(), cap.height()),
                            "graph_update": graph_update,
                        }
                    )
                    if self.cfg.mode == C.UPDATE_MODE_CHANGE:
                        # 連続発火を抑えるクールダウンを interval_sec に設定
                        self._cooldown_until = time.perf_counter() + self.cfg.interval_sec

                remain = self.cfg.interval_sec - (time.perf_counter() - t0)
                if remain > 0:
                    time.sleep(remain)
