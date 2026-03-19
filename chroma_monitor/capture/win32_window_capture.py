"""Win32 ウィンドウの低レベルキャプチャ補助。"""

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QRect

from .win32_windows import HAS_WIN32, ctypes_win_api, win32gui

_ctypes_win = ctypes_win_api
_WIN_BI_RGB = 0
_WIN_DIB_RGB_COLORS = 0
_WIN_PRINTWINDOW_FULL = 0x00000002


def get_window_rect(hwnd: int) -> Optional[QRect]:
    """対象ウィンドウ矩形を取得する。"""
    if not HAS_WIN32:
        return None
    try:
        left = top = right = bottom = None
        if win32gui:
            try:
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            except Exception:
                pass
        if (left is None or right is None or bottom is None) and _ctypes_win:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if not _ctypes_win["GetWindowRect"](hwnd, ctypes.byref(rect)):
                return None
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        if left is None or top is None or right is None or bottom is None:
            return None
        if right - left <= 0 or bottom - top <= 0:
            return None
        return QRect(left, top, right - left, bottom - top)
    except Exception:
        return None


def is_window_minimized(hwnd: int) -> bool:
    """対象ウィンドウが最小化中か判定する。"""
    if not HAS_WIN32:
        return False
    try:
        if win32gui:
            return bool(win32gui.IsIconic(hwnd))
        if _ctypes_win:
            return bool(_ctypes_win["IsIconic"](hwnd))
        return False
    except Exception:
        return False


def _capture_window_size(hwnd: int, *, get_window_rect_fn=get_window_rect) -> Optional[tuple[int, int]]:
    """対象ウィンドウのキャプチャ寸法を返す。"""
    wrect = get_window_rect_fn(hwnd)
    if wrect is None:
        return None
    width = int(wrect.width())
    height = int(wrect.height())
    if width <= 1 or height <= 1:
        return None
    return int(width), int(height)


def _create_window_capture_dc(user32, gdi32, hwnd: int):
    """WindowDC と互換メモリDCを作成して返す。"""
    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        return None, None
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    if not mem_dc:
        user32.ReleaseDC(hwnd, hwnd_dc)
        return None, None
    return hwnd_dc, mem_dc


def _release_window_capture_dc(user32, gdi32, hwnd: int, hwnd_dc, mem_dc) -> None:
    """WindowDC とメモリDCを解放する。"""
    if mem_dc:
        gdi32.DeleteDC(mem_dc)
    if hwnd_dc:
        user32.ReleaseDC(hwnd, hwnd_dc)


def _create_dib_section(
    *,
    ctypes_mod,
    wintypes_mod,
    gdi32,
    mem_dc,
    width: int,
    height: int,
):
    """32bit top-down DIB を作成し、メモリDCへ選択して返す。"""

    class BITMAPINFOHEADER(ctypes_mod.Structure):
        _fields_ = [
            ("biSize", wintypes_mod.DWORD),
            ("biWidth", wintypes_mod.LONG),
            ("biHeight", wintypes_mod.LONG),
            ("biPlanes", wintypes_mod.WORD),
            ("biBitCount", wintypes_mod.WORD),
            ("biCompression", wintypes_mod.DWORD),
            ("biSizeImage", wintypes_mod.DWORD),
            ("biXPelsPerMeter", wintypes_mod.LONG),
            ("biYPelsPerMeter", wintypes_mod.LONG),
            ("biClrUsed", wintypes_mod.DWORD),
            ("biClrImportant", wintypes_mod.DWORD),
        ]

    class BITMAPINFO(ctypes_mod.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes_mod.DWORD * 3)]

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes_mod.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = int(width)
    bmi.bmiHeader.biHeight = -int(height)
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = _WIN_BI_RGB

    bits = ctypes_mod.c_void_p()
    h_bitmap = gdi32.CreateDIBSection(
        mem_dc,
        ctypes_mod.byref(bmi),
        _WIN_DIB_RGB_COLORS,
        ctypes_mod.byref(bits),
        None,
        0,
    )
    if not h_bitmap or not bits:
        return None, None, None
    old_obj = gdi32.SelectObject(mem_dc, h_bitmap)
    return h_bitmap, old_obj, bits


def _print_window_to_dc(user32, hwnd: int, mem_dc) -> bool:
    """PrintWindow を実行してメモリDCへ描画する。"""
    ok = user32.PrintWindow(hwnd, mem_dc, _WIN_PRINTWINDOW_FULL)
    if ok:
        return True
    return bool(user32.PrintWindow(hwnd, mem_dc, 0))


def _dib_bits_to_bgr(*, ctypes_mod, bits, width: int, height: int) -> np.ndarray:
    """DIB先頭ポインタから BGR 画像を取り出す。"""
    size = int(width) * int(height) * 4
    buf = (ctypes_mod.c_ubyte * size).from_address(bits.value)
    bgra = np.frombuffer(buf, dtype=np.uint8).reshape((int(height), int(width), 4)).copy()
    return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)


def capture_window_bgr(
    hwnd: int,
    *,
    get_window_rect_fn=get_window_rect,
) -> Optional[np.ndarray]:
    """Win32 APIで対象ウィンドウ全体を BGR 画像として取得する。"""
    if not HAS_WIN32:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        size = _capture_window_size(hwnd, get_window_rect_fn=get_window_rect_fn)
        if size is None:
            return None
        width, height = size

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        hwnd_dc, mem_dc = _create_window_capture_dc(user32, gdi32, hwnd)
        if not hwnd_dc or not mem_dc:
            return None

        h_bitmap = None
        old_obj = None
        try:
            h_bitmap, old_obj, bits = _create_dib_section(
                ctypes_mod=ctypes,
                wintypes_mod=wintypes,
                gdi32=gdi32,
                mem_dc=mem_dc,
                width=width,
                height=height,
            )
            if not h_bitmap or not bits:
                return None
            if not _print_window_to_dc(user32, hwnd, mem_dc):
                return None
            return _dib_bits_to_bgr(
                ctypes_mod=ctypes,
                bits=bits,
                width=width,
                height=height,
            )
        finally:
            if old_obj:
                gdi32.SelectObject(mem_dc, old_obj)
            if h_bitmap:
                gdi32.DeleteObject(h_bitmap)
            _release_window_capture_dc(user32, gdi32, hwnd, hwnd_dc, mem_dc)
    except Exception:
        return None
