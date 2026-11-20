"""
DEM geometry: Web Mercator and tile arithmetic, decoding elevation tiles, and the `dem_result`
every later step works from. Nothing here touches the browser, so all of it is testable; the
fetching is in `dem.py`.

Two DEM sources feed it (see `dem.py`):

  "terrarium"  Mapzen/Tilezen Terrarium tiles on AWS open data; global, SRTM/GMTED-derived
               (~30–90 m). Each pixel encodes elevation (m) as R*256 + G + B/256 - 32768.
  "usgs_3dep"  USGS 3D Elevation Program mosaic as a GeoTIFF for any bbox; US only, down to 1 m,
               0.0 where there is no coverage.

Both return the same `dem_result` dict, keyed on a Web Mercator geotransform
(`mercator_bounds`), so the watershed pipeline and the map need not know which one produced it:

    grid             2-D float32 array of elevations, row 0 the north edge
    bounds           (south, west, north, east) in degrees
    mercator_bounds  (west_m, south_m, east_m, north_m) in EPSG:3857
    zoom             Terrarium zoom used, or None for 3DEP
    zoom_clamped     True if the resolution was reduced to fit `max_px`
    px_size_m        approximate ground size of a pixel, metres
    nodata_fraction  share of cells with no real data (0-1)
    source           the source actually used
"""
import math

import numpy as np

TILE_SIZE = 256
TILE_URL_TEMPLATE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
MAX_ZOOM = 14
KM_PER_DEG_LAT = 111.32
EARTH_RADIUS_M = 6378137.0          # the sphere EPSG:3857 uses

USGS_3DEP_URL = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
USGS_3DEP_MAX_PX = 8000

SOURCES = {
    "terrarium": "Terrarium (global, ~30 m)",
    "usgs_3dep": "USGS 3DEP (US only, down to 1 m)",
}


# ----------------------------------------------------------------- projection

def lonlat_to_mercator_m(lon, lat):
    """lon/lat (degrees) to Web Mercator (EPSG:3857) metres."""
    x_m = math.radians(lon) * EARTH_RADIUS_M
    y_m = EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x_m, y_m


def mercator_m_to_lonlat(x_m, y_m):
    """Web Mercator metres to lon/lat (degrees)."""
    lon = math.degrees(x_m / EARTH_RADIUS_M)
    lat = math.degrees(2 * math.atan(math.exp(y_m / EARTH_RADIUS_M)) - math.pi / 2)
    return lon, lat


def compute_bbox_mercator(lat, lon, radius_km):
    """(west_m, south_m, east_m, north_m) of a square around a point."""
    cx, cy = lonlat_to_mercator_m(lon, lat)
    r = radius_km * 1000.0
    return cx - r, cy - r, cx + r, cy + r


# ---------------------------------------------------------------------- tiles

def lonlat_to_tile(lon, lat, zoom):
    """Fractional XYZ tile coordinates of a lon/lat."""
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def tile_to_lonlat(x, y, zoom):
    """The lon/lat of a (possibly fractional) tile corner."""
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def meters_per_pixel(zoom, lat):
    """Ground resolution (m/px) of a Web Mercator zoom level at a latitude."""
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** zoom)


def zoom_for_resolution(target_resolution_m, lat):
    """The Terrarium zoom whose ground resolution is closest to the target."""
    return min(range(4, MAX_ZOOM + 1),
               key=lambda z: abs(meters_per_pixel(z, lat) - target_resolution_m))


def grid_px_across(radius_km, zoom, lat):
    """
    The fetched grid's width in pixels for a radius, zoom and latitude: the span over the true
    Mercator ground resolution (a flat degrees-to-km estimate badly undercounts away from the
    equator), plus two tiles for the rounding out to whole tiles.
    """
    return radius_km * 2000.0 / meters_per_pixel(zoom, lat) + 2 * TILE_SIZE


def pick_zoom(radius_km, lat, target_resolution_m, max_px=1400):
    """
    The Terrarium zoom to fetch at: the requested resolution unless the grid would pass
    `max_px` across, then the finest zoom that fits — so a fine request over a big radius cannot
    hang the browser.

    Returns:
        (zoom, was_clamped)
    """
    desired = zoom_for_resolution(target_resolution_m, lat)
    if grid_px_across(radius_km, desired, lat) <= max_px:
        return desired, False
    for zoom in range(desired - 1, 3, -1):
        if grid_px_across(radius_km, zoom, lat) <= max_px:
            return zoom, True
    return 4, True


def tile_range(west, south, east, north, zoom):
    """Inclusive (x0, y0, x1, y1) tile range covering a lon/lat box."""
    x0, y0 = lonlat_to_tile(west, north, zoom)
    x1, y1 = lonlat_to_tile(east, south, zoom)
    return int(math.floor(x0)), int(math.floor(y0)), int(math.floor(x1)), int(math.floor(y1))


def tile_url(zoom, x, y):
    return TILE_URL_TEMPLATE.format(z=zoom, x=x, y=y)


def tile_exists(zoom, x, y):
    n = 2 ** zoom
    return 0 <= x < n and 0 <= y < n


