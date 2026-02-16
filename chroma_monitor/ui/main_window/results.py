"""Result/update handlers extracted from MainWindow for readability."""

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
    if main_window.dock_edge.isVisible():
        main_window.edge_view.update_edge(bgr_preview)
    if main_window.dock_gray.isVisible():
        main_window.gray_view.update_gray(bgr_preview)
    if main_window.dock_binary.isVisible():
        main_window.binary_view.update_binary(bgr_preview)
    if main_window.dock_ternary.isVisible():
        main_window.ternary_view.update_ternary(bgr_preview)
    if main_window.dock_saliency.isVisible():
        main_window.saliency_view.update_saliency(bgr_preview)
    if main_window.dock_focus.isVisible():
        main_window.focus_peaking_view.update_focus(bgr_preview)
    if main_window.dock_squint.isVisible():
        main_window.squint_view.update_squint(bgr_preview)
    if main_window.dock_vectorscope.isVisible():
        main_window.vectorscope_view.update_scope(bgr_preview)
        main_window._update_vectorscope_warning_label()


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
            if res.get("h_plane") is not None and main_window.dock_hist.isVisible():
                main_window.hist_h.update_from_values(res["h_plane"])
            if res.get("s_plane") is not None and main_window.dock_hist.isVisible():
                main_window.hist_s.update_from_values(res["s_plane"])
            if res.get("v_plane") is not None and main_window.dock_hist.isVisible():
                main_window.hist_v.update_from_values(res["v_plane"])
            update_image_docks_from_frame(main_window, bgr_preview)
    finally:
        main_window.worker.mark_result_consumed()
