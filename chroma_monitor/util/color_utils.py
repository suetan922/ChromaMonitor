"""色名・色相分類の共通ユーティリティ。"""

HUE_NAME_12 = (
    "赤",
    "橙",
    "黄",
    "黄緑",
    "緑",
    "青緑",
    "水",
    "青",
    "藍",
    "紫",
    "赤紫",
    "紅",
)
"""12分割色相の表示名。"""


def hue_name_12_from_deg(hue_deg: float) -> str:
    """色相角(度)を12色相名へ丸めて返す。"""
    idx = int(((float(hue_deg) + 15.0) % 360.0) // 30.0) % len(HUE_NAME_12)
    return HUE_NAME_12[idx]
