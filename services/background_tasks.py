"""
Background Tasks Service
Extracted from main.py - handles all background async operations
"""

import asyncio
import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Import required modules
from radio_control.spot_processor import (
    band_from_khz,
    infer_mode,
    extract_special,
    clean_comment,
    classify_spot_source,
)
from radio_control.spot_intelligence import enrich_spot_intelligence
from radio_control.spot_aggregation import upsert_live_spot
from radio_control.local_heard import correlate_local_heard
from radio_control.spots_logger import log_spot
from radio_control.spot_classification import classify_call_status, classify_dxcc_status

logger = logging.getLogger(__name__)


BroadcastStatus = Callable[[dict], Awaitable[None]]
BroadcastSpots = Callable[[List[Dict]], Awaitable[None]]


@dataclass
class BackgroundTaskService:
    """Runtime dependencies and task handles for backend background workers."""

    context: Any
    broadcast_status: BroadcastStatus
    broadcast_spots: BroadcastSpots
    tasks: List[asyncio.Task] = field(default_factory=list)
    rbn_direct_task: Optional[asyncio.Task] = None


_service: Optional[BackgroundTaskService] = None


def configure_background_tasks(
    context: Any,
    broadcast_stat_func: BroadcastStatus,
    broadcast_spot_func: BroadcastSpots,
) -> BackgroundTaskService:
    """Configure background workers from the application context."""
    global _service
    _service = BackgroundTaskService(context, broadcast_stat_func, broadcast_spot_func)
    return _service


def get_background_task_service() -> Optional[BackgroundTaskService]:
    return _service


def require_background_task_service() -> BackgroundTaskService:
    if _service is None:
        raise RuntimeError("Background task service is not configured")
    return _service


def _normalize_cty_longitude(value):
    """Convert CTY longitude convention (west positive) to map longitude (east positive)."""
    try:
        longitude = float(value)
    except (TypeError, ValueError):
        return None
    if abs(longitude) > 180:
        return None
    return -longitude


def set_globals(
    flex_ctl,
    ws_clients,
    dx_cache,
    cluster,
    cluster_conn,
    cty_res,
    classif,
    wavelog_sync,
    sync_stats,
    broadcast_stat_func,
    broadcast_spot_func
):
    """Compatibility wrapper for older startup wiring."""
    context = SimpleNamespace(
        flex=flex_ctl,
        websocket_clients=ws_clients,
        dx_spots_cache=dx_cache,
        cluster_client=cluster,
        cluster_connected=cluster_conn,
        cty_resolver=cty_res,
        classifier=classif,
        wavelog_sync_manager=wavelog_sync,
        sync_status=sync_stats,
    )
    return configure_background_tasks(context, broadcast_stat_func, broadcast_spot_func)


