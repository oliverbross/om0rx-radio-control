"""
Background Tasks Service
Extracted from main.py - handles all background async operations
"""

import asyncio
import json
import logging
import time as wall_time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
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

WSJTX_ACTIVE_STATUS_MAX_AGE_MS = 45_000


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
    wsjtx_last_decode_key: Optional[str] = None
    wsjtx_seen_decode_keys: List[str] = field(default_factory=list)
    wsjtx_ingested_decodes: int = 0
    wsjtx_ingest_last_error: Optional[str] = None
    wsjtx_planner_last_action: Optional[str] = None
    wsjtx_planner_last_error: Optional[str] = None


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


def _should_queue_digital_spot_for_automation(spot: Dict[str, Any], settings: Any = None) -> bool:
    mode = str(spot.get("mode") or "").strip().upper()
    if mode not in {"FT8", "FT4", "FT2"}:
        return False
    try:
        from services.digital_automation import (
            payload_has_dxcc_hunt_interest,
            payload_has_reference_hunt_interest,
            payload_matches_hunter_spot_filters,
        )

        if payload_has_dxcc_hunt_interest(spot):
            return True
        return bool(
            settings
            and payload_has_reference_hunt_interest(spot, settings)
            and payload_matches_hunter_spot_filters(spot, settings)
        )
    except Exception:
        dxcc_status = str(spot.get("dxcc_status") or "").strip().lower()
        return dxcc_status in {"atno", "worked"} or "new band" in dxcc_status or "new mode" in dxcc_status


