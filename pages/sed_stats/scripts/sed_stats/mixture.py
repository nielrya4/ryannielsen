"""
Monte Carlo mixture (unmixing) model.

Randomly weights the source samples, sums them into a model curve, scores that
against the sink, and keeps the best-scoring configurations. The mean of those
top configurations is the estimated relative contribution of each source, and
their spread is the uncertainty.

Weights are drawn uniformly and normalized to sum to 1, so a configuration is
always a full partition of the sink.
"""
import numpy as np

from . import metrics

# metric -> (distribution form the metric expects, higher score is a better fit)
METRICS = {
    "cross_correlation": ("pdf", True),
    "ks": ("cdf", False),
    "kuiper": ("cdf", False),
}

DEFAULT_TRIALS = 10000
TOP_TRIALS = 10

# Trials are scored in blocks so peak memory stays bounded no matter how many
# bins the distributions have: a 10,000 x 2,000 model matrix would be 160 MB.
MAX_BLOCK_CELLS = 2_000_000


class Contribution:
    """One source's share of the sink, as a percentage."""

    def __init__(self, name: str, contribution: float, standard_deviation: float):
        self.name = name
        self.contribution = contribution
        self.standard_deviation = standard_deviation

    def __repr__(self):
        return (f"Contribution({self.name!r}, {self.contribution:.2f}%, "
                f"±{self.standard_deviation:.2f})")


class MixtureResult:
    """
    What one run of the model produced.

    Attributes:
        contributions - Contribution per source, in the order given
        top_lines     - (TOP_TRIALS, n_bins) model curves of the best trials
        top_scores    - the metric value for each of those curves
        metric        - the metric used
    """

    def __init__(self, contributions, top_lines, top_scores, metric,
                 grid_shape=None):
        self.contributions = contributions
        self.top_lines = top_lines
        self.top_scores = top_scores
        self.metric = metric
        # Set by the bivariate model: the (ny, nx) the flattened lines fold to.
        self.grid_shape = grid_shape

    @property
    def best_score(self):
        return float(self.top_scores[0]) if len(self.top_scores) else float("nan")

    @property
    def top_grids(self):
        """The winning trials folded back into density grids."""
        if not self.grid_shape:
            return []
        return [line.reshape(self.grid_shape) for line in self.top_lines]


def expected_form(metric: str) -> str:
    """Whether `metric` compares PDFs or CDFs."""
    try:
        return METRICS[metric][0]
    except KeyError:
        raise ValueError(f"Unknown metric '{metric}'")


def higher_is_better(metric: str) -> bool:
    try:
        return METRICS[metric][1]
    except KeyError:
        raise ValueError(f"Unknown metric '{metric}'")


def score_models(sink: np.ndarray, models: np.ndarray, metric: str) -> np.ndarray:
    """
    Score every row of `models` against `sink`.

    Vectorized equivalents of sed_stats.metrics, which take one curve at a
    time; scoring 10,000 trials one call at a time is far too slow in the
    browser.
    """
    if metric == "ks":
        # metrics.ks: max absolute difference between the two curves
        return np.abs(models - sink).max(axis=1)

    if metric == "kuiper":
        # metrics.kuiper: max(sink - model) + max(model - sink)
        return (sink - models).max(axis=1) + (models - sink).max(axis=1)

    if metric == "cross_correlation":
        # metrics.r2: squared Pearson correlation
        centered_sink = sink - sink.mean()
        sink_energy = float(np.dot(centered_sink, centered_sink))
        centered = models - models.mean(axis=1, keepdims=True)
        numerator = centered @ centered_sink
        denominator = np.sqrt((centered * centered).sum(axis=1) * sink_energy)
        with np.errstate(divide="ignore", invalid="ignore"):
            correlation = np.where(denominator > 0, numerator / denominator, np.nan)
        return correlation ** 2

    raise ValueError(f"Unknown metric '{metric}'")


def random_configurations(n_trials: int, n_sources: int, rng) -> np.ndarray:
    """`n_trials` weight vectors, each non-negative and summing to 1."""
    weights = rng.random((n_trials, n_sources))
    totals = weights.sum(axis=1, keepdims=True)
    # A row of all zeros is astronomically unlikely, but it would divide by 0.
    totals[totals == 0] = 1.0
    return weights / totals


