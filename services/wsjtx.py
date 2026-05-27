"""
WSJT-X Service Module

Extracted WSJT-X integration from main.py for modularization.
Includes auto-logging to Wavelog, QRZ data enrichment, and auto-rotation features.
"""

import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException

# Import required modules
from radio_control.spot_processor import band_from_khz
from radio_control.qso_outbox import get_qso_outbox
from radio_control import config
logger = logging.getLogger(__name__)


class WSJTXService:
    """
    Service class for WSJT-X operations, auto-logging, and auto-rotation.
    Encapsulates all WSJT-X related functionality extracted from main.py.
    """

    def __init__(self):
        self.wavelog_client = None
        self.qrz_client = None
        self.rotor_service = None
        self.cty_resolver = None
        self.adif_handler = None

    def set_dependencies(self, wavelog_client, qrz_client, rotor_service, cty_resolver=None, adif_handler=None):
        """Set external dependencies"""
        self.wavelog_client = wavelog_client
        self.qrz_client = qrz_client
        self.rotor_service = rotor_service
        self.cty_resolver = cty_resolver
        self.adif_handler = adif_handler

    async def log_qso(self, req: Dict[str, Any]):
        """
        Auto-log a QSO from WSJT-X to Wavelog
        Enriches with QRZ data if available
        """
        if not self.wavelog_client:
            raise HTTPException(status_code=503, detail="Wavelog client not initialized")

        try:
            call = req['call'].strip().upper()

            # Fetch QRZ data if not already provided
            qrz_data = req.get('qrz_data', {}) or {}
            if not qrz_data and self.qrz_client:
                try:
                    logger.info(f"📡 Fetching QRZ data for {call}...")
                    qrz_data = await self.qrz_client.lookup(call) or {}
                    if qrz_data:
                        logger.info(f"✅ QRZ lookup successful for {call}: {qrz_data.get('fname', 'N/A')} from {qrz_data.get('country', 'N/A')}")
                    else:
                        logger.debug(f"ℹ️  No QRZ data found for {call}")
                except Exception as e:
                    logger.warning(f"⚠️  QRZ lookup failed for {call}: {e}")
                    qrz_data = {}

            # Enrich with CTY data if available (for continent and other metadata)
            cty_data = {}
            if self.cty_resolver:
                try:
                    cty_data = self.cty_resolver.lookup(call) or {}
                    if cty_data and cty_data.get('continent'):
                        logger.debug(f"📍 CTY lookup for {call}: continent={cty_data.get('continent')}")
                except Exception as e:
                    logger.debug(f"CTY lookup failed for {call}: {e}")

            # Build QSO data from WSJT-X and QRZ
            # Match the standard QSORequest structure to ensure consistency with regular QSO logging
            band = band_from_khz(req.get('frequency_hz') / 1000) if req.get('frequency_hz') else "Unknown"
            
            qso_data = {
                # Core fields (required)
                "callsign": call,
                "frequency": req.get('frequency_hz') / 1_000_000 if req.get('frequency_hz') else None,
                "mode": req['mode'].upper(),
                "band": band,  # Include band for ADIF saving
                
                # RST values: keep as-is or use defaults (wavelog_api.py handles conversion)
                "rst_sent": req.get('rst_sent'),
                "rst_received": req.get('rst_received'),
                
                # Date/Time fields
                "date": None,  # Will use current date in wavelog_api
                "time_off": None,  # Will use current time in wavelog_api
                "date_time": None,  # Alternative date_time field
                
                # Station info (enriched from QRZ/CTY)
                "name": qrz_data.get("fname", ""),
                "qth": qrz_data.get("state", qrz_data.get("country", "")),
                "gridsquare": req.get('grid') or qrz_data.get("grid", ""),
                "notes": req.get('comments') or f"Auto-logged from WSJT-X ({req['mode']})",
                
                # Activation programs
                "pota": None,
                "sota": None,
                "iota": None,
                "wwff": None,
                
                # Location info
                "continent": cty_data.get("continent", qrz_data.get("continent", "")),  # Prefer CTY continent if available
                "cq_zone": qrz_data.get("cqzone"),
                "itu_zone": qrz_data.get("ituzone"),
                "region": None,
                "country": qrz_data.get("country", ""),
                "state": qrz_data.get("state", ""),
                "us_county": None,
                
                # Radio/Antenna
                "tx_pwr": None,
                "ant": None,
                
                # QSL info
                "qsl_rcvd": None,
                "qsl_sent": None,
                "lotw_member": qrz_data.get("lotw", False),
                "qsl_manager": None,
                
                # Advanced fields
                "email": qrz_data.get("email", ""),
                "prop_mode": None,
                "ant_path": None,
                "sat_name": None,
                "sat_mode": None,
                "freq_rx": None,
                "mode_rx": None,
            }

            logger.info(f"📝 Auto-logging QSO: {call} on {band} {req['mode']}")
            logger.debug(f"   QSO Data: name={qso_data['name']}, country={qso_data['country']}, grid={qso_data['gridsquare']}")

            # Log to Wavelog
            result = await self.wavelog_client.log_qso(qso_data)

            # Always save to local ADIF file (backup/archive with enriched data)
            adif_saved = False
            try:
                if self.adif_handler:
                    adif_saved = self.adif_handler.add_qso(qso_data)
                    if adif_saved:
                        logger.info(f"✅ QSO saved to local ADIF: {call} with enriched data (name, country, grid, etc.)")
                    else:
                        logger.warning(f"⚠️  Failed to save QSO to ADIF file: {call}")
            except Exception as e:
                logger.error(f"❌ ADIF save error for {call}: {e}", exc_info=True)
                adif_saved = False

            if result and result.get("success"):
                # Extract QSO ID from response if available
                qso_id = None
                if result.get("data"):
                    # Try different possible response formats
                    qso_id = result["data"].get("id") or result["data"].get("qso_id") or result["data"].get("lastid")
                
                logger.info(f"✅ QSO logged successfully to Wavelog: {call} (ID: {qso_id if qso_id else 'unknown'}), ADIF: {adif_saved}")
                
                # Return enriched QSO data to frontend for display in confirmation modal
                return {
                    "success": True, 
                    "qso_id": qso_id, 
                    "message": result.get("message", "QSO logged successfully"),
                    "adif_saved": adif_saved,
                    "qso_data": {
                        "callsign": call,
                        "frequency": req.get('frequency_hz') / 1_000_000 if req.get('frequency_hz') else None,
                        "mode": req['mode'].upper(),
                        "gridsquare": qso_data['gridsquare'],
                        "rst_sent": req.get('rst_sent'),
                        "rst_received": req.get('rst_received'),
                        "name": qso_data['name'],  # From QRZ enrichment
                        "country": qso_data['country'],  # From QRZ enrichment
                        "state": qso_data['state'],
                        "continent": qso_data['continent']
                    }
                }
            else:
                logger.error(f"❌ Failed to log QSO to Wavelog: {result}")
                outbox_queued = get_qso_outbox().enqueue(
                    qso_data,
                    reason=(result or {}).get("message", "WSJT-X Wavelog upload failed"),
                )
                # If Wavelog fails but ADIF saved, still return partial success
                if adif_saved or outbox_queued:
                    logger.info(
                        "ℹ️  QSO saved locally but Wavelog failed: %s (ADIF: %s, Outbox: %s)",
                        call,
                        adif_saved,
                        outbox_queued,
                    )
                    return {
                        "success": False,
                        "adif_saved": True,
                        "outbox_queued": outbox_queued,
                        "message": (
                            "Wavelog logging failed but QSO saved locally: "
                            f"{(result or {}).get('message', str(result))}"
                        )
                    }
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to log QSO: {(result or {}).get('message', str(result))}",
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ WSJT-X log error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def auto_rotate(self, req: Dict[str, Any]):
        """
        Auto-rotate to DX station based on grid square
        Only rotates if ROTOR_AUTO_ENABLED is True
        """
        if not config.ROTOR_AUTO_ENABLED or not self.rotor_service:
            return {"success": False, "reason": "Rotator auto mode not enabled"}

        try:
            call = req['call'].strip().upper()
            grid = req['grid'].strip().upper()

            if not grid or len(grid) < 4:
                logger.warning(f"⚠️  Invalid grid square for {call}: {grid}")
                return {"success": False, "reason": "Invalid grid square"}

            logger.info(f"🎯 Auto-rotating to {call} ({grid})...")

            result = await self.rotor_service.rotor_auto_goto({
                "callsign": call,
                "frequency_khz": req.get('frequency_hz') / 1000 if req.get('frequency_hz') else None,
                "gridsquare": grid,
                "location_source": "wsjtx_grid",
                "grid_source": "wsjtx",
            })

            if result.get("ok"):
                logger.info(f"✅ Rotator command sent: {call} on {result.get('bearing')}°")
                return {
                    "success": True,
                    "call": call,
                    "grid": grid,
                    "bearing": result.get("bearing"),
                    "adjusted_bearing": result.get("bearing"),
                    "band": result.get("band"),
                    "source": result.get("source"),
                    "confidence": result.get("confidence"),
                }
            else:
                logger.error(f"❌ Rotator command failed: {call}")
                return {
                    "success": False,
                    "reason": result.get("message") or result.get("error") or "Rotor command failed",
                    "bearing": result.get("bearing"),
                    "band": result.get("band"),
                    "source": result.get("source"),
                    "confidence": result.get("confidence"),
                }

        except Exception as e:
            logger.error(f"❌ Auto-rotate error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_config(self):
        """Get WSJT-X configuration"""
        return {
            "enabled": getattr(config, 'WSJTX_ENABLED', True),
            "udp_port": getattr(config, 'WSJTX_UDP_PORT', 2237),
            "multicast": getattr(config, 'WSJTX_UDP_MULTICAST', '224.0.0.1'),
            "ws_port": getattr(config, 'WSJTX_WS_PORT', 8091),
            "auto_log": getattr(config, 'WSJTX_AUTO_LOG', True),
            "auto_rotate": getattr(config, 'WSJTX_AUTO_ROTATE', True) and getattr(config, 'ROTOR_AUTO_ENABLED', False),
            "modal_fields": getattr(config, 'WSJTX_MODAL_FIELDS', {}),
        }


# Global service instance
_wsjtx_service: Optional[WSJTXService] = None


def get_wsjtx_service() -> WSJTXService:
    """Get the global WSJT-X service instance"""
    global _wsjtx_service
    if _wsjtx_service is None:
        _wsjtx_service = WSJTXService()
    return _wsjtx_service


def register_wsjtx_endpoints(app):
    """
    Register WSJT-X related endpoints with the FastAPI app.
    This function can be called from main.py to register all WSJT-X endpoints.
    """

    @app.post("/api/wsjtx/log-qso")
    async def wsjtx_log_qso(req: Dict[str, Any]):
        """
        Auto-log a QSO from WSJT-X to Wavelog
        Enriches with QRZ data if available
        """
        service = get_wsjtx_service()
        return await service.log_qso(req)

    @app.post("/api/wsjtx/auto-rotate")
    async def wsjtx_auto_rotate(req: Dict[str, Any]):
        """
        Auto-rotate to DX station based on grid square
        Only rotates if ROTOR_AUTO_ENABLED is True
        """
        service = get_wsjtx_service()
        return await service.auto_rotate(req)

    @app.get("/api/wsjtx/config")
    async def get_wsjtx_config():
        """Get WSJT-X configuration"""
        service = get_wsjtx_service()
        return service.get_config()
