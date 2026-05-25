from fastapi import APIRouter, HTTPException, Request
import asyncio
import logging
import os
import signal
from datetime import datetime
from radio_control import config
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/config")
async def get_config():
    """Get application configuration (safe, non-sensitive values only)"""
    try:
        # Return only configuration values that are safe to expose to frontend
        config_data = {
            "success": True,
            "config": {
                "MY_STATION": getattr(config, 'MY_STATION', 'N0CALL'),
                "ROTOR_ENABLED": getattr(config, 'ROTOR_ENABLED', False),
                "ROTOR_TYPE": getattr(config, 'ROTOR_TYPE', ''),
                "ROTOR_AUTO_ENABLED": getattr(config, 'ROTOR_AUTO_ENABLED', False),
                "ROTOR_AUTO_DELAY_SEC": getattr(config, 'ROTOR_AUTO_DELAY_SEC', 2),
                "WSJTX_ENABLED": getattr(config, 'WSJTX_ENABLED', True),
                "WSJTX_AUTO_LOG": getattr(config, 'WSJTX_AUTO_LOG', True),
                "WSJTX_AUTO_ROTATE": getattr(config, 'WSJTX_AUTO_ROTATE', True),
                "WAVELOG_ENABLED": getattr(config, 'WAVELOG_ENABLED', True),
                "QRZ_ENABLED": getattr(config, 'QRZ_ENABLED', True),
                "CLUSTER_ENABLED": getattr(config, 'CLUSTER_ENABLED', False),
                "CLUSTERS": getattr(config, 'CLUSTERS', []),
                "WINKEYER_ENABLED": getattr(config, 'WINKEYER_ENABLED', False),
                "WINKEYER_PORT": getattr(config, 'WINKEYER_PORT', 'COM3'),
                "WINKEYER_BAUDRATE": getattr(config, 'WINKEYER_BAUDRATE', 1200),
                "WINKEYER_DEFAULT_WPM": getattr(config, 'WINKEYER_DEFAULT_WPM', 20),
                "WINKEYER_MEMORIES": getattr(config, 'WINKEYER_MEMORIES', {}),
                "COLORS": getattr(config, 'COLORS', {}),
            }
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
    """Save application configuration"""
    try:
        body = await request.json()
        config_updates = body.get('config', {})
        
        if not config_updates:
            return {
                "success": False,
                "error": "No configuration data provided"
            }
        
        # Get the config file path
        import inspect
        config_file = inspect.getfile(config)
        
        # Read current config file
        with open(config_file, 'r') as f:
            config_lines = f.readlines()
        
        # Update configuration values
        updated_keys = set()
        for i, line in enumerate(config_lines):
            for key, value in config_updates.items():
                # Match lines like "KEY = value"
                if line.strip().startswith(key + ' =') or line.strip().startswith(key + '='):
                    # Prepare the new value
                    if isinstance(value, str):
                        new_value = f'"{value}"'
                    elif isinstance(value, dict):
                        new_value = str(value)
                    elif isinstance(value, list):
                        new_value = str(value)
                    else:
                        new_value = str(value)
                    
                    # Create the new line
                    config_lines[i] = f"{key} = {new_value}\n"
                    updated_keys.add(key)
                    logger.info(f"✏️ Updated config: {key} = {new_value}")
        
        # Write back to config file
        with open(config_file, 'w') as f:
            f.writelines(config_lines)
        
        logger.info(f"✅ Configuration saved: {list(updated_keys)}")
        
        return {
            "success": True,
            "message": f"Configuration saved ({len(updated_keys)} values updated)",
            "updated_keys": list(updated_keys)
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
