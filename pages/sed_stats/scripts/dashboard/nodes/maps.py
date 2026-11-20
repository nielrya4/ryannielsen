"""
Blocks that carry geography through the workflow.

    Watershed              (a source)           a watershed delineated on the Maps tab: its outline,
                                                a one-row summary table, and its highest and
                                                lowest points
    Table from the map     (a source)           rows the map fetched — gauge discharge, watershed
                                                precipitation and temperature — to graph or analyse
    Sample locations       Table -> Points      samples placed by their latitude and longitude
    Samples in watershed   Table, Polygon -> Table   which samples lie inside a watershed

The first two hold what the map made as an option, since fetching needs the network and a block's
computation does not; they are added from the Maps tab, and "Edit…" only renames them. Draw the
outline over the sample locations with a Scatterplot to see the two together.
"""
from workflow_lib import NodeProblem, Output, POINTS, POLYGON, Port, TABLE
from workflow_lib.types import Points, Polygons

from geo_lib import geometry, pipeline, series

from ..dataset import sample_names
from ..table_ops import number_of
from ..tables import result_table
from ..thumbnails import table_cells
from .base import DATA_PAGE, DIMENSION, Field, Node, OPTIONS_PAGE, SELECT, StepOutput, table_of

from antioch.elements import Div, P

NOTE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}

WATERSHED_KEY = "watershed"      # the option that holds a delineated watershed
ROWS_KEY = "rows"                # the option that holds a fetched table


