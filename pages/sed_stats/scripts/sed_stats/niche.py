"""
Isotopic niche: the standard ellipse and its area, the convex hull, and overlap.

After Jackson et al. (2011), J. Anim. Ecol. 80:595-602 (SIBER), whose definitions
were read from the paper:

  * the standard ellipse has the sample covariance matrix S for its shape, so its
    semi-axes are the square roots of S's eigenvalues, and its area (SEA) is
    pi * sqrt(det S). It is to a bivariate sample what the standard deviation is to
    a univariate one, and holds roughly 40 % of normally distributed points;
  * SEA is biased low for small samples, corrected by (n - 1) / (n - 2) (SEAc);
  * the total area (TA) is that of the convex hull of the points (Layman et al. 2007),
    which grows with every extra point, so it should not be compared between samples
    of different size.

Two further community measures from Layman et al. (2007) are given: the mean distance
to the centroid (CD) and the mean nearest-neighbour distance (MNND).
"""
import math

import numpy as np

from .hull import convex_hull

# A point cloud this small has no meaningful niche.
MINIMUM_POINTS = 3
# Below this, SEAc is available but is a poor estimate (Jackson et al. 2011 advise
# larger samples; Bayesian estimates are better for small n).
COMFORTABLE_POINTS = 10
SEGMENTS = 120


def _clean(xs, ys):
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys)
             if x is not None and y is not None and math.isfinite(x) and math.isfinite(y)]
    return np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])


def covariance(xs, ys):
    """The 2 x 2 sample covariance matrix (n - 1 in the denominator)."""
    x, y = _clean(xs, ys)
    if len(x) < 2:
        raise ValueError("Need at least two points for a covariance.")
    return np.cov(np.vstack([x, y]))


def prediction_scale(level):
    """
    Factor on the standard ellipse's axes that makes it hold `level` (0-1) of
    bivariate-normal points: the square root of the chi-square quantile on two
    degrees of freedom, sqrt(-2 ln(1 - level)). 1 is the standard ellipse itself.
    """
    if not 0 < level < 1:
        raise ValueError("The share of points must be between 0 and 1.")
    return math.sqrt(-2.0 * math.log(1.0 - level))


def ellipse(xs, ys, scale=1.0, segments=SEGMENTS):
    """
    The vertices of the ellipse centred on the mean with the sample covariance's shape,
    its axes multiplied by `scale`. Empty if there are too few points or they lie on a line.
    """
    x, y = _clean(xs, ys)
    if len(x) < MINIMUM_POINTS:
        return []
    values, vectors = np.linalg.eigh(np.cov(np.vstack([x, y])))
    if values[0] <= 1e-12 * max(values[1], 1e-300):
        return []
    angle = np.linspace(0.0, 2.0 * math.pi, segments, endpoint=False)
    unit = np.vstack([np.cos(angle), np.sin(angle)])
    shape = vectors @ (np.sqrt(values)[:, None] * unit) * scale
    return [(float(x.mean() + a), float(y.mean() + b)) for a, b in zip(shape[0], shape[1])]


def polygon_area(vertices):
    """Shoelace area of a simple polygon."""
    if len(vertices) < 3:
        return 0.0
    v = np.array(vertices, dtype=float)
    return 0.5 * abs(float(np.dot(v[:, 0], np.roll(v[:, 1], -1))
                           - np.dot(v[:, 1], np.roll(v[:, 0], -1))))


def clip_convex(subject, clip):
    """
    The intersection of two convex polygons (Sutherland-Hodgman), counter-clockwise.
    Ellipses and hulls are convex, so this is exact for them.
    """
    def inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0

    def crossing(p, q, a, b):
        x1, y1, x2, y2 = p[0], p[1], q[0], q[1]
        x3, y3, x4, y4 = a[0], a[1], b[0], b[1]
        d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    def counter_clockwise(poly):
        v = np.array(poly)
        signed = np.dot(v[:, 0], np.roll(v[:, 1], -1)) - np.dot(v[:, 1], np.roll(v[:, 0], -1))
        return list(poly) if signed >= 0 else list(reversed(poly))

    output = counter_clockwise(subject)
    clip = counter_clockwise(clip)
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        points, output = output, []
        if not points:
            break
        previous = points[-1]
        for current in points:
            if inside(current, a, b):
                if not inside(previous, a, b):
                    output.append(crossing(previous, current, a, b))
                output.append(current)
            elif inside(previous, a, b):
                output.append(crossing(previous, current, a, b))
            previous = current
    return output


def overlap_area(first, second):
    """Area shared by two convex outlines (0 if either is empty or they do not meet)."""
    if len(first) < 3 or len(second) < 3:
        return 0.0
    return polygon_area(clip_convex(first, second))


def metrics(xs, ys):
    """
    The niche measures of one group, as a dict: n, mean x and y, sea, seac, ta, cd, mnnd.
    Areas are None where they cannot be found (too few points, or all on a line).
    """
    x, y = _clean(xs, ys)
    n = len(x)
    out = {"n": n, "mean_x": float(x.mean()) if n else None,
           "mean_y": float(y.mean()) if n else None,
           "sea": None, "seac": None, "ta": None, "cd": None, "mnnd": None}
    if n < MINIMUM_POINTS:
        return out
    determinant = float(np.linalg.det(np.cov(np.vstack([x, y]))))
    if determinant > 0:
        out["sea"] = math.pi * math.sqrt(determinant)
        out["seac"] = out["sea"] * (n - 1) / (n - 2)
    out["ta"] = polygon_area(convex_hull(x, y)) or None
    out["cd"] = float(np.mean(np.hypot(x - x.mean(), y - y.mean())))
    distances = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
    np.fill_diagonal(distances, np.inf)
    out["mnnd"] = float(distances.min(axis=1).mean())
    return out
