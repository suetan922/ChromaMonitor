"""HSV channel histogram widget."""

import math

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QStackedLayout, QWidget

from ..util import constants as C


def _fit_hist_size(hist: np.ndarray, size: int) -> np.ndarray:
    arr = np.asarray(hist, dtype=np.int64).reshape(-1)
    if arr.size == size:
        return arr
    fixed = np.zeros(size, dtype=np.int64)
    n = min(size, arr.size)
    if n > 0:
        fixed[:n] = arr[:n]
    return fixed


def _draw_plot_guides(painter: QPainter, plot: QRect) -> None:
    painter.setPen(QColor(225, 225, 225))
    # 目盛りガイド線（横方向）を薄く引く。
    for i in range(1, 5):
        y = plot.top() + int(plot.height() * i / 5)
        painter.drawLine(plot.left(), y, plot.right(), y)
    painter.setPen(QColor(180, 180, 180))
    painter.drawLine(plot.left(), plot.top(), plot.left(), plot.bottom())
    painter.drawLine(plot.left(), plot.bottom(), plot.right(), plot.bottom())


class ChannelHistogram(QWidget):
    def __init__(self, title: str, bins: int, max_value: int, color: QColor, bucket: int = 4):
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
        bins = self._hist
        bucket = max(1, int(self._bucket))
        if self._bins % bucket == 0:
            return bins.reshape(-1, bucket).sum(axis=1)
        return bins

    def bucketed_max(self) -> int:
        if self._hist.size <= 0:
            return 0
        return int(self._bucketed_hist().max())

    def set_shared_max_y(self, max_y: int | None):
        next_value = None if max_y is None else max(1, int(max_y))
        if self._shared_max_y == next_value:
            return
        self._shared_max_y = next_value
        self.update()

    def _update_stats(self):
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
        # 入力配列を1次元化してヒストグラムへ集計する。
        flat = np.ravel(values)
        if flat.dtype != np.uint8 or self._max_value < 255 or self._bins < 256:
            # 0..255範囲外の可能性がある場合のみクリップ処理を行う。
            flat = np.asarray(flat, dtype=np.int32)
            np.clip(flat, 0, self._max_value, out=flat)
        hist = np.bincount(flat, minlength=self._bins)[: self._bins].astype(np.int64)
        self.update_from_hist(hist)

    def update_from_hist(self, hist: np.ndarray):
        # 既に集計済みヒストグラムを直接反映する。
        arr = _fit_hist_size(hist, self._bins)
        if self._hist.shape == arr.shape and np.array_equal(self._hist, arr):
            return
        self._hist = arr
        self._update_stats()
        self.update()

    def paintEvent(self, _):
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
            n_bins = len(bins)
            bin_w = plot.width() / float(n_bins)
            plot_h = max(1, plot.height() - 1)
            for i, val in enumerate(bins):
                h = min(plot_h, int(plot_h * (val / max_y)))
                x = plot.left() + int(i * bin_w)
                w = max(1, int(bin_w) - 1)
                y = plot.bottom() - h
                c = QColor(self._color)
                c.setAlpha(200)
                p.fillRect(QRect(x, y, w, h), c)

            p.setPen(QColor(30, 30, 30))
            axis_rect = QRect(plot.left(), plot.bottom() + 4, plot.width(), 14)
            p.drawText(axis_rect, Qt.AlignLeft | Qt.AlignVCenter, "0")
            p.drawText(axis_rect, Qt.AlignRight | Qt.AlignVCenter, str(self._max_value))

            stats = f"平均 {self._mean:.1f} / 標準偏差 {self._std:.1f}"
            p.drawText(
                QRect(plot.left(), plot.bottom() + 20, plot.width(), 18),
                Qt.AlignCenter | Qt.AlignVCenter,
                stats,
            )
        finally:
            p.end()


