"""
NMF in the dashboard: from per-sample curves to sources and weights, and the report.

`factorize_lines` turns a Distribution's Lines into `Factors` (see `sed_stats.nmf`
for the method and how it differs from the paper); `sources_as_lines` hands the
sources back as Lines so they can be compared with real samples; `draw_factors`
reports on it: how the number of sources was chosen, what the sources look like,
what each sample is made of, and how well the sources rebuild the samples.
"""
import math

import numpy as np

from antioch.elements import Div, P

from plot_lib import bar_trace, categorical_color, line_trace
from sed_stats import nmf
from workflow_lib import NodeProblem
from workflow_lib.types import Factors, Lines, Matrix

from .plots import make_plot
from .tables import result_table

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
WARNING_STYLE = {"font-size": "13px", "color": "#8a5a00", "background-color": "#fff8e6",
                 "border": "1px solid #f0d9a0", "border-radius": "4px",
                 "padding": "6px 10px", "margin": "0 0 8px 0"}
SECTION_STYLE = {**CAPTION_STYLE, "margin": "16px 0 6px 0"}
DEFAULT_MAX_SOURCES = 8
# Choosing the rank needs a bend to find: ranks 2, 3 and 4 at the least.
MIN_SAMPLES_FOR_AUTO = 4


def factorize_lines(lines, opts):
    """
    Factorize the samples of `lines` into sources.

    Options: rank_mode ("auto" picks the number of sources from the residual curve,
    "fixed" uses `sources`), sources, max_sources (the most ranks tried), restarts.

    Raises:
        NodeProblem: for too few samples, or more sources than samples
    """
    names = [sample for sample, _ in lines.pdf]
    V = np.array([curve for _, curve in lines.pdf], dtype=float)
    samples = len(names)
    restarts = int(opts.get("restarts") or 5)

    if opts.get("rank_mode", "auto") == "auto":
        top = min(int(opts.get("max_sources") or DEFAULT_MAX_SOURCES), samples)
        if samples < MIN_SAMPLES_FOR_AUTO or top < 4:
            raise NodeProblem(
                "Choosing the number of sources automatically fits a curve through the "
                "residuals for ranks 2 and up, so it needs at least four samples. With "
                "fewer, set the number of sources yourself.")
        ranks = list(range(2, top + 1))
        scanned = nmf.scan_ranks(V, ranks, restarts=restarts)
        residuals = [scanned[r].residual for r in ranks]
        chosen, totals = nmf.breakpoint_rank(ranks, residuals)
        best, automatic = scanned[chosen], True
    else:
        k = int(opts.get("sources") or 3)
        if not 1 <= k <= samples:
            raise NodeProblem(f"The number of sources must be between 1 and the number "
                              f"of samples ({samples}).")
        best = nmf.factorize(V, k, restarts=restarts)
        ranks, residuals, totals, automatic = [k], [best.residual], [], False

    warnings = nmf.separability_warnings(V, best.rank)
    if automatic and "spread by its uncertainty" in lines.note:
        warnings.append(
            "These curves are PDPs, each grain spread by its own uncertainty. For precisely "
            "dated grains PDPs are so spiky that their noise keeps the residual falling past "
            "the true number of sources, so the automatic choice can come out too low. A "
            "KDE (the density method the NMF sources tool starts from) smooths that away.")
    order = _by_position(best, lines)
    sources = best.sources[order]
    weights = best.weights[:, order]
    labels = [f"Source {i + 1}" for i in range(len(order))]
    shuffled = nmf.NMFResult(weights, sources, best.residual, best.rank)
    return Factors(
        name=lines.name, x=list(lines.x), sample_names=names, source_names=labels,
        sources=sources.tolist(), weights=weights.tolist(), ranks=ranks,
        residuals=residuals, totals=list(totals), automatic=automatic,
        quality=nmf.fit_quality(V, shuffled),
        warnings=warnings,
        categorical=lines.categorical)


def _by_position(result, lines):
    """Sources in order along the axis (youngest first), so Source 1 means the same
    thing from one run to the next; categories have no order, so keep the order found."""
    if lines.categorical:
        return np.arange(result.rank)
    x = np.array([float(v) for v in lines.x])
    return np.argsort(result.sources @ x)


def weights_matrix(factors):
    """How much of each source every sample holds, as a Matrix: a row per sample, a
    column per source, in percent."""
    return Matrix(
        name=f"{factors.name}: NMF weights", names=list(factors.sample_names),
        columns=list(factors.source_names),
        values=[[100.0 * w for w in row] for row in factors.weights],
        metric_label="% of sample",
        note=f"The share of each NMF source in each sample of {factors.name}, as a "
             "percentage; each row sums to 100.")


