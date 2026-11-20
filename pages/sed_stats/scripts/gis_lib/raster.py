"""
Raster Utilities

Utilities for working with raster data (GeoTIFF, imagery) in GIS applications.
"""
from typing import Optional, Dict, List, Tuple, Any
import base64
import json


class Raster:
    """Represents a georeferenced raster dataset."""

    def __init__(self, source: str, bounds: Optional[Dict] = None,
                 projection: str = "EPSG:4326", no_data_value: Optional[float] = None):
        """
        Initialize a raster dataset.

        Args:
            source: Path or URL to raster file
            bounds: Geographic bounds {"min_lat": ..., "max_lat": ..., "min_lng": ..., "max_lng": ...}
            projection: Projection/CRS string (e.g., "EPSG:4326", "EPSG:3857")
            no_data_value: Value representing no data/missing data
        """
        self.source = source
        self.bounds = bounds
        self.projection = projection
        self.no_data_value = no_data_value
        self.metadata = {}

    def get_bounds(self) -> Optional[Dict]:
        """Get the geographic bounds of the raster."""
        return self.bounds

    def to_leaflet_params(self, opacity: float = 1.0, colormap: Optional[str] = None) -> Dict:
        """
        Convert to parameters for Leaflet GeoTIFF rendering.

        Args:
            opacity: Raster opacity (0-1)
            colormap: Colormap name

        Returns:
            Dictionary of parameters
        """
        params = {
            "file_path": self.source,
            "opacity": opacity
        }

        if self.bounds:
            params["bounds"] = [
                [self.bounds["min_lat"], self.bounds["min_lng"]],
                [self.bounds["max_lat"], self.bounds["max_lng"]]
            ]

        return params


class ColorRamp:
    """Color ramp for visualizing raster data."""

    def __init__(self, colors: List[str], positions: Optional[List[float]] = None,
                 min_value: Optional[float] = None, max_value: Optional[float] = None):
        """
        Create a color ramp.

        Args:
            colors: List of color strings (hex or named)
            positions: Optional list of positions (0-1) for each color
            min_value: Minimum data value
            max_value: Maximum data value
        """
        self.colors = colors
        self.positions = positions or [i / (len(colors) - 1) for i in range(len(colors))]
        self.min_value = min_value
        self.max_value = max_value

    def to_matplotlib_cmap(self):
        """
        Convert to matplotlib colormap format.

        Note: Requires matplotlib to be available.
        """
        try:
            from matplotlib.colors import LinearSegmentedColormap
            import numpy as np

            # Convert hex colors to RGB
            colors_rgb = []
            for color in self.colors:
                if color.startswith('#'):
                    r = int(color[1:3], 16) / 255
                    g = int(color[3:5], 16) / 255
                    b = int(color[5:7], 16) / 255
                    colors_rgb.append((r, g, b))
                else:
                    # Assume named color, matplotlib will handle it
                    colors_rgb.append(color)

            return LinearSegmentedColormap.from_list('custom', list(zip(self.positions, colors_rgb)))
        except ImportError:
            raise ImportError("matplotlib is required for this operation")

    @classmethod
    def from_preset(cls, name: str, min_value: Optional[float] = None,
                   max_value: Optional[float] = None) -> 'ColorRamp':
        """
        Create a color ramp from a preset.

        Args:
            name: Preset name (e.g., "viridis", "terrain", "elevation", "temperature")
            min_value: Minimum data value
            max_value: Maximum data value

        Returns:
            ColorRamp instance
        """
        presets = {
            "viridis": ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"],
            "terrain": ["#333399", "#3366cc", "#66cc99", "#ccff66", "#ffcc66", "#ff9933", "#cc6633", "#996633"],
            "elevation": ["#0d5c0d", "#3d8b3d", "#6bb86b", "#9ace9a", "#c9e4c9", "#f0f0f0", "#e0c0a0", "#d0a080", "#c08060"],
            "temperature": ["#053061", "#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"],
            "grayscale": ["#000000", "#404040", "#808080", "#c0c0c0", "#ffffff"],
            "bathymetry": ["#00004d", "#000080", "#0000b3", "#0000e6", "#1a1aff", "#4d4dff", "#8080ff", "#b3b3ff"],
            "ndvi": ["#8b4513", "#cd853f", "#f4a460", "#ffe4b5", "#ffffe0", "#d0f0d0", "#90ee90", "#32cd32", "#228b22", "#006400"],
        }

        colors = presets.get(name.lower(), presets["viridis"])
        return cls(colors, min_value=min_value, max_value=max_value)


class RasterStats:
    """Statistics for raster data."""

    def __init__(self, min_value: float, max_value: float, mean: float,
                 std: float, count: int, no_data_count: int = 0):
        """
        Initialize raster statistics.

        Args:
            min_value: Minimum value
            max_value: Maximum value
            mean: Mean value
            std: Standard deviation
            count: Number of valid pixels
            no_data_count: Number of no-data pixels
        """
        self.min = min_value
        self.max = max_value
        self.mean = mean
        self.std = std
        self.count = count
        self.no_data_count = no_data_count

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "min": self.min,
            "max": self.max,
            "mean": self.mean,
            "std": self.std,
            "count": self.count,
            "no_data_count": self.no_data_count
        }


def create_hillshade(elevation_raster: Raster, azimuth: float = 315,
                     altitude: float = 45, z_factor: float = 1.0) -> Raster:
    """
    Create a hillshade from an elevation raster.

    Args:
        elevation_raster: Input elevation raster
        azimuth: Light source azimuth (0-360 degrees)
        altitude: Light source altitude (0-90 degrees)
        z_factor: Vertical exaggeration factor

    Returns:
        Hillshade raster

    Note:
        This is a placeholder. Actual implementation would require
        numpy and raster processing libraries like rasterio.
    """
    # TODO: Implement hillshade calculation
    # Would use numpy gradient calculation and illumination model
    raise NotImplementedError("Hillshade generation requires rasterio and numpy")


def calculate_slope(elevation_raster: Raster, units: str = "degrees") -> Raster:
    """
    Calculate slope from an elevation raster.

    Args:
        elevation_raster: Input elevation raster
        units: Output units ("degrees" or "percent")

    Returns:
        Slope raster

    Note:
        This is a placeholder. Actual implementation would require
        numpy and raster processing libraries.
    """
    # TODO: Implement slope calculation
    raise NotImplementedError("Slope calculation requires rasterio and numpy")


def reproject_raster(raster: Raster, target_crs: str) -> Raster:
    """
    Reproject a raster to a different coordinate system.

    Args:
        raster: Input raster
        target_crs: Target CRS (e.g., "EPSG:3857")

    Returns:
        Reprojected raster

    Note:
        This is a placeholder. Actual implementation would require
        rasterio or gdal.
    """
    # TODO: Implement reprojection
    raise NotImplementedError("Raster reprojection requires rasterio or gdal")


def clip_raster(raster: Raster, bounds: Dict) -> Raster:
    """
    Clip a raster to specified bounds.

    Args:
        raster: Input raster
        bounds: Bounding box {"min_lat": ..., "max_lat": ..., "min_lng": ..., "max_lng": ...}

    Returns:
        Clipped raster

    Note:
        This is a placeholder. Actual implementation would require
        rasterio.
    """
    # TODO: Implement clipping
    raise NotImplementedError("Raster clipping requires rasterio")
