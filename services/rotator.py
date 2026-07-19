"""
Rotator Service Module

Extracted rotator control endpoints from main.py for modularization.
Includes basic rotator operations, auto-rotation logic, and bearing calculations.
"""

import logging
import asyncio
import time
from typing import Optional, Dict, Any
from fastapi import HTTPException

# Import required modules
from radio_control.rotor_api import RotorController
from radio_control import config
from radio_control.settings_store import LEGACY_ROTOR_CONFIG_PATH, load_legacy_json, save_config_updates
from services.rotator_resolution import resolve_rotor_target
logger = logging.getLogger(__name__)


class RotatorService:
    """
    Service class for rotator operations, auto-rotation, and bearing calculations.
    Encapsulates all rotator-related functionality extracted from main.py.
    """

    def __init__(self):
        self.rotor: Optional[RotorController] = None
        self._status_lock = asyncio.Lock()
        self._status_cache: Optional[Dict[str, Any]] = None
        self._status_cache_time = 0.0

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
        """Migrate legacy rotor_config.json if it exists."""
        rotor_data = load_legacy_json(LEGACY_ROTOR_CONFIG_PATH)
        if not rotor_data:
            return

        save_result = save_config_updates(rotor_data)
        for key in save_result["updated_keys"]:
            setattr(config, key, rotor_data[key])

        logger.info("Migrated legacy rotor_config.json keys: %s", save_result["updated_keys"])

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
                self._status_cache = None
                self._status_cache_time = 0.0
                logger.info(f"✅ Rotator config updated: {req['host']}:{req['port']} ({req['protocol']})")
                return {"ok": True, "message": "Rotator configured"}
            else:
                self.rotor = None
                self._status_cache = None
                self._status_cache_time = 0.0
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

    async def get_rotor_status(self, fresh: bool = False):
        """Get rotator status (enabled and current azimuth if available)"""
        try:
            if not self.rotor:
                return {"ok": False, "enabled": False, "message": "Rotator not enabled"}

            now = time.monotonic()
            if not fresh and self._status_cache and now - self._status_cache_time < 2.0:
                return self._status_cache

            async with self._status_lock:
                now = time.monotonic()
                if not fresh and self._status_cache and now - self._status_cache_time < 2.0:
                    return self._status_cache

                try:
                    az_data = await self.rotor.get_azimuth()
                    status = {"ok": True, "enabled": True, "azimuth": az_data.get("az")}
                except Exception as exc:
                    logger.debug("Rotor status query failed: %s", exc)
                    status = {"ok": True, "enabled": True, "azimuth": None}

                self._status_cache = status
                self._status_cache_time = time.monotonic()
                return status

        except Exception as e:
            logger.error(f"Rotor status error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def rotor_goto(self, req: Dict[str, Any]):
        """Move rotator to specific azimuth"""
        if not self.rotor:
            raise HTTPException(status_code=503, detail="Rotator not enabled")

        try:
            result = await self.rotor.goto_azimuth(req['azimuth'])
            self._status_cache = None
            self._status_cache_time = 0.0
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
            self._status_cache = None
            self._status_cache_time = 0.0
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
            return {"ok": False, "error": "Rotor status is unavailable"}

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

            # Persist through the shared settings store.
            try:
                rotor_config_data = {
                    "ROTOR_HOME_GRID": config.ROTOR_HOME_GRID,
                    "ROTOR_HOME_LAT": config.ROTOR_HOME_LAT,
                    "ROTOR_HOME_LON": config.ROTOR_HOME_LON,
                    "ROTOR_BANDS": config.ROTOR_BANDS,
                    "ROTOR_AUTO_ENABLED": config.ROTOR_AUTO_ENABLED,
                }

                save_config_updates(rotor_config_data)

                bands_count = sum(1 for v in config.ROTOR_BANDS.values() if v) if config.ROTOR_BANDS else 0
                logger.info(f"✅ Rotor AUTO config saved to app settings: Grid={config.ROTOR_HOME_GRID}, "
                           f"AUTO={config.ROTOR_AUTO_ENABLED}, Bands={bands_count}")

            except Exception as save_err:
                logger.error(f"Failed to persist rotor AUTO config to app settings: {save_err}")
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

            return self.resolve_rotor_target(req)

        except Exception as e:
            logger.error(f"Rotor bearing endpoint error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def resolve_rotor_target(self, req: Dict[str, Any]):
        """Resolve the best target and calculate SP/LP bearings without moving."""
        home_lat = getattr(config, 'ROTOR_HOME_LAT', 48.17)
        home_lon = getattr(config, 'ROTOR_HOME_LON', 17.08)
        rotor_bands = getattr(config, 'ROTOR_BANDS', {})
        return resolve_rotor_target(req, home_lat, home_lon, rotor_bands)

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

            resolution = self.resolve_rotor_target(req)
            if not resolution.get("ok"):
                return resolution

            if not resolution.get("band_enabled", True):
                resolution["ok"] = False
                return resolution

            if not resolution.get("auto_allowed", False):
                resolution["ok"] = False
                return resolution

            # Move rotor to bearing
            try:
                bearing = resolution["bearing"]
                result = await self.rotor.goto_azimuth(int(round(bearing)))
                self._status_cache = None
                self._status_cache_time = 0.0
                logger.info(
                    "✅ AUTO rotor: %s on %s -> %.1f° (%s)",
                    req.get('callsign') or req.get('call'),
                    resolution.get("band") or "unknown",
                    bearing,
                    resolution.get("source"),
                )

                resolution.update({
                    "ok": True,
                    "rotor": result,
                    "message": f"Rotor moving to {bearing:.1f}° ({resolution.get('source_label')})"
                })
                return resolution
            except Exception as rotor_error:
                logger.error(f"Rotor GOTO during AUTO failed: {rotor_error}")
                resolution["ok"] = False
                resolution["message"] = f"Rotor command failed: {rotor_error}"
                return resolution

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
