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

    def capture_selection(self):
        return self._capture

    def capture_once(self):
        if self._capture_bgr is None:
            return None, None, "capture failed"
        return self._capture_bgr, None, None


def test_build_canvas_preview_snapshot_prefers_roi_capture() -> None:
    roi_bgr = np.zeros((40, 50, 3), dtype=np.uint8)
    loaded_bgr = np.zeros((60, 70, 3), dtype=np.uint8)
    main_window = SimpleNamespace(
        worker=_FakeWorker(roi_rel=object(), capture_bgr=roi_bgr),
        _loaded_image_source_bgr=loaded_bgr,
        _loaded_image_source_path="",
        _loaded_image_source_name="loaded.png",
        _loaded_file_title_name="current.png",
        _latest_result_snapshot={},
    )

    snapshot = tools_actions.build_canvas_preview_snapshot(main_window)

    assert snapshot is not None
    assert snapshot.source_label == "選択範囲"
    assert snapshot.bgr.shape == (40, 50, 3)


def test_build_canvas_preview_snapshot_uses_loaded_image_before_current_frame() -> None:
    frame_bgr = np.zeros((80, 90, 3), dtype=np.uint8)
    loaded_bgr = np.zeros((120, 130, 3), dtype=np.uint8)
    main_window = SimpleNamespace(
        worker=_FakeWorker(capture_bgr=frame_bgr),
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
