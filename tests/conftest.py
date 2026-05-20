"""テスト実行時の import path を整える共通設定。"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_runtime_outputs_for_tests(monkeypatch):
    """テスト中の config / debug log 出力先を作業ツリー直下の `.tmp/` へ隔離する。"""
    from chroma_monitor.util import config as cm_config
    from chroma_monitor.util import constants as C
    from chroma_monitor.util import debug_log as cm_debug_log

    base_dir = ROOT / ".tmp" / "pytest-runtime"
    config_dir = base_dir / "config"
    log_dir = base_dir / "logs"
    config_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("CHROMA_MONITOR_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv(C.DEBUG_UI_LOG_PATH_ENV, str(log_dir / C.DEBUG_UI_LOG_FILE))

    cm_config._CONFIG_PATH_CACHE = None
    cm_debug_log._LOGGER_ANNOUNCED_PATHS.clear()
    yield
    cm_config._CONFIG_PATH_CACHE = None
