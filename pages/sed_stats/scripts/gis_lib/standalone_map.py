"""
Standalone GISMap - Self-contained GIS mapping component

A complete GIS mapping component built directly on Leaflet without inheriting
from the base Map class. Provides full control over initialization, rendering,
and feature management.
"""
from typing import List, Dict, Optional, Union, Any, Callable
from antioch.macros.base import Macro
from antioch.elements import Div
from antioch.lib.loader import inject_script, inject_stylesheet
import js
from pyodide.ffi import create_proxy


# Ensure Leaflet is loaded
inject_stylesheet('antioch/lib/vendor/leaflet.css')
inject_script('antioch/lib/vendor/leaflet.js')
inject_script('antioch/lib/vendor/geotiff.js')
inject_script('antioch/lib/vendor/proj4.js')


class GISMap(Macro):
    """
    Standalone GIS mapping component with Leaflet.

    Features:
    - Action queue for sequential operations
    - Automatic visibility detection for tabs/hidden containers
    - Points, lines, polygons, circles
    - GeoTIFF raster support
    - Layer management
    - Custom styling
    """

    def __init__(self, center=None, zoom=13, width="100%", height="600px",
                 tile_layer="OpenStreetMap", **kwargs):
        """
        Initialize a GIS map.

        Args:
            center: [lat, lng] for map center (default: San Francisco)
            zoom: Initial zoom level (1-18)
            width: Map width
            height: Map height
            tile_layer: Tile layer name ("OpenStreetMap", "CartoDB", "Satellite")
        """
        super().__init__(macro_type="gis_map", **kwargs)

        # Default to San Francisco if no center provided
        if center is None:
            center = [37.7749, -122.4194]
        elif isinstance(center, tuple):
            center = list(center)

        # Set up state
        self._set_state(
            center=center,
            zoom=zoom,
            width=width,
            height=height,
            tile_layer=tile_layer,
            map_instance=None,
            initialized=False,
            markers=[],
            layers=[],
            raster_layers=[]
        )

        # Action queue
        self._action_queue = []
        self._is_processing = False
        self._is_ready = False

        # Visibility tracking
        self._visibility_observer = None
        self._has_been_visible = False

        # Create events
        self._create_event('ready')
        self._create_event('click')
        self._create_event('zoom')
        self._create_event('move')

        # Container style
        self._container_style = {
            "width": width,
            "height": height,
            "border": "1px solid #ccc",
            "border_radius": "4px",
            "overflow": "hidden",
            "position": "relative",
            "z_index": "1"
        }

        # Initialize macro
        self._init_macro()

    def _create_elements(self):
        """Create the map container element."""
        # Create container
        container = self._create_container(self._container_style)
        self._register_element('container', container)

        # Set ID
        container.set_attribute("id", self._id)
        if container._dom_element:
            container._dom_element.id = self._id

        # Initialize map after delay
        init_proxy = create_proxy(lambda: self._initialize_map())
        js.setTimeout(init_proxy, 500)

        return container

    def _initialize_map(self):
        """Initialize the Leaflet map."""
        if self._get_state('initialized'):
            return

        try:
            # Check if Leaflet is loaded
            if not hasattr(js, 'L'):
                init_proxy = create_proxy(lambda: self._initialize_map())
                js.setTimeout(init_proxy, 100)
                return

            container = self._get_element('container')
            if not container or not container._dom_element:
                init_proxy = create_proxy(lambda: self._initialize_map())
                js.setTimeout(init_proxy, 100)
                return

            print("GISMap: Initializing Leaflet map...")

            # Get settings
            center = self._get_state('center')
            zoom = self._get_state('zoom')
            width = self._get_state('width')
            height = self._get_state('height')

            # Ensure container has dimensions
            container._dom_element.style.width = width
            container._dom_element.style.height = height

            # Create Leaflet map
            map_instance = js.L.map(container._dom_element)

            # Set view
            js_center = js.Array.new()
            js_center.push(center[0])
            js_center.push(center[1])
            map_instance.setView(js_center, zoom)

            # Add tile layer
            self._add_tile_layer(map_instance)

            # Store map instance
            self._set_state(map_instance=map_instance, initialized=True)
            self._is_ready = True

            print("GISMap: Map initialized successfully")

            # Setup event handlers
            self._setup_map_events(map_instance)

            # Setup visibility observer
            self._setup_visibility_observer()

            # Invalidate size after delay
            def invalidate():
                map_instance.invalidateSize()
                print("GISMap: Initial size invalidation")

            invalidate_proxy = create_proxy(invalidate)
            js.setTimeout(invalidate_proxy, 100)
            js.setTimeout(invalidate_proxy, 300)

            # Fire ready event
            self._fire_event('ready')

            # Process queued actions
            self._process_queue()

        except Exception as e:
            print(f"GISMap: Error initializing map: {e}")
            init_proxy = create_proxy(lambda: self._initialize_map())
            js.setTimeout(init_proxy, 200)

    def _add_tile_layer(self, map_instance):
        """Add tile layer to the map."""
        tile_layer_name = self._get_state('tile_layer')

        tile_configs = {
            'OpenStreetMap': {
                'url': 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                'attribution': '&copy; OpenStreetMap contributors',
                'maxZoom': 19
            },
            'CartoDB': {
                'url': 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
                'attribution': '&copy; OpenStreetMap &copy; CARTO',
                'maxZoom': 19
            },
            'Satellite': {
                'url': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                'attribution': 'Tiles &copy; Esri',
                'maxZoom': 18
            }
        }

        config = tile_configs.get(tile_layer_name, tile_configs['OpenStreetMap'])

        # Create tile layer
        options = js.Object.new()
        options.attribution = config['attribution']
        options.maxZoom = config['maxZoom']

        js.L.tileLayer(config['url'], options).addTo(map_instance)

    def _setup_map_events(self, map_instance):
        """Setup event handlers for map interactions."""
        # Click event
        def handle_click(event):
            lat = event.latlng.lat
            lng = event.latlng.lng
            self._fire_event('click', {'lat': lat, 'lng': lng})

        click_proxy = create_proxy(handle_click)
        map_instance.on('click', click_proxy)

        # Zoom event
        def handle_zoom(event):
            zoom = map_instance.getZoom()
            self._set_state(zoom=zoom)
            self._fire_event('zoom', zoom)

        zoom_proxy = create_proxy(handle_zoom)
        map_instance.on('zoomend', zoom_proxy)

        # Move event
        def handle_move(event):
            center_obj = map_instance.getCenter()
            center = [center_obj.lat, center_obj.lng]
            self._set_state(center=center)
            self._fire_event('move', center)

        move_proxy = create_proxy(handle_move)
        map_instance.on('moveend', move_proxy)

    def _setup_visibility_observer(self):
        """Setup IntersectionObserver for automatic visibility handling."""
        container = self._get_element('container')
        if not container or not container._dom_element:
            return

        try:
            def on_visibility_change(entries, observer):
                for entry in entries:
                    if entry.isIntersecting:
                        if not self._has_been_visible:
                            print("GISMap: First time visible - fixing size")
                            self._has_been_visible = True
                            def delayed_fix():
                                self.fix_size_after_show()
                            fix_proxy = create_proxy(delayed_fix)
                            js.setTimeout(fix_proxy, 100)
                        else:
                            print("GISMap: Visible again - fixing size")
                            def delayed_fix():
                                self.fix_size_after_show()
                            fix_proxy = create_proxy(delayed_fix)
                            js.setTimeout(fix_proxy, 50)

            callback_proxy = create_proxy(on_visibility_change)
            options = js.Object.new()
            options.threshold = 0.01

            observer = js.IntersectionObserver.new(callback_proxy, options)
            observer.observe(container._dom_element)
            self._visibility_observer = observer

            print("GISMap: Visibility observer setup")

        except Exception as e:
            print(f"GISMap: Error setting up visibility observer: {e}")

    def fix_size_after_show(self):
        """Fix map sizing after becoming visible."""
        map_instance = self._get_state('map_instance')
        if not map_instance:
            return

        center = self._get_state('center')
        zoom = self._get_state('zoom')

        def fix_iteration(n):
            try:
                options = js.Object.new()
                options.pan = False
                options.animate = False
                map_instance.invalidateSize(options)

                js_center = js.Array.new()
                js_center.push(center[0])
                js_center.push(center[1])

                view_options = js.Object.new()
                view_options.animate = False
                map_instance.setView(js_center, zoom, view_options)

                print(f"GISMap: Size fix iteration {n}")
            except Exception as e:
                print(f"GISMap: Error in fix iteration: {e}")

        for i, delay in enumerate([0, 100, 300, 600], 1):
            if delay == 0:
                fix_iteration(i)
            else:
                proxy = create_proxy(lambda n=i: fix_iteration(n))
                js.setTimeout(proxy, delay)

    # Action queue methods
    def _queue_action(self, action: Callable, description: str = "action"):
        """Queue an action to execute when map is ready."""
        self._action_queue.append((action, description))

        if self._is_ready and not self._is_processing:
            self._process_queue()

    def _process_queue(self):
        """Process the action queue sequentially."""
        if self._is_processing or not self._is_ready:
            return

        if not self._action_queue:
            return

        self._is_processing = True
        action, description = self._action_queue.pop(0)

        try:
            print(f"GISMap: Executing {description}")
            action()
        except Exception as e:
            print(f"GISMap: Error executing {description}: {e}")
        finally:
            self._is_processing = False

            if self._action_queue:
                def process_next():
                    self._process_queue()
                next_proxy = create_proxy(process_next)
                js.setTimeout(next_proxy, 50)

    # Public API methods
    def add_point(self, lat: float, lng: float, properties: Optional[Dict] = None,
                  popup: Optional[str] = None, **kwargs):
        """Add a point marker to the map."""
        def do_add_point():
            map_instance = self._get_state('map_instance')
            if not map_instance:
                return

            # Create marker
            js_coords = js.Array.new()
            js_coords.push(lat)
            js_coords.push(lng)

            marker = js.L.marker(js_coords).addTo(map_instance)

            # Add popup if provided
            if popup:
                marker.bindPopup(popup)
            elif properties:
                popup_html = "<br>".join([f"<b>{k}:</b> {v}" for k, v in properties.items()])
                marker.bindPopup(popup_html)

            # Store marker
            markers = self._get_state('markers')
            markers.append(marker)
            self._set_state(markers=markers)

        self._queue_action(do_add_point, f"add_point({lat}, {lng})")

    def add_line(self, coordinates: List[Union[tuple, list]],
                 properties: Optional[Dict] = None,
                 color: str = "#3388ff", weight: int = 3, opacity: float = 1.0,
                 **kwargs):
        """Add a polyline to the map."""
        def do_add_line():
            map_instance = self._get_state('map_instance')
            if not map_instance:
                return

            # Convert coordinates to JS array
            js_coords = js.Array.new()
            for lat, lng in coordinates:
                js_point = js.Array.new()
                js_point.push(lat)
                js_point.push(lng)
                js_coords.push(js_point)

            # Create options
            options = js.Object.new()
            options.color = color
            options.weight = weight
            options.opacity = opacity

            # Create polyline
            polyline = js.L.polyline(js_coords, options).addTo(map_instance)

            # Store layer
            layers = self._get_state('layers')
            layers.append(polyline)
            self._set_state(layers=layers)

        self._queue_action(do_add_line, f"add_line({len(coordinates)} points)")

    def add_polygon(self, coordinates: List[Union[tuple, list]],
                    properties: Optional[Dict] = None,
                    color: str = "#3388ff", fill_color: Optional[str] = None,
                    fill_opacity: float = 0.2, **kwargs):
        """Add a polygon to the map."""
        def do_add_polygon():
            map_instance = self._get_state('map_instance')
            if not map_instance:
                return

            if fill_color is None:
                fill_color_actual = color
            else:
                fill_color_actual = fill_color

            # Convert coordinates to JS array
            js_coords = js.Array.new()
            for lat, lng in coordinates:
                js_point = js.Array.new()
                js_point.push(lat)
                js_point.push(lng)
                js_coords.push(js_point)

            # Create options
            options = js.Object.new()
            options.color = color
            options.fillColor = fill_color_actual
            options.fillOpacity = fill_opacity

            # Create polygon
            polygon = js.L.polygon(js_coords, options).addTo(map_instance)

            # Store layer
            layers = self._get_state('layers')
            layers.append(polygon)
            self._set_state(layers=layers)

        self._queue_action(do_add_polygon, f"add_polygon({len(coordinates)} points)")

    def add_circle(self, lat: float, lng: float, radius: float,
                   color: str = "#3388ff", fill_color: Optional[str] = None,
                   fill_opacity: float = 0.2, **kwargs):
        """Add a circle to the map."""
        def do_add_circle():
            map_instance = self._get_state('map_instance')
            if not map_instance:
                return

            if fill_color is None:
                fill_color_actual = color
            else:
                fill_color_actual = fill_color

            # Create position
            js_coords = js.Array.new()
            js_coords.push(lat)
            js_coords.push(lng)

            # Create options
            options = js.Object.new()
            options.color = color
            options.fillColor = fill_color_actual
            options.fillOpacity = fill_opacity
            options.radius = radius

            # Create circle
            circle = js.L.circle(js_coords, options).addTo(map_instance)

            # Store layer
            layers = self._get_state('layers')
            layers.append(circle)
            self._set_state(layers=layers)

        self._queue_action(do_add_circle, f"add_circle({lat}, {lng}, r={radius})")

    # Proj4 definition strings for common projections
    # proj4.js only has a few EPSG codes built-in, so we define others manually
    PROJ4_DEFS = {
        # Web Mercator
        3857: "+proj=merc +a=6378137 +b=6378137 +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 +k=1 +units=m +nadgrids=@null +wktext +no_defs",
        # WGS84 Geographic
        4326: "+proj=longlat +datum=WGS84 +no_defs",
        # UTM Zones (Northern Hemisphere) - zones 1-60
        **{32600 + zone: f"+proj=utm +zone={zone} +datum=WGS84 +units=m +no_defs" for zone in range(1, 61)},
        # UTM Zones (Southern Hemisphere) - zones 1-60
        **{32700 + zone: f"+proj=utm +zone={zone} +south +datum=WGS84 +units=m +no_defs" for zone in range(1, 61)},
        # NAD83 UTM Zones
        **{26900 + zone: f"+proj=utm +zone={zone} +datum=NAD83 +units=m +no_defs" for zone in range(1, 23)},
        # Common State Plane (NAD83)
        2163: "+proj=laea +lat_0=45 +lon_0=-100 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs",  # US National Atlas
    }

    def _get_proj4_def(self, epsg_code: int) -> str:
        """Get proj4 definition string for an EPSG code."""
        if epsg_code in self.PROJ4_DEFS:
            return self.PROJ4_DEFS[epsg_code]
        # Fallback: try EPSG code directly (works for some built-in codes)
        return f"EPSG:{epsg_code}"

    def _detect_projection_from_coords(self, bbox: list) -> str:
        """
        Attempt to detect the projection from coordinate ranges.
        Returns the proj4 definition string.
        """
        min_x, min_y, max_x, max_y = bbox

        # Web Mercator (EPSG:3857) - very large coordinate values
        if abs(min_x) > 1e6 or abs(max_x) > 1e6:
            if abs(min_y) > 1e5 and abs(max_y) < 2.1e7:  # Valid Web Mercator Y range
                return self._get_proj4_def(3857)

        # UTM zones - X typically 100,000-900,000, Y varies by hemisphere
        if 100000 < min_x < 900000 and 100000 < max_x < 900000:
            # Northern hemisphere UTM
            if 0 < min_y < 10000000:
                return self._get_proj4_def(32618)  # Default to zone 18N
            # Southern hemisphere UTM
            elif min_y > 1000000:
                return self._get_proj4_def(32718)  # Default to zone 18S

        # State Plane coordinates (US) - various ranges
        if 100000 < min_x < 4000000 and 0 < min_y < 1000000:
            return self._get_proj4_def(3857)

        # Default to Web Mercator
        return self._get_proj4_def(3857)

    def _try_fallback_projections(self, js, bbox: list, to_proj: str) -> list:
        """
        Try common projections until one produces valid geographic coordinates.
        Returns the converted bbox or the original if all fail.
        """
        # List of common EPSG codes to try
        epsg_codes_to_try = [
            3857,   # Web Mercator
            32618,  # UTM Zone 18N
            32610,  # UTM Zone 10N (US West Coast)
            32611,  # UTM Zone 11N
            32617,  # UTM Zone 17N
            32619,  # UTM Zone 19N
            26918,  # NAD83 / UTM Zone 18N
            26910,  # NAD83 / UTM Zone 10N
            2163,   # US National Atlas Equal Area
        ]

        for epsg in epsg_codes_to_try:
            try:
                from_proj = self._get_proj4_def(epsg)
                sw_js = js.proj4(from_proj, to_proj, js.Array.of(bbox[0], bbox[1]))
                ne_js = js.proj4(from_proj, to_proj, js.Array.of(bbox[2], bbox[3]))

                sw = list(sw_js.to_py())
                ne = list(ne_js.to_py())

                # Validate coordinates are in valid geographic range
                if (-180 <= sw[0] <= 180 and -90 <= sw[1] <= 90 and
                    -180 <= ne[0] <= 180 and -90 <= ne[1] <= 90):
                    print(f"GISMap: Fallback projection EPSG:{epsg} succeeded")
                    return [sw[0], sw[1], ne[0], ne[1]]
            except Exception:
                continue

        print("GISMap: All fallback projections failed, using original bounds")
        return bbox

    def add_geotiff(self, url: str, opacity: float = 1.0, colormap: str = "viridis",
                    vmin: Optional[float] = None, vmax: Optional[float] = None,
                    band: int = 0, rgb_bands: Optional[List[int]] = None, **kwargs):
        """
        Add a GeoTIFF raster to the map using geotiff.js and matplotlib.

        Args:
            url: URL or path to the GeoTIFF file
            opacity: Layer opacity (0-1)
            colormap: Matplotlib colormap name (e.g., "viridis", "terrain", "gray")
                      Ignored when rgb_bands is specified.
            vmin: Minimum value for color scaling (auto if None)
            vmax: Maximum value for color scaling (auto if None)
            band: Band index to display (0-indexed, default: 0)
                  Ignored when rgb_bands is specified.
            rgb_bands: List of 3 band indices for RGB composite [R, G, B].
                       Example: [0, 1, 2] for bands 1, 2, 3 as R, G, B.
                       When specified, creates true-color image instead of colormap.
        """
        def do_add_geotiff():
            map_instance = self._get_state('map_instance')
            if not map_instance:
                return

            print(f"GISMap: Loading GeoTIFF from {url}")

            # Check if geotiff.js is loaded
            if not hasattr(js, 'GeoTIFF'):
                print("GISMap: geotiff.js not loaded")
                return

            try:
                import numpy as np
                from matplotlib.colors import Normalize
                import matplotlib.cm as cm
                from PIL import Image
                from io import BytesIO
                import base64
                from pyodide.http import pyfetch

                print("GISMap: Processing libraries loaded")

                # Use async/await pattern with pyfetch
                async def load_and_process_geotiff():
                    try:
                        print(f"GISMap: Fetching {url}")
                        response = await pyfetch(url)
                        print("GISMap: Response received, getting bytes")

                        # Get bytes from response
                        tiff_bytes = await response.bytes()
                        print(f"GISMap: Received {len(tiff_bytes)} bytes")

                        # Convert Python bytes to JavaScript ArrayBuffer
                        uint8_array = js.Uint8Array.new(len(tiff_bytes))
                        uint8_array.assign(tiff_bytes)
                        array_buffer = uint8_array.buffer
                        print(f"GISMap: Converted to JS ArrayBuffer ({array_buffer.byteLength} bytes)")

                        # Parse with geotiff.js
                        # JS promises need to be converted to Python Future
                        import asyncio
                        from js import Promise

                        def js_to_py_promise(js_promise):
                            """Convert JS Promise to Python awaitable."""
                            future = asyncio.Future()

                            def on_success(result):
                                future.set_result(result)

                            def on_error(error):
                                future.set_exception(Exception(str(error)))

                            js_promise.then(create_proxy(on_success), create_proxy(on_error))
                            return future

                        tiff = await js_to_py_promise(js.GeoTIFF.fromArrayBuffer(array_buffer))
                        print("GISMap: TIFF parsed")

                        image = await js_to_py_promise(tiff.getImage())
                        print("GISMap: Image obtained")

                        # Get rasters and bbox
                        # readRasters() returns a PyodideFuture (awaitable)
                        rasters = await image.readRasters()

                        # Get geographic bounding box (WGS84 lat/lng)
                        # geotiff.js getBoundingBox() returns projected coordinates
                        # We need geographic coordinates for Leaflet
                        bbox_result_js = image.getBoundingBox()
                        bbox_result = list(bbox_result_js.to_py())
                        print(f"GISMap: Projected bounds: {bbox_result}")

                        # Convert projected coordinates to geographic (WGS84) using proj4
                        # Check if proj4 is available
                        if hasattr(js, 'proj4'):
                            print("GISMap: proj4 available, attempting coordinate conversion")

                            # Get the projection info from the GeoTIFF
                            geoKeys = image.getGeoKeys()

                            # Extract key projection parameters
                            model_type = getattr(geoKeys, 'GTModelTypeGeoKey', None)
                            projected_cs = getattr(geoKeys, 'ProjectedCSTypeGeoKey', None)
                            geographic_cs = getattr(geoKeys, 'GeographicTypeGeoKey', None)

                            print(f"GISMap: ModelType={model_type}, ProjectedCS={projected_cs}, GeographicCS={geographic_cs}")

                            # Determine if we need coordinate conversion
                            from_proj = None
                            to_proj = self._get_proj4_def(4326)  # WGS84 lat/lng

                            # Check if already in geographic coordinates (no conversion needed)
                            is_geographic = (
                                model_type == 2 or  # ModelTypeGeographic
                                (geographic_cs and geographic_cs in [4326, 4269, 4267]) or  # WGS84, NAD83, NAD27
                                (projected_cs is None and -180 <= bbox_result[0] <= 180 and -90 <= bbox_result[1] <= 90)
                            )

                            if is_geographic:
                                print("GISMap: Already in geographic coordinates, no conversion needed")
                                bbox = bbox_result
                            else:
                                # Need to convert from projected to geographic
                                # Try to use EPSG code if available
                                if projected_cs and projected_cs != 32767:  # 32767 = user-defined
                                    from_proj = self._get_proj4_def(projected_cs)
                                    print(f"GISMap: Using EPSG:{projected_cs} -> {from_proj[:50]}...")
                                else:
                                    # Try to detect projection from coordinate ranges
                                    from_proj = self._detect_projection_from_coords(bbox_result)
                                    print(f"GISMap: Detected projection: {from_proj[:50]}...")

                                # Convert corners [minX, minY, maxX, maxY] in projected coords
                                # to [minLon, minLat, maxLon, maxLat] in geographic coords
                                try:
                                    sw_lonlat_js = js.proj4(from_proj, to_proj, js.Array.of(bbox_result[0], bbox_result[1]))
                                    ne_lonlat_js = js.proj4(from_proj, to_proj, js.Array.of(bbox_result[2], bbox_result[3]))

                                    # Convert JS arrays to Python lists
                                    sw_lonlat = list(sw_lonlat_js.to_py())
                                    ne_lonlat = list(ne_lonlat_js.to_py())

                                    # Validate converted coordinates
                                    if (-180 <= sw_lonlat[0] <= 180 and -90 <= sw_lonlat[1] <= 90 and
                                        -180 <= ne_lonlat[0] <= 180 and -90 <= ne_lonlat[1] <= 90):
                                        bbox = [sw_lonlat[0], sw_lonlat[1], ne_lonlat[0], ne_lonlat[1]]
                                        print(f"GISMap: Converted bounds: SW={sw_lonlat}, NE={ne_lonlat}")
                                    else:
                                        raise ValueError(f"Invalid converted coordinates: SW={sw_lonlat}, NE={ne_lonlat}")
                                except Exception as proj_error:
                                    print(f"GISMap: Projection conversion failed: {proj_error}")
                                    print("GISMap: Trying fallback projections...")
                                    bbox = self._try_fallback_projections(js, bbox_result, to_proj)
                        else:
                            print("GISMap: proj4 not available, using bounds as-is")
                            bbox = bbox_result

                        # Get raster dimensions
                        width = image.getWidth()
                        height = image.getHeight()
                        print(f"GISMap: Raster size: {width}x{height}")

                        if rgb_bands is not None:
                            # RGB composite mode - combine 3 bands into true-color image
                            print(f"GISMap: Creating RGB composite from bands {rgb_bands}")

                            # Get the three bands
                            r_data = np.array(rasters[rgb_bands[0]].to_py()).reshape(height, width)
                            g_data = np.array(rasters[rgb_bands[1]].to_py()).reshape(height, width)
                            b_data = np.array(rasters[rgb_bands[2]].to_py()).reshape(height, width)

                            print(f"GISMap: R range: {r_data.min()}-{r_data.max()}, G: {g_data.min()}-{g_data.max()}, B: {b_data.min()}-{b_data.max()}")

                            # Normalize each band to 0-255
                            def normalize_band(data, vmin_val=None, vmax_val=None):
                                """Normalize band data to 0-255 range."""
                                # Mask nodata (0 values)
                                valid_data = data[data > 0]
                                if len(valid_data) == 0:
                                    return np.zeros_like(data, dtype=np.uint8)

                                # Use provided range or auto-detect
                                min_val = vmin_val if vmin_val is not None else np.percentile(valid_data, 2)
                                max_val = vmax_val if vmax_val is not None else np.percentile(valid_data, 98)

                                # Clip and scale
                                clipped = np.clip(data, min_val, max_val)
                                if max_val > min_val:
                                    normalized = ((clipped - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                                else:
                                    normalized = np.zeros_like(data, dtype=np.uint8)
                                return normalized

                            r_norm = normalize_band(r_data, vmin, vmax)
                            g_norm = normalize_band(g_data, vmin, vmax)
                            b_norm = normalize_band(b_data, vmin, vmax)

                            # Create alpha channel (transparent where all bands are 0)
                            alpha = np.where((r_data == 0) & (g_data == 0) & (b_data == 0), 0, 255).astype(np.uint8)

                            # Stack into RGBA
                            rgba_uint8 = np.stack([r_norm, g_norm, b_norm, alpha], axis=-1)

                            # Create PIL Image
                            img = Image.fromarray(rgba_uint8, mode='RGBA')
                            print(f"GISMap: RGB composite created")

                        else:
                            # Single band + colormap mode
                            data_js = rasters[band]

                            # Convert JS TypedArray to numpy array
                            data = np.array(data_js.to_py()).reshape(height, width)

                            print(f"GISMap: Data range: {data.min()} to {data.max()}")

                            # Mask nodata values
                            data_masked = np.ma.masked_equal(data, 0)

                            # Determine value range
                            vmin_actual = float(data_masked.min()) if vmin is None else vmin
                            vmax_actual = float(data_masked.max()) if vmax is None else vmax

                            print(f"GISMap: Scaling range: {vmin_actual} to {vmax_actual}")

                            # Apply colormap using matplotlib
                            norm = Normalize(vmin=vmin_actual, vmax=vmax_actual)
                            cmap = cm.get_cmap(colormap)

                            # Convert data to RGBA image
                            rgba = cmap(norm(data_masked.filled(0)))
                            rgba_uint8 = (rgba * 255).astype(np.uint8)
                            rgba_uint8[data == 0, 3] = 0  # Make nodata transparent

                            # Create PIL Image
                            img = Image.fromarray(rgba_uint8, mode='RGBA')

                        # Convert to base64 data URL
                        buffer = BytesIO()
                        img.save(buffer, format='PNG')
                        img_base64 = base64.b64encode(buffer.getvalue()).decode()
                        img_url = f"data:image/png;base64,{img_base64}"

                        print(f"GISMap: Image converted to PNG ({len(img_base64)} chars)")

                        # Create Leaflet bounds [[lat, lng], [lat, lng]]
                        bounds_array = js.Array.new()
                        sw = js.Array.new()
                        sw.push(bbox[1])  # min lat
                        sw.push(bbox[0])  # min lng
                        ne = js.Array.new()
                        ne.push(bbox[3])  # max lat
                        ne.push(bbox[2])  # max lng
                        bounds_array.push(sw)
                        bounds_array.push(ne)

                        # Add as image overlay
                        overlay = js.L.imageOverlay(img_url, bounds_array, js.Object.new())
                        overlay.setOpacity(opacity)
                        overlay.addTo(map_instance)

                        print("GISMap: GeoTIFF overlay added successfully")

                        # Store raster layer
                        raster_layers = self._get_state('raster_layers')
                        raster_layers.append(overlay)
                        self._set_state(raster_layers=raster_layers)

                    except Exception as e:
                        print(f"GISMap: Error loading GeoTIFF: {e}")
                        import traceback
                        traceback.print_exc()

                # Run the async function
                import asyncio
                asyncio.ensure_future(load_and_process_geotiff())

            except Exception as e:
                print(f"GISMap: Error loading GeoTIFF: {e}")
                import traceback
                traceback.print_exc()

        self._queue_action(do_add_geotiff, f"add_geotiff({url})")

    def clear_all(self):
        """Clear all features from the map."""
        def do_clear():
            map_instance = self._get_state('map_instance')
            if not map_instance:
                return

            # Clear markers
            for marker in self._get_state('markers'):
                map_instance.removeLayer(marker)
            self._set_state(markers=[])

            # Clear layers
            for layer in self._get_state('layers'):
                map_instance.removeLayer(layer)
            self._set_state(layers=[])

            # Clear raster layers
            for layer in self._get_state('raster_layers'):
                map_instance.removeLayer(layer)
            self._set_state(raster_layers=[])

        self._queue_action(do_clear, "clear_all")

    def set_view(self, center: List[float], zoom: Optional[int] = None):
        """Set the map center and zoom."""
        def do_set_view():
            map_instance = self._get_state('map_instance')
            if not map_instance:
                return

            if zoom is None:
                zoom_val = self._get_state('zoom')
            else:
                zoom_val = zoom

            js_center = js.Array.new()
            js_center.push(center[0])
            js_center.push(center[1])

            map_instance.setView(js_center, zoom_val)
            self._set_state(center=center, zoom=zoom_val)

        self._queue_action(do_set_view, f"set_view({center}, {zoom})")

    def fit_bounds(self, bounds: List[List[float]]):
        """Fit the map to given bounds."""
        def do_fit_bounds():
            map_instance = self._get_state('map_instance')
            if not map_instance:
                return

            # Convert bounds to JS array
            js_bounds = js.Array.new()
            for corner in bounds:
                js_corner = js.Array.new()
                js_corner.push(corner[0])
                js_corner.push(corner[1])
                js_bounds.push(js_corner)

            map_instance.fitBounds(js_bounds)

        self._queue_action(do_fit_bounds, "fit_bounds")
