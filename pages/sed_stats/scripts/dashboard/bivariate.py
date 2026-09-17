"""
Building bivariate distributions from spreadsheet rows.

Shared by the three bivariate tools: the density plots, the comparison
matrices and the MDS map all start from the same per-sample grids, which must
sit on one common axis pair for the 2D measures to mean anything.
"""
from antioch.elements import P

from sed_stats.distributions.bivariate import axis_grid, bivariate_density
from sed_stats.distributions.numeric import silverman_bandwidth

from .dataset import paired_by_sample

NOTE_STYLE = {"color": "#6c757d"}

# Silverman is computed on the pooled samples, so every sample is smoothed
# identically; smoothing them differently would put a difference in the metric
# that isn't in the data.


class BivariateSet:
    """
    Every selected sample's density on one shared grid.

    Attributes:
        entries    - [(sample_name, BivariateDistribution), ...]
        x_values, y_values - the shared axes
        used_uncertainties - (x, y) flags: did per-grain uncertainties drive
                             each axis's kernel widths
        x_bandwidth, y_bandwidth - the KDE widths, when they did not
        counts     - {sample: number of paired measurements}
    """

    def __init__(self, entries, x_values, y_values, used_uncertainties,
                 x_bandwidth, y_bandwidth, counts):
        self.entries = entries
        self.x_values = x_values
        self.y_values = y_values
        self.used_uncertainties = used_uncertainties
        self.x_bandwidth = x_bandwidth
        self.y_bandwidth = y_bandwidth
        self.counts = counts

    def __len__(self):
        return len(self.entries)

    @property
    def method_note(self):
        """How each axis was smoothed — they can differ."""
        use_x, use_y = self.used_uncertainties
        if use_x and use_y:
            return "each grain spread by its own analytical uncertainty (PDP)"
        if not use_x and not use_y:
            return (f"KDE, bandwidths {self.x_bandwidth:.3g} (x) "
                    f"and {self.y_bandwidth:.3g} (y)")
        if use_x:
            return (f"x from each grain's own uncertainty, "
                    f"y by KDE at bandwidth {self.y_bandwidth:.3g}")
        return (f"x by KDE at bandwidth {self.x_bandwidth:.3g}, "
                f"y from each grain's own uncertainty")


def prepare(rows, sample_col, y_dimension, opts, min_samples=1, purpose="compare"):
    """
    The density set for one y dimension, or a note explaining why there isn't one.

    Every bivariate tool needs the same four checks, and each one is a normal
    thing for a user to hit — an unset axis, a dimension paired with itself, a
    categorical column, too few samples. None of them is an error worth a
    traceback.

    Returns:
        (BivariateSet, None) on success, or (None, element) to render instead
    """
    x_dimension = opts.get("x_dimension")
    if not x_dimension:
        return None, P("Choose an x dimension.", style=NOTE_STYLE)
    if x_dimension == y_dimension:
        return None, P(f"'{y_dimension}' is already the x dimension; pick a "
                       f"different y dimension.", style=NOTE_STYLE)

    try:
        density_set = build_set(rows, sample_col, x_dimension, y_dimension, opts)
    except ValueError:
        # A density grid needs two numeric axes; a categorical column has no
        # position on one.
        return None, P(f"'{y_dimension}' is not numeric, so it cannot be a "
                       f"density axis. Use the Distributions tool for it.",
                       style=NOTE_STYLE)

    if not len(density_set):
        return None, P(f"No paired '{x_dimension}' and '{y_dimension}' values.",
                       style=NOTE_STYLE)
    if len(density_set) < min_samples:
        return None, P(f"Need at least {min_samples} samples with paired values "
                       f"to {purpose}.", style=NOTE_STYLE)

    return density_set, None


def build_set(rows, sample_col, x_dimension, y_dimension, opts) -> BivariateSet:
    """
    Densities for every selected sample over `x_dimension` vs `y_dimension`.

    Uses per-grain uncertainties when the density method is "auto" and the
    spreadsheet actually has them; otherwise falls back to a KDE, since a
    bivariate distribution has no binned form to retreat to.

    Raises:
        ValueError: if either dimension is not numeric
    """
    grouped = paired_by_sample(
        rows, sample_col, x_dimension, y_dimension,
        opts.get("samples"), opts.get("sigma_in", 1.0))
    if not grouped:
        return BivariateSet([], [], [], (False, False), 0.0, 0.0, {})

    pooled_x = [v for entry in grouped.values() for v in entry[0]]
    pooled_y = [v for entry in grouped.values() for v in entry[1]]
    pooled_x_sigma = [s for entry in grouped.values() for s in entry[2]]
    pooled_y_sigma = [s for entry in grouped.values() for s in entry[3]]

    # Decided per axis, not once for the pair. One variable commonly has an
    # uncertainty column and the other does not — age with a "1s" beside it,
    # plotted against a trace element that has none. Treating that as "the pair
    # has uncertainties" would give the second axis a kernel floored to half a
    # grid step, turning its density into a field of near-delta spikes.
    automatic = opts.get("density", "auto") == "auto"
    use_x_sigmas = automatic and any(s > 0 for s in pooled_x_sigma)
    use_y_sigmas = automatic and any(s > 0 for s in pooled_y_sigma)

    x_bandwidth = opts.get("x_bandwidth") or float(silverman_bandwidth(pooled_x))
    y_bandwidth = opts.get("y_bandwidth") or float(silverman_bandwidth(pooled_y))

    # Pad each axis by whatever kernel it will actually be drawn with, so a
    # grain with a large uncertainty is not clipped at the edge.
    grid = int(opts.get("grid", 128))
    x_values = axis_grid(pooled_x, pooled_x_sigma if use_x_sigmas else [x_bandwidth],
                         grid)
    y_values = axis_grid(pooled_y, pooled_y_sigma if use_y_sigmas else [y_bandwidth],
                         grid)

    entries = []
    counts = {}
    for sample, (xs, ys, x_sigmas, y_sigmas) in grouped.items():
        entries.append((sample, bivariate_density(
            xs, ys,
            x_sigmas if use_x_sigmas else x_bandwidth,
            y_sigmas if use_y_sigmas else y_bandwidth,
            x_values, y_values, name=sample)))
        counts[sample] = len(xs)

    return BivariateSet(entries, x_values, y_values,
                        (use_x_sigmas, use_y_sigmas),
                        x_bandwidth, y_bandwidth, counts)
