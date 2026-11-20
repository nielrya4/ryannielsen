"""
The Maps tab: pick a pour point on the map, delineate its watershed, look at its streams, gauges
and climate, and hand what was found to the workflow.

What the map makes goes to the canvas as blocks that hold it — a Watershed, a table of fetched
discharge and climate — so the rest of the workflow can read them like any other step, and a
Watershed block's right-click offers "View on the map" to come back here. The map also draws the
spreadsheet's samples, if it has latitude and longitude columns, and every Watershed on the
canvas.

Delineating is done in the browser, from a DEM (Terrarium tiles, or USGS 3DEP LiDAR in the US), or
a finished basin is fetched (USGS NLDI in the US, MERIT-Hydro worldwide); see `geo_lib`.
"""
import asyncio
import html
import json
import re
import time
from datetime import date, timedelta

import js
from pyodide.ffi import to_js

from antioch.elements import Button, Div, Input, Option, P, Select, Span
from antioch.event import when
from antioch.macros import Map

from geo_lib import basins, climate, dem as dem_fetch, gauges, geometry, pipeline, render, series, terrain
from geo_lib.net import RateLimitedError
from plot_lib.export import download_bytes
from ui_lib import next_frame

from .nodes.maps import guess_position_columns, read_locations

MAP_HEIGHT = "calc(100vh - 128px)"
SIDE_WIDTH = "340px"

SOURCES = {
    "terrarium": "Terrarium elevation (global, ~30 m)",
    "usgs_3dep": "USGS 3DEP elevation (US, down to 1 m)",
    "nldi": "USGS NLDI basin (US, ready-made)",
    "merit_global": "MERIT-Hydro basin (global, ready-made)",
}
PRECOMPUTED = ("nldi", "merit_global")
SOURCE_NOTES = {
    "terrarium": "Fetches elevation tiles and traces the watershed here, in the browser.",
    "usgs_3dep": "LiDAR-derived and much finer where it exists; US only, and blank outside its coverage.",
    "nldi": "The upstream basin of the nearest mapped NHD stream: instant, and good for large rivers.",
    "merit_global": "A ready-made global basin. A free community service (mghydro.com): please use it lightly.",
}
RESOLUTIONS = {"100": "Coarse (~100 m): fastest", "30": "Medium (~30 m): native global DEM",
               "10": "Fine (~10 m)", "1": "Finest (~1 m): 3DEP only"}
CLIMATE_VARIABLES = {"precipitation": "Precipitation (total)", "temperature": "Temperature (mean)",
                     "wind": "Wind (mean daily maximum)"}
BIN_SIZES = {"daily": "Daily", "hourly": "Hourly"}

HEADING = {"font-weight": "600", "font-size": "13px", "margin": "0 0 6px 0", "color": "#2c3e50"}
NOTE = {"font-size": "12px", "color": "#6c757d", "margin": "4px 0 0 0"}
RESULT = {"font-size": "13px", "margin": "3px 0"}
WARNING = {"background": "#fff3e0", "color": "#a15c00", "border": "1px solid #ffcc80",
           "border-radius": "4px", "padding": "8px", "margin": "6px 0", "font-size": "12px"}
SECTION = {"border-top": "1px solid #e9ecef", "padding": "12px 0"}
BUTTON = {"background-color": "#34495e", "color": "#fff", "border": "none", "padding": "6px 12px",
          "cursor": "pointer", "font-size": "13px", "border-radius": "3px", "margin": "0 6px 6px 0"}
PRIMARY = dict(BUTTON, **{"background-color": "#1f6fb2"})
FIELD = {"font-size": "13px", "padding": "3px 4px", "box-sizing": "border-box"}
ROW = {"display": "flex", "align-items": "center", "gap": "6px", "margin": "4px 0",
       "font-size": "13px", "flex-wrap": "wrap"}

WATERSHED = "watershed"      # the option a Watershed block holds its watershed in
BOUNDARY_STYLE = {"color": "#1b5e20", "weight": 2, "fill": False}
BLOCK_STYLE = {"color": "#e67e22", "weight": 2, "dashArray": "6 4", "fillOpacity": 0.05}


def _js(value):
    """A Python value as a plain JavaScript object, for Leaflet."""
    return to_js(value, dict_converter=js.Object.fromEntries)


def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower() or "watershed"


def _esc(text):
    """Text for a Leaflet popup, which takes HTML: sample and gauge names are data, not markup."""
    return html.escape(str(text))


def _today():
    return date.today()