async def poll_radio_status():
    """Poll radio for status updates - continuous sync for all parameters"""
    service = require_background_task_service()
    context = service.context
    consecutive_failures = 0
    max_failures = 5
    
    while True:
        try:
            flex = context.flex
            if flex:
                # Check socket health - reconnect if needed
                if not flex.sock:
                    logger.warning("⚠️  Radio socket lost - reconnecting...")
                    await asyncio.to_thread(flex.connect)
                    consecutive_failures += 1
                else:
                    # Read status updates from radio
                    success = await asyncio.to_thread(flex.refresh_radio_state)
                    if not success:
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 0

                    # Get only actual state changes (no smeter spam)
                    status_update = flex.last_state_changed.copy() if flex.last_state_changed else {}

                    # Map 'frequency' field if present (backend may use 'freq')
                    if 'freq' in status_update:
                        status_update['frequency'] = status_update.pop('freq')
                        logger.info(f"📡 SYNC: frequency={status_update['frequency']:.6f} MHz")

                    if status_update:
                        logger.debug(f"🔄 Broadcasting changes: {list(status_update.keys())}")
                        # Log significant changes
                        if 'mode' in status_update:
                            logger.info(f"📡 SYNC: mode={status_update['mode']}")
                        if 'volume' in status_update:
                            logger.info(f"📡 SYNC: volume={status_update['volume']}")
                        if 'filter_lo' in status_update or 'filter_hi' in status_update:
                            logger.info(f"📡 SYNC: filter={status_update.get('filter_lo', '?')}-{status_update.get('filter_hi', '?')} Hz")
                        if 'drive' in status_update:
                            logger.info(f"📡 SYNC: drive={status_update['drive']}")
                        
                        await service.broadcast_status(status_update)
                        flex.last_state_changed = {}
                    
                    # Force reconnect if too many consecutive failures
                    if consecutive_failures > max_failures:
                        logger.error(f"❌ Too many consecutive failures ({consecutive_failures}), forcing reconnect...")
                        try:
                            if flex.sock:
                                flex.sock.close()
                        except Exception:
                            pass
                        flex.sock = None
                        consecutive_failures = 0

            # SmartSDR sends subscribed state changes asynchronously. Polling
            # the socket once per second is enough to drain pending messages
            # without creating noisy radio/client activity.
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.error(f"Poll error: {e}")
            consecutive_failures += 1
            await asyncio.sleep(1.0)


async def monitor_cluster_status():
    """Monitor cluster connection status and broadcast to clients"""
    service = require_background_task_service()
    context = service.context

    last_status = None

    while True:
        try:
            cluster_client = context.cluster_client
            current_connected = cluster_client.connected if cluster_client else False

            # Only broadcast when status changes
            if current_connected != last_status:
                status = {
                    "cluster_status": "connected" if current_connected else "disconnected",
                    "cluster_connected": current_connected
                }
                
                # Add cluster info if connected
                if current_connected and cluster_client and hasattr(cluster_client, 'get_status'):
                    try:
                        cluster_info = cluster_client.get_status()
                        status["cluster_info"] = {
                            "activeName": cluster_info.get('active_name', ''),
                            "host": cluster_info.get('host', ''),
                            "port": cluster_info.get('port', '')
                        }
                    except Exception as e:
                        logger.debug(f"Could not get cluster info: {e}")
                
                logger.info(f"🔗 Cluster status: {'✅ Connected' if current_connected else '❌ Disconnected'}")
                await service.broadcast_status(status)
                last_status = current_connected
                context.cluster_connected = current_connected

            # Check every 3 seconds
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Cluster status monitor error: {e}")
            await asyncio.sleep(5)


