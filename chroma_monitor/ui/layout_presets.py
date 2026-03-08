"""レイアウトプリセットの管理処理。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ..util import constants as C
from ..util.config import load_config, save_config
from ..util.layout_state import apply_layout_state, capture_layout_state, restore_layout_geometry
from ..util.qt_helpers import blocked_signals
from ..util.value_utils import safe_int

_LAYOUT_ENGINE_VERSION = 2


def _stamp_layout_engine_version(cfg: dict) -> None:
    """設定辞書に現行レイアウト実装バージョンを記録する。"""
    cfg[C.CFG_LAYOUT_ENGINE_VERSION] = int(_LAYOUT_ENGINE_VERSION)


def _layout_presets_map(cfg: dict) -> dict:
    """設定辞書からレイアウトプリセット辞書を安全に取り出す。"""
    presets = cfg.get(C.CFG_LAYOUT_PRESETS, {})
    if not isinstance(presets, dict):
        return {}
    return presets


def _load_cfg_with_presets() -> tuple[dict, dict]:
    """設定本体とプリセット辞書を同時に取得する。"""
    cfg = load_config()
    return cfg, _layout_presets_map(cfg)


def _apply_layout_or_default(main_window, layout: dict) -> bool:
    """レイアウト適用を試し、失敗時は既定レイアウトへ戻す。"""
    restored = apply_layout_state(main_window, main_window._dock_map, layout)
    if not restored:
        main_window._apply_default_view_layout()
        return False
    _after_layout_apply(main_window, applied_layout=layout)
    return True


def _after_layout_apply(
    main_window,
    *,
    applied_layout: dict | None = None,
    schedule_rebalance: bool = True,
) -> None:
    """レイアウト適用後に必要なUI同期と保存予約を行う。"""
    main_window.sync_window_menu_checks()
    main_window.update_placeholder()
    if applied_layout is not None:
        # 適用前の最小サイズ制約で geometry 復元が大きい方へ丸められることがある。
        # placeholder 同期後に現在の最小サイズで再適用し、保存済みの縮小サイズを戻す。
        restore_layout_geometry(main_window, applied_layout)
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
    """3ドック構成を共通手順で再構築する。"""
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
    """標準の初期ビュー配置を適用する。"""
    # 既定状態は色相環/散布図/配色比率のみ表示する。
    # first=color, second=color_band を縦分割した後、first 側を scatter で横分割
    # => 上段2枚 + 下段1枚
    ok = apply_three_dock_layout(
        main_window,
        first_name="dock_color",
        second_name="dock_color_band",
        third_name="dock_scatter",
        area=Qt.RightDockWidgetArea,
        first_split=Qt.Vertical,
        second_split=Qt.Horizontal,
        split_parent_is_first=True,
        hide_others=True,
        primary_sizes=(620, 320),
        secondary_sizes=(500, 500),
    )
    if not ok:
        main_window.sync_window_menu_checks()


def save_current_layout_to_config(main_window, silent: bool = False) -> None:
    """現在レイアウトを設定へ保存する。"""
    # 現在のドック配置を layout_current へ保存する。
    cfg = load_config()
    _stamp_layout_engine_version(cfg)
    cfg[C.CFG_LAYOUT_CURRENT] = capture_layout_state(main_window, main_window._dock_map)
    save_config(cfg)
    if not silent:
        main_window.on_status("現在の配置を保存しました")
        main_window.refresh_layout_preset_views()


def schedule_layout_autosave(main_window) -> None:
    """条件を満たすときだけ遅延レイアウト保存を予約する。"""
    # 起動直後や最小化中は不要保存を抑止する。
    if not main_window._layout_autosave_enabled:
        return
    if main_window.isMinimized():
        return
    main_window._layout_save_timer.start()


def apply_layout_from_config(main_window, cfg: dict) -> None:
    """設定に保存されたレイアウトを読み込み適用する。"""
    # レイアウト実装更新時は旧保存状態を一度リセットして既定へ戻す。
    loaded_version = safe_int(cfg.get(C.CFG_LAYOUT_ENGINE_VERSION, 0), 0)
    if loaded_version != _LAYOUT_ENGINE_VERSION:
        main_window._apply_default_view_layout()
        saved = dict(cfg)
        _stamp_layout_engine_version(saved)
        # 旧仕様で保存したプリセットは互換性がないため破棄する。
        saved[C.CFG_LAYOUT_PRESETS] = {}
        saved[C.CFG_LAYOUT_CURRENT] = capture_layout_state(main_window, main_window._dock_map)
        save_config(saved)
        return
    # 復元失敗時は安全側として既定レイアウトに戻す。
    layout = cfg.get(C.CFG_LAYOUT_CURRENT, {})
    _apply_layout_or_default(main_window, layout)


def refresh_layout_preset_views(main_window) -> None:
    """プリセット一覧UIを設定内容で再構築する。"""
    # コンボボックスとメニューの両方を同じプリセット一覧で更新する。
    _, presets = _load_cfg_with_presets()
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
    """指定名のプリセットを読み込み適用する。"""
    # 名前解決できたプリセットだけ適用する。
    _, presets = _load_cfg_with_presets()
    layout = presets.get(name)
    if not isinstance(layout, dict):
        return
    if not _apply_layout_or_default(main_window, layout):
        return
    main_window.on_status(f"プリセット適用: {name}")


def load_selected_layout_preset(main_window) -> None:
    """コンボボックスで選択中のプリセットを適用する。"""
    name = main_window.combo_layout_presets.currentText().strip()
    if not name:
        return
    main_window.apply_layout_preset(name)


def save_layout_preset(main_window) -> None:
    """現在の配置を指定名でプリセット保存する。"""
    # 入力名が空なら選択中名を使う。
    name = (
        main_window.edit_preset_name.text().strip()
        or main_window.combo_layout_presets.currentText().strip()
    )
    if not name:
        QMessageBox.information(main_window, "情報", "プリセット名を入力してください。")
        return

    cfg, presets = _load_cfg_with_presets()
    presets[name] = capture_layout_state(main_window, main_window._dock_map)
    _stamp_layout_engine_version(cfg)
    cfg[C.CFG_LAYOUT_PRESETS] = presets
    cfg[C.CFG_LAYOUT_CURRENT] = presets[name]
    save_config(cfg)

    main_window.refresh_layout_preset_views()
    main_window.combo_layout_presets.setCurrentText(name)
    main_window.on_status(f"プリセット保存: {name}")


def delete_selected_layout_preset(main_window) -> None:
    """選択中プリセットを設定から削除する。"""
    # 選択名が存在するときだけ削除する。
    name = main_window.combo_layout_presets.currentText().strip()
    if not name:
        return

    cfg, presets = _load_cfg_with_presets()
    if name in presets:
        del presets[name]
    cfg[C.CFG_LAYOUT_PRESETS] = presets
    save_config(cfg)
    main_window.refresh_layout_preset_views()
    main_window.on_status(f"プリセット削除: {name}")
