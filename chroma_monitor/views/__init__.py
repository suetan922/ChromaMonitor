"""View widgets split by function."""

from .color_scatter import ColorWheelWidget, ScatterRasterWidget
from .edge_view import EdgeView
from .focus_peaking_view import FocusPeakingView
from .histogram import ChannelHistogram
from .preview import PreviewWindow
from .roi_selector import RoiSelector
from .saliency_view import SaliencyView
from .squint_view import SquintView
from .tonal_views import BinaryView, GrayscaleView, TernaryView
from .vectorscope_view import VectorScopeView

__all__ = [
    "BinaryView",
    "ChannelHistogram",
    "ColorWheelWidget",
    "EdgeView",
    "FocusPeakingView",
    "GrayscaleView",
    "PreviewWindow",
    "RoiSelector",
    "SaliencyView",
    "ScatterRasterWidget",
    "SquintView",
    "TernaryView",
    "VectorScopeView",
]
