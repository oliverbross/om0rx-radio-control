"""
DX Spots Management Service
Extracted from main.py - handles spot filtering, tuning, radio display, and spot logging/statistics
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import HTTPException
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime

# Import required modules
from spots_logger import get_spots_logger
from dxbridge import FlexCtl
from spot_processor import band_from_khz, infer_mode, extract_special, clean_comment
from cty_resolvers import CtyDatResolver
from classifier_api import ClassifierAPI
from rotor_math import grid_to_latlon, latlon_to_grid, initial_bearing, calculate_bearing_for_station, get_band_from_frequency

logger = logging.getLogger(__name__)

# Global state (will be passed from main app)
flex: Optional[FlexCtl] = None
dx_spots_cache: List[Dict] = []
cty_resolver: Optional[CtyDatResolver] = None
classifier: Optional[ClassifierAPI] = None
rotor = None

# Pydantic models for spots endpoints
class SpotTuneRequest(BaseModel):
    frequency: float
    mode: Optional[str] = None

class SpotAddRequest(BaseModel):
    """Request to add a spot to SmartSDR panadapter"""
    callsign: str
    frequency: float  # MHz
    mode: str
    spotter: str = "Web UI"
    comment: str = ""
    tag: Optional[str] = None


def init_spots_service(flex_radio: FlexCtl, spots_cache: List[Dict], cty: CtyDatResolver, cls: ClassifierAPI, rotor_controller=None):
    """Initialize the spots service with required dependencies"""
    global flex, dx_spots_cache, cty_resolver, classifier, rotor
    flex = flex_radio
    dx_spots_cache = spots_cache
    cty_resolver = cty
    classifier = cls
    rotor = rotor_controller


async def broadcast_status(data: dict):
    """Broadcast status to all WebSocket clients"""
    # This will be imported from websocket service
    from .websocket import broadcast_status as ws_broadcast_status
    await ws_broadcast_status(data)


async def broadcast_spots(spots: List[Dict]):
    """Broadcast DX spots to all WebSocket clients"""
    # This will be imported from websocket service
    from .websocket import broadcast_spots as ws_broadcast_spots
    await ws_broadcast_spots(spots)


# === DX Spots Endpoints ===

async def get_spots(
    band: Optional[str] = None,
    mode: Optional[str] = None,
    cq: Optional[str] = None,
    call_status: Optional[str] = None,
    dxcc_status: Optional[str] = None,
    special: Optional[str] = None
):
    """Get DX spots with optional filtering"""
    filtered_spots = dx_spots_cache

    # Apply filters
    if band:
        bands = set(band.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('band') in bands]

    if mode:
        modes = set(mode.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('mode') in modes]

    if cq:
        cqs = set(cq.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('cq') in cqs]

    if call_status:
        statuses = set(call_status.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('call_status') in statuses]

    if dxcc_status:
        statuses = set(dxcc_status.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('dxcc_status') in statuses]

    if special:
        specials = set(special.split(','))
        filtered_spots = [s for s in filtered_spots if s.get('special') in specials or ('(none)' in specials and not s.get('special'))]

    return {"spots": filtered_spots}


async def tune_to_spot(req: SpotTuneRequest):
    """Tune to DX spot frequency and optionally change mode"""
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        # Tune frequency
        success = flex.tune_mhz(req.frequency)
        if not success:
            raise HTTPException(status_code=400, detail="Tune command failed")

        # Set mode if provided
        if req.mode:
            mode_success = flex.set_mode(req.mode)
            if not mode_success:
                logger.warning(f"Mode change to {req.mode} failed, but frequency changed")

        # Broadcast status update
        update = {"frequency": req.frequency}
        if req.mode:
            update["mode"] = req.mode
        await broadcast_status(update)

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Spot tune error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def add_spot_to_radio(req: SpotAddRequest):
    """Add a spot to SmartSDR panadapter display"""
    if not flex or not flex.sock:
        raise HTTPException(status_code=503, detail="Radio not connected")

    try:
        # Map tag to color
        color_map = {
            'ATNO': '#FFFF8C00',           # Orange
            'New band': '#FF00BFFF',       # Cyan
            'New mode': '#FFFFC000',       # Yellow
            'New band+mode': '#FFE91E63',  # Pink
            'Need LoTW': '#FF32CD32',      # Lime Green
            'Worked': '#FFB0B0B0'          # Gray
        }
        color = color_map.get(req.tag, '#FFFFFFFF') if req.tag else '#FFFFFFFF'

        # Add spot to panadapter
        success = flex.add_spot(
            rx_mhz=req.frequency,
            callsign=req.callsign,
            mode=req.mode,
            source="web",
            spotter=req.spotter,
            comment=req.comment,
            lifetime=3600,
            priority=2,
            color=color
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to add spot to radio")

        logger.info(f"✨ Spot added to radio: {req.callsign} {req.frequency:.3f} MHz {req.mode}")
        return {"success": True, "message": f"Spot added: {req.callsign}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add spot to radio error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === DX Spots Logging & Statistics ===

async def get_spots_count(date: Optional[str] = None):
    """Get total number of logged spots, optionally filtered by date (YYYY-MM-DD)"""
    try:
        spots_logger = get_spots_logger()
        count = spots_logger.get_spot_count(date)
        return {"ok": True, "count": count, "date_filter": date}
    except Exception as e:
        logger.error(f"Error getting spot count: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_spots_stats_band(date: Optional[str] = None):
    """Get spot statistics grouped by band"""
    try:
        spots_logger = get_spots_logger()
        stats = spots_logger.get_stats_by_band(date)
        return {"ok": True, "data": stats, "date_filter": date}
    except Exception as e:
        logger.error(f"Error getting band stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_spots_stats_mode(date: Optional[str] = None):
    """Get spot statistics grouped by mode"""
    try:
        spots_logger = get_spots_logger()
        stats = spots_logger.get_stats_by_mode(date)
        return {"ok": True, "data": stats, "date_filter": date}
    except Exception as e:
        logger.error(f"Error getting mode stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_spots_stats_country(limit: int = 20, date: Optional[str] = None):
    """Get top countries by spot count"""
    try:
        spots_logger = get_spots_logger()
        stats = spots_logger.get_stats_by_country(limit, date)
        return {"ok": True, "data": stats, "limit": limit, "date_filter": date}
    except Exception as e:
        logger.error(f"Error getting country stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_recent_spots(limit: int = 100):
    """Get most recent spots"""
    try:
        spots_logger = get_spots_logger()
        spots = spots_logger.get_recent_spots(limit)
        # Always return fresh data, never cache this endpoint
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"ok": True, "data": spots, "count": len(spots)},
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except Exception as e:
        logger.error(f"Error getting recent spots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_spots_by_callsign(callsign: str, limit: int = 100):
    """Get all spots for a specific callsign"""
    try:
        spots_logger = get_spots_logger()
        spots = spots_logger.get_spots_by_callsign(callsign, limit)
        return {"ok": True, "data": spots, "callsign": callsign, "count": len(spots)}
    except Exception as e:
        logger.error(f"Error getting spots for {callsign}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_special_event_spots(limit: int = 100):
    """Get spots with special event tags (POTA, SOTA, IOTA, etc)"""
    try:
        spots_logger = get_spots_logger()
        spots = spots_logger.get_special_event_spots(limit)
        return {"ok": True, "data": spots, "count": len(spots)}
    except Exception as e:
        logger.error(f"Error getting special event spots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def export_spots_csv(date: Optional[str] = None):
    """Export spots to CSV file"""
    try:
        spots_logger = get_spots_logger()
        export_path = Path(__file__).parent.parent / "data" / f"spots_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        count = spots_logger.export_csv(str(export_path), date)
        return {
            "ok": True,
            "file": str(export_path),
            "count": count,
            "date_filter": date
        }
    except Exception as e:
        logger.error(f"Error exporting spots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Debug Endpoint ===

async def debug_spots_status():
    """Debug endpoint to check spots cache vs database status"""
    try:
        # Check cache
        cache_count = len(dx_spots_cache)
        cache_latest = None
        if dx_spots_cache:
            cache_latest = {
                'callsign': dx_spots_cache[0].get('callsign'),
                'timestamp': dx_spots_cache[0].get('timestamp'),
                'time': dx_spots_cache[0].get('time'),
                'received_at': dx_spots_cache[0].get('time')
            }

        # Check database
        spots_logger = get_spots_logger()
        db_count = spots_logger.get_spot_count()
        db_latest = None
        recent_from_db = spots_logger.get_recent_spots(1)
        if recent_from_db:
            db_latest = {
                'callsign': recent_from_db[0].get('callsign'),
                'received_at': recent_from_db[0].get('received_at'),
                'time_utc': recent_from_db[0].get('time_utc')
            }

        # Check cluster (will be imported from cluster service)
        from .database import cluster_connected
        cluster_is_connected = cluster_connected

        return {
            "ok": True,
            "cluster": {
                "connected": cluster_is_connected,
                "status": "connected" if cluster_is_connected else "disconnected"
            },
            "cache": {
                "count": cache_count,
                "latest": cache_latest
            },
            "database": {
                "count": db_count,
                "latest": db_latest
            },
            "note": "Cache shows real-time spots, Database shows all spots ever received"
        }
    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}")
        return {
            "ok": False,
            "error": str(e)
        }


# === Spot Processing Functions ===

async def process_cluster_spot(spot_data: Dict):
    """Process spot from cluster - classify and store"""
    try:
        freq_khz = spot_data['freq_khz']
        freq_khz_str = spot_data.get('freq_khz_str', str(freq_khz))  # Original string from cluster
        dxcall = spot_data['dxcall']
        spotter = spot_data['spotter']
        raw_comment = spot_data['comment']
        timestamp = spot_data['timestamp']

        # Clean comment
        comment = clean_comment(raw_comment)

        # Log spot to persistent database immediately
        try:
            from spots_logger import log_spot
            log_spot(spot_data)
        except Exception as e:
            logger.warning(f"Failed to log spot to database: {e}")

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

                    # DXCC status - show entity status, with band/mode qualifiers when appropriate
                    if not dx_worked:
                        dxcc_status = "ATNO"
                        tag = "ATNO"
                    elif dx_bandmode_conf:
                        # Confirmed on this exact band+mode
                        dxcc_status = "Confirmed"
                        tag = None
                    else:
                        # Worked overall - determine status with band/mode specifics
                        base_status = "Confirmed" if dx_conf else "Worked"
                        
                        # Show band/mode info only if both are new (both band AND mode never worked)
                        if dx_new_band and dx_new_mode:
                            dxcc_status = f"{base_status}/New Band+Mode"
                            tag = None
                        elif dx_new_band:
                            dxcc_status = f"{base_status}/New Band"
                            tag = None
                        elif dx_new_mode:
                            dxcc_status = f"{base_status}/New Mode"
                            tag = None
                        else:
                            # Neither band nor mode is new, but this band+mode combo is
                            dxcc_status = base_status
                            tag = "Need LoTW" if not dx_conf else None

                except Exception as e:
                    logger.warning(f"Error getting DXCC status for DXCC {dxcc}: {e}")
                    dxcc_status = "Unknown"
            else:
                # DXCC couldn't be resolved - show "Unknown" instead of blank
                dxcc_status = "Unknown"
                logger.warning(f"DXCC resolution failed for {dxcall} (country: {entity})")

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

        logger.info(f"📡 Spot: {dxcall} {freq_khz:.1f} kHz {emode} [{call_status}] {comment[:50]}")

    except Exception as e:
        logger.error(f"Spot processing error: {e}")