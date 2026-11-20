"""
Streamflow from USGS gauges (NWIS Water Services). A hydrograph needs measured discharge, and
USGS gauges are the only source of it, so this is US-only and works where a gauge exists: "no
gauge found" is the honest answer elsewhere.

`find_gauges_in_watershed` lists every gauge in the watershed by navigating NLDI's upstream
tributaries ("UT") from the pour point's reach, which is exactly the contributing area, so no
point-in-polygon test is needed. `find_gauge_nearby`, a plain bounding-box site search, is the
fallback where the point cannot be snapped to the NHD network.
"""
import asyncio
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from . import geometry, net
from .net import RateLimitedError  # noqa: F401  (callers catch it from here)

NLDI_BASE = "https://api.water.usgs.gov/nldi"
NWIS_SITE_URL = "https://waterservices.usgs.gov/nwis/site/"
NWIS_DV_URL = "https://waterservices.usgs.gov/nwis/dv/"
NWIS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
KM_PER_DEG_LAT = 111.32
CFS_TO_M3S = 0.028316846592


def parse_entry(entry, bin_size):
    """
    One NWIS value entry as (label, float), or None if unreadable. Hourly values arrive in the
    gauge's local time and are put in UTC so they line up with Open-Meteo's UTC hours; daily
    values keep their calendar date.
    """
    try:
        value = float(entry["value"])
    except (KeyError, ValueError, TypeError):
        return None
    raw = entry.get("dateTime", "")
    if bin_size == "hourly":
        try:
            when = datetime.fromisoformat(raw)
            if when.tzinfo is not None:
                when = when.astimezone(timezone.utc)
            return when.strftime("%Y-%m-%dT%H:%M"), value
        except ValueError:
            return raw[:16], value
    return raw[:10], value


def parse_sites(features, lat, lon):
    """
    USGS gauges from NLDI "nwissite" features, nearest (lat, lon) first, as
    {'site_no', 'name', 'lat', 'lon'}. The list also holds state-agency stations, which NWIS
    cannot serve and which make it reject a whole comma-separated request, so they are dropped.
    """
    sites = []
    for feature in features or []:
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates") or [None, None]
        identifier = props.get("identifier", "") or ""
        if not identifier.startswith("USGS-"):
            continue
        site_no = identifier[len("USGS-"):]
        if site_no and coords[0] is not None and coords[1] is not None:
            sites.append({"site_no": site_no, "name": props.get("name"),
                          "lat": coords[1], "lon": coords[0]})
    sites.sort(key=lambda s: (s["lat"] - lat) ** 2 + (s["lon"] - lon) ** 2)
    return sites


def inside(sites, polygons, lat, lon, margin_deg=0.003):
    """
    The gauges that lie in the polygons, or within `margin_deg` (about 300 m) of the pour point —
    a gauge at the outlet can fall just outside an outline traced from cells.

    Needed when the watershed came from a DEM: the NHD reach nearest a pour point can be a
    different, larger river, and the whole of its upstream network is not this watershed.
    """
    return [s for s in sites
            if geometry.contains(polygons, s["lon"], s["lat"])
            or (abs(s["lat"] - lat) <= margin_deg and abs(s["lon"] - lon) <= margin_deg)]


async def find_gauges_in_watershed(lat, lon, comid=None):
    """
    Every USGS gauge upstream of (lat, lon), nearest first; empty outside the NHD network.
    Pass `comid` when it is already known.
    """
    if comid is None:
        from .basins import comid_at
        comid = await comid_at(lat, lon)
        if comid is None:
            return []
    data = await net.get_json(f"{NLDI_BASE}/linked-data/comid/{comid}/navigation/UT/nwissite?f=json")
    return parse_sites((data or {}).get("features"), lat, lon)


def parse_site_map(xml_text, lat, lon):
    """The gauge nearest (lat, lon) in an NWIS "mapper" answer, or None."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    sites = []
    for element in root.iter("site"):
        try:
            sites.append({"site_no": element.get("sno"), "name": element.get("sna"),
                          "lat": float(element.get("lat")), "lon": float(element.get("lng"))})
        except (TypeError, ValueError):
            continue
    return min(sites, key=lambda s: (s["lat"] - lat) ** 2 + (s["lon"] - lon) ** 2) if sites else None


async def find_gauge_nearby(lat, lon, search_km=25):
    """The closest USGS discharge gauge within `search_km`, or None."""
    dlat = search_km / KM_PER_DEG_LAT
    dlon = search_km / (KM_PER_DEG_LAT * max(0.01, math.cos(math.radians(lat))))
    box = f"{lon - dlon:.5f},{lat - dlat:.5f},{lon + dlon:.5f},{lat + dlat:.5f}"
    text = await net.get_text(f"{NWIS_SITE_URL}?format=mapper&bBox={box}"
                              f"&siteType=ST&hasDataTypeCd=dv&parameterCd=00060")
    return parse_site_map(text, lat, lon) if text else None


def parse_series(data, bin_size):
    """
    {'dates', 'discharge_cfs', 'site_name'} for the first series in an NWIS answer, or None when
    it has no readable values.
    """
    try:
        series = data["value"]["timeSeries"][0]
        name = series["sourceInfo"]["siteName"]
        entries = series["values"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return None
    parsed = [p for p in (parse_entry(e, bin_size) for e in entries) if p]
    if not parsed:
        return None
    return {"dates": [d for d, _ in parsed], "discharge_cfs": [v for _, v in parsed],
            "site_name": name}


async def fetch_discharge_series(site_no, start_date, end_date, bin_size="daily"):
    """
    Discharge (cfs, parameter 00060) at one gauge over [start_date, end_date]. Hourly uses the
    instantaneous-values service, which keeps only about four months; daily has the full history.
    """
    base = NWIS_IV_URL if bin_size == "hourly" else NWIS_DV_URL
    data = await net.get_json(f"{base}?format=json&sites={site_no}"
                              f"&startDT={start_date}&endDT={end_date}&parameterCd=00060")
    return parse_series(data, bin_size)


async def fetch_discharge_batch(site_nos, start_date, end_date, bin_size="daily"):
    """
    Discharge at many gauges in one go, keeping those with any data in range — {site_no:
    {'dates', 'discharge_cfs', 'site_name'}} — so "every gauge here" becomes "every gauge with
    data for these dates" without a round trip each.
    """
    if not site_nos:
        return {}
    base = NWIS_IV_URL if bin_size == "hourly" else NWIS_DV_URL
    chunks = [site_nos[i:i + 100] for i in range(0, len(site_nos), 100)]
    answers = await asyncio.gather(*(net.get_json(
        f"{base}?format=json&sites={','.join(chunk)}&startDT={start_date}&endDT={end_date}"
        f"&parameterCd=00060") for chunk in chunks))
    found = {}
    for data in answers:
        try:
            all_series = data["value"]["timeSeries"]
        except (KeyError, TypeError):
            continue
        for series in all_series:
            try:
                site_no = series["sourceInfo"]["siteCode"][0]["value"]
                name = series["sourceInfo"]["siteName"]
                entries = series["values"][0]["value"]
            except (KeyError, IndexError, TypeError):
                continue
            parsed = [p for p in (parse_entry(e, bin_size) for e in entries) if p]
            if parsed:
                found[site_no] = {"dates": [d for d, _ in parsed],
                                  "discharge_cfs": [v for _, v in parsed], "site_name": name}
    return found
