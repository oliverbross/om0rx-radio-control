"""
Background Tasks Service
Extracted from main.py - handles all background async operations
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
import concurrent.futures
from functools import partial

# Import required modules
from radio_control.spot_processor import band_from_khz, infer_mode, extract_special, clean_comment
from radio_control.spots_logger import get_spots_logger, log_spot
from radio_control.cty_resolvers import CtyDatResolver
from radio_control.classifier_api import ClassifierAPI

logger = logging.getLogger(__name__)

# Global state (will be set by main application)
flex = None
websocket_clients = []
dx_spots_cache = []
cluster_client = None
cluster_connected = False
cty_resolver = None
classifier = None
wavelog_sync_manager = None
sync_status = {
    "syncing": False,
    "last_sync": None,
    "total_records": 0,
    "new_records_this_sync": 0,
    "records_skipped": 0,
    "next_sync_in": 0,
    "adif_file_path": None,
    "adif_file_size": 0,
    "adif_file_modified": None,
    "adif_qso_count": 0,
}

# Import broadcast functions (will be injected)
broadcast_status = None
broadcast_spots = None


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
    """Set global variables from main application"""
    global flex, websocket_clients, dx_spots_cache, cluster_client, cluster_connected
    global cty_resolver, classifier, wavelog_sync_manager, sync_status
    global broadcast_status, broadcast_spots

    flex = flex_ctl
    websocket_clients = ws_clients
    dx_spots_cache = dx_cache
    cluster_client = cluster
    cluster_connected = cluster_conn
    cty_resolver = cty_res
    classifier = classif
    wavelog_sync_manager = wavelog_sync
    sync_status = sync_stats
    broadcast_status = broadcast_stat_func
    broadcast_spots = broadcast_spot_func


async def poll_radio_status():
    """Poll radio for status updates - continuous sync for all parameters"""
    consecutive_failures = 0
    max_failures = 5
    
    while True:
        try:
            if flex:
                # Check socket health - reconnect if needed
                if not flex.sock:
                    logger.warning("⚠️  Radio socket lost - reconnecting...")
                    flex.connect()
                    consecutive_failures += 1
                else:
                    # Read status updates from radio
                    success = flex.refresh_radio_state()
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
                        
                        await broadcast_status(status_update)
                        flex.last_state_changed = {}
                    
                    # Force reconnect if too many consecutive failures
                    if consecutive_failures > max_failures:
                        logger.error(f"❌ Too many consecutive failures ({consecutive_failures}), forcing reconnect...")
                        try:
                            if flex.sock:
                                flex.sock.close()
                        except:
                            pass
                        flex.sock = None
                        consecutive_failures = 0

            # Fast polling: 250ms for responsive 2-way sync
            # This ensures we catch changes from SmartSDR in real-time
            await asyncio.sleep(0.25)
        except Exception as e:
            logger.error(f"Poll error: {e}")
            consecutive_failures += 1
            await asyncio.sleep(1.0)


async def monitor_cluster_status():
    """Monitor cluster connection status and broadcast to clients"""
    global cluster_client, cluster_connected

    last_status = None

    while True:
        try:
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
                await broadcast_status(status)
                last_status = current_connected
                cluster_connected = current_connected

            # Check every 3 seconds
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Cluster status monitor error: {e}")
            await asyncio.sleep(5)


async def process_cluster_spot(spot_data: dict):
    """Process spot from cluster - classify and store"""
    global dx_spots_cache, cty_resolver, classifier

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

        # Resolve country/DXCC using cty.dat (with DXCC from CSV when available)
        dxcc, entity, cq = None, None, None
        latitude, longitude = None, None  # === FIX: Add coordinates ===
        if cty_resolver:
            # Use lookup() to get info from cty.dat + DXCC from CSV
            info = cty_resolver.lookup(dxcall)
            dxcc = info.get('dxcc')
            entity = info.get('country')
            cq = info.get('cq')
            latitude = info.get('latitude')  # === FIX: Get latitude ===
            longitude = info.get('longitude')  # === FIX: Get longitude ===

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
                call_worked, call_conf = await classifier.call_overall(dxcall)
                call_new_band, call_new_mode, call_bandmode_conf = await classifier.call_bandmode_flags(dxcall, band, emode)

                # Call status (band+mode specific) - Check worked FIRST to avoid "New Call" showing as "New Band"
                if not call_worked:
                    call_status = "New Call"
                elif call_bandmode_conf:
                    call_status = "Confirmed"
                elif call_new_band and call_new_mode:
                    call_status = "New Band+Mode"
                elif call_new_band:
                    call_status = "New Band"
                elif call_new_mode:
                    call_status = "New Mode"
                else:
                    call_status = "Worked"
            except Exception as e:
                logger.warning(f"Error getting call status for {dxcall}: {e}")
                call_status = "Unknown"

            # DXCC classification (using API lookups via private_lookup with callsign context)
            if dxcc is not None:
                try:
                    dx_worked, dx_conf = await classifier.dxcc_overall(dxcc, callsign=dxcall)
                    dx_new_band, dx_new_mode, dx_bandmode_conf = await classifier.dxcc_bandmode_flags(dxcc, band, emode, callsign=dxcall)

                    # DXCC status with C/W prefix (Confirmed/Worked overall status)
                    if not dx_worked:
                        dxcc_status = "ATNO"
                        tag = "ATNO"
                    elif dx_bandmode_conf:
                        # Confirmed on this exact band+mode
                        dxcc_status = "Confirmed"
                        tag = None
                    elif dx_new_band and dx_new_mode:
                        # Need both new band AND new mode
                        prefix = "C" if dx_conf else "W"
                        dxcc_status = f"{prefix}/New Band+Mode"
                        tag = "New band+mode"
                    elif dx_new_band:
                        # Need new band
                        prefix = "C" if dx_conf else "W"
                        dxcc_status = f"{prefix}/New Band"
                        tag = "New band"
                    elif dx_new_mode:
                        # Need new mode
                        prefix = "C" if dx_conf else "W"
                        dxcc_status = f"{prefix}/New Mode"
                        tag = "New mode"
                    else:
                        # Worked on this band+mode but not confirmed
                        dxcc_status = "Worked"
                        tag = "Worked"

                    # Override tag for Need LoTW (worked but not confirmed on this band+mode)
                    if not dx_bandmode_conf and dx_worked and not (dx_new_band or dx_new_mode):
                        tag = "Need LoTW"

                except Exception as e:
                    logger.warning(f"Error getting DXCC status for DXCC {dxcc}: {e}")
                    dxcc_status = "Unknown"
            else:
                # DXCC couldn't be resolved - show "Unknown" instead of blank
                dxcc_status = "Unknown"
        
        # Log spot to persistent database WITH classifications
        try:
            result = log_spot(spot_data, call_status, dxcc_status)
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
        gridsquare = None  # === FIX: Convert lat/lon to gridsquare for rotor ===
        if latitude is not None and longitude is not None:
            try:
                from rotor_math import latlon_to_grid
                gridsquare = latlon_to_grid(latitude, longitude, precision=6)
            except:
                gridsquare = None

        spot = {
            'callsign': dxcall,
            'frequency': freq_khz_str,             # Original string from cluster (kHz) - for display
            'frequency_mhz': freq_khz / 1000.0,    # Float in MHz - for calculations/tuning
            'spotter': spotter,
            'spotter_continent': spotter_continent,  # Spotter's continent for filtering
            'mode': emode,
            'band': band,
            'comment': comment,
            'country': country,
            'cq': cq_display,
            'call_status': call_status,
            'dxcc_status': dxcc_status,
            'special': special_tag,
            'tag': tag,
            'timestamp': timestamp.timestamp(),
            'time': timestamp.strftime('%H:%M:%S'),
            'latitude': latitude,  # === FIX: Add latitude from cty.dat ===
            'longitude': longitude,  # === FIX: Add longitude from cty.dat ===
            'gridsquare': gridsquare  # === FIX: Add gridsquare converted from lat/lon ===
        }

        # Add to cache (keep last 200 spots)
        dx_spots_cache.insert(0, spot)
        if len(dx_spots_cache) > 200:
            dx_spots_cache.pop()

        # Broadcast to connected clients
        await broadcast_spots([spot])

        # Send spot to SmartSDR panadapter
        if flex and flex.sock:
            try:
                # Map DXCC status to color and call status to abbreviation
                from utils import get_dxcc_color, get_call_status_abbreviation
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
    global dx_spots_cache

    while True:
        try:
            # Just monitor - all spots come from cluster
            await asyncio.sleep(30.0)

            # Log stats
            if dx_spots_cache:
                logger.debug(f"Spot cache: {len(dx_spots_cache)} spots")
                if cluster_client:
                    logger.debug(f"Cluster connected: {cluster_client.connected}")

        except Exception as e:
            logger.error(f"Spot monitor error: {e}")
            await asyncio.sleep(30.0)


def count_adif_records(file_path: str) -> int:
    """Count the number of QSO records in an ADIF file"""
    try:
        if not Path(file_path).exists():
            return 0

        count = 0
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # Count EOR (End Of Record) markers - each represents one QSO
                if '<eor>' in line.lower():
                    count += 1
        return count
    except Exception as e:
        logger.error(f"❌ Error counting ADIF records: {str(e)}")
        return 0


# DEPRECATED: Old ADIF→DuckDB sync - replaced by Wavelog→DuckDB sync
# This function is no longer used. The new sync logic is in backend/core/__init__.py
# and uses wavelog_duckdb_sync.py module instead of adif_sync.py
#
# async def periodic_adif_sync():
#     """Periodically sync ADIF file to DuckDB (every 30 seconds)"""
#     # This function has been replaced by periodic_wavelog_sync() in backend/core/__init__.py
#     pass


# === Task Management ===

_background_tasks = []

async def start_background_tasks():
    """Start all background tasks"""
    global _background_tasks

    logger.info("🚀 Starting background tasks...")

    # Start radio polling
    radio_task = asyncio.create_task(poll_radio_status())
    _background_tasks.append(radio_task)
    logger.info("✅ Radio status polling started")

    # Start cluster monitoring
    cluster_task = asyncio.create_task(monitor_cluster_status())
    _background_tasks.append(cluster_task)
    logger.info("✅ Cluster status monitoring started")

    # Start spot polling (monitoring only)
    spots_task = asyncio.create_task(poll_dx_spots())
    _background_tasks.append(spots_task)
    logger.info("✅ Spot cache monitoring started")

    # Start Wavelog→DuckDB sync if manager is available
    if wavelog_sync_manager:
        # Import the periodic_wavelog_sync from backend.core
        from backend.core import periodic_wavelog_sync
        wavelog_task = asyncio.create_task(periodic_wavelog_sync())
        _background_tasks.append(wavelog_task)
        logger.info("✅ Wavelog→DuckDB periodic sync task started")

    logger.info(f"✅ All background tasks started ({len(_background_tasks)} tasks)")


async def stop_background_tasks():
    """Stop all background tasks"""
    global _background_tasks

    logger.info("⏹️ Stopping background tasks...")

    for task in _background_tasks:
        if not task.done():
            task.cancel()

    # Wait for tasks to complete
    try:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    except asyncio.CancelledError:
        pass

    _background_tasks.clear()
    logger.info("✅ All background tasks stopped")


def get_background_task_status():
    """Get status of background tasks"""
    return {
        "total_tasks": len(_background_tasks),
        "running_tasks": sum(1 for task in _background_tasks if not task.done()),
        "completed_tasks": sum(1 for task in _background_tasks if task.done()),
        "tasks": [
            {
                "name": task.get_name() if hasattr(task, 'get_name') else str(task),
                "done": task.done(),
                "cancelled": task.cancelled() if task.done() else False
            }
            for task in _background_tasks
        ]
    }