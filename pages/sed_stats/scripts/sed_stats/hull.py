"""Convex hulls of point clouds."""


def convex_hull(xs, ys):
    """
    The convex hull of points, counter-clockwise, without repeating the first.

    Andrew's monotone chain. Duplicate points are ignored, and fewer than
    three distinct points — or points that all lie on one line — have no
    enclosed area, so they give an empty list rather than a degenerate shape.
    """
    points = sorted(set(zip(map(float, xs), map(float, ys))))
    if len(points) < 3:
        return []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def half(sequence):
        chain = []
        for point in sequence:
            while len(chain) >= 2 and cross(chain[-2], chain[-1], point) <= 0:
                chain.pop()
            chain.append(point)
        return chain

    lower = half(points)
    upper = half(reversed(points))
    hull = lower[:-1] + upper[:-1]
    return hull if len(hull) >= 3 else []
