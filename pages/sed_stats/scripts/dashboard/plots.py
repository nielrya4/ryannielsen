"""Chart construction shared by the builders.

`charts` is always the running list of (name, PlotlyChart) pairs for the output
being built; the gallery uses it for resizing and for the SVG/zip export, so
every plot has to be registered there as it is made.
"""
from plot_lib import PlotlyChart, bar_trace, line_trace, series_color

from .config import CHART_WIDTH, VIEWS


def make_plot(charts, traces, title, x_title, y_title, height=420,
              show_legend=True, filename=None, extra_layout=None):
    """Build a plot and register it under `filename` for export."""
    name = filename or title.replace(" ", "_")
    layout = {
        "title": {"text": title},
        "xaxis": {"title": {"text": x_title}},
        "yaxis": {"title": {"text": y_title}, "rangemode": "tozero"},
        "showlegend": show_legend,
        "legend": {"orientation": "v", "x": 1.02, "y": 1},
        "barmode": "group",
    }
    if extra_layout:
        layout.update(extra_layout)

    chart = PlotlyChart(
        traces=traces,
        layout=layout,
        config={"toImageButtonOptions": {"format": "svg", "filename": name}},
        width=CHART_WIDTH,
        height=height,
    )
    charts.append((name, chart))
    return chart


def distribution_traces(labels, series, view, offset=0, total=None):
    """One trace per sample, colored by position in the overall series set."""
    total = total or len(series)
    chart_type = VIEWS[view]["chart_type"]
    traces = []
    for i, (sample, data) in enumerate(series):
        color = series_color(offset + i, total)
        if chart_type == "bar":
            traces.append(bar_trace(labels, data, sample, color))
        else:
            traces.append(line_trace(labels, data, sample, color))
    return traces
