"""The Mixture model tool's output: unmixing a sink sample into its sources."""
import math

from antioch.elements import Div, P

from plot_lib import error_bar_trace, line_trace
from sed_stats import mixture
from workflow_lib import NodeProblem
from workflow_lib.types import Proportions

from .config import MIXTURE_METRICS
from .plots import make_plot
from .tables import result_table

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}

TRIAL_COLOR = "rgba(0, 191, 214, 0.55)"
SINK_COLOR = "#1f4fd8"
CONTRIBUTION_COLOR = "#8e5b42"


def _model(series, opts, dimension):
    """
    Fit the sink as a mixture of the other samples in `series`.

    Returns:
        (MixtureResult, the sink's values)

    Raises:
        NodeProblem: if the sink is missing or there are too few sources
    """
    sink_name = opts["sink"]
    sink = next((data for name, data in series if name == sink_name), None)
    sources = [(name, data) for name, data in series if name != sink_name]
    if sink is None:
        raise NodeProblem(f"The sink sample '{sink_name}' has no data for "
                          f"'{dimension}'.")
    if len(sources) < 2:
        raise NodeProblem("Need at least two source samples with data to unmix.")
    result = mixture.monte_carlo_model(
        sink_values=sink,
        source_values=[data for _, data in sources],
        source_names=[name for name, _ in sources],
        n_trials=opts["trials"],
        metric=opts["metric"],
        refine=opts.get("refine", True),
    )
    return result, sink


def unmix_lines(lines, opts):
    """
    A sink's mix of the other samples' curves, as Proportions.

    The Proportions carry what a graph needs to show the fit as well — the
    best trial curves and the sink they chase — under `meta`.
    """
    result, sink = _model(lines.series(mixture.expected_form(opts["metric"])),
                          opts, lines.name)
    return _proportions(
        lines.name, opts, result,
        _summary_text(opts["sink"], opts["metric"], opts["trials"], result),
        {"labels": lines.x, "sink": sink})


def unmix_raster(raster, opts):
    """The same for bivariate densities."""
    density_set = raster.density_set
    sink_name = opts["sink"]
    sink = dict(density_set.entries).get(sink_name)
    sources = [(name, grid) for name, grid in density_set.entries
               if name != sink_name]
    if sink is None:
        raise NodeProblem(f"The sink sample '{sink_name}' has no paired values "
                          f"for {raster.name}.")
    if len(sources) < 2:
        raise NodeProblem("Need at least two source samples to unmix.")
    result = mixture.monte_carlo_model_2d(
        sink=sink, sources=[grid for _, grid in sources],
        source_names=[name for name, _ in sources],
        n_trials=opts["trials"], metric=opts["metric"],
        refine=opts.get("refine", True))
    info = MIXTURE_METRICS[opts["metric"]]
    note = (f"{opts['trials']:,} trials against {sink_name} over {raster.name}, "
            f"scored by 2D {info['label']} ({info['note']}). {_fit(result)} "
            f"{density_set.method_note.capitalize()}, "
            f"{len(density_set.x_values)}×{len(density_set.y_values)} grid.")
    warning = density_set.order_warning(opts["metric"])
    return _proportions(raster.name, opts, result,
                        f"{note} {warning}" if warning else note,
                        {"surfaces": (raster, sink)})


def _proportions(name, opts, result, note, meta):
    return Proportions(
        name=name,
        names=[c.name for c in result.contributions],
        values=[c.contribution for c in result.contributions],
        errors=[c.standard_deviation for c in result.contributions],
        label=(f"% contribution ({estimate_label(result)}, "
               f"{MIXTURE_METRICS[opts['metric']]['label']})"),
        note=note,
        meta={**meta, "result": result, "metric": opts["metric"],
              "sink_name": opts["sink"], "spread_n": len(result.top_scores)})


def draw_proportions(charts, proportions, show_fit=False):
    """Bars with error bars, a table, and (1D) optionally the fit behind them."""
    wrapper = Div(P(proportions.note, style=CAPTION_STYLE))
    meta = proportions.meta
    if show_fit and "labels" in meta:
        wrapper.add(_top_trials_plot(
            charts, meta["labels"], meta["sink"], meta["sink_name"],
            proportions.name, meta["result"]))
    elif show_fit and "surfaces" in meta:
        # Imported here: the bivariate module itself imports this one.
        from .bivariate_mixture import _surfaces
        raster, sink = meta["surfaces"]
        wrapper.add(_surfaces(charts, raster.name, meta["sink_name"],
                              raster.density_set, sink, meta["result"],
                              raster.x_name, raster.y_name))
    wrapper.add(
        contribution_bar(charts, f"{proportions.name} — relative contribution",
                         proportions.names, proportions.values, proportions.errors,
                         f"{proportions.name}_mixture_contribution"),
        _detail_table(meta["detail"]) if "detail" in meta else
        _table(proportions.label, proportions.names, proportions.values,
               proportions.errors, meta.get("spread_n", 0)))
    return wrapper


def _fit(result):
    if result.refined:
        return f"Optimised best fit: {result.best_score:.4g}."
    return (f"Best of the top {len(result.top_scores)}: {result.best_score:.4g}; "
            f"contributions are their mean.")


def _summary_text(sink_name, metric, trials, result):
    info = MIXTURE_METRICS[metric]
    return (f"{trials:,} trials against {sink_name}, scored by {info['label']} "
            f"({info['note']}). {_fit(result)}")


def _top_trials_plot(charts, labels, sink, sink_name, dimension, result):
    """The best model curves behind the sink they are trying to reproduce."""
    traces = []
    for i, line in enumerate(result.top_lines):
        traces.append(line_trace(
            labels, [float(v) for v in line],
            ("Best fit and top trials" if result.refined else "Top trials")
            if i == 0 else f"Trial {i + 1}",
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


def contribution_bar(charts, title, names, values, errors, filename):
    trace = error_bar_trace(names, values, errors, "Contribution",
                            color=CONTRIBUTION_COLOR)
    return Div(make_plot(
        charts, [trace], title, "Source sample", "% contribution",
        height=460, show_legend=False, filename=filename,
        extra_layout={
            "xaxis": {"title": {"text": "Source sample"},
                      "type": "category", "tickangle": -45},
            # Rotated sample names need room; the default 50px clipped them.
            "margin": {"l": 60, "r": 20, "t": 50, "b": 150},
        },
    ).element)


def _detail_table(detail):
    """A model's own table, when it has more to say than a value and a spread."""
    titles, rows = detail
    return Div(P("Relative contribution", style={**CAPTION_STYLE, "margin": "16px 0 6px 0"}),
               result_table(titles, rows))


def _table(value_title, names, values, errors, spread_n):
    body = [[name,
             "n/a" if math.isnan(value) else f"{value:.2f}",
             "n/a" if math.isnan(error) else f"{error:.2f}"]
            for name, value, error in zip(names, values, errors)]
    return Div(
        P("Relative contribution", style={**CAPTION_STYLE, "margin": "16px 0 6px 0"}),
        result_table(["Source", value_title,
                      f"Std. dev. of best {spread_n} trials"], body),
    )


def estimate_label(result):
    """What the contribution column holds: the optimised fit or a trial mean."""
    return "best fit" if result.refined else f"mean of best {len(result.top_scores)} trials"
