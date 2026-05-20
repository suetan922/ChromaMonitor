"""view_docks_common の dock visibility 回帰テスト。"""

from types import SimpleNamespace

from chroma_monitor.ui import view_docks_common


class _FakeDock:
    def __init__(self) -> None:
        self._attach_on_next_show = False


def _build_main_window(dock_name: str):
    log: list[str] = []
    dock = _FakeDock()
    main_window = SimpleNamespace(
        _dock_name_by_object={dock: dock_name},
        _dock_map={dock_name: dock},
        worker=SimpleNamespace(
            request_graph_refresh_once=lambda: log.append("refresh")
        ),
        _sync_worker_view_flags=lambda: log.append("sync"),
        _restore_dock_from_snapshot=lambda _dock: log.append("restore"),
    )
    return main_window, dock, log


def test_handle_view_dock_visibility_changed_requests_graph_refresh_before_restore() -> None:
    main_window, dock, log = _build_main_window("dock_hist")

    view_docks_common._handle_view_dock_visibility_changed(main_window, dock, True)

    assert log == ["sync", "refresh", "restore"]


def test_handle_view_dock_visibility_changed_syncs_hidden_without_restore() -> None:
    main_window, dock, log = _build_main_window("dock_hist")

    view_docks_common._handle_view_dock_visibility_changed(main_window, dock, False)

    assert log == ["sync"]


def test_handle_view_dock_visibility_changed_skips_graph_refresh_for_non_graph_dock() -> None:
    main_window, dock, log = _build_main_window("dock_edge")

    view_docks_common._handle_view_dock_visibility_changed(main_window, dock, True)

    assert log == ["sync", "restore"]
