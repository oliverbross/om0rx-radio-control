from fastapi import APIRouter, Request
import asyncio
import logging
import os
import signal
from radio_control import config
from radio_control.settings_store import public_config_from_module, save_config_updates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/config")
async def get_config():
    """Get application configuration values used by the local UI."""
    try:
        config_data = {
            "success": True,
            "config": public_config_from_module(config),
        }
        return config_data
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {
            "success": False,
            "error": str(e),
            "config": {}
        }


@router.post("/api/config")
async def save_config(request: Request):
    """Save application configuration without modifying Python source files."""
    try:
        body = await request.json()
        config_updates = body.get('config', {})
        
        if not config_updates:
            return {
                "success": False,
                "error": "No configuration data provided"
            }
        
        save_result = save_config_updates(config_updates)

        for key in save_result["updated_keys"]:
            setattr(config, key, config_updates[key])

        if save_result["rejected_keys"]:
            logger.warning("Rejected unsupported config keys: %s", save_result["rejected_keys"])

        logger.info("✅ Configuration saved: %s", save_result["updated_keys"])
        
        return {
            "success": True,
            "message": f"Configuration saved ({len(save_result['updated_keys'])} values updated)",
            "updated_keys": save_result["updated_keys"],
            "app_settings_keys": save_result["app_settings_keys"],
            "local_secret_keys": save_result["local_secret_keys"],
            "rejected_keys": save_result["rejected_keys"],
        }
        
    except Exception as e:
        logger.error(f"Error saving configuration: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/api/shutdown")
async def shutdown_server(request: Request):
    """Shutdown the server cleanly"""
    logger.warning("🛑 SHUTDOWN REQUEST RECEIVED - Server is shutting down...")

    try:
        # Access globals from app state
        websocket_clients = getattr(request.app.state, 'websocket_clients', [])
        adif_sync_task = getattr(request.app.state, 'adif_sync_task', None)
        flex = getattr(request.app.state, 'flex', None)

        # Close all WebSocket connections
        for ws in websocket_clients:
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except:
                pass
        websocket_clients.clear()

        # Stop Wavelog→DuckDB sync task if running
        if adif_sync_task and not adif_sync_task.done():
            adif_sync_task.cancel()
            try:
                await adif_sync_task
            except asyncio.CancelledError:
                pass

        # Stop Wavelog sync
        try:
            from radio_control.wavelog_sync import stop_wavelog_sync
            await stop_wavelog_sync()
        except:
            pass

        # Close FlexRadio connection
        if flex:
            try:
                flex.close()
            except:
                pass

        logger.info("✅ Server shutdown sequence complete")

        # Schedule server shutdown after a short delay to allow response to be sent
        loop = asyncio.get_event_loop()
        loop.call_later(1, lambda: os.kill(os.getpid(), signal.SIGTERM))

        return {"success": True, "message": "Server is shutting down"}

    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/api/restart")
async def restart_server(request: Request):
    """Restart the server"""
    logger.warning("🔄 RESTART REQUEST RECEIVED - Server is restarting...")

    try:
        # Access globals from app state
        websocket_clients = getattr(request.app.state, 'websocket_clients', [])
        adif_sync_task = getattr(request.app.state, 'adif_sync_task', None)
        flex = getattr(request.app.state, 'flex', None)

        # Close all WebSocket connections
        for ws in websocket_clients:
            try:
                await ws.close(code=1001, reason="Server restarting")
            except:
                pass
        websocket_clients.clear()

        # Stop Wavelog→DuckDB sync task if running
        if adif_sync_task and not adif_sync_task.done():
            adif_sync_task.cancel()
            try:
                await adif_sync_task
            except asyncio.CancelledError:
                pass

        # Stop Wavelog sync
        try:
            from radio_control.wavelog_sync import stop_wavelog_sync
            await stop_wavelog_sync()
        except:
            pass

        # Close FlexRadio connection
        if flex:
            try:
                flex.close()
            except:
                pass

        logger.info("✅ Server restart sequence complete")

        # Schedule server restart
        loop = asyncio.get_event_loop()
        loop.call_later(1, lambda: os.kill(os.getpid(), signal.SIGTERM))

        return {"success": True, "message": "Server is restarting"}

    except Exception as e:
        logger.error(f"❌ Restart error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
