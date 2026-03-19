"""設定ダイアログで共有するページ定義とレイアウト定数。"""

from ..util import constants as C

SETTINGS_PAGE_UPDATE = 1
SETTINGS_PAGE_WHEEL = 2
SETTINGS_PAGE_COLOR_BAND = 3
SETTINGS_PAGE_SCATTER = 4
SETTINGS_PAGE_VECTORSCOPE = 5
SETTINGS_PAGE_MIRROR = 6
SETTINGS_PAGE_EDGE = 7
SETTINGS_PAGE_BINARY = 8
SETTINGS_PAGE_TERNARY = 10
SETTINGS_PAGE_RGB_HIST = 11
SETTINGS_PAGE_FOCUS = 12
SETTINGS_PAGE_SQUINT = 13
SETTINGS_PAGE_SALIENCY = 14

SETTINGS_NAV_SPECS = (
    ("キャプチャ", C.SETTINGS_PAGE_CAPTURE),
    ("外観", C.SETTINGS_PAGE_THEME),
    ("更新", SETTINGS_PAGE_UPDATE),
    ("色相環", SETTINGS_PAGE_WHEEL),
    ("配色比率", SETTINGS_PAGE_COLOR_BAND),
    ("散布図", SETTINGS_PAGE_SCATTER),
    ("ベクトルスコープ", SETTINGS_PAGE_VECTORSCOPE),
    ("反転表示", SETTINGS_PAGE_MIRROR),
    ("エッジ検出", SETTINGS_PAGE_EDGE),
    ("2値化/3値化", SETTINGS_PAGE_BINARY),
    ("R/G/B ヒストグラム", SETTINGS_PAGE_RGB_HIST),
    ("フォーカスピーキング", SETTINGS_PAGE_FOCUS),
    ("スクイント表示", SETTINGS_PAGE_SQUINT),
    ("サリエンシーマップ", SETTINGS_PAGE_SALIENCY),
    ("レイアウト", C.SETTINGS_PAGE_LAYOUT),
)

SETTINGS_LABEL_TEXTS = (
    "取得元",
    "テーマ",
    "ターゲット",
    "解析解像度",
    "指定サイズ",
    "更新モード",
    "更新間隔",
    "差分閾値",
    "安定フレーム",
    "表示形状",
    "表示モード",
    "サンプル数",
    "表示方式",
    "反転方向",
    "彩度しきい値",
    "色彩調和タイプ",
    "エッジ感度",
    "2値化",
    "3値化",
    "重ね具合",
    "構図ガイド",
    "感度",
    "色",
    "線幅",
    "モード",
    "縮小率",
    "ぼかし",
    "高彩度しきい値",
    "プリセット",
    "新規名",
)

SETTINGS_LABEL_MIN_WIDTH = 88
SETTINGS_LABEL_MAX_WIDTH = 108
SETTINGS_LABEL_PAD_PX = 4
SETTINGS_FIELD_GAP_PX = 4
SETTINGS_FIELD_SLOT_WIDTH = 460
SETTINGS_NAV_ROW_HEIGHT = 22
