"""アプリ全体で共有する定数。"""

from PySide6.QtGui import QColor

# App/update metadata
APP_VERSION = "0.1.0"
"""現在のアプリバージョン文字列。"""
GITHUB_REPOSITORY = "suetan922/ChromaMonitor"
"""GitHub上の ``owner/repository`` 名。"""
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"
"""GitHub Releases 一覧URL。"""
LATEST_RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
"""最新リリース情報取得用のGitHub API URL。"""
UPDATE_CHECK_TIMEOUT_MS = 5000
"""更新確認HTTP要求のタイムアウト(ms)。"""

# ROI defaults
DEFAULT_ROI_SIZE = (640, 360)
"""ROI未指定時の初期サイズ（幅, 高さ）。"""

# Analyzer constraints
ANALYZER_MAX_DIM = 400
"""解析時の既定長辺ピクセル。"""
ANALYZER_MAX_DIM_MIN = 120
"""解析長辺のUI入力最小値。"""
ANALYZER_MAX_DIM_MAX = 4096
"""解析長辺のUI入力最大値。"""
# 画像読み込み時のみ使う内部自動上限（UI設定には出さない）
IMAGE_FILE_ANALYSIS_AUTO_MAX_DIM = 3072
ANALYZER_MIN_INTERVAL_SEC = 0.05
"""定期更新モードの最小間隔(秒)。"""
ANALYZER_MIN_SAMPLE_POINTS = 500
"""散布図サンプリング点数の最小値。"""
ANALYZER_MAX_SAMPLE_POINTS = 500000
"""散布図サンプリング点数の最大値。"""
ANALYZER_MIN_GRAPH_EVERY = 1
"""グラフ更新間引きの最小値。"""
ANALYZER_MIN_DIFF_THRESHOLD = 0.5
"""変化検出モードの差分しきい値最小値。"""
ANALYZER_MIN_STABLE_FRAMES = 1
"""変化検出モードの安定フレーム最小値。"""
ANALYZER_CHANGE_POLL_SEC = 0.08
"""変化検出のポーリング周期(秒)。"""
ANALYZER_CHANGE_COOLDOWN_SEC = 0.12
"""検出後クールダウン時間(秒)。"""
ANALYZER_CHANGE_DETECT_DIM = 120
"""変化検出用の縮小解像度（長辺）。"""

# Capture sources
CAPTURE_SOURCE_WINDOW = "window"
"""キャプチャ元: ウィンドウ。"""
CAPTURE_SOURCE_SCREEN = "screen"
"""キャプチャ元: 画面領域。"""
CAPTURE_SOURCES = (CAPTURE_SOURCE_WINDOW, CAPTURE_SOURCE_SCREEN)
"""キャプチャ元の許可値一覧。"""

# Scatter plot shapes
SCATTER_SHAPE_SQUARE = "square"
"""散布図形状: 四角座標。"""
SCATTER_SHAPE_TRIANGLE = "triangle"
"""散布図形状: 三角座標。"""
SCATTER_SHAPES = (SCATTER_SHAPE_SQUARE, SCATTER_SHAPE_TRIANGLE)
"""散布図形状の許可値一覧。"""
SCATTER_RENDER_MODE_DOMINANT = "dominant"
"""散布図描画: セル最頻色。"""
SCATTER_RENDER_MODE_HEATMAP = "heatmap"
"""散布図描画: 密度ヒートマップ。"""
SCATTER_RENDER_MODES = (SCATTER_RENDER_MODE_DOMINANT, SCATTER_RENDER_MODE_HEATMAP)
"""散布図描画モードの許可値一覧。"""

# Color wheel display modes
WHEEL_MODE_HSV180 = "hsv180"
WHEEL_MODE_MUNSELL40 = "munsell40"
WHEEL_MODES = (WHEEL_MODE_HSV180, WHEEL_MODE_MUNSELL40)

# RGB histogram display modes
RGB_HIST_MODE_SIDE_BY_SIDE = "side_by_side"
RGB_HIST_MODE_OVERLAY = "overlay"
RGB_HIST_MODES = (RGB_HIST_MODE_SIDE_BY_SIDE, RGB_HIST_MODE_OVERLAY)

# Analysis resolution modes
ANALYSIS_RESOLUTION_MODE_ORIGINAL = "original"
ANALYSIS_RESOLUTION_MODE_CUSTOM = "custom"
ANALYSIS_RESOLUTION_MODES = (
    ANALYSIS_RESOLUTION_MODE_ORIGINAL,
    ANALYSIS_RESOLUTION_MODE_CUSTOM,
)

