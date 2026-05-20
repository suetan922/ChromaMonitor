"""画像ドロップ受付用の overlay/controller。"""

from collections.abc import Callable, Iterable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtWidgets import QLabel, QWidget

from ..util.theme import get_ui_theme, qcolor


def _overlay_style_payload(theme_name: str | None) -> tuple[tuple[int, ...], str]:
    """テーマ名から overlay style の比較キーと stylesheet を作る。"""
    theme = get_ui_theme(theme_name)
    fill = qcolor(theme.panel_bg, 176)
    border = qcolor(theme.accent, 132)
    text = qcolor(theme.text_primary)
    style_key = (
        fill.red(),
        fill.green(),
        fill.blue(),
        fill.alpha(),
        border.red(),
        border.green(),
        border.blue(),
        border.alpha(),
        text.red(),
        text.green(),
        text.blue(),
        text.alpha(),
    )
    stylesheet = (
        "font-size:14px; font-weight:600; border-radius:6px;"
        f"background:rgba({fill.red()}, {fill.green()}, {fill.blue()}, {fill.alpha()});"
        f"border:2px dashed rgba({border.red()}, {border.green()}, {border.blue()}, {border.alpha()});"
        f"color:rgba({text.red()}, {text.green()}, {text.blue()}, {text.alpha()});"
    )
    return style_key, stylesheet


def _apply_overlay_label_style(
    overlay: QLabel,
    *,
    theme_name: str | None,
    cached_key: tuple[int, ...] | None,
) -> tuple[int, ...]:
    """必要なときだけ overlay stylesheet を再適用する。"""
    style_key, stylesheet = _overlay_style_payload(theme_name)
    if style_key != cached_key:
        overlay.setStyleSheet(stylesheet)
    return style_key


def _set_overlay_visible(
    overlay: QLabel,
    visible: bool,
    *,
    raise_when_visible: bool = False,
) -> None:
    """表示状態だけが変わるときだけ overlay visibility を更新する。"""
    target_visible = bool(visible)
    if overlay.isVisible() != target_visible:
        overlay.setVisible(target_visible)
    if target_visible and raise_when_visible:
        overlay.raise_()


def _extract_supported_drop_paths(
    mime_data,
    path_filter: Callable[[str], bool],
) -> list[str]:
    """mime data から重複を除いた対応ファイル一覧を取り出す。"""
    if mime_data is None or not bool(mime_data.hasUrls()):
        return []
    paths: list[str] = []
    seen: set[str] = set()
    for url in mime_data.urls():
        if url is None or not bool(url.isLocalFile()):
            continue
        path = str(url.toLocalFile() or "").strip()
        if not path or path in seen:
            continue
        if not bool(path_filter(path)):
            continue
        seen.add(path)
        paths.append(path)
    return paths


class ImageDropTargetController(QObject):
    """既存 widget に drag & drop オーバーレイと受付処理を追加する。"""

    def __init__(
        self,
        widget: QWidget,
        *,
        path_filter: Callable[[str], bool],
        can_drop_callback: Callable[[], bool],
        drop_handler: Callable[[list[str]], None],
        overlay_text: str = "画像をドロップして読み込み",
    ):
        """対象 widget と受付判定・完了処理を保持して初期化する。"""
        super().__init__(widget)
        self._widget = widget
        self._path_filter = path_filter
        self._can_drop_callback = can_drop_callback
        self._drop_handler = drop_handler
        self._overlay = QLabel(str(overlay_text), widget)
        self._overlay.setAlignment(Qt.AlignCenter)
        self._overlay.setWordWrap(True)
        self._overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._overlay.hide()
        self._overlay_style_key: tuple[int, ...] | None = None
        self._apply_overlay_style()
        self._sync_overlay_geometry()
        widget.setAcceptDrops(True)
        widget.installEventFilter(self)

    def _apply_overlay_style(self) -> None:
        """現在テーマに合わせてオーバーレイを描画する。"""
        theme_name = getattr(self._widget.window(), "_ui_theme_name", None)
        self._overlay_style_key = _apply_overlay_label_style(
            self._overlay,
            theme_name=theme_name,
            cached_key=self._overlay_style_key,
        )

    def _sync_overlay_geometry(self) -> None:
        """対象 widget に追従するようオーバーレイ矩形を更新する。"""
        self._overlay.setGeometry(self._widget.rect())
        self._overlay.raise_()

    def _show_overlay(self, visible: bool) -> None:
        """オーバーレイの一時表示を切り替える。"""
        _set_overlay_visible(self._overlay, visible)

    def _extract_supported_paths(self, mime_data) -> list[str]:
        """mime data から対応画像ファイルのみ抽出する。"""
        return _extract_supported_drop_paths(mime_data, self._path_filter)

    def _accepts(self, mime_data) -> tuple[bool, list[str]]:
        """現在の drag / drop を受け付けるか返す。"""
        paths = self._extract_supported_paths(mime_data)
        if not paths:
            return False, []
        if not bool(self._can_drop_callback()):
            return False, paths
        return True, paths

    def eventFilter(self, obj, event):
        """対象 widget の drag/drop と resize/show を処理する。"""
        if obj is not self._widget:
            return super().eventFilter(obj, event)

        event_type = event.type()
        if event_type in (QEvent.Resize, QEvent.Show):
            self._apply_overlay_style()
            self._sync_overlay_geometry()
            return False

        if event_type == QEvent.Hide:
            self._show_overlay(False)
            return False

        if event_type == QEvent.DragEnter:
            accepted, _paths = self._accepts(event.mimeData())
            self._apply_overlay_style()
            self._show_overlay(accepted)
            if accepted:
                event.acceptProposedAction()
            else:
                event.ignore()
            return True

        if event_type == QEvent.DragMove:
            accepted, _paths = self._accepts(event.mimeData())
            self._apply_overlay_style()
            self._show_overlay(accepted)
            if accepted:
                event.acceptProposedAction()
            else:
                event.ignore()
            return True

        if event_type == QEvent.DragLeave:
            self._show_overlay(False)
            event.accept()
            return True

        if event_type == QEvent.Drop:
            accepted, paths = self._accepts(event.mimeData())
            self._show_overlay(False)
            if accepted:
                self._drop_handler(paths)
                event.acceptProposedAction()
            else:
                event.ignore()
            return True

        return super().eventFilter(obj, event)


