"""
Core FastAPI application wiring and shared runtime state.

Route handlers and background workers live in backend.api and services. This
module intentionally stays small so startup ownership remains clear.
"""

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from radio_control import config
from radio_control.adif_handler import ADIFHandler
from radio_control.classifier_api import ClassifierAPI
from radio_control.cluster_client import ClusterManager
from radio_control.cty_resolvers import CtyDatResolver
from radio_control.dxbridge import FlexCtl
from radio_control.qrz_api import QRZClient
from radio_control.rotor_api import RotorController
from radio_control.settings_store import LEGACY_ROTOR_CONFIG_PATH, load_legacy_json, save_config_updates
from radio_control.wavelog_api import WavelogClient

from .models import (
    AGCRequest,
    BandRequest,
    ConfigUpdate,
    DSPLevelRequest,
    DSPRequest,
    FilterRequest,
    FrequencyRequest,
    ModeRequest,
    QSORequest,
    RITXITRequest,
    RX2Request,
    RecentQSOsRequest,
    RotorAutoConfigRequest,
    RotorAutoModeRequest,
    RotorBearingRequest,
    RotorConfigRequest,
    RotorDirectionRequest,
    RotorGotoRequest,
    SliderRequest,
    SplitRequest,
    SpotAddRequest,
    SpotTuneRequest,
    ToggleRequest,
    WSJTXAutoRotateRequest,
    WSJTXQSORequest,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(title="FlexRadio Web Control", version="2.0.0")

CORS_ALLOWED_ORIGINS = list(getattr(config, "CORS_ALLOWED_ORIGINS", []))

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("CORS allowed origins: %s", CORS_ALLOWED_ORIGINS)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log detailed validation errors for backend/API contract debugging."""
    logger.error("Validation error on %s", request.url.path)
    logger.error("Errors: %s", exc.errors())
    logger.error("Body: %s", await request.body())

    return {
        "success": False,
        "detail": "Request validation failed",
        "errors": exc.errors(),
    }


flex: Optional[FlexCtl] = None
websocket_clients: List[WebSocket] = []
dx_spots_cache: List[Dict] = []
db_connection = None
cluster_client: Optional[ClusterManager] = None
cluster_connected = False
classifier: Optional[ClassifierAPI] = None
cty_resolver: Optional[CtyDatResolver] = None
wavelog_client: Optional[WavelogClient] = None
qrz_client: Optional[QRZClient] = None
adif_handler: Optional[ADIFHandler] = None
wavelog_sync_manager = None
rotor: Optional[RotorController] = None
adif_sync_task: Optional[asyncio.Task] = None

sync_status = {
    "syncing": False,
    "last_sync": None,
    "total_records": 0,
    "new_records_this_sync": 0,
    "records_updated": 0,
    "next_sync_in": 0,
}


def _load_rotor_config():
    """Migrate legacy rotor settings if an old rotor_config.json is still present."""
    rotor_data = load_legacy_json(LEGACY_ROTOR_CONFIG_PATH)
    if not rotor_data:
        return

    save_result = save_config_updates(rotor_data)
    for key in save_result["updated_keys"]:
        setattr(config, key, rotor_data[key])

    logger.info(
        "Migrated legacy rotor_config.json keys to app settings: %s",
        save_result["updated_keys"],
    )


__all__ = [
    "app",
    "validation_exception_handler",
    "flex",
    "websocket_clients",
    "dx_spots_cache",
    "db_connection",
    "cluster_client",
    "cluster_connected",
    "classifier",
    "cty_resolver",
    "wavelog_client",
    "qrz_client",
    "adif_handler",
    "wavelog_sync_manager",
    "rotor",
    "adif_sync_task",
    "sync_status",
    "_load_rotor_config",
    "AGCRequest",
    "BandRequest",
    "ConfigUpdate",
    "DSPLevelRequest",
    "DSPRequest",
    "FilterRequest",
    "FrequencyRequest",
    "ModeRequest",
    "QSORequest",
    "RITXITRequest",
    "RX2Request",
    "RecentQSOsRequest",
    "RotorAutoConfigRequest",
    "RotorAutoModeRequest",
    "RotorBearingRequest",
    "RotorConfigRequest",
    "RotorDirectionRequest",
    "RotorGotoRequest",
    "SliderRequest",
    "SplitRequest",
    "SpotAddRequest",
    "SpotTuneRequest",
    "ToggleRequest",
    "WSJTXAutoRotateRequest",
    "WSJTXQSORequest",
]
