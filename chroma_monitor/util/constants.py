"""アプリ全体で共有する定数。"""

# Application identity
APP_NAME = "ChromaMonitor"
"""アプリケーション名。"""
APP_GITHUB_REPOSITORY = "suetan922/ChromaMonitor"
"""更新確認に使う GitHub リポジトリ識別子。"""
APP_RELEASES_URL = f"https://github.com/{APP_GITHUB_REPOSITORY}/releases"
"""リリースページURL。"""

# Analyzer constraints
ANALYZER_MAX_DIM = 640
"""解析時の既定長辺ピクセル。"""
ANALYZER_MAX_DIM_MIN = 120
"""解析長辺のUI入力最小値。"""
ANALYZER_MAX_DIM_MAX = 4096
"""解析長辺のUI入力最大値。"""
ANALYZER_MIN_SAMPLE_POINTS = 500
"""散布図サンプリング点数の最小値。"""
ANALYZER_MAX_SAMPLE_POINTS = 500000
"""散布図サンプリング点数の最大値。"""
ANALYZER_MIN_DIFF_THRESHOLD = 0.01
"""変化検出モードの差分しきい値最小値。"""
ANALYZER_MIN_STABLE_FRAMES = 1
"""変化検出モードの安定フレーム最小値。"""

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

# Color harmony guide types
WHEEL_HARMONY_GUIDE_NONE = "none"
"""色彩調和ガイド: 表示なし。"""
WHEEL_HARMONY_GUIDE_IDENTITY = "identity"
"""色彩調和ガイド: アイデンティティ。"""
WHEEL_HARMONY_GUIDE_ANALOGOUS = "analogous"
"""色彩調和ガイド: アナロジー。"""
WHEEL_HARMONY_GUIDE_INTERMEDIATE = "intermediate"
"""色彩調和ガイド: インターミディエート。"""
WHEEL_HARMONY_GUIDE_COMPLEMENTARY = "complementary"
"""色彩調和ガイド: コンプリメンタリー。"""
WHEEL_HARMONY_GUIDE_OPPONENT = "opponent"
"""色彩調和ガイド: オポーネント。"""
WHEEL_HARMONY_GUIDE_SPLIT_COMPLEMENTARY = "split_complementary"
"""色彩調和ガイド: スプリットコンプリメンタリー。"""
WHEEL_HARMONY_GUIDE_TRIAD = "triad"
"""色彩調和ガイド: トライアド。"""
WHEEL_HARMONY_GUIDE_TETRAD = "tetrad"
"""色彩調和ガイド: テトラード（正方形）。"""
WHEEL_HARMONY_GUIDE_TETRAD_RECT = "tetrad_rect"
"""色彩調和ガイド: テトラード（長方形）。"""
WHEEL_HARMONY_GUIDE_PENTAD = "pentad"
"""色彩調和ガイド: ペンタード。"""
WHEEL_HARMONY_GUIDE_HEXAD = "hexad"
"""色彩調和ガイド: ヘクサード。"""
WHEEL_HARMONY_GUIDE_TYPES = (
    WHEEL_HARMONY_GUIDE_NONE,
    WHEEL_HARMONY_GUIDE_IDENTITY,
    WHEEL_HARMONY_GUIDE_ANALOGOUS,
    WHEEL_HARMONY_GUIDE_INTERMEDIATE,
    WHEEL_HARMONY_GUIDE_COMPLEMENTARY,
    WHEEL_HARMONY_GUIDE_OPPONENT,
    WHEEL_HARMONY_GUIDE_SPLIT_COMPLEMENTARY,
    WHEEL_HARMONY_GUIDE_TRIAD,
    WHEEL_HARMONY_GUIDE_TETRAD,
    WHEEL_HARMONY_GUIDE_TETRAD_RECT,
    WHEEL_HARMONY_GUIDE_PENTAD,
    WHEEL_HARMONY_GUIDE_HEXAD,
)
"""色彩調和ガイドの許可値一覧。"""
WHEEL_HARMONY_GUIDE_COMBO_ORDER = (
    WHEEL_HARMONY_GUIDE_IDENTITY,
    WHEEL_HARMONY_GUIDE_ANALOGOUS,
    WHEEL_HARMONY_GUIDE_INTERMEDIATE,
    WHEEL_HARMONY_GUIDE_COMPLEMENTARY,
    WHEEL_HARMONY_GUIDE_OPPONENT,
    WHEEL_HARMONY_GUIDE_SPLIT_COMPLEMENTARY,
    WHEEL_HARMONY_GUIDE_TRIAD,
    WHEEL_HARMONY_GUIDE_TETRAD,
    WHEEL_HARMONY_GUIDE_TETRAD_RECT,
    WHEEL_HARMONY_GUIDE_PENTAD,
    WHEEL_HARMONY_GUIDE_HEXAD,
)
"""色彩調和コンボボックスの表示順。"""
WHEEL_HARMONY_GUIDE_LABELS = {
    WHEEL_HARMONY_GUIDE_NONE: "なし",
    WHEEL_HARMONY_GUIDE_IDENTITY: "アイデンティティ",
    WHEEL_HARMONY_GUIDE_ANALOGOUS: "アナロジー",
    WHEEL_HARMONY_GUIDE_INTERMEDIATE: "インターミディエート",
    WHEEL_HARMONY_GUIDE_COMPLEMENTARY: "コンプリメンタリー",
    WHEEL_HARMONY_GUIDE_OPPONENT: "オポーネント",
    WHEEL_HARMONY_GUIDE_SPLIT_COMPLEMENTARY: "スプリットコンプリメンタリー",
    WHEEL_HARMONY_GUIDE_TRIAD: "トライアド",
    WHEEL_HARMONY_GUIDE_TETRAD: "テトラード（正方形）",
    WHEEL_HARMONY_GUIDE_TETRAD_RECT: "テトラード（長方形）",
    WHEEL_HARMONY_GUIDE_PENTAD: "ペンタード",
    WHEEL_HARMONY_GUIDE_HEXAD: "ヘクサード",
}
"""色彩調和タイプの表示ラベル。"""
WHEEL_HARMONY_GUIDE_OFFSETS_DEG = {
    WHEEL_HARMONY_GUIDE_NONE: (0.0,),
    WHEEL_HARMONY_GUIDE_IDENTITY: (0.0,),
    WHEEL_HARMONY_GUIDE_ANALOGOUS: (-30.0, 0.0, 30.0),
    WHEEL_HARMONY_GUIDE_INTERMEDIATE: (-60.0, 0.0, 60.0),
    # HSV基準ではコンプリメンタリーは補色(H+180deg)と同義。
    WHEEL_HARMONY_GUIDE_COMPLEMENTARY: (0.0, 180.0),
    WHEEL_HARMONY_GUIDE_OPPONENT: (0.0, 150.0),
    WHEEL_HARMONY_GUIDE_SPLIT_COMPLEMENTARY: (0.0, 150.0, 210.0),
    WHEEL_HARMONY_GUIDE_TRIAD: (0.0, 120.0, 240.0),
    WHEEL_HARMONY_GUIDE_TETRAD: (0.0, 90.0, 180.0, 270.0),
    WHEEL_HARMONY_GUIDE_TETRAD_RECT: (0.0, 60.0, 180.0, 240.0),
    WHEEL_HARMONY_GUIDE_PENTAD: (0.0, 72.0, 144.0, 216.0, 288.0),
    WHEEL_HARMONY_GUIDE_HEXAD: (0.0, 60.0, 120.0, 180.0, 240.0, 300.0),
}
"""色彩調和タイプごとの色相オフセット角度。"""

