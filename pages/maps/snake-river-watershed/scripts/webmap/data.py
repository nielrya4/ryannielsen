"""The study's results, as exported by export_web_map.py into assets/."""
import json


def read_asset(name):
    """Text of an asset; Antioch copies assets/ into Pyodide's filesystem at /assets."""
    with open(f"/assets/{name}") as f:
        return f.read()


WATERSHEDS_TEXT = read_asset("watersheds.geojson")
RIVERS_TEXT = read_asset("rivers.geojson")
SAMPLES_TEXT = read_asset("samples.geojson")
CONFIG = json.loads(read_asset("layers.json"))

WATERSHEDS = json.loads(WATERSHEDS_TEXT)
PROPS = {f["properties"]["id"]: f["properties"] for f in WATERSHEDS["features"]}
LAYERS = {layer["id"]: layer for layer in CONFIG["layers"]}
POLYMERS = CONFIG["polymers"]
SINK = CONFIG["sink"]
MODEL = CONFIG["model"]


def bounds():
    """[[south, west], [north, east]] of the watersheds."""
    points = []
    for feature in WATERSHEDS["features"]:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" \
            else geometry["coordinates"]
        points += [pt for polygon in polygons for ring in polygon for pt in ring]
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]