# Update modes
UPDATE_MODE_INTERVAL = "interval"
UPDATE_MODE_CHANGE = "change"
UPDATE_MODES = (UPDATE_MODE_INTERVAL, UPDATE_MODE_CHANGE)

# Binary presets
BINARY_PRESET_AUTO = "auto"
BINARY_PRESET_MORE_WHITE = "more_white"
BINARY_PRESET_MORE_BLACK = "more_black"
BINARY_PRESETS = (BINARY_PRESET_AUTO, BINARY_PRESET_MORE_WHITE, BINARY_PRESET_MORE_BLACK)

# Ternary presets
TERNARY_PRESET_STANDARD = "standard"
TERNARY_PRESET_SOFT = "soft"
TERNARY_PRESET_STRONG = "strong"
TERNARY_PRESETS = (TERNARY_PRESET_STANDARD, TERNARY_PRESET_SOFT, TERNARY_PRESET_STRONG)

# Focus peaking colors
FOCUS_PEAK_COLOR_CYAN = "cyan"
FOCUS_PEAK_COLOR_GREEN = "green"
FOCUS_PEAK_COLOR_YELLOW = "yellow"
FOCUS_PEAK_COLOR_RED = "red"
FOCUS_PEAK_COLORS = (
    FOCUS_PEAK_COLOR_CYAN,
    FOCUS_PEAK_COLOR_GREEN,
    FOCUS_PEAK_COLOR_YELLOW,
    FOCUS_PEAK_COLOR_RED,
)
FOCUS_PEAK_COLOR_BGR = {
    FOCUS_PEAK_COLOR_CYAN: (255, 235, 0),
    FOCUS_PEAK_COLOR_GREEN: (0, 245, 120),
    FOCUS_PEAK_COLOR_YELLOW: (0, 225, 255),
    FOCUS_PEAK_COLOR_RED: (60, 60, 255),
}

# Squint modes
SQUINT_MODE_BLUR = "blur"
SQUINT_MODE_SCALE = "scale"
SQUINT_MODE_SCALE_BLUR = "scale_blur"
SQUINT_MODES = (
    SQUINT_MODE_BLUR,
    SQUINT_MODE_SCALE,
    SQUINT_MODE_SCALE_BLUR,
)

# Vectorscope
VECTORSCOPE_SIZE = 256
"""ベクトルスコープ基準キャンバスサイズ(px)。"""
VECTORSCOPE_CHROMA_FULL_SCALE = 181.0
"""彩度100%を表す半径基準値。"""
VECTORSCOPE_SKIN_LINE_ANGLE_DEG = 123.0
"""スキントーンライン角度(度)。"""
VECTORSCOPE_SCOPE_RADIUS_RATIO = 0.46
"""描画領域に対するスコープ半径比。"""
VECTORSCOPE_WARN_THRESHOLD_MIN = 40
"""高彩度警告しきい値(%)の最小値。"""
VECTORSCOPE_WARN_THRESHOLD_MAX = 100
"""高彩度警告しきい値(%)の最大値。"""
VECTORSCOPE_WARN_COLOR_BGR = (32, 64, 250)
"""高彩度警告表示色(BGR)。"""

# Color wheel orientation
# YUV vectorscope基準に合わせる。0度(赤)はおおむね左上方向。
COLOR_WHEEL_HUE_OFFSET_DEG = 106.0

# Munsell-like 40 hue labels and palette (2.5 steps)
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

# Composition guides
COMPOSITION_GUIDE_NONE = "none"
COMPOSITION_GUIDE_THIRDS = "thirds"
COMPOSITION_GUIDE_CENTER = "center"
COMPOSITION_GUIDE_DIAGONAL = "diagonal"
COMPOSITION_GUIDES = (
    COMPOSITION_GUIDE_NONE,
    COMPOSITION_GUIDE_THIRDS,
    COMPOSITION_GUIDE_CENTER,
    COMPOSITION_GUIDE_DIAGONAL,
)