async def process_cluster_spot(spot_data: dict):
    """Process spot from cluster - classify and store"""
    service = require_background_task_service()
    context = service.context
    cty_resolver = context.cty_resolver
    classifier = context.classifier
    dx_spots_cache = context.dx_spots_cache

    try:
        freq_khz = spot_data['freq_khz']
        freq_khz_str = spot_data.get('freq_khz_str', str(freq_khz))  # Original string from cluster
        dxcall = spot_data['dxcall']
        spotter = spot_data['spotter']
        raw_comment = spot_data['comment']
        timestamp = spot_data['timestamp']

        # Clean comment
        comment = clean_comment(raw_comment)

        # Determine band and mode
        band = band_from_khz(freq_khz)
        emode = infer_mode(comment, band, freq_khz)
        spot_source, rbl_group = classify_spot_source(spotter, comment, emode)
        spot_data["spot_source"] = spot_source
        spot_data["rbl_mode_group"] = rbl_group

        # Resolve country/DXCC using cty.dat (with DXCC from CSV when available)
        dxcc, entity, cq = None, None, None
        latitude, longitude = None, None
        location_source = None
        location_confidence = None
        if cty_resolver:
            # Use lookup() to get info from cty.dat + DXCC from CSV
            info = cty_resolver.lookup(dxcall)
            dxcc = info.get('dxcc')
            entity = info.get('country')
            cq = info.get('cq')
            latitude = info.get('latitude')
            longitude = _normalize_cty_longitude(info.get('longitude'))
            if latitude is not None and longitude is not None:
                location_source = "cty_exact" if info.get("exact_match") else "cty_prefix"
                location_confidence = "medium" if info.get("exact_match") else "low"

        # ✅ ALWAYS have a country - never "Unknown"
        country = entity.upper() if entity else "UNKNOWN"
        cq_display = str(cq) if cq is not None else "-"

        # Classify spot
        call_status = "Unknown"
        dxcc_status = "Unknown"
        tag = None

        if classifier:
            # Call classification using Wavelog API (more reliable than direct DB)
            # These are now async calls using the Wavelog API
            try:
                call_worked, call_conf, call_new_band, call_new_mode, call_bandmode_conf = (
                    await classifier.call_status_flags(dxcall, band, emode)
                )

                call_status = classify_call_status(
                    call_worked,
                    call_new_band,
                    call_new_mode,
                    call_bandmode_conf,
                )
            except Exception as e:
                logger.warning(f"Error getting call status for {dxcall}: {e}")
                call_status = "Unknown"

            # DXCC classification (using API lookups via private_lookup with callsign context)
            if dxcc is not None:
                try:
                    dxcc_overall = await classifier.dxcc_overall(
                        dxcc,
                        callsign=dxcall,
                        allow_unconfirmed_fallback=False,
                    )
                    dxcc_bandmode = await classifier.dxcc_bandmode_flags(
                        dxcc,
                        band,
                        emode,
                        callsign=dxcall,
                        allow_unconfirmed_fallback=False,
                    )

                    if dxcc_overall is None or dxcc_bandmode is None:
                        dxcc_status = "Unknown"
                        tag = None
                    else:
                        dx_worked, dx_conf = dxcc_overall
                        dx_new_band, dx_new_mode, dx_bandmode_conf = dxcc_bandmode
                        dxcc_display = classify_dxcc_status(
                            dx_worked,
                            dx_conf,
                            dx_new_band,
                            dx_new_mode,
                            dx_bandmode_conf,
                        )
                        dxcc_status = dxcc_display.status
                        tag = dxcc_display.tag

                except Exception as e:
                    logger.warning(f"Error getting DXCC status for DXCC {dxcc}: {e}")
                    dxcc_status = "Unknown"
            else:
                # DXCC couldn't be resolved - show "Unknown" instead of blank
                dxcc_status = "Unknown"
        
        # Log spot to persistent database WITH classifications
        try:
            result = await asyncio.to_thread(log_spot, spot_data, call_status, dxcc_status)
            if not result:
                logger.error(f"❌ Spot NOT saved to database: {dxcall} on {band}/{emode} - log_spot returned False")
            else:
                logger.debug(f"✅ Spot saved: {dxcall} on {band}/{emode}")
        except Exception as e:
            logger.error(f"❌ Exception logging spot to database: {dxcall} - {e}", exc_info=True)

        # Extract special tags
        special_tag = extract_special(comment)

        # Resolve spotter's country/continent
        spotter_continent = None
        if cty_resolver and spotter:
            spotter_info = cty_resolver.lookup(spotter)
            spotter_continent = spotter_info.get('continent')

        # Create spot object
        # IMPORTANT: Store BOTH the original string (for display) and float (for calculations)
        # The string preserves full precision from the cluster
        gridsquare = None
        if latitude is not None and longitude is not None:
            try:
                from radio_control.rotor_math import latlon_to_grid
                gridsquare = latlon_to_grid(latitude, longitude, precision=6)
            except Exception:
                gridsquare = None

        spot = {
            'callsign': dxcall,
            'frequency': freq_khz_str,             # Original string from cluster (kHz) - for display
            'frequency_mhz': freq_khz / 1000.0,    # Float in MHz - for calculations/tuning
            'spotter': spotter,
            'spotter_continent': spotter_continent,  # Spotter's continent for filtering
            'mode': emode,
            'spot_source': spot_source,
            'rbl_mode_group': rbl_group,
            'band': band,
            'comment': comment,
            'country': country,
            'dxcc': dxcc,
            'cq': cq_display,
            'call_status': call_status,
            'dxcc_status': dxcc_status,
            'special': special_tag,
            'tag': tag,
            'timestamp': timestamp.timestamp(),
            'time': timestamp.strftime('%H:%M:%S'),
            'latitude': latitude,
            'longitude': longitude,
            'gridsquare': gridsquare,
            'location_source': location_source,
            'location_confidence': location_confidence,
        }
        try:
            from services.ft8_service import get_ft8_service
            from radio_control import config

            decoded_messages = get_ft8_service().get_decoded_messages(limit=100)
            correlate_local_heard(spot, decoded_messages, mycall=getattr(config, "MY_STATION", ""))
        except Exception as e:
            logger.debug("Could not correlate spot with local decodes: %s", e)
        enrich_spot_intelligence(spot)
        try:
            activity_intelligence = getattr(context, "activity_intelligence", None)
            if activity_intelligence:
                activity_intelligence.enrich_spot(spot)
        except Exception:
            logger.debug("Could not enrich spot with Activity Intelligence", exc_info=True)

        # Add to cache (keep last 200 visible rows, aggregating repeated RBL spots)
        spot, was_merged = upsert_live_spot(dx_spots_cache, spot, max_len=200)
        if was_merged:
            logger.debug(
                "Aggregated repeated spot: %s %s/%s seen x%s",
                spot.get("callsign"),
                spot.get("band"),
                spot.get("mode"),
                spot.get("aggregate_count"),
            )

        # Broadcast to connected clients
        await service.broadcast_spots([spot])

        # Send spot to SmartSDR panadapter
        flex = context.flex
        if flex and flex.sock:
            try:
                # Map DXCC status to color and call status to abbreviation
                from radio_control.utils import get_dxcc_color, get_call_status_abbreviation
                color = get_dxcc_color(dxcc_status)
                status_label = get_call_status_abbreviation(call_status)

                # Append status label to callsign for panadapter display (with space for readability)
                display_callsign = f"{dxcall} {status_label}" if status_label else dxcall

                # Send spot to radio panadapter (rx_mhz, callsign, mode, source, spotter, comment, lifetime, priority, color)
                flex.add_spot(
                    rx_mhz=freq_khz / 1000.0,
                    callsign=display_callsign,
                    mode=emode,
                    source="cluster",
                    spotter=spotter,
                    comment=f"{country} • {comment}" if country != "-" else comment,
                    lifetime=3600,  # 1 hour
                    priority=3,
                    color=color,
                    ts_epoch=int(timestamp.timestamp())
                )
                logger.debug(f"Spot sent to SmartSDR: {display_callsign} {freq_khz:.1f} kHz [Color: {color}]")
            except Exception as e:
                logger.warning(f"Failed to send spot to SmartSDR: {e}")

        logger.info(f"📡 Spot: {dxcall} {freq_khz:.1f} kHz {emode} [{call_status}] {comment[:50]}")

    except Exception as e:
        logger.error(f"Spot processing error: {e}")


