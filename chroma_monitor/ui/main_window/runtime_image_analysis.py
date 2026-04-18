"""画像解析の起動/停止とアプリ終了時の後始末。"""

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence

import numpy as np

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
)

from ...analysis.image_file_worker import ImageFileAnalyzeWorker
from ...util import constants as C
from ...util.image_inputs import (
    is_supported_image_path as _is_supported_image_path,
    normalize_existing_image_path,
    qimage_to_bgr,
    supported_image_paths_from_text,
    supported_image_paths_from_urls,
)
from ...views.image_drop_target import install_dock_area_image_drop_target
from .runtime_common import (
    on_status,
    restore_visible_docks_from_snapshot,
    safe_call,
    safe_close_widget,
    schedule_snapshot_restore,
    set_run_toggle_state,
)
from .runtime_capture import capture_preflight_result
from .runtime_layout_pause import sync_worker_view_flags
from .settings_logic import selected_effective_color_band_sat_threshold


@dataclass(frozen=True, slots=True)
class ImageAnalysisRequest:
    """画像解析開始に必要な入力情報。"""

    display_name: str
    path: str | None = None
    source_bgr: np.ndarray | None = None


def is_image_analysis_running(main_window) -> bool:
    """画像ファイル解析スレッドの実行状態を返す。"""
    return main_window._image_thread is not None and main_window._image_thread.isRunning()


def is_live_analysis_running(main_window) -> bool:
    """ライブ解析ワーカーが実行状態なら True を返す。"""
    worker = getattr(main_window, "worker", None)
    is_running = getattr(worker, "is_running", None)
    if callable(is_running):
        try:
            return bool(is_running())
        except Exception:
            pass
    thread = getattr(worker, "_thread", None)
    return bool(thread is not None and getattr(thread, "is_alive", lambda: False)())


def _sync_live_run_toggle_state(main_window) -> None:
    """Start/Stop ボタン表示を現在のライブ解析状態へ戻す。"""
    set_run_toggle_state(main_window, is_live_analysis_running(main_window))


def _abort_live_start(
    main_window,
    message: str,
    *,
    warning: bool,
) -> None:
    """Start 不可時の通知とトグル復元を共通化する。"""
    on_status(main_window, message)
    if bool(warning):
        QMessageBox.warning(main_window, "画像解析", message)
    # checkable QPushButton は click 時点で ON になるため、失敗時は明示的に戻す。
    set_run_toggle_state(main_window, False)
    main_window.btn_stop_bar.setChecked(False)


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


def _clear_pending_loaded_image_source(main_window) -> None:
    """次回完了時に反映予定の読み込み画像情報を消す。"""
    main_window._pending_loaded_image_source_path = ""
    main_window._pending_loaded_image_source_name = ""
    main_window._pending_loaded_image_source_bgr = None


def _clear_loaded_image_source(main_window) -> None:
    """現在有効な読み込み画像情報を消す。"""
    main_window._loaded_image_source_path = ""
    main_window._loaded_image_source_name = ""
    main_window._loaded_image_source_bgr = None
    _clear_pending_loaded_image_source(main_window)


def _set_pending_loaded_image_source(main_window, request: ImageAnalysisRequest) -> None:
    """画像解析完了後に有効化する読み込み画像情報を保持する。"""
    _clear_pending_loaded_image_source(main_window)
    main_window._pending_loaded_image_source_name = str(request.display_name or "").strip()
    if request.path:
        main_window._pending_loaded_image_source_path = str(request.path)
        return
    if request.source_bgr is not None and request.source_bgr.size > 0:
        main_window._pending_loaded_image_source_bgr = np.ascontiguousarray(request.source_bgr)


def _promote_pending_loaded_image_source(main_window) -> None:
    """完了した読み込み画像情報を現在有効なものとして反映する。"""
    main_window._loaded_image_source_path = str(
        getattr(main_window, "_pending_loaded_image_source_path", "") or ""
    )
    main_window._loaded_image_source_name = str(
        getattr(main_window, "_pending_loaded_image_source_name", "") or ""
    )
    pending_bgr = getattr(main_window, "_pending_loaded_image_source_bgr", None)
    main_window._loaded_image_source_bgr = (
        None if pending_bgr is None else np.ascontiguousarray(pending_bgr)
    )
    _clear_pending_loaded_image_source(main_window)


