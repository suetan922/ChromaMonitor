"""実行時アクションの補助処理。"""

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QProgressDialog

from ...analysis.image_file_worker import ImageFileAnalyzeWorker
from ...capture.win32_windows import HAS_WIN32, list_windows
from ...util import constants as C
from ...util.qt_helpers import (
    blocked_signals,
    is_widget_renderable,
    set_checked_blocked,
    set_current_index_blocked,
    set_enabled_if,
    set_visible_if_changed,
)
from ...util.value_utils import safe_choice
from .settings_logic import selected_effective_color_band_sat_threshold

_WINDOW_LIST_MAX_ITEMS = 500
_WORKER_VIEW_FLAGS_DISABLED = {
    "color": False,
    "color_band": False,
    "scatter": False,
    "hsv_hist": False,
    "image": False,
    "preview": False,
}


def _safe_call(func, *args, **kwargs) -> bool:
    """例外を握りつぶして関数を呼び、成功可否を返す。"""
    try:
        # 後始末での例外伝播を防ぐ。
        func(*args, **kwargs)
        return True
    except Exception:
        return False


def _safe_is_visible(widget) -> bool:
    """isVisible を安全に評価する。"""
    if widget is None:
        return False
    try:
        return bool(widget.isVisible())
    except Exception:
        return False


def _find_combo_index_by_data(combo, data) -> int:
    """コンボボックス内で data が一致する最初のインデックスを返す。"""
    if data is None:
        return -1
    for idx in range(combo.count()):
        if combo.itemData(idx) == data:
            return int(idx)
    return -1


def _find_combo_index_by_text_casefold(combo, text: str) -> int:
    """コンボボックス内で大文字小文字を無視して text を検索する。"""
    needle = str(text).casefold()
    if not needle:
        return -1
    for idx in range(combo.count()):
        if combo.itemText(idx).casefold() == needle:
            return int(idx)
    return -1


def _preserved_window_editor_text(combo, editor) -> str:
    """ウィンドウ一覧更新前に保持すべき編集テキストを返す。"""
    if editor is None:
        return ""
    if editor.hasFocus() or combo.hasFocus():
        return str(editor.text())
    return ""


def _rebuild_window_combo_items(combo, wins: list[tuple[int, str]]) -> None:
    """ウィンドウ候補一覧でコンボ項目を再構築する。"""
    combo.clear()
    for hwnd, title in wins[:_WINDOW_LIST_MAX_ITEMS]:
        combo.addItem(title, hwnd)


def _restore_window_combo_selection(combo, editor, *, prev_hwnd, preserved_text: str) -> int:
    """更新後コンボへ選択状態と編集テキストを復元し、選択インデックスを返す。"""
    selected_idx = _find_combo_index_by_data(combo, prev_hwnd)
    combo.setCurrentIndex(int(selected_idx))
    if editor is not None:
        if preserved_text:
            combo.setEditText(preserved_text)
        elif selected_idx < 0:
            combo.clearEditText()
    return int(selected_idx)


def _clear_window_selection(main_window, combo, editor, *, text_to_keep: str | None = None) -> None:
    """現在のウィンドウ選択を解除し、必要に応じて入力文字列を維持する。"""
    set_current_index_blocked(combo, -1)
    if editor is not None:
        if text_to_keep is None:
            combo.clearEditText()
        else:
            editor.setText(str(text_to_keep))
    on_window_changed(main_window, -1)


def _set_worker_view_flags_if_changed(
    main_window,
    *,
    color: bool,
    color_band: bool,
    scatter: bool,
    hsv_hist: bool,
    image: bool,
    preview: bool,
) -> None:
    """ビュー可視状態が変わったときだけ worker の解析フラグを更新する。"""
    state = (
        bool(color),
        bool(color_band),
        bool(scatter),
        bool(hsv_hist),
        bool(image),
        bool(preview),
    )
    if state == getattr(main_window, "_worker_view_flags_state", None):
        return
    main_window._worker_view_flags_state = state
    main_window.worker.set_view_flags(
        color=state[0],
        color_band=state[1],
        scatter=state[2],
        hsv_hist=state[3],
        image=state[4],
        preview=state[5],
    )


