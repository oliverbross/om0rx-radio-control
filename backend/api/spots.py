"""
DX Spots API Router
Handles DX spot tuning, filtering, and spot management endpoints
"""

import logging
import asyncio
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from typing import Any, Dict, Optional, List

logger = logging.getLogger(__name__)

router = APIRouter()


class SpotTuneRequest(BaseModel):
    frequency: float
    mode: Optional[str] = None


class SpotPopoutCommandRequest(BaseModel):
    id: str
    action: str
    spot: Dict[str, Any]


class SpotFilterRequest(BaseModel):
    """Request model for filtered spot search"""
    limit: int = 100
    callsign: Optional[str] = None
    bands: Optional[List[str]] = None
    modes: Optional[List[str]] = None
    zones_cq: Optional[List[int]] = None
    continents: Optional[List[str]] = None
    special_tags: Optional[List[str]] = None
    spot_sources: Optional[List[str]] = None
    rbl_modes: Optional[List[str]] = None
    rbl_min_snr: Optional[float] = None
    rbl_dedupe_minutes: Optional[int] = None
    max_age_minutes: Optional[int] = None
    sort_by: str = "time"
    visual_map: bool = False


class SpotMaintenanceRepairRequest(BaseModel):
    limit: Optional[int] = None
    dry_run: bool = True
    vacuum: bool = False


def _radio_mode_for_spot(mode: Optional[str], frequency_mhz: Optional[float]) -> Optional[str]:
    """Map spot/logging modes to modes accepted by the Flex slice API."""
    value = (mode or "").strip().upper()
    if not value:
        return None

    if value == "SSB":
        try:
            return "LSB" if float(frequency_mhz or 0) < 14 else "USB"
        except (TypeError, ValueError):
            return "USB"

    if value in {"FT8", "FT4", "FT2", "JT65", "JT9", "PSK", "DIGI", "MFSK", "OLIVIA"}:
        return "DIGU"

    valid_modes = {"AM", "LSB", "USB", "CW", "NFM", "DIGL", "DIGU", "FM", "SAM", "DFM", "RTTY"}
    return value if value in valid_modes else value


def _spot_timestamp_seconds(spot: Dict[str, Any]) -> float:
    timestamp = spot.get("timestamp") or spot.get("created_at") or spot.get("received_at")
    if isinstance(timestamp, (int, float)):
        return float(timestamp)
    if isinstance(timestamp, str):
        try:
            from datetime import datetime

            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return parsed.timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _build_live_source_stats(spots: List[Dict[str, Any]]) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "total": 0,
        "cluster": 0,
        "rbl": 0,
        "other": 0,
        "modes": {},
        "rbl_modes": {},
        "last_any": 0,
        "last_cluster": 0,
        "last_rbl": 0,
    }

    for spot in spots or []:
        source = (spot.get("spot_source") or "cluster").lower()
        mode = (spot.get("mode") or "UNKNOWN").upper()
        rbl_group = (spot.get("rbl_mode_group") or "OTHER").upper()
        timestamp = _spot_timestamp_seconds(spot)

        stats["total"] += 1
        stats["last_any"] = max(stats["last_any"], timestamp)
        stats["modes"][mode] = stats["modes"].get(mode, 0) + 1

        if source == "rbl":
            stats["rbl"] += 1
            stats["last_rbl"] = max(stats["last_rbl"], timestamp)
            stats["rbl_modes"][rbl_group] = stats["rbl_modes"].get(rbl_group, 0) + 1
        elif source == "cluster":
            stats["cluster"] += 1
            stats["last_cluster"] = max(stats["last_cluster"], timestamp)
        else:
            stats["other"] += 1

    return stats


def _coordinate_is_valid(value: Any, limit: float) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return abs(number) <= limit


def _spot_has_valid_coordinate(spot: Dict[str, Any], keys: List[str], limit: float) -> bool:
    return any(
        key in spot and spot.get(key) is not None and _coordinate_is_valid(spot.get(key), limit)
        for key in keys
    )


def _clean_spotter_callsign(callsign: Any) -> str:
    value = str(callsign or "").strip().upper()
    if not value:
        return ""
    value = value.split()[0]
    value = value.split("#", 1)[0]
    if "-" in value:
        value = value.split("-", 1)[0]
    return "".join(ch for ch in value if ch.isalnum() or ch == "/")