class RgbOverlayHistogram(QWidget):
    # RGBヒストグラム重ね表示（0..255の3chを同一軸で描画）。

    def __init__(self):
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
        bucket = max(1, int(self._bucket))
        if hist.size % bucket != 0:
            return hist
        return hist.reshape(-1, bucket).sum(axis=1)

    def update_from_histograms(self, hist_r: np.ndarray, hist_g: np.ndarray, hist_b: np.ndarray):
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

            _draw_plot_guides(p, plot)

            h_r = self._bucketed(self._hist_r)
            h_g = self._bucketed(self._hist_g)
            h_b = self._bucketed(self._hist_b)
            max_y = max(1, int(h_r.max()), int(h_g.max()), int(h_b.max()))
            n_bins = int(h_r.size)
            if n_bins <= 1:
                return
            x_step = plot.width() / float(n_bins - 1)

            def _draw_curve(hist: np.ndarray, color: QColor):
                pen = QPen(color, 1.6)
                p.setPen(pen)
                prev_x = plot.left()
                prev_y = plot.bottom() - int((hist[0] / max_y) * (plot.height() - 1))
                prev_y = max(plot.top(), min(plot.bottom(), prev_y))
                for i in range(1, n_bins):
                    x = plot.left() + int(round(i * x_step))
                    y = plot.bottom() - int((hist[i] / max_y) * (plot.height() - 1))
                    y = max(plot.top(), min(plot.bottom(), y))
                    p.drawLine(prev_x, prev_y, x, y)
                    prev_x, prev_y = x, y

            color_r = QColor(C.R_COLOR)
            color_r.setAlpha(210)
            color_g = QColor(C.G_COLOR)
            color_g.setAlpha(210)
            color_b = QColor(C.B_COLOR)
            color_b.setAlpha(210)
            _draw_curve(h_r, color_r)
            _draw_curve(h_g, color_g)
            _draw_curve(h_b, color_b)

            axis_rect = QRect(plot.left(), plot.bottom() + 4, plot.width(), 14)
            p.setPen(QColor(30, 30, 30))
            p.drawText(axis_rect, Qt.AlignLeft | Qt.AlignVCenter, "0")
            p.drawText(axis_rect, Qt.AlignRight | Qt.AlignVCenter, "255")
            p.drawText(
                QRect(plot.left(), plot.top(), plot.width(), 14),
                Qt.AlignLeft | Qt.AlignTop,
                f"max {max_y}",
            )
        finally:
            p.end()


class RgbHistogramWidget(QWidget):
    MODE_SIDE_BY_SIDE = "side_by_side"
    MODE_OVERLAY = "overlay"

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._display_mode = self.MODE_SIDE_BY_SIDE
        self._hist_r = ChannelHistogram("赤", 256, 255, QColor(C.R_COLOR), bucket=2)
        self._hist_g = ChannelHistogram("緑", 256, 255, QColor(C.G_COLOR), bucket=2)
        self._hist_b = ChannelHistogram("青", 256, 255, QColor(C.B_COLOR), bucket=2)
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
        self.set_display_mode(self.MODE_SIDE_BY_SIDE)

    def set_display_mode(self, mode: str):
        normalized = str(mode or "").strip().lower()
        if normalized not in (self.MODE_SIDE_BY_SIDE, self.MODE_OVERLAY):
            normalized = self.MODE_SIDE_BY_SIDE
        self._display_mode = normalized
        self._stack.setCurrentIndex(1 if normalized == self.MODE_OVERLAY else 0)

    def update_from_bgr(self, bgr: np.ndarray):
        if bgr is None or bgr.size == 0 or bgr.ndim < 3 or bgr.shape[2] < 3:
            return
        # ライブキャプチャは uint8 が大半なので、clip/cast を省いて集計コストを下げる。
        if bgr.dtype == np.uint8:
            b = np.ravel(bgr[:, :, 0])
            g = np.ravel(bgr[:, :, 1])
            r = np.ravel(bgr[:, :, 2])
        else:
            flat = np.asarray(bgr[:, :, :3], dtype=np.int32).reshape(-1, 3)
            b = np.clip(flat[:, 0], 0, 255)
            g = np.clip(flat[:, 1], 0, 255)
            r = np.clip(flat[:, 2], 0, 255)
        hist_b = np.bincount(b, minlength=256)[:256].astype(np.int64)
        hist_g = np.bincount(g, minlength=256)[:256].astype(np.int64)
        hist_r = np.bincount(r, minlength=256)[:256].astype(np.int64)

        self._hist_r.update_from_hist(hist_r)
        self._hist_g.update_from_hist(hist_g)
        self._hist_b.update_from_hist(hist_b)
        self._overlay.update_from_histograms(hist_r, hist_g, hist_b)
