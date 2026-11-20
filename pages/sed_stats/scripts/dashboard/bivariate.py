"""
Building bivariate distributions from spreadsheet rows.

Shared by the three bivariate tools: the density plots, the comparison
matrices and the MDS map all start from the same per-sample grids, which must
sit on one common axis pair for the 2D measures to mean anything.
"""

from plot_lib import heatmap_trace
from sed_stats.distributions.bivariate import axis_grid, bivariate_density, category_axis
from sed_stats.distributions.numeric import silverman_bandwidth

from workflow_lib import NodeProblem

from .dataset import categories_of, is_numeric_column, paired_by_sample

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
        x_categories, y_categories - the category names along an axis that is
                             categorical (positions 0, 1, 2, ...), else None
    """

    def __init__(self, entries, x_values, y_values, used_uncertainties,
                 x_bandwidth, y_bandwidth, counts,
                 x_categories=None, y_categories=None):
        self.entries = entries
        self.x_values = x_values
        self.y_values = y_values
        self.used_uncertainties = used_uncertainties
        self.x_bandwidth = x_bandwidth
        self.y_bandwidth = y_bandwidth
        self.counts = counts
        self.x_categories = x_categories
        self.y_categories = y_categories

    def __len__(self):
        return len(self.entries)

    @property
    def categorical(self):
        return self.x_categories is not None or self.y_categories is not None

    @property
    def method_note(self):
        """How each axis was smoothed — they can differ."""
        if not self.categorical:
            use_x, use_y = self.used_uncertainties
            if use_x and use_y:
                return "each grain spread by its own analytical uncertainty (PDP)"
            if not use_x and not use_y:
                return (f"KDE, bandwidths {self.x_bandwidth:.3g} (x) "
                        f"and {self.y_bandwidth:.3g} (y)")
        parts = []
        for axis, categories, used, bandwidth in (
                ("x", self.x_categories, self.used_uncertainties[0], self.x_bandwidth),
                ("y", self.y_categories, self.used_uncertainties[1], self.y_bandwidth)):
            if categories is not None:
                parts.append(f"{axis} counted per category, unsmoothed")
            elif used:
                parts.append(f"{axis} from each grain's own uncertainty")
            else:
                parts.append(f"{axis} by KDE at bandwidth {bandwidth:.3g}")
        return ", ".join(parts)

    def order_warning(self, metric):
        """A caveat for the metrics that read an axis as ordered, or None."""
        if self.categorical and metric in ("ks", "kuiper"):
            return ("Note: this metric accumulates along each axis, and "
                    "categories have no natural order — the result depends on "
                    "their alphabetical order here. Likeness or similarity "
                    "compare category by category and do not.")
        return None

    def axis_layout(self, x_title, y_title):
        """Plotly axis settings: category names as ticks on a categorical axis."""
        def axis(title, categories):
            layout = {"title": {"text": title}, "rangemode": "normal"}
            if categories is not None:
                layout.update({
                    "tickmode": "array",
                    "tickvals": list(range(len(categories))),
                    "ticktext": list(categories),
                    "range": [-0.5, len(categories) - 0.5],
                })
            return layout
        return {"xaxis": axis(x_title, self.x_categories),
                "yaxis": axis(y_title, self.y_categories)}

    def heatmap(self, grid, **kwargs):
        """A heatmap on this set's axes, unsmoothed across categories."""
        trace = heatmap_trace(
            self.x_values, self.y_values,
            grid.tolist() if hasattr(grid, "tolist") else grid, **kwargs)
        if self.categorical:
            # Interpolating between "quartz" and "feldspar" invents a mineral.
            trace["zsmooth"] = False
        return trace


