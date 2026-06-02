"""
Country Data Service - GeoJSON country data handling and mapping functions
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
import json
from radio_control import config

logger = logging.getLogger(__name__)

# Router for country data endpoints
router = APIRouter()

_country_data_cache = None
_zone_overlay_cache = None
_admin1_overlay_cache = None

def load_country_data():
    """Load country GeoJSON data from TopoJSON file and convert to GeoJSON"""
    global _country_data_cache
    if _country_data_cache is not None:
        return _country_data_cache

    data_path = config.DATA_DIR / "countries-110m.json"
    if not data_path.exists():
        logger.warning(f"Country data file not found: {data_path}")
        return None

    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            topo_data = json.load(f)

        # Store full TopoJSON data including arcs for proper rendering
        # The frontend will handle TopoJSON decompression via topojson-client
        _country_data_cache = topo_data
        logger.info("✅ Country TopoJSON data loaded successfully")
        return _country_data_cache
    except Exception as e:
        logger.error(f"Error loading country data: {e}")
        return None


def load_zone_overlay_data():
    """Load amateur radio CQ/WAZ and ITU overlay boundaries."""
    global _zone_overlay_cache
    if _zone_overlay_cache is not None:
        return _zone_overlay_cache

    data_path = config.DATA_DIR / "zone-overlays.json"
    if not data_path.exists():
        logger.warning(f"Zone overlay data file not found: {data_path}")
        return None

    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            _zone_overlay_cache = json.load(f)

        logger.info("✅ Zone overlay data loaded successfully")
        return _zone_overlay_cache
    except Exception as e:
        logger.error(f"Error loading zone overlay data: {e}")
        return None


def load_admin1_overlay_data():
    """Load US state and Canada province overlay boundaries."""
    global _admin1_overlay_cache
    if _admin1_overlay_cache is not None:
        return _admin1_overlay_cache

    data_path = config.DATA_DIR / "visual-admin1-us-ca.geojson"
    if not data_path.exists():
        logger.warning(f"Admin-1 overlay data file not found: {data_path}")
        return None

    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            _admin1_overlay_cache = json.load(f)

        logger.info("✅ US/Canada admin-1 overlay data loaded successfully")
        return _admin1_overlay_cache
    except Exception as e:
        logger.error(f"Error loading admin-1 overlay data: {e}")
        return None

def normalize_name(name: str) -> str:
    """Normalize country name for matching"""
    if not name:
        return ""
    return name.lower().strip()

def map_cty_to_geojson_name(cty_name: str) -> str:
    """Map CTY database country names to GeoJSON equivalents.

    CTY database uses various formats that may not match GeoJSON names.
    This function handles known variations and name mappings.
    """
    if not cty_name:
        return cty_name

    # Mapping of CTY names to GeoJSON names
    cty_geojson_map = {
        # European countries with variations
        "fed. rep. of germany": "Germany",
        "germany": "Germany",
        "united kingdom": "United Kingdom",
        "republic of ireland": "Ireland",
        "northern ireland": "United Kingdom",

        # Commonwealth nations
        "australia": "Australia",
        "canada": "Canada",
        "new zealand": "New Zealand",

        # Asian countries
        "china": "China",
        "japan": "Japan",
        "south korea": "South Korea",
        "korea, republic of": "South Korea",
        "korea, dem. people's rep. of": "North Korea",
        "india": "India",

        # Americas
        "united states of america": "United States of America",
        "united states": "United States of America",
        "usa": "United States of America",
        "mexico": "Mexico",
        "brazil": "Brazil",

        # African countries
        "south africa": "South Africa",
        "egypt": "Egypt",
        "nigeria": "Nigeria",

        # Special cases and abbreviations
        "dem. rep. congo": "Dem. Rep. Congo",
        "congo": "Congo",
        "cote d'ivoire": "Côte d'Ivoire",
        "ivory coast": "Côte d'Ivoire",
        "falkland is.": "Falkland Is.",
        "fr. s. antarctic lands": "Fr. S. Antarctic Lands",
    }

    normalized = normalize_name(cty_name)

    # Check if we have a mapping for this country
    for cty_key, geojson_name in cty_geojson_map.items():
        if normalized == cty_key:
            return geojson_name

    # If no mapping found, return original name
    # (it might still work with the partial match fallback)
    return cty_name

def find_country_by_name(name: str) -> Optional[Dict]:
    """Find a country feature by name

    Handles CTY database name variations by mapping to GeoJSON equivalents.
    Returns feature in GeoJSON format for rendering.
    """
    data = load_country_data()
    if not data:
        return None

    # First, try to map CTY names to GeoJSON names
    mapped_name = map_cty_to_geojson_name(name)
    norm_search = normalize_name(mapped_name)

    # Handle both TopoJSON and GeoJSON formats
    geometries = []
    if 'objects' in data and 'countries' in data['objects']:
        # TopoJSON format
        geometries = data['objects']['countries'].get('geometries', [])
    elif 'features' in data:
        # GeoJSON format
        geometries = [f.get('geometry') for f in data.get('features', [])]

    # Try exact match first
    if 'objects' in data and 'countries' in data['objects']:
        for geom in geometries:
            props = geom.get('properties', {})
            country_name = props.get('name')
            if country_name and normalize_name(country_name) == norm_search:
                logger.debug(f"🌍 Country match found: '{name}' -> '{mapped_name}' -> '{country_name}'")
                # Return as GeoJSON feature for rendering
                return {
                    'type': 'Feature',
                    'properties': props,
                    'geometry': geom,
                    'arcs': data.get('arcs'),  # Include arcs for TopoJSON decompression
                    'objects': data.get('objects'),  # Include full object data
                    'transform': data.get('transform'),  # CRITICAL: Include transform for coordinate conversion!
                    'bbox': data.get('bbox')  # Include bbox
                }

    # Fallback: partial match
    if 'objects' in data and 'countries' in data['objects']:
        for geom in geometries:
            props = geom.get('properties', {})
            country_name = props.get('name')
            if country_name and norm_search in normalize_name(country_name):
                logger.debug(f"🌍 Country partial match found: '{name}' -> '{mapped_name}' (partial match in '{country_name}')")
                return {
                    'type': 'Feature',
                    'properties': props,
                    'geometry': geom,
                    'arcs': data.get('arcs'),
                    'objects': data.get('objects'),
                    'transform': data.get('transform'),  # CRITICAL: Include transform for coordinate conversion!
                    'bbox': data.get('bbox')  # Include bbox
                }

    logger.warning(f"⚠️ Country not found: '{name}' (mapped to '{mapped_name}')")
    return None

@router.get("/api/country/data")
async def get_country_data():
    """Get full country GeoJSON data"""
    data = load_country_data()
    if not data:
        raise HTTPException(status_code=404, detail="Country data not available")
    return data


@router.get("/api/zone-overlays")
async def get_zone_overlay_data():
    """Get amateur radio CQ/WAZ and ITU overlay boundary data."""
    data = load_zone_overlay_data()
    if not data:
        raise HTTPException(status_code=404, detail="Zone overlay data not available")
    return data


@router.get("/api/admin1-overlays")
async def get_admin1_overlay_data():
    """Get US state and Canada province overlay boundary data."""
    data = load_admin1_overlay_data()
    if not data:
        raise HTTPException(status_code=404, detail="Admin-1 overlay data not available")
    return data

@router.get("/api/country/by-name/{name}")
async def get_country_by_name(name: str):
    """Get a specific country by name"""
    feature = find_country_by_name(name)
    if not feature:
        raise HTTPException(status_code=404, detail=f"Country '{name}' not found")
    return feature