# General defaults
DEFAULT_INTERVAL_SEC = 2.0
"""更新間隔の既定値(秒)。"""
DEFAULT_SAMPLE_POINTS = 30000
"""散布図サンプリング点数の既定値。"""
DEFAULT_GRAPH_EVERY = 1
"""グラフ更新頻度の既定値。"""
DEFAULT_CAPTURE_SOURCE = CAPTURE_SOURCE_WINDOW
"""キャプチャ元の既定値。"""
DEFAULT_SCATTER_SHAPE = SCATTER_SHAPE_SQUARE
"""散布図形状の既定値。"""
DEFAULT_SCATTER_RENDER_MODE = SCATTER_RENDER_MODE_DOMINANT
"""散布図描画モードの既定値。"""
SCATTER_HUE_MIN = 0
"""色相スライダー最小値。"""
SCATTER_HUE_MAX = 179
"""色相スライダー最大値。"""
DEFAULT_SCATTER_HUE_FILTER_ENABLED = False
"""色相フィルター有効状態の既定値。"""
DEFAULT_SCATTER_HUE_CENTER = 0
"""色相フィルター中心値の既定値。"""
SCATTER_HUE_FILTER_HALF_WIDTH = 10
"""色相フィルター半値幅(度相当)。"""
DEFAULT_ANALYSIS_RESOLUTION_MODE = ANALYSIS_RESOLUTION_MODE_ORIGINAL
"""解析解像度モード既定値。"""
DEFAULT_WHEEL_MODE = WHEEL_MODE_HSV180
"""色相環モード既定値。"""
DEFAULT_RGB_HIST_MODE = RGB_HIST_MODE_SIDE_BY_SIDE
"""RGBヒストグラム表示モード既定値。"""
DEFAULT_WHEEL_SAT_THRESHOLD = 1
"""色相環集計で使う彩度しきい値既定値。"""
DEFAULT_EDGE_SENSITIVITY = 50
"""エッジ検出感度既定値。"""
DEFAULT_BINARY_PRESET = BINARY_PRESET_AUTO
"""2値化プリセット既定値。"""
DEFAULT_TERNARY_PRESET = TERNARY_PRESET_STANDARD
"""3値化プリセット既定値。"""
DEFAULT_SALIENCY_OVERLAY_ALPHA = 65
"""サリエンシーオーバーレイ不透明度既定値。"""
DEFAULT_COMPOSITION_GUIDE = COMPOSITION_GUIDE_NONE
"""構図ガイド既定値。"""
DEFAULT_FOCUS_PEAK_SENSITIVITY = 20
"""フォーカスピーキング感度既定値。"""
DEFAULT_FOCUS_PEAK_COLOR = FOCUS_PEAK_COLOR_RED
"""フォーカスピーキング色既定値。"""
DEFAULT_FOCUS_PEAK_THICKNESS = 1.0
"""フォーカスピーキング線幅既定値。"""
DEFAULT_SQUINT_MODE = SQUINT_MODE_SCALE_BLUR
"""スクイント表示モード既定値。"""
DEFAULT_SQUINT_SCALE_PERCENT = 18
"""スクイント縮小率(%)既定値。"""
DEFAULT_SQUINT_BLUR_SIGMA = 1.8
"""スクイントぼかしσ既定値。"""
DEFAULT_VECTORSCOPE_SHOW_SKIN_LINE = True
"""ベクトルスコープ肌色線の既定表示状態。"""
DEFAULT_VECTORSCOPE_WARN_THRESHOLD = 90
"""高彩度警告しきい値(%)既定値。"""
DEFAULT_PREVIEW_WINDOW = False
"""プレビュー別ウィンドウ表示の既定値。"""
DEFAULT_ALWAYS_ON_TOP = False
"""常に最前面表示の既定値。"""

# UI colors for histograms
H_COLOR = QColor(220, 90, 90)
"""Hヒストグラム描画色。"""
S_COLOR = QColor(90, 170, 90)
"""Sヒストグラム描画色。"""
V_COLOR = QColor(80, 140, 240)
"""Vヒストグラム描画色。"""
R_COLOR = QColor(228, 84, 84)
"""Rヒストグラム描画色。"""
G_COLOR = QColor(88, 176, 96)
"""Gヒストグラム描画色。"""
B_COLOR = QColor(88, 126, 236)
"""Bヒストグラム描画色。"""

# Change-trigger defaults
DEFAULT_MODE = UPDATE_MODE_INTERVAL
DEFAULT_DIFF_THRESHOLD = 4.0
DEFAULT_STABLE_FRAMES = 3

# UI behavior defaults
WINDOW_LIST_MAX_ITEMS = 500
"""ウィンドウ一覧コンボへ表示する最大件数。"""
VIEW_MIN_SIZE = 48
"""ドック/ビューの共通最小サイズ(px)。"""
SETTINGS_SAVE_DEBOUNCE_MS = 220
"""設定保存のデバウンス時間(ms)。"""
DOCK_REBALANCE_DEBOUNCE_MS = 36
"""ドック再バランスのデバウンス時間(ms)。"""
LAYOUT_ENGINE_VERSION = 2
"""レイアウト保存仕様の内部バージョン。"""

