"""テーマ定義と既定設定の回帰を防ぐテスト。"""

from chroma_monitor.util import config
from chroma_monitor.util import constants as C
from chroma_monitor.util import theme


def test_get_ui_theme_unknown_name_falls_back_to_default() -> None:
    # 不正なテーマ名でも既定テーマへ安全に戻ることを確認する。
    resolved = theme.get_ui_theme("unknown-theme")
    assert resolved.name == C.DEFAULT_UI_THEME


def test_light_theme_image_background_is_soft_gray() -> None:
    # ライトテーマの画像周囲背景は黒でも白でもなく薄いグレーにする。
    light = theme.get_ui_theme(C.UI_THEME_LIGHT)
    assert light.image_bg == "#E7EBF0"


def test_load_config_missing_file_includes_default_theme(tmp_path, monkeypatch) -> None:
    # 設定未作成時でもテーマ既定値が常に補完されることを確認する。
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: settings_path)

    loaded = config.load_config()
    assert loaded[C.CFG_UI_THEME] == C.DEFAULT_UI_THEME


def test_build_app_stylesheet_keeps_core_sections() -> None:
    # stylesheet 分割後も主要セレクタが欠けていないことを確認する。
    resolved = theme.get_ui_theme(C.DEFAULT_UI_THEME)
    stylesheet = theme.build_app_stylesheet(resolved)

    assert "QMainWindow, QDialog, QWidget" in stylesheet
    assert "QPushButton, QToolButton" in stylesheet
    assert "QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox" in stylesheet
    assert "QSlider#scatterHueSlider::groove:vertical" in stylesheet