# RGB histogram display modes
RGB_HIST_MODE_SIDE_BY_SIDE = "side_by_side"
RGB_HIST_MODE_OVERLAY = "overlay"
RGB_HIST_MODES = (RGB_HIST_MODE_SIDE_BY_SIDE, RGB_HIST_MODE_OVERLAY)

# Mirror display modes
MIRROR_MODE_HORIZONTAL = "horizontal"
MIRROR_MODE_VERTICAL = "vertical"
MIRROR_MODE_BOTH = "both"
MIRROR_MODES = (
    MIRROR_MODE_HORIZONTAL,
    MIRROR_MODE_VERTICAL,
    MIRROR_MODE_BOTH,
)

# Analysis resolution modes
ANALYSIS_RESOLUTION_MODE_ORIGINAL = "original"
ANALYSIS_RESOLUTION_MODE_CUSTOM = "custom"
ANALYSIS_RESOLUTION_MODES = (
    ANALYSIS_RESOLUTION_MODE_ORIGINAL,
    ANALYSIS_RESOLUTION_MODE_CUSTOM,
)
"""解析解像度モードの許可値一覧。"""

# Update modes
UPDATE_MODE_INTERVAL = "interval"
UPDATE_MODE_CHANGE = "change"
UPDATE_MODES = (UPDATE_MODE_INTERVAL, UPDATE_MODE_CHANGE)

