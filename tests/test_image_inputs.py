"""image_inputs の回帰テスト。"""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QImage

from chroma_monitor.util import image_inputs


def test_is_supported_image_path_rejects_psd_and_psb() -> None:
    assert image_inputs.is_supported_image_path("sample.png") is True
    assert image_inputs.is_supported_image_path("sample.psd") is False
    assert image_inputs.is_supported_image_path("sample.psb") is False


def test_supported_image_paths_from_urls_filters_supported_local_files(tmp_path) -> None:
    png_path = tmp_path / "sample.png"
    png_path.write_bytes(b"png")
    txt_path = tmp_path / "note.txt"
    txt_path.write_text("note", encoding="utf-8")

    paths = image_inputs.supported_image_paths_from_urls(
        [
            QUrl("https://example.com/sample.png"),
            QUrl.fromLocalFile(str(txt_path)),
            QUrl.fromLocalFile(str(png_path)),
        ]
    )

    assert paths == [str(png_path.resolve())]


def test_supported_image_paths_from_text_accepts_path_and_file_url(tmp_path) -> None:
    png_path = tmp_path / "sample.png"
    png_path.write_bytes(b"png")
    jpg_path = tmp_path / "second.jpg"
    jpg_path.write_bytes(b"jpg")

    text = f'"{png_path}"\n{QUrl.fromLocalFile(str(jpg_path)).toString()}\n/tmp/missing.bmp'

    assert image_inputs.supported_image_paths_from_text(text) == [
        str(png_path.resolve()),
        str(jpg_path.resolve()),
    ]


def test_load_image_path_to_bgr_decodes_common_image(tmp_path) -> None:
    bgr = np.array([[[12, 34, 56]]], dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", bgr)
    assert ok is True
    png_path = tmp_path / "sample.png"
    png_path.write_bytes(encoded.tobytes())

    loaded = image_inputs.load_image_path_to_bgr(png_path)

    assert loaded is not None
    assert loaded.shape == (1, 1, 3)
    assert loaded[0, 0].tolist() == [12, 34, 56]


def test_qimage_to_bgr_handles_alpha_channel() -> None:
    image_format = getattr(QImage, "Format_RGBA8888", QImage.Format_ARGB32)
    image = QImage(1, 1, image_format)
    image.setPixelColor(0, 0, QColor(10, 20, 30, 40))

    bgr = image_inputs.qimage_to_bgr(image)

    assert bgr is not None
    assert bgr.shape == (1, 1, 3)
    assert bgr[0, 0].tolist() == [30, 20, 10]
