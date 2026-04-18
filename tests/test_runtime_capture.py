"""runtime_capture の refresh / restore 回帰テスト。"""

from contextlib import nullcontext
from types import SimpleNamespace

from PySide6.QtCore import QRect

from chroma_monitor.ui.main_window import runtime_capture


class FakeEditor:
    def __init__(self, text: str = "", *, focused: bool = False) -> None:
        self._text = str(text)
        self._focused = bool(focused)

    def hasFocus(self) -> bool:
        return self._focused

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        self._text = str(text)


class FakeView:
    def __init__(self, *, visible: bool = False) -> None:
        self._visible = bool(visible)

    def isVisible(self) -> bool:
        return self._visible


class FakeCombo:
    def __init__(
        self,
        items: list[tuple[str, int | None]] | None = None,
        *,
        current_index: int = -1,
        current_text: str = "",
        combo_focused: bool = False,
        editor_focused: bool = False,
        popup_visible: bool = False,
    ) -> None:
        self._items = list(items or [])
        self._editor = FakeEditor(current_text, focused=editor_focused)
        self._current_index = -1
        self._combo_focused = bool(combo_focused)
        self._view = FakeView(visible=popup_visible)
        self.setCurrentIndex(current_index)

    def count(self) -> int:
        return len(self._items)

    def clear(self) -> None:
        self._items = []
        self._current_index = -1

    def addItem(self, title: str, data: int | None) -> None:
        self._items.append((str(title), data))

    def itemData(self, index: int):
        if 0 <= int(index) < len(self._items):
            return self._items[int(index)][1]
        return None

    def itemText(self, index: int) -> str:
        if 0 <= int(index) < len(self._items):
            return self._items[int(index)][0]
        return ""

    def currentIndex(self) -> int:
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:
        idx = int(index)
        self._current_index = idx if 0 <= idx < len(self._items) else -1
        if self._current_index >= 0:
            self._editor.setText(self.itemText(self._current_index))

    def currentData(self):
        return self.itemData(self._current_index)

    def currentText(self) -> str:
        if self._current_index >= 0:
            return self.itemText(self._current_index)
        return self._editor.text()

    def lineEdit(self) -> FakeEditor:
        return self._editor

    def hasFocus(self) -> bool:
        return self._combo_focused

    def view(self) -> FakeView:
        return self._view

    def setEditText(self, text: str) -> None:
        self._current_index = -1
        self._editor.setText(text)

    def clearEditText(self) -> None:
        self._editor.setText("")


class FakeWorker:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def set_capture_selection(self, **kwargs) -> None:
        self.calls.append(dict(kwargs))


def _rect_tuple(rect: QRect | None) -> tuple[int, int, int, int] | None:
    if rect is None:
        return None
    return (int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height()))


def _patch_refresh_dependencies(
    monkeypatch,
    *,
    list_windows_result: list[tuple[int, str]],
    window_source: bool,
) -> list[int]:
    changed_rows: list[int] = []
    monkeypatch.setattr(runtime_capture, "HAS_WIN32", True)
    monkeypatch.setattr(runtime_capture, "blocked_signals", lambda _obj: nullcontext())
    monkeypatch.setattr(runtime_capture, "list_windows", lambda: list(list_windows_result))
    monkeypatch.setattr(runtime_capture, "sync_capture_source_ui", lambda _mw: None)
    monkeypatch.setattr(runtime_capture, "on_status", lambda _mw, _text: None)
    monkeypatch.setattr(runtime_capture, "_is_window_capture_source", lambda _mw: window_source)
    monkeypatch.setattr(
        runtime_capture,
        "on_window_changed",
        lambda _mw, idx: changed_rows.append(int(idx)),
    )
    return changed_rows


def test_refresh_windows_restores_previous_hwnd_without_type_error(monkeypatch) -> None:
    combo = FakeCombo([("Renderer", 11)], current_index=0)
    main_window = SimpleNamespace(combo_win=combo)
    changed_rows = _patch_refresh_dependencies(
        monkeypatch,
        list_windows_result=[(11, "Renderer"), (22, "Scope")],
        window_source=True,
    )

    runtime_capture.refresh_windows(main_window, announce=False, force=True)

    assert combo.currentIndex() == 0
    assert combo.currentData() == 11
    assert changed_rows == []


def test_refresh_windows_uses_preferred_text_when_previous_hwnd_is_missing(monkeypatch) -> None:
    combo = FakeCombo([("Old Window", 99)], current_index=0)
    main_window = SimpleNamespace(combo_win=combo)
    changed_rows = _patch_refresh_dependencies(
        monkeypatch,
        list_windows_result=[(10, "Camera Capture"), (20, "Color Scope")],
        window_source=True,
    )

    runtime_capture.refresh_windows(
        main_window,
        announce=False,
        preferred_text="camera",
        force=True,
    )

    assert combo.currentIndex() == 0
    assert combo.currentData() == 10
    assert combo.currentText() == "Camera Capture"
    assert changed_rows == [0]


