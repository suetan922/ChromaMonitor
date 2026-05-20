"""キャンバスプレビューの純粋計算。"""

from __future__ import annotations

import math
import traceback
from dataclasses import dataclass
from fractions import Fraction

from ..util.debug_log import write_window_layout_debug_log
from .canvas_preview_constants import (
    CANVAS_FIT_COVER,
    CANVAS_ORIENTATION_LANDSCAPE,
    CANVAS_ORIENTATION_PORTRAIT,
    CanvasRatioPreset,
)

_SPECIAL_RATIO_TEXTS = {
    "standard_golden_ratio": {
        CANVAS_ORIENTATION_LANDSCAPE: "φ:1",
        CANVAS_ORIENTATION_PORTRAIT: "1:φ",
    },
    "standard_silver_ratio": {
        CANVAS_ORIENTATION_LANDSCAPE: "√2:1",
        CANVAS_ORIENTATION_PORTRAIT: "1:√2",
    },
}
_COVER_SCALE_EPSILON = 1.001
_GEOMETRY_EPSILON = 0.5
_SNAP_OFFSET_ROUND_DECIMALS = 6


@dataclass(frozen=True, slots=True)
class CanvasPreviewTransform:
    """シミュレーション上の画像変形状態。"""

    offset_x: float = 0.0
    offset_y: float = 0.0
    scale: float = 1.0
    rotation_deg: float = 0.0


@dataclass(frozen=True, slots=True)
class CanvasPreviewExtents:
    """変形後画像の外接矩形と余白/切れ量。"""

    bounds_left: float
    bounds_top: float
    bounds_right: float
    bounds_bottom: float
    margin_left: float
    margin_top: float
    margin_right: float
    margin_bottom: float
    crop_left: float
    crop_top: float
    crop_right: float
    crop_bottom: float


@dataclass(frozen=True, slots=True)
class CanvasPreviewSnapResult:
    """スナップ適用後の transform とガイド情報。"""

    transform: CanvasPreviewTransform
    guide_x: float | None = None
    guide_y: float | None = None
    snapped_x: bool = False
    snapped_y: bool = False


def _root_exception(exc: BaseException) -> BaseException:
    """`__cause__` を辿って元例外を返す。"""
    current = exc
    while True:
        next_exc = current.__cause__
        if next_exc is None or next_exc is current:
            return current
        current = next_exc


def _transform_fields(transform: CanvasPreviewTransform) -> dict[str, float | str]:
    """ログ用に transform を展開する。"""
    return {
        "transform": repr(transform),
        "offset_x": float(transform.offset_x),
        "offset_y": float(transform.offset_y),
        "scale": float(transform.scale),
        "rotation_deg": float(transform.rotation_deg),
    }


def _log_math_exception(event: str, exc: BaseException, **fields) -> None:
    """math 層の例外を traceback 付きで記録する。"""
    root = _root_exception(exc)
    write_window_layout_debug_log(
        event,
        wrapped_type=type(exc).__name__,
        wrapped_message=str(exc),
        root_type=type(root).__name__,
        root_message=str(root),
        traceback_text="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        **fields,
    )


def oriented_ratio(
    preset: CanvasRatioPreset,
    orientation: str,
) -> tuple[float, float]:
    """向きを反映した比率を返す。"""
    width = max(0.0, float(preset.ratio_w))
    height = max(0.0, float(preset.ratio_h))
    if width <= 0.0 or height <= 0.0:
        return 1.0, 1.0
    if math.isclose(width, height, rel_tol=1e-9, abs_tol=1e-9):
        return width, height
    if orientation == CANVAS_ORIENTATION_PORTRAIT:
        return min(width, height), max(width, height)
    return max(width, height), min(width, height)


def orientation_label_for_ratio(ratio_w: float, ratio_h: float) -> str:
    """比率から現在の向きラベルを返す。"""
    if math.isclose(float(ratio_w), float(ratio_h), rel_tol=1e-9, abs_tol=1e-9):
        return "正方形"
    if float(ratio_w) > float(ratio_h):
        return "横"
    return "縦"


