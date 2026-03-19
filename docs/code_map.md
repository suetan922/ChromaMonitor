## Code Map

### Folder Roles

- `chroma_monitor/analysis`
  ライブ解析で使う純粋計算寄りのロジックとワーカー補助。
  `change_detection.py` は change/stable 判定で使う純粋計算。
  `frame_analysis.py` は画像解析の入口と facade。
  `top_color_bars.py` は配色比率の代表色集計。
  `scatter_sampling.py` は散布図サンプル抽出。
  `screen_mapping.py` は Qt 論理座標と実画面座標の変換。
  `live_graph_data.py` は graph/result 組み立て。
  `result_payloads.py` は解析結果 payload 契約。

- `chroma_monitor/capture`
  OS 依存のキャプチャ取得。
  `win32_windows.py` はウィンドウ列挙と Win32 取得補助。
  `win32_window_capture.py` は PrintWindow ベースの低レベル取得。
  `frame_capture.py` は ROI 付きフレーム切り出しと画面領域キャプチャ。

- `chroma_monitor/ui`
  Qt UI 構築とダイアログ。
  `settings_dialog.py` は設定ウィンドウの facade。
  `settings_dialog_layout.py` は設定行レイアウトの共通部品。
  `settings_dialog_pages.py` は各設定ページの組み立て入口。
  `settings_dialog_page_sections.py` は各設定ページ断片の builder。
  `settings_dialog_specs.py` はページ番号とナビ定義。
  `view_docks.py` は各ビューのドック構成の facade。
  `view_docks_common.py` はドック共通部品と登録/共通設定。
  `view_docks_builders.py` は各ビュー/ドックの生成。
  `view_docks_layout.py` は placeholder と初期配置。

- `chroma_monitor/ui/main_window`
  MainWindow の補助モジュール群。
  `control_widgets.py` は control 群の facade。
  `control_widget_common.py` は共通入力 widget helper。
  `control_widget_sections.py` は capture / view / processing / layout ごとの control 生成。
  `control_signals.py` は control 群の signal 配線。
  `window_shell.py` はメニュー、ツールバー、プレビュー/ドック初期化。
  `window_events.py` は Qt event/eventFilter と dock event 補助。
  `window_tabs.py` はタブ関連の facade。
  `window_tab_sync.py` はタブ close/sync とタイトルバー同期。
  `window_tab_drag.py` はタブ drag/detach。
  `window_layout.py` は facade。実体は `window_layout_*` へ分割済み。
  `settings_logic.py` は facade。実体は `settings_apply.py` / `settings_persistence.py`。
  `settings_values.py` は facade。実体は `settings_value_common.py` / `settings_selected_values.py` / `settings_payload.py`。
  `runtime_actions.py` は facade。実体は `runtime_capture.py` / `runtime_image_analysis.py` / `runtime_layout_pause.py` / `runtime_preview.py`。
  `result_color_band.py` は UI 更新側。
  `result_color_band_palette.py` は配色候補・色変換・整形。
  `result_color_band_widgets.py` は配色詳細カードとコピー menu の小物 UI。

- `chroma_monitor/views`
  各可視化 QWidget。
  `color_scatter.py` は Widget/paintEvent 側。
  `color_scatter_constants.py` はマンセル色表と色相環/散布図の共有定数。
  `color_scatter_math.py` は座標変換・色相フィルタ・散布図ラスタ生成。

- `chroma_monitor/util`
  再利用される共通部品。
  `config.py` は設定保存先の解決と JSON 保存。
  `constants.py` は設定キー互換と既定値の基準。
  `theme.py` は facade。
  `theme_definitions.py` はテーマ定義。
  `theme_stylesheet.py` は stylesheet 生成。

### Main Entry Points

- `chroma_monitor/main_window.py`
  アプリのハブ。初期化、補助モジュール呼び出し、イベント集約を担当。

- `chroma_monitor/analyzer.py`
  ライブ解析ワーカー本体。
  スレッド制御とキャプチャループはここに残し、座標変換/graph 組み立て/change 計算/capture helper は分離。

### Read Paths

- レイアウトやドック挙動を追う
  `main_window.py` -> `ui/main_window/window_layout.py` -> `window_layout_*`

- 設定の保存/適用を追う
  `main_window.py` -> `ui/main_window/settings_logic.py`
  UI反映は `settings_apply.py`
  保存/復元は `settings_persistence.py`
  値正規化 facade は `settings_values.py`
  共通 helper は `settings_value_common.py`
  selected 値取得は `settings_selected_values.py`
  payload 組み立ては `settings_payload.py`

- 設定ダイアログの表示を追う
  `main_window.py` -> `ui/settings_dialog.py`
  行レイアウトは `settings_dialog_layout.py`
  各ページ構築入口は `settings_dialog_pages.py`
  ページ断片は `settings_dialog_page_sections.py`

- 実行時アクションを追う
  `main_window.py` -> `ui/main_window/runtime_actions.py`
  取得元切替は `runtime_capture.py`
  画像解析と終了処理は `runtime_image_analysis.py`
  一時停止と worker 可視フラグは `runtime_layout_pause.py`
  プレビュー更新は `runtime_preview.py`

- 配色比率ドックを追う
  `result_snapshot.py` -> `result_color_band.py`
  配色ロジックは `result_color_band_palette.py`
  小物 UI は `result_color_band_widgets.py`

- control 群の生成と配線を追う
  `main_window.py` -> `ui/main_window/control_widgets.py`
  共通 helper は `control_widget_common.py`
  セクション別生成は `control_widget_sections.py`
  signal 配線は `control_signals.py`

- メニュー/ツールバー/イベント入口を追う
  `main_window.py` -> `ui/main_window/window_shell.py`
  Qt event と dock event は `window_events.py`

- ドックタブの挙動を追う
  `window_events.py` -> `ui/main_window/window_tabs.py`
  close/sync は `window_tab_sync.py`
  drag/detach は `window_tab_drag.py`

- ビュー用ドックの構築を追う
  `window_shell.py` -> `ui/view_docks.py`
  各ドック生成は `view_docks_builders.py`
  初期配置は `view_docks_layout.py`

- 色相環/散布図を追う
  `views/color_scatter.py` -> `views/color_scatter_constants.py`
  数値変換とラスタ生成は `views/color_scatter_math.py`

- ROI と画面座標変換を追う
  `analyzer.py` -> `analysis/screen_mapping.py`

- ライブキャプチャと差分判定を追う
  `analyzer.py` -> `capture/frame_capture.py`
  Win32 低レベル取得は `capture/win32_window_capture.py`
  change/stable 計算は `analysis/change_detection.py`
  グラフ計算共通 helper は `analysis/live_graph_data.py`
  解析結果契約は `analysis/result_payloads.py`
  配色比率集計は `analysis/top_color_bars.py`
  散布図サンプル抽出は `analysis/scatter_sampling.py`

### Runtime Artifacts

- `config/` はポータブル運用のための実行時生成ディレクトリ。
  `settings.json` やデバッグログはソース管理対象に混ぜない前提。

- `__pycache__/`, `*.log`, `*.zip` は生成物として扱う。

### Current Refactor Notes

- 既存 import パスは極力維持し、`window_layout.py` / `settings_logic.py` / `runtime_actions.py` / `settings_dialog.py` は facade 化で互換を保っている。
- UI 文言と設定キー互換は変更していない。
- `main_window.py` は control 生成・signal 配線・イベント入口・shell UI 構築を `ui/main_window/` へ寄せ、ハブ寄りに整理している。
