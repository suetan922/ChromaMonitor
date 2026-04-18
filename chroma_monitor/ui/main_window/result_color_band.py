"""配色比率ドックの描画と詳細UI更新を扱う補助処理。"""

from dataclasses import dataclass

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidgetItem, QSizePolicy, QWidget

from ...analysis.frame_analysis import compute_top_bars_chromatic_medoid
from ...util import constants as C
from ...util.image_ops import clamp_render_size
from ...util.qt_helpers import is_widget_renderable, set_visible_if_changed
from ...util.theme import UiTheme, get_ui_theme, qcolor
from .result_color_band_palette import (
    COLOR_BAND_KEY_RATIO_DECIMALS,
    bar_key_item,
    filter_invisible_percent_bars,
    format_warmcool_text,
    harmony_palette_from_base,
    method_palettes_from_base,
    normalize_chip_entries,
    top_bar_item_ratio_color,
)
from .result_color_band_widgets import set_methods_preview, set_preview_row
from .settings_values import (
    selected_color_band_harmony_guide_enabled,
    selected_color_band_harmony_guide_type,
    selected_color_band_use_wheel_harmony,
    selected_effective_color_band_sat_threshold_safe,
    selected_wheel_harmony_guide_enabled,
    selected_wheel_harmony_guide_type,
)

_TOP_BAR_MIN_HEIGHT = 12
_TOP_BAR_TEXT_MIN_WIDTH = 240
_TOP_BAR_TEXT_MIN_SEGMENT_PX = 42
_TOP_BAR_LIGHT_TEXT_RGB_SUM_THRESHOLD = 400
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


