"""
Outlines on the globe: GeoJSON polygons as rings of (lon, lat), whether a point lies inside one,
how big one is, and a handful of points spread over one.

A *polygon* here is a list of rings, the first the outer boundary and any others holes; a
watershed may have several (a MultiPolygon), so the functions work on a list of them.
"""
import math

EARTH_RADIUS_KM = 6371.0088


def polygons_of(geojson):
    """
    The polygons in a GeoJSON Feature, FeatureCollection or geometry, as
    [[ring, ring, ...], ...] with each ring a list of (lon, lat).
    """
    if not geojson:
        return []
    kind = geojson.get("type")
    if kind == "FeatureCollection":
        return [p for f in geojson.get("features", []) for p in polygons_of(f)]
    if kind == "Feature":
        return polygons_of(geojson.get("geometry"))
    coordinates = geojson.get("coordinates")
    if kind == "Polygon":
        return [[[(float(x), float(y)) for x, y, *_ in ring] for ring in coordinates]]
    if kind == "MultiPolygon":
        return [[[(float(x), float(y)) for x, y, *_ in ring] for ring in poly]
                for poly in coordinates]
    return []


def _in_ring(lon, lat, ring):
    """Ray casting: is the point inside this one ring?"""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def contains(polygons, lon, lat):
    """Is (lon, lat) inside any polygon — in its outer ring and not in one of its holes?"""
    for rings in polygons:
        if rings and _in_ring(lon, lat, rings[0]) \
                and not any(_in_ring(lon, lat, hole) for hole in rings[1:]):
            return True
    return False


def bounds(polygons):
    """(south, west, north, east) of the polygons, or None when there are none."""
    points = [p for rings in polygons for ring in rings[:1] for p in ring]
    if not points:
        return None
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    return min(lats), min(lons), max(lats), max(lons)


def _ring_area_km2(ring):
    """Signed spherical-excess (trapezoid) area of a ring in km²; the sign follows the winding."""
    n = len(ring)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        lon1, lat1 = ring[i]
        lon2, lat2 = ring[(i + 1) % n]
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
    return total * EARTH_RADIUS_KM ** 2 / 2.0


def area_km2(polygons):
    """Area in km² on the sphere — a flat lat/lon estimate is wrong at basin scale."""
    total = 0.0
    for rings in polygons:
        if not rings:
            continue
        area = abs(_ring_area_km2(rings[0])) - sum(abs(_ring_area_km2(h)) for h in rings[1:])
        total += max(area, 0.0)
    return total


def centroid(polygons):
    """The middle of the polygons' bounding box as (lat, lon), or None."""
    box = bounds(polygons)
    if box is None:
        return None
    south, west, north, east = box
    return (south + north) / 2, (west + east) / 2


def grid_inside(polygons, n=8):
    """
    Up to n × n points on a regular grid over the polygons' box that fall inside them, as
    (lat, lon) — the places a watershed-wide average of a weather variable is sampled. A sliver
    that no grid point hits gets its box centre, so there is always at least one point.
    """
    box = bounds(polygons)
    if box is None:
        return []
    south, west, north, east = box
    found = []
    for i in range(n):
        lat = south + (north - south) * (i + 0.5) / n
        for j in range(n):
            lon = west + (east - west) * (j + 0.5) / n
            if contains(polygons, lon, lat):
                found.append((lat, lon))
    if not found:
        found.append(((south + north) / 2, (west + east) / 2))
    return found


def outline_shapes(polygons, name):
    """
    The outer rings as `Polygons` shapes — [(name, [(x, y), ...])], x being longitude and y
    latitude; a watershed with several parts gets "name (2)" and so on.
    """
    shapes = []
    for index, rings in enumerate(polygons):
        if rings:
            label = name if index == 0 else f"{name} ({index + 1})"
            shapes.append((label, list(rings[0])))
    return shapes


def to_geojson(polygons, properties=None):
    """A GeoJSON Feature for the polygons (a Polygon, or a MultiPolygon when there are several)."""
    coords = [[[list(p) for p in ring] for ring in rings] for rings in polygons]
    geometry = ({"type": "Polygon", "coordinates": coords[0]} if len(coords) == 1
                else {"type": "MultiPolygon", "coordinates": coords})
    return {"type": "Feature", "geometry": geometry, "properties": dict(properties or {})}


def round_polygons(polygons, places=5):
    """The polygons with coordinates rounded (1 m is about 5 decimal places), for storing."""
    return [[[(round(x, places), round(y, places)) for x, y in ring] for ring in rings]
            for rings in polygons]


def _simplify_ring(ring, tolerance):
    """Douglas–Peucker on a closed ring (without recursion — a basin outline can have 10⁵ points)."""
    if len(ring) < 5:
        return list(ring)
    open_ring = ring[:-1] if ring[0] == ring[-1] else list(ring)
    n = len(open_ring)
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = open_ring[first], open_ring[last]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        far, far_at = -1.0, -1
        for i in range(first + 1, last):
            x, y = open_ring[i]
            distance = (math.hypot(x - x1, y - y1) if length == 0
                        else abs(dy * (x - x1) - dx * (y - y1)) / length)
            if distance > far:
                far, far_at = distance, i
        if far > tolerance:
            keep[far_at] = True
            stack.append((first, far_at))
            stack.append((far_at, last))
    kept = [p for p, k in zip(open_ring, keep) if k]
    if len(kept) < 3:
        return list(ring)
    return kept + [kept[0]]


def point_count(polygons):
    return sum(len(ring) for rings in polygons for ring in rings)


def simplify(polygons, max_points=3000):
    """
    The polygons with vertices thinned until there are at most `max_points` (the tolerance is
    doubled from about a metre until they fit), so a stored watershed stays small. A polygon
    already short enough is returned as it is.
    """
    if point_count(polygons) <= max_points:
        return polygons
    tolerance = 1e-5
    thinned = polygons
    while point_count(thinned) > max_points and tolerance < 10:
        thinned = [[_simplify_ring(ring, tolerance) for ring in rings] for rings in polygons]
        tolerance *= 2
    return thinned
