"""
Distributions: building them from the spreadsheet and drawing them.

`compute_lines` and `draw_curves` are the two halves — a Distribution step makes
`Lines`, a Line plot step draws them — and `build_distribution` is the toolbar's
one-shot of the pair (plus the histogram, which bins rather than smooths).
"""
from antioch.elements import Div, P

from plot_lib import (
    bar_trace, line_trace, series_color, stacked_subplot_layout, subplot_axes,
    subplot_title,
)
from workflow_lib import NodeProblem
from workflow_lib.types import Lines

from .config import VIEWS
from .dataset import find_uncertainty_column, is_numeric_column, series_for
from .plots import make_plot

# Enough vertical room per subplot row to stay readable, plus title and axis.
ROW_HEIGHT = 150
STACK_CHROME = 90


def compute_lines(rows, sample_col, dimension, opts):
    """
    One dimension's curves for the selected samples, as PDFs and CDFs.

    Raises:
        NodeProblem: if no selected sample has data for the dimension
    """
    labels, pdf = series_for(rows, sample_col, dimension, "pdf", opts)
    if not pdf:
        raise NodeProblem(f"No data for '{dimension}'.")
    _, cdf = series_for(rows, sample_col, dimension, "cdf", opts)
    return Lines(dimension, labels, pdf, cdf,
                 categorical=not is_numeric_column(rows, dimension),
                 note=uncertainty_text(rows, dimension, opts) or "")


def build_distribution(charts, rows, sample_col, dimension, opts):
    labels, series = series_for(rows, sample_col, dimension, opts["view"], opts)
    if not series:
        return P(f"No data for '{dimension}'.", style={"color": "#6c757d"})

    view = VIEWS[opts["view"]]
    plot = draw_curves(
        charts, [(sample, labels, data) for sample, data in series],
        title=f"{dimension} — {view['label']}", x_title=dimension,
        y_title="Count" if opts["view"] == "histogram" else "Probability",
        layout=opts["layout"], style=view["chart_type"],
        filename=f"{dimension}_{opts['view']}")

    note = None
    if opts["view"] in ("pdf", "cdf"):
        note = uncertainty_text(rows, dimension, opts)
    return Div(note_paragraph(note), plot) if note else plot


def uncertainty_text(rows, dimension, opts):
    """Say how a curve was built when it came from kernels rather than bins."""
    if not rows:
        return None

    density = opts.get("density", "auto")
    if density == "kde":
        width = opts.get("bandwidth")
        described = f"bandwidth {width:g}" if width else "a Silverman bandwidth"
        return f"Kernel density estimate using {described}."
    if density == "auto":
        column, level = find_uncertainty_column(list(rows[0].keys()), dimension)
        if column is None:
            return None
        stated = level or opts.get("sigma_in", 1.0)
        return (f"Each measurement spread by its uncertainty from '{column}' "
                f"({stated:g}σ).")
    return None


def note_paragraph(text):
    return P(text, style={"font-size": "13px", "color": "#555",
                          "margin": "0 0 6px 0"})


def draw_curves(charts, curves, title, x_title, y_title, layout="overlay",
                style="line", filename=None):
    """
    Plot curves, overlaid on one set of axes or stacked as subplots.

    Args:
        curves: [(name, x, y), ...] — each curve brings its own x, since curves
            from different dimensions share nothing
        style: "line" or "bar"
        layout: "overlay" or "stacked"
    """
    filename = filename or title.replace(" ", "_")
    total = len(curves)
    if layout == "overlay":
        traces = [_trace(name, x, y, style, series_color(i, total))
                  for i, (name, x, y) in enumerate(curves)]
        return Div(make_plot(charts, traces, title, x_title, y_title,
                             filename=filename).element)

    # One figure with real subplots sharing an x-axis, not a column of figures.
    axis_layout = stacked_subplot_layout(total, shared_xaxis=True)
    traces, annotations = [], []
    for i, (name, x, y) in enumerate(curves):
        trace = _trace(name, x, y, style, series_color(i, total))
        trace["xaxis"], trace["yaxis"] = subplot_axes(i)
        trace["showlegend"] = False
        traces.append(trace)
        annotations.append(subplot_title(i, name))

        suffix = "" if i == 0 else str(i + 1)
        axis_layout[f"yaxis{suffix}"]["title"] = {"text": y_title}
        axis_layout[f"yaxis{suffix}"]["rangemode"] = "tozero"
        if i == total - 1:
            axis_layout[f"xaxis{suffix}"]["title"] = {"text": x_title}

    extra_layout = dict(axis_layout)
    extra_layout["annotations"] = annotations
    return Div(make_plot(
        charts, traces, title, x_title, y_title,
        height=max(240, ROW_HEIGHT * total + STACK_CHROME),
        show_legend=False, filename=f"{filename}_stacked",
        extra_layout=extra_layout).element)


def _trace(name, x, y, style, color):
    return (bar_trace(x, y, name, color) if style == "bar"
            else line_trace(x, y, name, color))
