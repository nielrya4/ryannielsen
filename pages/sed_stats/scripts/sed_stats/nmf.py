"""
Non-negative matrix factorization of detrital geochronological data.

After Saylor, Sundell & Sharman (2019), "Characterizing sediment sources by
non-negative matrix factorization of detrital geochronological data", Earth and
Planetary Science Letters 512, 46-58.

The sink samples' distributions form a matrix V, one row per sample and one
column per bin of a shared grid. NMF finds sources H and weights W, all
non-negative, with V ~ W H: row i of W says how much of each source sample i
holds, and row j of H is source j's own distribution. The inversion is not unique
and wants more sink samples than sources, which `separability_warnings` checks.

What follows the paper:
    - V holds finite mixture distributions (PDPs or KDEs), never ECDFs.
    - The objective is the Euclidean distance, 1/2 ||V - W H||^2.
    - Each sample's weights sum to one and each source distribution sums to one.
    - The number of sources is the breakpoint of the final residual plotted against
      rank: two straight lines are fitted, one over the low ranks and one over the
      high, and the rank that minimises the sum of their squared residuals is chosen
      (`breakpoint_rank`).

What does not: the paper alternates non-negative least squares. This uses
hierarchical alternating least squares (Cichocki & Phan 2009), which minimises the
same objective by coordinate descent but is cheap enough to scan every rank in the
browser. Both reach stationary points of that objective from random starts; the
number of restarts, the stopping rule and the seed are this module's own choices.
"""
from dataclasses import dataclass

import numpy as np

EPS = 1e-12


@dataclass
class NMFResult:
    """
    Attributes:
        weights: (n_samples, rank) — each row sums to 1
        sources: (rank, n_bins) — each row sums to 1
        residual: the Frobenius norm of V - W H, after normalising
        rank: the number of sources
        iterations: iterations the best restart took
    """
    weights: np.ndarray
    sources: np.ndarray
    residual: float
    rank: int
    iterations: int = 0

    def reconstruction(self):
        return self.weights @ self.sources


def _hals(V, rank, rng, max_iter, tol):
    """One factorization from a random start; W and H unnormalised."""
    n, m = V.shape
    scale = np.sqrt(max(V.mean(), EPS) / rank)
    W = rng.random((n, rank)) * scale + EPS
    H = rng.random((rank, m)) * scale + EPS
    previous = np.inf
    iteration = 0
    for iteration in range(1, max_iter + 1):
        # H, one source at a time, against the current weights.
        WtV, WtW = W.T @ V, W.T @ W
        for j in range(rank):
            if WtW[j, j] < EPS:                     # a source that died: restart it
                H[j] = rng.random(m) * scale + EPS
                continue
            H[j] = np.maximum(
                EPS, H[j] + (WtV[j] - WtW[j] @ H) / WtW[j, j])
        # Then W, one source at a time, against the new sources.
        VHt, HHt = V @ H.T, H @ H.T
        for j in range(rank):
            if HHt[j, j] < EPS:
                continue
            W[:, j] = np.maximum(
                EPS, W[:, j] + (VHt[:, j] - W @ HHt[:, j]) / HHt[j, j])
        error = np.linalg.norm(V - W @ H)
        if previous - error <= tol * max(previous, EPS) and iteration > 5:
            break
        previous = error
    return W, H, iteration


def _normalise(W, H):
    """Sources that sum to one, weights that sum to one, reconstruction kept."""
    scale = H.sum(axis=1)
    scale[scale < EPS] = 1.0
    H = H / scale[:, None]
    W = W * scale[None, :]
    totals = W.sum(axis=1)
    totals[totals < EPS] = 1.0
    return W / totals[:, None], H


