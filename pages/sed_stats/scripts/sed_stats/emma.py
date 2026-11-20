"""
End-member mixing analysis (EMMA): what share of a mixture came from each end member.

With k end members and m tracers, mass balance gives m equations,

    sum_i f_i * s_ij = mixture_j        (one for each tracer j),   sum_i f_i = 1,

so k = m + 1 end members have exactly one solution (Hooper et al. 1990; Christophersen &
Hooper 1992), and fewer have a best-fit one, found here by least squares. More end members
than tracers + 1 leave the fractions undetermined; IsoSource (`isosource.py`) lists the
feasible ones then.

Two choices, both made by the caller:
  * constrained or not. Constrained keeps every fraction between 0 and 1 (non-negative least
    squares). Unconstrained allows negatives, which is itself a finding: a fraction well
    below zero says the mixture lies outside the end members, so one is missing or wrong;
  * what uncertainty to carry. The end members' means and the mixture's are redrawn from
    normal distributions with the spread given (their standard errors, or their standard
    deviations) and the system solved again, many times; the fractions' spread over those
    draws is the uncertainty. This is a Monte Carlo version of the Gaussian error propagation
    of Genereux (1998). It is not a Bayesian model: end-member variability enters only as a
    spread about the mean, with no prior on the fractions.

When the system is over-determined, each tracer is scaled by the spread of the end members'
means, so that an isotope with larger numbers (delta-2H against delta-18O) does not dominate
the fit. For an exact solution the scaling changes nothing.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import nnls

# The weight of the sum-to-one equation against the tracer equations: large enough that the
# fractions sum to one to well within rounding, small enough to leave the solve well-conditioned.
SUM_WEIGHT = 1e4
SPREADS = ("none", "se", "sd")


@dataclass
class EmmaResult:
    fractions: np.ndarray               # (k,) the solution from the means, 0-1
    residual: np.ndarray                # (m,) modelled minus observed, in each tracer's own units
    exact: bool                         # k == m + 1: the equations are solved, not fitted
    clipped: bool                       # constrained, and the unconstrained solution had a negative
    draws: np.ndarray = None            # (trials, k) fractions from the Monte Carlo, or None
    summary: list = field(default_factory=list)   # per end member: mean, sd, p2_5, median, p97_5


def _scales(sources):
    """Per tracer, the spread of the end members' means (never zero)."""
    spread = np.ptp(sources, axis=0)
    spread[spread == 0] = 1.0
    return spread


def solve(sources, mixture, constrained=True, scale=None):
    """
    The fractions for one set of end-member and mixture values.

    Args:
        sources: (k, m) the end members' value for each tracer
        mixture: (m,) the mixture's
        scale: the (m,) factors to divide the tracers by, when several solves must share them
            (default: the spread of the end members' means)

    Returns:
        (fractions, clipped); fractions sum to one
    """
    s = np.asarray(sources, dtype=float)
    mix = np.asarray(mixture, dtype=float)
    scale = _scales(s) if scale is None else scale
    a = np.vstack([(s / scale).T, SUM_WEIGHT * np.ones((1, s.shape[0]))])
    b = np.concatenate([mix / scale, [SUM_WEIGHT]])
    free = np.linalg.lstsq(a, b, rcond=None)[0]
    if not constrained:
        return free, False
    fractions = nnls(a, b)[0]
    return fractions, bool(np.any(free < -1e-9))


def check_shape(k, m):
    """Raise ValueError unless k end members and m tracers can be solved."""
    if m < 1:
        raise ValueError("Choose at least one tracer.")
    if k < 2:
        raise ValueError("Need at least two end members.")
    if k > m + 1:
        raise ValueError(
            f"{k} end members need at least {k - 1} tracers to be solved; {m} "
            f"{'was' if m == 1 else 'were'} given. Add a tracer, drop an end member, or list the "
            "feasible mixes with Mixing solutions instead.")


