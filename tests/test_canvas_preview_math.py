"""canvas_preview_math の回帰テスト。"""

from __future__ import annotations

from chroma_monitor.views.canvas_preview_constants import (
    CANVAS_FIT_CONTAIN,
    CANVAS_ORIENTATION_LANDSCAPE,
    CANVAS_ORIENTATION_PORTRAIT,
    DEFAULT_CANVAS_RATIO_PRESET_ID,
    CanvasRatioPreset,
    canvas_ratio_presets_from_payload,
    default_canvas_ratio_presets,
    find_canvas_ratio_preset,
)
from chroma_monitor.views.canvas_preview_math import (
    CanvasPreviewTransform,
    canvas_pixels_from_image_long_edge,
    dominant_drag_axis,
    fixed_ratio_text_for_preset,
    fit_scale_for_mode,
    oriented_ratio,
    preview_extents,
    ratio_text_for_preset,
    snap_transform_to_canvas_guides,
)


def test_canvas_pixels_from_image_long_edge_uses_long_edge_base() -> None:
    assert canvas_pixels_from_image_long_edge(4980, 3780, 4, 3) == (4980, 3735)
    assert canvas_pixels_from_image_long_edge(4980, 3780, 3, 4) == (3735, 4980)
    assert canvas_pixels_from_image_long_edge(4980, 3780, 1, 1) == (4980, 4980)


def test_oriented_ratio_swaps_only_when_needed() -> None:
    preset = CanvasRatioPreset("4:5", 4, 5)

    assert oriented_ratio(preset, CANVAS_ORIENTATION_LANDSCAPE) == (5, 4)
    assert oriented_ratio(preset, CANVAS_ORIENTATION_PORTRAIT) == (4, 5)


def test_fit_scale_for_mode_accounts_for_rotation() -> None:
    scale = fit_scale_for_mode(
        CANVAS_FIT_CONTAIN,
        image_width=400,
        image_height=200,
        canvas_width=200,
        canvas_height=200,
        rotation_deg=90.0,
    )

    assert scale == 0.5


def test_preview_extents_reports_margin_and_crop_by_side() -> None:
    extents = preview_extents(
        image_width=100,
        image_height=100,
        canvas_width=150,
        canvas_height=100,
        transform=CanvasPreviewTransform(offset_x=40.0, offset_y=0.0, scale=1.0, rotation_deg=0.0),
    )

    assert extents.margin_left == 65.0
    assert extents.crop_right == 15.0
    assert extents.crop_left == 0.0
    assert extents.margin_top == 0.0


def test_preview_extents_clamps_subpixel_crop_to_zero() -> None:
    extents = preview_extents(
        image_width=100,
        image_height=100,
        canvas_width=200,
        canvas_height=200,
        transform=CanvasPreviewTransform(offset_x=-50.1, offset_y=0.0, scale=1.0, rotation_deg=0.0),
    )

    assert extents.crop_left == 0.0


def test_ratio_text_for_special_builtin_preset_uses_symbolic_label() -> None:
    preset = find_canvas_ratio_preset("standard_silver_ratio", default_canvas_ratio_presets())

    assert ratio_text_for_preset(preset, CANVAS_ORIENTATION_PORTRAIT) == "1:√2"
    assert ratio_text_for_preset(preset, CANVAS_ORIENTATION_LANDSCAPE) == "√2:1"


def test_fixed_ratio_text_for_preset_uses_stored_order() -> None:
    preset = CanvasRatioPreset("縦長", 4, 5)

    assert fixed_ratio_text_for_preset(preset) == "4:5"


def test_canvas_ratio_presets_from_payload_keeps_saved_order_and_appends_missing_builtins() -> None:
    presets = canvas_ratio_presets_from_payload(
        [
            {"id": "standard_16_9", "name": "動画"},
            {"id": "user_custom_a", "name": "カスタムA", "ratio_w": 2.39, "ratio_h": 1.0},
            {"id": DEFAULT_CANVAS_RATIO_PRESET_ID, "name": "定番4:3"},
        ]
    )

    assert [preset.preset_id for preset in presets[:3]] == [
        "standard_16_9",
        "user_custom_a",
        DEFAULT_CANVAS_RATIO_PRESET_ID,
    ]
    assert presets[0].is_builtin is True
    assert presets[0].name == "動画"
    assert presets[1].is_builtin is False
    assert presets[1].ratio_w == 2.39
    assert presets[1].ratio_h == 1.0
    assert any(preset.preset_id == "standard_silver_ratio" for preset in presets)


def test_dominant_drag_axis_prefers_larger_movement() -> None:
    assert dominant_drag_axis(40.0, 10.0) == "x"
    assert dominant_drag_axis(10.0, 40.0) == "y"
    assert dominant_drag_axis(0.0, 0.0) is None


def test_snap_transform_to_canvas_guides_aligns_edge_and_center() -> None:
    left_snap = snap_transform_to_canvas_guides(
        image_width=100,
        image_height=100,
        canvas_width=200,
        canvas_height=200,
        transform=CanvasPreviewTransform(offset_x=-45.0, offset_y=0.0, scale=1.0, rotation_deg=0.0),
        snap_distance=6.0,
    )
    assert left_snap.transform.offset_x == -50.0
    assert left_snap.guide_x == -100.0
    assert left_snap.snapped_x is True

    center_snap = snap_transform_to_canvas_guides(
        image_width=100,
        image_height=100,
        canvas_width=200,
        canvas_height=200,
        transform=CanvasPreviewTransform(offset_x=0.0, offset_y=4.5, scale=1.0, rotation_deg=0.0),
        snap_distance=6.0,
    )
    assert center_snap.transform.offset_y == 0.0
    assert center_snap.guide_y == 0.0
    assert center_snap.snapped_y is True
