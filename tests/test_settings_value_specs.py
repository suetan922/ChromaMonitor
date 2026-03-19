"""settings spec ベースの正規化処理の回帰テスト。"""

from types import SimpleNamespace

from chroma_monitor.ui.main_window.settings_value_specs import (
    COLOR_BAND_USE_WHEEL_HARMONY_SPEC,
    DIFF_THRESHOLD_SPEC,
    SAMPLE_POINTS_SPEC,
    UI_THEME_SPEC,
    collect_settings_from_specs,
    selected_setting_value,
)
from chroma_monitor.util import constants as C


class _FakeCombo:
    def __init__(self, value):
        self._value = value

    def currentData(self):
        return self._value


class _FakeSpin:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class _FakeCheck:
    def __init__(self, checked: bool):
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


def test_selected_setting_value_normalizes_widget_values_from_specs() -> None:
    main_window = SimpleNamespace(
        combo_ui_theme=_FakeCombo("invalid"),
        spin_points=_FakeSpin(C.ANALYZER_MAX_SAMPLE_POINTS + 999),
        spin_diff=_FakeSpin(-5.0),
    )

    assert selected_setting_value(main_window, UI_THEME_SPEC) == C.DEFAULT_UI_THEME
    assert selected_setting_value(main_window, SAMPLE_POINTS_SPEC) == C.ANALYZER_MAX_SAMPLE_POINTS
    assert selected_setting_value(main_window, DIFF_THRESHOLD_SPEC) == C.ANALYZER_MIN_DIFF_THRESHOLD


def test_collect_settings_from_specs_builds_payload_by_cfg_key() -> None:
    main_window = SimpleNamespace(
        combo_ui_theme=_FakeCombo(C.UI_THEME_DARK),
        spin_points=_FakeSpin(12345),
        chk_color_band_use_wheel_harmony=_FakeCheck(False),
    )

    payload = collect_settings_from_specs(
        main_window,
        (
            UI_THEME_SPEC,
            SAMPLE_POINTS_SPEC,
            COLOR_BAND_USE_WHEEL_HARMONY_SPEC,
        ),
    )

    assert payload == {
        C.CFG_UI_THEME: C.UI_THEME_DARK,
        C.CFG_SAMPLE_POINTS: 12345,
        C.CFG_COLOR_BAND_USE_WHEEL_HARMONY: False,
    }
