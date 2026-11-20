"""
The Sample PCA tool: one point per sample, from the samples' distributions.

Where the grain-level tool (pca_axes) fits a PCA across every grain and writes
scores back onto the grains, this one treats each sample as a single
observation. Its features are the sample's distribution for each chosen
dimension — the PDP of an age, the share of each polymer — laid end to end, so
a categorical dimension needs no encoding. Samples that plot close together
have similar distributions, and the loadings say which bins or categories
separate them.
"""
from collections import Counter

import numpy as np

from antioch.elements import Div, P

from plot_lib import bar_trace, categorical_color, line_trace, marker_trace, series_color
from sed_stats import pca
from workflow_lib import NodeProblem

from .dataset import is_numeric_column, series_for, values_by_sample
from .plots import make_plot
from .tables import result_table

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
NOTE_STYLE = {"color": "#6c757d"}
SECTION_STYLE = {**CAPTION_STYLE, "margin": "16px 0 6px 0"}

NO_COLOR = "(none)"
COMPONENT_COLORS = ("#2a78d6", "#eb6834")


def fit_sample_pca(rows, sample_col, dimensions, opts):
    """
    Fit the sample-level PCA.

    Returns:
        (result, samples, labels, categorical, dropped): the fit; the samples
        it covers, in order; each dimension's grid labels; which dimensions are
        categorical; and the samples left out for missing data

    Raises:
        NodeProblem: with no dimensions, or fewer than three samples
    """
    if not dimensions:
        raise NodeProblem("Choose at least one dimension.")

    blocks, labels, categorical, dropped = _feature_blocks(
        rows, sample_col, dimensions, opts)
    samples = blocks["samples"]
    if len(samples) < 3:
        raise NodeProblem("Need at least three samples with data for every "
                          "chosen dimension.")

    matrices = []
    for dimension in dimensions:
        matrix = blocks[dimension]
        if opts.get("clr") and categorical[dimension]:
            matrix = pca.clr(matrix)
        matrices.append((dimension, matrix))
    result = pca.combined_pca(matrices, samples, n_components=2)
    return result, samples, labels, categorical, dropped


def draw_report(charts, result, dimensions, labels, categorical, scree):
    """What drives the map: each dimension's share of each component, the
    loadings across its bins or categories, and optionally the scree plot."""
    wrapper = Div()
    if len(dimensions) > 1:
        wrapper.add(_contribution_table(result))
    for dimension in dimensions:
        wrapper.add(*_loadings_section(charts, result, dimension, labels[dimension],
                                       categorical[dimension]))
    if scree:
        wrapper.add(*_scree_section(charts, result))
    return wrapper


def _feature_blocks(rows, sample_col, dimensions, opts):
    """
    Each dimension as an (n_samples, n_bins) matrix over the samples that have
    data for every dimension.

    Returns:
        (blocks, labels, categorical, dropped) where blocks maps each
        dimension to its matrix and "samples" to the shared row order
    """
    series_by_dimension = {}
    labels = {}
    categorical = {}
    for dimension in dimensions:
        grid, series = series_for(rows, sample_col, dimension, "pdf", opts)
        series_by_dimension[dimension] = dict(series)
        labels[dimension] = list(grid)
        categorical[dimension] = not is_numeric_column(rows, dimension)

    requested = list(opts.get("samples") or [])
    first = series_by_dimension[dimensions[0]]
    order = requested or list(first)
    samples = [s for s in order
               if all(s in series_by_dimension[d] for d in dimensions)]
    dropped = [s for s in order if s not in samples]

    blocks = {"samples": samples}
    for dimension in dimensions:
        blocks[dimension] = np.asarray(
            [series_by_dimension[dimension][s] for s in samples], dtype=float)
    return blocks, labels, categorical, dropped


