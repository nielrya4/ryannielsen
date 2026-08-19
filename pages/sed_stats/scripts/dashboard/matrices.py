"""The Comparison matrices tool's output: every sample pair under one metric."""
import math

import numpy as np

from antioch.elements import Div, P, Table, Td, Th, Tr

from .config import CHART_WIDTH, METRICS
from .dataset import attribute_series

CELL_STYLE = {
    "border": "1px solid #ddd", "padding": "4px 8px",
    "text-align": "right", "font-size": "13px",
}
HEAD_STYLE = {**CELL_STYLE, "text-align": "center", "background-color": "#f8f9fa"}


def build_matrix(charts, rows, sample_col, dimension, opts):
    metric = METRICS[opts["metric"]]
    _, series = attribute_series(
        rows, sample_col, dimension, metric["input"], opts["bin_size"], opts["samples"]
    )
    if len(series) < 2:
        return P("Need at least two samples with data to compare.",
                 style={"color": "#6c757d"})

    # sed_stats.metrics operates on arrays, not lists.
    series = [(name, np.array(data, dtype=float)) for name, data in series]

    header = Tr(Th("", style=HEAD_STYLE),
                *[Th(name, style=HEAD_STYLE) for name, _ in series])
    body_rows = []
    for name_i, data_i in series:
        cells = [Th(name_i, style=HEAD_STYLE)]
        for name_j, data_j in series:
            if name_i == name_j:
                cells.append(Td("—", style=CELL_STYLE))
            else:
                value = float(metric["func"](data_i, data_j))
                # r2 is undefined when a sample has no variance across bins
                text = "n/a" if math.isnan(value) else f"{value:.3g}"
                cells.append(Td(text, style=CELL_STYLE))
        body_rows.append(Tr(*cells))

    return Div(
        P(f"{metric['label']} ({metric['note']})",
          style={"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}),
        Div(
            Table(header, *body_rows, style={"border-collapse": "collapse"}),
            style={"overflow-x": "auto", "max-width": f"{CHART_WIDTH}px"},
        ),
    )
