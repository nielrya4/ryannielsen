"""The MDS tool's output: the ordination map and its optional Shepard plot."""
import numpy as np

from antioch.elements import Div, P

from plot_lib import line_trace, marker_trace, series_color
from sed_stats import mds

from .config import METRICS, MDS_TYPES
from .dataset import attribute_series
from .plots import make_plot

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}


def build_mds(charts, rows, sample_col, dimension, opts):
    metric = opts["metric"]
    _, series = attribute_series(
        rows, sample_col, dimension, mds.expected_form(metric),
        opts["bin_size"], opts["samples"]
    )
    if len(series) < 3:
        return P("Need at least three samples with data for MDS.",
                 style={"color": "#6c757d"})

    non_metric = opts["mds_type"] == "non_metric"
    points, stress, matrix, embedding = mds.mds_function(series, metric, non_metric)

    wrapper = Div(
        P(f"{MDS_TYPES[opts['mds_type']]} on {METRICS[metric]['label']} "
          f"dissimilarity — Kruskal stress-1: {stress:.4f}", style=CAPTION_STYLE),
        Div(make_plot(charts, _map_traces(points), f"{dimension} — MDS",
                      "Dimension 1", "Dimension 2",
                      filename=f"{dimension}_mds").element),
    )

    if opts["shepard"]:
        wrapper.add(*_shepard_section(charts, dimension, matrix, embedding,
                                      non_metric, stress))
    return wrapper


def _map_traces(points):
    # Dashed segments joining each sample to its nearest neighbor. A None
    # breaks the line between segments; Plotly reads array entries as values,
    # so a non-numeric entry is simply a gap.
    nn_x, nn_y = [], []
    for point in points:
        if point.nearest_neighbor is not None:
            nn_x.extend([point.x, point.nearest_neighbor[0], None])
            nn_y.extend([point.y, point.nearest_neighbor[1], None])

    traces = []
    if nn_x:
        traces.append({
            "type": "scatter", "mode": "lines", "x": nn_x, "y": nn_y,
            "name": "Nearest neighbor",
            "line": {"color": "#999", "width": 1, "dash": "dash"},
            "connectgaps": False, "hoverinfo": "skip",
        })
    # Points are added after the connectors so they draw on top.
    traces.extend(
        marker_trace([p.x], [p.y], p.label,
                     color=series_color(i, len(points)), labels=[p.label])
        for i, p in enumerate(points)
    )
    return traces


def _shepard_section(charts, dimension, matrix, embedding, non_metric, stress):
    """Caption + plot comparing input dissimilarities to the embedding's distances."""
    shepard = mds.shepard_data(matrix, embedding, non_metric)
    dissimilarities = shepard["dissimilarities"]
    distances = shepard["distances"]
    max_val = float(max(dissimilarities.max(), distances.max())) if len(distances) else 1.0

    traces = [marker_trace(
        [float(d) for d in dissimilarities],
        [float(v) for v in distances],
        "Distances", color="rgba(54, 162, 235, 0.8)", size=7,
    )]
    if shepard["disparities"] is not None:
        order = np.argsort(dissimilarities)
        traces.append(line_trace(
            [float(dissimilarities[i]) for i in order],
            [float(shepard["disparities"][i]) for i in order],
            "Disparities", color="#d62728", markers=False,
        ))
    traces.append({
        "type": "scatter", "mode": "lines",
        "x": [0, max_val], "y": [0, max_val], "name": "1:1",
        "line": {"color": "#000", "width": 1, "dash": "dot"},
    })

    caption = P(f"Shepard plot — R² = {shepard['r2']:.3f}, stress-1 = {stress:.4f}",
                style={**CAPTION_STYLE, "margin": "16px 0 6px 0"})
    plot = Div(make_plot(charts, traces, f"{dimension} — Shepard plot",
                         "Dissimilarities", "Distances / disparities",
                         height=340, filename=f"{dimension}_shepard").element)
    return caption, plot
