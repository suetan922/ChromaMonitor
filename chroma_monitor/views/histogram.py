"""ヒストグラム表示ビュー。"""

import math

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QStackedLayout, QWidget

from ..util import constants as C
from ..util.value_utils import safe_choice

_R_COLOR = QColor(228, 84, 84)
_G_COLOR = QColor(88, 176, 96)
_B_COLOR = QColor(88, 126, 236)
_HIST_MAX_TEXT_MIN_WIDTH = 190
_HIST_MAX_TEXT_MIN_HEIGHT = 120
_RGB_OVERLAY_PLOT_BG = QColor(26, 28, 32)
_RGB_OVERLAY_GUIDE = QColor(92, 98, 108, 132)
_RGB_OVERLAY_R_FILL = QColor(236, 88, 88, 86)
_RGB_OVERLAY_G_FILL = QColor(96, 182, 104, 86)
_RGB_OVERLAY_B_FILL = QColor(96, 134, 244, 86)
_RGB_OVERLAY_RGB_OVERLAP_FILL = QColor(255, 255, 255, 122)
_RGB_OVERLAY_TEXT_MAIN = QColor(238, 241, 246)
_RGB_OVERLAY_MAX_BADGE_BG = QColor(12, 14, 18, 176)


def _fit_hist_size(hist: np.ndarray, size: int) -> np.ndarray:
    """ヒストグラム配列を指定ビン数へ切り詰め/ゼロ埋めする。"""
    arr = np.asarray(hist, dtype=np.int64).reshape(-1)
    if arr.size == size:
        return arr
    fixed = np.zeros(size, dtype=np.int64)
    n = min(size, arr.size)
    if n > 0:
        fixed[:n] = arr[:n]
    return fixed


def _draw_plot_guides(painter: QPainter, plot: QRect) -> None:
    """ヒストグラム背景の基準ガイド線を描画する。"""
    painter.setPen(QColor(225, 225, 225))
    # 目盛りガイド線（横方向）を薄く引く。
    for i in range(1, 5):
        y = plot.top() + int(plot.height() * i / 5)
        painter.drawLine(plot.left(), y, plot.right(), y)
    painter.setPen(QColor(180, 180, 180))
    painter.drawLine(plot.left(), plot.top(), plot.left(), plot.bottom())
    painter.drawLine(plot.left(), plot.bottom(), plot.right(), plot.bottom())


