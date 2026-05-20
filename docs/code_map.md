## Code Map

### Folder Roles

- `chroma_monitor/analysis`
  ライブ解析で使う純粋ロジックとワーカー補助。`change_detection.py` は change/stable 判定、`frame_analysis.py` は解析入口の facade、`top_color_bars.py` は上位色抽出、`scatter_sampling.py` は scatter 用サンプル、`screen_mapping.py` は座標変換、`live_graph_data.py` は graph/result 補助、`result_payloads.py` は payload 契約。
- `chroma_monitor/capture`
  OS キャプチャ層。`win32_windows.py` は対象ウィンドウ列挙、`win32_window_capture.py` は PrintWindow ベースの低レベル capture、`frame_capture.py` は ROI 切り出しと画面キャプチャの入口。
- `chroma_monitor/ui`
  Qt UI 構築とダイアログ。`settings_dialog.py` は設定ダイアログの facade、`settings_dialog_layout.py` は共通レイアウト、`settings_dialog_pages.py` はページ入口、`settings_dialog_page_sections.py` はページ断片 builder、`settings_dialog_specs.py` はナビ仕様。`view_docks.py` は現行 runtime における各ビューの dock 構築 source of truth。
- `chroma_monitor/ui/main_window`
  MainWindow の補助モジュール群。`control_widgets.py` は control 群の facade、`control_widget_common.py` は共通入力 helper、`control_widget_sections.py` は capture / view / processing / layout ごとの control 生成、`control_signals.py` は signal 配線。`window_layout.py` は現行 runtime におけるレイアウト処理の source of truth、`window_tabs.py` は現行 runtime におけるタブ関連処理の source of truth。`settings_logic.py`、`settings_values.py`、`runtime_actions.py` はそれぞれ facade として保ち、配下 helper へ委譲する。
- `chroma_monitor/views`
  各描画 QWidget。`color_scatter.py` は Widget/paintEvent 本体、`color_scatter_constants.py` は色表・定数、`color_scatter_math.py` は座標変換とサンプル補助。`canvas_preview.py` と `canvas_preview_math.py` は canvas preview の描画と座標系を担当する。
- `chroma_monitor/util`
  汎用 helper。`config.py` は JSON 設定保存、`constants.py` は設定キー互換と既定値、`theme.py` は facade、`theme_definitions.py` はテーマ定義、`theme_stylesheet.py` は stylesheet 生成。

### Main Entry Points

- `chroma_monitor/main_window.py`
  アプリのハブ。主要 widget の生成、control 配線、dock/view 初期化、runtime helper の委譲を行う。
- `chroma_monitor/analyzer.py`
  ライブ解析ワーカー本体。画面取得、解析、graph/result 更新、change 判定をまとめる。

### Read Paths

- レイアウトや dock 構築を追う:
  `main_window.py` -> `ui/main_window/window_layout.py`

- dock tab の挙動を追う:
  `main_window.py` -> `ui/main_window/window_tabs.py`

- ビュー用 dock の構築を追う:
  `main_window.py` -> `ui/view_docks.py`

- 設定の適用と保存を追う:
  `main_window.py` -> `ui/main_window/settings_logic.py`
  UI 反映は `settings_apply.py`
  保存/復元は `settings_persistence.py`
  値解決 facade は `settings_values.py`
  共通 helper は `settings_value_common.py`
  selected 値は `settings_selected_values.py`
  payload 組み立ては `settings_payload.py`

- 設定ダイアログを追う:
  `main_window.py` -> `ui/settings_dialog.py`
  レイアウトは `settings_dialog_layout.py`
  ページ入口は `settings_dialog_pages.py`
  ページ断片は `settings_dialog_page_sections.py`

- runtime action を追う:
  `main_window.py` -> `ui/main_window/runtime_actions.py`
  capture 系は `runtime_capture.py`
  画像解析と source 管理は `runtime_image_analysis.py`
  一時停止や worker 協調は `runtime_layout_pause.py`
  preview 表示は `runtime_preview.py`

- result color band を追う:
  `result_snapshot.py` -> `result_color_band.py`
  palette は `result_color_band_palette.py`
  menu/card UI は `result_color_band_widgets.py`

- control 生成と signal 配線を追う:
  `main_window.py` -> `ui/main_window/control_widgets.py`
  共通 helper は `control_widget_common.py`
  section 生成は `control_widget_sections.py`
  signal 配線は `control_signals.py`

- color scatter を追う:
  `views/color_scatter.py` -> `views/color_scatter_constants.py`
  数学処理とサンプル補助は `views/color_scatter_math.py`

- ROI と画面座標変換を追う:
  `analyzer.py` -> `analysis/screen_mapping.py`

- ライブ capture と change 判定を追う:
  `analyzer.py` -> `capture/frame_capture.py`
  Win32 低レベル capture は `capture/win32_window_capture.py`
  change/stable 判定は `analysis/change_detection.py`
  graph helper は `analysis/live_graph_data.py`
  payload 契約は `analysis/result_payloads.py`
  上位色抽出は `analysis/top_color_bars.py`
  scatter sampling は `analysis/scatter_sampling.py`

### Runtime Artifacts

- `config/` はポータブル運用向けの runtime 生成ディレクトリ。`settings.json` や debug log はソース管理対象にしない。
- `__pycache__/`, `*.log`, `*.zip` は生成物として扱う。

### Current Refactor Notes

- 既存 import パスは互換維持を優先し、`window_layout.py` / `settings_logic.py` / `runtime_actions.py` / `settings_dialog.py` は facade として読む。
- UI 文言と設定キー形式は不用意に変えない。
- `main_window.py` から分割された helper は、現行 runtime につながっている経路を先に確認してから触る。
