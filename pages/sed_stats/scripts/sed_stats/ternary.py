"""
Ternary (three-component) compositions.

A ternary plot shows three parts of a whole — QFL modal counts, a
clay/silt/sand split, three normalized oxides. Each grain is one point, and
because the three parts sum to a constant the point has only two degrees of
freedom, which is what lets a triangle hold it without loss.

Two things follow from "sums to a constant" and both are handled here:

  * Raw measurements rarely sum to exactly 100. Point counts stop at whatever
    total the operator counted to; percentages carry rounding. Closing each
    row to a constant sum is the standard first step, not a fudge.
  * A composition that sums to zero has no position on the triangle at all,
    and a negative part has none either. Those rows are reported rather than
    silently plotted somewhere wrong.
"""
import numpy as np

# Apex order, and what each position means. Plotly names them a/b/c; the
# geological convention puts the first at the top and reads the other two
# left to right along the base.
APEX_KEYS = ("a", "b", "c")
APEX_POSITIONS = ("top", "lower left", "lower right")

DEFAULT_TOTAL = 100.0

# How far a row's raw sum may sit from the target before it is worth
# mentioning — a percent either way is rounding, more than that is a
# different scale or a missing component.
CLOSURE_TOLERANCE = 1.0


class TernaryData:
    """
    Three components closed to a constant sum, plus what had to be dropped.

    Attributes:
        a, b, c   - the closed components, each (n,), summing row-wise to total
        total     - the constant they sum to
        keep      - boolean mask of the input rows that survived
        raw_sums  - each surviving row's sum before closure
        dropped   - {"nonpositive": n, "negative": n} counts of what was removed
    """

    def __init__(self, a, b, c, total, keep, raw_sums, dropped):
        self.a = a
        self.b = b
        self.c = c
        self.total = total
        self.keep = keep
        self.raw_sums = raw_sums
        self.dropped = dropped

    def __len__(self):
        return int(self.a.size)

    @property
    def dropped_total(self):
        return sum(self.dropped.values())

    @property
    def needed_closure(self):
        """Whether any surviving row's raw sum was far enough off to mention."""
        if self.raw_sums.size == 0:
            return False
        return bool(np.abs(self.raw_sums - self.total).max() > CLOSURE_TOLERANCE)

    @property
    def closure_range(self):
        """(min, max) of the raw row sums, for reporting what was normalized."""
        if self.raw_sums.size == 0:
            return (0.0, 0.0)
        return (float(self.raw_sums.min()), float(self.raw_sums.max()))


def close(a, b, c, total: float = DEFAULT_TOTAL) -> TernaryData:
    """
    Scale each row so its three parts sum to `total`.

    "Closure" is the compositional-data term for this: only the ratios between
    the parts carry information, so rescaling a row to a common sum discards
    nothing and makes rows comparable.

    Rows with a negative part, or with all three parts at zero, are dropped —
    neither has a position on the triangle.

    Raises:
        ValueError: if the three inputs are not the same length
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    c = np.asarray(c, dtype=float)
    if not (a.shape == b.shape == c.shape):
        raise ValueError("The three components must be the same length")

    stacked = np.vstack([a, b, c])
    finite = np.isfinite(stacked).all(axis=0)
    negative = finite & (stacked < 0).any(axis=0)
    sums = stacked.sum(axis=0)
    nonpositive = finite & ~negative & (sums <= 0)

    keep = finite & ~negative & ~nonpositive
    kept = stacked[:, keep]
    raw_sums = kept.sum(axis=0)
    closed = kept / raw_sums * total

    return TernaryData(
        a=closed[0], b=closed[1], c=closed[2], total=float(total),
        keep=keep, raw_sums=raw_sums,
        dropped={
            "negative": int(negative.sum()),
            "nonpositive": int(nonpositive.sum()),
            "missing": int((~finite).sum()),
        },
    )


def to_cartesian(a, b, c, total: float = DEFAULT_TOTAL):
    """
    Triangle coordinates as (x, y), for anything that needs a flat plane.

    The `a` apex sits at the top, `b` at the lower left and `c` at the lower
    right, matching APEX_POSITIONS. Plotly draws ternary traces from a/b/c
    directly, so this is for the computations that need a metric — nearest
    neighbours, a density, a convex hull.
    """
    a = np.asarray(a, dtype=float) / total
    b = np.asarray(b, dtype=float) / total
    c = np.asarray(c, dtype=float) / total
    return 0.5 * (2 * c + a), (np.sqrt(3) / 2) * a


def centroid(data: TernaryData):
    """
    The mean composition, as an (a, b, c) triple on the same scale.

    Arithmetic rather than geometric: the geometric (Aitchison) centre is the
    better-founded average for compositional data, but it is undefined when
    any part is exactly zero, which is common in modal counts — a sandstone
    with no lithics is an ordinary observation, not a missing one.
    """
    if not len(data):
        return (float("nan"),) * 3
    return (float(data.a.mean()), float(data.b.mean()), float(data.c.mean()))
