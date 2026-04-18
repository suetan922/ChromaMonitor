"""runtime_image_analysis のウィンドウタイトル挙動テスト。"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from chroma_monitor.ui.main_window import runtime_image_analysis


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs) -> None:
        for callback in tuple(self._callbacks):
            callback(*args, **kwargs)


class _FakeButton:
    def __init__(self) -> None:
        self.checked = False
        self.enabled = True

    def setChecked(self, value: bool) -> None:
        self.checked = bool(value)

    def setEnabled(self, value: bool) -> None:
        self.enabled = bool(value)


class _FakeLabel:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, value: str) -> None:
        self.text = str(value)


class _FakeSpin:
    def __init__(self, value: int) -> None:
        self._value = int(value)

    def value(self) -> int:
        return self._value


class _FakeCombo:
    def __init__(self, data) -> None:
        self._data = data

    def currentData(self):
        return self._data


class _FakeLiveWorker:
    def __init__(self, *, capture=None) -> None:
        self.cfg = SimpleNamespace(max_dim=1024)
        self.stop_calls = 0
        self.start_calls = 0
        self._running = False
        self._capture = capture or SimpleNamespace(
            target_hwnd=123,
            roi_rel=None,
            roi_abs=object(),
        )

    def stop(self) -> None:
        self.stop_calls += 1
        self._running = False

    def start(self) -> None:
        self.start_calls += 1
        self._running = True

    def capture_selection(self):
        return self._capture

    def is_running(self) -> bool:
        return bool(self._running)


class _FakeImageWorker:
    def __init__(self, **kwargs) -> None:
        self.kwargs = dict(kwargs)
        self.progress = _FakeSignal()
        self.finished = _FakeSignal()
        self.failed = _FakeSignal()
        self.canceled = _FakeSignal()
        self.thread = None

    def moveToThread(self, thread) -> None:
        self.thread = thread

    def run(self) -> None:
        return None

    def request_cancel(self) -> None:
        return None


class _FakeThread:
    def __init__(self, _parent) -> None:
        self.started = _FakeSignal()
        self.quit_calls = 0
        self.running = False

    def start(self) -> None:
        self.running = True
        self.started.emit()

    def quit(self) -> None:
        self.quit_calls += 1
        self.running = False

    def wait(self, _timeout: int) -> None:
        return None

    def isRunning(self) -> bool:
        return bool(self.running)


class _FakeProgressDialog:
    def __init__(self, *_args, **_kwargs) -> None:
        self.canceled = _FakeSignal()
        self.title = ""
        self.shown = False
        self.value = 0
        self.label = ""

    def setWindowTitle(self, title: str) -> None:
        self.title = str(title)

    def setWindowModality(self, _modality) -> None:
        return None

    def setMinimumDuration(self, _duration: int) -> None:
        return None

    def setValue(self, value: int) -> None:
        self.value = int(value)

    def setLabelText(self, text: str) -> None:
        self.label = str(text)

    def show(self) -> None:
        self.shown = True

    def close(self) -> None:
        self.shown = False


class _FakeMimeData:
    def hasUrls(self) -> bool:
        return False

    def urls(self) -> list[object]:
        return []

    def hasText(self) -> bool:
        return False

    def text(self) -> str:
        return ""


class _FakeClipboardImage:
    def isNull(self) -> bool:
        return False


class _FakeClipboard:
    def __init__(self, *, image=None, mime_data=None) -> None:
        self._image = image
        self._mime_data = mime_data or _FakeMimeData()

    def image(self):
        return self._image

    def mimeData(self):
        return self._mime_data


class _FakeApplication:
    def __init__(self, clipboard) -> None:
        self._clipboard = clipboard

    def clipboard(self):
        return self._clipboard


class _FakeMainWindow:
    def __init__(self) -> None:
        self._base_window_title = "ChromaMonitor"
        self._loaded_file_title_name = ""
        self._image_thread = None
        self._image_worker = None
        self._image_progress = None
        self.worker = _FakeLiveWorker()
        self.spin_points = _FakeSpin(12)
        self.lbl_status = _FakeLabel()
        self.btn_load_image_bar = _FakeButton()
        self.btn_start_bar = _FakeButton()
        self.btn_stop_bar = _FakeButton()
        self.combo_capture_source = _FakeCombo(runtime_image_analysis.C.CAPTURE_SOURCE_WINDOW)
        self.window_title = self._base_window_title

    def _selected_wheel_sat_threshold(self) -> float:
        return 0.42

    def on_image_analysis_progress(self, *_args, **_kwargs) -> None:
        return None

    def on_image_analysis_finished(self, *_args, **_kwargs) -> None:
        return None

    def on_image_analysis_failed(self, *_args, **_kwargs) -> None:
        return None

    def on_image_analysis_canceled(self, *_args, **_kwargs) -> None:
        return None

    def _cancel_image_analysis(self) -> None:
        return None

    def setWindowTitle(self, title: str) -> None:
        self.window_title = str(title)


def test_on_load_image_sets_window_title_to_loaded_file_name(monkeypatch) -> None:
    main_window = _FakeMainWindow()
    monkeypatch.setattr(
        runtime_image_analysis.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: ("/tmp/my_picture.png", "Images"),
    )
    monkeypatch.setattr(
        runtime_image_analysis,
        "normalize_existing_image_path",
        lambda path: str(path),
    )
    monkeypatch.setattr(runtime_image_analysis, "ImageFileAnalyzeWorker", _FakeImageWorker)
    monkeypatch.setattr(runtime_image_analysis, "QThread", _FakeThread)
    monkeypatch.setattr(runtime_image_analysis, "QProgressDialog", _FakeProgressDialog)
    monkeypatch.setattr(
        runtime_image_analysis,
        "selected_effective_color_band_sat_threshold",
        lambda _mw: 0.25,
    )

    runtime_image_analysis.on_load_image(main_window)

    assert main_window._loaded_file_title_name == "my_picture.png"
    assert main_window.window_title == "ChromaMonitor - my_picture.png"
    assert main_window.worker.stop_calls == 1
    assert main_window._image_thread is not None
    assert main_window._image_worker is not None


def test_on_start_clears_loaded_file_title(monkeypatch) -> None:
    main_window = _FakeMainWindow()
    main_window._loaded_file_title_name = "sample.psd"
    main_window.window_title = "ChromaMonitor - sample.psd"
    main_window.btn_start_bar.checked = True
    main_window.btn_stop_bar.checked = False
    monkeypatch.setattr(runtime_image_analysis, "sync_worker_view_flags", lambda _mw: None)

    runtime_image_analysis.on_start(main_window)

    assert main_window._loaded_file_title_name == ""
    assert main_window.window_title == "ChromaMonitor"
    assert main_window.worker.start_calls == 1
    assert main_window.btn_start_bar.checked is True
    assert main_window.btn_stop_bar.checked is False


def test_on_start_warns_when_window_capture_target_is_missing(monkeypatch) -> None:
    warnings: list[tuple[str, str]] = []
    cleared_titles: list[bool] = []
    cleared_sources: list[bool] = []
    main_window = _FakeMainWindow()
    main_window.worker = _FakeLiveWorker(
        capture=SimpleNamespace(target_hwnd=None, roi_rel=None, roi_abs=None)
    )
    main_window._loaded_file_title_name = "sample.psd"
    main_window.window_title = "ChromaMonitor - sample.psd"
    main_window.combo_capture_source = _FakeCombo(runtime_image_analysis.C.CAPTURE_SOURCE_WINDOW)
    main_window.btn_start_bar.checked = True
    main_window.btn_stop_bar.checked = False
    monkeypatch.setattr(runtime_image_analysis, "sync_worker_view_flags", lambda _mw: None)
    monkeypatch.setattr(
        runtime_image_analysis,
        "clear_loaded_file_title",
        lambda _mw: cleared_titles.append(True),
    )
    monkeypatch.setattr(
        runtime_image_analysis,
        "_clear_loaded_image_source",
        lambda _mw: cleared_sources.append(True),
    )
    monkeypatch.setattr(
        runtime_image_analysis.QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((str(title), str(message))),
    )

    runtime_image_analysis.on_start(main_window)

    assert warnings == [("画像解析", "ターゲットウィンドウを選択してください")]
    assert main_window.worker.start_calls == 0
    assert cleared_titles == []
    assert cleared_sources == []
    assert main_window._loaded_file_title_name == "sample.psd"
    assert main_window.window_title == "ChromaMonitor - sample.psd"
    assert main_window.btn_start_bar.checked is False
    assert main_window.btn_stop_bar.checked is False


def test_on_start_warns_when_screen_capture_roi_is_missing(monkeypatch) -> None:
    warnings: list[tuple[str, str]] = []
    cleared_titles: list[bool] = []
    cleared_sources: list[bool] = []
    main_window = _FakeMainWindow()
    main_window.worker = _FakeLiveWorker(
        capture=SimpleNamespace(target_hwnd=None, roi_rel=None, roi_abs=None)
    )
    main_window._loaded_file_title_name = "sample.psd"
    main_window.window_title = "ChromaMonitor - sample.psd"
    main_window.combo_capture_source = _FakeCombo(runtime_image_analysis.C.CAPTURE_SOURCE_SCREEN)
    main_window.btn_start_bar.checked = True
    main_window.btn_stop_bar.checked = False
    monkeypatch.setattr(runtime_image_analysis, "sync_worker_view_flags", lambda _mw: None)
    monkeypatch.setattr(
        runtime_image_analysis,
        "clear_loaded_file_title",
        lambda _mw: cleared_titles.append(True),
    )
    monkeypatch.setattr(
        runtime_image_analysis,
        "_clear_loaded_image_source",
        lambda _mw: cleared_sources.append(True),
    )
    monkeypatch.setattr(
        runtime_image_analysis.QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((str(title), str(message))),
    )

    runtime_image_analysis.on_start(main_window)

    assert warnings == [("画像解析", "キャプチャ領域を選択してください")]
    assert main_window.worker.start_calls == 0
    assert cleared_titles == []
    assert cleared_sources == []
    assert main_window._loaded_file_title_name == "sample.psd"
    assert main_window.window_title == "ChromaMonitor - sample.psd"
    assert main_window.btn_start_bar.checked is False
    assert main_window.btn_stop_bar.checked is False


def test_on_start_during_image_analysis_restores_run_toggle_state(monkeypatch) -> None:
    cleared_titles: list[bool] = []
    cleared_sources: list[bool] = []
    main_window = _FakeMainWindow()
    main_window._loaded_file_title_name = "sample.psd"
    main_window.window_title = "ChromaMonitor - sample.psd"
    main_window.btn_start_bar.checked = True
    main_window.btn_stop_bar.checked = False
    main_window._image_thread = SimpleNamespace(isRunning=lambda: True)
    monkeypatch.setattr(runtime_image_analysis, "sync_worker_view_flags", lambda _mw: None)
    monkeypatch.setattr(
        runtime_image_analysis,
        "clear_loaded_file_title",
        lambda _mw: cleared_titles.append(True),
    )
    monkeypatch.setattr(
        runtime_image_analysis,
        "_clear_loaded_image_source",
        lambda _mw: cleared_sources.append(True),
    )

    runtime_image_analysis.on_start(main_window)

    assert main_window.worker.start_calls == 0
    assert cleared_titles == []
    assert cleared_sources == []
    assert main_window._loaded_file_title_name == "sample.psd"
    assert main_window.window_title == "ChromaMonitor - sample.psd"
    assert main_window.btn_start_bar.checked is False
    assert main_window.btn_stop_bar.checked is False


def test_on_load_image_from_clipboard_sets_clipboard_title(monkeypatch) -> None:
    main_window = _FakeMainWindow()
    fake_clipboard = _FakeClipboard(image=_FakeClipboardImage())
    monkeypatch.setattr(
        runtime_image_analysis.QApplication,
        "instance",
        lambda: _FakeApplication(fake_clipboard),
    )
    monkeypatch.setattr(
        runtime_image_analysis,
        "qimage_to_bgr",
        lambda _img: np.zeros((1, 1, 3), dtype=np.uint8),
    )
    monkeypatch.setattr(runtime_image_analysis, "ImageFileAnalyzeWorker", _FakeImageWorker)
    monkeypatch.setattr(runtime_image_analysis, "QThread", _FakeThread)
    monkeypatch.setattr(runtime_image_analysis, "QProgressDialog", _FakeProgressDialog)
    monkeypatch.setattr(
        runtime_image_analysis,
        "selected_effective_color_band_sat_threshold",
        lambda _mw: 0.25,
    )

    runtime_image_analysis.on_load_image_from_clipboard(main_window)

    assert main_window._loaded_file_title_name == "Clipboard Image"
    assert main_window.window_title == "ChromaMonitor - Clipboard Image"
    assert main_window.worker.stop_calls == 1
    assert main_window._image_thread is not None
    assert main_window._image_worker is not None
    assert main_window._image_worker.kwargs["path"] is None
    assert main_window._image_worker.kwargs["source_bgr"].shape == (1, 1, 3)
