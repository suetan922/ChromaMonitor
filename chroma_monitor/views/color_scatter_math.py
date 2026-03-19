"""色相環/散布図で共有する純粋計算寄りのヘルパー。"""

from dataclasses import dataclass
import math

import cv2
import numpy as np

from ..util import constants as C


@dataclass(frozen=True, slots=True)
class ScatterRenderConfig:
    """散布図ラスタ生成に必要な最小設定。"""

    triangle_mode: bool
    render_mode: str
    need_rgb_for_render: bool
    hue_filter_enabled: bool
    hue_center: int
    hue_half_width: int


def build_hue180_to_munsell40_weights(dst_bins: int) -> np.ndarray:
    """HSV180ビンをマンセル色相へ再配分する重み行列を作る。"""
    src_bins = 180
    src_step = 360.0 / float(src_bins)
    dst_step = 360.0 / float(dst_bins)

    weights = np.zeros((dst_bins, src_bins), dtype=np.float32)
    for src_idx in range(src_bins):
        src_start = src_idx * src_step
        src_end = src_start + src_step
        pos = src_start
        while pos < src_end - 1e-9:
            dst_idx = int(math.floor(pos / dst_step)) % dst_bins
            dst_end = (math.floor(pos / dst_step) + 1.0) * dst_step
            overlap = min(src_end, dst_end) - pos
            if overlap <= 0.0:
                break
            weights[dst_idx, src_idx] += float(overlap / src_step)
            pos += overlap

    col_sum = np.sum(weights, axis=0, keepdims=True)
    col_sum[col_sum <= 0.0] = 1.0
    return (weights / col_sum).astype(np.float32)


def normalize_signed_delta_deg(delta_deg: float) -> float:
    """角度差を -180..180 の範囲へ正規化する。"""
    return (float(delta_deg) + 180.0) % 360.0 - 180.0


def normalize_rotation_deg(rotation_deg: float) -> float:
    """回転角を -180..180 の範囲へ正規化する。"""
    return (float(rotation_deg) + 180.0) % 360.0 - 180.0


def point_angle_deg(px: int, py: int, cx: int, cy: int) -> float:
    """中心基準の点座標から角度(度)を算出する。"""
    return math.degrees(math.atan2(float(cy - py), float(px - cx))) % 360.0


def guide_radius(inner_r: int, *, radius_ratio: float) -> int:
    """色彩調和ガイド描画半径を返す。"""
    return max(8, int(round(int(inner_r) * float(radius_ratio))))


def hue_offset_to_angle_deg(
    hue_deg: float,
    *,
    guide_rotation_deg: float,
    red_reference_deg: float,
    direction_sign: float,
) -> float:
    """色相オフセットを画面上の絶対角度へ変換する。"""
    return (
        float(red_reference_deg)
        + float(guide_rotation_deg)
        + float(direction_sign) * float(hue_deg)
    ) % 360.0


def guide_points(
    cx: int,
    cy: int,
    inner_r: int,
    *,
    guide_type: str,
    guide_rotation_deg: float,
    guide_offsets_deg: dict[str, tuple[float, ...]],
    radius_ratio: float,
    red_reference_deg: float,
    direction_sign: float,
) -> list[tuple[int, int]]:
    """現在ガイド種別に対応する頂点座標群を返す。"""
    offsets = guide_offsets_deg.get(str(guide_type))
    if not offsets:
        return []
    radius = guide_radius(inner_r, radius_ratio=radius_ratio)
    points: list[tuple[int, int]] = []
    for deg in offsets:
        angle = math.radians(
            hue_offset_to_angle_deg(
                deg,
                guide_rotation_deg=guide_rotation_deg,
                red_reference_deg=red_reference_deg,
                direction_sign=direction_sign,
            )
        )
        x = int(round(int(cx) + math.cos(angle) * radius))
        y = int(round(int(cy) - math.sin(angle) * radius))
        points.append((x, y))
    return points


def scatter_render_mode_needs_rgb(render_mode: str) -> bool:
    """描画モードが RGB を必要とするか返す。"""
    return str(render_mode) != C.SCATTER_RENDER_MODE_HEATMAP


