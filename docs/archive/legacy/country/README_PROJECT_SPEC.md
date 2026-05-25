# Country Overlay Modal – Project Spec

This document describes how to add an **offline country map overlay** into your existing Vue.js app with a Python backend. It includes two frontend options (pure SVG via `d3-geo` and Leaflet) and a simple FastAPI service that serves country polygons locally. Use whichever frontend fits your stack best.

---

## Goals

- Replace the static “cards” modal with a **map-first modal** that highlights the DXCC country and overlays station facts (Continent, CQ Zone, DXCC, Lat/Lon, Grid).
- **Offline-first**: polygons are stored locally; no external tile APIs.
- Clean dark theme to match the current UI.

---

## Directory layout (proposed)

```
/frontend
  /src/components
    CountryInfoModal.vue          # wrapper modal + overlay (common)
    WorldAtlasLocal.vue           # d3-geo (SVG) implementation
    LeafletCountryModal.vue       # Leaflet implementation (optional)
  /src/assets
    countries-110m.json           # TopoJSON (world-atlas)  — place here
    ne_countries_110m.geojson     # GeoJSON (Natural Earth) — alternative
/backend
  /fastapi
    main.py
    requirements.txt
  /data
    README.md
```

> **Choose one** of: `countries-110m.json` (TopoJSON) or `ne_countries_110m.geojson` (GeoJSON). The code supports both.

---

## Data sources (download once and commit)

1) **TopoJSON** (smaller):
- `countries-110m.json` from the `world-atlas` package (MIT):
  ```bash
  curl -L -o frontend/src/assets/countries-110m.json     https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json
  ```

2) **GeoJSON** (nicer detail, larger):
- Natural Earth “Admin 0 – Countries” (110m or 50m) GeoJSON:
  https://www.naturalearthdata.com/downloads/110m-cultural-vectors/

---

## Frontend (Vue 3)

We provide **two components**. Both are tailored to your fields and accept the data you already show today.

### A) Pure SVG with d3-geo (offline, no tiles)

- File: `WorldAtlasLocal.vue` (included in this bundle)
- Import in your modal wrapper: `CountryInfoModal.vue`

**Props to pass** (from your store/row):
```vue
<WorldAtlasLocal
  :lat="38" :lon="23.7"                 
  countryName="Greece"                
  continent="EU" 
  :cqZone="20" 
  :dxccId="236"
  grid="KM18AF97"
  :dxLat="null" :dxLon="null"        # optional great-circle target
/>
```

### B) Leaflet (also offline, uses local polygons)

- File: `LeafletCountryModal.vue` (included)
- Uses Leaflet with a local-geojson-only layer (no raster tiles).

---

## Modal wrapper

Use `CountryInfoModal.vue` as the shell your app opens. It houses the title bar, close button, and chooses one of the map components (SVG or Leaflet).

Bind to your **existing data**: DXCC → country name, continent, CQ zone, lat/lon, grid. You already compute DXCC; convert to country via your CTY file or a small map table on the backend.

---

## Backend (FastAPI)

The frontend can import assets directly from `/src/assets`, but some teams prefer serving polygons from the backend (cache in memory). We include a tiny FastAPI service that:

- Loads **either** TopoJSON or GeoJSON at startup.
- Exposes `/country/by-name/{name}` and `/country/by-iso3/{iso3}` endpoints.
- Returns a single-country GeoJSON Feature, ready to drop into Leaflet, or to compute bounds client-side.

> This is optional if you import the file directly in the frontend. Use it if you want stronger centralization or to reuse the same data for other apps (rotator, analytics).

### Start the backend

```bash
cd backend/fastapi
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8099
```

---

## Styling & UX notes

- Dark theme defaults included; match your existing `--brand` colors if needed.
- The overlay card is **non-blocking**—map remains visible underneath.
- Optional: draw a **great-circle** line from your QTH to the DX point for rotator context.
- Optional: add a small **flag** next to the country name (serve flags from `/assets/flags/ISO2.svg`).

---

## Integration checklist

1. Download and commit one of the world files to `src/assets/`.
2. Drop `CountryInfoModal.vue` + your preferred map component into `/src/components/`.
3. Wire the modal open state and feed the props from your selected row (DX spot).
4. If using the backend service, configure `COUNTRY_DATA_SOURCE` env and point the component to `GET /country/by-name/:name`.
5. QA with known calls:  
   - **SV3RPQ** (Greece): `EU`, `CQ 20`, `DXCC 236`, `Lat 38`, `Lon 23.7`, `Grid KM18AF97`  
   - Verify highlight and marker land in Greece.

---

## Example screenshot

(Design reference used to guide styling.)

---

## License

All code in this spec is MIT unless integrated into your closed-source repo.
