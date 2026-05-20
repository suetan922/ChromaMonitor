"""result_snapshot の graph 復元回帰テスト。"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from chroma_monitor.ui.main_window import result_snapshot


class _FakeThread:
    def __init__(self, *, alive: bool) -> None:
        self._alive = bool(alive)

    def is_alive(self) -> bool:
        return self._alive


class _FakeWorker:
    def __init__(self, *, alive: bool) -> None:
        self._thread = _FakeThread(alive=alive)
        self.cfg = SimpleNamespace(max_dim=64)
        self.capture_once_calls = 0

    def capture_once(self):
        self.capture_once_calls += 1
        return None, None, "unexpected"


class _FakeSpin:
    def __init__(self, value: int) -> None:
        self._value = int(value)

    def value(self) -> int:
        return self._value


class _FakeDock:
    def __init__(self) -> None:
        self._widget = object()

    def isVisible(self) -> bool:
        return True

    def widget(self):
        return self._widget


class _FakeWheel:
    def __init__(self) -> None:
        self.hist = None

    def update_hist(self, hist) -> None:
        self.hist = hist


class _FakeScatter:
    def __init__(self) -> None:
        self.sv = None
        self.rgb = None

    def update_scatter(self, sv, rgb) -> None:
        self.sv = sv
        self.rgb = rgb


class _FakeHistView:
    def __init__(self) -> None:
        self.hist = None
        self.values = None
        self.shared_max_y = None

    def update_from_hist(self, hist) -> None:
        self.hist = np.asarray(hist)

    def update_from_values(self, values) -> None:
        self.values = np.asarray(values)

    def bucketed_max(self) -> int:
        if self.hist is None:
            return 0
        return int(np.max(self.hist))

    def set_shared_max_y(self, max_y) -> None:
        self.shared_max_y = max_y


def _sample_bgr_preview() -> np.ndarray:
    return np.array(
        [
            [[0, 0, 255], [0, 255, 0], [255, 0, 0], [0, 255, 255]],
            [[0, 0, 255], [0, 255, 0], [255, 0, 0], [0, 255, 255]],
            [[255, 255, 0], [255, 0, 255], [64, 64, 64], [255, 255, 255]],
            [[255, 255, 0], [255, 0, 255], [64, 64, 64], [255, 255, 255]],
        ],
        dtype=np.uint8,
    )


def _build_main_window(*, worker_running: bool = True):
    dock_color = _FakeDock()
    dock_color_band = _FakeDock()
    dock_scatter = _FakeDock()
    dock_hist = _FakeDock()
    snapshot = result_snapshot._new_empty_result_snapshot()
    snapshot["bgr_preview"] = _sample_bgr_preview()
    main_window = SimpleNamespace(
        worker=_FakeWorker(alive=worker_running),
        spin_points=_FakeSpin(16),
        _selected_wheel_sat_threshold=lambda: 0,
        on_status=lambda _message: None,
        wheel=_FakeWheel(),
        scatter=_FakeScatter(),
        hist_h=_FakeHistView(),
        hist_s=_FakeHistView(),
        hist_v=_FakeHistView(),
        dock_color=dock_color,
        dock_color_band=dock_color_band,
        dock_scatter=dock_scatter,
        dock_hist=dock_hist,
        _latest_result_snapshot=snapshot,
        _latest_result_version=1,
        _dock_rendered_version={},
    )
    main_window._dock_map = {
        "dock_color": dock_color,
        "dock_color_band": dock_color_band,
        "dock_scatter": dock_scatter,
        "dock_hist": dock_hist,
    }
    main_window._dock_name_by_object = {dock: name for name, dock in main_window._dock_map.items()}
    return main_window


@pytest.mark.parametrize(
    ("dock_name", "snapshot_keys"),
    [
        ("dock_color", ("hist",)),
        ("dock_color_band", ("top_colors",)),
        ("dock_scatter", ("sv", "rgb")),
        ("dock_hist", ("h_hist", "s_hist", "v_hist")),
    ],
)
def test_ensure_snapshot_graph_data_uses_cached_bgr_while_worker_running(
    dock_name: str,
    snapshot_keys: tuple[str, ...],
) -> None:
    main_window = _build_main_window(worker_running=True)

    ensured = result_snapshot._ensure_snapshot_graph_data_for_dock(main_window, dock_name)

    assert ensured is True
    assert main_window.worker.capture_once_calls == 0
    for key in snapshot_keys:
        assert main_window._latest_result_snapshot[key] is not None


@pytest.mark.parametrize(
    "dock_name",
    ("dock_color", "dock_color_band", "dock_scatter", "dock_hist"),
)
def test_restore_dock_from_snapshot_immediately_renders_from_cached_bgr(
    monkeypatch: pytest.MonkeyPatch,
    dock_name: str,
) -> None:
    main_window = _build_main_window(worker_running=True)
    rendered_color_band: list[object] = []
    monkeypatch.setattr(result_snapshot, "is_widget_renderable", lambda _widget: True)
    monkeypatch.setattr(
        result_snapshot,
        "render_color_band_dock_from_snapshot",
        lambda _mw, snapshot: rendered_color_band.append(snapshot.get("top_colors")) or True,
    )

    result_snapshot.restore_dock_from_snapshot(
        main_window,
        main_window._dock_map[dock_name],
        force=True,
    )

    assert main_window.worker.capture_once_calls == 0
    if dock_name == "dock_color":
        assert main_window.wheel.hist is not None
    elif dock_name == "dock_color_band":
        assert rendered_color_band
        assert rendered_color_band[0] is not None
    elif dock_name == "dock_scatter":
        assert main_window.scatter.sv is not None
        assert main_window.scatter.rgb is not None
    else:
        assert main_window.hist_h.hist is not None
        assert main_window.hist_s.hist is not None
        assert main_window.hist_v.hist is not None
