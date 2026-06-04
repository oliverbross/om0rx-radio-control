from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
import logging
import asyncio
import time

from backend.core import get_app_context
from radio_control import config
from radio_control.postgres_store import get_postgres_dsn, should_use_postgres
from radio_control.qso_outbox import get_qso_outbox
from services.ft8_service import get_ft8_service
from services.rotator import get_rotator_service
from services.wsjtx import get_wsjtx_service

logger = logging.getLogger(__name__)
router = APIRouter()

SYNC_STATUS_TIMEOUT_SEC = 0.35
ROTOR_HEALTH_TIMEOUT_SEC = 0.35


def _service(
    service_id: str,
    label: str,
    status: str,
    value: str = "",
    detail: str = "",
    action: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": service_id,
        "label": label,
        "status": status,
        "value": value,
        "detail": detail,
        "action": action,
    }


def _cluster_status(cluster_client: Any) -> Dict[str, Any]:
    status = {
        "connected": bool(getattr(cluster_client, "connected", False)),
        "activeName": "",
        "host": "",
        "port": "",
    }
    if cluster_client and hasattr(cluster_client, "get_status"):
        try:
            cluster_info = cluster_client.get_status() or {}
            status.update({
                "connected": bool(cluster_info.get("connected", status["connected"])),
                "activeName": cluster_info.get("active_name", "") or cluster_info.get("activeName", ""),
                "host": cluster_info.get("host", "") or "",
                "port": str(cluster_info.get("port", "") or ""),
            })
        except Exception as exc:
            logger.debug("Could not get cluster info: %s", exc)
    return status


def _db_file_summary(path: Path) -> Dict[str, Any]:
    try:
        exists = path.exists()
        return {
            "path": str(path),
            "exists": exists,
            "size_bytes": path.stat().st_size if exists else 0,
        }
    except Exception as exc:
        return {"path": str(path), "exists": False, "size_bytes": 0, "error": str(exc)}


def _cached_sync_status(context: Any) -> Dict[str, Any]:
    """Return Wavelog sync state without opening the backing cache."""
    status = dict(context.sync_status or {})
    sync_manager = getattr(context, "wavelog_sync_manager", None)

    cached = getattr(sync_manager, "_cached_status", None)
    if isinstance(cached, dict):
        status.update(cached)

    if sync_manager is not None:
        status["syncing"] = bool(getattr(sync_manager, "_sync_active", False) or status.get("syncing"))

    if not status:
        status = {
            "syncing": False,
            "last_sync": None,
            "total_records": 0,
            "new_records_this_sync": 0,
            "records_updated": 0,
            "next_sync_in": 0,
            "status": "unknown",
        }

    status.setdefault("syncing", False)
    status.setdefault("total_records", 0)
    status.setdefault("last_sync", None)
    status.setdefault("last_sync_error", None)
    return status


async def _sync_status_fast(context: Any, timeout: float = SYNC_STATUS_TIMEOUT_SEC) -> Dict[str, Any]:
    """Refresh sync status with a very small budget, then fall back to cached state."""
    sync_manager = getattr(context, "wavelog_sync_manager", None)
    if not sync_manager:
        return _cached_sync_status(context)

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(sync_manager.get_sync_status),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.debug("Wavelog sync status timed out after %.2fs; using cached status", timeout)
    except Exception as exc:
        logger.debug("Wavelog sync status refresh failed; using cached status: %s", exc)

    cached = _cached_sync_status(context)
    cached["status_stale"] = True
    return cached


async def _rotor_health() -> Dict[str, Any]:
    if not getattr(config, "ROTOR_ENABLED", False):
        return _service("rotor", "Rotor", "off", "disabled", "Rotator is disabled in config", "config")

    try:
        service = get_rotator_service()
        if not getattr(service, "rotor", None):
            return _service("rotor", "Rotor", "warn", "not ready", "Rotator service is enabled but not connected", "config")

        cached_status = getattr(service, "_status_cache", None)
        cached_at = float(getattr(service, "_status_cache_time", 0.0) or 0.0)
        if cached_status and (time.monotonic() - cached_at) < 15.0:
            azimuth = cached_status.get("azimuth")
            if azimuth is not None:
                return _service("rotor", "Rotor", "ok", f"{round(float(azimuth))} deg", "Rotor azimuth available")

        status = await asyncio.wait_for(service.get_rotor_status(), timeout=ROTOR_HEALTH_TIMEOUT_SEC)
        azimuth = status.get("azimuth")
        if azimuth is None:
            return _service("rotor", "Rotor", "warn", "no az", "Rotor did not return azimuth", "rotor-refresh")
        return _service("rotor", "Rotor", "ok", f"{round(float(azimuth))} deg", "Rotor azimuth available")
    except Exception as exc:
        logger.debug("Rotor health check failed: %s", exc)
        return _service("rotor", "Rotor", "warn", "error", str(exc), "rotor-refresh")