def prepare_set(rows, sample_col, y_dimension, opts, min_samples=1,
                purpose="compare"):
    """
    The density set for one y dimension.

    Every bivariate step needs the same four checks, and each one is a normal
    thing for a user to hit — an unset axis, a dimension paired with itself,
    too few samples. None of them is an error worth a traceback.

    Raises:
        NodeProblem: saying what to change
    """
    x_dimension = opts.get("x_dimension")
    if not x_dimension:
        raise NodeProblem("Choose an x dimension.")
    if x_dimension == y_dimension:
        raise NodeProblem(f"'{y_dimension}' is already the x dimension; pick a "
                          f"different y dimension.")

    density_set = build_set(rows, sample_col, x_dimension, y_dimension, opts)

    if not len(density_set):
        raise NodeProblem(
            f"No paired '{x_dimension}' and '{y_dimension}' values.")
    if len(density_set) < min_samples:
        raise NodeProblem(f"Need at least {min_samples} samples with paired "
                          f"values to {purpose}.")
    return density_set


def build_set(rows, sample_col, x_dimension, y_dimension, opts) -> BivariateSet:
    """
    Densities for every selected sample over `x_dimension` vs `y_dimension`.

    Uses per-grain uncertainties when the density method is "auto" and the
    spreadsheet actually has them; otherwise falls back to a KDE, since a
    bivariate distribution has no binned form to retreat to.

    A categorical dimension (any column that isn't all numbers) becomes an
    axis with one column per category, shared by every sample and never
    smoothed — a grain counts wholly toward its own category.
    """
    x_categories = _categories(rows, sample_col, x_dimension, opts)
    y_categories = _categories(rows, sample_col, y_dimension, opts)
    grouped = paired_by_sample(
        rows, sample_col, x_dimension, y_dimension,
        opts.get("samples"), opts.get("sigma_in", 1.0),
        x_categories=x_categories, y_categories=y_categories)
    if not grouped:
        return BivariateSet([], [], [], (False, False), 0.0, 0.0, {},
                            x_categories, y_categories)

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

    # A categorical axis has no width to smooth by, and no uncertainty column.
    use_x_sigmas = use_x_sigmas and x_categories is None
    use_y_sigmas = use_y_sigmas and y_categories is None
    x_bandwidth = (None if x_categories is not None else
                   opts.get("x_bandwidth") or float(silverman_bandwidth(pooled_x)))
    y_bandwidth = (None if y_categories is not None else
                   opts.get("y_bandwidth") or float(silverman_bandwidth(pooled_y)))

    # Pad each axis by whatever kernel it will actually be drawn with, so a
    # grain with a large uncertainty is not clipped at the edge.
    grid = int(opts.get("grid", 128))
    x_values = (category_axis(len(x_categories)) if x_categories is not None else
                axis_grid(pooled_x, pooled_x_sigma if use_x_sigmas else [x_bandwidth],
                          grid))
    y_values = (category_axis(len(y_categories)) if y_categories is not None else
                axis_grid(pooled_y, pooled_y_sigma if use_y_sigmas else [y_bandwidth],
                          grid))

    entries = []
    counts = {}
    for sample, (xs, ys, x_sigmas, y_sigmas) in grouped.items():
        entries.append((sample, bivariate_density(
            xs, ys,
            _widths_for(x_categories, use_x_sigmas, x_sigmas, x_bandwidth),
            _widths_for(y_categories, use_y_sigmas, y_sigmas, y_bandwidth),
            x_values, y_values, name=sample)))
        counts[sample] = len(xs)

    return BivariateSet(entries, x_values, y_values,
                        (use_x_sigmas, use_y_sigmas),
                        x_bandwidth, y_bandwidth, counts,
                        x_categories, y_categories)


def _categories(rows, sample_col, dimension, opts):
    """The category list for a non-numeric dimension, or None for a numeric one."""
    if is_numeric_column(rows, dimension):
        return None
    return categories_of(rows, sample_col, dimension, opts.get("samples")) or None


def _widths_for(categories, use_sigmas, sigmas, bandwidth):
    """What bivariate_density wants as an axis's kernel: None marks categorical."""
    if categories is not None:
        return None
    return sigmas if use_sigmas else bandwidth
