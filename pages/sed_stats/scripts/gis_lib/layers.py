"""
GIS Layer Management

Provides classes for organizing and managing geographic features in layers.
"""
from typing import List, Dict, Optional, Any, Union
from .features import Feature, FeatureCollection, Point, Line, Polygon, Polyline


class Layer:
    """A layer containing geographic features with shared properties."""

    def __init__(self, name: str, features: Optional[List[Feature]] = None,
                 visible: bool = True, opacity: float = 1.0,
                 style: Optional[Dict[str, Any]] = None):
        """
        Create a layer.

        Args:
            name: Layer name
            features: List of features to add to the layer
            visible: Whether layer is visible by default
            opacity: Layer opacity (0-1)
            style: Default style for all features in this layer
        """
        self.name = name
        self.features = features or []
        self.visible = visible
        self.opacity = opacity
        self.style = style or {}
        self._map_objects = []  # Store references to Leaflet objects

    def add_feature(self, feature: Feature):
        """Add a feature to the layer."""
        self.features.append(feature)

    def add_features(self, features: List[Feature]):
        """Add multiple features to the layer."""
        self.features.extend(features)

    def remove_feature(self, feature: Feature):
        """Remove a feature from the layer."""
        if feature in self.features:
            self.features.remove(feature)

    def clear(self):
        """Remove all features from the layer."""
        self.features = []
        self._map_objects = []

    def to_feature_collection(self) -> FeatureCollection:
        """Convert layer to a FeatureCollection."""
        return FeatureCollection(self.features)

    def to_geojson(self) -> Dict:
        """Convert layer to GeoJSON FeatureCollection."""
        return self.to_feature_collection().to_geojson()

    def filter_by_property(self, key: str, value: Any) -> 'Layer':
        """
        Create a new layer with features matching a property value.

        Args:
            key: Property key to filter on
            value: Property value to match

        Returns:
            New Layer with matching features
        """
        matching = [f for f in self.features if f.properties.get(key) == value]
        return Layer(f"{self.name}_filtered", matching, self.visible, self.opacity, self.style)

    def get_bounds(self) -> Optional[Dict]:
        """
        Calculate bounding box for all features in the layer.

        Returns:
            Dictionary with min_lat, max_lat, min_lng, max_lng or None if no features
        """
        if not self.features:
            return None

        lats = []
        lngs = []

        for feature in self.features:
            if isinstance(feature, Point):
                lats.append(feature.lat)
                lngs.append(feature.lng)
            elif isinstance(feature, (Line, Polyline, Polygon)):
                for lat, lng in feature.coordinates:
                    lats.append(lat)
                    lngs.append(lng)

        if not lats:
            return None

        return {
            "min_lat": min(lats),
            "max_lat": max(lats),
            "min_lng": min(lngs),
            "max_lng": max(lngs)
        }

    def __len__(self):
        """Get number of features in layer."""
        return len(self.features)

    def __iter__(self):
        """Iterate over features."""
        return iter(self.features)


class VectorLayer(Layer):
    """A layer specifically for vector features (points, lines, polygons)."""

    def __init__(self, name: str, features: Optional[List[Feature]] = None,
                 visible: bool = True, opacity: float = 1.0,
                 style: Optional[Dict[str, Any]] = None,
                 interactive: bool = True,
                 popup_template: Optional[str] = None):
        """
        Create a vector layer.

        Args:
            name: Layer name
            features: List of features
            visible: Whether layer is visible
            opacity: Layer opacity (0-1)
            style: Default style for features
            interactive: Whether features can be clicked/hovered
            popup_template: Template string for popups (e.g., "Name: {name}, Pop: {population}")
        """
        super().__init__(name, features, visible, opacity, style)
        self.interactive = interactive
        self.popup_template = popup_template

    def generate_popup(self, feature: Feature) -> Optional[str]:
        """
        Generate popup HTML for a feature using the template.

        Args:
            feature: The feature to generate popup for

        Returns:
            HTML string or None if no template
        """
        if not self.popup_template:
            return None

        try:
            return self.popup_template.format(**feature.properties)
        except KeyError:
            # If template references missing properties, show all properties
            props_html = "<br>".join([f"{k}: {v}" for k, v in feature.properties.items()])
            return f"<strong>{self.name}</strong><br>{props_html}"


class RasterLayer(Layer):
    """A layer for raster data (GeoTIFF, images with georeferencing)."""

    def __init__(self, name: str, source: str, bounds: Optional[Dict] = None,
                 visible: bool = True, opacity: float = 1.0,
                 colormap: Optional[str] = None,
                 min_value: Optional[float] = None,
                 max_value: Optional[float] = None):
        """
        Create a raster layer.

        Args:
            name: Layer name
            source: Path or URL to raster file (GeoTIFF)
            bounds: Geographic bounds {"min_lat": ..., "max_lat": ..., "min_lng": ..., "max_lng": ...}
            visible: Whether layer is visible
            opacity: Layer opacity (0-1)
            colormap: Colormap name for rendering (e.g., "viridis", "terrain")
            min_value: Minimum value for color scaling
            max_value: Maximum value for color scaling
        """
        super().__init__(name, [], visible, opacity)
        self.source = source
        self.bounds = bounds
        self.colormap = colormap
        self.min_value = min_value
        self.max_value = max_value
        self.raster_type = self._infer_raster_type(source)

    def _infer_raster_type(self, source: str) -> str:
        """Infer raster type from file extension."""
        source_lower = source.lower()
        if source_lower.endswith('.tif') or source_lower.endswith('.tiff'):
            return 'geotiff'
        elif source_lower.endswith(('.png', '.jpg', '.jpeg')):
            return 'image'
        else:
            return 'unknown'


class LayerGroup:
    """A group of layers that can be managed together."""

    def __init__(self, name: str, layers: Optional[List[Layer]] = None):
        """
        Create a layer group.

        Args:
            name: Group name
            layers: List of layers in the group
        """
        self.name = name
        self.layers = layers or []

    def add_layer(self, layer: Layer):
        """Add a layer to the group."""
        self.layers.append(layer)

    def remove_layer(self, layer: Layer):
        """Remove a layer from the group."""
        if layer in self.layers:
            self.layers.remove(layer)

    def get_layer(self, name: str) -> Optional[Layer]:
        """Get a layer by name."""
        for layer in self.layers:
            if layer.name == name:
                return layer
        return None

    def show_all(self):
        """Make all layers in the group visible."""
        for layer in self.layers:
            layer.visible = True

    def hide_all(self):
        """Make all layers in the group invisible."""
        for layer in self.layers:
            layer.visible = False

    def set_opacity(self, opacity: float):
        """Set opacity for all layers in the group."""
        for layer in self.layers:
            layer.opacity = opacity

    def __len__(self):
        """Get number of layers in group."""
        return len(self.layers)

    def __iter__(self):
        """Iterate over layers."""
        return iter(self.layers)
