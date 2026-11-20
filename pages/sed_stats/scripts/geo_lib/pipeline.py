"""
Delineating from a DEM, and turning a result into what the workflow stores.

The loop and the stored form are here, away from the page, so they are tested: the loop is given
the function that fetches a DEM, and the page gives it the real one.
"""
from . import geometry, render, terrain, watershed

BASE_RADIUS_KM = 5.0
RADIUS_MULTIPLIER = 2.0
MAX_ATTEMPTS = 6
STORED_POINTS = 3000          # a stored outline is thinned to about this many vertices


async def delineate_expanding(fetch, source, lat, lon, resolution_m, report=None, pause=None,
                              base_radius_km=BASE_RADIUS_KM, multiplier=RADIUS_MULTIPLIER,
                              max_attempts=MAX_ATTEMPTS, snap_radius=10, min_stream_km2=0.5):
    """
    Delineate the watershed of a pour point, widening the DEM until the catchment no longer
    reaches its edge (a catchment cut off by the window is not the whole watershed).

    Args:
        fetch: `async (source, lat, lon, radius_km, target_resolution_m, *, progress) -> dem_result`
        report: `(text)`, called with what is happening, for the busy curtain
        pause: `async ()`, awaited after a message and before the long computation so the page
            can paint it
        snap_radius: how far (cells) the pour point may move onto a channel
        min_stream_km2: the drainage area that makes a channel

    Returns:
        (dem, result, radius_km); `result["touches_edge"]` is still True if the last, widest
        attempt did not contain the watershed
    """
    say = report or (lambda text: None)
    radius = base_radius_km
    dem = result = None
    for attempt in range(max_attempts):
        say(f"Fetching elevation data, radius {radius:g} km"
            + (f" (attempt {attempt + 1} of {max_attempts})" if attempt else ""))
        dem = await fetch(source, lat, lon, radius, resolution_m,
                          progress=lambda done, total: say(f"Fetching elevation data: {done}/{total} tiles")
                          if total and total > 1 else None)
        height, width = dem["grid"].shape
        say(f"Delineating on a {width}×{height} grid (~{dem['px_size_m']:.0f} m per cell)")
        if pause:
            await pause()
        result = watershed.delineate(dem, lat, lon, snap_radius=snap_radius,
                                     min_stream_drainage_km2=min_stream_km2)
        if not result["touches_edge"] or attempt == max_attempts - 1:
            break
        radius *= multiplier
        say("The watershed runs past the fetched area; widening it")
    return dem, result, radius


def stored_watershed(name, dem, result, source_label, method="dem"):
    """
    What a Watershed block holds for a DEM delineation: the pour point as snapped, the area, the
    elevation statistics and the outline thinned for storage.
    """
    pour_lat, pour_lon = terrain.pixel_to_latlon(result["pour_row"] + 0.5,
                                                 result["pour_col"] + 0.5, dem)
    polygons = geometry.simplify(geometry.round_polygons(geometry.polygons_of(result["geojson"])),
                                 STORED_POINTS)
    held = {"name": name, "pour_lat": round(pour_lat, 6), "pour_lon": round(pour_lon, 6),
            "area_km2": round(float(result["area_km2"]), 4), "method": method,
            "source": source_label, "resolution_m": round(float(dem["px_size_m"]), 1),
            "polygons": polygons}
    stats = render.elevation_stats(dem["grid"], result["mask"])
    if stats:
        held["mean_elevation_m"], held["min_elevation_m"], held["max_elevation_m"] = (
            round(v, 1) for v in stats)
    extremes = render.elevation_extremes(dem["grid"], result["mask"])
    if extremes:
        for key, (row, col, elevation) in zip(("high_point", "low_point"), extremes):
            lat, lon = terrain.pixel_to_latlon(row + 0.5, col + 0.5, dem)
            held[key] = {"lat": round(lat, 6), "lon": round(lon, 6),
                         "elevation_m": round(elevation, 1)}
    return held


def stored_basin(name, basin, lat, lon, source_label):
    """What a Watershed block holds for a precomputed NLDI or MERIT basin."""
    polygons = geometry.simplify(geometry.round_polygons(geometry.polygons_of(basin["geojson"])),
                                 STORED_POINTS)
    return {"name": name, "pour_lat": round(lat, 6), "pour_lon": round(lon, 6),
            "area_km2": round(float(basin["area_km2"]), 4), "method": basin["source"],
            "source": source_label, "polygons": polygons, "comid": basin.get("comid")}


POINT_LABELS = (("high_point", "Highest point"), ("low_point", "Lowest point"))


def held_points(held):
    """[(label, lat, lon, elevation_m)] for the highest and lowest points a watershed holds. Empty for
    a ready-made basin, which has no elevation grid, and for one stored before these were kept."""
    return [(label, held[key]["lat"], held[key]["lon"], held[key]["elevation_m"])
            for key, label in POINT_LABELS if held.get(key)]


def held_points_geojson(held):
    """The highest and lowest points as a GeoJSON FeatureCollection of Points, for download."""
    name = held.get("name", "")
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {"watershed": name, "point": label, "elevation_m": elevation},
         "geometry": {"type": "Point", "coordinates": [lon, lat]}}
        for label, lat, lon, elevation in held_points(held)]}


def held_geojson(held):
    """The GeoJSON feature of a stored watershed, for the map and for download."""
    properties = {k: held[k] for k in ("name", "pour_lat", "pour_lon", "area_km2", "source")
                  if k in held}
    return geometry.to_geojson(held["polygons"], properties)
