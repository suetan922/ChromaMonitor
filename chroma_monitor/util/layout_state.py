from typing import Any, Dict

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QGuiApplication

#: 保存時のキー名: ウィンドウジオメトリ。
_KEY_GEOMETRY = "geometry"
#: 保存時のキー名: ドック配置状態。
_KEY_STATE = "state"
#: 保存時のキー名: ドック可視フラグ群。
_KEY_VISIBLE_DOCKS = "visible_docks"
#: 保存時のキー名: 明示ジオメトリ矩形。
_KEY_GEOMETRY_RECT = "geometry_rect"
#: 保存時のキー名: 画面構成シグネチャ。
_KEY_DISPLAY_TOPOLOGY = "display_topology"
#: 保存時のキー名: フローティングドック矩形群。
_KEY_FLOATING_DOCK_GEOMETRY = "floating_dock_geometry"


def _encode_qbytearray(data: QByteArray) -> str:
    """`QByteArray` を設定保存用のBase64文字列へ変換する。"""
    return bytes(data.toBase64()).decode("ascii")


def _decode_qbytearray(text: str) -> QByteArray:
    """Base64文字列を `QByteArray` へ復元する。"""
    if not text:
        return QByteArray()
    return QByteArray.fromBase64(text.encode("ascii"))


def _restore_encoded_blob(window, encoded: Any, restore_fn) -> bool:
    """エンコード済み状態を復元関数へ渡して適用する。"""
    if not isinstance(encoded, str) or not encoded:
        return False
    return bool(restore_fn(_decode_qbytearray(encoded)))


def _apply_visible_docks(docks: Dict[str, Any], visible: Any) -> bool:
    """保存された可視状態をドック群へ適用する。"""
    if not isinstance(visible, dict) or not visible:
        return False
    for name, flag in visible.items():
        dock = docks.get(name)
        if dock is not None:
            dock.setVisible(bool(flag))
    return True


def _capture_window_geometry_rect(window) -> dict[str, int]:
    """ウィンドウ geometry を単純矩形として取得する。"""
    geom = window.geometry()
    return {
        "x": int(geom.x()),
        "y": int(geom.y()),
        "w": int(geom.width()),
        "h": int(geom.height()),
    }


def _normalize_geometry_rect(raw: Any) -> tuple[int, int, int, int] | None:
    """保存済み geometry_rect を検証済みタプルへ変換する。"""
    if not isinstance(raw, dict):
        return None
    try:
        x = int(raw.get("x", 0))
        y = int(raw.get("y", 0))
        w = int(raw.get("w", 0))
        h = int(raw.get("h", 0))
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


def _capture_floating_dock_geometry(docks: Dict[str, Any]) -> dict[str, dict[str, int]]:
    """フローティング中ドックの geometry を保存用辞書へ変換する。"""
    out: dict[str, dict[str, int]] = {}
    for name, dock in docks.items():
        if dock is None or not bool(getattr(dock, "isFloating", lambda: False)()):
            continue
        try:
            geom = dock.geometry()
        except Exception:
            continue
        if geom.width() <= 0 or geom.height() <= 0:
            continue
        out[str(name)] = {
            "x": int(geom.x()),
            "y": int(geom.y()),
            "w": int(geom.width()),
            "h": int(geom.height()),
        }
    return out


def _capture_display_topology() -> list[dict[str, int]]:
    """現在のスクリーン構成を比較用シグネチャとして取得する。"""
    topology: list[dict[str, int]] = []
    for screen in QGuiApplication.screens():
        rect = screen.geometry()
        topology.append(
            {
                "x": int(rect.x()),
                "y": int(rect.y()),
                "w": int(rect.width()),
                "h": int(rect.height()),
            }
        )
    topology.sort(key=lambda item: (item["x"], item["y"], item["w"], item["h"]))
    return topology


