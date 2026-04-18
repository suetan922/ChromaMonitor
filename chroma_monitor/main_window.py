from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QNetworkAccessManager
from PySide6.QtWidgets import QMainWindow

from .analyzer import AnalyzerWorker
from .capture.win32_windows import HAS_WIN32
from .ui import layout_presets as mw_layout_presets
from .ui.main_window import control_signals as mw_controls_signals
from .ui.main_window import control_widgets as mw_controls
from .ui.main_window import help_actions as mw_help
from .ui.main_window import result_color_band as mw_color_band
from .ui.main_window import result_snapshot as mw_snapshot
from .ui.main_window import roi_handlers as mw_roi
from .ui.main_window import runtime_actions as mw_runtime
from .ui.main_window import settings_logic as mw_settings
from .ui.main_window import tools_actions as mw_tools
from .ui.main_window import window_events as mw_window_events
from .ui.main_window import window_layout as mw_windowing
from .ui.main_window import window_shell as mw_window_shell
from .ui.main_window import window_tabs as mw_tabs
from .ui.main_window import window_topmost as mw_topmost
from .ui.settings_dialog import hide_settings_window as hide_settings_dialog_window
from .ui.settings_dialog import show_settings_window as show_settings_dialog_window
from .util import constants as C
from .util.debug_log import is_window_layout_debug_enabled
_DEFAULT_PREVIEW_WINDOW = False
_SETTINGS_SAVE_DEBOUNCE_MS = 220
_DOCK_REBALANCE_DEBOUNCE_MS = 36
_LAYOUT_INTERACTION_RESUME_DEBOUNCE_MS = 220
_FOCUS_PEAK_THICKNESS_STEP = 0.1
_SQUINT_BLUR_SIGMA_STEP = 0.1


def _build_control_widgets_with_defaults(main_window) -> None:
    """既定パラメータで control widget 群を構築する。"""
    mw_controls.build_control_widgets(
        main_window,
        default_preview_window=_DEFAULT_PREVIEW_WINDOW,
        focus_peak_thickness_step=_FOCUS_PEAK_THICKNESS_STEP,
        squint_blur_sigma_step=_SQUINT_BLUR_SIGMA_STEP,
    )


def _build_menu_bar_with_defaults(main_window) -> None:
    """既定のドックメニュー定義でメニューバーを構築する。"""
    mw_window_shell.build_menu_bar(
        main_window,
        window_dock_menu_items=mw_window_shell.WINDOW_DOCK_MENU_ITEMS,
    )


class _MainWindowFacades:
    """MainWindow が委譲する補助モジュール群の名前空間。

    責務一覧:
    - help: リリース確認とヘルプ操作
    - controls/control_signals: 入力UIの生成と signal 配線
    - shell/events/tabs/windowing/topmost: メインウィンドウ外殻とドック挙動
    - runtime: 実行時 capture / preview / start-stop / 画像解析
    - settings: 設定適用と保存復元
    - color_band/snapshot/roi/layout_presets: 補助UI、結果復元、領域選択、レイアウト
    """

    # Help / release checks
    help = mw_help
    # Control widgets / signal wiring
    controls = mw_controls
    control_signals = mw_controls_signals
    # Result rendering / ROI / runtime actions
    color_band = mw_color_band
    snapshot = mw_snapshot
    roi = mw_roi
    runtime = mw_runtime
    tools = mw_tools
    # Settings / event entry points / shell
    settings = mw_settings
    events = mw_window_events
    windowing = mw_windowing
    shell = mw_window_shell
    tabs = mw_tabs
    topmost = mw_topmost
    # Layout preset persistence
    layout_presets = mw_layout_presets


_MW = _MainWindowFacades()


