"""runtime_image_analysis のウィンドウタイトル挙動テスト。"""

from __future__ import annotations

from types import SimpleNamespace

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


class _FakeLiveWorker:
    def __init__(self) -> None:
        self.cfg = SimpleNamespace(max_dim=1024)
        self.stop_calls = 0
        self.start_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1

    def start(self) -> None:
        self.start_calls += 1


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
    monkeypatch.setattr(runtime_image_analysis, "sync_worker_view_flags", lambda _mw: None)

    runtime_image_analysis.on_start(main_window)

    assert main_window._loaded_file_title_name == ""
    assert main_window.window_title == "ChromaMonitor"
    assert main_window.worker.start_calls == 1
    assert main_window.btn_start_bar.checked is True
    assert main_window.btn_stop_bar.checked is False
