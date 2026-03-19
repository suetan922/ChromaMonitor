"""設定ダイアログの共通レイアウト部品。"""

from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .settings_dialog_specs import (
    SETTINGS_FIELD_GAP_PX,
    SETTINGS_FIELD_SLOT_WIDTH,
    SETTINGS_LABEL_MAX_WIDTH,
    SETTINGS_LABEL_MIN_WIDTH,
    SETTINGS_LABEL_PAD_PX,
    SETTINGS_LABEL_TEXTS,
)


@lru_cache(maxsize=1)
def settings_label_width() -> int:
    """設定ラベル幅を最長ラベル基準で算出する。"""
    probe = QLabel()
    metrics = QFontMetrics(probe.font())
    longest = max(metrics.horizontalAdvance(text) for text in SETTINGS_LABEL_TEXTS)
    target = int(longest + SETTINGS_LABEL_PAD_PX)
    return max(SETTINGS_LABEL_MIN_WIDTH, min(SETTINGS_LABEL_MAX_WIDTH, target))


def preferred_field_width(widget: QWidget) -> int:
    """設定ダイアログ内で使う入力欄の妥当な表示幅を返す。"""
    width = max(
        int(widget.minimumWidth()),
        int(widget.minimumSizeHint().width()),
        int(widget.sizeHint().width()),
    )
    if isinstance(widget, QAbstractSpinBox):
        return max(120, min(180, width))
    if isinstance(widget, QLineEdit):
        return max(320, min(460, width))
    if isinstance(widget, QComboBox):
        minimum = 380 if widget.isEditable() else 220
        maximum = 460 if widget.isEditable() else 320
        return max(minimum, min(maximum, width))
    return max(220, min(460, width))


def _wrap_setting_field(widget: QWidget, *, field_width: int | None = None) -> QWidget:
    """入力欄を左寄せのコンテナへ包み、必要なら単位ラベルも添える。"""
    field_width = int(field_width) if field_width is not None else int(preferred_field_width(widget))
    field_width = max(80, min(SETTINGS_FIELD_SLOT_WIDTH, field_width))
    widget.setFixedWidth(int(field_width))

    policy = widget.sizePolicy()
    policy.setHorizontalPolicy(
        QSizePolicy.Fixed if isinstance(widget, QAbstractSpinBox) else QSizePolicy.Preferred
    )
    widget.setSizePolicy(policy)

    holder = QWidget()
    holder.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    holder_layout = QHBoxLayout(holder)
    holder_layout.setContentsMargins(0, 0, 0, 0)
    holder_layout.setSpacing(6)
    holder_layout.addWidget(widget, 0)

    unit_text = str(getattr(widget, "_chroma_unit_label_text", "")).strip()
    if unit_text:
        unit_label = QLabel(unit_text)
        unit_label.setProperty("chromaRole", "muted")
        unit_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        holder_layout.addWidget(unit_label, 0)

    holder_layout.addStretch(1)
    holder.setFixedWidth(SETTINGS_FIELD_SLOT_WIDTH)
    return holder


def make_labeled_row(
    label_text: str,
    widget: QWidget,
    *,
    field_width: int | None = None,
) -> QWidget:
    """左ラベルと入力ウィジェットを並べた設定行を作る。"""
    row = QWidget()
    row.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SETTINGS_FIELD_GAP_PX)
    label = QLabel(label_text)
    label.setFixedWidth(settings_label_width())
    label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    layout.addWidget(label, 0)
    layout.addWidget(_wrap_setting_field(widget, field_width=field_width), 0)
    row.setFixedWidth(
        settings_label_width() + SETTINGS_FIELD_GAP_PX + SETTINGS_FIELD_SLOT_WIDTH
    )
    return row


def add_labeled_row(
    layout: QVBoxLayout,
    label_text: str,
    field: QWidget,
    *,
    field_width: int | None = None,
) -> QWidget:
    """ラベル付き入力行を作成して左寄せ追加し、生成行を返す。"""
    row = make_labeled_row(label_text, field, field_width=field_width)
    layout.addWidget(row, 0, Qt.AlignLeft | Qt.AlignTop)
    return row


def make_hint_label(text: str, *, word_wrap: bool = False) -> QLabel:
    """設定説明向けの補助ラベルを作る。"""
    hint = QLabel(text)
    hint.setProperty("chromaRole", "hint")
    hint.setWordWrap(bool(word_wrap))
    return hint


def create_settings_page(spacing: int = 10) -> tuple[QWidget, QVBoxLayout]:
    """設定ページのルートウィジェットと縦レイアウトを作る。"""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(int(spacing))
    layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    return page, layout


def add_hint_rows_settings_page(
    pages: QStackedWidget,
    *,
    hint: str,
    rows: list[tuple[str, QWidget] | tuple[str, QWidget, int]],
) -> list[QWidget]:
    """説明文 + 複数入力行で構成される設定ページを追加し、行を返す。"""
    page, layout = create_settings_page()
    layout.addWidget(make_hint_label(hint))
    created_rows: list[QWidget] = []
    for row in rows:
        if len(row) == 3:
            label_text, field, field_width = row
            created = add_labeled_row(
                layout,
                str(label_text),
                field,
                field_width=int(field_width),
            )
        else:
            label_text, field = row
            created = add_labeled_row(layout, str(label_text), field)
        created_rows.append(created)
    layout.addStretch(1)
    pages.addWidget(page)
    return created_rows
