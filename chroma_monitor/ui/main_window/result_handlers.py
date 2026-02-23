import math

import cv2
import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

from ...util import constants as C

_MAX_RENDER_EDGE = 2048
_MAX_RENDER_AREA = _MAX_RENDER_EDGE * _MAX_RENDER_EDGE
_TOP_BAR_MIN_HEIGHT = 12
_TOP_BAR_TEXT_MIN_WIDTH = 240
_TOP_BAR_TEXT_MIN_SEGMENT_PX = 42


def _clamp_render_size(width: int, height: int) -> tuple[int, int]:
    # 極端に大きい描画要求でメモリが跳ねないよう上限を掛ける。
    w = max(1, int(width))
    h = max(1, int(height))
    w = min(w, _MAX_RENDER_EDGE)
    h = min(h, _MAX_RENDER_EDGE)
    area = w * h
    if area > _MAX_RENDER_AREA:
        scale = math.sqrt(_MAX_RENDER_AREA / float(area))
        w = max(1, int(w * scale))
        h = max(1, int(h * scale))
    return w, h


def top_hue_bars(
    hist: np.ndarray | None,
) -> tuple[str, list[tuple[str, float, tuple[int, int, int]]]]:
    if hist is None:
        return C.TOP_COLORS_TITLE, []
    hist = np.asarray(hist, dtype=np.int64).reshape(-1)
    if hist.size != 180:
        fixed = np.zeros(180, dtype=np.int64)
        n = min(180, hist.size)
        if n > 0:
            fixed[:n] = hist[:n]
        hist = fixed
    total = float(hist.sum())
    if total <= 0:
        return C.TOP_COLORS_TITLE, []

    top_idx = np.argsort(hist)[::-1]
    bars: list[tuple[str, float, tuple[int, int, int]]] = []
    for idx in top_idx[: C.TOP_COLORS_COUNT]:
        count = hist[idx]
        if count <= 0:
            continue
        ratio = float(count) / total
        hsv = np.uint8([[[idx * 2, 255, 255]]])
        rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0]
        bars.append((f"H{idx}", ratio, (int(rgb[0]), int(rgb[1]), int(rgb[2]))))
    return C.TOP_COLORS_TITLE, bars


def _top_bar_item_ratio_color(item: tuple) -> tuple[float, tuple[int, int, int]]:
    if len(item) == 3:
        _, ratio, color = item
    else:
        ratio, color = item
    return float(ratio), tuple(int(c) for c in color)


def render_top_color_bar(
    bars: list[tuple], width: int = 300, height: int = C.TOP_COLOR_BAR_HEIGHT
) -> QPixmap:
    safe_w, safe_h = _clamp_render_size(width, max(_TOP_BAR_MIN_HEIGHT, height))
    pm = QPixmap(safe_w, safe_h)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    try:
        painter.fillRect(QRect(0, 0, pm.width(), pm.height()), QColor(235, 235, 235))
        show_text = pm.width() >= _TOP_BAR_TEXT_MIN_WIDTH
        x = 0
        remaining = pm.width()
        for item in bars:
            ratio, color = _top_bar_item_ratio_color(item)
            w = int(round(pm.width() * ratio))
            w = max(1, min(w, remaining))
            painter.fillRect(QRect(x, 0, w, pm.height()), QColor(*color))
            if show_text and w >= _TOP_BAR_TEXT_MIN_SEGMENT_PX:
                pct = f"{ratio*100:.1f}%"
                painter.setPen(QColor(255, 255, 255) if sum(color) < 400 else QColor(40, 40, 40))
                painter.drawText(QRect(x + 2, 0, w - 4, pm.height()), Qt.AlignCenter, pct)
            x += w
            remaining = pm.width() - x
            if remaining <= 0:
                break
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
    finally:
        painter.end()
    return pm


def refresh_top_color_bar(main_window) -> None:
    # 表示対象がないときはバーを消してキャッシュキーも初期化する。
    bars = getattr(main_window, "_last_top_bars", None)
    if not bars:
        main_window._top_bar_render_key = None
        main_window.top_colors_bar.clear()
        return

    def _bar_key_item(item):
        if len(item) == 3:
            name, ratio, color = item
        else:
            name, ratio, color = "", item[0], item[1]
        return (
            str(name),
            round(float(ratio), 6),
            tuple(int(c) for c in color),
        )

    render_key = (
        int(main_window.top_colors_bar.width()),
        int(main_window.top_colors_bar.height()),
        tuple(_bar_key_item(item) for item in bars),
    )
    # 前回描画と同じ条件なら再レンダリングを省略する。
    if render_key == getattr(main_window, "_top_bar_render_key", None):
        return
    main_window._top_bar_render_key = render_key
    main_window.top_colors_bar.setPixmap(
        render_top_color_bar(
            bars,
            width=main_window.top_colors_bar.width(),
            height=main_window.top_colors_bar.height(),
        )
    )


