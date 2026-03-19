"""画像変換キャッシュとリサイズの挙動を守るテスト。"""

import cv2
import numpy as np

from chroma_monitor.util.image_ops import (
    clear_cvt_color_cache,
    clear_resize_cache,
    cvt_color_cached,
    resize_by_long_edge,
)


def test_resize_by_long_edge_shrinks_long_side() -> None:
    # 長辺基準で縦横比を維持して縮小されることを確認する。
    src = np.zeros((120, 240, 3), dtype=np.uint8)
    out = resize_by_long_edge(src, 60)
    assert out.shape[:2] == (30, 60)


def test_resize_by_long_edge_cache_reuse_and_clear() -> None:
    # 同一入力はキャッシュ再利用、clear後は再生成されることを確認する。
    clear_resize_cache()
    src = np.zeros((200, 300, 3), dtype=np.uint8)
    out1 = resize_by_long_edge(src, 100)
    out2 = resize_by_long_edge(src, 100)
    assert out1 is out2

    clear_resize_cache()
    out3 = resize_by_long_edge(src, 100)
    assert out3 is not out1


def test_cvt_color_cached_reuse_and_clear() -> None:
    # 色変換キャッシュの再利用とclear挙動を確認する。
    clear_cvt_color_cache()
    src = np.zeros((8, 8, 3), dtype=np.uint8)
    out1 = cvt_color_cached(src, cv2.COLOR_BGR2HSV)
    out2 = cvt_color_cached(src, cv2.COLOR_BGR2HSV)
    assert out1 is out2

    clear_cvt_color_cache()
    out3 = cvt_color_cached(src, cv2.COLOR_BGR2HSV)
    assert out3 is not out1