# Shared hue orientation
HUE_RED_REFERENCE_DEG = 150.0
"""色相表示での赤(0deg)の基準角度。黄色(約60deg)が真上になる値。"""
HUE_DIRECTION_SIGN = -1.0
"""色相進行方向。`1.0` は反時計回り、`-1.0` は時計回り。"""

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
VECTORSCOPE_WARN_THRESHOLD_MIN = 1
"""高彩度警告しきい値(%)の最小値。"""
VECTORSCOPE_WARN_THRESHOLD_MAX = 100
"""高彩度警告しきい値(%)の最大値。"""

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
DEFAULT_ANALYSIS_RESOLUTION_MODE = ANALYSIS_RESOLUTION_MODE_ORIGINAL
"""解析解像度モード既定値。"""
DEFAULT_WHEEL_MODE = WHEEL_MODE_HSV180
"""色相環モード既定値。"""
DEFAULT_WHEEL_HARMONY_GUIDE_ENABLED = False
"""色彩調和ガイド表示の既定値。"""
DEFAULT_WHEEL_HARMONY_GUIDE_TYPE = WHEEL_HARMONY_GUIDE_IDENTITY
"""色彩調和ガイド種別の既定値。"""
DEFAULT_RGB_HIST_MODE = RGB_HIST_MODE_SIDE_BY_SIDE
"""RGBヒストグラム表示モード既定値。"""
DEFAULT_MIRROR_MODE = MIRROR_MODE_HORIZONTAL
"""反転表示モード既定値。"""
DEFAULT_WHEEL_SAT_THRESHOLD = 1
"""色相環集計で使う彩度しきい値既定値。"""
DEFAULT_COLOR_BAND_USE_WHEEL_SAT_THRESHOLD = False
"""配色比率の彩度しきい値で色相環設定を使う既定値。"""
DEFAULT_COLOR_BAND_SAT_THRESHOLD = 0
"""配色比率集計で使う彩度しきい値既定値。"""
DEFAULT_COLOR_BAND_USE_WHEEL_HARMONY = True
"""配色比率の色彩調和で色相環設定を使う既定値。"""
DEFAULT_COLOR_BAND_HARMONY_GUIDE_ENABLED = False
"""配色比率の色彩調和表示の既定値。"""
DEFAULT_COLOR_BAND_HARMONY_GUIDE_TYPE = WHEEL_HARMONY_GUIDE_IDENTITY
"""配色比率の色彩調和タイプ既定値。"""
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
DEFAULT_VECTORSCOPE_WARN_THRESHOLD = 100
"""高彩度警告しきい値(%)既定値。"""
DEFAULT_ALWAYS_ON_TOP = False
"""常に最前面表示の既定値。"""
UI_THEME_LIGHT = "light"
"""ライトテーマ識別子。"""
UI_THEME_DARK = "dark"
"""ダークテーマ識別子。"""
UI_THEMES = (UI_THEME_LIGHT, UI_THEME_DARK)
"""利用可能なUIテーマ一覧。"""
UI_THEME_LABELS = {
    UI_THEME_LIGHT: "ライト",
    UI_THEME_DARK: "ダーク",
}
"""UIテーマの表示ラベル。"""
DEFAULT_UI_THEME = UI_THEME_LIGHT
"""UIテーマの既定値。"""

# Change-trigger defaults
DEFAULT_MODE = UPDATE_MODE_INTERVAL
DEFAULT_DIFF_THRESHOLD = 4.0
DEFAULT_STABLE_FRAMES = 3

# UI behavior defaults
VIEW_MIN_WIDTH = 48
"""ドック/ビューの共通最小幅(px)。"""
VIEW_MIN_HEIGHT = 48
"""ドック/ビューの共通最小高さ(px)。"""