def _cty_location_payload(callsign: str, info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    latitude = info.get("latitude")
    longitude = _normalize_cty_longitude(info.get("longitude"))
    if not (_coordinate_is_valid(latitude, 90) and _coordinate_is_valid(longitude, 180)):
        return None
    return {
        "callsign": callsign,
        "country": info.get("country"),
        "dxcc": info.get("dxcc"),
        "cq": info.get("cq"),
        "itu": info.get("itu"),
        "continent": info.get("continent"),
        "latitude": latitude,
        "longitude": longitude,
        "location_source": "cty_prefix",
    }


def _normalize_cty_longitude(value: Any) -> Optional[float]:
    """Convert CTY longitude convention (west positive) to map longitude (east positive)."""
    try:
        longitude = float(value)
    except (TypeError, ValueError):
        return None
    if abs(longitude) > 180:
        return None
    return -longitude


def _update_cty_grid_from_coordinates(spot: Dict[str, Any]) -> None:
    """Keep generated CTY grids consistent with normalized CTY coordinates."""
    try:
        from radio_control.rotor_math import latlon_to_grid

        latitude = float(spot.get("latitude"))
        longitude = float(spot.get("longitude"))
        spot["gridsquare"] = latlon_to_grid(latitude, longitude, precision=6)
    except Exception:
        return


def _enrich_spot_cty_locations(app_state: Any, spots: List[Dict[str, Any]], max_lookups: int = 500) -> None:
    """Add CTY-prefix country, zone, and approximate entity coordinates when absent."""
    cty_resolver = getattr(app_state, "cty_resolver", None)
    if not cty_resolver:
        return

    cache: Dict[str, Dict[str, Any]] = {}
    lookups = 0

    def resolve_callsign(raw_callsign: Any) -> tuple[str, Dict[str, Any]]:
        nonlocal lookups
        callsign = _clean_spotter_callsign(raw_callsign)
        if not callsign:
            return "", {}
        if callsign not in cache:
            if lookups >= max_lookups:
                return callsign, {}
            try:
                cache[callsign] = cty_resolver.lookup(callsign) or {}
            except Exception:
                logger.debug("CTY enrichment lookup failed for %s", callsign, exc_info=True)
                cache[callsign] = {}
            lookups += 1
        return callsign, cache.get(callsign) or {}

    for spot in spots or []:
        callsign = (spot.get("callsign") or "").strip().upper()
        if not callsign:
            continue
        _, info = resolve_callsign(callsign)
        if not info:
            continue

        if not spot.get("country") or spot.get("country") == "UNKNOWN":
            spot["country"] = info.get("country")
        if spot.get("dxcc") is None and info.get("dxcc") is not None:
            spot["dxcc"] = info.get("dxcc")
        if not spot.get("continent") and info.get("continent"):
            spot["continent"] = info.get("continent")
        if not spot.get("cq") and not spot.get("cq_zone") and info.get("cq"):
            spot["cq"] = info.get("cq")
        if not spot.get("itu") and not spot.get("itu_zone") and info.get("itu"):
            spot["itu"] = info.get("itu")

        has_lat = _spot_has_valid_coordinate(spot, ["latitude", "lat", "dxcc_lat"], 90)
        has_lon = _spot_has_valid_coordinate(spot, ["longitude", "lon", "lng", "dxcc_long"], 180)
        if not has_lat and _coordinate_is_valid(info.get("latitude"), 90):
            spot["latitude"] = info.get("latitude")
        normalized_longitude = _normalize_cty_longitude(info.get("longitude"))
        approximate_cty_location = spot.get("location_source") == "cty_prefix" or spot.get("location_confidence") == "low"
        if (not has_lon or approximate_cty_location) and _coordinate_is_valid(normalized_longitude, 180):
            spot["longitude"] = normalized_longitude
            if _coordinate_is_valid(spot.get("latitude"), 90):
                _update_cty_grid_from_coordinates(spot)
        if (not has_lat or not has_lon) and spot.get("latitude") is not None and spot.get("longitude") is not None:
            spot.setdefault("location_source", "cty_prefix")

        raw_spotters: List[Any] = []
        if spot.get("aggregate_spotters") and isinstance(spot.get("aggregate_spotters"), list):
            raw_spotters.extend(spot.get("aggregate_spotters")[:8])
        for key in ("spotter", "dx_de", "dxde", "spotter_call"):
            if spot.get(key):
                raw_spotters.append(spot.get(key))

        spotter_locations: List[Dict[str, Any]] = []
        seen_spotters: set[str] = set()
        for raw_spotter in raw_spotters:
            spotter_call, spotter_info = resolve_callsign(raw_spotter)
            if not spotter_call or spotter_call in seen_spotters:
                continue
            seen_spotters.add(spotter_call)
            payload = _cty_location_payload(spotter_call, spotter_info)
            if payload:
                spotter_locations.append(payload)

        if spotter_locations:
            primary = spotter_locations[0]
            spot["spotter_callsign"] = primary["callsign"]
            spot["spotter_country"] = primary.get("country")
            spot["spotter_latitude"] = primary.get("latitude")
            spot["spotter_longitude"] = primary.get("longitude")
            spot["spotter_cq"] = primary.get("cq")
            spot["spotter_itu"] = primary.get("itu")
            spot["spotter_locations"] = spotter_locations


async def _refresh_uncertain_spot_classifications(
    app_state: Any,
    spots: List[Dict[str, Any]],
    max_rechecks: int = 25,
) -> None:
    """Repair stale or unsafe DXCC status rows before returning cached spots."""
    classifier = getattr(app_state, "classifier", None)
    cty_resolver = getattr(app_state, "cty_resolver", None)
    if not classifier:
        return

    from radio_control.spot_classification import classify_dxcc_status

    checked = 0
    for spot in spots:
        if checked >= max_rechecks:
            return
        if spot.get("dxcc_status_source") == "verified":
            continue
        status = str(spot.get("dxcc_status") or "").strip()
        if status not in {"", "ATNO", "Unknown", "Worked", "W/New Band", "W/New Mode", "W/New Band+Mode"}:
            continue

        callsign = (spot.get("callsign") or "").strip().upper()
        band = spot.get("band")
        mode = spot.get("mode")
        if not callsign or not band or not mode:
            continue

        dxcc = spot.get("dxcc")
        if dxcc is None and cty_resolver:
            cty_info = cty_resolver.lookup(callsign)
            dxcc = cty_info.get("dxcc")
            if dxcc is not None:
                spot["dxcc"] = dxcc
                if not spot.get("country") or spot.get("country") == "UNKNOWN":
                    spot["country"] = (cty_info.get("country") or "").upper()

        if dxcc is None:
            continue

        checked += 1
        dxcc_overall = await classifier.dxcc_overall(
            dxcc,
            callsign=callsign,
            allow_unconfirmed_fallback=False,
        )
        dxcc_bandmode = await classifier.dxcc_bandmode_flags(
            dxcc,
            band,
            mode,
            callsign=callsign,
            allow_unconfirmed_fallback=False,
        )

        if dxcc_overall is None or dxcc_bandmode is None:
            spot["dxcc_status"] = "Unknown"
            spot["tag"] = None
            continue

        worked, confirmed = dxcc_overall
        new_band, new_mode, bandmode_confirmed = dxcc_bandmode
        display = classify_dxcc_status(
            worked,
            confirmed,
            new_band,
            new_mode,
            bandmode_confirmed,
        )
        spot["dxcc_status"] = display.status
        spot["tag"] = display.tag
        spot["dxcc_status_source"] = "verified"


@router.get("/api/spots")
async def get_spots(
    request: Request,
    band: Optional[str] = None,
    mode: Optional[str] = None,
    cq: Optional[str] = None,
    call_status: Optional[str] = None,
    dxcc_status: Optional[str] = None,
    special: Optional[str] = None
):
    """Get DX spots with optional filtering (from cache only)"""
    dx_spots_cache = getattr(request.app.state, 'dx_spots_cache', [])
    await _refresh_uncertain_spot_classifications(request.app.state, dx_spots_cache)
    _enrich_spot_cty_locations(request.app.state, dx_spots_cache)
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

    try:
        from radio_control.spot_intelligence import enrich_spot_intelligence
        from radio_control.local_heard import correlate_local_heard
        from services.ft8_service import get_ft8_service
        from radio_control import config as app_config
        from activity_intelligence.services import get_activity_intelligence_service

        decoded_messages = get_ft8_service().get_decoded_messages(limit=100)
        activity_intelligence = get_activity_intelligence_service()
        for spot in filtered_spots:
            correlate_local_heard(spot, decoded_messages, mycall=getattr(app_config, "MY_STATION", ""))
            enrich_spot_intelligence(spot)
            activity_intelligence.enrich_spot(spot)
    except Exception:
        logger.debug("Could not enrich cached spots with intelligence fields", exc_info=True)
    
    return {"spots": filtered_spots}


@router.get("/api/spots/live-cache")
async def get_live_spot_cache(request: Request, limit: int = 250):
    """Return current in-memory spot cache rows without expensive enrichment."""
    dx_spots_cache = getattr(request.app.state, "dx_spots_cache", [])
    safe_limit = max(1, min(int(limit or 250), 500))
    return {"spots": [dict(spot) for spot in dx_spots_cache[:safe_limit]]}


@router.post("/api/spots/popout-command")
async def post_spots_popout_command(command: SpotPopoutCommandRequest, request: Request):
    """Relay a detached Filters window spot action to the main app window."""
    commands = getattr(request.app.state, "spots_popout_commands", None)
    if commands is None:
        commands = []
        request.app.state.spots_popout_commands = commands

    payload = command.dict()
    commands.append(payload)
    if len(commands) > 50:
        del commands[:-50]
    try:
        from services.websocket import websocket_manager

        await websocket_manager.broadcast("spot-command", payload)
    except Exception:
        logger.exception("Failed to broadcast detached Filters spot command")
    return {"ok": True, "id": command.id}


@router.get("/api/spots/popout-command")
async def get_spots_popout_commands(request: Request, since: Optional[str] = None):
    """Return detached Filters window commands after the provided command id."""
    commands = list(getattr(request.app.state, "spots_popout_commands", []))
    if since:
        for index, command in enumerate(commands):
            if command.get("id") == since:
                commands = commands[index + 1 :]
                break
    return {"ok": True, "commands": commands}


@router.get("/api/spots/cty-prefixes")
async def get_cty_prefixes():
    """Serve CTY prefix CSV for frontend-only visual spot location fallback."""
    try:
        from radio_control import config as app_config

        cty_csv = app_config.DATA_DIR / "cty.csv"
        if not cty_csv.exists():
            raise HTTPException(status_code=404, detail="cty.csv not found")
        return Response(
            content=cty_csv.read_text(encoding="utf-8", errors="replace"),
            media_type="text/csv",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error serving CTY prefix CSV: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/spots/explain/{callsign:path}")
async def explain_spot_classification(
    callsign: str,
    request: Request,
    band: Optional[str] = None,
    mode: Optional[str] = None,
    frequency_khz: Optional[float] = None,
    comment: str = "",
):
    """Explain CTY resolution and Wavelog/DXCC classification for one callsign."""
    try:
        from radio_control.spot_processor import band_from_khz, infer_mode
        from radio_control.spot_classification import classify_call_status, classify_dxcc_status
        from services.digital_status import call_status_from_recent_qsos

        callsign_upper = callsign.strip().upper()
        if not callsign_upper:
            raise HTTPException(status_code=400, detail="callsign is required")

        resolved_band = band
        if not resolved_band and frequency_khz is not None:
            resolved_band = band_from_khz(frequency_khz)
        resolved_mode = mode
        if not resolved_mode and frequency_khz is not None:
            resolved_mode = infer_mode(comment or "", resolved_band, frequency_khz)

        cty_resolver = getattr(request.app.state, "cty_resolver", None)
        classifier = getattr(request.app.state, "classifier", None)

        cty_info = cty_resolver.lookup(callsign_upper) if cty_resolver else {}
        dxcc = cty_info.get("dxcc")

        call_flags = {}
        dxcc_flags = {}
        call_status = "Unknown"
        dxcc_status = "Unknown"
        tag = None

        if classifier:
            call_worked, call_confirmed, call_new_band, call_new_mode, call_bandmode_confirmed = (
                await classifier.call_status_flags(callsign_upper, resolved_band, resolved_mode)
            )
            call_flags = {
                "worked": call_worked,
                "confirmed": call_confirmed,
                "new_band": call_new_band,
                "new_mode": call_new_mode,
                "bandmode_confirmed": call_bandmode_confirmed,
            }
            call_status = classify_call_status(
                call_worked,
                call_new_band,
                call_new_mode,
                call_bandmode_confirmed,
            )
            recent_call_status = await call_status_from_recent_qsos(callsign_upper, resolved_band, resolved_mode)
            if recent_call_status:
                call_status = recent_call_status

            if dxcc is not None:
                dxcc_overall = await classifier.dxcc_overall(
                    dxcc,
                    callsign=callsign_upper,
                    allow_unconfirmed_fallback=False,
                )
                dxcc_bandmode = (
                    await classifier.dxcc_bandmode_flags(
                        dxcc,
                        resolved_band,
                        resolved_mode,
                        callsign=callsign_upper,
                        allow_unconfirmed_fallback=False,
                    )
                )
                if dxcc_overall is None or dxcc_bandmode is None:
                    dxcc_status = "Unknown"
                    dxcc_flags = {"status_source": "unavailable"}
                else:
                    dxcc_worked, dxcc_confirmed = dxcc_overall
                    dxcc_new_band, dxcc_new_mode, dxcc_bandmode_confirmed = dxcc_bandmode
                    dxcc_flags = {
                        "worked": dxcc_worked,
                        "confirmed": dxcc_confirmed,
                        "new_band": dxcc_new_band,
                        "new_mode": dxcc_new_mode,
                        "bandmode_confirmed": dxcc_bandmode_confirmed,
                    }
                    dxcc_display = classify_dxcc_status(
                        dxcc_worked,
                        dxcc_confirmed,
                        dxcc_new_band,
                        dxcc_new_mode,
                        dxcc_bandmode_confirmed,
                    )
                    dxcc_status = dxcc_display.status
                    tag = dxcc_display.tag

        qso_cache = {}
        if classifier and getattr(classifier, "qso_status_store", None):
            try:
                qso_cache = await asyncio.wait_for(
                    asyncio.to_thread(classifier.qso_status_store.diagnostics),
                    timeout=0.5,
                )
            except asyncio.TimeoutError:
                qso_cache = {"loaded": False, "status": "diagnostics timed out"}

        return {
            "ok": True,
            "callsign": callsign_upper,
            "inputs": {
                "band": resolved_band,
                "mode": resolved_mode,
                "frequency_khz": frequency_khz,
                "comment": comment,
            },
            "cty": cty_info,
            "call": {
                "status": call_status,
                "flags": call_flags,
            },
            "dxcc": {
                "adif": dxcc,
                "status": dxcc_status,
                "tag": tag,
                "flags": dxcc_flags,
            },
            "sources": {
                "cty": "data/cty.dat + data/cty.csv",
                "call_status": "Wavelog private_lookup",
                "dxcc_worked": "Wavelog database status cache",
                "dxcc_confirmed": "Wavelog database status cache",
            },
            "qso_cache": qso_cache,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error explaining spot classification for %s: %s", callsign, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/spots/filtered-search")
async def search_filtered_spots(req: SpotFilterRequest, request: Request):
    """
    Search spots in the DuckDB database with comprehensive filtering
    This endpoint queries the persistent spots database, allowing access to all historical spots
    not just the cached recent ones.
    
    Classifications (call_status and dxcc_status) are pre-computed and stored when spots are 
    received from the cluster, so filtered search is fast.
    
    Returns up to 'limit' spots matching all specified filters with cached classifications.
    """
    try:
        from radio_control.spots_logger import get_spots_logger
        
        logger.info(f"🔍 Filtered search: callsign={req.callsign}, bands={req.bands}, modes={req.modes}, limit={req.limit}")
        
        spots_logger = get_spots_logger()
        spots = spots_logger.get_filtered_spots(
            limit=req.limit,
            callsign=req.callsign,
            bands=req.bands,
            modes=req.modes,
            zones_cq=req.zones_cq,
            continents=req.continents,
            special_tags_filter=req.special_tags,
            spot_sources=req.spot_sources,
            rbl_mode_groups=req.rbl_modes,
            rbl_min_snr=req.rbl_min_snr,
            rbl_dedupe_minutes=req.rbl_dedupe_minutes,
            max_age_minutes=req.max_age_minutes,
            sort_by=req.sort_by,
        )
        _enrich_spot_cty_locations(request.app.state, spots)
        if not req.visual_map:
            try:
                from radio_control.local_heard import correlate_local_heard
                from radio_control.spot_intelligence import enrich_spot_intelligence
                from services.ft8_service import get_ft8_service
                from radio_control import config as app_config
                from activity_intelligence.services import get_activity_intelligence_service

                decoded_messages = get_ft8_service().get_decoded_messages(limit=100)
                activity_intelligence = get_activity_intelligence_service()
                for spot in spots:
                    correlate_local_heard(spot, decoded_messages, mycall=getattr(app_config, "MY_STATION", ""))
                    enrich_spot_intelligence(spot)
                    activity_intelligence.enrich_spot(spot)
                if req.sort_by == "score":
                    spots.sort(key=lambda spot: (spot.get("spot_score", 0), spot.get("timestamp", 0)), reverse=True)
            except Exception:
                logger.debug("Could not correlate filtered spots with local decodes", exc_info=True)
        
        logger.debug(f"✓ Filtered search returned {len(spots)} spots (using pre-computed classifications from database)")
        return {"ok": True, "spots": spots, "count": len(spots)}
        
    except Exception as e:
        message = str(e)
        if "Cannot open file" in message and "spots.duckdb" in message:
            logger.warning("Filtered spot search unavailable because spots.duckdb is locked: %s", message)
            return {
                "ok": False,
                "spots": [],
                "count": 0,
                "warning": "spots database is locked by another process",
            }
        logger.error(f"Error in filtered search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/spots/maintenance/repair")
async def repair_spot_metadata(req: SpotMaintenanceRepairRequest):
    """Recompute stored spot mode/source/RBL/special/country metadata."""
    try:
        from radio_control.spots_logger import get_spots_logger

        spots_logger = get_spots_logger()
        result = await asyncio.to_thread(
            spots_logger.repair_spot_metadata,
            limit=req.limit,
            dry_run=req.dry_run,
            vacuum=req.vacuum,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error", "repair failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Spot metadata repair error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/spots/tune")
async def tune_to_spot(req: SpotTuneRequest, request: Request):
    """Tune to DX spot frequency and optionally change mode"""
    flex = request.app.state.flex
    
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")
    
    try:
        # Import broadcast function
        from services.websocket import broadcast_status
        
        # Tune frequency
        success = flex.tune_mhz(req.frequency)
        if not success:
            raise HTTPException(status_code=400, detail="Tune command failed")
        
        radio_mode = _radio_mode_for_spot(req.mode, req.frequency)

        # Set mode if provided
        if radio_mode:
            mode_success = flex.set_mode(radio_mode)
            if not mode_success:
                logger.warning(f"Mode change to {radio_mode} failed, but frequency changed")
        
        # Broadcast status update
        update = {"frequency": req.frequency}
        if radio_mode:
            update["mode"] = radio_mode
        await broadcast_status(update)
        
        return {"success": True, "mode": radio_mode}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tune to spot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/spots/count")
async def get_spots_count(request: Request):
    """Get total count of spots from persistent database"""
    try:
        from radio_control.spots_logger import get_spots_logger
        spots_logger = get_spots_logger()
        count = spots_logger.get_spot_count()
        return {"count": count}
    except Exception as e:
        logger.error(f"Error getting spot count: {e}")
        return {"count": 0}


@router.get("/api/spots/source-stats")
async def get_spots_source_stats(request: Request, fast: bool = False):
    """Get live cache and persisted recent source counts for cluster/RBL monitoring."""
    live_stats = _build_live_source_stats(getattr(request.app.state, "dx_spots_cache", []))
    if fast:
        return {
            "ok": True,
            "live": live_stats,
            "all_time": live_stats,
            "windows": [],
        }
    try:
        from radio_control.spots_logger import get_spots_logger

        spots_logger = get_spots_logger()
        persisted = spots_logger.get_source_stats([5, 15, 60])
        if not persisted.get("ok"):
            return {
                "ok": False,
                "live": live_stats,
                "all_time": persisted.get("all_time", {}),
                "windows": persisted.get("windows", []),
                "error": persisted.get("error", "source stats unavailable"),
            }
        return {
            "ok": True,
            "live": live_stats,
            "all_time": persisted.get("all_time", {}),
            "windows": persisted.get("windows", []),
        }
    except Exception as e:
        logger.error("Error getting source stats: %s", e, exc_info=True)
        return {
            "ok": False,
            "live": live_stats,
            "all_time": {},
            "windows": [],
            "error": str(e),
        }


@router.get("/api/spots/stats/band")
async def get_spots_stats_by_band(date: Optional[str] = None):
    """Get persisted spots grouped by band."""
    try:
        from radio_control.spots_logger import get_spots_logger
        spots_logger = get_spots_logger()
        stats = spots_logger.get_stats_by_band(date)
        return {"ok": True, "data": stats, "date_filter": date}
    except Exception as e:
        logger.error(f"Error getting band statistics: {e}", exc_info=True)
        return {"ok": False, "data": [], "date_filter": date, "error": str(e)}


@router.get("/api/spots/stats/mode")
async def get_spots_stats_by_mode(date: Optional[str] = None):
    """Get persisted spots grouped by mode."""
    try:
        from radio_control.spots_logger import get_spots_logger
        spots_logger = get_spots_logger()
        stats = spots_logger.get_stats_by_mode(date)
        return {"ok": True, "data": stats, "date_filter": date}
    except Exception as e:
        logger.error(f"Error getting mode statistics: {e}", exc_info=True)
        return {"ok": False, "data": [], "date_filter": date, "error": str(e)}


@router.get("/api/spots/stats/country")
async def get_spots_stats_by_country(
    limit: int = 20,
    date: Optional[str] = None,
):
    """Get persisted spots grouped by country."""
    try:
        from radio_control.spots_logger import get_spots_logger
        spots_logger = get_spots_logger()
        stats = spots_logger.get_stats_by_country(limit, date)
        return {"ok": True, "data": stats, "limit": limit, "date_filter": date}
    except Exception as e:
        logger.error(f"Error getting country statistics: {e}", exc_info=True)
        return {"ok": False, "data": [], "limit": limit, "date_filter": date, "error": str(e)}


@router.get("/api/spots/special")
async def get_special_event_spots(limit: int = 100):
    """Get persisted spots tagged as special event stations."""
    try:
        from radio_control.spots_logger import get_spots_logger
        spots_logger = get_spots_logger()
        spots = spots_logger.get_special_event_spots(limit)
        return {"ok": True, "data": spots, "count": len(spots)}
    except Exception as e:
        logger.error(f"Error getting special event spots: {e}", exc_info=True)
        return {"ok": False, "data": [], "count": 0, "error": str(e)}


@router.get("/api/spots/recent")
async def get_recent_spots(request: Request, limit: int = 999999):
    """Get recent spots from persistent database (not just cache)"""
    try:
        from radio_control.spots_logger import get_spots_logger
        spots_logger = get_spots_logger()
        spots = spots_logger.get_recent_spots(limit)
        return {"spots": spots}
    except Exception as e:
        logger.error(f"Error getting recent spots: {e}")
        # Fallback to cache if database is unavailable
        dx_spots_cache = getattr(request.app.state, 'dx_spots_cache', [])
        return {"spots": dx_spots_cache[:limit]}


@router.get("/api/spots/callsign/{callsign}")
async def get_spots_by_callsign(callsign: str, request: Request, limit: int = 100):
    """Get all spots for a specific callsign from persistent database"""
    try:
        from radio_control.spots_logger import get_spots_logger
        spots_logger = get_spots_logger()
        spots = spots_logger.get_spots_by_callsign(callsign, limit)
        return {"callsign": callsign, "count": len(spots), "spots": spots}
    except Exception as e:
        logger.error(f"Error getting spots for {callsign}: {e}")
        # Fallback to cache
        dx_spots_cache = getattr(request.app.state, 'dx_spots_cache', [])
        callsign_upper = callsign.upper()
        spots = [s for s in dx_spots_cache if s.get('callsign', '').upper() == callsign_upper]
        return {"callsign": callsign, "count": len(spots), "spots": spots}


@router.post("/api/spots/add-to-radio")
async def add_spot_to_radio(req: SpotTuneRequest, request: Request):
    """Tune to DX spot frequency and optionally change mode (alias for /api/spots/tune)"""
    flex = getattr(request.app.state, 'flex', None)
    
    if not flex:
        return {"success": False, "error": "Radio not initialized"}
    
    try:
        # Import broadcast function
        from services.websocket import broadcast_status
        
        # Tune frequency
        success = flex.tune_mhz(req.frequency)
        if not success:
            return {"success": False, "error": "Tune command failed"}
        
        radio_mode = _radio_mode_for_spot(req.mode, req.frequency)

        # Set mode if provided
        if radio_mode:
            mode_success = flex.set_mode(radio_mode)
            if not mode_success:
                logger.warning(f"Mode change to {radio_mode} failed, but frequency changed")
        
        # Broadcast status update
        update = {"frequency": req.frequency}
        if radio_mode:
            update["mode"] = radio_mode
        await broadcast_status(update)
        
        return {"success": True, "mode": radio_mode}
    except Exception as e:
        logger.error(f"Add spot to radio error: {e}")
        return {"success": False, "error": str(e)}
