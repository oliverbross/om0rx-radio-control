from fastapi import APIRouter, HTTPException, Request
import asyncio
import copy
import logging
import os
import signal
from backend.core import get_app_context
from radio_control import config
from radio_control.lifecycle import reload_enabled, supervisor_enabled, write_lifecycle_request
from radio_control.postgres_store import get_postgres_dsn_from_values, test_connection
from radio_control.settings_store import (
    ALLOWED_CONFIG_KEYS,
    SECRET_KEYS,
    normalize_config_updates,
    public_config_from_module,
    save_config_updates,
)
from services.elecraft_station import StationActionError

logger = logging.getLogger(__name__)

router = APIRouter()

STATION_CONFIG_KEYS = {
    "DIGITAL_KPA_POLICY",
    "ELECRAFT_FOLLOW_RADIO",
    "FLEX_ANTENNA_POLICY",
    "KPA500_ENABLED",
    "KPA500_PORT",
    "KPA500_BAUDRATE",
    "KAT500_ENABLED",
    "KAT500_PORT",
    "KAT500_BAUDRATE",
    "KAT500_ANTENNA_POLICY",
    "KAT500_ANTENNA_NAMES",
    "STATION_AMPLIFIER_ALLOWED_BANDS",
    "STATION_AMPLIFIER_DRIVE_W",
    "STATION_BAREFOOT_DRIVE_W",
    "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS",
    "STATION_DIGITAL_AMPLIFIER_DRIVE_W",
    "STATION_ROUTE_VERIFY_TTL_SECONDS",
    "STATION_TUNE_POWER_W",
    "STATION_TUNE_TARGET_SWR",
    "STATION_TUNE_ABORT_SWR",
    "STATION_TUNE_TIMEOUT_SECONDS",
}


async def _prepare_for_process_exit(request: Request, reason: str) -> None:
    """Close local resources before the backend process exits."""
    context = get_app_context(request)
    flex = context.flex

    if context.station_coordinator:
        # Do not close FLEX or schedule process exit unless carrier-off and
        # amplifier standby were independently confirmed by the coordinator.
        await context.station_coordinator.stop()

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

        accepted_updates = {
            key: value for key, value in config_updates.items() if key in ALLOWED_CONFIG_KEYS
        }
        normalized_updates = normalize_config_updates(accepted_updates)
        context = get_app_context(request)
        coordinator = getattr(context, "station_coordinator", None)
        elecraft_keys = {
            "ELECRAFT_FOLLOW_RADIO",
            "KPA500_ENABLED",
            "KPA500_PORT",
            "KPA500_BAUDRATE",
            "KAT500_ENABLED",
            "KAT500_PORT",
            "KAT500_BAUDRATE",
            "KAT500_ANTENNA_POLICY",
            "KAT500_ANTENNA_NAMES",
        }
        route_affecting_keys = elecraft_keys | {
            "DIGITAL_KPA_POLICY",
            "FLEX_ANTENNA_POLICY",
            "STATION_AMPLIFIER_ALLOWED_BANDS",
            "STATION_AMPLIFIER_DRIVE_W",
            "STATION_BAREFOOT_DRIVE_W",
            "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS",
            "STATION_DIGITAL_AMPLIFIER_DRIVE_W",
        }

        live_changed_keys = {
            key
            for key, value in normalized_updates.items()
            if key not in SECRET_KEYS
            and (not hasattr(config, key) or getattr(config, key) != value)
        }
        station_changed_keys = STATION_CONFIG_KEYS.intersection(live_changed_keys)
        route_changed_keys = route_affecting_keys.intersection(live_changed_keys)
        old_values = {
            key: copy.deepcopy(getattr(config, key))
            for key in live_changed_keys
            if hasattr(config, key)
        }

        async def apply_updates():
            if route_changed_keys:
                from services.digital_engine import get_digital_engine_service

                get_digital_engine_service().clear_station_authorizations(
                    "station-configuration-change"
                )

            save_result = save_config_updates(config_updates)
            applied_live_keys = live_changed_keys.intersection(normalized_updates)
            try:
                for key in applied_live_keys:
                    setattr(config, key, normalized_updates[key])

                if elecraft_keys.intersection(applied_live_keys):
                    from radio_control.elecraft import get_elecraft_manager

                    await get_elecraft_manager().reconfigure()

                if coordinator and station_changed_keys:
                    coordinator.invalidate_route()
            except Exception:
                rollback = {
                    key: old_values[key]
                    for key in applied_live_keys
                    if key in old_values
                }
                if rollback:
                    save_config_updates(rollback)
                    for key, value in rollback.items():
                        setattr(config, key, value)
                    if elecraft_keys.intersection(rollback):
                        try:
                            from radio_control.elecraft import get_elecraft_manager

                            await get_elecraft_manager().reconfigure()
                        except Exception:
                            logger.critical(
                                "Station configuration rollback could not restore device connections",
                                exc_info=True,
                            )
                raise

            save_result["updated_keys"] = sorted(
                set(save_result["updated_keys"]) | set(applied_live_keys)
            )
            return save_result

        if coordinator and station_changed_keys:
            async with coordinator.configuration_update(
                route_affecting=bool(route_changed_keys)
            ):
                save_result = await apply_updates()
        else:
            save_result = await apply_updates()

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
    except StationActionError as exc:
        raise HTTPException(
            status_code=int(exc.status_code or 409),
            detail=f"{exc.code}: {exc.message}",
        ) from exc
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
        await _prepare_for_process_exit(request, "Server shutting down")
        write_lifecycle_request("shutdown")
        logger.info("✅ Backend shutdown sequence complete")
        _schedule_backend_exit()

        return {"success": True, "message": "Backend shutdown requested"}

    except HTTPException:
        raise
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
        await _prepare_for_process_exit(request, "Server restarting")
        write_lifecycle_request("restart")
        logger.info("✅ Backend restart request sequence complete")
        _schedule_backend_exit()

        return {"success": True, "message": "Application restart requested"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Restart error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Restart request could not be persisted") from e
