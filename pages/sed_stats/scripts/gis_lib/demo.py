"""
GIS Library Demo

A simple demo application showing how to use the GIS library with Antioch.
Run this file to see the GIS library in action.
"""
import sys
sys.path.insert(0, '/home/ryan/PycharmProjects/mpGraph/scripts')

from gis_lib import GISMap


def create_demo_map():
    """Create a demonstration map with various features."""

    # Create a map centered on San Francisco
    print("Creating standalone GIS map...")
    gis_map = GISMap(
        center=[37.7749, -122.4194],
        zoom=12,
        width="100%",
        height="600px"
    )

    # Add point markers
    print("Queueing point markers...")
    gis_map.add_point(
        37.7749, -122.4194,
        properties={"name": "City Hall", "type": "government"},
        popup="<b>San Francisco City Hall</b><br>Civic Center"
    )

    gis_map.add_point(
        37.8080, -122.4177,
        properties={"name": "Fisherman's Wharf"},
        popup="<b>Fisherman's Wharf</b><br>Popular tourist destination"
    )

    # Add a polyline (road)
    print("Queueing polyline...")
    market_street = [
        [37.7938, -122.3993],
        [37.7897, -122.4042],
        [37.7857, -122.4091],
        [37.7816, -122.4140]
    ]
    gis_map.add_line(
        market_street,
        properties={"name": "Market Street"},
        color="#ff6600",
        weight=4,
        opacity=0.7
    )

    # Add polygons (parks)
    print("Queueing polygons...")
    golden_gate_park = [
        [37.7694, -122.5107],
        [37.7694, -122.4542],
        [37.7750, -122.4542],
        [37.7750, -122.5107]
    ]
    gis_map.add_polygon(
        golden_gate_park,
        properties={"name": "Golden Gate Park", "area_acres": 1017},
        fill_color="#228B22",
        fill_opacity=0.3,
        color="#006400"
    )

    # Add a circle
    print("Queueing circle...")
    gis_map.add_circle(
        37.7749, -122.4194,
        radius=500,  # 500 meters
        fill_color="#3388ff",
        fill_opacity=0.2,
        color="#0066cc"
    )

    # Add GeoTIFF raster overlays
    print("Queueing GeoTIFFs...")

    # RGB satellite imagery - true color composite (Bahamas area)
    # Use rgb_bands to display as true-color image instead of colormap
    gis_map.add_geotiff(
        "/assets/RGB.byte.tif",
        opacity=0.9,
        rgb_bands=[0, 1, 2]  # Red, Green, Blue bands for true-color
    )

    # DEM (elevation) with colormap - California Sierra Nevada / Yosemite
    # Single-band data displayed with terrain colormap
    gis_map.add_geotiff(
        "/assets/dem_90m.tif",
        opacity=0.6,
        colormap="terrain",  # Great for elevation: "terrain", "gist_earth", "RdYlGn"
        band=0,
        vmin=0,    # Sea level
        vmax=4000  # ~4000m peak elevation
    )

    print("GIS map created! All actions queued and will execute when ready.")
    print("Features: 2 points, 1 line, 1 polygon, 1 circle, 2 GeoTIFFs")
    print("\nGeoTIFF 1: RGB satellite (Bahamas ~24°N, 78°W) - true-color composite")
    print("GeoTIFF 2: DEM elevation (California ~37°N, 119°W) - terrain colormap")
    print("\nFor satellite imagery: use rgb_bands=[R, G, B] for true-color")
    print("For elevation/analysis: use colormap='terrain' or other matplotlib colormap")

    return gis_map


# Export the function with a simpler name
demo_map = create_demo_map


if __name__ == "__main__":
    # Create the demo map
    map_instance = create_demo_map()

    print("\n" + "="*60)
    print("GIS Library Demo")
    print("="*60)
    print("\nThe demo map has been created with the following layers:")
    for layer_name, layer in map_instance.layers.items():
        print(f"  - {layer_name}: {len(layer.features)} features")

    print("\nTo use this map in an Antioch application:")
    print("  1. Import the GIS library: from gis_lib import GISMap")
    print("  2. Create a map: map = GISMap(center=[lat, lng], zoom=12)")
    print("  3. Add features using map.add_point(), map.add_line(), map.add_polygon()")
    print("  4. Add the map to your application's UI")
    print("\nSee examples.py for more detailed usage examples.")
    print("See README.md for complete documentation.")
