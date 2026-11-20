"""
Straight-line fits of one variable on another, for lines such as a local meteoric
water line (delta-2H against delta-18O).

Either can be weighted, by precipitation amount for a local meteoric water line: the weighted
fit minimises sum(w * residual^2) with each point's weight w (Hughes & Crawford 2012, who
weighted by rainfall amount; Crawford et al. 2014 compared the weighted and unweighted forms of
these methods). Large events then count for more, and the many small ones, whose d-excess is
often lowered by evaporation below the cloud, for less.

Two methods, both defined by their formulas:
  * ordinary least squares, y on x: the slope is cov(x, y) / var(x). It treats x as
    exact and puts all the scatter in y;
  * reduced major axis, which treats the two alike: |slope| = sd(y) / sd(x), with the
    sign of the correlation. Where both variables are measured with error (as isotope
    ratios are) it is the usual alternative, and for a high correlation the two agree.
"""
import math

import numpy as np

METHODS = {"ols": "Ordinary least squares (y on x)", "rma": "Reduced major axis"}


def linear_fit(xs, ys, method="ols", weights=None):
    """
    Fit y = slope * x + intercept.

    Args:
        weights: a weight for each point (an amount), or None for equal weights. Only their
            ratios matter: multiplying every weight by a constant changes nothing. A point
            with a missing or zero weight is left out.

    Returns:
        dict: n, slope, intercept, r2, slope_se, intercept_se (the standard errors of
        the least squares fit, which are the ones in common use, for either method;
        weighted, they use sum(w * r^2) / (n - 2) for the variance), x_min, x_max, weighted

    Raises:
        ValueError: for fewer than three points, x with no spread, a negative weight, or an
            unknown method
    """
    if method not in METHODS:
        raise ValueError(f"Unknown method '{method}'.")
    if weights is None:
        weights = [1.0] * len(xs)
    if len(weights) != len(xs):
        raise ValueError("Each point needs a weight.")
    weighted = any(w != weights[0] for w in weights)
    pairs = []
    for x, y, w in zip(xs, ys, weights):
        if x is None or y is None or w is None:
            continue
        x, y, w = float(x), float(y), float(w)
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(w)):
            continue
        if w < 0:
            raise ValueError("A weight cannot be negative.")
        if w > 0:
            pairs.append((x, y, w))
    if len(pairs) < 3:
        raise ValueError("Need at least three points to fit a line.")
    x = np.array([p[0] for p in pairs])
    y = np.array([p[1] for p in pairs])
    w = np.array([p[2] for p in pairs])
    n = len(x)
    total = w.sum()
    mx, my = float((w * x).sum() / total), float((w * y).sum() / total)
    sxx = float((w * (x - mx) ** 2).sum())
    syy = float((w * (y - my) ** 2).sum())
    sxy = float((w * (x - mx) * (y - my)).sum())
    if sxx <= 0:
        raise ValueError("The x values do not vary, so no line can be fitted.")
    r = sxy / math.sqrt(sxx * syy) if syy > 0 else 0.0
    ols_slope = sxy / sxx
    ols_intercept = my - ols_slope * mx
    residual = float((w * (y - (ols_slope * x + ols_intercept)) ** 2).sum())
    mean_square = residual / (n - 2)
    slope_se = math.sqrt(mean_square / sxx)
    intercept_se = math.sqrt(mean_square * (1.0 / total + mx ** 2 / sxx))
    if method == "rma":
        if syy <= 0:
            raise ValueError("The y values do not vary, so no line can be fitted.")
        slope = math.copysign(math.sqrt(syy / sxx), sxy)
        intercept = my - slope * mx
    else:
        slope, intercept = ols_slope, ols_intercept
    return {"n": n, "slope": slope, "intercept": intercept, "r2": r * r,
            "slope_se": slope_se, "intercept_se": intercept_se,
            "x_min": float(x.min()), "x_max": float(x.max()), "weighted": weighted}
