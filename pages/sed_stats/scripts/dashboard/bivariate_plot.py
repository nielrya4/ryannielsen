"""The Bivariate density tool's output: one density grid per sample."""
from antioch.elements import Div, P

from plot_lib import heatmap_trace, marker_trace

from .bivariate import prepare
from .plots import make_plot

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}

# Grains drawn over the density, faint enough not to fight it.
POINT_COLOR = "rgba(20, 20, 20, 0.45)"


def build_bivariate(charts, rows, sample_col, dimension, opts):
    """
    `dimension` is the y variable; the x variable is fixed for the whole output.

    Each sample gets its own figure rather than sharing one, since two
    overlapping heatmaps would hide each other.
    """
    density_set, problem = prepare(rows, sample_col, dimension, opts)
    if problem:
        return problem
    x_dimension = opts["x_dimension"]

    wrapper = Div(P(f"{x_dimension} vs {dimension} — {density_set.method_note}.",
                    style=CAPTION_STYLE))

    for sample, distribution in density_set.entries:
        traces = [heatmap_trace(
            density_set.x_values, density_set.y_values,
            distribution.densities.tolist(),
            name=sample, colorbar_title="Density",
        )]
        if opts.get("show_points"):
            xs, ys = _sample_points(rows, sample_col, sample, x_dimension, dimension)
            if xs:
                points = marker_trace(xs, ys, "Grains", color=POINT_COLOR, size=4)
                points["showlegend"] = False
                traces.append(points)

        count = density_set.counts.get(sample, 0)
        wrapper.add(Div(make_plot(
            charts, traces, f"{sample} — {x_dimension} vs {dimension}",
            x_dimension, dimension,
            height=460, show_legend=False,
            filename=f"{sample}_{x_dimension}_{dimension}_density",
            # A density axis has no reason to reach zero; padding a Ti
            # temperature axis down to 0 K wastes most of the plot.
            extra_layout={
                "xaxis": {"title": {"text": x_dimension}, "rangemode": "normal"},
                "yaxis": {"title": {"text": dimension}, "rangemode": "normal"},
            },
        ).element))
        wrapper.add(P(f"n = {count}", style={**CAPTION_STYLE,
                                            "margin": "0 0 14px 0"}))

    return wrapper


def _sample_points(rows, sample_col, sample, x_dimension, y_dimension):
    """The raw grains behind one sample's density, for the scatter overlay."""
    xs, ys = [], []
    for row in rows:
        if str(row.get(sample_col, "") or "").strip() != sample:
            continue
        x_raw, y_raw = row.get(x_dimension, ""), row.get(y_dimension, "")
        if x_raw in ("", None) or y_raw in ("", None):
            continue
        try:
            xs.append(float(x_raw))
            ys.append(float(y_raw))
        except (TypeError, ValueError):
            continue
    return xs, ys