def update_image_docks_from_frame(main_window, bgr_preview):
    # 可視ドックだけ更新して不要な画像処理を避ける。
    if bgr_preview is None:
        return
    for dock, update_fn, after_fn in getattr(main_window, "_image_update_targets", ()):
        if not dock.isVisible():
            continue
        update_fn(bgr_preview)
        if after_fn is not None:
            after_fn()


def on_result(main_window, res: dict):
    # 例外時でも inflight フラグを解除するため finally で終端する。
    try:
        bgr_preview = res.get("bgr_preview")
        if main_window.preview_window.isVisible() and bgr_preview is not None:
            main_window.preview_window.update_preview(bgr_preview)

        # graph_update が False のときはグラフ系更新をスキップする。
        if res["graph_update"]:
            if res["hist"] is not None and main_window.dock_color.isVisible():
                main_window.wheel.update_hist(res["hist"])
                bars = res.get("top_colors")
                if bars is None:
                    _, bars = top_hue_bars(res["hist"])
                main_window._last_top_bars = bars
                refresh_top_color_bar(main_window)
                main_window.lbl_warmcool.setText(
                    "暖色: "
                    f"{res['warm_ratio']*100:.1f}%   "
                    f"寒色: {res['cool_ratio']*100:.1f}%   "
                    f"その他: {res.get('other_ratio', 0)*100:.1f}%"
                )
            if (
                res["sv"] is not None
                and res["rgb"] is not None
                and main_window.dock_scatter.isVisible()
            ):
                main_window.scatter.update_scatter(res["sv"], res["rgb"])
            if main_window.dock_hist.isVisible():
                h_hist = res.get("h_hist")
                s_hist = res.get("s_hist")
                v_hist = res.get("v_hist")
                h_plane = res.get("h_plane")
                s_plane = res.get("s_plane")
                v_plane = res.get("v_plane")
                need_h_fallback = h_hist is None and h_plane is None
                need_s_fallback = s_hist is None and s_plane is None
                need_v_fallback = v_hist is None and v_plane is None
                # 何らかの理由でヒスト/平面データが欠けた場合は、プレビュー画像から補完して表示欠落を防ぐ。
                if (
                    (need_h_fallback or need_s_fallback or need_v_fallback)
                    and bgr_preview is not None
                    and bgr_preview.size > 0
                ):
                    try:
                        h_full, s_full, v_full = cv2.split(
                            cv2.cvtColor(bgr_preview, cv2.COLOR_BGR2HSV)
                        )
                        if need_h_fallback:
                            h_hist = np.bincount(h_full[s_full > 0].reshape(-1), minlength=180)[
                                :180
                            ].astype(np.int64)
                        if need_s_fallback:
                            s_hist = np.bincount(s_full.reshape(-1), minlength=256)[:256].astype(
                                np.int64
                            )
                        if need_v_fallback:
                            v_hist = np.bincount(v_full.reshape(-1), minlength=256)[:256].astype(
                                np.int64
                            )
                    except Exception:
                        pass
                if h_hist is not None:
                    main_window.hist_h.update_from_hist(h_hist)
                elif h_plane is not None:
                    main_window.hist_h.update_from_values(h_plane)
                if s_hist is not None:
                    main_window.hist_s.update_from_hist(s_hist)
                elif s_plane is not None:
                    main_window.hist_s.update_from_values(s_plane)
                if v_hist is not None:
                    main_window.hist_v.update_from_hist(v_hist)
                elif v_plane is not None:
                    main_window.hist_v.update_from_values(v_plane)
                # H/S/V のY軸上限を揃えて、チャネル間の相対比較をしやすくする。
                shared_max_y = max(
                    int(main_window.hist_h.bucketed_max()),
                    int(main_window.hist_s.bucketed_max()),
                    int(main_window.hist_v.bucketed_max()),
                )
                for hist_view in (main_window.hist_h, main_window.hist_s, main_window.hist_v):
                    hist_view.set_shared_max_y(shared_max_y if shared_max_y > 0 else None)
            update_image_docks_from_frame(main_window, bgr_preview)
    finally:
        main_window.worker.mark_result_consumed()
