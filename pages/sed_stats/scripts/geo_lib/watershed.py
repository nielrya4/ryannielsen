"""
Watershed delineation, implemented in pure NumPy/Python.

Mirrors the classic pysheds-based pipeline (fill depressions -> resolve
flats -> D8 flow direction -> flow accumulation -> catchment delineation)
from the reference notebook, but without pysheds/rasterio/GDAL -- none of
which are available in Pyodide. Everything here runs on plain NumPy arrays
so it can execute client-side in the browser.

Pipeline (see `delineate`):
    1. fill_depressions   - Priority-Flood (Barnes et al. 2014)
    2. compute_flow_direction - vectorized D8 steepest descent
    3. resolve_flats      - routes flat/plateau cells toward their spill point
    4. flow_accumulation  - topological (Kahn's algorithm) upstream-cell count
    5. snap_to_stream     - snaps a clicked pour point onto the nearest channel
    6. delineate_catchment - BFS over the reverse flow-direction graph
    7. mask_to_geojson    - traces the catchment mask into a GeoJSON polygon
"""
import math
from collections import deque

import numpy as np

from . import terrain

# ESRI D8 direction codes, matching the reference notebook's dirmap:
# (N, NE, E, SE, S, SW, W, NW)
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)
_D8_OFFSETS = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
_D8_DISTS = [1.0, math.sqrt(2), 1.0, math.sqrt(2), 1.0, math.sqrt(2), 1.0, math.sqrt(2)]
_D8_4_OFFSETS = [(-1, 0), (0, 1), (1, 0), (0, -1)]


# ---------------------------------------------------------------------------
# 1. Depression filling
# ---------------------------------------------------------------------------

def fill_depressions(dem, n_buckets=20000):
    """
    Priority-Flood depression filling (Barnes et al., 2014), using a bucket
    queue instead of a binary heap.

    Raises every interior cell just enough that a monotonic non-increasing
    D8 path exists from it to some edge cell, eliminating all interior
    local minima ("pits") without otherwise altering the terrain.

    A bucket queue exploits the fact that elevations are bounded: cells are
    sorted into `n_buckets` elevation bins instead of a comparison-based
    heap, and a pointer that only ever moves forward finds the next
    non-empty bucket. That makes pop-minimum O(1) amortized instead of
    O(log n), which matters a lot at the cell counts a coarse-to-fine DEM
    grid can reach (RichDEM and other production priority-flood
    implementations use this same technique). Ties within a bucket are
    processed in arbitrary order, which is safe as long as buckets are fine
    enough that within-bucket elevation differences are negligible relative
    to the DEM's own resolution -- `n_buckets=20000` over a typical few
    hundred to few thousand meter elevation range keeps buckets well under
    0.5m wide.
    """
    H, W = dem.shape
    filled = dem.astype(np.float64).copy()
    visited = np.zeros((H, W), dtype=bool)

    emin = float(filled.min())
    emax = float(filled.max())
    span = max(emax - emin, 1e-6)
    scale = (n_buckets - 1) / span

    def bucket_of(elev):
        b = int((elev - emin) * scale)
        if b < 0:
            return 0
        if b >= n_buckets:
            return n_buckets - 1
        return b

    buckets = [[] for _ in range(n_buckets)]

    def push(elev, r, c, min_bucket=0):
        b = bucket_of(elev)
        if b < min_bucket:
            b = min_bucket
        buckets[b].append((elev, r, c))

    for c in range(W):
        for r in (0, H - 1):
            if not visited[r, c]:
                visited[r, c] = True
                push(filled[r, c], r, c)
    for r in range(H):
        for c in (0, W - 1):
            if not visited[r, c]:
                visited[r, c] = True
                push(filled[r, c], r, c)

    current = 0
    while current < n_buckets:
        bucket = buckets[current]
        if not bucket:
            current += 1
            continue
        elev, r, c = bucket.pop()
        for dr, dc in _D8_OFFSETS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W and not visited[nr, nc]:
                visited[nr, nc] = True
                new_elev = filled[nr, nc] if filled[nr, nc] > elev else elev
                filled[nr, nc] = new_elev
                # new_elev >= elev always, so its bucket should never be
                # behind `current` -- clamped defensively against float
                # rounding right at a bucket boundary.
                push(new_elev, nr, nc, min_bucket=current)

    return filled


