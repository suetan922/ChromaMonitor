"""配色比率詳細の純粋計算ロジックの回帰テスト。"""

from chroma_monitor.ui.main_window.result_color_band import (
    compute_color_band_compact_visibility,
    compute_color_band_detail_state,
)
from chroma_monitor.util import constants as C


def test_compute_color_band_detail_state_for_empty_selection() -> None:
    state = compute_color_band_detail_state(
        [],
        -1,
        harmony_enabled=False,
        guide_type=C.WHEEL_HARMONY_GUIDE_NONE,
        entries_signature=(),
    )

    assert state.has_selection is False
    assert state.show_info is True
    assert state.detail_text == "一覧から色を選択してください。"


def test_compute_color_band_detail_state_for_achromatic_selection() -> None:
    state = compute_color_band_detail_state(
        [{"label": "無彩色", "rgb": (120, 120, 120)}],
        0,
        harmony_enabled=True,
        guide_type=C.WHEEL_HARMONY_GUIDE_TRIAD,
        entries_signature=(("gray", 0.5),),
    )

    assert state.has_selection is True
    assert state.achromatic is True
    assert state.show_info is True
    assert state.harmony_colors == ()


def test_compute_color_band_detail_state_merges_complement_when_requested() -> None:
    state = compute_color_band_detail_state(
        [{"label": "赤", "rgb": (255, 0, 0)}],
        0,
        harmony_enabled=True,
        guide_type=C.WHEEL_HARMONY_GUIDE_COMPLEMENTARY,
        entries_signature=(("red", 0.5),),
    )

    assert state.has_selection is True
    assert state.achromatic is False
    assert state.merge_complement is True
    assert state.show_info is False
    assert len(state.harmony_colors) >= 2
    assert state.complement_colors == ()
    assert "補色" in state.harmony_text


def test_compute_color_band_compact_visibility_uses_detail_state() -> None:
    detail_state = compute_color_band_detail_state(
        [{"label": "青", "rgb": (0, 0, 255)}],
        0,
        harmony_enabled=True,
        guide_type=C.WHEEL_HARMONY_GUIDE_TRIAD,
        entries_signature=(("blue", 0.5),),
    )

    visibility = compute_color_band_compact_visibility(
        260,
        detail_state,
        harmony_enabled=True,
    )

    assert visibility.show_top_bar is True
    assert visibility.show_chip_list is True
    assert visibility.show_detail is True
    assert visibility.show_harmony is True
    assert visibility.show_complement is True
    assert visibility.show_color_models is True
