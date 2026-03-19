"""Qt 論理座標と mss/Win32 物理座標の対応付けヘルパー。"""

import mss
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication


def load_native_monitors() -> list[dict]:
    """mss から実モニタ一覧を取得する。"""
    try:
        with mss.mss() as sct:
            return [m for m in sct.monitors[1:]]
    except Exception:
        return []


def qt_screen_infos(qt_screens) -> list[dict]:
    """Qt画面一覧をマッチング用の情報辞書へ変換する。"""
    infos: list[dict] = []
    for screen in qt_screens:
        g = screen.geometry()
        infos.append(
            {
                "screen": screen,
                "rect": g,
                "dpr": max(0.5, float(screen.devicePixelRatio())),
            }
        )
    return infos


def qt_bounds(qt_infos: list[dict]) -> tuple[float, float, float, float]:
    """Qt画面群の境界を返す。"""
    q_left = min(info["rect"].left() for info in qt_infos)
    q_top = min(info["rect"].top() for info in qt_infos)
    q_right = max(info["rect"].left() + info["rect"].width() for info in qt_infos)
    q_bottom = max(info["rect"].top() + info["rect"].height() for info in qt_infos)
    q_w = max(1.0, float(q_right - q_left))
    q_h = max(1.0, float(q_bottom - q_top))
    return float(q_left), float(q_top), float(q_w), float(q_h)


def native_bounds(native_monitors: list[dict]) -> tuple[float, float, float, float]:
    """実モニタ群の境界を返す。"""
    m_left = min(m["left"] for m in native_monitors)
    m_top = min(m["top"] for m in native_monitors)
    m_right = max(m["left"] + m["width"] for m in native_monitors)
    m_bottom = max(m["top"] + m["height"] for m in native_monitors)
    m_w = max(1.0, float(m_right - m_left))
    m_h = max(1.0, float(m_bottom - m_top))
    return float(m_left), float(m_top), float(m_w), float(m_h)


def monitor_match_pairs(
    qt_infos: list[dict],
    native_monitors: list[dict],
    *,
    q_bounds: tuple[float, float, float, float],
    m_bounds: tuple[float, float, float, float],
) -> list[tuple[float, int, int]]:
    """Qt画面と実モニタの対応候補スコア一覧を作る。"""
    q_left, q_top, q_w, q_h = q_bounds
    m_left, m_top, m_w, m_h = m_bounds
    pairs: list[tuple[float, int, int]] = []
    for qi, q in enumerate(qt_infos):
        qrect = q["rect"]
        qw = max(1.0, float(qrect.width()))
        qh = max(1.0, float(qrect.height()))
        qcx = qrect.left() + qw * 0.5
        qcy = qrect.top() + qh * 0.5
        qx_norm = (qcx - q_left) / q_w
        qy_norm = (qcy - q_top) / q_h
        for mi, mon in enumerate(native_monitors):
            sx = float(mon["width"]) / qw
            sy = float(mon["height"]) / qh
            mcx = mon["left"] + mon["width"] * 0.5
            mcy = mon["top"] + mon["height"] * 0.5
            mx_norm = (mcx - m_left) / m_w
            my_norm = (mcy - m_top) / m_h
            score = (
                abs(sx - sy) * 300.0
                + abs(sx - q["dpr"]) * 80.0
                + abs(sy - q["dpr"]) * 80.0
                + abs(qx_norm - mx_norm) * 60.0
                + abs(qy_norm - my_norm) * 60.0
            )
            pairs.append((score, qi, mi))
    pairs.sort(key=lambda x: x[0])
    return pairs


def resolve_monitor_mapping(
    qt_infos: list[dict],
    native_monitors: list[dict],
    pairs: list[tuple[float, int, int]],
) -> dict:
    """候補スコアから画面対応表を解決する。"""
    used_q = set()
    used_m = set()
    mapping = {}
    for _, qi, mi in pairs:
        if qi in used_q or mi in used_m:
            continue
        used_q.add(qi)
        used_m.add(mi)
        mapping[qt_infos[qi]["screen"]] = native_monitors[mi]

    for i, info in enumerate(qt_infos):
        if info["screen"] in mapping:
            continue
        fallback = native_monitors[min(i, len(native_monitors) - 1)]
        mapping[info["screen"]] = fallback
    return mapping


def current_screen_signature(qt_screens) -> tuple:
    """現在の Qt 画面構成を表すキャッシュキーを返す。"""
    return tuple(
        (
            id(screen),
            str(screen.name()),
            int(screen.geometry().left()),
            int(screen.geometry().top()),
            int(screen.geometry().width()),
            int(screen.geometry().height()),
            round(float(screen.devicePixelRatio()), 3),
        )
        for screen in qt_screens
    )


