"""UI 共通 stylesheet 生成。"""

from .theme_definitions import UiTheme


def _join_stylesheet_sections(*sections: str) -> str:
    """空要素を除いて stylesheet 断片を連結する。"""
    return "\n".join(section.strip() for section in sections if section).strip()


def _build_base_styles(theme: UiTheme) -> str:
    """全体のベース色と文字色を組み立てる。"""
    return f"""
        QMainWindow, QDialog, QWidget {{
            background:{theme.window_bg};
            color:{theme.text_primary};
        }}
        QWidget#centralWidget {{
            background:{theme.window_bg};
        }}
        QLabel {{
            color:{theme.text_primary};
            background:transparent;
        }}
        QLabel[chromaRole="muted"],
        QLabel[chromaRole="hint"] {{
            color:{theme.text_muted};
        }}
        QLabel[chromaRole="status"] {{
            color:{theme.text_muted};
        }}
        QLabel[chromaRole="placeholder"] {{
            color:{theme.text_muted};
            font-size:14px;
        }}
        QLabel[chromaRole="detailTitle"] {{
            color:{theme.text_primary};
            font-size:12px;
            font-weight:600;
        }}
        QLabel[chromaRole="detailText"],
        QLabel[chromaRole="infoLabel"],
        QLabel[chromaRole="titleLabel"] {{
            color:{theme.text_primary};
            font-size:12px;
        }}
        QLabel[chromaRole="subtleText"] {{
            color:{theme.text_secondary};
            font-size:10px;
        }}
        QLabel[chromaRole="vectorscopeWarning"][chromaWarnLevel="muted"] {{
            color:{theme.warning_muted};
        }}
        QLabel[chromaRole="vectorscopeWarning"][chromaWarnLevel="warn"] {{
            color:{theme.warning_low};
        }}
        QLabel[chromaRole="vectorscopeWarning"][chromaWarnLevel="alert"] {{
            color:{theme.warning_high};
        }}
        QLabel[chromaViewRole="image"] {{
            background:{theme.image_bg};
            border:1px solid {theme.image_border};
            color:{theme.image_text};
        }}
        QLabel[chromaViewRole="scatter"] {{
            background:{theme.panel_bg};
            border:none;
            color:{theme.text_secondary};
        }}
        QToolTip {{
            background:{theme.menu_bg};
            color:{theme.text_primary};
            border:1px solid {theme.menu_border};
        }}
        QMenuBar {{
            background:{theme.toolbar_bg};
            color:{theme.text_primary};
        }}
        QMenuBar::item {{
            background:transparent;
            padding:4px 8px;
        }}
        QMenuBar::item:selected {{
            background:{theme.button_hover_bg};
        }}
        QMenu {{
            background:{theme.menu_bg};
            color:{theme.text_primary};
            border:1px solid {theme.menu_border};
        }}
        QMenu::item:selected {{
            background:{theme.accent};
            color:{theme.text_inverse};
        }}
    """


def _build_button_styles(theme: UiTheme) -> str:
    """ボタンとツールボタン群の stylesheet を返す。"""
    return f"""
        QPushButton, QToolButton {{
            background:{theme.button_bg};
            border:1px solid {theme.border};
            padding:6px 12px;
            border-radius:4px;
            color:{theme.text_primary};
        }}
        QPushButton:hover, QToolButton:hover {{
            border:1px solid {theme.border_strong};
            background:{theme.button_hover_bg};
        }}
        QPushButton:pressed, QToolButton:pressed {{
            background:{theme.button_pressed_bg};
        }}
        QPushButton:disabled, QToolButton:disabled {{
            background:{theme.input_disabled_bg};
            color:{theme.text_disabled};
            border:1px solid {theme.border};
        }}
        QPushButton#runStartBtn, QPushButton#runStopBtn {{
            font-weight:600;
            padding:6px 12px;
            border-radius:8px;
            min-width:72px;
        }}
        QPushButton#runStartBtn:checked {{
            background:{theme.success_bg};
            border:1px solid {theme.success_border};
            color:{theme.text_inverse};
        }}
        QPushButton#runStopBtn:checked {{
            background:{theme.danger_bg};
            border:1px solid {theme.danger_border};
            color:{theme.text_inverse};
        }}
        QToolButton[chromaDockTabCloseButton="true"] {{
            border:none;
            background:transparent;
            color:{theme.text_muted};
            padding:0;
            font-size:13px;
            font-weight:700;
        }}
        QToolButton[chromaDockTabCloseButton="true"]:hover {{
            color:{theme.danger_bg};
        }}
        QToolButton[chromaDockTabCloseButton="true"]:pressed {{
            color:{theme.danger_border};
        }}
    """