def color_groups(rows, sample_col, samples, attribute):
    """
    How the sample points are coloured.

    Returns a dict with "legend" (whether a legend helps), and either
    "values" (a number per sample, drawn on a continuous scale), "groups" (an
    ordered {name: [sample indexes]}), or neither for one colour per sample.
    """
    if not attribute or attribute == NO_COLOR:
        return {"legend": False, "title": None}

    grouped = values_by_sample(rows, sample_col, attribute, set(samples))
    if is_numeric_column(rows, attribute):
        means = [(float(np.mean([float(v) for v in grouped[s]])) if s in grouped
                  else float("nan")) for s in samples]
        return {"legend": False, "title": attribute, "values": means}

    labels = [Counter(str(v) for v in grouped[s]).most_common(1)[0][0]
              if s in grouped else "no data" for s in samples]
    groups = {}
    for index, label in enumerate(labels):
        groups.setdefault(label, []).append(index)
    return {"legend": True, "title": attribute, "groups": groups}


def map_traces(xs, ys, samples, colors):
    """The sample points, coloured as `color_groups` says."""
    if "values" in colors:
        return [{
            "type": "scatter", "mode": "markers+text",
            "x": xs, "y": ys, "text": list(samples),
            "textposition": "top center", "textfont": {"size": 10},
            "showlegend": False, "name": "Samples",
            "marker": {"size": 13, "color": colors["values"],
                       "colorscale": "Viridis", "showscale": True,
                       "colorbar": {"title": {"text": colors["title"],
                                              "side": "right"}}},
        }]

    if "groups" in colors:
        return [marker_trace([xs[i] for i in members], [ys[i] for i in members],
                             name, color=categorical_color(k), size=12,
                             labels=[samples[i] for i in members])
                for k, (name, members) in enumerate(colors["groups"].items())]

    return [marker_trace([x], [y], sample, size=12, labels=[sample],
                         color=series_color(i, len(samples)))
            for i, (sample, x, y) in enumerate(zip(samples, xs, ys))]


def _contribution_table(result):
    """How much each dimension drives each component, as percentages."""
    first = dict(result.block_contributions(0))
    second = dict(result.block_contributions(1)) if result.components.shape[0] > 1 else {}
    body = [[name, f"{first[name] * 100:.1f}%",
             f"{second.get(name, 0.0) * 100:.1f}%"] for name in first]
    return Div(
        P("Which dimension drives each component — shares sum to 100% down a "
          "column.", style=SECTION_STYLE),
        result_table(["Dimension", f"PC1 ({result.percent(0):.1f}%)",
                      f"PC2 ({result.percent(1):.1f}%)"], body),
    )


def _loadings_section(charts, result, dimension, labels, is_categorical):
    """PC1 and PC2 loadings across one dimension's bins or categories."""
    start, stop = next((a, b) for name, a, b in result.blocks if name == dimension)
    traces = []
    for axis in range(min(2, result.components.shape[0])):
        values = [float(v) for v in result.components[axis, start:stop]]
        name = f"PC{axis + 1}"
        color = COMPONENT_COLORS[axis]
        traces.append(bar_trace(labels, values, name, color) if is_categorical
                      else line_trace(labels, values, name, color))

    caption = P(f"Loadings across {dimension} — where a component is positive, "
                f"samples rich in that part sit toward the positive end; "
                f"opposite signs are a trade-off.", style=SECTION_STYLE)
    layout = {"yaxis": {"title": {"text": "Loading"}, "rangemode": "normal"}}
    if is_categorical:
        layout["xaxis"] = {"title": {"text": dimension}, "type": "category",
                           "tickangle": -45}
        layout["margin"] = {"l": 60, "r": 20, "t": 50, "b": 110}
    plot = Div(make_plot(
        charts, traces, f"{dimension} — loadings", dimension, "Loading",
        height=340, show_legend=True, filename=f"{dimension}_sample_pca_loadings",
        extra_layout=layout,
    ).element)
    return caption, plot


def _scree_section(charts, result):
    ratios = [float(r) * 100 for r in result.explained_ratio_all]
    names = [f"PC{i + 1}" for i in range(len(ratios))]
    caption = P("Scree plot — variance carried by each component. A steep drop "
                "after PC1 or PC2 means two axes describe the samples well; with "
                "n samples there are at most n − 1 components.",
                style=SECTION_STYLE)
    plot = Div(make_plot(
        charts, [bar_trace(names, ratios, "Explained variance", color="#3b6fb6")],
        "Sample PCA — scree", "Component", "% variance",
        height=320, show_legend=False, filename="sample_pca_scree",
        extra_layout={"xaxis": {"title": {"text": "Component"}, "type": "category"}},
    ).element)
    return caption, plot
