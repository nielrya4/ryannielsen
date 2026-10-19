"""The Bivariate comparison tool's output: 2D measures for every sample pair."""
import math

from antioch.elements import Div, P

from .bivariate import prepare
from .config import BIVARIATE_METRICS
from .tables import result_table

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}


def build_bivariate_matrix(charts, rows, sample_col, dimension, opts):
    """`dimension` is the y variable; x is fixed for the whole output."""
    density_set, problem = prepare(rows, sample_col, dimension, opts,
                                   min_samples=2, purpose="compare")
    if problem:
        return problem
    x_dimension = opts["x_dimension"]
    metric = BIVARIATE_METRICS[opts["metric"]]

    entries = density_set.entries
    names = [name for name, _ in entries]

    body = []
    for name_i, distribution_i in entries:
        cells = [name_i]
        for name_j, distribution_j in entries:
            if name_i == name_j:
                cells.append("—")
            else:
                value = float(metric["func"](distribution_i, distribution_j))
                cells.append("n/a" if math.isnan(value) else f"{value:.3g}")
        body.append(cells)

    return Div(
        P(f"{metric['label']} of {x_dimension} vs {dimension} "
          f"({metric['note']}) — {density_set.method_note}, "
          f"{len(density_set.x_values)}×{len(density_set.y_values)} grid.",
          style=CAPTION_STYLE),
        result_table(["Sample"] + names, body),
    )
