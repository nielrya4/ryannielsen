"""
GIS Feature Classes - Point, Line, Polygon, Polyline

Provides high-level abstractions for working with geographic features.
These classes handle data conversion and work seamlessly with the Leaflet-based Map class.
"""
from typing import List, Dict, Tuple, Union, Optional, Any
import json


class Feature:
    """Base class for all geographic features."""

    def __init__(self, properties: Optional[Dict[str, Any]] = None, style: Optional[Dict[str, Any]] = None):
        """
        Initialize a feature.

        Args:
            properties: Attribute data for the feature (e.g., {"name": "City Hall", "population": 50000})
            style: Style properties for rendering (e.g., {"color": "red", "weight": 2})
        """
        self.properties = properties or {}
        self.style = style or {}
        self._id = None

    def to_geojson(self) -> Dict:
        """Convert feature to GeoJSON format."""
        raise NotImplementedError("Subclasses must implement to_geojson()")

    def to_leaflet(self) -> Dict:
        """Convert feature to Leaflet-compatible format."""
        # By default, use GeoJSON (Leaflet supports it)
        return self.to_geojson()


class Point(Feature):
    """A geographic point feature."""

    def __init__(self, lat: float, lng: float, properties: Optional[Dict[str, Any]] = None,
                 style: Optional[Dict[str, Any]] = None):
        """
        Create a point feature.

        Args:
            lat: Latitude
            lng: Longitude
            properties: Attribute data (e.g., {"name": "City Hall"})
            style: Marker style (e.g., {"color": "red", "icon": "marker"})
        """
        super().__init__(properties, style)
        self.lat = lat
        self.lng = lng

    def to_geojson(self) -> Dict:
        """Convert to GeoJSON Point."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [self.lng, self.lat]  # GeoJSON uses [lng, lat]
            },
            "properties": self.properties
        }

    def to_leaflet_marker(self) -> Dict:
        """Convert to Leaflet marker parameters."""
        return {
            "lat": self.lat,
            "lng": self.lng,
            "properties": self.properties,
            **self.style
        }

    @classmethod
    def from_coords(cls, coords: Union[Tuple[float, float], List[float]],
                    properties: Optional[Dict] = None, style: Optional[Dict] = None) -> 'Point':
        """
        Create a Point from coordinate tuple/list.

        Args:
            coords: (lat, lng) or [lat, lng]
            properties: Attribute data
            style: Marker style

        Returns:
            Point instance
        """
        return cls(coords[0], coords[1], properties, style)


class Line(Feature):
    """A geographic line feature (polyline)."""

    def __init__(self, coordinates: List[Union[Tuple[float, float], List[float]]],
                 properties: Optional[Dict[str, Any]] = None,
                 style: Optional[Dict[str, Any]] = None):
        """
        Create a line feature.

        Args:
            coordinates: List of [lat, lng] or (lat, lng) coordinate pairs
            properties: Attribute data (e.g., {"name": "Highway 101", "lanes": 4})
            style: Line style (e.g., {"color": "blue", "weight": 3, "opacity": 0.7})
        """
        super().__init__(properties, style)
        self.coordinates = [list(coord) for coord in coordinates]

    def to_geojson(self) -> Dict:
        """Convert to GeoJSON LineString."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[lng, lat] for lat, lng in self.coordinates]  # GeoJSON uses [lng, lat]
            },
            "properties": self.properties
        }

    def to_leaflet_polyline(self) -> Dict:
        """Convert to Leaflet polyline parameters."""
        return {
            "latlngs": [[lat, lng] for lat, lng in self.coordinates],
            "properties": self.properties,
            **self.style
        }


class Polyline(Line):
    """Alias for Line - a polyline with multiple connected segments."""
    pass


