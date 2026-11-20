"""
Multidimensional scaling by majorization, and the isotonic fit it needs.

These replace scikit-learn's `manifold.MDS` and `isotonic.IsotonicRegression`.
Not for want of trust in those — they are the reference this was checked
against — but for weight: scikit-learn drags SciPy behind it, and the pair
costs about 19 MB of the roughly 22 MB this app downloads before it can run.
Two algorithms of a hundred lines each is a fair trade for that.

SMACOF (Scaling by MAjorizing A COmplicated Function, de Leeuw 1977) minimises
Kruskal's raw stress

    sigma(X) = sum over i<j of (d_ij(X) - dhat_ij)^2

by repeatedly applying the Guttman transform, which is guaranteed not to
increase the stress. In metric MDS the target dhat is the dissimilarity
itself; in non-metric MDS it is whatever monotonically increasing function of
the dissimilarities best fits the current distances — which is what the
isotonic regression supplies.
"""
import numpy as np


def isotonic_regression(x, y, weights=None) -> np.ndarray:
    """
    Fit a non-decreasing step function of `x` to `y`, by least squares.

    Pool Adjacent Violators: walk the points in order of `x` keeping a stack
    of blocks, and whenever a new block's mean falls below its predecessor's
    merge the two. Merging can cascade, but each point joins and leaves a
    block at most once, so the whole pass is linear.

    Ties in `x` are averaged before fitting. Without that, two points sharing
    an x could be given different fitted values, and the result would not be a
    function of x at all.

    Returns:
        Fitted values, in the order the inputs were given.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.shape != y.shape:
        raise ValueError("x and y must be the same length")
    if x.size == 0:
        return np.array([], dtype=float)

    w = np.ones(x.size) if weights is None else np.asarray(weights, dtype=float)

    # Stable sort, so equal x keep their input order and group together.
    order = np.argsort(x, kind="mergesort")
    x_sorted, y_sorted, w_sorted = x[order], y[order], w[order]

    # Collapse ties into one weighted point each. reduceat rather than a
    # comprehension over np.split: non-metric SMACOF calls this once per
    # iteration per restart, so it is genuinely hot.
    starts = np.concatenate(([0], np.flatnonzero(np.diff(x_sorted)) + 1))
    sizes = np.diff(np.append(starts, x_sorted.size))
    group_weight = np.add.reduceat(w_sorted, starts)
    weighted = np.add.reduceat(w_sorted * y_sorted, starts)
    group_value = np.where(group_weight > 0,
                           weighted / np.where(group_weight > 0, group_weight, 1),
                           np.add.reduceat(y_sorted, starts) / sizes)

    # PAVA over the collapsed points.
    value = np.empty(group_value.size)
    weight = np.empty(group_value.size)
    count = np.empty(group_value.size, dtype=int)
    top = 0
    for index in range(group_value.size):
        value[top] = group_value[index]
        weight[top] = group_weight[index]
        count[top] = 1
        while top > 0 and value[top - 1] > value[top]:
            combined = weight[top - 1] + weight[top]
            value[top - 1] = (
                (weight[top - 1] * value[top - 1] + weight[top] * value[top])
                / combined if combined > 0
                else (value[top - 1] + value[top]) / 2
            )
            weight[top - 1] = combined
            count[top - 1] += count[top]
            top -= 1
        top += 1

    # Back out to every original point: block value -> group -> input order.
    per_group = np.repeat(value[:top], count[:top])
    fitted = np.empty(x.size)
    fitted[order] = np.repeat(per_group, sizes)
    return fitted


def _pairwise_distances(points: np.ndarray) -> np.ndarray:
    """Euclidean distance matrix, with an exact zero diagonal."""
    squared = np.sum(points ** 2, axis=1)
    gram = points @ points.T
    distances = squared[:, None] + squared[None, :] - 2 * gram
    np.maximum(distances, 0, out=distances)
    np.sqrt(distances, out=distances)
    np.fill_diagonal(distances, 0.0)
    return distances


def classical_mds(dissimilarities: np.ndarray, n_components: int = 2) -> np.ndarray:
    """
    Torgerson scaling: an eigen-decomposition that lands near the answer.

    Used as SMACOF's starting point. A random start needs many restarts to
    avoid a poor local minimum; starting from the classical solution usually
    converges to a better one, and does so in the same place every time.
    """
    n = dissimilarities.shape[0]
    squared = dissimilarities ** 2
    # Double centering turns squared distances into a Gram matrix.
    centering = np.eye(n) - np.ones((n, n)) / n
    gram = -0.5 * centering @ squared @ centering
    gram = (gram + gram.T) / 2  # symmetrize away the rounding

    values, vectors = np.linalg.eigh(gram)
    # eigh returns ascending; the largest eigenvalues carry the structure.
    order = np.argsort(values)[::-1][:n_components]
    values, vectors = values[order], vectors[:, order]
    return vectors * np.sqrt(np.maximum(values, 0))


def _stress_1(distances, fitted) -> float:
    """
    Kruskal's stress-1: the residual, normalised by the distances themselves.

    Scale-invariant, which raw stress is not — and in non-metric MDS the
    configuration's overall size is free, so raw stress cannot be compared
    between runs at all. A configuration collapsing toward a point would post
    a flatteringly small raw stress while fitting nothing.
    """
    total = float(np.sum(distances ** 2))
    if total <= 0:
        return 1.0  # everything on top of everything: the worst possible fit
    return float(np.sqrt(np.sum((distances - fitted) ** 2) / total))


def _smacof_single(dissimilarities, n_components, metric, max_iter, eps,
                   init=None, rng=None):
    """One SMACOF run. Returns (embedding, stress-1, iterations)."""
    n = dissimilarities.shape[0]
    upper = np.triu_indices(n, k=1)
    delta = dissimilarities[upper]

    if init is not None:
        points = np.array(init, dtype=float)
    else:
        points = rng.uniform(-1.0, 1.0, size=(n, n_components))

    target = np.empty((n, n))
    previous = None
    stress = 0.0
    iteration = 0

    for iteration in range(1, max_iter + 1):
        distance_matrix = _pairwise_distances(points)
        distances = distance_matrix[upper]

        if metric:
            fitted = delta
        else:
            # The monotone transform of the dissimilarities that best matches
            # the current distances, rescaled to fix the arbitrary overall
            # size that a rank-only target would otherwise leave free.
            fitted = isotonic_regression(delta, distances)
            norm = np.sqrt(np.sum(fitted ** 2))
            if norm > 0:
                fitted = fitted * np.sqrt(fitted.size) / norm

        stress = float(np.sum((distances - fitted) ** 2))
        normalized_stress = _stress_1(distances, fitted)

        # Guttman transform. Zero distances would divide by zero; they also
        # contribute nothing, so their ratio is pinned to zero.
        target[upper] = fitted
        target.T[upper] = fitted
        np.fill_diagonal(target, 0.0)

        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(distance_matrix > 0, target / distance_matrix, 0.0)
        guttman = -ratio
        np.fill_diagonal(guttman, 0.0)
        np.fill_diagonal(guttman, -guttman.sum(axis=1))
        points = (guttman @ points) / n

        # Convergence on the stress relative to the configuration's own size,
        # so the test does not depend on how large the numbers happen to be.
        scale = np.sum(np.sqrt(np.sum(points ** 2, axis=1)))
        normalized = stress / scale if scale > 0 else stress
        if previous is not None and abs(previous - normalized) < eps:
            break
        previous = normalized

    return points, normalized_stress, iteration


def smacof(dissimilarities, n_components: int = 2, metric: bool = True,
           n_init: int = 8, max_iter: int = 300, eps: float = 1e-6,
           random_state: int = 0):
    """
    Fit an embedding to a precomputed dissimilarity matrix.

    The first run starts from the classical MDS solution, which is
    deterministic and usually good; the rest start randomly, in case that one
    sits in a poor local minimum. The lowest-stress run wins.

    Args:
        dissimilarities: symmetric (n, n), zero diagonal
        metric: True preserves distances, False only their rank order
        n_init: how many starts to try
        random_state: pinned, so the same data always gives the same map

    Returns:
        (embedding, stress_1) where embedding is (n, n_components) and
        stress_1 is Kruskal's normalised stress — scale-invariant, so it is
        comparable between runs and between datasets.
    """
    dissimilarities = np.asarray(dissimilarities, dtype=float)
    n = dissimilarities.shape[0]
    if dissimilarities.ndim != 2 or dissimilarities.shape[1] != n:
        raise ValueError("dissimilarities must be a square matrix")
    if n <= n_components:
        # Fewer points than dimensions: the classical solution is exact.
        return classical_mds(dissimilarities, n_components), 0.0

    rng = np.random.default_rng(random_state)

    best_points, best_stress = None, np.inf
    for run in range(max(1, n_init)):
        init = classical_mds(dissimilarities, n_components) if run == 0 else None
        points, stress, _ = _smacof_single(
            dissimilarities, n_components, metric, max_iter, eps,
            init=init, rng=rng)
        # Compared on stress-1, never raw stress: see _stress_1.
        if stress < best_stress:
            best_points, best_stress = points, stress

    return best_points, float(best_stress)