def _queue_digital_spot_for_automation(context: Any, spot: Dict[str, Any]) -> None:
    try:
        from services.ft8_service import get_ft8_service

        controller = getattr(get_ft8_service(), "automation_controller", None)
        if not controller:
            return
        if not _should_queue_digital_spot_for_automation(spot, controller.settings):
            return
        classifier = getattr(context, "classifier", None)
        qso_status_store = getattr(classifier, "qso_status_store", None) if classifier else None
        if hasattr(controller, "set_status_sources"):
            controller.set_status_sources(
                qso_status_store=qso_status_store,
                cty_resolver=getattr(context, "cty_resolver", None),
            )
        payload = dict(spot)
        source = str(payload.get("spot_source") or payload.get("source") or "spot").strip().lower()
        payload["source"] = "rbl" if source == "rbl" else "cluster"
        payload["heard"] = bool(payload.get("local_heard"))
        payload["enableTx"] = False
        if payload.get("frequency_mhz") is not None:
            payload["base_frequency"] = payload["frequency_mhz"]
        target = controller.ingest_target(payload)
        if target:
            logger.info(
                "Queued digital spot listen candidate: %s %s/%s %s MHz [%s/%s]",
                target.call,
                target.band,
                target.mode,
                target.dial_frequency,
                target.call_status,
                target.dxcc_status,
            )
    except Exception as exc:
        logger.debug("Could not queue digital spot for automation: %s", exc, exc_info=True)


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
    last_active_status_query = 0.0
    last_authoritative_status_broadcast = 0.0
    
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

                    # Subscription updates can be sparse, and a missed slice
                    # update leaves the UI with stale frequency/mode. When the
                    # radio stream is quiet, do a low-rate explicit snapshot.
                    now = wall_time.time()
                    radio_quiet_for = now - float(getattr(flex, "last_radio_message_time", 0) or 0)
                    needs_snapshot = (
                        not getattr(flex, "current_freq", None)
                        or not getattr(flex, "current_mode", None)
                        or radio_quiet_for > 5.0
                    )
                    recent_command = now - float(getattr(flex, "last_command_time", 0) or 0) < 2.5
                    if success and needs_snapshot and not recent_command and now - last_active_status_query > 5.0:
                        snapshot_started = wall_time.time()
                        levels = await asyncio.to_thread(flex.get_current_levels, 0.6)
                        last_active_status_query = now
                        if float(getattr(flex, "last_command_time", 0) or 0) > snapshot_started:
                            levels = {}
                        if levels:
                            if "freq" in levels:
                                status_update.setdefault("freq", levels["freq"])
                            if "mode" in levels:
                                status_update.setdefault("mode", levels["mode"])
                            if "filter_lo" in levels:
                                status_update.setdefault("filter_lo", levels["filter_lo"])
                            if "filter_hi" in levels:
                                status_update.setdefault("filter_hi", levels["filter_hi"])
                            if "audio_level" in levels:
                                status_update.setdefault("volume", levels["audio_level"])
                            if "rfpower" in levels:
                                status_update.setdefault("drive", levels["rfpower"])
                            if "tunepower" in levels:
                                status_update.setdefault("tune_power", levels["tunepower"])
                            if "miclevel" in levels:
                                status_update.setdefault("mic_level", levels["miclevel"])
                            if "mox" in levels:
                                status_update.setdefault("mox", levels["mox"])
                            if "interlock_state" in levels:
                                status_update.setdefault("interlock_state", levels["interlock_state"])
                            if "vox_enable" in levels:
                                status_update.setdefault("vox_enabled", levels["vox_enable"])

                    # Map 'frequency' field if present (backend may use 'freq')
                    if 'freq' in status_update:
                        status_update['frequency'] = status_update.pop('freq')
                        logger.info(f"📡 SYNC: frequency={status_update['frequency']:.6f} MHz")

                    # A frequency change notification is easy for a browser to
                    # miss during a reconnect. Repeat the cached authoritative
                    # tuning state at a low rate so one lost WebSocket frame can
                    # never leave the UI parked on an old band indefinitely.
                    if now - last_authoritative_status_broadcast >= 5.0:
                        if getattr(flex, "current_freq", None) is not None:
                            status_update.setdefault("frequency", flex.current_freq)
                        if getattr(flex, "current_mode", None):
                            status_update.setdefault("mode", flex.current_mode)
                        last_authoritative_status_broadcast = now

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

                    context.radio_snapshot = {
                        "connected": bool(flex.sock),
                        "known": bool(flex.sock and flex.current_freq is not None),
                        "stale": not bool(flex.sock),
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                        "frequency": flex.current_freq,
                        "mode": flex.current_mode,
                        "filter_lo": flex.current_filter_lo,
                        "filter_hi": flex.current_filter_hi,
                        "volume": flex.current_volume,
                        "drive": flex.current_rfpower,
                        "tune_power": flex.current_tunepower,
                        "mic_level": flex.current_miclevel,
                        "mox": flex.current_mox,
                        "interlock_state": flex.current_interlock_state,
                        "vox_enabled": flex.current_vox_enable,
                    }
                    
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

            else:
                context.radio_snapshot = {
                    **getattr(context, "radio_snapshot", {}),
                    "connected": False,
                    "known": False,
                    "stale": True,
                }

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
        call_worked = False
        call_new_band = False
        call_new_mode = False
        worked_before_date = None

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

            qso_status_store = getattr(classifier, "qso_status_store", None)
            if qso_status_store and hasattr(qso_status_store, "worked_before_date"):
                try:
                    worked_before_date = await asyncio.to_thread(
                        qso_status_store.worked_before_date,
                        dxcall,
                        band,
                        emode,
                    )
                except Exception:
                    logger.debug(
                        "Could not read worked-before date for %s %s %s",
                        dxcall,
                        band,
                        emode,
                        exc_info=True,
                    )
        
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
            'worked_before_date': worked_before_date,
            'needed': {
                'call': bool(not call_worked) if classifier else False,
            },
            'needed_on_band': {
                'call': bool(call_new_band) if classifier else False,
                'mode': bool(call_new_mode) if classifier else False,
            },
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
        _queue_digital_spot_for_automation(context, spot)

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


