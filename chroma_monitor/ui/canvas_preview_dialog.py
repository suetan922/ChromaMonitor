"""キャンバスプレビュー用ダイアログ。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
import sys
import traceback
from uuid import uuid4

import numpy as np
from PySide6.QtCore import QEvent, QObject, QRect, QSize, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .input_widgets import configure_numeric_input
from ..util import constants as APP_C
from ..util.config import load_config, save_config
from ..util.debug_log import write_window_layout_debug_log
from ..util.theme import get_ui_theme, refresh_widget_style
from ..views.canvas_preview import CanvasPreviewWidget
from ..views.canvas_preview_constants import (
    CANVAS_FIT_CONTAIN,
    CANVAS_FIT_COVER,
    CANVAS_FIT_CUSTOM,
    CANVAS_ORIENTATION_LANDSCAPE,
    CANVAS_ORIENTATION_PORTRAIT,
    CANVAS_PREVIEW_BACKGROUND_DARK,
    CANVAS_PREVIEW_BACKGROUND_LIGHT,
    DEFAULT_CANVAS_RATIO_PRESET_ID,
    CanvasRatioPreset,
    canvas_ratio_presets_from_payload,
    canvas_ratio_presets_to_payload,
    default_canvas_ratio_presets,
    find_canvas_ratio_preset,
)
from ..views.canvas_preview_math import (
    CanvasPreviewTransform,
    canvas_pixels_from_image_long_edge,
    fit_scale_for_mode,
    oriented_ratio,
    preview_extents,
)

_PREVIEW_ZOOM_MIN_PERCENT = 10
_PREVIEW_ZOOM_MAX_PERCENT = 300
_PRESET_RATIO_MIN = 0.01
_PRESET_RATIO_MAX = 9999.0
_PRESET_RATIO_DECIMALS = 2
_USER_PRESET_NAME_PREFIX = "カスタム"
_BUILTIN_PRESET_DELETE_TOOLTIP = "標準プリセットは削除できません"
_EDGE_TEXT_ZERO_THRESHOLD_PX = 0.05
_ROTATION_HALF_TURN_DEG = 180.0
_ROTATION_FULL_TURN_DEG = 360.0
_RATIO_COMPARE_EPSILON = 1e-9
_RESET_BUTTON_SIZE = QSize(36, 36)
_RESET_ICON_SIZE = QSize(28, 28)
_RESET_ICON_REL_PATH = Path("assets/icons/arrow-rotate-left-solid.png")
_RESET_ICON_SOURCE_CACHE: QPixmap | None = None
_RESET_ICON_SOURCE_BBOX_CACHE: QRect | None = None
_RESET_ICON_SOURCE_CACHE_KEY: int | None = None
_RESET_ICON_FALLBACK_CACHE: dict[tuple[int, int], QPixmap] = {}
_RESET_ICON_PIXMAP_CACHE: dict[tuple[int, int, int, int, int, int], QPixmap] = {}
_RESET_ICON_CACHE: dict[tuple[int, int, int, int, int], QIcon] = {}
_THEME_REFRESH_EVENTS = {
    QEvent.PaletteChange,
    QEvent.ApplicationPaletteChange,
    QEvent.StyleChange,
}
if hasattr(QEvent, "ThemeChange"):
    _THEME_REFRESH_EVENTS.add(QEvent.ThemeChange)


@dataclass(frozen=True, slots=True)
class CanvasPreviewSnapshot:
    """ツール起動時点で固定した入力画像。"""

    bgr: np.ndarray
    source_label: str
    title: str


def _qimage_from_bgr(bgr: np.ndarray) -> QImage:
    """BGR 配列を Qt 描画用 `QImage` に変換する。"""
    bgr = np.ascontiguousarray(bgr)
    rgb = np.ascontiguousarray(bgr[:, :, ::-1])
    height, width = rgb.shape[:2]
    return QImage(rgb.data, width, height, width * 3, QImage.Format_RGB888).copy()


def _app_resource_base_dir() -> Path:
    """PyInstaller / 開発実行の両方で asset 基準ディレクトリを返す。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        try:
            return Path(meipass)
        except Exception:
            pass
    return Path(__file__).resolve().parent.parent.parent


def _reset_icon_asset_paths() -> tuple[Path, ...]:
    """reset icon asset ?????????"""
    base = _app_resource_base_dir()
    exe_dir = Path(sys.executable).resolve().parent
    return (
        base / _RESET_ICON_REL_PATH,
        exe_dir / _RESET_ICON_REL_PATH,
        exe_dir / _RESET_ICON_REL_PATH.name,
    )


def _clear_reset_icon_caches() -> None:
    """reset icon ?? cache ???????"""
    global _RESET_ICON_SOURCE_CACHE
    global _RESET_ICON_SOURCE_BBOX_CACHE
    global _RESET_ICON_SOURCE_CACHE_KEY
    _RESET_ICON_SOURCE_CACHE = None
    _RESET_ICON_SOURCE_BBOX_CACHE = None
    _RESET_ICON_SOURCE_CACHE_KEY = None
    _RESET_ICON_FALLBACK_CACHE.clear()
    _RESET_ICON_PIXMAP_CACHE.clear()
    _RESET_ICON_CACHE.clear()


def _load_reset_icon_source_pixmap() -> QPixmap:
    """reset icon asset ?????? source pixmap ????"""
    global _RESET_ICON_SOURCE_CACHE
    global _RESET_ICON_SOURCE_BBOX_CACHE
    global _RESET_ICON_SOURCE_CACHE_KEY
    if _RESET_ICON_SOURCE_CACHE is not None:
        return QPixmap(_RESET_ICON_SOURCE_CACHE)
    for path_candidate in _reset_icon_asset_paths():
        try:
            if not path_candidate.is_file():
                continue
            pixmap = QPixmap(str(path_candidate))
            if not pixmap.isNull():
                _RESET_ICON_SOURCE_CACHE = QPixmap(pixmap)
                _RESET_ICON_SOURCE_BBOX_CACHE = None
                _RESET_ICON_SOURCE_CACHE_KEY = int(pixmap.cacheKey())
                return QPixmap(_RESET_ICON_SOURCE_CACHE)
        except Exception:
            continue
    _RESET_ICON_SOURCE_CACHE = QPixmap()
    _RESET_ICON_SOURCE_BBOX_CACHE = QRect()
    _RESET_ICON_SOURCE_CACHE_KEY = None
    return QPixmap()


def _source_alpha_bounding_rect(source: QPixmap) -> QRect:
    """source pixmap ?????? bounding box ????"""
    global _RESET_ICON_SOURCE_BBOX_CACHE
    global _RESET_ICON_SOURCE_CACHE_KEY
    if source.isNull():
        return QRect()
    source_cache_key = int(source.cacheKey())
    if (
        _RESET_ICON_SOURCE_BBOX_CACHE is not None
        and _RESET_ICON_SOURCE_CACHE_KEY is not None
        and source_cache_key == _RESET_ICON_SOURCE_CACHE_KEY
    ):
        return QRect(_RESET_ICON_SOURCE_BBOX_CACHE)

    image = source.toImage().convertToFormat(QImage.Format_ARGB32)
    width = int(image.width())
    height = int(image.height())
    if width <= 0 or height <= 0:
        return QRect()

    bits = image.constBits()
    alpha = np.frombuffer(bits, dtype=np.uint8)
    alpha = alpha.reshape((height, int(image.bytesPerLine())))[:, : width * 4]
    alpha = alpha.reshape((height, width, 4))[:, :, 3]
    coords = np.argwhere(alpha > 0)
    if coords.size == 0:
        rect = QRect()
    else:
        min_y, min_x = coords.min(axis=0)
        max_y, max_x = coords.max(axis=0)
        rect = QRect(int(min_x), int(min_y), int(max_x - min_x + 1), int(max_y - min_y + 1))

    if (
        _RESET_ICON_SOURCE_CACHE_KEY is not None
        and source_cache_key == _RESET_ICON_SOURCE_CACHE_KEY
    ):
        _RESET_ICON_SOURCE_BBOX_CACHE = QRect(rect)
    return rect


def _fallback_reset_icon_source_pixmap(widget: QWidget, size: QSize) -> QPixmap:
    """asset ???? Qt ?? reload icon pixmap ????"""
    cache_key = (int(size.width()), int(size.height()))
    cached = _RESET_ICON_FALLBACK_CACHE.get(cache_key)
    if cached is not None:
        return QPixmap(cached)
    if widget.style() is None:
        return QPixmap()
    pixmap = widget.style().standardIcon(QStyle.SP_BrowserReload).pixmap(size)
    _RESET_ICON_FALLBACK_CACHE[cache_key] = QPixmap(pixmap)
    return QPixmap(pixmap)


