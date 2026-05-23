"""キャンバスプレビュー描画 widget。"""

from __future__ import annotations

import math
import traceback

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import QWidget

from ..util.debug_log import write_window_layout_debug_log
from ..util.theme import get_ui_theme, qcolor
from .canvas_preview_constants import (
    CANVAS_PREVIEW_BACKGROUND_DARK,
    CANVAS_PREVIEW_BACKGROUND_LIGHT,
)
from .canvas_preview_math import (
    dominant_drag_axis,
    snap_transform_to_canvas_guides,
    CanvasPreviewTransform,
    image_polygon_points,
    preview_extents,
)


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


def _log_widget_exception(event: str, exc: BaseException, **fields) -> None:
    """widget 層の例外を traceback 付きで記録する。"""
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


class CanvasPreviewWidget(QWidget):
    """キャンバスシミュレーションを描画する。"""

    transformChanged = Signal(float, float, float, float)
    viewZoomChanged = Signal(float)

    _OUTER_PADDING = 24.0
    _VIEWPORT_RADIUS = 14.0
    _CHECKER_CELL = 18.0
    _VIEW_ZOOM_MIN = 0.1
    _VIEW_ZOOM_MAX = 1.0
    _IMAGE_SCALE_MIN = 0.01
    _IMAGE_SCALE_MAX = 16.0
    _WHEEL_FACTOR = 1.12
    _SNAP_DISTANCE_VIEW = 10.0
    _VIEWPORT_BORDER_WIDTH = 0.9
    _CANVAS_BORDER_HALO_WIDTH = 3.0
    _CANVAS_BORDER_WIDTH = 1.5
    _CROP_OUTLINE_HALO_WIDTH = 3.0
    _CROP_OUTLINE_WIDTH = 1.5
    _SNAP_GUIDE_HALO_WIDTH = 2.5
    _SNAP_GUIDE_WIDTH = 1.4
    _CROP_MASK_EPSILON = 0.5

    def __init__(self, parent=None):
        """描画対象画像とシミュレーション状態を初期化する。"""
        super().__init__(parent)
        self.setMinimumSize(320, 280)
        self.setMouseTracking(True)
        self._image = QImage()
        self._image_grayscale = QImage()
        self._canvas_width = 1
        self._canvas_height = 1
        self._transform = CanvasPreviewTransform()
        self._view_zoom = 1.0
        self._background_tone = CANVAS_PREVIEW_BACKGROUND_LIGHT
        self._theme_override = None
        self._drag_active = False
        self._drag_start_pos = QPoint()
        self._drag_start_transform = CanvasPreviewTransform()
        self._drag_axis_lock: str | None = None
        self._snap_guide_x: float | None = None
        self._snap_guide_y: float | None = None

    def _clear_drag_feedback(self, *, clear_axis_lock: bool = False) -> None:
        """ドラッグ中のガイド表示と軸固定状態を初期化する。"""
        self._snap_guide_x = None
        self._snap_guide_y = None
        if clear_axis_lock:
            self._drag_axis_lock = None

    def sizeHint(self) -> QSize:
        """中央カラム向けの標準サイズを返す。"""
        return QSize(760, 620)

    def set_source_image(self, image: QImage) -> None:
        """描画元画像を差し替える。"""
        write_window_layout_debug_log(
            "canvas_preview_widget_set_source_image_begin",
            image_width=int(image.width()),
            image_height=int(image.height()),
            image_is_null=bool(image.isNull()),
        )
        try:
            self._image = QImage(image)
            self._image_grayscale = (
                self._image.convertToFormat(QImage.Format_Grayscale8)
                if not self._image.isNull()
                else QImage()
            )
            self._clear_drag_feedback(clear_axis_lock=True)
            self.update()
            write_window_layout_debug_log(
                "canvas_preview_widget_set_source_image_ok",
                image_width=int(self._image.width()),
                image_height=int(self._image.height()),
                image_is_null=bool(self._image.isNull()),
            )
        except Exception as exc:
            _log_widget_exception(
                "canvas_preview_widget_set_source_image_fail",
                exc,
                image_width=int(image.width()),
                image_height=int(image.height()),
                image_is_null=bool(image.isNull()),
            )
            raise

    def set_canvas_pixels(self, width: int, height: int) -> None:
        """シミュレーション対象キャンバスサイズを更新する。"""
        write_window_layout_debug_log(
            "canvas_preview_widget_set_canvas_pixels_begin",
            canvas_width=int(width),
            canvas_height=int(height),
        )
        try:
            self._canvas_width = max(1, int(width))
            self._canvas_height = max(1, int(height))
            self._clear_drag_feedback(clear_axis_lock=True)
            self.update()
            write_window_layout_debug_log(
                "canvas_preview_widget_set_canvas_pixels_ok",
                canvas_width=int(self._canvas_width),
                canvas_height=int(self._canvas_height),
            )
        except Exception as exc:
            _log_widget_exception(
                "canvas_preview_widget_set_canvas_pixels_fail",
                exc,
                canvas_width=int(width),
                canvas_height=int(height),
            )
            raise

    def set_transform_state(self, transform: CanvasPreviewTransform) -> None:
        """画像変形状態を更新する。"""
        write_window_layout_debug_log(
            "canvas_preview_widget_set_transform_state_begin",
            **_transform_fields(transform),
        )
        try:
            self._transform = transform
            if not self._drag_active:
                self._clear_drag_feedback(clear_axis_lock=True)
            self.update()
            write_window_layout_debug_log(
                "canvas_preview_widget_set_transform_state_ok",
                **_transform_fields(self._transform),
            )
        except Exception as exc:
            _log_widget_exception(
                "canvas_preview_widget_set_transform_state_fail",
                exc,
                **_transform_fields(transform),
            )
            raise

    def set_view_zoom(self, zoom: float) -> None:
        """プレビュー全体の表示倍率を更新する。"""
        write_window_layout_debug_log(
            "canvas_preview_widget_set_view_zoom_begin",
            requested_view_zoom=float(zoom),
            current_view_zoom=float(self._view_zoom),
        )
        try:
            self._view_zoom = max(self._VIEW_ZOOM_MIN, min(self._VIEW_ZOOM_MAX, float(zoom)))
            self.update()
            write_window_layout_debug_log(
                "canvas_preview_widget_set_view_zoom_ok",
                requested_view_zoom=float(zoom),
                applied_view_zoom=float(self._view_zoom),
            )
        except Exception as exc:
            _log_widget_exception(
                "canvas_preview_widget_set_view_zoom_fail",
                exc,
                requested_view_zoom=float(zoom),
                current_view_zoom=float(self._view_zoom),
            )
            raise

    def set_theme(self, theme) -> None:
        """親ウィンドウから受け取ったテーマを保持する。"""
        self._theme_override = theme
        self.update()

    def set_background_tone(self, tone: str) -> None:
        """キャンバスの確認用背景トーンを更新する。"""
        tone_name = str(tone or CANVAS_PREVIEW_BACKGROUND_LIGHT)
        if tone_name not in {
            CANVAS_PREVIEW_BACKGROUND_LIGHT,
            CANVAS_PREVIEW_BACKGROUND_DARK,
        }:
            tone_name = CANVAS_PREVIEW_BACKGROUND_LIGHT
        if tone_name == self._background_tone:
            return
        self._background_tone = tone_name
        self.update()

    def preview_image(self) -> QImage:
        """現在のシミュレーション結果をキャンバス範囲だけ画像化する。"""
        image = QImage(
            max(1, int(self._canvas_width)),
            max(1, int(self._canvas_height)),
            QImage.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        canvas_rect = QRectF(0.0, 0.0, float(image.width()), float(image.height()))
        self._draw_canvas_scene(
            painter,
            canvas_rect,
            theme=self._theme(),
            clip_rect=canvas_rect,
            include_checker=False,
            show_outside_mask=False,
        )
        painter.end()
        return image

    def guide_image(self) -> QImage:
        """ガイド線のみを透明背景 PNG 用に描画する。"""
        image = QImage(
            max(1, int(self._canvas_width)),
            max(1, int(self._canvas_height)),
            QImage.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        theme = self._theme()
        frame_pen = QPen(qcolor(theme.accent))
        frame_pen.setWidthF(self._CANVAS_BORDER_WIDTH)
        painter.setPen(frame_pen)
        painter.drawRect(QRectF(1.0, 1.0, image.width() - 2.0, image.height() - 2.0))
        canvas_rect = QRectF(0.0, 0.0, float(image.width()), float(image.height()))
        self._draw_center_guides(painter, canvas_rect, theme=theme)
        painter.end()
        return image

    def _theme(self):
        """現在テーマを返す。"""
        if self._theme_override is not None:
            return self._theme_override
        widget = self
        while widget is not None:
            theme_name = getattr(widget, "_ui_theme_name", None)
            if theme_name:
                return get_ui_theme(theme_name)
            widget = widget.parentWidget()
        return get_ui_theme(None)

    def _viewport_rect(self) -> QRectF:
        """プレビュー表示全体のビューポート矩形を返す。"""
        return QRectF(self.rect()).adjusted(
            self._OUTER_PADDING,
            self._OUTER_PADDING,
            -self._OUTER_PADDING,
            -self._OUTER_PADDING,
        )

    def _viewport_content_inset(self) -> float:
        """viewport 枠線と AA の内側だけへ scene を閉じ込める inset を返す。"""
        return max(1.0, float(self._VIEWPORT_BORDER_WIDTH) * 0.5 + 1.0)

    def _viewport_content_rect(self, viewport_rect: QRectF) -> QRectF:
        """viewport 枠線の内側だけを scene 描画範囲として返す。"""
        inset = self._viewport_content_inset()
        content_rect = QRectF(viewport_rect).adjusted(inset, inset, -inset, -inset)
        return content_rect if not content_rect.isEmpty() else QRectF()

    def _viewport_rounded_path(self, rect: QRectF, radius: float) -> QPainterPath:
        """viewport 背景/clip 用の rounded path を返す。"""
        path = QPainterPath()
        path.addRoundedRect(rect, max(0.0, float(radius)), max(0.0, float(radius)))
        return path

    def _fit_canvas_view_scale(self, viewport_rect: QRectF | None = None) -> float:
        """キャンバス全体を収める基準縮尺を返す。"""
        viewport = self._viewport_rect() if viewport_rect is None else QRectF(viewport_rect)
        if viewport.isEmpty():
            return 1.0
        return min(
            float(viewport.width()) / float(max(1, self._canvas_width)),
            float(viewport.height()) / float(max(1, self._canvas_height)),
        )

    def _canvas_rect(self) -> QRectF:
        """widget 内で現在の表示倍率を反映したキャンバス矩形を返す。"""
        viewport = self._viewport_rect()
        if viewport.width() <= 0.0 or viewport.height() <= 0.0:
            return QRectF()
        fit_viewport = self._viewport_content_rect(viewport)
        if fit_viewport.isEmpty():
            fit_viewport = viewport
        scale = self._fit_canvas_view_scale(fit_viewport) * float(self._view_zoom)
        draw_width = float(self._canvas_width) * scale
        draw_height = float(self._canvas_height) * scale
        return QRectF(
            viewport.center().x() - draw_width * 0.5,
            viewport.center().y() - draw_height * 0.5,
            draw_width,
            draw_height,
        )

    def _canvas_view_scale(self, canvas_rect: QRectF | None = None) -> float:
        """キャンバス px を view 座標へ写す縮尺を返す。"""
        rect = self._canvas_rect() if canvas_rect is None else QRectF(canvas_rect)
        if rect.isEmpty():
            return 1.0
        return float(rect.width()) / float(max(1, self._canvas_width))

    def _image_transform_for_rect(self, canvas_rect: QRectF) -> QTransform:
        """指定キャンバス矩形上で画像描画に使う transform を返す。"""
        view_scale = self._canvas_view_scale(canvas_rect)
        canvas_center = canvas_rect.center()
        transform = QTransform()
        transform.translate(
            canvas_center.x() + float(self._transform.offset_x) * view_scale,
            canvas_center.y() + float(self._transform.offset_y) * view_scale,
        )
        transform.rotate(float(self._transform.rotation_deg))
        transform.scale(
            float(self._transform.scale) * view_scale,
            float(self._transform.scale) * view_scale,
        )
        transform.translate(-float(self._image.width()) * 0.5, -float(self._image.height()) * 0.5)
        return transform

    def _image_polygon_for_rect(self, canvas_rect: QRectF) -> QPolygonF:
        """現在 transform 後の画像ポリゴンを view 座標で返す。"""
        if self._image.isNull():
            return QPolygonF()
        view_scale = self._canvas_view_scale(canvas_rect)
        center = canvas_rect.center()
        points = image_polygon_points(
            self._image.width(),
            self._image.height(),
            self._transform,
        )
        polygon = QPolygonF()
        for x_pos, y_pos in points:
            polygon.append(
                QPointF(
                    center.x() + float(x_pos) * view_scale,
                    center.y() + float(y_pos) * view_scale,
                )
            )
        return polygon

    def _checker_colors(self):
        """チェック柄の 2 色を確認用トーンに応じて返す。"""
        if self._background_tone == CANVAS_PREVIEW_BACKGROUND_DARK:
            return qcolor("#202020"), qcolor("#111111")
        return qcolor("#FFFFFF"), qcolor("#E9E9E9")

    def _outer_background_color(self, *, theme):
        """viewport 外側で使うテーマ由来の背景色を返す。"""
        return qcolor(theme.window_bg)

    def _viewport_fill_color(self, *, theme):
        """canvas 周囲の viewport ベース色を返す。"""
        return qcolor(theme.image_bg)

    def _draw_checker_background(self, painter: QPainter, canvas_rect: QRectF, *, theme) -> None:
        """余白確認用のチェック柄背景を描く。"""
        del theme
        inset = max(float(self._CANVAS_BORDER_HALO_WIDTH), float(self._CANVAS_BORDER_WIDTH)) * 0.5
        checker_clip_rect = QRectF(canvas_rect).adjusted(inset, inset, -inset, -inset)
        if checker_clip_rect.isEmpty():
            return
        light, dark = self._checker_colors()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setClipRect(checker_clip_rect)
        cell = max(1, int(round(self._CHECKER_CELL)))
        left = int(math.floor(checker_clip_rect.left()))
        top = int(math.floor(checker_clip_rect.top()))
        right = int(math.ceil(checker_clip_rect.right()))
        bottom = int(math.ceil(checker_clip_rect.bottom()))
        y_pos = top
        row_index = 0
        while y_pos < bottom:
            x_pos = left
            col_index = row_index % 2
            while x_pos < right:
                painter.fillRect(
                    x_pos,
                    y_pos,
                    cell,
                    cell,
                    light if (col_index % 2 == 0) else dark,
                )
                x_pos += cell
                col_index += 1
            y_pos += cell
            row_index += 1
        painter.restore()

    def _clear_checker_outside_canvas(
        self,
        painter: QPainter,
        canvas_rect: QRectF,
        *,
        theme,
        clip_rect: QRectF | None,
    ) -> None:
        """checker の小数境界はみ出しを最終描画経路で塗り戻す。"""
        if clip_rect is None or QRectF(clip_rect).isEmpty():
            return
        inset = max(float(self._CANVAS_BORDER_HALO_WIDTH), float(self._CANVAS_BORDER_WIDTH)) * 0.5
        visible_path = QPainterPath()
        visible_path.addRect(QRectF(clip_rect))
        canvas_inner_path = QPainterPath()
        canvas_inner_path.addRect(QRectF(canvas_rect).adjusted(inset, inset, -inset, -inset))
        outside_path = visible_path.subtracted(canvas_inner_path)
        if outside_path.isEmpty():
            return
        painter.save()
        painter.fillPath(outside_path, self._viewport_fill_color(theme=theme))
        painter.restore()

    def _draw_center_guides(self, painter: QPainter, canvas_rect: QRectF, *, theme) -> None:
        """中央十字ガイドを描画する。"""
        pen = QPen(qcolor(theme.accent, 180))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(
            QPointF(canvas_rect.center().x(), canvas_rect.top()),
            QPointF(canvas_rect.center().x(), canvas_rect.bottom()),
        )
        painter.drawLine(
            QPointF(canvas_rect.left(), canvas_rect.center().y()),
            QPointF(canvas_rect.right(), canvas_rect.center().y()),
        )

    def _contrast_outline_color(self, *, theme, alpha: int):
        """画像上でも視認しやすい輪郭色を返す。"""
        if self._viewport_fill_color(theme=theme).lightness() < 128:
            return qcolor("#FFFFFF", alpha)
        return qcolor("#000000", alpha)

    def _cropped_image_path(
        self,
        image_polygon: QPolygonF,
        canvas_rect: QRectF,
        *,
        clip_rect: QRectF | None = None,
    ) -> QPainterPath:
        """キャンバス外へはみ出した画像部分だけの path を返す。"""
        if image_polygon.isEmpty():
            return QPainterPath()
        if not self._image.isNull():
            extents = preview_extents(
                self._image.width(),
                self._image.height(),
                self._canvas_width,
                self._canvas_height,
                self._transform,
            )
            if max(
                float(extents.crop_left),
                float(extents.crop_top),
                float(extents.crop_right),
                float(extents.crop_bottom),
            ) <= self._CROP_MASK_EPSILON:
                return QPainterPath()
        image_path = QPainterPath()
        image_path.setFillRule(Qt.WindingFill)
        image_path.addPolygon(image_polygon)
        image_path.closeSubpath()
        visible_image_path = QPainterPath(image_path)
        if clip_rect is not None:
            visible_path = QPainterPath()
            visible_path.setFillRule(Qt.WindingFill)
            visible_path.addRect(QRectF(clip_rect))
            visible_image_path = visible_image_path.intersected(visible_path)
            if visible_image_path.isEmpty():
                return QPainterPath()
        canvas_mask_rect = QRectF(canvas_rect).adjusted(
            -self._CROP_MASK_EPSILON,
            -self._CROP_MASK_EPSILON,
            self._CROP_MASK_EPSILON,
            self._CROP_MASK_EPSILON,
        )
        canvas_path = QPainterPath()
        canvas_path.setFillRule(Qt.WindingFill)
        canvas_path.addRect(canvas_mask_rect)
        return visible_image_path.subtracted(canvas_path)

    def _draw_transformed_image(
        self,
        painter: QPainter,
        image: QImage,
        canvas_rect: QRectF,
        *,
        clip_rect: QRectF | None,
        opacity: float = 1.0,
    ) -> None:
        """指定画像を現在の画像 transform で描画する。"""
        if image.isNull():
            return
        image_transform = self._image_transform_for_rect(canvas_rect)
        image_clip_path = QPainterPath()
        if clip_rect is not None:
            image_clip_path = self._image_clip_path_for_view_rect(
                image_transform,
                QRectF(clip_rect),
                image_size=image.size(),
            )
            if image_clip_path.isEmpty():
                return
        painter.save()
        painter.setOpacity(float(opacity))
        painter.setTransform(image_transform, False)
        if clip_rect is not None:
            # 変換後の view 座標 clip を、画像座標に戻してから適用する。
            painter.setClipPath(image_clip_path)
        painter.drawImage(
            QRectF(0.0, 0.0, float(image.width()), float(image.height())),
            image,
        )
        painter.restore()

    def _draw_transformed_image_with_image_clip(
        self,
        painter: QPainter,
        image: QImage,
        canvas_rect: QRectF,
        image_clip_path: QPainterPath,
        *,
        opacity: float = 1.0,
    ) -> None:
        """画像座標の clip path で変換描画する。"""
        if image.isNull() or image_clip_path.isEmpty():
            return
        painter.save()
        painter.setOpacity(float(opacity))
        painter.setTransform(self._image_transform_for_rect(canvas_rect), False)
        painter.setClipPath(image_clip_path)
        painter.drawImage(
            QRectF(0.0, 0.0, float(image.width()), float(image.height())),
            image,
        )
        painter.restore()

    def _image_clip_path_for_view_rect(
        self,
        image_transform: QTransform,
        view_rect: QRectF,
        *,
        image_size: QSize,
    ) -> QPainterPath:
        """view 座標の矩形 clip を画像座標の path に変換する。"""
        if view_rect.isEmpty() or image_size.isEmpty():
            return QPainterPath()
        inverted, invertible = image_transform.inverted()
        if not invertible:
            return QPainterPath()
        view_path = QPainterPath()
        view_path.addRect(view_rect)
        image_clip_path = inverted.map(view_path)
        image_bounds = QPainterPath()
        image_bounds.addRect(QRectF(0.0, 0.0, float(image_size.width()), float(image_size.height())))
        return image_clip_path.intersected(image_bounds)

    def _image_clip_path_for_view_path(
        self,
        image_transform: QTransform,
        view_path: QPainterPath,
        *,
        image_size: QSize,
    ) -> QPainterPath:
        """view 座標の任意 path を画像座標の clip path に変換する。"""
        if view_path.isEmpty() or image_size.isEmpty():
            return QPainterPath()
        inverted, invertible = image_transform.inverted()
        if not invertible:
            return QPainterPath()
        image_clip_path = inverted.map(view_path)
        image_bounds = QPainterPath()
        image_bounds.addRect(QRectF(0.0, 0.0, float(image_size.width()), float(image_size.height())))
        return image_clip_path.intersected(image_bounds)

    def _draw_normal_image_clipped_to_canvas(
        self,
        painter: QPainter,
        canvas_rect: QRectF,
        *,
        clip_rect: QRectF | None,
    ) -> None:
        """通常画像をキャンバス内だけに描画する。"""
        if self._image.isNull():
            return
        view_path = QPainterPath()
        view_path.setFillRule(Qt.WindingFill)
        view_path.addRect(QRectF(canvas_rect))
        if clip_rect is not None:
            clip_path = QPainterPath()
            clip_path.setFillRule(Qt.WindingFill)
            clip_path.addRect(QRectF(clip_rect))
            view_path = view_path.intersected(clip_path)
        if view_path.isEmpty():
            return
        image_clip_path = self._image_clip_path_for_view_path(
            self._image_transform_for_rect(canvas_rect),
            view_path,
            image_size=self._image.size(),
        )
        if image_clip_path.isEmpty():
            return
        self._draw_transformed_image_with_image_clip(
            painter,
            self._image,
            canvas_rect,
            image_clip_path,
        )

    def _draw_muted_outside_image(
        self,
        painter: QPainter,
        image_polygon: QPolygonF,
        canvas_rect: QRectF,
        *,
        theme,
        clip_rect: QRectF | None,
    ) -> QPainterPath:
        """キャンバス外へはみ出した画像領域を暗く、少し落ち着かせて示す。"""
        _ = theme
        cropped_path = self._cropped_image_path(
            image_polygon,
            canvas_rect,
            clip_rect=clip_rect,
        )
        if cropped_path.isEmpty():
            return cropped_path
        if not self._image_grayscale.isNull():
            muted_path = QPainterPath(cropped_path)
            if clip_rect is not None:
                clip_path = QPainterPath()
                clip_path.addRect(QRectF(clip_rect))
                muted_path = muted_path.intersected(clip_path)
            image_clip_path = self._image_clip_path_for_view_path(
                self._image_transform_for_rect(canvas_rect),
                muted_path,
                image_size=self._image_grayscale.size(),
            )
            self._draw_transformed_image_with_image_clip(
                painter,
                self._image_grayscale,
                canvas_rect,
                image_clip_path,
                opacity=0.50,
            )
        painter.save()
        if clip_rect is not None:
            painter.setClipRect(clip_rect)
        # tint は view 座標 path として扱い、ここでは painter transform を変更しない。
        painter.fillPath(cropped_path, qcolor("#091018", 120))
        painter.restore()
        return cropped_path

    def _draw_crop_outline(
        self,
        painter: QPainter,
        cropped_path: QPainterPath,
        *,
        theme,
        clip_rect: QRectF | None,
    ) -> None:
        """はみ出し領域の外周を細い赤系ラインで示す。"""
        if cropped_path.isEmpty():
            return
        painter.save()
        if clip_rect is not None:
            painter.setClipRect(clip_rect)
        halo_pen = QPen(self._contrast_outline_color(theme=theme, alpha=110))
        halo_pen.setWidthF(self._CROP_OUTLINE_HALO_WIDTH)
        halo_pen.setCapStyle(Qt.RoundCap)
        halo_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(halo_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(cropped_path)
        crop_pen = QPen(qcolor(theme.warning_high, 220))
        crop_pen.setWidthF(self._CROP_OUTLINE_WIDTH)
        crop_pen.setCapStyle(Qt.RoundCap)
        crop_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(crop_pen)
        painter.drawPath(cropped_path)
        painter.restore()

    def _draw_canvas_boundary(self, painter: QPainter, canvas_rect: QRectF, *, theme) -> None:
        """キャンバス境界を画像上でも分かりやすく描画する。"""
        halo_pen = QPen(self._contrast_outline_color(theme=theme, alpha=96))
        halo_pen.setWidthF(self._CANVAS_BORDER_HALO_WIDTH)
        halo_pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(halo_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(canvas_rect)

        border_pen = QPen(qcolor(theme.accent, 220))
        border_pen.setWidthF(self._CANVAS_BORDER_WIDTH)
        border_pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(border_pen)
        painter.drawRect(canvas_rect)

    def _draw_snap_guides(self, painter: QPainter, canvas_rect: QRectF, *, theme) -> None:
        """スナップ中の辺/中心ガイドを軽く重ねる。"""
        if self._snap_guide_x is None and self._snap_guide_y is None:
            return
        view_scale = self._canvas_view_scale(canvas_rect)
        painter.save()
        painter.setClipRect(canvas_rect)
        if self._snap_guide_x is not None:
            x_pos = canvas_rect.center().x() + float(self._snap_guide_x) * view_scale
            is_center = abs(float(self._snap_guide_x)) <= 1e-6
            halo_pen = QPen(self._contrast_outline_color(theme=theme, alpha=96))
            halo_pen.setWidthF(self._SNAP_GUIDE_HALO_WIDTH)
            painter.setPen(halo_pen)
            painter.drawLine(
                QPointF(x_pos, canvas_rect.top()),
                QPointF(x_pos, canvas_rect.bottom()),
            )
            guide_pen = QPen(
                qcolor(theme.accent if is_center else theme.warning_high, 235 if is_center else 220)
            )
            guide_pen.setWidthF(self._SNAP_GUIDE_WIDTH)
            painter.setPen(guide_pen)
            painter.drawLine(
                QPointF(x_pos, canvas_rect.top()),
                QPointF(x_pos, canvas_rect.bottom()),
            )
        if self._snap_guide_y is not None:
            y_pos = canvas_rect.center().y() + float(self._snap_guide_y) * view_scale
            is_center = abs(float(self._snap_guide_y)) <= 1e-6
            halo_pen = QPen(self._contrast_outline_color(theme=theme, alpha=96))
            halo_pen.setWidthF(self._SNAP_GUIDE_HALO_WIDTH)
            painter.setPen(halo_pen)
            painter.drawLine(
                QPointF(canvas_rect.left(), y_pos),
                QPointF(canvas_rect.right(), y_pos),
            )
            guide_pen = QPen(
                qcolor(theme.accent if is_center else theme.warning_high, 235 if is_center else 220)
            )
            guide_pen.setWidthF(self._SNAP_GUIDE_WIDTH)
            painter.setPen(guide_pen)
            painter.drawLine(
                QPointF(canvas_rect.left(), y_pos),
                QPointF(canvas_rect.right(), y_pos),
            )
        painter.restore()

    def _draw_canvas_scene(
        self,
        painter: QPainter,
        canvas_rect: QRectF,
        *,
        theme,
        clip_rect: QRectF | None,
        include_checker: bool,
        show_outside_mask: bool,
    ) -> None:
        """キャンバス上の画像、ガイド、補助表示をまとめて描画する。"""
        if include_checker:
            self._draw_checker_background(painter, canvas_rect, theme=theme)
            self._clear_checker_outside_canvas(
                painter,
                canvas_rect,
                theme=theme,
                clip_rect=clip_rect,
            )
        cropped_path = QPainterPath()
        if not self._image.isNull():
            if show_outside_mask:
                cropped_path = self._draw_muted_outside_image(
                    painter,
                    self._image_polygon_for_rect(canvas_rect),
                    canvas_rect,
                    theme=theme,
                    clip_rect=clip_rect,
                )
                self._draw_normal_image_clipped_to_canvas(
                    painter,
                    canvas_rect,
                    clip_rect=clip_rect,
                )
            else:
                self._draw_transformed_image(
                    painter,
                    self._image,
                    canvas_rect,
                    clip_rect=clip_rect,
                )
        else:
            painter.save()
            if clip_rect is not None:
                painter.setClipRect(clip_rect)
            painter.setPen(qcolor(theme.text_muted))
            painter.drawText(canvas_rect, Qt.AlignCenter, "画像を取得できませんでした")
            painter.restore()

        self._draw_canvas_boundary(painter, canvas_rect, theme=theme)
        if show_outside_mask:
            self._draw_crop_outline(
                painter,
                cropped_path,
                theme=theme,
                clip_rect=clip_rect,
            )

        self._draw_center_guides(painter, canvas_rect, theme=theme)
        self._draw_snap_guides(painter, canvas_rect, theme=theme)

    def paintEvent(self, event) -> None:
        """キャンバス、画像、余白、はみ出し、ガイドをまとめて描画する。"""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        theme = self._theme()
        painter.fillRect(self.rect(), self._outer_background_color(theme=theme))

        viewport_rect = self._viewport_rect()
        if viewport_rect.isEmpty():
            painter.end()
            return

        painter.setPen(Qt.NoPen)
        painter.setBrush(self._viewport_fill_color(theme=theme))
        painter.drawRoundedRect(viewport_rect, self._VIEWPORT_RADIUS, self._VIEWPORT_RADIUS)

        canvas_rect = self._canvas_rect()
        if canvas_rect.isEmpty():
            painter.end()
            return

        viewport_content_rect = self._viewport_content_rect(viewport_rect)
        if viewport_content_rect.isEmpty():
            painter.end()
            return
        viewport_content_radius = max(
            0.0,
            float(self._VIEWPORT_RADIUS) - self._viewport_content_inset(),
        )
        viewport_content_path = self._viewport_rounded_path(
            viewport_content_rect,
            viewport_content_radius,
        )
        painter.save()
        painter.setClipPath(viewport_content_path)
        self._draw_canvas_scene(
            painter,
            canvas_rect,
            theme=theme,
            clip_rect=viewport_content_rect,
            include_checker=True,
            show_outside_mask=True,
        )
        painter.restore()
        viewport_pen = QPen(qcolor(theme.border))
        viewport_pen.setWidthF(self._VIEWPORT_BORDER_WIDTH)
        painter.setPen(viewport_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(viewport_rect, self._VIEWPORT_RADIUS, self._VIEWPORT_RADIUS)
        painter.end()

    def _apply_drag_transform(self, transform: CanvasPreviewTransform) -> None:
        """ドラッグ操作で確定した transform を widget/UI へ反映する。"""
        self._transform = transform
        self.transformChanged.emit(
            float(transform.offset_x),
            float(transform.offset_y),
            float(transform.scale),
            float(transform.rotation_deg),
        )
        self.update()

    def _drag_transform_from_pointer(
        self,
        point: QPoint,
        modifiers,
    ) -> CanvasPreviewTransform:
        """現在ポインタ位置と modifier からドラッグ後 transform を返す。"""
        view_scale = max(0.0001, self._canvas_view_scale())
        total_delta = point - self._drag_start_pos
        delta_x = float(total_delta.x()) / view_scale
        delta_y = float(total_delta.y()) / view_scale
        if modifiers & Qt.ShiftModifier:
            if self._drag_axis_lock is None:
                self._drag_axis_lock = dominant_drag_axis(delta_x, delta_y)
            if self._drag_axis_lock == "x":
                delta_y = 0.0
            elif self._drag_axis_lock == "y":
                delta_x = 0.0
        else:
            self._drag_axis_lock = None
        transform = CanvasPreviewTransform(
            offset_x=float(self._drag_start_transform.offset_x) + delta_x,
            offset_y=float(self._drag_start_transform.offset_y) + delta_y,
            scale=float(self._drag_start_transform.scale),
            rotation_deg=float(self._drag_start_transform.rotation_deg),
        )
        if modifiers & (Qt.ControlModifier | Qt.ShiftModifier) or self._image.isNull():
            self._snap_guide_x = None
            self._snap_guide_y = None
            return transform
        snap_result = snap_transform_to_canvas_guides(
            image_width=self._image.width(),
            image_height=self._image.height(),
            canvas_width=self._canvas_width,
            canvas_height=self._canvas_height,
            transform=transform,
            snap_distance=float(self._SNAP_DISTANCE_VIEW) / view_scale,
        )
        self._snap_guide_x = snap_result.guide_x
        self._snap_guide_y = snap_result.guide_y
        return snap_result.transform

    def mousePressEvent(self, event) -> None:
        """左ドラッグで画像を移動できるようにする。"""
        if (
            event.button() == Qt.LeftButton
            and not self._image.isNull()
            and self._viewport_rect().contains(event.position())
        ):
            self._drag_active = True
            self._drag_start_pos = event.position().toPoint()
            self._drag_start_transform = self._transform
            self._clear_drag_feedback(clear_axis_lock=True)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """ドラッグ移動を中心基準 offset に反映する。"""
        if not self._drag_active:
            super().mouseMoveEvent(event)
            return
        transform = self._drag_transform_from_pointer(
            event.position().toPoint(),
            event.modifiers(),
        )
        self._apply_drag_transform(transform)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        """ドラッグ終了時にカーソルを戻す。"""
        if event.button() == Qt.LeftButton and self._drag_active:
            self._drag_active = False
            self._clear_drag_feedback(clear_axis_lock=True)
            self.unsetCursor()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        """ホイール単体は表示倍率、Ctrl+ホイールは画像 scale を調整する。"""
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        factor = pow(self._WHEEL_FACTOR, float(delta) / 120.0)
        if event.modifiers() & Qt.ControlModifier:
            transform = CanvasPreviewTransform(
                offset_x=float(self._transform.offset_x),
                offset_y=float(self._transform.offset_y),
                scale=max(
                    self._IMAGE_SCALE_MIN,
                    min(self._IMAGE_SCALE_MAX, float(self._transform.scale) * factor),
                ),
                rotation_deg=float(self._transform.rotation_deg),
            )
            self._transform = transform
            self.transformChanged.emit(
                float(transform.offset_x),
                float(transform.offset_y),
                float(transform.scale),
                float(transform.rotation_deg),
            )
            self.update()
            event.accept()
            return
        self._view_zoom = max(
            self._VIEW_ZOOM_MIN,
            min(self._VIEW_ZOOM_MAX, float(self._view_zoom) * factor),
        )
        self.viewZoomChanged.emit(float(self._view_zoom))
        self.update()
        event.accept()
