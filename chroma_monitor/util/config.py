import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from . import constants as C

DEFAULT_CONFIG = {
    C.CFG_INTERVAL: C.DEFAULT_INTERVAL_SEC,
    C.CFG_SAMPLE_POINTS: C.DEFAULT_SAMPLE_POINTS,
    C.CFG_ANALYZER_MAX_DIM: C.ANALYZER_MAX_DIM,
    C.CFG_SCATTER_SHAPE: C.DEFAULT_SCATTER_SHAPE,
    C.CFG_SCATTER_POINT_ALPHA: C.DEFAULT_SCATTER_POINT_ALPHA,
    C.CFG_WHEEL_MODE: C.DEFAULT_WHEEL_MODE,
    C.CFG_WHEEL_SAT_THRESHOLD: C.DEFAULT_WHEEL_SAT_THRESHOLD,
    C.CFG_GRAPH_EVERY: C.DEFAULT_GRAPH_EVERY,
    C.CFG_CAPTURE_SOURCE: C.DEFAULT_CAPTURE_SOURCE,
    C.CFG_EDGE_SENSITIVITY: C.DEFAULT_EDGE_SENSITIVITY,
    C.CFG_BINARY_PRESET: C.DEFAULT_BINARY_PRESET,
    C.CFG_TERNARY_PRESET: C.DEFAULT_TERNARY_PRESET,
    C.CFG_SALIENCY_OVERLAY_ALPHA: C.DEFAULT_SALIENCY_OVERLAY_ALPHA,
    C.CFG_COMPOSITION_GUIDE: C.DEFAULT_COMPOSITION_GUIDE,
    C.CFG_FOCUS_PEAK_SENSITIVITY: C.DEFAULT_FOCUS_PEAK_SENSITIVITY,
    C.CFG_FOCUS_PEAK_COLOR: C.DEFAULT_FOCUS_PEAK_COLOR,
    C.CFG_FOCUS_PEAK_THICKNESS: C.DEFAULT_FOCUS_PEAK_THICKNESS,
    C.CFG_SQUINT_MODE: C.DEFAULT_SQUINT_MODE,
    C.CFG_SQUINT_SCALE_PERCENT: C.DEFAULT_SQUINT_SCALE_PERCENT,
    C.CFG_SQUINT_BLUR_SIGMA: C.DEFAULT_SQUINT_BLUR_SIGMA,
    C.CFG_VECTORSCOPE_SHOW_SKIN_LINE: C.DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE,
    C.CFG_VECTORSCOPE_WARN_THRESHOLD: C.DEFAULT_VECTORSCOPE_WARN_THRESHOLD,
    C.CFG_PREVIEW_WINDOW: C.DEFAULT_PREVIEW_WINDOW,
    C.CFG_MODE: C.DEFAULT_MODE,
    C.CFG_DIFF_THRESHOLD: C.DEFAULT_DIFF_THRESHOLD,
    C.CFG_STABLE_FRAMES: C.DEFAULT_STABLE_FRAMES,
    C.CFG_LAYOUT_CURRENT: {},
    C.CFG_LAYOUT_PRESETS: {},
}


def _user_config_dir() -> Path:
    """Return a per-user writable config directory.

    PyInstaller 一時展開先(_MEIxxx)は書き込み不可なので、OSごとに標準の
    設定ディレクトリを使う。
    """
    # 環境変数で上書きできるようにする
    override = os.environ.get("CHROMA_MONITOR_CONFIG_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ChromaMonitor"


def config_path() -> Path:
    cfg_dir = _user_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "settings.json"


def load_config() -> Dict[str, Any]:
    path = config_path()
    if not path.exists():
        return DEFAULT_CONFIG.copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return DEFAULT_CONFIG.copy()
        cfg = data.copy()
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(cfg: Dict[str, Any]) -> None:
    path = config_path()
    try:
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
