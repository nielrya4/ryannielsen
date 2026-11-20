"""
Pre-computed basins, for catchments too big to delineate from a DEM in the browser (the Columbia
is ~600,000 km²). Each returns a finished polygon: no DEM, no flow routing here.

  "nldi"         USGS Network Linked Data Index (NHDPlus), US only. A point is snapped to the
                 nearest NHD reach (its COMID), then that reach's whole upstream basin is fetched.
  "merit_global" mghydro.com's Global Watersheds API on MERIT-Hydro, global. A free,
                 donation-funded service: its responses ask for the credit "Global Watersheds,
                 https://mghydro.com", which the map shows, and it should be used sparingly.
"""
from . import geometry, net

NLDI_BASE = "https://api.water.usgs.gov/nldi"
MERIT_BASE = "https://mghydro.com/app/watershed_api"
MERIT_RIVERS_BASE = "https://mghydro.com/app/upstream_rivers_api"
NLDI_MAX_SEGMENTS = 6000
NLDI_NAVIGATION_DISTANCE_KM = 200

ATTRIBUTION = {
    "nldi": "USGS Network Linked Data Index (NHDPlus)",
    "merit_global": "Global Watersheds (mghydro.com), MERIT-Hydro",
}


def first_comid(position):
    """The COMID of the reach NLDI snapped a point to, from its `comid/position` answer."""
    features = (position or {}).get("features") or []
    if not features:
        return None
    return features[0].get("properties", {}).get("comid")


async def comid_at(lat, lon):
    """The NHD reach (COMID) nearest a point, or None outside NHDPlus coverage."""
    return first_comid(await net.get_json(
        f"{NLDI_BASE}/linked-data/comid/position?coords=POINT({lon}%20{lat})"))


async def fetch_basin_nldi(lat, lon):
    """
    The upstream basin of the NHD reach nearest (lat, lon).

    Returns:
        {'geojson', 'area_km2', 'comid', 'source', 'attribution'}, or None when the point cannot
        be snapped to the network (too far from a mapped stream, or outside the US)
    """
    comid = await comid_at(lat, lon)
    if comid is None:
        return None
    data = await net.get_json(f"{NLDI_BASE}/linked-data/comid/{comid}/basin")
    features = (data or {}).get("features") or []
    if not features:
        return None
    feature = features[0]
    return {"geojson": feature,
            "area_km2": geometry.area_km2(geometry.polygons_of(feature)),
            "comid": comid, "source": "nldi", "attribution": ATTRIBUTION["nldi"]}


def merit_area(feature):
    """The area a MERIT feature states (km², with thousands separators), else the polygon's."""
    raw = feature.get("properties", {}).get("area_km2")
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return geometry.area_km2(geometry.polygons_of(feature))


async def fetch_basin_merit(lat, lon):
    """The MERIT-Hydro watershed containing (lat, lon), or None where it has no coverage."""
    data = await net.get_json(f"{MERIT_BASE}?lat={lat}&lng={lon}&precision=high")
    features = (data or {}).get("features") or []
    if not features:
        return None
    feature = features[0]
    return {"geojson": feature, "area_km2": merit_area(feature), "comid": None,
            "source": "merit_global", "attribution": ATTRIBUTION["merit_global"]}


def nldi_streams(data):
    """
    The flowlines of an NLDI navigation answer as one feature, thinned to NLDI_MAX_SEGMENTS.
    NHD flowlines carry no stream order here, so there is no order filter.

    Returns:
        {'stream_features', 'has_order_filter', 'min_order_available', 'max_order_available',
         'truncated', 'source', 'attribution'}, or None when there are no lines
    """
    features = (data or {}).get("features") or []
    segments = [f["geometry"]["coordinates"] for f in features
                if f.get("geometry", {}).get("type") == "LineString"]
    if not segments:
        return None
    truncated = len(segments) > NLDI_MAX_SEGMENTS
    if truncated:
        segments = segments[::-(-len(segments) // NLDI_MAX_SEGMENTS)]
    return {"stream_features": [{"type": "Feature", "properties": {"stream_order": 1},
                                 "geometry": {"type": "MultiLineString", "coordinates": segments}}],
            "has_order_filter": False, "min_order_available": None, "max_order_available": None,
            "truncated": truncated, "source": "nldi", "attribution": ATTRIBUTION["nldi"]}


async def fetch_rivers_nldi(comid):
    """
    The upstream flowlines of a reach, out to NLDI_NAVIGATION_DISTANCE_KM. The distance is capped
    because the whole network of a Columbia-sized basin is a 139 MB answer that Pyodide cannot
    parse in any reasonable time; the caller says that distant tributaries may be missing.
    """
    data = await net.get_json(
        f"{NLDI_BASE}/linked-data/comid/{comid}/navigation/UT/flowlines"
        f"?distance={NLDI_NAVIGATION_DISTANCE_KM}&f=json")
    return nldi_streams(data)


def merit_streams(data):
    """The MERIT river lines grouped by Strahler order, one feature per order, or None."""
    by_order = {}
    for feature in (data or {}).get("features") or []:
        geom = feature.get("geometry", {})
        order = feature.get("properties", {}).get("sorder")
        if geom.get("type") == "LineString" and order is not None:
            by_order.setdefault(int(order), []).append(geom["coordinates"])
    if not by_order:
        return None
    orders = sorted(by_order)
    return {"stream_features": [
                {"type": "Feature", "properties": {"stream_order": o},
                 "geometry": {"type": "MultiLineString", "coordinates": by_order[o]}}
                for o in orders],
            "has_order_filter": True, "min_order_available": orders[0],
            "max_order_available": orders[-1], "truncated": False,
            "source": "merit_global", "attribution": ATTRIBUTION["merit_global"]}


async def fetch_rivers_merit(lat, lon):
    """
    The upstream rivers by Strahler order. The service prunes to the largest rivers for a big
    basin, so the smallest order returned may be well above 1.
    """
    return merit_streams(await net.get_json(f"{MERIT_RIVERS_BASE}?lat={lat}&lng={lon}&precision=high"))
