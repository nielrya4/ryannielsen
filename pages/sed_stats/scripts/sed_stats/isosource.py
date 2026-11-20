"""
Mixing models by exhaustive search of the feasible solutions: IsoSource.

After Phillips & Gregg (2003), Oecologia 136:261-269. With more sources than isotopes
plus one, the mixing equations have no single solution. IsoSource lists every
combination of source proportions, in steps of a chosen increment, that add to 100 %
and reproduce the mixture's isotope values to within a tolerance, and reports the
distribution of each source's proportion across them. The honest answer is that
distribution, not one value: a source that can be anywhere from 0 to 60 % is not
"30 %".

The sources are taken at their mean values, so their own variability, and the
uncertainty in the mixture and in the fractionation, are not propagated. When the sources
and tracers allow one solution, End-member mixing (`emma.py`) carries them through.
"""
import math

import numpy as np

# A feasible-solution search this large is slow in a browser; ask for a coarser increment.
MAXIMUM_COMBINATIONS = 6_000_000


def combination_count(sources, steps):
    """How many ways `steps` increments can be shared among `sources`."""
    return math.comb(steps + sources - 1, sources - 1)


class _Compositions:
    """All the ways to split n steps among p parts, cached by (n, p)."""

    def __init__(self):
        self.cache = {}

    def of(self, n, parts):
        key = (n, parts)
        if key not in self.cache:
            if parts == 1:
                result = np.array([[n]], dtype=np.int16)
            else:
                blocks = []
                for first in range(n + 1):
                    rest = self.of(n - first, parts - 1)
                    blocks.append(np.hstack([np.full((len(rest), 1), first, dtype=np.int16), rest]))
                result = np.vstack(blocks)
            self.cache[key] = result
        return self.cache[key]


def feasible_solutions(source_values, mixture, increment=1.0, tolerance=0.1):
    """
    Every set of source proportions that reproduces the mixture.

    Args:
        source_values: one row per source, one column per isotope
        mixture: the mixture's value for each isotope
        increment: step in percent (100 must be a multiple of it)
        tolerance: how far, in the isotopes' own units, the modelled mixture may be from
            the real one on each isotope

    Returns:
        (array of shape (solutions, sources) in percent, number of combinations tried)

    Raises:
        ValueError: for inconsistent inputs, or a search too large to run
    """
    s = np.asarray(source_values, dtype=float)
    m = np.asarray(mixture, dtype=float)
    if s.ndim != 2 or s.shape[1] != len(m):
        raise ValueError("Each source needs a value for every isotope the mixture has.")
    if s.shape[0] < 2:
        raise ValueError("Need at least two sources.")
    if not np.all(np.isfinite(s)) or not np.all(np.isfinite(m)):
        raise ValueError("Every source and the mixture need a number for each isotope.")
    if increment <= 0 or increment > 100 or abs(100 / increment - round(100 / increment)) > 1e-9:
        raise ValueError("The increment must divide 100 evenly (1, 2, 5, ...).")
    if tolerance < 0:
        raise ValueError("The tolerance cannot be negative.")
    steps = int(round(100 / increment))
    count = combination_count(s.shape[0], steps)
    if count > MAXIMUM_COMBINATIONS:
        raise ValueError(
            f"{s.shape[0]} sources in steps of {increment:g}% is {count:,} combinations, "
            "too many to search here. Use a larger increment, or fewer sources.")

    compositions = _Compositions()
    found = []
    # The first source's share is looped over, so only one slice is in memory at a time.
    for first in range(steps + 1):
        rest = compositions.of(steps - first, s.shape[0] - 1)
        shares = np.hstack([np.full((len(rest), 1), first, dtype=np.int16), rest])
        ok = np.all(np.abs(shares / steps @ s - m) <= tolerance + 1e-12, axis=1)
        if ok.any():
            found.append(shares[ok] * float(increment))
    solutions = np.vstack(found) if found else np.empty((0, s.shape[0]))
    return solutions, count


def summarize(solutions):
    """
    Per source, the distribution of its proportion across the feasible solutions:
    mean, standard deviation, minimum, 1st percentile, median, 99th percentile, maximum.
    """
    if len(solutions) == 0:
        return []
    out = []
    for column in solutions.T:
        out.append({
            "mean": float(column.mean()), "sd": float(column.std(ddof=1)) if len(column) > 1 else 0.0,
            "min": float(column.min()), "p1": float(np.percentile(column, 1)),
            "median": float(np.median(column)), "p99": float(np.percentile(column, 99)),
            "max": float(column.max())})
    return out