class Polygon(Feature):
    """A geographic polygon feature."""

    def __init__(self, coordinates: List[Union[Tuple[float, float], List[float]]],
                 holes: Optional[List[List[Union[Tuple[float, float], List[float]]]]] = None,
                 properties: Optional[Dict[str, Any]] = None,
                 style: Optional[Dict[str, Any]] = None):
        """
        Create a polygon feature.

        Args:
            coordinates: List of [lat, lng] or (lat, lng) coordinate pairs for the outer ring
            holes: Optional list of coordinate lists for interior holes
            properties: Attribute data (e.g., {"name": "City Boundary", "area_sq_km": 150})
            style: Polygon style (e.g., {"fillColor": "green", "fillOpacity": 0.3, "color": "darkgreen", "weight": 2})
        """
        super().__init__(properties, style)
        self.coordinates = [list(coord) for coord in coordinates]
        self.holes = [[list(coord) for coord in hole] for hole in (holes or [])]

    def to_geojson(self) -> Dict:
        """Convert to GeoJSON Polygon."""
        # First ring is exterior, subsequent rings are holes
        rings = [[[lng, lat] for lat, lng in self.coordinates]]
        for hole in self.holes:
            rings.append([[lng, lat] for lat, lng in hole])

        return {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": rings
            },
            "properties": self.properties
        }

    def to_leaflet_polygon(self) -> Dict:
        """Convert to Leaflet polygon parameters."""
        result = {
            "latlngs": [[lat, lng] for lat, lng in self.coordinates],
            "properties": self.properties,
            **self.style
        }

        # Add holes if present
        if self.holes:
            result["holes"] = [[[lat, lng] for lat, lng in hole] for hole in self.holes]

        return result


class MultiPoint(Feature):
    """A collection of point features."""

    def __init__(self, points: List[Point], properties: Optional[Dict[str, Any]] = None):
        """
        Create a multi-point feature.

        Args:
            points: List of Point instances
            properties: Shared attribute data for all points
        """
        super().__init__(properties)
        self.points = points

    def to_geojson(self) -> Dict:
        """Convert to GeoJSON MultiPoint."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "MultiPoint",
                "coordinates": [[point.lng, point.lat] for point in self.points]
            },
            "properties": self.properties
        }


class MultiLine(Feature):
    """A collection of line features."""

    def __init__(self, lines: List[Line], properties: Optional[Dict[str, Any]] = None):
        """
        Create a multi-line feature.

        Args:
            lines: List of Line instances
            properties: Shared attribute data for all lines
        """
        super().__init__(properties)
        self.lines = lines

    def to_geojson(self) -> Dict:
        """Convert to GeoJSON MultiLineString."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "MultiLineString",
                "coordinates": [
                    [[lng, lat] for lat, lng in line.coordinates]
                    for line in self.lines
                ]
            },
            "properties": self.properties
        }


class MultiPolygon(Feature):
    """A collection of polygon features."""

    def __init__(self, polygons: List[Polygon], properties: Optional[Dict[str, Any]] = None):
        """
        Create a multi-polygon feature.

        Args:
            polygons: List of Polygon instances
            properties: Shared attribute data for all polygons
        """
        super().__init__(properties)
        self.polygons = polygons

    def to_geojson(self) -> Dict:
        """Convert to GeoJSON MultiPolygon."""
        coordinates = []
        for polygon in self.polygons:
            rings = [[[lng, lat] for lat, lng in polygon.coordinates]]
            for hole in polygon.holes:
                rings.append([[lng, lat] for lat, lng in hole])
            coordinates.append(rings)

        return {
            "type": "Feature",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": coordinates
            },
            "properties": self.properties
        }


class FeatureCollection:
    """A collection of mixed feature types."""

    def __init__(self, features: List[Feature]):
        """
        Create a feature collection.

        Args:
            features: List of Feature instances (can be mixed types)
        """
        self.features = features

    def to_geojson(self) -> Dict:
        """Convert to GeoJSON FeatureCollection."""
        return {
            "type": "FeatureCollection",
            "features": [feature.to_geojson() for feature in self.features]
        }

    def to_json_string(self) -> str:
        """Convert to GeoJSON string."""
        return json.dumps(self.to_geojson())

    def add_feature(self, feature: Feature):
        """Add a feature to the collection."""
        self.features.append(feature)

    def remove_feature(self, feature: Feature):
        """Remove a feature from the collection."""
        if feature in self.features:
            self.features.remove(feature)

    def filter_by_property(self, key: str, value: Any) -> 'FeatureCollection':
        """
        Filter features by property value.

        Args:
            key: Property key to filter on
            value: Property value to match

        Returns:
            New FeatureCollection with matching features
        """
        matching = [f for f in self.features if f.properties.get(key) == value]
        return FeatureCollection(matching)

    def __len__(self):
        """Get number of features in collection."""
        return len(self.features)

    def __iter__(self):
        """Iterate over features."""
        return iter(self.features)
