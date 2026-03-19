"""Qt ウィジェット制御の共通補助関数。"""

from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtCore import QObject, QRect, QSignalBlocker
from PySide6.QtGui import QGuiApplication

_FALLBACK_SCREEN_RECT = QRect(0, 0, 1920, 1080)


@contextmanager
def blocked_signals(obj: QObject) -> Iterator[None]:
    """`obj` の Qt シグナルを一時的にブロックする。"""
    _blocker = QSignalBlocker(obj)
    try:
        yield
    finally:
        del _blocker


def screen_union_geometry(available: bool = False) -> QRect:
    """全スクリーンを覆う矩形を返す。"""
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


def set_current_index_blocked(widget: QObject, index: int) -> None:
    """シグナルを止めた状態で `setCurrentIndex` を呼ぶ。"""
    with blocked_signals(widget):
        widget.setCurrentIndex(int(index))


def set_checked_blocked(widget: QObject, checked: bool) -> None:
    """シグナルを止めた状態で `setChecked` を呼ぶ。"""
    with blocked_signals(widget):
        widget.setChecked(bool(checked))


def set_visible_if(widget: QObject | None, visible: bool) -> None:
    """`widget` が存在するときだけ `setVisible` を呼ぶ。"""
    if widget is None:
        return
    widget.setVisible(bool(visible))


def set_visible_if_changed(widget: QObject | None, visible: bool) -> None:
    """可視状態が変わるときだけ `setVisible` を呼ぶ。"""
    if widget is None:
        return
    show = bool(visible)
    try:
        if widget.isHidden() == (not show):
            return
    except Exception:
        pass
    widget.setVisible(show)


def set_enabled_if(widget: QObject | None, enabled: bool) -> None:
    """`widget` が存在するときだけ `setEnabled` を呼ぶ。"""
    if widget is None:
        return
    widget.setEnabled(bool(enabled))


def rect_to_dict(rect) -> dict[str, int] | None:
    """QRect互換オブジェクトを `{x,y,w,h}` へ変換する。"""
    if rect is None:
        return None
    try:
        x = int(rect.x())
        y = int(rect.y())
        w = int(rect.width())
        h = int(rect.height())
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def dict_to_rect(raw) -> QRect | None:
    """`{x,y,w,h}` 辞書を検証済み `QRect` に変換する。"""
    if not isinstance(raw, dict):
        return None
    try:
        x = int(raw.get("x"))
        y = int(raw.get("y"))
        w = int(raw.get("w"))
        h = int(raw.get("h"))
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    return QRect(x, y, w, h)


def is_widget_renderable(widget: QObject) -> bool:
    """ウィジェットが実描画対象として更新可能かを返す。"""
    if widget is None:
        return False
    try:
        if not widget.isVisible() or widget.isHidden():
            return False
    except Exception:
        return False

    try:
        if widget.width() <= 1 or widget.height() <= 1:
            return False
    except Exception:
        pass

    try:
        win = widget.window()
        if win is not None and win.isMinimized():
            return False
    except Exception:
        pass
    return True


def safe_window_handle(widget: QObject | None):
    """`windowHandle()` を安全に取得し、失敗時は `None` を返す。"""
    if widget is None:
        return None
    try:
        return widget.windowHandle()
    except Exception:
        return None