async def poll_dx_spots():
    """Monitor spot cache (disabled - using real-time cluster only)"""
    service = require_background_task_service()
    context = service.context

    while True:
        try:
            # Just monitor - all spots come from cluster
            await asyncio.sleep(30.0)

            # Log stats
            dx_spots_cache = context.dx_spots_cache
            if dx_spots_cache:
                logger.debug(f"Spot cache: {len(dx_spots_cache)} spots")
                if context.cluster_client:
                    logger.debug(f"Cluster connected: {context.cluster_client.connected}")

        except Exception as e:
            logger.error(f"Spot monitor error: {e}")
            await asyncio.sleep(30.0)


async def poll_activity_intelligence():
    """Refresh external Activity Intelligence sources without blocking core services."""
    service = require_background_task_service()
    context = service.context

    while True:
        try:
            activity_intelligence = getattr(context, "activity_intelligence", None)
            if activity_intelligence:
                await activity_intelligence.refresh_due_sources(force=False)
                rbn_settings = activity_intelligence.settings.get("rbn", {})
                rbn_enabled = rbn_settings.get("enabled", True) and rbn_settings.get("directTelnet", False)
                if rbn_enabled and (service.rbn_direct_task is None or service.rbn_direct_task.done()):
                    service.rbn_direct_task = asyncio.create_task(activity_intelligence.run_direct_rbn_telnet())
                    service.tasks.append(service.rbn_direct_task)
                    logger.info("✅ Direct RBN telnet task started")
                elif not rbn_enabled and service.rbn_direct_task and not service.rbn_direct_task.done():
                    service.rbn_direct_task.cancel()
                    service.rbn_direct_task = None
                    logger.info("⏹️ Direct RBN telnet task stopped")
            await asyncio.sleep(60.0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Activity Intelligence refresh loop error: %s", e)
            await asyncio.sleep(120.0)


async def start_background_tasks():
    """Start all background tasks"""
    service = require_background_task_service()
    tasks = service.tasks

    logger.info("🚀 Starting background tasks...")

    # Start radio polling
    radio_task = asyncio.create_task(poll_radio_status())
    tasks.append(radio_task)
    logger.info("✅ Radio status polling started")

    # Start cluster monitoring
    cluster_task = asyncio.create_task(monitor_cluster_status())
    tasks.append(cluster_task)
    logger.info("✅ Cluster status monitoring started")

    # Start spot polling (monitoring only)
    spots_task = asyncio.create_task(poll_dx_spots())
    tasks.append(spots_task)
    logger.info("✅ Spot cache monitoring started")

    if getattr(service.context, "activity_intelligence", None):
        activity_task = asyncio.create_task(poll_activity_intelligence())
        tasks.append(activity_task)
        logger.info("✅ Activity Intelligence refresh task started")

    # Start Wavelog local read-cache sync if manager is available
    if service.context.wavelog_sync_manager:
        from radio_control.wavelog_duckdb_sync import periodic_wavelog_sync

        wavelog_task = asyncio.create_task(periodic_wavelog_sync())
        tasks.append(wavelog_task)
        logger.info("✅ Wavelog local read-cache periodic sync task started")

    if service.context.wavelog_client:
        from radio_control import config
        from radio_control.qso_outbox import get_qso_outbox

        outbox_task = asyncio.create_task(
            get_qso_outbox().replay_periodically(
                service.context.wavelog_client,
                interval_seconds=getattr(config, "WAVELOG_OUTBOX_RETRY_INTERVAL", 60),
                max_records=getattr(config, "WAVELOG_OUTBOX_RETRY_BATCH_SIZE", 20),
            )
        )
        tasks.append(outbox_task)
        logger.info("✅ Wavelog offline outbox retry task started")

    logger.info(f"✅ All background tasks started ({len(tasks)} tasks)")


async def stop_background_tasks():
    """Stop all background tasks"""
    service = get_background_task_service()
    if service is None:
        return

    tasks = service.tasks

    logger.info("⏹️ Stopping background tasks...")

    for task in tasks:
        if not task.done():
            task.cancel()

    # Wait for tasks to complete
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        pass

    tasks.clear()
    logger.info("✅ All background tasks stopped")


def get_background_task_status():
    """Get status of background tasks"""
    service = get_background_task_service()
    tasks = service.tasks if service else []
    return {
        "total_tasks": len(tasks),
        "running_tasks": sum(1 for task in tasks if not task.done()),
        "completed_tasks": sum(1 for task in tasks if task.done()),
        "tasks": [
            {
                "name": task.get_name() if hasattr(task, 'get_name') else str(task),
                "done": task.done(),
                "cancelled": task.cancelled() if task.done() else False
            }
            for task in tasks
        ]
    }
