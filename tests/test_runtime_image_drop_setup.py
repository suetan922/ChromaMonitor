"""runtime_image_analysis の drag & drop 設定テスト。"""

from __future__ import annotations

from types import SimpleNamespace

from chroma_monitor.ui.main_window import runtime_image_analysis


def test_setup_image_input_drop_targets_installs_single_dock_area_controller(monkeypatch) -> None:
    dock_a = object()
    dock_b = object()
    captured: dict[str, object] = {}
    controller = object()

    def _fake_install(main_window, **kwargs):
        captured["main_window"] = main_window
        captured.update(kwargs)
        return controller

    main_window = SimpleNamespace(
        _dock_map={"dock_a": dock_a, "dock_b": dock_b},
        is_supported_image_path=lambda _path: True,
        can_accept_image_drop_target=lambda *_args, **_kwargs: True,
        on_image_files_dropped=lambda _paths: None,
    )
    monkeypatch.setattr(
        runtime_image_analysis,
        "install_dock_area_image_drop_target",
        _fake_install,
    )

    runtime_image_analysis.setup_image_input_drop_targets(main_window)

    assert captured["main_window"] is main_window
    assert captured["dock_widgets"] == (dock_a, dock_b)
    assert main_window._image_drop_target_controller is controller
    assert main_window._image_drop_target_controllers == [controller]