def _safe_close_widget(widget, *, only_if_visible: bool = False) -> None:
    """例外を握りつぶして安全にウィジェットを閉じる。"""
    if widget is None:
        return
    if only_if_visible and not _safe_is_visible(widget):
        return
    _safe_call(widget.close)


def _is_window_capture_source(main_window) -> bool:
    """取得元がウィンドウモードかを返す。"""
    return selected_capture_source(main_window) == C.CAPTURE_SOURCE_WINDOW and HAS_WIN32


def _set_run_toggle_state(main_window, running: bool) -> None:
    """Start/Stop のトグル表示状態を同期する。"""
    main_window.btn_start_bar.setChecked(bool(running))
    main_window.btn_stop_bar.setChecked(not bool(running))


def on_status(main_window, text: str):
    """ステータスラベルを更新する。"""
    # ステータス表示更新はこの関数経由に寄せる。
    main_window.lbl_status.setText(text)


def is_image_analysis_running(main_window) -> bool:
    """画像ファイル解析スレッドの実行状態を返す。"""
    # 画像ファイル解析は別スレッドで動くため、スレッド状態で判定する。
    return main_window._image_thread is not None and main_window._image_thread.isRunning()


def set_image_analysis_busy(main_window, busy: bool):
    """画像解析中のUIボタン有効/無効を切り替える。"""
    # 実行中は二重起動を避けるためボタンを無効化。
    main_window.btn_load_image_bar.setEnabled(not busy)


def cleanup_image_analysis(main_window):
    """画像解析用スレッド/ワーカー/進捗UIを後始末する。"""
    # 進捗ダイアログ／スレッド／ワーカー参照をまとめて解放する。
    if main_window._image_progress is not None:
        # 進捗ダイアログは閉じるだけ。
        _safe_call(main_window._image_progress.close)
        main_window._image_progress = None
    if main_window._image_thread is not None:
        # スレッド終了は quit -> wait の順で固定。
        def _stop_image_thread() -> None:
            # スレッド停止要求。
            main_window._image_thread.quit()
            # 最大1.5秒だけ待つ。
            main_window._image_thread.wait(1500)

        _safe_call(_stop_image_thread)
    main_window._image_worker = None
    main_window._image_thread = None
    set_image_analysis_busy(main_window, False)


def cancel_image_analysis(main_window):
    """画像解析ワーカーへキャンセル要求を出す。"""
    # 実処理はワーカー側フラグで安全停止させる。
    if main_window._image_worker is not None:
        _safe_call(main_window._image_worker.request_cancel)


def on_load_image(main_window):
    """画像ファイル解析を開始する。"""
    # ライブ計測中に画像解析へ切り替えるため、先に worker を停止する。
    if is_image_analysis_running(main_window):
        on_status(main_window, "画像解析を実行中です。キャンセルしてから再実行してください。")
        return

    file_path, _ = QFileDialog.getOpenFileName(
        main_window,
        "画像を読み込む",
        "",
        "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All Files (*)",
    )
    if not file_path:
        return

    main_window.worker.stop()
    _set_run_toggle_state(main_window, False)

    worker = ImageFileAnalyzeWorker(
        path=file_path,
        sample_points=int(main_window.spin_points.value()),
        wheel_sat_threshold=main_window._selected_wheel_sat_threshold(),
        color_band_sat_threshold=selected_effective_color_band_sat_threshold(main_window),
    )
    # 重い解析は QThread 上で実行し、UI スレッドはブロックしない。
    thread = QThread(main_window)
    worker.moveToThread(thread)
    worker.progress.connect(main_window.on_image_analysis_progress)
    worker.finished.connect(main_window.on_image_analysis_finished)
    worker.failed.connect(main_window.on_image_analysis_failed)
    worker.canceled.connect(main_window.on_image_analysis_canceled)
    for signal in (worker.finished, worker.failed, worker.canceled):
        signal.connect(thread.quit)
    thread.started.connect(worker.run)
    main_window._image_worker = worker
    main_window._image_thread = thread

    dlg = QProgressDialog("画像を解析中…", "キャンセル", 0, 100, main_window)
    dlg.setWindowTitle("画像解析")
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(0)
    dlg.setValue(0)
    dlg.canceled.connect(main_window._cancel_image_analysis)
    main_window._image_progress = dlg
    set_image_analysis_busy(main_window, True)

    on_status(main_window, f"画像解析を開始: {Path(file_path).name}")
    thread.start()
    dlg.show()


