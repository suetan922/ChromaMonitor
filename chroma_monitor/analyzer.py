"""ライブ解析ワーカー。"""

import threading
import time
from dataclasses import dataclass
from typing import Optional, TypedDict

import cv2
import mss
import numpy as np
from PySide6.QtCore import QObject, QPoint, QRect, Signal
from PySide6.QtGui import QGuiApplication

from .analysis.frame_analysis import (
    _compute_hsv_histograms,
    _compute_wheel_stats_from_hs,
    _sample_sv_and_rgb,
    compute_top_bars_chromatic_medoid,
    compute_top_bars_chromatic_medoid_from_hs,
)
from .capture.win32_windows import HAS_WIN32, ctypes_win_api, win32gui
from .util import constants as C
from .util.debug_log import write_window_layout_debug_log
from .util.image_ops import resize_by_long_edge
from .util.value_utils import clamp_int

_ctypes_win = ctypes_win_api
_CAPTURE_SELECTION_KEEP = object()
_EMPTY_GRAPH_DATA: "GraphData" = {
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
_ANALYZER_MIN_INTERVAL_SEC = 0.05
_ANALYZER_MIN_GRAPH_EVERY = 1
_ANALYZER_CHANGE_POLL_SEC = 0.08
_ANALYZER_CHANGE_COOLDOWN_SEC = 0.12
_ANALYZER_CHANGE_DETECT_DIM = 120
_CAPTURE_SLEEP_SEC_DEFAULT = 0.5
_CAPTURE_SLEEP_SEC_RETRY = 0.3
_WIN_BI_RGB = 0
_WIN_DIB_RGB_COLORS = 0
_WIN_PRINTWINDOW_FULL = 0x00000002


class GraphData(TypedDict):
    """1フレーム分のグラフ計算結果。"""

    hist: Optional[np.ndarray]
    sv: Optional[np.ndarray]
    rgb: Optional[np.ndarray]
    h_hist: Optional[np.ndarray]
    s_hist: Optional[np.ndarray]
    v_hist: Optional[np.ndarray]
    top_colors: Optional[list]
    warm_ratio: float
    cool_ratio: float
    other_ratio: float


@dataclass
class AnalyzerConfig:
    """ライブ解析ループで利用する設定値の保持クラス。"""

    interval_sec: float = C.DEFAULT_INTERVAL_SEC
    sample_points: int = C.DEFAULT_SAMPLE_POINTS
    max_dim: int = C.ANALYZER_MAX_DIM
    wheel_sat_threshold: int = C.DEFAULT_WHEEL_SAT_THRESHOLD
    color_band_sat_threshold: int = C.DEFAULT_COLOR_BAND_SAT_THRESHOLD
    graph_every: int = _ANALYZER_MIN_GRAPH_EVERY
    mode: str = C.DEFAULT_MODE
    diff_threshold: float = C.DEFAULT_DIFF_THRESHOLD
    stable_frames: int = C.DEFAULT_STABLE_FRAMES
    view_color: bool = True
    view_color_band: bool = True
    view_scatter: bool = True
    view_hsv_hist: bool = True
    view_image: bool = True
    want_preview: bool = False


class AnalyzerWorker(QObject):
    """キャプチャと解析をバックグラウンドで実行するワーカー。"""

    resultReady = Signal(dict)
    status = Signal(str)

    def __init__(self):
        """解析設定・状態・内部キャッシュを初期化する。"""
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
        self._hue_wrap_buf: Optional[np.ndarray] = None
        self._stable_frames: int = 0
        self._was_stable: bool = False
        self._cooldown_until: float = 0.0
        self._force_emit_once: bool = False
        # 複数画面の論理<->物理座標対応は画面構成が変わるまで再利用する。
        self._screen_monitor_map_cache: Optional[dict] = None
        self._screen_monitor_map_signature: tuple = ()

    def _reset_change_state(self, emit_once: bool = False):
        """差分更新モードで使う履歴状態を初期化する。"""
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
        """解析スレッドを開始する。"""
        # 既に稼働中なら二重起動しない。
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._result_inflight.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.status.emit("計測開始")

    def stop(self):
        """解析スレッドへ停止要求を出す。"""
        # 停止要求は次ループで反映される。
        self._stop.set()
        self._result_inflight.clear()
        self.status.emit("停止")

    def mark_result_consumed(self):
        """UI側で結果消費完了したことをワーカーへ通知する。"""
        self._result_inflight.clear()

    def set_interval(self, sec: float):
        """更新間隔を設定する。"""
        self.cfg.interval_sec = max(_ANALYZER_MIN_INTERVAL_SEC, float(sec))

    def set_sample_points(self, n: int):
        """散布図のサンプル点数を設定する。"""
        self.cfg.sample_points = clamp_int(
            n, C.ANALYZER_MIN_SAMPLE_POINTS, C.ANALYZER_MAX_SAMPLE_POINTS
        )

    def set_max_dim(self, n: int):
        """解析用の最大辺サイズを設定する。"""
        n = int(n)
        if n <= 0:
            # 0 はオリジナル解像度（縮小なし）として扱う
            self.cfg.max_dim = 0
            return
        self.cfg.max_dim = clamp_int(n, C.ANALYZER_MAX_DIM_MIN, C.ANALYZER_MAX_DIM_MAX)

    def set_wheel_sat_threshold(self, n: int):
        """色相環用の彩度しきい値を設定する。"""
        self.cfg.wheel_sat_threshold = clamp_int(
            n, C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX
        )

    def set_color_band_sat_threshold(self, n: int):
        """配色比率用の彩度しきい値を設定する。"""
        self.cfg.color_band_sat_threshold = clamp_int(
            n, C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX
        )

    def set_graph_every(self, n: int):
        """グラフ更新間引き間隔を設定する。"""
        self.cfg.graph_every = max(_ANALYZER_MIN_GRAPH_EVERY, int(n))

    def set_mode(self, mode: str):
        """更新モードを設定する。"""
        self.cfg.mode = mode if mode in C.UPDATE_MODES else C.DEFAULT_MODE
        # モード切替時は差分検知用の状態をリセット
        self._reset_change_state()

    def set_diff_threshold(self, th: float):
        """差分更新モードの変化量しきい値を設定する。"""
        self.cfg.diff_threshold = max(C.ANALYZER_MIN_DIFF_THRESHOLD, float(th))

    def set_stable_frames(self, n: int):
        """差分更新モードの安定判定フレーム数を設定する。"""
        self.cfg.stable_frames = max(C.ANALYZER_MIN_STABLE_FRAMES, int(n))

    def set_view_flags(
        self,
        color: Optional[bool] = None,
        color_band: Optional[bool] = None,
        scatter: Optional[bool] = None,
        hsv_hist: Optional[bool] = None,
        image: Optional[bool] = None,
        preview: Optional[bool] = None,
    ):
        """可視ビューに応じた解析有効フラグを更新する。"""
        if color is not None:
            self.cfg.view_color = bool(color)
        if color_band is not None:
            self.cfg.view_color_band = bool(color_band)
        if scatter is not None:
            self.cfg.view_scatter = bool(scatter)
        if hsv_hist is not None:
            self.cfg.view_hsv_hist = bool(hsv_hist)
        if image is not None:
            self.cfg.view_image = bool(image)
        if preview is not None:
            self.cfg.want_preview = bool(preview)

    def set_capture_selection(
        self,
        *,
        target_hwnd: Optional[int] | object = _CAPTURE_SELECTION_KEEP,
        roi_rel: Optional[QRect] | object = _CAPTURE_SELECTION_KEEP,
        roi_abs: Optional[QRect] | object = _CAPTURE_SELECTION_KEEP,
    ):
        """キャプチャ対象とROIをまとめて更新し、差分履歴を1回だけリセットする。"""
        if (
            target_hwnd is _CAPTURE_SELECTION_KEEP
            and roi_rel is _CAPTURE_SELECTION_KEEP
            and roi_abs is _CAPTURE_SELECTION_KEEP
        ):
            return
        # 取得対象切替時は差分履歴を捨てて誤判定を避ける。
        if target_hwnd is not _CAPTURE_SELECTION_KEEP:
            self.target_hwnd = target_hwnd
        if roi_rel is not _CAPTURE_SELECTION_KEEP:
            self.roi_rel = roi_rel
        if roi_abs is not _CAPTURE_SELECTION_KEEP:
            # Qtの論理座標からmssが扱う物理座標へ変換して保持する。
            self.roi_abs = None if roi_abs is None else self._logical_rect_to_native(roi_abs)
        self._reset_change_state(emit_once=True)

    def _get_window_rect(self, hwnd: int) -> Optional[QRect]:
        """対象ウィンドウ矩形を取得する。"""
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
        """対象ウィンドウが最小化中か判定する。"""
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

    @staticmethod
    def _load_native_monitors() -> list[dict]:
        """mss から実モニタ一覧を取得する。"""
        try:
            with mss.mss() as sct:
                return [m for m in sct.monitors[1:]]
        except Exception:
            return []

    @staticmethod
    def _qt_screen_infos(qt_screens) -> list[dict]:
        """Qt画面一覧をマッチング用の情報辞書へ変換する。"""
        infos: list[dict] = []
        for screen in qt_screens:
            g = screen.geometry()
            infos.append(
                {
                    "screen": screen,
                    "rect": g,
                    "dpr": max(0.5, float(screen.devicePixelRatio())),
                }
            )
        return infos

    @staticmethod
    def _qt_bounds(qt_infos: list[dict]) -> tuple[float, float, float, float]:
        """Qt画面群の境界を返す。"""
        q_left = min(info["rect"].left() for info in qt_infos)
        q_top = min(info["rect"].top() for info in qt_infos)
        q_right = max(info["rect"].left() + info["rect"].width() for info in qt_infos)
        q_bottom = max(info["rect"].top() + info["rect"].height() for info in qt_infos)
        q_w = max(1.0, float(q_right - q_left))
        q_h = max(1.0, float(q_bottom - q_top))
        return float(q_left), float(q_top), float(q_w), float(q_h)

    @staticmethod
    def _native_bounds(native_monitors: list[dict]) -> tuple[float, float, float, float]:
        """実モニタ群の境界を返す。"""
        m_left = min(m["left"] for m in native_monitors)
        m_top = min(m["top"] for m in native_monitors)
        m_right = max(m["left"] + m["width"] for m in native_monitors)
        m_bottom = max(m["top"] + m["height"] for m in native_monitors)
        m_w = max(1.0, float(m_right - m_left))
        m_h = max(1.0, float(m_bottom - m_top))
        return float(m_left), float(m_top), float(m_w), float(m_h)

    @staticmethod
    def _monitor_match_pairs(
        qt_infos: list[dict],
        native_monitors: list[dict],
        *,
        q_bounds: tuple[float, float, float, float],
        m_bounds: tuple[float, float, float, float],
    ) -> list[tuple[float, int, int]]:
        """Qt画面と実モニタの対応候補スコア一覧を作る。"""
        q_left, q_top, q_w, q_h = q_bounds
        m_left, m_top, m_w, m_h = m_bounds
        pairs: list[tuple[float, int, int]] = []
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
        return pairs

    @staticmethod
    def _resolve_monitor_mapping(
        qt_infos: list[dict],
        native_monitors: list[dict],
        pairs: list[tuple[float, int, int]],
    ) -> dict:
        """候補スコアから画面対応表を解決する。"""
        used_q = set()
        used_m = set()
        mapping = {}
        for _, qi, mi in pairs:
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

    def _build_screen_monitor_map(self):
        """Qt画面とmssモニタの対応表を構築/再利用する。"""
        # Qt画面情報（論理座標）と mss 画面情報（物理座標）を近似マッチングする。
        qt_screens = QGuiApplication.screens()
        if not qt_screens:
            return {}
        screen_sig = tuple(
            (
                id(screen),
                str(screen.name()),
                int(screen.geometry().left()),
                int(screen.geometry().top()),
                int(screen.geometry().width()),
                int(screen.geometry().height()),
                round(float(screen.devicePixelRatio()), 3),
            )
            for screen in qt_screens
        )
        if (
            isinstance(self._screen_monitor_map_cache, dict)
            and self._screen_monitor_map_cache
            and self._screen_monitor_map_signature == screen_sig
        ):
            return self._screen_monitor_map_cache

        native_monitors = self._load_native_monitors()
        if not native_monitors:
            return {}
        qt_infos = self._qt_screen_infos(qt_screens)
        q_bounds = self._qt_bounds(qt_infos)
        m_bounds = self._native_bounds(native_monitors)
        pairs = self._monitor_match_pairs(
            qt_infos,
            native_monitors,
            q_bounds=q_bounds,
            m_bounds=m_bounds,
        )
        mapping = self._resolve_monitor_mapping(qt_infos, native_monitors, pairs)
        self._screen_monitor_map_cache = mapping
        self._screen_monitor_map_signature = screen_sig
        return mapping

    def _logical_point_to_native(self, x: float, y: float, mapping) -> tuple[float, float]:
        """Qt論理座標の点を物理座標へ変換する。"""
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
        """物理座標の点をQt論理座標へ変換する。"""
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
        """Qt論理座標の矩形を物理座標矩形へ変換する。"""
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
        """物理座標の矩形をQt論理座標矩形へ変換する。"""
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
        """現在設定から実キャプチャに使う矩形を解決する。"""
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

    def _capture_window_size(self, hwnd: int) -> Optional[tuple[int, int]]:
        """対象ウィンドウのキャプチャ寸法を返す。"""
        wrect = self._get_window_rect(hwnd)
        if wrect is None:
            return None
        width = int(wrect.width())
        height = int(wrect.height())
        if width <= 1 or height <= 1:
            return None
        return int(width), int(height)

    @staticmethod
    def _create_window_capture_dc(user32, gdi32, hwnd: int):
        """WindowDC と互換メモリDCを作成して返す。"""
        hwnd_dc = user32.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None, None
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        if not mem_dc:
            user32.ReleaseDC(hwnd, hwnd_dc)
            return None, None
        return hwnd_dc, mem_dc

    @staticmethod
    def _release_window_capture_dc(user32, gdi32, hwnd: int, hwnd_dc, mem_dc) -> None:
        """WindowDC とメモリDCを解放する。"""
        if mem_dc:
            gdi32.DeleteDC(mem_dc)
        if hwnd_dc:
            user32.ReleaseDC(hwnd, hwnd_dc)

    @staticmethod
    def _create_dib_section(
        *,
        ctypes_mod,
        wintypes_mod,
        gdi32,
        mem_dc,
        width: int,
        height: int,
    ):
        """32bit top-down DIB を作成し、メモリDCへ選択して返す。"""

        class BITMAPINFOHEADER(ctypes_mod.Structure):
            _fields_ = [
                ("biSize", wintypes_mod.DWORD),
                ("biWidth", wintypes_mod.LONG),
                ("biHeight", wintypes_mod.LONG),
                ("biPlanes", wintypes_mod.WORD),
                ("biBitCount", wintypes_mod.WORD),
                ("biCompression", wintypes_mod.DWORD),
                ("biSizeImage", wintypes_mod.DWORD),
                ("biXPelsPerMeter", wintypes_mod.LONG),
                ("biYPelsPerMeter", wintypes_mod.LONG),
                ("biClrUsed", wintypes_mod.DWORD),
                ("biClrImportant", wintypes_mod.DWORD),
            ]

        class BITMAPINFO(ctypes_mod.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes_mod.DWORD * 3)]

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes_mod.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = int(width)
        bmi.bmiHeader.biHeight = -int(height)  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = _WIN_BI_RGB

        bits = ctypes_mod.c_void_p()
        h_bitmap = gdi32.CreateDIBSection(
            mem_dc,
            ctypes_mod.byref(bmi),
            _WIN_DIB_RGB_COLORS,
            ctypes_mod.byref(bits),
            None,
            0,
        )
        if not h_bitmap or not bits:
            return None, None, None
        old_obj = gdi32.SelectObject(mem_dc, h_bitmap)
        return h_bitmap, old_obj, bits

    @staticmethod
    def _print_window_to_dc(user32, hwnd: int, mem_dc) -> bool:
        """PrintWindow を実行してメモリDCへ描画する。"""
        ok = user32.PrintWindow(hwnd, mem_dc, _WIN_PRINTWINDOW_FULL)
        if ok:
            return True
        return bool(user32.PrintWindow(hwnd, mem_dc, 0))

    @staticmethod
    def _dib_bits_to_bgr(*, ctypes_mod, bits, width: int, height: int) -> np.ndarray:
        """DIB先頭ポインタから BGR 画像を取り出す。"""
        size = int(width) * int(height) * 4
        buf = (ctypes_mod.c_ubyte * size).from_address(bits.value)
        bgra = np.frombuffer(buf, dtype=np.uint8).reshape((int(height), int(width), 4)).copy()
        return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)

    def _capture_window_bgr(self, hwnd: int) -> Optional[np.ndarray]:
        """Win32 APIで対象ウィンドウ全体を BGR 画像として取得する。"""
        if not HAS_WIN32:
            return None
        try:
            import ctypes
            from ctypes import wintypes

            size = self._capture_window_size(hwnd)
            if size is None:
                return None
            width, height = size

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            hwnd_dc, mem_dc = self._create_window_capture_dc(user32, gdi32, hwnd)
            if not hwnd_dc or not mem_dc:
                return None

            h_bitmap = None
            old_obj = None
            try:
                h_bitmap, old_obj, bits = self._create_dib_section(
                    ctypes_mod=ctypes,
                    wintypes_mod=wintypes,
                    gdi32=gdi32,
                    mem_dc=mem_dc,
                    width=width,
                    height=height,
                )
                if not h_bitmap or not bits:
                    return None
                if not self._print_window_to_dc(user32, hwnd, mem_dc):
                    return None
                return self._dib_bits_to_bgr(
                    ctypes_mod=ctypes,
                    bits=bits,
                    width=width,
                    height=height,
                )
            finally:
                if old_obj:
                    gdi32.SelectObject(mem_dc, old_obj)
                if h_bitmap:
                    gdi32.DeleteObject(h_bitmap)
                self._release_window_capture_dc(user32, gdi32, hwnd, hwnd_dc, mem_dc)
        except Exception:
            return None

    def _capture_target_window_region(self) -> tuple[Optional[np.ndarray], Optional[QRect]]:
        """対象ウィンドウ画像から ROI 相当領域を切り出して返す。"""
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

        mon = {
            "left": int(left),
            "top": int(top),
            "width": int(width),
            "height": int(height),
        }
        try:
            img = np.asarray(sct.grab(mon), dtype=np.uint8)
        except mss.exception.ScreenShotError:
            return None, None, "画面キャプチャに失敗しました（権限/表示/Wayland設定を確認）"
        bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return bgr, QRect(int(left), int(top), int(width), int(height)), None

    def capture_once(self) -> tuple[Optional[np.ndarray], Optional[QRect], Optional[str]]:
        """現在設定で1回だけキャプチャを実行する。"""
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
        """前回との差分量を1つのスカラー値へ集約する。"""
        # 8bit配列同士の差分は cv2.absdiff で計算して一時配列の型変換を減らす。
        prev_h = self._prev_h
        prev_s = self._prev_s
        prev_v = self._prev_v
        if prev_h is None or prev_s is None or prev_v is None:
            return 0.0

        hue_diff = cv2.absdiff(dh, prev_h)
        hue_wrap = self._hue_wrap_buf
        if hue_wrap is None or hue_wrap.shape != hue_diff.shape:
            hue_wrap = np.empty_like(hue_diff)
            self._hue_wrap_buf = hue_wrap
        # min(d, 180-d) を in-place で計算して一時配列を減らす。
        np.subtract(180, hue_diff, out=hue_wrap, casting="unsafe")
        np.minimum(hue_diff, hue_wrap, out=hue_diff)
        sat_diff = cv2.absdiff(ds, prev_s)
        val_diff = cv2.absdiff(dv, prev_v)
        return (
            float(cv2.mean(hue_diff)[0])
            + float(cv2.mean(sat_diff)[0]) * 0.5
            + float(cv2.mean(val_diff)[0]) * 0.5
        )

    def _should_emit_in_change_mode(self, bgr: np.ndarray, now: float) -> bool:
        """差分更新モードで今回フレームを通知すべきか判定する。"""
        # 差分判定は軽量化のため専用縮小サイズで行う。
        detect_bgr = resize_by_long_edge(bgr, _ANALYZER_CHANGE_DETECT_DIM)
        detect_hsv = cv2.cvtColor(detect_bgr, cv2.COLOR_BGR2HSV)
        # split はチャネルごとに配列コピーするため、ビュー参照で取り出す。
        dh = detect_hsv[:, :, 0]
        ds = detect_hsv[:, :, 1]
        dv = detect_hsv[:, :, 2]

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

    @staticmethod
    def _extract_hsv_channels(
        bgr: np.ndarray,
        *,
        enabled: bool,
    ) -> tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
        """必要時のみ HSV を生成し、チャネルビューを返す。"""
        if not enabled:
            return None, None, None
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        # split はチャネルごとに配列コピーするため、ビュー参照で取り出す。
        return hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    @staticmethod
    def _optional_hsv_histograms(
        *,
        enabled: bool,
        h: Optional[np.ndarray],
        s: Optional[np.ndarray],
        v: Optional[np.ndarray],
    ) -> tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
        """HSVヒストグラムが必要なときだけ集計結果を返す。"""
        if not enabled or h is None or s is None or v is None:
            return None, None, None
        return _compute_hsv_histograms(h, s, v)

    def _optional_wheel_stats(
        self,
        *,
        enabled: bool,
        h: Optional[np.ndarray],
        s: Optional[np.ndarray],
    ) -> tuple[Optional[np.ndarray], float, float, float]:
        """色相環ヒストグラムと暖寒比率を必要時のみ計算する。"""
        if not enabled or h is None or s is None:
            return None, 0.0, 0.0, 0.0
        return _compute_wheel_stats_from_hs(h, s, int(self.cfg.wheel_sat_threshold))

    def _optional_scatter_samples(
        self,
        *,
        enabled: bool,
        h: Optional[np.ndarray],
        s: Optional[np.ndarray],
        v: Optional[np.ndarray],
        bgr: np.ndarray,
    ) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """散布図サンプルが必要なときだけ SV/RGB を生成する。"""
        if not enabled or h is None or s is None or v is None:
            return None, None
        return _sample_sv_and_rgb(h, s, v, bgr, self.cfg.sample_points)

    def _optional_top_colors(
        self,
        *,
        enabled: bool,
        bgr: np.ndarray,
        h: Optional[np.ndarray],
        s: Optional[np.ndarray],
    ):
        """配色比率の代表色を必要時のみ計算する。"""
        if not enabled:
            return None
        if h is not None and s is not None:
            return compute_top_bars_chromatic_medoid_from_hs(
                bgr,
                h,
                s,
                sat_threshold=int(self.cfg.color_band_sat_threshold),
                top_count=int(C.TOP_COLORS_COUNT),
            )
        return compute_top_bars_chromatic_medoid(
            bgr,
            sat_threshold=int(self.cfg.color_band_sat_threshold),
            top_count=int(C.TOP_COLORS_COUNT),
        )

    def _collect_graph_data(
        self,
        bgr: np.ndarray,
        need_color: bool,
        need_color_band: bool,
        need_scatter: bool,
        need_hsv_hist: bool,
    ) -> GraphData:
        """現在フレームから要求されたグラフ項目だけを計算する。"""
        # 設定された解析上限（max_dim）で縮小してから重い集計を行う。
        bgr_small = resize_by_long_edge(bgr, self.cfg.max_dim)
        need_hsv_channels = need_hsv_hist or need_color or need_scatter or need_color_band
        h, s, v = self._extract_hsv_channels(bgr_small, enabled=need_hsv_channels)
        h_hist, s_hist, v_hist = self._optional_hsv_histograms(
            enabled=need_hsv_hist,
            h=h,
            s=s,
            v=v,
        )
        hist, warm_ratio, cool_ratio, other_ratio = self._optional_wheel_stats(
            enabled=need_color,
            h=h,
            s=s,
        )
        sv, rgb = self._optional_scatter_samples(
            enabled=need_scatter,
            h=h,
            s=s,
            v=v,
            bgr=bgr_small,
        )
        # 配色比率の代表色計算は解析解像度(max_dim適用後)で行い、負荷を抑える。
        top_colors = self._optional_top_colors(
            enabled=need_color_band,
            bgr=bgr_small,
            h=h,
            s=s,
        )

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

    def _emit_status_and_sleep(self, message: Optional[str], sleep_sec: float) -> None:
        """必要時だけステータス通知して待機する。"""
        if message:
            self.status.emit(message)
        time.sleep(float(sleep_sec))

    @staticmethod
    def _screen_capture_retry_sleep(err: Optional[str]) -> float:
        """画面キャプチャ失敗時の待機秒を返す。"""
        if err and err.startswith("領域が画面外"):
            return _CAPTURE_SLEEP_SEC_RETRY
        return _CAPTURE_SLEEP_SEC_DEFAULT

    @staticmethod
    def _loop_interval_sec(cfg: AnalyzerConfig) -> float:
        """現在モードに応じた1ループの待機秒数を返す。"""
        if cfg.mode == C.UPDATE_MODE_INTERVAL:
            return float(cfg.interval_sec)
        return float(_ANALYZER_CHANGE_POLL_SEC)

    @staticmethod
    def _view_requirements(cfg: AnalyzerConfig) -> tuple[bool, bool, bool, bool, bool, bool]:
        """現在設定からビュー更新要件フラグを返す。"""
        need_color = cfg.view_color
        need_color_band = cfg.view_color_band
        need_scatter = cfg.view_scatter
        need_hsv_hist = cfg.view_hsv_hist
        need_graph_data = need_color or need_color_band or need_scatter or need_hsv_hist
        need_bgr_emit = cfg.view_image or cfg.want_preview
        return (
            need_color,
            need_color_band,
            need_scatter,
            need_hsv_hist,
            need_graph_data,
            need_bgr_emit,
        )

    def _capture_frame_for_loop(self, sct) -> tuple[Optional[np.ndarray], Optional[QRect]]:
        """メインループ1回分のキャプチャを実行して返す。"""
        # windowモードは ROI未指定でもウィンドウ全体を直接取得する。
        if self.target_hwnd is not None and HAS_WIN32:
            if self._is_window_minimized(self.target_hwnd):
                write_window_layout_debug_log(
                    "capture_window_source_error",
                    target_hwnd=int(self.target_hwnd),
                    reason="minimized",
                )
                self._emit_status_and_sleep(
                    "ターゲットウィンドウが最小化されています（色を取得できません）",
                    _CAPTURE_SLEEP_SEC_DEFAULT,
                )
                return None, None
            bgr, cap = self._capture_target_window_region()
            if bgr is None or cap is None:
                write_window_layout_debug_log(
                    "capture_window_source_error",
                    target_hwnd=int(self.target_hwnd),
                    reason="capture_failed",
                )
                self._emit_status_and_sleep(
                    "選択ウィンドウのキャプチャに失敗しました",
                    _CAPTURE_SLEEP_SEC_RETRY,
                )
                return None, None
            return bgr, cap

        bgr, cap, err = self._capture_screen_region(sct, self._compute_capture_rect())
        if bgr is None or cap is None:
            self._emit_status_and_sleep(err, self._screen_capture_retry_sleep(err))
            return None, None
        return bgr, cap

    def _emit_and_graph_update_flags(
        self, cfg: AnalyzerConfig, bgr: np.ndarray
    ) -> tuple[bool, bool]:
        """更新モードに応じて通知可否とグラフ更新可否を返す。"""
        if cfg.mode == C.UPDATE_MODE_CHANGE:
            emit_now = self._should_emit_in_change_mode(bgr, now=time.perf_counter())
            # changeモードで発火したときは全ビューを同じタイミングで更新
            return bool(emit_now), bool(emit_now)

        # intervalモードでは graph_every 間隔でグラフ更新する。
        self._frame += 1
        graph_update = self._frame % cfg.graph_every == 0
        return True, bool(graph_update)

    @staticmethod
    def _build_result_payload(
        *,
        bgr: np.ndarray,
        cap: QRect,
        graph_data: GraphData,
        graph_update: bool,
        need_bgr_emit: bool,
        dt_ms: float,
    ) -> dict:
        """UI通知用ペイロードを組み立てる。"""
        return {
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
            "dt_ms": float(dt_ms),
            "cap": (cap.left(), cap.top(), cap.width(), cap.height()),
            "graph_update": bool(graph_update),
        }

    def _graph_data_for_frame(
        self,
        *,
        emit_now: bool,
        graph_update: bool,
        need_graph_data: bool,
        bgr: np.ndarray,
        need_color: bool,
        need_color_band: bool,
        need_scatter: bool,
        need_hsv_hist: bool,
    ) -> GraphData:
        """必要なときだけグラフ計算を実行する。"""
        if not (emit_now and graph_update and need_graph_data):
            return _EMPTY_GRAPH_DATA
        return self._collect_graph_data(
            bgr,
            need_color=need_color,
            need_color_band=need_color_band,
            need_scatter=need_scatter,
            need_hsv_hist=need_hsv_hist,
        )

    def _emit_result_if_possible(self, payload: dict, *, cfg: AnalyzerConfig) -> None:
        """未消費キューが空いている場合のみ結果を通知する。"""
        if self._result_inflight.is_set():
            return
        # UI側が未消費の間は次結果を積まず、キュー膨張を防ぐ。
        self._result_inflight.set()
        self.resultReady.emit(payload)
        if cfg.mode == C.UPDATE_MODE_CHANGE:
            # 連続発火を抑える短いクールダウン
            self._cooldown_until = time.perf_counter() + _ANALYZER_CHANGE_COOLDOWN_SEC

    def _run(self):
        """キャプチャ/解析/通知を繰り返すメインループ。"""
        # mss は with 内で使い回し、毎フレーム初期化コストを避ける。
        with mss.mss() as sct:
            while not self._stop.is_set():
                t0 = time.perf_counter()

                cfg = self.cfg
                # 可視ビューから必要計算を決める。
                (
                    need_color,
                    need_color_band,
                    need_scatter,
                    need_hsv_hist,
                    need_graph_data,
                    need_bgr_emit,
                ) = self._view_requirements(cfg)
                loop_interval = self._loop_interval_sec(cfg)
                idle_sleep_sec = max(0.01, loop_interval)
                if not need_graph_data and not need_bgr_emit:
                    # 表示先が1つもない間はキャプチャ/解析を休止してCPU使用率を下げる。
                    time.sleep(idle_sleep_sec)
                    continue
                if self._result_inflight.is_set():
                    # UIが前フレームを消費中の間は新規キャプチャを抑止して無駄負荷を避ける。
                    time.sleep(idle_sleep_sec)
                    continue

                # 1フレーム取得。
                bgr, cap = self._capture_frame_for_loop(sct)
                if bgr is None or cap is None:
                    continue

                # 今回フレームを通知するか判定。
                emit_now, graph_update = self._emit_and_graph_update_flags(cfg, bgr)
                # UI未消費で結果が捨てられる状態なら重い計算を省く。
                can_emit_now = bool(emit_now and not self._result_inflight.is_set())
                # 必要時のみ重い集計を走らせる。
                graph_data = self._graph_data_for_frame(
                    emit_now=can_emit_now,
                    graph_update=graph_update,
                    need_graph_data=need_graph_data,
                    bgr=bgr,
                    need_color=need_color,
                    need_color_band=need_color_band,
                    need_scatter=need_scatter,
                    need_hsv_hist=need_hsv_hist,
                )

                if can_emit_now:
                    # グラフ更新なしでも画像プレビューが必要なら通知する。
                    should_emit_payload = need_bgr_emit or (graph_update and need_graph_data)
                    if should_emit_payload:
                        dt_ms = (time.perf_counter() - t0) * 1000.0
                        payload = self._build_result_payload(
                            bgr=bgr,
                            cap=cap,
                            graph_data=graph_data,
                            graph_update=bool(graph_update),
                            need_bgr_emit=bool(need_bgr_emit),
                            dt_ms=float(dt_ms),
                        )
                        self._emit_result_if_possible(payload, cfg=cfg)

                # ループ周期を維持。
                remain = loop_interval - (time.perf_counter() - t0)
                if remain > 0:
                    time.sleep(remain)