@dataclass(frozen=True, slots=True)
class ColorBandDetailState:
    """配色詳細表示で必要な計算済み状態。"""

    render_key: tuple
    has_selection: bool = False
    achromatic: bool = False
    merge_complement: bool = False
    show_info: bool = True
    detail_text: str = _COLOR_DETAIL_HINT_SELECT
    harmony_text: str = _COLOR_DETAIL_LABEL_HARMONY
    complement_text: str = _COLOR_DETAIL_LABEL_COMPLEMENT
    methods_text: str = _COLOR_DETAIL_LABEL_METHODS
    harmony_colors: tuple[tuple[int, int, int], ...] = ()
    complement_colors: tuple[tuple[int, int, int], ...] = ()
    method_palettes: tuple[tuple[str, tuple[tuple[int, int, int], ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class ColorBandCompactVisibilityState:
    """配色比率ドックの compact 表示判定結果。"""

    show_top_bar: bool
    show_warmcool: bool
    show_chip_list: bool
    show_detail: bool
    show_info: bool
    show_harmony: bool
    show_complement: bool
    show_color_models: bool


@dataclass(frozen=True, slots=True)
class ColorBandDetailWidgets:
    """配色詳細更新に必要なウィジェット参照。"""

    detail_label: QLabel
    harmony_label: QLabel
    complement_label: QLabel
    methods_label: QLabel
    harmony_layout: object
    complement_layout: object
    methods_layout: object


@dataclass(frozen=True, slots=True)
class ColorBandVisibilityWidgets:
    """compact 表示切替に必要なウィジェット参照。"""

    warmcool_label: object
    top_colors_bar: object
    splitter: object
    chip_list: object
    detail_scroll: object
    detail_title: object
    detail_info: object
    harmony_section: object
    complement_section: object
    methods_section: object
    harmony_label: object
    harmony_preview: object
    complement_label: object
    complement_preview: object
    methods_label: object
    methods_preview: object


@dataclass(frozen=True, slots=True)
class ColorBandSelectionInfo:
    """配色詳細計算に使う選択行情報。"""

    entry: dict
    render_key: tuple
    achromatic: bool


def _default_color_band_detail_state() -> ColorBandDetailState:
    """未選択時の既定詳細状態を返す。"""
    return ColorBandDetailState(render_key=("initial",))


def _theme_from(main_window) -> UiTheme:
    """現在のUIテーマを返す。"""
    return getattr(main_window, "_ui_theme", None) or get_ui_theme()


def render_top_color_bar(
    bars: list[tuple],
    *,
    theme: UiTheme,
    width: int = 300,
    height: int = C.TOP_COLOR_BAR_HEIGHT,
) -> QPixmap:
    """配色比率バーのピクスマップを描画して返す。"""
    safe_w, safe_h = clamp_render_size(width, max(_TOP_BAR_MIN_HEIGHT, height))
    pm = QPixmap(safe_w, safe_h)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    try:
        painter.fillRect(QRect(0, 0, pm.width(), pm.height()), qcolor(theme.top_bar_bg))
        show_text = pm.width() >= _TOP_BAR_TEXT_MIN_WIDTH
        if bars:
            ratio_color_pairs = [top_bar_item_ratio_color(item) for item in bars]
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
                    painter.setPen(
                        QColor(255, 255, 255)
                        if sum(color) < _TOP_BAR_LIGHT_TEXT_RGB_SUM_THRESHOLD
                        else QColor(40, 40, 40)
                    )
                    painter.drawText(QRect(x + 2, 0, w - 4, pm.height()), Qt.AlignCenter, pct)
                x += w
        painter.setPen(QPen(qcolor(theme.top_bar_border), 1))
        painter.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
    finally:
        painter.end()
    return pm


def refresh_top_color_bar(main_window) -> None:
    """バー表示条件が変わったときだけ配色比率バーを再描画する。"""
    # 表示対象がないときはバーを消してキャッシュキーも初期化する。
    theme = _theme_from(main_window)
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
        bars_key = tuple(bar_key_item(item) for item in bars)
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
            theme=theme,
            width=main_window.top_colors_bar.width(),
            height=main_window.top_colors_bar.height(),
        )
    )


def apply_color_band_theme(main_window, _theme: UiTheme) -> None:
    """配色比率ドック内のテーマ依存表示を更新する。"""
    main_window._top_bar_render_key = None
    main_window._color_palette_render_key = None
    if getattr(main_window, "_color_chip_entries", None):
        _set_color_chip_items(main_window, list(main_window._color_chip_entries))
    refresh_top_color_bar(main_window)
    if hasattr(main_window, "list_color_chips"):
        on_color_chip_selected(main_window, int(main_window.list_color_chips.currentRow()))


def _set_color_chip_items(main_window, entries: list[dict]) -> None:
    """配色比率の一覧UIを現在の entries で再構築する。"""
    list_widget = getattr(main_window, "list_color_chips", None)
    if list_widget is None:
        return
    theme = _theme_from(main_window)
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
                f"border:1px solid {theme.swatch_border}; border-radius:3px;"
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
            text.setProperty("chromaRole", "detailText")
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


def _harmony_enabled_from_ui(main_window) -> bool:
    """配色比率詳細で色彩調和を表示するかを返す。"""
    try:
        if selected_color_band_use_wheel_harmony(main_window):
            return selected_wheel_harmony_guide_enabled(main_window)
        return selected_color_band_harmony_guide_enabled(main_window)
    except (AttributeError, TypeError, ValueError):
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
    except (AttributeError, TypeError, ValueError):
        return C.WHEEL_HARMONY_GUIDE_IDENTITY
    return value if value in C.WHEEL_HARMONY_GUIDE_OFFSETS_DEG else C.WHEEL_HARMONY_GUIDE_IDENTITY


def _set_color_detail_headers(
    widgets: ColorBandDetailWidgets,
    *,
    detail_text: str = "",
    harmony_text: str = _COLOR_DETAIL_LABEL_HARMONY,
    complement_text: str = _COLOR_DETAIL_LABEL_COMPLEMENT,
    methods_text: str = _COLOR_DETAIL_LABEL_METHODS,
) -> None:
    """詳細領域の見出しテキストを更新する。"""
    widgets.detail_label.setText(detail_text)
    widgets.harmony_label.setText(harmony_text)
    widgets.complement_label.setText(complement_text)
    widgets.methods_label.setText(methods_text)


def _color_band_detail_widgets(main_window) -> ColorBandDetailWidgets | None:
    """詳細表示更新に必要なウィジェット参照を解決する。"""
    try:
        return ColorBandDetailWidgets(
            detail_label=main_window.lbl_color_detail_info,
            harmony_label=main_window.lbl_color_harmony_info,
            complement_label=main_window.lbl_color_complement_info,
            methods_label=main_window.lbl_color_methods_info,
            harmony_layout=main_window.color_harmony_preview_layout,
            complement_layout=main_window.color_complement_preview_layout,
            methods_layout=main_window.color_methods_preview_layout,
        )
    except AttributeError:
        return None


def _color_band_visibility_widgets(main_window) -> ColorBandVisibilityWidgets | None:
    """compact 表示切替に必要なウィジェット参照を解決する。"""
    try:
        return ColorBandVisibilityWidgets(
            warmcool_label=main_window.lbl_warmcool,
            top_colors_bar=main_window.top_colors_bar,
            splitter=main_window.color_band_splitter,
            chip_list=main_window.list_color_chips,
            detail_scroll=main_window.color_detail_scroll,
            detail_title=main_window.lbl_color_detail_title,
            detail_info=main_window.lbl_color_detail_info,
            harmony_section=getattr(main_window, "color_harmony_section", None),
            complement_section=getattr(main_window, "color_complement_section", None),
            methods_section=getattr(main_window, "color_methods_section", None),
            harmony_label=main_window.lbl_color_harmony_info,
            harmony_preview=main_window.color_harmony_preview,
            complement_label=main_window.lbl_color_complement_info,
            complement_preview=main_window.color_complement_preview,
            methods_label=main_window.lbl_color_methods_info,
            methods_preview=main_window.color_methods_preview,
        )
    except AttributeError:
        return None


def _current_color_band_detail_state(main_window) -> ColorBandDetailState:
    """現在保持している配色詳細状態を返す。"""
    state = getattr(main_window, "_color_detail_state", None)
    if isinstance(state, ColorBandDetailState):
        return state
    return _default_color_band_detail_state()


def _empty_color_band_detail_state(
    entries_signature: tuple,
    *,
    harmony_enabled: bool,
    guide_type: str,
) -> ColorBandDetailState:
    """未選択時の詳細状態を返す。"""
    return ColorBandDetailState(
        render_key=("empty", entries_signature, bool(harmony_enabled), str(guide_type)),
    )


def _is_achromatic_color_entry(entry) -> bool:
    """無彩色行かどうかを返す。"""
    return str(entry.get("label", "")) == "無彩色"


def _color_band_detail_render_key(
    *,
    row: int,
    harmony_enabled: bool,
    guide_type: str,
    entries_signature: tuple,
    is_achromatic: bool,
) -> tuple:
    """詳細パネルの再描画判定キーを返す。"""
    return (
        int(row),
        bool(harmony_enabled),
        str(guide_type),
        entries_signature,
        bool(is_achromatic),
    )


def _color_band_harmony_text(
    *,
    harmony_enabled: bool,
    guide_type: str,
    merge_complement: bool,
) -> str:
    """詳細ヘッダへ表示する色彩調和ラベルを返す。"""
    guide_name = C.WHEEL_HARMONY_GUIDE_LABELS.get(guide_type, "色彩調和")
    if merge_complement:
        return f"{_COLOR_DETAIL_LABEL_HARMONY}（{guide_name} / {_COLOR_DETAIL_LABEL_COMPLEMENT}）"
    if harmony_enabled:
        return f"{_COLOR_DETAIL_LABEL_HARMONY}（{guide_name}）"
    return _COLOR_DETAIL_LABEL_HARMONY


def _color_band_palette_state(
    entry,
    *,
    harmony_enabled: bool,
    guide_type: str,
) -> tuple[
    bool,
    tuple[tuple[int, int, int], ...],
    tuple[tuple[int, int, int], ...],
    tuple[tuple[str, tuple[tuple[int, int, int], ...]], ...],
]:
    """選択色から詳細表示用 palette 群を構築する。"""
    merge_complement = bool(harmony_enabled and guide_type == C.WHEEL_HARMONY_GUIDE_COMPLEMENTARY)
    harmony_palette = (
        harmony_palette_from_base(entry["rgb"], guide_type)
        if harmony_enabled and guide_type != C.WHEEL_HARMONY_GUIDE_NONE
        else []
    )
    complement_palette = harmony_palette_from_base(
        entry["rgb"], C.WHEEL_HARMONY_GUIDE_COMPLEMENTARY
    )
    method_palettes = method_palettes_from_base(entry["rgb"])
    return (
        merge_complement,
        tuple(rgb for _h, rgb, _name in harmony_palette),
        tuple(() if merge_complement else (rgb for _h, rgb, _name in complement_palette)),
        tuple(
            (str(method_name), tuple(tuple(int(c) for c in rgb) for rgb in colors))
            for method_name, colors in method_palettes
        ),
    )


def _detail_preview_colors(colors: tuple[tuple[int, int, int], ...]) -> list[tuple[int, int, int]]:
    """詳細 preview row 用にタプル列を list 化する。"""
    return list(colors)


def _detail_method_preview_items(
    method_palettes: tuple[tuple[str, tuple[tuple[int, int, int], ...]], ...],
) -> list[tuple[str, list[tuple[int, int, int]]]]:
    """手法 preview 用に palette 構造を list ベースへ変換する。"""
    return [(name, list(colors)) for name, colors in method_palettes]


def _validate_color_band_detail_selection(
    entries,
    row: int,
    *,
    harmony_enabled: bool,
    guide_type: str,
    entries_signature: tuple,
) -> ColorBandSelectionInfo | None:
    """選択行を検証し、有効なら詳細計算用の情報を返す。"""
    if not entries or row < 0 or row >= len(entries):
        return None
    entry = entries[int(row)]
    achromatic = _is_achromatic_color_entry(entry)
    return ColorBandSelectionInfo(
        entry=entry,
        render_key=_color_band_detail_render_key(
            row=row,
            harmony_enabled=harmony_enabled,
            guide_type=guide_type,
            entries_signature=entries_signature,
            is_achromatic=achromatic,
        ),
        achromatic=achromatic,
    )


def _achromatic_color_band_detail_state(render_key: tuple) -> ColorBandDetailState:
    """無彩色選択時の詳細状態を返す。"""
    return ColorBandDetailState(
        render_key=render_key,
        has_selection=True,
        achromatic=True,
        detail_text=_COLOR_DETAIL_HINT_ACHROMATIC,
    )


def _color_band_detail_texts(
    *,
    harmony_enabled: bool,
    guide_type: str,
    merge_complement: bool,
) -> tuple[str, str, str, str]:
    """詳細表示に使う見出し文言を返す。"""
    return (
        "",
        _color_band_harmony_text(
            harmony_enabled=harmony_enabled,
            guide_type=guide_type,
            merge_complement=merge_complement,
        ),
        _COLOR_DETAIL_LABEL_COMPLEMENT,
        _COLOR_DETAIL_LABEL_METHODS,
    )


def _chromatic_color_band_detail_state(
    selection: ColorBandSelectionInfo,
    *,
    harmony_enabled: bool,
    guide_type: str,
) -> ColorBandDetailState:
    """有彩色選択時の詳細状態を返す。"""
    (
        merge_complement,
        harmony_colors,
        complement_colors,
        method_palettes,
    ) = _color_band_palette_state(
        selection.entry,
        harmony_enabled=harmony_enabled,
        guide_type=guide_type,
    )
    detail_text, harmony_text, complement_text, methods_text = _color_band_detail_texts(
        harmony_enabled=harmony_enabled,
        guide_type=guide_type,
        merge_complement=merge_complement,
    )
    return ColorBandDetailState(
        render_key=selection.render_key,
        has_selection=True,
        show_info=False,
        merge_complement=merge_complement,
        detail_text=detail_text,
        harmony_text=harmony_text,
        complement_text=complement_text,
        methods_text=methods_text,
        harmony_colors=harmony_colors,
        complement_colors=complement_colors,
        method_palettes=method_palettes,
    )


def compute_color_band_detail_state(
    entries,
    row: int,
    *,
    harmony_enabled: bool,
    guide_type: str,
    entries_signature: tuple,
) -> ColorBandDetailState:
    """選択行と色彩調和設定から詳細表示状態を計算する。"""
    selection = _validate_color_band_detail_selection(
        entries,
        row,
        harmony_enabled=harmony_enabled,
        guide_type=guide_type,
        entries_signature=entries_signature,
    )
    if selection is None:
        return _empty_color_band_detail_state(
            entries_signature,
            harmony_enabled=harmony_enabled,
            guide_type=guide_type,
        )
    if selection.achromatic:
        return _achromatic_color_band_detail_state(selection.render_key)
    return _chromatic_color_band_detail_state(
        selection,
        harmony_enabled=harmony_enabled,
        guide_type=guide_type,
    )


def _apply_color_band_detail_state(
    main_window,
    widgets: ColorBandDetailWidgets,
    state: ColorBandDetailState,
    *,
    theme: UiTheme,
) -> None:
    """計算済みの配色詳細状態を Qt ウィジェットへ反映する。"""
    main_window._color_palette_render_key = state.render_key
    main_window._color_detail_state = state
    set_preview_row(widgets.harmony_layout, _detail_preview_colors(state.harmony_colors), theme)
    set_preview_row(
        widgets.complement_layout,
        _detail_preview_colors(state.complement_colors),
        theme,
    )
    set_methods_preview(
        widgets.methods_layout,
        _detail_method_preview_items(state.method_palettes),
        theme,
    )
    _set_color_detail_headers(
        widgets,
        detail_text=state.detail_text,
        harmony_text=state.harmony_text,
        complement_text=state.complement_text,
        methods_text=state.methods_text,
    )


def compute_color_band_compact_visibility(
    body_h: int,
    detail_state: ColorBandDetailState,
    *,
    harmony_enabled: bool,
) -> ColorBandCompactVisibilityState:
    """ドック高さと詳細状態から compact 表示条件を計算する。"""
    show_top_bar = body_h >= _COLOR_BAND_MIN_H_SHOW_TOP_BAR
    show_warmcool = body_h >= _COLOR_BAND_MIN_H_SHOW_WARMCOOL
    show_chip_list = body_h >= _COLOR_BAND_MIN_H_SHOW_CHIP_LIST
    show_detail = bool(body_h >= _COLOR_BAND_MIN_H_SHOW_DETAIL and detail_state.has_selection)
    show_info = bool(show_detail and detail_state.show_info)
    show_color_models = bool(show_detail and not detail_state.achromatic)
    return ColorBandCompactVisibilityState(
        show_top_bar=show_top_bar,
        show_warmcool=show_warmcool,
        show_chip_list=show_chip_list,
        show_detail=show_detail,
        show_info=show_info,
        show_harmony=bool(show_color_models and harmony_enabled),
        show_complement=bool(show_color_models and not detail_state.merge_complement),
        show_color_models=show_color_models,
    )


def _apply_color_band_compact_visibility(
    widgets: ColorBandVisibilityWidgets,
    state: ColorBandCompactVisibilityState,
) -> None:
    """計算済みの compact 表示条件を Qt ウィジェットへ反映する。"""
    set_visible_if_changed(widgets.warmcool_label, state.show_warmcool)
    set_visible_if_changed(widgets.top_colors_bar, state.show_top_bar)
    set_visible_if_changed(widgets.splitter, state.show_chip_list)
    set_visible_if_changed(widgets.chip_list, state.show_chip_list)
    set_visible_if_changed(widgets.detail_scroll, state.show_detail and state.show_chip_list)
    set_visible_if_changed(widgets.detail_title, state.show_detail)
    set_visible_if_changed(widgets.detail_info, state.show_info)
    if widgets.harmony_section is not None:
        set_visible_if_changed(widgets.harmony_section, state.show_harmony)
    else:
        set_visible_if_changed(widgets.harmony_label, state.show_harmony)
        set_visible_if_changed(widgets.harmony_preview, state.show_harmony)
    if widgets.complement_section is not None:
        set_visible_if_changed(widgets.complement_section, state.show_complement)
    else:
        set_visible_if_changed(widgets.complement_label, state.show_complement)
        set_visible_if_changed(widgets.complement_preview, state.show_complement)
    if widgets.methods_section is not None:
        set_visible_if_changed(widgets.methods_section, state.show_color_models)
    else:
        set_visible_if_changed(widgets.methods_label, state.show_color_models)
        set_visible_if_changed(widgets.methods_preview, state.show_color_models)


def on_color_chip_selected(main_window, row: int) -> None:
    """配色比率一覧の選択変更に合わせて詳細表示を更新する。"""
    entries = getattr(main_window, "_color_chip_entries", ())
    widgets = _color_band_detail_widgets(main_window)
    if widgets is None:
        return
    theme = _theme_from(main_window)
    state = compute_color_band_detail_state(
        entries,
        row,
        harmony_enabled=_harmony_enabled_from_ui(main_window),
        guide_type=_guide_type_from_ui(main_window),
        entries_signature=_color_chip_entries_signature(main_window, entries),
    )
    if state.render_key == getattr(main_window, "_color_palette_render_key", None):
        return
    _apply_color_band_detail_state(main_window, widgets, state, theme=theme)
    update_color_band_compact_visibility(main_window)


def update_color_band_compact_visibility(main_window) -> None:
    """配色比率ドックの高さに応じて表示要素を段階的に切り替える。"""
    dock = getattr(main_window, "dock_color_band", None)
    content = dock.widget() if dock is not None else None
    if content is None:
        return
    widgets = _color_band_visibility_widgets(main_window)
    if widgets is None:
        return
    visibility_state = compute_color_band_compact_visibility(
        int(content.height()),
        _current_color_band_detail_state(main_window),
        harmony_enabled=_harmony_enabled_from_ui(main_window),
    )
    _apply_color_band_compact_visibility(widgets, visibility_state)


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
                raw_bars = compute_top_bars_chromatic_medoid(
                    snapshot.get("bgr_preview"),
                    sat_threshold=selected_effective_color_band_sat_threshold_safe(main_window),
                    top_count=int(C.TOP_COLORS_COUNT),
                )
            snapshot["top_colors_full"] = raw_bars
        if raw_bars is None:
            raw_bars = []
        bars = filter_invisible_percent_bars(raw_bars)
        bars_key = tuple(bar_key_item(item) for item in bars)
        snapshot["top_colors_filtered"] = bars
        snapshot["top_colors_key"] = bars_key
    if bars is None:
        bars = []
    if bars_key is None:
        bars_key = tuple(bar_key_item(item) for item in bars)
        snapshot["top_colors_key"] = bars_key
    return bars, bars_key


def _sync_color_chip_entries(main_window, bars: list[tuple], bars_key: tuple) -> None:
    """配色比率一覧のデータソースを必要時のみ更新する。"""
    if bars_key != getattr(main_window, "_color_chip_list_source_key", None):
        chip_entries = normalize_chip_entries(bars)
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
        (str(e["hex"]), round(float(e["ratio"]), COLOR_BAND_KEY_RATIO_DECIMALS)) for e in entries
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
    warmcool_text = format_warmcool_text(snapshot)
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
