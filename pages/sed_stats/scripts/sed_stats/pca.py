"""
Principal component analysis over per-sample distributions.

Each sample is one observation and every grid position is a feature, so a set
of distributions becomes an (n_samples, n_points) matrix. The first two
components are the plane that captures the most variance between samples.

This is the linear counterpart to sed_stats.mds: MDS starts from a pairwise
dissimilarity matrix and only preserves rank order or distance, whereas PCA
works on the distributions themselves and so can also report *which* parts of
the distribution drive the separation, via the component loadings.

Computation only — plotting is left to the caller.
"""
import numpy as np


class PCAPoint:
    """One sample's position in component space."""

    def __init__(self, x: float, y: float, label: str):
        self.x = x
        self.y = y
        self.label = label

    def __repr__(self):
        return f"PCAPoint({self.label!r}, {self.x:.4g}, {self.y:.4g})"


class PCAResult:
    """
    Attributes:
        points          - PCAPoint per sample, in the order given
        scores          - (n_samples, n_components) coordinates
        components      - (n_components, n_features) loadings, one row per PC
        explained_ratio - fraction of total variance per component
        mean            - the feature mean that was subtracted
        singular_values - from the SVD, for a scree plot
    """

    def __init__(self, points, scores, components, explained_ratio, mean,
                 singular_values, explained_ratio_all=None, blocks=None):
        self.points = points
        self.scores = scores
        self.components = components
        self.explained_ratio = explained_ratio
        self.mean = mean
        self.singular_values = singular_values
        # Every component, not just the kept ones — a scree plot needs the tail
        # to show where the useful variance stops.
        self.explained_ratio_all = (explained_ratio if explained_ratio_all is None
                                    else explained_ratio_all)
        # [(variable_name, start, stop), ...] when the feature vector was
        # concatenated from several variables; empty for a single-variable PCA.
        self.blocks = blocks or []

    def percent(self, component: int) -> float:
        """Percent of variance explained by a 0-indexed component."""
        if component >= self.explained_ratio.size:
            return 0.0
        return float(self.explained_ratio[component] * 100)

    def block_contributions(self, component: int):
        """
        How much each variable drives a component, as fractions summing to 1.

        Only meaningful for a combined_pca result. Component rows are unit
        vectors, so the squared loadings inside one variable's slice are that
        variable's share of the component.

        Returns:
            [(name, fraction), ...], or [] when the PCA was over one variable
        """
        if not self.blocks or component >= self.components.shape[0]:
            return []
        loadings = self.components[component] ** 2
        total = float(loadings.sum()) or 1.0
        return [(name, float(loadings[start:stop].sum()) / total)
                for name, start, stop in self.blocks]


class GrainPCAResult:
    """
    A PCA fitted across individual measurements rather than whole samples.

    Attributes:
        scores          - (n_grains, n_components) per-grain coordinates
        components      - (n_components, n_variables) loadings
        explained_ratio - fraction of total variance per component
        variables       - the variable names, in column order
        mean, scale     - the standardization that was applied
    """

    def __init__(self, scores, components, explained_ratio, variables,
                 mean, scale, explained_ratio_all=None):
        self.scores = scores
        self.components = components
        self.explained_ratio = explained_ratio
        self.variables = list(variables)
        self.mean = mean
        self.scale = scale
        self.explained_ratio_all = (explained_ratio if explained_ratio_all is None
                                    else explained_ratio_all)

    def percent(self, component: int) -> float:
        if component >= self.explained_ratio.size:
            return 0.0
        return float(self.explained_ratio[component] * 100)

    def loadings(self, component: int):
        """[(variable, loading), ...] for one component, largest first."""
        if component >= self.components.shape[0]:
            return []
        pairs = list(zip(self.variables, self.components[component]))
        return sorted(pairs, key=lambda pair: abs(pair[1]), reverse=True)


def grain_pca(matrix, variables=None, n_components: int = 2,
              weights=None) -> GrainPCAResult:
    """
    Fit one PCA across every measurement, for use as a derived axis.

    This is the transform that makes multivariate top-down unmixing work. A
    mixture of grain populations produces a distribution that is a convex
    combination of its sources' distributions, and that stays true under any
    fixed per-grain map — so projecting every grain onto a single, globally
    fitted PC1 gives a new scalar whose distributions still mix linearly.

    Two things it therefore must NOT do, both of which would break that
    property: fit separately per sample, or standardize per sample. The fit and
    the standardization are global, over the pooled measurements.

    Args:
        matrix: (n_grains, n_variables), every grain from every sample
        variables: column names, for reporting the loadings
        n_components: how many components to keep
        weights: optional per-grain weight. Pass 1/n for each grain of a
            sample to stop a sample with many analyses from dominating the
            axis; the projection itself stays unweighted.

    Raises:
        ValueError: with fewer than two grains or fewer than two variables
    """
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("Expected a (grains, variables) matrix")
    n_grains, n_variables = matrix.shape
    if n_grains < 2:
        raise ValueError("Need at least two measurements")
    if n_variables < 2:
        raise ValueError("Need at least two variables")

    if variables is None:
        variables = [f"v{i + 1}" for i in range(n_variables)]

    if weights is None:
        weight_vector = np.ones(n_grains)
    else:
        weight_vector = np.asarray(weights, dtype=float)
        if weight_vector.shape[0] != n_grains:
            raise ValueError("weights must be one per measurement")
    total_weight = float(weight_vector.sum()) or 1.0

    mean = (weight_vector @ matrix) / total_weight
    centered = matrix - mean

    # Standardize: variables in different units (Ma, °C, ratios) would
    # otherwise be ranked by the size of their numbers, not their information.
    variance = (weight_vector @ (centered ** 2)) / total_weight
    scale = np.sqrt(variance)
    scale[scale <= 0] = 1.0  # a constant column carries nothing either way
    standardized = centered / scale

    # The SVD is weighted; the projection is not, so every grain still lands at
    # its own honest position on the axis.
    weighted = standardized * np.sqrt(weight_vector)[:, np.newaxis]
    _, singular_values, right = np.linalg.svd(weighted, full_matrices=False)

    n_components = max(1, min(n_components, n_variables))
    components = right[:n_components].copy()
    scores = standardized @ components.T
    components, scores = _flip_signs(components, scores)

    total = float(np.sum(singular_values ** 2))
    explained_ratio = (singular_values ** 2 / total) if total > 0 else \
        np.zeros_like(singular_values)

    return GrainPCAResult(
        scores=scores,
        components=components,
        explained_ratio=explained_ratio[:n_components],
        explained_ratio_all=explained_ratio,
        variables=variables,
        mean=mean,
        scale=scale,
    )


