"""
Solar and HF Conditions API
Provides solar indices and HF band conditions data
"""

import logging
import time
from typing import Dict, Any, Optional
import httpx
from defusedxml import ElementTree as ET
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/solar", tags=["Solar & HF Conditions"])

# Cache configuration
CACHE_TTL = 600  # 10 minutes in seconds
MAX_SOLAR_XML_BYTES = 1024 * 1024
_solar_cache: Dict[str, Any] = {"timestamp": 0, "data": None}

def _safe_int(value: Any) -> Optional[int]:
    """Safely convert value to integer"""
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return None

def _safe_str(value: Any, default: str = "—") -> str:
    """Safely convert value to string with default"""
    try:
        return str(value) if value is not None else default
    except:
        return default

async def fetch_hamqsl_solar_data() -> Dict[str, Any]:
    """
    Fetch solar data from HamQSL API
    Returns formatted solar conditions data
    """
    try:
        # Try multiple endpoints in case one is down
        endpoints = [
            "https://hamqsl.com/solarxml.php",
            "https://www.hamqsl.com/solarxml.php", 
            "http://hamqsl.com/solarxml.php"
        ]
        
        solar_data = {}
        for url in endpoints:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    
                    if len(response.content) > MAX_SOLAR_XML_BYTES:
                        raise ValueError("Solar XML response exceeded the allowed size")
                    root = ET.fromstring(response.content)
                    
                    # Find the solardata element
                    solardata = root.find("solardata")
                    if solardata is None:
                        continue
                    
                    # Extract basic indices
                    solar_data = {
                        "solarflux": solardata.find("solarflux").text if solardata.find("solarflux") is not None else None,
                        "aindex": solardata.find("aindex").text if solardata.find("aindex") is not None else None,
                        "kindex": solardata.find("kindex").text if solardata.find("kindex") is not None else None,
                        "updated": solardata.find("updated").text if solardata.find("updated") is not None else None,
                        "band_80m_40m": "Fair",
                        "band_30m_20m": "Fair", 
                        "band_17m_15m": "Fair",
                        "band_12m_10m": "Fair"
                    }
                    
                    # Parse band conditions from calculatedconditions
                    calc_cond = solardata.find("calculatedconditions")
                    if calc_cond is not None:
                        for band_elem in calc_cond.findall("band"):
                            band_name = band_elem.get("name")
                            time_attr = band_elem.get("time")
                            condition = band_elem.text
                            
                            if time_attr == "day":
                                if band_name == "80m-40m":
                                    solar_data["band_80m_40m"] = condition
                                elif band_name == "30m-20m":
                                    solar_data["band_30m_20m"] = condition
                                elif band_name == "17m-15m":
                                    solar_data["band_17m_15m"] = condition
                                elif band_name == "12m-10m":
                                    solar_data["band_12m_10m"] = condition
                    break  # Success, exit loop
            except Exception as e:
                logger.warning(f"Failed to fetch from {url}: {e}")
                continue
        
        if not solar_data:
            raise HTTPException(status_code=502, detail="Solar data service is unavailable")
        
        # Build our standardized payload
        payload = {
            "source": "HamQSL",
            "updated": _safe_str(solar_data.get("updated")),
            "indices": {
                "sfi": _safe_int(solar_data.get("solarflux")),  # Solar Flux Index
                "a_index": _safe_int(solar_data.get("aindex")),  # A-index (geomagnetic activity)
                "k_index": _safe_int(solar_data.get("kindex"))   # K-index (geomagnetic activity)
            },
            "hf_conditions": {
                "80m_40m": {
                    "day": _safe_str(solar_data.get("band_80m_40m"), "Fair"),
                    "night": "Fair"  # XML endpoint doesn't provide night data
                },
                "30m_20m": {
                    "day": _safe_str(solar_data.get("band_30m_20m"), "Fair"),
                    "night": "Fair"
                },
                "17m_15m": {
                    "day": _safe_str(solar_data.get("band_17m_15m"), "Fair"),
                    "night": "Fair"
                },
                "12m_10m": {
                    "day": _safe_str(solar_data.get("band_12m_10m"), "Fair"),
                    "night": "Fair"
                }
            },
            "quality_levels": {
                "sfi": get_sfi_level(_safe_int(solar_data.get("solarflux"))),
                "a_index": get_a_level(_safe_int(solar_data.get("aindex"))),
                "k_index": get_k_level(_safe_int(solar_data.get("kindex")))
            }
        }
        
        return payload
        
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch solar data from HamQSL: {e}")
        raise HTTPException(status_code=502, detail=f"Solar data service unavailable: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching solar data: {e}")
        raise HTTPException(status_code=500, detail=f"Solar data processing error: {str(e)}")

def get_sfi_level(sfi: Optional[int]) -> str:
    """Determine SFI quality level"""
    if sfi is None:
        return "unknown"
    elif sfi >= 150:
        return "good"
    elif sfi >= 120:
        return "fair"
    else:
        return "poor"

def get_a_level(a_index: Optional[int]) -> str:
    """Determine A-index quality level"""
    if a_index is None:
        return "unknown"
    elif a_index <= 10:
        return "good"
    elif a_index <= 20:
        return "fair"
    else:
        return "poor"

def get_k_level(k_index: Optional[int]) -> str:
    """Determine K-index quality level"""
    if k_index is None:
        return "unknown"
    elif k_index <= 3:
        return "good"
    elif k_index <= 4:
        return "fair"
    else:
        return "poor"

@router.get("")
async def get_solar_conditions():
    """
    Get current solar and HF conditions
    Returns cached data (10 min TTL) to avoid excessive API calls
    """
    current_time = time.time()
    
    # Check if cache is valid
    if (_solar_cache["data"] is not None and 
        current_time - _solar_cache["timestamp"] < CACHE_TTL):
        logger.debug("Returning cached solar data")
        return JSONResponse(_solar_cache["data"])
    
    # Cache is invalid, fetch new data
    try:
        logger.info("Fetching fresh solar data from HamQSL API")
        solar_data = await fetch_hamqsl_solar_data()
        
        # Update cache
        _solar_cache["data"] = solar_data
        _solar_cache["timestamp"] = current_time
        
        return JSONResponse(solar_data)
        
    except HTTPException as e:
        # If we have stale cached data, return it instead of failing
        if _solar_cache["data"] is not None:
            logger.warning("Solar API failed, returning stale cached data")
            return JSONResponse({
                **_solar_cache["data"],
                "warning": "Data may be outdated due to service unavailability"
            })
        else:
            # No cached data available, re-raise the exception
            raise e

@router.get("/health")
async def solar_api_health():
    """Health check for solar data API"""
    try:
        # Try to fetch data (will use cache if available)
        await get_solar_conditions()
        return {
            "status": "healthy",
            "cache_age_seconds": time.time() - _solar_cache["timestamp"] if _solar_cache["data"] else None,
            "has_cached_data": _solar_cache["data"] is not None
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "has_cached_data": _solar_cache["data"] is not None
        }

@router.post("/refresh")
async def refresh_solar_data():
    """Force refresh of solar data (bypasses cache)"""
    try:
        logger.info("Forcing refresh of solar data")
        solar_data = await fetch_hamqsl_solar_data()
        
        # Update cache
        _solar_cache["data"] = solar_data
        _solar_cache["timestamp"] = time.time()
        
        return JSONResponse({
            "status": "refreshed",
            "data": solar_data
        })
        
    except Exception as e:
        logger.error(f"Failed to refresh solar data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh: {str(e)}")
