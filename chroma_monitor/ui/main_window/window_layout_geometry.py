"""ウィンドウ/ダイアログ/トップレベル部品のジオメトリ補正。"""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QSizePolicy, QToolBar, QWidget

from ...util.qt_helpers import screen_union_geometry
from .window_layout_common import (
    _DIALOG_FIT_MARGIN_PX,
    _DIALOG_MIN_H,
    _DIALOG_MIN_W,
    _MAIN_WINDOW_COMPACT_MIN_H_FLOOR,
    _MAIN_WINDOW_COMPACT_MIN_W_FLOOR,
    _MAIN_WINDOW_FIT_MARGIN_PX,
    _MAIN_WINDOW_MAX_H_FLOOR,
    _MAIN_WINDOW_MAX_W_FLOOR,
    _MAIN_WINDOW_MIN_H,
    _MAIN_WINDOW_MIN_W,
    _PLACEHOLDER_SHOW_MIN_H,
    _PLACEHOLDER_SHOW_MIN_W,
    _TOPLEVEL_FIT_MARGIN_PX,
    _TOPLEVEL_MAX_H_FLOOR,
    _TOPLEVEL_MAX_W_FLOOR,
    _TOPLEVEL_MIN_H,
    _TOPLEVEL_MIN_W,
)


def desktop_available_geometry(main_window) -> QRect:
    """メインウィンドウ基準の利用可能デスクトップ領域を返す。"""
    rect = screen_union_geometry(available=True)
    if rect.isValid() and rect.width() > 0 and rect.height() > 0:
        return rect
    return rect


def _available_geometry_for_widget(main_window, widget: QWidget | None = None) -> QRect:
    """対象ウィジェット基準の利用可能領域を返す。"""
    screen_candidates = []
    if widget is not None:
        try:
            ws = widget.screen()
            if ws is not None:
                screen_candidates.append(ws)
        except Exception:
            pass
        try:
            center = widget.frameGeometry().center()
            at_center = QGuiApplication.screenAt(center)
            if at_center is not None and at_center not in screen_candidates:
                screen_candidates.append(at_center)
        except Exception:
            pass
    try:
        ms = main_window.screen()
        if ms is not None and ms not in screen_candidates:
            screen_candidates.append(ms)
    except Exception:
        pass

    for screen in screen_candidates:
        rect = screen.availableGeometry()
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            return rect
    return screen_union_geometry(available=True)


def _compact_main_window_min_size(main_window) -> tuple[int, int]:
    """ドック0件時に必要となる最小クライアントサイズを返す。"""
    toolbar = main_window.findChild(QToolBar, "controlToolbar")
    toolbar_hint = toolbar.sizeHint() if toolbar is not None else QSize()
    menubar = main_window.menuBar() if hasattr(main_window, "menuBar") else None
    menubar_h = int(menubar.sizeHint().height()) if menubar is not None else 0
    min_w = max(
        _MAIN_WINDOW_COMPACT_MIN_W_FLOOR,
        int(toolbar_hint.width()) + 12,
    )
    min_h = max(
        _MAIN_WINDOW_COMPACT_MIN_H_FLOOR,
        int(toolbar_hint.height()) + menubar_h,
    )
    return int(min_w), int(min_h)


def _apply_main_window_minimum(main_window, has_visible_dock: bool) -> None:
    """ドック可視状態に応じてメインウィンドウの最小サイズを切り替える。"""
    if has_visible_dock:
        target_w, target_h = _MAIN_WINDOW_MIN_W, _MAIN_WINDOW_MIN_H
    else:
        target_w, target_h = _compact_main_window_min_size(main_window)
    if int(main_window.minimumWidth()) == int(target_w) and int(main_window.minimumHeight()) == int(
        target_h
    ):
        return
    main_window.setMinimumSize(int(target_w), int(target_h))


def _clamp_top_left_in_available(
    avail: QRect,
    frame: QRect,
    margin: int,
    x: int,
    y: int,
) -> tuple[int, int]:
    """矩形が利用可能領域に収まるよう左上座標を丸める。"""
    min_x = avail.left() + margin
    min_y = avail.top() + margin
    max_x = avail.right() - margin - frame.width() + 1
    max_y = avail.bottom() - margin - frame.height() + 1
    if max_x < min_x:
        max_x = min_x
    if max_y < min_y:
        max_y = min_y
    return min(max(int(x), min_x), max_x), min(max(int(y), min_y), max_y)


def fit_window_to_desktop(main_window):
    """メインウィンドウを利用可能領域内へ収める。"""
    if main_window.isMaximized() or main_window.isFullScreen():
        return
    avail = desktop_available_geometry(main_window)
    if avail.width() <= 0 or avail.height() <= 0:
        return

    margin = _MAIN_WINDOW_FIT_MARGIN_PX
    max_w = max(_MAIN_WINDOW_MAX_W_FLOOR, avail.width() - margin * 2)
    max_h = max(_MAIN_WINDOW_MAX_H_FLOOR, avail.height() - margin * 2)

    frame = main_window.frameGeometry()
    geom = main_window.geometry()
    extra_w = max(0, int(frame.width() - geom.width()))
    extra_h = max(0, int(frame.height() - geom.height()))
    max_client_w = max(_MAIN_WINDOW_MAX_W_FLOOR, max_w - extra_w)
    max_client_h = max(_MAIN_WINDOW_MAX_H_FLOOR, max_h - extra_h)
    min_client_w = max(1, int(main_window.minimumWidth()))
    min_client_h = max(1, int(main_window.minimumHeight()))
    target_client_w = min(max(min_client_w, int(geom.width())), max_client_w)
    target_client_h = min(max(min_client_h, int(geom.height())), max_client_h)
    if target_client_w != int(geom.width()) or target_client_h != int(geom.height()):
        main_window.resize(target_client_w, target_client_h)
        frame = main_window.frameGeometry()

    target_x, target_y = _clamp_top_left_in_available(
        avail,
        frame,
        margin,
        frame.x(),
        frame.y(),
    )
    if target_x != frame.x() or target_y != frame.y():
        main_window.move(target_x, target_y)