def _coerce_number(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _wsjtx_decode_key(decode: Dict[str, Any]) -> str:
    return "|".join(
        str(decode.get(key, ""))
        for key in ("time", "message", "deltaFrequency", "dialFrequency", "frequency", "ts")
    )


def _mode_from_wsjtx_decode(decode: Dict[str, Any], status: Dict[str, Any]) -> str:
    for candidate in (decode.get("mode"), status.get("mode")):
        mode = str(candidate or "").strip().upper()
        if mode in {"FT8", "FT4", "FT2"}:
            return mode
    return "FT8"


def _timestamp_from_wsjtx_qtime(value: Any) -> str:
    milliseconds = _coerce_number(value)
    now = datetime.now(timezone.utc)
    if milliseconds is None or milliseconds < 0:
        return now.isoformat()
    milliseconds = int(milliseconds) % 86_400_000
    seconds, millis = divmod(milliseconds, 1000)
    hour, remainder = divmod(seconds, 3600)
    minute, second = divmod(remainder, 60)
    decoded_time = time(hour=hour, minute=minute, second=second, microsecond=millis * 1000, tzinfo=timezone.utc)
    return datetime.combine(now.date(), decoded_time).isoformat()


def build_wsjtx_decode_automation_payload(
    status_payload: Dict[str, Any],
    decode_override: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Convert bridge /wsjtx/status into a Digital automation decoded target."""
    stats = status_payload.get("stats") if isinstance(status_payload.get("stats"), dict) else {}
    decode = decode_override if isinstance(decode_override, dict) else stats.get("lastDecode") if isinstance(stats.get("lastDecode"), dict) else {}
    last_status = stats.get("lastStatus") if isinstance(stats.get("lastStatus"), dict) else {}
    if not decode or not decode.get("message"):
        return None
    if decode.get("isNew") is False:
        return None

    dial_frequency = _coerce_number(decode.get("dialFrequency") or decode.get("frequency") or last_status.get("dialFrequency"))
    payload: Dict[str, Any] = {
        "source": "decoded",
        "decoder_source": "wsjtx",
        "heard": True,
        "message": str(decode.get("message") or "").strip(),
        "mode": _mode_from_wsjtx_decode(decode, last_status),
        "timestamp": _timestamp_from_wsjtx_qtime(decode.get("time")),
        "slot_start_utc": _timestamp_from_wsjtx_qtime(decode.get("time")),
    }

    delta_frequency = _coerce_number(decode.get("deltaFrequency"))
    if delta_frequency is not None:
        payload["freq"] = int(round(delta_frequency))
        payload["audio_offset"] = int(round(delta_frequency))

    snr = _coerce_number(decode.get("snr"))
    if snr is not None:
        payload["snr"] = snr

    if dial_frequency is not None and dial_frequency > 0:
        payload["dial_frequency"] = int(round(dial_frequency))
        payload["frequency_mhz"] = float(dial_frequency) / 1_000_000
        payload["base_frequency"] = float(dial_frequency) / 1_000_000
        try:
            payload["band"] = band_from_khz(float(dial_frequency) / 1000)
        except Exception:
            pass

    return payload


async def ingest_latest_wsjtx_decode_once() -> Optional[Dict[str, Any]]:
    """Ingest fresh bridge decodes into the backend automation queue."""
    service = require_background_task_service()
    try:
        from services.ft8_service import get_ft8_service
        from services.wsjtx import get_wsjtx_service

        bridge_status = await asyncio.to_thread(get_wsjtx_service().get_bridge_status)
        stats = bridge_status.get("stats") if isinstance(bridge_status, dict) else {}
        if not isinstance(stats, dict):
            return None

        raw_decodes = stats.get("recentDecodes")
        if isinstance(raw_decodes, list):
            decodes = [decode for decode in raw_decodes if isinstance(decode, dict)]
        else:
            decode = stats.get("lastDecode")
            decodes = [decode] if isinstance(decode, dict) else []
        if not decodes:
            return None

        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        fresh_decodes: list[Dict[str, Any]] = []
        for decode in decodes:
            ts = _coerce_number(decode.get("ts"))
            age_ms = (now_ms - ts) if ts else _coerce_number(stats.get("lastDecodeAgeMs"))
            if age_ms is None or age_ms > 90_000:
                continue
            key = _wsjtx_decode_key(decode)
            if not key or key in service.wsjtx_seen_decode_keys:
                continue
            fresh_decodes.append(decode)

        if not fresh_decodes:
            return None

        ft8_service = get_ft8_service()
        last_status = stats.get("lastStatus") if isinstance(stats.get("lastStatus"), dict) else {}
        if last_status:
            ft8_service.automation_controller.handle_wsjtx_status(last_status)
        classifier = getattr(service.context, "classifier", None)
        ft8_service.automation_controller.set_status_sources(
            qso_status_store=getattr(classifier, "qso_status_store", None) if classifier else None,
            cty_resolver=getattr(service.context, "cty_resolver", None),
        )
        selected_target = None
        for decode in fresh_decodes:
            key = _wsjtx_decode_key(decode)
            payload = build_wsjtx_decode_automation_payload(bridge_status, decode)
            service.wsjtx_seen_decode_keys.append(key)
            service.wsjtx_last_decode_key = key
            if not payload:
                continue
            target = ft8_service.automation_controller.ingest_target(payload)
            if target:
                selected_target = target
                service.wsjtx_ingested_decodes += 1
        if len(service.wsjtx_seen_decode_keys) > 500:
            service.wsjtx_seen_decode_keys = service.wsjtx_seen_decode_keys[-500:]
        service.wsjtx_ingest_last_error = None
        return selected_target.to_dict() if selected_target else None
    except Exception as exc:
        service.wsjtx_ingest_last_error = str(exc)
        logger.debug("WSJT-X decode ingest failed: %s", exc, exc_info=True)
        return None


def _planner_payload(controller: Any, bridge_status: Dict[str, Any]) -> Dict[str, Any]:
    stats = bridge_status.get("stats") if isinstance(bridge_status.get("stats"), dict) else {}
    last_status = stats.get("lastStatus") if isinstance(stats.get("lastStatus"), dict) else {}
    settings = controller.settings.to_dict()
    automation: Dict[str, Any] = {
        **settings,
        "enabled": bool(settings.get("enabled")),
        "autoCall": True,
        "autoCQ": False,
        "cqOnly": False,
        "spotHuntEnabled": bool(settings.get("spot_hunt_enabled")),
        "bandHopping": bool(settings.get("band_hopping")),
        "modeSwitching": bool(settings.get("mode_switching")),
        "requireHeardBeforeCall": True,
        "watchdogEnabled": True,
        "watchdogFT8": 2,
        "watchdogFT4": 2,
        "source": "backend-dxcc-hunt-planner",
    }
    mode = str(last_status.get("mode") or "").strip().upper()
    if mode:
        automation["currentMode"] = mode
    band = str(last_status.get("band") or "").strip().lower()
    if band:
        automation["currentBand"] = band
    dial_frequency = _coerce_number(last_status.get("dialFrequency") or last_status.get("frequency"))
    if dial_frequency:
        automation["dialFrequency"] = dial_frequency
    return {"source": "backend-dxcc-hunt-planner", "automation": automation}


def _fresh_wsjtx_status(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Return the last WSJT status only while it can describe live QSO state."""
    last_status = stats.get("lastStatus") if isinstance(stats.get("lastStatus"), dict) else {}
    if not last_status:
        return {}
    age_ms = _coerce_number(stats.get("lastStatusAgeMs"))
    if age_ms is None:
        status_ts = _coerce_number(last_status.get("ts"))
        if status_ts:
            age_ms = datetime.now(timezone.utc).timestamp() * 1000 - status_ts
    if age_ms is not None and age_ms > WSJTX_ACTIVE_STATUS_MAX_AGE_MS:
        return {}
    return last_status


def _post_wsjtx_planner_tick(payload: Dict[str, Any]) -> Dict[str, Any]:
    from radio_control import config

    url = f"http://127.0.0.1:{int(getattr(config, 'BACKEND_PORT', 8080))}/api/wsjtx/automation/tick"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    token = str(getattr(config, "CONTROL_TOKEN", "") or "")
    if token:
        headers["X-OM0RX-Control-Token"] = token
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2.5) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {"success": True}


async def run_wsjtx_automation_planner_once() -> Optional[Dict[str, Any]]:
    """Drive the backend planner continuously; WSJT-Z remains the radio/QSO executor."""
    service = require_background_task_service()
    try:
        from services.ft8_service import get_ft8_service
        from services.wsjtx import get_wsjtx_service

        ft8_service = get_ft8_service()
        controller = ft8_service.automation_controller
        if not controller.settings.enabled:
            return None
        bridge_status = await asyncio.to_thread(get_wsjtx_service().get_bridge_status)
        stats = bridge_status.get("stats") if isinstance(bridge_status, dict) else {}
        last_status = _fresh_wsjtx_status(stats) if isinstance(stats, dict) else {}
        status_outcome: Dict[str, Any] = {}
        if last_status:
            status_outcome = controller.handle_wsjtx_status(last_status)
        elif not controller.active_target_key and controller.active_qso_state not in {
            "idle", "completed", "logged", "failed", "aborted"
        }:
            controller.transition_active_qso("idle", reason="stale-wsjtx-status")

        qso_state = str(
            status_outcome.get("qso_state")
            or last_status.get("qsoState")
            or last_status.get("qso_state")
            or ""
        ).strip().lower().replace("-", "_")
        busy_states = {"calling", "in_qso", "waiting_rrr", "waiting_73", "transmitting", "tx"}
        if qso_state in busy_states and not controller.active_target_key:
            service.wsjtx_planner_last_action = "deferred-current-qso"
            service.wsjtx_planner_last_error = None
            return {"success": True, "action": "deferred", "reason": "finish-current-qso"}

        result = await asyncio.to_thread(
            _post_wsjtx_planner_tick,
            _planner_payload(controller, bridge_status),
        )
        service.wsjtx_planner_last_action = str(result.get("action") or "idle")
        service.wsjtx_planner_last_error = None
        return result
    except Exception as exc:
        service.wsjtx_planner_last_error = str(exc)
        logger.debug("WSJT-Z automation planner tick failed: %s", exc, exc_info=True)
        return None


async def poll_wsjtx_automation_planner():
    while True:
        try:
            await run_wsjtx_automation_planner_once()
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("WSJT-Z automation planner loop error: %s", exc, exc_info=True)
            await asyncio.sleep(2.0)


async def poll_wsjtx_decode_ingest():
    """Feed patched WSJT-X bridge decodes into the Digital automation ranker."""
    while True:
        try:
            await ingest_latest_wsjtx_decode_once()
            await asyncio.sleep(0.75)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("WSJT-X decode ingest loop error: %s", exc, exc_info=True)
            await asyncio.sleep(2.0)


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

    if getattr(service.context, "activity_intelligence", None):
        activity_task = asyncio.create_task(poll_activity_intelligence())
        tasks.append(activity_task)
        logger.info("✅ Activity Intelligence refresh task started")

    wsjtx_ingest_task = asyncio.create_task(poll_wsjtx_decode_ingest())
    tasks.append(wsjtx_ingest_task)
    logger.info("✅ WSJT-X decode automation ingest task started")

    wsjtx_planner_task = asyncio.create_task(poll_wsjtx_automation_planner())
    tasks.append(wsjtx_planner_task)
    logger.info("✅ WSJT-Z DXCC hunt planner started")

    # Start Wavelog local read-cache sync if manager is available
    if service.context.wavelog_sync_manager:
        from radio_control.wavelog_duckdb_sync import periodic_wavelog_sync

        wavelog_task = asyncio.create_task(periodic_wavelog_sync())
        tasks.append(wavelog_task)
        logger.info("✅ Wavelog local read-cache periodic sync task started")

    if service.context.wavelog_client:
        from radio_control import config
        from radio_control.qso_outbox import get_qso_outbox
        from services.qso_logging import record_qso_status_from_adif

        outbox_task = asyncio.create_task(
            get_qso_outbox().replay_periodically(
                service.context.wavelog_client,
                interval_seconds=getattr(config, "WAVELOG_OUTBOX_RETRY_INTERVAL", 60),
                max_records=getattr(config, "WAVELOG_OUTBOX_RETRY_BATCH_SIZE", 20),
                on_resolved_record=record_qso_status_from_adif,
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
        "wsjtx_decode_ingest": {
            "last_decode_key": service.wsjtx_last_decode_key if service else None,
            "ingested_decodes": service.wsjtx_ingested_decodes if service else 0,
            "last_error": service.wsjtx_ingest_last_error if service else None,
        },
        "wsjtx_automation_planner": {
            "last_action": service.wsjtx_planner_last_action if service else None,
            "last_error": service.wsjtx_planner_last_error if service else None,
        },
        "tasks": [
            {
                "name": task.get_name() if hasattr(task, 'get_name') else str(task),
                "done": task.done(),
                "cancelled": task.cancelled() if task.done() else False
            }
            for task in tasks
        ]
    }
