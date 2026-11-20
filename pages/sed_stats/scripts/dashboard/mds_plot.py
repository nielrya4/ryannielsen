"""The MDS tool's output: the ordination map and its optional Shepard plot."""
import numpy as np

from antioch.elements import Div, P

from plot_lib import line_trace, marker_trace
from sed_stats import mds

from .plots import make_plot

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}


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