def monte_carlo_model(sink_values, source_values, source_names=None,
                      n_trials: int = DEFAULT_TRIALS,
                      metric: str = "cross_correlation",
                      n_top: int = TOP_TRIALS,
                      seed=0) -> MixtureResult:
    """
    Run the model.

    Args:
        sink_values: the sink sample's curve, as a 1-D array
        source_values: one curve per source, all on the sink's x grid
        source_names: labels for the sources; defaults to "Source 1", ...
        n_trials: how many random configurations to try
        metric: "cross_correlation", "ks", or "kuiper"
        n_top: how many of the best trials to average
        seed: fixed by default so rebuilding a figure reproduces its numbers;
              pass None for a fresh draw each run

    Raises:
        ValueError: on an unknown metric, no sources, or ragged inputs
    """
    if metric not in METRICS:
        raise ValueError(f"Unknown metric '{metric}'")

    sink = np.asarray(sink_values, dtype=float)
    sources = np.asarray(source_values, dtype=float)
    if sources.ndim != 2 or sources.shape[0] == 0:
        raise ValueError("Need at least one source distribution")
    if sources.shape[1] != sink.shape[0]:
        raise ValueError("Sources and sink must share the same x grid")

    n_sources = sources.shape[0]
    if source_names is None:
        source_names = [f"Source {i + 1}" for i in range(n_sources)]

    rng = np.random.default_rng(seed)
    n_top = max(1, min(n_top, n_trials))

    # Only the weights and scores are kept for every trial; the model curves of
    # the winners are recomputed at the end from their weights.
    all_weights = np.empty((n_trials, n_sources))
    all_scores = np.empty(n_trials)

    block = max(1, min(n_trials, MAX_BLOCK_CELLS // max(sink.shape[0], 1)))
    for start in range(0, n_trials, block):
        stop = min(start + block, n_trials)
        weights = random_configurations(stop - start, n_sources, rng)
        all_weights[start:stop] = weights
        all_scores[start:stop] = score_models(sink, weights @ sources, metric)

    best = higher_is_better(metric)
    # A degenerate trial scores NaN; push those to the losing end rather than
    # letting argsort's NaN-last convention make them look like winners.
    ranked = np.where(np.isnan(all_scores),
                      -np.inf if best else np.inf,
                      all_scores)
    order = np.argsort(ranked)
    top_indices = order[::-1][:n_top] if best else order[:n_top]

    top_weights = all_weights[top_indices]
    contributions = [
        Contribution(name,
                     float(top_weights[:, i].mean() * 100),
                     float(top_weights[:, i].std() * 100))
        for i, name in enumerate(source_names)
    ]

    return MixtureResult(
        contributions=contributions,
        top_lines=top_weights @ sources,
        top_scores=all_scores[top_indices],
        metric=metric,
    )


# ---------------------------------------------------------------- bivariate

# The 2D measures of Sundell & Saylor (2021). Unlike the 1D table there is no
# "form" column: a bivariate distribution is always a density grid, and the
# CDF-based measures derive their own cumulative forms.
METRICS_2D = {
    "cross_correlation": True,   # higher is better
    "ks": False,
    "kuiper": False,
}


def _flatten_grid(distribution):
    """A BivariateDistribution or 2-D array as (densities, shape)."""
    grid = getattr(distribution, "densities", distribution)
    grid = np.asarray(grid, dtype=float)
    if grid.ndim != 2:
        raise ValueError("Expected a 2-D density grid")
    return grid.ravel(), grid.shape


def _quadrant_stack(grid):
    """Each of a grid's four quadrant CDFs, flattened into one row apiece."""
    from .distributions.bivariate import quadrant_cdfs

    return np.asarray([cdf.ravel() for cdf in quadrant_cdfs(grid)])


def _score_models_2d(sink_grid, sink_quadrants, source_flat, source_quadrants,
                     weights, metric):
    """Score a block of trials without ever materializing a per-trial cumsum."""
    models = weights @ source_flat

    if metric == "cross_correlation":
        return score_models(sink_grid, models, "cross_correlation")

    # Cumulative summing is linear, so the quadrant CDF of a mixture is the
    # same mixture of the sources' quadrant CDFs. Precomputing them once turns
    # what would be four cumsums over the whole grid *per trial* into one more
    # matmul, which is what makes 2D unmixing affordable at all.
    best = None
    for quadrant in range(sink_quadrants.shape[0]):
        model_cdfs = weights @ source_quadrants[quadrant]
        difference = sink_quadrants[quadrant] - model_cdfs
        if metric == "ks":
            values = np.abs(difference).max(axis=1)
        else:  # kuiper
            values = difference.max(axis=1) + (-difference).max(axis=1)
        best = values if best is None else np.maximum(best, values)
    return best


def monte_carlo_model_2d(sink, sources, source_names=None,
                         n_trials: int = DEFAULT_TRIALS,
                         metric: str = "cross_correlation",
                         n_top: int = TOP_TRIALS,
                         seed=0) -> MixtureResult:
    """
    Top-down unmixing on bivariate density grids.

    The same convex-mixture logic as the univariate model: a sink drawn from
    several source populations has a density that is a weighted sum of theirs,
    in two dimensions exactly as in one.

    K-S and Kuiper cannot be had by flattening the grid and running the 1D
    statistic — the cumulative sum would depend on whether you walked the grid
    by rows or by columns. They use the four quadrant CDFs of Peacock (1983)
    instead, as sed_stats.metrics_2d does.

    Args:
        sink: BivariateDistribution or 2-D array
        sources: one per source, all on the sink's grid
        source_names: labels; defaults to "Source 1", ...
        metric: "cross_correlation", "ks", or "kuiper"

    Returns:
        MixtureResult whose top_lines are flattened grids; use `.top_grids`
    """
    if metric not in METRICS_2D:
        raise ValueError(f"Unknown metric '{metric}'")

    sink_flat, shape = _flatten_grid(sink)
    flattened = []
    for source in sources:
        source_flat, source_shape = _flatten_grid(source)
        if source_shape != shape:
            raise ValueError("Sources and sink must share the same grid")
        flattened.append(source_flat)
    if not flattened:
        raise ValueError("Need at least one source distribution")

    source_flat = np.asarray(flattened)
    n_sources = source_flat.shape[0]
    if source_names is None:
        source_names = [f"Source {i + 1}" for i in range(n_sources)]

    sink_quadrants = np.zeros((0, sink_flat.size))
    source_quadrants = np.zeros((0, n_sources, sink_flat.size))
    if metric in ("ks", "kuiper"):
        sink_quadrants = _quadrant_stack(sink_flat.reshape(shape))
        source_quadrants = np.stack(
            [_quadrant_stack(row.reshape(shape)) for row in source_flat], axis=1)

    rng = np.random.default_rng(seed)
    n_top = max(1, min(n_top, n_trials))

    all_weights = np.empty((n_trials, n_sources))
    all_scores = np.empty(n_trials)

    block = max(1, min(n_trials, MAX_BLOCK_CELLS // max(sink_flat.size, 1)))
    for start in range(0, n_trials, block):
        stop = min(start + block, n_trials)
        weights = random_configurations(stop - start, n_sources, rng)
        all_weights[start:stop] = weights
        all_scores[start:stop] = _score_models_2d(
            sink_flat, sink_quadrants, source_flat, source_quadrants,
            weights, metric)

    best = METRICS_2D[metric]
    ranked = np.where(np.isnan(all_scores),
                      -np.inf if best else np.inf,
                      all_scores)
    order = np.argsort(ranked)
    top_indices = order[::-1][:n_top] if best else order[:n_top]

    top_weights = all_weights[top_indices]
    contributions = [
        Contribution(name,
                     float(top_weights[:, i].mean() * 100),
                     float(top_weights[:, i].std() * 100))
        for i, name in enumerate(source_names)
    ]

    result = MixtureResult(
        contributions=contributions,
        top_lines=top_weights @ source_flat,
        top_scores=all_scores[top_indices],
        metric=metric,
    )
    result.grid_shape = shape
    return result
