"""キャンバスプレビュー描画用 widget と補助関数群。"""

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
    """連鎖した例外から最終的な根本例外を取り出す。"""
    # 例外の原因連鎖をたどり、最も内側で発生した例外を返す。
    current = exc
    # `__cause__` が尽きるまでたどって、根本原因だけを抜き出す。
    while True:
        next_exc = current.__cause__
        if next_exc is None or next_exc is current:
            return current
        current = next_exc


def _transform_fields(transform: CanvasPreviewTransform) -> dict[str, float | str]:
    """ログ出力用に transform の主要値を辞書へ展開する。"""
    # ログで差分追跡しやすいよう、各フィールドを素直な型に変換して返す。
    return {
        "transform": repr(transform),
        "offset_x": float(transform.offset_x),
        "offset_y": float(transform.offset_y),
        "scale": float(transform.scale),
        "rotation_deg": float(transform.rotation_deg),
    }


def _log_widget_exception(event: str, exc: BaseException, **fields) -> None:
    """ウィジェット内例外を traceback 付きで debug log に残す。"""
    # まずは原因連鎖の末端例外を取り出し、ログに併記できるようにする。
    root = _root_exception(exc)
    # 呼び出し元の補助情報と一緒に、例外内容を構造化ログへ記録する。
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
    """キャンバスプレビューを描画し、位置・回転・倍率操作を受け持つ。"""

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
        # QWidget の基本初期化を先に行い、描画・入力設定を有効にする。
        super().__init__(parent)
        self.setMinimumSize(320, 280)
        self.setMouseTracking(True)
        # 画像・キャンバス・変形の現在状態を初期値でそろえる。
        self._image = QImage()
        self._image_grayscale = QImage()
        self._canvas_width = 1
        self._canvas_height = 1
        self._transform = CanvasPreviewTransform()
        self._view_zoom = 1.0
        self._background_tone = CANVAS_PREVIEW_BACKGROUND_LIGHT
        self._theme_override = None
        # ドラッグ中の補助状態を初期化し、最初はガイドも出さない。
        self._drag_active = False
        self._drag_start_pos = QPoint()
        self._drag_start_transform = CanvasPreviewTransform()
        self._drag_axis_lock: str | None = None
        self._snap_guide_x: float | None = None
        self._snap_guide_y: float | None = None

    def _clear_drag_feedback(self, *, clear_axis_lock: bool = False) -> None:
        """ドラッグ中のガイド表示と軸固定状態を初期化する。"""
        # 表示中のスナップガイドを毎回クリアし、古い補助線を残さないようにする。
        self._snap_guide_x = None
        self._snap_guide_y = None
        # 呼び出し元が明示した場合だけ、Shift 軸固定も解除する。
        if clear_axis_lock:
            self._drag_axis_lock = None

    def sizeHint(self) -> QSize:
        """中央カラム向けの標準サイズを返す。"""
        # 通常利用時に十分な作業領域を確保できるサイズを既定値として返す。
        return QSize(760, 620)

    def set_source_image(self, image: QImage) -> None:
        """描画元画像を差し替える。"""
        # 受け取った画像のサイズと null 状態を、更新前のログとして残す。
        write_window_layout_debug_log(
            "canvas_preview_widget_set_source_image_begin",
            image_width=int(image.width()),
            image_height=int(image.height()),
            image_is_null=bool(image.isNull()),
        )
        # 画像差し替えと派生画像生成をまとめて保護し、失敗時に状態追跡しやすくする。
        try:
            # 呼び出し元の寿命に依存しないよう、入力画像は必ずコピーして保持する。
            self._image = QImage(image)
            # outside mask 用に、通常画像とは別でグレースケール版も保持する。
            self._image_grayscale = (
                self._image.convertToFormat(QImage.Format_Grayscale8)
                if not self._image.isNull()
                else QImage()
            )
            # 画像差し替え後は、古いドラッグ補助表示を残さない。
            self._clear_drag_feedback(clear_axis_lock=True)
            # 新しい画像で再描画するため、更新を要求する。
            self.update()
            # 適用後の実画像状態をログへ残す。
            write_window_layout_debug_log(
                "canvas_preview_widget_set_source_image_ok",
                image_width=int(self._image.width()),
                image_height=int(self._image.height()),
                image_is_null=bool(self._image.isNull()),
            )
        # 画像差し替え中の失敗は、入力画像情報つきでログへ残して再送出する。
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
        # 受け取ったサイズを更新前ログへ残し、状態遷移を追いやすくする。
        write_window_layout_debug_log(
            "canvas_preview_widget_set_canvas_pixels_begin",
            canvas_width=int(width),
            canvas_height=int(height),
        )
        # サイズ更新と再描画要求をまとめて保護し、失敗時の追跡を容易にする。
        try:
            # ゼロ以下が来ても描画計算が壊れないよう、最低 1px を保証する。
            self._canvas_width = max(1, int(width))
            self._canvas_height = max(1, int(height))
            # サイズ変更後は、古いスナップ補助や軸固定をいったん外す。
            self._clear_drag_feedback(clear_axis_lock=True)
            # 新しいキャンバス寸法で再描画する。
            self.update()
            # 実際に採用したサイズをログへ残す。
            write_window_layout_debug_log(
                "canvas_preview_widget_set_canvas_pixels_ok",
                canvas_width=int(self._canvas_width),
                canvas_height=int(self._canvas_height),
            )
        # サイズ更新失敗時は要求値ごと例外を記録して再送出する。
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
        # 反映前の transform をログへ残し、外部同期の前後差分を追いやすくする。
        write_window_layout_debug_log(
            "canvas_preview_widget_set_transform_state_begin",
            **_transform_fields(transform),
        )
        # 状態差し替えと再描画要求をまとめて保護する。
        try:
            self._transform = transform
            # 外部から状態同期されたときは、ドラッグ中以外の補助表示を消しておく。
            if not self._drag_active:
                self._clear_drag_feedback(clear_axis_lock=True)
            # 新しい transform で再描画する。
            self.update()
            # 適用後の transform をログへ残す。
            write_window_layout_debug_log(
                "canvas_preview_widget_set_transform_state_ok",
                **_transform_fields(self._transform),
            )
        # transform 反映失敗時は要求値と一緒に記録して再送出する。
        except Exception as exc:
            _log_widget_exception(
                "canvas_preview_widget_set_transform_state_fail",
                exc,
                **_transform_fields(transform),
            )
            raise

    def set_view_zoom(self, zoom: float) -> None:
        """プレビュー全体の表示倍率を更新する。"""
        # 変更要求前の倍率と要求値をログへ残し、UI 操作の流れを追いやすくする。
        write_window_layout_debug_log(
            "canvas_preview_widget_set_view_zoom_begin",
            requested_view_zoom=float(zoom),
            current_view_zoom=float(self._view_zoom),
        )
        # 倍率 clamp と再描画要求をまとめて保護する。
        try:
            # プレビュー倍率は定義済みの最小・最大範囲に必ず収める。
            self._view_zoom = max(self._VIEW_ZOOM_MIN, min(self._VIEW_ZOOM_MAX, float(zoom)))
            # 表示倍率変更を再描画へ反映する。
            self.update()
            # 実際に採用した倍率をログへ残す。
            write_window_layout_debug_log(
                "canvas_preview_widget_set_view_zoom_ok",
                requested_view_zoom=float(zoom),
                applied_view_zoom=float(self._view_zoom),
            )
        # 倍率更新失敗時は要求値を保持したまま例外を記録する。
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
        # 親ウィジェットではなく明示テーマを優先したい場合に備えて保持する。
        self._theme_override = theme
        # テーマ色変更を即座に描画へ反映する。
        self.update()

    def set_background_tone(self, tone: str) -> None:
        """キャンバスの確認用背景トーンを更新する。"""
        # 想定外の値が来ても UI が壊れないよう、文字列として正規化して扱う。
        tone_name = str(tone or CANVAS_PREVIEW_BACKGROUND_LIGHT)
        # 既知のトーン以外は安全側でライトへ寄せる。
        if tone_name not in {
            CANVAS_PREVIEW_BACKGROUND_LIGHT,
            CANVAS_PREVIEW_BACKGROUND_DARK,
        }:
            tone_name = CANVAS_PREVIEW_BACKGROUND_LIGHT
        # 値が変わらない場合は再描画を避ける。
        if tone_name == self._background_tone:
            return
        self._background_tone = tone_name
        # 背景トーン変更を再描画へ反映する。
        self.update()

    def preview_image(self) -> QImage:
        """現在のシミュレーション結果をキャンバス範囲だけ画像化する。"""
        # 保存や外部利用向けに、キャンバスサイズちょうどの透過画像を用意する。
        image = QImage(
            max(1, int(self._canvas_width)),
            max(1, int(self._canvas_height)),
            QImage.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.transparent)
        # 本番描画と同じ描画経路を流しつつ、背景チェッカーと outside mask は除外する。
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        canvas_rect = QRectF(0.0, 0.0, float(image.width()), float(image.height()))
        # キャンバス出力では実画像だけを得たいので、装飾を抑えて scene を描く。
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
        # ガイド線だけを別出力できるよう、透過背景の画像を新規に作る。
        image = QImage(
            max(1, int(self._canvas_width)),
            max(1, int(self._canvas_height)),
            QImage.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.transparent)
        # 中央ガイドと枠線だけを描く専用 painter を用意する。
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        theme = self._theme()
        # ガイド画像でも枠が分かるよう、アクセント色で外枠を描く。
        frame_pen = QPen(qcolor(theme.accent))
        frame_pen.setWidthF(self._CANVAS_BORDER_WIDTH)
        painter.setPen(frame_pen)
        painter.drawRect(QRectF(1.0, 1.0, image.width() - 2.0, image.height() - 2.0))
        canvas_rect = QRectF(0.0, 0.0, float(image.width()), float(image.height()))
        # 中央ガイドは本体描画と同じ helper を使ってそろえる。
        self._draw_center_guides(painter, canvas_rect, theme=theme)
        painter.end()
        return image

    def _theme(self):
        """現在テーマを返す。"""
        # 明示テーマがある場合は、親探索よりもそれを優先する。
        if self._theme_override is not None:
            return self._theme_override
        widget = self
        # 親ウィジェットをたどり、最初に見つかった `_ui_theme_name` を採用する。
        while widget is not None:
            theme_name = getattr(widget, "_ui_theme_name", None)
            if theme_name:
                return get_ui_theme(theme_name)
            widget = widget.parentWidget()
        # 親にテーマ情報が無い場合は既定テーマへフォールバックする。
        return get_ui_theme(None)

    def _viewport_rect(self) -> QRectF:
        """プレビュー表示全体のビューポート矩形を返す。"""
        # 外周 padding を差し引いた領域だけを、描画用 viewport として扱う。
        return QRectF(self.rect()).adjusted(
            self._OUTER_PADDING,
            self._OUTER_PADDING,
            -self._OUTER_PADDING,
            -self._OUTER_PADDING,
        )

    def _viewport_content_inset(self) -> float:
        """viewport 枠線と AA の内側だけへ scene を閉じ込める inset を返す。"""
        # 枠線幅とアンチエイリアスのにじみを見込んだ最小 inset を返す。
        return max(1.0, float(self._VIEWPORT_BORDER_WIDTH) * 0.5 + 1.0)

    def _viewport_content_rect(self, viewport_rect: QRectF) -> QRectF:
        """viewport 枠線の内側だけを scene 描画範囲として返す。"""
        # 枠線内側に閉じた描画領域へ縮め、外周に絵がにじまないようにする。
        inset = self._viewport_content_inset()
        content_rect = QRectF(viewport_rect).adjusted(inset, inset, -inset, -inset)
        return content_rect if not content_rect.isEmpty() else QRectF()

    def _viewport_rounded_path(self, rect: QRectF, radius: float) -> QPainterPath:
        """viewport 背景/clip 用の rounded path を返す。"""
        # 背景塗りと clip の両方で使えるよう、丸角 path を一度で組み立てる。
        path = QPainterPath()
        path.addRoundedRect(rect, max(0.0, float(radius)), max(0.0, float(radius)))
        return path

    def _fit_canvas_view_scale(self, viewport_rect: QRectF | None = None) -> float:
        """キャンバス全体を収める基準縮尺を返す。"""
        # 呼び出し側指定がなければ、通常の viewport 全体を基準にする。
        viewport = self._viewport_rect() if viewport_rect is None else QRectF(viewport_rect)
        # 無効な矩形では縮尺計算できないため、安全側で 1.0 を返す。
        if viewport.isEmpty():
            return 1.0
        # 横・縦のうち小さい方を採用し、キャンバス全体が必ず収まる縮尺にする。
        return min(
            float(viewport.width()) / float(max(1, self._canvas_width)),
            float(viewport.height()) / float(max(1, self._canvas_height)),
        )

    def _canvas_rect(self) -> QRectF:
        """widget 内で現在の表示倍率を反映したキャンバス矩形を返す。"""
        # まずは描画の基準になる viewport を取り出す。
        viewport = self._viewport_rect()
        # 表示領域が成立しない場合は、空矩形を返して描画を止める。
        if viewport.width() <= 0.0 or viewport.height() <= 0.0:
            return QRectF()
        # 実際の scene は content rect 内へ収めたいので、fit 基準も内側領域へ寄せる。
        fit_viewport = self._viewport_content_rect(viewport)
        # content rect が空なら、最後の保険として viewport 全体へ戻す。
        if fit_viewport.isEmpty():
            fit_viewport = viewport
        # fit 縮尺に preview zoom を掛けて、現在の描画サイズを決める。
        scale = self._fit_canvas_view_scale(fit_viewport) * float(self._view_zoom)
        draw_width = float(self._canvas_width) * scale
        draw_height = float(self._canvas_height) * scale
        # 位置は viewport 中央基準のまま保ち、サイズだけを反映する。
        return QRectF(
            viewport.center().x() - draw_width * 0.5,
            viewport.center().y() - draw_height * 0.5,
            draw_width,
            draw_height,
        )

    def _canvas_view_scale(self, canvas_rect: QRectF | None = None) -> float:
        """キャンバス px を view 座標へ写す縮尺を返す。"""
        # 呼び出し側指定がなければ、現在の canvas rect から縮尺を求める。
        rect = self._canvas_rect() if canvas_rect is None else QRectF(canvas_rect)
        # 無効な矩形では変換係数を求められないため 1.0 を返す。
        if rect.isEmpty():
            return 1.0
        return float(rect.width()) / float(max(1, self._canvas_width))

    def _image_transform_for_rect(self, canvas_rect: QRectF) -> QTransform:
        """指定キャンバス矩形上で画像描画に使う transform を返す。"""
        # キャンバス座標系に合わせた view 側縮尺を先に求める。
        view_scale = self._canvas_view_scale(canvas_rect)
        canvas_center = canvas_rect.center()
        transform = QTransform()
        # 位置移動・回転・画像スケールの順で transform を積み上げる。
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
        # 画像が無い場合は空ポリゴンを返して、以降の path 計算を止める。
        if self._image.isNull():
            return QPolygonF()
        view_scale = self._canvas_view_scale(canvas_rect)
        center = canvas_rect.center()
        # 数学 helper から得た各頂点を view 座標へ写して polygon を組み立てる。
        points = image_polygon_points(
            self._image.width(),
            self._image.height(),
            self._transform,
        )
        polygon = QPolygonF()
        # 各頂点をキャンバス中心基準で view 座標へ変換する。
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
        # 背景トーンが dark のときだけ、暗色系のチェック柄へ切り替える。
        if self._background_tone == CANVAS_PREVIEW_BACKGROUND_DARK:
            return qcolor("#202020"), qcolor("#111111")
        return qcolor("#FFFFFF"), qcolor("#E9E9E9")

    def _outer_background_color(self, *, theme):
        """viewport 外側で使うテーマ由来の背景色を返す。"""
        # 外周は通常ウィンドウ背景と同じ色でなじませる。
        return qcolor(theme.window_bg)

    def _viewport_fill_color(self, *, theme):
        """canvas 周囲の viewport ベース色を返す。"""
        # viewport 内側は画像確認向けの背景色を使う。
        return qcolor(theme.image_bg)

    def _draw_checker_background(self, painter: QPainter, canvas_rect: QRectF, *, theme) -> None:
        """余白確認用のチェック柄背景を描く。"""
        del theme
        # キャンバス枠線に重ならないよう、内側へ少し inset した領域だけへ描く。
        inset = max(float(self._CANVAS_BORDER_HALO_WIDTH), float(self._CANVAS_BORDER_WIDTH)) * 0.5
        checker_clip_rect = QRectF(canvas_rect).adjusted(inset, inset, -inset, -inset)
        # 有効な描画領域が無い場合は何も描かない。
        if checker_clip_rect.isEmpty():
            return
        light, dark = self._checker_colors()
        # チェッカーは crisp に見せたいので、AA を切って矩形敷き詰めで描く。
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
        # 縦方向にセルを走査して、行ごとに交互色の起点をずらす。
        while y_pos < bottom:
            x_pos = left
            col_index = row_index % 2
            # 横方向にもセルを敷き詰めて、チェック柄を完成させる。
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
        # clip rect が無い場合は、塗り戻し領域を定義できないので何もしない。
        if clip_rect is None or QRectF(clip_rect).isEmpty():
            return
        # 枠線内側だけをキャンバス本体とみなし、外側だけを viewport 色で戻す。
        inset = max(float(self._CANVAS_BORDER_HALO_WIDTH), float(self._CANVAS_BORDER_WIDTH)) * 0.5
        visible_path = QPainterPath()
        visible_path.addRect(QRectF(clip_rect))
        canvas_inner_path = QPainterPath()
        canvas_inner_path.addRect(QRectF(canvas_rect).adjusted(inset, inset, -inset, -inset))
        outside_path = visible_path.subtracted(canvas_inner_path)
        # はみ出しが無い場合は塗り戻し不要なので終了する。
        if outside_path.isEmpty():
            return
        # viewport 内側色で outside 領域を塗り戻し、にじみを打ち消す。
        painter.save()
        painter.fillPath(outside_path, self._viewport_fill_color(theme=theme))
        painter.restore()

    def _draw_center_guides(self, painter: QPainter, canvas_rect: QRectF, *, theme) -> None:
        """中央十字ガイドを描画する。"""
        # 中央ガイドはテーマの accent を半透明で使い、画像の上でも見やすくする。
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
        # viewport 背景が暗いときは白、明るいときは黒を返してコントラストを確保する。
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
        # 画像ポリゴンが無い場合は outside path も成立しない。
        if image_polygon.isEmpty():
            return QPainterPath()
        # 実際に crop が発生していない場合は、mask 用 path を空にして処理を省く。
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
        # まずは画像ポリゴン全体を path 化し、outside 差集合計算の土台にする。
        image_path = QPainterPath()
        image_path.setFillRule(Qt.WindingFill)
        image_path.addPolygon(image_polygon)
        image_path.closeSubpath()
        visible_image_path = QPainterPath(image_path)
        # 可視領域が指定されている場合だけ、viewport 内へ絞った path で outside を求める。
        if clip_rect is not None:
            visible_path = QPainterPath()
            visible_path.setFillRule(Qt.WindingFill)
            visible_path.addRect(QRectF(clip_rect))
            visible_image_path = visible_image_path.intersected(visible_path)
            if visible_image_path.isEmpty():
                return QPainterPath()
        # 小数座標の誤差で canvas 内側が outside 扱いされないよう、mask 側だけ微小に広げる。
        canvas_mask_rect = QRectF(canvas_rect).adjusted(
            -self._CROP_MASK_EPSILON,
            -self._CROP_MASK_EPSILON,
            self._CROP_MASK_EPSILON,
            self._CROP_MASK_EPSILON,
        )
        canvas_path = QPainterPath()
        canvas_path.setFillRule(Qt.WindingFill)
        canvas_path.addRect(canvas_mask_rect)
        # 可視画像 path から canvas 領域を差し引き、outside だけを返す。
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
        # 画像が無い場合は描画せずに終了する。
        if image.isNull():
            return
        # 指定 canvas rect に対する画像 transform を一度だけ計算して使い回す。
        image_transform = self._image_transform_for_rect(canvas_rect)
        image_clip_path = QPainterPath()
        # clip rect がある場合だけ、view 座標の矩形を画像座標 clip に変換する。
        if clip_rect is not None:
            image_clip_path = self._image_clip_path_for_view_rect(
                image_transform,
                QRectF(clip_rect),
                image_size=image.size(),
            )
            if image_clip_path.isEmpty():
                return
        # 画像描画中だけ opacity / transform / clip を局所適用する。
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
        # 画像または clip path が空なら描画対象が無いので終了する。
        if image.isNull() or image_clip_path.isEmpty():
            return
        # 既に画像座標 clip ができている前提で、そのまま transform 描画へ流す。
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
        # 空矩形や無効画像サイズでは clip path を作れない。
        if view_rect.isEmpty() or image_size.isEmpty():
            return QPainterPath()
        # 画像 transform が逆変換できない場合は安全に空を返す。
        inverted, invertible = image_transform.inverted()
        if not invertible:
            return QPainterPath()
        # まず view 矩形を path 化し、逆変換後に画像境界へ切り詰める。
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
        # 空 path や無効画像サイズでは clip path を作れない。
        if view_path.isEmpty() or image_size.isEmpty():
            return QPainterPath()
        # 画像 transform が逆変換できない場合は安全に空を返す。
        inverted, invertible = image_transform.inverted()
        if not invertible:
            return QPainterPath()
        # 任意 path を画像座標へ戻し、画像境界だけに切り詰める。
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
        # 画像が無い場合は通常描画も不要。
        if self._image.isNull():
            return
        # 最終描画範囲は実 canvas rect を基準に組み立てる。
        view_path = QPainterPath()
        view_path.setFillRule(Qt.WindingFill)
        view_path.addRect(QRectF(canvas_rect))
        # viewport clip がある場合だけ、canvas 内表示範囲をさらに絞る。
        if clip_rect is not None:
            clip_path = QPainterPath()
            clip_path.setFillRule(Qt.WindingFill)
            clip_path.addRect(QRectF(clip_rect))
            view_path = view_path.intersected(clip_path)
        if view_path.isEmpty():
            return
        # 通常描画は実 canvas 内に限定した画像座標 clip path を使う。
        image_clip_path = self._image_clip_path_for_view_path(
            self._image_transform_for_rect(canvas_rect),
            view_path,
            image_size=self._image.size(),
        )
        if image_clip_path.isEmpty():
            return
        # clip 済みの画像 path を通常色で描き、outside mask の上から戻す。
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
        # outside mask は可視領域内に限定した crop path から作る。
        cropped_path = self._cropped_image_path(
            image_polygon,
            canvas_rect,
            clip_rect=clip_rect,
        )
        if cropped_path.isEmpty():
            return cropped_path
        # グレースケール画像がある場合だけ、outside 部分を muted 表示に差し替える。
        if not self._image_grayscale.isNull():
            muted_path = QPainterPath(cropped_path)
            # viewport clip がある場合は、muted 表示も見えている領域だけへ絞る。
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
        # muted 画像の上に、さらに半透明 tint を重ねて outside を識別しやすくする。
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
        # outside path が無い場合は輪郭線も不要。
        if cropped_path.isEmpty():
            return
        # 輪郭線の halo と本線を重ね、背景に埋もれないように描く。
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
        # まず halo を描いて、どの背景でも枠線が埋もれないようにする。
        halo_pen = QPen(self._contrast_outline_color(theme=theme, alpha=96))
        halo_pen.setWidthF(self._CANVAS_BORDER_HALO_WIDTH)
        halo_pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(halo_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(canvas_rect)

        # その上から accent 色の本線を重ね、キャンバス境界を明示する。
        border_pen = QPen(qcolor(theme.accent, 220))
        border_pen.setWidthF(self._CANVAS_BORDER_WIDTH)
        border_pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(border_pen)
        painter.drawRect(canvas_rect)

    def _draw_snap_guides(self, painter: QPainter, canvas_rect: QRectF, *, theme) -> None:
        """スナップ中の辺/中心ガイドを軽く重ねる。"""
        # スナップ対象が無いときはガイド描画を省く。
        if self._snap_guide_x is None and self._snap_guide_y is None:
            return
        view_scale = self._canvas_view_scale(canvas_rect)
        # ガイドは canvas 内だけに限定して描き、外へ漏らさない。
        painter.save()
        painter.setClipRect(canvas_rect)
        # X ガイドがある場合は、中心線か端ガイドかで色を分けて描く。
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
        # Y ガイドも同様に、中心線か端ガイドかで色を分けて描く。
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
        # 背景チェッカーが必要な描画モードでは、最初に土台を描く。
        if include_checker:
            self._draw_checker_background(painter, canvas_rect, theme=theme)
            self._clear_checker_outside_canvas(
                painter,
                canvas_rect,
                theme=theme,
                clip_rect=clip_rect,
            )
        cropped_path = QPainterPath()
        # 画像がある場合だけ、通常画像と outside mask を組み合わせて描画する。
        if not self._image.isNull():
            # outside mask を使うモードでは、muted -> normal の順で責務を分けて描く。
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
                # 単純プレビューでは outside mask を使わず、通常画像だけを描く。
                self._draw_transformed_image(
                    painter,
                    self._image,
                    canvas_rect,
                    clip_rect=clip_rect,
                )
        else:
            # 画像が無い場合は、中央にエラーメッセージだけを表示する。
            painter.save()
            if clip_rect is not None:
                painter.setClipRect(clip_rect)
            painter.setPen(qcolor(theme.text_muted))
            painter.drawText(canvas_rect, Qt.AlignCenter, "画像を取得できませんでした")
            painter.restore()

        # 画像の有無に関係なく、最後にキャンバス境界を重ねて見失いにくくする。
        self._draw_canvas_boundary(painter, canvas_rect, theme=theme)
        if show_outside_mask:
            # outside mask を使うモードでは、crop 輪郭も上から重ねる。
            self._draw_crop_outline(
                painter,
                cropped_path,
                theme=theme,
                clip_rect=clip_rect,
            )

        # 仕上げに中央ガイドとスナップガイドを重ねて操作補助を見せる。
        self._draw_center_guides(painter, canvas_rect, theme=theme)
        self._draw_snap_guides(painter, canvas_rect, theme=theme)

    def paintEvent(self, event) -> None:
        """キャンバス、画像、余白、はみ出し、ガイドをまとめて描画する。"""
        del event
        # 毎回の paintEvent で使う painter とテーマを先に確定する。
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        theme = self._theme()
        painter.fillRect(self.rect(), self._outer_background_color(theme=theme))

        # まず viewport 全体を決め、無効なら描画を打ち切る。
        viewport_rect = self._viewport_rect()
        if viewport_rect.isEmpty():
            painter.end()
            return

        # viewport 背景は rounded rect で先に塗り、内部 scene の土台にする。
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._viewport_fill_color(theme=theme))
        painter.drawRoundedRect(viewport_rect, self._VIEWPORT_RADIUS, self._VIEWPORT_RADIUS)

        # 現在倍率と content rect 基準を反映した canvas rect を求める。
        canvas_rect = self._canvas_rect()
        if canvas_rect.isEmpty():
            painter.end()
            return

        # scene 本体は viewport 枠線の内側だけへクリップする。
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
        # scene 描画中だけ rounded clip を適用し、外周へにじまないようにする。
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
        # 最後に viewport 枠線を上から重ねて、境界を明確にする。
        viewport_pen = QPen(qcolor(theme.border))
        viewport_pen.setWidthF(self._VIEWPORT_BORDER_WIDTH)
        painter.setPen(viewport_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(viewport_rect, self._VIEWPORT_RADIUS, self._VIEWPORT_RADIUS)
        painter.end()

    def _apply_drag_transform(self, transform: CanvasPreviewTransform) -> None:
        """ドラッグ操作で確定した transform を widget/UI へ反映する。"""
        # 内部状態を更新したうえで、外部同期用 signal と再描画を順に流す。
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
        # view 座標の移動量を canvas 系の offset へ戻すため、表示縮尺を使う。
        view_scale = max(0.0001, self._canvas_view_scale())
        total_delta = point - self._drag_start_pos
        delta_x = float(total_delta.x()) / view_scale
        delta_y = float(total_delta.y()) / view_scale
        # Shift 中は優勢軸だけを残し、水平または垂直ドラッグに固定する。
        if modifiers & Qt.ShiftModifier:
            if self._drag_axis_lock is None:
                self._drag_axis_lock = dominant_drag_axis(delta_x, delta_y)
            if self._drag_axis_lock == "x":
                delta_y = 0.0
            elif self._drag_axis_lock == "y":
                delta_x = 0.0
        else:
            # Shift を離したら軸固定を解除し、自由移動へ戻す。
            self._drag_axis_lock = None
        # 基本の移動結果を、ドラッグ開始時 transform に対して加算する。
        transform = CanvasPreviewTransform(
            offset_x=float(self._drag_start_transform.offset_x) + delta_x,
            offset_y=float(self._drag_start_transform.offset_y) + delta_y,
            scale=float(self._drag_start_transform.scale),
            rotation_deg=float(self._drag_start_transform.rotation_deg),
        )
        # Ctrl/Shift 中や画像未設定時はスナップせず、そのままの移動量を採用する。
        if modifiers & (Qt.ControlModifier | Qt.ShiftModifier) or self._image.isNull():
            self._snap_guide_x = None
            self._snap_guide_y = None
            return transform
        # 通常ドラッグ時だけ、キャンバス端と中心へのスナップ候補を計算する。
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
        # 左ボタン・画像あり・viewport 内開始のときだけ、独自ドラッグへ入る。
        if (
            event.button() == Qt.LeftButton
            and not self._image.isNull()
            and self._viewport_rect().contains(event.position())
        ):
            # 開始位置と開始時 transform を保存し、以降の差分計算基準にする。
            self._drag_active = True
            self._drag_start_pos = event.position().toPoint()
            self._drag_start_transform = self._transform
            # ガイド表示を初期化し、ドラッグ中カーソルへ切り替える。
            self._clear_drag_feedback(clear_axis_lock=True)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        # 独自ドラッグ条件に入らない入力は既定処理へ委ねる。
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """ドラッグ移動を中心基準 offset に反映する。"""
        # ドラッグ中でない move は既定処理へ戻し、余計な移動を防ぐ。
        if not self._drag_active:
            super().mouseMoveEvent(event)
            return
        # 現在ポインタ位置から新しい transform を算出して反映する。
        transform = self._drag_transform_from_pointer(
            event.position().toPoint(),
            event.modifiers(),
        )
        # 計算済み transform を widget と外部同期へ適用する。
        self._apply_drag_transform(transform)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        """ドラッグ終了時にカーソルを戻す。"""
        # 左ドラッグの終了時だけ、一時状態を片付けて通常表示へ戻す。
        if event.button() == Qt.LeftButton and self._drag_active:
            self._drag_active = False
            self._clear_drag_feedback(clear_axis_lock=True)
            self.unsetCursor()
            # ガイドやカーソル解除を見た目へ反映するため、再描画を要求する。
            self.update()
            event.accept()
            return
        # 独自ドラッグに関係しない release は既定処理へ委ねる。
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        """ホイール単体は表示倍率、Ctrl+ホイールは画像 scale を調整する。"""
        delta = event.angleDelta().y()
        # ホイール差分が取れない場合は独自処理せず、既定ハンドラへ渡す。
        if delta == 0:
            super().wheelEvent(event)
            return
        factor = pow(self._WHEEL_FACTOR, float(delta) / 120.0)
        # Ctrl+ホイール時だけ、画像そのものの scale を既存範囲内で更新する。
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
            # 画像 scale の変更は transformChanged で外部コントロールへ同期する。
            self.transformChanged.emit(
                float(transform.offset_x),
                float(transform.offset_y),
                float(transform.scale),
                float(transform.rotation_deg),
            )
            self.update()
            event.accept()
            return
        # Ctrl 無しでは preview 表示倍率だけを clamp 付きで更新する。
        self._view_zoom = max(
            self._VIEW_ZOOM_MIN,
            min(self._VIEW_ZOOM_MAX, float(self._view_zoom) * factor),
        )
        # 表示倍率の変更を通知してから再描画し、UI 表示を揃える。
        self.viewZoomChanged.emit(float(self._view_zoom))
        self.update()
        event.accept()
