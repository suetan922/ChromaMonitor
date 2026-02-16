"""HSV channel histogram widget."""

import math

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget


class ChannelHistogram(QWidget):
    def __init__(self, title: str, bins: int, max_value: int, color: QColor, bucket: int = 4):
        super().__init__()
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._title = title
        self._bins = bins
        self._max_value = max_value
        self._color = color
        self._bucket = max(1, bucket)
        self._hist = np.zeros(bins, dtype=np.int64)
        self._mean = 0.0
        self._std = 0.0
        self._total = 0

    def update_from_values(self, values: np.ndarray):
        # 入力配列を1次元化してヒストグラムへ集計する。
        flat = values.reshape(-1).astype(np.int32)
        flat = np.clip(flat, 0, self._max_value)
        hist = np.bincount(flat, minlength=self._bins)[: self._bins]
        self._hist = hist
        total = int(hist.sum())
        self._total = total
        if total > 0:
            # 表示補助として平均と標準偏差も同時に保持する。
            idx = np.arange(self._bins, dtype=np.float64)
            mean = float((idx * hist).sum() / total)
            var = float((((idx - mean) ** 2) * hist).sum() / total)
            self._mean = mean
            self._std = math.sqrt(var)
        else:
            self._mean = self._std = 0.0
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
                return

            max_y = int(self._hist.max())
            if max_y <= 0:
                max_y = 1

            p.setPen(QColor(225, 225, 225))
            # 目盛りガイド線（横方向）を薄く引く。
            for i in range(1, 5):
                y = plot.top() + int(plot.height() * i / 5)
                p.drawLine(plot.left(), y, plot.right(), y)

            p.setPen(QColor(180, 180, 180))
            p.drawLine(plot.left(), plot.top(), plot.left(), plot.bottom())
            p.drawLine(plot.left(), plot.bottom(), plot.right(), plot.bottom())

            bucket = self._bucket
            bins = self._hist
            # ビン数が多い場合は指定バケット幅でまとめて可読性を上げる。
            if self._bins % bucket == 0:
                bins = bins.reshape(-1, bucket).sum(axis=1)
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


_DEFAULT_IMAGE_VIEW_STYLE = "background:#111; border:1px solid #333; color:#AAA;"
