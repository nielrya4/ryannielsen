"""The Bivariate mixture tool's output: top-down unmixing on density grids."""
import math

from antioch.elements import Div, P

from plot_lib import DENSITY_COLORSCALE, error_bar_trace, heatmap_trace
from sed_stats import metrics_2d, mixture

from .bivariate import prepare
from .config import MIXTURE_METRICS
from .plots import make_plot
from .tables import result_table

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
NOTE_STYLE = {"color": "#6c757d"}
CONTRIBUTION_COLOR = "#8e5b42"

# Mismatch is signed in spirit — where the model over- or under-shoots — so it
# gets a diverging scale rather than the density ramp.
MISMATCH_COLORSCALE = [
    [0.0, "#ffffff"],
    [0.5, "#f5c542"],
    [1.0, "#c1121f"],
]


def build_bivariate_mixture(charts, rows, sample_col, dimension, opts):
    """`dimension` is the y variable; x is fixed for the whole output."""
    density_set, problem = prepare(rows, sample_col, dimension, opts,
                                   min_samples=3, purpose="unmix")
    if problem:
        return problem

    x_dimension = opts["x_dimension"]
    sink_name = opts["sink"]
    entries = dict(density_set.entries)
    sink = entries.get(sink_name)
    sources = [(name, grid) for name, grid in density_set.entries
               if name != sink_name]

    if sink is None:
        return P(f"The sink sample '{sink_name}' has no paired values here.",
                 style=NOTE_STYLE)
    if len(sources) < 2:
        return P("Need at least two source samples to unmix.", style=NOTE_STYLE)

    result = mixture.monte_carlo_model_2d(
        sink=sink,
        sources=[grid for _, grid in sources],
        source_names=[name for name, _ in sources],
        n_trials=opts["trials"],
        metric=opts["metric"],
    )

    label = f"{x_dimension} vs {dimension}"
    return Div(
        _summary(label, sink_name, opts, density_set, result),
        _surfaces(charts, label, sink_name, density_set, sink, result),
        _contribution_plot(charts, label, result),
        _contribution_table(opts["metric"], result),
    )


def _summary(label, sink_name, opts, density_set, result):
    info = MIXTURE_METRICS[opts["metric"]]
    return P(f"{opts['trials']:,} trials against {sink_name} over {label}, "
             f"scored by 2D {info['label']} ({info['note']}). "
             f"Best of the top {len(result.top_scores)}: "
             f"{result.best_score:.4g}. "
             f"{density_set.method_note.capitalize()}, "
             f"{len(density_set.x_values)}×{len(density_set.y_values)} grid.",
             style=CAPTION_STYLE)


def _surfaces(charts, label, sink_name, density_set, sink, result):
    """
    Sink, best model, and where they disagree.

    Ten overlaid trial curves work in 1D; ten stacked heatmaps do not. The
    useful comparison in 2D is the sink against the single best model, plus the
    mismatch surface showing which part of the grid the model fails to
    reproduce.
    """
    grids = result.top_grids
    if not grids:
        return Div()
    best = grids[0]

    x_title, y_title = label.split(" vs ")[0], label.split(" vs ")[-1]
    wrapper = Div()
    for title, grid, scale, filename in (
        (f"{sink_name} (sink)", sink.densities, DENSITY_COLORSCALE, "sink"),
        ("Best model", best, DENSITY_COLORSCALE, "model"),
        ("Mismatch", metrics_2d.mismatch_surface(sink.densities, best),
         MISMATCH_COLORSCALE, "mismatch"),
    ):
        trace = heatmap_trace(
            density_set.x_values, density_set.y_values,
            grid.tolist() if hasattr(grid, "tolist") else grid,
            colorscale=scale,
            colorbar_title="Mismatch" if filename == "mismatch" else "Density",
        )
        wrapper.add(Div(make_plot(
            charts, [trace], f"{label} — {title}",
            x_title, y_title,
            height=420, show_legend=False,
            filename=f"{label}_{filename}".replace(" ", "_"),
            extra_layout={
                "xaxis": {"title": {"text": x_title}, "rangemode": "normal"},
                "yaxis": {"title": {"text": y_title}, "rangemode": "normal"},
            },
        ).element))
    return wrapper


def _contribution_plot(charts, label, result):
    names = [c.name for c in result.contributions]
    values = [c.contribution for c in result.contributions]
    errors = [c.standard_deviation for c in result.contributions]

    trace = error_bar_trace(names, values, errors, "Contribution",
                            color=CONTRIBUTION_COLOR)
    return Div(make_plot(
        charts, [trace], f"{label} — relative contribution",
        "Source sample", "% contribution",
        height=460, show_legend=False, filename=f"{label}_contribution".replace(" ", "_"),
        extra_layout={
            "xaxis": {"title": {"text": "Source sample"},
                      "type": "category", "tickangle": -45},
            # Rotated sample names need room; the default 50px clipped them.
            "margin": {"l": 60, "r": 20, "t": 50, "b": 150},
        },
    ).element)


def _contribution_table(metric, result):
    body = [
        [c.name,
         "n/a" if math.isnan(c.contribution) else f"{c.contribution:.2f}",
         "n/a" if math.isnan(c.standard_deviation)
         else f"{c.standard_deviation:.2f}"]
        for c in result.contributions
    ]
    return Div(
        P("Relative contribution", style={**CAPTION_STYLE, "margin": "16px 0 6px 0"}),
        result_table(
            ["Source",
             f"% contribution (2D {MIXTURE_METRICS[metric]['label']})",
             "Standard deviation"],
            body,
        ),
    )
