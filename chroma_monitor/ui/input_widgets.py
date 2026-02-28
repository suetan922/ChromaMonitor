"""入力系ウィジェットと補助関数。"""

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QAbstractSpinBox, QLineEdit, QSpinBox


class SelectAllLineEdit(QLineEdit):
    """フォーカス時は全選択、ダブルクリック時は位置編集を優先する入力欄。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._select_all_on_release = False

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if event.reason() != Qt.MouseFocusReason:
            self.selectAll()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.hasFocus():
            self._select_all_on_release = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._select_all_on_release:
            self.selectAll()
            self._select_all_on_release = False

    def mouseDoubleClickEvent(self, event):
        self._select_all_on_release = False
        super().mouseDoubleClickEvent(event)
        point = event.position().toPoint() if hasattr(event, "position") else event.pos()
        self.setCursorPosition(self.cursorPositionAt(point))
        self.deselect()


class SelectAllSpinBox(QSpinBox):
    """フォーカス時に数値部分のみ選択する `QSpinBox`。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._select_value_on_release = False

    def _select_value_text(self):
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
        super().focusInEvent(event)
        if event.reason() != Qt.MouseFocusReason:
            QTimer.singleShot(0, self._select_value_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.hasFocus():
            self._select_value_on_release = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._select_value_on_release:
            self._select_value_on_release = False
            self._select_value_text()

    def mouseDoubleClickEvent(self, event):
        self._select_value_on_release = False
        super().mouseDoubleClickEvent(event)


def configure_numeric_input(
    widget: QAbstractSpinBox,
    *,
    min_width: int = 110,
    min_height: int = 28,
) -> None:
    """Spin系入力の共通見た目を設定する。"""
    widget.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
    widget.setMinimumWidth(int(min_width))
    widget.setMinimumHeight(int(min_height))


def add_checkable_action(menu, text: str, checked: bool, toggled_cb):
    """メニューのチェック可能アクション生成を共通化する。"""
    action = menu.addAction(text)
    action.setCheckable(True)
    action.setChecked(bool(checked))
    action.toggled.connect(toggled_cb)
    return action
