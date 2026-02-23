import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterator

from . import constants as C

DEFAULT_CONFIG = {
    C.CFG_INTERVAL: C.DEFAULT_INTERVAL_SEC,
    C.CFG_SAMPLE_POINTS: C.DEFAULT_SAMPLE_POINTS,
    C.CFG_ANALYZER_MAX_DIM: C.ANALYZER_MAX_DIM,
    C.CFG_ANALYSIS_RESOLUTION_MODE: C.DEFAULT_ANALYSIS_RESOLUTION_MODE,
    C.CFG_SCATTER_SHAPE: C.DEFAULT_SCATTER_SHAPE,
    C.CFG_SCATTER_RENDER_MODE: C.DEFAULT_SCATTER_RENDER_MODE,
    C.CFG_SCATTER_HUE_FILTER_ENABLED: C.DEFAULT_SCATTER_HUE_FILTER_ENABLED,
    C.CFG_SCATTER_HUE_CENTER: C.DEFAULT_SCATTER_HUE_CENTER,
    C.CFG_WHEEL_MODE: C.DEFAULT_WHEEL_MODE,
    C.CFG_RGB_HIST_MODE: C.DEFAULT_RGB_HIST_MODE,
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
    C.CFG_ALWAYS_ON_TOP: C.DEFAULT_ALWAYS_ON_TOP,
    C.CFG_MODE: C.DEFAULT_MODE,
    C.CFG_DIFF_THRESHOLD: C.DEFAULT_DIFF_THRESHOLD,
    C.CFG_STABLE_FRAMES: C.DEFAULT_STABLE_FRAMES,
    C.CFG_LAYOUT_ENGINE_VERSION: 0,
    C.CFG_LAYOUT_CURRENT: {},
    C.CFG_LAYOUT_PRESETS: {},
}
_CONFIG_PATH_CACHE: Path | None = None


def _legacy_user_config_dir() -> Path:
    # 旧来の保存先（AppData / XDG_CONFIG_HOME など）を返す。
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ChromaMonitor"


def _portable_config_dir() -> Path:
    # 「見える場所」に置くため、実行ファイル(開発時は起動スクリプト)の隣を優先する。
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        argv0 = Path(sys.argv[0]).expanduser()
        if argv0.exists():
            base = argv0.resolve().parent
        else:
            base = Path.cwd()
    return base / "config"


def _iter_candidate_config_dirs() -> Iterator[Path]:
    # 環境変数で上書き指定があれば最優先。
    override = os.environ.get("CHROMA_MONITOR_CONFIG_DIR")
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(_portable_config_dir())
    candidates.append(_legacy_user_config_dir())
    candidates.append(Path.cwd() / "config")

    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        yield path


def _is_dir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".chroma_monitor_write_test"
        probe.write_text("ok", encoding="utf-8")
        try:
            probe.unlink()
        except Exception:
            pass
        return True
    except Exception:
        return False


def config_path() -> Path:
    global _CONFIG_PATH_CACHE
    # 候補探索はI/Oを伴うため初回結果をキャッシュして再利用する。
    if _CONFIG_PATH_CACHE is not None:
        return _CONFIG_PATH_CACHE
    for cfg_dir in _iter_candidate_config_dirs():
        if not _is_dir_writable(cfg_dir):
            continue
        _CONFIG_PATH_CACHE = cfg_dir / "settings.json"
        return _CONFIG_PATH_CACHE
    # ここに来るのは極めて稀。最低限 cwd 直下へ退避する。
    _CONFIG_PATH_CACHE = Path.cwd() / "settings.json"
    return _CONFIG_PATH_CACHE


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
