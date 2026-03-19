from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMessageBox

from ...capture.win32_windows import HAS_WIN32
from ...util import constants as C
from ...views.roi_selector import RoiSelector


def on_roi_selector_destroyed(main_window, selector):
    """破棄されたROIセレクタを管理リストから除外する。"""
    # 破棄済みセレクタを管理リストから外す。
    main_window._roi_selectors = [s for s in main_window._roi_selectors if s is not selector]


def close_roi_selectors(main_window):
    """現在開いているROIセレクタをすべて閉じる。"""
    # 複数画面分のセレクタをまとめて閉じる。
    selectors = list(main_window._roi_selectors)
    main_window._roi_selectors = []
    for s in selectors:
        try:
            s.close()
        except Exception:
            pass


def cancel_roi_selection(main_window, *, announce: bool = False) -> None:
    """進行中の領域選択をキャンセルして必要ならステータス表示する。"""
    had_selectors = bool(getattr(main_window, "_roi_selectors", ()))
    close_roi_selectors(main_window)
    if announce and had_selectors:
        main_window.on_status("領域選択をキャンセルしました")


def _build_roi_selector(main_window, bounds: QRect, help_text: str, on_selected):
    """共通設定済みのROIセレクタを生成する。"""
    sel = RoiSelector(bounds=bounds, help_text=help_text, as_window=True)
    sel.roiSelected.connect(on_selected)
    # どの画面でキャンセルしても、残りのオーバーレイを必ず閉じる。
    sel.selectionCanceled.connect(lambda mw=main_window: cancel_roi_selection(mw, announce=True))
    # destroyed シグナルで逆参照を片付ける。
    sel.destroyed.connect(lambda _=None, s=sel: on_roi_selector_destroyed(main_window, s))
    return sel


def open_multi_screen_roi_selectors(
    main_window,
    help_text: str,
    on_selected,
    allowed_bounds: QRect | None = None,
):
    """画面ごとにROIセレクタを開き、選択結果を共通ハンドラへ渡す。"""
    # マルチモニタ環境では画面ごとに1つずつROIセレクタを開く。
    # allowed_bounds 指定時はその範囲に重なる部分だけオーバーレイを出す。
    close_roi_selectors(main_window)
    screens = [s for s in QGuiApplication.screens() if s is not None]
    if not screens:
        ps = QGuiApplication.primaryScreen()
        if ps is not None:
            screens = [ps]
    selectors = []
    for screen in screens:
        bounds = QRect(screen.geometry())
        if allowed_bounds is not None:
            bounds = bounds.intersected(allowed_bounds)
            if bounds.width() < 10 or bounds.height() < 10:
                continue
        sel = _build_roi_selector(main_window, bounds, help_text, on_selected)
        sel.createWinId()
        handle = sel.windowHandle()
        if handle is not None:
            handle.setScreen(screen)
        selectors.append(sel)
    if not selectors and allowed_bounds is not None:
        # 変換誤差で各画面との交差が消えた場合は、指定範囲そのものを1枚で表示する。
        sel = _build_roi_selector(main_window, QRect(allowed_bounds), help_text, on_selected)
        selectors.append(sel)
    main_window._roi_selectors = selectors
    for sel in selectors:
        sel.show()
        sel.raise_()
        sel.activateWindow()


def pick_roi_on_screen(main_window):
    """画面全体を対象にROI選択モードへ入る。"""
    # 画面選択に入る前に capture source を screen に揃える。
    if main_window._selected_capture_source() != C.CAPTURE_SOURCE_SCREEN:
        idx = main_window.combo_capture_source.findData(C.CAPTURE_SOURCE_SCREEN)
        if idx >= 0:
            main_window.combo_capture_source.setCurrentIndex(idx)
    open_multi_screen_roi_selectors(
        main_window,
        "画面上で領域をドラッグ選択（Escでキャンセル）",
        main_window.on_roi_screen_selected,
    )
    main_window.on_status("画面領域選択中…")


def on_roi_screen_selected(main_window, r: QRect):
    """画面座標で確定したROIをワーカーへ反映する。"""
    # 画面ROIは window ターゲットと排他的に扱う。
    close_roi_selectors(main_window)
    main_window.worker.set_capture_selection(target_hwnd=None, roi_rel=None, roi_abs=r)
    main_window.on_status(f"画面領域: x={r.left()} y={r.top()} w={r.width()} h={r.height()}")
    main_window._update_preview_snapshot()
    main_window._request_save_settings()


def pick_roi_in_window(main_window):
    """対象ウィンドウ内のROI選択モードへ入る。"""
    # ウィンドウ内選択に入る前に capture source を window に揃える。
    if main_window._selected_capture_source() != C.CAPTURE_SOURCE_WINDOW:
        idx = main_window.combo_capture_source.findData(C.CAPTURE_SOURCE_WINDOW)
        if idx >= 0:
            main_window.combo_capture_source.setCurrentIndex(idx)
    if not HAS_WIN32:
        QMessageBox.information(
            main_window,
            "情報",
            "この環境ではウィンドウ選択は使えません。\n画面の領域選択を使ってください。",
        )
        return
    hwnd = main_window.combo_win.currentData()
    if hwnd is None:
        QMessageBox.information(main_window, "情報", "まずターゲットウィンドウを選んでください。")
        return
    bounds_native = main_window.worker.get_window_rect(int(hwnd))
    if bounds_native is None:
        QMessageBox.warning(main_window, "警告", "ウィンドウの表示範囲を取得できませんでした。")
        return
    window_bounds_logical = main_window.worker.native_rect_to_logical(bounds_native)
    help_text = "ターゲットウィンドウ内で領域をドラッグ選択（Escでキャンセル）"
    open_multi_screen_roi_selectors(
        main_window,
        help_text,
        lambda r, h=int(hwnd), wr=QRect(bounds_native): main_window.on_roi_window_selected(
            h, wr, r
        ),
        allowed_bounds=window_bounds_logical,
    )
    main_window.on_status("ウィンドウ内領域選択中…")


def on_roi_window_selected(main_window, hwnd: int, wrect: QRect, roi_abs_logical: QRect):
    """ウィンドウ内ROIを確定し、相対座標としてワーカーへ設定する。"""
    close_roi_selectors(main_window)
    # 論理座標選択をネイティブ座標へ変換してからウィンドウ矩形と交差判定する。
    roi_abs_native = main_window.worker.logical_rect_to_native(roi_abs_logical)
    hit = roi_abs_native.intersected(wrect)
    if hit.width() < 10 or hit.height() < 10:
        main_window.on_status(
            "選択領域がターゲットウィンドウに重なっていません。もう一度選択してください。"
        )
        return

    rel = QRect(hit.left() - wrect.left(), hit.top() - wrect.top(), hit.width(), hit.height())
    main_window.worker.set_capture_selection(target_hwnd=hwnd, roi_rel=rel, roi_abs=None)
    main_window.on_status(
        f"ウィンドウ領域: rel_x={rel.left()} rel_y={rel.top()} w={rel.width()} h={rel.height()}"
    )
    main_window._update_preview_snapshot()
    main_window._request_save_settings()
