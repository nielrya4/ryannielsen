"""The Distributions tool's output: histograms, PDFs and CDFs."""
from antioch.elements import Div, P

from plot_lib import stacked_subplot_layout, subplot_axes, subplot_title

from .config import VIEWS
from .dataset import attribute_series
from .plots import distribution_traces, make_plot

# Enough vertical room per subplot row to stay readable, plus title and axis.
ROW_HEIGHT = 150
STACK_CHROME = 90


def build_distribution(charts, rows, sample_col, dimension, opts):
    labels, series = attribute_series(
        rows, sample_col, dimension, opts["view"], opts["bin_size"], opts["samples"]
    )
    if not series:
        return P(f"No data for '{dimension}'.", style={"color": "#6c757d"})

    y_title = "Count" if opts["view"] == "histogram" else "Probability"
    title = f"{dimension} — {VIEWS[opts['view']]['label']}"

    if opts["layout"] == "overlay":
        return _overlay(charts, labels, series, dimension, opts, title, y_title)
    return _stacked(charts, labels, series, dimension, opts, title, y_title)


def _overlay(charts, labels, series, dimension, opts, title, y_title):
    traces = distribution_traces(labels, series, opts["view"])
    return Div(make_plot(charts, traces, title, dimension, y_title,
                         filename=f"{dimension}_{opts['view']}").element)


def _stacked(charts, labels, series, dimension, opts, title, y_title):
    """One figure with real subplots sharing an x-axis, not a column of figures."""
    row_count = len(series)
    axis_layout = stacked_subplot_layout(row_count, shared_xaxis=True)
    traces = []
    annotations = []

    for i, (sample, data) in enumerate(series):
        trace = distribution_traces(labels, [(sample, data)], opts["view"],
                                    offset=i, total=row_count)[0]
        x_axis, y_axis = subplot_axes(i)
        trace["xaxis"] = x_axis
        trace["yaxis"] = y_axis
        trace["showlegend"] = False
        traces.append(trace)
        annotations.append(subplot_title(i, sample))

        suffix = "" if i == 0 else str(i + 1)
        axis_layout[f"yaxis{suffix}"]["title"] = {"text": y_title}
        axis_layout[f"yaxis{suffix}"]["rangemode"] = "tozero"
        if i == row_count - 1:
            axis_layout[f"xaxis{suffix}"]["title"] = {"text": dimension}

    extra_layout = dict(axis_layout)
    extra_layout["annotations"] = annotations
    return Div(make_plot(
        charts, traces, title, dimension, y_title,
        height=max(240, ROW_HEIGHT * row_count + STACK_CHROME),
        show_legend=False,
        filename=f"{dimension}_{opts['view']}_stacked",
        extra_layout=extra_layout,
    ).element)
