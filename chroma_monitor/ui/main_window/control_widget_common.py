"""MainWindow control widget 構築で使う共通 helper。"""

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox

from ..input_widgets import SelectAllSpinBox, configure_numeric_input
from ...util import constants as C


def set_widget_unit_label(widget, suffix: str) -> None:
    """設定ダイアログ表示用の単位ラベル文字列をウィジェットへ保持する。"""
    widget._chroma_unit_label_text = str(suffix).strip()


def populate_data_combo(combo: QComboBox, items) -> None:
    """`(label, data)` 形式の候補列でコンボを初期化する。"""
    popup_view = combo.view()
    if popup_view is not None:
        popup_view.setProperty("chromaRole", "comboPopup")
    combo.clear()
    for label, data in items:
        combo.addItem(label, data)


def build_int_spinbox(
    minimum: int,
    maximum: int,
    value: int,
    *,
    step: int = 1,
    suffix: str = "",
    min_width: int = 110,
    min_height: int = 28,
) -> SelectAllSpinBox:
    """共通設定済みの整数入力欄を生成する。"""
    spin = SelectAllSpinBox()
    spin.setRange(int(minimum), int(maximum))
    spin.setSingleStep(int(step))
    spin.setValue(int(value))
    if suffix:
        set_widget_unit_label(spin, suffix)
    configure_numeric_input(spin, min_width=min_width, min_height=min_height)
    return spin


def build_double_spinbox(
    minimum: float,
    maximum: float,
    value: float,
    *,
    decimals: int,
    step: float,
    suffix: str = "",
    min_width: int = 110,
    min_height: int = 28,
) -> QDoubleSpinBox:
    """共通設定済みの小数入力欄を生成する。"""
    spin = QDoubleSpinBox()
    spin.setRange(float(minimum), float(maximum))
    spin.setDecimals(int(decimals))
    spin.setSingleStep(float(step))
    spin.setValue(float(value))
    if suffix:
        set_widget_unit_label(spin, suffix)
    configure_numeric_input(spin, min_width=min_width, min_height=min_height)
    return spin


def populate_harmony_guide_combo(combo: QComboBox) -> None:
    """色彩調和ガイド用コンボへ候補を設定する。"""
    populate_data_combo(
        combo,
        (
            (C.WHEEL_HARMONY_GUIDE_LABELS[guide_type], guide_type)
            for guide_type in C.WHEEL_HARMONY_GUIDE_COMBO_ORDER
        ),
    )
