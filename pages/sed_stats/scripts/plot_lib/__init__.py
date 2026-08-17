"""
Plotting library for Antioch apps, backed by plotly.js.

Components:
    PlotlyChart - chart macro with native SVG export
    bar_trace / line_trace / marker_trace - trace builders for common plots
"""
from .chart import PlotlyChart
from .traces import (
    bar_trace, line_trace, marker_trace, series_color,
    stacked_subplot_layout, subplot_axes, subplot_title,
)
from .export import charts_to_zip, download_bytes, safe_filename

__all__ = [
    'PlotlyChart',
    'bar_trace',
    'line_trace',
    'marker_trace',
    'series_color',
    'stacked_subplot_layout',
    'subplot_axes',
    'subplot_title',
    'charts_to_zip',
    'download_bytes',
    'safe_filename',
]

__version__ = '0.1.0'