def build_screen_monitor_map(
    *,
    cache: dict | None,
    signature: tuple,
) -> tuple[dict, tuple]:
    """Qt画面とmssモニタの対応表を構築/再利用する。"""
    qt_screens = QGuiApplication.screens()
    if not qt_screens:
        return {}, ()
    screen_sig = current_screen_signature(qt_screens)
    if isinstance(cache, dict) and cache and signature == screen_sig:
        return cache, screen_sig

    native_monitors = load_native_monitors()
    if not native_monitors:
        return {}, screen_sig
    qt_infos = qt_screen_infos(qt_screens)
    pairs = monitor_match_pairs(
        qt_infos,
        native_monitors,
        q_bounds=qt_bounds(qt_infos),
        m_bounds=native_bounds(native_monitors),
    )
    return resolve_monitor_mapping(qt_infos, native_monitors, pairs), screen_sig


def logical_point_to_native(x: float, y: float, mapping) -> tuple[float, float]:
    """Qt論理座標の点を物理座標へ変換する。"""
    screen = QGuiApplication.screenAt(QPoint(int(round(x)), int(round(y))))
    if screen is None:
        screens = QGuiApplication.screens()
        screen = screens[0] if screens else None
    mon = mapping.get(screen) if screen is not None else None
    if screen is None or mon is None:
        return float(x), float(y)

    g = screen.geometry()
    gw = max(1.0, float(g.width()))
    gh = max(1.0, float(g.height()))
    sx = float(mon["width"]) / gw
    sy = float(mon["height"]) / gh
    nx = float(mon["left"]) + (float(x) - float(g.left())) * sx
    ny = float(mon["top"]) + (float(y) - float(g.top())) * sy
    return nx, ny


def native_point_to_logical(x: float, y: float, mapping) -> tuple[float, float]:
    """物理座標の点をQt論理座標へ変換する。"""
    target_screen = None
    target_mon = None
    for screen, mon in mapping.items():
        left = float(mon["left"])
        top = float(mon["top"])
        right = left + float(mon["width"])
        bottom = top + float(mon["height"])
        if left <= float(x) < right and top <= float(y) < bottom:
            target_screen = screen
            target_mon = mon
            break

    if target_screen is None or target_mon is None:
        best = None
        best_dist = None
        for screen, mon in mapping.items():
            cx = float(mon["left"]) + float(mon["width"]) * 0.5
            cy = float(mon["top"]) + float(mon["height"]) * 0.5
            dist = (float(x) - cx) ** 2 + (float(y) - cy) ** 2
            if best is None or (best_dist is not None and dist < best_dist):
                best = (screen, mon)
                best_dist = dist
        if best is None:
            return float(x), float(y)
        target_screen, target_mon = best

    g = target_screen.geometry()
    mw = max(1.0, float(target_mon["width"]))
    mh = max(1.0, float(target_mon["height"]))
    lx = float(g.left()) + (float(x) - float(target_mon["left"])) * (float(g.width()) / mw)
    ly = float(g.top()) + (float(y) - float(target_mon["top"])) * (float(g.height()) / mh)
    return lx, ly


def logical_rect_to_native(rect: QRect, mapping) -> QRect:
    """Qt論理座標の矩形を物理座標矩形へ変換する。"""
    if not mapping:
        return QRect(rect)
    x1, y1 = logical_point_to_native(float(rect.left()), float(rect.top()), mapping)
    x2, y2 = logical_point_to_native(
        float(rect.left() + rect.width()),
        float(rect.top() + rect.height()),
        mapping,
    )
    left = int(round(min(x1, x2)))
    top = int(round(min(y1, y2)))
    width = max(1, int(round(abs(x2 - x1))))
    height = max(1, int(round(abs(y2 - y1))))
    return QRect(left, top, width, height)


def native_rect_to_logical(rect: QRect, mapping) -> QRect:
    """物理座標の矩形をQt論理座標矩形へ変換する。"""
    if not mapping:
        return QRect(rect)
    x1, y1 = native_point_to_logical(float(rect.left()), float(rect.top()), mapping)
    x2, y2 = native_point_to_logical(
        float(rect.left() + rect.width()),
        float(rect.top() + rect.height()),
        mapping,
    )
    left = int(round(min(x1, x2)))
    top = int(round(min(y1, y2)))
    width = max(1, int(round(abs(x2 - x1))))
    height = max(1, int(round(abs(y2 - y1))))
    return QRect(left, top, width, height)
