"""ドック再配置・再バランス補助。"""

from PySide6.QtCore import QRect, QSize, Qt

from .window_layout_common import (
    _REBALANCE_CHAIN_TOUCH_TOLERANCE_PX,
    _REBALANCE_COLUMN_W_TOLERANCE_PX,
    _REBALANCE_COLUMN_X_TOLERANCE_PX,
    _REBALANCE_HEIGHT_CHANGE_THRESHOLD_PX,
)


def _capture_dock_geometry_snapshot(main_window) -> dict[str, QRect]:
    """可視・ドック内ウィジェットの幾何情報を取得する。"""
    snapshot: dict[str, QRect] = {}
    for name, dock in getattr(main_window, "_dock_map", {}).items():
        if dock is None or not dock.isVisible() or dock.isFloating():
            continue
        if main_window.dockWidgetArea(dock) == Qt.NoDockWidgetArea:
            continue
        geom = dock.geometry()
        if not geom.isValid() or geom.width() <= 0 or geom.height() <= 0:
            continue
        snapshot[name] = QRect(geom)
    return snapshot


def _dock_entries_from_snapshot(main_window, snapshot: dict[str, QRect]):
    """再配分計算用に `(name, dock, geometry)` エントリを抽出する。"""
    entries = []
    for name, geom in snapshot.items():
        dock = getattr(main_window, "_dock_map", {}).get(name)
        if dock is None:
            continue
        entries.append((name, dock, geom))
    entries.sort(key=lambda item: (item[2].x(), item[2].y()))
    return entries


def _group_entries_into_columns(entries):
    """X座標/幅が近いエントリを同一列としてグルーピングする。"""
    columns: list[dict] = []
    for entry in entries:
        geom = entry[2]
        attached = False
        for col in columns:
            if (
                abs(geom.x() - col["x"]) <= _REBALANCE_COLUMN_X_TOLERANCE_PX
                and abs(geom.width() - col["w"]) <= _REBALANCE_COLUMN_W_TOLERANCE_PX
            ):
                col["items"].append(entry)
                count = len(col["items"])
                col["x"] = int(round((col["x"] * (count - 1) + geom.x()) / float(count)))
                col["w"] = int(round((col["w"] * (count - 1) + geom.width()) / float(count)))
                attached = True
                break
        if not attached:
            columns.append({"x": geom.x(), "w": geom.width(), "items": [entry]})
    return columns


def _build_vertical_chain(items):
    """列内アイテムから上下連結チェーンを抽出する。"""
    sorted_items = sorted(items, key=lambda item: item[2].y())
    chain = []
    last_bottom = None
    for item in sorted_items:
        geom = item[2]
        if last_bottom is None or geom.y() >= (last_bottom - _REBALANCE_CHAIN_TOUCH_TOLERANCE_PX):
            chain.append(item)
            last_bottom = geom.bottom()
            continue
        if geom.height() > chain[-1][2].height():
            chain[-1] = item
            last_bottom = geom.bottom()
    return chain


def _vertical_dock_chains(main_window, snapshot: dict[str, QRect]):
    """縦連結しているドック群をチェーン単位で抽出する。"""
    entries = _dock_entries_from_snapshot(main_window, snapshot)
    columns = _group_entries_into_columns(entries)
    chains = []
    for col in columns:
        chain = _build_vertical_chain(col["items"])
        if len(chain) >= 3:
            chains.append(chain)
    return chains


def schedule_dock_rebalance(main_window) -> None:
    """ドック再バランス処理をタイマーで予約する。"""
    if not hasattr(main_window, "_dock_rebalance_timer"):
        return
    if main_window.isMinimized():
        return
    main_window._dock_rebalance_timer.start()


def _update_rebalance_baseline(main_window, snapshot: dict[str, QRect], main_size: QSize) -> None:
    """次回比較用の再配分基準スナップショットを更新する。"""
    main_window._dock_geometry_snapshot = snapshot
    main_window._dock_rebalance_last_main_size = main_size


def _rebalance_pivot_info(changed: list[bool]) -> tuple[int, list[int]] | None:
    """変更フラグ列から再配分対象ペアと非隣接インデックスを求める。"""
    pivot = next((idx for idx in range(len(changed) - 1) if changed[idx]), None)
    if pivot is None:
        return None
    non_adjacent = [idx for idx in range(len(changed)) if idx not in (pivot, pivot + 1)]
    if not any(changed[idx] for idx in non_adjacent):
        return None
    return pivot, non_adjacent


