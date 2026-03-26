"""画像入力の共通 helper。"""

from collections.abc import Iterable
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QUrl
from PySide6.QtGui import QImage

from . import constants as C

_SUPPORTED_IMAGE_SUFFIXES = tuple(str(suffix).lower() for suffix in C.IMAGE_INPUT_SUFFIXES)
_QIMAGE_FORMAT_RGBA8888 = getattr(QImage, "Format_RGBA8888", None)


def _strip_wrapping_quotes(text: str) -> str:
    """前後の空白と単純な引用符を取り除く。"""
    candidate = str(text or "").strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in ('"', "'"):
        candidate = candidate[1:-1].strip()
    return candidate


def is_supported_image_path(path: str | Path) -> bool:
    """対応画像拡張子かを返す。"""
    candidate = _strip_wrapping_quotes(str(path))
    if not candidate:
        return False
    return Path(candidate).suffix.lower() in _SUPPORTED_IMAGE_SUFFIXES


def normalize_existing_image_path(path: str | Path) -> str | None:
    """存在する対応画像ファイルなら正規化したパス文字列を返す。"""
    candidate = _strip_wrapping_quotes(str(path))
    if not candidate:
        return None
    resolved = Path(candidate).expanduser()
    if not resolved.exists() or not resolved.is_file():
        return None
    if not is_supported_image_path(resolved):
        return None
    return str(resolved.resolve())


def _unique_existing_paths(paths: Iterable[str]) -> list[str]:
    """重複を除きつつ存在する対応画像パスのみ返す。"""
    normalized_paths: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = normalize_existing_image_path(path)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        normalized_paths.append(normalized)
    return normalized_paths


def supported_image_paths_from_urls(urls: Iterable[QUrl]) -> list[str]:
    """URL 群からローカル画像ファイルのパスを抽出する。"""
    return _unique_existing_paths(
        url.toLocalFile()
        for url in urls
        if url is not None and bool(url.isLocalFile())
    )


def supported_image_paths_from_text(text: str) -> list[str]:
    """テキスト中の各行から画像ファイルパス / file URL を抽出する。"""
    candidates: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = _strip_wrapping_quotes(raw_line)
        if not line:
            continue
        url = QUrl(line)
        if url.isValid() and bool(url.isLocalFile()):
            candidates.append(url.toLocalFile())
            continue
        candidates.append(line)
    return _unique_existing_paths(candidates)


def decode_image_buffer_to_bgr(buf: np.ndarray) -> np.ndarray | None:
    """エンコード済み画像バッファを BGR 3ch へ正規化する。"""
    img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if img is None or img.size == 0:
        return None
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.ndim != 3:
        return None
    channels = int(img.shape[2])
    if channels == 3:
        return img
    if channels == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    if channels == 1:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return None


def load_image_path_to_bgr(path: str | Path) -> np.ndarray | None:
    """画像ファイルパスを読み込み、BGR 3ch 配列へ変換する。"""
    normalized = normalize_existing_image_path(path)
    if normalized is None:
        return None
    buf = np.fromfile(normalized, dtype=np.uint8)
    if buf.size == 0:
        return None
    return decode_image_buffer_to_bgr(buf)


def qimage_to_bgr(image: QImage) -> np.ndarray | None:
    """`QImage` を BGR 3ch 配列へ変換する。"""
    if image is None or image.isNull():
        return None

    if _QIMAGE_FORMAT_RGBA8888 is not None:
        qimg = image.convertToFormat(_QIMAGE_FORMAT_RGBA8888)
        width = int(qimg.width())
        height = int(qimg.height())
        if width <= 0 or height <= 0:
            return None
        bytes_per_line = int(qimg.bytesPerLine())
        rgba = np.frombuffer(
            qimg.bits(),
            dtype=np.uint8,
            count=bytes_per_line * height,
        ).reshape((height, bytes_per_line))
        rgba = np.ascontiguousarray(rgba[:, : width * 4].reshape((height, width, 4)))
        return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)

    qimg = image.convertToFormat(QImage.Format_ARGB32)
    width = int(qimg.width())
    height = int(qimg.height())
    if width <= 0 or height <= 0:
        return None
    bytes_per_line = int(qimg.bytesPerLine())
    bgra = np.frombuffer(
        qimg.bits(),
        dtype=np.uint8,
        count=bytes_per_line * height,
    ).reshape((height, bytes_per_line))
    bgra = np.ascontiguousarray(bgra[:, : width * 4].reshape((height, width, 4)))
    return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)


__all__ = [
    "decode_image_buffer_to_bgr",
    "is_supported_image_path",
    "load_image_path_to_bgr",
    "normalize_existing_image_path",
    "qimage_to_bgr",
    "supported_image_paths_from_text",
    "supported_image_paths_from_urls",
]
