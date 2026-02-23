"""Result/update handlers extracted from MainWindow for readability."""

import cv2
import numpy as np

from ...util.functions import render_top_color_bar, top_hue_bars


def refresh_top_color_bar(main_window) -> None:
    # 表示対象がないときはバーを消してキャッシュキーも初期化する。
    bars = getattr(main_window, "_last_top_bars", None)
    if not bars:
        main_window._top_bar_render_key = None
        main_window.top_colors_bar.clear()
        return

    def _bar_key_item(item):
        if len(item) == 3:
            name, ratio, color = item
        else:
            name, ratio, color = "", item[0], item[1]
        return (
            str(name),
            round(float(ratio), 6),
            tuple(int(c) for c in color),
        )

    render_key = (
        int(main_window.top_colors_bar.width()),
        int(main_window.top_colors_bar.height()),
        tuple(_bar_key_item(item) for item in bars),
    )
    # 前回描画と同じ条件なら再レンダリングを省略する。
    if render_key == getattr(main_window, "_top_bar_render_key", None):
        return
    main_window._top_bar_render_key = render_key
    main_window.top_colors_bar.setPixmap(
        render_top_color_bar(
            bars,
            width=main_window.top_colors_bar.width(),
            height=main_window.top_colors_bar.height(),
        )
    )


def update_image_docks_from_frame(main_window, bgr_preview):
    # 可視ドックだけ更新して不要な画像処理を避ける。
    if bgr_preview is None:
        return
    for dock, update_fn, after_fn in getattr(main_window, "_image_update_targets", ()):
        if not dock.isVisible():
            continue
        update_fn(bgr_preview)
        if after_fn is not None:
            after_fn()


def on_result(main_window, res: dict):
    # 例外時でも inflight フラグを解除するため finally で終端する。
    try:
        bgr_preview = res.get("bgr_preview")
        if main_window.preview_window.isVisible() and bgr_preview is not None:
            main_window.preview_window.update_preview(bgr_preview)

        # graph_update が False のときはグラフ系更新をスキップする。
        if res["graph_update"]:
            if res["hist"] is not None and main_window.dock_color.isVisible():
                main_window.wheel.update_hist(res["hist"])
                bars = res.get("top_colors")
                if bars is None:
                    _, bars = top_hue_bars(res["hist"])
                main_window._last_top_bars = bars
                refresh_top_color_bar(main_window)
                main_window.lbl_warmcool.setText(
                    "暖色: "
                    f"{res['warm_ratio']*100:.1f}%   "
                    f"寒色: {res['cool_ratio']*100:.1f}%   "
                    f"その他: {res.get('other_ratio', 0)*100:.1f}%"
                )
            if (
                res["sv"] is not None
                and res["rgb"] is not None
                and main_window.dock_scatter.isVisible()
            ):
                main_window.scatter.update_scatter(res["sv"], res["rgb"])
            if main_window.dock_hist.isVisible():
                h_hist = res.get("h_hist")
                s_hist = res.get("s_hist")
                v_hist = res.get("v_hist")
                h_plane = res.get("h_plane")
                s_plane = res.get("s_plane")
                v_plane = res.get("v_plane")
                need_h_fallback = h_hist is None and h_plane is None
                need_s_fallback = s_hist is None and s_plane is None
                need_v_fallback = v_hist is None and v_plane is None
                # 何らかの理由でヒスト/平面データが欠けた場合は、プレビュー画像から補完して表示欠落を防ぐ。
                if (
                    (need_h_fallback or need_s_fallback or need_v_fallback)
                    and bgr_preview is not None
                    and bgr_preview.size > 0
                ):
                    try:
                        h_full, s_full, v_full = cv2.split(
                            cv2.cvtColor(bgr_preview, cv2.COLOR_BGR2HSV)
                        )
                        if need_h_fallback:
                            h_hist = np.bincount(h_full[s_full > 0].reshape(-1), minlength=180)[
                                :180
                            ].astype(np.int64)
                        if need_s_fallback:
                            s_hist = np.bincount(s_full.reshape(-1), minlength=256)[:256].astype(
                                np.int64
                            )
                        if need_v_fallback:
                            v_hist = np.bincount(v_full.reshape(-1), minlength=256)[:256].astype(
                                np.int64
                            )
                    except Exception:
                        pass
                if h_hist is not None:
                    main_window.hist_h.update_from_hist(h_hist)
                elif h_plane is not None:
                    main_window.hist_h.update_from_values(h_plane)
                if s_hist is not None:
                    main_window.hist_s.update_from_hist(s_hist)
                elif s_plane is not None:
                    main_window.hist_s.update_from_values(s_plane)
                if v_hist is not None:
                    main_window.hist_v.update_from_hist(v_hist)
                elif v_plane is not None:
                    main_window.hist_v.update_from_values(v_plane)
                # H/S/V のY軸上限を揃えて、チャネル間の相対比較をしやすくする。
                shared_max_y = max(
                    int(main_window.hist_h.bucketed_max()),
                    int(main_window.hist_s.bucketed_max()),
                    int(main_window.hist_v.bucketed_max()),
                )
                for hist_view in (main_window.hist_h, main_window.hist_s, main_window.hist_v):
                    hist_view.set_shared_max_y(shared_max_y if shared_max_y > 0 else None)
            update_image_docks_from_frame(main_window, bgr_preview)
    finally:
        main_window.worker.mark_result_consumed()