class MainWindow(QMainWindow):
    """メインUIと解析ワーカー連携を統括するアプリ主画面。"""

    def __init__(self):
        """ウィンドウ状態・各種UI・シグナル接続を順に初期化する。"""
        super().__init__()
        self._init_window_runtime_state()
        self._init_analyzer_workers()

        self._build_control_widgets()
        self._connect_control_signals()

        self._build_menu_bar()
        self._build_toolbar()
        self._setup_preview_and_docks()

        # --- Styling (theme) ---
        self._apply_ui_style()

        # --- Init ---
        self._initialize_runtime_defaults()

    def _init_window_runtime_state(self) -> None:
        """ランタイム管理用フラグ・タイマー・ネットワーク状態を初期化する。"""
        title = C.APP_NAME
        if is_window_layout_debug_enabled():
            title = f"{title} [DEBUG]"
        self.setWindowTitle(title)
        self._base_window_title = title
        self._loaded_file_title_name = ""
        self.resize(1120, 700)
        self._did_initial_screen_fit = False
        self._layout_autosave_enabled = False
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(600)
        self._layout_save_timer.timeout.connect(
            lambda: self.save_current_layout_to_config(silent=True)
        )
        self._fit_window_timer = QTimer(self)
        self._fit_window_timer.setSingleShot(True)
        self._fit_window_timer.setInterval(80)
        self._fit_window_timer.timeout.connect(self._fit_window_to_desktop)
        self._dock_rebalance_timer = QTimer(self)
        self._dock_rebalance_timer.setSingleShot(True)
        self._dock_rebalance_timer.setInterval(_DOCK_REBALANCE_DEBOUNCE_MS)
        self._dock_rebalance_timer.timeout.connect(self._rebalance_dock_layout)
        self._dock_rebalance_running = False
        self._dockability_sync_timer = None
        self._dock_geometry_snapshot = {}
        self._dock_rebalance_last_main_size = self.size()
        self._layout_interaction_pause_active = False
        self._layout_interaction_pause_reasons = set()
        self._layout_interaction_resume_timer = QTimer(self)
        self._layout_interaction_resume_timer.setSingleShot(True)
        self._layout_interaction_resume_timer.setInterval(_LAYOUT_INTERACTION_RESUME_DEBOUNCE_MS)
        self._layout_interaction_resume_timer.timeout.connect(self._end_layout_interaction_pause)
        self._settings_save_timer = QTimer(self)
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(_SETTINGS_SAVE_DEBOUNCE_MS)
        self._settings_save_timer.timeout.connect(self._flush_settings_save)
        self._settings_save_pending = False
        self._settings_load_in_progress = False
        self._startup_finished = False
        # 同一画面構成時は起動直後の位置補正を抑止する。
        self._startup_should_fit_window = True
        self._release_page_url = C.APP_RELEASES_URL
        self._update_check_started = False
        self._update_reply = None
        self._update_network = QNetworkAccessManager(self)
        self._update_network.finished.connect(self._on_release_check_finished)
        self._ui_theme_name = C.DEFAULT_UI_THEME
        self._ui_theme = None
        # ROI選択オーバーレイ（マルチモニタ対応）管理。
        self._roi_selectors = []
        self._canvas_preview_window = None
        self._loaded_image_source_path = ""
        self._loaded_image_source_name = ""
        self._loaded_image_source_bgr = None
        self._pending_loaded_image_source_path = ""
        self._pending_loaded_image_source_name = ""
        self._pending_loaded_image_source_bgr = None

    def _init_analyzer_workers(self) -> None:
        """ライブ解析と画像解析のワーカー参照を初期化する。"""
        # キャプチャ解析ワーカー（ライブ）と画像解析ワーカー（単発）を分離して保持。
        self.worker = AnalyzerWorker()
        self.worker.resultReady.connect(self.on_result)
        self.worker.status.connect(self.on_status)
        self._image_thread = None
        self._image_worker = None
        self._image_progress = None

    def _initialize_runtime_defaults(self) -> None:
        """起動直後のワーカー既定値をUI設定から反映する。"""
        self.worker.set_interval(self.spin_interval.value())
        self.worker.set_sample_points(self.spin_points.value())
        self.apply_analysis_resolution_settings(save=False)
        self.worker.set_wheel_sat_threshold(self.spin_wheel_sat_threshold.value())
        self.worker.set_graph_every(C.DEFAULT_GRAPH_EVERY)
        # 初回表示前に設定/レイアウトを反映して、表示後の位置ジャンプを避ける。
        self._finish_startup()

    def _finish_startup(self):
        """設定ロード後の初期描画同期と自動処理開始を行う。"""
        if self._startup_finished:
            return
        self._startup_finished = True
        self.load_settings()
        if (
            HAS_WIN32
            and self._selected_capture_source() == C.CAPTURE_SOURCE_WINDOW
            and self.combo_win.count() <= 1
        ):
            self.refresh_windows()
        for dock in self._dock_map.values():
            self._on_dock_top_level_changed(dock, dock.isFloating())
        self._sync_tabbed_dock_title_bars()
        self.sync_window_menu_checks()
        self.update_placeholder()
        self._schedule_dock_rebalance()
        self._layout_autosave_enabled = True
        self._schedule_layout_autosave()
        self._start_release_check_once()
        # 構成差分時のみ、起動直後に最終補正する。
        if bool(self._startup_should_fit_window):
            QTimer.singleShot(260, self._fit_window_to_desktop)

    # Help / release delegates
    _setup_help_menu = _MW.help.setup_help_menu
    _start_release_check_once = _MW.help.start_release_check_once
    _check_latest_release = _MW.help.check_latest_release
    _on_release_check_finished = _MW.help.on_release_check_finished
    _open_release_page = _MW.help.open_release_page

    # Control construction delegates
    # Read: ui/main_window/control_widgets.py, control_widget_sections.py, control_signals.py
    _build_control_widgets = _build_control_widgets_with_defaults
    _connect_control_signals = _MW.control_signals.connect_control_signals
    _connect_capture_control_signals = _MW.control_signals.connect_capture_control_signals
    _connect_analysis_control_signals = _MW.control_signals.connect_analysis_control_signals
    _connect_layout_preset_signals = _MW.control_signals.connect_layout_preset_signals

    # Window shell / Qt event delegates
    # Read: ui/main_window/window_shell.py, window_events.py
    _build_menu_bar = _build_menu_bar_with_defaults
    _ensure_menu_popup_width = _MW.shell.ensure_menu_popup_width
    _build_toolbar = _MW.shell.build_toolbar
    _setup_preview_and_docks = _MW.shell.setup_preview_and_docks
    _on_tabified_dock_activated = _MW.shell.on_tabified_dock_activated
    showEvent = _MW.events.show_event
    event = _MW.events.window_event
    keyPressEvent = _MW.events.key_press_event
    _handle_top_colors_bar_resize_event = _MW.events.handle_top_colors_bar_resize_event
    _handle_color_band_layout_event = _MW.events.handle_color_band_layout_event
    _handle_floating_state_dock_event = _MW.events.handle_floating_state_dock_event
    _maybe_restore_dock_snapshot_after_event = _MW.events.maybe_restore_dock_snapshot_after_event
    _handle_dock_layout_event = _MW.events.handle_dock_layout_event
    _is_managed_dock = _MW.events.is_managed_dock
    eventFilter = _MW.events.event_filter
    moveEvent = _MW.events.move_event
    resizeEvent = _MW.events.resize_event

    def _request_save_settings(self):
        """設定保存をデバウンス付きで予約する。"""
        if self._settings_load_in_progress:
            return
        self._settings_save_pending = True
        self._settings_save_timer.start()

    def _flush_settings_save(self):
        """保留中の設定保存を実行する。"""
        if not self._settings_save_pending:
            return
        self._settings_save_pending = False
        self.save_settings()

    # Window layout / dock / topmost delegates
    # Read: ui/main_window/window_layout.py, window_tabs.py, window_topmost.py
    _fit_window_to_desktop = _MW.windowing.fit_window_to_desktop
    _fit_dialog_to_desktop = _MW.windowing.fit_dialog_to_desktop
    _schedule_window_fit = _MW.windowing.schedule_window_fit
    _is_always_on_top_enabled = _MW.topmost.is_always_on_top_enabled
    _schedule_dock_rebalance = _MW.windowing.schedule_dock_rebalance
    _rebalance_dock_layout = _MW.windowing.rebalance_dock_layout
    _on_dock_top_level_changed = _MW.windowing.on_dock_top_level_changed
    _update_floating_dock_dockability = _MW.windowing.update_floating_dock_dockability
    _sync_all_floating_dock_dockability = _MW.windowing.sync_all_floating_dock_dockability
    _schedule_floating_dock_dockability_sync = _MW.windowing.schedule_floating_dock_dockability_sync
    _notify_floating_dock_moved = _MW.windowing.notify_floating_dock_moved
    _track_floating_dock_size = _MW.windowing.track_floating_dock_size

    def _sync_tabbed_dock_title_bars(self, *_):
        """タブ化状態に応じてドックのタイトルバー表示を同期する。"""
        _MW.tabs.sync_tabbed_dock_title_bars(self)

    # Topmost / dialog presentation delegates
    # Read: ui/main_window/window_topmost.py
    apply_always_on_top = _MW.topmost.apply_always_on_top
    _refresh_topmost_if_enabled = _MW.topmost.refresh_topmost_if_enabled
    _present_settings_window = _MW.topmost.present_settings_window

    # Tools delegates
    show_canvas_preview_window = _MW.tools.show_canvas_preview_window
    _close_canvas_preview_window = _MW.tools.close_canvas_preview_window

    # Result snapshot / runtime delegates
    # Read: ui/main_window/result_snapshot.py, runtime_actions.py, runtime_*.py
    _refresh_top_color_bar = _MW.color_band.refresh_top_color_bar
    _on_color_chip_selected = _MW.color_band.on_color_chip_selected
    _update_color_band_compact_visibility = _MW.color_band.update_color_band_compact_visibility
    _restore_dock_from_snapshot = _MW.snapshot.restore_dock_from_snapshot
    on_status = _MW.runtime.on_status
    _cancel_image_analysis = _MW.runtime.cancel_image_analysis
    can_accept_image_drop_target = _MW.runtime.can_accept_image_drop_target
    is_supported_image_path = _MW.runtime.is_supported_image_path
    _setup_image_input_drop_targets = _MW.runtime.setup_image_input_drop_targets
    on_image_files_dropped = _MW.runtime.on_image_files_dropped
    on_load_image = _MW.runtime.on_load_image
    on_load_image_from_clipboard = _MW.runtime.on_load_image_from_clipboard
    on_image_analysis_progress = _MW.runtime.on_image_analysis_progress
    on_image_analysis_finished = _MW.runtime.on_image_analysis_finished
    on_image_analysis_failed = _MW.runtime.on_image_analysis_failed
    on_image_analysis_canceled = _MW.runtime.on_image_analysis_canceled
    on_start = _MW.runtime.on_start
    on_stop = _MW.runtime.on_stop
    closeEvent = _MW.runtime.close_event
    refresh_windows = _MW.runtime.refresh_windows
    _selected_capture_source = _MW.runtime.selected_capture_source
    _sync_capture_source_ui = _MW.runtime.sync_capture_source_ui
    apply_capture_source = _MW.runtime.apply_capture_source
    on_window_changed = _MW.runtime.on_window_changed
    on_window_text_changed = _MW.runtime.on_window_text_changed
    on_window_index_activated = _MW.runtime.on_window_index_activated
    on_window_text_activated = _MW.runtime.on_window_text_activated
    on_window_popup_row_selected = _MW.runtime.on_window_popup_row_selected
    on_window_text_edited = _MW.runtime.on_window_text_edited
    on_window_text_committed = _MW.runtime.on_window_text_committed
    _sync_worker_view_flags = _MW.runtime.sync_worker_view_flags
    _begin_layout_interaction_pause = _MW.runtime.begin_layout_interaction_pause
    _schedule_layout_interaction_resume = _MW.runtime.schedule_layout_interaction_resume
    _end_layout_interaction_pause = _MW.runtime.end_layout_interaction_pause
    _update_preview_snapshot = _MW.runtime.update_preview_snapshot
    on_preview_toggled = _MW.runtime.on_preview_toggled
    on_preview_closed = _MW.runtime.on_preview_closed

    # Settings apply / persistence delegates
    # Read: ui/main_window/settings_logic.py and its split modules
    _selected_wheel_sat_threshold = _MW.settings.selected_wheel_sat_threshold
    _on_wheel_harmony_rotation_changed = _MW.settings.on_wheel_harmony_rotation_changed
    _apply_ui_style = _MW.windowing.apply_ui_style
    _sync_mode_dependent_rows = _MW.settings.sync_mode_dependent_rows
    _sync_squint_mode_rows = _MW.settings.sync_squint_mode_rows
    _sync_analysis_resolution_rows = _MW.settings.sync_analysis_resolution_rows
    _sync_color_band_controls = _MW.settings.sync_color_band_controls
    apply_sample_points_settings = _MW.settings.apply_sample_points_settings
    apply_theme_settings = _MW.settings.apply_theme_settings
    _sync_scatter_filter_controls = _MW.settings.sync_scatter_filter_controls
    apply_scatter_settings = _MW.settings.apply_scatter_settings
    apply_analysis_resolution_settings = _MW.settings.apply_analysis_resolution_settings
    apply_wheel_settings = _MW.settings.apply_wheel_settings
    apply_color_band_settings = _MW.settings.apply_color_band_settings
    apply_rgb_hist_settings = _MW.settings.apply_rgb_hist_settings
    apply_mirror_settings = _MW.settings.apply_mirror_settings
    apply_edge_settings = _MW.settings.apply_edge_settings
    apply_binary_settings = _MW.settings.apply_binary_settings
    apply_ternary_settings = _MW.settings.apply_ternary_settings
    apply_saliency_settings = _MW.settings.apply_saliency_settings
    apply_composition_guide_settings = _MW.settings.apply_composition_guide_settings
    apply_focus_peaking_settings = _MW.settings.apply_focus_peaking_settings
    apply_squint_settings = _MW.settings.apply_squint_settings
    _update_vectorscope_warning_label = _MW.settings.update_vectorscope_warning_label
    apply_vectorscope_settings = _MW.settings.apply_vectorscope_settings
    apply_mode_settings = _MW.settings.apply_mode_settings
    load_settings = _MW.settings.load_settings
    save_settings = _MW.settings.save_settings

    # Layout preset / dock visibility delegates
    # Read: ui/layout_presets.py, ui/main_window/window_layout.py
    sync_window_menu_checks = _MW.windowing.sync_window_menu_checks
    _apply_default_view_layout = _MW.layout_presets.apply_default_view_layout
    save_current_layout_to_config = _MW.layout_presets.save_current_layout_to_config
    _schedule_layout_autosave = _MW.layout_presets.schedule_layout_autosave
    apply_layout_from_config = _MW.layout_presets.apply_layout_from_config
    refresh_layout_preset_views = _MW.layout_presets.refresh_layout_preset_views
    apply_layout_preset = _MW.layout_presets.apply_layout_preset
    load_selected_layout_preset = _MW.layout_presets.load_selected_layout_preset
    save_layout_preset = _MW.layout_presets.save_layout_preset
    delete_selected_layout_preset = _MW.layout_presets.delete_selected_layout_preset
    toggle_dock = _MW.windowing.toggle_dock
    update_placeholder = _MW.windowing.update_placeholder

    # Settings dialog / ROI / result dispatch delegates
    # Read: ui/settings_dialog.py, ui/main_window/roi_handlers.py, result_snapshot.py
    show_settings_window = show_settings_dialog_window
    hide_settings_window = hide_settings_dialog_window
    _close_roi_selectors = _MW.roi.close_roi_selectors
    _cancel_roi_selection = _MW.roi.cancel_roi_selection
    pick_roi_on_screen = _MW.roi.pick_roi_on_screen
    on_roi_screen_selected = _MW.roi.on_roi_screen_selected
    pick_roi_in_window = _MW.roi.pick_roi_in_window
    on_roi_window_selected = _MW.roi.on_roi_window_selected
    on_result = _MW.snapshot.on_result
