# GIS Library for Antioch

A high-level GIS library for working with geographic data in Leaflet maps. Built on top of the Antioch framework's Map class.

## Key Features

### Automatic Visibility Detection
The GISMap automatically detects when it becomes visible (e.g., when switching tabs) and fixes sizing/rendering issues. No manual intervention needed!

### Action Queue System
All map operations are queued and executed sequentially after the map initializes. You can call `add_point()`, `add_polygon()`, etc. immediately - they'll execute when ready.

## Features

### Vector Features
- **Points** - Create and display point features with custom markers
- **Lines/Polylines** - Draw linear features like roads, rivers, and trails
- **Polygons** - Display areas like parks, buildings, and land parcels
- **Multi-part features** - Support for MultiPoint, MultiLine, and MultiPolygon

### Layer Management
- **VectorLayer** - Organize vector features into named layers
- **RasterLayer** - Display georeferenced raster data
- **LayerGroup** - Group multiple layers for easier management
- **Layer visibility control** - Show/hide layers programmatically
- **Layer bounds** - Automatically calculate and zoom to layer extents

### Styling
- **Style classes** - MarkerStyle, LineStyle, PolygonStyle
- **Style presets** - Ready-to-use styles for common feature types
- **Conditional styling** - Style features based on their properties
- **Choropleth mapping** - Create thematic maps based on numeric values
- **Color ramps** - Built-in color palettes for data visualization

### Data Formats
- **GeoJSON** - Full support for GeoJSON import/export
- **Shapefiles** - Load ESRI shapefiles (.shp, .zip)
- **GeoTIFF** - Display georeferenced raster imagery
- **Feature Collections** - Group and manage multiple features

## Quick Start

```python
from gis_lib import GISMap, Point, Line, Polygon
from gis_lib import StylePresets

# Create a map
map = GISMap(center=[37.7749, -122.4194], zoom=12)

# Add a point
map.add_point(
    37.7749, -122.4194,
    properties={"name": "City Hall"},
    style=StylePresets.MARKER_RED,
    popup="<b>City Hall</b>"
)

# Add a line
road_coords = [
    [37.7749, -122.4194],
    [37.7849, -122.4094]
]
map.add_line(road_coords, style=StylePresets.LINE_ROAD)

# Add a polygon
park_coords = [
    [37.77, -122.45],
    [37.77, -122.43],
    [37.78, -122.43],
    [37.78, -122.45]
]
map.add_polygon(park_coords, style=StylePresets.POLYGON_PARK)
```

## Working with Layers

```python
from gis_lib import GISMap, VectorLayer, Polygon
from gis_lib import StylePresets

# Create map
map = GISMap(center=[37.7749, -122.4194], zoom=12)

# Create a layer
parks_layer = VectorLayer("parks", style=StylePresets.POLYGON_PARK.to_dict())

# Add features to the layer
park1 = Polygon(
    [[37.77, -122.45], [37.77, -122.43], [37.78, -122.43], [37.78, -122.45]],
    properties={"name": "Golden Gate Park", "area_acres": 1017}
)
parks_layer.add_feature(park1)

# Add layer to map
map.add_layer(parks_layer)

# Control layer visibility
map.show_layer("parks")
map.hide_layer("parks")

# Zoom to layer bounds
map.fit_layer("parks")
```

## Custom Styling

```python
from gis_lib import GISMap, MarkerStyle, LineStyle, PolygonStyle

map = GISMap(center=[37.7749, -122.4194], zoom=12)

# Custom marker style
custom_marker = MarkerStyle(
    color="purple",
    icon="https://example.com/icon.png"
)

# Custom line style
custom_line = LineStyle(
    color="#ff0000",
    weight=5,
    opacity=0.7,
    dash_array="10, 5"  # Dashed line
)

# Custom polygon style
custom_polygon = PolygonStyle(
    fill_color="#00ff00",
    fill_opacity=0.4,
    color="#006600",  # Border color
    weight=3
)

# Use custom styles
map.add_point(37.7749, -122.4194, style=custom_marker)
map.add_line(coords, style=custom_line)
map.add_polygon(coords, style=custom_polygon)
```

## Conditional Styling

Style features based on their properties:

```python
from gis_lib import ConditionalStyle, PolygonStyle, StylePresets

# Create a conditional style based on land use
land_use_style = ConditionalStyle(
    "land_use",
    {
        "residential": PolygonStyle(fill_color="yellow", fill_opacity=0.3),
        "commercial": PolygonStyle(fill_color="red", fill_opacity=0.3),
        "industrial": PolygonStyle(fill_color="purple", fill_opacity=0.3),
        "park": StylePresets.POLYGON_PARK
    },
    default_style=PolygonStyle(fill_color="gray", fill_opacity=0.2)
)

# Apply style based on feature properties
for parcel in parcels:
    style = land_use_style.get_style(parcel)
    parcel.style = style.to_dict()
```

## Choropleth Maps

