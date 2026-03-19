"""画像正規化ロジックの退化を防ぐテスト。"""

import numpy as np

from chroma_monitor.analysis.frame_analysis import (
    compute_top_bars_chromatic_medoid_from_hs,
    sample_sv_and_rgb,
)
from chroma_monitor.util import constants as C
from chroma_monitor.util.image_math import normalize_map
from chroma_monitor.views.color_scatter_math import (
    ScatterRenderConfig,
    build_scatter_image,
    build_square_fallback_scatter_image,
    guide_points,
    normalize_rotation_deg,
    point_angle_deg,
    scatter_render_mode_needs_rgb,
)


def test_normalize_map_empty_returns_placeholder() -> None:
    # 空入力でshape/dtypeを維持したダミー配列を返すことを確認する。
    out = normalize_map(np.array([], dtype=np.float32))
    assert out.shape == (1, 1)
    assert out.dtype == np.float32
    assert float(out[0, 0]) == 0.0


def test_normalize_map_constant_returns_zeros() -> None:
    # 定数画像ではゼロ配列になることを確認する。
    src = np.full((4, 5), 7.0, dtype=np.float32)
    out = normalize_map(src)
    assert out.shape == src.shape
    assert out.dtype == np.float32
    assert np.all(out == 0.0)


def test_normalize_map_scales_into_zero_to_one() -> None:
    # 通常入力で 0..1 に正規化されることを確認する。
    src = np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32)
    out = normalize_map(src)
    assert out.shape == src.shape
    assert out.dtype == np.float32
    assert float(out.min()) == 0.0
    assert float(out.max()) == 1.0


def test_normalize_rotation_deg_wraps_into_signed_range() -> None:
    # 色相環ガイド回転は常に -180..180 に正規化される。
    assert normalize_rotation_deg(181.0) == -179.0
    assert normalize_rotation_deg(-181.0) == 179.0


def test_point_angle_deg_uses_screen_coordinates() -> None:
    # 画面座標系でも右=0, 上=90 になることを確認する。
    assert point_angle_deg(2, 1, 1, 1) == 0.0
    assert point_angle_deg(1, 0, 1, 1) == 90.0


def test_guide_points_match_guide_type_count() -> None:
    # ガイド種別の頂点数が offsets 定義と一致することを確認する。
    points = guide_points(
        100,
        100,
        40,
        guide_type=C.WHEEL_HARMONY_GUIDE_TRIAD,
        guide_rotation_deg=0.0,
        guide_offsets_deg=C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG,
        radius_ratio=0.82,
        red_reference_deg=C.HUE_RED_REFERENCE_DEG,
        direction_sign=C.HUE_DIRECTION_SIGN,
    )
    assert len(points) == len(C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG[C.WHEEL_HARMONY_GUIDE_TRIAD])


def test_scatter_render_mode_needs_rgb_matches_heatmap_rule() -> None:
    # heatmap 以外は代表色描画のため RGB を要求する。
    assert scatter_render_mode_needs_rgb(C.SCATTER_RENDER_MODE_HEATMAP) is False
    assert scatter_render_mode_needs_rgb(C.SCATTER_RENDER_MODE_DOMINANT) is True


def test_build_scatter_image_and_fallback_return_rgba() -> None:
    # 純粋 helper だけで散布図画像を構築できることを確認する。
    sv = np.array([[0, 255, 255], [30, 200, 180], [60, 128, 160]], dtype=np.uint8)
    rgb = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255]], dtype=np.uint8)
    config = ScatterRenderConfig(
        triangle_mode=False,
        render_mode=C.SCATTER_RENDER_MODE_DOMINANT,
        need_rgb_for_render=True,
        hue_filter_enabled=False,
        hue_center=0,
        hue_half_width=10,
    )

    out = build_scatter_image(sv, rgb, config=config)
    fallback = build_square_fallback_scatter_image(sv, rgb)

    assert out is not None
    assert fallback is not None
    assert out.shape == (256, 256, 4)
    assert fallback.shape == (256, 256, 4)


def test_sample_sv_and_rgb_respects_requested_count() -> None:
    # 散布図サンプル抽出は要求件数を上限に RGB と対で返す。
    h = np.array([[0, 10], [20, 30]], dtype=np.uint8)
    s = np.array([[100, 110], [120, 130]], dtype=np.uint8)
    v = np.array([[200, 210], [220, 230]], dtype=np.uint8)
    bgr = np.array(
        [[[0, 0, 255], [0, 255, 0]], [[255, 0, 0], [32, 64, 96]]],
        dtype=np.uint8,
    )

    sv, rgb = sample_sv_and_rgb(h, s, v, bgr, sample_points=2)

    assert sv.shape == (2, 3)
    assert rgb.shape == (2, 3)
    assert sv.dtype == np.uint8
    assert rgb.dtype == np.uint8


def test_compute_top_bars_chromatic_medoid_from_hs_returns_dominant_hue_label() -> None:
    # 準備済み H/S を使う経路でも代表色とラベルが返ることを確認する。
    bgr = np.array(
        [
            [[0, 0, 255], [0, 0, 255]],
            [[0, 255, 0], [0, 0, 255]],
        ],
        dtype=np.uint8,
    )
    h = np.array([[0, 0], [60, 0]], dtype=np.uint8)
    s = np.full((2, 2), 255, dtype=np.uint8)

    bars = compute_top_bars_chromatic_medoid_from_hs(
        bgr,
        h,
        s,
        sat_threshold=1,
        top_count=2,
    )

    assert len(bars) >= 1
    assert bars[0][0] == "赤"
    assert bars[0][1] > 0.5
