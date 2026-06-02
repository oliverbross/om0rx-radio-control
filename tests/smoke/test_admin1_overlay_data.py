import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ADMIN1_OVERLAYS = ROOT / "data" / "visual-admin1-us-ca.geojson"


def iter_coordinates(geometry):
    coords = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        polygons = [coords]
    elif geometry["type"] == "MultiPolygon":
        polygons = coords
    else:
        raise AssertionError(f"Unexpected geometry type: {geometry['type']}")

    for polygon in polygons:
        for ring in polygon:
            for lon, lat in ring:
                yield lon, lat


def test_admin1_overlay_asset_has_expected_regions():
    payload = json.loads(ADMIN1_OVERLAYS.read_text(encoding="utf-8"))
    features = payload["features"]
    us = [item for item in features if item["properties"]["admin"] == "United States of America"]
    ca = [item for item in features if item["properties"]["admin"] == "Canada"]
    labels = {item["properties"]["postal"] for item in features}

    assert len(us) == 51
    assert len(ca) == 13
    assert {"CA", "TX", "NY", "ON", "QC", "BC"}.issubset(labels)


def test_admin1_overlay_coordinates_are_valid():
    payload = json.loads(ADMIN1_OVERLAYS.read_text(encoding="utf-8"))
    point_count = 0
    for feature in payload["features"]:
        props = feature["properties"]
        assert props["postal"]
        assert props["name"]
        for lon, lat in iter_coordinates(feature["geometry"]):
            assert -180 <= lon <= 180
            assert -90 <= lat <= 90
            point_count += 1

    assert point_count > 1000