# Debug logging
DEBUG_UI_LOG_ENABLED = False
"""UI デバッグログの既定有効状態。"""
DEBUG_UI_LOG_FILE = "ui_debug.log"
"""UI デバッグログの既定ファイル名。"""
DEBUG_UI_LOG_MAX_BYTES = 5 * 1024 * 1024
"""UI デバッグログ1ファイルあたりの最大サイズ。"""
DEBUG_UI_LOG_BACKUP_COUNT = 3
"""UI デバッグログの世代数。"""
DEBUG_UI_LOG_ENV = "CHROMA_MONITOR_DEBUG_UI_LOG"
"""UI デバッグログ有効化を上書きする環境変数名。"""
DEBUG_UI_LOG_PATH_ENV = "CHROMA_MONITOR_DEBUG_UI_LOG_PATH"
"""UI デバッグログ出力先を上書きする環境変数名。"""

# Backward-compatible aliases (legacy names)
DEBUG_WINDOW_LAYOUT_LOG_ENABLED = DEBUG_UI_LOG_ENABLED
"""互換用: UI デバッグログ有効状態。"""
DEBUG_WINDOW_LAYOUT_LOG_FILE = DEBUG_UI_LOG_FILE
"""互換用: UI デバッグログ既定ファイル名。"""
DEBUG_WINDOW_LAYOUT_LOG_MAX_BYTES = DEBUG_UI_LOG_MAX_BYTES
"""互換用: UI デバッグログ最大サイズ。"""
DEBUG_WINDOW_LAYOUT_LOG_BACKUP_COUNT = DEBUG_UI_LOG_BACKUP_COUNT
"""互換用: UI デバッグログ世代数。"""
DEBUG_WINDOW_LAYOUT_LOG_ENV = "CHROMA_MONITOR_DEBUG_WINDOW_LAYOUT_LOG"
"""互換用: 旧デバッグログ有効化環境変数名。"""
DEBUG_WINDOW_LAYOUT_LOG_PATH_ENV = "CHROMA_MONITOR_DEBUG_WINDOW_LAYOUT_LOG_PATH"
"""互換用: 旧デバッグログ出力先環境変数名。"""

# Settings page indices
SETTINGS_PAGE_CAPTURE = 0
SETTINGS_PAGE_LAYOUT = 9
SETTINGS_PAGE_THEME = 15

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
SQUINT_SCALE_PERCENT_MIN = 2
"""スクイント縮小率(%)の最小値。"""
SQUINT_SCALE_PERCENT_MAX = 100
"""スクイント縮小率(%)の最大値。"""
SQUINT_BLUR_SIGMA_MIN = 0.0
"""スクイントぼかしσの最小値。"""
SQUINT_BLUR_SIGMA_MAX = 30.0
"""スクイントぼかしσの最大値。"""

# Top-color display
TOP_COLORS_COUNT = 8
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
CFG_MIRROR_MODE = "mirror_mode"
CFG_WHEEL_SAT_THRESHOLD = "wheel_sat_threshold"
CFG_WHEEL_HARMONY_GUIDE_ENABLED = "wheel_harmony_guide_enabled"
CFG_WHEEL_HARMONY_GUIDE_TYPE = "wheel_harmony_guide_type"
CFG_WHEEL_HARMONY_GUIDE_ROTATION = "wheel_harmony_guide_rotation"
CFG_COLOR_BAND_USE_WHEEL_SAT_THRESHOLD = "color_band_use_wheel_sat_threshold"
CFG_COLOR_BAND_SAT_THRESHOLD = "color_band_sat_threshold"
CFG_COLOR_BAND_USE_WHEEL_HARMONY = "color_band_use_wheel_harmony"
CFG_COLOR_BAND_HARMONY_GUIDE_ENABLED = "color_band_harmony_guide_enabled"
CFG_COLOR_BAND_HARMONY_GUIDE_TYPE = "color_band_harmony_guide_type"
CFG_CAPTURE_SOURCE = "capture_source"
CFG_CAPTURE_WINDOW_TITLE = "capture_window_title"
CFG_CAPTURE_WINDOW_TEXT = "capture_window_text"
CFG_CAPTURE_WINDOW_ROI_REL = "capture_window_roi_rel"
CFG_CAPTURE_SCREEN_ROI_ABS = "capture_screen_roi_abs"
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
CFG_UI_THEME = "ui_theme"
CFG_ALWAYS_ON_TOP = "always_on_top"
CFG_MODE = "mode"
CFG_DIFF_THRESHOLD = "diff_threshold"
CFG_STABLE_FRAMES = "stable_frames"
CFG_LAYOUT_ENGINE_VERSION = "layout_engine_version"
CFG_LAYOUT_CURRENT = "layout_current"
CFG_LAYOUT_PRESETS = "layout_presets"