class ChannelHistogram(QWidget):
    """単一チャネル用ヒストグラム表示ウィジェット。"""

    def __init__(self, title: str, bins: int, max_value: int, color: QColor, bucket: int = 4):
        """チャネル名・ビン数・色を指定して初期化する。"""
        super().__init__()
        # ドックの縦積み時に上側でリサイズが詰まらないよう、最小高さは持たせない。
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._title = title
        self._bins = bins
        self._max_value = max_value
        self._color = color
        self._bucket = max(1, bucket)
        self._hist = np.zeros(bins, dtype=np.int64)
        self._idx = np.arange(bins, dtype=np.float64)
        self._mean = 0.0
        self._std = 0.0
        self._total = 0
        self._shared_max_y: int | None = None

    def _bucketed_hist(self) -> np.ndarray:
        """描画用にバケット集約したヒストグラムを返す。"""
        bins = self._hist
        bucket = max(1, int(self._bucket))
        if self._bins % bucket == 0:
            return bins.reshape(-1, bucket).sum(axis=1)
        return bins

    def bucketed_max(self) -> int:
        """バケット化後ヒストグラムの最大値を返す。"""
        if self._hist.size <= 0:
            return 0
        return int(self._bucketed_hist().max())

    def set_shared_max_y(self, max_y: int | None):
        """共有Y上限を設定する。`None` で個別スケールへ戻す。"""
        next_value = None if max_y is None else max(1, int(max_y))
        if self._shared_max_y == next_value:
            return
        self._shared_max_y = next_value
        self.update()

    def _update_stats(self):
        """平均・標準偏差など表示用統計値を再計算する。"""
        total = int(self._hist.sum())
        if total <= 0:
            self._total = 0
            self._mean = 0.0
            self._std = 0.0
            return
        self._total = total
        mean = float((self._idx * self._hist).sum() / total)
        var = float((((self._idx - mean) ** 2) * self._hist).sum() / total)
        self._mean = mean
        self._std = math.sqrt(max(0.0, var))

    def update_from_values(self, values: np.ndarray):
        """入力値配列からヒストグラムを再集計して更新する。"""
        # 入力配列を1次元化してヒストグラムへ集計する。
        flat = np.ravel(values)
        if flat.dtype != np.uint8 or self._max_value < 255 or self._bins < 256:
            # 0..255範囲外の可能性がある場合のみクリップ処理を行う。
            flat = np.asarray(flat, dtype=np.int32)
            np.clip(flat, 0, self._max_value, out=flat)
        hist = np.bincount(flat, minlength=self._bins)[: self._bins]
        self.update_from_hist(hist)

    def update_from_hist(self, hist: np.ndarray):
        """集計済みヒストグラムを反映して表示更新する。"""
        # 既に集計済みヒストグラムを直接反映する。
        arr = _fit_hist_size(hist, self._bins)
        if self._hist.shape == arr.shape and np.array_equal(self._hist, arr):
            return
        self._hist = arr
        self._update_stats()
        self.update()

    def paintEvent(self, _):
        """チャネルヒストグラム本体と統計テキストを描画する。"""
        # 描画は毎回ヒストグラム配列から再生成する。
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.fillRect(self.rect(), QColor(255, 255, 255, 255))

            title_rect = self.rect().adjusted(10, 6, -10, -6)
            p.setPen(QColor(30, 30, 30))
            p.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop, self._title)

            if self._total == 0:
                p.setPen(QColor(120, 120, 120))
                p.drawText(self.rect(), Qt.AlignCenter, "データなし")
                return

            plot = self.rect().adjusted(12, 26, -12, -44)
            if plot.width() <= 10 or plot.height() <= 10:
                p.setPen(QColor(30, 30, 30))
                p.drawText(
                    self.rect().adjusted(10, 24, -10, -8),
                    Qt.AlignLeft | Qt.AlignBottom,
                    f"平均 {self._mean:.1f} / 標準偏差 {self._std:.1f}",
                )
                return

            _draw_plot_guides(p, plot)

            # ビン数が多い場合は指定バケット幅でまとめて可読性を上げる。
            bins = self._bucketed_hist()
            auto_max_y = max(1, int(bins.max()))
            if self._shared_max_y is not None:
                max_y = max(auto_max_y, int(self._shared_max_y))
            else:
                max_y = auto_max_y
            # 表示ラベルの max は、Y軸スケールではなく
            # そのチャネル実データが取り得ている最大頻度を示す。
            data_max = max(1, int(self._hist.max()))
            n_bins = len(bins)
            bin_w = plot.width() / float(n_bins)
            plot_h = max(1, plot.height() - 1)
            fill_color = QColor(self._color)
            fill_color.setAlpha(200)
            bar_w = max(1, int(bin_w) - 1)
            for i, val in enumerate(bins):
                h = min(plot_h, int(plot_h * (val / max_y)))
                x = plot.left() + int(i * bin_w)
                y = plot.bottom() - h
                p.fillRect(QRect(x, y, bar_w, h), fill_color)

            p.setPen(QColor(30, 30, 30))
            axis_rect = QRect(plot.left(), plot.bottom() + 4, plot.width(), 14)
            p.drawText(axis_rect, Qt.AlignLeft | Qt.AlignVCenter, "0")
            p.drawText(axis_rect, Qt.AlignRight | Qt.AlignVCenter, str(self._max_value))

            stats = f"平均 {self._mean:.1f} / 標準偏差 {self._std:.1f}"
            if (
                plot.width() >= _HIST_MAX_TEXT_MIN_WIDTH
                and self.height() >= _HIST_MAX_TEXT_MIN_HEIGHT
            ):
                stats = f"max {data_max} / {stats}"
            p.drawText(
                QRect(plot.left(), plot.bottom() + 20, plot.width(), 18),
                Qt.AlignCenter | Qt.AlignVCenter,
                stats,
            )
        finally:
            p.end()


