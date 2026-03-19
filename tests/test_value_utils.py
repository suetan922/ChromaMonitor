"""値変換ユーティリティの境界値を守るテスト。"""

from chroma_monitor.util.value_utils import (
    clamp_float,
    clamp_int,
    normalized_ratio,
    safe_choice,
    safe_int,
)


def test_clamp_int_bounds() -> None:
    # intの上下限クリップが崩れないことを確認する。
    assert clamp_int(-5, 0, 10) == 0
    assert clamp_int(5, 0, 10) == 5
    assert clamp_int(99, 0, 10) == 10


def test_clamp_float_bounds() -> None:
    # floatの上下限クリップが崩れないことを確認する。
    assert clamp_float(-1.5, 0.0, 1.0) == 0.0
    assert clamp_float(0.25, 0.0, 1.0) == 0.25
    assert clamp_float(2.0, 0.0, 1.0) == 1.0


def test_normalized_ratio_handles_edges() -> None:
    # 比率正規化が端点と異常レンジ(hi<=lo)で破綻しないことを確認する。
    assert normalized_ratio(0.0, 0.0, 100.0) == 0.0
    assert normalized_ratio(50.0, 0.0, 100.0) == 0.5
    assert normalized_ratio(200.0, 0.0, 100.0) == 1.0
    assert normalized_ratio(5.0, 10.0, 10.0) == 0.0


def test_safe_int_and_choice() -> None:
    # 入力が壊れていても既定値へ安全にフォールバックできることを確認する。
    assert safe_int("42", 0) == 42
    assert safe_int("x", 7) == 7
    assert safe_choice("b", ["a", "b", "c"], "a") == "b"
    assert safe_choice("z", ["a", "b", "c"], "a") == "a"
