from PySide6.QtWidgets import QMessageBox

from ..util import constants as C
from ..util.config import load_config, save_config
from ..util.functions import blocked_signals
from ..util.layout_state import apply_layout_state, capture_layout_state


def apply_default_view_layout(main_window) -> None:
    # 既定状態は全ビュー非表示（プレースホルダ表示）にする。
    for dock in main_window._dock_map.values():
        dock.setVisible(False)
    main_window.sync_window_menu_checks()


def save_current_layout_to_config(main_window, silent: bool = False) -> None:
    # 現在のドック配置を CFG_LAYOUT_CURRENT へ保存する。
    cfg = load_config()
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
    # 復元失敗時は安全側として既定レイアウトに戻す。
    layout = cfg.get(C.CFG_LAYOUT_CURRENT, {})
    restored = apply_layout_state(main_window, main_window._dock_map, layout)
    if not restored:
        main_window._apply_default_view_layout()
    main_window.sync_window_menu_checks()
    main_window.update_placeholder()
    main_window._fit_window_to_desktop()
    main_window._schedule_layout_autosave()


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
    apply_layout_state(main_window, main_window._dock_map, layout)
    main_window.sync_window_menu_checks()
    main_window.update_placeholder()
    main_window._fit_window_to_desktop()
    main_window._schedule_layout_autosave()
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
