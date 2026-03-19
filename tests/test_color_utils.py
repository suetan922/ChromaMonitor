"""色相角→色名変換の境界と周回を守るテスト。"""

from chroma_monitor.util.color_utils import hue_name_12_from_deg


def test_hue_name_12_boundaries() -> None:
    # 15度境界で区分が切り替わることを確認する。
    assert hue_name_12_from_deg(0.0) == "赤"
    assert hue_name_12_from_deg(14.9) == "赤"
    assert hue_name_12_from_deg(15.0) == "橙"


def test_hue_name_12_wraparound() -> None:
    # 360度周回と負値入力でも破綻しないことを確認する。
    assert hue_name_12_from_deg(359.0) == "赤"
    assert hue_name_12_from_deg(360.0) == "赤"
    assert hue_name_12_from_deg(-1.0) == "赤"
