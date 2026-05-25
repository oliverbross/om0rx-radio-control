"""
FlexRadio Web Control - Core Module
Contains imports, global state, and basic app initialization
"""

import asyncio
import logging
import time
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sys
import os
from pathlib import Path
import json
import mysql.connector as mysql

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import existing code
from dxbridge import FlexCtl, DX_RE
import config
from cluster_client import ClusterClient, ClusterManager
from classifier_api import ClassifierAPI, get_classifier_api
from cty_resolvers import CtyDatResolver
from spot_processor import band_from_khz, infer_mode, extract_special, clean_comment
from spots_logger import get_spots_logger, log_spot
from wavelog_api import WavelogClient
from qrz_api import QRZClient
from adif_handler import ADIFHandler
from wavelog_duckdb_sync import get_wavelog_sync, init_wavelog_sync, periodic_wavelog_sync
from wavelog_sync import start_wavelog_sync, stop_wavelog_sync
from rotor_api import RotorController
from rotor_math import (
    grid_to_latlon, latlon_to_grid, initial_bearing,
    calculate_bearing_for_station, get_band_from_frequency
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="FlexRadio Web Control", version="2.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log detailed validation errors for debugging"""
    logger.error(f"❌ Validation Error on {request.url.path}")
    logger.error(f"   Errors: {exc.errors()}")
    logger.error(f"   Body: {await request.body()}")

    return {"success": False, "detail": "Request validation failed", "errors": exc.errors()}

# Global state
flex: Optional[FlexCtl] = None
websocket_clients: List[WebSocket] = []
dx_spots_cache: List[Dict] = []  # In-memory DX spots cache
db_connection = None
cluster_client: Optional[ClusterManager] = None
cluster_connected: bool = False  # Track cluster connection status
classifier: Optional[ClassifierAPI] = None
cty_resolver: Optional[CtyDatResolver] = None
wavelog_client: Optional[WavelogClient] = None
qrz_client: Optional[QRZClient] = None
adif_handler: Optional[ADIFHandler] = None
wavelog_sync_manager = None
rotor: Optional[RotorController] = None
adif_sync_task: Optional[asyncio.Task] = None

# Sync status tracking
sync_status = {
    "syncing": False,
    "last_sync": None,
    "total_records": 0,
    "new_records_this_sync": 0,
    "records_updated": 0,
    "next_sync_in": 0,
}


# === Startup/Shutdown Events ===

def _load_rotor_config():
    """Load rotor configuration from JSON file if it exists"""
    global config
    try:
        rotor_config_file = os.path.join(os.path.dirname(__file__), '..', '..', 'rotor_config.json')
        rotor_config_file = os.path.abspath(rotor_config_file)

        if os.path.exists(rotor_config_file):
            with open(rotor_config_file, 'r', encoding='utf-8') as f:
                rotor_data = json.load(f)

            # Update config from JSON
            config.ROTOR_HOME_GRID = rotor_data.get('ROTOR_HOME_GRID', config.ROTOR_HOME_GRID)
            config.ROTOR_HOME_LAT = rotor_data.get('ROTOR_HOME_LAT', config.ROTOR_HOME_LAT)
            config.ROTOR_HOME_LON = rotor_data.get('ROTOR_HOME_LON', config.ROTOR_HOME_LON)
            config.ROTOR_BANDS = rotor_data.get('ROTOR_BANDS', config.ROTOR_BANDS)
            config.ROTOR_AUTO_ENABLED = rotor_data.get('ROTOR_AUTO_ENABLED', config.ROTOR_AUTO_ENABLED)

            logger.info(f"✅ Loaded rotor config from JSON: Grid={config.ROTOR_HOME_GRID}, AUTO={config.ROTOR_AUTO_ENABLED}")
        else:
            logger.info("ℹ️  No rotor_config.json found, using defaults from config.py")
    except Exception as e:
        logger.warning(f"⚠️  Failed to load rotor config from JSON: {e}, using defaults")


# DEPRECATED: This handler is no longer used (see startup_event() at line 686 instead)
async def startup_event_old():
    """Initialize services on app startup - DEPRECATED"""
    logger.info("🚀 FastAPI backend starting...")

    # Load rotor configuration from JSON (if saved)
    _load_rotor_config()

    try:
        await start_wavelog_sync()
        logger.info("✅ Wavelog sync manager initialized")
    except Exception as e:
        logger.error(f"❌ Failed to start Wavelog sync: {str(e)}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on app shutdown"""
    logger.info("⏹️ FastAPI backend shutting down...")
    try:
        await stop_wavelog_sync()
        logger.info("✅ Wavelog sync manager stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping Wavelog sync: {str(e)}")

    # Close persistent HTTP session
    try:
        if wavelog_client:
            await wavelog_client.close_session()
            logger.info("✅ Wavelog HTTP session closed")
    except Exception as e:
        logger.error(f"❌ Error closing Wavelog session: {str(e)}")


# === Pydantic Models ===

class FrequencyRequest(BaseModel):
    frequency: float

class ModeRequest(BaseModel):
    mode: str

class BandRequest(BaseModel):
    band: str

class FilterRequest(BaseModel):
    filter_lo: int
    filter_hi: int

class SliderRequest(BaseModel):
    value: int

class ToggleRequest(BaseModel):
    enabled: bool

class AGCRequest(BaseModel):
    mode: str  # off, slow, med, fast

class DSPRequest(BaseModel):
    control: str  # nb, nr, anf, apf
    enabled: bool

class DSPLevelRequest(BaseModel):
    control: str  # nb_level, nr_level, anf_level, apf_level
    value: int  # 0-100

class RITXITRequest(BaseModel):
    enabled: bool
    freq_hz: Optional[int] = 0

class RX2Request(BaseModel):
    frequency: Optional[float] = None
    enabled: bool

class SplitRequest(BaseModel):
    enabled: bool
    tx_frequency: Optional[float] = None

class SpotTuneRequest(BaseModel):
    frequency: float
    mode: Optional[str] = None

class QSORequest(BaseModel):
    callsign: str
    frequency: float
    mode: str
    # RST values can be integers (SSB/CW) or strings (FT8/FT4 SNR like "-12", "+15")
    rst_sent: Optional[str] = None
    rst_received: Optional[str] = None
    date: Optional[str] = None
    time_off: Optional[str] = None
    name: Optional[str] = None
    qth: Optional[str] = None
    gridsquare: Optional[str] = None
    notes: Optional[str] = None
    pota: Optional[str] = None
    sota: Optional[str] = None
    iota: Optional[str] = None
    wwff: Optional[str] = None
    date_time: Optional[str] = None
    continent: Optional[str] = None
    cq_zone: Optional[int] = None
    itu_zone: Optional[int] = None
    region: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    us_county: Optional[str] = None
    tx_pwr: Optional[str] = None
    ant: Optional[str] = None
    qsl_rcvd: Optional[str] = None
    qsl_sent: Optional[str] = None
    lotw_member: Optional[bool] = None
    qsl_manager: Optional[str] = None
    email: Optional[str] = None
    prop_mode: Optional[str] = None
    ant_path: Optional[str] = None
    sat_name: Optional[str] = None
    sat_mode: Optional[str] = None
    freq_rx: Optional[str] = None
    mode_rx: Optional[str] = None

class RecentQSOsRequest(BaseModel):
    callsign: str
    limit: int = 5

class RotorGotoRequest(BaseModel):
    azimuth: int  # 0-359

class RotorDirectionRequest(BaseModel):
    direction: str  # "N", "S", "E", "W"

class RotorConfigRequest(BaseModel):
    enabled: bool
    host: str
    port: int
    protocol: str  # "DCU-1" or "Yaesu GS-232A"
    timeout: float = 2.5

class RotorAutoModeRequest(BaseModel):
    enabled: bool

class RotorBearingRequest(BaseModel):
    callsign: str
    frequency_khz: Optional[float] = None  # Current frequency (to determine band)
    gridsquare: Optional[str] = None  # Station gridsquare (from QRZ or cty.dat)
    latitude: Optional[float] = None  # Station latitude
    longitude: Optional[float] = None  # Station longitude

class RotorAutoConfigRequest(BaseModel):
    home_grid: str
    home_lat: float
    home_lon: float
    bands: Dict[str, bool]  # Band name -> enabled (e.g., {"20m": true, "10m": false})
    auto_enabled: bool


# WSJT-X Request Models
class WSJTXQSORequest(BaseModel):
    """QSO data from WSJT-X to log"""
    call: str
    grid: Optional[str] = None
    mode: str  # "FT8", "FT4", etc.
    frequency_hz: Optional[int] = None  # Frequency in Hz
    # RST values can be integers (SSB/CW) or strings (FT8/FT4 SNR like "-12", "+15")
    rst_sent: Optional[str] = None
    rst_received: Optional[str] = None
    operator: Optional[str] = None
    comments: Optional[str] = None
    qrz_data: Optional[Dict[str, Any]] = None  # Pre-fetched QRZ data

class WSJTXAutoRotateRequest(BaseModel):
    """Auto-rotate request based on DX grid"""
    call: str
    grid: str
    frequency_hz: Optional[int] = None


# === Database Connection ===

def get_db_connection():
    """Get MySQL connection for DX spots"""
    global db_connection
    try:
        if db_connection is None or not db_connection.is_connected():
            db_connection = mysql.connect(
                host=config.DB_HOST,
                port=config.DB_PORT,
                user=config.DB_USER,
                password=config.DB_PASS,
                database=config.DB_NAME
            )
        return db_connection
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None


# === FlexRadio Initialization ===

def init_flex():
    """Initialize FlexCtl connection"""
    global flex
    try:
        host = getattr(config, 'FLEX_TCP_HOST', '192.168.1.100')
        port = getattr(config, 'FLEX_TCP_PORT', 4992)
        slice_id = getattr(config, 'FLEX_SLICE_ID', 0)

        logger.info(f"Initializing FlexCtl: {host}:{port}, slice {slice_id}")
        flex = FlexCtl(host, port, slice_id)

        if flex.connect():
            logger.info("✅ FlexRadio connected successfully")
            return True
        else:
            logger.error("❌ FlexRadio connection failed")
            return False
    except Exception as e:
        logger.error(f"❌ FlexCtl initialization error: {e}")
        return False


# === WebSocket Broadcasting ===

async def broadcast_status(data: dict):
    """Broadcast status to all WebSocket clients"""
    if not websocket_clients:
        return

    message = json.dumps({"type": "status", "data": data})
    disconnected = []

    for client in websocket_clients:
        try:
            await client.send_text(message)
        except Exception as e:
            logger.warning(f"Failed to send to WebSocket: {e}")
            disconnected.append(client)

    for client in disconnected:
        websocket_clients.remove(client)


async def broadcast_spots(spots: List[Dict]):
    """Broadcast DX spots to all WebSocket clients"""
    if not websocket_clients:
        return

    message = json.dumps({"type": "spots", "data": spots})
    disconnected = []

    for client in websocket_clients:
        try:
            await client.send_text(message)
        except Exception as e:
            logger.warning(f"Failed to broadcast spots: {e}")
            disconnected.append(client)

    for client in disconnected:
        websocket_clients.remove(client)


# === Background Tasks ===

async def poll_radio_status():
    """Poll radio for status updates - increased frequency for faster 2-way sync"""
    while True:
        try:
            if flex and flex.sock:
                flex.refresh_radio_state()

                # Get only actual state changes (no smeter spam)
                status_update = flex.last_state_changed.copy() if flex.last_state_changed else {}

                # Map 'frequency' field if present (backend may use 'freq')
                if 'freq' in status_update:
                    status_update['frequency'] = status_update.pop('freq')
                    logger.info(f"🚀 FREQUENCY SYNC: freq={status_update['frequency']}")

                if status_update:
                    logger.info(f"Broadcasting changes: {list(status_update.keys())}")
                    await broadcast_status(status_update)
                    flex.last_state_changed = {}

            # Increased polling frequency: 500ms instead of 1s for faster responsiveness
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Poll error: {e}")
            await asyncio.sleep(5.0)


async def monitor_cluster_status():
    """Monitor cluster connection status and broadcast to clients"""
    global cluster_client, cluster_connected

    last_status = None
    last_active_name = None

    while True:
        try:
            current_connected = cluster_client.connected if cluster_client else False
            
            # Get active cluster info
            cluster_info_obj = {
                "activeName": "",
                "host": "",
                "port": ""
            }
            
            if cluster_client and hasattr(cluster_client, 'get_status'):
                try:
                    cluster_info = cluster_client.get_status()
                    if cluster_info:
                        cluster_info_obj = {
                            "activeName": cluster_info.get('active_name', ''),
                            "host": cluster_info.get('host', ''),
                            "port": str(cluster_info.get('port', ''))
                        }
                except Exception as e:
                    logger.debug(f"Could not get cluster info: {e}")
            
            current_active_name = cluster_info_obj["activeName"]

            # Broadcast when status OR active cluster changes
            if current_connected != last_status or current_active_name != last_active_name:
                status = {
                    "cluster_status": "connected" if current_connected else "disconnected",
                    "cluster_connected": current_connected,
                    "cluster_info": cluster_info_obj
                }
                
                if current_active_name != last_active_name:
                    logger.info(f"🔗 Active cluster changed to: {current_active_name}")
                else:
                    logger.info(f"🔗 Cluster status: {'✅ Connected' if current_connected else '❌ Disconnected'}")
                
                await broadcast_status(status)
                last_status = current_connected
                last_active_name = current_active_name
                cluster_connected = current_connected

            # Check every 3 seconds
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Cluster status monitor error: {e}")
            await asyncio.sleep(5)


async def process_cluster_spot(spot_data: Dict):
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
        call_status = "New Call"
        dxcc_status = "—"
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
                call_status = "New Call"  # Default to New Call on API error

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
                logger.warning(f"DXCC resolution failed for {dxcall} (country: {entity})")

        # 🔧 FIX: Log spot to database with computed classifications
        try:
            log_spot(spot_data, call_status=call_status, dxcc_status=dxcc_status)
        except Exception as e:
            logger.warning(f"Failed to log spot to database: {e}")

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

        logger.info(f"📡 Spot: {dxcall} {freq_khz:.1f} kHz {emode} [{dxcc_status}] {comment[:50]}")

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
        if not os.path.exists(file_path):
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


async def periodic_wavelog_sync():
    """Periodically sync Wavelog database to DuckDB (configurable interval)"""
    import concurrent.futures
    from functools import partial
    from pathlib import Path

    global wavelog_sync_manager, sync_status

    sync_interval = getattr(config, 'WAVELOG_SYNC_INTERVAL', 60)
    logger.info(f"🔄 Starting periodic Wavelog→DuckDB sync task ({sync_interval} second interval)")

    loop = asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    # Run sync immediately on startup (in background thread to not block event loop)
    logger.info("⏳ Running initial Wavelog→DuckDB sync in background...")

    last_sync_time = 0

    while True:
        try:
            current_time = time.time()

            if wavelog_sync_manager:
                sync_status["syncing"] = True

                # Run sync in thread pool to avoid blocking event loop
                result = await loop.run_in_executor(executor, wavelog_sync_manager.sync)

                # Update sync status
                sync_status["total_records"] = result.get('total_records', 0)
                sync_status["new_records_this_sync"] = result.get('records_added', 0)
                sync_status["records_updated"] = result.get('records_updated', 0)
                sync_status["last_sync"] = datetime.now().isoformat()

                if result.get('synced', False):
                    if result.get('records_added', 0) > 0 or result.get('records_updated', 0) > 0:
                        logger.info(f"✅ Wavelog sync: +{result.get('records_added', 0)} new, "
                                    f"~{result.get('records_updated', 0)} updated, "
                                    f"total: {result.get('total_records', 0)}")
                # Silent on no changes to reduce log noise

            sync_status["syncing"] = False
            last_sync_time = current_time

            # Calculate next sync time
            time_until_next = sync_interval - (time.time() - current_time)
            sync_status["next_sync_in"] = max(0, int(time_until_next))

            await asyncio.sleep(float(sync_interval))  # Wait configured interval before next sync

        except Exception as e:
            logger.error(f"❌ Periodic Wavelog sync error: {str(e)}", exc_info=True)
            sync_status["syncing"] = False
            await asyncio.sleep(float(sync_interval))


# === Startup (DEPRECATED - use backend/main.py instead) ===

async def _startup_event_deprecated():
    """Initialize on startup"""
    global classifier, cty_resolver, cluster_client, wavelog_client, qrz_client, adif_handler, rotor, wavelog_sync_manager, adif_sync_task

    logger.info("🚀 Starting FlexRadio Web Control Backend v2.0")

    # Initialize logging clients
    wavelog_client = WavelogClient()
    qrz_client = QRZClient()
    adif_handler = ADIFHandler()

    # Initialize Wavelog→DuckDB Sync
    try:
        wavelog_sync_manager = init_wavelog_sync()
        logger.info("✅ Wavelog→DuckDB sync initialized")

        # Start periodic Wavelog sync task (handles both initial and ongoing syncs)
        adif_sync_task = asyncio.create_task(periodic_wavelog_sync())
        sync_interval = getattr(config, 'WAVELOG_SYNC_INTERVAL', 60)
        logger.info(f"✅ Wavelog→DuckDB periodic sync task started (runs first immediately, then every {sync_interval} seconds)")
    except Exception as e:
        logger.error(f"❌ Wavelog→DuckDB sync initialization failed: {e}")
        wavelog_sync_manager = None

    # Initialize FlexRadio
    init_flex()

    # Initialize CTY resolver
    logger.info("Loading CTY data...")
    try:
        dat_path = getattr(config, 'CTY_DAT_PATH', None)
        csv_path = getattr(config, 'CTY_CSV_PATH', None)
        ignore_suffixes = getattr(config, 'CTY_IGNORE_SUFFIXES', [])
        cty_resolver = CtyDatResolver(dat_path, csv_path=csv_path, ignore_suffixes=ignore_suffixes)
        logger.info("✅ CTY resolver loaded")
    except Exception as e:
        logger.error(f"❌ CTY resolver failed: {e}")
        cty_resolver = None

    # Initialize API-based Classifier (uses Wavelog API for more reliable results)
    logger.info("Initializing Wavelog API classifier...")
    try:
        classifier = await get_classifier_api(wavelog_client)
        logger.info("✅ API-based classifier initialized (uses Wavelog API for accurate DXCC/call status)")
    except Exception as e:
        logger.error(f"❌ Classifier initialization failed: {e}")
        classifier = None

    # Initialize cluster manager with failover support
    try:
        # Get clusters configuration from config.py
        clusters_config = getattr(config, 'CLUSTERS', [])
        
        if clusters_config:
            # Use ClusterManager for multi-cluster failover support
            cluster_client = ClusterManager(clusters_config)
            cluster_client.set_spot_callback(process_cluster_spot)
            
            # Start cluster manager in background with auto-reconnect and failover
            asyncio.create_task(cluster_client.run())
            logger.info(f"✅ Cluster manager started with {len(cluster_client.cluster_clients)} cluster(s)")
        else:
            # Fallback to legacy single-cluster configuration
            logger.warning("⚠️  No CLUSTERS configuration found, using legacy CLUSTER_HOST/PORT settings")
            cluster_host = getattr(config, 'CLUSTER_HOST', 'localhost')
            cluster_port = getattr(config, 'CLUSTER_PORT', 7373)
            cluster_user = getattr(config, 'CLUSTER_USER', 'N0CALL')
            cluster_pass = getattr(config, 'CLUSTER_PASS', '')
            
            cluster_client = ClusterClient(cluster_host, cluster_port, cluster_user, cluster_pass)
            cluster_client.set_spot_callback(process_cluster_spot)
            
            # Start cluster in background
            asyncio.create_task(cluster_client.run())
            logger.info("✅ Cluster client started (legacy mode)")
    except Exception as e:
        logger.error(f"❌ Cluster client initialization failed: {e}")

    # Initialize rotator controller if enabled
    try:
        rotor_enabled = getattr(config, 'ROTOR_ENABLED', False)
        if rotor_enabled:
            rotor_host = getattr(config, 'ROTOR_HOST', '192.168.0.198')
            rotor_port = getattr(config, 'ROTOR_PORT', 4001)
            rotor_protocol = getattr(config, 'ROTOR_PROTOCOL', 'DCU-1')
            rotor_timeout = getattr(config, 'ROTOR_TIMEOUT_SEC', 2.5)

            rotor = RotorController(rotor_host, rotor_port, rotor_protocol, rotor_timeout)
            logger.info(f"✅ Rotator initialized: {rotor_host}:{rotor_port} ({rotor_protocol})")
        else:
            logger.info("ℹ️ Rotator disabled in config")
    except Exception as e:
        logger.error(f"❌ Rotator initialization failed: {e}")
        rotor = None

    # Start background tasks
    asyncio.create_task(poll_radio_status())
    asyncio.create_task(poll_dx_spots())
    asyncio.create_task(monitor_cluster_status())

    # NOTE: periodic_adif_sync() already started on line 779, don't create duplicate task!


# === Health Check ===

@app.get("/api/health")
async def health_check():
    """Health check"""
    connected = flex is not None and flex.sock is not None
    return {
        "status": "ok" if connected else "disconnected",
        "connected": connected,
        "version": "2.0.0"
    }


# === Sync Status ===

@app.get("/api/sync-status")
async def get_sync_status():
    """Get ADIF sync status"""
    global sync_status
    return sync_status


# === Radio Status ===
# REMOVED: Old /api/status endpoint - now handled by backend/api/health.py router
# The new implementation provides graceful error handling with default values
# instead of throwing 503 errors when radio is not initialized.
