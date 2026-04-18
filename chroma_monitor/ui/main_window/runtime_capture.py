"""キャプチャ取得元選択とウィンドウ候補同期。"""

from dataclasses import dataclass

from PySide6.QtCore import QRect

from ...capture.win32_windows import HAS_WIN32, list_windows
from ...util import constants as C
from ...util.debug_log import write_window_layout_debug_log
from ...util.qt_helpers import (
    blocked_signals,
    set_current_index_blocked,
    set_enabled_if,
    set_visible_if_changed,
)
from ...util.value_utils import safe_choice
from .runtime_common import on_status

_WINDOW_LIST_MAX_ITEMS = 500
_CAPTURE_RESTORE_UNSET = object()


@dataclass(frozen=True, slots=True)
class CaptureRestoreRequest:
    """取得元切替時に復元したい選択状態。"""

    window_title: str = ""
    window_text: str = ""
    window_roi_rel: QRect | object = _CAPTURE_RESTORE_UNSET
    screen_roi_abs: QRect | object = _CAPTURE_RESTORE_UNSET


@dataclass(frozen=True, slots=True)
class WindowComboSelection:
    """現在のコンボ選択から確定したウィンドウ選択状態。"""

    idx: int
    hwnd: int | None
    text: str


@dataclass(frozen=True, slots=True)
class WindowRefreshState:
    """一覧更新前に退避したウィンドウ選択状態。"""

    prev_hwnd: int | None
    prev_text: str
    prev_title: str
    preserved_text: str
    restore_title: str
    restore_text: str


@dataclass(frozen=True, slots=True)
class WindowRefreshResult:
    """一覧更新後に UI へ反映する結果。"""

    wins: list[tuple[int, str]]
    selected_idx: int
    announce: bool
    force: bool


@dataclass(frozen=True, slots=True)
class WindowTextCommitState:
    """入力欄確定時点のコンボ状態。"""

    text: str
    current_idx: int
    current_hwnd: int | None


@dataclass(frozen=True, slots=True)
class CapturePreflightResult:
    """現在の取得元で処理を開始できるか表す。"""

    ready: bool
    message: str | None = None


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


def _find_combo_index_by_text_hint(combo, text: str) -> int:
    """完全一致優先で検索し、無ければ一意部分一致を返す。"""
    needle = str(text).strip().casefold()
    if not needle:
        return -1
    partial_idx = -1
    for idx in range(combo.count()):
        item_text = combo.itemText(idx).casefold()
        if item_text == needle:
            return int(idx)
        if needle not in item_text:
            continue
        if partial_idx >= 0:
            return -1
        partial_idx = int(idx)
    return int(partial_idx)


def _find_combo_index_by_hints(combo, *hints: str) -> int:
    """複数ヒントを順に評価して最初に解決したインデックスを返す。"""
    for hint in hints:
        idx = _find_combo_index_by_text_hint(combo, hint)
        if idx >= 0:
            return int(idx)
    return -1


def _find_combo_index_for_text(combo, text: str, *, allow_partial: bool) -> int:
    """入力テキストから候補 index を解決する。"""
    if allow_partial:
        return _find_combo_index_by_text_hint(combo, text)
    return _find_combo_index_by_text_casefold(combo, text)


def _debug_capture_target(event: str, **fields) -> None:
    """キャプチャ対象選択周りのデバッグログを出力する。"""
    write_window_layout_debug_log(f"capture_target_{event}", **fields)


