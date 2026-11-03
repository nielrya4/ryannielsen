"""The Leaflet map: basemaps, the watersheds (recolored on demand), rivers and sample sites."""
import js
from antioch.event import when
from antioch.macros import Map
from pyodide.ffi import create_proxy, to_js

from . import config as c
from .data import PROPS, RIVERS_TEXT, SAMPLES_TEXT, SINK, WATERSHEDS_TEXT, bounds
from .popup import Popup

# Keyless basemaps (CARTO's now needs an API key): Esri light gray first, imagery as an option.
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
BASEMAPS = {
    "Light gray": (ESRI.format("Canvas/World_Light_Gray_Base"),
                   "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap "
                   "contributors", 16),
    "Satellite": (ESRI.format("World_Imagery"), "Tiles &copy; Esri", 18),
}
# State lines and place names, drawn over the watersheds (transparent tiles).
REFERENCE = ESRI.format("Reference/World_Boundaries_and_Places_Alternate")
# Map panes (Leaflet z-index): the reference above the watersheds and rivers (overlay pane,
# 400), the sample dots above that so labels never cover them; popups stay on top (700).
PANES = {"reference": 420, "samples": 450}
MIN_ZOOM_SLACK = 1  # zoom levels the viewer may go out past the fitted view
PAN_MARGIN = 1.0    # panning stops this far past the study area (fraction of its size)
MAP_STYLE = {"display": "block", "border": "none", "border_radius": "0"}


def js_obj(d):
    return to_js(d, dict_converter=js.Object.fromEntries)


