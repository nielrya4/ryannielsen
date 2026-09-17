"""
Two-dimensional comparison measures.

Sundell & Saylor (2021), G-cubed 22, e2020GC009559, eqs 15-20.

Similarity, Likeness and Cross-correlation extend to 2D unchanged: eqs 15, 16
and 18 are their 1D counterparts summed over a matrix instead of a vector, so
those delegate to sed_stats.metrics on the flattened grid rather than
restating the arithmetic.

The K-S and Kuiper tests genuinely differ. A bivariate CDF depends on which
quadrant it accumulates toward, so following Peacock (1983) each statistic is
computed against all four and the largest reported.
"""
import numpy as np

from . import metrics
from .distributions.bivariate import BivariateDistribution, quadrant_cdfs


def _grid(distribution) -> np.ndarray:
    """Accept a BivariateDistribution or a raw 2-D array."""
    if isinstance(distribution, BivariateDistribution):
        return distribution.densities
    grid = np.asarray(distribution, dtype=float)
    if grid.ndim != 2:
        raise ValueError("Expected a 2-D density grid")
    return grid


def _pair(first, second):
    grid_1, grid_2 = _grid(first), _grid(second)
    if grid_1.shape != grid_2.shape:
        raise ValueError(
            f"Distributions must share a grid; got {grid_1.shape} and {grid_2.shape}")
    return grid_1, grid_2


# ------------------------------------------------------------ density measures

def similarity_2d(first, second) -> float:
    """S_2D (eq 15): sum of the geometric mean of each cell. 1 is identical."""
    grid_1, grid_2 = _pair(first, second)
    return float(metrics.similarity(grid_1.ravel(), grid_2.ravel()))


def mismatch_2d(first, second) -> float:
    """M_2D (eq 16): half the summed absolute difference. 0 is identical."""
    grid_1, grid_2 = _pair(first, second)
    return float(np.sum(np.abs(grid_1 - grid_2)) / 2)


def likeness_2d(first, second) -> float:
    """L_2D (eq 17): 1 - M_2D. 1 is identical."""
    grid_1, grid_2 = _pair(first, second)
    return float(metrics.likeness(grid_1.ravel(), grid_2.ravel()))


def r2_2d(first, second) -> float:
    """R²_2D (eq 18): squared Pearson correlation of the cells. 1 is identical."""
    grid_1, grid_2 = _pair(first, second)
    return float(metrics.r2(grid_1.ravel(), grid_2.ravel()))


# ---------------------------------------------------------------- CDF measures

def ks_2d(first, second) -> float:
    """
    D_2D (eq 19): the largest absolute CDF difference over all four quadrants.

    0 is identical.
    """
    grid_1, grid_2 = _pair(first, second)
    return float(max(
        np.abs(cdf_1 - cdf_2).max()
        for cdf_1, cdf_2 in zip(quadrant_cdfs(grid_1), quadrant_cdfs(grid_2))
    ))


def kuiper_2d(first, second) -> float:
    """
    V_2D (eq 20): max(CDF1 - CDF2) + max(CDF2 - CDF1), over all four quadrants.

    0 is identical.
    """
    grid_1, grid_2 = _pair(first, second)
    return float(max(
        (cdf_1 - cdf_2).max() + (cdf_2 - cdf_1).max()
        for cdf_1, cdf_2 in zip(quadrant_cdfs(grid_1), quadrant_cdfs(grid_2))
    ))


# ------------------------------------------------------------- dissimilarities

# Similarity, Likeness and Cross-correlation yield similarity matrices; MDS
# needs dissimilarity, which section 3.3 gets by subtracting from 1. K-S and
# Kuiper already measure dissimilarity.

def dis_similarity_2d(first, second) -> float:
    return float(1 - similarity_2d(first, second))


def dis_likeness_2d(first, second) -> float:
    return float(1 - likeness_2d(first, second))


def dis_r2_2d(first, second) -> float:
    return float(1 - r2_2d(first, second))


# ------------------------------------------------------- intermediate surfaces

# Similarity and Mismatch are sums over per-cell contributions, so the terms can
# be plotted before summing to show *where* two distributions agree or differ
# (the paper's Figures 2h and 2i). The others cannot: Likeness is already
# reduced to a scalar, and Cross-correlation involves several summations.

# Metric key -> dissimilarity function, matching sed_stats.mds's 1D table so
# the same MDS pipeline can consume either.
DISSIMILARITY_FUNCTIONS_2D = {
    "similarity": dis_similarity_2d,
    "likeness": dis_likeness_2d,
    "r2": dis_r2_2d,
    "ks": ks_2d,
    "kuiper": kuiper_2d,
}


def dissimilarity_matrix_2d(distributions, metric: str) -> np.ndarray:
    """
    Pairwise dissimilarity for bivariate distributions on a shared grid.

    Parameters:
        distributions: [(name, BivariateDistribution or 2-D array), ...]
        metric: key into DISSIMILARITY_FUNCTIONS_2D

    Returns:
        Symmetric (n, n) matrix with a zero diagonal, ready for
        sed_stats.mds.compute_mds
    """
    if metric not in DISSIMILARITY_FUNCTIONS_2D:
        raise ValueError(f"Unknown metric '{metric}'")
    func = DISSIMILARITY_FUNCTIONS_2D[metric]

    n = len(distributions)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            value = float(func(distributions[i][1], distributions[j][1]))
            # r2 is undefined for a flat grid; treat that as maximally dissimilar
            if np.isnan(value):
                value = 1.0
            matrix[i, j] = value
            matrix[j, i] = value
    return matrix


def similarity_surface(first, second) -> np.ndarray:
    """Per-cell geometric means; summing this gives S_2D."""
    grid_1, grid_2 = _pair(first, second)
    return np.sqrt(grid_1 * grid_2)


def mismatch_surface(first, second) -> np.ndarray:
    """Per-cell half-absolute-differences; summing this gives M_2D."""
    grid_1, grid_2 = _pair(first, second)
    return np.abs(grid_1 - grid_2) / 2
