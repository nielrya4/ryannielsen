"""
GIS Library for Antioch

A high-level GIS library for working with geographic data in Leaflet maps.
Makes it easy to create and display points, lines, polygons, and rasters.

Example:
    >>> from gis_lib import GISMap, Point, Polygon, VectorLayer
    >>> from gis_lib import StylePresets, PolygonStyle
    >>>
    >>> # Create a map
    >>> map = GISMap(center=[37.7749, -122.4194], zoom=12)
    >>>
    >>> # Add a point
    >>> point = map.add_point(37.7749, -122.4194,
    ...                       properties={"name": "San Francisco"},
    ...                       style=StylePresets.MARKER_RED)
    >>>
    >>> # Add a polygon
    >>> coords = [[37.7, -122.5], [37.7, -122.3], [37.8, -122.3], [37.8, -122.5]]
    >>> polygon = map.add_polygon(coords, style=StylePresets.POLYGON_PARK)
    >>>
    >>> # Work with layers
    >>> layer = VectorLayer("parks")
    >>> layer.add_feature(polygon)
    >>> map.add_layer(layer)
"""

# Main map class (standalone implementation)
from .standalone_map import GISMap

# Feature classes
from .features import (
    Feature,
    Point,
    Line,
    Polyline,
    Polygon,
    MultiPoint,
    MultiLine,
    MultiPolygon,
    FeatureCollection
)

# Layer classes
from .layers import (
    Layer,
    VectorLayer,
    RasterLayer,
    LayerGroup
)

# Styling
from .styles import (
    Style,
    MarkerStyle,
    LineStyle,
    PolygonStyle,
    StylePresets,
    ConditionalStyle,
    ChoroplethStyle
)

# Raster utilities
from .raster import (
    Raster,
    ColorRamp,
    RasterStats
)

__all__ = [
    # Map
    'GISMap',

    # Features
    'Feature',
    'Point',
    'Line',
    'Polyline',
    'Polygon',
    'MultiPoint',
    'MultiLine',
    'MultiPolygon',
    'FeatureCollection',

    # Layers
    'Layer',
    'VectorLayer',
    'RasterLayer',
    'LayerGroup',

    # Styles
    'Style',
    'MarkerStyle',
    'LineStyle',
    'PolygonStyle',
    'StylePresets',
    'ConditionalStyle',
    'ChoroplethStyle',

    # Raster
    'Raster',
    'ColorRamp',
    'RasterStats',
]

__version__ = '0.1.0'
