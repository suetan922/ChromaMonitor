from typing import Any, Dict

from PySide6.QtCore import QByteArray

#: 保存時のキー名: ウィンドウジオメトリ。
_KEY_GEOMETRY = "geometry"
#: 保存時のキー名: ドック配置状態。
_KEY_STATE = "state"
#: 保存時のキー名: ドック可視フラグ群。
_KEY_VISIBLE_DOCKS = "visible_docks"


def _encode_qbytearray(data: QByteArray) -> str:
    return bytes(data.toBase64()).decode("ascii")


def _decode_qbytearray(text: str) -> QByteArray:
    if not text:
        return QByteArray()
    return QByteArray.fromBase64(text.encode("ascii"))


def _restore_encoded_blob(window, encoded: Any, restore_fn) -> bool:
    if not isinstance(encoded, str) or not encoded:
        return False
    return bool(restore_fn(_decode_qbytearray(encoded)))


def _apply_visible_docks(docks: Dict[str, Any], visible: Any) -> bool:
    if not isinstance(visible, dict) or not visible:
        return False
    for name, flag in visible.items():
        dock = docks.get(name)
        if dock is not None:
            dock.setVisible(bool(flag))
    return True


def capture_layout_state(window, docks: Dict[str, Any]) -> Dict[str, Any]:
    return {
        _KEY_GEOMETRY: _encode_qbytearray(window.saveGeometry()),
        _KEY_STATE: _encode_qbytearray(window.saveState()),
        _KEY_VISIBLE_DOCKS: {name: bool(dock.isVisible()) for name, dock in docks.items()},
    }


def apply_layout_state(window, docks: Dict[str, Any], data: Dict[str, Any]) -> bool:
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
