"""設定UI値の正規化で共有する補助処理。"""

from ...util.qt_helpers import blocked_signals
from ...util.value_utils import clamp_float, clamp_int, safe_choice, safe_int


def cfg_int(cfg: dict, key: str, default: int, low: int, high: int) -> int:
    """設定辞書から整数値を取り出し、範囲内へ丸めて返す。"""
    return clamp_int(safe_int(cfg.get(key, default), default), low, high)


def cfg_float(
    cfg: dict,
    key: str,
    default: float,
    low: float | None = None,
    high: float | None = None,
) -> float:
    """設定辞書から浮動小数値を取り出し、必要なら範囲内へ丸める。"""
    try:
        value = float(cfg.get(key, default))
    except (TypeError, ValueError):
        value = float(default)
    if low is not None and high is not None:
        return clamp_float(value, low, high)
    return value


def set_value_blocked(widget, value) -> None:
    """シグナルを抑止して値を設定する。"""
    with blocked_signals(widget):
        widget.setValue(value)


def set_combobox_data_blocked(combo, data, default_data=None) -> int:
    """シグナル抑止でコンボ選択値を設定し、選択インデックスを返す。"""
    index = combo.findData(data)
    if index < 0 and default_data is not None:
        index = combo.findData(default_data)
    if index < 0 and combo.count() > 0:
        index = 0
    if index >= 0:
        with blocked_signals(combo):
            combo.setCurrentIndex(int(index))
    return index


def apply_combo_choice(combo, raw_value, allowed, default) -> None:
    """許容値へ正規化してコンボ選択へ反映する。"""
    set_combobox_data_blocked(
        combo,
        safe_choice(raw_value, allowed, default),
        default_data=default,
    )


def selected_combo_data(combo, allowed, default):
    """コンボ選択値を許容値へ正規化して返す。"""
    return safe_choice(combo.currentData(), allowed, default)


def selected_checked(widget) -> bool:
    """チェック系ウィジェットの選択状態を返す。"""
    return bool(widget.isChecked())


def selected_checked_attr(main_window, attr_name: str) -> bool:
    """チェック系属性名から選択状態を返す。"""
    return selected_checked(getattr(main_window, attr_name))


def selected_int_in_range(widget, low: int, high: int) -> int:
    """数値入力ウィジェット値を範囲内へ丸めて返す。"""
    return clamp_int(int(widget.value()), int(low), int(high))


def selected_int_attr(main_window, attr_name: str, low: int, high: int) -> int:
    """数値入力属性名から範囲内整数値を返す。"""
    return selected_int_in_range(getattr(main_window, attr_name), low, high)


def selected_combo_attr(main_window, attr_name: str, allowed, default):
    """コンボ属性名から正規化済み選択値を返す。"""
    return selected_combo_data(getattr(main_window, attr_name), allowed, default)