# ---------------------------------------------------------------------------
# 2. D8 flow direction (vectorized)
# ---------------------------------------------------------------------------

def compute_flow_direction(dem, dirmap=DIRMAP):
    """
    Vectorized D8 flow direction.

    Returns an (H, W) int32 array of direction codes from `dirmap`, or 0
    for cells with no strictly-downhill neighbor (pits/flats left for
    `resolve_flats`, or genuine edge outlets).
    """
    H, W = dem.shape
    padded = np.full((H + 2, W + 2), np.nan, dtype=np.float64)
    padded[1:-1, 1:-1] = dem

    best_slope = np.zeros((H, W), dtype=np.float64)
    direction = np.zeros((H, W), dtype=np.int32)

    for (dr, dc), dist, code in zip(_D8_OFFSETS, _D8_DISTS, dirmap):
        neighbor = padded[1 + dr:1 + dr + H, 1 + dc:1 + dc + W]
        slope = (dem - neighbor) / dist
        slope = np.nan_to_num(slope, nan=-np.inf)
        better = slope > best_slope
        direction = np.where(better, code, direction)
        best_slope = np.where(better, slope, best_slope)

    direction[best_slope <= 0] = 0
    return direction


# ---------------------------------------------------------------------------
# 3. Flat resolution
# ---------------------------------------------------------------------------

def resolve_flats(dem, direction):
    """
    Assign a flow direction to flat cells (direction == 0) by routing them
    toward the nearest lower terrain via a distance-from-outlet gradient
    (a simplified Garbrecht & Martz 1997). Mutates and returns `direction`.
    """
    H, W = dem.shape
    unresolved = direction == 0
    if not np.any(unresolved):
        return direction

    visited = np.zeros((H, W), dtype=bool)
    unresolved_rows, unresolved_cols = np.nonzero(unresolved)

    for start_r, start_c in zip(unresolved_rows.tolist(), unresolved_cols.tolist()):
        if visited[start_r, start_c]:
            continue

        elevation = dem[start_r, start_c]
        flat_cells = []
        outlet_cells = []
        queue = deque([(start_r, start_c)])
        visited[start_r, start_c] = True

        while queue:
            r, c = queue.popleft()
            flat_cells.append((r, c))
            has_outlet_neighbor = False
            for dr, dc in _D8_OFFSETS:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < H and 0 <= nc < W):
                    continue
                # A neighbor is part of *this* flat only if it's at the same
                # elevation AND was itself unresolved -- an equal-elevation
                # neighbor that already has a valid direction is not part of
                # the flat, it's a legitimate spill target (this happens
                # whenever fill_depressions raises a basin to exactly match
                # its lowest rim cell's natural elevation).
                neighbor_in_flat = dem[nr, nc] == elevation and unresolved[nr, nc]
                if neighbor_in_flat:
                    if not visited[nr, nc]:
                        visited[nr, nc] = True
                        queue.append((nr, nc))
                elif dem[nr, nc] <= elevation:
                    has_outlet_neighbor = True
            if has_outlet_neighbor:
                outlet_cells.append((r, c))

        if not outlet_cells:
            # Fully enclosed flat with no lower neighbor anywhere (shouldn't
            # happen after fill_depressions) -- leave as a terminal sink.
            continue

        flat_set = set(flat_cells)
        outlet_set = set(outlet_cells)

        dist = {cell: 0 for cell in outlet_cells}
        bfs_queue = deque(outlet_cells)
        while bfs_queue:
            r, c = bfs_queue.popleft()
            for dr, dc in _D8_OFFSETS:
                nr, nc = r + dr, c + dc
                if (nr, nc) in flat_set and (nr, nc) not in dist:
                    dist[(nr, nc)] = dist[(r, c)] + 1
                    bfs_queue.append((nr, nc))

        for (r, c) in flat_cells:
            if (r, c) in outlet_set:
                best_code, best_elev, found = 0, None, False
                for (dr, dc), code in zip(_D8_OFFSETS, DIRMAP):
                    nr, nc = r + dr, c + dc
                    if not (0 <= nr < H and 0 <= nc < W):
                        continue
                    neighbor_in_flat = dem[nr, nc] == elevation and unresolved[nr, nc]
                    if neighbor_in_flat or dem[nr, nc] > elevation:
                        continue
                    if not found or dem[nr, nc] < best_elev:
                        best_elev = dem[nr, nc]
                        best_code = code
                        found = True
                if best_code:
                    direction[r, c] = best_code
            else:
                my_dist = dist.get((r, c))
                if my_dist is None:
                    continue
                best_code, best_d = 0, my_dist
                for (dr, dc), code in zip(_D8_OFFSETS, DIRMAP):
                    nd = dist.get((r + dr, c + dc))
                    if nd is not None and nd < best_d:
                        best_d = nd
                        best_code = code
                if best_code:
                    direction[r, c] = best_code

    return direction


