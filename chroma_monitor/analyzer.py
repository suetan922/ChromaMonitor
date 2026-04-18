"""ライブ解析ワーカー。"""

import threading
import time
from dataclasses import dataclass, replace
from typing import Optional

import mss
import numpy as np
from PySide6.QtCore import QObject, QRect, Signal

from .analysis import change_detection, live_graph_data, screen_mapping
from .analysis.result_payloads import GraphDataPayload
from .capture import frame_capture, win32_window_capture
from .capture.win32_windows import HAS_WIN32
from .util import constants as C
from .util.debug_log import write_window_layout_debug_log
from .util.value_utils import clamp_int

GraphData = GraphDataPayload

_CAPTURE_SELECTION_KEEP = object()
_EMPTY_GRAPH_DATA: GraphData = {
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
_ANALYZER_MIN_INTERVAL_SEC = 0.10
_ANALYZER_MIN_GRAPH_EVERY = 1
_ANALYZER_CHANGE_POLL_SEC = 0.08
_ANALYZER_CHANGE_COOLDOWN_SEC = 0.12
_ANALYZER_CHANGE_DETECT_DIM = 120
_CAPTURE_SLEEP_SEC_DEFAULT = 0.5
_CAPTURE_SLEEP_SEC_RETRY = 0.3


@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True)
class AnalyzerCaptureSelection:
    """ライブ解析で使うキャプチャ対象の保持クラス。"""

    target_hwnd: Optional[int] = None
    roi_rel: Optional[QRect] = None
    roi_abs: Optional[QRect] = None


@dataclass(frozen=True, slots=True)
class AnalyzerRuntimeSnapshot:
    """ワーカーループが1回分で参照する不変スナップショット。"""

    cfg: AnalyzerConfig
    capture: AnalyzerCaptureSelection


@dataclass(frozen=True, slots=True)
class AnalyzerLoopState:
    """ループ1回分で使う判定条件を束ねた状態。"""

    cfg: AnalyzerConfig
    capture: AnalyzerCaptureSelection
    need_color: bool
    need_color_band: bool
    need_scatter: bool
    need_hsv_hist: bool
    need_graph_data: bool
    need_bgr_emit: bool
    loop_interval: float
    idle_sleep_sec: float


@dataclass(frozen=True, slots=True)
class AnalyzerFrameState:
    """取得済み1フレームに対する通知判定結果。"""

    started_at: float
    bgr: np.ndarray
    cap: QRect
    emit_now: bool
    graph_update: bool
    graph_data: GraphData


@dataclass(frozen=True, slots=True)
class AnalyzerFrameDecision:
    """現在フレームの通知可否とグラフ更新可否。"""

    emit_now: bool
    graph_update: bool


@dataclass(frozen=True, slots=True)
class AnalyzerGraphRequest:
    """グラフ計算に必要な入力群。"""

    can_emit_now: bool
    graph_update: bool
    need_graph_data: bool
    bgr: np.ndarray
    cfg: AnalyzerConfig
    need_color: bool
    need_color_band: bool
    need_scatter: bool
    need_hsv_hist: bool


def _copy_rect(rect: Optional[QRect]) -> Optional[QRect]:
    """`QRect` を共有しないようコピーして返す。"""
    return None if rect is None else QRect(rect)


