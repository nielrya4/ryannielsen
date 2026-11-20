"""
GIS Styling Utilities

Provides classes and utilities for styling geographic features.
"""
from typing import Dict, Optional, Union, List, Callable, Any


class Style:
    """Base class for feature styles."""

    def __init__(self, **kwargs):
        """
        Create a style with arbitrary properties.

        Common properties for all features:
            - opacity: Overall opacity (0-1)
            - className: CSS class name

        Args:
            **kwargs: Style properties
        """
        self.properties = kwargs

    def to_dict(self) -> Dict:
        """Convert style to dictionary."""
        return self.properties.copy()

    def merge(self, other: 'Style') -> 'Style':
        """
        Merge with another style (other takes precedence).

        Args:
            other: Style to merge with

        Returns:
            New merged Style
        """
        merged = self.properties.copy()
        merged.update(other.properties)
        return Style(**merged)


class MarkerStyle(Style):
    """Style for point markers."""

    def __init__(self, color: str = "blue", icon: Optional[str] = None,
                 icon_size: Optional[tuple] = None, icon_anchor: Optional[tuple] = None,
                 popup_anchor: Optional[tuple] = None, **kwargs):
        """
        Create a marker style.

        Args:
            color: Marker color (hex or named color)
            icon: URL to custom icon image
            icon_size: Icon size as (width, height) in pixels
            icon_anchor: Point of the icon which corresponds to marker's location as (x, y)
            popup_anchor: Point where popup should open relative to icon anchor as (x, y)
            **kwargs: Additional style properties
        """
        super().__init__(
            color=color,
            icon=icon,
            icon_size=icon_size,
            icon_anchor=icon_anchor,
            popup_anchor=popup_anchor,
            **kwargs
        )


class LineStyle(Style):
    """Style for lines and polylines."""

    def __init__(self, color: str = "#3388ff", weight: int = 3,
                 opacity: float = 1.0, line_cap: str = "round",
                 line_join: str = "round", dash_array: Optional[str] = None,
                 dash_offset: Optional[str] = None, **kwargs):
        """
        Create a line style.

        Args:
            color: Stroke color (hex or named color)
            weight: Stroke width in pixels
            opacity: Stroke opacity (0-1)
            line_cap: Line cap style ("butt", "round", "square")
            line_join: Line join style ("miter", "round", "bevel")
            dash_array: Dash pattern string (e.g., "5, 10")
            dash_offset: Distance into dash pattern to start
            **kwargs: Additional style properties
        """
        super().__init__(
            color=color,
            weight=weight,
            opacity=opacity,
            lineCap=line_cap,
            lineJoin=line_join,
            dashArray=dash_array,
            dashOffset=dash_offset,
            **kwargs
        )


class PolygonStyle(Style):
    """Style for polygons."""

    def __init__(self, fill_color: str = "#3388ff", fill_opacity: float = 0.2,
                 color: str = "#3388ff", weight: int = 2, opacity: float = 1.0,
                 line_cap: str = "round", line_join: str = "round",
                 dash_array: Optional[str] = None, **kwargs):
        """
        Create a polygon style.

        Args:
            fill_color: Fill color (hex or named color)
            fill_opacity: Fill opacity (0-1)
            color: Border color (hex or named color)
            weight: Border width in pixels
            opacity: Border opacity (0-1)
            line_cap: Line cap style for border
            line_join: Line join style for border
            dash_array: Dash pattern for border
            **kwargs: Additional style properties
        """
        super().__init__(
            fillColor=fill_color,
            fillOpacity=fill_opacity,
            color=color,
            weight=weight,
            opacity=opacity,
            lineCap=line_cap,
            lineJoin=line_join,
            dashArray=dash_array,
            **kwargs
        )