def install_image_drop_target(
    widget: QWidget,
    *,
    path_filter: Callable[[str], bool],
    can_drop_callback: Callable[[], bool],
    drop_handler: Callable[[list[str]], None],
    overlay_text: str = "画像をドロップして読み込み",
) -> ImageDropTargetController:
    """既存 widget へ画像ドロップ受付を追加する。"""
    return ImageDropTargetController(
        widget,
        path_filter=path_filter,
        can_drop_callback=can_drop_callback,
        drop_handler=drop_handler,
        overlay_text=overlay_text,
    )


def dock_area_union_rect(dock_widgets: Iterable[QWidget]) -> QRect:
    """visible かつ非 floating な dock の geometry union を返す。"""
    union_rect = QRect()
    has_rect = False
    for dock in dock_widgets:
        if dock is None or not bool(dock.isVisible()):
            continue
        is_floating = getattr(dock, "isFloating", None)
        if callable(is_floating) and bool(is_floating()):
            continue
        rect = QRect(dock.geometry())
        if rect.width() <= 1 or rect.height() <= 1:
            continue
        union_rect = rect if not has_rect else union_rect.united(rect)
        has_rect = True
    return union_rect


def dock_area_overlay_rect(dock_widgets: Iterable[QWidget], fallback_rect: QRect) -> QRect:
    """dock union が空なら fallback を返す overlay 用矩形。"""
    rect = dock_area_union_rect(dock_widgets)
    if not rect.isNull():
        return rect
    fallback = QRect(fallback_rect)
    if fallback.width() <= 1 or fallback.height() <= 1:
        return QRect()
    return fallback


def map_widget_rect(widget: QWidget | None, target: QWidget | None) -> QRect:
    """widget の rect を target ローカル座標へ変換する。"""
    if widget is None or target is None or not bool(widget.isVisible()):
        return QRect()
    top_left = QPoint(0, 0) if widget is target else widget.mapTo(target, QPoint(0, 0))
    rect = QRect(top_left, widget.size())
    if rect.width() <= 1 or rect.height() <= 1:
        return QRect()
    return rect


def resolve_fallback_drop_widget(main_window: QWidget) -> QWidget | None:
    """dock 全閉時に drop を受ける既存中央領域 widget を返す。"""
    fallback = getattr(main_window, "central_container", None)
    if fallback is not None:
        return fallback
    central_widget_getter = getattr(main_window, "centralWidget", None)
    if callable(central_widget_getter):
        return central_widget_getter()
    return None


