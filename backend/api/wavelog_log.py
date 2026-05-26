"""
Wavelog Log API Endpoints
Direct database access for log viewing
"""

from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
import logging

from backend.core import get_app_context
from services.wavelog_log import get_wavelog_log_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wavelog-log", tags=["wavelog-log"])


@router.get("/entries")
async def get_log_entries(
    limit: int = Query(default=100, ge=1, le=10000, description="Number of log entries to return"),
    station_id: int = Query(default=1, description="Station profile ID")
):
    """
    Fetch log entries from Wavelog database
    
    - **limit**: Number of entries to return (1-10000, default: 100)
    - **station_id**: Station profile ID (default: 1)
    
    Returns list of QSO log entries sorted by date (newest first)
    """
    try:
        service = get_wavelog_log_service()
        entries = service.get_log_entries(limit=limit, station_id=station_id)
        
        return {
            "success": True,
            "count": len(entries),
            "limit": limit,
            "entries": entries
        }
        
    except Exception as e:
        logger.error(f"Error fetching log entries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch log entries: {str(e)}")


@router.get("/stats")
async def get_log_stats(
    station_id: int = Query(default=1, description="Station profile ID")
):
    """
    Get log statistics
    
    - **station_id**: Station profile ID (default: 1)
    
    Returns statistics about the log (total QSOs, unique DXCC, etc.)
    """
    try:
        service = get_wavelog_log_service()
        stats = service.get_log_stats(station_id=station_id)
        
        return {
            "success": True,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Error fetching log stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch log stats: {str(e)}")


@router.get("/search/{callsign:path}")
async def search_callsign(
    callsign: str,
    station_id: int = Query(default=1, description="Station profile ID"),
    limit: int = Query(default=20, ge=1, le=50, description="Maximum number of QSOs to return")
):
    """
    Search for all QSOs with a specific callsign
    
    - **callsign**: Callsign to search for (case insensitive, supports suffixes with /)
    - **station_id**: Station profile ID (default: 1)
    - **limit**: Maximum number of QSOs to return (default: 20, max: 50)
    
    Returns:
    - List of QSOs with the callsign
    - Summary information (DXCC, CQ, Continent, Grid, IOTA, POTA, SOTA, WWFF, etc.)
    - Band/mode matrix showing worked/confirmed status
    """
    try:
        service = get_wavelog_log_service()
        results = service.search_callsign(callsign=callsign, station_id=station_id, limit=limit)
        
        return {
            "success": True,
            "callsign": callsign.upper(),
            "count": len(results['qsos']),
            "qsos": results['qsos'],
            "summary": results['summary'],
            "matrix": results['matrix']
        }
        
    except Exception as e:
        logger.error(f"Error searching for callsign {callsign}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search for callsign: {str(e)}")


@router.get("/sync-status")
async def get_wavelog_sync_status(request: Request):
    """
    Get Wavelog→DuckDB read-cache sync status
    
    Returns current sync status including:
    - Total records synced
    - Last sync timestamp
    - Sync state (running/idle)
    """
    try:
        sync_manager = get_app_context(request).wavelog_sync_manager
        
        if sync_manager:
            status = sync_manager.get_sync_status()
            return status
        else:
            return {
                "syncing": False,
                "last_sync": None,
                "total_records": 0,
                "error": "Sync manager not initialized"
            }
            
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return {
            "syncing": False,
            "last_sync": None,
            "total_records": 0,
            "error": str(e)
        }


@router.post("/reset-sync")
async def reset_wavelog_sync(
    request: Request,
    clear_data: bool = Query(default=False, description="Clear all synced data (if True)")
):
    """
    Reset Wavelog→DuckDB read-cache sync to force a fresh initial sync
    
    - **clear_data**: If true, also clears all synced QSO records (default: False)
    
    Use this if sync gets stuck or you want to re-sync all data from scratch.
    """
    try:
        sync_manager = get_app_context(request).wavelog_sync_manager
        
        if not sync_manager:
            raise HTTPException(status_code=503, detail="Sync manager not initialized")
        
        result = sync_manager.reset_sync(clear_data=clear_data)
        
        if result.get('success'):
            return {
                "success": True,
                "message": result['message'],
                "data_cleared": result['data_cleared']
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', 'Unknown error'))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting sync: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset sync: {str(e)}")


@router.get("/statistics")
async def get_wavelog_statistics():
    """
    Get general statistics from Wavelog API
    
    Returns:
    - Today's QSOs
    - Month's QSOs  
    - Year's QSOs
    - Total QSOs
    """
    try:
        from radio_control.wavelog_api import WavelogClient
        
        client = WavelogClient()
        result = await client.get_statistics()
        
        if result.get('success'):
            return {
                "success": True,
                "data": result['data']
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('message', 'Failed to fetch statistics'))
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Wavelog statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch statistics: {str(e)}")


@router.get("/wp-statistics")
async def get_wavelog_wp_statistics():
    """
    Get detailed statistics from Wavelog API (get_wp_stats)
    
    Returns:
    - Total QSOs all time
    - Total QSOs this year
    - QSOs grouped by mode (with submodes)
    """
    try:
        from radio_control.wavelog_api import WavelogClient
        
        client = WavelogClient()
        result = await client.get_wp_stats()
        
        if result.get('success'):
            return {
                "success": True,
                "data": result['data']
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('message', 'Failed to fetch WP statistics'))
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Wavelog WP statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch WP statistics: {str(e)}")
