"""
Fetching a DEM in the browser: Terrarium tiles drawn through a canvas to read their pixels, or a
3DEP GeoTIFF read with geotiff.js. Everything that is arithmetic is in `terrain`.
"""
import asyncio

import numpy as np

from . import net, terrain

TILE_SECONDS = 30          # one elevation tile
DEP_SECONDS = 240          # a 3DEP raster: the service renders it on request and can be slow


async def _tile_elevation(x, y, zoom):
    """One Terrarium tile as a (256, 256) elevation array, or None if it is missing."""
    import js
    if not terrain.tile_exists(zoom, x, y):
        return None
    try:
        response = await net.js_fetch(terrain.tile_url(zoom, x, y), TILE_SECONDS)
        if not response.ok:
            return None
        bitmap = await js.createImageBitmap(await response.blob())
    except Exception:
        return None
    size = terrain.TILE_SIZE
    canvas = js.document.createElement("canvas")
    canvas.width = canvas.height = size
    context = canvas.getContext("2d")
    context.drawImage(bitmap, 0, 0)
    raw = bytes(context.getImageData(0, 0, size, size).data.to_py())
    return terrain.decode_terrarium(np.frombuffer(raw, dtype=np.uint8).reshape(size, size, 4))


async def _terrarium(lat, lon, radius_km, target_resolution_m, max_px, progress):
    zoom, clamped = terrain.pick_zoom(radius_km, lat, target_resolution_m, max_px)
    west_m, south_m, east_m, north_m = terrain.compute_bbox_mercator(lat, lon, radius_km)
    west, north = terrain.mercator_m_to_lonlat(west_m, north_m)
    east, south = terrain.mercator_m_to_lonlat(east_m, south_m)
    x0, y0, x1, y1 = terrain.tile_range(west, south, east, north, zoom)
    total = (x1 - x0 + 1) * (y1 - y0 + 1)
    done = 0

    async def one(row, col, x, y):
        nonlocal done
        elevation = await _tile_elevation(x, y, zoom)
        done += 1
        if progress:
            progress(done, total)
        return (row, col), elevation

    found = await asyncio.gather(*[
        one(row, col, x, y)
        for row, y in enumerate(range(y0, y1 + 1))
        for col, x in enumerate(range(x0, x1 + 1))])
    return terrain.terrarium_dem(dict(found), x0, y0, x1, y1, zoom, lat, clamped)


async def _3dep(lat, lon, radius_km, target_resolution_m, max_px, progress):
    import js
    if not hasattr(js, "GeoTIFF"):
        raise RuntimeError("GeoTIFF.js is not loaded yet — try again in a moment")
    bbox = terrain.compute_bbox_mercator(lat, lon, radius_km)
    size, clamped = terrain.size_3dep(radius_km, target_resolution_m, max_px)
    if progress:
        progress(0, 1)
    try:
        response = await net.js_fetch(terrain.url_3dep(bbox, size), DEP_SECONDS)
    except Exception as error:
        raise RuntimeError(f"USGS 3DEP did not answer within {DEP_SECONDS // 60} minutes "
                           f"({error}). Try again, or use Terrarium.") from error
    if not response.ok:
        raise RuntimeError(f"USGS 3DEP request failed: HTTP {response.status}")
    buffer = await response.arrayBuffer()
    try:
        tiff = await js.GeoTIFF.fromArrayBuffer(buffer)
        image = await tiff.getImage()
        rasters = await image.readRasters()
        grid = np.frombuffer(bytes(rasters[0].to_py()), dtype=np.float32).reshape(size, size).copy()
    except Exception:
        # Outside 3DEP's coverage the service sends a degenerate file that geotiff.js cannot
        # read; 0.0 is already "no data", so an empty grid gives the right warning downstream.
        grid = np.zeros((size, size), dtype=np.float32)
    if progress:
        progress(1, 1)
    return terrain.bbox_dem(grid, bbox, lat, "usgs_3dep", clamped)


async def fetch_dem(source, lat, lon, radius_km, target_resolution_m=30.0, max_px=3000,
                    progress=None):
    """
    A DEM centred on (lat, lon), as a `terrain` dem_result.

    Args:
        source: "terrarium" or "usgs_3dep"
        target_resolution_m: the ground resolution wanted, m per pixel
        max_px: a hard cap on the grid's width, so a fine request over a wide area degrades
            instead of fetching without bound
        progress: `(done, total)`, called as tiles arrive
    """
    fetch = _3dep if source == "usgs_3dep" else _terrarium
    return await fetch(lat, lon, radius_km, target_resolution_m, max_px, progress)
