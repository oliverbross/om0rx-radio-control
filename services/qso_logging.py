"""
QSO Logging Service Module
Extracted from main.py - provides QSO logging endpoints for Wavelog integration,
QRZ lookups, and recent QSOs retrieval.
"""

import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel

# Import required clients and handlers
from radio_control.wavelog_api import WavelogClient
from radio_control.qrz_api import QRZClient
from radio_control.adif_handler import ADIFHandler
from radio_control.cty_resolvers import CtyDatResolver
from radio_control.qso_outbox import get_qso_outbox

logger = logging.getLogger(__name__)

# Create router for QSO logging endpoints
router = APIRouter()

# Global clients (will be initialized when module is imported)
wavelog_client: Optional[WavelogClient] = None
qrz_client: Optional[QRZClient] = None
adif_handler: Optional[ADIFHandler] = None
cty_resolver: Optional[CtyDatResolver] = None


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


def init_qso_logging_clients(w_client: WavelogClient, q_client: QRZClient,
                           a_handler: ADIFHandler, c_resolver: CtyDatResolver):
    """Initialize the global clients for QSO logging"""
    global wavelog_client, qrz_client, adif_handler, cty_resolver
    wavelog_client = w_client
    qrz_client = q_client
    adif_handler = a_handler
    cty_resolver = c_resolver
    logger.info("✅ QSO logging clients initialized")


