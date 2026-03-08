"""配色比率ドックの描画と詳細UI更新を扱う補助処理。"""

import cv2
import numpy as np
from functools import lru_cache
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...analysis.frame_analysis import compute_top_bars_chromatic_medoid
from ...util import constants as C
from ...util.image_ops import clamp_render_size
from ...util.qt_helpers import (
    is_widget_renderable,
    set_visible_if_changed,
)
from .settings_values import (
    selected_color_band_harmony_guide_enabled,
    selected_color_band_harmony_guide_type,
    selected_color_band_use_wheel_harmony,
    selected_effective_color_band_sat_threshold,
    selected_wheel_harmony_guide_enabled,
    selected_wheel_harmony_guide_type,
)

_TOP_BAR_MIN_HEIGHT = 12
_TOP_BAR_TEXT_MIN_WIDTH = 240
_TOP_BAR_TEXT_MIN_SEGMENT_PX = 42
_COLOR_BAND_MIN_VISIBLE_PERCENT = 0.1
_COLOR_BAND_KEY_RATIO_DECIMALS = 3  # 0.1%表示に合わせて更新判定も丸める。
# 配色比率の表示優先度:
# 1) カラーバー 2) 暖色寒色 3) 一覧 4) 詳細
# 高さ不足時は下位から順に隠す。
_COLOR_BAND_MIN_H_SHOW_TOP_BAR = 1
_COLOR_BAND_MIN_H_SHOW_WARMCOOL = 56
_COLOR_BAND_MIN_H_SHOW_CHIP_LIST = 120
_COLOR_BAND_MIN_H_SHOW_DETAIL = 210
_COLOR_DETAIL_HINT_SELECT = "一覧から色を選択してください。"
_COLOR_DETAIL_HINT_ACHROMATIC = "無彩色が選択されています。調和色は表示されません。"
_COLOR_DETAIL_LABEL_HARMONY = "色彩調和"
_COLOR_DETAIL_LABEL_COMPLEMENT = "補色"
_COLOR_DETAIL_LABEL_METHODS = "配色手法"

