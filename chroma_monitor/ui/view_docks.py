"""ビュー用ドック構築の facade。"""

from .view_docks_builders import build_view_docks
from .view_docks_layout import setup_view_dock_layout


def setup_view_docks(main_window) -> None:
    """解析ビュー一式のドックと初期レイアウトを構築する。"""
    build_view_docks(main_window)
    setup_view_dock_layout(main_window)


__all__ = ["setup_view_docks"]