# ---------------------------------------------------------------------------
# 4. Flow accumulation
# ---------------------------------------------------------------------------

def compute_downstream_index(direction, dirmap=DIRMAP):
    """
    Flatten the direction raster into a downstream-cell-index array:
    `downstream[i]` is the flat index of the cell that cell `i` drains
    into, or -1 if it has no valid downstream neighbor (an outlet).
    """
    H, W = direction.shape
    rows, cols = np.indices((H, W))
    rows_flat = rows.ravel()
    cols_flat = cols.ravel()
    flat_idx = rows_flat * W + cols_flat
    dir_flat = direction.ravel()

    downstream = np.full(rows_flat.shape[0], -1, dtype=np.int64)

    for (dr, dc), code in zip(_D8_OFFSETS, dirmap):
        mask = dir_flat == code
        if not np.any(mask):
            continue
        r = rows_flat[mask] + dr
        c = cols_flat[mask] + dc
        valid = (r >= 0) & (r < H) & (c >= 0) & (c < W)
        idxs = flat_idx[mask]
        downstream[idxs[valid]] = r[valid] * W + c[valid]

    return downstream


def flow_accumulation(downstream):
    """
    Flow accumulation via Kahn's topological sort over the flow-direction
    DAG: each cell starts with an accumulation of 1 (itself) and adds its
    total to its downstream neighbor once all of that neighbor's other
    upstream cells have been processed.
    """
    n = downstream.shape[0]
    in_degree = np.zeros(n, dtype=np.int64)
    valid_targets = downstream[downstream >= 0]
    np.add.at(in_degree, valid_targets, 1)

    acc = np.ones(n, dtype=np.float64)
    queue = deque(np.nonzero(in_degree == 0)[0].tolist())
    while queue:
        cell = queue.popleft()
        target = downstream[cell]
        if target >= 0:
            acc[target] += acc[cell]
            in_degree[target] -= 1
            if in_degree[target] == 0:
                queue.append(target)
    return acc


# ---------------------------------------------------------------------------
# 5. Pour point snapping
# ---------------------------------------------------------------------------

def snap_to_stream(acc_grid, row, col, search_radius=10):
    """
    Snap a clicked pour point to the highest-flow-accumulation cell within
    `search_radius` pixels, so it lands on an actual channel rather than a
    hillslope pixel a few cells off the true stream.
    """
    H, W = acc_grid.shape
    r0, r1 = max(0, row - search_radius), min(H, row + search_radius + 1)
    c0, c1 = max(0, col - search_radius), min(W, col + search_radius + 1)
    window = acc_grid[r0:r1, c0:c1]
    local_r, local_c = np.unravel_index(np.argmax(window), window.shape)
    return r0 + int(local_r), c0 + int(local_c)


