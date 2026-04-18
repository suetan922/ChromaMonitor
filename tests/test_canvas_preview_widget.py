"""canvas_preview widget の描画回帰テスト。"""

from __future__ import annotations

import os

from PySide6.QtCore import QPoint, Qt
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


def test_canvas_preview_outside_region_is_muted_and_has_red_crop_outline() -> None:
    app = _app()
    widget = CanvasPreviewWidget()
    widget.set_theme(get_ui_theme(C.UI_THEME_LIGHT))
    widget.resize(480, 360)

    source = QImage(240, 120, QImage.Format_RGB32)
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
