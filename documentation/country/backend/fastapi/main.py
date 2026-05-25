from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json

app = FastAPI(title="Country Polygons API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
# Prefer TopoJSON for smaller size
TOPO_PATH = DATA_DIR / 'countries-110m.json'
GEO_PATH  = DATA_DIR / 'ne_countries_110m.geojson'

countries_geo = None

def load_data():
    global countries_geo
    if TOPO_PATH.exists():
        # Lazy topojson conversion without external lib: expect 'objects' and 'arcs' (pre-converted here to FeatureCollection).
        # For simplicity, we assume the file is already a GeoJSON FeatureCollection. If using true TopoJSON,
        # convert it in frontend, or pre-generate a GeoJSON copy at build time.
        # Many teams put a pre-converted GeoJSON file here to keep backend light.
        try:
            with open(TOPO_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if 'type' in data and data['type'] == 'FeatureCollection':
                countries_geo = data
            else:
                # If it's true TopoJSON, error with instructions
                raise RuntimeError('Found TopoJSON. Convert to GeoJSON for backend or serve the raw file to the frontend.')
        except Exception as e:
            raise
    elif GEO_PATH.exists():
        with open(GEO_PATH, 'r', encoding='utf-8') as f:
            countries_geo = json.load(f)
    else:
        raise FileNotFoundError('Place countries-110m.json (GeoJSON) or ne_countries_110m.geojson in backend/data/')

def find_by_name(name: str):
    norm = lambda s: (s or '').lower()
    for f in countries_geo.get('features', []):
        props = f.get('properties', {})
        n = norm(props.get('name') or props.get('NAME') or props.get('ADMIN') or props.get('NAME_EN'))
        if n == norm(name) or (n and norm(name) in n):
            return f
    return None

@app.on_event('startup')
def startup():
    load_data()

@app.get('/health')
def health(): return { 'ok': True }

@app.get('/country/by-name/{name}')
def by_name(name: str):
    f = find_by_name(name)
    if not f:
        raise HTTPException(404, 'Country not found')
    return f

# Minimal DXCC→country helper, extend with your CTY mapping if needed
DXCC_TO_COUNTRY = {
    236: 'Greece',  # SV
}

@app.get('/country/by-dxcc/{dxcc_id}')
def by_dxcc(dxcc_id: int):
    name = DXCC_TO_COUNTRY.get(dxcc_id)
    if not name:
        raise HTTPException(404, 'DXCC mapping unknown')
    return by_name(name)