class WatershedMap:
    """
    Attributes:
        element - the map's root element
        layer   - id of the coloring the watersheds are drawn in
    """

    def __init__(self, layer):
        self.layer = layer
        self._features = {}  # watershed id -> Leaflet layer
        self._popups = {}    # watershed id, or "sink" -> its Popup while open
        self._contents = {}  # the same keys -> the popup's content function (a JS proxy)
        self._sink = None    # the sink sample's marker
        self._proxies = []   # JS callbacks, kept alive
        self._map = Map(center=[43.9, -115.6], zoom=7, width="100%", height="100%",
                        container_style=MAP_STYLE)
        self.element = self._map.element

        @when(self._map.events.ready)
        def on_ready(sender, *args):
            leaflet = self._map._get_state("map_instance")
            for name, z in PANES.items():
                pane = leaflet.createPane(name)
                pane.style.zIndex = str(z)
                pane.style.pointerEvents = "none"  # clicks reach the watersheds below
            self._add_watersheds()
            self._add_rivers()
            self._add_samples(leaflet)
            self._add_basemaps(leaflet)
            self._map.fit_bounds(bounds())
            # No zooming out past the whole study area, and no panning away from it.
            (south, west), (north, east) = bounds()
            area = js.L.latLngBounds(js_obj([south, west]), js_obj([north, east]))
            leaflet.setMinZoom(leaflet.getBoundsZoom(area) - MIN_ZOOM_SLACK)
            leaflet.setMaxBounds(area.pad(PAN_MARGIN))
            leaflet.options.maxBoundsViscosity = 1.0  # a hard edge, not a rubber band

    def color_by(self, layer):
        """Redraw the watersheds in coloring `layer`, and any open popup with its stats."""
        self.layer = layer
        for wid, feature in self._features.items():
            feature.setStyle(self._style(wid))
        for key, owner in [*self._features.items(), ("sink", self._sink)]:
            if owner is not None and owner.isPopupOpen():
                self._popups.pop(key).closed()
                # The content function again, not a built element: Leaflet keeps whatever it
                # is given, and a fixed element would stop later openings rebuilding the stats.
                owner.setPopupContent(self._contents[key])
                self._popups[key].opened()

    def _popup(self, key):
        """The DOM content of a popup (a watershed id, or "sink") under the current coloring."""
        self._popups[key] = (Popup(SINK, self.layer, sink=True) if key == "sink"
                             else Popup(PROPS[key], self.layer))
        return self._popups[key].element.dom_element

    def _bind_popup(self, layer, key):
        """Give a Leaflet layer the popup for key. It is built when opened, so it shows the
        stats of the coloring at that moment; its charts are drawn once it is in the page, and
        freed when it closes."""
        self._contents[key] = self._proxy(lambda _: self._popup(key))
        layer.bindPopup(self._contents[key],
                        js_obj({"maxWidth": 340, "autoPanPaddingTopLeft": [60, 20]}))
        layer.on("popupopen", self._proxy(lambda e: self._popups[key].opened()))
        layer.on("popupclose", self._proxy(lambda e: self._popups.pop(key).closed()
                                           if key in self._popups else None))

    def _proxy(self, fn):
        proxy = create_proxy(fn)
        self._proxies.append(proxy)
        return proxy

    def _style(self, wid, weight=1.5):
        return js_obj({"color": c.OUTLINE, "weight": weight, "opacity": 1,
                       "fillColor": PROPS[wid]["fill"][self.layer],
                       "fillOpacity": c.FILL_OPACITY})

    def _add_watersheds(self):
        def each(feature, layer):
            wid = feature.properties.id
            self._features[wid] = layer
            layer.setStyle(self._style(wid))
            self._bind_popup(layer, wid)
            layer.on("mouseover", self._proxy(lambda e: layer.setStyle(self._style(wid, 3))))
            layer.on("mouseout", self._proxy(lambda e: layer.setStyle(self._style(wid))))

        self._map.add_geojson(js.JSON.parse(WATERSHEDS_TEXT), name="Watersheds",
                              on_each_feature=each, add_to_control=False)

    def _add_rivers(self):
        def each(feature, layer):
            order = feature.properties.sorder
            layer.setStyle(js_obj({"color": c.RIVER, "weight": 0.6 + 0.55 * (order - 4),
                                   "opacity": 0.85}))

        self._map.add_geojson(js.JSON.parse(RIVERS_TEXT), name="Rivers", on_each_feature=each)

    def _add_samples(self, leaflet):
        def marker(feature, latlng):
            p = feature.properties
            size = {"radius": 8, "weight": 2} if p.sink else {"radius": 6, "weight": 1.5}
            return js.L.circleMarker(latlng, js_obj({**size, "fillColor": p.color,
                                                     "color": c.OUTLINE, "fillOpacity": 1,
                                                     "pane": "samples"}))

        def each(feature, layer):
            p = feature.properties
            if p.sink:
                self._sink = layer
                self._bind_popup(layer, "sink")
            else:
                layer.bindPopup(f"<b>{p.sample_id}</b><br>{p.site}<br>a source in the mixture "
                                "model")

        # Map.add_geojson takes no pointToLayer, so the circles are built directly.
        samples = js.L.geoJSON(js.JSON.parse(SAMPLES_TEXT), js_obj({
            "pointToLayer": self._proxy(marker), "onEachFeature": self._proxy(each)}))
        samples.addTo(leaflet)
        self._map._add_to_layer_control(samples, "Sample sites")

    def _add_basemaps(self, leaflet):
        """Swap the macro's default tiles for BASEMAPS, all offered in the layer control, and
        add the REFERENCE overlay (on by default)."""
        leaflet.eachLayer(self._proxy(lambda layer: leaflet.removeLayer(layer)
                                      if hasattr(layer, "getTileUrl") else None))
        control = self._map._get_state("layer_control")
        for i, (name, (url, attribution, max_zoom)) in enumerate(BASEMAPS.items()):
            tiles = js.L.tileLayer(url, js_obj({"attribution": attribution, "maxZoom": max_zoom}))
            if i == 0:
                tiles.addTo(leaflet)
            control.addBaseLayer(tiles, name)
        reference = js.L.tileLayer(REFERENCE, js_obj({"pane": "reference", "maxZoom": 16}))
        reference.addTo(leaflet)
        control.addOverlay(reference, "State lines & places")
