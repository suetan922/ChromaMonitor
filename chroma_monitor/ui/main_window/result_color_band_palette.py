"""配色比率ドックで共有する色変換・配色候補生成・表示整形。"""

from functools import lru_cache

import cv2
import numpy as np

from ...util import constants as C
from ...util.color_utils import hue_name_12_from_deg

COLOR_BAND_KEY_RATIO_DECIMALS = 3  # 0.1%表示に合わせて更新判定も丸める。
_COLOR_BAND_MIN_VISIBLE_PERCENT = 0.1


def top_bar_item_ratio_color(item: tuple) -> tuple[float, tuple[int, int, int]]:
    """バー項目を `(ratio, rgb)` 形式へ正規化する。"""
    if len(item) == 3:
        _, ratio, color = item
    else:
        ratio, color = item
    return float(ratio), tuple(int(c) for c in color)


def is_visible_color_band_ratio(ratio: float) -> bool:
    """配色比率一覧/バーに表示する最小割合(%)以上かを判定する。"""
    try:
        return max(0.0, float(ratio)) * 100.0 >= float(_COLOR_BAND_MIN_VISIBLE_PERCENT)
    except Exception:
        return False


def filter_invisible_percent_bars(bars: list[tuple]) -> list[tuple]:
    """最小表示割合(%)未満の項目を除外する。"""
    return [item for item in bars if is_visible_color_band_ratio(top_bar_item_ratio_color(item)[0])]


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """RGBタプルを`#RRGGBB`形式文字列へ変換する。"""
    r, g, b = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return f"#{r:02X}{g:02X}{b:02X}"


def bar_key_item(item: tuple) -> tuple[str, float, tuple[int, int, int]]:
    """配色比率項目を描画キャッシュ比較用キーへ正規化する。"""
    if len(item) == 3:
        name, ratio, color = item
    else:
        name, ratio, color = "", item[0], item[1]
    return (
        str(name),
        round(float(ratio), COLOR_BAND_KEY_RATIO_DECIMALS),
        tuple(int(c) for c in color),
    )


def rgb_to_hsv_text(rgb: tuple[int, int, int]) -> str:
    """RGBタプルを表示用HSV文字列へ変換する。"""
    h_deg, s, v = rgb_to_hsv_parts(rgb)
    return f"HSV({int(round(h_deg)) % 360}, {int(s)}, {int(v)})"


def normalize_chip_entries(bars: list[tuple]) -> list[dict]:
    """バー項目を一覧表示向けの辞書配列へ変換する。"""
    entries = []
    for idx, item in enumerate(bars, start=1):
        ratio, color = top_bar_item_ratio_color(item)
        rgb = (int(color[0]), int(color[1]), int(color[2]))
        hue, sat, val = rgb_to_hsv_parts(rgb)
        hsv_text = f"HSV({int(round(hue)) % 360}, {int(sat)}, {int(val)})"
        base_label = str(item[0]).strip() if len(item) == 3 else ""
        if base_label.startswith("H") and base_label[1:].isdigit():
            label = hue_name_12_from_deg(hue)
        elif base_label:
            label = base_label
        else:
            label = hue_name_12_from_deg(hue)
        entries.append(
            {
                "index": idx - 1,
                "label": f"{label}",
                "ratio": float(ratio),
                "rgb": rgb,
                "hsv_text": hsv_text,
                "hex": rgb_to_hex(rgb),
                "hue_deg": hue,
            }
        )
    return entries


def hsv_deg_to_rgb(hue_deg: float, sat: int, val: int) -> tuple[int, int, int]:
    """HSV度数指定から RGB タプルへ変換する。"""
    hue_8bit = int(round(float(hue_deg) / 2.0)) % 180
    sat_8bit = int(np.clip(int(sat), 0, 255))
    val_8bit = int(np.clip(int(val), 0, 255))
    return _hsv8_to_rgb_cached(hue_8bit, sat_8bit, val_8bit)


def rgb_to_hsv_parts(rgb: tuple[int, int, int]) -> tuple[float, int, int]:
    """RGBタプルから HSV(度, 8bit, 8bit) を返す。"""
    r, g, b = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return _rgb_to_hsv_parts_cached(r, g, b)


@lru_cache(maxsize=4096)
def _hsv8_to_rgb_cached(hue_8bit: int, sat_8bit: int, val_8bit: int) -> tuple[int, int, int]:
    """8bit HSVをRGBへ変換するキャッシュ付きヘルパー。"""
    rgb = cv2.cvtColor(
        np.uint8([[[int(hue_8bit), int(sat_8bit), int(val_8bit)]]]),
        cv2.COLOR_HSV2RGB,
    )[0, 0]
    return (int(rgb[0]), int(rgb[1]), int(rgb[2]))