def test_restore_window_capture_source_selection_matches_saved_text(monkeypatch) -> None:
    combo = FakeCombo(
        [("Primary View", 11), ("Color Scope", 22)],
        current_index=-1,
    )
    main_window = SimpleNamespace(combo_win=combo)
    monkeypatch.setattr(runtime_capture, "HAS_WIN32", True)
    monkeypatch.setattr(
        runtime_capture,
        "set_current_index_blocked",
        lambda widget, idx: widget.setCurrentIndex(idx),
    )

    selection = runtime_capture._restore_window_capture_source_selection(
        main_window,
        runtime_capture.CaptureRestoreRequest(window_text="scope"),
    )

    assert combo.currentIndex() == 1
    assert selection.hwnd == 22
    assert selection.text == "Color Scope"


def test_apply_window_capture_source_restore_sets_window_roi_and_clears_screen_roi(
    monkeypatch,
) -> None:
    worker = FakeWorker()
    main_window = SimpleNamespace(worker=worker)
    roi_rel = QRect(1, 2, 30, 40)
    monkeypatch.setattr(
        runtime_capture,
        "_restore_window_capture_source_selection",
        lambda _mw, _req: runtime_capture.WindowComboSelection(idx=0, hwnd=123, text="Target"),
    )

    runtime_capture._apply_window_capture_source_restore(
        main_window,
        runtime_capture.CaptureRestoreRequest(window_roi_rel=roi_rel),
    )

    assert len(worker.calls) == 1
    call = worker.calls[0]
    assert call["target_hwnd"] == 123
    assert _rect_tuple(call["roi_rel"]) == (1, 2, 30, 40)
    assert call["roi_abs"] is None


def test_apply_screen_capture_source_restore_applies_saved_screen_roi() -> None:
    worker = FakeWorker()
    main_window = SimpleNamespace(worker=worker)
    roi_abs = QRect(5, 6, 70, 80)

    runtime_capture._apply_screen_capture_source_restore(
        main_window,
        runtime_capture.CaptureRestoreRequest(screen_roi_abs=roi_abs),
    )

    assert len(worker.calls) == 1
    call = worker.calls[0]
    assert call["target_hwnd"] is None
    assert call["roi_rel"] is None
    assert _rect_tuple(call["roi_abs"]) == (5, 6, 70, 80)


def test_capture_preflight_message_returns_shared_window_message() -> None:
    main_window = SimpleNamespace(
        combo_capture_source=SimpleNamespace(currentData=lambda: runtime_capture.C.CAPTURE_SOURCE_WINDOW),
        worker=SimpleNamespace(
            capture_selection=lambda: SimpleNamespace(target_hwnd=None, roi_rel=None, roi_abs=None)
        ),
    )

    assert runtime_capture.capture_preflight_message(main_window) == "ターゲットウィンドウを選択してください"


def test_capture_preflight_result_returns_not_ready_for_window_without_target() -> None:
    main_window = SimpleNamespace(
        combo_capture_source=SimpleNamespace(currentData=lambda: runtime_capture.C.CAPTURE_SOURCE_WINDOW),
        worker=SimpleNamespace(
            capture_selection=lambda: SimpleNamespace(target_hwnd=None, roi_rel=None, roi_abs=None)
        ),
    )

    result = runtime_capture.capture_preflight_result(main_window)

    assert result.ready is False
    assert result.message == "ターゲットウィンドウを選択してください"


def test_capture_preflight_message_returns_shared_screen_message() -> None:
    main_window = SimpleNamespace(
        combo_capture_source=SimpleNamespace(currentData=lambda: runtime_capture.C.CAPTURE_SOURCE_SCREEN),
        worker=SimpleNamespace(
            capture_selection=lambda: SimpleNamespace(target_hwnd=None, roi_rel=None, roi_abs=None)
        ),
    )

    assert runtime_capture.capture_preflight_message(main_window) == "キャプチャ領域を選択してください"


def test_capture_preflight_result_returns_not_ready_for_screen_without_roi() -> None:
    main_window = SimpleNamespace(
        combo_capture_source=SimpleNamespace(currentData=lambda: runtime_capture.C.CAPTURE_SOURCE_SCREEN),
        worker=SimpleNamespace(
            capture_selection=lambda: SimpleNamespace(target_hwnd=None, roi_rel=None, roi_abs=None)
        ),
    )

    result = runtime_capture.capture_preflight_result(main_window)

    assert result.ready is False
    assert result.message == "キャプチャ領域を選択してください"
