import cv2
import numpy as np
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

from ...analysis.frame_analysis import analyze_bgr_frame
from ...util import constants as C
from ...util.functions import (
    clamp_render_size,
    clear_cvt_color_cache,
    clear_resize_cache,
    is_widget_renderable,
)

_TOP_BAR_MIN_HEIGHT = 12
_TOP_BAR_TEXT_MIN_WIDTH = 240
_TOP_BAR_TEXT_MIN_SEGMENT_PX = 42
_COLOR_BAND_MEDOID_CANDIDATE_LIMIT = 96
# カラー割合の表示優先度:
# 1) カラーバー 2) 暖色寒色 3) 一覧 4) 詳細
# 高さ不足時は下位から順に隠す。
_COLOR_BAND_MIN_H_SHOW_TOP_BAR = 1
_COLOR_BAND_MIN_H_SHOW_WARMCOOL = 56
_COLOR_BAND_MIN_H_SHOW_CHIP_LIST = 120
_COLOR_BAND_MIN_H_SHOW_DETAIL = 210
_SNAPSHOT_DOCK_COLOR = "dock_color"
_SNAPSHOT_DOCK_COLOR_BAND = "dock_color_band"
_SNAPSHOT_DOCK_SCATTER = "dock_scatter"
_SNAPSHOT_DOCK_HIST = "dock_hist"

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


def _medoid_rgb_from_pixels(rgb_pixels: np.ndarray) -> tuple[int, int, int]:
    # 実在色から代表色を選ぶため、量子化色空間で近似メドイドを求める。
    arr = np.asarray(rgb_pixels, dtype=np.uint8)
    if arr.ndim != 2 or arr.shape[0] <= 0 or arr.shape[1] < 3:
        return (0, 0, 0)
    if arr.shape[0] == 1:
        return (int(arr[0, 0]), int(arr[0, 1]), int(arr[0, 2]))

    q = np.right_shift(arr.astype(np.uint16), 3)
    packed = (q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]
    unique_codes, counts = np.unique(packed, return_counts=True)
    if unique_codes.size <= 0:
        return (int(arr[0, 0]), int(arr[0, 1]), int(arr[0, 2]))

    ur = np.right_shift(unique_codes, 10) & 31
    ug = np.right_shift(unique_codes, 5) & 31
    ub = unique_codes & 31
    all_centers = np.stack([ur, ug, ub], axis=1).astype(np.float32) * 8.0 + 4.0
    all_weights = counts.astype(np.float32)

    candidate_count = min(int(_COLOR_BAND_MEDOID_CANDIDATE_LIMIT), int(unique_codes.size))
    if candidate_count < unique_codes.size:
        candidate_idx = np.argpartition(counts, -candidate_count)[-candidate_count:]
    else:
        candidate_idx = np.arange(unique_codes.size, dtype=np.int32)
    cand_centers = all_centers[candidate_idx]

    # 候補色->全量子化色の重み付き距離和を最小化する候補を選ぶ。
    diff = np.abs(cand_centers[:, None, :] - all_centers[None, :, :]).sum(axis=2)
    scores = diff @ all_weights
    best_local = int(np.argmin(scores))
    best_idx = int(candidate_idx[best_local])
    best_code = int(unique_codes[best_idx])
    best_center = all_centers[best_idx]

    members = arr[packed == best_code]
    if members.size <= 0:
        members = arr
    d2 = ((members.astype(np.float32) - best_center) ** 2).sum(axis=1)
    rep = members[int(np.argmin(d2))]
    return (int(rep[0]), int(rep[1]), int(rep[2]))


