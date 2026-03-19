"""UI テーマ定義。"""

from dataclasses import dataclass

from . import constants as C


@dataclass(frozen=True, slots=True)
class UiTheme:
    """UIテーマで使う主要色をまとめた定義。"""

    name: str
    window_bg: str
    window_alt_bg: str
    panel_bg: str
    panel_alt_bg: str
    toolbar_bg: str
    dock_title_bg: str
    dock_title_border: str
    tab_bg: str
    tab_hover_bg: str
    tab_selected_bg: str
    tab_border: str
    menu_bg: str
    menu_border: str
    input_bg: str
    input_disabled_bg: str
    button_bg: str
    button_hover_bg: str
    button_pressed_bg: str
    text_primary: str
    text_secondary: str
    text_muted: str
    text_disabled: str
    text_inverse: str
    border: str
    border_strong: str
    accent: str
    accent_hover: str
    success_bg: str
    success_border: str
    danger_bg: str
    danger_border: str
    image_bg: str
    image_border: str
    image_text: str
    wheel_canvas_bg: str
    wheel_outer_bg: str
    wheel_inner_bg: str
    plot_bg: str
    plot_border: str
    plot_grid: str
    plot_grid_subtle: str
    scatter_frame: str
    scope_outer_bg: str
    scope_inner_bg: str
    scope_border: str
    scope_grid: str
    scope_grid_soft: str
    scope_spoke: str
    scope_center: str
    scope_skin_line_outer: str
    scope_skin_line_inner: str
    scope_warn_outer: str
    scope_warn_inner: str
    chip_list_bg: str
    chip_list_border: str
    chip_selected_border: str
    swatch_border: str
    swatch_base_border: str
    top_bar_bg: str
    top_bar_border: str
    warning_muted: str
    warning_low: str
    warning_high: str
    slider_groove_border: str
    slider_handle_bg: str
    slider_handle_border: str


LIGHT_THEME = UiTheme(
    name=C.UI_THEME_LIGHT,
    window_bg="#F3F4F6",
    window_alt_bg="#FAFBFD",
    panel_bg="#FFFFFF",
    panel_alt_bg="#F7F8FB",
    toolbar_bg="#F3F4F6",
    dock_title_bg="#F9FAFC",
    dock_title_border="#DFE3E8",
    tab_bg="#E9EDF2",
    tab_hover_bg="#EEF2F7",
    tab_selected_bg="#FFFFFF",
    tab_border="#CDD4DD",
    menu_bg="#FFFFFF",
    menu_border="#D7DCE4",
    input_bg="#FFFFFF",
    input_disabled_bg="#ECEFF3",
    button_bg="#F7F8FB",
    button_hover_bg="#EEF0F3",
    button_pressed_bg="#E4E6EA",
    text_primary="#111827",
    text_secondary="#334155",
    text_muted="#64748B",
    text_disabled="#8A9099",
    text_inverse="#F8FAFC",
    border="#CDD1D6",
    border_strong="#B6BAC0",
    accent="#2563EB",
    accent_hover="#1D4ED8",
    success_bg="#16A34A",
    success_border="#15803D",
    danger_bg="#DC2626",
    danger_border="#B91C1C",
    image_bg="#E7EBF0",
    image_border="#C7CDD6",
    image_text="#6B7280",
    wheel_canvas_bg="#FFFFFF",
    wheel_outer_bg="#D9DDE3",
    wheel_inner_bg="#FFFFFF",
    plot_bg="#FFFFFF",
    plot_border="#C8D0DA",
    plot_grid="#E0E5EC",
    plot_grid_subtle="#BAC2CE",
    scatter_frame="#5F6976",
    scope_outer_bg="#EDF1F5",
    scope_inner_bg="#E4EAF1",
    scope_border="#9AA9BA",
    scope_grid="#AEB9C7",
    scope_grid_soft="#CDD6E0",
    scope_spoke="#BCC6D2",
    scope_center="#7B8896",
    scope_skin_line_outer="#A9B8CA",
    scope_skin_line_inner="#5B7698",
    scope_warn_outer="#CED7E2",
    scope_warn_inner="#8096AF",
    chip_list_bg="#FFFFFF",
    chip_list_border="#D6DBE4",
    chip_selected_border="#2563EB",
    swatch_border="#9AA1AD",
    swatch_base_border="#1E3A8A",
    top_bar_bg="#E7EBEF",
    top_bar_border="#C7CFD9",
    warning_muted="#8B97A8",
    warning_low="#B89C52",
    warning_high="#D06B5D",
    slider_groove_border="#C4C9D4",
    slider_handle_bg="#F5F7FB",
    slider_handle_border="#4E5565",
)

DARK_THEME = UiTheme(
    name=C.UI_THEME_DARK,
    window_bg="#161A20",
    window_alt_bg="#1A2027",
    panel_bg="#1C222B",
    panel_alt_bg="#232A35",
    toolbar_bg="#171C23",
    dock_title_bg="#202734",
    dock_title_border="#33404E",
    tab_bg="#202734",
    tab_hover_bg="#27303C",
    tab_selected_bg="#2C3644",
    tab_border="#374151",
    menu_bg="#1B212A",
    menu_border="#394553",
    input_bg="#202631",
    input_disabled_bg="#2A313C",
    button_bg="#242B36",
    button_hover_bg="#2D3542",
    button_pressed_bg="#353F4D",
    text_primary="#E5E7EB",
    text_secondary="#CBD5E1",
    text_muted="#94A3B8",
    text_disabled="#6B7280",
    text_inverse="#F8FAFC",
    border="#3A4654",
    border_strong="#4C5B6E",
    accent="#3B82F6",
    accent_hover="#60A5FA",
    success_bg="#16A34A",
    success_border="#15803D",
    danger_bg="#DC2626",
    danger_border="#B91C1C",
    image_bg="#0F1318",
    image_border="#2F3640",
    image_text="#94A3B8",
    wheel_canvas_bg="#161A20",
    wheel_outer_bg="#2A3038",
    wheel_inner_bg="#161A20",
    plot_bg="#0F141B",
    plot_border="#495362",
    plot_grid="#333C49",
    plot_grid_subtle="#5F6A7A",
    scatter_frame="#738093",
    scope_outer_bg="#080B10",
    scope_inner_bg="#0D1015",
    scope_border="#4A5666",
    scope_grid="#36414F",
    scope_grid_soft="#525E6E",
    scope_spoke="#28313D",
    scope_center="#7C8795",
    scope_skin_line_outer="#243141",
    scope_skin_line_inner="#84A6CA",
    scope_warn_outer="#1C2430",
    scope_warn_inner="#7C8FA5",
    chip_list_bg="#161C23",
    chip_list_border="#364152",
    chip_selected_border="#60A5FA",
    swatch_border="#677182",
    swatch_base_border="#93C5FD",
    top_bar_bg="#202630",
    top_bar_border="#394556",
    warning_muted="#94A3B8",
    warning_low="#D5B66A",
    warning_high="#F28C7E",
    slider_groove_border="#4A5568",
    slider_handle_bg="#DCE3EC",
    slider_handle_border="#2D3642",
)

THEMES = {
    LIGHT_THEME.name: LIGHT_THEME,
    DARK_THEME.name: DARK_THEME,
}


def get_ui_theme(theme_name: str | None = None) -> UiTheme:
    """テーマ名から対応テーマを返す。"""
    return THEMES.get(str(theme_name or "").strip(), THEMES[C.DEFAULT_UI_THEME])
