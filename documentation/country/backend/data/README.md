# Backend data

Put ONE of these files here:

- `countries-110m.json`  — a **GeoJSON** FeatureCollection of world countries (you may pre-convert from world-atlas TopoJSON).
- `ne_countries_110m.geojson` — Natural Earth GeoJSON.

If you only have TopoJSON, either:
1) Serve it directly to the frontend (recommended), or
2) Convert to GeoJSON during build (e.g., `mapshaper -i countries-110m.json format=geojson -o countries.geojson`).
