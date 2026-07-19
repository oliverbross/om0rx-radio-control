"""
Rotor API Router

FastAPI router for rotor control endpoints.
Wraps RotatorService methods as HTTP endpoints.
"""

import logging
from fastapi import APIRouter, HTTPException, Body, Query
from typing import Dict, Any

# Configure logging
logger = logging.getLogger(__name__)

# Global rotor service instance (will be set when registering)
rotor_service = None

router = APIRouter(prefix="/api", tags=["rotor"])


# === Helper function to ensure service is initialized ===

def get_rotor_service():
    """Get the rotor service instance"""
    global rotor_service
    if rotor_service is None:
        raise HTTPException(status_code=503, detail="Rotor service not initialized")
    return rotor_service


# === Rotor Status Endpoints ===

@router.get("/rotor/status")
async def get_rotor_status(fresh: bool = Query(False)):
    """Get current rotor status"""
    service = get_rotor_service()
    try:
        return await service.get_rotor_status(fresh=fresh)
    except Exception as e:
        logger.error(f"Error getting rotor status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rotor/goto")
async def rotor_goto(request: Dict[str, Any] = Body(...)):
    """Move rotor to specific azimuth"""
    service = get_rotor_service()
    try:
        azimuth = request.get('azimuth')
        if azimuth is None:
            raise ValueError("Missing 'azimuth' parameter")
        return await service.rotor_goto(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in rotor goto: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rotor/direction")
async def rotor_direction(request: Dict[str, Any] = Body(...)):
    """Move rotor in a direction"""
    service = get_rotor_service()
    try:
        direction = request.get('direction')
        if direction is None:
            raise ValueError("Missing 'direction' parameter")
        return await service.rotor_direction(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in rotor direction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rotor/stop")
async def rotor_stop():
    """Stop rotor movement"""
    service = get_rotor_service()
    try:
        return await service.rotor_stop()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping rotor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Rotor Configuration Endpoints ===

@router.post("/rotor/config")
async def rotor_config(request: Dict[str, Any] = Body(...)):
    """Update rotor configuration"""
    service = get_rotor_service()
    try:
        return await service.set_rotor_config(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in rotor config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rotor/config")
async def get_rotor_config():
    """Get rotor configuration"""
    service = get_rotor_service()
    try:
        return await service.get_rotor_config()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting rotor config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Rotor AUTO Mode Endpoints ===

@router.get("/rotor/auto/status")
async def get_rotor_auto_status():
    """Get rotor AUTO mode status"""
    service = get_rotor_service()
    try:
        return await service.get_rotor_auto_status()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting rotor AUTO status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rotor/auto/config")
async def rotor_auto_config(request: Dict[str, Any] = Body(...)):
    """Update rotor AUTO configuration"""
    service = get_rotor_service()
    try:
        return await service.set_rotor_auto_config(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in rotor AUTO config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rotor/bearing")
async def rotor_bearing(request: Dict[str, Any] = Body(...)):
    """Calculate bearing to a station"""
    service = get_rotor_service()
    try:
        return await service.calculate_rotor_bearing(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating bearing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rotor/resolve")
async def rotor_resolve(request: Dict[str, Any] = Body(...)):
    """Resolve the best rotator target and return diagnostics without moving."""
    service = get_rotor_service()
    try:
        return service.resolve_rotor_target(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving rotor target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rotor/auto/bearing")
async def rotor_auto_bearing(request: Dict[str, Any] = Body(...)):
    """Calculate AUTO rotor bearing without moving the rotor."""
    return await rotor_bearing(request)


@router.post("/rotor/auto/goto")
async def rotor_auto_goto(request: Dict[str, Any] = Body(...)):
    """AUTO rotor GOTO - calculate and move"""
    service = get_rotor_service()
    try:
        return await service.rotor_auto_goto(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in AUTO rotor goto: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def set_rotor_service(service):
    """Set the rotor service instance for this router"""
    global rotor_service
    rotor_service = service
