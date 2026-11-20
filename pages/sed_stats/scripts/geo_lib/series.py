"""
Tables built from what the map fetches, in the layout the hydrology blocks read: a `sample`
column, a `series` column, a `date`, and then the measurements (the same layout as
`gibson_jack_hydro.csv`), so a fetched table goes straight into Time series or Hydrograph.
"""
from .gauges import CFS_TO_M3S
from .pipeline import held_points

COLUMNS = ("sample", "series", "date", "discharge_m3s", "precip_mm", "temperature_c")


def _key(label, hourly):
    """The time a value belongs to: its day, or its hour."""
    return str(label)[:13] if hourly else str(label)[:10]


def _label(key, hourly):
    return f"{key}:00" if hourly else key


def _hourly_means(dates, values):
    """{hour: mean} of readings that may come every 15 minutes."""
    buckets = {}
    for label, value in zip(dates, values):
        if value is not None:
            buckets.setdefault(_key(label, True), []).append(value)
    return {k: sum(v) / len(v) for k, v in buckets.items()}


def hydro_rows(sample, discharge=None, climate=None, hourly=False, series_name=None):
    """
    One row per time step with the discharge at a gauge and the climate over a watershed.

    Args:
        sample: what the first column says (the watershed or the gauge's name)
        discharge: {'dates', 'discharge_cfs', ...} from `gauges`, or None
        climate: {'dates', 'precipitation_mm', 'temperature_c'} from `climate`, or None
        hourly: the series are hourly, so values are matched by hour (15-minute gauge readings
            are averaged into the hour) and the date column carries the time
        series_name: the `series` column; defaults to what the table holds

    Returns:
        rows (dicts, in date order) with only the columns that have something in them
    """
    flow, rain, temp = {}, {}, {}
    if discharge:
        values = [None if v is None else v * CFS_TO_M3S for v in discharge["discharge_cfs"]]
        if hourly:
            flow = _hourly_means(discharge["dates"], values)
        else:
            flow = {_key(d, False): v for d, v in zip(discharge["dates"], values)}
    if climate:
        for label, precip, temperature in zip(climate["dates"], climate["precipitation_mm"],
                                              climate["temperature_c"]):
            rain[_key(label, hourly)] = precip
            temp[_key(label, hourly)] = temperature
    keys = sorted(set(flow) | set(rain) | set(temp))
    kind = "hourly" if hourly else "daily"
    name = series_name or " and ".join(
        part for part, present in (("discharge", flow), ("climate", rain)) if present) or "series"
    rows = []
    for key in keys:
        rows.append({"sample": sample, "series": f"{kind} {name}", "date": _label(key, hourly),
                     "discharge_m3s": _round(flow.get(key)), "precip_mm": _round(rain.get(key)),
                     "temperature_c": _round(temp.get(key))})
    for column in ("discharge_m3s", "precip_mm", "temperature_c"):
        if all(row[column] is None for row in rows):
            for row in rows:
                del row[column]
    return rows


def _round(value):
    return None if value is None else round(float(value), 6)


def extremes_rows(name, held):
    """The highest and lowest points of a watershed as table rows (latitude and longitude columns
    are named so a Sample locations block reads them), or [] if it holds none."""
    return [{"watershed": name, "point": label, "latitude": lat, "longitude": lon,
             "elevation_m": elevation}
            for label, lat, lon, elevation in held_points(held)]


def summary_row(name, result):
    """A one-row table describing a delineated watershed (see `MapsPanel` for the keys)."""
    row = {
        "watershed": name,
        "pour_lat": result.get("pour_lat"),
        "pour_lon": result.get("pour_lon"),
        "area_km2": result.get("area_km2"),
        "method": result.get("method", ""),
        "source": result.get("source", ""),
    }
    if result.get("resolution_m") is not None:
        row["resolution_m"] = result["resolution_m"]
    if result.get("mean_elevation_m") is not None:
        row["mean_elevation_m"] = result["mean_elevation_m"]
        row["min_elevation_m"] = result["min_elevation_m"]
        row["max_elevation_m"] = result["max_elevation_m"]
    return row
