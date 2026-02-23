"""Runtime actions (capture/start/stop/preview/image-load) for MainWindow."""

from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QProgressDialog

from ...analyzer import ImageFileAnalyzeWorker
from ...capture.win32_windows import HAS_WIN32, list_windows
from ...util import constants as C
from ...util.functions import (
    blocked_signals,
    safe_choice,
    set_checked_blocked,
    set_current_index_blocked,
)


def _safe_close_widget(widget, *, only_if_visible: bool = False) -> None:
    if widget is None:
        return
    try:
        if only_if_visible and not widget.isVisible():
            return
        widget.close()
    except Exception:
        pass


def _is_window_capture_source(main_window) -> bool:
    return selected_capture_source(main_window) == C.CAPTURE_SOURCE_WINDOW and HAS_WIN32


def on_status(main_window, text: str):
    # ステータス表示更新はこの関数経由に寄せる。
    main_window.lbl_status.setText(text)


def is_image_analysis_running(main_window) -> bool:
    # 画像ファイル解析は別スレッドで動くため、スレッド状態で判定する。
    return main_window._image_thread is not None and main_window._image_thread.isRunning()


def set_image_analysis_busy(main_window, busy: bool):
    # 実行中は二重起動を避けるためボタンを無効化。
    main_window.btn_load_image_bar.setEnabled(not busy)


def cleanup_image_analysis(main_window):
    # 進捗ダイアログ／スレッド／ワーカー参照をまとめて解放する。
    if main_window._image_progress is not None:
        try:
            main_window._image_progress.close()
        except Exception:
            pass
        main_window._image_progress = None
    if main_window._image_thread is not None:
        try:
            main_window._image_thread.quit()
            main_window._image_thread.wait(1500)
        except Exception:
            pass
    main_window._image_worker = None
    main_window._image_thread = None
    set_image_analysis_busy(main_window, False)


def cancel_image_analysis(main_window):
    # 実処理はワーカー側フラグで安全停止させる。
    if main_window._image_worker is not None:
        try:
            main_window._image_worker.request_cancel()
        except Exception:
            pass