class RgbOverlayHistogram(QWidget):
    """RGB重ね表示ヒストグラムウィジェット。"""

    def __init__(self):
        """重ね表示用ヒストグラム状態を初期化する。"""
        super().__init__()
        # ドックの縦積み時に上側でリサイズが詰まらないよう、最小高さは持たせない。
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._hist_r = np.zeros(256, dtype=np.int64)
        self._hist_g = np.zeros(256, dtype=np.int64)
        self._hist_b = np.zeros(256, dtype=np.int64)
        self._total = 0
        self._bucket = 2

    def _bucketed(self, hist: np.ndarray) -> np.ndarray:
        """描画負荷を抑えるためバケット集約した配列を返す。"""
        bucket = max(1, int(self._bucket))
        if hist.size % bucket != 0:
            return hist
        return hist.reshape(-1, bucket).sum(axis=1)

    def update_from_histograms(self, hist_r: np.ndarray, hist_g: np.ndarray, hist_b: np.ndarray):
        """RGB各ヒストグラムを反映して表示を更新する。"""
        next_r = _fit_hist_size(hist_r, 256)
        next_g = _fit_hist_size(hist_g, 256)
        next_b = _fit_hist_size(hist_b, 256)
        if (
            np.array_equal(self._hist_r, next_r)
            and np.array_equal(self._hist_g, next_g)
            and np.array_equal(self._hist_b, next_b)
        ):
            return
        self._hist_r = next_r
        self._hist_g = next_g
        self._hist_b = next_b
        self._total = int(max(self._hist_r.sum(), self._hist_g.sum(), self._hist_b.sum()))
        self.update()

    def paintEvent(self, _):
        """重ね表示ヒストグラムを連続パスで描画する。"""
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.fillRect(self.rect(), QColor(255, 255, 255, 255))
            title_rect = self.rect().adjusted(10, 6, -10, -6)
            p.setPen(QColor(30, 30, 30))
            p.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop, "RGB")

            if self._total <= 0:
                p.setPen(QColor(120, 120, 120))
                p.drawText(self.rect(), Qt.AlignCenter, "データなし")
                return

            plot = self.rect().adjusted(12, 26, -12, -24)
            if plot.width() <= 10 or plot.height() <= 10:
                return

            # 重ね表示の重複を視認しやすくするため、プロット領域は暗色背景にする。
            p.fillRect(plot, _RGB_OVERLAY_PLOT_BG)
            p.setPen(_RGB_OVERLAY_GUIDE)
            for i in range(1, 5):
                y = plot.top() + int(plot.height() * i / 5)
                p.drawLine(plot.left(), y, plot.right(), y)
            p.setPen(QColor(128, 136, 149))
            p.drawRect(plot)

            h_r = self._bucketed(self._hist_r)
            h_g = self._bucketed(self._hist_g)
            h_b = self._bucketed(self._hist_b)
            max_y = max(1, int(h_r.max()), int(h_g.max()), int(h_b.max()))
            n_bins = int(h_r.size)
            if n_bins <= 1:
                return
            x_step = plot.width() / float(n_bins - 1)
            plot_h = max(1, plot.height() - 1)
            # 縦筋アーティファクトを避けるため、ビン矩形ではなく連続パスで塗る。
            x_vals = np.arange(n_bins, dtype=np.float32) * float(x_step) + float(plot.left())
            y_r = plot.bottom() - np.clip((h_r.astype(np.float32) / float(max_y)) * plot_h, 0, plot_h)
            y_g = plot.bottom() - np.clip((h_g.astype(np.float32) / float(max_y)) * plot_h, 0, plot_h)
            y_b = plot.bottom() - np.clip((h_b.astype(np.float32) / float(max_y)) * plot_h, 0, plot_h)
            h_overlap = np.minimum(np.minimum(h_r, h_g), h_b).astype(np.float32)
            y_overlap = plot.bottom() - np.clip((h_overlap / float(max_y)) * plot_h, 0, plot_h)

            def _build_area_path(y_vals: np.ndarray) -> QPainterPath:
                path = QPainterPath()
                path.moveTo(float(plot.left()), float(plot.bottom()))
                path.lineTo(float(x_vals[0]), float(y_vals[0]))
                for i in range(1, n_bins):
                    path.lineTo(float(x_vals[i]), float(y_vals[i]))
                path.lineTo(float(plot.right()), float(plot.bottom()))
                path.closeSubpath()
                return path

            p.setPen(Qt.NoPen)
            p.setBrush(_RGB_OVERLAY_R_FILL)
            p.drawPath(_build_area_path(y_r))
            p.setBrush(_RGB_OVERLAY_G_FILL)
            p.drawPath(_build_area_path(y_g))
            p.setBrush(_RGB_OVERLAY_B_FILL)
            p.drawPath(_build_area_path(y_b))
            p.setBrush(_RGB_OVERLAY_RGB_OVERLAP_FILL)
            p.drawPath(_build_area_path(y_overlap))

            def _draw_curve(y_vals: np.ndarray, color: QColor):
                pen = QPen(color, 1.6)
                p.setPen(pen)
                prev_x = int(round(float(x_vals[0])))
                prev_y = int(round(float(y_vals[0])))
                for i in range(1, n_bins):
                    x = int(round(float(x_vals[i])))
                    y = int(round(float(y_vals[i])))
                    p.drawLine(prev_x, prev_y, x, y)
                    prev_x, prev_y = x, y

            color_r = QColor(_R_COLOR)
            color_r.setAlpha(210)
            color_g = QColor(_G_COLOR)
            color_g.setAlpha(210)
            color_b = QColor(_B_COLOR)
            color_b.setAlpha(210)
            _draw_curve(y_r, color_r)
            _draw_curve(y_g, color_g)
            _draw_curve(y_b, color_b)

            axis_rect = QRect(plot.left(), plot.bottom() + 4, plot.width(), 14)
            p.setPen(QColor(30, 30, 30))
            p.drawText(axis_rect, Qt.AlignLeft | Qt.AlignVCenter, "0")
            p.drawText(axis_rect, Qt.AlignRight | Qt.AlignVCenter, "255")

            badge_w = max(84, int(plot.width() * 0.18))
            badge_h = 16
            badge = QRect(plot.right() - badge_w + 1, plot.top() + 1, badge_w, badge_h)
            p.fillRect(badge, _RGB_OVERLAY_MAX_BADGE_BG)
            p.setPen(_RGB_OVERLAY_TEXT_MAIN)
            p.drawText(badge.adjusted(6, 0, -6, 0), Qt.AlignCenter, f"max {max_y}")
        finally:
            p.end()