# Settings page indices
SETTINGS_PAGE_CAPTURE = 0
SETTINGS_PAGE_UPDATE = 1
SETTINGS_PAGE_SCATTER = 2
SETTINGS_PAGE_WHEEL = 3
SETTINGS_PAGE_IMAGE = 4
SETTINGS_PAGE_SALIENCY = 5
SETTINGS_PAGE_FOCUS = 6
SETTINGS_PAGE_SQUINT = 7
SETTINGS_PAGE_VECTORSCOPE = 8
SETTINGS_PAGE_LAYOUT = 9
SETTINGS_PAGE_RGB_HIST = 10

# Shared UI ranges
WHEEL_SAT_THRESHOLD_MIN = 0
"""色相環彩度しきい値の最小値。"""
WHEEL_SAT_THRESHOLD_MAX = 255
"""色相環彩度しきい値の最大値。"""
EDGE_SENSITIVITY_MIN = 1
"""エッジ検出感度の最小値。"""
EDGE_SENSITIVITY_MAX = 100
"""エッジ検出感度の最大値。"""
SALIENCY_ALPHA_MIN = 0
"""サリエンシー不透明度の最小値。"""
SALIENCY_ALPHA_MAX = 100
"""サリエンシー不透明度の最大値。"""
FOCUS_PEAK_SENSITIVITY_MIN = 1
"""フォーカスピーキング感度の最小値。"""
FOCUS_PEAK_SENSITIVITY_MAX = 100
"""フォーカスピーキング感度の最大値。"""
FOCUS_PEAK_THICKNESS_MIN = 0.1
"""フォーカスピーキング線幅の最小値。"""
FOCUS_PEAK_THICKNESS_MAX = 6.0
"""フォーカスピーキング線幅の最大値。"""
FOCUS_PEAK_THICKNESS_STEP = 0.1
"""フォーカスピーキング線幅の刻み値。"""
SQUINT_SCALE_PERCENT_MIN = 2
"""スクイント縮小率(%)の最小値。"""
SQUINT_SCALE_PERCENT_MAX = 100
"""スクイント縮小率(%)の最大値。"""
SQUINT_BLUR_SIGMA_MIN = 0.0
"""スクイントぼかしσの最小値。"""
SQUINT_BLUR_SIGMA_MAX = 30.0
"""スクイントぼかしσの最大値。"""
SQUINT_BLUR_SIGMA_STEP = 0.1
"""スクイントぼかしσの刻み値。"""

# Top-color display
TOP_COLORS_TITLE = "色割合TOP5"
TOP_COLORS_COUNT = 5
TOP_COLOR_BAR_HEIGHT = 24

# Config keys
CFG_INTERVAL = "interval"
CFG_SAMPLE_POINTS = "sample_points"
CFG_ANALYZER_MAX_DIM = "analyzer_max_dim"
CFG_ANALYSIS_RESOLUTION_MODE = "analysis_resolution_mode"
CFG_SCATTER_SHAPE = "scatter_shape"
CFG_SCATTER_RENDER_MODE = "scatter_render_mode"
CFG_SCATTER_HUE_FILTER_ENABLED = "scatter_hue_filter_enabled"
CFG_SCATTER_HUE_CENTER = "scatter_hue_center"
CFG_WHEEL_MODE = "wheel_mode"
CFG_RGB_HIST_MODE = "rgb_hist_mode"
CFG_WHEEL_SAT_THRESHOLD = "wheel_sat_threshold"
CFG_CAPTURE_SOURCE = "capture_source"
CFG_EDGE_SENSITIVITY = "edge_sensitivity"
CFG_BINARY_PRESET = "binary_preset"
CFG_TERNARY_PRESET = "ternary_preset"
CFG_SALIENCY_OVERLAY_ALPHA = "saliency_overlay_alpha"
CFG_COMPOSITION_GUIDE = "composition_guide"
CFG_FOCUS_PEAK_SENSITIVITY = "focus_peak_sensitivity"
CFG_FOCUS_PEAK_COLOR = "focus_peak_color"
CFG_FOCUS_PEAK_THICKNESS = "focus_peak_thickness"
CFG_SQUINT_MODE = "squint_mode"
CFG_SQUINT_SCALE_PERCENT = "squint_scale_percent"
CFG_SQUINT_BLUR_SIGMA = "squint_blur_sigma"
CFG_VECTORSCOPE_SHOW_SKIN_LINE = "vectorscope_show_skin_line"
CFG_VECTORSCOPE_WARN_THRESHOLD = "vectorscope_warn_threshold"
CFG_ALWAYS_ON_TOP = "always_on_top"
CFG_MODE = "mode"
CFG_DIFF_THRESHOLD = "diff_threshold"
CFG_STABLE_FRAMES = "stable_frames"
CFG_LAYOUT_ENGINE_VERSION = "layout_engine_version"
CFG_LAYOUT_CURRENT = "layout_current"
CFG_LAYOUT_PRESETS = "layout_presets"