Create thematic maps based on numeric values:

```python
from gis_lib import ChoroplethStyle

# Create a choropleth style for population density
choropleth = ChoroplethStyle(
    "population_density",
    breaks=[100, 500, 1000, 5000, 10000],
    colors=["#ffffcc", "#c7e9b4", "#7fcdbb", "#41b6c4", "#2c7fb8", "#253494"]
)

# Apply to census tracts
for tract in census_tracts:
    style = choropleth.get_style(tract)
    tract.style = style.to_dict()
```

## Loading External Data

### GeoJSON

```python
map.add_geojson_layer(
    geojson_data,
    layer_name="my_geojson",
    style={"color": "blue", "weight": 2}
)
```

### Shapefiles

```python
map.add_shapefile(
    "/path/to/shapefile.zip",
    layer_name="shapefile_data",
    style={"color": "green", "fillOpacity": 0.3}
)
```

### GeoTIFF Rasters

The GIS library uses **geotiff.js**, **numpy**, and **matplotlib** for GeoTIFF processing:

```python
# Single-band with colormap (e.g., elevation data)
map.add_geotiff(
    "/assets/elevation.tif",
    opacity=0.7,
    colormap="terrain",  # Matplotlib colormap name
    vmin=0,              # Optional: min value for color scaling
    vmax=1000,           # Optional: max value for color scaling
    band=0               # Band index to display (0-indexed)
)

# RGB composite for satellite imagery (true-color)
map.add_geotiff(
    "/assets/satellite.tif",
    opacity=0.9,
    rgb_bands=[0, 1, 2]  # Red, Green, Blue band indices
)

# False-color composite (e.g., NIR-R-G for vegetation)
map.add_geotiff(
    "/assets/multispectral.tif",
    opacity=0.9,
    rgb_bands=[3, 0, 1]  # NIR as Red, Red as Green, Green as Blue
)
```

**Available colormaps** (for single-band mode):
- Perceptual: `"viridis"`, `"plasma"`, `"inferno"`, `"magma"`, `"cividis"`
- Sequential: `"Greys"`, `"Blues"`, `"Greens"`, `"Oranges"`, `"Reds"`
- Diverging: `"RdBu"`, `"RdYlGn"`, `"RdYlBu"`, `"Spectral"`
- Terrain: `"terrain"`, `"gist_earth"`
- And any other matplotlib colormap

**Features:**
- **RGB composite support** - Display satellite imagery in true color or false color
- **Automatic projection handling** - Works with any coordinate system:
  - Reads EPSG code from GeoTIFF metadata when available
  - Auto-detects common projections (Web Mercator, UTM zones, State Plane)
  - Falls back to trying multiple projections until one works
  - Supports geographic coordinates (WGS84, NAD83, NAD27) without conversion
- Automatic contrast stretching (2nd-98th percentile) for RGB composites
- Automatic value range detection for colormapped displays
- NoData value handling (transparent)
- Multi-band support (RGB, multispectral, single-band elevation, etc.)
- Full matplotlib colormap library
- Memory-efficient processing via geotiff.js

## Feature Collections

Work with multiple features as a group:

```python
from gis_lib import FeatureCollection, Point, Line, Polygon

# Create features
point = Point(37.7749, -122.4194, properties={"name": "Point 1"})
line = Line([[37.77, -122.45], [37.78, -122.43]], properties={"type": "road"})
polygon = Polygon(coords, properties={"type": "park"})

# Create collection
collection = FeatureCollection([point, line, polygon])

# Filter features by property
parks = collection.filter_by_property("type", "park")

# Convert to GeoJSON
geojson = collection.to_geojson()

# Add to map
map.add_geojson_layer(geojson, layer_name="features")
```

## Style Presets

The library includes ready-to-use style presets:

### Marker Presets
- `StylePresets.MARKER_DEFAULT` (blue)
- `StylePresets.MARKER_RED`
- `StylePresets.MARKER_GREEN`
- `StylePresets.MARKER_YELLOW`
- `StylePresets.MARKER_PURPLE`

### Line Presets
- `StylePresets.LINE_DEFAULT`
- `StylePresets.LINE_THIN`
- `StylePresets.LINE_THICK`
- `StylePresets.LINE_DASHED`
- `StylePresets.LINE_ROAD`
- `StylePresets.LINE_HIGHWAY`
- `StylePresets.LINE_RIVER`
- `StylePresets.LINE_TRAIL`

### Polygon Presets
- `StylePresets.POLYGON_DEFAULT`
- `StylePresets.POLYGON_PARK`
- `StylePresets.POLYGON_WATER`
- `StylePresets.POLYGON_BUILDING`
- `StylePresets.POLYGON_URBAN`
- `StylePresets.POLYGON_AGRICULTURE`
- `StylePresets.POLYGON_FOREST`

## Color Utilities

Generate colors for categorical or sequential data:

