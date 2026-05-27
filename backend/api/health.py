from fastapi import APIRouter, Request
import logging
import asyncio

from backend.core import get_app_context

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/api/health")
async def health_check(request: Request):
    """Health check"""
    flex = get_app_context(request).flex
    connected = flex is not None and flex.sock is not None
    return {
        "status": "ok" if connected else "disconnected",
        "connected": connected,
        "version": "2.0.0"
    }


@router.get("/api/status")
async def get_status(request: Request):
    """Get complete radio status"""
    context = get_app_context(request)
    flex = context.flex
    
    # Get cluster status and info
    cluster_client = context.cluster_client
    cluster_status = {
        "connected": cluster_client.connected if cluster_client else False,
        "activeName": "",
        "host": "",
        "port": ""
    }
    
    # Try to get active cluster info
    if cluster_client and hasattr(cluster_client, 'get_status'):
        try:
            cluster_info = cluster_client.get_status()
            if cluster_info:
                cluster_status.update({
                    "activeName": cluster_info.get('active_name', ''),
                    "host": cluster_info.get('host', ''),
                    "port": str(cluster_info.get('port', ''))
                })
        except Exception as e:
            logger.debug(f"Could not get cluster info: {e}")
    
    connected = bool(flex and flex.sock)
    return {
        "frequency": getattr(flex, "current_freq", None) or 14.074,
        "mode": getattr(flex, "current_mode", None) or "USB",
        "filter_lo": getattr(flex, "current_filter_lo", None) or 100,
        "filter_hi": getattr(flex, "current_filter_hi", None) or 2900,
        "volume": getattr(flex, "current_volume", None) or 50,
        "drive": getattr(flex, "current_rfpower", None) or 31,
        "tune_power": getattr(flex, "current_tunepower", None) or 18,
        "mic_level": getattr(flex, "current_miclevel", None) or 32,
        "vox_enabled": getattr(flex, "current_vox_enable", None) or False,
        "agc_mode": "med",
        "agc_threshold": 65,
        "monitor": 0,
        "nb_enabled": False,
        "nr_enabled": False,
        "anf_enabled": False,
        "apf_enabled": False,
        "connected": connected,
        "cluster_connected": cluster_status["connected"],
        "cluster_info": cluster_status,
        **({} if flex else {"message": "Radio not initialized - check connection settings"}),
    }


@router.get("/api/sync-status")
async def get_sync_status(request: Request):
    """Get the Wavelog to DuckDB sync status."""
    context = get_app_context(request)
    sync_manager = context.wavelog_sync_manager
    if sync_manager:
        try:
            status = await asyncio.wait_for(
                asyncio.to_thread(sync_manager.get_sync_status),
                timeout=1.5,
            )
        except asyncio.TimeoutError:
            logger.warning("Wavelog sync status timed out")
            status = {
                "status": "busy",
                "last_sync_error": "Sync status timed out",
                "total_records": 0,
            }
        return {
            "syncing": False,
            "last_sync": status.get("last_sync"),
            "total_records": status.get("total_records", 0),
            "new_records_this_sync": status.get("last_sync_added", 0),
            "records_updated": status.get("last_sync_updated", 0),
            "next_sync_in": 0,
            **status,
        }

    sync_status = context.sync_status or {
        "syncing": False,
        "last_sync": None,
        "total_records": 0,
        "new_records_this_sync": 0,
        "records_updated": 0,
        "next_sync_in": 0,
    }
    return sync_status
