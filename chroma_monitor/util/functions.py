"""UI/解析まわりで再利用する小さな共通関数群。"""

import math
from contextlib import contextmanager
from typing import Any, Iterator, Sequence, Tuple, TypeVar

import cv2
import numpy as np
from PySide6.QtCore import QObject, QRect, QSignalBlocker, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPixmap

T = TypeVar("T")
#: 描画変換時に許可する最大ピクセル辺長。
_MAX_RENDER_EDGE = 2048
#: 描画変換時に許可する最大ピクセル面積。
_MAX_RENDER_AREA = _MAX_RENDER_EDGE * _MAX_RENDER_EDGE
#: スクリーン情報取得に失敗した場合のフォールバック矩形。
_FALLBACK_SCREEN_RECT = QRect(0, 0, 1920, 1080)


@contextmanager
def blocked_signals(obj: QObject) -> Iterator[None]:
    """`obj` の Qt シグナルを一時的にブロックする。

    設定反映時の相互更新でシグナルが再入するのを防ぎたいときに使う。
    `with` を抜けた時点で必ず元の状態へ戻る。

    Args:
        obj: シグナルを一時停止する対象オブジェクト。

    Yields:
        None: ブロック中のコンテキスト。
    """
    blocker = QSignalBlocker(obj)
    try:
        yield
    finally:
        del blocker


def clamp_int(value: int, low: int, high: int) -> int:
    """整数値を `[low, high]` の範囲に収める。

    Args:
        value: 対象値。
        low: 下限値。
        high: 上限値。

    Returns:
        範囲内へ丸めた整数値。
    """
    return max(low, min(high, int(value)))


def clamp_float(value: float, low: float, high: float) -> float:
    """浮動小数点値を `[low, high]` の範囲に収める。

    Args:
        value: 対象値。
        low: 下限値。
        high: 上限値。

    Returns:
        範囲内へ丸めた浮動小数点値。
    """
    return max(float(low), min(float(high), float(value)))


def safe_int(value: Any, default: int) -> int:
    """`value` を整数へ変換し、失敗時は `default` を返す。

    Args:
        value: 整数化したい入力値。
        default: 変換失敗時の代替値。

    Returns:
        変換結果、または代替値。
    """
    try:
        return int(value)
    except Exception:
        return int(default)


def screen_union_geometry(available: bool = False) -> QRect:
    """全スクリーンを覆う矩形を返す。

    複数ディスプレイ環境では各画面矩形の和集合を返す。
    画面情報が取れない場合はプライマリ画面、最後に固定フォールバックを使う。

    Args:
        available: `True` の場合はタスクバー等を除いた `availableGeometry` を使う。

    Returns:
        利用可能なスクリーン領域を表す矩形。
    """
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
    return QRect(_FALLBACK_SCREEN_RECT)


def safe_choice(value: T, allowed: Sequence[T], default: T) -> T:
    """`value` が候補にあるときのみ採用し、なければ `default` を返す。

    Args:
        value: 判定対象値。
        allowed: 許可する候補値の列。
        default: 候補外だった場合の代替値。

    Returns:
        `value` または `default`。
    """
    return value if value in allowed else default


def set_current_index_blocked(widget: QObject, index: int) -> None:
    """シグナルを止めた状態で `setCurrentIndex` を呼ぶ。

    Args:
        widget: `setCurrentIndex(int)` を持つ Qt ウィジェット。
        index: 設定するインデックス。
    """
    with blocked_signals(widget):
        widget.setCurrentIndex(int(index))


def set_checked_blocked(widget: QObject, checked: bool) -> None:
    """シグナルを止めた状態で `setChecked` を呼ぶ。

    Args:
        widget: `setChecked(bool)` を持つ Qt ウィジェット。
        checked: 設定するチェック状態。
    """
    with blocked_signals(widget):
        widget.setChecked(bool(checked))


def resize_by_long_edge(
    img: np.ndarray, max_dim: int, interpolation: int = cv2.INTER_AREA
) -> np.ndarray:
    """画像を長辺基準で縮小する。

    既に `max_dim` 以下なら元画像をそのまま返す。縦横比は維持する。

    Args:
        img: 入力画像 (`H x W x C` または `H x W`)。
        max_dim: 長辺の上限ピクセル。`0` 以下は縮小しない。
        interpolation: `cv2.resize` の補間方式。

    Returns:
        縮小後画像、または元画像。
    """
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


def _clamp_render_size(width: int, height: int) -> Tuple[int, int]:
    """描画用サイズを安全上限に収める。

    辺長上限と面積上限の両方を適用し、過大な `QPixmap` 生成を抑える。

    Args:
        width: 要求幅。
        height: 要求高。

    Returns:
        上限適用後の `(width, height)`。
    """
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


def _scaled_qpixmap_from_qimage(qimg: QImage, max_w: int, max_h: int) -> QPixmap:
    """`QImage` を描画上限つきで `QPixmap` に変換して縮小する。

    Args:
        qimg: 元画像。
        max_w: 表示先の最大幅。
        max_h: 表示先の最大高さ。

    Returns:
        `Qt.KeepAspectRatio` で縮小した `QPixmap`。
    """
    pm = QPixmap.fromImage(qimg)
    max_w, max_h = _clamp_render_size(max_w, max_h)
    return pm.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def rgb_to_qpixmap(rgb: np.ndarray, max_w: int, max_h: int) -> QPixmap:
    """NumPy の RGB 配列を `QPixmap` に変換する。

    Args:
        rgb: `uint8` の RGB 配列 (`H x W x 3`)。
        max_w: 表示先の最大幅。
        max_h: 表示先の最大高さ。

    Returns:
        表示上限内に収まる `QPixmap`。
    """
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
    return _scaled_qpixmap_from_qimage(qimg, max_w=max_w, max_h=max_h)


def bgr_to_qpixmap(bgr: np.ndarray, max_w: int = 560, max_h: int = 420) -> QPixmap:
    """NumPy の BGR 配列を `QPixmap` に変換する。

    Args:
        bgr: `uint8` の BGR 配列 (`H x W x 3`)。
        max_w: 表示先の最大幅。
        max_h: 表示先の最大高さ。

    Returns:
        表示上限内に収まる `QPixmap`。
    """
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb_to_qpixmap(rgb, max_w=max_w, max_h=max_h)