def _show_input_message(
    main_window,
    title: str,
    message: str,
    *,
    warning: bool,
) -> None:
    """入力関連メッセージを status とダイアログへ反映する。"""
    on_status(main_window, message)
    if warning:
        QMessageBox.warning(main_window, title, message)
        return
    QMessageBox.information(main_window, title, message)


def is_supported_image_path(main_window, path: str) -> bool:
    """対応画像パスか判定する。"""
    _ = main_window
    return bool(_is_supported_image_path(path))


def can_accept_image_drop_target(main_window, *_args, **_kwargs) -> bool:
    """dock 領域全体で新規ドロップを受け付けられるか返す。"""
    return not is_image_analysis_running(main_window)


def setup_image_input_drop_targets(main_window) -> None:
    """dock 領域全体へ 1 枚 overlay の drag & drop 受付を追加する。"""
    controller = install_dock_area_image_drop_target(
        main_window,
        dock_widgets=tuple(getattr(main_window, "_dock_map", {}).values()),
        path_filter=main_window.is_supported_image_path,
        can_drop_callback=lambda self=main_window: self.can_accept_image_drop_target(),
        drop_handler=main_window.on_image_files_dropped,
    )
    main_window._image_drop_target_controller = controller
    main_window._image_drop_target_controllers = [controller]


def _image_request_from_path(
    main_window,
    path: str,
    *,
    error_title: str,
    warning: bool,
) -> ImageAnalysisRequest | None:
    """ファイルパスから解析リクエストを組み立てる。"""
    normalized = normalize_existing_image_path(path)
    if normalized is None:
        _show_input_message(
            main_window,
            error_title,
            "対応している画像ファイルを選択してください。",
            warning=warning,
        )
        return None
    return ImageAnalysisRequest(
        display_name=Path(normalized).name,
        path=normalized,
    )


def _clipboard_image_request(main_window) -> ImageAnalysisRequest | None:
    """クリップボードから画像解析リクエストを作る。"""
    app = QApplication.instance()
    if app is None:
        _show_input_message(
            main_window,
            "クリップボード読込",
            "クリップボードを利用できません。",
            warning=True,
        )
        return None

    clipboard = app.clipboard()
    if clipboard is None:
        _show_input_message(
            main_window,
            "クリップボード読込",
            "クリップボードを利用できません。",
            warning=True,
        )
        return None

    image = clipboard.image()
    if image is not None and not image.isNull():
        bgr = qimage_to_bgr(image)
        if bgr is None or bgr.size == 0:
            _show_input_message(
                main_window,
                "クリップボード読込",
                "クリップボード画像の変換に失敗しました。",
                warning=True,
            )
            return None
        return ImageAnalysisRequest(
            display_name=C.CLIPBOARD_IMAGE_TITLE,
            source_bgr=bgr,
        )

    mime_data = clipboard.mimeData()
    if mime_data is not None:
        paths = supported_image_paths_from_urls(mime_data.urls()) if mime_data.hasUrls() else []
        if not paths and mime_data.hasText():
            paths = supported_image_paths_from_text(mime_data.text())
        if paths:
            return ImageAnalysisRequest(
                display_name=Path(paths[0]).name,
                path=paths[0],
            )

    _show_input_message(
        main_window,
        "クリップボード読込",
        "クリップボードに読み込める画像データまたは画像ファイルのパスがありません。",
        warning=False,
    )
    return None