def on_image_analysis_progress(main_window, percent: int, text: str):
    """画像解析進捗をダイアログへ反映する。"""
    # 異常値が来ても表示が壊れないよう 0..100 に丸める。
    if main_window._image_progress is not None:
        main_window._image_progress.setLabelText(text)
        main_window._image_progress.setValue(max(0, min(100, int(percent))))


def on_image_analysis_finished(main_window, res: dict):
    """画像解析完了時に結果反映と後処理を行う。"""
    cleanup_image_analysis(main_window)
    main_window.on_result(res)
    _restore_visible_docks_from_snapshot(main_window)
    _schedule_snapshot_restore(main_window, 0, 80)
    on_status(main_window, f"画像解析完了 ({res.get('dt_ms', 0.0):.1f} ms)")


def _restore_visible_docks_from_snapshot(main_window) -> None:
    """可視ドックを最新スナップショットで再描画する。"""
    # 見えているドックだけ復元する。
    for dock in getattr(main_window, "_dock_map", {}).values():
        if dock is None:
            continue
        if not _safe_is_visible(dock):
            continue
        # 1ドックずつ安全に復元。
        _safe_call(main_window._restore_dock_from_snapshot, dock)


def _schedule_snapshot_restore(main_window, *delays_ms: int) -> None:
    """遅延タイミングを指定してスナップショット復元を予約する。"""
    # レイアウト確定後にも再適用して描画取りこぼしを防ぐ。
    for delay in delays_ms:
        QTimer.singleShot(
            int(delay),
            lambda mw=main_window: _restore_visible_docks_from_snapshot(mw),
        )


def on_image_analysis_failed(main_window, message: str):
    """画像解析失敗時の共通エラーハンドリング。"""
    cleanup_image_analysis(main_window)
    on_status(main_window, message)
    QMessageBox.warning(main_window, "画像解析", message)


def on_image_analysis_canceled(main_window):
    """画像解析キャンセル完了時の後処理。"""
    cleanup_image_analysis(main_window)
    on_status(main_window, "画像解析をキャンセルしました")


def on_start(main_window):
    """ライブ解析を開始する。"""
    # 画像解析中はキャプチャループを開始しない。
    if is_image_analysis_running(main_window):
        on_status(main_window, "画像解析中です。キャンセル完了後にStartしてください。")
        return
    # Start時点の表示状態を再同期して、必要ビューの計算漏れを防ぐ。
    sync_worker_view_flags(main_window)
    main_window.worker.start()
    _set_run_toggle_state(main_window, True)


def on_stop(main_window):
    """ライブ解析停止または画像解析キャンセルを行う。"""
    # 画像解析中ならまずキャンセル要求、通常時は計測ループ停止。
    if is_image_analysis_running(main_window):
        cancel_image_analysis(main_window)
        on_status(main_window, "画像解析のキャンセルを要求しました")
        return
    main_window.worker.stop()
    _set_run_toggle_state(main_window, False)


def close_event(main_window, event):
    """メインウィンドウ終了時のクリーンアップ処理。"""
    # メイン終了時に補助ウィンドウも確実に閉じる
    main_window._flush_settings_save()
    main_window.save_settings(silent=True)
    main_window.save_current_layout_to_config(silent=True)
    cancel_image_analysis(main_window)
    cleanup_image_analysis(main_window)
    main_window.worker.stop()
    _safe_close_widget(getattr(main_window, "preview_window", None), only_if_visible=True)
    _safe_close_widget(getattr(main_window, "_settings_window", None))
    # ROI選択窓が残っていれば閉じる。
    _safe_call(main_window._close_roi_selectors)
    QMainWindow.closeEvent(main_window, event)


