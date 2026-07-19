from fastapi import APIRouter, HTTPException, Request
import asyncio
import logging
import os
import signal
from backend.core import get_app_context
from radio_control import config
from radio_control.lifecycle import reload_enabled, supervisor_enabled, write_lifecycle_request
from radio_control.postgres_store import get_postgres_dsn_from_values, test_connection
from radio_control.settings_store import public_config_from_module, save_config_updates

logger = logging.getLogger(__name__)

router = APIRouter()


async def _prepare_for_process_exit(request: Request, reason: str) -> None:
    """Close local resources before the backend process exits."""
    context = get_app_context(request)
    flex = context.flex

    if context.websocket_manager:
        await context.websocket_manager.close_all(reason)
    else:
        websocket_clients = context.websocket_clients
        for ws in list(websocket_clients):
            try:
                await ws.close(code=1001, reason=reason)
            except Exception:
                pass
        websocket_clients.clear()

    if flex:
        try:
            flex.close()
        except Exception:
            pass


def _schedule_backend_exit() -> None:
    """Terminate the current backend process after the HTTP response is sent."""
    loop = asyncio.get_event_loop()
    loop.call_later(1, lambda: os.kill(os.getpid(), signal.SIGTERM))


@router.get("/api/config")
async def get_config():
    """Get application configuration values used by the local UI."""
    try:
        config_data = {
            "success": True,
            "config": public_config_from_module(config),
        }
        return config_data
    except Exception:
        logger.exception("Error loading public configuration")
        raise HTTPException(status_code=500, detail="Configuration could not be loaded")


@router.post("/api/config")
async def save_config(request: Request):
    """Save application configuration without modifying Python source files."""
    try:
        body = await request.json()
        config_updates = body.get('config', {})
        
        if not isinstance(config_updates, dict) or not config_updates:
            raise HTTPException(status_code=422, detail="A non-empty configuration object is required")
        
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
        
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Error saving configuration")
        raise HTTPException(status_code=500, detail="Configuration could not be saved")


@router.post("/api/config/postgres/test")
async def test_postgres_config(request: Request):
    """Test PostgreSQL settings supplied by the config form without saving them."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    config_values = body.get("config", body) if isinstance(body, dict) else {}
    dsn = get_postgres_dsn_from_values(config_values)
    if not dsn:
        dsn = None

    try:
        details = test_connection(dsn=dsn, timeout_seconds=5)
        return {
            "success": True,
            "message": (
                f"Connected to PostgreSQL {details.get('server_version')} "
                f"as {details.get('user')} on {details.get('database')}"
            ),
            "details": details,
        }
    except Exception as e:
        logger.warning("PostgreSQL connection test failed: %s", e)
        return {
            "success": False,
            "message": f"PostgreSQL connection failed: {e}",
            "details": {},
        }


@router.post("/api/shutdown")
async def shutdown_server(request: Request):
    """Request a clean backend shutdown."""
    if reload_enabled():
        raise HTTPException(
            status_code=409,
            detail="Backend shutdown is disabled while Uvicorn reload mode is active.",
        )

    logger.warning("🛑 SHUTDOWN REQUEST RECEIVED - Backend is shutting down...")

    try:
        write_lifecycle_request("shutdown")
        await _prepare_for_process_exit(request, "Server shutting down")
        logger.info("✅ Backend shutdown sequence complete")
        _schedule_backend_exit()

        return {"success": True, "message": "Backend shutdown requested"}

    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Shutdown request could not be persisted") from e


@router.post("/api/restart")
async def restart_server(request: Request):
    """Request a supervised application restart."""
    if reload_enabled():
        raise HTTPException(
            status_code=409,
            detail="Application restart is disabled while Uvicorn reload mode is active.",
        )

    if not supervisor_enabled():
        raise HTTPException(
            status_code=409,
            detail=(
                "Restart requires the lifecycle-aware launcher. "
                "Start the app with start_all.ps1 or scripts/start/start_services_only.ps1."
            ),
        )

    logger.warning("🔄 RESTART REQUEST RECEIVED - Supervisor will restart services...")

    try:
        write_lifecycle_request("restart")
        await _prepare_for_process_exit(request, "Server restarting")
        logger.info("✅ Backend restart request sequence complete")
        _schedule_backend_exit()

        return {"success": True, "message": "Application restart requested"}

    except Exception as e:
        logger.error(f"❌ Restart error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Restart request could not be persisted") from e