def munsell_hist(hist: np.ndarray, weights: np.ndarray, *, dst_bins: int) -> np.ndarray:
    """HSV180ビンからマンセル色相数へ再サンプリングしたヒストグラムを返す。"""
    src = np.asarray(hist, dtype=np.float32)
    if src.size != 180:
        return np.zeros(dst_bins, dtype=np.float32)
    return (weights @ src).astype(np.float32)


def compute_scatter_xy(sv_arr: np.ndarray, *, triangle_mode: bool) -> tuple[np.ndarray, np.ndarray]:
    """S/V配列を散布図座標(x,y)へ変換する。"""
    s = np.clip(sv_arr[:, 0].astype(np.int32), 0, 255)
    v = np.clip(sv_arr[:, 1].astype(np.int32), 0, 255)
    if triangle_mode:
        prod = s * v
        x = np.clip(prod // 255, 0, 255).astype(np.int32)
        y = np.clip(v - (prod // 510), 0, 255).astype(np.int32)
        return x, y
    return s, v


def to_rgb_u8(rgb_arr: np.ndarray, n: int) -> np.ndarray:
    """RGB配列を先頭n件のuint8連続配列へ正規化する。"""
    rgb_view = rgb_arr[:n, :3]
    if rgb_view.dtype == np.uint8:
        return np.ascontiguousarray(rgb_view)
    return np.clip(rgb_view, 0, 255).astype(np.uint8, copy=False)


def four_neighborhood_flat_indices(
    x: np.ndarray,
    y: np.ndarray,
    *,
    triangle_mode: bool = False,
    dtype: np.dtype = np.int32,
) -> np.ndarray:
    """(x, y) の4近傍セルを 256x256 画像の flat index で返す。"""
    n = int(x.size)
    if n <= 0:
        return np.empty((0,), dtype=dtype)
    xx0 = np.clip(x, 0, 255)
    xx1 = np.clip(x + 1, 0, 255)
    yy0 = np.clip(y, 0, 255)
    yy1 = np.clip(y + 1, 0, 255)

    if triangle_mode:
        y0f = yy0.astype(np.float32)
        y1f = yy1.astype(np.float32)
        x_max0 = np.where(
            yy0 <= 128,
            y0f * (255.0 / 128.0),
            (255.0 - y0f) * (255.0 / 127.0),
        )
        x_max1 = np.where(
            yy1 <= 128,
            y1f * (255.0 / 128.0),
            (255.0 - y1f) * (255.0 / 127.0),
        )
        x_max0_i = np.clip(np.floor(x_max0).astype(np.int32), 0, 255)
        x_max1_i = np.clip(np.floor(x_max1).astype(np.int32), 0, 255)
        xx0_y0 = np.minimum(xx0, x_max0_i)
        xx1_y0 = np.minimum(xx1, x_max0_i)
        xx0_y1 = np.minimum(xx0, x_max1_i)
        xx1_y1 = np.minimum(xx1, x_max1_i)
    else:
        xx0_y0 = xx0
        xx1_y0 = xx1
        xx0_y1 = xx0
        xx1_y1 = xx1

    out = np.empty((n * 4,), dtype=np.int32)
    out[0:n] = (yy0 << 8) + xx0_y0
    out[n : 2 * n] = (yy0 << 8) + xx1_y0
    out[2 * n : 3 * n] = (yy1 << 8) + xx0_y1
    out[3 * n : 4 * n] = (yy1 << 8) + xx1_y1
    return out.astype(dtype, copy=False)


def extract_hue_from_rgb(rgb_u8: np.ndarray) -> np.ndarray:
    """RGB配列から色相(H)を推定して返す。"""
    if rgb_u8.size == 0:
        return np.empty((0,), dtype=np.int16)
    bgr = rgb_u8[:, ::-1].reshape((-1, 1, 3))
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return hsv[:, 0, 0].astype(np.int16, copy=False)


def apply_hue_filter_mask(
    h_arr: np.ndarray,
    *,
    center: int,
    half_width: int,
) -> np.ndarray:
    """中心色相からの円環距離でフィルターマスクを生成する。"""
    if h_arr.size == 0:
        return np.zeros((0,), dtype=bool)
    diff = np.abs(h_arr.astype(np.int16, copy=False) - int(center))
    wrap = 180 - diff
    dist = np.minimum(diff, wrap)
    return dist <= int(half_width)


def render_scatter_dominant(
    x: np.ndarray,
    y: np.ndarray,
    rgb_u8: np.ndarray,
    *,
    triangle_mode: bool,
) -> np.ndarray:
    """同一セルの最頻色で散布図ラスタを生成する。"""
    out = np.zeros((256 * 256, 4), dtype=np.uint8)
    if x.size == 0 or y.size == 0 or rgb_u8.size == 0:
        return out.reshape((256, 256, 4))

    flat_idx = four_neighborhood_flat_indices(
        x,
        y,
        triangle_mode=triangle_mode,
        dtype=np.uint32,
    )
    color_key_base = (
        (rgb_u8[:, 0].astype(np.uint32) << 16)
        | (rgb_u8[:, 1].astype(np.uint32) << 8)
        | rgb_u8[:, 2].astype(np.uint32)
    )
    color_key = np.tile(color_key_base, 4)
    pair_key = (flat_idx.astype(np.uint64) << 24) | color_key.astype(np.uint64)
    if pair_key.size == 0:
        return out.reshape((256, 256, 4))

    order = np.argsort(pair_key, kind="mergesort")
    pair_sorted = pair_key[order]
    run_start = np.concatenate(
        ([0], np.flatnonzero(np.diff(pair_sorted) != 0).astype(np.int64) + 1)
    )
    run_end = np.concatenate((run_start[1:], [pair_sorted.size]))
    pair_unique = pair_sorted[run_start]
    run_counts = (run_end - run_start).astype(np.int32, copy=False)
    run_last_pos = order[run_end - 1]

    pixel_idx = (pair_unique >> 24).astype(np.int32, copy=False)
    color_unique = (pair_unique & 0xFFFFFF).astype(np.uint32, copy=False)
    if pixel_idx.size <= 0:
        return out.reshape((256, 256, 4))

    candidate_order = np.lexsort((run_last_pos, run_counts, pixel_idx))
    if candidate_order.size <= 0:
        return out.reshape((256, 256, 4))

    pixel_sorted = pixel_idx[candidate_order]
    group_start = np.concatenate(
        ([0], np.flatnonzero(np.diff(pixel_sorted) != 0).astype(np.int64) + 1)
    )
    group_end = np.concatenate((group_start[1:], [candidate_order.size]))
    best_rows = candidate_order[group_end - 1]

    best_pixels = pixel_idx[best_rows]
    best_colors = color_unique[best_rows]
    out[best_pixels, 0] = ((best_colors >> 16) & 0xFF).astype(np.uint8, copy=False)
    out[best_pixels, 1] = ((best_colors >> 8) & 0xFF).astype(np.uint8, copy=False)
    out[best_pixels, 2] = (best_colors & 0xFF).astype(np.uint8, copy=False)
    out[best_pixels, 3] = 255
    return out.reshape((256, 256, 4))


def render_scatter_heatmap(
    x: np.ndarray,
    y: np.ndarray,
    *,
    triangle_mode: bool,
) -> np.ndarray:
    """密度ヒートマップ方式で散布図ラスタを生成する。"""
    out = np.zeros((256, 256, 4), dtype=np.uint8)
    if x.size == 0 or y.size == 0:
        return out

    flat_idx = four_neighborhood_flat_indices(
        x,
        y,
        triangle_mode=triangle_mode,
    )
    density = np.bincount(flat_idx, minlength=256 * 256).astype(np.float32, copy=False)

    density_img = density.reshape((256, 256))
    if float(density_img.max()) <= 0.0:
        return out

    smooth = cv2.GaussianBlur(density_img, (0, 0), sigmaX=1.2, sigmaY=1.2)
    tone = np.log1p(smooth)
    peak = float(tone.max())
    if peak <= 0.0:
        return out
    norm = np.clip(tone / peak, 0.0, 1.0)
    gray = np.clip(norm * 255.0, 0.0, 255.0).astype(np.uint8)
    cmap = getattr(cv2, "COLORMAP_TURBO", cv2.COLORMAP_JET)
    heat_bgr = cv2.applyColorMap(gray, cmap)

    out[:, :, 0:3] = heat_bgr[:, :, ::-1]
    alpha = np.clip(np.power(norm, 0.55) * 255.0, 0.0, 255.0).astype(np.uint8)
    alpha[norm < 0.02] = 0
    out[:, :, 3] = alpha
    return out


def validated_scatter_arrays(
    sv: np.ndarray,
    rgb: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, int] | None:
    """散布図入力配列を検証し、正規化済み配列と件数を返す。"""
    sv_arr = np.asarray(sv)
    rgb_arr = np.asarray(rgb)
    if sv_arr.ndim != 2 or sv_arr.shape[1] < 2:
        return None
    if rgb_arr.ndim != 2 or rgb_arr.shape[1] < 3:
        return None
    n = min(int(sv_arr.shape[0]), int(rgb_arr.shape[0]))
    if n <= 0:
        return None
    return sv_arr, rgb_arr, int(n)


def prepare_scatter_samples(
    sv_arr: np.ndarray,
    rgb_arr: np.ndarray,
    *,
    n: int,
    need_rgb_for_render: bool,
    hue_filter_enabled: bool,
    hue_center: int,
    hue_half_width: int,
) -> tuple[np.ndarray, np.ndarray | None] | None:
    """描画用の SV / RGB サンプルを抽出・フィルタして返す。"""
    need_rgb_for_hue = bool(hue_filter_enabled and sv_arr.shape[1] < 3)
    need_rgb = bool(need_rgb_for_render or need_rgb_for_hue)
    rgb_u8 = to_rgb_u8(rgb_arr, int(n)) if need_rgb else None
    if sv_arr.shape[1] >= 3:
        h_arr = sv_arr[:n, 0]
        if hue_filter_enabled:
            h_arr = np.clip(h_arr, C.SCATTER_HUE_MIN, C.SCATTER_HUE_MAX)
        sv_used = sv_arr[:n, 1:3]
    else:
        h_arr = extract_hue_from_rgb(rgb_u8) if hue_filter_enabled and rgb_u8 is not None else None
        sv_used = sv_arr[:n, :2]

    if hue_filter_enabled:
        if h_arr is None or h_arr.size == 0:
            return None
        keep = apply_hue_filter_mask(
            h_arr,
            center=int(hue_center),
            half_width=int(hue_half_width),
        )
        if not np.any(keep):
            return None
        sv_used = sv_used[keep]
        if rgb_u8 is not None:
            rgb_u8 = rgb_u8[keep]
        if sv_used.size == 0 or (rgb_u8 is not None and rgb_u8.size == 0):
            return None
    return sv_used, rgb_u8


def build_scatter_image(
    sv: np.ndarray,
    rgb: np.ndarray,
    *,
    config: ScatterRenderConfig,
) -> np.ndarray | None:
    """設定に従って散布図ラスタ画像を構築する。"""
    validated = validated_scatter_arrays(sv, rgb)
    if validated is None:
        return None
    sv_arr, rgb_arr, n = validated
    prepared = prepare_scatter_samples(
        sv_arr,
        rgb_arr,
        n=n,
        need_rgb_for_render=bool(config.need_rgb_for_render),
        hue_filter_enabled=bool(config.hue_filter_enabled),
        hue_center=int(config.hue_center),
        hue_half_width=int(config.hue_half_width),
    )
    if prepared is None:
        return None
    sv_used, rgb_u8 = prepared
    x, y = compute_scatter_xy(
        sv_used,
        triangle_mode=bool(config.triangle_mode),
    )
    if str(config.render_mode) == C.SCATTER_RENDER_MODE_HEATMAP:
        return render_scatter_heatmap(
            x,
            y,
            triangle_mode=bool(config.triangle_mode),
        )
    if rgb_u8 is None:
        return None
    return render_scatter_dominant(
        x,
        y,
        rgb_u8,
        triangle_mode=bool(config.triangle_mode),
    )


def build_square_fallback_scatter_image(
    sv: np.ndarray,
    rgb: np.ndarray,
) -> np.ndarray | None:
    """例外時の安全側フォールバック画像(四角/代表色)を返す。"""
    validated = validated_scatter_arrays(sv, rgb)
    if validated is None:
        return None
    sv_arr, rgb_arr, n = validated
    sv_used = sv_arr[:n, 1:3] if sv_arr.shape[1] >= 3 else sv_arr[:n, :2]
    rgb_u8 = to_rgb_u8(rgb_arr, n)
    x, y = compute_scatter_xy(sv_used, triangle_mode=False)
    return render_scatter_dominant(
        x,
        y,
        rgb_u8,
        triangle_mode=False,
    )