def _start_image_analysis_request(
    main_window,
    request: ImageAnalysisRequest | None,
) -> None:
    """共通の画像解析開始処理。"""
    if request is None:
        return
    if is_image_analysis_running(main_window):
        on_status(main_window, "画像解析を実行中です。キャンセルしてから再実行してください。")
        return

    _set_pending_loaded_image_source(main_window, request)
    main_window.worker.stop()
    set_run_toggle_state(main_window, False)
    set_loaded_file_title(main_window, request.display_name)

    worker = ImageFileAnalyzeWorker(
        path=request.path,
        sample_points=int(main_window.spin_points.value()),
        wheel_sat_threshold=main_window._selected_wheel_sat_threshold(),
        color_band_sat_threshold=selected_effective_color_band_sat_threshold(main_window),
        max_dim=int(getattr(main_window.worker.cfg, "max_dim", 0)),
        source_bgr=request.source_bgr,
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

    on_status(main_window, f"画像解析を開始: {request.display_name}")
    thread.start()
    dlg.show()


def on_load_image(main_window):
    """ファイルダイアログから画像ファイル解析を開始する。"""
    if is_image_analysis_running(main_window):
        on_status(main_window, "画像解析を実行中です。キャンセルしてから再実行してください。")
        return

    file_path, _ = QFileDialog.getOpenFileName(
        main_window,
        "画像を読み込む",
        "",
        C.IMAGE_INPUT_FILE_DIALOG_FILTER,
    )
    if not file_path:
        return
    _start_image_analysis_request(
        main_window,
        _image_request_from_path(
            main_window,
            file_path,
            error_title="ファイル読込",
            warning=True,
        ),
    )


def on_load_image_from_clipboard(main_window):
    """クリップボードから画像ファイル解析を開始する。"""
    _start_image_analysis_request(main_window, _clipboard_image_request(main_window))


def on_image_files_dropped(main_window, paths: Sequence[str]) -> None:
    """dock 領域 overlay へドロップされた画像ファイルを読み込む。"""
    first_path = next((str(path) for path in paths if str(path).strip()), "")
    if not first_path:
        return
    _start_image_analysis_request(
        main_window,
        _image_request_from_path(
            main_window,
            first_path,
            error_title="ドラッグ＆ドロップ",
            warning=False,
        ),
    )


def on_image_analysis_progress(main_window, percent: int, text: str):
    """画像解析進捗をダイアログへ反映する。"""
    if main_window._image_progress is not None:
        main_window._image_progress.setLabelText(text)
        main_window._image_progress.setValue(max(0, min(100, int(percent))))


def on_image_analysis_finished(main_window, res: dict):
    """画像解析完了時に結果反映と後処理を行う。"""
    cleanup_image_analysis(main_window)
    _promote_pending_loaded_image_source(main_window)
    main_window.on_result(res)
    restore_visible_docks_from_snapshot(main_window)
    schedule_snapshot_restore(main_window, 0, 80)
    on_status(main_window, f"画像解析完了 ({res.get('dt_ms', 0.0):.1f} ms)")


def on_image_analysis_failed(main_window, message: str):
    """画像解析失敗時の共通エラーハンドリング。"""
    cleanup_image_analysis(main_window)
    _clear_pending_loaded_image_source(main_window)
    on_status(main_window, message)
    QMessageBox.warning(main_window, "画像解析", message)


def on_image_analysis_canceled(main_window):
    """画像解析キャンセル完了時の後処理。"""
    cleanup_image_analysis(main_window)
    _clear_pending_loaded_image_source(main_window)
    on_status(main_window, "画像解析をキャンセルしました")


def on_start(main_window):
    """ライブ解析を開始する。"""
    if is_image_analysis_running(main_window):
        _abort_live_start(
            main_window,
            "画像解析中です。キャンセル完了後にStartしてください。",
            warning=False,
        )
        return
    preflight = capture_preflight_result(main_window)
    if not preflight.ready:
        _abort_live_start(
            main_window,
            str(preflight.message or ""),
            warning=True,
        )
        return
    sync_worker_view_flags(main_window)
    clear_loaded_file_title(main_window)
    _clear_loaded_image_source(main_window)
    main_window.worker.start()
    _sync_live_run_toggle_state(main_window)


def on_stop(main_window):
    """ライブ解析停止または画像解析キャンセルを行う。"""
    if is_image_analysis_running(main_window):
        cancel_image_analysis(main_window)
        on_status(main_window, "画像解析のキャンセルを要求しました")
        _sync_live_run_toggle_state(main_window)
        return
    main_window.worker.stop()
    _sync_live_run_toggle_state(main_window)


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
    safe_close_widget(getattr(main_window, "_canvas_preview_window", None))
    safe_call(main_window._close_roi_selectors)
    QMainWindow.closeEvent(main_window, event)
