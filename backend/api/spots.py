"""
DX Spots API Router
Handles DX spot tuning, filtering, and spot management endpoints
"""

import logging
import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List

logger = logging.getLogger(__name__)

router = APIRouter()


class SpotTuneRequest(BaseModel):
    frequency: float
    mode: Optional[str] = None


class SpotFilterRequest(BaseModel):
    """Request model for filtered spot search"""
    limit: int = 100
    callsign: Optional[str] = None
    bands: Optional[List[str]] = None
    modes: Optional[List[str]] = None
    zones_cq: Optional[List[int]] = None
    continents: Optional[List[str]] = None
    special_tags: Optional[List[str]] = None


@router.get("/api/spots")
async def get_spots(
    request: Request,
    band: Optional[str] = None,
    mode: Optional[str] = None,
    cq: Optional[str] = None,
    call_status: Optional[str] = None,
    dxcc_status: Optional[str] = None,
    special: Optional[str] = None
):
    """Get DX spots with optional filtering (from cache only)"""
    dx_spots_cache = getattr(request.app.state, 'dx_spots_cache', [])
    filtered_spots = dx_spots_cache
    
    # Apply filters
    if band:
        bands = set(band.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('band') in bands]
    
    if mode:
        modes = set(mode.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('mode') in modes]
    
    if cq:
        cqs = set(cq.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('cq') in cqs]
    
    if call_status:
        statuses = set(call_status.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('call_status') in statuses]
    
    if dxcc_status:
        statuses = set(dxcc_status.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('dxcc_status') in statuses]
    
    if special:
        specials = set(special.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('special') in specials or ('(none)' in specials and not s.get('special'))]
    
    return {"spots": filtered_spots}


@router.post("/api/spots/filtered-search")
async def search_filtered_spots(req: SpotFilterRequest, request: Request):
    """
    Search spots in the DuckDB database with comprehensive filtering
    This endpoint queries the persistent spots database, allowing access to all historical spots
    not just the cached recent ones.
    
    Classifications (call_status and dxcc_status) are pre-computed and stored when spots are 
    received from the cluster, so filtered search is fast.
    
    Returns up to 'limit' spots matching all specified filters with cached classifications.
    """
    try:
        from radio_control.spots_logger import get_spots_logger
        
        logger.info(f"🔍 Filtered search: callsign={req.callsign}, bands={req.bands}, modes={req.modes}, limit={req.limit}")
        
        spots_logger = get_spots_logger()
        spots = spots_logger.get_filtered_spots(
            limit=req.limit,
            callsign=req.callsign,
            bands=req.bands,
            modes=req.modes,
            zones_cq=req.zones_cq,
            continents=req.continents,
            special_tags_filter=req.special_tags
        )
        
        logger.debug(f"✓ Filtered search returned {len(spots)} spots (using pre-computed classifications from database)")
        return {"ok": True, "spots": spots, "count": len(spots)}
        
    except Exception as e:
        logger.error(f"Error in filtered search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/spots/tune")
async def tune_to_spot(req: SpotTuneRequest, request: Request):
    """Tune to DX spot frequency and optionally change mode"""
    flex = request.app.state.flex
    
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")
    
    try:
        # Import broadcast function
        from services.websocket import broadcast_status
        
        # Tune frequency
        success = flex.tune_mhz(req.frequency)
        if not success:
            raise HTTPException(status_code=400, detail="Tune command failed")
        
        # Set mode if provided
        if req.mode:
            mode_success = flex.set_mode(req.mode)
            if not mode_success:
                logger.warning(f"Mode change to {req.mode} failed, but frequency changed")
        
        # Broadcast status update
        update = {"frequency": req.frequency}
        if req.mode:
            update["mode"] = req.mode
        await broadcast_status(update)
        
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tune to spot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/spots/count")
async def get_spots_count(request: Request):
    """Get total count of spots from persistent database"""
    try:
        from radio_control.spots_logger import get_spots_logger
        spots_logger = get_spots_logger()
        count = spots_logger.get_spot_count()
        return {"count": count}
    except Exception as e:
        logger.error(f"Error getting spot count: {e}")
        return {"count": 0}


@router.get("/api/spots/recent")
async def get_recent_spots(request: Request, limit: int = 999999):
    """Get recent spots from persistent database (not just cache)"""
    try:
        from radio_control.spots_logger import get_spots_logger
        spots_logger = get_spots_logger()
        spots = spots_logger.get_recent_spots(limit)
        return {"spots": spots}
    except Exception as e:
        logger.error(f"Error getting recent spots: {e}")
        # Fallback to cache if database is unavailable
        dx_spots_cache = getattr(request.app.state, 'dx_spots_cache', [])
        return {"spots": dx_spots_cache[:limit]}


@router.get("/api/spots/callsign/{callsign}")
async def get_spots_by_callsign(callsign: str, request: Request, limit: int = 100):
    """Get all spots for a specific callsign from persistent database"""
    try:
        from radio_control.spots_logger import get_spots_logger
        spots_logger = get_spots_logger()
        spots = spots_logger.get_spots_by_callsign(callsign, limit)
        return {"callsign": callsign, "count": len(spots), "spots": spots}
    except Exception as e:
        logger.error(f"Error getting spots for {callsign}: {e}")
        # Fallback to cache
        dx_spots_cache = getattr(request.app.state, 'dx_spots_cache', [])
        callsign_upper = callsign.upper()
        spots = [s for s in dx_spots_cache if s.get('callsign', '').upper() == callsign_upper]
        return {"callsign": callsign, "count": len(spots), "spots": spots}


@router.post("/api/spots/add-to-radio")
async def add_spot_to_radio(req: SpotTuneRequest, request: Request):
    """Tune to DX spot frequency and optionally change mode (alias for /api/spots/tune)"""
    flex = getattr(request.app.state, 'flex', None)
    
    if not flex:
        return {"success": False, "error": "Radio not initialized"}
    
    try:
        # Import broadcast function
        from services.websocket import broadcast_status
        
        # Tune frequency
        success = flex.tune_mhz(req.frequency)
        if not success:
            return {"success": False, "error": "Tune command failed"}
        
        # Set mode if provided
        if req.mode:
            mode_success = flex.set_mode(req.mode)
            if not mode_success:
                logger.warning(f"Mode change to {req.mode} failed, but frequency changed")
        
        # Broadcast status update
        update = {"frequency": req.frequency}
        if req.mode:
            update["mode"] = req.mode
        await broadcast_status(update)
        
        return {"success": True}
    except Exception as e:
        logger.error(f"Add spot to radio error: {e}")
        return {"success": False, "error": str(e)}