class RgbHistogramWidget(QWidget):
    """RGBヒストグラムの表示モード切替コンテナ。"""

    def __init__(self):
        """横並び/重ね表示の両ビューを構築して初期化する。"""
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._display_mode = C.DEFAULT_RGB_HIST_MODE
        self._hist_r = ChannelHistogram("赤", 256, 255, QColor(_R_COLOR), bucket=2)
        self._hist_g = ChannelHistogram("緑", 256, 255, QColor(_G_COLOR), bucket=2)
        self._hist_b = ChannelHistogram("青", 256, 255, QColor(_B_COLOR), bucket=2)
        self._overlay = RgbOverlayHistogram()

        side_widget = QWidget()
        side_layout = QHBoxLayout(side_widget)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)
        side_layout.addWidget(self._hist_r, 1)
        side_layout.addWidget(self._hist_g, 1)
        side_layout.addWidget(self._hist_b, 1)

        root = QStackedLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(side_widget)
        root.addWidget(self._overlay)
        self._stack = root
        self.set_display_mode(C.DEFAULT_RGB_HIST_MODE)

    def set_display_mode(self, mode: str):
        """表示モードを切り替える。"""
        normalized = safe_choice(mode, C.RGB_HIST_MODES, C.DEFAULT_RGB_HIST_MODE)
        self._display_mode = normalized
        self._stack.setCurrentIndex(1 if normalized == C.RGB_HIST_MODE_OVERLAY else 0)

    def update_from_bgr(self, bgr: np.ndarray):
        """入力BGRフレームからRGBヒストグラムを更新する。"""
        if bgr is None or bgr.size == 0 or bgr.ndim < 3 or bgr.shape[2] < 3:
            return
        # ライブキャプチャは uint8 が大半なので、クリップと型変換を省いて集計コストを下げる。
        if bgr.dtype == np.uint8:
            b = np.ravel(bgr[:, :, 0])
            g = np.ravel(bgr[:, :, 1])
            r = np.ravel(bgr[:, :, 2])
        else:
            flat = np.asarray(bgr[:, :, :3], dtype=np.int32).reshape(-1, 3)
            b = np.clip(flat[:, 0], 0, 255)
            g = np.clip(flat[:, 1], 0, 255)
            r = np.clip(flat[:, 2], 0, 255)
        hist_b = np.bincount(b, minlength=256)[:256]
        hist_g = np.bincount(g, minlength=256)[:256]
        hist_r = np.bincount(r, minlength=256)[:256]

        self._hist_r.update_from_hist(hist_r)
        self._hist_g.update_from_hist(hist_g)
        self._hist_b.update_from_hist(hist_b)
        # 横並び3チャネルはY軸スケールを揃えて相対比較しやすくする。
        shared_max_y = max(
            int(self._hist_r.bucketed_max()),
            int(self._hist_g.bucketed_max()),
            int(self._hist_b.bucketed_max()),
        )
        for view in (self._hist_r, self._hist_g, self._hist_b):
            view.set_shared_max_y(shared_max_y if shared_max_y > 0 else None)
        self._overlay.update_from_histograms(hist_r, hist_g, hist_b)