def _tinted_icon_pixmap(
    source: QPixmap,
    color: QColor,
    *,
    size: QSize,
    device_pixel_ratio: float,
) -> QPixmap:
    """source pixmap ????? tint ?? pixmap ????"""
    if source.isNull():
        return QPixmap()
    source_rect = _source_alpha_bounding_rect(source)
    if not source_rect.isValid() or source_rect.isEmpty():
        source_rect = source.rect()
    ratio = max(1.0, float(device_pixel_ratio))
    ratio_milli = max(1, int(round(ratio * 1000.0)))
    rgba = int(QColor(color).rgba())
    pixmap_cache_key = (
        int(source.cacheKey()),
        rgba,
        int(size.width()),
        int(size.height()),
        ratio_milli,
        0,
    )
    cached = _RESET_ICON_PIXMAP_CACHE.get(pixmap_cache_key)
    if cached is not None:
        return QPixmap(cached)

    logical_width = max(1, int(size.width()))
    logical_height = max(1, int(size.height()))
    pixmap = QPixmap(int(round(logical_width * ratio)), int(round(logical_height * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(pixmap.rect(), source, source_rect)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
    finally:
        painter.end()
    _RESET_ICON_PIXMAP_CACHE[pixmap_cache_key] = QPixmap(pixmap)
    return pixmap


def _reset_icon_pixmap(
    color: QColor,
    *,
    size: QSize,
    device_pixel_ratio: float,
    widget: QWidget | None = None,
) -> QPixmap:
    """??????????? circular arrow ??????????"""
    source = _load_reset_icon_source_pixmap()
    if source.isNull() and widget is not None:
        source = _fallback_reset_icon_source_pixmap(widget, size)
    return _tinted_icon_pixmap(
        source,
        color,
        size=size,
        device_pixel_ratio=device_pixel_ratio,
    )


def _reset_icon_from_palette(widget: QWidget, *, size: QSize = _RESET_ICON_SIZE) -> QIcon:
    """?? palette ?????????????????"""
    palette = widget.palette()
    ratio = float(widget.devicePixelRatioF())
    ratio_milli = max(1, int(round(ratio * 1000.0)))
    normal = QColor(palette.color(QPalette.ButtonText))
    disabled = QColor(palette.color(QPalette.Disabled, QPalette.ButtonText))
    icon_cache_key = (
        int(normal.rgba()),
        int(disabled.rgba()),
        int(size.width()),
        int(size.height()),
        ratio_milli,
    )
    cached_icon = _RESET_ICON_CACHE.get(icon_cache_key)
    if cached_icon is not None:
        return QIcon(cached_icon)

    normal_pm = _reset_icon_pixmap(normal, size=size, device_pixel_ratio=ratio, widget=widget)
    disabled_pm = _reset_icon_pixmap(disabled, size=size, device_pixel_ratio=ratio, widget=widget)
    icon = QIcon()
    if not normal_pm.isNull():
        icon.addPixmap(normal_pm, QIcon.Normal, QIcon.Off)
    if not disabled_pm.isNull():
        icon.addPixmap(disabled_pm, QIcon.Disabled, QIcon.Off)
    _RESET_ICON_CACHE[icon_cache_key] = QIcon(icon)
    return icon


def _format_edge_value(value: float) -> str:
    """px 値を読みやすい文字列へ整形する。"""
    if abs(float(value)) < _EDGE_TEXT_ZERO_THRESHOLD_PX:
        return "0 px"
    rounded = round(float(value), 1)
    if abs(rounded - round(rounded)) < _EDGE_TEXT_ZERO_THRESHOLD_PX:
        return f"{int(round(rounded))} px"
    return f"{rounded:.1f} px"


def _format_edge_values(left: float, top: float, right: float, bottom: float) -> str:
    """上下左右量を 1 行文字列へ整形する。"""
    values = (float(left), float(top), float(right), float(bottom))
    if all(abs(value) < _EDGE_TEXT_ZERO_THRESHOLD_PX for value in values):
        return "なし"
    return (
        f"左 {_format_edge_value(left)} / 上 {_format_edge_value(top)} / "
        f"右 {_format_edge_value(right)} / 下 {_format_edge_value(bottom)}"
    )


def _load_ratio_presets_from_config() -> list[CanvasRatioPreset]:
    """設定から保存済みプリセット一覧を読み込む。"""
    cfg = load_config()
    payload = cfg.get(APP_C.CFG_CANVAS_RATIO_PRESETS, [])
    presets = canvas_ratio_presets_from_payload(payload)
    return list(presets or default_canvas_ratio_presets())


def _default_background_tone_for_theme(theme_name: str | None) -> str:
    """テーマ未保存時の透明背景トーン既定値を返す。"""
    if str(theme_name or "").strip() == APP_C.UI_THEME_DARK:
        return CANVAS_PREVIEW_BACKGROUND_DARK
    return CANVAS_PREVIEW_BACKGROUND_LIGHT


def _load_background_tone_from_config(theme_name: str | None) -> str:
    """保存値優先で透明背景トーンを設定から復元する。"""
    cfg = load_config()
    tone = str(cfg.get(APP_C.CFG_CANVAS_PREVIEW_BACKGROUND_TONE, "") or "").strip()
    if tone in {
        CANVAS_PREVIEW_BACKGROUND_LIGHT,
        CANVAS_PREVIEW_BACKGROUND_DARK,
    }:
        return tone
    return _default_background_tone_for_theme(theme_name)


def _root_exception(exc: BaseException) -> BaseException:
    """`__cause__` を辿って元例外を返す。"""
    current = exc
    while True:
        next_exc = current.__cause__
        if next_exc is None or next_exc is current:
            return current
        current = next_exc


def _format_traceback_text(exc: BaseException) -> str:
    """例外の traceback 文字列を返す。"""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


@contextmanager
def signal_blocked(*widgets: QObject | None) -> Iterator[None]:
    """複数 widget の Qt シグナルを一時的にブロックする。"""
    blockers = [QSignalBlocker(widget) for widget in widgets if widget is not None]
    try:
        yield
    finally:
        blockers.clear()


class CanvasPreviewDialog(QDialog):
    """構図・出力シミュレーション用のツールウィンドウ。"""

    def __init__(self, main_window, snapshot: CanvasPreviewSnapshot):
        """入力画像を元に UI を構築する。"""
        super().__init__(main_window)
        self._main_window = main_window
        self._ui_theme_name = getattr(main_window, "_ui_theme_name", None)
        self._snapshot = snapshot
        self._source_image = _qimage_from_bgr(snapshot.bgr)
        self._ratio_presets = _load_ratio_presets_from_config()
        default_preset = find_canvas_ratio_preset(
            DEFAULT_CANVAS_RATIO_PRESET_ID,
            self._ratio_presets,
        )
        self._preset_id = default_preset.preset_id
        self._orientation = (
            CANVAS_ORIENTATION_LANDSCAPE
            if self._source_image.width() > self._source_image.height()
            else CANVAS_ORIENTATION_PORTRAIT
        )
        self._background_tone = _load_background_tone_from_config(self._ui_theme_name)
        self._draft_preset: CanvasRatioPreset | None = None
        self._transform = CanvasPreviewTransform()
        self._preview_zoom = 1.0
        self._fit_mode = CANVAS_FIT_CONTAIN
        self._theme_refreshing = False
        self._ui_ready = False
        self._syncing_controls = False

        flags = self.windowFlags()
        flags &= ~Qt.Dialog
        flags |= (
            Qt.Window
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setWindowFlags(flags)
        self.setWindowTitle("キャンバスプレビュー")
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(1240, 780)

        self._run_init_step("UI構築", self._build_ui)
        self._ui_ready = True
        self._run_init_step("初期状態の適用", self._apply_initial_state)

    def _debug_state_fields(self, *, include_canvas: bool = False) -> dict[str, object]:
        """ログへ添える現在状態を安全にまとめる。"""
        fields: dict[str, object] = {
            "preset_id": str(getattr(self, "_preset_id", "") or ""),
            "orientation": str(getattr(self, "_orientation", "") or ""),
            "fit_mode": str(getattr(self, "_fit_mode", "") or ""),
            "preview_zoom": float(getattr(self, "_preview_zoom", 1.0)),
            "transform": repr(getattr(self, "_transform", CanvasPreviewTransform())),
            "ratio_preset_count": len(getattr(self, "_ratio_presets", ())),
        }
        image = getattr(self, "_source_image", None)
        if image is not None:
            try:
                fields["image_width"] = int(image.width())
                fields["image_height"] = int(image.height())
            except Exception as exc:
                fields["image_size_error"] = f"{type(exc).__name__}: {exc}"
        try:
            ratio_w, ratio_h = self._current_ratio()
            fields["ratio_w"] = float(ratio_w)
            fields["ratio_h"] = float(ratio_h)
        except Exception as exc:
            fields["ratio_error"] = f"{type(exc).__name__}: {exc}"
        if include_canvas:
            try:
                canvas_width, canvas_height = self._current_canvas_pixels()
                fields["canvas_width"] = int(canvas_width)
                fields["canvas_height"] = int(canvas_height)
            except Exception as exc:
                fields["canvas_error"] = f"{type(exc).__name__}: {exc}"
        return fields

    def _log_debug(self, event: str, *, include_canvas: bool = False, **fields) -> None:
        """ダイアログ初期化・同期系の調査ログを出す。"""
        payload = self._debug_state_fields(include_canvas=include_canvas)
        payload.update(fields)
        write_window_layout_debug_log(event, **payload)

    def _log_exception(
        self,
        event: str,
        exc: BaseException,
        *,
        include_canvas: bool = False,
        **fields,
    ) -> None:
        """例外を root cause と traceback 付きで記録する。"""
        root = _root_exception(exc)
        payload = self._debug_state_fields(include_canvas=include_canvas)
        payload.update(fields)
        payload.update(
            {
                "wrapped_type": type(exc).__name__,
                "wrapped_message": str(exc),
                "root_type": type(root).__name__,
                "root_message": str(root),
                "traceback_text": _format_traceback_text(exc),
            }
        )
        write_window_layout_debug_log(event, **payload)

    def _run_logged_step(
        self,
        event_prefix: str,
        stage: str,
        callback,
        *,
        include_canvas: bool = False,
        **fields,
    ):
        """begin/ok/fail を揃えてサブステップを実行する。"""
        self._log_debug(
            f"{event_prefix}_begin",
            stage=stage,
            include_canvas=include_canvas,
            **fields,
        )
        try:
            result = callback()
        except Exception as exc:
            self._log_exception(
                f"{event_prefix}_fail",
                exc,
                stage=stage,
                include_canvas=include_canvas,
                **fields,
            )
            raise
        self._log_debug(
            f"{event_prefix}_ok",
            stage=stage,
            include_canvas=include_canvas,
            **fields,
        )
        return result

    def _run_init_step(self, stage: str, callback) -> None:
        """初期化段階を文脈付きで実行する。"""
        self._log_debug("canvas_preview_init_step_begin", stage=stage)
        try:
            callback()
        except Exception as exc:
            self._log_exception("canvas_preview_init_step_fail", exc, stage=stage)
            self._log_exception("canvas_preview_init_error", exc, stage=stage)
            raise RuntimeError(f"キャンバスプレビュー初期化中に {stage} で失敗しました") from exc
        self._log_debug("canvas_preview_init_step_ok", stage=stage)

    def _build_ui_section(self, name: str, builder):
        """UI セクション構築を文脈付きで実行する。"""
        try:
            return builder()
        except Exception as exc:
            raise RuntimeError(f"{name} の構築に失敗しました") from exc

    def _build_ui(self) -> None:
        """3 カラム UI を構築する。"""
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(self._build_ui_section("左カラム", self._build_left_column), 0)
        root.addWidget(self._build_ui_section("中央カラム", self._build_center_column), 1)
        root.addWidget(self._build_ui_section("右カラム", self._build_right_column), 0)

    def _build_left_column(self) -> QWidget:
        """左カラムを構築する。"""
        holder = QWidget()
        holder.setFixedWidth(292)
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_ratio_box(), 1)
        layout.addWidget(self._build_preset_manage_box(), 0)
        return holder

    def _build_ratio_box(self) -> QGroupBox:
        """比率一覧グループを構築する。"""
        ratio_box = QGroupBox("キャンバス比率")
        ratio_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        ratio_layout = QVBoxLayout(ratio_box)
        ratio_layout.setContentsMargins(12, 12, 12, 12)
        ratio_layout.setSpacing(8)
        ratio_layout.addWidget(self._build_orientation_row())
        ratio_layout.addWidget(self._build_ratio_preset_list(), 1)
        return ratio_box

    def _build_orientation_row(self) -> QWidget:
        """向き切替行を構築する。"""
        self.orientation_row = QWidget()
        orientation_layout = QHBoxLayout(self.orientation_row)
        orientation_layout.setContentsMargins(0, 0, 0, 0)
        orientation_layout.setSpacing(10)
        self.radio_landscape = QRadioButton("横")
        self.radio_portrait = QRadioButton("縦")
        self.radio_landscape.setProperty("chromaRole", "canvasOrientation")
        self.radio_portrait.setProperty("chromaRole", "canvasOrientation")
        self.orientation_group = QButtonGroup(self)
        self.orientation_group.addButton(self.radio_landscape)
        self.orientation_group.addButton(self.radio_portrait)
        self.radio_landscape.toggled.connect(self._on_orientation_toggled)
        self.radio_portrait.toggled.connect(self._on_orientation_toggled)
        orientation_layout.addWidget(self.radio_landscape)
        orientation_layout.addWidget(self.radio_portrait)
        orientation_layout.addStretch(1)
        return self.orientation_row

    def _build_ratio_preset_list(self) -> QListWidget:
        """比率プリセット一覧を構築する。"""
        self.list_ratio_presets = QListWidget()
        self.list_ratio_presets.setProperty("chromaRole", "canvasPresetList")
        self.list_ratio_presets.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_ratio_presets.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_ratio_presets.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.list_ratio_presets.currentRowChanged.connect(self._on_ratio_preset_row_changed)
        return self.list_ratio_presets

    def _build_preset_manage_box(self) -> QGroupBox:
        """プリセット編集グループを構築する。"""
        manage_box = QGroupBox("プリセット編集")
        manage_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        manage_form = QFormLayout(manage_box)
        manage_form.setContentsMargins(12, 12, 12, 12)
        manage_form.setSpacing(8)

        self.edit_preset_name = QLineEdit()
        self.edit_preset_name.setPlaceholderText("表示名")
        manage_form.addRow("表示名", self.edit_preset_name)
        manage_form.addRow("比率", self._build_preset_ratio_editor_row())
        manage_form.addRow(self._build_preset_button_row())
        return manage_box

    def _build_preset_ratio_editor_row(self) -> QWidget:
        """プリセット比率編集行を構築する。"""
        ratio_editor_row = QWidget()
        ratio_editor_layout = QHBoxLayout(ratio_editor_row)
        ratio_editor_layout.setContentsMargins(0, 0, 0, 0)
        ratio_editor_layout.setSpacing(6)
        self.spin_preset_ratio_w = self._build_double_spin(
            _PRESET_RATIO_MIN,
            _PRESET_RATIO_MAX,
            step=0.01,
            decimals=_PRESET_RATIO_DECIMALS,
        )
        self.spin_preset_ratio_h = self._build_double_spin(
            _PRESET_RATIO_MIN,
            _PRESET_RATIO_MAX,
            step=0.01,
            decimals=_PRESET_RATIO_DECIMALS,
        )
        ratio_editor_layout.addWidget(QLabel("W"))
        ratio_editor_layout.addWidget(self.spin_preset_ratio_w, 1)
        ratio_editor_layout.addWidget(QLabel(":"))
        ratio_editor_layout.addWidget(QLabel("H"))
        ratio_editor_layout.addWidget(self.spin_preset_ratio_h, 1)
        return ratio_editor_row

    def _build_preset_button_row(self) -> QWidget:
        """プリセット編集ボタン行を構築する。"""
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)
        self.btn_add_preset = QPushButton("新規追加")
        self.btn_save_preset = QPushButton("保存")
        self.btn_delete_preset = QPushButton("削除")
        self.btn_add_preset.clicked.connect(self._start_new_user_preset)
        self.btn_save_preset.clicked.connect(self._save_selected_preset)
        self.btn_delete_preset.clicked.connect(self._delete_selected_preset)
        button_layout.addWidget(self.btn_add_preset)
        button_layout.addWidget(self.btn_save_preset)
        button_layout.addWidget(self.btn_delete_preset)
        return button_row

    def _build_center_column(self) -> QWidget:
        """中央カラムを構築する。"""
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.preview_widget = CanvasPreviewWidget()
        self.preview_widget.transformChanged.connect(self._on_preview_transform_changed)
        self.preview_widget.viewZoomChanged.connect(self._on_preview_view_zoom_changed)

        layout.addWidget(self._build_preview_zoom_row())
        layout.addWidget(self.preview_widget, 1)
        layout.addWidget(self._build_background_row())
        return holder

    def _build_preview_zoom_row(self) -> QWidget:
        """プレビュー表示倍率の操作行を構築する。"""
        zoom_row = QWidget()
        zoom_layout = QHBoxLayout(zoom_row)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(8)
        zoom_layout.addWidget(QLabel("プレビュー表示"))
        self.slider_preview_zoom = QSlider(Qt.Horizontal)
        self.slider_preview_zoom.setRange(_PREVIEW_ZOOM_MIN_PERCENT, _PREVIEW_ZOOM_MAX_PERCENT)
        self.slider_preview_zoom.setPageStep(10)
        self.slider_preview_zoom.valueChanged.connect(self._on_preview_zoom_changed)
        self.lbl_preview_zoom_value = QLabel()
        self.lbl_preview_zoom_value.setFixedWidth(52)
        self.btn_preview_zoom_reset = QPushButton("100%")
        self.btn_preview_zoom_reset.clicked.connect(self._reset_preview_zoom)
        self.btn_preview_zoom_reset.setToolTip("プレビュー表示倍率だけを 100% に戻します")
        zoom_layout.addWidget(self.slider_preview_zoom, 1)
        zoom_layout.addWidget(self.lbl_preview_zoom_value)
        zoom_layout.addWidget(self.btn_preview_zoom_reset)
        return zoom_row

    def _build_background_row(self) -> QWidget:
        """背景トーン切替行を構築する。"""
        background_row = QWidget()
        background_layout = QHBoxLayout(background_row)
        background_layout.setContentsMargins(0, 0, 0, 0)
        background_layout.setSpacing(6)
        background_layout.addStretch(1)
        background_label = QLabel("透明背景")
        background_label.setProperty("chromaRole", "detailText")
        self.btn_background_light = QPushButton("白")
        self.btn_background_dark = QPushButton("黒")
        for button in (self.btn_background_light, self.btn_background_dark):
            button.setCheckable(True)
            button.setProperty("chromaRole", "canvasPreviewToggle")
        self.background_group = QButtonGroup(self)
        self.background_group.setExclusive(True)
        self.background_group.addButton(self.btn_background_light)
        self.background_group.addButton(self.btn_background_dark)
        self.btn_background_light.toggled.connect(self._on_background_toggled)
        self.btn_background_dark.toggled.connect(self._on_background_toggled)
        background_layout.addWidget(background_label)
        background_layout.addWidget(self.btn_background_light)
        background_layout.addWidget(self.btn_background_dark)
        background_layout.addStretch(1)
        return background_row

    def _build_right_column(self) -> QWidget:
        """右カラムを構築する。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(320)

        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_display_action_box())
        layout.addWidget(self._build_adjust_box_with_reset_buttons())
        layout.addWidget(self._build_rotation_box())
        layout.addWidget(self._build_info_box())
        layout.addWidget(self._build_export_box())
        layout.addStretch(1)
        return scroll

    def _build_display_action_box(self) -> QGroupBox:
        """表示操作グループを構築する。"""
        quick_box = QGroupBox("表示操作")
        quick_layout = QVBoxLayout(quick_box)
        quick_layout.setContentsMargins(12, 12, 12, 12)
        quick_layout.setSpacing(6)
        self.btn_fit = QPushButton("全体を収める")
        self.btn_fill = QPushButton("埋める")
        self.btn_center = QPushButton("中央に戻す")
        for button in (self.btn_fit, self.btn_fill, self.btn_center):
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_fit.clicked.connect(lambda: self._apply_fit_mode(CANVAS_FIT_CONTAIN))
        self.btn_fill.clicked.connect(lambda: self._apply_fit_mode(CANVAS_FIT_COVER))
        self.btn_center.clicked.connect(self._center_image)
        self.btn_fit.setToolTip("画像全体がキャンバス内に収まる倍率にします")
        self.btn_fill.setToolTip("キャンバス全体を画像で埋める倍率にします")
        self.btn_center.setToolTip("X位置とY位置だけを初期位置に戻します")
        quick_layout.addWidget(self.btn_fit)
        quick_layout.addWidget(self.btn_fill)
        quick_layout.addWidget(self.btn_center)
        return quick_box

    def _build_adjust_box_with_reset_buttons(self) -> QGroupBox:
        """位置と拡大率の個別リセット付き調整グループを構築する。"""
        adjust_box = QGroupBox("位置と拡大率")
        adjust_form = QFormLayout(adjust_box)
        self.spin_offset_x = self._build_double_spin(
            -20000.0,
            20000.0,
            step=10.0,
            decimals=1,
            suffix=" px",
        )
        self.spin_offset_y = self._build_double_spin(
            -20000.0,
            20000.0,
            step=10.0,
            decimals=1,
            suffix=" px",
        )
        self.spin_scale = self._build_double_spin(
            1.0,
            1600.0,
            step=1.0,
            decimals=1,
            suffix=" %",
        )
        self.btn_reset_offset_x = self._build_reset_button(
            self._reset_offset_x,
            tooltip="X位置を初期値に戻す",
        )
        self.btn_reset_offset_y = self._build_reset_button(
            self._reset_offset_y,
            tooltip="Y位置を初期値に戻す",
        )
        self.btn_reset_scale = self._build_reset_button(
            self._reset_scale,
            tooltip="拡大率を初期値に戻す",
        )
        self.spin_offset_x.valueChanged.connect(self._on_manual_transform_changed)
        self.spin_offset_y.valueChanged.connect(self._on_manual_transform_changed)
        self.spin_scale.valueChanged.connect(self._on_manual_transform_changed)
        adjust_form.addRow(
            "X位置", self._build_adjust_spin_row(self.spin_offset_x, self.btn_reset_offset_x)
        )
        adjust_form.addRow(
            "Y位置", self._build_adjust_spin_row(self.spin_offset_y, self.btn_reset_offset_y)
        )
        adjust_form.addRow(
            "拡大率", self._build_adjust_spin_row(self.spin_scale, self.btn_reset_scale)
        )
        return adjust_box

    def _build_rotation_box(self) -> QGroupBox:
        """回転編集グループを構築する。"""
        rotation_box = QGroupBox("回転")
        rotation_layout = QVBoxLayout(rotation_box)
        self.slider_rotation = QSlider(Qt.Horizontal)
        self.slider_rotation.setRange(-180, 180)
        self.slider_rotation.valueChanged.connect(self._on_rotation_slider_changed)
        self.spin_rotation = self._build_double_spin(
            -180.0,
            180.0,
            step=0.5,
            decimals=1,
            suffix=" °",
        )
        self.spin_rotation.valueChanged.connect(self._on_rotation_spin_changed)
        rotation_buttons = QHBoxLayout()
        self.btn_rotate_left = QPushButton("90°左")
        self.btn_rotate_zero = QPushButton("0°")
        self.btn_rotate_right = QPushButton("90°右")
        self.btn_rotate_left.clicked.connect(lambda: self._rotate_by(-90.0))
        self.btn_rotate_zero.clicked.connect(self._reset_rotation)
        self.btn_rotate_right.clicked.connect(lambda: self._rotate_by(90.0))
        rotation_buttons.addWidget(self.btn_rotate_left)
        rotation_buttons.addWidget(self.btn_rotate_zero)
        rotation_buttons.addWidget(self.btn_rotate_right)
        rotation_layout.addWidget(self.slider_rotation)
        rotation_layout.addWidget(self.spin_rotation)
        rotation_layout.addLayout(rotation_buttons)
        return rotation_box

    def _build_info_box(self) -> QGroupBox:
        """情報表示グループを構築する。"""
        info_box = QGroupBox("情報")
        info_grid = QGridLayout(info_box)
        info_grid.setContentsMargins(12, 12, 12, 12)
        info_grid.setHorizontalSpacing(12)
        info_grid.setVerticalSpacing(6)
        info_grid.setColumnStretch(1, 1)

        self.lbl_info_source_size = self._build_info_value_label()
        self.lbl_info_canvas_size = self._build_info_value_label(emphasis=True)
        self.lbl_info_margin = self._build_info_value_label()
        self.lbl_info_crop = self._build_info_value_label()

        self._add_info_row(info_grid, 0, "元画像サイズ", self.lbl_info_source_size)
        self._add_info_row(info_grid, 1, "キャンバスサイズ", self.lbl_info_canvas_size)
        self._add_info_row(info_grid, 2, "余白量", self.lbl_info_margin)
        self._add_info_row(info_grid, 3, "切れ量", self.lbl_info_crop)
        return info_box

    def _build_export_box(self) -> QGroupBox:
        """保存グループを構築する。"""
        export_box = QGroupBox("保存")
        export_layout = QVBoxLayout(export_box)
        self.btn_export_preview = QPushButton("キャンバス画像を保存")
        self.btn_export_preview.clicked.connect(self._export_preview_image)
        export_layout.addWidget(self.btn_export_preview)
        return export_box

    def _build_info_value_label(self, *, emphasis: bool = False) -> QLabel:
        """情報欄の値ラベルを構築する。"""
        label = QLabel()
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        label.setProperty("chromaRole", "detailText")
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        label.setMinimumWidth(0)
        if emphasis:
            font = label.font()
            font.setBold(True)
            label.setFont(font)
        return label

    def _add_info_row(self, layout: QGridLayout, row: int, title: str, value_label: QLabel) -> None:
        """情報欄へ見出し+値の行を追加する。"""
        title_label = QLabel(str(title))
        title_label.setProperty("chromaRole", "infoLabel")
        title_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        row_index = int(row)
        try:
            layout.addWidget(title_label, row_index, 0, 1, 1, Qt.AlignTop | Qt.AlignLeft)
            layout.addWidget(value_label, row_index, 1, 1, 1, Qt.AlignTop | Qt.AlignLeft)
        except Exception as exc:
            raise RuntimeError(f"情報欄 '{title}' の行追加に失敗しました") from exc

    def _set_info_label_text(self, label: QLabel, text: str) -> None:
        """情報ラベルへ値と補助 tooltip を設定する。"""
        label.setText(str(text))
        label.setToolTip(str(text))
        label.updateGeometry()

    def _build_double_spin(
        self,
        minimum: float,
        maximum: float,
        *,
        step: float,
        decimals: int,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        """入力用 `QDoubleSpinBox` を構築する。"""
        spin = QDoubleSpinBox()
        spin.setRange(float(minimum), float(maximum))
        spin.setSingleStep(float(step))
        spin.setDecimals(int(decimals))
        spin.setSuffix(str(suffix))
        configure_numeric_input(spin, min_width=84, min_height=30)
        return spin

    def _build_adjust_spin_row(self, spin: QDoubleSpinBox, reset_button: QToolButton) -> QWidget:
        """数値入力と個別リセットボタンの行を構築する。"""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(spin, 1)
        layout.addWidget(reset_button, 0)
        return row

    def _build_reset_button(self, callback, *, tooltip: str) -> QToolButton:
        """個別値を初期値へ戻すアイコンボタンを構築する。"""
        button = QToolButton()
        button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        button.setAutoRaise(False)
        button.setText("")
        button.setToolTip(str(tooltip))
        button.setAccessibleName(str(tooltip))
        button.setIconSize(_RESET_ICON_SIZE)
        button.setFixedSize(_RESET_BUTTON_SIZE)
        button.setIcon(_reset_icon_from_palette(button))
        button.clicked.connect(callback)
        return button

    def _apply_initial_state(self) -> None:
        """初期選択と最初のフィット状態を適用する。"""
        self._log_debug("canvas_preview_apply_initial_state_begin")
        self._run_logged_step(
            "canvas_preview_apply_initial_state_step",
            "set_source_image",
            lambda: self.preview_widget.set_source_image(self._source_image),
        )
        self._run_logged_step(
            "canvas_preview_apply_initial_state_step",
            "apply_theme",
            lambda: self.set_theme(get_ui_theme(self._ui_theme_name)),
        )
        self._run_logged_step(
            "canvas_preview_apply_initial_state_step",
            "refresh_ratio_preset_list",
            self._refresh_ratio_preset_list,
        )
        self._run_logged_step(
            "canvas_preview_apply_initial_state_step",
            "set_orientation_controls",
            self._apply_initial_orientation_controls,
        )
        self._run_logged_step(
            "canvas_preview_apply_initial_state_step",
            "set_preview_zoom_control",
            self._apply_initial_preview_zoom_control,
        )
        self._run_logged_step(
            "canvas_preview_apply_initial_state_step",
            "set_background_controls",
            self._apply_initial_background_controls,
        )
        self._run_logged_step(
            "canvas_preview_apply_initial_state_step",
            "apply_fit_mode",
            lambda: self._apply_fit_mode(CANVAS_FIT_CONTAIN),
            include_canvas=True,
        )
        self._log_debug("canvas_preview_apply_initial_state_ok", include_canvas=True)

    def _apply_initial_orientation_controls(self) -> None:
        """初回表示時の向きラジオだけを同期する。"""
        self._syncing_controls = True
        try:
            with signal_blocked(
                self.radio_landscape,
                self.radio_portrait,
            ):
                self.radio_landscape.setChecked(self._orientation == CANVAS_ORIENTATION_LANDSCAPE)
                self.radio_portrait.setChecked(self._orientation == CANVAS_ORIENTATION_PORTRAIT)
        finally:
            self._syncing_controls = False

    def _apply_initial_preview_zoom_control(self) -> None:
        """初回表示時のズーム UI だけを既定値へ合わせる。"""
        self._syncing_controls = True
        try:
            with signal_blocked(self.slider_preview_zoom):
                self.slider_preview_zoom.setValue(100)
        finally:
            self._syncing_controls = False

    def _apply_initial_background_controls(self) -> None:
        """初回表示時の背景切替 UI を既定値へ合わせる。"""
        self._syncing_controls = True
        try:
            with signal_blocked(
                self.btn_background_light,
                self.btn_background_dark,
            ):
                self.btn_background_light.setChecked(
                    self._background_tone == CANVAS_PREVIEW_BACKGROUND_LIGHT
                )
                self.btn_background_dark.setChecked(
                    self._background_tone == CANVAS_PREVIEW_BACKGROUND_DARK
                )
        finally:
            self._syncing_controls = False
        self.preview_widget.set_background_tone(self._background_tone)

    def _builtin_presets(self) -> list[CanvasRatioPreset]:
        """表示中の標準プリセット一覧を返す。"""
        return [preset for preset in self._ratio_presets if preset.is_builtin]

    def _saved_user_presets(self) -> list[CanvasRatioPreset]:
        """保存済みユーザープリセット一覧を返す。"""
        return [preset for preset in self._ratio_presets if not preset.is_builtin]

    def _user_presets(self) -> list[CanvasRatioPreset]:
        """表示中のユーザープリセット一覧を返す。"""
        presets = list(self._saved_user_presets())
        if self._draft_preset is not None:
            presets.append(self._draft_preset)
        return presets

    def _visible_presets(self) -> list[CanvasRatioPreset]:
        """現在 UI に表示する全プリセットを返す。"""
        return [*self._builtin_presets(), *self._user_presets()]

    def _find_visible_preset(self, preset_id: str) -> CanvasRatioPreset:
        """表示中プリセットから ID に対応する項目を返す。"""
        visible = self._visible_presets()
        if not visible:
            self._ratio_presets = list(default_canvas_ratio_presets())
            visible = self._visible_presets()
        current_id = str(preset_id or "").strip()
        return next(
            (preset for preset in visible if preset.preset_id == current_id),
            visible[0],
        )

    def _current_preset(self) -> CanvasRatioPreset:
        """現在選択中のプリセットを返す。"""
        return self._find_visible_preset(self._preset_id)

    def _current_ratio(self) -> tuple[float, float]:
        """UI 状態に対応する現在の比率を返す。"""
        return oriented_ratio(self._current_preset(), self._orientation)

    def _current_canvas_pixels(self) -> tuple[int, int]:
        """現在比率から算出したキャンバス px 値を返す。"""
        ratio_w, ratio_h = self._current_ratio()
        return canvas_pixels_from_image_long_edge(
            self._source_image.width(),
            self._source_image.height(),
            ratio_w,
            ratio_h,
        )

    def _fallback_user_preset_name(self) -> str:
        """新規ユーザープリセット向けの既定名を返す。"""
        existing = {str(preset.name).strip() for preset in self._visible_presets()}
        index = 1
        while True:
            candidate = f"{_USER_PRESET_NAME_PREFIX}{index}"
            if candidate not in existing:
                return candidate
            index += 1

    def _normalized_editor_name(self, fallback: str) -> str:
        """入力欄から表示名を取り出して空文字を補う。"""
        text = str(self.edit_preset_name.text() or "").strip()
        return text or str(fallback or "").strip() or self._fallback_user_preset_name()

    def _editor_ratio_values(self) -> tuple[float, float]:
        """編集欄の比率値を保存向け精度へ丸めて返す。"""
        ratio_w = round(float(self.spin_preset_ratio_w.value()), _PRESET_RATIO_DECIMALS)
        ratio_h = round(float(self.spin_preset_ratio_h.value()), _PRESET_RATIO_DECIMALS)
        return ratio_w, ratio_h

    def _save_ratio_presets(self) -> None:
        """現在のプリセット一覧を設定へ保存する。"""
        cfg = load_config()
        cfg[APP_C.CFG_CANVAS_RATIO_PRESETS] = canvas_ratio_presets_to_payload(self._ratio_presets)
        save_config(cfg)

    def _save_background_tone(self) -> None:
        """透明背景トーンの現在値を設定へ保存する。"""
        cfg = load_config()
        cfg[APP_C.CFG_CANVAS_PREVIEW_BACKGROUND_TONE] = str(self._background_tone)
        save_config(cfg)

    def _preset_list_text(self, preset: CanvasRatioPreset) -> str:
        """一覧表示用の表示名を返す。"""
        return str(preset.name or "").strip() or str(preset.default_name or "").strip()

    def _refresh_ratio_preset_list(self) -> None:
        """比率プリセット一覧表示を更新する。"""
        self._log_debug("canvas_preview_refresh_ratio_preset_list_begin")
        try:
            if not self._ratio_presets:
                self._ratio_presets = list(default_canvas_ratio_presets())
            current = self._current_preset()
            self._preset_id = current.preset_id
            self._syncing_controls = True
            try:
                with signal_blocked(self.list_ratio_presets):
                    self.list_ratio_presets.clear()
                    for preset in self._visible_presets():
                        item = QListWidgetItem(self._preset_list_text(preset))
                        item.setData(Qt.UserRole, preset.preset_id)
                        self.list_ratio_presets.addItem(item)
            finally:
                self._syncing_controls = False
            self._sync_controls()
        except Exception as exc:
            self._log_exception("canvas_preview_refresh_ratio_preset_list_fail", exc)
            raise
        self._log_debug(
            "canvas_preview_refresh_ratio_preset_list_ok",
            current_row=int(self.list_ratio_presets.currentRow()),
        )

    def _sync_preset_editor(self) -> None:
        """左カラムのプリセット管理欄を現在選択へ合わせる。"""
        self._log_debug("canvas_preview_sync_preset_editor_begin")
        try:
            preset = self._current_preset()
            is_builtin = bool(preset.is_builtin)
            self._syncing_controls = True
            try:
                with signal_blocked(
                    self.edit_preset_name,
                    self.spin_preset_ratio_w,
                    self.spin_preset_ratio_h,
                ):
                    self.edit_preset_name.setText(preset.name)
                    self.spin_preset_ratio_w.setValue(float(preset.ratio_w))
                    self.spin_preset_ratio_h.setValue(float(preset.ratio_h))
            finally:
                self._syncing_controls = False
            self.edit_preset_name.setEnabled(True)
            self.spin_preset_ratio_w.setEnabled(not is_builtin)
            self.spin_preset_ratio_h.setEnabled(not is_builtin)
            self.btn_save_preset.setEnabled(True)
            self.btn_save_preset.setToolTip("")
            self.btn_delete_preset.setEnabled(not is_builtin)
            self.btn_delete_preset.setToolTip(_BUILTIN_PRESET_DELETE_TOOLTIP if is_builtin else "")
        except Exception as exc:
            self._log_exception("canvas_preview_sync_preset_editor_fail", exc)
            raise
        self._log_debug(
            "canvas_preview_sync_preset_editor_ok",
            preset_name=str(preset.name),
            preset_builtin=bool(is_builtin),
        )

    def _reset_buttons(self) -> tuple[QToolButton, ...]:
        """個別リセットボタンをまとめて返す。"""
        buttons = (
            getattr(self, "btn_reset_offset_x", None),
            getattr(self, "btn_reset_offset_y", None),
            getattr(self, "btn_reset_scale", None),
        )
        return tuple(button for button in buttons if isinstance(button, QToolButton))

    def _refresh_reset_button_icons(self) -> None:
        """テーマや DPI に合わせて個別リセットアイコンを描き直す。"""
        for button in self._reset_buttons():
            button.setIcon(_reset_icon_from_palette(button))
            button.setIconSize(_RESET_ICON_SIZE)

    def set_theme(self, theme) -> None:
        """テーマ変更をダイアログへ即時反映する。"""
        self._ui_theme_name = getattr(theme, "name", self._ui_theme_name)
        self.preview_widget.set_theme(theme)
        self._refresh_theme_state()

    def _refresh_theme_state(self) -> None:
        """テーマ変更後のスタイルと再描画をまとめて更新する。"""
        if self._theme_refreshing:
            self._log_debug("canvas_preview_refresh_theme_state_skip", reason="already_refreshing")
            return
        if not self._ui_ready:
            self._log_debug("canvas_preview_refresh_theme_state_skip", reason="ui_not_ready")
            self.update()
            return
        self._log_debug("canvas_preview_refresh_theme_state_begin")
        self._theme_refreshing = True
        try:
            refresh_widget_style(self)
            widgets = (
                self.orientation_row,
                self.radio_landscape,
                self.radio_portrait,
                self.list_ratio_presets,
                self.list_ratio_presets.viewport(),
                self.btn_background_light,
                self.btn_background_dark,
                *self._reset_buttons(),
                self.preview_widget,
            )
            for widget in widgets:
                refresh_widget_style(widget)
            self._refresh_reset_button_icons()
            self.list_ratio_presets.viewport().update()
            self.preview_widget.update()
            self.update()
        except Exception as exc:
            self._log_exception("canvas_preview_refresh_theme_state_fail", exc)
            raise
        finally:
            self._theme_refreshing = False
        self._log_debug("canvas_preview_refresh_theme_state_ok")

    def _set_transform(
        self,
        *,
        offset_x: float | None = None,
        offset_y: float | None = None,
        scale: float | None = None,
        rotation_deg: float | None = None,
        preserve_fit_mode: bool = False,
    ) -> None:
        """画像変形状態を更新して UI へ反映する。"""
        self._transform = CanvasPreviewTransform(
            offset_x=float(self._transform.offset_x if offset_x is None else offset_x),
            offset_y=float(self._transform.offset_y if offset_y is None else offset_y),
            scale=float(self._transform.scale if scale is None else scale),
            rotation_deg=float(
                self._transform.rotation_deg if rotation_deg is None else rotation_deg
            ),
        )
        if not preserve_fit_mode:
            self._fit_mode = CANVAS_FIT_CUSTOM
        elif self._fit_mode == CANVAS_FIT_COVER:
            self._ensure_cover_scale()
        self._sync_view_and_labels()

    def _fit_mode_scale(self, fit_mode: str) -> float:
        """指定 fit mode に対応する scale を返す。"""
        canvas_width, canvas_height = self._current_canvas_pixels()
        return fit_scale_for_mode(
            fit_mode,
            image_width=self._source_image.width(),
            image_height=self._source_image.height(),
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            rotation_deg=float(self._transform.rotation_deg),
        )

    def _reset_transform_for_fit_mode(self, fit_mode: str) -> None:
        """fit mode 基準の transform へ戻す。"""
        self._fit_mode = str(fit_mode or CANVAS_FIT_CONTAIN)
        self._transform = CanvasPreviewTransform(
            offset_x=0.0,
            offset_y=0.0,
            scale=float(self._fit_mode_scale(self._fit_mode)),
            rotation_deg=float(self._transform.rotation_deg),
        )

    def _apply_fit_mode(self, fit_mode: str) -> None:
        """指定状態で scale と位置を基準状態へ戻す。"""
        requested_fit_mode = str(fit_mode or CANVAS_FIT_CONTAIN)
        self._log_debug(
            "canvas_preview_apply_fit_mode_begin",
            fit_mode=requested_fit_mode,
            include_canvas=True,
        )
        try:
            self._reset_transform_for_fit_mode(requested_fit_mode)
            self._sync_view_and_labels()
        except Exception as exc:
            self._log_exception(
                "canvas_preview_apply_fit_mode_fail",
                exc,
                fit_mode=requested_fit_mode,
                include_canvas=True,
            )
            raise
        self._log_debug(
            "canvas_preview_apply_fit_mode_ok",
            fit_mode=requested_fit_mode,
            applied_scale=float(self._transform.scale),
            include_canvas=True,
        )

    def _set_preview_zoom(self, zoom: float) -> None:
        """プレビュー全体の表示倍率を更新する。"""
        clamped = max(
            _PREVIEW_ZOOM_MIN_PERCENT / 100.0,
            min(_PREVIEW_ZOOM_MAX_PERCENT / 100.0, float(zoom)),
        )
        self._preview_zoom = clamped
        self._sync_view_and_labels()

    def _center_image(self) -> None:
        """位置だけを中央へ戻す。"""
        self._set_transform(offset_x=0.0, offset_y=0.0, preserve_fit_mode=True)

    def _reset_offset_x(self) -> None:
        """X位置だけを初期値へ戻す。"""
        self._set_transform(offset_x=0.0, preserve_fit_mode=True)

    def _reset_offset_y(self) -> None:
        """Y位置だけを初期値へ戻す。"""
        self._set_transform(offset_y=0.0, preserve_fit_mode=True)

    def _reset_scale(self) -> None:
        """拡大率だけを初期値へ戻す。"""
        self._set_transform(scale=1.0)

    def _rotate_by(self, delta_deg: float) -> None:
        """相対回転を適用する。"""
        rotation = float(self._transform.rotation_deg) + float(delta_deg)
        while rotation > _ROTATION_HALF_TURN_DEG:
            rotation -= _ROTATION_FULL_TURN_DEG
        while rotation < -_ROTATION_HALF_TURN_DEG:
            rotation += _ROTATION_FULL_TURN_DEG
        self._set_transform(rotation_deg=rotation, preserve_fit_mode=True)

    def _reset_rotation(self) -> None:
        """回転を 0° に戻す。"""
        self._set_transform(rotation_deg=0.0, preserve_fit_mode=True)

    def _reset_preview_zoom(self) -> None:
        """プレビュー全体の表示倍率を 100% に戻す。"""
        self._set_preview_zoom(1.0)

    def _preset_index_in(self, presets: list[CanvasRatioPreset]) -> int:
        """現在選択中 ID の index を一覧内から返す。"""
        for index, preset in enumerate(presets):
            if preset.preset_id == self._preset_id:
                return index
        return -1

    def _sync_view_and_labels(self) -> None:
        """preview widget と各表示ラベルをまとめて更新する。"""
        self._log_debug("canvas_preview_sync_view_and_labels_begin", include_canvas=True)
        try:
            self._ui_theme_name = getattr(self._main_window, "_ui_theme_name", self._ui_theme_name)
            canvas_width, canvas_height = self._current_canvas_pixels()
            self._run_logged_step(
                "canvas_preview_sync_view_and_labels_step",
                "set_canvas_pixels",
                lambda: self.preview_widget.set_canvas_pixels(canvas_width, canvas_height),
                include_canvas=True,
                canvas_width=int(canvas_width),
                canvas_height=int(canvas_height),
            )
            self._run_logged_step(
                "canvas_preview_sync_view_and_labels_step",
                "set_transform_state",
                lambda: self.preview_widget.set_transform_state(self._transform),
                include_canvas=True,
            )
            self._run_logged_step(
                "canvas_preview_sync_view_and_labels_step",
                "set_view_zoom",
                lambda: self.preview_widget.set_view_zoom(self._preview_zoom),
                include_canvas=True,
            )
            self._run_logged_step(
                "canvas_preview_sync_view_and_labels_step",
                "sync_controls",
                self._sync_controls,
                include_canvas=True,
            )
            self._run_logged_step(
                "canvas_preview_sync_view_and_labels_step",
                "sync_labels",
                self._sync_labels,
                include_canvas=True,
            )
        except Exception as exc:
            self._log_exception(
                "canvas_preview_sync_view_and_labels_fail", exc, include_canvas=True
            )
            raise
        self._log_debug("canvas_preview_sync_view_and_labels_ok", include_canvas=True)

    def _sync_control_values(self) -> None:
        """block 済み前提で入力欄とトグルを現在状態へ揃える。"""
        self.list_ratio_presets.setCurrentRow(self._preset_index_in(self._visible_presets()))
        self.spin_offset_x.setValue(float(self._transform.offset_x))
        self.spin_offset_y.setValue(float(self._transform.offset_y))
        self.spin_scale.setValue(float(self._transform.scale) * 100.0)
        self.spin_rotation.setValue(float(self._transform.rotation_deg))
        self.slider_rotation.setValue(int(round(float(self._transform.rotation_deg))))
        self.slider_preview_zoom.setValue(int(round(float(self._preview_zoom) * 100.0)))
        self.radio_landscape.setChecked(self._orientation == CANVAS_ORIENTATION_LANDSCAPE)
        self.radio_portrait.setChecked(self._orientation == CANVAS_ORIENTATION_PORTRAIT)
        self.btn_background_light.setChecked(
            self._background_tone == CANVAS_PREVIEW_BACKGROUND_LIGHT
        )
        self.btn_background_dark.setChecked(self._background_tone == CANVAS_PREVIEW_BACKGROUND_DARK)

    def _sync_preview_zoom_label(self) -> None:
        """プレビュー倍率ラベルだけを同期する。"""
        self.lbl_preview_zoom_value.setText(f"{int(round(float(self._preview_zoom) * 100.0))}%")

    def _sync_controls(self) -> None:
        """入力欄と一覧選択を現在状態へ同期する。"""
        self._log_debug("canvas_preview_sync_controls_begin", include_canvas=True)
        try:
            self._syncing_controls = True
            try:
                with signal_blocked(
                    self.list_ratio_presets,
                    self.spin_offset_x,
                    self.spin_offset_y,
                    self.spin_scale,
                    self.spin_rotation,
                    self.slider_rotation,
                    self.slider_preview_zoom,
                    self.radio_landscape,
                    self.radio_portrait,
                    self.btn_background_light,
                    self.btn_background_dark,
                ):
                    self._sync_control_values()
                self._sync_preview_zoom_label()
            finally:
                self._syncing_controls = False
            self._sync_preset_editor()
        except Exception as exc:
            self._log_exception("canvas_preview_sync_controls_fail", exc, include_canvas=True)
            raise
        self._log_debug(
            "canvas_preview_sync_controls_ok",
            current_row=int(self.list_ratio_presets.currentRow()),
            zoom_label=str(self.lbl_preview_zoom_value.text()),
            include_canvas=True,
        )

    def _current_preview_info(self):
        """情報欄更新に必要な現在キャンバス情報を返す。"""
        canvas_width, canvas_height = self._current_canvas_pixels()
        extents = preview_extents(
            self._source_image.width(),
            self._source_image.height(),
            canvas_width,
            canvas_height,
            self._transform,
        )
        return canvas_width, canvas_height, extents

    def _apply_preview_info_labels(self, canvas_width: int, canvas_height: int, extents) -> None:
        """情報欄ラベルへ現在値を反映する。"""
        self._set_info_label_text(
            self.lbl_info_source_size,
            f"{self._source_image.width()} x {self._source_image.height()} px",
        )
        self._set_info_label_text(
            self.lbl_info_canvas_size,
            f"{canvas_width} x {canvas_height} px",
        )
        self._set_info_label_text(
            self.lbl_info_margin,
            _format_edge_values(
                extents.margin_left,
                extents.margin_top,
                extents.margin_right,
                extents.margin_bottom,
            ),
        )
        self._set_info_label_text(
            self.lbl_info_crop,
            _format_edge_values(
                extents.crop_left,
                extents.crop_top,
                extents.crop_right,
                extents.crop_bottom,
            ),
        )

    def _sync_labels(self) -> None:
        """数値情報ラベルを更新する。"""
        self._log_debug("canvas_preview_sync_labels_begin", include_canvas=True)
        try:
            canvas_width, canvas_height, extents = self._current_preview_info()
            self._apply_preview_info_labels(canvas_width, canvas_height, extents)
        except Exception as exc:
            self._log_exception("canvas_preview_sync_labels_fail", exc, include_canvas=True)
            raise
        self._log_debug(
            "canvas_preview_sync_labels_ok",
            info_source_size=str(self.lbl_info_source_size.text()),
            info_canvas_size=str(self.lbl_info_canvas_size.text()),
            info_margin=str(self.lbl_info_margin.text()),
            info_crop=str(self.lbl_info_crop.text()),
            include_canvas=True,
        )

    def _ensure_cover_scale(self) -> None:
        """埋める状態では回転後もキャンバス内に空白を残さない。"""
        if self._fit_mode != CANVAS_FIT_COVER:
            return
        canvas_width, canvas_height = self._current_canvas_pixels()
        cover_scale = fit_scale_for_mode(
            CANVAS_FIT_COVER,
            image_width=self._source_image.width(),
            image_height=self._source_image.height(),
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            rotation_deg=float(self._transform.rotation_deg),
        )
        if float(self._transform.scale) >= float(cover_scale):
            return
        self._transform = replace(self._transform, scale=float(cover_scale))

    def _start_new_user_preset(self) -> None:
        """その場で編集できる未保存ユーザープリセット draft を作る。"""
        if self._draft_preset is None:
            base = self._current_preset()
            name = self._fallback_user_preset_name()
            self._draft_preset = CanvasRatioPreset(
                name=name,
                ratio_w=float(base.ratio_w),
                ratio_h=float(base.ratio_h),
                preset_id=f"user_{uuid4().hex[:10]}",
                is_builtin=False,
                default_name=name,
            )
        self._preset_id = self._draft_preset.preset_id
        self._refresh_ratio_preset_list()
        self.edit_preset_name.setFocus(Qt.OtherFocusReason)
        self.edit_preset_name.selectAll()

    def _saved_user_preset_index(self, preset_id: str) -> int:
        """保存済みユーザープリセット内の index を返す。"""
        current_id = str(preset_id or "").strip()
        for index, preset in enumerate(self._saved_user_presets()):
            if preset.preset_id == current_id:
                return index
        return -1

    def _replace_saved_user_preset(self, preset_id: str, updated: CanvasRatioPreset) -> None:
        """保存済みユーザープリセットを更新する。"""
        target_id = str(preset_id or "").strip()
        for index, preset in enumerate(self._ratio_presets):
            if not preset.is_builtin and preset.preset_id == target_id:
                self._ratio_presets[index] = updated
                return
        raise ValueError(f"user preset not found: {target_id}")

    def _save_selected_preset(self) -> None:
        """現在選択中のプリセットを保存する。"""
        current = self._current_preset()
        updated_name = self._normalized_editor_name(current.default_name or current.name)
        if current.is_builtin:
            updated = replace(current, name=updated_name)
            ratio_changed = False
        else:
            ratio_w, ratio_h = self._editor_ratio_values()
            updated = replace(
                current,
                name=updated_name,
                ratio_w=ratio_w,
                ratio_h=ratio_h,
                default_name=updated_name,
            )
            ratio_changed = (
                abs(float(updated.ratio_w) - float(current.ratio_w)) > _RATIO_COMPARE_EPSILON
                or abs(float(updated.ratio_h) - float(current.ratio_h)) > _RATIO_COMPARE_EPSILON
            )
        if self._draft_preset is not None and current.preset_id == self._draft_preset.preset_id:
            self._ratio_presets.append(updated)
            self._draft_preset = None
        elif current.is_builtin:
            self._ratio_presets = [
                updated if preset.preset_id == current.preset_id else preset
                for preset in self._ratio_presets
            ]
        else:
            self._replace_saved_user_preset(current.preset_id, updated)
        self._preset_id = updated.preset_id
        self._save_ratio_presets()
        self._refresh_ratio_preset_list()
        if ratio_changed:
            self._apply_fit_mode(CANVAS_FIT_CONTAIN)
        else:
            self._sync_view_and_labels()

    def _delete_selected_preset(self) -> None:
        """現在選択中のユーザープリセットを削除する。"""
        current = self._current_preset()
        if current.is_builtin:
            return
        if self._draft_preset is not None and current.preset_id == self._draft_preset.preset_id:
            self._draft_preset = None
            user_presets = self._saved_user_presets()
            if user_presets:
                self._preset_id = user_presets[-1].preset_id
            else:
                self._preset_id = find_canvas_ratio_preset(
                    DEFAULT_CANVAS_RATIO_PRESET_ID,
                    self._ratio_presets,
                ).preset_id
            self._refresh_ratio_preset_list()
            self._sync_view_and_labels()
            return
        answer = QMessageBox.question(
            self,
            "プリセット削除",
            f"「{current.name}」を削除しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        index = self._saved_user_preset_index(current.preset_id)
        if index < 0:
            return
        user_preset_ids = [preset.preset_id for preset in self._saved_user_presets()]
        del user_preset_ids[index]
        self._ratio_presets = [
            preset
            for preset in self._ratio_presets
            if preset.is_builtin or preset.preset_id != current.preset_id
        ]
        if user_preset_ids:
            next_index = min(index, len(user_preset_ids) - 1)
            self._preset_id = user_preset_ids[next_index]
        else:
            self._preset_id = find_canvas_ratio_preset(
                DEFAULT_CANVAS_RATIO_PRESET_ID,
                self._ratio_presets,
            ).preset_id
        self._save_ratio_presets()
        self._refresh_ratio_preset_list()
        self._apply_fit_mode(CANVAS_FIT_CONTAIN)

    def _select_preset_from_list(self, index: int) -> None:
        """選択された一覧項目から現在プリセットを更新する。"""
        self._log_debug(
            "canvas_preview_on_ratio_preset_row_changed",
            row_index=int(index),
            syncing_controls=bool(self._syncing_controls),
        )
        if self._syncing_controls or index < 0:
            return
        item = self.list_ratio_presets.item(index)
        preset_id = str(item.data(Qt.UserRole) if item is not None else "").strip()
        if not preset_id:
            return
        self._preset_id = preset_id
        refit_mode = self._fit_mode if self._fit_mode != CANVAS_FIT_CUSTOM else CANVAS_FIT_CONTAIN
        self._apply_fit_mode(refit_mode)

    def _on_ratio_preset_row_changed(self, index: int) -> None:
        """比率プリセット変更を反映する。"""
        self._select_preset_from_list(index)

    def _on_background_toggled(self) -> None:
        """背景トーン切替を表示だけへ反映する。"""
        sender = self.sender()
        self._log_debug(
            "canvas_preview_on_background_toggled",
            sender_type=type(sender).__name__ if sender is not None else "",
            syncing_controls=bool(self._syncing_controls),
            light_checked=bool(self.btn_background_light.isChecked()),
            dark_checked=bool(self.btn_background_dark.isChecked()),
        )
        if self._syncing_controls:
            return
        if sender is self.btn_background_light and not self.btn_background_light.isChecked():
            return
        if sender is self.btn_background_dark and not self.btn_background_dark.isChecked():
            return
        self._background_tone = (
            CANVAS_PREVIEW_BACKGROUND_DARK
            if self.btn_background_dark.isChecked()
            else CANVAS_PREVIEW_BACKGROUND_LIGHT
        )
        self.preview_widget.set_background_tone(self._background_tone)
        self._save_background_tone()

    def _on_orientation_toggled(self) -> None:
        """向き切替を反映する。"""
        sender = self.sender()
        self._log_debug(
            "canvas_preview_on_orientation_toggled",
            sender_type=type(sender).__name__ if sender is not None else "",
            syncing_controls=bool(self._syncing_controls),
            landscape_checked=bool(self.radio_landscape.isChecked()),
            portrait_checked=bool(self.radio_portrait.isChecked()),
        )
        if self._syncing_controls:
            return
        if sender is self.radio_landscape and not self.radio_landscape.isChecked():
            return
        if sender is self.radio_portrait and not self.radio_portrait.isChecked():
            return
        self._orientation = (
            CANVAS_ORIENTATION_PORTRAIT
            if self.radio_portrait.isChecked()
            else CANVAS_ORIENTATION_LANDSCAPE
        )
        refit_mode = self._fit_mode if self._fit_mode != CANVAS_FIT_CUSTOM else CANVAS_FIT_CONTAIN
        self._apply_fit_mode(refit_mode)

    def _on_preview_zoom_changed(self, value: int) -> None:
        """プレビュー全体の表示倍率を UI から反映する。"""
        if self._syncing_controls:
            return
        self._set_preview_zoom(float(value) / 100.0)

    def _on_preview_view_zoom_changed(self, value: float) -> None:
        """widget 側ホイール操作からプレビュー全体ズームを反映する。"""
        if self._syncing_controls:
            return
        self._set_preview_zoom(float(value))

    def _on_rotation_slider_changed(self, value: int) -> None:
        """スライダー回転値を変形状態へ反映する。"""
        if self._syncing_controls:
            return
        self._set_transform(rotation_deg=float(value), preserve_fit_mode=True)

    def _on_rotation_spin_changed(self, value: float) -> None:
        """数値入力回転値を変形状態へ反映する。"""
        if self._syncing_controls:
            return
        self._set_transform(rotation_deg=float(value), preserve_fit_mode=True)

    def _on_manual_transform_changed(self) -> None:
        """右カラム入力から位置と拡大率を反映する。"""
        if self._syncing_controls:
            return
        self._set_transform(
            offset_x=float(self.spin_offset_x.value()),
            offset_y=float(self.spin_offset_y.value()),
            scale=max(0.01, float(self.spin_scale.value()) / 100.0),
        )

    def _on_preview_transform_changed(
        self,
        offset_x: float,
        offset_y: float,
        scale: float,
        rotation_deg: float,
    ) -> None:
        """中央プレビューでのドラッグや Ctrl+ホイール結果を UI へ反映する。"""
        self._fit_mode = CANVAS_FIT_CUSTOM
        self._transform = CanvasPreviewTransform(
            offset_x=float(offset_x),
            offset_y=float(offset_y),
            scale=float(scale),
            rotation_deg=float(rotation_deg),
        )
        self._sync_view_and_labels()

    def _suggest_output_path(self, suffix: str) -> str:
        """出力ダイアログ向けの既定ファイル名を返す。"""
        return f"canvas_preview{str(suffix or '')}"

    def _export_preview_image(self) -> None:
        """現在のシミュレーション結果を PNG 保存する。"""
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "キャンバス画像を保存",
            self._suggest_output_path(".png"),
            "PNG Files (*.png)",
        )
        if not path:
            return
        ok = self.preview_widget.preview_image().save(path, "PNG")
        if not ok:
            QMessageBox.warning(self, "保存", "キャンバス画像の保存に失敗しました。")
            return
        QMessageBox.information(self, "保存", f"キャンバス画像を保存しました。\n{path}")

    def changeEvent(self, event) -> None:
        """スタイル変更時にプレビューを再描画して見た目を揃える。"""
        super().changeEvent(event)
        if event.type() in _THEME_REFRESH_EVENTS:
            self._refresh_theme_state()