class MapNode(Node):
    """A block of the Map category. `keep` names options a dialog does not edit and so must not
    drop; `listed` False hides it from the Add menu, because it can only be made on the map."""

    def __init__(self, *args, keep=(), listed=True, subtitle=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.keep = tuple(keep)
        self.listed = listed
        self._subtitle = subtitle

    def describe(self, opts):
        text = self._subtitle(opts) if self._subtitle else ""
        return text or super().describe(opts)


def _note(text):
    return P(text, style=NOTE)


# ------------------------------------------------------------------- Watershed

def watershed_polygons(opts):
    """The stored watershed's polygons, or a NodeProblem saying where to make one."""
    held = opts.get(WATERSHED_KEY)
    if not held or not held.get("polygons"):
        raise NodeProblem("This block holds no watershed. On the Maps tab, delineate one and "
                          "choose “Add to workflow”.")
    return held["polygons"], held


def _run_watershed(inputs, opts):
    polygons, held = watershed_polygons(opts)
    name = opts.get("title") or held.get("name") or "Watershed"
    outline = Polygons("Longitude (°)", "Latitude (°)", geometry.outline_shapes(polygons, name),
                       note=f"{held.get('area_km2', 0):,.1f} km²", name=name, reference=[name])
    row = series.summary_row(name, held)
    titles, cells, _ = table_cells([row])
    extremes = series.extremes_rows(name, held)
    marks = Points("Longitude (°)", "Latitude (°)",
                   [(f"{name}: {label.lower()}", [lon], [lat])
                    for label, lat, lon, _ in pipeline.held_points(held)],
                   note="; ".join(f"{label} {elevation:,.0f} m"
                                  for label, _, _, elevation in pipeline.held_points(held)),
                   title=f"{name}: highest and lowest points", name=name,
                   meta={"labeled": True})
    parts = [_note(f"{held.get('area_km2', 0):,.1f} km² draining to {held.get('pour_lat', 0):.5f}, "
                   f"{held.get('pour_lon', 0):.5f}, by {held.get('source') or held.get('method', '')}."),
             result_table(titles, cells)]
    if extremes:
        e_titles, e_cells, _ = table_cells(extremes)
        parts += [_note("Highest and lowest points:"), result_table(e_titles, e_cells)]
    else:
        parts.append(_note("No highest and lowest points: a ready-made basin has no elevation "
                           "grid, and a watershed delineated before they were kept does not "
                           "hold them. Delineate it again with Terrarium or 3DEP to get them."))
    card = StepOutput(name, Div(*parts), [], None)
    return {"": [outline], "summary": [[row]], "extremes": [marks], "extremes_table": [extremes]}, card


def _watershed_subtitle(opts):
    held = opts.get(WATERSHED_KEY) or {}
    if not held:
        return "no watershed yet"
    return f"{held.get('area_km2', 0):,.1f} km² · {held.get('pour_lat', 0):.4f}, {held.get('pour_lon', 0):.4f}"


watershed = MapNode(
    "watershed", "Watershed", "Map", [], POLYGON, [], _run_watershed,
    description="A watershed delineated on the Maps tab. Its outline can be drawn with a "
                "Scatterplot or used to pick the samples inside it; its summary — pour point, "
                "area, how it was found — is a table. Its highest and lowest points come out "
                "as points and as a table.",
    extras=(Output("summary", TABLE, "Summary table"),
            Output("extremes", POINTS, "Highest and lowest points"),
            Output("extremes_table", TABLE, "Highest and lowest table")),
    output_label="Outline",
    keep=(WATERSHED_KEY,), listed=False, subtitle=_watershed_subtitle)


# ----------------------------------------------------------- Table from the map

def _run_map_table(inputs, opts):
    rows = opts.get(ROWS_KEY)
    if not rows:
        raise NodeProblem("This block holds no table. On the Maps tab, fetch discharge or "
                          "climate for a watershed and choose “Add to workflow”.")
    return [rows], None


def _map_table_subtitle(opts):
    rows = opts.get(ROWS_KEY) or []
    if not rows:
        return "no data yet"
    dates = [r.get("date") for r in rows if r.get("date")]
    span = f" · {min(dates)} to {max(dates)}" if dates else ""
    return f"{opts.get('what', 'table')} · {len(rows):,} rows{span}"


map_table = MapNode(
    "map_table", "Table from the map", "Map", [], TABLE, [], _run_map_table,
    description="Rows the Maps tab fetched: gauge discharge and watershed precipitation and "
                "temperature, by date. Draw it with Hydrograph, or Time series.",
    keep=(ROWS_KEY, "what"), listed=False, subtitle=_map_table_subtitle)


# ------------------------------------------------------------ Sample locations

def _lat_field(page=DATA_PAGE):
    return Field("lat", "Latitude column", DIMENSION, numeric_only=True, page=page,
                 like=("lat",), hint="Decimal degrees, north positive")


def _lon_field(page=DATA_PAGE):
    return Field("lon", "Longitude column", DIMENSION, numeric_only=True, nth=1, page=page,
                 like=("lon", "lng", "long"), hint="Decimal degrees, east positive")


LAT_NAMES = ("latitude", "lat", "lat_dd", "latitude_dd")
LON_NAMES = ("longitude", "lon", "lng", "long", "lon_dd", "longitude_dd")


def guess_position_columns(columns):
    """(latitude column, longitude column) of a table by their names, or None if it lacks either."""
    lowered = {str(c).strip().lower(): c for c in columns}
    lat = next((lowered[n] for n in LAT_NAMES if n in lowered), None)
    lon = next((lowered[n] for n in LON_NAMES if n in lowered), None)
    return (lat, lon) if lat is not None and lon is not None else None


def read_locations(rows, sample_col, lat_col, lon_col):
    """
    [(sample, lat, lon)] for the rows with a usable position, and how many had none.

    A latitude beyond ±90 or a longitude beyond ±180 is not a position, and is counted with
    the blanks.
    """
    found, missing = [], 0
    for row in rows:
        lat, lon = number_of(row.get(lat_col)), number_of(row.get(lon_col))
        if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
            missing += 1
            continue
        found.append((str(row.get(sample_col, "") or "").strip(), lat, lon))
    return found, missing


def _run_locations(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    found, missing = read_locations(rows, sample_col, opts["lat"], opts["lon"])
    if not found:
        raise NodeProblem(f"No row has a latitude in '{opts['lat']}' and a longitude in "
                          f"'{opts['lon']}'.")
    order = {name: i for i, name in enumerate(sample_names(rows, sample_col))}
    groups = {}
    for name, lat, lon in found:
        xs, ys = groups.setdefault(name or "(unnamed)", ([], []))
        xs.append(lon)
        ys.append(lat)
    note = f"{len(found):,} location{'s' if len(found) != 1 else ''}"
    if missing:
        note += f"; {missing:,} row{'s' if missing != 1 else ''} had no usable position"
    points = Points("Longitude (°)", "Latitude (°)",
                    [(name, xs, ys) for name, (xs, ys) in groups.items()],
                    note=note + ".", title="Sample locations", name="Sample locations",
                    meta={"order": order})
    return [points], None


def _validate_locations(opts, context):
    if not opts.get("lat") or not opts.get("lon"):
        return "Choose the latitude and longitude columns."
    if opts["lat"] == opts["lon"]:
        return "Latitude and longitude must be different columns."
    return None


sample_locations = MapNode(
    "sample_locations", "Sample locations", "Map",
    [Port("table", (TABLE,), "Table")], POINTS,
    [_lat_field(), _lon_field()], _run_locations, _validate_locations,
    description="Places samples by their latitude and longitude. A Scatterplot draws them, "
                "with a Watershed's outline over them if both are connected to it.")


# ----------------------------------------------------------- Samples in watershed

INSIDE_MODES = {
    "flag": "Add an “in_watershed” column (yes / no)",
    "inside": "Keep only the samples inside",
    "outside": "Keep only the samples outside",
}


def _run_inside(inputs, opts):
    rows, _ = table_of(inputs, "table")
    outline = inputs["watershed"][0][0]
    polygons = [[list(vertices)] for _, vertices in outline.shapes]
    mode = opts.get("mode", "flag")
    out, inside, outside, unplaced = [], 0, 0, 0
    for row in rows:
        lat, lon = number_of(row.get(opts["lat"])), number_of(row.get(opts["lon"]))
        if lat is None or lon is None:
            unplaced += 1
            verdict = None
        else:
            verdict = geometry.contains(polygons, lon, lat)
            inside, outside = inside + verdict, outside + (not verdict)
        if mode == "flag":
            out.append({**row, "in_watershed": "" if verdict is None else ("yes" if verdict else "no")})
        elif verdict is not None and verdict == (mode == "inside"):
            out.append(dict(row))
    if inside + outside == 0:
        raise NodeProblem(f"No row has a latitude in '{opts['lat']}' and a longitude in "
                          f"'{opts['lon']}'.")
    one = unplaced == 1
    fate = (("is" if one else "are") + " left unmarked" if mode == "flag"
            else ("was" if one else "were") + " dropped")
    note = (f"{inside:,} of {inside + outside:,} located row{'s' if inside + outside != 1 else ''} "
            f"{'is' if inside + outside == 1 else 'are'} inside the watershed"
            + (f"; {unplaced:,} had no position and {fate}" if unplaced else "")
            + ".")
    return [out], StepOutput(opts.get("title") or "Samples in watershed",
                             Div(_note(note)), [], None)


def _validate_inside(opts, context):
    if not opts.get("lat") or not opts.get("lon"):
        return "Choose the latitude and longitude columns."
    if opts["lat"] == opts["lon"]:
        return "Latitude and longitude must be different columns."
    return None


samples_in_watershed = MapNode(
    "samples_in_watershed", "Samples in watershed", "Map",
    [Port("table", (TABLE,), "Table"), Port("watershed", (POLYGON,), "Watershed")], TABLE,
    [_lat_field(), _lon_field(),
     Field("mode", "Result", SELECT, choices=INSIDE_MODES, default="flag", page=OPTIONS_PAGE)],
    _run_inside, _validate_inside,
    description="Tests each sample's latitude and longitude against a watershed's outline: "
                "mark them, or keep only those inside (or outside). Connect a Watershed to the "
                "second input.")


MAP_NODES = [watershed, map_table, sample_locations, samples_in_watershed]