def _to_int_or(value, fallback: int = -1) -> int:
    """`value` を int へ変換し、失敗時は `fallback` を返す。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def _is_worker_capture_selection_empty(main_window) -> bool:
    """worker 側のキャプチャ選択状態が未設定なら True を返す。"""
    capture = main_window.worker.capture_selection()
    return (
        capture.target_hwnd is None
        and capture.roi_rel is None
        and capture.roi_abs is None
    )


def _has_any_capture_selection(main_window, combo) -> bool:
    """コンボまたは worker のどちらかに選択状態があれば True を返す。"""
    return (
        combo.currentData() is not None
        or int(combo.currentIndex()) >= 0
        or (not _is_worker_capture_selection_empty(main_window))
    )


def _resolve_combo_selection(combo, signal_idx: int) -> WindowComboSelection:
    """シグナル由来インデックスと現在状態から有効な選択状態を返す。"""
    sig_idx = int(signal_idx)
    idx = sig_idx if sig_idx >= 0 else int(combo.currentIndex())
    hwnd = combo.itemData(idx) if idx >= 0 else combo.currentData()
    text = combo.itemText(idx) if idx >= 0 else str(combo.currentText() or "")
    return WindowComboSelection(
        idx=int(idx),
        hwnd=None if hwnd is None else int(hwnd),
        text=str(text or ""),
    )


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


def _should_skip_window_refresh(
    combo,
    editor,
    *,
    announce: bool,
    force: bool,
) -> bool:
    """編集中は一覧更新を見送り、入力中テキストの破壊を避ける。"""
    return bool(
        (not bool(force))
        and (not announce)
        and combo.count() > 0
        and (
            (editor is not None and editor.hasFocus())
            or (combo.hasFocus() and not combo.view().isVisible())
        )
    )


def _window_refresh_state(
    combo,
    editor,
    *,
    preferred_title: str,
    preferred_text: str,
) -> WindowRefreshState:
    """一覧再構築後の復元に必要な状態を退避する。"""
    prev_hwnd = combo.currentData()
    prev_text = str(combo.currentText() or "").strip()
    prev_idx = int(combo.currentIndex())
    prev_title = ""
    if prev_idx >= 0 and combo.itemData(prev_idx) is not None:
        prev_title = str(combo.itemText(prev_idx) or "").strip()
    preserved_text = _preserved_window_editor_text(combo, editor)
    restore_text = str(preferred_text or "").strip() or prev_text
    restore_title = str(preferred_title or "").strip() or prev_title
    return WindowRefreshState(
        prev_hwnd=None if prev_hwnd is None else int(prev_hwnd),
        prev_text=prev_text,
        prev_title=prev_title,
        preserved_text=preserved_text,
        restore_title=restore_title,
        restore_text=restore_text,
    )


def _window_refresh_candidates() -> list[tuple[int, str]]:
    """現在環境で取得できるウィンドウ候補一覧を返す。"""
    return list_windows() if HAS_WIN32 else []


def _announce_window_refresh(main_window, wins: list[tuple[int, str]], *, announce: bool) -> None:
    """ウィンドウ一覧更新後の状態メッセージを反映する。"""
    if not announce:
        return
    if not HAS_WIN32:
        on_status(main_window, "この環境ではウィンドウ選択は使えません（画面の領域選択を使用）")
        return
    on_status(main_window, f"ウィンドウ {len(wins)} 件")


def _restore_window_combo_after_refresh(
    combo,
    editor,
    *,
    prev_hwnd,
    preserved_text: str,
    preferred_title: str = "",
    preferred_text: str = "",
) -> int:
    """一覧更新後コンボへ選択状態と編集テキストを復元する。"""
    live_text = str(preserved_text or "").strip()
    saved_text = str(preferred_text or "").strip()
    saved_title = str(preferred_title or "").strip()

    selected_idx = _find_combo_index_by_data(combo, prev_hwnd)
    if selected_idx < 0:
        selected_idx = _find_combo_index_by_hints(combo, live_text, saved_text, saved_title)
    combo.setCurrentIndex(int(selected_idx))
    if editor is not None:
        if live_text:
            combo.setEditText(live_text)
        elif saved_text and selected_idx < 0:
            combo.setEditText(saved_text)
        elif selected_idx < 0:
            combo.clearEditText()
    return int(selected_idx)


def _prepare_window_refresh_state(
    combo,
    editor,
    *,
    preferred_title: str,
    preferred_text: str,
) -> WindowRefreshState:
    """一覧更新前に必要な退避状態を返す。"""
    return _window_refresh_state(
        combo,
        editor,
        preferred_title=preferred_title,
        preferred_text=preferred_text,
    )


def _rebuild_window_refresh_items(combo, wins: list[tuple[int, str]]) -> None:
    """一覧更新時にコンボ項目だけを再構築する。"""
    _rebuild_window_combo_items(combo, wins)


def _restore_window_refresh_selection(
    combo,
    editor,
    state: WindowRefreshState,
) -> int:
    """一覧再構築後に退避済み選択状態を復元する。"""
    return _restore_window_combo_after_refresh(
        combo,
        editor,
        prev_hwnd=state.prev_hwnd,
        preserved_text=state.preserved_text,
        preferred_title=state.restore_title,
        preferred_text=state.restore_text,
    )


def _apply_window_refresh_result(
    main_window,
    state: WindowRefreshState,
    result: WindowRefreshResult,
) -> None:
    """更新後の debug/status/UI 同期をまとめて反映する。"""
    combo = main_window.combo_win
    selected_idx = int(result.selected_idx)
    wins = result.wins
    new_hwnd = combo.itemData(selected_idx) if selected_idx >= 0 else None
    _debug_capture_target(
        "refresh",
        count=int(len(wins)),
        prev_hwnd=state.prev_hwnd,
        new_hwnd=new_hwnd,
        selected_idx=int(selected_idx),
        preferred_title=state.restore_title,
        preferred_text=state.restore_text,
        preserved_text=str(state.preserved_text or ""),
        prev_title=state.prev_title,
        prev_text=state.prev_text,
        force=bool(result.force),
    )
    _announce_window_refresh(main_window, wins, announce=result.announce)
    sync_capture_source_ui(main_window)
    if _is_window_capture_source(main_window) and new_hwnd != state.prev_hwnd:
        on_window_changed(main_window, selected_idx)


def _current_window_text_commit_state(combo) -> WindowTextCommitState:
    """入力確定時点のテキストと現在選択を返す。"""
    current_hwnd = combo.currentData()
    return WindowTextCommitState(
        text=str(combo.currentText() or "").strip(),
        current_idx=int(combo.currentIndex()),
        current_hwnd=None if current_hwnd is None else int(current_hwnd),
    )


def _sync_window_editor_to_item_text(combo, editor, idx: int) -> None:
    """エディタ表示を指定 index の項目テキストへ揃える。"""
    if editor is None:
        return
    item_text = combo.itemText(int(idx))
    if editor.text() != item_text:
        editor.setText(item_text)


def _handle_empty_window_text_commit(main_window, combo, editor, *, text: str) -> bool:
    """空文字確定時の解除処理を行い、処理済みなら True を返す。"""
    if text:
        return False
    if _has_any_capture_selection(main_window, combo):
        _debug_capture_target("text_commit_clear")
        _clear_window_selection(main_window, combo, editor, text_to_keep=None)
    return True


def _window_text_commit_keeps_current(combo, state: WindowTextCommitState) -> bool:
    """現在選択をそのまま維持できる確定入力かを返す。"""
    return bool(
        state.current_idx >= 0
        and state.current_hwnd is not None
        and combo.itemText(state.current_idx).casefold() == state.text.casefold()
    )


def _resolved_window_text_commit_index(combo, text: str) -> int:
    """確定テキストから候補 index を解決する。"""
    return _find_combo_index_for_text(combo, text, allow_partial=True)


def _handle_unresolved_window_text_commit(
    main_window,
    combo,
    editor,
    state: WindowTextCommitState,
    *,
    resolved_idx: int,
) -> bool:
    """確定テキストが候補へ解決できない場合の処理を行う。"""
    if resolved_idx >= 0:
        return False
    if state.current_hwnd is not None or state.current_idx >= 0:
        _debug_capture_target("text_commit_no_match", text=state.text)
        _clear_window_selection(main_window, combo, editor, text_to_keep=state.text)
    return True


def _clear_window_selection(main_window, combo, editor, *, text_to_keep: str | None = None) -> None:
    """現在のウィンドウ選択を解除し、必要に応じて入力文字列を維持する。"""
    set_current_index_blocked(combo, -1)
    if editor is not None:
        if text_to_keep is None:
            combo.clearEditText()
        else:
            editor.setText(str(text_to_keep))
    on_window_changed(main_window, -1)


def _restore_window_capture_source_selection(
    main_window,
    request: CaptureRestoreRequest,
) -> WindowComboSelection:
    """設定ロード時の request からウィンドウ選択を復元する。"""
    combo = main_window.combo_win
    if HAS_WIN32 and combo.count() <= 0:
        refresh_windows(
            main_window,
            preferred_title=request.window_title,
            preferred_text=request.window_text,
        )
    elif HAS_WIN32 and combo.currentData() is None:
        idx = _find_combo_index_by_hints(
            combo,
            request.window_text,
            request.window_title,
        )
        if idx >= 0:
            set_current_index_blocked(combo, idx)
        elif request.window_text:
            editor = combo.lineEdit()
            if editor is not None and not editor.hasFocus():
                editor.setText(str(request.window_text))
    return _resolve_combo_selection(combo, combo.currentIndex())


def _apply_window_capture_source_restore(
    main_window,
    request: CaptureRestoreRequest,
) -> None:
    """ウィンドウ取得元の復元 request を worker へ適用する。"""
    selection = _restore_window_capture_source_selection(main_window, request)
    roi_rel = None
    if selection.hwnd is not None and request.window_roi_rel is not _CAPTURE_RESTORE_UNSET:
        roi_rel = None if request.window_roi_rel is None else QRect(request.window_roi_rel)
    main_window.worker.set_capture_selection(
        target_hwnd=selection.hwnd,
        roi_rel=roi_rel,
        roi_abs=None,
    )


def _apply_screen_capture_source_restore(main_window, request: CaptureRestoreRequest) -> None:
    """画面取得元の復元 request を worker へ適用する。"""
    if request.screen_roi_abs is _CAPTURE_RESTORE_UNSET:
        main_window.worker.set_capture_selection(target_hwnd=None, roi_rel=None)
        return
    main_window.worker.set_capture_selection(
        target_hwnd=None,
        roi_rel=None,
        roi_abs=None if request.screen_roi_abs is None else QRect(request.screen_roi_abs),
    )


def _clear_window_capture_selection(
    main_window,
    selection: WindowComboSelection,
    *,
    signal_idx: int,
) -> None:
    """確定済みウィンドウ選択を解除する。"""
    main_window.worker.set_capture_selection(target_hwnd=None, roi_rel=None, roi_abs=None)
    _debug_capture_target(
        "changed_none",
        signal_idx=signal_idx,
        combo_idx=selection.idx,
        combo_text=selection.text,
    )
    on_status(main_window, "ターゲット未選択（候補を選択してください）")
    _update_preview_if_enabled(main_window)
    main_window._request_save_settings()


def _commit_window_capture_selection(
    main_window,
    selection: WindowComboSelection,
    *,
    signal_idx: int,
) -> None:
    """現在のウィンドウ選択を worker と UI へ反映する。"""
    main_window.worker.set_capture_selection(target_hwnd=selection.hwnd, roi_rel=None, roi_abs=None)
    rect = main_window.worker.get_window_rect(int(selection.hwnd))
    if rect is None:
        on_status(main_window, "ターゲット設定: 取得失敗")
        main_window._request_save_settings()
        return
    on_status(
        main_window,
        (
            f"ターゲット設定: {selection.text}  "
            f"({rect.width()}x{rect.height()}) / 次にウィンドウ内領域を選択してください"
        ),
    )
    _update_preview_if_enabled(main_window)
    _debug_capture_target(
        "changed",
        signal_idx=signal_idx,
        combo_idx=selection.idx,
        hwnd=int(selection.hwnd),
        combo_text=selection.text,
    )
    main_window._request_save_settings()


def _is_window_capture_source(main_window) -> bool:
    """取得元がウィンドウモードかを返す。"""
    return selected_capture_source(main_window) == C.CAPTURE_SOURCE_WINDOW and HAS_WIN32


def _resolve_supported_capture_source(main_window) -> str:
    """環境制約を反映した有効な取得元を返す。"""
    source = selected_capture_source(main_window)
    if source != C.CAPTURE_SOURCE_WINDOW or HAS_WIN32:
        return source
    idx = main_window.combo_capture_source.findData(C.CAPTURE_SOURCE_SCREEN)
    if idx >= 0:
        set_current_index_blocked(main_window.combo_capture_source, idx)
    on_status(main_window, "この環境では画面範囲モードを使用します")
    return C.CAPTURE_SOURCE_SCREEN


def _apply_capture_source_restore_request(
    main_window,
    source: str,
    request: CaptureRestoreRequest,
) -> None:
    """取得元ごとの restore request 適用処理を振り分ける。"""
    if source == C.CAPTURE_SOURCE_WINDOW:
        _apply_window_capture_source_restore(main_window, request)
        return
    _apply_screen_capture_source_restore(main_window, request)


def refresh_windows(
    main_window,
    announce: bool = True,
    preferred_title: str = "",
    preferred_text: str = "",
    *,
    force: bool = False,
):
    """ウィンドウ候補一覧を再取得してコンボへ反映する。"""
    combo = main_window.combo_win
    editor = combo.lineEdit()
    if _should_skip_window_refresh(combo, editor, announce=announce, force=force):
        _debug_capture_target(
            "refresh_skipped_interaction",
            count=int(combo.count()),
            current_idx=int(combo.currentIndex()),
            current_text=str(combo.currentText() or ""),
            current_hwnd=combo.currentData(),
            force=bool(force),
        )
        return
    wins = _window_refresh_candidates()
    restore_state = _prepare_window_refresh_state(
        combo,
        editor,
        preferred_title=preferred_title,
        preferred_text=preferred_text,
    )
    with blocked_signals(combo):
        _rebuild_window_refresh_items(combo, wins)
        selected_idx = _restore_window_refresh_selection(combo, editor, restore_state)
    _apply_window_refresh_result(
        main_window,
        restore_state,
        WindowRefreshResult(
            wins=wins,
            selected_idx=selected_idx,
            announce=bool(announce),
            force=bool(force),
        ),
    )


def selected_capture_source(main_window) -> str:
    """UI選択から取得元種別を安全な値で返す。"""
    source = main_window.combo_capture_source.currentData()
    return safe_choice(source, C.CAPTURE_SOURCES, C.DEFAULT_CAPTURE_SOURCE)


def capture_preflight_result(main_window) -> CapturePreflightResult:
    """現在の取得設定で処理可能かどうかを返す。"""
    capture = main_window.worker.capture_selection()
    source = selected_capture_source(main_window)
    if source == C.CAPTURE_SOURCE_WINDOW and capture.target_hwnd is None:
        return CapturePreflightResult(False, "ターゲットウィンドウを選択してください")
    if source == C.CAPTURE_SOURCE_SCREEN and capture.roi_abs is None:
        return CapturePreflightResult(False, "キャプチャ領域を選択してください")
    return CapturePreflightResult(True)


def capture_preflight_message(main_window) -> str | None:
    """現在の取得設定で実行前に不足している入力があれば返す。"""
    return capture_preflight_result(main_window).message


def _capture_source_row_widget(main_window, row_attr: str, fallback_widget):
    """設定行ウィジェットがあれば優先し、無ければ本体ウィジェットを返す。"""
    row = getattr(main_window, row_attr, None)
    return row if row is not None else fallback_widget


def _update_preview_if_enabled(main_window) -> None:
    """プレビューが有効時のみスナップショットを更新する。"""
    if bool(main_window.chk_preview_window.isChecked()):
        main_window._update_preview_snapshot()


def sync_capture_source_ui(main_window):
    """取得元に応じて関連UIの表示/有効状態を切り替える。"""
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

    has_settings_window = hasattr(main_window, "_settings_window")
    if has_settings_window:
        set_visible_if_changed(main_window._row_target_settings, is_window)
        for widget in window_widgets:
            set_visible_if_changed(widget, is_window)
        for widget in screen_widgets:
            set_visible_if_changed(widget, not is_window)
    else:
        for widget in (*window_widgets, *screen_widgets):
            set_visible_if_changed(widget, False)

    can_window = is_window and HAS_WIN32
    set_enabled_if(main_window.combo_win, can_window)
    set_enabled_if(main_window.btn_pick_roi_win, can_window)
    set_enabled_if(main_window.btn_pick_roi_screen, not is_window)


def apply_capture_source(
    main_window,
    *_,
    save: bool = True,
    restore_window_title: str = "",
    restore_window_text: str = "",
    restore_window_roi_rel=_CAPTURE_RESTORE_UNSET,
    restore_screen_roi_abs=_CAPTURE_RESTORE_UNSET,
):
    """取得元切替の実処理。シグナル接続と設定復元の両方から使う。"""
    request = CaptureRestoreRequest(
        window_title=str(restore_window_title or ""),
        window_text=str(restore_window_text or ""),
        window_roi_rel=restore_window_roi_rel,
        screen_roi_abs=restore_screen_roi_abs,
    )
    source = _resolve_supported_capture_source(main_window)
    _apply_capture_source_restore_request(main_window, source, request)

    sync_capture_source_ui(main_window)
    _update_preview_if_enabled(main_window)
    if save:
        main_window._request_save_settings()


def on_window_changed(main_window, _idx: int):
    """対象ウィンドウ選択変更を worker と表示へ反映する。"""
    signal_idx = _to_int_or(_idx, fallback=-1)
    if not _is_window_capture_source(main_window):
        _debug_capture_target(
            "changed_ignored_non_window_source",
            signal_idx=signal_idx,
            capture_source=str(selected_capture_source(main_window) or ""),
            has_win32=bool(HAS_WIN32),
        )
        return
    combo = main_window.combo_win
    selection = _resolve_combo_selection(combo, signal_idx)
    if selection.hwnd is None:
        _clear_window_capture_selection(main_window, selection, signal_idx=signal_idx)
        return
    _commit_window_capture_selection(main_window, selection, signal_idx=signal_idx)


def on_window_index_activated(main_window, _idx: int):
    """プルダウン選択確定時にターゲット反映を強制する。"""
    combo = main_window.combo_win
    idx = int(combo.currentIndex())
    signal_idx = _to_int_or(_idx, fallback=-1)
    _debug_capture_target(
        "activated_signal",
        signal_idx=signal_idx,
        combo_idx=idx,
        combo_text=str(combo.currentText() or ""),
        combo_hwnd=combo.currentData(),
    )
    on_window_changed(main_window, idx)


def on_window_text_activated(main_window, text: str):
    """テキスト確定経路でもターゲット反映を行う。"""
    combo = main_window.combo_win
    idx = int(combo.currentIndex())
    _debug_capture_target(
        "text_activated_signal",
        text=str(text or ""),
        combo_idx=idx,
        combo_text=str(combo.currentText() or ""),
        combo_hwnd=combo.currentData(),
    )
    if idx >= 0 and combo.itemData(idx) is not None:
        on_window_changed(main_window, idx)
    else:
        on_window_text_committed(main_window)


def on_window_popup_row_selected(main_window, model_index):
    """ポップアップ行クリック時に選択を確定して反映する。"""
    combo = main_window.combo_win
    row = -1
    try:
        if model_index is not None:
            row = int(model_index.row())
    except (AttributeError, TypeError, ValueError):
        row = -1
    if row < 0:
        row = int(combo.currentIndex())
    hwnd = combo.itemData(row) if row >= 0 else None
    text = combo.itemText(row) if row >= 0 else str(combo.currentText() or "")
    _debug_capture_target(
        "popup_row_selected",
        row=row,
        hwnd=hwnd,
        text=str(text or ""),
    )
    if row >= 0:
        set_current_index_blocked(combo, row)
    on_window_changed(main_window, row)


def on_window_text_changed(main_window, text: str):
    """テキスト変化時に候補と一致すれば選択を確定する。"""
    if not _is_window_capture_source(main_window):
        return
    combo = main_window.combo_win
    if combo.currentData() is not None:
        return
    normalized = str(text or "").strip()
    if not normalized:
        return
    idx = _find_combo_index_for_text(combo, normalized, allow_partial=False)
    if idx < 0:
        return
    hwnd = combo.itemData(idx)
    if hwnd is None:
        return
    _debug_capture_target(
        "text_changed_resolved",
        text=normalized,
        idx=idx,
        hwnd=hwnd,
    )
    set_current_index_blocked(combo, idx)
    on_window_changed(main_window, idx)


def on_window_text_edited(main_window, text: str):
    """対象ウィンドウ入力欄の編集中イベントを処理する。"""
    if not _is_window_capture_source(main_window):
        return
    if str(text).strip():
        return
    combo = main_window.combo_win
    editor = combo.lineEdit()
    if (
        combo.currentData() is None
        and int(combo.currentIndex()) < 0
        and _is_worker_capture_selection_empty(main_window)
    ):
        return
    _debug_capture_target("text_edited_clear", text=str(text or ""))
    _clear_window_selection(main_window, combo, editor, text_to_keep="")


def on_window_text_committed(main_window):
    """編集可能コンボ入力を既存候補へ解決して選択確定する。"""
    if not _is_window_capture_source(main_window):
        return
    combo = main_window.combo_win
    editor = combo.lineEdit()
    state = _current_window_text_commit_state(combo)
    if _handle_empty_window_text_commit(main_window, combo, editor, text=state.text):
        return

    if _window_text_commit_keeps_current(combo, state):
        _sync_window_editor_to_item_text(combo, editor, state.current_idx)
        _debug_capture_target(
            "text_commit_keep_current",
            text=state.text,
            idx=state.current_idx,
            hwnd=state.current_hwnd,
        )
        return

    idx = _resolved_window_text_commit_index(combo, state.text)
    if _handle_unresolved_window_text_commit(
        main_window,
        combo,
        editor,
        state,
        resolved_idx=idx,
    ):
        return

    if idx == state.current_idx and state.current_hwnd is not None:
        _sync_window_editor_to_item_text(combo, editor, idx)
        _debug_capture_target("text_commit_same", text=state.text, idx=idx)
        return

    set_current_index_blocked(combo, idx)
    _debug_capture_target("text_commit_select", text=state.text, idx=idx, hwnd=combo.itemData(idx))
    on_window_changed(main_window, idx)
