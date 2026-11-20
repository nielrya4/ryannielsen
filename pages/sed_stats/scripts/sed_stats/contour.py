"""
Density contours: the outline of the region that holds a share of a density.

`density_level` finds the height at which the cells above it hold a chosen share
of the total (a highest-density region), and `contour_rings` traces the closed
outlines of that region on the grid by marching squares.
"""
import numpy as np

# For each of the 16 ways the four corners of a cell can sit above or below the
# level, the pairs of cell edges the contour crosses. Corners run c0 (lower
# left), c1 (lower right), c2 (upper right), c3 (upper left) as bits 1, 2, 4, 8;
# edges are 0 bottom, 1 right, 2 top, 3 left.
_SEGMENTS = {
    1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)],
    5: [(3, 0), (1, 2)],            # saddle: c0 and c2 above
    6: [(0, 2)], 7: [(3, 2)], 8: [(2, 3)], 9: [(0, 2)],
    10: [(0, 1), (2, 3)],           # saddle: c1 and c3 above
    11: [(1, 2)], 12: [(1, 3)], 13: [(0, 1)], 14: [(3, 0)],
}


def density_level(grid, share):
    """
    The density value such that the cells at or above it hold `share` (0-1) of
    the grid's total.
    """
    flat = np.sort(np.asarray(grid, dtype=float).ravel())[::-1]
    total = flat.sum()
    if total <= 0:
        return 0.0
    index = int(np.searchsorted(np.cumsum(flat), share * total))
    return float(flat[min(index, flat.size - 1)])


def contour_rings(x_values, y_values, grid, level):
    """
    Closed outlines of the region where `grid` (rows are y) is at or above `level`.

    The grid is padded with a border of zeros first, so a region that runs off
    the edge still closes into a ring instead of an open line.

    Returns:
        a list of rings, each a list of (x, y) vertices without repeating the
        first. A region with a hole gives an outer ring and an inner one.
    """
    x_values = np.asarray(x_values, dtype=float)
    y_values = np.asarray(y_values, dtype=float)
    grid = np.pad(np.asarray(grid, dtype=float), 1)
    dx = float(x_values[1] - x_values[0]) if x_values.size > 1 else 1.0
    dy = float(y_values[1] - y_values[0]) if y_values.size > 1 else 1.0
    xs = np.concatenate([[x_values[0] - dx], x_values, [x_values[-1] + dx]])
    ys = np.concatenate([[y_values[0] - dy], y_values, [y_values[-1] + dy]])
    if level <= 0:
        return []

    def crossing(kind, i, j):
        """The point where the contour crosses an edge, by linear interpolation."""
        if kind == "h":      # between (j, i) and (j, i + 1)
            a, b = grid[j, i], grid[j, i + 1]
            t = (level - a) / (b - a)
            return float(xs[i] + t * (xs[i + 1] - xs[i])), float(ys[j])
        a, b = grid[j, i], grid[j + 1, i]       # between (j, i) and (j + 1, i)
        t = (level - a) / (b - a)
        return float(xs[i]), float(ys[j] + t * (ys[j + 1] - ys[j]))

    above = grid >= level
    neighbours = {}
    for j in range(grid.shape[0] - 1):
        for i in range(grid.shape[1] - 1):
            case = (int(above[j, i]) | int(above[j, i + 1]) << 1
                    | int(above[j + 1, i + 1]) << 2 | int(above[j + 1, i]) << 3)
            for first, second in _SEGMENTS.get(case, ()):
                edges = {0: ("h", i, j), 1: ("v", i + 1, j),
                         2: ("h", i, j + 1), 3: ("v", i, j)}
                p, q = edges[first], edges[second]
                neighbours.setdefault(p, []).append(q)
                neighbours.setdefault(q, []).append(p)

    rings, visited = [], set()
    for start in neighbours:
        if start in visited:
            continue
        ring, previous, current = [], None, start
        while current not in visited:
            visited.add(current)
            ring.append(crossing(*current))
            options = [n for n in neighbours[current] if n != previous]
            if not options:
                break
            previous, current = current, options[0]
            if current == start:
                break
        if len(ring) >= 3:
            rings.append(ring)
    return rings
