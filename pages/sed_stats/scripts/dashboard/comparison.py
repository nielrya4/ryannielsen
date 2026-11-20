"""
Comparing samples: a metric over every pair, as a Matrix.

The Comparison step reads either Lines (one dimension, the 1D metrics) or a
Raster (two dimensions, the 2D measures of Sundell & Saylor 2021) and makes the
same thing from both — a `Matrix` — so whatever reads a matrix doesn't care
which it came from. The comparison matrices tool is this plus `draw_matrix`.
"""
import math

import numpy as np

from antioch.elements import Div, P

from sed_stats import mds, metrics_2d
from workflow_lib import NodeProblem
from workflow_lib.types import Lines, Matrix, Raster

from .config import BIVARIATE_METRICS, METRICS
from .tables import result_table

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
NOTE_STYLE = {"color": "#6c757d"}


def metrics_for(data_type):
    """The metrics that apply to Lines (1D) or a Raster (2D)."""
    return BIVARIATE_METRICS if data_type == "raster" else METRICS


def compare(datum, metric_key):
    """
    The matrix of `metric_key` over every pair of samples in `datum`.

    Raises:
        NodeProblem: with fewer than two samples, or input that is not
            something samples can be compared on
    """
    if isinstance(datum, Lines):
        metric = METRICS[metric_key]
        matrix = matrix_from_series(datum.name, datum.series(metric["input"]),
                                    metric_key)
        if datum.note.startswith("Pooled"):
            matrix.warning = datum.note
        return matrix
    if isinstance(datum, Raster):
        matrix = matrix_from_entries(datum.x_name, datum.y_name,
                                     datum.density_set, metric_key)
        if datum.note:
            matrix.warning = f"{datum.note} {matrix.warning}".strip()
        return matrix
    raise NodeProblem("A comparison needs lines or rasters to compare.")


def matrix_from_series(name, series, metric_key):
    """`series` is [(sample, values)], already in the form the metric reads."""
    metric = METRICS[metric_key]
    if len(series) < 2:
        raise NodeProblem("Need at least two samples with data to compare.")
    # sed_stats.metrics operates on arrays, not lists.
    arrays = [(sample, np.array(data, dtype=float)) for sample, data in series]
    values = _pairwise(arrays, metric["func"])
    return Matrix(
        name=name, names=[sample for sample, _ in arrays], values=values,
        metric_label=metric["label"],
        note=f"{metric['label']} ({metric['note']})",
        dissimilarity=lambda: mds.dissimilarity_matrix(arrays, metric_key))


def matrix_from_entries(x_name, y_name, density_set, metric_key):
    """The 2D version, over a BivariateSet's per-sample densities."""
    metric = BIVARIATE_METRICS[metric_key]
    entries = density_set.entries
    if len(entries) < 2:
        raise NodeProblem("Need at least two samples with paired values to compare.")
    values = _pairwise(entries, metric["func"])
    label = f"{x_name} vs {y_name}"
    return Matrix(
        name=label, names=[sample for sample, _ in entries], values=values,
        metric_label=metric["label"],
        note=(f"{metric['label']} of {label} ({metric['note']}) — "
              f"{density_set.method_note}, {len(density_set.x_values)}×"
              f"{len(density_set.y_values)} grid."),
        dissimilarity=lambda: metrics_2d.dissimilarity_matrix_2d(entries, metric_key),
        warning=density_set.order_warning(metric_key) or "")


def match_sets(candidates, references, metric_key):
    """
    How alike each candidate is to each empirical sample: a Matrix with a row per
    candidate and a column per reference, under a metric.

    Unlike a Comparison of everything together, it never sets the candidates against
    themselves or the empirical samples against each other, which is the comparison
    that was not wanted. Both sets are put on one grid first. The note names the best
    match for each candidate — the highest value, or the lowest for a measure like
    Kuiper that counts differences.

    Args:
        candidates, references: Lines, or Rasters; both the same kind

    Raises:
        NodeProblem: for a mix of kinds, or nothing to compare
    """
    from .combine import combine
    if isinstance(candidates, Lines) and isinstance(references, Lines):
        metric = METRICS[metric_key]
        count = len(candidates.pdf)
        names = [name for name, _ in candidates.pdf]
        columns = [name for name, _ in references.pdf]
        pooled = combine([candidates, references])
        series = [np.array(curve, dtype=float) for _, curve in pooled.series(metric["input"])]
        label = references.name
    elif isinstance(candidates, Raster) and isinstance(references, Raster):
        metric = BIVARIATE_METRICS[metric_key]
        count = len(candidates.density_set.entries)
        names = [name for name, _ in candidates.density_set.entries]
        columns = [name for name, _ in references.density_set.entries]
        pooled = combine([candidates, references])
        series = [dist for _, dist in pooled.density_set.entries]
        label = references.name
    else:
        raise NodeProblem("The candidates and the empirical sources must both be lines, or "
                          "both rasters.")
    if not names or not columns:
        raise NodeProblem("Need at least one candidate and one empirical sample to match.")

    rows = [[float(metric["func"](a, b)) for b in series[count:]] for a in series[:count]]
    higher = "higher" in metric["note"]
    best = []
    for name, row in zip(names, rows):
        usable = [(v, c) for v, c in zip(row, columns) if not math.isnan(v)]
        if usable:
            value, column = (max if higher else min)(usable)
            best.append(f"{name} ↔ {column} ({value:.3g})")
    note = (f"{metric['label']} ({metric['note']}) between each of {len(names)} candidates "
            f"and each of {len(columns)} empirical samples, over {label}."
            + (" Best match: " + "; ".join(best) + "." if best else ""))
    return Matrix(name=f"{label}: candidates vs empirical sources", names=names,
                  columns=columns, values=rows, metric_label=metric["label"], note=note,
                  warning=pooled.note if pooled.note.startswith("Pooled") else "")


def _pairwise(items, func):
    """n×n of `func` over every ordered pair; the diagonal is None."""
    rows = []
    for name_i, data_i in items:
        row = []
        for name_j, data_j in items:
            row.append(None if name_i == name_j else float(func(data_i, data_j)))
        rows.append(row)
    return rows


def draw_matrix(matrix):
    """A matrix as a table. r2 and the like are undefined for a flat sample: n/a."""
    cells = []
    for name, row in zip(matrix.names, matrix.values):
        cells.append([name] + ["—" if v is None else
                               "n/a" if math.isnan(v) else f"{v:.3g}"
                               for v in row])
    body = Div(P(matrix.note, style=CAPTION_STYLE),
               result_table(["Sample"] + list(matrix.columns or matrix.names), cells))
    if matrix.warning:
        body.add(P(matrix.warning, style=NOTE_STYLE))
    return body
