"""runtime_preview の preflight 共通化回帰テスト。"""

from __future__ import annotations

from types import SimpleNamespace

from chroma_monitor.ui.main_window import runtime_preview


class _FakeCheck:
    def __init__(self, checked: bool = True) -> None:
        self._checked = bool(checked)

    def isChecked(self) -> bool:
        return bool(self._checked)


class _FakePreviewWindow:
    def __init__(self) -> None:
        self.placeholders: list[str] = []
        self.visible = False

    def isVisible(self) -> bool:
        return bool(self.visible)

    def show(self) -> None:
        self.visible = True

    def show_placeholder(self, text: str) -> None:
        self.placeholders.append(str(text))


class _FakeWorker:
    def __init__(self) -> None:
        self.capture_once_calls = 0

    def capture_once(self):
        self.capture_once_calls += 1
        return None, None, "capture failed"


def test_update_preview_snapshot_uses_shared_capture_preflight_helper(monkeypatch) -> None:
    statuses: list[str] = []
    presented: list[str] = []
    main_window = SimpleNamespace(
        chk_preview_window=_FakeCheck(True),
        preview_window=_FakePreviewWindow(),
        worker=_FakeWorker(),
    )
    monkeypatch.setattr(
        runtime_preview,
        "present_top_level_widget",
        lambda *_args, **_kwargs: presented.append("present"),
    )
    monkeypatch.setattr(
        runtime_preview,
        "capture_preflight_result",
        lambda _mw: SimpleNamespace(
            ready=False,
            message="ターゲットウィンドウを選択してください",
        ),
    )
    monkeypatch.setattr(runtime_preview, "on_status", lambda _mw, text: statuses.append(str(text)))

    runtime_preview.update_preview_snapshot(main_window)

    assert presented == ["present"]
    assert main_window.preview_window.placeholders == ["ターゲットウィンドウを選択してください"]
    assert statuses == ["ターゲットウィンドウを選択してください"]
    assert main_window.worker.capture_once_calls == 0
