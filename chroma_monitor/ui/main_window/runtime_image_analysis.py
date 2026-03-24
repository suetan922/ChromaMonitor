"""画像解析の起動/停止とアプリ終了時の後始末。"""

from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QProgressDialog

from ...analysis.image_file_worker import ImageFileAnalyzeWorker
from .runtime_common import (
    on_status,
    restore_visible_docks_from_snapshot,
    safe_call,
    safe_close_widget,
    schedule_snapshot_restore,
    set_run_toggle_state,
)
from .runtime_layout_pause import sync_worker_view_flags
from .settings_logic import selected_effective_color_band_sat_threshold


def is_image_analysis_running(main_window) -> bool:
    """画像ファイル解析スレッドの実行状態を返す。"""
    return main_window._image_thread is not None and main_window._image_thread.isRunning()


def set_image_analysis_busy(main_window, busy: bool):
    """画像解析中のUIボタン有効/無効を切り替える。"""
    main_window.btn_load_image_bar.setEnabled(not busy)


def cleanup_image_analysis(main_window):
    """画像解析用スレッド/ワーカー/進捗UIを後始末する。"""
    if main_window._image_progress is not None:
        safe_call(main_window._image_progress.close)
        main_window._image_progress = None
    if main_window._image_thread is not None:
        def _stop_image_thread() -> None:
            main_window._image_thread.quit()
            main_window._image_thread.wait(1500)

        safe_call(_stop_image_thread)
    main_window._image_worker = None
    main_window._image_thread = None
    set_image_analysis_busy(main_window, False)


def cancel_image_analysis(main_window):
    """画像解析ワーカーへキャンセル要求を出す。"""
    if main_window._image_worker is not None:
        safe_call(main_window._image_worker.request_cancel)


def _base_window_title(main_window) -> str:
    """初期化時に決めたアプリの基本タイトルを返す。"""
    return str(getattr(main_window, "_base_window_title", "") or "ChromaMonitor")


def set_loaded_file_title(main_window, file_name: str | None) -> None:
    """読み込んだファイル名をウィンドウタイトルへ反映する。"""
    name = str(file_name or "").strip()
    main_window._loaded_file_title_name = name
    base_title = _base_window_title(main_window)
    main_window.setWindowTitle(f"{base_title} - {name}" if name else base_title)


def clear_loaded_file_title(main_window) -> None:
    """ファイル名付きタイトルを基本タイトルへ戻す。"""
    set_loaded_file_title(main_window, None)


def on_load_image(main_window):
    """画像ファイル解析を開始する。"""
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
    set_run_toggle_state(main_window, False)
    set_loaded_file_title(main_window, Path(file_path).name)

    worker = ImageFileAnalyzeWorker(
        path=file_path,
        sample_points=int(main_window.spin_points.value()),
        wheel_sat_threshold=main_window._selected_wheel_sat_threshold(),
        color_band_sat_threshold=selected_effective_color_band_sat_threshold(main_window),
        max_dim=int(getattr(main_window.worker.cfg, "max_dim", 0)),
    )
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
    if main_window._image_progress is not None:
        main_window._image_progress.setLabelText(text)
        main_window._image_progress.setValue(max(0, min(100, int(percent))))


def on_image_analysis_finished(main_window, res: dict):
    """画像解析完了時に結果反映と後処理を行う。"""
    cleanup_image_analysis(main_window)
    main_window.on_result(res)
    restore_visible_docks_from_snapshot(main_window)
    schedule_snapshot_restore(main_window, 0, 80)
    on_status(main_window, f"画像解析完了 ({res.get('dt_ms', 0.0):.1f} ms)")


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
    if is_image_analysis_running(main_window):
        on_status(main_window, "画像解析中です。キャンセル完了後にStartしてください。")
        return
    sync_worker_view_flags(main_window)
    clear_loaded_file_title(main_window)
    main_window.worker.start()
    set_run_toggle_state(main_window, True)


def on_stop(main_window):
    """ライブ解析停止または画像解析キャンセルを行う。"""
    if is_image_analysis_running(main_window):
        cancel_image_analysis(main_window)
        on_status(main_window, "画像解析のキャンセルを要求しました")
        return
    main_window.worker.stop()
    set_run_toggle_state(main_window, False)


def close_event(main_window, event):
    """メインウィンドウ終了時のクリーンアップ処理。"""
    main_window._flush_settings_save()
    main_window.save_settings(silent=True)
    main_window.save_current_layout_to_config(silent=True)
    cancel_image_analysis(main_window)
    cleanup_image_analysis(main_window)
    main_window.worker.stop()
    safe_close_widget(getattr(main_window, "preview_window", None), only_if_visible=True)
    safe_close_widget(getattr(main_window, "_settings_window", None))
    safe_call(main_window._close_roi_selectors)
    QMainWindow.closeEvent(main_window, event)