def _top_bars_chromatic_medoid(
    bgr_preview: np.ndarray | None,
    sat_threshold: int = 0,
) -> list[tuple[str, float, tuple[int, int, int]]]:
    if bgr_preview is None:
        return []
    bgr = np.asarray(bgr_preview)
    if bgr.ndim != 3 or bgr.shape[2] < 3 or bgr.size == 0:
        return []
    if bgr.dtype != np.uint8:
        try:
            bgr = np.clip(np.round(bgr), 0, 255).astype(np.uint8)
        except Exception:
            return []

    try:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    except Exception:
        return []

    h = hsv[:, :, 0].reshape(-1).astype(np.int32)
    s = hsv[:, :, 1].reshape(-1).astype(np.int32)
    if h.size == 0:
        return []

    # 仕様:
    # - しきい値=0: 無彩色を「無彩色」ビンとして含める
    # - しきい値>0: 低彩度(<=しきい値)は除外し、有彩色のみで100%正規化する
    sat_th = int(max(0, min(255, int(sat_threshold))))
    rgb_all = bgr.reshape(-1, 3)[:, ::-1]
    if sat_th <= 0:
        achro_bin = 12
        seg = np.full(h.shape, achro_bin, dtype=np.int32)
        chroma_mask = s > 0
        seg[chroma_mask] = ((h[chroma_mask] * 2) // 30) % 12
        counts = np.bincount(seg, minlength=13)[:13]
        total = int(counts.sum())
        if total <= 0:
            return []

        order = np.argsort(counts)[::-1]
        bars: list[tuple[str, float, tuple[int, int, int]]] = []
        for idx in order:
            cnt = int(counts[idx])
            if cnt <= 0:
                continue
            ratio = float(cnt) / float(total)
            members = rgb_all[seg == int(idx)]
            rgb = _medoid_rgb_from_pixels(members)
            label = "無彩色" if int(idx) == achro_bin else _HUE_NAME_12[int(idx) % 12]
            bars.append((label, ratio, rgb))
            if len(bars) >= int(C.TOP_COLORS_COUNT):
                break
        return bars

    chroma_mask = s > sat_th
    if not np.any(chroma_mask):
        return []

    h_chroma = h[chroma_mask]
    seg = ((h_chroma * 2) // 30) % 12
    counts = np.bincount(seg, minlength=12)[:12]
    total = int(counts.sum())
    if total <= 0:
        return []
    rgb_chroma = rgb_all[chroma_mask]

    order = np.argsort(counts)[::-1]
    bars: list[tuple[str, float, tuple[int, int, int]]] = []
    for idx in order:
        cnt = int(counts[idx])
        if cnt <= 0:
            continue
        ratio = float(cnt) / float(total)
        members = rgb_chroma[seg == int(idx)]
        rgb = _medoid_rgb_from_pixels(members)
        label = _HUE_NAME_12[int(idx) % 12]
        bars.append((label, ratio, rgb))
        if len(bars) >= int(C.TOP_COLORS_COUNT):
            break
    return bars


def _top_bar_item_ratio_color(item: tuple) -> tuple[float, tuple[int, int, int]]:
    if len(item) == 3:
        _, ratio, color = item
    else:
        ratio, color = item
    return float(ratio), tuple(int(c) for c in color)


def render_top_color_bar(
    bars: list[tuple], width: int = 300, height: int = C.TOP_COLOR_BAR_HEIGHT
) -> QPixmap:
    safe_w, safe_h = clamp_render_size(width, max(_TOP_BAR_MIN_HEIGHT, height))
    pm = QPixmap(safe_w, safe_h)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    try:
        painter.fillRect(QRect(0, 0, pm.width(), pm.height()), QColor(235, 235, 235))
        show_text = pm.width() >= _TOP_BAR_TEXT_MIN_WIDTH
        x = 0
        remaining = pm.width()
        for item in bars:
            ratio, color = _top_bar_item_ratio_color(item)
            w = int(round(pm.width() * ratio))
            w = max(1, min(w, remaining))
            painter.fillRect(QRect(x, 0, w, pm.height()), QColor(*color))
            if show_text and w >= _TOP_BAR_TEXT_MIN_SEGMENT_PX:
                pct = f"{ratio*100:.1f}%"
                painter.setPen(QColor(255, 255, 255) if sum(color) < 400 else QColor(40, 40, 40))
                painter.drawText(QRect(x + 2, 0, w - 4, pm.height()), Qt.AlignCenter, pct)
            x += w
            remaining = pm.width() - x
            if remaining <= 0:
                break
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
    finally:
        painter.end()
    return pm


def refresh_top_color_bar(main_window) -> None:
    # 表示対象がないときはバーを消してキャッシュキーも初期化する。
    bars = getattr(main_window, "_last_top_bars", None)
    if not bars:
        main_window._top_bar_render_key = None
        main_window.top_colors_bar.clear()
        return
    if not main_window.top_colors_bar.isVisible():
        return

    render_key = (
        int(main_window.top_colors_bar.width()),
        int(main_window.top_colors_bar.height()),
        tuple(_bar_key_item(item) for item in bars),
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
    idx = int(((float(hue_deg) + 15.0) % 360.0) // 30.0) % len(_HUE_NAME_12)
    return _HUE_NAME_12[idx]


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return f"#{r:02X}{g:02X}{b:02X}"


def _bar_key_item(item: tuple) -> tuple[str, float, tuple[int, int, int]]:
    if len(item) == 3:
        name, ratio, color = item
    else:
        name, ratio, color = "", item[0], item[1]
    return (
        str(name),
        round(float(ratio), 6),
        tuple(int(c) for c in color),
    )


def _rgb_to_hsv_text(rgb: tuple[int, int, int]) -> str:
    h_deg, s, v = _rgb_to_hsv_parts(rgb)
    return f"HSV({int(round(h_deg)) % 360}, {int(s)}, {int(v)})"


def _normalize_chip_entries(bars: list[tuple]) -> list[dict]:
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
    app = QApplication.instance()
    if app is None:
        return
    app.clipboard().setText(str(text))


def _selected_text_from_widget(widget) -> str:
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
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    label.setContextMenuPolicy(Qt.CustomContextMenu)
    label.customContextMenuRequested.connect(
        lambda pos, w=label: _show_copy_menu_for_text_widget(w, pos)
    )


def _color_band_sat_threshold_from_ui(main_window) -> int:
    use_wheel_widget = getattr(main_window, "chk_color_band_use_wheel_sat_threshold", None)
    use_wheel = bool(use_wheel_widget is not None and use_wheel_widget.isChecked())
    if use_wheel:
        wheel_spin = getattr(main_window, "spin_wheel_sat_threshold", None)
        if wheel_spin is None:
            return 0
        try:
            return int(wheel_spin.value())
        except Exception:
            return 0
    own_spin = getattr(main_window, "spin_color_band_sat_threshold", None)
    if own_spin is None:
        return 0
    try:
        return int(own_spin.value())
    except Exception:
        return 0


def _harmony_enabled_from_ui(main_window) -> bool:
    use_wheel_widget = getattr(main_window, "chk_color_band_use_wheel_harmony", None)
    use_wheel = bool(use_wheel_widget is not None and use_wheel_widget.isChecked())
    if use_wheel:
        enabled_widget = getattr(main_window, "chk_wheel_harmony_guide", None)
        return bool(enabled_widget is not None and enabled_widget.isChecked())
    enabled_widget = getattr(main_window, "chk_color_band_harmony_guide", None)
    return bool(enabled_widget is not None and enabled_widget.isChecked())


def _guide_type_from_ui(main_window) -> str:
    if not _harmony_enabled_from_ui(main_window):
        return C.WHEEL_HARMONY_GUIDE_NONE
    use_wheel_widget = getattr(main_window, "chk_color_band_use_wheel_harmony", None)
    use_wheel = bool(use_wheel_widget is not None and use_wheel_widget.isChecked())
    combo = (
        getattr(main_window, "combo_wheel_harmony_guide", None)
        if use_wheel
        else getattr(main_window, "combo_color_band_harmony_guide", None)
    )
    if combo is None:
        return C.WHEEL_HARMONY_GUIDE_IDENTITY
    value = combo.currentData()
    return (
        value
        if value in C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG
        else C.WHEEL_HARMONY_GUIDE_IDENTITY
    )


def _hsv_deg_to_rgb(hue_deg: float, sat: int, val: int) -> tuple[int, int, int]:
    hue_8bit = int(round(float(hue_deg) / 2.0)) % 180
    sat_8bit = int(np.clip(int(sat), 0, 255))
    val_8bit = int(np.clip(int(val), 0, 255))
    rgb = cv2.cvtColor(
        np.uint8([[[hue_8bit, sat_8bit, val_8bit]]]),
        cv2.COLOR_HSV2RGB,
    )[0, 0]
    return (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def _rgb_to_hsv_parts(rgb: tuple[int, int, int]) -> tuple[float, int, int]:
    r, g, b = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    hsv = cv2.cvtColor(np.uint8([[[r, g, b]]]), cv2.COLOR_RGB2HSV)[0, 0]
    return float(int(hsv[0]) * 2), int(hsv[1]), int(hsv[2])


def _harmony_palette_from_base(
    base_rgb: tuple[int, int, int],
    guide_type: str,
) -> list[tuple[int, tuple[int, int, int], str]]:
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
    base_hue, base_sat, base_val = _rgb_to_hsv_parts(base_rgb)
    base_rgb_tuple = (int(base_rgb[0]), int(base_rgb[1]), int(base_rgb[2]))
    sat_mid = max(96, int(base_sat))
    val_mid = max(112, int(base_val))
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
    neutral_lo = int(np.clip(neutral - 52, 0, 255))
    tone_sat = int(np.clip(max(88, int(base_sat * 0.78)), 56, 196))
    tone_val = int(np.clip(max(120, int(base_val * 0.96)), 76, 240))

    def mk(offset: float, sat: int, val: int) -> tuple[int, int, int]:
        return _hsv_deg_to_rgb(base_hue + float(offset), sat, val)

    return [
        (
            "トーンオントーン",
            [
                base_rgb_tuple,
                mk(0.0, sat_mid - 64, val_mid + 44),
                mk(0.0, sat_mid - 26, val_mid + 16),
                mk(0.0, sat_mid + 44, val_mid - 26),
            ],
        ),
        (
            "トーンイントーン",
            [
                base_rgb_tuple,
                mk(-30.0, sat_mid, val_mid - 12),
                mk(30.0, sat_mid, val_mid + 12),
                mk(60.0, sat_mid, val_mid),
            ],
        ),
        (
            "ドミナントカラー",
            [
                base_rgb_tuple,
                mk(18.0, sat_mid - 28, val_mid + 14),
                mk(-14.0, sat_mid - 36, val_mid - 8),
                mk(110.0, sat_mid + 12, val_mid - 14),
            ],
        ),
        (
            "ドミナントトーン",
            [
                base_rgb_tuple,
                mk(-26.0, tone_sat, tone_val),
                mk(26.0, tone_sat, tone_val),
                mk(52.0, tone_sat, tone_val),
            ],
        ),
        (
            "セパレーション",
            [
                base_rgb_tuple,
                (neutral_hi, neutral_hi, neutral_hi),
                mk(180.0, sat_mid, val_mid),
                (neutral_lo, neutral_lo, neutral_lo),
            ],
        ),
        (
            "アクセントカラー",
            [
                base_rgb_tuple,
                (neutral_hi, neutral_hi, neutral_hi),
                (neutral, neutral, neutral),
                (neutral_lo, neutral_lo, neutral_lo),
            ],
        ),
    ]


def _build_palette_preview_card(rgb: tuple[int, int, int], *, is_base: bool = False) -> QWidget:
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
    if layout is None:
        return
    _clear_layout_widgets(layout)
    for method_name, colors in method_palettes:
        layout.addWidget(_build_method_preview_row(method_name, colors), 0)
    layout.addStretch(1)


def _set_palette_preview(
    main_window,
    *,
    harmony_palette: list[tuple[int, tuple[int, int, int], str]],
    complement_palette: list[tuple[int, tuple[int, int, int], str]],
    method_palettes: list[tuple[str, list[tuple[int, int, int]]]],
) -> None:
    harmony_layout = getattr(main_window, "color_harmony_preview_layout", None)
    complement_layout = getattr(main_window, "color_complement_preview_layout", None)
    methods_layout = getattr(main_window, "color_methods_preview_layout", None)
    harmony_colors = [rgb for _h, rgb, _name in harmony_palette]
    complement_colors = [rgb for _h, rgb, _name in complement_palette]
    _set_preview_row(harmony_layout, harmony_colors)
    _set_preview_row(complement_layout, complement_colors)
    _set_methods_preview(methods_layout, method_palettes)


def on_color_chip_selected(main_window, row: int) -> None:
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
    if not entries or row < 0 or row >= len(entries):
        key = (
            "empty",
            len(entries),
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
        detail_label.setText("一覧から色を選択してください。")
        harmony_label.setText("色彩調和")
        complement_label.setText("補色")
        methods_label.setText("配色手法")
        update_color_band_compact_visibility(main_window)
        return

    entry = entries[int(row)]
    is_achromatic = str(entry.get("label", "")) == "無彩色"
    key = (
        int(row),
        bool(harmony_enabled),
        str(guide_type),
        tuple((str(e["hex"]), round(float(e["ratio"]), 4)) for e in entries),
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
        detail_label.setText("無彩色が選択されています。調和色は表示されません。")
        harmony_label.setText("色彩調和")
        complement_label.setText("補色")
        methods_label.setText("配色手法")
        update_color_band_compact_visibility(main_window)
        return

    guide_name = C.WHEEL_HARMONY_GUIDE_LABELS.get(guide_type, "色彩調和")
    merge_complement = bool(harmony_enabled and guide_type == C.WHEEL_HARMONY_GUIDE_COMPLEMENTARY)
    detail_label.setText("")
    main_window._color_detail_show_info = False
    harmony_label.setText(
        f"色彩調和（{guide_name} / 補色）"
        if merge_complement
        else (f"色彩調和（{guide_name}）" if harmony_enabled else "色彩調和")
    )
    complement_label.setText("補色")
    methods_label.setText("配色手法")
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
    _set_palette_preview(
        main_window,
        harmony_palette=harmony_palette,
        complement_palette=([] if merge_complement else complement_palette),
        method_palettes=method_palettes,
    )
    update_color_band_compact_visibility(main_window)


def _set_visible_if_changed(widget, visible: bool) -> None:
    if widget is None:
        return
    show = bool(visible)
    if widget.isHidden() == (not show):
        return
    widget.setVisible(show)


def update_color_band_compact_visibility(main_window) -> None:
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
    # 補色は色彩調和の表示ON/OFFに依存させず常時表示する（統合時を除く）。
    show_complement = bool(show_color_models and not merge_complement)
    _set_visible_if_changed(getattr(main_window, "lbl_warmcool", None), show_warmcool)
    _set_visible_if_changed(getattr(main_window, "top_colors_bar", None), show_top_bar)
    _set_visible_if_changed(getattr(main_window, "color_band_splitter", None), show_chip_list)
    _set_visible_if_changed(getattr(main_window, "list_color_chips", None), show_chip_list)
    _set_visible_if_changed(
        getattr(main_window, "color_detail_scroll", None), show_detail and show_chip_list
    )
    _set_visible_if_changed(getattr(main_window, "lbl_color_detail_title", None), show_detail)
    _set_visible_if_changed(getattr(main_window, "lbl_color_detail_info", None), show_info)
    harmony_section = getattr(main_window, "color_harmony_section", None)
    complement_section = getattr(main_window, "color_complement_section", None)
    methods_section = getattr(main_window, "color_methods_section", None)
    if harmony_section is not None:
        _set_visible_if_changed(harmony_section, show_harmony)
    else:
        _set_visible_if_changed(getattr(main_window, "lbl_color_harmony_info", None), show_harmony)
        _set_visible_if_changed(getattr(main_window, "color_harmony_preview", None), show_harmony)
    if complement_section is not None:
        _set_visible_if_changed(complement_section, show_complement)
    else:
        _set_visible_if_changed(
            getattr(main_window, "lbl_color_complement_info", None), show_complement
        )
        _set_visible_if_changed(
            getattr(main_window, "color_complement_preview", None), show_complement
        )
    if methods_section is not None:
        _set_visible_if_changed(methods_section, show_color_models)
    else:
        _set_visible_if_changed(
            getattr(main_window, "lbl_color_methods_info", None), show_color_models
        )
        _set_visible_if_changed(
            getattr(main_window, "color_methods_preview", None), show_color_models
        )


def _new_empty_result_snapshot() -> dict:
    return {
        "bgr_preview": None,
        "hist": None,
        "sv": None,
        "rgb": None,
        "h_plane": None,
        "s_plane": None,
        "v_plane": None,
        "h_hist": None,
        "s_hist": None,
        "v_hist": None,
        "top_colors": None,
        "top_colors_full": None,
        "warm_ratio": 0.0,
        "cool_ratio": 0.0,
        "other_ratio": 0.0,
        "dt_ms": 0.0,
        "cap": None,
        "graph_update": False,
    }


def _ensure_snapshot_state(main_window) -> None:
    if not hasattr(main_window, "_latest_result_snapshot"):
        main_window._latest_result_snapshot = _new_empty_result_snapshot()
    if not hasattr(main_window, "_latest_result_version"):
        main_window._latest_result_version = 0
    if not hasattr(main_window, "_dock_rendered_version"):
        main_window._dock_rendered_version = {}


def _store_result_snapshot(
    main_window,
    res: dict,
    *,
    update_bgr: bool = True,
    bump_version: bool = True,
) -> tuple[dict, int]:
    _ensure_snapshot_state(main_window)
    snap = dict(main_window._latest_result_snapshot)

    if update_bgr:
        bgr_preview = res.get("bgr_preview")
        if bgr_preview is not None:
            snap["bgr_preview"] = bgr_preview
    if res.get("cap") is not None:
        snap["cap"] = res.get("cap")
    if res.get("dt_ms") is not None:
        snap["dt_ms"] = float(res.get("dt_ms", 0.0))

    if bool(res.get("graph_update")):
        snap["top_colors_full"] = None
        if res.get("hist") is not None:
            snap["hist"] = res.get("hist")
            snap["warm_ratio"] = float(res.get("warm_ratio", snap["warm_ratio"]))
            snap["cool_ratio"] = float(res.get("cool_ratio", snap["cool_ratio"]))
            snap["other_ratio"] = float(res.get("other_ratio", snap["other_ratio"]))
        if res.get("top_colors") is not None:
            snap["top_colors"] = res.get("top_colors")
        for key in ("sv", "rgb", "h_plane", "s_plane", "v_plane", "h_hist", "s_hist", "v_hist"):
            value = res.get(key)
            if value is not None:
                snap[key] = value

    if bump_version:
        main_window._latest_result_version = int(main_window._latest_result_version) + 1
    main_window._latest_result_snapshot = snap
    return snap, int(main_window._latest_result_version)


def _dock_name_from_object(main_window, dock) -> str | None:
    dock_name_map = getattr(main_window, "_dock_name_by_object", None)
    if isinstance(dock_name_map, dict):
        return dock_name_map.get(dock)
    for name, mapped in getattr(main_window, "_dock_map", {}).items():
        if mapped is dock:
            return name
    return None


def _mark_docks_rendered(main_window, version: int, dock_names: set[str]) -> None:
    if not dock_names:
        return
    _ensure_snapshot_state(main_window)
    for name in dock_names:
        main_window._dock_rendered_version[name] = int(version)


def _render_color_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    hist = snapshot.get("hist")
    if hist is None or not is_widget_renderable(main_window.dock_color):
        return False
    main_window.wheel.update_hist(hist)
    return True


def _render_color_band_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    if not is_widget_renderable(getattr(main_window, "dock_color_band", None)):
        return False
    bars = snapshot.get("top_colors_full")
    if bars is None:
        bars = _top_bars_chromatic_medoid(
            snapshot.get("bgr_preview"),
            sat_threshold=_color_band_sat_threshold_from_ui(main_window),
        )
        snapshot["top_colors_full"] = bars
    if bars is None:
        bars = []
    main_window._last_top_bars = bars
    refresh_top_color_bar(main_window)
    bars_key = tuple(_bar_key_item(item) for item in bars)
    if bars_key != getattr(main_window, "_color_chip_list_source_key", None):
        chip_entries = _normalize_chip_entries(bars)
        main_window._color_chip_entries = chip_entries
        _set_color_chip_items(main_window, chip_entries)
        main_window._color_chip_list_source_key = bars_key
    elif not hasattr(main_window, "_color_chip_entries"):
        main_window._color_chip_entries = []
    warmcool_text = (
        "暖色: "
        f"{float(snapshot.get('warm_ratio', 0.0))*100:.1f}%   "
        f"寒色: {float(snapshot.get('cool_ratio', 0.0))*100:.1f}%   "
        f"その他: {float(snapshot.get('other_ratio', 0.0))*100:.1f}%"
    )
    if main_window.lbl_warmcool.text() != warmcool_text:
        main_window.lbl_warmcool.setText(warmcool_text)
    selected_row = -1
    list_widget = getattr(main_window, "list_color_chips", None)
    if list_widget is not None:
        selected_row = int(list_widget.currentRow())
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


def _render_scatter_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    sv = snapshot.get("sv")
    rgb = snapshot.get("rgb")
    if sv is None or rgb is None or not is_widget_renderable(main_window.dock_scatter):
        return False
    main_window.scatter.update_scatter(sv, rgb)
    return True


def _apply_hsv_hist_fallback_from_bgr(snapshot: dict, bgr_preview) -> tuple[object, object, object]:
    h_hist = snapshot.get("h_hist")
    s_hist = snapshot.get("s_hist")
    v_hist = snapshot.get("v_hist")
    h_plane = snapshot.get("h_plane")
    s_plane = snapshot.get("s_plane")
    v_plane = snapshot.get("v_plane")
    need_h_fallback = h_hist is None and h_plane is None
    need_s_fallback = s_hist is None and s_plane is None
    need_v_fallback = v_hist is None and v_plane is None
    if (
        (need_h_fallback or need_s_fallback or need_v_fallback)
        and bgr_preview is not None
        and bgr_preview.size > 0
    ):
        try:
            h_full, s_full, v_full = cv2.split(cv2.cvtColor(bgr_preview, cv2.COLOR_BGR2HSV))
            if need_h_fallback:
                h_hist = np.bincount(h_full[s_full > 0].ravel(), minlength=180)[:180].astype(
                    np.int64
                )
                snapshot["h_hist"] = h_hist
            if need_s_fallback:
                s_hist = np.bincount(s_full.ravel(), minlength=256)[:256].astype(np.int64)
                snapshot["s_hist"] = s_hist
            if need_v_fallback:
                v_hist = np.bincount(v_full.ravel(), minlength=256)[:256].astype(np.int64)
                snapshot["v_hist"] = v_hist
        except Exception:
            pass
    return h_hist, s_hist, v_hist


def _render_hist_dock_from_snapshot(main_window, snapshot: dict) -> bool:
    if not is_widget_renderable(main_window.dock_hist):
        return False
    bgr_preview = snapshot.get("bgr_preview")
    h_hist, s_hist, v_hist = _apply_hsv_hist_fallback_from_bgr(snapshot, bgr_preview)
    h_plane = snapshot.get("h_plane")
    s_plane = snapshot.get("s_plane")
    v_plane = snapshot.get("v_plane")

    if h_hist is not None:
        main_window.hist_h.update_from_hist(h_hist)
    elif h_plane is not None:
        main_window.hist_h.update_from_values(h_plane)
    else:
        return False
    if s_hist is not None:
        main_window.hist_s.update_from_hist(s_hist)
    elif s_plane is not None:
        main_window.hist_s.update_from_values(s_plane)
    else:
        return False
    if v_hist is not None:
        main_window.hist_v.update_from_hist(v_hist)
    elif v_plane is not None:
        main_window.hist_v.update_from_values(v_plane)
    else:
        return False

    # H/S/V のY軸上限を揃えて、チャネル間の相対比較をしやすくする。
    shared_max_y = max(
        int(main_window.hist_h.bucketed_max()),
        int(main_window.hist_s.bucketed_max()),
        int(main_window.hist_v.bucketed_max()),
    )
    for hist_view in (main_window.hist_h, main_window.hist_s, main_window.hist_v):
        hist_view.set_shared_max_y(shared_max_y if shared_max_y > 0 else None)
    return True


def _update_single_image_dock_from_frame(main_window, target_dock, bgr_preview) -> bool:
    if bgr_preview is None:
        return False
    if not is_widget_renderable(target_dock):
        return False
    dock_widget = target_dock.widget()
    if not is_widget_renderable(dock_widget):
        return False
    for dock, update_fn, after_fn in getattr(main_window, "_image_update_targets", ()):
        if dock is not target_dock:
            continue
        update_fn(bgr_preview)
        if after_fn is not None:
            after_fn()
        return True
    return False


def update_image_docks_from_frame(main_window, bgr_preview) -> set[str]:
    # 可視ドックだけ更新して不要な画像処理を避ける。
    if bgr_preview is None:
        return set()
    updated_docks: set[str] = set()
    for dock, update_fn, after_fn in getattr(main_window, "_image_update_targets", ()):
        if not is_widget_renderable(dock):
            continue
        dock_widget = dock.widget()
        if not is_widget_renderable(dock_widget):
            continue
        update_fn(bgr_preview)
        if after_fn is not None:
            after_fn()
        name = _dock_name_from_object(main_window, dock)
        if name is not None:
            updated_docks.add(name)
    return updated_docks


def _snapshot_has_graph_data_for_dock(snapshot: dict, dock_name: str) -> bool:
    if dock_name in (_SNAPSHOT_DOCK_COLOR, _SNAPSHOT_DOCK_COLOR_BAND):
        return snapshot.get("hist") is not None
    if dock_name == _SNAPSHOT_DOCK_SCATTER:
        return snapshot.get("sv") is not None and snapshot.get("rgb") is not None
    if dock_name == _SNAPSHOT_DOCK_HIST:
        has_h = snapshot.get("h_hist") is not None or snapshot.get("h_plane") is not None
        has_s = snapshot.get("s_hist") is not None or snapshot.get("s_plane") is not None
        has_v = snapshot.get("v_hist") is not None or snapshot.get("v_plane") is not None
        return has_h and has_s and has_v
    return True


def _is_worker_running(main_window) -> bool:
    thread = getattr(main_window.worker, "_thread", None)
    return bool(thread is not None and thread.is_alive())


def _ensure_snapshot_graph_data_for_dock(main_window, dock_name: str) -> bool:
    _ensure_snapshot_state(main_window)
    snapshot = main_window._latest_result_snapshot
    if _snapshot_has_graph_data_for_dock(snapshot, dock_name):
        return True
    if _is_worker_running(main_window):
        return False

    bgr_preview = snapshot.get("bgr_preview")
    if bgr_preview is None:
        bgr_preview, cap, err = main_window.worker.capture_once()
        if bgr_preview is None:
            if err:
                main_window.on_status(err)
            return False
        snapshot, _ = _store_result_snapshot(
            main_window,
            {"bgr_preview": bgr_preview, "cap": cap, "graph_update": False},
            update_bgr=True,
            bump_version=True,
        )

    try:
        graph_res = analyze_bgr_frame(
            bgr=bgr_preview,
            sample_points=int(main_window.spin_points.value()),
            wheel_sat_threshold=main_window._selected_wheel_sat_threshold(),
            max_dim=int(main_window.worker.cfg.max_dim),
        )
    except Exception:
        return False
    if graph_res is None:
        return False
    graph_res["graph_update"] = True
    _store_result_snapshot(main_window, graph_res, update_bgr=False, bump_version=True)
    return _snapshot_has_graph_data_for_dock(main_window._latest_result_snapshot, dock_name)


def restore_dock_from_snapshot(main_window, dock) -> None:
    if dock is None or not dock.isVisible():
        return
    dock_name = _dock_name_from_object(main_window, dock)
    if dock_name is None:
        return

    _ensure_snapshot_state(main_window)
    snapshot_version = int(main_window._latest_result_version)
    if snapshot_version <= 0:
        return
    rendered_version = int(main_window._dock_rendered_version.get(dock_name, 0))
    if rendered_version == snapshot_version:
        return

    if dock_name in (
        _SNAPSHOT_DOCK_COLOR,
        _SNAPSHOT_DOCK_COLOR_BAND,
        _SNAPSHOT_DOCK_SCATTER,
        _SNAPSHOT_DOCK_HIST,
    ):
        if not _ensure_snapshot_graph_data_for_dock(main_window, dock_name):
            return

    snapshot = main_window._latest_result_snapshot
    updated = False
    if dock_name == _SNAPSHOT_DOCK_COLOR:
        updated = _render_color_dock_from_snapshot(main_window, snapshot)
    elif dock_name == _SNAPSHOT_DOCK_COLOR_BAND:
        updated = _render_color_band_dock_from_snapshot(main_window, snapshot)
    elif dock_name == _SNAPSHOT_DOCK_SCATTER:
        updated = _render_scatter_dock_from_snapshot(main_window, snapshot)
    elif dock_name == _SNAPSHOT_DOCK_HIST:
        updated = _render_hist_dock_from_snapshot(main_window, snapshot)
    else:
        updated = _update_single_image_dock_from_frame(
            main_window,
            dock,
            snapshot.get("bgr_preview"),
        )

    if updated:
        _mark_docks_rendered(main_window, int(main_window._latest_result_version), {dock_name})


def on_result(main_window, res: dict):
    # 例外時でも inflight フラグを解除するため finally で終端する。
    try:
        snapshot, snapshot_version = _store_result_snapshot(main_window, res)
        rendered_docks: set[str] = set()
        bgr_preview = res.get("bgr_preview")
        if main_window.preview_window.isVisible() and bgr_preview is not None:
            main_window.preview_window.update_preview(bgr_preview)

        # graph_update が False のときはグラフ系更新をスキップする。
        if res["graph_update"]:
            if _render_color_dock_from_snapshot(main_window, snapshot):
                rendered_docks.add(_SNAPSHOT_DOCK_COLOR)
            if _render_color_band_dock_from_snapshot(main_window, snapshot):
                rendered_docks.add(_SNAPSHOT_DOCK_COLOR_BAND)
            if _render_scatter_dock_from_snapshot(main_window, snapshot):
                rendered_docks.add(_SNAPSHOT_DOCK_SCATTER)
            if _render_hist_dock_from_snapshot(main_window, snapshot):
                rendered_docks.add(_SNAPSHOT_DOCK_HIST)

        rendered_docks.update(update_image_docks_from_frame(main_window, bgr_preview))
        _mark_docks_rendered(main_window, snapshot_version, rendered_docks)
    finally:
        # 同一フレーム内で使った縮小キャッシュを破棄して次フレームへ持ち越さない。
        clear_cvt_color_cache()
        clear_resize_cache()
        main_window.worker.mark_result_consumed()
