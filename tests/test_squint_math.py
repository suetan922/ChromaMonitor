"""squint_math の回帰テスト。"""

from __future__ import annotations

import numpy as np

from chroma_monitor.util import constants as C
from chroma_monitor.views.squint_math import fit_image_to_bounds, render_squint_frame


def test_fit_image_to_bounds_preserves_aspect_ratio() -> None:
    width, height = fit_image_to_bounds(1920, 1080, max_width=320, max_height=200)

    assert (width, height) == (320, 180)


def test_render_squint_frame_smaller_scale_percent_has_stronger_effect() -> None:
    rng = np.random.default_rng(123)
    source = rng.integers(0, 256, size=(480, 640, 3), dtype=np.uint8)

    base = render_squint_frame(
        source,
        mode=C.SQUINT_MODE_SCALE,
        scale_percent=100,
        blur_sigma=0.0,
        target_width=160,
        target_height=120,
    )
    near_original = render_squint_frame(
        source,
        mode=C.SQUINT_MODE_SCALE,
        scale_percent=80,
        blur_sigma=0.0,
        target_width=160,
        target_height=120,
    )
    strongly_squinted = render_squint_frame(
        source,
        mode=C.SQUINT_MODE_SCALE,
        scale_percent=10,
        blur_sigma=0.0,
        target_width=160,
        target_height=120,
    )

    near_original_diff = np.abs(near_original.astype(np.int16) - base.astype(np.int16)).mean()
    strongly_squinted_diff = np.abs(
        strongly_squinted.astype(np.int16) - base.astype(np.int16)
    ).mean()

    assert base.shape == (120, 160, 3)
    assert strongly_squinted_diff > near_original_diff
