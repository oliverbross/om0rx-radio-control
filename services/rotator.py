"""
Rotator Service Module

Extracted rotator control endpoints from main.py for modularization.
Includes basic rotator operations, auto-rotation logic, and bearing calculations.
"""

import asyncio
import logging
import json
import os
from typing import Optional, Dict, Any
from fastapi import HTTPException

# Import required modules
from radio_control.rotor_api import RotorController
from radio_control.rotor_math import (
    grid_to_latlon, latlon_to_grid, initial_bearing,
    calculate_bearing_for_station, get_band_from_frequency
)
from radio_control import config
logger = logging.getLogger(__name__)


class RotatorService:
    """
    Service class for rotator operations, auto-rotation, and bearing calculations.
    Encapsulates all rotator-related functionality extracted from main.py.
    """

    def __init__(self):
        self.rotor: Optional[RotorController] = None

    async def initialize(self):
        """Initialize the rotator service"""
        try:
            # Load rotor configuration from JSON (if saved)
            self._load_rotor_config()

            # Initialize rotator controller if enabled
            rotor_enabled = getattr(config, 'ROTOR_ENABLED', False)
            if rotor_enabled:
                rotor_host = getattr(config, 'ROTOR_HOST', '192.168.0.198')
                rotor_port = getattr(config, 'ROTOR_PORT', 4001)
                rotor_protocol = getattr(config, 'ROTOR_PROTOCOL', 'DCU-1')
                rotor_timeout = getattr(config, 'ROTOR_TIMEOUT_SEC', 2.5)

                self.rotor = RotorController(rotor_host, rotor_port, rotor_protocol, rotor_timeout)
                logger.info(f"✅ Rotator initialized: {rotor_host}:{rotor_port} ({rotor_protocol})")
            else:
                logger.info("ℹ️ Rotator disabled in config")

            return True
        except Exception as e:
            logger.error(f"❌ Rotator initialization failed: {e}")
            self.rotor = None
            return False

    async def shutdown(self):
        """Shutdown the rotator service"""
        # No specific shutdown needed for rotator
        logger.info("✅ Rotator service shutdown complete")

    def _load_rotor_config(self):
        """Load rotor configuration from JSON file if it exists"""
        try:
            rotor_config_file = config.ROTOR_CONFIG_PATH

            if rotor_config_file.exists():
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

    # === Basic Rotator Operations ===

    async def set_rotor_config(self, req: Dict[str, Any]):
        """Update rotator configuration"""
        try:
            # Update config in memory
            config.ROTOR_ENABLED = req['enabled']
            config.ROTOR_HOST = req['host']
            config.ROTOR_PORT = req['port']
            config.ROTOR_PROTOCOL = req['protocol']
            config.ROTOR_TIMEOUT_SEC = req['timeout']

            # Reinitialize rotator
            if req['enabled']:
                self.rotor = RotorController(req['host'], req['port'], req['protocol'], req['timeout'])
                logger.info(f"✅ Rotator config updated: {req['host']}:{req['port']} ({req['protocol']})")
                return {"ok": True, "message": "Rotator configured"}
            else:
                self.rotor = None
                logger.info("ℹ️ Rotator disabled")
                return {"ok": True, "message": "Rotator disabled"}

        except Exception as e:
            logger.error(f"Rotor config error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_rotor_config(self):
        """Get current rotator configuration"""
        try:
            return {
                "ok": True,
                "enabled": getattr(config, 'ROTOR_ENABLED', False),
                "host": getattr(config, 'ROTOR_HOST', '192.168.0.198'),
                "port": getattr(config, 'ROTOR_PORT', 4001),
                "protocol": getattr(config, 'ROTOR_PROTOCOL', 'DCU-1'),
                "timeout": getattr(config, 'ROTOR_TIMEOUT_SEC', 2.5),
                "type": getattr(config, 'ROTOR_TYPE', 'Microham ARCO')
            }
        except Exception as e:
            logger.error(f"Rotor config retrieval error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_rotor_status(self):
        """Get rotator status (enabled and current azimuth if available)"""
        try:
            if not self.rotor:
                return {"ok": False, "enabled": False, "message": "Rotator not enabled"}

            # Try to get current azimuth
            try:
                az_data = await self.rotor.get_azimuth()
                return {"ok": True, "enabled": True, "azimuth": az_data.get("az")}
            except:
                # Rotator might not be responsive, but still return enabled status
                return {"ok": True, "enabled": True, "azimuth": None}

        except Exception as e:
            logger.error(f"Rotor status error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def rotor_goto(self, req: Dict[str, Any]):
        """Move rotator to specific azimuth"""
        if not self.rotor:
            raise HTTPException(status_code=503, detail="Rotator not enabled")

        try:
            result = await self.rotor.goto_azimuth(req['azimuth'])
            return result
        except Exception as e:
            logger.error(f"Rotor GOTO error: {e}")
            raise HTTPException(status_code=502, detail=f"Rotor command failed: {e}")

    async def rotor_direction(self, req: Dict[str, Any]):
        """Move rotator to cardinal direction (N/S/E/W)"""
        if not self.rotor:
            raise HTTPException(status_code=503, detail="Rotator not enabled")

        try:
            result = await self.rotor.goto_direction(req['direction'])
            return result
        except Exception as e:
            logger.error(f"Rotor direction error: {e}")
            raise HTTPException(status_code=502, detail=f"Rotor command failed: {e}")

    async def rotor_stop(self):
        """Stop rotator movement"""
        if not self.rotor:
            raise HTTPException(status_code=503, detail="Rotator not enabled")

        try:
            result = await self.rotor.stop()
            return result
        except Exception as e:
            logger.error(f"Rotor stop error: {e}")
            raise HTTPException(status_code=502, detail=f"Rotor command failed: {e}")

    async def rotor_ping(self):
        """Check if rotator is responsive"""
        if not self.rotor:
            return {"ok": False, "enabled": False}

        try:
            result = await self.rotor.ping()
            return result
        except Exception as e:
            logger.error(f"Rotor ping error: {e}")
            return {"ok": False, "error": str(e)}

    # === Rotor AUTO Control ===

    async def set_rotor_auto_config(self, req: Dict[str, Any]):
        """Update rotor AUTO configuration (bands, home location, AUTO mode)"""
        try:
            # Update config in memory first
            config.ROTOR_HOME_GRID = req['home_grid'].upper().strip()
            config.ROTOR_HOME_LAT = req['home_lat']
            config.ROTOR_HOME_LON = req['home_lon']
            config.ROTOR_BANDS = req['bands']
            config.ROTOR_AUTO_ENABLED = req['auto_enabled']

            # Persist to JSON file (won't trigger file watcher)
            try:
                rotor_config_file = config.ROTOR_CONFIG_PATH
                rotor_config_file.parent.mkdir(parents=True, exist_ok=True)

                rotor_config_data = {
                    "ROTOR_HOME_GRID": config.ROTOR_HOME_GRID,
                    "ROTOR_HOME_LAT": config.ROTOR_HOME_LAT,
                    "ROTOR_HOME_LON": config.ROTOR_HOME_LON,
                    "ROTOR_BANDS": config.ROTOR_BANDS,
                    "ROTOR_AUTO_ENABLED": config.ROTOR_AUTO_ENABLED,
                }

                with open(rotor_config_file, 'w', encoding='utf-8') as f:
                    json.dump(rotor_config_data, f, indent=2)

                bands_count = sum(1 for v in config.ROTOR_BANDS.values() if v) if config.ROTOR_BANDS else 0
                logger.info(f"✅ Rotor AUTO config saved to JSON: Grid={config.ROTOR_HOME_GRID}, "
                           f"AUTO={config.ROTOR_AUTO_ENABLED}, Bands={bands_count}")

            except Exception as save_err:
                logger.error(f"Failed to persist rotor AUTO config to JSON: {save_err}")
                # Don't fail completely, config is still in memory for this session

            return {
                "ok": True,
                "message": "Rotor AUTO configuration updated and saved",
                "home_grid": config.ROTOR_HOME_GRID,
                "auto_enabled": config.ROTOR_AUTO_ENABLED
            }

        except Exception as e:
            logger.error(f"Rotor AUTO config error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_rotor_auto_status(self):
        """Get rotor AUTO configuration status"""
        try:
            # Reload rotor config from JSON to ensure we have latest settings
            self._load_rotor_config()

            return {
                "ok": True,
                "auto_enabled": getattr(config, 'ROTOR_AUTO_ENABLED', False),
                "home_grid": getattr(config, 'ROTOR_HOME_GRID', 'JN88TQ'),
                "home_lat": getattr(config, 'ROTOR_HOME_LAT', 48.17),
                "home_lon": getattr(config, 'ROTOR_HOME_LON', 17.08),
                "bands": getattr(config, 'ROTOR_BANDS', {}),
                "delay_sec": getattr(config, 'ROTOR_AUTO_DELAY_SEC', 2.0)
            }
        except Exception as e:
            logger.error(f"Rotor AUTO status error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def calculate_rotor_bearing(self, req: Dict[str, Any]):
        """
        Calculate bearing to a station for AUTO rotor control.

        Uses QRZ gridsquare if available, falls back to cty.dat lat/lon.
        Checks if band is enabled in rotor config.
        """
        try:
            # Reload rotor config from JSON to ensure we have latest settings
            self._load_rotor_config()

            # Get home location
            home_lat = getattr(config, 'ROTOR_HOME_LAT', 48.17)
            home_lon = getattr(config, 'ROTOR_HOME_LON', 17.08)
            rotor_bands = getattr(config, 'ROTOR_BANDS', {})

            # Determine band if frequency provided
            band = None
            if req.get('frequency_khz'):
                band = get_band_from_frequency(req['frequency_khz'])

            # Check if band is enabled for rotor
            band_enabled = True
            if band and band not in rotor_bands:
                band_enabled = False
                logger.warning(f"Band {band} not configured for rotor")
            elif band and not rotor_bands.get(band, False):
                band_enabled = False
                logger.info(f"Rotor disabled for band {band}")

            # Calculate bearing (prefers gridsquare over lat/lon)
            try:
                bearing = calculate_bearing_for_station(
                    home_lat, home_lon,
                    station_grid=req.get('gridsquare'),
                    station_lat=req.get('latitude'),
                    station_lon=req.get('longitude')
                )

                if bearing is None:
                    return {
                        "ok": False,
                        "bearing": None,
                        "short_path_bearing": None,
                        "long_path_bearing": None,
                        "band": band,
                        "band_enabled": band_enabled,
                        "error": "Insufficient data to calculate bearing (no gridsquare or coordinates)"
                    }

                short_path = round(bearing, 1)
                long_path = round((bearing + 180) % 360, 1)

                return {
                    "ok": True,
                    "bearing": short_path,
                    "short_path_bearing": short_path,
                    "long_path_bearing": long_path,
                    "band": band,
                    "band_enabled": band_enabled,
                    "callsign": req.get('callsign'),
                    "source": "gridsquare" if req.get('gridsquare') else "coordinates"
                }

            except Exception as calc_error:
                logger.error(f"Bearing calculation error: {calc_error}")
                return {
                    "ok": False,
                    "bearing": None,
                    "short_path_bearing": None,
                    "long_path_bearing": None,
                    "band": band,
                    "band_enabled": band_enabled,
                    "error": str(calc_error)
                }

        except Exception as e:
            logger.error(f"Rotor bearing endpoint error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def rotor_auto_goto(self, req: Dict[str, Any]):
        """
        AUTO rotor GOTO - Calculate bearing and move rotor if AUTO is enabled and band is valid.
        This endpoint combines bearing calculation with actual rotor movement.
        """
        try:
            # Reload rotor config from JSON to ensure we have latest settings
            self._load_rotor_config()

            # Check AUTO mode enabled globally
            auto_enabled = getattr(config, 'ROTOR_AUTO_ENABLED', False)
            if not auto_enabled:
                logger.info(f"⚠️  AUTO rotor not executed: AUTO mode not enabled (config value: {auto_enabled})")
                return {"ok": False, "message": "AUTO mode not enabled"}

            # Check rotor is available
            if not self.rotor:
                return {"ok": False, "message": "Rotor not enabled"}

            # Get band and check if rotor enabled for this band
            band = None
            if req.get('frequency_khz'):
                band = get_band_from_frequency(req['frequency_khz'])

            rotor_bands = getattr(config, 'ROTOR_BANDS', {})
            if band and not rotor_bands.get(band, False):
                return {
                    "ok": False,
                    "band": band,
                    "message": f"Rotor not enabled for band {band}"
                }

            # Calculate bearing
            home_lat = getattr(config, 'ROTOR_HOME_LAT', 48.17)
            home_lon = getattr(config, 'ROTOR_HOME_LON', 17.08)

            bearing = calculate_bearing_for_station(
                home_lat, home_lon,
                station_grid=req.get('gridsquare'),
                station_lat=req.get('latitude'),
                station_lon=req.get('longitude')
            )

            if bearing is None:
                return {
                    "ok": False,
                    "message": "Cannot calculate bearing (insufficient data)"
                }

            # Move rotor to bearing
            try:
                result = await self.rotor.goto_azimuth(int(round(bearing)))
                logger.info(f"✅ AUTO rotor: {req.get('callsign')} on {band or 'unknown'} -> {bearing:.1f}°")

                # Calculate short path and long path bearings for UI display
                short_path = round(bearing, 1)
                long_path = round((bearing + 180) % 360, 1)

                return {
                    "ok": True,
                    "bearing": short_path,
                    "short_path_bearing": short_path,
                    "long_path_bearing": long_path,
                    "band": band,
                    "callsign": req.get('callsign'),
                    "message": f"Rotor moving to {bearing:.1f}°"
                }
            except Exception as rotor_error:
                logger.error(f"Rotor GOTO during AUTO failed: {rotor_error}")
                short_path = round(bearing, 1)
                long_path = round((bearing + 180) % 360, 1)
                return {
                    "ok": False,
                    "bearing": short_path,
                    "short_path_bearing": short_path,
                    "long_path_bearing": long_path,
                    "message": f"Rotor command failed: {rotor_error}"
                }

        except Exception as e:
            logger.error(f"Rotor AUTO GOTO error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# Global service instance
_rotator_service: Optional[RotatorService] = None


def get_rotator_service() -> RotatorService:
    """Get the global rotator service instance"""
    global _rotator_service
    if _rotator_service is None:
        _rotator_service = RotatorService()
    return _rotator_service


async def init_rotator_service() -> bool:
    """Initialize the global rotator service"""
    global _rotator_service
    if _rotator_service is None:
        _rotator_service = RotatorService()
    return await _rotator_service.initialize()


async def shutdown_rotator_service():
    """Shutdown the global rotator service"""
    global _rotator_service
    if _rotator_service:
        await _rotator_service.shutdown()
        _rotator_service = None


def register_rotator_endpoints(app):
    """
    Register rotator-related endpoints with the FastAPI app.
    This function can be called from main.py to register all rotator endpoints.
    """

    # === Basic Rotator Operations ===

    @app.post("/api/rotor/config")
    async def set_rotor_config(req: Dict[str, Any]):
        """Update rotator configuration"""
        service = get_rotator_service()
        return await service.set_rotor_config(req)

    @app.get("/api/rotor/status")
    async def get_rotor_status():
        """Get rotator status (enabled and current azimuth if available)"""
        service = get_rotator_service()
        return await service.get_rotor_status()

    @app.post("/api/rotor/goto")
    async def rotor_goto(req: Dict[str, Any]):
        """Move rotator to specific azimuth"""
        service = get_rotator_service()
        return await service.rotor_goto(req)

    @app.post("/api/rotor/direction")
    async def rotor_direction(req: Dict[str, Any]):
        """Move rotator to cardinal direction (N/S/E/W)"""
        service = get_rotator_service()
        return await service.rotor_direction(req)

    @app.post("/api/rotor/stop")
    async def rotor_stop():
        """Stop rotator movement"""
        service = get_rotator_service()
        return await service.rotor_stop()

    @app.get("/api/rotor/ping")
    async def rotor_ping():
        """Check if rotator is responsive"""
        service = get_rotator_service()
        return await service.rotor_ping()

    # === Rotor AUTO Control ===

    @app.post("/api/rotor/auto/config")
    async def set_rotor_auto_config(req: Dict[str, Any]):
        """Update rotor AUTO configuration (bands, home location, AUTO mode)"""
        service = get_rotator_service()
        return await service.set_rotor_auto_config(req)

    @app.get("/api/rotor/auto/status")
    async def get_rotor_auto_status():
        """Get rotor AUTO configuration status"""
        service = get_rotator_service()
        return await service.get_rotor_auto_status()

    @app.post("/api/rotor/auto/bearing")
    async def calculate_rotor_bearing(req: Dict[str, Any]):
        """
        Calculate bearing to a station for AUTO rotor control.

        Uses QRZ gridsquare if available, falls back to cty.dat lat/lon.
        Checks if band is enabled in rotor config.
        """
        service = get_rotator_service()
        return await service.calculate_rotor_bearing(req)

    @app.post("/api/rotor/auto/goto")
    async def rotor_auto_goto(req: Dict[str, Any]):
        """
        AUTO rotor GOTO - Calculate bearing and move rotor if AUTO is enabled and band is valid.
        This endpoint combines bearing calculation with actual rotor movement.
        """
        service = get_rotator_service()
        return await service.rotor_auto_goto(req)