def on_load_image(main_window):
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
    main_window.btn_stop_bar.setChecked(True)
    main_window.btn_start_bar.setChecked(False)

    worker = ImageFileAnalyzeWorker(
        path=file_path,
        sample_points=int(main_window.spin_points.value()),
        wheel_sat_threshold=main_window._selected_wheel_sat_threshold(),
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
    # 異常値が来ても表示が壊れないよう 0..100 に丸める。
    if main_window._image_progress is not None:
        main_window._image_progress.setLabelText(text)
        main_window._image_progress.setValue(max(0, min(100, int(percent))))


def on_image_analysis_finished(main_window, res: dict):
    cleanup_image_analysis(main_window)
    main_window.on_result(res)
    on_status(main_window, f"画像解析完了 ({res.get('dt_ms', 0.0):.1f} ms)")


def on_image_analysis_failed(main_window, message: str):
    cleanup_image_analysis(main_window)
    on_status(main_window, message)
    QMessageBox.warning(main_window, "画像解析", message)


def on_image_analysis_canceled(main_window):
    cleanup_image_analysis(main_window)
    on_status(main_window, "画像解析をキャンセルしました")


def on_start(main_window):
    # 画像解析中はキャプチャループを開始しない。
    if is_image_analysis_running(main_window):
        on_status(main_window, "画像解析中です。キャンセル完了後にStartしてください。")
        return
    # Start時点の表示状態を再同期して、必要ビューの計算漏れを防ぐ。
    sync_worker_view_flags(main_window)
    main_window.worker.start()
    main_window.btn_start_bar.setChecked(True)
    main_window.btn_stop_bar.setChecked(False)


def on_stop(main_window):
    # 画像解析中ならまずキャンセル要求、通常時は計測ループ停止。
    if is_image_analysis_running(main_window):
        cancel_image_analysis(main_window)
        on_status(main_window, "画像解析のキャンセルを要求しました")
        return
    main_window.worker.stop()
    main_window.btn_stop_bar.setChecked(True)
    main_window.btn_start_bar.setChecked(False)


def close_event(main_window, event):
    # メイン終了時に補助ウィンドウも確実に閉じる
    main_window._flush_settings_save()
    main_window.save_settings(silent=True)
    main_window.save_current_layout_to_config(silent=True)
    cancel_image_analysis(main_window)
    cleanup_image_analysis(main_window)
    main_window.worker.stop()
    _safe_close_widget(getattr(main_window, "preview_window", None), only_if_visible=True)
    _safe_close_widget(getattr(main_window, "_settings_window", None))
    try:
        main_window._close_roi_selectors()
    except Exception:
        pass
    QMainWindow.closeEvent(main_window, event)


def refresh_windows(main_window):
    # Win32 環境ではウィンドウ一覧を再取得し、先頭に未選択行を固定で置く。
    wins = list_windows() if HAS_WIN32 else []
    with blocked_signals(main_window.combo_win):
        main_window.combo_win.clear()
        main_window.combo_win.addItem("（未選択）", None)
        for hwnd, title in wins[: C.WINDOW_LIST_MAX_ITEMS]:
            main_window.combo_win.addItem(title, hwnd)
    if not HAS_WIN32:
        on_status(main_window, "この環境ではウィンドウ選択は使えません（画面の領域選択を使用）")
    else:
        on_status(main_window, f"ウィンドウ {len(wins)} 件")
    sync_capture_source_ui(main_window)


def selected_capture_source(main_window) -> str:
    # UIが不正状態でも安全なソース値へ正規化する。
    source = main_window.combo_capture_source.currentData()
    return safe_choice(source, C.CAPTURE_SOURCES, C.DEFAULT_CAPTURE_SOURCE)


def sync_capture_source_ui(main_window):
    # 取得元に応じて、表示すべき操作ボタンと入力欄を切り替える。
    is_window = selected_capture_source(main_window) == C.CAPTURE_SOURCE_WINDOW

    # 設定ダイアログ生成前はこれらのウィジェットが親なし(top-level)のため、
    # setVisible(True) を呼ぶと単独ウィンドウとして出てしまう。
    has_settings_window = hasattr(main_window, "_settings_window")
    if has_settings_window:
        if main_window._row_target_settings is not None:
            main_window._row_target_settings.setVisible(is_window)
        main_window.btn_refresh.setVisible(is_window)
        main_window.btn_pick_roi_win.setVisible(is_window)
        main_window.btn_pick_roi_screen.setVisible(not is_window)
    else:
        # 起動時に誤表示しないよう、親なし状態では明示的に隠す。
        main_window.btn_refresh.hide()
        main_window.btn_pick_roi_win.hide()
        main_window.btn_pick_roi_screen.hide()

    can_window = is_window and HAS_WIN32
    main_window.btn_refresh.setEnabled(can_window)
    main_window.combo_win.setEnabled(can_window)
    main_window.btn_pick_roi_win.setEnabled(can_window)
    main_window.btn_pick_roi_screen.setEnabled(not is_window)


def apply_capture_source(main_window, *_):
    _apply_capture_source(main_window, save=True)


def _apply_capture_source(main_window, save: bool):
    source = selected_capture_source(main_window)
    # 非Win32では window モードを screen モードへ強制フォールバック。
    if source == C.CAPTURE_SOURCE_WINDOW and not HAS_WIN32:
        idx = main_window.combo_capture_source.findData(C.CAPTURE_SOURCE_SCREEN)
        if idx >= 0:
            set_current_index_blocked(main_window.combo_capture_source, idx)
        source = C.CAPTURE_SOURCE_SCREEN
        on_status(main_window, "この環境では画面範囲モードを使用します")

    if source == C.CAPTURE_SOURCE_WINDOW:
        if HAS_WIN32 and main_window.combo_win.count() <= 1:
            refresh_windows(main_window)
        main_window.worker.set_roi_on_screen(None)
        # ウィンドウ取得時の初期ROIはウィンドウ全体に戻す
        main_window.worker.set_roi_in_window(None)
        hwnd = main_window.combo_win.currentData()
        # 未選択なら先頭の実ウィンドウを初期選択
        if hwnd is None and main_window.combo_win.count() > 1:
            set_current_index_blocked(main_window.combo_win, 1)
            hwnd = main_window.combo_win.currentData()
        main_window.worker.set_target_window(int(hwnd) if hwnd is not None else None)
    else:
        main_window.worker.set_target_window(None)
        main_window.worker.set_roi_in_window(None)
        set_current_index_blocked(main_window.combo_win, 0)

    sync_capture_source_ui(main_window)
    if main_window.chk_preview_window.isChecked():
        update_preview_snapshot(main_window)
    if save:
        main_window._request_save_settings()


def on_window_changed(main_window, _idx: int):
    # window モード時のみターゲットウィンドウ変更を worker へ伝える。
    if not _is_window_capture_source(main_window):
        return
    hwnd = main_window.combo_win.currentData()
    if hwnd is None:
        main_window.worker.set_target_window(None)
        main_window.worker.set_roi_in_window(None)
        on_status(main_window, "ターゲット未選択（画面領域を使います）")
        return
    # ウィンドウターゲットを選んだら、画面領域モードを解除（排他的）
    main_window.worker.set_target_window(int(hwnd))
    main_window.worker.set_roi_on_screen(None)
    main_window.worker.set_roi_in_window(None)
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
    # 編集可能コンボの入力文字列を候補へ寄せて選択確定する。
    if not _is_window_capture_source(main_window):
        return
    text = main_window.combo_win.currentText().strip()
    if not text:
        if main_window.combo_win.currentData() is not None:
            set_current_index_blocked(main_window.combo_win, 0)
            on_window_changed(main_window, 0)
        return

    needle = text.casefold()
    idx = -1
    for i in range(main_window.combo_win.count()):
        if main_window.combo_win.itemText(i).casefold() == needle:
            idx = i
            break
    if idx < 0:
        for i in range(main_window.combo_win.count()):
            if needle in main_window.combo_win.itemText(i).casefold():
                idx = i
                break
    if idx < 0:
        return

    if idx != main_window.combo_win.currentIndex():
        set_current_index_blocked(main_window.combo_win, idx)
    on_window_changed(main_window, idx)


def has_visible_image_dock(main_window) -> bool:
    # 画像系ドックが1つでも開いていれば image 処理を有効にする。
    targets = getattr(main_window, "_image_update_targets", ())
    return any(dock.isVisible() for dock, _update, _after in targets)


def sync_worker_view_flags(main_window):
    # 可視ビューに合わせて worker 側の計算フラグを絞る。
    main_window.worker.set_view_flags(
        color=bool(main_window.dock_color.isVisible()),
        scatter=bool(main_window.dock_scatter.isVisible()),
        hsv_hist=bool(main_window.dock_hist.isVisible()),
        image=has_visible_image_dock(main_window),
        preview=bool(main_window.chk_preview_window.isChecked()),
    )


def update_preview_snapshot(main_window):
    # プレビューは一度だけキャプチャして更新する軽量経路。
    if not main_window.chk_preview_window.isChecked():
        return
    if (
        selected_capture_source(main_window) == C.CAPTURE_SOURCE_WINDOW
        and main_window.worker.target_hwnd is None
    ):
        on_status(main_window, "ターゲットウィンドウを選択してください")
        return
    bgr, _cap, err = main_window.worker.capture_once()
    if bgr is None:
        if err:
            on_status(main_window, err)
        return
    if not main_window.preview_window.isVisible():
        main_window.preview_window.show()
    main_window.preview_window.update_preview(bgr)


def on_preview_toggled(main_window, checked: bool):
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
    # プレビュー側の × 閉じる操作を設定チェックへ反映する。
    if main_window.chk_preview_window.isChecked():
        set_checked_blocked(main_window.chk_preview_window, False)
    sync_worker_view_flags(main_window)
    on_status(main_window, "プレビュー非表示")
