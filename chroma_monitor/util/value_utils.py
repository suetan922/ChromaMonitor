"""値の正規化や安全な変換を行う共通関数。"""

from typing import Any, Sequence, TypeVar

T = TypeVar("T")


def clamp_int(value: int, low: int, high: int) -> int:
    """整数値を `[low, high]` の範囲に収める。"""
    return max(low, min(high, int(value)))


def clamp_float(value: float, low: float, high: float) -> float:
    """浮動小数点値を `[low, high]` の範囲に収める。"""
    return max(float(low), min(float(high), float(value)))


def normalized_ratio(value: float, low: float, high: float) -> float:
    """`value` を `[low, high]` の相対位置として `0.0..1.0` に正規化する。"""
    low_f = float(low)
    high_f = float(high)
    if high_f <= low_f:
        return 0.0
    ratio = (float(value) - low_f) / (high_f - low_f)
    return max(0.0, min(1.0, ratio))


def safe_int(value: Any, default: int) -> int:
    """`value` を整数へ変換し、失敗時は `default` を返す。"""
    try:
        return int(value)
    except Exception:
        return int(default)


def safe_choice(value: T, allowed: Sequence[T], default: T) -> T:
    """`value` が候補にあるときのみ採用し、なければ `default` を返す。"""
    return value if value in allowed else default