def _build_input_styles(theme: UiTheme) -> str:
    """入力系ウィジェットの stylesheet を返す。"""
    return f"""
        QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox {{
            background:{theme.input_bg};
            border:1px solid {theme.border};
            color:{theme.text_primary};
            border-radius:4px;
            padding:4px 24px 4px 6px;
        }}
        QComboBox:focus {{
            outline:none;
            border:1px solid {theme.border};
        }}
        QComboBox:disabled, QLineEdit:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled {{
            background:{theme.input_disabled_bg};
            color:{theme.text_disabled};
            border:1px solid {theme.border};
        }}
        QComboBox QLineEdit {{
            background:{theme.input_bg};
            color:{theme.text_primary};
            selection-background-color:{theme.accent};
            selection-color:{theme.text_inverse};
        }}
        QComboBox QAbstractItemView {{
            background:{theme.menu_bg};
            color:{theme.text_primary};
            border:1px solid {theme.menu_border};
            selection-background-color:{theme.accent};
            selection-color:{theme.text_inverse};
        }}
        QAbstractItemView[chromaRole="comboPopup"] {{
            background:{theme.menu_bg};
            color:{theme.text_primary};
            border:1px solid {theme.menu_border};
            selection-background-color:{theme.accent};
            selection-color:{theme.text_inverse};
        }}
        QAbstractItemView[chromaRole="comboPopup"]::item {{
            color:{theme.text_primary};
            background:{theme.menu_bg};
        }}
        QAbstractItemView[chromaRole="comboPopup"]::item:selected {{
            color:{theme.text_inverse};
            background:{theme.accent};
        }}
        QAbstractItemView[chromaRole="comboPopup"]:focus {{
            outline:none;
        }}
        QAbstractItemView[chromaRole="comboPopup"]::item:focus {{
            outline:none;
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-origin:border;
            width:20px;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin:border;
            width:20px;
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            width:9px;
            height:9px;
        }}
        QCheckBox {{
            color:{theme.text_primary};
            spacing:7px;
        }}
        QCheckBox::indicator {{
            width:18px;
            height:18px;
        }}
        QCheckBox::indicator:unchecked {{
            background:{theme.input_bg};
            border:1px solid {theme.border_strong};
            border-radius:4px;
        }}
        QCheckBox::indicator:unchecked:hover {{
            border:1px solid {theme.accent_hover};
        }}
        QCheckBox::indicator:disabled:unchecked {{
            background:{theme.input_disabled_bg};
            border:1px solid {theme.border};
        }}
    """


def _build_container_styles(theme: UiTheme) -> str:
    """ドックやリストなどコンテナ系の stylesheet を返す。"""
    return f"""
        QDockWidget::title {{
            background:{theme.dock_title_bg};
            padding:4px 8px;
            border:1px solid {theme.dock_title_border};
            border-radius:4px;
        }}
        QToolBar {{
            spacing:8px;
            border:none;
            background:{theme.toolbar_bg};
            padding:4px 8px;
        }}
        QGroupBox {{
            background:{theme.window_alt_bg};
            color:{theme.text_primary};
            border:1px solid {theme.border};
            border-radius:6px;
            margin-top:8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left:10px;
            padding:2px 8px 2px 8px;
            background:{theme.window_alt_bg};
            border-radius:4px;
        }}
        QListWidget[chromaRole="settingsNav"] {{
            background:{theme.panel_bg};
            border:1px solid {theme.border};
            border-radius:6px;
        }}
        QListWidget[chromaRole="settingsNav"]:focus {{
            outline:none;
            border:1px solid {theme.border};
        }}
        QListWidget[chromaRole="settingsNav"]::item {{
            padding:2px 8px;
        }}
        QListWidget[chromaRole="settingsNav"]::item:focus {{
            outline:none;
        }}
        QListWidget[chromaRole="settingsNav"]::item:selected {{
            background:{theme.accent};
            color:{theme.text_inverse};
        }}
        QListWidget[chromaRole="colorChipList"] {{
            background:{theme.chip_list_bg};
            border:1px solid {theme.chip_list_border};
            border-radius:6px;
        }}
        QListWidget[chromaRole="colorChipList"]::item {{
            padding:2px 4px;
        }}
        QListWidget[chromaRole="colorChipList"]::item:selected {{
            background:{theme.panel_alt_bg};
            border:1px solid {theme.chip_selected_border};
        }}
        QScrollArea {{
            border:none;
            background:transparent;
        }}
        QTabBar::tab {{
            background:{theme.tab_bg};
            color:{theme.text_secondary};
            border:1px solid {theme.tab_border};
            padding:5px 10px;
            border-top-left-radius:4px;
            border-top-right-radius:4px;
        }}
        QTabBar::tab:hover {{
            background:{theme.tab_hover_bg};
        }}
        QTabBar::tab:selected {{
            background:{theme.tab_selected_bg};
            color:{theme.text_primary};
        }}
        QSplitter::handle {{
            background:{theme.border};
        }}
    """


def _build_scatter_slider_styles(theme: UiTheme) -> str:
    """散布図色相スライダー専用の stylesheet を返す。"""
    return f"""
        QSlider#scatterHueSlider::groove:vertical {{
            border:1px solid {theme.slider_groove_border};
            width:10px;
            margin:8px 0;
            border-radius:6px;
            background:qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #ff0000,
                stop:0.16 #ff00ff,
                stop:0.33 #0000ff,
                stop:0.5 #00ffff,
                stop:0.66 #00ff00,
                stop:0.83 #ffff00,
                stop:1 #ff0000
            );
        }}
        QSlider#scatterHueSlider::handle:vertical {{
            background:{theme.slider_handle_bg};
            border:1px solid {theme.slider_handle_border};
            width:20px;
            height:14px;
            margin:0 -5px;
            border-radius:7px;
        }}
        QLabel#scatterHueValue {{
            color:{theme.text_secondary};
            font-size:11px;
        }}
    """


def build_app_stylesheet(theme: UiTheme) -> str:
    """アプリ全体へ適用する共通 stylesheet を返す。"""
    return _join_stylesheet_sections(
        _build_base_styles(theme),
        _build_button_styles(theme),
        _build_input_styles(theme),
        _build_container_styles(theme),
        _build_scatter_slider_styles(theme),
    )