class MapsPanel:
    """
    Usage:
        maps = MapsPanel(get_rows, workflow_panel)
        maps.attach(loading_overlay)
        DOM.add(maps.element)

    Attributes:
        element - the whole tab: the map and the side panel
    """

    def __init__(self, get_rows, workflow, center=(42.78, -112.43), zoom=10):
        self._get_rows = get_rows
        self._workflow = workflow          # the WorkflowPanel the results go to
        self._overlay = None
        self._busy = False
        self._pour = None                  # (lat, lon) as clicked
        self._current = None               # the watershed shown, as a Watershed block stores it
        self._dem = self._mask = None      # of a DEM delineation, while it is on the map
        self._streams = None               # the river network found, with how to describe it
        self._gauges = []
        self._table = None                 # (rows, what) fetched and not yet added
        self._groups = {}                  # what is drawn, by name: [(kind, Leaflet object)]
        self._wired = []

        self.map = Map(center=list(center), zoom=zoom, width="100%", height=MAP_HEIGHT)
        self.map.on_click(self._on_map_click)
        self._build_side()
        self.element = Div(
            Div(self.map.element, style={"flex": "1", "min-width": "0"}),
            self._side,
            style={"display": "flex", "height": "100%", "min-height": "0"})

    # ------------------------------------------------------------------- layout

    def attach(self, overlay):
        """Give the panel the busy curtain it covers long work with."""
        self._overlay = overlay
        return self

    def _button(self, text, handler, primary=False, title=""):
        button = Button(text, style=dict(PRIMARY if primary else BUTTON))
        if title:
            button.set_attribute("title", title)

        @when(button.events.click)
        def on_click(sender, *args):
            handler()
        self._wired.append(on_click)
        return button

    @staticmethod
    def _select(choices, value=None):
        select = Select(style=dict(FIELD))
        for key, label in choices.items():
            select.add(Option(label, value=key))
        if value is not None:
            select.value = value
        return select

    @staticmethod
    def _field(kind, value="", width="100px", **attributes):
        field = Input(kind, style=dict(FIELD, width=width), **attributes)
        field.value = value
        return field

    @staticmethod
    def _checkbox(checked=False):
        box = Input("checkbox")
        box._dom_element.checked = checked
        return box

    @staticmethod
    def _row(label, *controls):
        return Div(Span(label, style={"min-width": "70px"}), *controls, style=dict(ROW))

    @staticmethod
    def _check(box, text, *controls):
        """A checkbox and what it switches on, on one line."""
        return Div(box, Span(text), *controls, style=dict(ROW))

    @staticmethod
    def _section(title, *children):
        return Div(P(title, style=dict(HEADING)), *children, style=dict(SECTION))

    def _build_side(self):
        end = _today() - timedelta(days=5)         # the archive runs a few days behind
        self._lat = self._field("number", width="110px", step="any", placeholder="latitude")
        self._lon = self._field("number", width="110px", step="any", placeholder="longitude")
        self._name = self._field("text", width="200px", placeholder="Name (optional)")
        self._source = self._select(SOURCES, "terrarium")
        self._source_note = P(SOURCE_NOTES["terrarium"], style=dict(NOTE))
        self._resolution = self._select(RESOLUTIONS, "30")
        self._resolution_row = self._row("Resolution", self._resolution)
        self._source.on("change", lambda e: self._source_changed())
        for field in (self._lat, self._lon):
            field.on("change", lambda e: self._typed_position())

        self._status = P("Click the map to choose a pour point.", style=dict(NOTE, **{"margin": "8px 0"}))
        self._results = Div()
        self._after = Div(style={"display": "none"})

        self._show_samples = self._checkbox()
        self._show_blocks = self._checkbox()
        self._show_streams = self._checkbox(True)
        self._min_order = self._select({"1": "1"}, "1")
        for box in (self._show_samples, self._show_blocks, self._show_streams):
            box.on("change", lambda e: self._layers_changed())
        self._min_order.on("change", lambda e: self._draw_streams())
        self._sample_note = P("", style=dict(NOTE))

        self._gauge = self._select({"": "No gauges found yet"})
        self._start = self._field("date", (end - timedelta(days=365)).isoformat(), "140px")
        self._end = self._field("date", end.isoformat(), "140px")
        self._bin = self._select(BIN_SIZES, "daily")
        self._with_climate = self._checkbox(True)
        self._table_note = P("", style=dict(NOTE))
        self._table_buttons = Div(style={"display": "none"})

        self._variable = self._select(CLIMATE_VARIABLES, "precipitation")
        self._climate_note = P("", style=dict(NOTE))
        self._weather = Div()

        self._side = Div(
            self._section(
                "Pour point",
                self._row("Latitude", self._lat), self._row("Longitude", self._lon),
                self._row("Name", self._name),
                self._row("Method", self._source), self._source_note, self._resolution_row,
                Div(self._button("Delineate watershed", lambda: asyncio.ensure_future(self._delineate()),
                                 primary=True),
                    self._button("Clear", self._clear_all), style={"margin-top": "8px"}),
                self._status, self._results, self._after),
            self._section(
                "Show on the map",
                self._check(self._show_streams, "Streams, order at least", self._min_order),
                self._check(self._show_blocks, "Watersheds in the workflow (orange)"),
                self._check(self._show_samples, "Spreadsheet samples"),
                self._sample_note),
            self._section(
                "Gauges and discharge",
                P("USGS stream gauges in the watershed, and their measured discharge with the "
                  "watershed's precipitation and temperature, as a table for the hydrograph.",
                  style=dict(NOTE, **{"margin": "0 0 6px 0"})),
                self._button("Find gauges", lambda: asyncio.ensure_future(self._find_gauges())),
                self._row("Gauge", self._gauge),
                self._row("From", self._start), self._row("To", self._end),
                self._row("Steps", self._bin),
                self._check(self._with_climate, "Include the watershed's precipitation and temperature"),
                self._button("Fetch table", lambda: asyncio.ensure_future(self._fetch_table()),
                             primary=True),
                self._table_note, self._table_buttons),
            self._section(
                "Climate",
                self._row("Variable", self._variable),
                P("Averaged over the dates above at a grid of points inside the watershed.",
                  style=dict(NOTE, **{"margin": "0 0 6px 0"})),
                self._button("Sample the watershed", lambda: asyncio.ensure_future(self._sample_climate())),
                self._button("Current weather", lambda: asyncio.ensure_future(self._current_weather())),
                self._climate_note, self._weather),
            style={"width": SIDE_WIDTH, "flex-shrink": "0", "overflow-y": "auto", "padding": "4px 14px",
                   "border-left": "1px solid #dee2e6", "background": "#fafbfc",
                   "box-sizing": "border-box"})
        self._build_after()

    def _build_after(self):
        """The buttons that appear once there is a watershed to hand on."""
        self._after.add(
            self._button("Add to workflow", self._add_watershed, primary=True,
                         title="Puts the watershed on the canvas as a block"),
            self._button("Download GeoJSON", self._download),
            self._button("Download high and low points", self._download_extremes,
                         title="The highest and lowest points as GeoJSON points"))

    # ---------------------------------------------------------------- map layers

    def _drawn(self, group, kind, obj):
        if obj is not None:
            self._groups.setdefault(group, []).append((kind, obj))
        return obj

    def _forget(self, group):
        for kind, obj in self._groups.pop(group, []):
            try:
                (self.map.remove_marker if kind == "marker" else self.map.remove_layer)(obj)
            except Exception:
                pass

    def _geojson(self, group, feature, name, style, add_to_control=True):
        return self._drawn(group, "layer", self.map.add_geojson(
            _js(feature), name=name, style_options=style, add_to_control=add_to_control))

    def _instance(self):
        return self.map._get_state("map_instance")

    def shown(self):
        """The tab was opened: Leaflet measured the hidden map as empty, so size it again."""
        instance = self._instance()
        if instance:
            instance.invalidateSize()
        self._layers_changed()

    def _layers_changed(self):
        self._draw_blocks()
        self._draw_samples()
        self._draw_streams()

    def _draw_blocks(self):
        self._forget("blocks")
        if not self._show_blocks._dom_element.checked:
            return
        for step_id, name, held in self._workflow.watershed_blocks():
            layer = self._geojson("blocks", pipeline.held_geojson(held), name, BLOCK_STYLE,
                                  add_to_control=False)
            if layer is not None:
                layer.bindTooltip(_esc(f"{self._workflow.number_of(self._workflow.workflow.get(step_id))}: {name}"))

    def _dot(self, lat, lon, popup, fill="#e74c3c", edge="#7b241c", radius=6):
        """A small dot with a popup — a sample (red), which must not look like the pour point's pin."""
        instance = self._instance()
        if not instance:
            return None
        options = js.Object.new()
        options.radius, options.color, options.weight = radius, edge, 1
        options.fillColor, options.fillOpacity = fill, 0.9
        dot = js.L.circleMarker(to_js([lat, lon]), options).addTo(instance)
        dot.bindPopup(popup)
        return dot

    def _draw_samples(self):
        self._forget("samples")
        self._sample_note.set_text("")
        if not self._show_samples._dom_element.checked:
            return
        rows = self._get_rows() or []
        columns = list(rows[0].keys()) if rows else []
        position = guess_position_columns(columns)
        if not position:
            self._sample_note.set_text("The spreadsheet has no latitude and longitude columns "
                                       "(named lat/latitude and lon/lng/longitude).")
            return
        sample_col = columns[0]
        found, missing = read_locations(rows, sample_col, *position)
        for name, lat, lon in found[:1000]:
            self._drawn("samples", "layer", self._dot(lat, lon, _esc(name or "(unnamed)")))
        note = f"{min(len(found), 1000):,} sample{'s' if len(found) != 1 else ''} shown"
        if missing:
            note += f"; {missing:,} row{'s' if missing != 1 else ''} had no usable position"
        if len(found) > 1000:
            note += "; only the first 1,000 are drawn"
        self._sample_note.set_text(note + ".")

    def _draw_streams(self):
        self._forget("streams")
        streams = self._streams
        if not streams or not self._show_streams._dom_element.checked:
            return
        smallest = int(self._min_order.value or 1)
        for feature in streams["stream_features"]:
            order = feature["properties"].get("stream_order", 1)
            if order >= smallest:
                self._geojson("streams", feature, f"Streams (order {order})",
                              {"color": "#1565c0", "weight": 1 + 0.7 * order, "opacity": 0.9},
                              add_to_control=False)

    # ------------------------------------------------------------- the pour point

    def _on_map_click(self, sender, data, dom_event=None):
        if not self._busy:
            self._set_pour(data["lat"], data["lng"])

    def _typed_position(self):
        try:
            lat, lon = float(self._lat.value), float(self._lon.value)
        except ValueError:
            return
        if abs(lat) <= 90 and abs(lon) <= 180:
            self._set_pour(lat, lon, pan=True)

    def _set_pour(self, lat, lon, pan=False):
        self._pour = (lat, lon)
        self._lat.value, self._lon.value = f"{lat:.5f}", f"{lon:.5f}"
        self._forget("pour")
        self._drawn("pour", "marker", self.map.add_marker(lat, lon, popup_text="Pour point"))
        if pan:
            self.map.set_view([lat, lon])
        self._status.set_text("Choose a method and press Delineate watershed.")

    def _source_changed(self):
        source = self._source.value
        self._source_note.set_text(SOURCE_NOTES[source])
        self._resolution_row.style.display = "none" if source in PRECOMPUTED else "flex"

    # ------------------------------------------------------------- delineating

    def _say(self, text, warning=False):
        self._status.set_text(text)
        self._status.style.color = "#a15c00" if warning else "#6c757d"

    def _line(self, text, **style):
        self._results.add(P(text, style=dict(RESULT, **style)))

    def _warn(self, text):
        self._results.add(Div(text, style=dict(WARNING)))

    def _clear_results(self):
        for group in ("elevation", "mask", "boundary", "extremes", "streams", "climate", "gauges"):
            self._forget(group)
        self._results._dom_element.innerHTML = ""
        self._weather._dom_element.innerHTML = ""
        self._after.style.display = "none"
        self._table_buttons.style.display = "none"
        self._table_note.set_text("")
        self._climate_note.set_text("")
        self._current = self._dem = self._mask = self._streams = None
        self._gauges, self._table = [], None
        self._gauge.clear()
        self._gauge.add(Option("No gauges found yet", value=""))

    def _clear_all(self):
        if self._busy:
            return
        self._clear_results()
        self._forget("pour")
        self._pour = None
        self._lat.value = self._lon.value = ""
        self._say("Click the map to choose a pour point.")

    def _paint(self, text):
        if self._overlay:
            self._overlay.message(text)

    async def _delineate(self):
        if self._busy:
            return
        if not self._pour:
            self._say("Click the map to choose a pour point first.", warning=True)
            return
        lat, lon = self._pour
        source = self._source.value
        self._busy = True
        started = time.time()
        try:
            # Inside the try: whatever fails here must still let go of _busy, or Clear and the
            # map would ignore every later click.
            self._clear_results()
            if self._overlay:
                self._overlay.show("Starting…")
            if source in PRECOMPUTED:
                await self._from_basin(source, lat, lon)
            else:
                await self._from_dem(source, lat, lon, float(self._resolution.value))
            self._say(f"Done in {time.time() - started:.1f} s.")
        except RateLimitedError:
            self._say("That service's request limit was reached. Try again later.", warning=True)
        except Exception as error:
            self._say(f"Delineation failed: {error}", warning=True)
        finally:
            self._busy = False
            if self._overlay:
                self._overlay.hide()

    def _name_for(self, lat, lon):
        return (self._name.value or "").strip() or f"Watershed at {lat:.3f}, {lon:.3f}"

    async def _from_dem(self, source, lat, lon, resolution):
        dem, result, radius = await pipeline.delineate_expanding(
            dem_fetch.fetch_dem, source, lat, lon, resolution,
            report=self._paint, pause=next_frame)
        self._paint("Drawing the result…")
        await next_frame()
        label = "USGS 3DEP" if dem["source"] == "usgs_3dep" else "Terrarium (global)"
        if result["geojson"] is None or not result["cell_count"]:
            self._say("No watershed could be traced from that point.", warning=True)
            return
        held = pipeline.stored_watershed(self._name_for(lat, lon), dem, result, label)
        self._dem, self._mask = dem, result["mask"]
        self._streams = ({"stream_features": result["stream_features"], "has_order_filter": True,
                          "min_order_available": 1, "max_order_available": result["max_stream_order"]}
                         if result["stream_features"] else None)

        self._drawn("elevation", "layer", self.map.add_rgba_overlay(
            render.elevation_rgba(dem["grid"]), dem["bounds"], opacity=0.55, name="Elevation"))
        self._drawn("mask", "layer", self.map.add_rgba_overlay(
            render.mask_rgba(result["mask"]), dem["bounds"], opacity=0.45, name="Watershed",
            fit_bounds=True))
        self._show(held)
        if result["touches_edge"]:
            self._warn(f"Partial result: the watershed still runs past the fetched area at a "
                       f"{radius:g} km radius. It may be part of a very large basin; try a "
                       "ready-made basin.")
        if dem.get("nodata_fraction", 0) > 0.3:
            self._warn(f"{dem['nodata_fraction'] * 100:.0f}% of the fetched area has no {label} data"
                       + (" — likely outside 3DEP coverage; try Terrarium."
                          if dem["source"] == "usgs_3dep" else "."))
        h, w = dem["grid"].shape
        self._line(f"{label}: {w}×{h} cells (~{dem['px_size_m']:.0f} m), radius {radius:g} km",
                   color="#777")
        if dem.get("zoom_clamped"):
            self._warn("The resolution was reduced to keep this computable; choose a coarser "
                       "setting for areas this large.")
        self._set_stream_orders()

    async def _from_basin(self, source, lat, lon):
        self._paint("Fetching the basin…")
        fetch = basins.fetch_basin_nldi if source == "nldi" else basins.fetch_basin_merit
        basin = await fetch(lat, lon)
        if not basin:
            self._say("No basin was found there: " + (
                "the point is too far from a mapped NHD stream, or outside the US."
                if source == "nldi" else "it is outside MERIT-Hydro's coverage."), warning=True)
            return
        held = pipeline.stored_basin(self._name_for(lat, lon), basin, lat, lon, basin["attribution"])
        self._show(held)
        self._line(f"Source: {basin['attribution']}", color="#777")
        self._paint("Fetching the river network…")
        rivers = (await basins.fetch_rivers_nldi(basin["comid"]) if source == "nldi"
                  else await basins.fetch_rivers_merit(lat, lon))
        if rivers:
            self._streams = rivers
            low, high = rivers.get("min_order_available"), rivers.get("max_order_available")
            if rivers["has_order_filter"] and low and low > 1:
                self._warn(f"For a basin this large only orders {low}–{high} are available.")
            elif source == "nldi":
                self._warn("NLDI has no stream orders, so this shows the streams within about "
                           "200 km of the pour point; distant tributaries of a very large basin "
                           "may be missing" + (" and the lines were thinned." if rivers.get("truncated") else "."))
            self._set_stream_orders()
        else:
            self._line("No river network was available for this point.", color="#999")

    def _set_stream_orders(self):
        streams = self._streams
        self._min_order.clear()
        if not streams:
            self._min_order.add(Option("1", value="1"))
            return
        low = streams.get("min_order_available") or 1
        high = streams.get("max_order_available") or 1
        orders = range(low, high + 1) if streams.get("has_order_filter", True) else [1]
        for order in orders:
            self._min_order.add(Option(str(order), value=str(order)))
        self._min_order.value = str(low)
        self._draw_streams()

    def _show(self, held):
        """Make a watershed the current one: draw its outline, and say what it is."""
        self._current = held
        self._forget("boundary")
        layer = self._geojson("boundary", pipeline.held_geojson(held), "Watershed boundary",
                              BOUNDARY_STYLE)
        if layer is not None and self._dem is None:
            self.map.zoom_to_layers(padding=20)
        self._line(f"Area: {held['area_km2']:,.2f} km²", **{"font-weight": "600"})
        self._line(f"Pour point: {held['pour_lat']:.5f}, {held['pour_lon']:.5f}", color="#555")
        if "mean_elevation_m" in held:
            self._line(f"Elevation: {held['min_elevation_m']:,.0f}–{held['max_elevation_m']:,.0f} m "
                       f"(mean {held['mean_elevation_m']:,.0f} m)", color="#555")
        self._show_extremes(held)
        self._after.style.display = "block"

    def _show_extremes(self, held):
        """Mark the watershed's highest (purple) and lowest (teal) points, and say where they are."""
        self._forget("extremes")
        for label, lat, lon, elevation in pipeline.held_points(held):
            high = label.startswith("Highest")
            self._drawn("extremes", "layer", self._dot(
                lat, lon, _esc(f"{label}: {elevation:,.0f} m"),
                fill="#8e44ad" if high else "#16a0a0", edge="#fff", radius=8))
            self._line(f"{label}: {elevation:,.0f} m at {lat:.5f}, {lon:.5f}", color="#555")

    # ----------------------------------------------------------- from the canvas

    def show_block(self, step_id):
        """Show a Watershed block's watershed here (its right-click "View on the map")."""
        for found, name, held in self._workflow.watershed_blocks():
            if found == step_id:
                break
        else:
            return
        self.shown()
        self._clear_results()
        held = dict(held, name=name)
        self._pour = (held["pour_lat"], held["pour_lon"])
        self._lat.value, self._lon.value = f"{held['pour_lat']:.5f}", f"{held['pour_lon']:.5f}"
        self._name.value = name
        self._forget("pour")
        self._drawn("pour", "marker", self.map.add_marker(held["pour_lat"], held["pour_lon"],
                                                           popup_text="Pour point"))
        self._show(held)
        self.map.zoom_to_layers(padding=20)
        self._line(f"From workflow step {self._workflow.number_of(self._workflow.workflow.get(step_id))}.",
                   color="#777")
        self._say("Gauges and climate can be fetched for this watershed.")

    def _add_watershed(self):
        if not self._current:
            return
        held = dict(self._current, name=self._name_for(self._current["pour_lat"], self._current["pour_lon"]))
        step_id = self._workflow.add_from_map("watershed", {WATERSHED: held}, held["name"])
        self._say(f"Added to the workflow as step "
                  f"{self._workflow.number_of(self._workflow.workflow.get(step_id))}.")
        self._draw_blocks()

    def _download(self):
        if not self._current:
            return
        feature = pipeline.held_geojson(self._current)
        download_bytes(json.dumps(feature).encode("utf-8"), f"{_slug(self._current['name'])}.geojson",
                       "application/geo+json")

    def _download_extremes(self):
        if not self._current:
            return
        if not pipeline.held_points(self._current):
            self._say("This watershed has no highest and lowest points: only a delineation from "
                      "Terrarium or 3DEP elevation keeps them.", warning=True)
            return
        collection = pipeline.held_points_geojson(self._current)
        download_bytes(json.dumps(collection).encode("utf-8"),
                       f"{_slug(self._current['name'])}_high_low_points.geojson",
                       "application/geo+json")

    # ------------------------------------------------------- gauges and discharge

    def _need_watershed(self):
        if self._current:
            return True
        self._say("Delineate a watershed first.", warning=True)
        return False

    async def _find_gauges(self):
        if self._busy or not self._need_watershed():
            return
        held = self._current
        self._busy = True
        if self._overlay:
            self._overlay.show("Looking for gauges…")
        try:
            lat, lon = held["pour_lat"], held["pour_lon"]
            found = await gauges.find_gauges_in_watershed(lat, lon, held.get("comid"))
            if held.get("comid") is None:
                # The NHD reach nearest a pour point can be a larger river, whose whole upstream
                # network is not this watershed: keep only the gauges that lie inside it.
                found = gauges.inside(found, held["polygons"], lat, lon)
            note = ""
            if not found:
                nearby = await gauges.find_gauge_nearby(lat, lon)
                found = [nearby] if nearby else []
                note = " None lies inside the watershed; this is the nearest within 25 km." if found else ""
            self._forget("gauges")
            self._gauges = found
            self._gauge.clear()
            if not found:
                self._gauge.add(Option("No gauges found", value=""))
                self._say("No USGS gauges were found (they are US only).", warning=True)
                return
            dates = self._dates(False, quiet=True)
            self._paint("Checking which gauges have data…")
            have = (await gauges.fetch_discharge_batch([g["site_no"] for g in found], *dates)
                    if dates else {})
            found.sort(key=lambda g: g["site_no"] not in have)       # with data first, then by distance
            self._gauges = found
            for site in found:
                days = len(have[site["site_no"]]["dates"]) if site["site_no"] in have else 0
                label = f"{site['name'] or 'Gauge'} ({site['site_no']})"
                if dates:
                    label += f" — {days} days of data" if days else " — no data in these dates"
                self._gauge.add(Option(label, value=site["site_no"]))
                self._drawn("gauges", "marker", self.map.add_marker(
                    site["lat"], site["lon"], popup_text=_esc(f"{site['name']} (USGS {site['site_no']})")))
            count = len(found)
            self._say(f"{count} gauge{'s' if count != 1 else ''} in the watershed"
                      + (f"; {len(have)} with discharge in these dates, listed first" if dates else "")
                      + "." + note)
        except RateLimitedError:
            self._say("USGS's request limit was reached. Try again later.", warning=True)
        except Exception as error:
            self._say(f"Looking for gauges failed: {error}", warning=True)
        finally:
            self._busy = False
            if self._overlay:
                self._overlay.hide()

    def _dates(self, hourly, quiet=False):
        """(start, end) as the user gave them, or None — with a message unless `quiet` — when they
        will not do."""
        def refuse(text):
            if not quiet:
                self._say(text, warning=True)

        try:
            start, end = date.fromisoformat(self._start.value), date.fromisoformat(self._end.value)
        except ValueError:
            refuse("Give the From and To dates.")
            return None
        if end < start:
            refuse("The end date is before the start date.")
            return None
        if hourly and (end - start).days > 62:
            refuse("Hourly data is limited to about two months at a time; shorten the dates "
                   "or use daily steps.")
            return None
        if (end - start).days > 366 * 5:
            refuse("Choose at most five years at a time.")
            return None
        return start.isoformat(), end.isoformat()

    async def _fetch_table(self):
        if self._busy or not self._need_watershed():
            return
        hourly = self._bin.value == "hourly"
        dates = self._dates(hourly)
        if not dates:
            return
        site_no = self._gauge.value
        with_climate = self._with_climate._dom_element.checked
        if not site_no and not with_climate:
            self._say("Find gauges and choose one, or include the climate.", warning=True)
            return
        held = self._current
        self._busy = True
        if self._overlay:
            self._overlay.show("Fetching…")
        try:
            discharge = weather = None
            notes = []
            if site_no:
                self._paint(f"Fetching discharge at USGS {site_no}…")
                discharge = await gauges.fetch_discharge_series(site_no, *dates, "hourly" if hourly else "daily")
                if not discharge:
                    notes.append(f"USGS {site_no} has no discharge in those dates"
                                 + (" (hourly data goes back only about four months)." if hourly else "."))
                    if not with_climate:
                        self._say(notes[0], warning=True)
                        return
            if with_climate:
                self._paint("Fetching precipitation and temperature…")
                points = geometry.grid_inside(held["polygons"], 8)
                weather = await climate.fetch_watershed_series(points, *dates, hourly=hourly)
                if not weather:
                    notes.append("No climate data came back for those dates.")
            if not discharge and not weather:
                self._say(" ".join(notes), warning=True)
                return
            sample = (discharge or {}).get("site_name") or held["name"]
            rows = series.hydro_rows(sample, discharge, weather, hourly=hourly)
            if len(rows) > 20000:
                self._say(f"That makes {len(rows):,} rows; shorten the dates.", warning=True)
                return
            what = " and ".join(p for p, v in (("discharge", discharge), ("climate", weather)) if v).capitalize()
            self._table = (rows, what, bool(discharge), bool(weather))
            self._table_note.set_text(f"{len(rows):,} rows, {rows[0]['date']} to {rows[-1]['date']}: {what.lower()}"
                                      f"{' at ' + sample if discharge else ' over ' + held['name']}.")
            self._table_buttons._dom_element.innerHTML = ""
            self._table_buttons.add(
                self._button("Add table to workflow", lambda: self._add_table(False), primary=True),
                self._button("Add table and hydrograph", lambda: self._add_table(True),
                             title="Also draws the hydrograph and hyetograph"))
            self._table_buttons.style.display = "block"
            self._say(" ".join(["Fetched."] + notes), warning=bool(notes))
        except RateLimitedError:
            self._say("A request limit was reached (USGS or Open-Meteo). Try again later.", warning=True)
        except Exception as error:
            self._say(f"Fetching failed: {error}", warning=True)
        finally:
            self._busy = False
            if self._overlay:
                self._overlay.hide()

    def _add_table(self, with_hydrograph):
        if not self._table:
            return
        rows, what, has_flow, has_rain = self._table
        title = f"{what}: {rows[0]['sample']}"
        table_id = self._workflow.add_from_map("map_table", {"rows": rows, "what": what, "title": title},
                                               title, run=not with_hydrograph)
        message = f"Added to the workflow as step {self._workflow.number_of(self._workflow.workflow.get(table_id))}"
        if with_hydrograph:
            options = {"date": "date", "samples": [rows[0]["sample"]], "use_flow": has_flow,
                       "use_rain": has_rain, "view": "timeline", "rain_at": "start",
                       "flow_units": "m³/s", "rain_units": "mm"}
            if has_flow:
                options["flow"] = "discharge_m3s"
            if has_rain:
                options["rain"] = "precip_mm"
            hydro_id = self._workflow.add_from_map("hydrograph", options, "Hydrograph",
                                                   inputs={"table": [table_id]}, run=False)
            self._workflow.run_steps([table_id, hydro_id])
            message += f", with a hydrograph (step {self._workflow.number_of(self._workflow.workflow.get(hydro_id))})"
        self._say(message + ".")

    # ---------------------------------------------------------------- climate

    async def _sample_climate(self):
        if self._busy or not self._need_watershed():
            return
        dates = self._dates(False)
        if not dates:
            return
        variable = self._variable.value
        held = self._current
        self._busy = True
        if self._overlay:
            self._overlay.show("Sampling the watershed…")
        try:
            points = geometry.grid_inside(held["polygons"], 8)
            answer = await climate.fetch_historical_grid(points, *dates, variable)
            if not answer:
                self._say("No climate data came back.", warning=True)
                return
            self._forget("climate")
            colors, low, high = render.value_colors(answer["values"])
            south, west, north, east = geometry.bounds(held["polygons"])
            spacing_m = max((north - south) * 111320 / 8, 200)
            for (lat, lon), value, color in zip(points, answer["values"], colors):
                if value is None:
                    continue
                circle = self._drawn("climate", "layer", self.map.add_circle(
                    lat, lon, spacing_m / 2, color=color, fill_color=color, fill_opacity=0.75))
                if circle is not None:
                    circle.bindPopup(f"{value:,.1f} {answer['unit']}")
            if low is None:
                self._climate_note.set_text("No values came back.")
            else:
                self._climate_note.set_text(
                    f"{CLIMATE_VARIABLES[variable]}, {dates[0]} to {dates[1]}: {low:,.1f} to {high:,.1f} "
                    f"{answer['unit']} across {len(points)} points (dark to light).")
        except RateLimitedError:
            self._say("Open-Meteo's request limit was reached. Try again later.", warning=True)
        except Exception as error:
            self._say(f"Sampling failed: {error}", warning=True)
        finally:
            self._busy = False
            if self._overlay:
                self._overlay.hide()

    async def _current_weather(self):
        if self._busy or not self._pour:
            self._say("Choose a pour point first.", warning=True)
            return
        lat, lon = self._pour
        try:
            now = await climate.fetch_current_weather(lat, lon)
        except RateLimitedError:
            self._say("Open-Meteo's request limit was reached. Try again later.", warning=True)
            return
        self._weather._dom_element.innerHTML = ""
        if not now:
            self._weather.add(P("Current weather is not available.", style=dict(NOTE)))
            return
        for text in (now["description"], f"{now['temperature_c']:.1f} °C, humidity {now['relative_humidity_pct']}%",
                     f"Wind {now['wind_speed_kmh']:.0f} km/h, precipitation {now['precipitation_mm']} mm"):
            self._weather.add(P(text, style=dict(RESULT)))
        self._weather.add(P(now["attribution"], style=dict(NOTE)))