class AnalyzerWorker(QObject):
    """キャプチャと解析をバックグラウンドで実行するワーカー。"""

    resultReady = Signal(dict)
    status = Signal(str)

    def __init__(self):
        """解析設定・状態・内部キャッシュを初期化する。"""
        super().__init__()
        self._state_lock = threading.Lock()
        self._change_state_lock = threading.Lock()
        self._cfg = AnalyzerConfig()
        self._capture_selection = AnalyzerCaptureSelection()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # UIスレッドが処理しきれないとキューが肥大化するため、未処理フレームは1件までに制限
        self._result_inflight = threading.Event()

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
        with self._change_state_lock:
            # changeモードの履歴を初期化する。
            self._prev_h = None
            self._prev_s = None
            self._prev_v = None
            self._stable_frames = 0
            self._was_stable = False
            self._cooldown_until = 0.0
            if emit_once:
                self._force_emit_once = True

    @property
    def cfg(self) -> AnalyzerConfig:
        """現在の設定スナップショットを返す。"""
        with self._state_lock:
            return self._cfg

    @property
    def target_hwnd(self) -> Optional[int]:
        """現在の対象ウィンドウハンドルを返す。"""
        return self.capture_selection().target_hwnd

    @property
    def roi_rel(self) -> Optional[QRect]:
        """現在のウィンドウ相対ROIを返す。"""
        return self.capture_selection().roi_rel

    @property
    def roi_abs(self) -> Optional[QRect]:
        """現在の画面絶対ROIを返す。"""
        return self.capture_selection().roi_abs

    def capture_selection(self) -> AnalyzerCaptureSelection:
        """現在のキャプチャ選択をコピー付きで返す。"""
        with self._state_lock:
            capture = self._capture_selection
            return AnalyzerCaptureSelection(
                target_hwnd=capture.target_hwnd,
                roi_rel=_copy_rect(capture.roi_rel),
                roi_abs=_copy_rect(capture.roi_abs),
            )

    def runtime_snapshot(self) -> AnalyzerRuntimeSnapshot:
        """ループ1回分で使う設定・選択状態のスナップショットを返す。"""
        with self._state_lock:
            capture = self._capture_selection
            return AnalyzerRuntimeSnapshot(
                cfg=self._cfg,
                capture=AnalyzerCaptureSelection(
                    target_hwnd=capture.target_hwnd,
                    roi_rel=_copy_rect(capture.roi_rel),
                    roi_abs=_copy_rect(capture.roi_abs),
                ),
            )

    def _update_cfg(self, **changes) -> None:
        """設定差分をまとめて適用する。"""
        if not changes:
            return
        with self._state_lock:
            self._cfg = replace(self._cfg, **changes)

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

    def is_running(self) -> bool:
        """ライブ解析が実行状態なら True を返す。"""
        thread = self._thread
        return bool(thread is not None and thread.is_alive() and not self._stop.is_set())

    def mark_result_consumed(self):
        """UI側で結果消費完了したことをワーカーへ通知する。"""
        self._result_inflight.clear()

    def set_interval(self, sec: float):
        """更新間隔を設定する。"""
        self._update_cfg(interval_sec=max(_ANALYZER_MIN_INTERVAL_SEC, float(sec)))

    def set_sample_points(self, n: int):
        """散布図のサンプル点数を設定する。"""
        self._update_cfg(
            sample_points=clamp_int(
                n, C.ANALYZER_MIN_SAMPLE_POINTS, C.ANALYZER_MAX_SAMPLE_POINTS
            )
        )

    def set_max_dim(self, n: int):
        """解析用の最大辺サイズを設定する。"""
        n = int(n)
        if n <= 0:
            # 0 はオリジナル解像度（縮小なし）として扱う
            self._update_cfg(max_dim=0)
            return
        self._update_cfg(max_dim=clamp_int(n, C.ANALYZER_MAX_DIM_MIN, C.ANALYZER_MAX_DIM_MAX))

    def set_wheel_sat_threshold(self, n: int):
        """色相環用の彩度しきい値を設定する。"""
        self._update_cfg(
            wheel_sat_threshold=clamp_int(
                n, C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX
            )
        )

    def set_color_band_sat_threshold(self, n: int):
        """配色比率用の彩度しきい値を設定する。"""
        self._update_cfg(
            color_band_sat_threshold=clamp_int(
                n, C.WHEEL_SAT_THRESHOLD_MIN, C.WHEEL_SAT_THRESHOLD_MAX
            )
        )

    def set_graph_every(self, n: int):
        """グラフ更新間引き間隔を設定する。"""
        self._update_cfg(graph_every=max(_ANALYZER_MIN_GRAPH_EVERY, int(n)))

    def set_mode(self, mode: str):
        """更新モードを設定する。"""
        self._update_cfg(mode=mode if mode in C.UPDATE_MODES else C.DEFAULT_MODE)
        # モード切替時は差分検知用の状態をリセット
        self._reset_change_state()

    def set_diff_threshold(self, th: float):
        """差分更新モードの変化量しきい値を設定する。"""
        self._update_cfg(diff_threshold=max(C.ANALYZER_MIN_DIFF_THRESHOLD, float(th)))

    def set_stable_frames(self, n: int):
        """差分更新モードの安定判定フレーム数を設定する。"""
        self._update_cfg(stable_frames=max(C.ANALYZER_MIN_STABLE_FRAMES, int(n)))

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
        changes = {}
        if color is not None:
            changes["view_color"] = bool(color)
        if color_band is not None:
            changes["view_color_band"] = bool(color_band)
        if scatter is not None:
            changes["view_scatter"] = bool(scatter)
        if hsv_hist is not None:
            changes["view_hsv_hist"] = bool(hsv_hist)
        if image is not None:
            changes["view_image"] = bool(image)
        if preview is not None:
            changes["want_preview"] = bool(preview)
        self._update_cfg(**changes)

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
        next_roi_abs = _CAPTURE_SELECTION_KEEP
        if roi_abs is not _CAPTURE_SELECTION_KEEP:
            # Qtの論理座標からmssが扱う物理座標へ変換して保持する。
            next_roi_abs = None if roi_abs is None else self._logical_rect_to_native(QRect(roi_abs))
        next_roi_rel = (
            _CAPTURE_SELECTION_KEEP
            if roi_rel is _CAPTURE_SELECTION_KEEP
            else _copy_rect(None if roi_rel is None else QRect(roi_rel))
        )
        with self._state_lock:
            current = self._capture_selection
            self._capture_selection = AnalyzerCaptureSelection(
                target_hwnd=(
                    current.target_hwnd
                    if target_hwnd is _CAPTURE_SELECTION_KEEP
                    else (None if target_hwnd is None else int(target_hwnd))
                ),
                roi_rel=current.roi_rel if next_roi_rel is _CAPTURE_SELECTION_KEEP else next_roi_rel,
                roi_abs=current.roi_abs if next_roi_abs is _CAPTURE_SELECTION_KEEP else next_roi_abs,
            )
        self._reset_change_state(emit_once=True)

    def get_window_rect(self, hwnd: int) -> Optional[QRect]:
        """UI 層向けにウィンドウ矩形を返す。"""
        return self._get_window_rect(hwnd)

    def logical_rect_to_native(self, rect: QRect) -> QRect:
        """UI 層向けに論理座標矩形を物理座標へ変換する。"""
        return self._logical_rect_to_native(rect)

    def native_rect_to_logical(self, rect: QRect) -> QRect:
        """UI 層向けに物理座標矩形を論理座標へ変換する。"""
        return self._native_rect_to_logical(rect)

    def _build_screen_monitor_map(self):
        """Qt画面とmssモニタの対応表を構築/再利用する。"""
        mapping, screen_sig = screen_mapping.build_screen_monitor_map(
            cache=self._screen_monitor_map_cache,
            signature=self._screen_monitor_map_signature,
        )
        self._screen_monitor_map_cache = mapping
        self._screen_monitor_map_signature = screen_sig
        return mapping

    def _logical_rect_to_native(self, rect: QRect) -> QRect:
        """Qt論理座標の矩形を物理座標矩形へ変換する。"""
        mapping = self._build_screen_monitor_map()
        return screen_mapping.logical_rect_to_native(rect, mapping)

    def _native_rect_to_logical(self, rect: QRect) -> QRect:
        """物理座標の矩形をQt論理座標矩形へ変換する。"""
        mapping = self._build_screen_monitor_map()
        return screen_mapping.native_rect_to_logical(rect, mapping)

    def _compute_capture_rect(self, capture: AnalyzerCaptureSelection) -> Optional[QRect]:
        """現在設定から実キャプチャに使う矩形を解決する。"""
        return frame_capture.compute_capture_rect(
            target_hwnd=capture.target_hwnd,
            roi_rel=capture.roi_rel,
            roi_abs=capture.roi_abs,
            get_window_rect_fn=self._get_window_rect,
        )

    @staticmethod
    def _get_window_rect(hwnd: int) -> Optional[QRect]:
        """対象ウィンドウ矩形を取得する。"""
        return win32_window_capture.get_window_rect(hwnd)

    @staticmethod
    def _is_window_minimized(hwnd: int) -> bool:
        """対象ウィンドウが最小化中か判定する。"""
        return win32_window_capture.is_window_minimized(hwnd)

    def _capture_window_bgr(self, hwnd: int) -> Optional[np.ndarray]:
        """Win32 APIで対象ウィンドウ全体を BGR 画像として取得する。"""
        return win32_window_capture.capture_window_bgr(
            hwnd,
            get_window_rect_fn=self._get_window_rect,
        )

    def _capture_target_window_region(
        self,
        capture: AnalyzerCaptureSelection,
    ) -> tuple[Optional[np.ndarray], Optional[QRect]]:
        """対象ウィンドウ画像から ROI 相当領域を切り出して返す。"""
        return frame_capture.capture_target_window_region(
            target_hwnd=capture.target_hwnd,
            roi_rel=capture.roi_rel,
            get_window_rect_fn=self._get_window_rect,
            capture_window_bgr_fn=self._capture_window_bgr,
        )

    @staticmethod
    def _capture_screen_region(
        sct,
        cap: Optional[QRect],
    ) -> tuple[Optional[np.ndarray], Optional[QRect], Optional[str]]:
        """画面領域キャプチャを実行し、画像と実キャプチャ矩形を返す。"""
        return frame_capture.capture_screen_region(sct, cap)

    def capture_once(self) -> tuple[Optional[np.ndarray], Optional[QRect], Optional[str]]:
        """現在設定で1回だけキャプチャを実行する。"""
        runtime = self.runtime_snapshot()
        capture = runtime.capture
        try:
            if capture.target_hwnd is not None and HAS_WIN32:
                if self._is_window_minimized(capture.target_hwnd):
                    return (
                        None,
                        None,
                        "ターゲットウィンドウが最小化されています（色を取得できません）",
                    )
                bgr, cap = self._capture_target_window_region(capture)
                if bgr is None or cap is None:
                    return None, None, "選択ウィンドウのキャプチャに失敗しました"
                return bgr, cap, None

            with mss.mss() as sct:
                return self._capture_screen_region(sct, self._compute_capture_rect(capture))
        except Exception as exc:
            # キャプチャ backend 依存で例外型が広いため、挙動は守りつつ文脈を残す。
            write_window_layout_debug_log(
                "capture_once_exception",
                target_hwnd=capture.target_hwnd,
                roi_rel=capture.roi_rel,
                roi_abs=capture.roi_abs,
                error=repr(exc),
            )
            return None, None, "プレビュー取得に失敗しました"

    def _compute_change_metric(self, dh: np.ndarray, ds: np.ndarray, dv: np.ndarray) -> float:
        """前回との差分量を1つのスカラー値へ集約する。"""
        metric, self._hue_wrap_buf = change_detection.compute_change_metric(
            dh,
            ds,
            dv,
            prev_h=self._prev_h,
            prev_s=self._prev_s,
            prev_v=self._prev_v,
            hue_wrap_buf=self._hue_wrap_buf,
        )
        return float(metric)

    def _should_emit_in_change_mode(
        self,
        bgr: np.ndarray,
        now: float,
        cfg: AnalyzerConfig,
    ) -> bool:
        """差分更新モードで今回フレームを通知すべきか判定する。"""
        with self._change_state_lock:
            dh, ds, dv = change_detection.prepare_change_detection_channels(
                bgr,
                detect_dim=_ANALYZER_CHANGE_DETECT_DIM,
            )

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
                if metric < cfg.diff_threshold:
                    self._stable_frames += 1
                else:
                    self._stable_frames = 0
                    self._was_stable = False
                emit_now = self._stable_frames >= cfg.stable_frames and not self._was_stable
                if emit_now:
                    self._was_stable = True

            self._prev_h = dh
            self._prev_s = ds
            self._prev_v = dv
            if self._force_emit_once:
                self._force_emit_once = False
                emit_now = True
            return emit_now

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

    def _capture_frame_for_loop(
        self,
        sct,
        capture: AnalyzerCaptureSelection,
    ) -> tuple[Optional[np.ndarray], Optional[QRect]]:
        """メインループ1回分のキャプチャを実行して返す。"""
        # windowモードは ROI未指定でもウィンドウ全体を直接取得する。
        if capture.target_hwnd is not None and HAS_WIN32:
            if self._is_window_minimized(capture.target_hwnd):
                write_window_layout_debug_log(
                    "capture_window_source_error",
                    target_hwnd=int(capture.target_hwnd),
                    reason="minimized",
                )
                self._emit_status_and_sleep(
                    "ターゲットウィンドウが最小化されています（色を取得できません）",
                    _CAPTURE_SLEEP_SEC_DEFAULT,
                )
                return None, None
            bgr, cap = self._capture_target_window_region(capture)
            if bgr is None or cap is None:
                write_window_layout_debug_log(
                    "capture_window_source_error",
                    target_hwnd=int(capture.target_hwnd),
                    reason="capture_failed",
                )
                self._emit_status_and_sleep(
                    "選択ウィンドウのキャプチャに失敗しました",
                    _CAPTURE_SLEEP_SEC_RETRY,
                )
                return None, None
            return bgr, cap

        bgr, cap, err = self._capture_screen_region(sct, self._compute_capture_rect(capture))
        if bgr is None or cap is None:
            self._emit_status_and_sleep(err, self._screen_capture_retry_sleep(err))
            return None, None
        return bgr, cap

    def _emit_and_graph_update_flags(
        self, cfg: AnalyzerConfig, bgr: np.ndarray
    ) -> tuple[bool, bool]:
        """更新モードに応じて通知可否とグラフ更新可否を返す。"""
        if cfg.mode == C.UPDATE_MODE_CHANGE:
            emit_now = self._should_emit_in_change_mode(
                bgr,
                now=time.perf_counter(),
                cfg=cfg,
            )
            # changeモードで発火したときは全ビューを同じタイミングで更新
            return bool(emit_now), bool(emit_now)

        # intervalモードでは graph_every 間隔でグラフ更新する。
        self._frame += 1
        graph_update = self._frame % cfg.graph_every == 0
        return True, bool(graph_update)

    def _frame_decision_for_loop(
        self,
        cfg: AnalyzerConfig,
        bgr: np.ndarray,
    ) -> AnalyzerFrameDecision:
        """現在フレームの通知/グラフ更新判定を返す。"""
        emit_now, graph_update = self._emit_and_graph_update_flags(cfg, bgr)
        return AnalyzerFrameDecision(
            emit_now=bool(emit_now),
            graph_update=bool(graph_update),
        )

    def _graph_request_for_frame(
        self,
        state: AnalyzerLoopState,
        bgr: np.ndarray,
        decision: AnalyzerFrameDecision,
    ) -> AnalyzerGraphRequest:
        """現在フレームの graph 計算要求を組み立てる。"""
        return AnalyzerGraphRequest(
            can_emit_now=bool(decision.emit_now and not self._result_inflight.is_set()),
            graph_update=bool(decision.graph_update),
            need_graph_data=bool(state.need_graph_data),
            bgr=bgr,
            cfg=state.cfg,
            need_color=bool(state.need_color),
            need_color_band=bool(state.need_color_band),
            need_scatter=bool(state.need_scatter),
            need_hsv_hist=bool(state.need_hsv_hist),
        )

    def _graph_data_for_frame(self, request: AnalyzerGraphRequest) -> GraphData:
        """必要なときだけグラフ計算を実行する。"""
        if not (request.can_emit_now and request.graph_update and request.need_graph_data):
            return _EMPTY_GRAPH_DATA
        return live_graph_data.collect_graph_data(
            request.bgr,
            request.cfg,
            need_color=request.need_color,
            need_color_band=request.need_color_band,
            need_scatter=request.need_scatter,
            need_hsv_hist=request.need_hsv_hist,
        )

    def _frame_state_for_loop(
        self,
        state: AnalyzerLoopState,
        *,
        started_at: float,
        bgr: np.ndarray,
        cap,
    ) -> AnalyzerFrameState:
        """今回キャプチャ済みフレームの通知状態をまとめる。"""
        decision = self._frame_decision_for_loop(state.cfg, bgr)
        graph_request = self._graph_request_for_frame(state, bgr, decision)
        return AnalyzerFrameState(
            started_at=float(started_at),
            bgr=bgr,
            cap=cap,
            emit_now=bool(graph_request.can_emit_now),
            graph_update=bool(graph_request.graph_update),
            graph_data=self._graph_data_for_frame(graph_request),
        )

    @staticmethod
    def _sleep_remaining_loop_interval(state: AnalyzerLoopState, started_at: float) -> None:
        """ループ周期を維持するため残り時間だけ待機する。"""
        remain = state.loop_interval - (time.perf_counter() - started_at)
        if remain > 0:
            time.sleep(remain)

    def _emit_result_if_possible(self, payload: dict, *, cfg: AnalyzerConfig) -> None:
        """未消費キューが空いている場合のみ結果を通知する。"""
        if self._result_inflight.is_set():
            return
        # UI側が未消費の間は次結果を積まず、キュー膨張を防ぐ。
        self._result_inflight.set()
        self.resultReady.emit(payload)
        if cfg.mode == C.UPDATE_MODE_CHANGE:
            # 連続発火を抑える短いクールダウン
            with self._change_state_lock:
                self._cooldown_until = time.perf_counter() + _ANALYZER_CHANGE_COOLDOWN_SEC

    def _loop_state(self) -> AnalyzerLoopState:
        """ループ1回分で必要な設定・表示要求をまとめて返す。"""
        runtime = self.runtime_snapshot()
        cfg = runtime.cfg
        capture = runtime.capture
        # 可視ビューから必要計算を決める。
        (
            need_color,
            need_color_band,
            need_scatter,
            need_hsv_hist,
            need_graph_data,
            need_bgr_emit,
        ) = live_graph_data.view_requirements(cfg)
        loop_interval = self._loop_interval_sec(cfg)
        return AnalyzerLoopState(
            cfg=cfg,
            capture=capture,
            need_color=bool(need_color),
            need_color_band=bool(need_color_band),
            need_scatter=bool(need_scatter),
            need_hsv_hist=bool(need_hsv_hist),
            need_graph_data=bool(need_graph_data),
            need_bgr_emit=bool(need_bgr_emit),
            loop_interval=float(loop_interval),
            idle_sleep_sec=max(0.01, float(loop_interval)),
        )

    def _should_skip_loop_iteration(self, state: AnalyzerLoopState) -> bool:
        """表示要求や UI 側の消費状況に応じて1ループ休止する。"""
        if not state.need_graph_data and not state.need_bgr_emit:
            # 表示先が1つもない間はキャプチャ/解析を休止してCPU使用率を下げる。
            time.sleep(state.idle_sleep_sec)
            return True
        if self._result_inflight.is_set():
            # UIが前フレームを消費中の間は新規キャプチャを抑止して無駄負荷を避ける。
            time.sleep(state.idle_sleep_sec)
            return True
        return False

    def _maybe_emit_loop_payload(
        self,
        state: AnalyzerLoopState,
        frame: AnalyzerFrameState,
    ) -> None:
        """通知条件を満たす場合だけ payload を組み立てて emit する。"""
        if not frame.emit_now:
            return
        # グラフ更新なしでも画像プレビューが必要なら通知する。
        should_emit_payload = state.need_bgr_emit or (frame.graph_update and state.need_graph_data)
        if not should_emit_payload:
            return
        dt_ms = (time.perf_counter() - frame.started_at) * 1000.0
        payload = live_graph_data.build_result_payload(
            bgr=frame.bgr,
            cap=frame.cap,
            graph_data=frame.graph_data,
            graph_update=bool(frame.graph_update),
            need_bgr_emit=bool(state.need_bgr_emit),
            dt_ms=float(dt_ms),
        )
        self._emit_result_if_possible(payload, cfg=state.cfg)

    def _run_loop_iteration(self, sct) -> None:
        """メインループ1回分の判定・取得・通知を実行する。"""
        t0 = time.perf_counter()
        state = self._loop_state()
        if self._should_skip_loop_iteration(state):
            return

        # 1フレーム取得。
        bgr, cap = self._capture_frame_for_loop(sct, state.capture)
        if bgr is None or cap is None:
            return

        frame = self._frame_state_for_loop(
            state,
            started_at=float(t0),
            bgr=bgr,
            cap=cap,
        )
        self._maybe_emit_loop_payload(state, frame)

        # ループ周期を維持。
        self._sleep_remaining_loop_interval(state, float(t0))

    def _run(self):
        """キャプチャ/解析/通知を繰り返すメインループ。"""
        # mss は with 内で使い回し、毎フレーム初期化コストを避ける。
        with mss.mss() as sct:
            while not self._stop.is_set():
                self._run_loop_iteration(sct)
