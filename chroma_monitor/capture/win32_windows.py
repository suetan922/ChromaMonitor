import sys

HAS_WIN32 = sys.platform.startswith("win")

ctypes_win_api = None
if HAS_WIN32:
    try:
        import win32gui  # type: ignore
    except Exception:
        win32gui = None
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            ctypes_win_api = {
                "EnumWindows": user32.EnumWindows,
                "IsWindowVisible": user32.IsWindowVisible,
                "GetWindowTextW": user32.GetWindowTextW,
                "GetWindowTextLengthW": user32.GetWindowTextLengthW,
                "GetWindowRect": user32.GetWindowRect,
                "IsIconic": user32.IsIconic,
            }
            # argtypes を設定して不正呼び出しを防ぐ
            ctypes_win_api["EnumWindows"].argtypes = [
                ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM),
                wintypes.LPARAM,
            ]
            ctypes_win_api["IsWindowVisible"].argtypes = [wintypes.HWND]
            ctypes_win_api["GetWindowTextW"].argtypes = [
                wintypes.HWND,
                wintypes.LPWSTR,
                ctypes.c_int,
            ]
            ctypes_win_api["GetWindowTextLengthW"].argtypes = [wintypes.HWND]
            ctypes_win_api["GetWindowRect"].argtypes = [
                wintypes.HWND,
                ctypes.POINTER(wintypes.RECT),
            ]
            ctypes_win_api["IsIconic"].argtypes = [wintypes.HWND]
        except Exception:
            HAS_WIN32 = False
            ctypes_win_api = None
else:
    win32gui = None


def list_windows():
    if not HAS_WIN32:
        return []

    out = []
    if win32gui:

        def enum_proc(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title or not title.strip():
                return
            out.append((hwnd, title))

        win32gui.EnumWindows(enum_proc, None)
    elif ctypes_win_api:
        import ctypes
        from ctypes import wintypes

        enum_windows = ctypes_win_api["EnumWindows"]
        is_window_visible = ctypes_win_api["IsWindowVisible"]
        get_window_text_length = ctypes_win_api["GetWindowTextLengthW"]
        get_window_text = ctypes_win_api["GetWindowTextW"]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def enum_proc(hwnd, _lparam):
            if not is_window_visible(hwnd):
                return True
            length = get_window_text_length(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            get_window_text(hwnd, buf, length + 1)
            title = buf.value
            if title and title.strip():
                out.append((hwnd, title))
            return True

        enum_windows(enum_proc, 0)

    out.sort(key=lambda x: x[1].lower())
    return out