def _rebalance_remaining_height(
    *,
    mins: list[int],
    targets: list[int],
    non_adjacent: list[int],
    total_height: int,
    pair_min: int,
) -> int | None:
    """非隣接分を固定した後、ペアへ割り当て可能な残り高さを返す。"""
    fixed_height = int(sum(targets[idx] for idx in non_adjacent))
    remain = int(total_height) - fixed_height
    if remain >= pair_min:
        return remain
    shortage = pair_min - remain
    for idx in reversed(non_adjacent):
        reducible = max(0, targets[idx] - mins[idx])
        take = min(reducible, shortage)
        targets[idx] -= take
        shortage -= take
        if shortage <= 0:
            break
    fixed_height = int(sum(targets[idx] for idx in non_adjacent))
    remain = int(total_height) - fixed_height
    if remain < pair_min:
        return None
    return remain


def _calculate_rebalance_targets_for_chain(chain, previous_snapshot: dict[str, QRect]):
    """1チェーン分の再配分先高さを計算し、必要時のみ返す。"""
    names = [item[0] for item in chain]
    docks = [item[1] for item in chain]
    if any(name not in previous_snapshot for name in names):
        return None

    cur_heights = [int(item[2].height()) for item in chain]
    prev_heights = [int(previous_snapshot[name].height()) for name in names]
    changed = [
        abs(c - p) >= _REBALANCE_HEIGHT_CHANGE_THRESHOLD_PX
        for c, p in zip(cur_heights, prev_heights)
    ]
    if sum(changed) < 3:
        return None

    pivot_info = _rebalance_pivot_info(changed)
    if pivot_info is None:
        return None
    pivot, non_adjacent = pivot_info

    mins = [max(1, int(dock.minimumHeight())) for dock in docks]
    targets = list(cur_heights)
    for idx in non_adjacent:
        targets[idx] = max(mins[idx], int(prev_heights[idx]))

    total_height = int(sum(cur_heights))
    pair_min = mins[pivot] + mins[pivot + 1]
    remain = _rebalance_remaining_height(
        mins=mins,
        targets=targets,
        non_adjacent=non_adjacent,
        total_height=total_height,
        pair_min=pair_min,
    )
    if remain is None:
        return None

    w0 = max(1, cur_heights[pivot])
    w1 = max(1, cur_heights[pivot + 1])
    pair0 = int(round(remain * (w0 / float(w0 + w1))))
    pair0 = max(mins[pivot], min(pair0, remain - mins[pivot + 1]))
    pair1 = remain - pair0
    targets[pivot] = pair0
    targets[pivot + 1] = pair1
    if targets == cur_heights:
        return None
    return docks, targets


def rebalance_dock_layout(main_window) -> None:
    """縦積みドックの高さ連動を抑えるための再配分を行う。"""
    if getattr(main_window, "_dock_rebalance_running", False):
        return

    current_snapshot = _capture_dock_geometry_snapshot(main_window)
    previous_snapshot = getattr(main_window, "_dock_geometry_snapshot", {})
    if len(current_snapshot) < 3:
        _update_rebalance_baseline(main_window, current_snapshot, main_window.size())
        return
    main_size = main_window.size()
    last_main_size = getattr(main_window, "_dock_rebalance_last_main_size", None)

    if (
        not previous_snapshot
        or not current_snapshot
        or (last_main_size is not None and main_size != last_main_size)
    ):
        _update_rebalance_baseline(main_window, current_snapshot, main_size)
        return

    adjusted = False
    for chain in _vertical_dock_chains(main_window, current_snapshot):
        target = _calculate_rebalance_targets_for_chain(chain, previous_snapshot)
        if target is None:
            continue
        docks, targets = target

        main_window._dock_rebalance_running = True
        try:
            main_window.resizeDocks(docks, targets, Qt.Vertical)
        finally:
            main_window._dock_rebalance_running = False
        adjusted = True
        break

    if adjusted:
        current_snapshot = _capture_dock_geometry_snapshot(main_window)
    _update_rebalance_baseline(main_window, current_snapshot, main_size)