def _flip_signs(components, scores):
    """
    Pin the arbitrary sign of each component.

    An SVD is only defined up to a sign per component, so an unpinned plot can
    come out mirrored for no reason. Forcing the largest-magnitude loading
    positive makes the orientation reproducible.
    """
    for i in range(components.shape[0]):
        largest = int(np.argmax(np.abs(components[i])))
        if components[i, largest] < 0:
            components[i] *= -1
            scores[:, i] *= -1
    return components, scores


def _decompose(centered, sample_names, mean, n_components, blocks=None) -> PCAResult:
    """The shared SVD core, on an already-centered matrix."""
    n_samples, n_features = centered.shape
    # An n-sample set spans at most n-1 dimensions once it is centered.
    n_components = max(1, min(n_components, n_samples - 1, n_features))

    # SVD rather than an eigendecomposition of the covariance matrix: there are
    # far more grid points than samples, so the covariance matrix would be huge
    # and rank-deficient.
    _, singular_values, right = np.linalg.svd(centered, full_matrices=False)

    components = right[:n_components].copy()
    scores = centered @ components.T
    components, scores = _flip_signs(components, scores)

    total = float(np.sum(singular_values ** 2))
    explained_ratio = (singular_values ** 2 / total) if total > 0 else \
        np.zeros_like(singular_values)

    points = [
        PCAPoint(float(scores[i, 0]),
                 float(scores[i, 1]) if n_components > 1 else 0.0,
                 name)
        for i, name in enumerate(sample_names)
    ]

    return PCAResult(
        points=points,
        scores=scores,
        components=components,
        explained_ratio=explained_ratio[:n_components],
        explained_ratio_all=explained_ratio,
        mean=mean,
        singular_values=singular_values,
        blocks=blocks,
    )


def pca_function(series, n_components: int = 2) -> PCAResult:
    """
    Run PCA on a list of (sample_name, values) pairs.

    Args:
        series: every sample's distribution, all on the same grid
        n_components: how many components to keep

    Returns:
        PCAResult

    Raises:
        ValueError: with fewer than two samples, or ragged distributions
    """
    if len(series) < 2:
        raise ValueError("PCA needs at least two samples")

    matrix = np.asarray([np.asarray(values, dtype=float) for _, values in series])
    if matrix.ndim != 2:
        raise ValueError("Every sample must be on the same grid")

    mean = matrix.mean(axis=0)
    return _decompose(matrix - mean, [name for name, _ in series], mean,
                      n_components)


def combined_pca(blocks, sample_names, n_components: int = 2,
                 weighting: str = "equal") -> PCAResult:
    """
    One PCA over several variables at once.

    Each sample's feature vector is its distribution for every variable laid
    end to end, so the result answers "how do these samples relate given
    everything measured" rather than one variable at a time.

    Args:
        blocks: [(variable_name, matrix)], each matrix (n_samples, n_features_i)
                with rows in the same sample order
        sample_names: one per row, shared by every block
        n_components: how many components to keep
        weighting: "equal" divides each variable by its own first singular
                   value, so a variable cannot dominate merely by having a
                   longer grid or larger numbers (Escofier & Pages' multiple
                   factor analysis). "none" concatenates raw.

    Raises:
        ValueError: with no blocks, fewer than two samples, or mismatched rows
    """
    if not blocks:
        raise ValueError("Need at least one variable")
    if len(sample_names) < 2:
        raise ValueError("PCA needs at least two samples")

    pieces = []
    spans = []
    start = 0
    for name, matrix in blocks:
        matrix = np.asarray(matrix, dtype=float)
        if matrix.shape[0] != len(sample_names):
            raise ValueError(f"'{name}' has {matrix.shape[0]} rows, "
                             f"expected {len(sample_names)}")
        centered = matrix - matrix.mean(axis=0)

        scale = 1.0
        if weighting == "equal":
            values = np.linalg.svd(centered, compute_uv=False)
            if values.size and values[0] > 0:
                scale = float(values[0])

        pieces.append(centered / scale)
        spans.append((name, start, start + centered.shape[1]))
        start += centered.shape[1]

    # Every block was centered on its own, so the concatenation already is.
    combined = np.hstack(pieces)
    return _decompose(combined, list(sample_names),
                      np.zeros(combined.shape[1]), n_components, blocks=spans)
