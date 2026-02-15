from typing import Dict, Any

from PySide6.QtCore import QByteArray


def _encode_qbytearray(data: QByteArray) -> str:
    return bytes(data.toBase64()).decode("ascii")


def _decode_qbytearray(text: str) -> QByteArray:
    if not text:
        return QByteArray()
    return QByteArray.fromBase64(text.encode("ascii"))


def capture_layout_state(window, docks: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "geometry": _encode_qbytearray(window.saveGeometry()),
        "state": _encode_qbytearray(window.saveState()),
        "visible_docks": {name: bool(dock.isVisible()) for name, dock in docks.items()},
    }


def apply_layout_state(window, docks: Dict[str, Any], data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False

    restored = False
    state_b64 = data.get("state", "")
    geo_b64 = data.get("geometry", "")
    visible = data.get("visible_docks", {})

    if isinstance(geo_b64, str) and geo_b64:
        restored = bool(window.restoreGeometry(_decode_qbytearray(geo_b64))) or restored
    if isinstance(state_b64, str) and state_b64:
        restored = bool(window.restoreState(_decode_qbytearray(state_b64))) or restored

    if isinstance(visible, dict) and visible:
        for name, flag in visible.items():
            dock = docks.get(name)
            if dock is not None:
                dock.setVisible(bool(flag))
        restored = True

    return restored