@lru_cache(maxsize=4096)
def _rgb_to_hsv_parts_cached(r: int, g: int, b: int) -> tuple[float, int, int]:
    """RGB整数値をHSV(度,8bit,8bit)へ変換するキャッシュ付きヘルパー。"""
    hsv = cv2.cvtColor(np.uint8([[[int(r), int(g), int(b)]]]), cv2.COLOR_RGB2HSV)[0, 0]
    return float(int(hsv[0]) * 2), int(hsv[1]), int(hsv[2])


def harmony_palette_from_base(
    base_rgb: tuple[int, int, int],
    guide_type: str,
) -> list[tuple[int, tuple[int, int, int], str]]:
    """基準色とガイド種別から調和色パレットを生成する。"""
    offsets = C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG.get(guide_type, (0.0,))
    base_hue, base_sat, base_val = rgb_to_hsv_parts(base_rgb)
    base_rgb_tuple = (int(base_rgb[0]), int(base_rgb[1]), int(base_rgb[2]))
    sat = int(base_sat)
    val = int(base_val)

    base_item = (int(round(base_hue)) % 360, base_rgb_tuple, "基準色")
    harmony_items: list[tuple[int, tuple[int, int, int], str]] = []
    for offset in offsets:
        off = float(offset)
        if abs(off) < 1e-9 or abs(abs(off) - 360.0) < 1e-9:
            continue
        hue_deg = (base_hue + off) % 360.0
        rgb_tuple = hsv_deg_to_rgb(hue_deg, sat, val)
        harmony_items.append((int(round(hue_deg)), rgb_tuple, f"調和{len(harmony_items) + 1}"))
    return [base_item, *harmony_items]


def method_palettes_from_base(
    base_rgb: tuple[int, int, int],
) -> list[tuple[str, list[tuple[int, int, int]]]]:
    """基準色から配色手法ごとの参考パレットを生成する。"""
    base_hue, base_sat, base_val = rgb_to_hsv_parts(base_rgb)
    base_rgb_tuple = (int(base_rgb[0]), int(base_rgb[1]), int(base_rgb[2]))
    sat_mid = int(np.clip(max(96, int(base_sat)), 0, 255))
    val_mid = int(np.clip(max(112, int(base_val)), 0, 255))
    neutral = int(
        np.clip(
            round(
                0.299 * base_rgb_tuple[0] + 0.587 * base_rgb_tuple[1] + 0.114 * base_rgb_tuple[2]
            ),
            0,
            255,
        )
    )
    neutral_hi = int(np.clip(neutral + 52, 0, 255))
    tone_sat = int(np.clip(max(72, int(base_sat * 0.55)), 48, 170))
    tone_val = int(np.clip(max(122, int(base_val * 1.05)), 90, 245))
    tint_sat = int(np.clip(max(64, int(base_sat * 0.85)), 52, 210))
    tint_val = int(np.clip(max(96, int(base_val)), 80, 240))

    def mk(offset: float, sat: int, val: int) -> tuple[int, int, int]:
        sat_u8 = int(np.clip(int(sat), 0, 255))
        val_u8 = int(np.clip(int(val), 0, 255))
        return hsv_deg_to_rgb(base_hue + float(offset), sat_u8, val_u8)

    return [
        (
            "トーンオントーン",
            [
                base_rgb_tuple,
                mk(0.0, int(base_sat * 0.30), int(base_val + 84)),
                mk(0.0, int(base_sat * 0.58), int(base_val + 32)),
                mk(0.0, int(base_sat * 1.08) + 20, int(base_val - 54)),
            ],
        ),
        (
            "トーンイントーン",
            [
                base_rgb_tuple,
                mk(-20.0, tint_sat, tint_val + 8),
                mk(20.0, tint_sat, tint_val),
                mk(42.0, tint_sat - 10, tint_val - 8),
            ],
        ),
        (
            "ドミナントカラー",
            [
                base_rgb_tuple,
                mk(14.0, int(base_sat * 0.42), int(base_val + 26)),
                mk(-12.0, int(base_sat * 0.32), int(base_val - 6)),
                mk(138.0, int(base_sat * 0.95), int(base_val - 18)),
            ],
        ),
        (
            "ドミナントトーン",
            [
                base_rgb_tuple,
                mk(-90.0, tone_sat, tone_val),
                mk(90.0, tone_sat, tone_val),
                mk(150.0, tone_sat, tone_val),
            ],
        ),
        (
            "セパレーション",
            [
                base_rgb_tuple,
                (neutral_hi, neutral_hi, neutral_hi),
                mk(180.0, sat_mid, val_mid),
            ],
        ),
    ]


def format_warmcool_text(snapshot: dict) -> str:
    """暖色/寒色/その他の表示文字列を生成する。"""
    return (
        "暖色: "
        f"{float(snapshot.get('warm_ratio', 0.0))*100:.1f}%   "
        f"寒色: {float(snapshot.get('cool_ratio', 0.0))*100:.1f}%   "
        f"その他: {float(snapshot.get('other_ratio', 0.0))*100:.1f}%"
    )