# ---------------------------------------------------------------------------
# 6. Catchment delineation
# ---------------------------------------------------------------------------

def delineate_catchment(downstream, pour_idx, shape):
    """BFS over the reverse flow-direction graph from the pour point."""
    n = shape[0] * shape[1]
    upstream = [[] for _ in range(n)]
    for cell in range(n):
        target = downstream[cell]
        if target >= 0:
            upstream[target].append(cell)

    visited = np.zeros(n, dtype=bool)
    visited[pour_idx] = True
    queue = deque([pour_idx])
    while queue:
        cell = queue.popleft()
        for up in upstream[cell]:
            if not visited[up]:
                visited[up] = True
                queue.append(up)

    return visited.reshape(shape)


def mask_touches_edge(mask):
    return bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())


def approximate_area_km2(mask, px_size_m):
    cell_km2 = (px_size_m / 1000.0) ** 2
    return float(mask.sum()) * cell_km2


# ---------------------------------------------------------------------------
# 7. Stream network & Strahler order
# ---------------------------------------------------------------------------

def stream_mask_from_area(acc, px_size_m, min_drainage_area_km2=0.5):
    """
    Boolean mask (flat, matching `acc`) of "stream" cells: flow
    accumulation at or above a minimum drainage area, expressed in real
    km^2 rather than a raw cell-count threshold -- the same cell count
    means a wildly different drainage area at 10m/px vs 100m/px, so a
    fixed cell threshold wouldn't mean the same thing across our range of
    grid resolutions.
    """
    cell_km2 = (px_size_m / 1000.0) ** 2
    threshold_cells = max(1.0, min_drainage_area_km2 / cell_km2)
    return acc >= threshold_cells


def compute_stream_order(downstream, is_stream):
    """
    Strahler stream order for cells where `is_stream` is True (0 elsewhere).

    Topological (Kahn's algorithm) pass, identical in structure to
    `flow_accumulation`, but instead of summing, each cell tracks
    `(max_order_seen, tie_count)` among its *already-processed* upstream
    stream-neighbors: a headwater (no upstream stream cell) is order 1;
    where tributaries meet, the order increases by one only if two or
    more upstream tributaries share the current maximum order, otherwise
    the max order continues downstream unchanged -- the standard Strahler
    rule.
    """
    n = downstream.shape[0]
    order = np.zeros(n, dtype=np.int32)
    stream_idx = np.nonzero(is_stream)[0]
    if stream_idx.size == 0:
        return order

    in_degree = np.zeros(n, dtype=np.int64)
    for cell in stream_idx.tolist():
        target = downstream[cell]
        if target >= 0 and is_stream[target]:
            in_degree[target] += 1

    max_seen = np.zeros(n, dtype=np.int32)
    tie_count = np.zeros(n, dtype=np.int32)

    queue = deque(cell for cell in stream_idx.tolist() if in_degree[cell] == 0)
    for cell in queue:
        order[cell] = 1

    while queue:
        cell = queue.popleft()
        target = downstream[cell]
        if target < 0 or not is_stream[target]:
            continue
        c_order = order[cell]
        if c_order > max_seen[target]:
            max_seen[target] = c_order
            tie_count[target] = 1
        elif c_order == max_seen[target]:
            tie_count[target] += 1
        in_degree[target] -= 1
        if in_degree[target] == 0:
            order[target] = max_seen[target] + 1 if tie_count[target] >= 2 else max_seen[target]
            queue.append(target)

    return order


