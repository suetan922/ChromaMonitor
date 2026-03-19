"""配色比率ドックの小物 UI 構築 helper。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget

from ...util.theme import UiTheme
from .result_color_band_palette import rgb_to_hex, rgb_to_hsv_text


def clear_layout_widgets(layout) -> None:
    """指定レイアウト配下の子ウィジェット/子レイアウトを破棄する。"""
    while layout.count() > 0:
        item = layout.takeAt(0)
        child = item.widget()
        if child is not None:
            child.deleteLater()
            continue
        child_layout = item.layout()
        if child_layout is not None:
            clear_layout_widgets(child_layout)


def copy_text_to_clipboard(text: str) -> None:
    """文字列をクリップボードへコピーする。"""
    app = QApplication.instance()
    if app is None:
        return
    app.clipboard().setText(str(text))


def selected_text_from_widget(widget) -> str:
    """選択中テキストを安全に取り出す。"""
    if widget is None:
        return ""
    if hasattr(widget, "textCursor"):
        try:
            cursor = widget.textCursor()
        except (AttributeError, RuntimeError):
            return ""
        if cursor.hasSelection():
            return str(cursor.selectedText()).replace("\u2029", "\n")
        return ""
    if hasattr(widget, "selectedText"):
        try:
            return str(widget.selectedText() or "")
        except (AttributeError, RuntimeError):
            return ""
    return ""


def all_text_from_widget(widget) -> str:
    """ウィジェット全文を安全に取り出す。"""
    if widget is None:
        return ""
    if hasattr(widget, "toPlainText"):
        try:
            return str(widget.toPlainText())
        except (AttributeError, RuntimeError):
            return ""
    if hasattr(widget, "text"):
        try:
            return str(widget.text())
        except (AttributeError, RuntimeError):
            return ""
    return ""


def show_copy_menu_for_text_widget(text_widget, pos) -> None:
    """テキストコピー用の右クリックメニューを表示する。"""
    if text_widget is None:
        return
    menu = QMenu(text_widget)
    act_copy_sel = menu.addAction("選択範囲をコピー")
    act_copy_all = menu.addAction("全体をコピー")
    selected = selected_text_from_widget(text_widget)
    if not selected:
        act_copy_sel.setEnabled(False)
    chosen = menu.exec(text_widget.mapToGlobal(pos))
    if chosen is act_copy_sel:
        copy_text_to_clipboard(selected)
    elif chosen is act_copy_all:
        copy_text_to_clipboard(all_text_from_widget(text_widget))


def enable_select_copy_on_label(label: QLabel) -> None:
    """ラベルにテキスト選択とコピー用コンテキストメニューを付与する。"""
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    label.setContextMenuPolicy(Qt.CustomContextMenu)
    label.customContextMenuRequested.connect(
        lambda pos, w=label: show_copy_menu_for_text_widget(w, pos)
    )


def build_palette_preview_card(
    rgb: tuple[int, int, int],
    *,
    theme: UiTheme,
    is_base: bool = False,
) -> QWidget:
    """1色分のプレビューカードを生成する。"""
    r, g, b = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    hex_code = rgb_to_hex((r, g, b))
    hsv_text = rgb_to_hsv_text((r, g, b))
    card = QWidget()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    swatch = QLabel()
    swatch.setFixedSize(74, 40)
    border_width = 2 if bool(is_base) else 1
    border_color = theme.swatch_base_border if bool(is_base) else theme.swatch_border
    swatch.setStyleSheet(
        f"border:{border_width}px solid {border_color}; border-radius:5px;"
        f"background: rgb({r}, {g}, {b});"
    )
    layout.addWidget(swatch, 0, Qt.AlignHCenter)

    hsv_label = QLabel(hsv_text)
    hsv_label.setProperty("chromaRole", "subtleText")
    enable_select_copy_on_label(hsv_label)
    layout.addWidget(hsv_label, 0, Qt.AlignHCenter)

    rgb_label = QLabel(f"RGB({r}, {g}, {b})")
    rgb_label.setProperty("chromaRole", "subtleText")
    enable_select_copy_on_label(rgb_label)
    layout.addWidget(rgb_label, 0, Qt.AlignHCenter)

    hex_label = QLabel(hex_code)
    hex_label.setProperty("chromaRole", "subtleText")
    enable_select_copy_on_label(hex_label)
    layout.addWidget(hex_label, 0, Qt.AlignHCenter)
    return card


def set_preview_row(layout, colors: list[tuple[int, int, int]], theme: UiTheme) -> None:
    """色カード行を差し替える。"""
    if layout is None:
        return
    clear_layout_widgets(layout)
    for i, rgb in enumerate(colors):
        layout.addWidget(build_palette_preview_card(rgb, theme=theme, is_base=(i == 0)), 0)
    layout.addStretch(1)


def build_method_preview_row(
    title: str,
    colors: list[tuple[int, int, int]],
    *,
    theme: UiTheme,
) -> QWidget:
    """配色手法1行分の見出し+色カードを構築する。"""
    row = QWidget()
    layout = QVBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    title_label = QLabel(str(title))
    title_label.setProperty("chromaRole", "titleLabel")
    title_label.setWordWrap(True)
    layout.addWidget(title_label, 0)

    preview = QWidget()
    preview_l = QHBoxLayout(preview)
    preview_l.setContentsMargins(0, 0, 0, 0)
    preview_l.setSpacing(6)
    for i, rgb in enumerate(colors):
        preview_l.addWidget(build_palette_preview_card(rgb, theme=theme, is_base=(i == 0)), 0)
    preview_l.addStretch(1)
    layout.addWidget(preview, 0)
    return row


def set_methods_preview(
    layout,
    method_palettes: list[tuple[str, list[tuple[int, int, int]]]],
    theme: UiTheme,
) -> None:
    """配色手法一覧を描画する。"""
    if layout is None:
        return
    clear_layout_widgets(layout)
    for method_name, colors in method_palettes:
        layout.addWidget(build_method_preview_row(method_name, colors, theme=theme), 0)
    layout.addStretch(1)
