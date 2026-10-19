"""The Bivariate MDS tool's output: an ordination of 2D dissimilarities."""
from antioch.elements import Div, P

from sed_stats import mds, metrics_2d

from .bivariate import prepare
from .config import BIVARIATE_METRICS, MDS_TYPES
from .mds_plot import CAPTION_STYLE, _map_traces, _shepard_section
from .plots import make_plot


def build_bivariate_mds(charts, rows, sample_col, dimension, opts):
    """
    `dimension` is the y variable; x is fixed for the whole output.

    Only the dissimilarity matrix differs from the univariate MDS — the
    embedding, stress and Shepard diagram all take a precomputed matrix, so
    they are reused as-is.
    """
    density_set, problem = prepare(rows, sample_col, dimension, opts,
                                   min_samples=3, purpose="run MDS")
    if problem:
        return problem
    x_dimension = opts["x_dimension"]
    metric = opts["metric"]

    matrix = metrics_2d.dissimilarity_matrix_2d(density_set.entries, metric)
    non_metric = opts["mds_type"] == "non_metric"
    embedding, stress = mds.compute_mds(matrix, non_metric=non_metric)
    points = mds.mds_points(density_set.entries, matrix, embedding)

    label = f"{x_dimension} vs {dimension}"
    wrapper = Div(
        P(f"{MDS_TYPES[opts['mds_type']]} on 2D "
          f"{BIVARIATE_METRICS[metric]['label']} dissimilarity of {label} — "
          f"Kruskal stress-1: {stress:.4f}. {density_set.method_note.capitalize()}.",
          style=CAPTION_STYLE),
        Div(make_plot(charts, _map_traces(points), f"{label} — 2D MDS",
                      "Dimension 1", "Dimension 2",
                      filename=f"{x_dimension}_{dimension}_mds_2d").element),
    )

    if opts.get("shepard"):
        wrapper.add(*_shepard_section(charts, label, matrix, embedding,
                                      non_metric, stress))
    return wrapper
