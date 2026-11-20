"""
Plotting library for Antioch apps, backed by plotly.js.

Components:
    PlotlyChart - chart macro with native SVG export
    bar_trace / line_trace / marker_trace / scatter_trace - trace builders
    CATEGORICAL_PALETTE - fixed, validated series colours
"""
from .chart import PlotlyChart
from .traces import (
    bar_trace, line_trace, marker_trace, error_bar_trace, heatmap_trace,
    series_color, DENSITY_COLORSCALE,
    scatter_trace, ternary_trace, ternary_layout,
    categorical_color, series_symbol,
    CATEGORICAL_PALETTE, SCATTER_CAP, SERIES_SYMBOLS,
    stacked_subplot_layout, subplot_axes, subplot_title,
)
from .export import charts_to_zip, download_bytes, safe_filename

__all__ = [
    'PlotlyChart',
    'bar_trace',
    'line_trace',
    'marker_trace',
    'error_bar_trace',
    'heatmap_trace',
    'DENSITY_COLORSCALE',
    'series_color',
    'scatter_trace',
    'ternary_trace',
    'ternary_layout',
    'categorical_color',
    'series_symbol',
    'CATEGORICAL_PALETTE',
    'SCATTER_CAP',
    'SERIES_SYMBOLS',
    'stacked_subplot_layout',
    'subplot_axes',
    'subplot_title',
    'charts_to_zip',
    'download_bytes',
    'safe_filename',
]

__version__ = '0.1.0'