```python
from gis_lib import StylePresets

# Get categorical colors (for distinct categories)
colors = StylePresets.get_categorical_colors(5)
# Returns: ['#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00']

# Get sequential colors (for numeric ranges)
colors = StylePresets.get_sequential_colors(5, palette="blues")
# Returns graduated blue colors from light to dark
```

## Architecture

The GIS library is a standalone Leaflet-based mapping solution that provides:

**Core Technologies:**
- **Leaflet.js** - Interactive web mapping
- **geotiff.js** - GeoTIFF reading in the browser
- **proj4.js** - Coordinate projection handling
- **NumPy** - Raster data processing
- **Matplotlib** - Colormaps for visualization
- **Pillow** - Image generation

**Key Features:**
- High-level Python API for feature creation
- Automatic action queue for sequential map operations
- Automatic visibility detection for hidden containers (tabs)
- Universal projection support with auto-detection
- RGB composite support for satellite imagery
- Layer management and organization
- Comprehensive styling system

## Files

- `standalone_map.py` - Main GISMap class with Leaflet integration
- `features.py` - Feature classes (Point, Line, Polygon, etc.)
- `layers.py` - Layer management classes
- `styles.py` - Styling utilities and presets
- `raster.py` - Raster data handling utilities
- `demo.py` - Demo application
- `__init__.py` - Public API exports
- `README.md` - This documentation

## Using Maps in Tabs or Hidden Containers

The GISMap automatically handles being placed in hidden containers (like inactive tabs):

```python
# Create tabs
tabs = TabNav()
tabs.add_tab("Overview", "overview", content=overview_content, active=True)
tabs.add_tab("Map", "map", content=GISMap(center=[37.7749, -122.4194], zoom=12))

# That's it! The map will automatically fix its sizing when the tab becomes visible
# No manual event handlers or size fixes needed
```

### How It Works

1. **IntersectionObserver**: The map sets up an IntersectionObserver to detect when its container becomes visible
2. **Automatic Fix**: When visibility changes from hidden to visible, the map automatically:
   - Recalculates its dimensions
   - Re-centers the view
   - Refreshes tile rendering
3. **Multiple Iterations**: The fix runs at 0ms, 100ms, 300ms, and 600ms intervals to ensure proper rendering

### Manual Size Fix (Optional)

If you need to manually trigger a size fix (e.g., after dynamically resizing the container):

```python
map.fix_size_after_show()
```

## Finding GeoTIFF Data

Several sources provide free GeoTIFF elevation data:

### Public Data Sources:

1. **[USGS - The National Map](https://www.usgs.gov/the-national-map-data-delivery/gis-data-download)**
   - Free elevation data for the United States
   - Cloud Optimized GeoTIFF (COG) format
   - Various resolutions available

2. **[Global Elevation Data Download Tool](https://mapscaping.com/global-elevation-data-download-tool/)**
   - OpenTopography data access
   - SRTM, ASTER, ALOS World 3D datasets
   - GeoTIFF, ASCII Grid, or IMG formats

3. **[GIS Geography - Free Global DEM Data](https://gisgeography.com/free-global-dem-data-sources/)**
   - SRTM (30m resolution)
   - ASTER GDEM (30m resolution)
   - Copernicus DEM
   - GMTED2010

4. **[Rasterio Sample Data](https://github.com/rasterio/rasterio/raw/main/tests/data/RGB.byte.tif)**
   - Small test GeoTIFF (718x791 pixels)
   - Perfect for testing and examples
   - Direct download available

### Example GeoTIFF Files:

```python
# RGB satellite imagery (true-color composite)
map.add_geotiff(
    "/assets/RGB.byte.tif",
    opacity=0.9,
    rgb_bands=[0, 1, 2]  # Red, Green, Blue
)

# Elevation DEM with terrain colormap
map.add_geotiff(
    "/assets/dem_90m.tif",
    opacity=0.7,
    colormap="terrain",
    vmin=0,
    vmax=4000
)
```

## Dependencies

The GIS library requires these packages (automatically loaded in Pyodide):

**Python Packages (via micropip):**
- **numpy** - Raster data processing
- **matplotlib** - Colormaps for visualization
- **pillow** - PNG image generation

**JavaScript Libraries (bundled with Antioch):**
- **Leaflet.js** - Interactive mapping
- **geotiff.js** - GeoTIFF reading in browser
- **proj4.js** - Coordinate projection handling

All Python packages are available in [Pyodide 0.29.3+](https://pyodide.org/en/stable/usage/packages-in-pyodide.html) and are specified in `antioch.toml`.

## Future Enhancements

Potential additions for future versions:
- Spatial analysis tools (buffer, intersection, union)
- Raster algebra operations (band math, NDVI, etc.)
- Hillshade and slope generation from DEMs
- Vector data loading from shapefiles
- Geocoding and reverse geocoding
- Spatial queries and filters
- Animation and time-series support
- Drawing tools for user-created features
- Export to GeoJSON/KML