def mix(source_means, mixture_mean, source_spread=None, mixture_spread=None, constrained=True,
        trials=5000, seed=0):
    """
    Solve the mixing problem, and optionally put an uncertainty on the answer.

    Args:
        source_means: (k, m); mixture_mean: (m,)
        source_spread: (k, m) the standard deviation to redraw each mean with, or None to
            solve once; mixture_spread: (m,) likewise (zeros if None)
        constrained: keep every fraction between 0 and 1
        trials, seed: for the Monte Carlo; seeded, so a result is repeatable

    Raises:
        ValueError: for a shape that cannot be solved (see `check_shape`), or non-finite input
    """
    s = np.asarray(source_means, dtype=float)
    m = np.asarray(mixture_mean, dtype=float)
    check_shape(s.shape[0], s.shape[1])
    if len(m) != s.shape[1]:
        raise ValueError("The mixture needs a value for every tracer the end members have.")
    if not (np.all(np.isfinite(s)) and np.all(np.isfinite(m))):
        raise ValueError("Every end member and the mixture need a number for each tracer.")
    fractions, clipped = solve(s, m, constrained)
    result = EmmaResult(fractions, fractions @ s - m, s.shape[0] == s.shape[1] + 1, clipped)
    if source_spread is None:
        return result

    rng = np.random.default_rng(seed)
    sd = np.asarray(source_spread, dtype=float)
    msd = np.zeros(len(m)) if mixture_spread is None else np.asarray(mixture_spread, dtype=float)
    draws = np.empty((trials, s.shape[0]))
    for t in range(trials):
        draws[t] = solve(s + rng.standard_normal(s.shape) * sd,
                         m + rng.standard_normal(len(m)) * msd, constrained)[0]
    result.draws = draws
    result.summary = [
        {"mean": float(c.mean()), "sd": float(c.std(ddof=1)),
         "p2_5": float(np.percentile(c, 2.5)), "median": float(np.median(c)),
         "p97_5": float(np.percentile(c, 97.5))} for c in draws.T]
    return result


def separate(source_means, mixtures, source_spread=None, constrained=True, trials=1000, seed=0,
             budget=200_000):
    """
    Solve many mixtures against the same end members: a stream sampled through time.

    Each row of `mixtures` is solved from the end members' means, and, if `source_spread` is
    given, again for every Monte Carlo redraw of those means, the same redraws serving every row,
    so the spread says how much each fraction depends on how well the end members are known.
    A mixture's own measurement error is not carried: it is taken as exact.

    Args:
        source_means: (k, m); mixtures: (rows, m)
        source_spread: (k, m) standard deviations to redraw with, or None
        trials: the Monte Carlo draws, reduced if rows * trials exceeds `budget` solves

    Returns:
        (fractions (rows, k), standard deviations (rows, k) or None, clipped (rows,) bool, trials used)

    Raises:
        ValueError: for a shape that cannot be solved (see `check_shape`), or non-finite input
    """
    s = np.asarray(source_means, dtype=float)
    b = np.asarray(mixtures, dtype=float)
    if b.ndim != 2 or b.shape[1] != s.shape[1]:
        raise ValueError("Each mixture needs a value for every tracer the end members have.")
    check_shape(s.shape[0], s.shape[1])
    if not (np.all(np.isfinite(s)) and np.all(np.isfinite(b))):
        raise ValueError("Every end member and mixture need a number for each tracer.")
    scale = _scales(s)
    solved = [solve(s, row, constrained, scale) for row in b]
    fractions = np.array([f for f, _ in solved])
    clipped = np.array([c for _, c in solved])
    if source_spread is None:
        return fractions, None, clipped, 0
    sd = np.asarray(source_spread, dtype=float)
    used = max(50, min(int(trials), budget // max(len(b), 1)))
    rng = np.random.default_rng(seed)
    draws = np.empty((used, len(b), s.shape[0]))
    targets = np.vstack([(b / scale).T, SUM_WEIGHT * np.ones((1, len(b)))])
    for t in range(used):
        drawn = s + rng.standard_normal(s.shape) * sd
        if constrained:
            for r, row in enumerate(b):
                draws[t, r] = solve(drawn, row, True, scale)[0]
        else:
            a = np.vstack([(drawn / scale).T, SUM_WEIGHT * np.ones((1, s.shape[0]))])
            draws[t] = (np.linalg.pinv(a) @ targets).T
    return fractions, draws.std(axis=0, ddof=1), clipped, used
