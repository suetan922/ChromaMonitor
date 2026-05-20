"""window_layout の復元スケジュール回帰テスト。"""

from __future__ import annotations

from chroma_monitor.ui.main_window import window_layout


class _FakeDock:
    def isFloating(self) -> bool:
        return True

    def isVisible(self) -> bool:
        return True


class _FakeMainWindow:
    def __init__(self) -> None:
        self.restore_calls: list[tuple[object, bool]] = []

    def _restore_dock_from_snapshot(self, dock, *, force: bool = False) -> None:
        self.restore_calls.append((dock, bool(force)))


def test_schedule_force_restore_dock_snapshot_calls_bound_restore_without_main_window(
    monkeypatch,
) -> None:
    main_window = _FakeMainWindow()
    dock = _FakeDock()
    scheduled_delays: list[int] = []

    def _single_shot(delay: int, callback) -> None:
        scheduled_delays.append(int(delay))
        callback()

    monkeypatch.setattr(window_layout.QTimer, "singleShot", _single_shot)

    window_layout._schedule_force_restore_dock_snapshot(main_window, dock)

    assert scheduled_delays == [0, 70, 160]
    assert main_window.restore_calls == [(dock, True), (dock, True), (dock, True)]
