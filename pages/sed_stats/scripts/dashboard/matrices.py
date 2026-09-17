"""The Comparison matrices tool's output: every sample pair under one metric."""
import math

import numpy as np

from antioch.elements import Div, P

from .config import METRICS
from .dataset import series_for
from .tables import result_table

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}


def build_matrix(charts, rows, sample_col, dimension, opts):
    metric = METRICS[opts["metric"]]
    _, series = series_for(rows, sample_col, dimension, metric["input"], opts)
    if len(series) < 2:
        return P("Need at least two samples with data to compare.",
                 style={"color": "#6c757d"})

    # sed_stats.metrics operates on arrays, not lists.
    series = [(name, np.array(data, dtype=float)) for name, data in series]

    names = [name for name, _ in series]
    body = []
    for name_i, data_i in series:
        cells = [name_i]
        for name_j, data_j in series:
            if name_i == name_j:
                cells.append("—")
            else:
                value = float(metric["func"](data_i, data_j))
                # r2 is undefined when a sample has no variance across bins
                cells.append("n/a" if math.isnan(value) else f"{value:.3g}")
        body.append(cells)

    return Div(
        P(f"{metric['label']} ({metric['note']})", style=CAPTION_STYLE),
        result_table(["Sample"] + names, body),
    )
