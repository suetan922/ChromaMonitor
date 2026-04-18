"""ツール系ウィンドウの起動と画像スナップショット取得。"""

from __future__ import annotations

import traceback
from PySide6.QtWidgets import QMessageBox

from ...util.debug_log import write_window_layout_debug_log
from ...util.image_inputs import load_image_path_to_bgr
from ..canvas_preview_dialog import CanvasPreviewDialog, CanvasPreviewSnapshot
from .runtime_common import on_status
from .window_topmost import present_top_level_widget


def _clear_canvas_preview_window_ref(main_window, dialog=None, *_args) -> None:
    """破棄済みツールウィンドウ参照を外す。"""
    if dialog is not None and getattr(main_window, "_canvas_preview_window", None) is not dialog:
        return
    main_window._canvas_preview_window = None


def _root_exception(exc: BaseException) -> BaseException:
    """`__cause__` を辿って元例外を返す。"""
    current = exc
    while True:
        next_exc = current.__cause__
        if next_exc is None or next_exc is current:
            return current
        current = next_exc


def _has_capture_roi(main_window) -> bool:
    """現在のキャプチャ設定に ROI があるか返す。"""
    capture = main_window.worker.capture_selection()
    return capture.roi_rel is not None or capture.roi_abs is not None


def _snapshot_from_capture(main_window, *, source_label: str) -> CanvasPreviewSnapshot | None:
    """現在のキャプチャ設定から画像を 1 枚取得する。"""
    bgr, _cap, _err = main_window.worker.capture_once()
    if bgr is None or bgr.size == 0:
        return None
    title = getattr(main_window, "_loaded_file_title_name", "") or str(source_label)
    return CanvasPreviewSnapshot(bgr=bgr.copy(), source_label=source_label, title=str(title))


def _snapshot_from_loaded_image(main_window) -> CanvasPreviewSnapshot | None:
    """現在有効な読み込み画像から原寸スナップショットを返す。"""
    source_bgr = getattr(main_window, "_loaded_image_source_bgr", None)
    source_path = str(getattr(main_window, "_loaded_image_source_path", "") or "").strip()
    title = str(getattr(main_window, "_loaded_image_source_name", "") or "読み込み画像")
    if source_bgr is not None and getattr(source_bgr, "size", 0) > 0:
        return CanvasPreviewSnapshot(
            bgr=source_bgr.copy(),
            source_label="読み込み画像",
            title=title,
        )
    if source_path:
        bgr = load_image_path_to_bgr(source_path)
        if bgr is not None and bgr.size > 0:
            return CanvasPreviewSnapshot(
                bgr=bgr,
                source_label="読み込み画像",
                title=title,
            )
    return None


def _snapshot_from_latest_result(main_window) -> CanvasPreviewSnapshot | None:
    """現在の表示内容から画像を返す。"""
    latest = getattr(main_window, "_latest_result_snapshot", None)
    if not isinstance(latest, dict):
        return None
    bgr = latest.get("bgr_preview")
    if bgr is None or getattr(bgr, "size", 0) == 0:
        return None
    title = getattr(main_window, "_loaded_file_title_name", "") or "表示中の画像"
    return CanvasPreviewSnapshot(
        bgr=bgr.copy(),
        source_label="表示中の画像",
        title=str(title),
    )


def build_canvas_preview_snapshot(main_window) -> CanvasPreviewSnapshot | None:
    """優先順位に従ってキャンバスプレビュー用スナップショットを返す。"""
    if _has_capture_roi(main_window):
        snapshot = _snapshot_from_capture(main_window, source_label="選択範囲")
        if snapshot is not None:
            return snapshot
    snapshot = _snapshot_from_loaded_image(main_window)
    if snapshot is not None:
        return snapshot
    snapshot = _snapshot_from_capture(main_window, source_label="表示中の画像")
    if snapshot is not None:
        return snapshot
    return _snapshot_from_latest_result(main_window)


def show_canvas_preview_window(main_window) -> None:
    """キャンバスプレビューウィンドウを最新スナップショットで開く。"""
    write_window_layout_debug_log("canvas_preview_window_open_begin")
    try:
        snapshot = build_canvas_preview_snapshot(main_window)
        if snapshot is None:
            message = "プレビューできる画像がありません。\n画像を読み込むか、選択範囲を作ってから開いてください。"
            on_status(main_window, "キャンバスプレビューを開けませんでした")
            QMessageBox.warning(
                main_window,
                "キャンバスプレビュー",
                message,
            )
            return

        existing = getattr(main_window, "_canvas_preview_window", None)
        if existing is not None:
            try:
                existing.close()
            except Exception:
                pass

        dialog = CanvasPreviewDialog(main_window, snapshot)
        dialog.destroyed.connect(
            lambda *_args, mw=main_window, dlg=dialog: _clear_canvas_preview_window_ref(mw, dlg)
        )
        main_window._canvas_preview_window = dialog
        present_top_level_widget(
            main_window,
            dialog,
            fit_before_show=lambda: main_window._fit_dialog_to_desktop(
                dialog,
                center_on_parent=True,
            ),
        )
        on_status(main_window, "キャンバスプレビューを開きました")
        write_window_layout_debug_log(
            "canvas_preview_window_open_ok",
            source_label=str(snapshot.source_label),
            title=str(snapshot.title),
        )
    except Exception as exc:
        traceback.print_exc()
        root = _root_exception(exc)
        write_window_layout_debug_log(
            "canvas_preview_window_open_fail",
            wrapped_type=type(exc).__name__,
            wrapped_message=str(exc),
            root_type=type(root).__name__,
            root_message=str(root),
            traceback_text="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        )
        on_status(main_window, "キャンバスプレビューを開けませんでした")
        message = f"キャンバスプレビューを開けませんでした。\n{type(exc).__name__}: {exc}"
        if root is not exc:
            message += f"\n原因: {type(root).__name__}: {root}"
        QMessageBox.critical(
            main_window,
            "キャンバスプレビュー",
            message,
        )


def close_canvas_preview_window(main_window) -> None:
    """開いているキャンバスプレビューを閉じる。"""
    dialog = getattr(main_window, "_canvas_preview_window", None)
    if dialog is None:
        return
    try:
        dialog.close()
    finally:
        main_window._canvas_preview_window = None
