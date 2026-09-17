"""The Mixture model tool's output: unmixing a sink sample into its sources."""
import math

from antioch.elements import Div, P

from plot_lib import error_bar_trace, line_trace
from sed_stats import mixture

from .config import MIXTURE_METRICS
from .dataset import series_for
from .plots import make_plot
from .tables import result_table

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}

TRIAL_COLOR = "rgba(0, 191, 214, 0.55)"
SINK_COLOR = "#1f4fd8"
CONTRIBUTION_COLOR = "#8e5b42"


def build_mixture(charts, rows, sample_col, dimension, opts):
    metric = opts["metric"]
    labels, series = series_for(rows, sample_col, dimension,
                                mixture.expected_form(metric), opts)

    sink_name = opts["sink"]
    sink = next((data for name, data in series if name == sink_name), None)
    sources = [(name, data) for name, data in series if name != sink_name]

    if sink is None:
        return P(f"The sink sample '{sink_name}' has no data for '{dimension}'.",
                 style={"color": "#6c757d"})
    if len(sources) < 2:
        return P("Need at least two source samples with data to unmix.",
                 style={"color": "#6c757d"})

    result = mixture.monte_carlo_model(
        sink_values=sink,
        source_values=[data for _, data in sources],
        source_names=[name for name, _ in sources],
        n_trials=opts["trials"],
        metric=metric,
    )

    return Div(
        _summary(sink_name, metric, opts["trials"], result),
        _top_trials_plot(charts, labels, sink, sink_name, dimension, result),
        _contribution_plot(charts, dimension, result),
        _contribution_table(metric, result),
    )


def _summary(sink_name, metric, trials, result):
    info = MIXTURE_METRICS[metric]
    return P(f"{trials:,} trials against {sink_name}, scored by {info['label']} "
             f"({info['note']}). Best of the top {len(result.top_scores)}: "
             f"{result.best_score:.4g}.", style=CAPTION_STYLE)


def _top_trials_plot(charts, labels, sink, sink_name, dimension, result):
    """The best model curves behind the sink they are trying to reproduce."""
    traces = []
    for i, line in enumerate(result.top_lines):
        traces.append(line_trace(
            labels, [float(v) for v in line],
            "Top trials" if i == 0 else f"Trial {i + 1}",
            color=TRIAL_COLOR, markers=False,
        ))
        # One legend entry stands for the whole bundle.
        traces[-1]["showlegend"] = i == 0
        traces[-1]["hoverinfo"] = "skip"

    # Added last so the sink draws on top of the bundle.
    traces.append(line_trace(labels, sink, sink_name, color=SINK_COLOR, markers=False))
    traces[-1]["line"]["width"] = 3

    y_title = "Probability"
    return Div(make_plot(charts, traces, f"{dimension} — top trials",
                         dimension, y_title,
                         filename=f"{dimension}_mixture_trials").element)


def _contribution_plot(charts, dimension, result):
    names = [c.name for c in result.contributions]
    values = [c.contribution for c in result.contributions]
    errors = [c.standard_deviation for c in result.contributions]

    trace = error_bar_trace(names, values, errors, "Contribution",
                            color=CONTRIBUTION_COLOR)
    return Div(make_plot(
        charts, [trace], f"{dimension} — relative contribution",
        "Source sample", "% contribution",
        height=460, show_legend=False,
        filename=f"{dimension}_mixture_contribution",
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
             f"% contribution ({MIXTURE_METRICS[metric]['label']})",
             "Standard deviation"],
            body,
        ),
    )