def _normalize_display_topology(raw: Any) -> list[tuple[int, int, int, int]]:
    """保存済み/現在値を同一比較形式へ正規化する。"""
    if not isinstance(raw, list):
        return []
    normalized: list[tuple[int, int, int, int]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            x = int(entry.get("x", 0))
            y = int(entry.get("y", 0))
            w = int(entry.get("w", 0))
            h = int(entry.get("h", 0))
        except Exception:
            continue
        if w <= 0 or h <= 0:
            continue
        normalized.append((x, y, w, h))
    normalized.sort()
    return normalized


def capture_layout_state(window, docks: Dict[str, Any]) -> Dict[str, Any]:
    """ウィンドウ配置・ドック状態を保存可能な辞書へシリアライズする。"""
    return {
        _KEY_GEOMETRY: _encode_qbytearray(window.saveGeometry()),
        _KEY_STATE: _encode_qbytearray(window.saveState()),
        _KEY_VISIBLE_DOCKS: {name: bool(dock.isVisible()) for name, dock in docks.items()},
        _KEY_GEOMETRY_RECT: _capture_window_geometry_rect(window),
        _KEY_DISPLAY_TOPOLOGY: _capture_display_topology(),
        _KEY_FLOATING_DOCK_GEOMETRY: _capture_floating_dock_geometry(docks),
    }


def apply_layout_state(window, docks: Dict[str, Any], data: Dict[str, Any]) -> bool:
    """保存済みレイアウト辞書をウィンドウへ復元適用する。"""
    if not isinstance(data, dict):
        return False

    restored = False
    restored = (
        _restore_encoded_blob(window, data.get(_KEY_GEOMETRY, ""), window.restoreGeometry)
        or restored
    )
    restored = (
        _restore_encoded_blob(window, data.get(_KEY_STATE, ""), window.restoreState) or restored
    )
    restored = _apply_visible_docks(docks, data.get(_KEY_VISIBLE_DOCKS, {})) or restored

    return restored


def restore_layout_geometry(window, data: Dict[str, Any]) -> bool:
    """保存済みレイアウト辞書からウィンドウ geometry だけを再適用する。"""
    if not isinstance(data, dict):
        return False
    return _restore_encoded_blob(window, data.get(_KEY_GEOMETRY, ""), window.restoreGeometry)


def restore_layout_geometry_rect(window, data: Dict[str, Any]) -> bool:
    """保存済みレイアウト辞書から明示矩形を再適用する。"""
    if not isinstance(data, dict):
        return False
    rect = _normalize_geometry_rect(data.get(_KEY_GEOMETRY_RECT))
    if rect is None:
        return False
    x, y, w, h = rect
    try:
        window.setGeometry(int(x), int(y), int(w), int(h))
    except Exception:
        return False
    return True


def restore_floating_dock_geometry(docks: Dict[str, Any], data: Dict[str, Any]) -> int:
    """保存済みフローティングドック矩形を再適用し、適用件数を返す。"""
    if not isinstance(data, dict):
        return 0
    raw = data.get(_KEY_FLOATING_DOCK_GEOMETRY, {})
    if not isinstance(raw, dict):
        return 0
    applied = 0
    for name, rect_raw in raw.items():
        dock = docks.get(name)
        if dock is None:
            continue
        if not bool(getattr(dock, "isFloating", lambda: False)()):
            continue
        rect = _normalize_geometry_rect(rect_raw)
        if rect is None:
            continue
        x, y, w, h = rect
        try:
            dock.setGeometry(int(x), int(y), int(w), int(h))
            applied += 1
        except Exception:
            continue
    return int(applied)


def is_layout_display_topology_unchanged(data: Dict[str, Any]) -> bool:
    """保存時と現在でスクリーン構成が同一かを返す。"""
    if not isinstance(data, dict):
        return False
    saved = _normalize_display_topology(data.get(_KEY_DISPLAY_TOPOLOGY, []))
    if not saved:
        # 旧保存データは比較不能なので安全側(補正あり)へ倒す。
        return False
    current = _normalize_display_topology(_capture_display_topology())
    if not current:
        return False
    return saved == current
