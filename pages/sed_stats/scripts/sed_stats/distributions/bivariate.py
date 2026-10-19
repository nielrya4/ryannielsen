"""
Bivariate density distributions.

Sundell & Saylor (2021), Two-Dimensional Quantitative Comparison of Density
Distributions in Detrital Geochronology and Geochemistry, G-cubed 22,
e2020GC009559.

A univariate age distribution can only say two samples share age peaks. Pairing
each measurement with a second variable — Hf, a trace element ratio, grain
roundness — separates sources that overlap in one dimension but not in two.
"""
import numpy as np

# Points per axis. The paper discretizes to 512 for computation; 128 keeps a
# comparison responsive in the browser and is ample for the metrics, which only
# need both distributions on the same grid.
DEFAULT_GRID = 128

PAD_SIGMAS = 3.0

# Kernels are accumulated in blocks so a large sample against a fine grid never
# allocates one (n_points x grid) matrix.
_BLOCK_CELLS = 2_000_000


class BivariateDistribution:
    """
    A density over an x-y grid.

    Attributes:
        x_values, y_values - the grid axes
        densities - (len(y_values), len(x_values)), summing to 1 (row = y)
    """

    def __init__(self, x_values, y_values, densities, name: str = None):
        self.name = name
        self.x_values = np.asarray(x_values, dtype=float)
        self.y_values = np.asarray(y_values, dtype=float)
        self.densities = np.asarray(densities, dtype=float)

        expected = (self.y_values.size, self.x_values.size)
        if self.densities.shape != expected:
            raise ValueError(
                f"densities must be {expected}, got {self.densities.shape}")

    @property
    def shape(self):
        return self.densities.shape

    def flatten(self) -> np.ndarray:
        """The grid as a 1-D vector, which is what the 2D measures compare."""
        return self.densities.ravel()

    def subset(self, x_range=None, y_range=None) -> "BivariateDistribution":
        """Crop to a window, renormalized so the result still sums to 1."""
        x_mask = np.ones(self.x_values.shape, dtype=bool)
        y_mask = np.ones(self.y_values.shape, dtype=bool)
        if x_range is not None:
            low, high = x_range
            x_mask = (self.x_values >= low) & (self.x_values <= high)
        if y_range is not None:
            low, high = y_range
            y_mask = (self.y_values >= low) & (self.y_values <= high)

        densities = self.densities[np.ix_(y_mask, x_mask)]
        total = densities.sum()
        if total > 0:
            densities = densities / total
        return BivariateDistribution(
            self.x_values[x_mask], self.y_values[y_mask], densities, self.name)


def axis_grid(values, widths, n_points: int = DEFAULT_GRID, pad_sigmas: float = PAD_SIGMAS):
    """
    An evenly spaced axis covering the data plus `pad_sigmas` of kernel tail.

    Both distributions in a comparison have to sit on the same grid, so the
    caller builds one axis from the pooled samples and passes it to each.
    """
    values = np.asarray(values, dtype=float)
    widths = np.atleast_1d(np.asarray(widths, dtype=float))
    if values.size == 0:
        raise ValueError("Cannot build a grid from no values")
    if widths.size == 1:
        # .flat[0] rather than float(widths): numpy 2 refuses to convert a
        # one-element array to a scalar, and callers routinely pass [bandwidth].
        widths = np.full(values.shape, widths.flat[0])

    low = float(np.min(values - pad_sigmas * widths))
    high = float(np.max(values + pad_sigmas * widths))
    if high <= low:
        pad = abs(low) * 0.01 or 1.0
        low, high = low - pad, high + pad
    return np.linspace(low, high, max(int(n_points), 2))


def _widths(uncertainties, count, floor):
    """Per-point kernel widths, floored so a zero uncertainty is not a pole."""
    widths = np.atleast_1d(np.asarray(uncertainties, dtype=float))
    if widths.size == 1:
        widths = np.full(count, widths.flat[0])
    if widths.shape[0] != count:
        raise ValueError("uncertainties must be scalar or one per measurement")
    return np.where(np.isfinite(widths) & (widths > floor), widths, floor)


def _kernel_matrix(centers, widths, grid):
    """(n_points, len(grid)) of 1-D Gaussians, one row per measurement."""
    offsets = grid[np.newaxis, :] - centers[:, np.newaxis]
    spreads = widths[:, np.newaxis]
    return np.exp(-(offsets ** 2) / (2 * spreads ** 2)) / (
        np.sqrt(2 * np.pi) * spreads)


