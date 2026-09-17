"""
The Scatterplot tool's output: raw grain measurements, coloured by sample.

Every other tool in the app shows a distribution — something estimated from the
grains. This one shows the grains. It is the plot to reach for when a density
looks wrong and you want to know whether the data or the kernel is responsible.
"""
from antioch.elements import Div, P

from plot_lib import SCATTER_CAP, categorical_color, scatter_trace, series_symbol

from .config import CHART_WIDTH
from .dataset import paired_by_sample, sample_names
from .plots import make_plot

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
NOTE_STYLE = {"color": "#6c757d"}

# One neutral colour when nothing is being distinguished.
PLAIN_COLOR = "#4a5568"


def build_scatter(charts, rows, sample_col, dimension, opts):
    """`dimension` is the y variable; x is fixed for the whole output."""
    x_dimension = opts.get("x_dimension")
    if not x_dimension:
        return P("Choose an x dimension.", style=NOTE_STYLE)
    if x_dimension == dimension:
        return P(f"'{dimension}' is already the x dimension; pick a different "
                 f"y dimension.", style=NOTE_STYLE)

    try:
        grouped = paired_by_sample(rows, sample_col, x_dimension, dimension,
                                   opts.get("samples"))
    except ValueError:
        return P(f"'{dimension}' is not numeric, so it cannot be a scatter axis.",
                 style=NOTE_STYLE)
    if not grouped:
        return P(f"No paired '{x_dimension}' and '{dimension}' values.",
                 style=NOTE_STYLE)

    # Colour keyed to the sample's place in the spreadsheet, not its place in
    # the current selection — so a sample keeps its colour when the selection
    # changes and two outputs stay comparable.
    order = {name: index
             for index, name in enumerate(sample_names(rows, sample_col))}

    if opts.get("layout") == "facet":
        return _facets(charts, grouped, order, x_dimension, dimension, opts)
    return _overlay(charts, grouped, order, x_dimension, dimension, opts)


def _style(sample, order, opts):
    """The colour and shape a sample is drawn with."""
    if not opts.get("color_by_sample", True):
        return PLAIN_COLOR, "circle"
    index = order.get(sample, 0)
    return categorical_color(index), series_symbol(index)


def _points(sample, values, order, x_dimension, dimension, opts):
    color, symbol = _style(sample, order, opts)
    return scatter_trace(
        values[0], values[1], sample,
        color=color, symbol=symbol,
        size=opts.get("point_size", 7),
        opacity=opts.get("opacity", 0.75),
        hover_x=x_dimension, hover_y=dimension,
    )


def _axes(x_dimension, dimension):
    # Measurements have no reason to reach zero; the default "tozero" would pad
    # a temperature axis down to 0 and waste most of the plot.
    return {
        "xaxis": {"title": {"text": x_dimension}, "rangemode": "normal"},
        "yaxis": {"title": {"text": dimension}, "rangemode": "normal"},
    }


def _overlay(charts, grouped, order, x_dimension, dimension, opts):
    traces = [_points(sample, values, order, x_dimension, dimension, opts)
              for sample, values in grouped.items()]
    total = sum(len(v[0]) for v in grouped.values())

    wrapper = Div(
        P(f"{total:,} grains across {len(grouped)} "
          f"sample{'s' if len(grouped) != 1 else ''}.", style=CAPTION_STYLE),
        Div(make_plot(
            charts, traces, f"{x_dimension} vs {dimension}",
            x_dimension, dimension,
            height=520, show_legend=len(traces) > 1,
            filename=f"{x_dimension}_{dimension}_scatter",
            extra_layout=_axes(x_dimension, dimension),
        ).element),
    )

    # Past three series, colour alone cannot keep every pair apart — every
    # series touches every other on a scatter, so it is all pairs that have to
    # separate, not just neighbours. Marker shape carries identity too, which is
    # what makes more than three legible; say so rather than implying the
    # colours alone are doing the work.
    if opts.get("color_by_sample", True) and len(grouped) > SCATTER_CAP:
        wrapper.add(P(
            f"Beyond {SCATTER_CAP} samples the colours alone stop separating "
            f"reliably, so each sample also has its own marker shape. For many "
            f"samples, 'One plot per sample' reads more clearly.",
            style=NOTE_STYLE))
    return wrapper


def _facets(charts, grouped, order, x_dimension, dimension, opts):
    """
    One panel per sample, on shared axes.

    Shared ranges are the point: panels that each auto-scale would show every
    sample filling its own frame and hide the differences between them.
    """
    all_x = [v for values in grouped.values() for v in values[0]]
    all_y = [v for values in grouped.values() for v in values[1]]
    limits = {
        "xaxis": {**_axes(x_dimension, dimension)["xaxis"],
                  "range": _padded(all_x)},
        "yaxis": {**_axes(x_dimension, dimension)["yaxis"],
                  "range": _padded(all_y)},
    }

    wrapper = Div(P(f"{len(grouped)} samples on shared axes.",
                    style=CAPTION_STYLE))
    for sample, values in grouped.items():
        trace = _points(sample, values, order, x_dimension, dimension, opts)
        wrapper.add(Div(make_plot(
            charts, [trace], f"{sample} — {x_dimension} vs {dimension}",
            x_dimension, dimension,
            height=380, show_legend=False,
            filename=f"{sample}_{x_dimension}_{dimension}_scatter",
            extra_layout=limits,
        ).element))
        wrapper.add(P(f"n = {len(values[0]):,}",
                      style={**CAPTION_STYLE, "margin": "0 0 14px 0"}))
    return wrapper


def _padded(values, fraction=0.04):
    """A range with a little air, so points never sit on the frame."""
    low, high = min(values), max(values)
    pad = (high - low) * fraction or (abs(low) * 0.04 or 1.0)
    return [low - pad, high + pad]
