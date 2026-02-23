from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ..util import constants as C
from ..util.config import load_config, save_config
from ..util.functions import blocked_signals
from ..util.layout_state import apply_layout_state, capture_layout_state


def _layout_engine_version(cfg: dict) -> int:
    try:
        return int(cfg.get(C.CFG_LAYOUT_ENGINE_VERSION, 0))
    except Exception:
        return 0


def _stamp_layout_engine_version(cfg: dict) -> None:
    cfg[C.CFG_LAYOUT_ENGINE_VERSION] = int(C.LAYOUT_ENGINE_VERSION)


def _after_layout_apply(main_window, *, schedule_rebalance: bool = True) -> None:
    main_window.sync_window_menu_checks()
    main_window.update_placeholder()
    if schedule_rebalance:
        main_window._schedule_dock_rebalance()
    main_window._fit_window_to_desktop()
    main_window._schedule_layout_autosave()


def apply_three_dock_layout(
    main_window,
    *,
    first_name: str,
    second_name: str,
    third_name: str,
    area: Qt.DockWidgetArea = Qt.RightDockWidgetArea,
    first_split: Qt.Orientation = Qt.Vertical,
    second_split: Qt.Orientation = Qt.Horizontal,
    split_parent_is_first: bool = True,
    hide_others: bool = True,
    primary_sizes: tuple[int, int] = (640, 300),
    secondary_sizes: tuple[int, int] = (500, 500),
) -> bool:
    """Apply a generic 3-dock nested split layout.

    first_split:
        first と second の最初の分割方向。
    split_parent_is_first:
        True なら first 側を再分割、False なら second 側を再分割。
    second_split:
        上記ターゲット側を third で再分割する方向。
    """
    dock_map = getattr(main_window, "_dock_map", {})
    first = dock_map.get(first_name)
    second = dock_map.get(second_name)
    third = dock_map.get(third_name)
    if first is None or second is None or third is None:
        return False

    target_names = {first_name, second_name, third_name}
    if hide_others:
        # 既存配置を一度外してから再構築し、ネストの残骸をなくす。
        for name, dock in dock_map.items():
            if dock.isFloating():
                dock.setFloating(False)
            dock.setVisible(name in target_names)
            main_window.removeDockWidget(dock)
    else:
        for dock in (first, second, third):
            if dock.isFloating():
                dock.setFloating(False)
            main_window.removeDockWidget(dock)
            dock.setVisible(True)

    main_window.addDockWidget(area, first)
    main_window.splitDockWidget(first, second, first_split)
    split_root = first if split_parent_is_first else second
    main_window.splitDockWidget(split_root, third, second_split)
    for dock in (first, second, third):
        dock.setVisible(True)

    main_window.resizeDocks([first, second], list(primary_sizes), first_split)
    main_window.resizeDocks([split_root, third], list(secondary_sizes), second_split)
    _after_layout_apply(main_window)
    return True


def apply_default_view_layout(main_window) -> None:
    # 既定状態は色相環/散布図/HSVヒストグラムのみ表示する。
    # first=color, second=hist を縦分割した後、first 側を scatter で横分割
    # => 上段2枚 + 下段1枚
    ok = apply_three_dock_layout(
        main_window,
        first_name="dock_color",
        second_name="dock_hist",
        third_name="dock_scatter",
        area=Qt.RightDockWidgetArea,
        first_split=Qt.Vertical,
        second_split=Qt.Horizontal,
        split_parent_is_first=True,
        hide_others=True,
        primary_sizes=(640, 300),
        secondary_sizes=(500, 500),
    )
    if not ok:
        main_window.sync_window_menu_checks()


def save_current_layout_to_config(main_window, silent: bool = False) -> None:
    # 現在のドック配置を CFG_LAYOUT_CURRENT へ保存する。
    cfg = load_config()
    _stamp_layout_engine_version(cfg)
    cfg[C.CFG_LAYOUT_CURRENT] = capture_layout_state(main_window, main_window._dock_map)
    save_config(cfg)
    if not silent:
        main_window.on_status("現在の配置を保存しました")
        main_window.refresh_layout_preset_views()


def schedule_layout_autosave(main_window) -> None:
    # 起動直後や最小化中は不要保存を抑止する。
    if not main_window._layout_autosave_enabled:
        return
    if main_window.isMinimized():
        return
    main_window._layout_save_timer.start()