def bivariate_density(x, y, x_uncertainties, y_uncertainties,
                      x_values, y_values, name: str = None,
                      sigma_floor: float = None) -> BivariateDistribution:
    """
    Sum a 2-D Gaussian per measurement onto the grid.

    The kernel is separable, so the (n_points, nx) and (n_points, ny) matrices
    of 1-D kernels multiply out to the grid in a single matmul rather than one
    outer product per measurement.

    Args:
        x, y: paired measurements, same length
        x_uncertainties, y_uncertainties: per-measurement widths, or a scalar
            bandwidth to use for every measurement
        x_values, y_values: the shared grid axes
        sigma_floor: smallest usable width; defaults to half a grid step

    Returns:
        BivariateDistribution whose densities sum to 1
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.shape != y.shape:
        raise ValueError("x and y must be paired, so the same length")

    x_values = np.asarray(x_values, dtype=float)
    y_values = np.asarray(y_values, dtype=float)
    densities = np.zeros((y_values.size, x_values.size), dtype=float)
    if x.size == 0:
        return BivariateDistribution(x_values, y_values, densities, name)

    # One floor per axis, from that axis's own step. A single floor taken from
    # min(x_step, y_step) would let a fine axis set the floor for a coarse one
    # — an age axis stepping 30 Ma with a 3 Ma floor produces kernels an eighth
    # of a cell wide, which alias into spikes instead of a density.
    if sigma_floor is None:
        x_step = float(x_values[1] - x_values[0]) if x_values.size > 1 else 1.0
        y_step = float(y_values[1] - y_values[0]) if y_values.size > 1 else 1.0
        x_floor = max(abs(x_step) / 2, 1e-12)
        y_floor = max(abs(y_step) / 2, 1e-12)
    else:
        x_floor = y_floor = max(float(sigma_floor), 1e-12)

    x_widths = _widths(x_uncertainties, x.size, x_floor)
    y_widths = _widths(y_uncertainties, y.size, y_floor)

    cells = max(x_values.size + y_values.size, 1)
    block = max(1, _BLOCK_CELLS // cells)
    for start in range(0, x.size, block):
        stop = min(start + block, x.size)
        kernels_x = _kernel_matrix(x[start:stop], x_widths[start:stop], x_values)
        kernels_y = _kernel_matrix(y[start:stop], y_widths[start:stop], y_values)
        # Row i of each holds that measurement's 1-D kernel; the matmul sums
        # every outer product at once.
        densities += kernels_y.T @ kernels_x

    total = densities.sum()
    if total > 0:
        densities /= total
    return BivariateDistribution(x_values, y_values, densities, name)


def bivariate_pdp(x, y, x_uncertainties, y_uncertainties,
                  x_values, y_values, name: str = None) -> BivariateDistribution:
    """Bivariate PDP: each measurement spread by its own analytical uncertainty."""
    return bivariate_density(x, y, x_uncertainties, y_uncertainties,
                             x_values, y_values, name)


def bivariate_kde(x, y, x_bandwidth: float, y_bandwidth: float,
                  x_values, y_values, name: str = None) -> BivariateDistribution:
    """
    Bivariate KDE: one bandwidth per axis for every measurement.

    The paper's rule of thumb is to set bandwidths from typical analytical
    precision — 1-2% for U-Pb, 0.5-1 epsilon units for Lu-Hf at 1 sigma.
    """
    return bivariate_density(x, y, float(x_bandwidth), float(y_bandwidth),
                             x_values, y_values, name,
                             # Honour a deliberately narrow bandwidth rather
                             # than widening it to the grid step.
                             sigma_floor=1e-12)


# Quadrant definitions, eqs 5-8. Each entry says which axes to reverse before
# accumulating, so the sum runs toward that quadrant's corner.
#   I:   P(X <= x, Y <= y)      III: P(X > x,  Y > y)
#   II:  P(X > x,  Y <= y)      IV:  P(X <= x, Y > y)
QUADRANTS = {
    1: (False, False),
    2: (True, False),
    3: (True, True),
    4: (False, True),
}


def bivariate_cdf(distribution, quadrant: int = 1) -> np.ndarray:
    """
    Cumulative distribution over the grid, accumulated toward one quadrant.

    A bivariate CDF is not unique: it depends on which corner you sum from, so
    the paper defines four (eqs 5-8) and the 2D K-S and Kuiper tests consider
    all of them.
    """
    if quadrant not in QUADRANTS:
        raise ValueError(f"quadrant must be 1-4, got {quadrant}")

    densities = (distribution.densities
                 if isinstance(distribution, BivariateDistribution)
                 else np.asarray(distribution, dtype=float))
    flip_x, flip_y = QUADRANTS[quadrant]

    working = densities
    if flip_x:
        working = working[:, ::-1]
    if flip_y:
        working = working[::-1, :]

    cumulative = np.cumsum(np.cumsum(working, axis=0), axis=1)

    if flip_y:
        cumulative = cumulative[::-1, :]
    if flip_x:
        cumulative = cumulative[:, ::-1]
    return cumulative


def quadrant_cdfs(distribution):
    """All four bivariate CDFs, in quadrant order."""
    return [bivariate_cdf(distribution, q) for q in sorted(QUADRANTS)]