# ------------------------------------------------------------------- decoding

def decode_terrarium(rgba):
    """
    Elevation in metres from a Terrarium tile's pixels.

    Args:
        rgba: array (256, 256, 3 or 4) of 0-255 values

    Returns:
        float32 array (256, 256)
    """
    arr = np.asarray(rgba, dtype=np.float32).reshape(TILE_SIZE, TILE_SIZE, -1)
    return (arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0) - 32768.0


def _pixel_size_m(west, east, width_px, lat):
    span_km = (east - west) * KM_PER_DEG_LAT * math.cos(math.radians(lat))
    return span_km * 1000.0 / width_px


def terrarium_dem(tiles, x0, y0, x1, y1, zoom, lat, zoom_clamped=False):
    """
    Stitch decoded tiles into a `dem_result`.

    Args:
        tiles: {(row, col): elevation array or None} for the tile at row `row`, column `col`
            of the range; a None is a tile that could not be fetched
        x0, y0, x1, y1: the tile range, inclusive
        lat: the centre latitude, for the pixel size
    """
    rows, cols = y1 - y0 + 1, x1 - x0 + 1
    grid = np.zeros((rows * TILE_SIZE, cols * TILE_SIZE), dtype=np.float32)
    missing = 0
    for (row, col), elevation in tiles.items():
        if elevation is None:
            missing += 1
            continue
        grid[row * TILE_SIZE:(row + 1) * TILE_SIZE, col * TILE_SIZE:(col + 1) * TILE_SIZE] = elevation
    west, north = tile_to_lonlat(x0, y0, zoom)
    east, south = tile_to_lonlat(x1 + 1, y1 + 1, zoom)
    west_m, north_m = lonlat_to_mercator_m(west, north)
    east_m, south_m = lonlat_to_mercator_m(east, south)
    total = rows * cols
    return {
        "grid": grid,
        "bounds": (south, west, north, east),
        "mercator_bounds": (west_m, south_m, east_m, north_m),
        "zoom": zoom,
        "zoom_clamped": zoom_clamped,
        "px_size_m": _pixel_size_m(west, east, grid.shape[1], lat),
        "nodata_fraction": missing / total if total else 0.0,
        "source": "terrarium",
    }


def bbox_dem(grid, mercator_bounds, lat, source, zoom_clamped=False):
    """A `dem_result` for a grid fetched for an exact Mercator box (3DEP)."""
    west_m, south_m, east_m, north_m = mercator_bounds
    west, north = mercator_m_to_lonlat(west_m, north_m)
    east, south = mercator_m_to_lonlat(east_m, south_m)
    return {
        "grid": grid,
        "bounds": (south, west, north, east),
        "mercator_bounds": tuple(mercator_bounds),
        "zoom": None,
        "zoom_clamped": zoom_clamped,
        "px_size_m": _pixel_size_m(west, east, grid.shape[1], lat),
        # The service returns 0.0 outside its coverage, and a true 0 m reading is effectively
        # never real here, so 0 is taken as missing (as a missing Terrarium tile is).
        "nodata_fraction": float((grid == 0.0).mean()),
        "source": source,
    }


def size_3dep(radius_km, target_resolution_m, max_px):
    """(size in pixels, was_clamped, mercator bbox) of a 3DEP request around a point."""
    # The box is built by the caller from the point; only the size depends on the settings.
    span_m = radius_km * 2000.0
    ideal = span_m / target_resolution_m
    size = int(max(16, min(max_px, USGS_3DEP_MAX_PX, ideal)))
    return size, ideal > size + 0.5


def url_3dep(bbox_m, size_px):
    west, south, east, north = bbox_m
    return (f"{USGS_3DEP_URL}/exportImage"
            f"?bbox={west},{south},{east},{north}&bboxSR=3857&imageSR=3857"
            f"&size={size_px},{size_px}&format=tiff&pixelType=F32"
            f"&interpolation=RSP_BilinearInterpolation&noData=0&f=image")


# ------------------------------------------------------- pixels and positions

def latlon_to_pixel(lat, lon, dem_result):
    """(row, col) of a lat/lon in a DEM grid, by its Mercator geotransform."""
    west_m, south_m, east_m, north_m = dem_result["mercator_bounds"]
    h, w = dem_result["grid"].shape
    x_m, y_m = lonlat_to_mercator_m(lon, lat)
    col = (x_m - west_m) / (east_m - west_m) * w
    row = (north_m - y_m) / (north_m - south_m) * h
    # floor, not round: pixel i covers [i, i+1) in corner space.
    return int(math.floor(row)), int(math.floor(col))


def pixel_to_latlon(row, col, dem_result):
    """The lat/lon of a (row, col) pixel position in a DEM grid."""
    west_m, south_m, east_m, north_m = dem_result["mercator_bounds"]
    h, w = dem_result["grid"].shape
    x_m = west_m + (col / w) * (east_m - west_m)
    y_m = north_m - (row / h) * (north_m - south_m)
    lon, lat = mercator_m_to_lonlat(x_m, y_m)
    return lat, lon