def apply_layout_from_config(main_window, cfg: dict) -> None:
    # レイアウト実装更新時は旧保存状態を一度リセットして既定へ戻す。
    if _layout_engine_version(cfg) != C.LAYOUT_ENGINE_VERSION:
        main_window._apply_default_view_layout()
        saved = dict(cfg)
        _stamp_layout_engine_version(saved)
        # 旧仕様で保存したプリセットは互換性がないため破棄する。
        saved[C.CFG_LAYOUT_PRESETS] = {}
        saved[C.CFG_LAYOUT_CURRENT] = capture_layout_state(main_window, main_window._dock_map)
        save_config(saved)
        return
    else:
        # 復元失敗時は安全側として既定レイアウトに戻す。
        layout = cfg.get(C.CFG_LAYOUT_CURRENT, {})
        restored = apply_layout_state(main_window, main_window._dock_map, layout)
        if not restored:
            main_window._apply_default_view_layout()
            return
    _after_layout_apply(main_window)


def refresh_layout_preset_views(main_window) -> None:
    # コンボボックスとメニューの両方を同じプリセット一覧で更新する。
    cfg = load_config()
    presets = cfg.get(C.CFG_LAYOUT_PRESETS, {})
    if not isinstance(presets, dict):
        presets = {}
    preset_names = sorted(presets.keys())

    current = main_window.combo_layout_presets.currentText()
    with blocked_signals(main_window.combo_layout_presets):
        main_window.combo_layout_presets.clear()
        for name in preset_names:
            main_window.combo_layout_presets.addItem(name)
        if current:
            idx = main_window.combo_layout_presets.findText(current)
            if idx >= 0:
                main_window.combo_layout_presets.setCurrentIndex(idx)

    main_window.presets_menu.clear()
    if not presets:
        act = main_window.presets_menu.addAction("（プリセットなし）")
        act.setEnabled(False)
    else:
        for name in preset_names:
            act = main_window.presets_menu.addAction(name)
            act.triggered.connect(lambda _checked=False, n=name: main_window.apply_layout_preset(n))


def apply_layout_preset(main_window, name: str) -> None:
    # 名前解決できたプリセットだけ適用する。
    cfg = load_config()
    presets = cfg.get(C.CFG_LAYOUT_PRESETS, {})
    if not isinstance(presets, dict):
        return
    layout = presets.get(name)
    if not isinstance(layout, dict):
        return
    restored = apply_layout_state(main_window, main_window._dock_map, layout)
    if not restored:
        main_window._apply_default_view_layout()
        return
    _after_layout_apply(main_window)
    main_window.on_status(f"プリセット適用: {name}")


def load_selected_layout_preset(main_window) -> None:
    name = main_window.combo_layout_presets.currentText().strip()
    if not name:
        return
    main_window.apply_layout_preset(name)


def save_layout_preset(main_window) -> None:
    # 入力名が空なら選択中名を使う。
    name = (
        main_window.edit_preset_name.text().strip()
        or main_window.combo_layout_presets.currentText().strip()
    )
    if not name:
        QMessageBox.information(main_window, "情報", "プリセット名を入力してください。")
        return

    cfg = load_config()
    presets = cfg.get(C.CFG_LAYOUT_PRESETS, {})
    if not isinstance(presets, dict):
        presets = {}
    presets[name] = capture_layout_state(main_window, main_window._dock_map)
    _stamp_layout_engine_version(cfg)
    cfg[C.CFG_LAYOUT_PRESETS] = presets
    cfg[C.CFG_LAYOUT_CURRENT] = presets[name]
    save_config(cfg)

    main_window.refresh_layout_preset_views()
    main_window.combo_layout_presets.setCurrentText(name)
    main_window.on_status(f"プリセット保存: {name}")


def delete_selected_layout_preset(main_window) -> None:
    # 選択名が存在するときだけ削除する。
    name = main_window.combo_layout_presets.currentText().strip()
    if not name:
        return

    cfg = load_config()
    presets = cfg.get(C.CFG_LAYOUT_PRESETS, {})
    if not isinstance(presets, dict):
        return
    if name in presets:
        del presets[name]
        cfg[C.CFG_LAYOUT_PRESETS] = presets
        save_config(cfg)
        main_window.refresh_layout_preset_views()
        main_window.on_status(f"プリセット削除: {name}")