def refresh_windows(main_window, announce: bool = True):
    """ウィンドウ候補一覧を再取得してコンボへ反映する。"""
    # Win32 環境ではウィンドウ一覧を再取得し、可能なら既存選択を維持する。
    combo = main_window.combo_win
    editor = combo.lineEdit()
    wins = list_windows() if HAS_WIN32 else []
    prev_hwnd = combo.currentData()
    preserved_text = _preserved_window_editor_text(combo, editor)
    with blocked_signals(combo):
        _rebuild_window_combo_items(combo, wins)
        selected_idx = _restore_window_combo_selection(
            combo,
            editor,
            prev_hwnd=prev_hwnd,
            preserved_text=preserved_text,
        )
    new_hwnd = combo.itemData(selected_idx) if selected_idx >= 0 else None
    if announce and not HAS_WIN32:
        on_status(main_window, "この環境ではウィンドウ選択は使えません（画面の領域選択を使用）")
    elif announce:
        on_status(main_window, f"ウィンドウ {len(wins)} 件")
    sync_capture_source_ui(main_window)
    if _is_window_capture_source(main_window) and new_hwnd != prev_hwnd:
        on_window_changed(main_window, int(selected_idx))


def selected_capture_source(main_window) -> str:
    """UI選択から取得元種別を安全な値で返す。"""
    # UIが不正状態でも安全なソース値へ正規化する。
    source = main_window.combo_capture_source.currentData()
    return safe_choice(source, C.CAPTURE_SOURCES, C.DEFAULT_CAPTURE_SOURCE)


def _capture_source_row_widget(main_window, row_attr: str, fallback_widget):
    """設定行ウィジェットがあれば優先し、無ければ本体ウィジェットを返す。"""
    row = getattr(main_window, row_attr, None)
    return row if row is not None else fallback_widget


def sync_capture_source_ui(main_window):
    """取得元に応じて関連UIの表示/有効状態を切り替える。"""
    # 取得元に応じて、表示すべき操作ボタンと入力欄を切り替える。
    is_window = selected_capture_source(main_window) == C.CAPTURE_SOURCE_WINDOW
    window_widgets = (
        _capture_source_row_widget(
            main_window,
            "_row_pick_roi_win_settings",
            main_window.btn_pick_roi_win,
        ),
    )
    screen_widgets = (
        _capture_source_row_widget(
            main_window,
            "_row_pick_roi_screen_settings",
            main_window.btn_pick_roi_screen,
        ),
    )

    # 設定ダイアログ生成前はこれらのウィジェットが親なし(top-level)のため、
    # setVisible(True) を呼ぶと単独ウィンドウとして出てしまう。
    has_settings_window = hasattr(main_window, "_settings_window")
    if has_settings_window:
        set_visible_if_changed(main_window._row_target_settings, is_window)
        for widget in window_widgets:
            set_visible_if_changed(widget, is_window)
        for widget in screen_widgets:
            set_visible_if_changed(widget, not is_window)
    else:
        # 起動時に誤表示しないよう、親なし状態では明示的に隠す。
        for widget in (*window_widgets, *screen_widgets):
            set_visible_if_changed(widget, False)

    can_window = is_window and HAS_WIN32
    set_enabled_if(main_window.combo_win, can_window)
    set_enabled_if(main_window.btn_pick_roi_win, can_window)
    set_enabled_if(main_window.btn_pick_roi_screen, not is_window)


def apply_capture_source(main_window, *_):
    """取得元切替の公開ハンドラ。"""
    _apply_capture_source(main_window, save=True)