_HUE_NAME_12 = (
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


def _top_bars_chromatic_medoid(
    bgr_preview: np.ndarray | None,
    sat_threshold: int = 0,
) -> list[tuple[str, float, tuple[int, int, int]]]:
    """配色比率の上位色を共通パラメータで計算するラッパー。"""
    return compute_top_bars_chromatic_medoid(
        bgr_preview,
        sat_threshold=int(sat_threshold),
        top_count=int(C.TOP_COLORS_COUNT),
    )


def _top_bar_item_ratio_color(item: tuple) -> tuple[float, tuple[int, int, int]]:
    """バー項目を `(ratio, rgb)` 形式へ正規化する。"""
    if len(item) == 3:
        _, ratio, color = item
    else:
        ratio, color = item
    return float(ratio), tuple(int(c) for c in color)


def _is_visible_color_band_ratio(ratio: float) -> bool:
    """配色比率一覧/バーに表示する最小割合(%)以上かを判定する。"""
    try:
        return max(0.0, float(ratio)) * 100.0 >= float(_COLOR_BAND_MIN_VISIBLE_PERCENT)
    except Exception:
        return False


def _filter_invisible_percent_bars(bars: list[tuple]) -> list[tuple]:
    """最小表示割合(%)未満の項目を除外する。"""
    return [
        item
        for item in bars
        if _is_visible_color_band_ratio(_top_bar_item_ratio_color(item)[0])
    ]


def render_top_color_bar(
    bars: list[tuple], width: int = 300, height: int = C.TOP_COLOR_BAR_HEIGHT
) -> QPixmap:
    """配色比率バーのピクスマップを描画して返す。"""
    safe_w, safe_h = clamp_render_size(width, max(_TOP_BAR_MIN_HEIGHT, height))
    pm = QPixmap(safe_w, safe_h)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    try:
        painter.fillRect(QRect(0, 0, pm.width(), pm.height()), QColor(235, 235, 235))
        show_text = pm.width() >= _TOP_BAR_TEXT_MIN_WIDTH
        if bars:
            ratio_color_pairs = [_top_bar_item_ratio_color(item) for item in bars]
            ratios = [max(0.0, float(pair[0])) for pair in ratio_color_pairs]
            colors = [tuple(int(c) for c in pair[1]) for pair in ratio_color_pairs]
            total_ratio = float(sum(ratios))
            if total_ratio <= 0.0:
                widths = [0] * len(bars)
            else:
                scale = float(pm.width()) / total_ratio
                widths = [max(1, int(round(r * scale))) for r in ratios]
                total_w = int(sum(widths))
                if total_w != int(pm.width()):
                    # 端数誤差は最大割合セグメントに寄せ、極小セグメントの過大化を避ける。
                    anchor = max(range(len(ratios)), key=lambda i: ratios[i])
                    widths[anchor] = max(1, int(widths[anchor] + (pm.width() - total_w)))

            x = 0
            n = len(bars)
            for i in range(n):
                ratio = ratios[i]
                color = colors[i]
                if i == n - 1:
                    w = max(0, int(pm.width() - x))
                else:
                    w = max(0, min(int(widths[i]), int(pm.width() - x)))
                if w <= 0:
                    continue
                painter.fillRect(QRect(x, 0, w, pm.height()), QColor(*color))
                if show_text and w >= _TOP_BAR_TEXT_MIN_SEGMENT_PX:
                    pct = f"{ratio*100:.1f}%"
                    painter.setPen(QColor(255, 255, 255) if sum(color) < 400 else QColor(40, 40, 40))
                    painter.drawText(QRect(x + 2, 0, w - 4, pm.height()), Qt.AlignCenter, pct)
                x += w
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
    finally:
        painter.end()
    return pm


def refresh_top_color_bar(main_window) -> None:
    """バー表示条件が変わったときだけ配色比率バーを再描画する。"""
    # 表示対象がないときはバーを消してキャッシュキーも初期化する。
    bars = getattr(main_window, "_last_top_bars", None)
    if not bars:
        main_window._top_bar_render_key = None
        main_window._last_top_bars_key = None
        main_window.top_colors_bar.clear()
        return
    if not main_window.top_colors_bar.isVisible():
        return

    bars_key = getattr(main_window, "_last_top_bars_key", None)
    if bars_key is None:
        bars_key = tuple(_bar_key_item(item) for item in bars)
        main_window._last_top_bars_key = bars_key
    render_key = (
        int(main_window.top_colors_bar.width()),
        int(main_window.top_colors_bar.height()),
        bars_key,
    )
    # 前回描画と同じ条件なら再レンダリングを省略する。
    if render_key == getattr(main_window, "_top_bar_render_key", None):
        return
    main_window._top_bar_render_key = render_key
    main_window.top_colors_bar.setPixmap(
        render_top_color_bar(
            bars,
            width=main_window.top_colors_bar.width(),
            height=main_window.top_colors_bar.height(),
        )
    )


def _hue_name(hue_deg: float) -> str:
    """色相角(度)を12色相名へ丸めて返す。"""
    idx = int(((float(hue_deg) + 15.0) % 360.0) // 30.0) % len(_HUE_NAME_12)
    return _HUE_NAME_12[idx]


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """RGBタプルを`#RRGGBB`形式文字列へ変換する。"""
    r, g, b = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return f"#{r:02X}{g:02X}{b:02X}"


def _bar_key_item(item: tuple) -> tuple[str, float, tuple[int, int, int]]:
    """配色比率項目を描画キャッシュ比較用キーへ正規化する。"""
    if len(item) == 3:
        name, ratio, color = item
    else:
        name, ratio, color = "", item[0], item[1]
    return (
        str(name),
        round(float(ratio), _COLOR_BAND_KEY_RATIO_DECIMALS),
        tuple(int(c) for c in color),
    )


def _rgb_to_hsv_text(rgb: tuple[int, int, int]) -> str:
    """RGBタプルを表示用HSV文字列へ変換する。"""
    h_deg, s, v = _rgb_to_hsv_parts(rgb)
    return f"HSV({int(round(h_deg)) % 360}, {int(s)}, {int(v)})"


def _normalize_chip_entries(bars: list[tuple]) -> list[dict]:
    """バー項目を一覧表示向けの辞書配列へ変換する。"""
    entries = []
    for idx, item in enumerate(bars, start=1):
        ratio, color = _top_bar_item_ratio_color(item)
        rgb = (int(color[0]), int(color[1]), int(color[2]))
        hue, sat, val = _rgb_to_hsv_parts(rgb)
        hsv_text = f"HSV({int(round(hue)) % 360}, {int(sat)}, {int(val)})"
        base_label = str(item[0]).strip() if len(item) == 3 else ""
        if base_label.startswith("H") and base_label[1:].isdigit():
            label = _hue_name(hue)
        elif base_label:
            label = base_label
        else:
            label = _hue_name(hue)
        entries.append(
            {
                "index": idx - 1,
                "label": f"{label}",
                "ratio": float(ratio),
                "rgb": rgb,
                "hsv_text": hsv_text,
                "hex": _rgb_to_hex(rgb),
                "hue_deg": hue,
            }
        )
    return entries


def _set_color_chip_items(main_window, entries: list[dict]) -> None:
    """配色比率の一覧UIを現在の entries で再構築する。"""
    list_widget = getattr(main_window, "list_color_chips", None)
    if list_widget is None:
        return
    prev_row = int(list_widget.currentRow())
    list_widget.blockSignals(True)
    try:
        list_widget.clear()
        for entry in entries:
            rgb = entry["rgb"]
            item = QListWidgetItem()
            item.setData(Qt.UserRole, int(entry["index"]))
            item.setSizeHint(QSize(0, 34))
            list_widget.addItem(item)

            row = QWidget()
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(6, 4, 6, 4)
            row_l.setSpacing(8)

            swatch = QLabel()
            swatch.setFixedSize(22, 22)
            swatch.setStyleSheet(
                "border:1px solid #9aa1ad; border-radius:3px;"
                f"background: rgb({int(rgb[0])}, {int(rgb[1])}, {int(rgb[2])});"
            )
            row_l.addWidget(swatch, 0)

            text = QLabel(
                f"{entry['index']+1}. {entry['label']}   "
                f"{entry['ratio']*100:.1f}%   "
                f"{entry['hsv_text']}   "
                f"RGB({int(rgb[0])}, {int(rgb[1])}, {int(rgb[2])})   "
                f"{entry['hex']}"
            )
            text.setStyleSheet("color:#111; font-size:12px;")
            text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            row_l.addWidget(text, 1)
            list_widget.setItemWidget(item, row)
        if list_widget.count() > 0 and 0 <= prev_row < list_widget.count():
            list_widget.setCurrentRow(prev_row)
        else:
            # 初回表示時は自動選択しない。ユーザーが明示的に選択したときだけ詳細を出す。
            list_widget.setCurrentRow(-1)
    finally:
        list_widget.blockSignals(False)


def _clear_layout_widgets(layout) -> None:
    """指定レイアウト配下の子ウィジェット/子レイアウトを破棄する。"""
    while layout.count() > 0:
        item = layout.takeAt(0)
        child = item.widget()
        if child is not None:
            child.deleteLater()
            continue
        child_layout = item.layout()
        if child_layout is not None:
            _clear_layout_widgets(child_layout)


def _copy_text_to_clipboard(text: str) -> None:
    """文字列をクリップボードへコピーする。"""
    app = QApplication.instance()
    if app is None:
        return
    app.clipboard().setText(str(text))


def _selected_text_from_widget(widget) -> str:
    """選択中テキストを安全に取り出す。"""
    if widget is None:
        return ""
    if hasattr(widget, "textCursor"):
        try:
            cursor = widget.textCursor()
            if cursor.hasSelection():
                return str(cursor.selectedText()).replace("\u2029", "\n")
            return ""
        except Exception:
            return ""
    if hasattr(widget, "selectedText"):
        try:
            return str(widget.selectedText() or "")
        except Exception:
            return ""
    return ""


def _all_text_from_widget(widget) -> str:
    """ウィジェット全文を安全に取り出す。"""
    if widget is None:
        return ""
    if hasattr(widget, "toPlainText"):
        try:
            return str(widget.toPlainText())
        except Exception:
            return ""
    if hasattr(widget, "text"):
        try:
            return str(widget.text())
        except Exception:
            return ""
    return ""


def _show_copy_menu_for_text_widget(text_widget, pos) -> None:
    """テキストコピー用の右クリックメニューを表示する。"""
    if text_widget is None:
        return
    menu = QMenu(text_widget)
    act_copy_sel = menu.addAction("選択範囲をコピー")
    act_copy_all = menu.addAction("全体をコピー")
    selected = _selected_text_from_widget(text_widget)
    if not selected:
        act_copy_sel.setEnabled(False)
    chosen = menu.exec(text_widget.mapToGlobal(pos))
    if chosen is act_copy_sel:
        _copy_text_to_clipboard(selected)
    elif chosen is act_copy_all:
        _copy_text_to_clipboard(_all_text_from_widget(text_widget))


def _enable_select_copy_on_label(label: QLabel) -> None:
    """ラベルにテキスト選択とコピー用コンテキストメニューを付与する。"""
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    label.setContextMenuPolicy(Qt.CustomContextMenu)
    label.customContextMenuRequested.connect(
        lambda pos, w=label: _show_copy_menu_for_text_widget(w, pos)
    )


def _color_band_sat_threshold_from_ui(main_window) -> int:
    """現在UIで有効な配色比率の彩度しきい値を返す。"""
    try:
        return int(selected_effective_color_band_sat_threshold(main_window))
    except Exception:
        return 0


def _harmony_enabled_from_ui(main_window) -> bool:
    """配色比率詳細で色彩調和を表示するかを返す。"""
    try:
        if selected_color_band_use_wheel_harmony(main_window):
            return selected_wheel_harmony_guide_enabled(main_window)
        return selected_color_band_harmony_guide_enabled(main_window)
    except Exception:
        return False


def _guide_type_from_ui(main_window) -> str:
    """有効な色彩調和ガイド種別を返す。"""
    if not _harmony_enabled_from_ui(main_window):
        return C.WHEEL_HARMONY_GUIDE_NONE
    try:
        if selected_color_band_use_wheel_harmony(main_window):
            value = selected_wheel_harmony_guide_type(main_window)
        else:
            value = selected_color_band_harmony_guide_type(main_window)
    except Exception:
        return C.WHEEL_HARMONY_GUIDE_IDENTITY
    return value if value in C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG else C.WHEEL_HARMONY_GUIDE_IDENTITY


def _hsv_deg_to_rgb(hue_deg: float, sat: int, val: int) -> tuple[int, int, int]:
    """HSV度数指定から RGB タプルへ変換する。"""
    hue_8bit = int(round(float(hue_deg) / 2.0)) % 180
    sat_8bit = int(np.clip(int(sat), 0, 255))
    val_8bit = int(np.clip(int(val), 0, 255))
    return _hsv8_to_rgb_cached(hue_8bit, sat_8bit, val_8bit)


def _rgb_to_hsv_parts(rgb: tuple[int, int, int]) -> tuple[float, int, int]:
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


def _harmony_palette_from_base(
    base_rgb: tuple[int, int, int],
    guide_type: str,
) -> list[tuple[int, tuple[int, int, int], str]]:
    """基準色とガイド種別から調和色パレットを生成する。"""
    offsets = C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG.get(guide_type, (0.0,))
    base_hue, base_sat, base_val = _rgb_to_hsv_parts(base_rgb)
    base_rgb_tuple = (int(base_rgb[0]), int(base_rgb[1]), int(base_rgb[2]))
    sat = int(base_sat)
    val = int(base_val)

    # 常に左端を選択元の原色にする。
    base_item = (int(round(base_hue)) % 360, base_rgb_tuple, "基準色")
    harmony_items: list[tuple[int, tuple[int, int, int], str]] = []
    for offset in offsets:
        off = float(offset)
        if abs(off) < 1e-9 or abs(abs(off) - 360.0) < 1e-9:
            continue
        hue_deg = (base_hue + off) % 360.0
        rgb_tuple = _hsv_deg_to_rgb(hue_deg, sat, val)
        harmony_items.append((int(round(hue_deg)), rgb_tuple, f"調和{len(harmony_items) + 1}"))
    return [base_item, *harmony_items]


def _method_palettes_from_base(
    base_rgb: tuple[int, int, int],
) -> list[tuple[str, list[tuple[int, int, int]]]]:
    """基準色から配色手法ごとの参考パレットを生成する。"""
    base_hue, base_sat, base_val = _rgb_to_hsv_parts(base_rgb)
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
    # 「ドミナントトーン」は色相差を広く取りつつ、トーン（S/V）を揃える。
    tone_sat = int(np.clip(max(72, int(base_sat * 0.55)), 48, 170))
    tone_val = int(np.clip(max(122, int(base_val * 1.05)), 90, 245))
    # 「トーンイントーン」は近接色相で、S/Vも近いレンジに寄せる。
    tint_sat = int(np.clip(max(64, int(base_sat * 0.85)), 52, 210))
    tint_val = int(np.clip(max(96, int(base_val)), 80, 240))

    def mk(offset: float, sat: int, val: int) -> tuple[int, int, int]:
        sat_u8 = int(np.clip(int(sat), 0, 255))
        val_u8 = int(np.clip(int(val), 0, 255))
        return _hsv_deg_to_rgb(base_hue + float(offset), sat_u8, val_u8)

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


def _build_palette_preview_card(rgb: tuple[int, int, int], *, is_base: bool = False) -> QWidget:
    """1色分のプレビューカードを生成する。"""
    r, g, b = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    hex_code = _rgb_to_hex((r, g, b))
    hsv_text = _rgb_to_hsv_text((r, g, b))
    card = QWidget()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    swatch = QLabel()
    swatch.setFixedSize(74, 40)
    border_width = 2 if bool(is_base) else 1
    border_color = "#1e3a8a" if bool(is_base) else "#8f96a3"
    swatch.setStyleSheet(
        f"border:{border_width}px solid {border_color}; border-radius:5px;"
        f"background: rgb({r}, {g}, {b});"
    )
    layout.addWidget(swatch, 0, Qt.AlignHCenter)

    hsv_label = QLabel(hsv_text)
    hsv_label.setStyleSheet("color:#334155; font-size:10px;")
    _enable_select_copy_on_label(hsv_label)
    layout.addWidget(hsv_label, 0, Qt.AlignHCenter)

    rgb_label = QLabel(f"RGB({r}, {g}, {b})")
    rgb_label.setStyleSheet("color:#334155; font-size:10px;")
    _enable_select_copy_on_label(rgb_label)
    layout.addWidget(rgb_label, 0, Qt.AlignHCenter)

    hex_label = QLabel(hex_code)
    hex_label.setStyleSheet("color:#334155; font-size:10px;")
    _enable_select_copy_on_label(hex_label)
    layout.addWidget(hex_label, 0, Qt.AlignHCenter)
    return card


def _set_preview_row(layout, colors: list[tuple[int, int, int]]) -> None:
    """色カード行を差し替える。"""
    if layout is None:
        return
    _clear_layout_widgets(layout)
    for i, rgb in enumerate(colors):
        layout.addWidget(_build_palette_preview_card(rgb, is_base=(i == 0)), 0)
    layout.addStretch(1)


def _build_method_preview_row(
    title: str,
    colors: list[tuple[int, int, int]],
) -> QWidget:
    """配色手法1行分の見出し+色カードを構築する。"""
    row = QWidget()
    layout = QVBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    title_label = QLabel(str(title))
    title_label.setStyleSheet("color:#111; font-size:12px;")
    title_label.setWordWrap(True)
    layout.addWidget(title_label, 0)

    preview = QWidget()
    preview_l = QHBoxLayout(preview)
    preview_l.setContentsMargins(0, 0, 0, 0)
    preview_l.setSpacing(6)
    for i, rgb in enumerate(colors):
        preview_l.addWidget(_build_palette_preview_card(rgb, is_base=(i == 0)), 0)
    preview_l.addStretch(1)
    layout.addWidget(preview, 0)
    return row


def _set_methods_preview(
    layout,
    method_palettes: list[tuple[str, list[tuple[int, int, int]]]],
) -> None:
    """配色手法一覧を描画する。"""
    if layout is None:
        return
    _clear_layout_widgets(layout)
    for method_name, colors in method_palettes:
        layout.addWidget(_build_method_preview_row(method_name, colors), 0)
    layout.addStretch(1)


def _set_color_detail_headers(
    detail_label: QLabel,
    harmony_label: QLabel,
    complement_label: QLabel,
    methods_label: QLabel,
    *,
    detail_text: str = "",
    harmony_text: str = _COLOR_DETAIL_LABEL_HARMONY,
    complement_text: str = _COLOR_DETAIL_LABEL_COMPLEMENT,
    methods_text: str = _COLOR_DETAIL_LABEL_METHODS,
) -> None:
    """詳細領域の見出しテキストを更新する。"""
    detail_label.setText(detail_text)
    harmony_label.setText(harmony_text)
    complement_label.setText(complement_text)
    methods_label.setText(methods_text)


def on_color_chip_selected(main_window, row: int) -> None:
    """配色比率一覧の選択変更に合わせて詳細表示を更新する。"""
    entries = getattr(main_window, "_color_chip_entries", ())
    detail_label = getattr(main_window, "lbl_color_detail_info", None)
    harmony_label = getattr(main_window, "lbl_color_harmony_info", None)
    complement_label = getattr(main_window, "lbl_color_complement_info", None)
    methods_label = getattr(main_window, "lbl_color_methods_info", None)
    harmony_layout = getattr(main_window, "color_harmony_preview_layout", None)
    complement_layout = getattr(main_window, "color_complement_preview_layout", None)
    methods_layout = getattr(main_window, "color_methods_preview_layout", None)
    if (
        detail_label is None
        or harmony_label is None
        or complement_label is None
        or methods_label is None
        or harmony_layout is None
        or complement_layout is None
        or methods_layout is None
    ):
        return
    harmony_enabled = _harmony_enabled_from_ui(main_window)
    guide_type = _guide_type_from_ui(main_window)
    entries_signature = _color_chip_entries_signature(main_window, entries)
    if not entries or row < 0 or row >= len(entries):
        key = (
            "empty",
            entries_signature,
            bool(harmony_enabled),
            str(guide_type),
        )
        if key == getattr(main_window, "_color_palette_render_key", None):
            return
        main_window._color_palette_render_key = key
        main_window._color_detail_has_selection = False
        main_window._color_detail_achromatic = False
        main_window._color_detail_merge_complement = False
        main_window._color_detail_show_info = True
        _set_preview_row(harmony_layout, [])
        _set_preview_row(complement_layout, [])
        _set_methods_preview(methods_layout, [])
        _set_color_detail_headers(
            detail_label,
            harmony_label,
            complement_label,
            methods_label,
            detail_text=_COLOR_DETAIL_HINT_SELECT,
        )
        update_color_band_compact_visibility(main_window)
        return

    entry = entries[int(row)]
    is_achromatic = str(entry.get("label", "")) == "無彩色"
    key = (
        int(row),
        bool(harmony_enabled),
        str(guide_type),
        entries_signature,
        bool(is_achromatic),
    )
    if key == getattr(main_window, "_color_palette_render_key", None):
        return
    main_window._color_palette_render_key = key
    main_window._color_detail_has_selection = True
    main_window._color_detail_achromatic = bool(is_achromatic)
    main_window._color_detail_merge_complement = False
    main_window._color_detail_show_info = bool(is_achromatic)
    _set_preview_row(harmony_layout, [])
    _set_preview_row(complement_layout, [])
    _set_methods_preview(methods_layout, [])

    if is_achromatic:
        _set_color_detail_headers(
            detail_label,
            harmony_label,
            complement_label,
            methods_label,
            detail_text=_COLOR_DETAIL_HINT_ACHROMATIC,
        )
        update_color_band_compact_visibility(main_window)
        return

    guide_name = C.WHEEL_HARMONY_GUIDE_LABELS.get(guide_type, "色彩調和")
    merge_complement = bool(harmony_enabled and guide_type == C.WHEEL_HARMONY_GUIDE_COMPLEMENTARY)
    main_window._color_detail_show_info = False
    _set_color_detail_headers(
        detail_label,
        harmony_label,
        complement_label,
        methods_label,
        harmony_text=(
            f"{_COLOR_DETAIL_LABEL_HARMONY}（{guide_name} / {_COLOR_DETAIL_LABEL_COMPLEMENT}）"
            if merge_complement
            else (
                f"{_COLOR_DETAIL_LABEL_HARMONY}（{guide_name}）"
                if harmony_enabled
                else _COLOR_DETAIL_LABEL_HARMONY
            )
        ),
    )
    harmony_palette = (
        _harmony_palette_from_base(entry["rgb"], guide_type)
        if harmony_enabled and guide_type != C.WHEEL_HARMONY_GUIDE_NONE
        else []
    )
    complement_palette = _harmony_palette_from_base(
        entry["rgb"], C.WHEEL_HARMONY_GUIDE_COMPLEMENTARY
    )
    main_window._color_detail_merge_complement = merge_complement
    method_palettes = _method_palettes_from_base(entry["rgb"])
    harmony_colors = [rgb for _h, rgb, _name in harmony_palette]
    complement_colors = [rgb for _h, rgb, _name in complement_palette]
    _set_preview_row(harmony_layout, harmony_colors)
    _set_preview_row(complement_layout, [] if merge_complement else complement_colors)
    _set_methods_preview(methods_layout, method_palettes)
    update_color_band_compact_visibility(main_window)


def update_color_band_compact_visibility(main_window) -> None:
    """配色比率ドックの高さに応じて表示要素を段階的に切り替える。"""
    dock = getattr(main_window, "dock_color_band", None)
    content = dock.widget() if dock is not None else None
    if content is None:
        return
    body_h = int(content.height())
    # 縮小時の非表示優先順: カラーバー -> 暖色寒色 -> 配色一覧。
    show_top_bar = body_h >= _COLOR_BAND_MIN_H_SHOW_TOP_BAR
    show_warmcool = body_h >= _COLOR_BAND_MIN_H_SHOW_WARMCOOL
    show_chip_list = body_h >= _COLOR_BAND_MIN_H_SHOW_CHIP_LIST
    has_selection = bool(getattr(main_window, "_color_detail_has_selection", False))
    show_detail = bool(body_h >= _COLOR_BAND_MIN_H_SHOW_DETAIL and has_selection)
    show_info = bool(show_detail and getattr(main_window, "_color_detail_show_info", True))
    hide_color_models = bool(getattr(main_window, "_color_detail_achromatic", False))
    merge_complement = bool(getattr(main_window, "_color_detail_merge_complement", False))
    show_color_models = bool(show_detail and not hide_color_models)
    show_harmony = bool(show_color_models and _harmony_enabled_from_ui(main_window))
    # 補色は色彩調和の表示有無に関係なく表示する（統合表示時を除く）。
    show_complement = bool(show_color_models and not merge_complement)
    set_visible_if_changed(getattr(main_window, "lbl_warmcool", None), show_warmcool)
    set_visible_if_changed(getattr(main_window, "top_colors_bar", None), show_top_bar)
    set_visible_if_changed(getattr(main_window, "color_band_splitter", None), show_chip_list)
    set_visible_if_changed(getattr(main_window, "list_color_chips", None), show_chip_list)
    set_visible_if_changed(
        getattr(main_window, "color_detail_scroll", None), show_detail and show_chip_list
    )
    set_visible_if_changed(getattr(main_window, "lbl_color_detail_title", None), show_detail)
    set_visible_if_changed(getattr(main_window, "lbl_color_detail_info", None), show_info)
    harmony_section = getattr(main_window, "color_harmony_section", None)
    complement_section = getattr(main_window, "color_complement_section", None)
    methods_section = getattr(main_window, "color_methods_section", None)
    if harmony_section is not None:
        set_visible_if_changed(harmony_section, show_harmony)
    else:
        set_visible_if_changed(getattr(main_window, "lbl_color_harmony_info", None), show_harmony)
        set_visible_if_changed(getattr(main_window, "color_harmony_preview", None), show_harmony)
    if complement_section is not None:
        set_visible_if_changed(complement_section, show_complement)
    else:
        set_visible_if_changed(
            getattr(main_window, "lbl_color_complement_info", None), show_complement
        )
        set_visible_if_changed(
            getattr(main_window, "color_complement_preview", None), show_complement
        )
    if methods_section is not None:
        set_visible_if_changed(methods_section, show_color_models)
    else:
        set_visible_if_changed(
            getattr(main_window, "lbl_color_methods_info", None), show_color_models
        )
        set_visible_if_changed(
            getattr(main_window, "color_methods_preview", None), show_color_models
        )


def _resolve_color_band_bars(
    main_window,
    snapshot: dict,
) -> tuple[list[tuple], tuple]:
    """配色比率バー表示用の bars / bars_key を snapshot から解決して返す。"""
    bars = snapshot.get("top_colors_filtered")
    bars_key = snapshot.get("top_colors_key")
    if bars is None:
        raw_bars = snapshot.get("top_colors_full")
        if raw_bars is None:
            raw_bars = snapshot.get("top_colors")
            if raw_bars is None:
                raw_bars = _top_bars_chromatic_medoid(
                    snapshot.get("bgr_preview"),
                    sat_threshold=_color_band_sat_threshold_from_ui(main_window),
                )
            snapshot["top_colors_full"] = raw_bars
        if raw_bars is None:
            raw_bars = []
        bars = _filter_invisible_percent_bars(raw_bars)
        bars_key = tuple(_bar_key_item(item) for item in bars)
        snapshot["top_colors_filtered"] = bars
        snapshot["top_colors_key"] = bars_key
    if bars is None:
        bars = []
    if bars_key is None:
        bars_key = tuple(_bar_key_item(item) for item in bars)
        snapshot["top_colors_key"] = bars_key
    return bars, bars_key


def _format_warmcool_text(snapshot: dict) -> str:
    """暖色/寒色/その他の表示文字列を生成する。"""
    return (
        "暖色: "
        f"{float(snapshot.get('warm_ratio', 0.0))*100:.1f}%   "
        f"寒色: {float(snapshot.get('cool_ratio', 0.0))*100:.1f}%   "
        f"その他: {float(snapshot.get('other_ratio', 0.0))*100:.1f}%"
    )


def _sync_color_chip_entries(main_window, bars: list[tuple], bars_key: tuple) -> None:
    """配色比率一覧のデータソースを必要時のみ更新する。"""
    if bars_key != getattr(main_window, "_color_chip_list_source_key", None):
        chip_entries = _normalize_chip_entries(bars)
        main_window._color_chip_entries = chip_entries
        _set_color_chip_items(main_window, chip_entries)
        main_window._color_chip_list_source_key = bars_key
    elif not hasattr(main_window, "_color_chip_entries"):
        main_window._color_chip_entries = []


def _selected_color_chip_row(main_window) -> int:
    """カラー一覧の選択行番号を返す。"""
    list_widget = getattr(main_window, "list_color_chips", None)
    if list_widget is None:
        return -1
    return int(list_widget.currentRow())


def _color_chip_entries_signature(main_window, entries) -> tuple:
    """詳細表示の再描画判定に使う署名を返す。"""
    sig = getattr(main_window, "_color_chip_list_source_key", None)
    if sig is not None:
        return sig
    return tuple(
        (str(e["hex"]), round(float(e["ratio"]), _COLOR_BAND_KEY_RATIO_DECIMALS))
        for e in entries
    )


def render_color_band_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    """配色比率ドックへスナップショットを反映する。"""
    if not is_widget_renderable(getattr(main_window, "dock_color_band", None)):
        return False
    bars, bars_key = _resolve_color_band_bars(main_window, snapshot)
    main_window._last_top_bars = bars
    main_window._last_top_bars_key = bars_key
    refresh_top_color_bar(main_window)
    _sync_color_chip_entries(main_window, bars, bars_key)
    warmcool_text = _format_warmcool_text(snapshot)
    if main_window.lbl_warmcool.text() != warmcool_text:
        main_window.lbl_warmcool.setText(warmcool_text)
    selected_row = _selected_color_chip_row(main_window)
    selection_render_key = (
        bars_key,
        int(selected_row),
        bool(_harmony_enabled_from_ui(main_window)),
        str(_guide_type_from_ui(main_window)),
    )
    if selection_render_key != getattr(main_window, "_color_chip_selection_render_key", None):
        on_color_chip_selected(main_window, selected_row)
        main_window._color_chip_selection_render_key = selection_render_key
    else:
        update_color_band_compact_visibility(main_window)
    return True
