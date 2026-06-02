import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ZONE_OVERLAYS = ROOT / "data" / "zone-overlays.json"


def test_zone_overlay_asset_has_expected_layers():
    payload = json.loads(ZONE_OVERLAYS.read_text(encoding="utf-8"))
    overlays = payload["overlays"]

    assert set(overlays) == {"cq", "itu"}
    assert len(overlays["cq"]["labels"]) == 40
    assert len(overlays["itu"]["labels"]) == 90
    assert len(overlays["cq"]["lines"]) >= 35
    assert len(overlays["itu"]["lines"]) >= 70


def test_zone_overlay_lines_have_valid_coordinates():
    payload = json.loads(ZONE_OVERLAYS.read_text(encoding="utf-8"))
    for overlay in payload["overlays"].values():
        point_count = 0
        for line in overlay["lines"]:
            assert len(line["points"]) >= 2
            for lon, lat in line["points"]:
                assert -180 <= lon <= 180
                assert -90 <= lat <= 90
                point_count += 1
        assert point_count >= 1000