class StylePresets:
    """Predefined style presets for common use cases."""

    # Marker presets
    MARKER_DEFAULT = MarkerStyle(color="blue")
    MARKER_RED = MarkerStyle(color="red")
    MARKER_GREEN = MarkerStyle(color="green")
    MARKER_YELLOW = MarkerStyle(color="gold")
    MARKER_PURPLE = MarkerStyle(color="purple")

    # Line presets
    LINE_DEFAULT = LineStyle(color="#3388ff", weight=3)
    LINE_THIN = LineStyle(color="#3388ff", weight=1)
    LINE_THICK = LineStyle(color="#3388ff", weight=5)
    LINE_DASHED = LineStyle(color="#3388ff", weight=2, dash_array="5, 10")
    LINE_ROAD = LineStyle(color="#ff8800", weight=4, opacity=0.8)
    LINE_HIGHWAY = LineStyle(color="#ff0000", weight=6, opacity=0.9)
    LINE_RIVER = LineStyle(color="#0066ff", weight=3, opacity=0.7)
    LINE_TRAIL = LineStyle(color="#8B4513", weight=2, dash_array="5, 5")

    # Polygon presets
    POLYGON_DEFAULT = PolygonStyle(fill_color="#3388ff", fill_opacity=0.2, color="#3388ff", weight=2)
    POLYGON_PARK = PolygonStyle(fill_color="#228B22", fill_opacity=0.3, color="#006400", weight=2)
    POLYGON_WATER = PolygonStyle(fill_color="#0066ff", fill_opacity=0.3, color="#003399", weight=1)
    POLYGON_BUILDING = PolygonStyle(fill_color="#888888", fill_opacity=0.5, color="#333333", weight=1)
    POLYGON_URBAN = PolygonStyle(fill_color="#ff6600", fill_opacity=0.25, color="#cc5200", weight=2)
    POLYGON_AGRICULTURE = PolygonStyle(fill_color="#FFFF99", fill_opacity=0.4, color="#CCCC00", weight=1)
    POLYGON_FOREST = PolygonStyle(fill_color="#228B22", fill_opacity=0.4, color="#006400", weight=1)

    @classmethod
    def get_categorical_colors(cls, n_categories: int) -> List[str]:
        """
        Get a list of visually distinct colors for categorical data.

        Args:
            n_categories: Number of categories needed

        Returns:
            List of hex color strings
        """
        # Color brewer qualitative palette
        colors = [
            "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
            "#ffff33", "#a65628", "#f781bf", "#999999", "#66c2a5",
            "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854", "#ffd92f"
        ]

        # Repeat colors if more categories than colors
        while len(colors) < n_categories:
            colors.extend(colors)

        return colors[:n_categories]

    @classmethod
    def get_sequential_colors(cls, n_bins: int, palette: str = "blues") -> List[str]:
        """
        Get a list of sequential colors for numeric data.

        Args:
            n_bins: Number of bins/classes needed
            palette: Color palette name ("blues", "greens", "reds", "purples", "oranges")

        Returns:
            List of hex color strings
        """
        palettes = {
            "blues": ["#f7fbff", "#deebf7", "#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#08519c", "#08306b"],
            "greens": ["#f7fcf5", "#e5f5e0", "#c7e9c0", "#a1d99b", "#74c476", "#41ab5d", "#238b45", "#006d2c", "#00441b"],
            "reds": ["#fff5f0", "#fee0d2", "#fcbba1", "#fc9272", "#fb6a4a", "#ef3b2c", "#cb181d", "#a50f15", "#67000d"],
            "purples": ["#fcfbfd", "#efedf5", "#dadaeb", "#bcbddc", "#9e9ac8", "#807dba", "#6a51a3", "#54278f", "#3f007d"],
            "oranges": ["#fff5eb", "#fee6ce", "#fdd0a2", "#fdae6b", "#fd8d3c", "#f16913", "#d94801", "#a63603", "#7f2704"]
        }

        palette_colors = palettes.get(palette.lower(), palettes["blues"])

        # Interpolate if n_bins doesn't match palette length
        if n_bins <= len(palette_colors):
            # Sample evenly from palette
            step = len(palette_colors) / n_bins
            return [palette_colors[int(i * step)] for i in range(n_bins)]
        else:
            # Return all colors and repeat the darkest
            return palette_colors + [palette_colors[-1]] * (n_bins - len(palette_colors))


class ConditionalStyle:
    """Style features based on their properties."""

    def __init__(self, property_name: str, style_map: Dict[Any, Style],
                 default_style: Optional[Style] = None):
        """
        Create a conditional style based on a property value.

        Args:
            property_name: Name of the property to base styling on
            style_map: Dictionary mapping property values to styles
            default_style: Style to use if property value not in style_map

        Example:
            >>> style = ConditionalStyle(
            ...     "type",
            ...     {
            ...         "residential": PolygonStyle(fill_color="yellow"),
            ...         "commercial": PolygonStyle(fill_color="red"),
            ...         "industrial": PolygonStyle(fill_color="purple")
            ...     },
            ...     default_style=PolygonStyle(fill_color="gray")
            ... )
        """
        self.property_name = property_name
        self.style_map = style_map
        self.default_style = default_style or Style()

    def get_style(self, feature) -> Style:
        """
        Get the appropriate style for a feature.

        Args:
            feature: Feature to style

        Returns:
            Style object
        """
        prop_value = feature.properties.get(self.property_name)
        return self.style_map.get(prop_value, self.default_style)


class ChoroplethStyle:
    """Style polygons based on numeric property values."""

    def __init__(self, property_name: str, breaks: List[float],
                 colors: List[str], default_color: str = "#cccccc"):
        """
        Create a choropleth style.

        Args:
            property_name: Name of numeric property to base colors on
            breaks: List of break values (must be sorted)
            colors: List of colors (length must be len(breaks) + 1)
            default_color: Color for features with missing/invalid values

        Example:
            >>> style = ChoroplethStyle(
            ...     "population",
            ...     [1000, 5000, 10000, 50000],
            ...     ["#ffffcc", "#c7e9b4", "#7fcdbb", "#41b6c4", "#225ea8"]
            ... )
        """
        if len(colors) != len(breaks) + 1:
            raise ValueError("Number of colors must be len(breaks) + 1")

        self.property_name = property_name
        self.breaks = sorted(breaks)
        self.colors = colors
        self.default_color = default_color

    def get_style(self, feature) -> PolygonStyle:
        """
        Get the appropriate style for a feature.

        Args:
            feature: Feature to style

        Returns:
            PolygonStyle object
        """
        value = feature.properties.get(self.property_name)

        if value is None or not isinstance(value, (int, float)):
            return PolygonStyle(fill_color=self.default_color)

        # Find the appropriate color bin
        color_idx = 0
        for i, break_val in enumerate(self.breaks):
            if value > break_val:
                color_idx = i + 1
            else:
                break

        return PolygonStyle(fill_color=self.colors[color_idx])