def stream_network_geojson(downstream, order, is_stream, dem_result):
    """
    Trace the stream network into one GeoJSON MultiLineString Feature per
    Strahler order present -- a segment per stream cell to its downstream
    stream neighbor, in lon/lat. A handful of features (one per order
    level actually present), not one per cell.
    """
    _, W = dem_result['grid'].shape
    segments_by_order = {}

    for cell in np.nonzero(is_stream)[0].tolist():
        target = downstream[cell]
        if target < 0 or not is_stream[target]:
            continue
        cell_order = int(order[cell])
        r0, c0 = divmod(cell, W)
        r1, c1 = divmod(int(target), W)
        lat0, lon0 = terrain.pixel_to_latlon(r0 + 0.5, c0 + 0.5, dem_result)
        lat1, lon1 = terrain.pixel_to_latlon(r1 + 0.5, c1 + 0.5, dem_result)
        segments_by_order.setdefault(cell_order, []).append([[lon0, lat0], [lon1, lat1]])

    return [
        {
            "type": "Feature",
            "geometry": {"type": "MultiLineString", "coordinates": segments_by_order[o]},
            "properties": {"stream_order": o},
        }
        for o in sorted(segments_by_order)
    ]


# ---------------------------------------------------------------------------
# 8. Boundary tracing -> GeoJSON
# ---------------------------------------------------------------------------

def _trace_rings(mask):
    """
    Trace the boundary of True regions in a boolean mask as one or more
    closed rectilinear rings, in (row, col) pixel-corner coordinates.

    Uses raster boundary/edge tracing -- the same principle GDAL's
    Polygonize / rasterio.features.shapes use: every unit edge between a
    True pixel and a False (or out-of-bounds) neighbor becomes a directed
    boundary segment, and chaining those segments end-to-end yields closed
    rings with no ambiguity, since the input is strictly binary.
    """
    H, W = mask.shape
    edges_from = {}

    def add_edge(a, b):
        edges_from.setdefault(a, []).append(b)

    rows, cols = np.nonzero(mask)
    for r, c in zip(rows.tolist(), cols.tolist()):
        if r == 0 or not mask[r - 1, c]:
            add_edge((r, c), (r, c + 1))            # top, going right
        if c == W - 1 or not mask[r, c + 1]:
            add_edge((r, c + 1), (r + 1, c + 1))     # right, going down
        if r == H - 1 or not mask[r + 1, c]:
            add_edge((r + 1, c + 1), (r + 1, c))     # bottom, going left
        if c == 0 or not mask[r, c - 1]:
            add_edge((r + 1, c), (r, c))             # left, going up

    rings = []
    while edges_from:
        start = next(iter(edges_from))
        ring = [start]
        current = start
        while True:
            targets = edges_from.get(current)
            if not targets:
                break
            nxt = targets.pop()
            if not targets:
                del edges_from[current]
            ring.append(nxt)
            current = nxt
            if current == start:
                break
        if len(ring) > 3:
            rings.append(ring[:-1])  # drop the duplicated closing point
    return rings


def _drop_collinear(ring):
    """Remove points that sit exactly on a straight run (cheap pre-simplify)."""
    n = len(ring)
    if n < 3:
        return ring
    result = []
    for i in range(n):
        pr = ring[i - 1]
        cur = ring[i]
        nxt = ring[(i + 1) % n]
        d1 = (cur[0] - pr[0], cur[1] - pr[1])
        d2 = (nxt[0] - cur[0], nxt[1] - cur[1])
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        dot = d1[0] * d2[0] + d1[1] * d2[1]
        if cross != 0 or dot < 0:
            result.append(cur)
    return result if len(result) >= 3 else ring


