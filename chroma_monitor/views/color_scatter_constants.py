"""色相環 / 散布図ビューで共有する定数群。"""

from PySide6.QtGui import QColor

from .color_scatter_math import build_hue180_to_munsell40_weights

SCATTER_HUE_FILTER_HALF_WIDTH = 10
SCATTER_RESIZE_RECALC_DEBOUNCE_MS = 160
SCATTER_LAYOUT_SYNC_DEBOUNCE_MS = 24
MUNSELL_HUE_LABELS = (
    "2.5R",
    "5R",
    "7.5R",
    "10R",
    "2.5YR",
    "5YR",
    "7.5YR",
    "10YR",
    "2.5Y",
    "5Y",
    "7.5Y",
    "10Y",
    "2.5GY",
    "5GY",
    "7.5GY",
    "10GY",
    "2.5G",
    "5G",
    "7.5G",
    "10G",
    "2.5BG",
    "5BG",
    "7.5BG",
    "10BG",
    "2.5B",
    "5B",
    "7.5B",
    "10B",
    "2.5PB",
    "5PB",
    "7.5PB",
    "10PB",
    "2.5P",
    "5P",
    "7.5P",
    "10P",
    "2.5RP",
    "5RP",
    "7.5RP",
    "10RP",
)
MUNSELL_COLORS_RGB = (
    (218, 43, 97),
    (227, 32, 55),
    (228, 31, 32),
    (233, 108, 28),
    (237, 148, 20),
    (242, 172, 0),
    (246, 194, 0),
    (247, 200, 0),
    (241, 211, 2),
    (240, 220, 0),
    (241, 224, 0),
    (222, 217, 1),
    (200, 214, 35),
    (167, 198, 56),
    (112, 180, 62),
    (43, 169, 58),
    (0, 157, 81),
    (0, 161, 103),
    (0, 161, 125),
    (0, 156, 142),
    (0, 152, 156),
    (0, 148, 163),
    (2, 137, 159),
    (2, 135, 165),
    (0, 122, 163),
    (0, 110, 174),
    (1, 94, 169),
    (0, 76, 157),
    (7, 62, 149),
    (35, 39, 137),
    (54, 39, 138),
    (72, 39, 130),
    (64, 40, 131),
    (81, 40, 132),
    (116, 39, 137),
    (151, 27, 134),
    (173, 37, 136),
    (195, 38, 133),
    (202, 38, 133),
    (222, 35, 105),
)
WHEEL_HARMONY_GUIDE_RADIUS_RATIO = 0.82
WHEEL_HARMONY_GUIDE_DOT_RADIUS = 3
WHEEL_THICKNESS_MODE_ABSOLUTE = "absolute"
WHEEL_THICKNESS_MODE_RELATIVE_MAX = "relative_max"
WHEEL_THICKNESS_MODE = WHEEL_THICKNESS_MODE_RELATIVE_MAX
HUE180_TO_MUNSELL40_WEIGHTS = build_hue180_to_munsell40_weights(len(MUNSELL_HUE_LABELS))
MUNSELL_COLORS_Q = tuple(QColor(r, g, b, 255) for (r, g, b) in MUNSELL_COLORS_RGB)
HSV180_COLORS_Q = tuple(QColor.fromHsv(int((h / 180.0) * 360.0), 255, 255) for h in range(180))