def _apply_capture_source(main_window, save: bool):
    """取得元切替の実処理。"""
    source = selected_capture_source(main_window)
    # 非Win32では window モードを screen モードへ強制フォールバック。
    if source == C.CAPTURE_SOURCE_WINDOW and not HAS_WIN32:
        idx = main_window.combo_capture_source.findData(C.CAPTURE_SOURCE_SCREEN)
        if idx >= 0:
            set_current_index_blocked(main_window.combo_capture_source, idx)
        source = C.CAPTURE_SOURCE_SCREEN
        on_status(main_window, "この環境では画面範囲モードを使用します")

    if source == C.CAPTURE_SOURCE_WINDOW:
        if HAS_WIN32 and main_window.combo_win.count() <= 0:
            refresh_windows(main_window)
        hwnd = main_window.combo_win.currentData()
        # ウィンドウ取得時の初期ROIはウィンドウ全体に戻す。
        main_window.worker.set_capture_selection(
            target_hwnd=int(hwnd) if hwnd is not None else None,
            roi_rel=None,
            roi_abs=None,
        )
    else:
        main_window.worker.set_capture_selection(target_hwnd=None, roi_rel=None)

    sync_capture_source_ui(main_window)
    if main_window.chk_preview_window.isChecked():
        update_preview_snapshot(main_window)
    if save:
        main_window._request_save_settings()


def on_window_changed(main_window, _idx: int):
    """対象ウィンドウ選択変更を worker と表示へ反映する。"""
    # window モード時のみターゲットウィンドウ変更を worker へ伝える。
    if not _is_window_capture_source(main_window):
        return
    hwnd = main_window.combo_win.currentData()
    if hwnd is None:
        main_window.worker.set_capture_selection(target_hwnd=None, roi_rel=None)
        on_status(main_window, "ターゲット未選択（画面領域を使います）")
        return
    # ウィンドウターゲットを選んだら、画面領域モードを解除（排他的）
    main_window.worker.set_capture_selection(target_hwnd=int(hwnd), roi_rel=None, roi_abs=None)
    rect = main_window.worker._get_window_rect(int(hwnd))
    if rect is None:
        on_status(main_window, "ターゲット設定: 取得失敗")
        return
    on_status(
        main_window,
        (
            f"ターゲット設定: {main_window.combo_win.currentText()}  "
            f"({rect.width()}x{rect.height()}) / 次にウィンドウ内領域を選択してください"
        ),
    )
    if main_window.chk_preview_window.isChecked():
        update_preview_snapshot(main_window)


def on_window_text_committed(main_window):
    """編集可能コンボ入力を既存候補へ解決して選択確定する。"""
    # 入力だけでは確定せず、完全一致か明示選択のときだけターゲットを切り替える。
    if not _is_window_capture_source(main_window):
        return
    combo = main_window.combo_win
    editor = combo.lineEdit()
    text = combo.currentText().strip()
    if not text:
        if combo.currentData() is not None:
            _clear_window_selection(main_window, combo, editor, text_to_keep=None)
        return

    idx = _find_combo_index_by_text_casefold(combo, text)

    if idx < 0:
        if combo.currentData() is not None:
            _clear_window_selection(main_window, combo, editor, text_to_keep=text)
        return

    current_idx = int(combo.currentIndex())
    if idx == current_idx and combo.currentData() is not None:
        if editor is not None and editor.text() != combo.itemText(idx):
            editor.setText(combo.itemText(idx))
        return

    set_current_index_blocked(combo, idx)
    on_window_changed(main_window, idx)


def has_visible_image_dock(main_window) -> bool:
    """画像系ドックが1つ以上可視なら True を返す。"""
    # 画像系ドックが1つでも開いていれば image 処理を有効にする。
    targets = getattr(main_window, "_image_update_targets", ())
    return any(
        is_widget_renderable(dock) and is_widget_renderable(dock.widget()) for dock, *_ in targets
    )


def sync_worker_view_flags(main_window):
    """現在UI可視状態に応じた worker 側の解析対象を同期する。"""
    # 可視ビューに合わせて worker 側の計算フラグを絞る。
    if bool(getattr(main_window, "_layout_interaction_pause_active", False)):
        _set_worker_view_flags_if_changed(main_window, **_WORKER_VIEW_FLAGS_DISABLED)
        return

    color_band_visible = bool(
        getattr(main_window, "dock_color_band", None) is not None
        and main_window.dock_color_band.isVisible()
    )
    color_visible = bool(main_window.dock_color.isVisible() or color_band_visible)
    _set_worker_view_flags_if_changed(
        main_window,
        color=color_visible,
        color_band=color_band_visible,
        scatter=bool(main_window.dock_scatter.isVisible()),
        hsv_hist=bool(main_window.dock_hist.isVisible()),
        # 配色比率は無彩色(白/灰/黒)集計で bgr_preview を使うため、
        # 当該ドック表示中は画像系ドックが無くても bgr を受け取る。
        image=bool(has_visible_image_dock(main_window) or color_band_visible),
        preview=bool(main_window.chk_preview_window.isChecked()),
    )


