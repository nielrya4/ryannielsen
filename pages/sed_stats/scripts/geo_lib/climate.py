"""
Weather and climate from Open-Meteo (free, keyless, CORS-open): current conditions at a point,
the average of a variable over a date range at a grid of points (the map's climate raster), and
daily precipitation and temperature averaged over a watershed (the hyetograph's input).
"""
from . import net
from .net import RateLimitedError  # noqa: F401

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# variable -> (Open-Meteo daily parameter, unit, how a range collapses to one value)
VARIABLES = {
    "precipitation": ("precipitation_sum", "mm total", "sum"),
    "temperature": ("temperature_2m_mean", "°C avg", "mean"),
    "wind": ("wind_speed_10m_max", "km/h avg daily max", "mean"),
}
VARIABLE_LABELS = {"precipitation": "Precipitation", "temperature": "Temperature",
                   "wind": "Wind"}

# WMO weather codes, which Open-Meteo uses.
_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def describe_weather_code(code):
    return _CODES.get(int(code), f"Unknown conditions (code {code})")


def parse_current(data):
    """Current conditions from a forecast answer, or None if it has an unexpected shape."""
    current = (data or {}).get("current")
    if not current:
        return None
    try:
        return {"temperature_c": current["temperature_2m"],
                "precipitation_mm": current["precipitation"],
                "wind_speed_kmh": current["wind_speed_10m"],
                "relative_humidity_pct": current["relative_humidity_2m"],
                "description": describe_weather_code(current["weather_code"]),
                "attribution": "Open-Meteo (open-meteo.com)"}
    except KeyError:
        return None


async def fetch_current_weather(lat, lon):
    return parse_current(await net.get_json(
        f"{FORECAST_URL}?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,precipitation,weather_code,wind_speed_10m,relative_humidity_2m"
        f"&timezone=auto"))


def _coordinates(points):
    return (",".join(f"{lat:.5f}" for lat, _ in points),
            ",".join(f"{lon:.5f}" for _, lon in points))


def _entries(data):
    """One answer object per requested point (a single point comes back as a bare object)."""
    return data if isinstance(data, list) else [data]


def collapse(values, how):
    """The sum or mean of the numbers among `values` (None where there are none)."""
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return sum(clean) if how == "sum" else sum(clean) / len(clean)


def parse_grid(data, variable):
    """{'values': [one per point, None where missing], 'unit'} from an archive answer."""
    param, unit, how = VARIABLES[variable]
    values = [collapse(((entry or {}).get("daily") or {}).get(param) or [], how)
              for entry in _entries(data)]
    return {"values": values, "unit": unit}


async def fetch_historical_grid(points, start_date, end_date, variable="precipitation"):
    """
    `variable` averaged (or summed) over the dates at each of `points` — (lat, lon) pairs — in
    one request, or None if it failed.
    """
    if variable not in VARIABLES:
        variable = "precipitation"
    lats, lons = _coordinates(points)
    data = await net.get_json(
        f"{ARCHIVE_URL}?latitude={lats}&longitude={lons}&start_date={start_date}"
        f"&end_date={end_date}&daily={VARIABLES[variable][0]}&timezone=UTC")
    return parse_grid(data, variable) if data else None


def average_series(data, params, step="daily"):
    """
    Each parameter in `params` averaged across the points of an archive answer, per time step.

    Returns:
        {'dates': [...], param: [...]}, or None when there is no series
    """
    dates, per_point = None, {p: [] for p in params}
    for entry in _entries(data):
        block = (entry or {}).get(step) or {}
        if dates is None:
            dates = block.get("time")
        for param in params:
            if block.get(param):
                per_point[param].append(block[param])
    if not dates or not any(per_point.values()):
        return None
    out = {"dates": list(dates)}
    for param, series in per_point.items():
        out[param] = [collapse([s[i] for s in series if i < len(s)], "mean")
                      for i in range(len(dates))]
    return out


async def fetch_watershed_series(points, start_date, end_date, hourly=False):
    """
    Precipitation (mm) and temperature (°C) averaged over `points` — a grid inside the
    watershed — one value per day, or per hour with `hourly`. Hourly is Open-Meteo's native
    series; daily precipitation is its daily total.

    Returns:
        {'dates', 'precipitation_mm', 'temperature_c'}, or None
    """
    step = "hourly" if hourly else "daily"
    params = (["precipitation", "temperature_2m"] if hourly
              else ["precipitation_sum", "temperature_2m_mean"])
    lats, lons = _coordinates(points)
    data = await net.get_json(
        f"{ARCHIVE_URL}?latitude={lats}&longitude={lons}&start_date={start_date}"
        f"&end_date={end_date}&{step}={','.join(params)}&timezone=UTC")
    averaged = average_series(data, params, step) if data else None
    if averaged is None:
        return None
    return {"dates": averaged["dates"], "precipitation_mm": averaged[params[0]],
            "temperature_c": averaged[params[1]]}
