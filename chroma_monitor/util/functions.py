import math
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Sequence, Tuple, TypeVar

import cv2
import numpy as np
from PySide6.QtCore import QObject, QRect, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QComboBox

from . import constants as C

T = TypeVar("T")
_MAX_RENDER_EDGE = 2048
_MAX_RENDER_AREA = _MAX_RENDER_EDGE * _MAX_RENDER_EDGE


@contextmanager
def blocked_signals(obj: QObject) -> Iterator[None]:
    # 一時的にシグナルを止め、UI相互更新の無限ループを防ぐ。
    blocker = QSignalBlocker(obj)
    try:
        yield
    finally:
        del blocker


def clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def clamp_float(value: float, low: float, high: float) -> float:
    return max(float(low), min(float(high), float(value)))


def screen_union_geometry(available: bool = False) -> QRect:
    """Return the union rect of all screens with a safe fallback."""
    screens = QGuiApplication.screens()
    if screens:
        first = screens[0].availableGeometry() if available else screens[0].geometry()
        rect = QRect(first)
        for screen in screens[1:]:
            part = screen.availableGeometry() if available else screen.geometry()
            rect = rect.united(part)
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            return rect

    ps = QGuiApplication.primaryScreen()
    if ps is not None:
        fallback_rect = ps.availableGeometry() if available else ps.virtualGeometry()
        if fallback_rect.isValid() and fallback_rect.width() > 0 and fallback_rect.height() > 0:
            return fallback_rect
    return QRect(0, 0, 1920, 1080)


def safe_choice(value: T, allowed: Sequence[T], default: T) -> T:
    # 候補外の値を受けても既定値で安全に継続する。
    return value if value in allowed else default


def set_current_index_blocked(widget: QObject, index: int) -> None:
    with blocked_signals(widget):
        widget.setCurrentIndex(int(index))


def set_checked_blocked(widget: QObject, checked: bool) -> None:
    with blocked_signals(widget):
        widget.setChecked(bool(checked))


def set_value_blocked(widget: QObject, value: Any) -> None:
    with blocked_signals(widget):
        widget.setValue(value)


def set_combobox_data_blocked(combo: QComboBox, data: Any, default_data: Any = None) -> int:
    # data -> default_data -> index0 の順でフォールバックする。
    index = combo.findData(data)
    if index < 0 and default_data is not None:
        index = combo.findData(default_data)
    if index < 0 and combo.count() > 0:
        index = 0
    if index >= 0:
        set_current_index_blocked(combo, index)
    return index


def resize_by_long_edge(
    img: np.ndarray, max_dim: int, interpolation: int = cv2.INTER_AREA
) -> np.ndarray:
    # 長辺のみを基準に縮小し、縦横比は維持する。
    if img is None:
        return img
    h, w = img.shape[:2]
    max_dim = int(max_dim)
    if max_dim <= 0 or max(h, w) <= max_dim:
        return img
    scale = max_dim / float(max(h, w))
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return cv2.resize(img, (new_w, new_h), interpolation=interpolation)


def clamp_render_size(width: int, height: int) -> Tuple[int, int]:
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


def rgb_to_qpixmap(rgb: np.ndarray, max_w: int, max_h: int) -> QPixmap:
    # NumPy RGB 配列を QPixmap に変換し、表示領域へフィットさせる。
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
    pm = QPixmap.fromImage(qimg)
    max_w, max_h = clamp_render_size(max_w, max_h)
    return pm.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def gray_to_qpixmap(gray: np.ndarray, max_w: int, max_h: int) -> QPixmap:
    # グレースケール配列の軽量変換経路。
    gray = np.ascontiguousarray(gray)
    h, w = gray.shape[:2]
    qimg = QImage(gray.data, w, h, w, QImage.Format_Grayscale8)
    pm = QPixmap.fromImage(qimg)
    max_w, max_h = clamp_render_size(max_w, max_h)
    return pm.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def bgr_to_qpixmap(bgr: np.ndarray, max_w: int = 560, max_h: int = 420) -> QPixmap:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb_to_qpixmap(rgb, max_w=max_w, max_h=max_h)


def top_hue_bars(
    hist: Optional[np.ndarray],
) -> Tuple[str, List[Tuple[str, float, Tuple[int, int, int]]]]:
    """
    実際に使われている色相の上位色をそのまま出す。
    Hueビン（0-179）のうち出現が多い順に C.TOP_COLORS_COUNT 個取り、各ビンの色をそのHueで塗る。
    """
    if hist is None:
        return C.TOP_COLORS_TITLE, []
    hist = np.asarray(hist).astype(np.int64)
    total = float(hist.sum())
    if total <= 0:
        return C.TOP_COLORS_TITLE, []

    top_idx = np.argsort(hist)[::-1]
    bars: List[Tuple[str, float, Tuple[int, int, int]]] = []
    for idx in top_idx[: C.TOP_COLORS_COUNT]:
        count = hist[idx]
        if count <= 0:
            continue
        ratio = count / total
        # Hue idx (0-179) -> actual hue deg = idx*2
        hsv = np.uint8([[[idx * 2, 255, 255]]])
        rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0]
        color = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        bars.append((f"H{idx}", ratio, color))
    return C.TOP_COLORS_TITLE, bars


def render_top_color_bar(
    bars: List[Tuple], width: int = 300, height: int = C.TOP_COLOR_BAR_HEIGHT
) -> QPixmap:
    """
    bars: [(ratio, (r,g,b))] or [(name, ratio, (r,g,b))]
    # 比率バーを横方向へ敷き詰めて表示する。
    """
    safe_w, safe_h = clamp_render_size(width, max(12, height))
    pm = QPixmap(safe_w, safe_h)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    try:
        painter.fillRect(QRect(0, 0, pm.width(), pm.height()), QColor(235, 235, 235))
        show_text = pm.width() >= 240
        x = 0
        remaining = pm.width()
        for item in bars:
            if len(item) == 3:
                _, ratio, color = item
            else:
                ratio, color = item
            w = int(round(pm.width() * ratio))
            w = max(1, min(w, remaining))
            painter.fillRect(QRect(x, 0, w, pm.height()), QColor(*color))
            if show_text and w >= 42:
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