def canvas_pixels_from_image_long_edge(
    image_width: int,
    image_height: int,
    ratio_w: float,
    ratio_h: float,
) -> tuple[int, int]:
    """画像長辺を基準にキャンバス px 値を算出する。"""
    write_window_layout_debug_log(
        "canvas_preview_math_canvas_pixels_from_image_long_edge_begin",
        image_width=int(image_width),
        image_height=int(image_height),
        ratio_w=float(ratio_w),
        ratio_h=float(ratio_h),
    )
    try:
        image_width = max(1, int(image_width))
        image_height = max(1, int(image_height))
        ratio_w = max(0.0001, float(ratio_w))
        ratio_h = max(0.0001, float(ratio_h))
        long_edge = max(image_width, image_height)
        unit = float(long_edge) / float(max(ratio_w, ratio_h))
        canvas_width = max(1, int(round(float(ratio_w) * unit)))
        canvas_height = max(1, int(round(float(ratio_h) * unit)))
        write_window_layout_debug_log(
            "canvas_preview_math_canvas_pixels_from_image_long_edge_ok",
            image_width=int(image_width),
            image_height=int(image_height),
            ratio_w=float(ratio_w),
            ratio_h=float(ratio_h),
            canvas_width=int(canvas_width),
            canvas_height=int(canvas_height),
        )
        return canvas_width, canvas_height
    except Exception as exc:
        _log_math_exception(
            "canvas_preview_math_canvas_pixels_from_image_long_edge_fail",
            exc,
            image_width=int(image_width),
            image_height=int(image_height),
            ratio_w=float(ratio_w),
            ratio_h=float(ratio_h),
        )
        raise


def _trim_ratio_number(value: float) -> str:
    """比率表示用に小数を短く整形する。"""
    rounded = round(float(value), 4)
    if math.isclose(rounded, round(rounded), rel_tol=1e-9, abs_tol=1e-9):
        return str(int(round(rounded)))
    text = f"{rounded:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _sanitize_edge_delta(value: float) -> float:
    """境界ぴったり付近の微小誤差を 0 とみなす。"""
    value = float(value)
    if abs(value) <= _GEOMETRY_EPSILON:
        return 0.0
    return value


def _rounded_offset(value: float) -> float:
    """スナップ後の offset を安定した小数へ丸める。"""
    value = round(float(value), _SNAP_OFFSET_ROUND_DECIMALS)
    if abs(value) <= 10 ** (-_SNAP_OFFSET_ROUND_DECIMALS):
        return 0.0
    return value


def ratio_text_for_values(ratio_w: float, ratio_h: float) -> str:
    """比率値から人向け表示文字列を返す。"""
    ratio_w = max(0.0001, float(ratio_w))
    ratio_h = max(0.0001, float(ratio_h))
    quotient = ratio_w / ratio_h
    fraction = Fraction(quotient).limit_denominator(100)
    if math.isclose(
        quotient,
        float(fraction.numerator) / float(fraction.denominator),
        rel_tol=1e-4,
        abs_tol=1e-4,
    ):
        return f"{fraction.numerator}:{fraction.denominator}"
    base = min(ratio_w, ratio_h)
    return f"{_trim_ratio_number(ratio_w / base)}:{_trim_ratio_number(ratio_h / base)}"


def fixed_ratio_text_for_preset(preset: CanvasRatioPreset) -> str:
    """プリセットの基準比率を固定表示用に返す。"""
    special = _SPECIAL_RATIO_TEXTS.get(str(preset.preset_id or "").strip())
    if special is not None:
        return special[CANVAS_ORIENTATION_LANDSCAPE]
    return ratio_text_for_values(preset.ratio_w, preset.ratio_h)


def ratio_text_for_preset(preset: CanvasRatioPreset, orientation: str) -> str:
    """プリセットと向きから現在比率の表示文字列を返す。"""
    special = _SPECIAL_RATIO_TEXTS.get(str(preset.preset_id or "").strip())
    if special is not None:
        return special.get(orientation, special[CANVAS_ORIENTATION_LANDSCAPE])
    ratio_w, ratio_h = oriented_ratio(preset, orientation)
    return ratio_text_for_values(ratio_w, ratio_h)


