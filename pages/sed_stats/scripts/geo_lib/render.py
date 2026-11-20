"""
Pixels for the map: elevation shaded by height, a mask as a flat colour, and a value ramp for
climate samples. NumPy only, so a million cells cost an array operation, not a Python loop.
"""
import numpy as np

# Low to high: green lowlands through browns to white peaks.
ELEVATION_RAMP = [
    (0.00, (56, 118, 77)), (0.25, (143, 176, 98)), (0.50, (214, 200, 130)),
    (0.75, (158, 118, 84)), (1.00, (250, 248, 244)),
]

# Cool to warm for climate values.
VALUE_RAMP = [
    (0.00, (68, 1, 84)), (0.25, (59, 82, 139)), (0.50, (33, 145, 140)),
    (0.75, (94, 201, 98)), (1.00, (253, 231, 37)),
]


def ramp(t, stops):
    """RGB (floats) for each t in 0-1 along `stops`, [(position, (r, g, b)), ...]."""
    t = np.clip(np.asarray(t, dtype=np.float64), 0.0, 1.0)
    positions = [p for p, _ in stops]
    return np.stack([np.interp(t, positions, [c[i] for _, c in stops]) for i in range(3)], axis=-1)


def elevation_rgba(grid, nodata_zero=True):
    """
    A (h, w, 4) uint8 image of a DEM, hypsometrically tinted between its own lowest and highest
    real cells. Cells with no data (0 m in a 3DEP grid, or NaN) are transparent.
    """
    grid = np.asarray(grid, dtype=np.float64)
    valid = np.isfinite(grid)
    if nodata_zero:
        valid &= grid != 0.0
    image = np.zeros(grid.shape + (4,), dtype=np.uint8)
    if not valid.any():
        return image
    low, high = grid[valid].min(), grid[valid].max()
    t = (grid - low) / ((high - low) or 1.0)
    image[..., :3] = ramp(t, ELEVATION_RAMP).round().astype(np.uint8)
    image[..., 3] = np.where(valid, 255, 0)
    return image


def mask_rgba(mask, color=(33, 150, 243)):
    """A (h, w, 4) uint8 image that is `color` where the mask is True and transparent elsewhere."""
    mask = np.asarray(mask, dtype=bool)
    image = np.zeros(mask.shape + (4,), dtype=np.uint8)
    image[mask] = (*color, 255)
    return image


def value_colors(values):
    """
    ('#rrggbb' or None for each value, low, high) for a ramp across the values' range; None
    where a value is missing.
    """
    real = [v for v in values if v is not None]
    if not real:
        return [None] * len(values), None, None
    low, high = min(real), max(real)
    span = (high - low) or 1.0
    colors = []
    for value in values:
        if value is None:
            colors.append(None)
            continue
        r, g, b = ramp((value - low) / span, VALUE_RAMP).round().astype(int)
        colors.append(f"#{r:02x}{g:02x}{b:02x}")
    return colors, low, high


def elevation_stats(grid, mask):
    """(mean, min, max) elevation inside the mask over real cells, or None if there are none."""
    grid = np.asarray(grid, dtype=np.float64)
    inside = np.asarray(mask, dtype=bool) & np.isfinite(grid) & (grid != 0.0)
    if not inside.any():
        return None
    cells = grid[inside]
    return float(cells.mean()), float(cells.min()), float(cells.max())


def elevation_extremes(grid, mask):
    """
    The highest and lowest real cells inside the mask, as ((row, col, elevation), (row, col,
    elevation)), or None if there are none. Where several cells share the extreme elevation, the
    first in reading order (top to bottom, left to right) is the one reported.
    """
    grid = np.asarray(grid, dtype=np.float64)
    inside = np.asarray(mask, dtype=bool) & np.isfinite(grid) & (grid != 0.0)
    if not inside.any():
        return None

    def cell(values):
        row, col = np.unravel_index(int(np.argmax(values)), grid.shape)
        return int(row), int(col), float(grid[row, col])
    return cell(np.where(inside, grid, -np.inf)), cell(np.where(inside, -grid, -np.inf))
