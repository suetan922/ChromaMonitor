"""設定ファイル読み書きの回帰を防ぐテスト。"""

import json

from chroma_monitor.util import config
from chroma_monitor.util import constants as C


def test_load_config_missing_file_returns_independent_defaults(tmp_path, monkeypatch) -> None:
    # ファイル未作成時、可変dictの参照共有が起きないことを確認する。
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: settings_path)

    cfg1 = config.load_config()
    cfg1[C.CFG_LAYOUT_CURRENT]["edited"] = 1
    cfg1[C.CFG_LAYOUT_PRESETS]["p1"] = {"dummy": True}

    cfg2 = config.load_config()
    assert cfg2[C.CFG_LAYOUT_CURRENT] == {}
    assert cfg2[C.CFG_LAYOUT_PRESETS] == {}


def test_load_config_merges_and_normalizes_layout_fields(tmp_path, monkeypatch) -> None:
    # 不正型のレイアウト値が空dictへ正規化されることを確認する。
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: settings_path)
    settings_path.write_text(
        json.dumps(
            {
                C.CFG_INTERVAL: 1.25,
                C.CFG_LAYOUT_CURRENT: "invalid",
                C.CFG_LAYOUT_PRESETS: ["invalid"],
            }
        ),
        encoding="utf-8",
    )

    loaded = config.load_config()
    assert loaded[C.CFG_INTERVAL] == 1.25
    assert loaded[C.CFG_LAYOUT_CURRENT] == {}
    assert loaded[C.CFG_LAYOUT_PRESETS] == {}


def test_load_config_invalid_json_returns_defaults(tmp_path, monkeypatch) -> None:
    # JSON破損時でもデフォルトで安全復帰することを確認する。
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: settings_path)
    settings_path.write_text("{invalid json", encoding="utf-8")

    loaded = config.load_config()
    assert loaded[C.CFG_INTERVAL] == C.DEFAULT_INTERVAL_SEC
    assert loaded[C.CFG_LAYOUT_CURRENT] == {}
    assert loaded[C.CFG_LAYOUT_PRESETS] == {}


def test_save_config_writes_json(tmp_path, monkeypatch) -> None:
    # save_config が実ファイルへJSONを書き出すことを確認する。
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: settings_path)

    payload = {
        C.CFG_INTERVAL: 3.0,
        C.CFG_LAYOUT_CURRENT: {"x": 10},
        C.CFG_LAYOUT_PRESETS: {},
    }
    config.save_config(payload)

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved[C.CFG_INTERVAL] == 3.0
    assert saved[C.CFG_LAYOUT_CURRENT] == {"x": 10}
