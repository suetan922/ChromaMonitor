"""AnalyzerWorker の snapshot/state 管理の回帰テスト。"""

from dataclasses import FrozenInstanceError

import pytest
from PySide6.QtCore import QRect

from chroma_monitor.analyzer import AnalyzerWorker
from chroma_monitor.util import constants as C


def test_capture_selection_returns_copied_qrect_instances() -> None:
    worker = AnalyzerWorker()
    worker.set_capture_selection(target_hwnd=123, roi_rel=QRect(1, 2, 30, 40))

    snapshot = worker.capture_selection()
    assert snapshot.target_hwnd == 123
    assert snapshot.roi_rel is not None
    snapshot.roi_rel.setX(99)

    current = worker.capture_selection()
    assert current.roi_rel is not None
    assert current.roi_rel.x() == 1


def test_cfg_property_returns_frozen_replaced_snapshot() -> None:
    worker = AnalyzerWorker()
    before = worker.cfg

    with pytest.raises(FrozenInstanceError):
        before.interval_sec = 0.5  # type: ignore[misc]

    worker.set_interval(0.5)
    worker.set_sample_points(C.ANALYZER_MIN_SAMPLE_POINTS)
    after = worker.cfg

    assert before is not after
    assert before.interval_sec == C.DEFAULT_INTERVAL_SEC
    assert after.interval_sec == 0.5
    assert after.sample_points == C.ANALYZER_MIN_SAMPLE_POINTS