def rotated_bounds_size(
    image_width: int,
    image_height: int,
    rotation_deg: float,
) -> tuple[float, float]:
    """回転後画像の外接矩形サイズを返す。"""
    image_width = max(1.0, float(image_width))
    image_height = max(1.0, float(image_height))
    radians = math.radians(float(rotation_deg))
    cos_v = abs(math.cos(radians))
    sin_v = abs(math.sin(radians))
    return (
        image_width * cos_v + image_height * sin_v,
        image_width * sin_v + image_height * cos_v,
    )


def fit_scale_for_mode(
    fit_mode: str,
    *,
    image_width: int,
    image_height: int,
    canvas_width: int,
    canvas_height: int,
    rotation_deg: float = 0.0,
) -> float:
    """フィット方式ごとの基準 scale を返す。"""
    write_window_layout_debug_log(
        "canvas_preview_math_fit_scale_for_mode_begin",
        fit_mode=str(fit_mode),
        image_width=int(image_width),
        image_height=int(image_height),
        canvas_width=int(canvas_width),
        canvas_height=int(canvas_height),
        rotation_deg=float(rotation_deg),
    )
    try:
        image_width = max(1, int(image_width))
        image_height = max(1, int(image_height))
        canvas_width = max(1, int(canvas_width))
        canvas_height = max(1, int(canvas_height))
        radians = math.radians(float(rotation_deg))
        cos_v = abs(math.cos(radians))
        sin_v = abs(math.sin(radians))
        if fit_mode == CANVAS_FIT_COVER:
            required_width = float(canvas_width) * cos_v + float(canvas_height) * sin_v
            required_height = float(canvas_width) * sin_v + float(canvas_height) * cos_v
            scale = max(
                required_width / float(image_width),
                required_height / float(image_height),
            ) * _COVER_SCALE_EPSILON
        else:
            bounds_width, bounds_height = rotated_bounds_size(
                image_width,
                image_height,
                rotation_deg,
            )
            if bounds_width <= 0.0 or bounds_height <= 0.0:
                scale = 1.0
            else:
                scale_x = float(canvas_width) / float(bounds_width)
                scale_y = float(canvas_height) / float(bounds_height)
                scale = min(scale_x, scale_y)
        write_window_layout_debug_log(
            "canvas_preview_math_fit_scale_for_mode_ok",
            fit_mode=str(fit_mode),
            image_width=int(image_width),
            image_height=int(image_height),
            canvas_width=int(canvas_width),
            canvas_height=int(canvas_height),
            rotation_deg=float(rotation_deg),
            result_scale=float(scale),
        )
        return float(scale)
    except Exception as exc:
        _log_math_exception(
            "canvas_preview_math_fit_scale_for_mode_fail",
            exc,
            fit_mode=str(fit_mode),
            image_width=int(image_width),
            image_height=int(image_height),
            canvas_width=int(canvas_width),
            canvas_height=int(canvas_height),
            rotation_deg=float(rotation_deg),
        )
        raise


def image_polygon_points(
    image_width: int,
    image_height: int,
    transform: CanvasPreviewTransform,
) -> tuple[tuple[float, float], ...]:
    """中心基準 transform を適用した画像4隅座標を返す。"""
    half_width = max(1.0, float(image_width)) * float(transform.scale) * 0.5
    half_height = max(1.0, float(image_height)) * float(transform.scale) * 0.5
    radians = math.radians(float(transform.rotation_deg))
    cos_v = math.cos(radians)
    sin_v = math.sin(radians)
    corners = (
        (-half_width, -half_height),
        (half_width, -half_height),
        (half_width, half_height),
        (-half_width, half_height),
    )
    points: list[tuple[float, float]] = []
    for x_pos, y_pos in corners:
        rot_x = x_pos * cos_v - y_pos * sin_v + float(transform.offset_x)
        rot_y = x_pos * sin_v + y_pos * cos_v + float(transform.offset_y)
        points.append((rot_x, rot_y))
    return tuple(points)


