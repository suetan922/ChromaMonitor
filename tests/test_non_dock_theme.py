"""non_dock_theme の追加反映テスト。"""

from types import SimpleNamespace

from chroma_monitor.ui.main_window import non_dock_theme


class _FakeThemeable:
    def __init__(self) -> None:
        self.calls = []

    def set_theme(self, theme) -> None:
        self.calls.append(theme.name)


def test_apply_additional_theme_updates_only_non_dock_widgets(monkeypatch) -> None:
    nav_calls = []
    monkeypatch.setattr(
        "chroma_monitor.ui.settings_dialog.refresh_settings_nav_style",
        lambda _mw: nav_calls.append("nav"),
    )

    preview = _FakeThemeable()
    canvas_preview = _FakeThemeable()
    main_window = SimpleNamespace(
        _ui_theme_name="light",
        _ui_theme=None,
        preview_window=preview,
        _canvas_preview_window=canvas_preview,
    )

    non_dock_theme.apply_additional_theme(main_window, "dark")

    assert main_window._ui_theme_name == "dark"
    assert getattr(main_window._ui_theme, "name", None) == "dark"
    assert nav_calls == ["nav"]
    assert preview.calls == ["dark"]
    assert canvas_preview.calls == ["dark"]