@router.post("/api/qso/log")
async def log_qso(qso: QSORequest):
    """Log a QSO to Wavelog and local ADIF file"""
    global wavelog_client, adif_handler

    try:
        logger.info(f"📝 QSO Log Request - Callsign: {qso.callsign}, Freq: {qso.frequency}, Mode: {qso.mode}, RST_sent: {qso.rst_sent}, RST_rcvd: {qso.rst_received}")

        # Initialize clients if needed (with error handling)
        try:
            if not wavelog_client:
                logger.debug("🔌 Initializing WavelogClient...")
                wavelog_client = WavelogClient()
                logger.info("✅ WavelogClient initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize WavelogClient: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to initialize Wavelog client: {str(e)}")

        try:
            if not adif_handler:
                logger.debug("🔌 Initializing ADIFHandler...")
                adif_handler = ADIFHandler()
                logger.info("✅ ADIFHandler initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ADIFHandler: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to initialize ADIF handler: {str(e)}")

        # Convert request to dict and preserve RST values as-is
        # They can be strings (FT8 SNR like "-12") or will be converted by wavelog_api
        qso_dict = qso.dict(exclude_unset=False)  # Include all fields

        # Don't override RST values here - let wavelog_api handle the conversion
        # It will use 599 as default for empty values
        logger.debug(f"QSO dict: {qso_dict}")

        # Log to Wavelog API with error handling
        try:
            logger.debug("📤 Sending QSO to Wavelog API...")
            wavelog_result = await wavelog_client.log_qso(qso_dict)
            logger.debug(f"✅ Wavelog result: {wavelog_result}")
        except Exception as e:
            logger.error(f"❌ Wavelog API call failed: {str(e)}", exc_info=True)
            wavelog_result = {'success': False, 'message': f'Wavelog error: {str(e)}'}

        # Always save to local ADIF file (backup/archive)
        try:
            adif_saved = adif_handler.add_qso(qso_dict)
            if not adif_saved:
                logger.warning(f"Failed to save QSO to ADIF file after retries: {qso.callsign}")
        except Exception as e:
            logger.error(f"ADIF save failed: {str(e)}", exc_info=True)
            adif_saved = False

        outbox_queued = False
        if not wavelog_result.get('success'):
            reason = wavelog_result.get('message') or wavelog_result.get('error') or 'Wavelog upload failed'
            outbox_queued = get_qso_outbox().enqueue(qso_dict, reason=reason)

        logger.info(
            "✅ QSO processed: %s on %s MHz (Wavelog: %s, ADIF: %s, Outbox: %s)",
            qso.callsign,
            qso.frequency,
            wavelog_result.get('success'),
            adif_saved,
            outbox_queued,
        )

        return {
            "success": wavelog_result.get('success', False) or outbox_queued,
            "message": wavelog_result.get('message', 'QSO logged successfully'),
            "wavelog": wavelog_result,
            "adif_saved": adif_saved,
            "outbox_queued": outbox_queued,
            "outbox": get_qso_outbox().status(),
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected QSO logging error: {str(e)}", exc_info=True)
        logger.error(f"   Full traceback available above", exc_info=False)
        raise HTTPException(
            status_code=500,
            detail=f"QSO logging failed: {type(e).__name__}: {str(e)}"
        )


@router.get("/api/qrz/profile/{callsign:path}")
async def get_qrz_profile(callsign: str):
    """Get QRZ profile picture and info for a callsign"""
    global qrz_client

    try:
        if not qrz_client:
            qrz_client = QRZClient()

        result = await qrz_client.get_profile_picture(callsign)

        if result.get('success'):
            logger.info(f"✅ QRZ profile retrieved for {callsign}")
        else:
            logger.warning(f"QRZ profile not found for {callsign}")

        return result

    except Exception as e:
        logger.error(f"QRZ profile error: {str(e)}")
        return {'success': False, 'message': str(e)}


@router.get("/api/qrz/history/{callsign:path}")
async def get_qrz_history(callsign: str, limit: int = 20):
    """Get QRZ contact history for a callsign"""
    global qrz_client

    try:
        if not qrz_client:
            qrz_client = QRZClient()

        result = await qrz_client.get_contact_history(callsign, limit)
        return result

    except Exception as e:
        logger.error(f"QRZ history error: {str(e)}")
        return {'success': False, 'data': []}


@router.post("/api/wavelog/private_lookup")
async def wavelog_private_lookup(data: dict):
    """
    Perform private lookup in Wavelog logbook for a callsign
    Returns comprehensive info including worked/confirmed status by band/mode
    Enhanced with DXCC entity name and geographic data for country modal
    """
    global wavelog_client, cty_resolver

    try:
        if not wavelog_client:
            wavelog_client = WavelogClient()

        callsign = data.get('callsign', '').strip().upper()
        band = data.get('band', '')
        mode = data.get('mode', '')

        if not callsign:
            return {'success': False, 'message': 'Callsign required'}

        result = await wavelog_client.private_lookup(callsign, band or None, mode or None)

        # Enrich response with DXCC entity name and geographic data
        if result.get('success') and result.get('data'):
            response_data = result['data']

            # Try to get DXCC info using cty_resolver
            if cty_resolver:
                try:
                    info = cty_resolver.lookup(callsign)
                    if info:
                        # Add DXCC entity name (country name)
                        if 'country' in info and not response_data.get('dxcc_entity'):
                            response_data['dxcc_entity'] = info['country']

                        # Add continent
                        if 'continent' in info and not response_data.get('continent'):
                            response_data['continent'] = info['continent']

                        # Add CQ zone
                        if 'cq' in info and not response_data.get('cq'):
                            response_data['cq'] = info['cq']

                        # Add DXCC ID
                        if 'dxcc' in info and not response_data.get('dxcc'):
                            response_data['dxcc'] = info['dxcc']

                        # Add ITU zone
                        if 'itu' in info and not response_data.get('itu'):
                            response_data['itu'] = info['itu']

                        # Add latitude/longitude
                        if 'latitude' in info and not response_data.get('latitude'):
                            response_data['latitude'] = info['latitude']
                        if 'longitude' in info and not response_data.get('longitude'):
                            response_data['longitude'] = info['longitude']

                        # Add grid square
                        if 'grid' in info and not response_data.get('grid'):
                            response_data['grid'] = info['grid']

                        logger.debug(f"✅ Enhanced DXCC lookup for {callsign}: {info}")
                except Exception as e:
                    logger.debug(f"Could not enrich DXCC data for {callsign}: {e}")

        return result

    except Exception as e:
        logger.error(f"Wavelog private lookup error: {str(e)}")
        return {'success': False, 'message': str(e)}


@router.post("/api/wavelog/recent_qsos")
async def wavelog_recent_qsos(req: RecentQSOsRequest):
    """
    Get recent QSOs with a specific callsign from Wavelog API.
    Uses Wavelog's api/get_contacts_adif endpoint to fetch QSO history.
    Returns last N QSOs (default 5) with date, band, mode, RST, LoTW status, etc.

    Response format (per QSO):
    {
        "call": "OM0AAO",
        "qso_date": "20251014",
        "time_on": "174200",
        "mode": "SSB",
        "frequency": 14.074,
        "rst_sent": "599",
        "rst_rcvd": "599",
        "band": "20m",
        "lotw_qsl": "Y"
    }
    """
    global adif_handler, wavelog_client

    try:
        callsign = req.callsign.strip().upper()
        limit = req.limit

        logger.info(f"🔍 Recent QSOs request for {callsign} (limit={limit})")

        if not callsign:
            return {'success': False, 'message': 'Callsign required'}

        # Use Wavelog API only - no local fallback
        if not wavelog_client:
            wavelog_client = WavelogClient()

        logger.debug(f"  Attempting Wavelog API for {callsign}")
        result = await wavelog_client.get_recent_qsos(callsign, limit)

        if result.get('success') and result.get('data'):
            data = result['data']
            logger.info(f"✅ Found {len(data)} recent QSOs for {callsign} from Wavelog API")

            # Validate that all required fields are present
            required_fields = ['call', 'qso_date', 'mode', 'rst_sent', 'rst_rcvd', 'band', 'lotw_qsl']
            for qso in data:
                missing = [f for f in required_fields if f not in qso]
                if missing:
                    logger.debug(f"  QSO missing fields: {missing}")

            return {'success': True, 'data': data}
        else:
            # No QSOs found in Wavelog - return empty result (still successful API call)
            logger.debug(f"ℹ️ No recent QSOs found for {callsign} in Wavelog API - returning empty result")
            return {'success': True, 'data': []}

    except Exception as e:
        logger.error(f"❌ Recent QSOs error for {req.callsign}: {str(e)}")
        import traceback
        logger.debug(traceback.format_exc())
        return {'success': False, 'message': str(e)}


@router.get("/api/qso/outbox/status")
async def qso_outbox_status():
    """Return the offline Wavelog upload outbox status."""
    return {"success": True, "outbox": get_qso_outbox().status()}


@router.post("/api/qso/outbox/retry")
async def retry_qso_outbox(max_records: int = 20):
    """Retry queued Wavelog uploads from the offline ADIF outbox."""
    global wavelog_client
    if not wavelog_client:
        wavelog_client = WavelogClient()
    result = await get_qso_outbox().replay(wavelog_client, max_records=max_records)
    return {"success": result.get("success", False), "result": result, "outbox": get_qso_outbox().status()}


@router.get("/api/wavelog/contacts")
async def get_wavelog_contacts(limit: int = 100):
    """Get recent contacts directly from Wavelog API (fresh data, not cached)"""
    global wavelog_client
    
    try:
        if not wavelog_client:
            wavelog_client = WavelogClient()
        
        # Fetch directly from Wavelog API for fresh, up-to-date contacts
        result = await wavelog_client.get_contacts_from_wavelog_api(limit)
        
        if result.get('success'):
            contact_count = len(result.get('data', []))
            logger.info(f"✅ Retrieved {contact_count} fresh contacts from Wavelog API (limit: {limit})")
            return result
        else:
            logger.warning(f"Failed to retrieve contacts from API: {result.get('message', 'Unknown error')}")
            # Return empty success response instead of error
            return {'success': True, 'data': []}
    
    except Exception as e:
        logger.error(f"Error fetching Wavelog contacts: {str(e)}")
        import traceback
        logger.debug(traceback.format_exc())
        return {'success': True, 'data': []}


def register_qso_logging_endpoints(app):
    """Register all QSO logging endpoints with the FastAPI app"""
    app.include_router(router)
    logger.info("✅ QSO logging endpoints registered with FastAPI app")
