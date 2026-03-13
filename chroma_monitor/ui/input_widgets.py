"""入力系ウィジェットと補助関数。"""

import time

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit, QSpinBox


class SelectAllLineEdit(QLineEdit):
    """フォーカス時は全選択、ダブルクリック時は位置編集を優先する入力欄。"""

    def __init__(self, *args, **kwargs):
        """全選択制御フラグを初期化する。"""
        super().__init__(*args, **kwargs)
        self._select_all_on_release = False
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def focusInEvent(self, event):
        """キーボード遷移時は全選択して再入力しやすくする。"""
        super().focusInEvent(event)
        if event.reason() != Qt.MouseFocusReason:
            self.selectAll()

    def mousePressEvent(self, event):
        """未フォーカス状態のクリック開始を検知して全選択予約する。"""
        if event.button() == Qt.LeftButton and not self.hasFocus():
            self._select_all_on_release = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """クリックでフォーカスを得た直後に全選択を適用する。"""
        super().mouseReleaseEvent(event)
        if self._select_all_on_release:
            self.selectAll()
            self._select_all_on_release = False

    def mouseDoubleClickEvent(self, event):
        """ダブルクリック時は単語選択ではなくカーソル位置編集を優先する。"""
        self._select_all_on_release = False
        super().mouseDoubleClickEvent(event)
        point = event.position().toPoint() if hasattr(event, "position") else event.pos()
        self.setCursorPosition(self.cursorPositionAt(point))
        self.deselect()


class SelectAllSpinBox(QSpinBox):
    """フォーカス時に数値部分のみ選択する `QSpinBox`。"""

    def __init__(self, *args, **kwargs):
        """クリック選択制御フラグを初期化する。"""
        super().__init__(*args, **kwargs)
        self._select_value_on_release = False

    def _select_value_text(self) -> None:
        """prefix/suffix を除いた数値部分だけを選択状態にする。"""
        editor = self.lineEdit()
        if editor is None:
            return
        start = len(self.prefix())
        length = len(self.cleanText())
        if length <= 0:
            editor.selectAll()
            return
        editor.setSelection(start, length)

    def focusInEvent(self, event):
        """キーボード遷移時は数値部分を全選択する。"""
        super().focusInEvent(event)
        if event.reason() != Qt.MouseFocusReason:
            QTimer.singleShot(0, self._select_value_text)

    def mousePressEvent(self, event):
        """未フォーカス状態の左クリックでリリース後選択を予約する。"""
        if event.button() == Qt.LeftButton and not self.hasFocus():
            self._select_value_on_release = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """フォーカス取得直後に数値部分を選択する。"""
        super().mouseReleaseEvent(event)
        if self._select_value_on_release:
            self._select_value_on_release = False
            self._select_value_text()

    def mouseDoubleClickEvent(self, event):
        """ダブルクリック時の自動選択予約を解除する。"""
        self._select_value_on_release = False
        super().mouseDoubleClickEvent(event)


class RefreshOnInteractComboBox(QComboBox):
    """フォーカス時とポップアップ表示時に更新コールバックを走らせる `QComboBox`。"""

    def __init__(self, *args, **kwargs):
        """更新コールバックと重複抑止用状態を初期化する。"""
        super().__init__(*args, **kwargs)
        self._refresh_callback = None
        self._refresh_min_interval_sec = 0.0
        self._last_refresh_monotonic = 0.0
        self._install_line_edit_filter()

    def setLineEdit(self, edit: QLineEdit) -> None:
        """差し替えた入力欄にもフォーカス監視を再設定する。"""
        prev = self.lineEdit()
        if prev is not None:
            prev.removeEventFilter(self)
        super().setLineEdit(edit)
        self._install_line_edit_filter()

    def set_refresh_callback(self, callback, *, min_interval_ms: int = 700) -> None:
        """候補更新コールバックと最小再実行間隔を設定する。"""
        self._refresh_callback = callback
        self._refresh_min_interval_sec = max(0.0, int(min_interval_ms) / 1000.0)

    def _install_line_edit_filter(self) -> None:
        """内包 `QLineEdit` のフォーカスイベントを監視する。"""
        editor = self.lineEdit()
        if editor is not None:
            editor.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            editor.installEventFilter(self)

    def _maybe_refresh_items(self) -> None:
        """短時間の重複呼び出しを抑止して更新コールバックを実行する。"""
        if not callable(self._refresh_callback):
            return
        now = time.monotonic()
        if (now - float(self._last_refresh_monotonic)) < float(self._refresh_min_interval_sec):
            return
        self._last_refresh_monotonic = now
        self._refresh_callback()

    def focusInEvent(self, event) -> None:
        """コンボ本体へフォーカスが来た時に候補を最新化する。"""
        super().focusInEvent(event)
        self._maybe_refresh_items()

    def showPopup(self) -> None:
        """候補一覧を開く直前に対象一覧を最新化する。"""
        self._maybe_refresh_items()
        super().showPopup()

    def eventFilter(self, obj, event):
        """内包入力欄のフォーカス時にも候補を最新化する。"""
        if obj is self.lineEdit() and event.type() == QEvent.FocusIn:
            self._maybe_refresh_items()
        return super().eventFilter(obj, event)


def configure_numeric_input(
    widget: QAbstractSpinBox,
    *,
    min_width: int = 110,
    min_height: int = 28,
) -> None:
    """Spin系入力の共通見た目と入力ガイドを設定する。"""
    widget.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
    widget.setMinimumWidth(int(min_width))
    widget.setMinimumHeight(int(min_height))
    numeric_align = Qt.AlignRight | Qt.AlignVCenter
    set_alignment = getattr(widget, "setAlignment", None)
    if callable(set_alignment):
        set_alignment(numeric_align)
    editor = widget.lineEdit()
    if editor is not None:
        editor.setAlignment(numeric_align)
    _apply_spin_input_hint(widget)


def _apply_spin_input_hint(widget: QAbstractSpinBox) -> None:
    """数値入力に「範囲のみ」のツールチップを付与する。"""

    decimals_getter = getattr(widget, "decimals", None)
    if callable(decimals_getter):
        decimals = max(0, int(decimals_getter()))
        min_text = f"{float(widget.minimum()):.{decimals}f}"
        max_text = f"{float(widget.maximum()):.{decimals}f}"
    else:
        min_text = str(int(round(float(widget.minimum()))))
        max_text = str(int(round(float(widget.maximum()))))

    tooltip = f"範囲: {min_text} ～ {max_text}"
    widget.setToolTip(tooltip)


def add_checkable_action(menu, text: str, checked: bool, toggled_cb):
    """メニューのチェック可能アクション生成を共通化する。"""
    action = menu.addAction(text)
    action.setCheckable(True)
    action.setChecked(bool(checked))
    action.toggled.connect(toggled_cb)
    return action