def schedule_window_fit(main_window):
    """メインウィンドウ位置/サイズ補正をタイマーで予約する。"""
    if main_window.isMinimized() or main_window.isMaximized() or main_window.isFullScreen():
        return
    main_window._fit_window_timer.start()


def fit_dialog_to_desktop(main_window, dialog: QDialog, center_on_parent: bool = False):
    """ダイアログを利用可能領域内へ収めて表示位置を補正する。"""
    avail = _available_geometry_for_widget(main_window, dialog)
    if avail.width() <= 0 or avail.height() <= 0:
        return

    margin = _DIALOG_FIT_MARGIN_PX
    max_w = max(_DIALOG_MIN_W, avail.width() - margin * 2)
    max_h = max(_DIALOG_MIN_H, avail.height() - margin * 2)
    target_w = min(max(_DIALOG_MIN_W, dialog.width()), max_w)
    target_h = min(max(_DIALOG_MIN_H, dialog.height()), max_h)
    if target_w != dialog.width() or target_h != dialog.height():
        dialog.resize(target_w, target_h)

    frame = dialog.frameGeometry()
    use_center = center_on_parent or not avail.intersects(frame)
    if use_center:
        base = main_window.frameGeometry().center() if main_window.isVisible() else avail.center()
        target_x = base.x() - frame.width() // 2
        target_y = base.y() - frame.height() // 2
    else:
        target_x = frame.x()
        target_y = frame.y()

    target_x, target_y = _clamp_top_left_in_available(
        avail,
        frame,
        margin,
        target_x,
        target_y,
    )
    dialog.move(target_x, target_y)


def fit_top_level_widget_to_desktop(
    main_window,
    widget: QWidget,
    *,
    allow_resize: bool = True,
    allow_move: bool = True,
):
    """トップレベルウィジェットを利用可能領域内へ収める。"""
    avail = _available_geometry_for_widget(main_window, widget)
    if avail.width() <= 0 or avail.height() <= 0:
        return
    if widget.windowState() & Qt.WindowMinimized:
        return

    margin = _TOPLEVEL_FIT_MARGIN_PX
    frame = widget.frameGeometry()
    if allow_resize:
        max_w = max(_TOPLEVEL_MAX_W_FLOOR, avail.width() - margin * 2)
        max_h = max(_TOPLEVEL_MAX_H_FLOOR, avail.height() - margin * 2)

        geom = widget.geometry()
        extra_w = max(0, int(frame.width() - geom.width()))
        extra_h = max(0, int(frame.height() - geom.height()))
        max_client_w = max(_TOPLEVEL_MAX_W_FLOOR, max_w - extra_w)
        max_client_h = max(_TOPLEVEL_MAX_H_FLOOR, max_h - extra_h)
        target_client_w = min(max(_TOPLEVEL_MIN_W, int(geom.width())), max_client_w)
        target_client_h = min(max(_TOPLEVEL_MIN_H, int(geom.height())), max_client_h)
        if target_client_w != int(geom.width()) or target_client_h != int(geom.height()):
            widget.resize(target_client_w, target_client_h)
            frame = widget.frameGeometry()

    if allow_move:
        move_avail = screen_union_geometry(available=True)
        if not move_avail.isValid() or move_avail.width() <= 0 or move_avail.height() <= 0:
            move_avail = avail
        target_x, target_y = _clamp_top_left_in_available(
            move_avail,
            frame,
            margin,
            frame.x(),
            frame.y(),
        )
        if target_x != frame.x() or target_y != frame.y():
            widget.move(target_x, target_y)


def update_placeholder(main_window):
    """可視ドック有無に応じて中央プレースホルダ表示を切り替える。"""
    any_visible = any(
        dock.isVisible()
        and not dock.isFloating()
        and main_window.dockWidgetArea(dock) != Qt.NoDockWidgetArea
        for dock in main_window._dock_map.values()
    )
    _apply_main_window_minimum(main_window, any_visible)
    main_window.central_container.setMaximumSize(16777215, 16777215)
    main_window.central_container.setMinimumSize(0, 0)
    if any_visible:
        main_window.placeholder.hide()
        main_window.central_container.hide()
    else:
        central_size = main_window.central_container.size()
        should_show_placeholder = (
            int(central_size.width()) >= _PLACEHOLDER_SHOW_MIN_W
            and int(central_size.height()) >= _PLACEHOLDER_SHOW_MIN_H
        )
        if should_show_placeholder:
            main_window.placeholder.show()
        else:
            main_window.placeholder.hide()
        main_window.central_container.show()
        main_window.central_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    main_window.central_container.updateGeometry()