def _ft8_health() -> Dict[str, Any]:
    if not getattr(config, "FT8_ENABLED", True):
        return _service("ft8", "Digital", "off", "disabled", "FT8/FT4 service is disabled in config", "config")

    try:
        stats = get_ft8_service().get_stats()
        mode = stats.get("mode") or getattr(config, "FT8_MODE", "FT8")
        decoded = int(stats.get("decoded_count") or 0)
        decoder_status = stats.get("decoder_status") or "unknown"
        if stats.get("enabled"):
            status = "ok" if decoder_status == "available" else "warn"
            return _service(
                "ft8",
                "Digital",
                status,
                f"{mode} {decoded}",
                f"Decoder {decoder_status}; {decoded} decoded messages",
                "digital",
            )
        return _service("ft8", "Digital", "off", str(mode), "Digital service is configured but stopped", "digital")
    except Exception as exc:
        logger.debug("Digital health check failed: %s", exc)
        return _service("ft8", "Digital", "warn", "error", str(exc), "digital")


def _wsjtx_health() -> Dict[str, Any]:
    try:
        health = get_wsjtx_service().get_health()
        return _service(
            "wsjtx",
            "WSJT",
            health.get("status") or "unknown",
            health.get("value") or "",
            health.get("detail") or "",
            "wsjtx-config",
        )
    except Exception as exc:
        logger.debug("WSJT health check failed: %s", exc)
        return _service("wsjtx", "WSJT", "warn", "error", str(exc), "wsjtx-config")

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
    current_mox = getattr(flex, "current_mox", None)
    return {
        "frequency": getattr(flex, "current_freq", None) or 14.074,
        "mode": getattr(flex, "current_mode", None) or "USB",
        "filter_lo": getattr(flex, "current_filter_lo", None) or 100,
        "filter_hi": getattr(flex, "current_filter_hi", None) or 2900,
        "volume": getattr(flex, "current_volume", None) or 50,
        "drive": getattr(flex, "current_rfpower", None) or 31,
        "tune_power": getattr(flex, "current_tunepower", None) or 18,
        "mic_level": getattr(flex, "current_miclevel", None) or 32,
        "mox": bool(current_mox) if current_mox is not None else False,
        "interlock_state": getattr(flex, "current_interlock_state", None) or "",
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
    """Get the Wavelog local read-cache sync status."""
    context = get_app_context(request)
    status = await _sync_status_fast(context)
    if context.wavelog_sync_manager:
        return {
            "syncing": bool(status.get("syncing")),
            "last_sync": status.get("last_sync"),
            "total_records": status.get("total_records", 0),
            "new_records_this_sync": status.get("last_sync_added", 0),
            "records_updated": status.get("last_sync_updated", 0),
            "next_sync_in": 0,
            **status,
        }

    return status


@router.get("/api/service-health")
async def get_service_health(request: Request):
    """Return a compact operating-status summary for the main station services."""
    started = time.perf_counter()
    context = get_app_context(request)
    flex = context.flex
    radio_connected = bool(flex and getattr(flex, "sock", None))
    services = []

    frequency = getattr(flex, "current_freq", None) if flex else None
    mode = getattr(flex, "current_mode", None) if flex else None
    radio_value = f"{float(frequency):.3f} {mode or ''}".strip() if frequency else "offline"
    services.append(_service(
        "radio",
        "Radio",
        "ok" if radio_connected else "off",
        radio_value,
        "FlexRadio socket connected" if radio_connected else "Radio socket is not connected",
    ))

    cluster = _cluster_status(context.cluster_client)
    cluster_name = cluster.get("activeName") or cluster.get("host") or "cluster"
    cluster_detail = f"{cluster.get('host') or ''}:{cluster.get('port') or ''}".strip(":")
    services.append(_service(
        "cluster",
        "Cluster",
        "ok" if cluster["connected"] else "off",
        cluster_name,
        cluster_detail or "DX cluster is not connected",
        None if cluster["connected"] else "cluster-reconnect",
    ))

    sync_status = _cached_sync_status(context)
    wavelog_configured = bool(getattr(config, "WAVELOG_ENABLED", True) and config.WAVELOG_API_URL and config.WAVELOG_API_KEY)
    outbox_status = get_qso_outbox().status()
    outbox_queued = int(outbox_status.get("queued") or 0)
    if not getattr(config, "WAVELOG_ENABLED", True):
        wavelog = _service("wavelog", "Wavelog", "off", "disabled", "Wavelog integration is disabled", "config")
    elif not wavelog_configured:
        wavelog = _service("wavelog", "Wavelog", "warn", "missing cfg", "Wavelog URL or API key is missing", "config")
    elif outbox_queued:
        wavelog = _service("wavelog", "Wavelog", "warn", f"{outbox_queued} queued", "Offline upload outbox has queued QSOs", "outbox-retry")
    elif sync_status.get("syncing") or sync_status.get("status") == "busy":
        wavelog = _service("wavelog", "Wavelog", "busy", "syncing", "Wavelog local sync is running", "sync")
    elif sync_status.get("status_stale"):
        records = int(sync_status.get("total_records") or 0)
        wavelog = _service("wavelog", "Wavelog", "warn", f"{records} QSOs", "Using cached Wavelog sync status", "sync")
    elif sync_status.get("last_sync_error"):
        records = int(sync_status.get("total_records") or 0)
        wavelog = _service("wavelog", "Wavelog", "warn", f"{records} QSOs", str(sync_status.get("last_sync_error")), "sync")
    else:
        records = int(sync_status.get("total_records") or 0)
        wavelog = _service("wavelog", "Wavelog", "ok", f"{records} QSOs", "Wavelog configured and local sync is ready", "sync")
    services.append(wavelog)

    if not getattr(config, "QRZ_ENABLED", True):
        qrz = _service("qrz", "QRZ", "off", "disabled", "QRZ integration is disabled", "config")
    elif config.QRZ_USERNAME and config.QRZ_PASSWORD:
        qrz = _service("qrz", "QRZ", "ok", config.QRZ_USERNAME, "QRZ credentials configured")
    else:
        qrz = _service("qrz", "QRZ", "warn", "missing cfg", "QRZ username or password is missing", "config")
    services.append(qrz)

    if should_use_postgres():
        dsn_configured = bool(get_postgres_dsn())
        services.append(_service(
            "datastore",
            "Data Store",
            "ok" if dsn_configured else "warn",
            "PostgreSQL" if dsn_configured else "missing cfg",
            "PostgreSQL local read cache is selected",
            None if dsn_configured else "config",
        ))
    else:
        spots_db = _db_file_summary(config.DATA_DIR / "spots.duckdb")
        qso_db = _db_file_summary(config.DATA_DIR / "qso_log.duckdb")
        db_ok = spots_db["exists"] and qso_db["exists"]
        db_value = f"spots {'ok' if spots_db['exists'] else 'missing'} / qso {'ok' if qso_db['exists'] else 'missing'}"
        services.append(_service(
            "datastore",
            "Data Store",
            "ok" if db_ok else "warn",
            db_value,
            f"Legacy spots DB: {spots_db['path']}; QSO DB: {qso_db['path']}",
        ))

    services.append(_ft8_health())
    services.append(_wsjtx_health())
    services.append(await _rotor_health())

    browser_clients = len(context.websocket_clients or [])
    services.append(_service(
        "websocket",
        "Browser",
        "ok" if browser_clients else "warn",
        f"{browser_clients} client{'s' if browser_clients != 1 else ''}",
        "Live browser websocket clients connected" if browser_clients else "No live browser websocket clients registered",
    ))

    summary = {"ok": 0, "warn": 0, "off": 0, "busy": 0}
    for item in services:
        status = item.get("status")
        summary[status] = summary.get(status, 0) + 1

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "summary": summary,
        "services": services,
    }
