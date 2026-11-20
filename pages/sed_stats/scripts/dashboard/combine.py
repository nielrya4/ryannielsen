"""
Pooling the samples of several inputs so a block can treat them as one set.

A Comparison or a Mixture model can read more than one Distribution step: the
samples of all of them are pooled and compared together. Two steps built their
curves on grids of their own, though, and the measures compare curves point by
point, so before pooling every curve is resampled onto one shared grid.

    Lines    numeric: linear interpolation onto an evenly spaced grid covering
             both, the PDF renormalised and the CDF interpolated on its own
             (so it still runs from 0 to 1). Categorical: the union of the
             categories, a category a step lacks counting as zero.
    Raster   the same, along each numeric axis; categorical axes must already
             agree.

A sample name used by more than one input is told apart by which input it came
from. All of this is plain numpy and takes nothing from the browser.
"""
import numpy as np

from sed_stats.distributions.bivariate import BivariateDistribution
from workflow_lib import NodeProblem
from workflow_lib.types import Lines, Raster

from .bivariate import BivariateSet


def unique_names(groups):
    """
    Names for pooled samples. `groups` is one list of names per input; a name that
    appears in more than one input becomes "name (input k)", wherever it appears.
    """
    seen = {}
    for names in groups:
        for name in set(names):
            seen[name] = seen.get(name, 0) + 1
    return [[f"{name} (input {k + 1})" if seen[name] > 1 else name for name in names]
            for k, names in enumerate(groups)]


def combine(group):
    """
    One item from several: the group's Lines pooled into Lines, or its Rasters
    into a Raster. A single item is returned as it is.

    Raises:
        NodeProblem: for a mix of kinds, or items that cannot share a grid
    """
    group = list(group)
    if len(group) == 1:
        return group[0]
    if all(isinstance(item, Lines) for item in group):
        return combine_lines(group)
    if all(isinstance(item, Raster) for item in group):
        return combine_rasters(group)
    raise NodeProblem("The inputs mix lines and rasters; connect only one kind "
                      "to a block that pools several.")


# ------------------------------------------------------------------- lines

def combine_lines(items):
    if any(item.categorical != items[0].categorical for item in items):
        raise NodeProblem("Cannot pool a categorical dimension with a numeric one.")
    names = unique_names([[s for s, _ in item.pdf] for item in items])
    label = " + ".join(dict.fromkeys(item.name for item in items))
    if items[0].categorical:
        x, pdf, cdf = _pool_categories(items, names)
    else:
        x, pdf, cdf = _pool_grids(items, names)
    note = (f"Pooled {len(items)} inputs onto one grid. Each input was smoothed on its "
            "own, so use the same density method and bandwidth in each for a fair "
            "comparison. " + " ".join(dict.fromkeys(item.note for item in items if item.note)))
    return Lines(label, x, pdf, cdf, categorical=items[0].categorical, note=note.strip())


def _pool_categories(items, names):
    categories = sorted({c for item in items for c in item.x})
    where = {c: i for i, c in enumerate(categories)}
    pdf = []
    for item, labels in zip(items, names):
        for (_, values), name in zip(item.pdf, labels):
            row = np.zeros(len(categories))
            for category, value in zip(item.x, values):
                row[where[category]] = value
            pdf.append((name, row.tolist()))
    cdf = [(name, np.cumsum(row).tolist()) for name, row in pdf]
    return categories, pdf, cdf


def _pool_grids(items, names):
    grids = [np.array([float(v) for v in item.x]) for item in items]
    if all(np.array_equal(g, grids[0]) for g in grids):
        grid = grids[0]
    else:
        grid = np.linspace(min(g.min() for g in grids), max(g.max() for g in grids),
                           max(len(g) for g in grids))
    pdf, cdf = [], []
    for item, own, labels in zip(items, grids, names):
        for (_, values), (_, cumulative), name in zip(item.pdf, item.cdf, labels):
            if np.array_equal(own, grid):
                pdf.append((name, list(values)))
                cdf.append((name, list(cumulative)))
                continue
            moved = np.interp(grid, own, values, left=0.0, right=0.0)
            total = moved.sum()
            pdf.append((name, (moved / total if total > 0 else moved).tolist()))
            cdf.append((name, np.interp(grid, own, cumulative, left=0.0, right=1.0).tolist()))
    return [f"{v:g}" for v in grid], pdf, cdf


# ----------------------------------------------------------------- rasters

def combine_rasters(items):
    first = items[0]
    if any((item.x_name, item.y_name) != (first.x_name, first.y_name) for item in items):
        raise NodeProblem("The rasters plot different dimensions, so they cannot be pooled.")
    sets = [item.density_set for item in items]
    base = sets[0]
    for other in sets[1:]:
        if (other.x_categories, other.y_categories) != (base.x_categories, base.y_categories):
            raise NodeProblem("The rasters disagree about a categorical axis, "
                              "so they cannot be pooled.")
    numeric_x, numeric_y = base.x_categories is None, base.y_categories is None
    x_values = _shared_axis([s.x_values for s in sets], numeric_x)
    y_values = _shared_axis([s.y_values for s in sets], numeric_y)

    names = unique_names([[n for n, _ in s.entries] for s in sets])
    entries, counts = [], {}
    for density_set, labels in zip(sets, names):
        for (original, dist), name in zip(density_set.entries, labels):
            grid = dist.densities
            if not (np.array_equal(dist.x_values, x_values)
                    and np.array_equal(dist.y_values, y_values)):
                grid = _resample(dist, x_values, y_values)
            entries.append((name, BivariateDistribution(x_values, y_values, grid, name)))
            counts[name] = density_set.counts.get(original, 0)
    pooled = BivariateSet(entries, x_values, y_values, base.used_uncertainties,
                          base.x_bandwidth, base.y_bandwidth, counts,
                          base.x_categories, base.y_categories)
    note = (f"Pooled {len(items)} inputs onto one grid. Each input was smoothed on "
            "its own, so use the same density method and bandwidths in each for a "
            "fair comparison.")
    return Raster(first.x_name, first.y_name, pooled, note=note)


def _shared_axis(axes, numeric):
    if all(np.array_equal(a, axes[0]) for a in axes) or not numeric:
        return axes[0]
    return np.linspace(min(a.min() for a in axes), max(a.max() for a in axes),
                       max(len(a) for a in axes))


def _resample(dist, x_values, y_values):
    """A density on its own grid moved onto another, mass kept at 1."""
    across = np.array([np.interp(x_values, dist.x_values, row, left=0.0, right=0.0)
                       for row in dist.densities])
    down = np.array([np.interp(y_values, dist.y_values, across[:, j], left=0.0, right=0.0)
                     for j in range(across.shape[1])]).T
    total = down.sum()
    return down / total if total > 0 else down
