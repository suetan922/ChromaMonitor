"""canvas_preview widget の描画回帰テスト。"""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from chroma_monitor.util import constants as C
from chroma_monitor.util.theme import get_ui_theme, qcolor
from chroma_monitor.views.canvas_preview import CanvasPreviewWidget
from chroma_monitor.views.canvas_preview_constants import (
    CANVAS_PREVIEW_BACKGROUND_DARK,
    CANVAS_PREVIEW_BACKGROUND_LIGHT,
)
from chroma_monitor.views.canvas_preview_math import CanvasPreviewTransform

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _render_widget(widget: CanvasPreviewWidget) -> QImage:
    image = QImage(widget.size(), QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    try:
        widget.render(painter, QPoint())
    finally:
        painter.end()
    return image


def _relative_luminance(color) -> float:
    return (
        0.2126 * float(color.redF())
        + 0.7152 * float(color.greenF())
        + 0.0722 * float(color.blueF())
    )


def _first_point_in_path(path) -> QPointF | None:
    bounds = path.boundingRect()
    left = int(math.floor(bounds.left()))
    top = int(math.floor(bounds.top()))
    right = int(math.ceil(bounds.right()))
    bottom = int(math.ceil(bounds.bottom()))
    for y_pos in range(top, bottom + 1):
        for x_pos in range(left, right + 1):
            point = QPointF(float(x_pos) + 0.5, float(y_pos) + 0.5)
            if path.contains(point):
                return point
    return None


def _path_from_polygon(polygon) -> object:
    from PySide6.QtGui import QPainterPath

    path = QPainterPath()
    path.setFillRule(Qt.WindingFill)
    path.addPolygon(polygon)
    path.closeSubpath()
    return path


def _rect_path(rect: QRectF):
    from PySide6.QtGui import QPainterPath

    path = QPainterPath()
    path.addRect(rect)
    return path


def _sample_points_in_path(
    path,
    *,
    canvas_rect,
    require_inside_canvas: bool,
    visible_rect=None,
    limit: int = 3,
) -> list[QPointF]:
    points: list[QPointF] = []
    bounds = path.boundingRect()
    left = int(math.floor(bounds.left()))
    top = int(math.floor(bounds.top()))
    right = int(math.ceil(bounds.right()))
    bottom = int(math.ceil(bounds.bottom()))
    for y_pos in range(top, bottom + 1, 4):
        for x_pos in range(left, right + 1, 4):
            point = QPointF(float(x_pos) + 0.5, float(y_pos) + 0.5)
            if not path.contains(point):
                continue
            if not all(
                path.contains(QPointF(point.x() + dx, point.y() + dy))
                for dx, dy in ((-6.0, 0.0), (6.0, 0.0), (0.0, -6.0), (0.0, 6.0))
            ):
                continue
            if visible_rect is not None and not visible_rect.adjusted(4.0, 4.0, -4.0, -4.0).contains(point):
                continue
            inside_canvas = canvas_rect.contains(point)
            if inside_canvas != require_inside_canvas:
                continue
            if inside_canvas:
                if not canvas_rect.adjusted(28.0, 28.0, -28.0, -28.0).contains(point):
                    continue
                if abs(point.x() - canvas_rect.center().x()) < 8.0:
                    continue
                if abs(point.y() - canvas_rect.center().y()) < 8.0:
                    continue
            else:
                near_canvas_x = canvas_rect.left() - 4.0 <= point.x() <= canvas_rect.right() + 4.0
                near_canvas_y = canvas_rect.top() - 4.0 <= point.y() <= canvas_rect.bottom() + 4.0
                if near_canvas_x and near_canvas_y:
                    continue
            points.append(point)
            if len(points) >= int(limit):
                return points
    if points:
        return points
    raise AssertionError("sample points not found")


def _assert_render_keeps_canvas_inside_normal_and_outside_muted(
    *,
    image_size: tuple[int, int],
    canvas_size: tuple[int, int],
    transform: CanvasPreviewTransform,
    view_zoom: float = 1.0,
    expect_visible_outside: bool = True,
) -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(760, 620)

    source = QImage(image_size[0], image_size[1], QImage.Format_RGB32)
    source.fill(qcolor("#4AA5FF"))
    widget.set_source_image(source)
    widget.set_canvas_pixels(*canvas_size)
    widget.set_view_zoom(view_zoom)
    widget.set_transform_state(transform)
    widget.show()
    app.processEvents()

    canvas_rect = widget._canvas_rect()
    visible_rect = widget._viewport_rect()
    image_path = _path_from_polygon(widget._image_polygon_for_rect(canvas_rect))
    inside_points = _sample_points_in_path(
        image_path,
        canvas_rect=canvas_rect,
        require_inside_canvas=True,
        visible_rect=visible_rect,
    )
    rendered = _render_widget(widget)

    source_color = qcolor("#4AA5FF")

    inside_colors = [
        rendered.pixelColor(int(point.x()), int(point.y()))
        for point in inside_points
    ]
    for inside_color in inside_colors:
        assert abs(inside_color.red() - source_color.red()) <= 12
        assert abs(inside_color.green() - source_color.green()) <= 12
        assert abs(inside_color.blue() - source_color.blue()) <= 12
    if expect_visible_outside:
        outside_points = _sample_points_in_path(
            widget._cropped_image_path(widget._image_polygon_for_rect(canvas_rect), canvas_rect),
            canvas_rect=canvas_rect,
            require_inside_canvas=False,
            visible_rect=visible_rect,
        )
        outside_colors = [
            rendered.pixelColor(int(point.x()), int(point.y()))
            for point in outside_points
        ]
        min_inside_saturation = min(color.saturation() for color in inside_colors)
        min_inside_luminance = min(_relative_luminance(color) for color in inside_colors)
        for outside_color in outside_colors:
            assert outside_color.saturation() < min_inside_saturation
            assert _relative_luminance(outside_color) < min_inside_luminance

    widget.close()
    app.processEvents()


def _assert_render_keeps_inside_image_normal_when_canvas_has_margins(
    *,
    image_size: tuple[int, int],
    canvas_size: tuple[int, int],
    transform: CanvasPreviewTransform,
    view_zoom: float,
) -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(760, 620)

    source = QImage(image_size[0], image_size[1], QImage.Format_RGB32)
    source.fill(qcolor("#4AA5FF"))
    widget.set_source_image(source)
    widget.set_canvas_pixels(*canvas_size)
    widget.set_view_zoom(view_zoom)
    widget.set_transform_state(transform)
    widget.show()
    app.processEvents()

    canvas_rect = widget._canvas_rect()
    visible_rect = widget._viewport_rect()
    image_polygon = widget._image_polygon_for_rect(canvas_rect)
    image_path = _path_from_polygon(image_polygon)
    cropped_path = widget._cropped_image_path(image_polygon, canvas_rect)

    assert cropped_path.isEmpty() is True

    inside_points = _sample_points_in_path(
        image_path,
        canvas_rect=canvas_rect,
        require_inside_canvas=True,
        visible_rect=visible_rect,
        limit=4,
    )
    rendered = _render_widget(widget)
    source_color = qcolor("#4AA5FF")

    for point in inside_points:
        color = rendered.pixelColor(int(point.x()), int(point.y()))
        assert abs(color.red() - source_color.red()) <= 12
        assert abs(color.green() - source_color.green()) <= 12
        assert abs(color.blue() - source_color.blue()) <= 12

    widget.close()
    app.processEvents()


def test_canvas_preview_outside_region_is_muted_and_has_red_crop_outline() -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(480, 360)

    source = QImage(240, 240, QImage.Format_RGB32)
    source.fill(qcolor("#4AA5FF"))
    widget.set_source_image(source)
    widget.set_canvas_pixels(120, 120)

    widget.show()
    app.processEvents()

    canvas_rect = widget._canvas_rect()
    image_bounds = widget._image_polygon_for_rect(canvas_rect).boundingRect()
    rendered = _render_widget(widget)

    inside_x = int(round(canvas_rect.center().x()))
    inside_y = int(round(canvas_rect.center().y()))
    outside_x = int(round(canvas_rect.left() - min(20.0, (canvas_rect.left() - image_bounds.left()) * 0.5)))
    outside_y = inside_y

    inside_color = rendered.pixelColor(inside_x, inside_y)
    outside_color = rendered.pixelColor(outside_x, outside_y)

    assert _relative_luminance(outside_color) < _relative_luminance(inside_color)
    assert outside_color.saturation() < inside_color.saturation()

    boundary_x = int(round(canvas_rect.left()))
    red_dominance = max(
        rendered.pixelColor(boundary_x + offset, inside_y).red()
        - max(
            rendered.pixelColor(boundary_x + offset, inside_y).green(),
            rendered.pixelColor(boundary_x + offset, inside_y).blue(),
        )
        for offset in range(-3, 4)
    )
    assert red_dominance >= 3

    widget.close()
    app.processEvents()


def test_canvas_preview_drag_supports_shift_lock_and_ctrl_snap_bypass() -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(480, 360)

    source = QImage(100, 100, QImage.Format_RGB32)
    source.fill(qcolor("#4AA5FF"))
    widget.set_source_image(source)
    widget.set_canvas_pixels(200, 200)

    canvas_rect = widget._canvas_rect()
    start = canvas_rect.center().toPoint()
    widget._drag_active = True
    widget._drag_start_pos = start
    widget._drag_start_transform = CanvasPreviewTransform()
    horizontal = widget._drag_transform_from_pointer(start + QPoint(48, 10), Qt.ShiftModifier)
    assert horizontal.offset_y == 0.0
    assert horizontal.offset_x != 0.0
    assert widget._snap_guide_x is None
    assert widget._snap_guide_y is None

    widget._drag_active = True
    widget._drag_axis_lock = None
    widget._drag_start_pos = start
    widget._drag_start_transform = CanvasPreviewTransform(offset_x=-45.0, offset_y=0.0)
    snapped = widget._drag_transform_from_pointer(start, Qt.NoModifier)
    assert snapped.offset_x == -50.0
    assert widget._snap_guide_x == -100.0

    widget._drag_active = True
    widget._drag_axis_lock = None
    widget._drag_start_pos = start
    widget._drag_start_transform = CanvasPreviewTransform(offset_x=-45.0, offset_y=0.0)
    unsnapped = widget._drag_transform_from_pointer(start, Qt.ControlModifier)
    assert unsnapped.offset_x == -45.0
    assert widget._snap_guide_x is None

    widget.close()
    app.processEvents()


def test_canvas_preview_does_not_mask_inside_area_when_edge_aligned() -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(480, 360)

    source = QImage(100, 100, QImage.Format_RGB32)
    source.fill(qcolor("#4AA5FF"))
    widget.set_source_image(source)
    widget.set_canvas_pixels(200, 200)
    widget.set_transform_state(CanvasPreviewTransform(offset_x=-50.0, offset_y=0.0, scale=1.0))

    canvas_rect = widget._canvas_rect()
    cropped_path = widget._cropped_image_path(
        widget._image_polygon_for_rect(canvas_rect),
        canvas_rect,
    )

    assert cropped_path.isEmpty() is True

    widget.close()
    app.processEvents()


def test_canvas_preview_masks_only_outside_when_image_shifted_left_up() -> None:
    _assert_render_keeps_canvas_inside_normal_and_outside_muted(
        image_size=(1046, 1503),
        canvas_size=(1127, 1503),
        transform=CanvasPreviewTransform(offset_x=-498.9, offset_y=-93.3, scale=1.0),
    )


def test_canvas_preview_masks_only_outside_when_image_shifted_left_up_farther() -> None:
    _assert_render_keeps_canvas_inside_normal_and_outside_muted(
        image_size=(1046, 1503),
        canvas_size=(1127, 1503),
        transform=CanvasPreviewTransform(offset_x=-470.9, offset_y=-312.5, scale=1.0),
    )


def test_canvas_preview_masks_only_outside_when_image_shifted_right_down() -> None:
    _assert_render_keeps_canvas_inside_normal_and_outside_muted(
        image_size=(1046, 1503),
        canvas_size=(1127, 1503),
        transform=CanvasPreviewTransform(offset_x=498.9, offset_y=93.3, scale=1.0),
    )


def test_canvas_preview_masks_only_outside_with_rotation() -> None:
    _assert_render_keeps_canvas_inside_normal_and_outside_muted(
        image_size=(320, 220),
        canvas_size=(240, 240),
        transform=CanvasPreviewTransform(offset_x=20.0, offset_y=-18.0, scale=1.25, rotation_deg=27.0),
    )


def test_canvas_preview_masks_only_outside_with_view_zoom() -> None:
    _assert_render_keeps_canvas_inside_normal_and_outside_muted(
        image_size=(320, 220),
        canvas_size=(240, 240),
        transform=CanvasPreviewTransform(offset_x=-42.0, offset_y=20.0, scale=1.2),
        view_zoom=0.8,
    )


def test_canvas_preview_keeps_inside_image_normal_when_canvas_is_taller_than_source() -> None:
    _assert_render_keeps_inside_image_normal_when_canvas_has_margins(
        image_size=(700, 427),
        canvas_size=(700, 525),
        transform=CanvasPreviewTransform(offset_x=0.0, offset_y=0.0, scale=1.0),
        view_zoom=3.0,
    )


def test_canvas_preview_masks_only_outside_when_image_is_larger_than_canvas() -> None:
    _assert_render_keeps_canvas_inside_normal_and_outside_muted(
        image_size=(240, 240),
        canvas_size=(120, 120),
        transform=CanvasPreviewTransform(offset_x=0.0, offset_y=0.0, scale=1.0),
        view_zoom=1.0,
    )


def test_canvas_preview_masks_only_outside_with_rotation_offset_and_zoom_regression() -> None:
    _assert_render_keeps_canvas_inside_normal_and_outside_muted(
        image_size=(320, 220),
        canvas_size=(240, 240),
        transform=CanvasPreviewTransform(offset_x=28.0, offset_y=-22.0, scale=1.22, rotation_deg=24.0),
        view_zoom=1.8,
        expect_visible_outside=False,
    )


def test_canvas_preview_masks_only_outside_with_large_negative_offsets() -> None:
    _assert_render_keeps_canvas_inside_normal_and_outside_muted(
        image_size=(1046, 1503),
        canvas_size=(1127, 1503),
        transform=CanvasPreviewTransform(offset_x=-470.9, offset_y=-312.5, scale=1.0),
        view_zoom=1.0,
    )


def test_canvas_preview_masks_only_outside_with_large_positive_offsets() -> None:
    _assert_render_keeps_canvas_inside_normal_and_outside_muted(
        image_size=(1046, 1503),
        canvas_size=(1127, 1503),
        transform=CanvasPreviewTransform(offset_x=470.9, offset_y=312.5, scale=1.0),
        view_zoom=1.0,
    )


def test_canvas_preview_crop_path_stays_outside_canvas_with_rotation_and_zoom() -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(520, 420)

    source = QImage(220, 140, QImage.Format_RGB32)
    source.fill(qcolor("#4AA5FF"))
    widget.set_source_image(source)
    widget.set_canvas_pixels(120, 120)
    widget.set_view_zoom(1.6)
    widget.set_transform_state(
        CanvasPreviewTransform(offset_x=18.0, offset_y=-12.0, scale=1.35, rotation_deg=27.0)
    )
    widget.show()
    app.processEvents()

    canvas_rect = widget._canvas_rect()
    visible_rect = widget._viewport_rect()
    image_polygon = widget._image_polygon_for_rect(canvas_rect)
    image_path = _path_from_polygon(image_polygon)
    cropped_path = widget._cropped_image_path(
        image_polygon,
        canvas_rect,
    )
    outside_point = _first_point_in_path(cropped_path)
    inside_points = _sample_points_in_path(
        image_path,
        canvas_rect=canvas_rect,
        require_inside_canvas=True,
        visible_rect=visible_rect,
        limit=4,
    )

    assert cropped_path.isEmpty() is False
    assert outside_point is not None
    assert canvas_rect.contains(outside_point) is False
    assert cropped_path.contains(outside_point) is True
    assert cropped_path.contains(canvas_rect.center()) is False
    assert all(not cropped_path.contains(point) for point in inside_points)

    widget.close()
    app.processEvents()


def test_canvas_preview_shows_no_normal_image_when_image_polygon_is_fully_outside_canvas() -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(520, 420)

    source = QImage(120, 120, QImage.Format_RGB32)
    source.fill(qcolor("#4AA5FF"))
    widget.set_source_image(source)
    widget.set_canvas_pixels(120, 120)
    widget.set_transform_state(
        CanvasPreviewTransform(offset_x=260.0, offset_y=0.0, scale=1.0)
    )
    widget.show()
    app.processEvents()

    canvas_rect = widget._canvas_rect()
    image_path = _path_from_polygon(widget._image_polygon_for_rect(canvas_rect))
    canvas_path = _rect_path(canvas_rect)
    rendered = _render_widget(widget)
    center_color = rendered.pixelColor(
        int(round(canvas_rect.center().x())),
        int(round(canvas_rect.center().y())),
    )
    source_color = qcolor("#4AA5FF")

    assert image_path.intersected(canvas_path).isEmpty() is True
    assert abs(center_color.red() - source_color.red()) > 20 or abs(center_color.green() - source_color.green()) > 20 or abs(center_color.blue() - source_color.blue()) > 20

    widget.close()
    app.processEvents()


def test_canvas_preview_background_tone_switches_checker_only() -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    theme = get_ui_theme(C.UI_THEME_LIGHT)
    widget.set_theme(theme)
    widget.resize(480, 360)

    source = QImage(80, 80, QImage.Format_RGB32)
    source.fill(qcolor("#4AA5FF"))
    widget.set_source_image(source)
    widget.set_canvas_pixels(200, 200)

    widget.set_background_tone(CANVAS_PREVIEW_BACKGROUND_LIGHT)
    light_checker_colors = widget._checker_colors()
    light_outer_fill = widget._outer_background_color(theme=theme)
    light_viewport_fill = widget._viewport_fill_color(theme=theme)
    light_outline = widget._contrast_outline_color(theme=theme, alpha=96)
    widget.show()
    app.processEvents()
    light_render = _render_widget(widget)

    widget.set_background_tone(CANVAS_PREVIEW_BACKGROUND_DARK)
    dark_checker_colors = widget._checker_colors()
    dark_outer_fill = widget._outer_background_color(theme=theme)
    dark_viewport_fill = widget._viewport_fill_color(theme=theme)
    dark_outline = widget._contrast_outline_color(theme=theme, alpha=96)
    app.processEvents()
    dark_render = _render_widget(widget)

    canvas_rect = widget._canvas_rect()
    viewport_rect = widget._viewport_rect()
    sample_x = int(round(canvas_rect.left() + 18))
    sample_y = int(round(canvas_rect.top() + 18))
    viewport_x = int(round((viewport_rect.left() + canvas_rect.left()) * 0.5))
    viewport_y = int(round(canvas_rect.center().y()))
    outer_x = int(round(viewport_rect.left() * 0.5))
    outer_y = int(round(viewport_rect.center().y()))

    light_color = light_render.pixelColor(sample_x, sample_y)
    dark_color = dark_render.pixelColor(sample_x, sample_y)
    light_viewport_color = light_render.pixelColor(viewport_x, viewport_y)
    dark_viewport_color = dark_render.pixelColor(viewport_x, viewport_y)
    light_outer_color = light_render.pixelColor(outer_x, outer_y)
    dark_outer_color = dark_render.pixelColor(outer_x, outer_y)

    assert light_checker_colors != dark_checker_colors
    assert light_outer_fill == dark_outer_fill
    assert light_viewport_fill == dark_viewport_fill
    assert light_outline == dark_outline
    assert _relative_luminance(light_color) > _relative_luminance(dark_color)
    assert light_viewport_color == dark_viewport_color
    assert light_outer_color == dark_outer_color

    widget.close()
    app.processEvents()


def _assert_checker_tiles_are_clipped_inside_canvas(tone: str) -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.set_background_tone(tone)
    widget.set_source_image(QImage(1046, 1503, QImage.Format_RGB32))
    widget.set_canvas_pixels(1503, 1503)
    widget.set_view_zoom(3.0)
    widget.set_transform_state(
        CanvasPreviewTransform(
            offset_x=0.7515,
            offset_y=329.41205,
            scale=1.4383393881453153,
        )
    )

    base_color = qcolor("#335577")
    image = QImage(220, 220, QImage.Format_ARGB32_Premultiplied)
    image.fill(base_color)
    painter = QPainter(image)
    try:
        canvas_rect = QRectF(40.35, 38.65, 140.3, 140.3)
        widget._draw_checker_background(painter, canvas_rect, theme=get_ui_theme(C.UI_THEME_LIGHT))
    finally:
        painter.end()

    checker_colors = {color.rgb() for color in widget._checker_colors()}
    inset = max(widget._CANVAS_BORDER_HALO_WIDTH, widget._CANVAS_BORDER_WIDTH) * 0.5
    inside_color = image.pixelColor(
        int(canvas_rect.left() + inset + 8.0),
        int(canvas_rect.top() + inset + 8.0),
    )
    outside_points = (
        (int(canvas_rect.left()) - 1, int(canvas_rect.center().y())),
        (int(canvas_rect.left()) - 3, int(canvas_rect.center().y())),
        (int(canvas_rect.right()) + 1, int(canvas_rect.center().y())),
        (int(canvas_rect.right()) + 3, int(canvas_rect.center().y())),
        (int(canvas_rect.center().x()), int(canvas_rect.top()) - 1),
        (int(canvas_rect.center().x()), int(canvas_rect.top()) - 3),
        (int(canvas_rect.center().x()), int(canvas_rect.bottom()) + 1),
        (int(canvas_rect.center().x()), int(canvas_rect.bottom()) + 3),
    )

    assert inside_color.rgb() in checker_colors
    for x_pos, y_pos in outside_points:
        assert image.pixelColor(x_pos, y_pos).rgb() == base_color.rgb()

    widget.close()
    app.processEvents()


def test_canvas_preview_checker_tiles_do_not_bleed_outside_canvas_light_tone() -> None:
    _assert_checker_tiles_are_clipped_inside_canvas(CANVAS_PREVIEW_BACKGROUND_LIGHT)


def test_canvas_preview_checker_tiles_do_not_bleed_outside_canvas_dark_tone() -> None:
    _assert_checker_tiles_are_clipped_inside_canvas(CANVAS_PREVIEW_BACKGROUND_DARK)


def _assert_checker_tiles_do_not_bleed_in_final_render(tone: str) -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(2400, 620)
    widget.set_background_tone(tone)

    source = QImage(1046, 1503, QImage.Format_ARGB32_Premultiplied)
    source.fill(Qt.transparent)
    widget.set_source_image(source)
    widget.set_canvas_pixels(1503, 1503)
    widget.set_view_zoom(3.0)
    widget.set_transform_state(
        CanvasPreviewTransform(
            offset_x=0.7515,
            offset_y=329.41205,
            scale=1.4383393881453153,
        )
    )
    widget.show()
    app.processEvents()

    rendered = _render_widget(widget)
    canvas_rect = widget._canvas_rect()
    checker_colors = {color.rgb() for color in widget._checker_colors()}
    inset = max(widget._CANVAS_BORDER_HALO_WIDTH, widget._CANVAS_BORDER_WIDTH) * 0.5
    sample_y = int(widget._viewport_rect().top() + 96)
    inside_x = int(canvas_rect.left() + inset + 18)
    inside_color = rendered.pixelColor(inside_x, sample_y)
    outside_points = (
        (int(math.floor(canvas_rect.left())) - 1, sample_y),
        (int(math.floor(canvas_rect.left())) - 2, sample_y),
        (int(math.floor(canvas_rect.left())) - 3, sample_y),
        (int(math.ceil(canvas_rect.right())) + 1, sample_y),
        (int(math.ceil(canvas_rect.right())) + 2, sample_y),
        (int(math.ceil(canvas_rect.right())) + 3, sample_y),
    )

    assert inside_color.rgb() in checker_colors
    for x_pos, y_pos in outside_points:
        assert rendered.pixelColor(x_pos, y_pos).rgb() not in checker_colors

    widget.close()
    app.processEvents()


def test_canvas_preview_checker_tiles_do_not_bleed_in_final_render_light_tone() -> None:
    _assert_checker_tiles_do_not_bleed_in_final_render(CANVAS_PREVIEW_BACKGROUND_LIGHT)


def test_canvas_preview_checker_tiles_do_not_bleed_in_final_render_dark_tone() -> None:
    _assert_checker_tiles_do_not_bleed_in_final_render(CANVAS_PREVIEW_BACKGROUND_DARK)


def test_canvas_preview_viewport_border_stays_above_checker_at_high_zoom() -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(760, 620)

    source = QImage(1046, 1503, QImage.Format_ARGB32_Premultiplied)
    source.fill(Qt.transparent)
    widget.set_source_image(source)
    widget.set_canvas_pixels(1503, 1503)
    widget.set_view_zoom(3.0)
    widget.set_transform_state(
        CanvasPreviewTransform(
            offset_x=0.7515,
            offset_y=329.41205,
            scale=1.4383393881453153,
        )
    )
    widget.show()
    app.processEvents()

    rendered = _render_widget(widget)
    viewport_rect = widget._viewport_rect()
    checker_colors = {color.rgb() for color in widget._checker_colors()}
    border_points = (
        (int(viewport_rect.left()), int(viewport_rect.center().y())),
        (int(viewport_rect.right()), int(viewport_rect.center().y())),
        (int(viewport_rect.center().x()), int(viewport_rect.top())),
        (int(viewport_rect.center().x()), int(viewport_rect.bottom())),
    )
    inside_color = rendered.pixelColor(
        int(viewport_rect.left() + 24),
        int(viewport_rect.top() + 48),
    )

    assert inside_color.rgb() in checker_colors
    for x_pos, y_pos in border_points:
        assert rendered.pixelColor(x_pos, y_pos).rgb() not in checker_colors

    widget.close()
    app.processEvents()


def test_canvas_preview_scene_is_clipped_inside_viewport_border_at_high_zoom() -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(760, 620)

    source = QImage(700, 427, QImage.Format_ARGB32_Premultiplied)
    source.fill(Qt.transparent)
    widget.set_source_image(source)
    widget.set_canvas_pixels(700, 525)
    widget.set_view_zoom(3.0)
    widget.set_transform_state(CanvasPreviewTransform())
    widget.show()
    app.processEvents()

    rendered = _render_widget(widget)
    viewport_rect = widget._viewport_rect()
    content_rect = widget._viewport_content_rect(viewport_rect)
    checker_colors = {color.rgb() for color in widget._checker_colors()}
    border_probe_points = (
        (int(viewport_rect.left() + 1), int(viewport_rect.center().y())),
        (int(viewport_rect.right() - 1), int(viewport_rect.center().y())),
        (int(viewport_rect.center().x()), int(viewport_rect.top() + 1)),
        (int(viewport_rect.center().x()), int(viewport_rect.bottom() - 1)),
    )
    content_color = rendered.pixelColor(
        int(content_rect.left() + 48),
        int(content_rect.top() + 48),
    )

    assert content_color.rgb() in checker_colors
    for x_pos, y_pos in border_probe_points:
        assert rendered.pixelColor(x_pos, y_pos).rgb() not in checker_colors

    widget.close()
    app.processEvents()