def preview_extents(
    image_width: int,
    image_height: int,
    canvas_width: int,
    canvas_height: int,
    transform: CanvasPreviewTransform,
) -> CanvasPreviewExtents:
    """現在 transform に対する外接矩形と余白/切れ量を返す。"""
    write_window_layout_debug_log(
        "canvas_preview_math_preview_extents_begin",
        image_width=int(image_width),
        image_height=int(image_height),
        canvas_width=int(canvas_width),
        canvas_height=int(canvas_height),
        **_transform_fields(transform),
    )
    try:
        points = image_polygon_points(image_width, image_height, transform)
        min_x = min(point[0] for point in points)
        max_x = max(point[0] for point in points)
        min_y = min(point[1] for point in points)
        max_y = max(point[1] for point in points)

        canvas_left = -float(canvas_width) * 0.5
        canvas_right = float(canvas_width) * 0.5
        canvas_top = -float(canvas_height) * 0.5
        canvas_bottom = float(canvas_height) * 0.5

        margin_left = max(0.0, _sanitize_edge_delta(min_x - canvas_left))
        margin_top = max(0.0, _sanitize_edge_delta(min_y - canvas_top))
        margin_right = max(0.0, _sanitize_edge_delta(canvas_right - max_x))
        margin_bottom = max(0.0, _sanitize_edge_delta(canvas_bottom - max_y))
        crop_left = max(0.0, _sanitize_edge_delta(canvas_left - min_x))
        crop_top = max(0.0, _sanitize_edge_delta(canvas_top - min_y))
        crop_right = max(0.0, _sanitize_edge_delta(max_x - canvas_right))
        crop_bottom = max(0.0, _sanitize_edge_delta(max_y - canvas_bottom))

        extents = CanvasPreviewExtents(
            bounds_left=min_x,
            bounds_top=min_y,
            bounds_right=max_x,
            bounds_bottom=max_y,
            margin_left=margin_left,
            margin_top=margin_top,
            margin_right=margin_right,
            margin_bottom=margin_bottom,
            crop_left=crop_left,
            crop_top=crop_top,
            crop_right=crop_right,
            crop_bottom=crop_bottom,
        )
        write_window_layout_debug_log(
            "canvas_preview_math_preview_extents_ok",
            image_width=int(image_width),
            image_height=int(image_height),
            canvas_width=int(canvas_width),
            canvas_height=int(canvas_height),
            **_transform_fields(transform),
            extents=repr(extents),
        )
        return extents
    except Exception as exc:
        _log_math_exception(
            "canvas_preview_math_preview_extents_fail",
            exc,
            image_width=int(image_width),
            image_height=int(image_height),
            canvas_width=int(canvas_width),
            canvas_height=int(canvas_height),
            **_transform_fields(transform),
        )
        raise


def dominant_drag_axis(delta_x: float, delta_y: float) -> str | None:
    """ドラッグ量から優勢軸を返す。"""
    abs_x = abs(float(delta_x))
    abs_y = abs(float(delta_y))
    if abs_x <= 1e-9 and abs_y <= 1e-9:
        return None
    return "x" if abs_x >= abs_y else "y"


def _snap_axis(
    image_min: float,
    image_center: float,
    image_max: float,
    canvas_min: float,
    canvas_center: float,
    canvas_max: float,
    snap_distance: float,
) -> tuple[float, float | None, bool]:
    """単一軸の edge/center を最も近いガイドへ吸着させる。"""
    candidates = (
        (float(canvas_min) - float(image_min), float(canvas_min)),
        (float(canvas_center) - float(image_center), float(canvas_center)),
        (float(canvas_max) - float(image_max), float(canvas_max)),
    )
    best_delta = 0.0
    best_guide = None
    best_distance = float(snap_distance) + 1.0
    for delta, guide in candidates:
        distance = abs(float(delta))
        if distance > float(snap_distance):
            continue
        if distance >= best_distance:
            continue
        best_delta = float(delta)
        best_guide = float(guide)
        best_distance = distance
    if best_guide is None:
        return 0.0, None, False
    return best_delta, best_guide, True