def sources_as_lines(factors):
    """The factorized sources as Lines, to plot or compare with real samples."""
    pdf = list(zip(factors.source_names, factors.sources))
    cdf = [(name, np.cumsum(curve).tolist()) for name, curve in pdf]
    return Lines(f"{factors.name} sources", list(factors.x), pdf, cdf,
                 categorical=factors.categorical,
                 note=f"{factors.rank} sources factorized by NMF.")


# ----------------------------------------------------------------------- report

def draw_factors(charts, factors):
    wrapper = Div(P(_summary(factors), style=CAPTION_STYLE))
    for warning in factors.warnings:
        wrapper.add(P(warning, style=WARNING_STYLE))
    if len(factors.ranks) > 1:
        wrapper.add(*_rank_section(charts, factors))
    wrapper.add(*_sources_section(charts, factors))
    wrapper.add(*_mixing_section(charts, factors))
    return wrapper


def _summary(factors):
    how = ("chosen from where the residual curve bends" if factors.automatic
           else "set by you")
    quality = [q for q in factors.quality if not math.isnan(q)]
    fit = (f" On average the sources rebuild a sample with R² = "
           f"{sum(quality) / len(quality):.3f}." if quality else "")
    return (f"{len(factors.sample_names)} samples of {factors.name} factorized into "
            f"{factors.rank} source{'s' if factors.rank != 1 else ''} ({how}).{fit}")


def _rank_section(charts, factors):
    """The residual at each rank, and the search for the bend in it."""
    chosen = factors.rank
    marker = [("circle-open" if r == chosen else "circle") for r in factors.ranks]
    trace = line_trace(factors.ranks, factors.residuals, "Final residual",
                       color="#3b6fb6", markers=True)
    trace["marker"] = {"size": [13 if r == chosen else 6 for r in factors.ranks],
                       "color": "#3b6fb6", "symbol": marker,
                       "line": {"width": 2, "color": "#d62728"}}
    caption = P(f"Residual against number of sources. It falls steeply until the true "
                f"number is reached and slowly after; two straight lines are fitted "
                f"either side of each candidate bend and the best fit is {chosen}.",
                style=SECTION_STYLE)
    layout = {"xaxis": {"title": {"text": "Number of sources"}, "dtick": 1},
              "yaxis": {"title": {"text": "‖V − WH‖"}, "rangemode": "tozero"}}
    plot = Div(make_plot(charts, [trace], f"{factors.name} — residual by rank",
                         "Number of sources", "Final residual", height=340,
                         show_legend=False, filename=f"{factors.name}_nmf_rank",
                         extra_layout=layout).element)
    parts = [caption, plot]
    if factors.totals:
        bends = line_trace(factors.ranks, factors.totals, "Summed squared residuals",
                           color="#7f7f7f", markers=True)
        parts.append(Div(make_plot(
            charts, [bends], f"{factors.name} — search for the bend",
            "Candidate number of sources", "SSR₁ + SSR₂", height=300,
            show_legend=False, filename=f"{factors.name}_nmf_bend",
            extra_layout={"xaxis": {"dtick": 1}}).element))
    return parts


def _sources_section(charts, factors):
    traces = []
    for i, (name, curve) in enumerate(zip(factors.source_names, factors.sources)):
        color = categorical_color(i)
        traces.append(bar_trace(factors.x, curve, name, color) if factors.categorical
                      else line_trace(factors.x, curve, name, color=color))
    caption = P("The sources the samples are made of. Each is a distribution summing to "
                "one; compare them with candidate source samples by feeding them to a "
                "Comparison.", style=SECTION_STYLE)
    plot = Div(make_plot(charts, traces, f"{factors.name} — factorized sources",
                         factors.name, "Probability", filename=f"{factors.name}_nmf_sources").element)
    return caption, plot


def _mixing_section(charts, factors):
    """What each sample is made of: stacked bars, then the same as a table."""
    weights = np.array(factors.weights) * 100
    traces = [bar_trace(factors.sample_names, weights[:, j], name, categorical_color(j))
              for j, name in enumerate(factors.source_names)]
    caption = P("What each sample is made of: the share of each source, summing to "
                "100% down a bar.", style=SECTION_STYLE)
    plot = Div(make_plot(
        charts, traces, f"{factors.name} — source weights", "Sample", "% of sample",
        height=460, filename=f"{factors.name}_nmf_weights",
        extra_layout={"barmode": "stack",
                      "xaxis": {"title": {"text": "Sample"}, "type": "category",
                                "tickangle": -45},
                      "yaxis": {"title": {"text": "% of sample"}, "range": [0, 100]},
                      "margin": {"l": 60, "r": 20, "t": 50, "b": 150}}).element)
    rows = [[name] + [f"{w:.1f}" for w in row] + ["n/a" if math.isnan(q) else f"{q:.3f}"]
            for name, row, q in zip(factors.sample_names, weights, factors.quality)]
    table = result_table(["Sample"] + [f"{s} (%)" for s in factors.source_names]
                         + ["R² of rebuilt sample"], rows)
    return caption, plot, table
