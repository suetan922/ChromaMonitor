"""キャンバスプレビューで共有する定数。"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class CanvasRatioPreset:
    """キャンバス比率プリセット。"""

    name: str
    ratio_w: float
    ratio_h: float
    preset_id: str = ""
    is_builtin: bool = False
    default_name: str = ""


CANVAS_ORIENTATION_LANDSCAPE = "landscape"
CANVAS_ORIENTATION_PORTRAIT = "portrait"
CANVAS_ORIENTATIONS = (
    CANVAS_ORIENTATION_LANDSCAPE,
    CANVAS_ORIENTATION_PORTRAIT,
)

CANVAS_FIT_CONTAIN = "contain"
CANVAS_FIT_COVER = "cover"
CANVAS_FIT_CUSTOM = "custom"

CANVAS_RATIO_PRESETS = (
    CanvasRatioPreset(
        "1:1",
        1.0,
        1.0,
        preset_id="standard_1_1",
        is_builtin=True,
        default_name="1:1",
    ),
    CanvasRatioPreset(
        "4:3",
        4.0,
        3.0,
        preset_id="standard_4_3",
        is_builtin=True,
        default_name="4:3",
    ),
    CanvasRatioPreset(
        "3:2",
        3.0,
        2.0,
        preset_id="standard_3_2",
        is_builtin=True,
        default_name="3:2",
    ),
    CanvasRatioPreset(
        "16:9",
        16.0,
        9.0,
        preset_id="standard_16_9",
        is_builtin=True,
        default_name="16:9",
    ),
    CanvasRatioPreset(
        "黄金比",
        (1.0 + math.sqrt(5.0)) * 0.5,
        1.0,
        preset_id="standard_golden_ratio",
        is_builtin=True,
        default_name="黄金比",
    ),
    CanvasRatioPreset(
        "白銀比",
        math.sqrt(2.0),
        1.0,
        preset_id="standard_silver_ratio",
        is_builtin=True,
        default_name="白銀比",
    ),
)

DEFAULT_CANVAS_RATIO_PRESET_ID = "standard_4_3"
DEFAULT_CANVAS_RATIO_PRESET_NAME = DEFAULT_CANVAS_RATIO_PRESET_ID
CANVAS_PREVIEW_BACKGROUND_LIGHT = "light"
CANVAS_PREVIEW_BACKGROUND_DARK = "dark"
CANVAS_PREVIEW_BACKGROUND_MODES = (
    CANVAS_PREVIEW_BACKGROUND_LIGHT,
    CANVAS_PREVIEW_BACKGROUND_DARK,
)


def _fallback_preset_name(value: object, default: str) -> str:
    """空文字を避けた表示名を返す。"""
    text = str(value or "").strip()
    return text or str(default or "").strip() or "カスタム比率"


def default_canvas_ratio_presets() -> tuple[CanvasRatioPreset, ...]:
    """既定の標準プリセット列を返す。"""
    return tuple(CANVAS_RATIO_PRESETS)


def find_canvas_ratio_preset(
    preset_id: str,
    presets: tuple[CanvasRatioPreset, ...] | list[CanvasRatioPreset] | None = None,
) -> CanvasRatioPreset:
    """内部 ID から対象プリセットを返す。"""
    available = tuple(CANVAS_RATIO_PRESETS if presets is None else presets)
    if not available:
        return CANVAS_RATIO_PRESETS[0]
    current_id = str(preset_id or "").strip()
    return next(
        (preset for preset in available if preset.preset_id == current_id),
        available[0],
    )


def canvas_ratio_presets_from_payload(payload: object) -> tuple[CanvasRatioPreset, ...]:
    """保存 payload からプリセット一覧を復元する。"""
    builtin_map = {
        preset.preset_id: preset
        for preset in CANVAS_RATIO_PRESETS
        if str(preset.preset_id or "").strip()
    }
    results: list[CanvasRatioPreset] = []
    seen_ids: set[str] = set()
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            preset_id = str(item.get("id") or item.get("preset_id") or "").strip()
            if not preset_id or preset_id in seen_ids:
                continue
            if preset_id in builtin_map:
                base = builtin_map[preset_id]
                results.append(
                    replace(
                        base,
                        name=_fallback_preset_name(
                            item.get("name") or item.get("display_name"),
                            base.default_name or base.name,
                        ),
                    )
                )
                seen_ids.add(preset_id)
                continue
            try:
                ratio_w = float(item.get("ratio_w") or item.get("ratio_width"))
                ratio_h = float(item.get("ratio_h") or item.get("ratio_height"))
            except (TypeError, ValueError):
                continue
            if ratio_w <= 0.0 or ratio_h <= 0.0:
                continue
            name = _fallback_preset_name(
                item.get("name") or item.get("display_name"),
                "カスタム比率",
            )
            results.append(
                CanvasRatioPreset(
                    name=name,
                    ratio_w=ratio_w,
                    ratio_h=ratio_h,
                    preset_id=preset_id,
                    is_builtin=False,
                    default_name=name,
                )
            )
            seen_ids.add(preset_id)
    for preset in CANVAS_RATIO_PRESETS:
        if preset.preset_id not in seen_ids:
            results.append(preset)
    return tuple(results)


def canvas_ratio_presets_to_payload(
    presets: tuple[CanvasRatioPreset, ...] | list[CanvasRatioPreset],
) -> list[dict[str, object]]:
    """プリセット一覧を保存用 payload へ直列化する。"""
    payload: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for preset in presets:
        preset_id = str(preset.preset_id or "").strip()
        if not preset_id or preset_id in seen_ids:
            continue
        seen_ids.add(preset_id)
        item: dict[str, object] = {
            "id": preset_id,
            "name": _fallback_preset_name(preset.name, preset.default_name or preset.name),
            "builtin": bool(preset.is_builtin),
        }
        if not preset.is_builtin:
            item["ratio_w"] = float(preset.ratio_w)
            item["ratio_h"] = float(preset.ratio_h)
        payload.append(item)
    return payload