def factorize(V, rank, restarts=10, max_iter=500, tol=1e-7, seed=0):
    """
    Factorize V into `rank` sources, keeping the best of several random starts.

    Args:
        V: (n_samples, n_bins) non-negative, each row a distribution
        rank: number of sources, at least 1 and at most the number of samples
        restarts: random starts; the lowest final residual wins
        seed: fixes the starts, so the same data gives the same answer

    Raises:
        ValueError: for a rank that cannot be fitted, or negative data
    """
    V = np.asarray(V, dtype=float)
    if V.ndim != 2 or V.size == 0:
        raise ValueError("The data must be a samples-by-bins table.")
    if (V < 0).any():
        raise ValueError("NMF needs non-negative data.")
    if not 1 <= rank <= V.shape[0]:
        raise ValueError(f"The number of sources must be between 1 and the number "
                         f"of samples ({V.shape[0]}).")
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(max(1, restarts)):
        W, H, iterations = _hals(V, rank, rng, max_iter, tol)
        W, H = _normalise(W, H)
        residual = float(np.linalg.norm(V - W @ H))
        if best is None or residual < best.residual:
            best = NMFResult(W, H, residual, rank, iterations)
    return best


def scan_ranks(V, ranks, **kwargs):
    """{rank: NMFResult} for each rank, for choosing how many sources there are."""
    return {rank: factorize(V, rank, **kwargs) for rank in ranks}


def _line_ssr(x, y):
    """Squared residual of the least-squares line through the points (0 for two or fewer)."""
    if len(x) <= 2:
        return 0.0
    slope, intercept = np.polyfit(x, y, 1)
    return float(np.sum((y - (slope * x + intercept)) ** 2))


def breakpoint_rank(ranks, residuals):
    """
    The number of sources, from how the final residual falls with rank.

    The residual drops quickly until the true number of sources is reached and
    slowly after. Two straight lines are fitted — one over the ranks up to a
    candidate breakpoint and one from it onwards, each by least squares — and the
    candidate with the smallest total squared residual is the rank.

    Returns:
        (rank, totals): the chosen rank, and the summed squared residuals for
        every candidate, in the order of `ranks`

    Raises:
        ValueError: with fewer than three ranks, where there is no curve to bend
    """
    x = np.asarray(ranks, dtype=float)
    y = np.asarray(residuals, dtype=float)
    if len(x) < 3 or len(x) != len(y):
        raise ValueError("Choosing the number of sources needs at least three ranks.")
    totals = [_line_ssr(x[:i + 1], y[:i + 1]) + _line_ssr(x[i:], y[i:])
              for i in range(len(x))]
    return int(x[int(np.argmin(totals))]), totals


def fit_quality(V, result):
    """R^2 between each sample's distribution and its reconstruction (Pearson, as
    the paper's cross-correlation)."""
    rebuilt = result.reconstruction()
    out = []
    for observed, modelled in zip(np.asarray(V, float), rebuilt):
        if observed.std() < EPS or modelled.std() < EPS:
            out.append(float("nan"))
        else:
            out.append(float(np.corrcoef(observed, modelled)[0, 1] ** 2))
    return out


def separability_warnings(V, rank):
    """
    The paper's conditions for trusting a factorization, as plain sentences for
    whichever are not met. Its simulations found sources recovered well when there
    were more than about three times as many sink samples as sources, and the
    sinks differed from one another (their cross-correlation coefficients spanning
    more than 0.3).
    """
    V = np.asarray(V, dtype=float)
    notes = []
    samples = V.shape[0]
    if samples < 3 * rank:
        notes.append(
            f"{samples} samples is fewer than three times {rank} sources. In "
            "Saylor et al.'s tests sources were recovered reliably only with more "
            "than about three times as many sink samples as sources.")
    if samples >= 3:
        r2 = np.corrcoef(V) ** 2
        pairs = r2[np.triu_indices(samples, k=1)]
        pairs = pairs[~np.isnan(pairs)]
        if pairs.size and pairs.max() - pairs.min() < 0.3:
            notes.append(
                "The samples are very alike (their cross-correlation spans "
                f"{pairs.max() - pairs.min():.2f}, under 0.3), which makes the "
                "sources poorly constrained.")
    return notes