class DockAreaImageDropController(QObject):
    """dock 領域全体へ 1 枚 overlay を出す drag & drop controller。"""

    def __init__(
        self,
        main_window: QWidget,
        *,
        dock_widgets: Iterable[QWidget],
        path_filter: Callable[[str], bool],
        can_drop_callback: Callable[[], bool],
        drop_handler: Callable[[list[str]], None],
        overlay_text: str = "画像をドロップして読み込み",
    ):
        """main window と監視対象 dock 群を保持して初期化する。"""
        super().__init__(main_window)
        self._main_window = main_window
        self._dock_widgets = tuple(dock_widgets)
        self._fallback_widget = resolve_fallback_drop_widget(main_window)
        self._path_filter = path_filter
        self._can_drop_callback = can_drop_callback
        self._drop_handler = drop_handler
        self._overlay = QLabel(str(overlay_text), main_window)
        self._overlay.setAlignment(Qt.AlignCenter)
        self._overlay.setWordWrap(True)
        self._overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._overlay.hide()
        self._overlay_style_key: tuple[int, ...] | None = None
        self._apply_overlay_style()
        self._sync_overlay_geometry()
        self._install_watch_targets()

    def _install_watch_targets(self) -> None:
        """main window と各 dock に drag/drop 監視を入れる。"""
        self._main_window.setAcceptDrops(True)
        self._main_window.installEventFilter(self)
        if self._fallback_widget is not None:
            self._fallback_widget.setAcceptDrops(True)
            self._fallback_widget.installEventFilter(self)
        for dock in self._dock_widgets:
            if dock is None:
                continue
            dock.setAcceptDrops(True)
            dock.installEventFilter(self)

    def _apply_overlay_style(self) -> None:
        """現在テーマに合わせてオーバーレイを描画する。"""
        theme_name = getattr(self._main_window, "_ui_theme_name", None)
        self._overlay_style_key = _apply_overlay_label_style(
            self._overlay,
            theme_name=theme_name,
            cached_key=self._overlay_style_key,
        )

    def _dock_area_rect(self) -> QRect:
        """表示中 dock 領域全体の overlay 用矩形を返す。"""
        rect = dock_area_overlay_rect(
            self._dock_widgets,
            self._fallback_rect(),
        )
        if rect.isNull():
            return QRect()
        return rect.intersected(self._main_window.rect())

    def _fallback_rect(self) -> QRect:
        """dock 全閉時に使う既存中央領域の矩形を返す。"""
        return map_widget_rect(self._fallback_widget, self._main_window)

    def _sync_overlay_geometry(self) -> None:
        """overlay を現在の dock area union に追従させる。"""
        rect = self._dock_area_rect()
        self._overlay.setGeometry(rect)
        self._overlay.raise_()

    def _show_overlay(self, visible: bool) -> None:
        """overlay の表示を切り替える。"""
        visible = bool(visible) and not self._dock_area_rect().isNull()
        _set_overlay_visible(self._overlay, visible, raise_when_visible=True)

    def _extract_supported_paths(self, mime_data) -> list[str]:
        """mime data から対応画像ファイルのみ抽出する。"""
        return _extract_supported_drop_paths(mime_data, self._path_filter)

    def _event_pos_in_main_window(self, obj, event) -> QPoint:
        """drag event 座標を main window ローカル座標へ変換する。"""
        point = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if obj is self._main_window:
            return QPoint(point)
        if isinstance(obj, QWidget):
            return obj.mapTo(self._main_window, point)
        return QPoint(point)

    def _accepts(self, mime_data, *, local_pos: QPoint) -> tuple[bool, list[str]]:
        """現在の drag / drop を受け付けるか返す。"""
        paths = self._extract_supported_paths(mime_data)
        if not paths:
            return False, []
        area_rect = self._dock_area_rect()
        if area_rect.isNull() or not area_rect.contains(local_pos):
            return False, paths
        if not bool(self._can_drop_callback()):
            return False, paths
        return True, paths

    def eventFilter(self, obj, event):
        """main window / dock の drag/drop と geometry 変化を処理する。"""
        main_window = getattr(self, "_main_window", None)
        fallback_widget = getattr(self, "_fallback_widget", None)
        dock_widgets = getattr(self, "_dock_widgets", ())
        if main_window is None:
            return super().eventFilter(obj, event)
        watched = (
            obj is main_window
            or obj is fallback_widget
            or obj in dock_widgets
        )
        if not watched:
            return super().eventFilter(obj, event)

        event_type = event.type()
        if event_type in (QEvent.Move, QEvent.Resize, QEvent.Show):
            self._apply_overlay_style()
            self._sync_overlay_geometry()
            return False

        if event_type == QEvent.Hide:
            self._show_overlay(False)
            return False

        if event_type in (QEvent.DragEnter, QEvent.DragMove):
            local_pos = self._event_pos_in_main_window(obj, event)
            accepted, _paths = self._accepts(event.mimeData(), local_pos=local_pos)
            self._apply_overlay_style()
            self._sync_overlay_geometry()
            self._show_overlay(accepted)
            if accepted:
                event.acceptProposedAction()
            else:
                event.ignore()
            return True

        if event_type == QEvent.DragLeave:
            self._show_overlay(False)
            event.accept()
            return True

        if event_type == QEvent.Drop:
            local_pos = self._event_pos_in_main_window(obj, event)
            accepted, paths = self._accepts(event.mimeData(), local_pos=local_pos)
            self._show_overlay(False)
            if accepted:
                self._drop_handler(paths)
                event.acceptProposedAction()
            else:
                event.ignore()
            return True

        return super().eventFilter(obj, event)


def install_dock_area_image_drop_target(
    main_window: QWidget,
    *,
    dock_widgets: Iterable[QWidget],
    path_filter: Callable[[str], bool],
    can_drop_callback: Callable[[], bool],
    drop_handler: Callable[[list[str]], None],
    overlay_text: str = "画像をドロップして読み込み",
) -> DockAreaImageDropController:
    """dock 領域全体向けの画像ドロップ controller を追加する。"""
    return DockAreaImageDropController(
        main_window,
        dock_widgets=dock_widgets,
        path_filter=path_filter,
        can_drop_callback=can_drop_callback,
        drop_handler=drop_handler,
        overlay_text=overlay_text,
    )
