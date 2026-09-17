"""
Multidimensional scaling over per-sample distributions.

Adapted from the dzToolBox implementation. Computation only — plotting is left
to the caller so the same results can be rendered with any charting library.
"""
import numpy as np

from . import metrics
from .smacof import isotonic_regression, smacof

# Metric key -> (function, distribution form it expects).
# similarity/likeness/r2 measure similarity, so their dis_* complements are
# used here; ks/kuiper are already distances and are used directly.
# Restarts per fit. The first begins at the classical MDS solution and the
# rest at random, guarding against a poor local minimum. Measured against
# scikit-learn across metric and non-metric fits, eight already wins or ties
# every case; sixteen doubles the time for an identical answer.
MDS_RESTARTS = 8

DISSIMILARITY_FUNCTIONS = {
    "similarity": (metrics.dis_similarity, "pdf"),
    "likeness": (metrics.dis_likeness, "pdf"),
    "r2": (metrics.dis_r2, "pdf"),
    "ks": (metrics.ks, "cdf"),
    "kuiper": (metrics.kuiper, "cdf"),
}


class MDSPoint:
    def __init__(self, x: float, y: float, label: str, nearest_neighbor: tuple = None):
        self.x = x
        self.y = y
        self.label = label
        self.nearest_neighbor = nearest_neighbor  # (x, y) or None


def expected_form(metric: str) -> str:
    """Whether `metric` should be fed PDFs or CDFs."""
    return DISSIMILARITY_FUNCTIONS[metric][1]


def dissimilarity_matrix(series, metric: str) -> np.ndarray:
    """
    Pairwise dissimilarity matrix for samples sharing a common grid.

    Parameters:
        series: [(sample_name, values), ...] where values are already in the
                form `metric` expects (see expected_form)
        metric: key into DISSIMILARITY_FUNCTIONS

    Returns:
        Symmetric (n, n) matrix with a zero diagonal
    """
    if metric not in DISSIMILARITY_FUNCTIONS:
        raise ValueError(f"Unknown metric '{metric}'")
    func, _ = DISSIMILARITY_FUNCTIONS[metric]

    n_samples = len(series)
    matrix = np.zeros((n_samples, n_samples))
    for i in range(n_samples):
        for j in range(i + 1, n_samples):
            value = float(func(np.asarray(series[i][1], dtype=float),
                               np.asarray(series[j][1], dtype=float)))
            # r2 is undefined for a flat sample; treat that as maximally dissimilar
            if np.isnan(value):
                value = 1.0
            matrix[i, j] = value
            matrix[j, i] = value  # matrix is symmetric
    return matrix


def compute_mds(matrix: np.ndarray, non_metric: bool = True, random_state: int = 0):
    """
    Run MDS on a precomputed dissimilarity matrix.

    Returns:
        (embedding, kruskal_stress) where embedding is an (n, 2) array

    `random_state` is pinned so the map stays put across re-renders rather
    than reshuffling every time a control changes.
    """
    embedding, kruskal_stress = smacof(
        matrix,
        n_components=2,
        metric=(not non_metric),
        n_init=MDS_RESTARTS,
        max_iter=1000,
        random_state=random_state,
    )

    # SMACOF fixes no absolute size — only the shape is determined — so the
    # embedding is rescaled to sit on the same scale as the dissimilarities
    # it came from. Uniform scaling leaves the topology untouched.
    upper = np.triu_indices_from(matrix, k=1)
    mean_dissimilarity = float(np.mean(matrix[upper])) if upper[0].size else 0.0
    spread = float(np.std(embedding))
    if spread > 0 and mean_dissimilarity > 0:
        embedding = embedding * (mean_dissimilarity / spread)

    return embedding, kruskal_stress


def mds_points(series, matrix: np.ndarray, embedding: np.ndarray):
    """Build MDSPoint list, each linked to its nearest neighbor."""
    points = []
    for i, (name, _) in enumerate(series):
        row = matrix[i].copy()
        row[i] = np.inf
        nearest = None
        if np.isfinite(row).any():
            j = int(np.argmin(row))
            nearest = (float(embedding[j][0]), float(embedding[j][1]))
        points.append(MDSPoint(float(embedding[i][0]), float(embedding[i][1]), name, nearest))
    return points


def mds_function(series, metric: str = "similarity", non_metric: bool = True):
    """
    Full MDS pipeline for a list of (sample_name, values) pairs.

    Returns:
        (points, kruskal_stress, matrix, embedding)
    """
    matrix = dissimilarity_matrix(series, metric)
    embedding, kruskal_stress = compute_mds(matrix, non_metric=non_metric)
    return mds_points(series, matrix, embedding), kruskal_stress, matrix, embedding


def shepard_data(matrix: np.ndarray, embedding: np.ndarray, non_metric: bool = True):
    """
    Shepard-diagram data: original dissimilarities vs. MDS distances.

    Returns a dict with `dissimilarities`, `distances`, `disparities`
    (isotonic fit, non-metric only) and `r2`.

    r2 is the correlation between dissimilarities and MDS distances rather
    than between disparities and distances — the latter is inflated because
    disparities are fitted directly to the distances.
    """
    upper = np.triu_indices_from(matrix, k=1)
    dissimilarities = matrix[upper].astype(float)
    distances = np.array([
        float(np.linalg.norm(embedding[i] - embedding[j])) for i, j in zip(*upper)
    ])

    disparities = None
    if non_metric and dissimilarities.size:
        disparities = isotonic_regression(dissimilarities, distances)

    r2 = 0.0
    if dissimilarities.size > 1 and np.std(dissimilarities) > 0 and np.std(distances) > 0:
        r2 = float(np.corrcoef(dissimilarities, distances)[0, 1] ** 2)

    return {
        "dissimilarities": dissimilarities,
        "distances": distances,
        "disparities": disparities,
        "r2": r2,
    }