def _axis_alignment_delta(
    *,
    guide: float | None,
    canvas_min: float,
    canvas_max: float,
    bounds_min: float,
    bounds_max: float,
) -> float:
    """吸着後の軸をガイドへ厳密に寄せる補正量を返す。"""
    if guide is None:
        return 0.0
    guide = float(guide)
    if math.isclose(guide, 0.0, abs_tol=_GEOMETRY_EPSILON):
        return -(float(bounds_min) + float(bounds_max)) * 0.5
    if math.isclose(guide, float(canvas_min), abs_tol=_GEOMETRY_EPSILON):
        return float(canvas_min) - float(bounds_min)
    if math.isclose(guide, float(canvas_max), abs_tol=_GEOMETRY_EPSILON):
        return float(canvas_max) - float(bounds_max)
    return 0.0


def snap_transform_to_canvas_guides(
    *,
    image_width: int,
    image_height: int,
    canvas_width: int,
    canvas_height: int,
    transform: CanvasPreviewTransform,
    snap_distance: float,
) -> CanvasPreviewSnapResult:
    """外接矩形ベースでキャンバス辺/中心へ軽く吸着させる。"""
    extents = preview_extents(
        image_width=image_width,
        image_height=image_height,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        transform=transform,
    )
    canvas_left = -float(canvas_width) * 0.5
    canvas_right = float(canvas_width) * 0.5
    canvas_top = -float(canvas_height) * 0.5
    canvas_bottom = float(canvas_height) * 0.5
    center_x = (float(extents.bounds_left) + float(extents.bounds_right)) * 0.5
    center_y = (float(extents.bounds_top) + float(extents.bounds_bottom)) * 0.5
    snap_delta_x, guide_x, snapped_x = _snap_axis(
        extents.bounds_left,
        center_x,
        extents.bounds_right,
        canvas_left,
        0.0,
        canvas_right,
        snap_distance,
    )
    snap_delta_y, guide_y, snapped_y = _snap_axis(
        extents.bounds_top,
        center_y,
        extents.bounds_bottom,
        canvas_top,
        0.0,
        canvas_bottom,
        snap_distance,
    )
    snapped_transform = CanvasPreviewTransform(
        offset_x=float(transform.offset_x) + float(snap_delta_x),
        offset_y=float(transform.offset_y) + float(snap_delta_y),
        scale=float(transform.scale),
        rotation_deg=float(transform.rotation_deg),
    )
    if snapped_x or snapped_y:
        snapped_extents = preview_extents(
            image_width=image_width,
            image_height=image_height,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            transform=snapped_transform,
        )
        snapped_transform = CanvasPreviewTransform(
            offset_x=_rounded_offset(
                float(snapped_transform.offset_x)
                + _axis_alignment_delta(
                    guide=guide_x,
                    canvas_min=canvas_left,
                    canvas_max=canvas_right,
                    bounds_min=snapped_extents.bounds_left,
                    bounds_max=snapped_extents.bounds_right,
                )
            ),
            offset_y=_rounded_offset(
                float(snapped_transform.offset_y)
                + _axis_alignment_delta(
                    guide=guide_y,
                    canvas_min=canvas_top,
                    canvas_max=canvas_bottom,
                    bounds_min=snapped_extents.bounds_top,
                    bounds_max=snapped_extents.bounds_bottom,
                )
            ),
            scale=float(transform.scale),
            rotation_deg=float(transform.rotation_deg),
        )
    return CanvasPreviewSnapResult(
        transform=snapped_transform,
        guide_x=guide_x,
        guide_y=guide_y,
        snapped_x=bool(snapped_x),
        snapped_y=bool(snapped_y),
    )


__all__ = [
    "CanvasPreviewExtents",
    "CanvasPreviewSnapResult",
    "CanvasPreviewTransform",
    "canvas_pixels_from_image_long_edge",
    "dominant_drag_axis",
    "fit_scale_for_mode",
    "fixed_ratio_text_for_preset",
    "image_polygon_points",
    "orientation_label_for_ratio",
    "oriented_ratio",
    "preview_extents",
    "ratio_text_for_preset",
    "ratio_text_for_values",
    "rotated_bounds_size",
    "snap_transform_to_canvas_guides",
]