def begin_layout_interaction_pause(main_window, reason: str = "layout") -> None:
    """レイアウト操作中の解析一時停止を開始する。"""
    # ドック再配置中は解析更新を一時停止してUIの引っ掛かりを減らす。
    reasons = getattr(main_window, "_layout_interaction_pause_reasons", None)
    if isinstance(reasons, set):
        reasons.add(str(reason))

    timer = getattr(main_window, "_layout_interaction_resume_timer", None)
    if timer is not None:
        timer.stop()

    if bool(getattr(main_window, "_layout_interaction_pause_active", False)):
        return

    main_window._layout_interaction_pause_active = True
    _set_worker_view_flags_if_changed(main_window, **_WORKER_VIEW_FLAGS_DISABLED)


def schedule_layout_interaction_resume(main_window, reason: str = "layout") -> None:
    """レイアウト操作停止後の解析再開をタイマーで予約する。"""
    # 最後の操作から一定時間無操作なら自動で再開する。
    reasons = getattr(main_window, "_layout_interaction_pause_reasons", None)
    if isinstance(reasons, set):
        reasons.discard(str(reason))

    timer = getattr(main_window, "_layout_interaction_resume_timer", None)
    if timer is None:
        end_layout_interaction_pause(main_window)
        return
    timer.start()


def end_layout_interaction_pause(main_window) -> None:
    """解析一時停止を解除し、可視ドックの再描画を行う。"""
    if not bool(getattr(main_window, "_layout_interaction_pause_active", False)):
        return

    timer = getattr(main_window, "_layout_interaction_resume_timer", None)
    if timer is not None:
        timer.stop()

    main_window._layout_interaction_pause_active = False
    reasons = getattr(main_window, "_layout_interaction_pause_reasons", None)
    if isinstance(reasons, set):
        reasons.clear()

    sync_worker_view_flags(main_window)
    _restore_visible_docks_from_snapshot(main_window)


def update_preview_snapshot(main_window):
    """現在の取得設定でプレビューを1回更新する。"""
    # プレビューは一度だけキャプチャして更新する軽量経路。
    if not main_window.chk_preview_window.isChecked():
        return
    if (
        selected_capture_source(main_window) == C.CAPTURE_SOURCE_WINDOW
        and main_window.worker.target_hwnd is None
    ):
        on_status(main_window, "ターゲットウィンドウを選択してください")
        return
    bgr, _, err = main_window.worker.capture_once()
    if bgr is None:
        if err:
            on_status(main_window, err)
        return
    if not main_window.preview_window.isVisible():
        main_window.preview_window.show()
    main_window.preview_window.update_preview(bgr)


def on_preview_toggled(main_window, checked: bool):
    """プレビューの有効状態を実ウィンドウへ反映する。"""
    # チェック状態と実ウィンドウ表示を常に同期させる。
    if checked:
        main_window.preview_window.show()
        update_preview_snapshot(main_window)
        on_status(main_window, "プレビュー表示")
    else:
        main_window.preview_window.hide()
        on_status(main_window, "プレビュー非表示")
    sync_worker_view_flags(main_window)
    main_window._request_save_settings()


def on_preview_closed(main_window):
    """プレビューウィンドウの手動クローズをチェック状態へ反映する。"""
    # プレビュー側の × 閉じる操作を設定チェックへ反映する。
    if main_window.chk_preview_window.isChecked():
        set_checked_blocked(main_window.chk_preview_window, False)
    sync_worker_view_flags(main_window)
    on_status(main_window, "プレビュー非表示")