def _douglas_peucker(points, tolerance):
    """Iterative Douglas-Peucker simplification (explicit stack, no recursion limit risk)."""
    n = len(points)
    if n < 3 or tolerance <= 0:
        return points

    keep = bytearray(n)
    keep[0] = 1
    keep[-1] = 1
    stack = [(0, n - 1)]

    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        ax, ay = points[start]
        bx, by = points[end]
        dx, dy = bx - ax, by - ay
        denom = dx * dx + dy * dy

        max_d, idx = 0.0, -1
        for i in range(start + 1, end):
            x, y = points[i]
            if denom == 0:
                d = math.hypot(x - ax, y - ay)
            else:
                t = ((x - ax) * dx + (y - ay) * dy) / denom
                px, py = ax + t * dx, ay + t * dy
                d = math.hypot(x - px, y - py)
            if d > max_d:
                max_d, idx = d, i

        if max_d > tolerance:
            keep[idx] = 1
            stack.append((start, idx))
            stack.append((idx, end))

    return [pt for pt, k in zip(points, keep) if k]


def _ring_area(ring):
    """Signed shoelace area (row/col space)."""
    area = 0.0
    n = len(ring)
    for i in range(n):
        r1, c1 = ring[i]
        r2, c2 = ring[(i + 1) % n]
        area += c1 * r2 - c2 * r1
    return area / 2.0


def mask_to_geojson(mask, dem_result, simplify_tolerance=0.75, min_ring_points=4):
    """Convert a boolean watershed mask into a GeoJSON Polygon Feature (lon/lat)."""
    rings = _trace_rings(mask)
    if not rings:
        return None

    processed = []
    for ring in rings:
        ring = _drop_collinear(ring)
        ring = _douglas_peucker(ring, simplify_tolerance)
        if len(ring) < min_ring_points:
            continue
        area = _ring_area(ring)
        processed.append((abs(area), ring))

    if not processed:
        return None

    processed.sort(key=lambda t: t[0], reverse=True)
    exterior = processed[0][1]
    holes = [ring for (_, ring) in processed[1:]]

    def to_lonlat_ring(ring):
        coords = []
        for (r, c) in ring:
            lat, lon = terrain.pixel_to_latlon(r, c, dem_result)
            coords.append([lon, lat])
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        return coords

    coordinates = [to_lonlat_ring(exterior)] + [to_lonlat_ring(h) for h in holes]

    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": coordinates
        },
        "properties": {}
    }


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def delineate(dem_result, lat, lon, snap_radius=10, min_stream_drainage_km2=0.5):
    """
    Run the full fill -> flow direction -> resolve flats -> flow
    accumulation -> catchment pipeline for a clicked pour point.

    Returns a dict with: mask, pour_row, pour_col, touches_edge, area_km2,
    cell_count, geojson, stream_features, max_stream_order.
    """
    grid = dem_result['grid']
    H, W = grid.shape

    filled = fill_depressions(grid)
    direction = compute_flow_direction(filled)
    resolve_flats(filled, direction)

    downstream = compute_downstream_index(direction)
    acc = flow_accumulation(downstream)
    acc_grid = acc.reshape(H, W)

    row, col = terrain.latlon_to_pixel(lat, lon, dem_result)
    row = min(max(row, 0), H - 1)
    col = min(max(col, 0), W - 1)
    snap_row, snap_col = snap_to_stream(acc_grid, row, col, search_radius=snap_radius)

    pour_idx = snap_row * W + snap_col
    mask = delineate_catchment(downstream, pour_idx, (H, W))

    # Stream network, restricted to cells actually within this catchment
    # (the fetched DEM window can include unrelated neighboring drainages).
    is_stream = stream_mask_from_area(acc, dem_result['px_size_m'], min_stream_drainage_km2) & mask.ravel()
    stream_order = compute_stream_order(downstream, is_stream)
    stream_features = stream_network_geojson(downstream, stream_order, is_stream, dem_result)
    max_stream_order = int(stream_order.max()) if stream_features else 0

    return {
        'mask': mask,
        'pour_row': snap_row,
        'pour_col': snap_col,
        'touches_edge': mask_touches_edge(mask),
        'area_km2': approximate_area_km2(mask, dem_result['px_size_m']),
        'cell_count': int(mask.sum()),
        'geojson': mask_to_geojson(mask, dem_result),
        'stream_features': stream_features,
        'max_stream_order': max_stream_order,
    }
