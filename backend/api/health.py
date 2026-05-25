from fastapi import APIRouter, Request, HTTPException
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/api/health")
async def health_check(request: Request):
    """Health check"""
    flex = request.app.state.flex
    connected = flex is not None and flex.sock is not None
    return {
        "status": "ok" if connected else "disconnected",
        "connected": connected,
        "version": "2.0.0"
    }


@router.get("/api/status")
async def get_status(request: Request):
    """Get complete radio status"""
    logger.info("📊 /api/status endpoint called")
    flex = getattr(request.app.state, 'flex', None)
    logger.info(f"🔍 Flex object: {flex}")
    
    # Get cluster status and info
    cluster_client = getattr(request.app.state, 'cluster_client', None)
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
    
    # If radio not initialized, return disconnected status instead of error
    if not flex:
        return {
            "frequency": 14.074,
            "mode": "USB",
            "filter_lo": 100,
            "filter_hi": 2900,
            "volume": 50,
            "drive": 31,
            "tune_power": 18,
            "mic_level": 32,
            "vox_enabled": False,
            "agc_mode": "med",
            "agc_threshold": 65,
            "monitor": 0,
            "nb_enabled": False,
            "nr_enabled": False,
            "anf_enabled": False,
            "apf_enabled": False,
            "connected": False,
            "cluster_connected": cluster_status["connected"],
            "cluster_info": cluster_status,
            "message": "Radio not initialized - check connection settings"
        }
    
    try:
        logger.info("📡 Attempting to get current levels from flex")
        levels = flex.get_current_levels(timeout=0.5)
        logger.info(f"✅ Got levels: {levels}")
        
        status = {
            "frequency": flex.current_freq or levels.get("freq", 14.074),
            "mode": flex.current_mode or levels.get("mode", "USB"),
            "filter_lo": flex.current_filter_lo or levels.get("filter_lo", 100),
            "filter_hi": flex.current_filter_hi or levels.get("filter_hi", 2900),
            "volume": levels.get("audio_level", 50),
            "drive": flex.current_rfpower or levels.get("rfpower", 31),
            "tune_power": flex.current_tunepower or levels.get("tunepower", 18),
            "mic_level": flex.current_miclevel or levels.get("miclevel", 32),
            "vox_enabled": flex.current_vox_enable or False,
            "agc_mode": levels.get("agc_mode", "med"),
            "agc_threshold": levels.get("agc_threshold", 65),
            "monitor": levels.get("mon", 0),
            "nb_enabled": levels.get("nb", False),
            "nr_enabled": levels.get("nr", False),
            "anf_enabled": levels.get("anf", False),
            "apf_enabled": levels.get("apf", False),
            "connected": True,
            "cluster_connected": cluster_status["connected"],
            "cluster_info": cluster_status
        }
        logger.info(f"✅ /api/status returning: {status}")
        return status
    except Exception as e:
        logger.error(f"❌ Error fetching radio status: {str(e)}", exc_info=True)
        # Return status with error flag instead of 500 error
        error_status = {
            "frequency": 14.074,
            "mode": "USB",
            "filter_lo": 100,
            "filter_hi": 2900,
            "volume": 50,
            "drive": 31,
            "tune_power": 18,
            "mic_level": 32,
            "vox_enabled": False,
            "agc_mode": "med",
            "agc_threshold": 65,
            "monitor": 0,
            "nb_enabled": False,
            "nr_enabled": False,
            "anf_enabled": False,
            "apf_enabled": False,
            "connected": False,
            "cluster_connected": cluster_status["connected"],
            "cluster_info": cluster_status,
            "message": f"Error fetching radio status: {str(e)}"
        }
        logger.info(f"⚠️ /api/status returning error status: {error_status}")
        return error_status


@router.get("/api/sync-status")
async def get_sync_status(request: Request):
    """Get ADIF sync status"""
    sync_status = getattr(request.app.state, 'sync_status', {
        "syncing": False,
        "last_sync": None,
        "total_records": 0,
        "new_records_this_sync": 0,
        "records_skipped": 0,
        "next_sync_in": 0,
        "adif_file_path": None,
        "adif_file_size": 0,
    })
    return sync_status