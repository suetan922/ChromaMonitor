"""tools_actions の回帰テスト。"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from chroma_monitor.ui.main_window import tools_actions


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)


class _FakeWorker:
    def __init__(self, *, roi_rel=None, roi_abs=None, capture_bgr=None) -> None:
        self._capture = SimpleNamespace(roi_rel=roi_rel, roi_abs=roi_abs)
        self._capture_bgr = capture_bgr
        self.capture_once_calls = 0
        self.capture_selection_calls = 0

    def capture_selection(self):
        self.capture_selection_calls += 1
        return self._capture

    def capture_once(self):
        self.capture_once_calls += 1
        if self._capture_bgr is None:
            return None, None, "capture failed"
        return self._capture_bgr, None, None


def test_build_canvas_preview_snapshot_prefers_latest_result_over_roi_and_loaded_image() -> None:
    latest_bgr = np.full((20, 30, 3), 3, dtype=np.uint8)
    roi_bgr = np.zeros((40, 50, 3), dtype=np.uint8)
    loaded_bgr = np.full((60, 70, 3), 7, dtype=np.uint8)
    worker = _FakeWorker(roi_rel=object(), capture_bgr=roi_bgr)
    main_window = SimpleNamespace(
        worker=worker,
        _loaded_image_source_bgr=loaded_bgr,
        _loaded_image_source_path="",
        _loaded_image_source_name="loaded.png",
        _loaded_file_title_name="current.png",
        _latest_result_snapshot={"bgr_preview": latest_bgr},
    )

    snapshot = tools_actions.build_canvas_preview_snapshot(main_window)

    assert snapshot is not None
    assert snapshot.source_label == "最終計算画像"
    assert snapshot.title == "current.png"
    assert snapshot.bgr.shape == (20, 30, 3)
    assert snapshot.bgr[0, 0, 0] == 3
    assert np.shares_memory(snapshot.bgr, latest_bgr) is False
    assert worker.capture_selection_calls == 0
    assert worker.capture_once_calls == 0


def test_build_canvas_preview_snapshot_uses_loaded_image_before_roi_capture() -> None:
    frame_bgr = np.zeros((80, 90, 3), dtype=np.uint8)
    loaded_bgr = np.zeros((120, 130, 3), dtype=np.uint8)
    worker = _FakeWorker(roi_rel=object(), capture_bgr=frame_bgr)
    main_window = SimpleNamespace(
        worker=worker,
        _loaded_image_source_bgr=loaded_bgr,
        _loaded_image_source_path="",
        _loaded_image_source_name="loaded.png",
        _loaded_file_title_name="loaded.png",
        _latest_result_snapshot={},
    )

    snapshot = tools_actions.build_canvas_preview_snapshot(main_window)

    assert snapshot is not None
    assert snapshot.source_label == "読み込み画像"
    assert snapshot.bgr.shape == (120, 130, 3)
    assert worker.capture_selection_calls == 0
    assert worker.capture_once_calls == 0


def test_build_canvas_preview_snapshot_uses_roi_capture_as_fallback() -> None:
    roi_bgr = np.zeros((40, 50, 3), dtype=np.uint8)
    worker = _FakeWorker(roi_rel=object(), capture_bgr=roi_bgr)
    main_window = SimpleNamespace(
        worker=worker,
        _loaded_image_source_bgr=None,
        _loaded_image_source_path="",
        _loaded_image_source_name="",
        _loaded_file_title_name="",
        _latest_result_snapshot={},
    )

    snapshot = tools_actions.build_canvas_preview_snapshot(main_window)

    assert snapshot is not None
    assert snapshot.source_label == "選択範囲"
    assert snapshot.bgr.shape == (40, 50, 3)
    assert worker.capture_selection_calls == 1
    assert worker.capture_once_calls == 1


def test_build_canvas_preview_snapshot_uses_current_display_label_for_capture() -> None:
    frame_bgr = np.zeros((80, 90, 3), dtype=np.uint8)
    main_window = SimpleNamespace(
        worker=_FakeWorker(capture_bgr=frame_bgr),
        _loaded_image_source_bgr=None,
        _loaded_image_source_path="",
        _loaded_image_source_name="",
        _loaded_file_title_name="",
        _latest_result_snapshot={},
    )

    snapshot = tools_actions.build_canvas_preview_snapshot(main_window)

    assert snapshot is not None
    assert snapshot.source_label == "表示中の画像"
    assert snapshot.title == "表示中の画像"


def test_build_canvas_preview_snapshot_returns_none_when_no_image_available() -> None:
    main_window = SimpleNamespace(
        worker=_FakeWorker(capture_bgr=None),
        _loaded_image_source_bgr=None,
        _loaded_image_source_path="",
        _loaded_image_source_name="",
        _loaded_file_title_name="",
        _latest_result_snapshot={},
    )

    snapshot = tools_actions.build_canvas_preview_snapshot(main_window)

    assert snapshot is None


class _FakeDialog:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls
        self.destroyed = _FakeSignal()

    def close(self) -> None:
        self._calls.append("close")

    def show(self) -> None:
        self._calls.append("show")

    def showNormal(self) -> None:
        self._calls.append("showNormal")

    def raise_(self) -> None:
        self._calls.append("raise")

    def activateWindow(self) -> None:
        self._calls.append("activate")


def test_show_canvas_preview_window_warns_and_does_not_open_dialog_without_image(
    monkeypatch,
) -> None:
    warning_calls: list[tuple[object, str, str]] = []
    dialog_calls: list[str] = []
    status_calls: list[str] = []
    main_window = SimpleNamespace(_canvas_preview_window=None)

    monkeypatch.setattr(tools_actions, "build_canvas_preview_snapshot", lambda _mw: None)
    monkeypatch.setattr(
        tools_actions.QMessageBox,
        "warning",
        lambda parent, title, message: warning_calls.append((parent, title, message)),
    )
    monkeypatch.setattr(
        tools_actions,
        "CanvasPreviewDialog",
        lambda *_args, **_kwargs: dialog_calls.append("dialog"),
    )
    monkeypatch.setattr(
        tools_actions,
        "present_top_level_widget",
        lambda *_args, **_kwargs: dialog_calls.append("present"),
    )
    monkeypatch.setattr(
        tools_actions,
        "on_status",
        lambda _mw, message: status_calls.append(message),
    )

    tools_actions.show_canvas_preview_window(main_window)

    assert warning_calls == [
        (
            main_window,
            "キャンバスプレビュー",
            "プレビューできる画像がありません。\n画像を読み込むか、選択範囲を作ってから開いてください。",
        )
    ]
    assert dialog_calls == []
    assert status_calls == ["キャンバスプレビューを開けませんでした"]
    assert main_window._canvas_preview_window is None


def test_show_canvas_preview_window_fits_before_show(monkeypatch) -> None:
    calls: list[str] = []
    dialog = _FakeDialog(calls)
    snapshot = SimpleNamespace(source_label="loaded", title="loaded.png")

    class _FakeMainWindow:
        def __init__(self) -> None:
            self._canvas_preview_window = None

        def _fit_dialog_to_desktop(self, widget, center_on_parent: bool = False) -> None:
            assert widget is dialog
            calls.append(f"fit:{center_on_parent}")

    main_window = _FakeMainWindow()
    monkeypatch.setattr(tools_actions, "build_canvas_preview_snapshot", lambda _mw: snapshot)
    monkeypatch.setattr(tools_actions, "CanvasPreviewDialog", lambda _mw, _snap: dialog)
    monkeypatch.setattr(
        tools_actions,
        "present_top_level_widget",
        lambda _mw, widget, *, fit_before_show, **_kwargs: (
            fit_before_show(),
            widget.show(),
            widget.raise_(),
            widget.activateWindow(),
        ),
    )
    monkeypatch.setattr(tools_actions, "on_status", lambda *_args, **_kwargs: None)

    tools_actions.show_canvas_preview_window(main_window)

    assert main_window._canvas_preview_window is dialog
    assert calls == ["fit:True", "show", "raise", "activate"]


def test_show_canvas_preview_window_closes_existing_dialog_before_recreate(monkeypatch) -> None:
    calls: list[str] = []
    existing = _FakeDialog(calls)
    dialog = _FakeDialog(calls)
    snapshot = SimpleNamespace(source_label="loaded", title="loaded.png")

    class _FakeMainWindow:
        def __init__(self) -> None:
            self._canvas_preview_window = existing

        def _fit_dialog_to_desktop(self, widget, center_on_parent: bool = False) -> None:
            assert widget is dialog
            calls.append(f"fit:{center_on_parent}")

    main_window = _FakeMainWindow()
    monkeypatch.setattr(tools_actions, "build_canvas_preview_snapshot", lambda _mw: snapshot)
    monkeypatch.setattr(tools_actions, "CanvasPreviewDialog", lambda _mw, _snap: dialog)
    monkeypatch.setattr(
        tools_actions,
        "present_top_level_widget",
        lambda _mw, widget, *, fit_before_show, **_kwargs: (
            fit_before_show(),
            widget.show(),
            widget.raise_(),
            widget.activateWindow(),
        ),
    )
    monkeypatch.setattr(tools_actions, "on_status", lambda *_args, **_kwargs: None)

    tools_actions.show_canvas_preview_window(main_window)

    assert main_window._canvas_preview_window is dialog
    assert calls == ["close", "fit:True", "show", "raise", "activate"]
