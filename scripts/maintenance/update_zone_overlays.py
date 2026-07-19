"""Build compact CQ/WAZ and ITU zone overlay data from public KMZ files."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path
from defusedxml import ElementTree


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data" / "zone-overlays.json"
SOURCES = {
    "cq": {
        "name": "CQ/WAZ zones",
        "url": "https://g7vjr.org/wp-content/uploads/2019/08/WAZ-%40-IV3TMM-v1.2.kmz_.zip",
        "credit": "IV3TMM WAZ (@ IV3TMM) v1.2 via G7VJR",
    },
    "itu": {
        "name": "ITU zones",
        "url": "https://g7vjr.org/wp-content/uploads/2019/08/ITU-%40-IV3TMM-v1.1.kmz_.zip",
        "credit": "IV3TMM ITU (@ IV3TMM) v1.1 via G7VJR",
    },
}
KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_ENTRY_BYTES = 20 * 1024 * 1024


def download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "om0rx-radio-control/zone-data"})
    with urllib.request.urlopen(request, timeout=45) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
            raise ValueError("Zone overlay download exceeded the allowed size")
        payload = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(payload) > MAX_DOWNLOAD_BYTES:
            raise ValueError("Zone overlay download exceeded the allowed size")
        return payload


def extract_kml(payload: bytes) -> bytes:
    """Extract doc.kml from a zip/kmz payload, including one nested archive level."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for info in archive.infolist():
            if info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
                raise ValueError(f"Archive entry too large: {info.filename}")
        for name in archive.namelist():
            lowered = name.lower()
            if lowered.endswith(".kml"):
                return archive.read(name)
        for name in archive.namelist():
            lowered = name.lower()
            if lowered.endswith((".kmz", ".zip")) and "__macosx" not in lowered:
                return extract_kml(archive.read(name))
    raise ValueError("No KML document found in archive")


def parse_coordinates(text: str) -> list[list[float]]:
    points: list[list[float]] = []
    for token in re.split(r"\s+", text.strip()):
        if not token:
            continue
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = round(float(parts[0]), 4)
            lat = round(float(parts[1]), 4)
        except ValueError:
            continue
        if abs(lon) <= 180 and abs(lat) <= 90:
            points.append([lon, lat])
    return points


def simplify_line(points: list[list[float]], min_delta: float) -> list[list[float]]:
    if len(points) <= 2:
        return points
    simplified = [points[0]]
    last_lon, last_lat = points[0]
    for lon, lat in points[1:-1]:
        if abs(lon - last_lon) >= min_delta or abs(lat - last_lat) >= min_delta:
            simplified.append([lon, lat])
            last_lon, last_lat = lon, lat
    if simplified[-1] != points[-1]:
        simplified.append(points[-1])
    return simplified


def placemark_name(placemark: ElementTree.Element) -> str:
    name = placemark.find("kml:name", KML_NS)
    return (name.text or "").strip() if name is not None else ""


def parse_overlay(kind: str, source: dict[str, str], min_delta: float) -> dict[str, object]:
    kml = extract_kml(download_bytes(source["url"]))
    root = ElementTree.fromstring(kml)
    lines = []
    labels = []

    for placemark in root.findall(".//kml:Placemark", KML_NS):
        name = placemark_name(placemark)
        line_coords = placemark.find(".//kml:LineString/kml:coordinates", KML_NS)
        if line_coords is not None and line_coords.text:
            points = simplify_line(parse_coordinates(line_coords.text), min_delta)
            if len(points) >= 2:
                lines.append({"name": name, "points": points})
            continue

        point_coords = placemark.find(".//kml:Point/kml:coordinates", KML_NS)
        if point_coords is not None and point_coords.text:
            points = parse_coordinates(point_coords.text)
            match = re.search(r"(\d+)", name)
            if points and match:
                lon, lat = points[0]
                labels.append({
                    "zone": int(match.group(1)),
                    "label": f"{kind.upper()} {int(match.group(1))}",
                    "lon": lon,
                    "lat": lat,
                })

    return {
        "name": source["name"],
        "source": source["credit"],
        "url": source["url"],
        "lines": lines,
        "labels": sorted(labels, key=lambda item: item["zone"]),
    }


def build_zone_overlays(output: Path, min_delta: float) -> None:
    overlays = {
        kind: parse_overlay(kind, source, min_delta)
        for kind, source in SOURCES.items()
    }
    payload = {
        "version": 1,
        "generated_by": "scripts/maintenance/update_zone_overlays.py",
        "description": "Amateur radio CQ/WAZ and ITU boundary lines plus label points for visual overlays.",
        "overlays": overlays,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-delta", type=float, default=0.035)
    args = parser.parse_args()
    build_zone_overlays(args.output, args.min_delta)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
