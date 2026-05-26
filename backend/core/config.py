"""
Compatibility wrappers for configuration endpoints.

The active application registers /api/config through backend.api.server_control.
This module remains available for older imports, but delegates persistence to the
JSON-backed settings store instead of editing radio_control/config.py.
"""

import logging
from typing import Any, Dict

from fastapi import FastAPI
from pydantic import BaseModel

from radio_control import config as cfg
from radio_control.settings_store import public_config_from_module, save_config_updates


logger = logging.getLogger(__name__)


class ConfigUpdate(BaseModel):
    """Configuration update model."""

    config: Dict[str, Any]


def get_config():
    """Get current configuration."""
    return {"success": True, "config": public_config_from_module(cfg)}


def update_config(config_update: ConfigUpdate):
    """Persist configuration updates through JSON settings files."""
    save_result = save_config_updates(config_update.config)

    for key in save_result["updated_keys"]:
        setattr(cfg, key, config_update.config[key])

    if save_result["rejected_keys"]:
        logger.warning("Rejected unsupported config keys: %s", save_result["rejected_keys"])

    return {
        "success": True,
        "message": "Configuration updated successfully",
        **save_result,
    }


def register_config_endpoints(app: FastAPI):
    """Register configuration endpoints with the FastAPI app."""

    @app.get("/api/config")
    async def api_get_config():
        return get_config()

    @app.post("/api/config")
    async def api_update_config(req: ConfigUpdate):
        return update_config(req)

    @app.get("/api/config/ft8")
    async def api_get_ft8_config():
        from backend.api.ft8 import get_ft8_config

        return await get_ft8_config()

    @app.post("/api/config/ft8")
    async def api_update_ft8_config(new_config: dict):
        from backend.api.ft8 import update_ft8_config

        return await update_ft8_config(new_config)
