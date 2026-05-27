"""
Core FastAPI application wiring and shared runtime state.

Route handlers and background workers live in backend.api and services. This
module intentionally stays small so startup ownership remains clear.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from radio_control import config
from radio_control.settings_store import LEGACY_ROTOR_CONFIG_PATH, load_legacy_json, save_config_updates

from .context import AppContext, get_app_context, install_app_context, sync_app_state
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


app = FastAPI(title="OM0RX Radio Control", version="2.0.0")
context = AppContext()

CORS_ALLOWED_ORIGINS = list(getattr(config, "CORS_ALLOWED_ORIGINS", []))

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("CORS allowed origins: %s", CORS_ALLOWED_ORIGINS)
install_app_context(app, context)


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


flex = context.flex
websocket_clients = context.websocket_clients
dx_spots_cache = context.dx_spots_cache
db_connection = context.db_connection
cluster_client = context.cluster_client
cluster_connected = context.cluster_connected
classifier = context.classifier
cty_resolver = context.cty_resolver
wavelog_client = context.wavelog_client
qrz_client = context.qrz_client
adif_handler = context.adif_handler
wavelog_sync_manager = context.wavelog_sync_manager
rotor = context.rotor
sync_status = context.sync_status


def sync_legacy_globals_from_context():
    """Keep old backend.core module globals aligned while routes migrate."""
    global flex, db_connection, cluster_client, cluster_connected, classifier, cty_resolver
    global wavelog_client, qrz_client, adif_handler, wavelog_sync_manager, rotor

    flex = context.flex
    db_connection = context.db_connection
    cluster_client = context.cluster_client
    cluster_connected = context.cluster_connected
    classifier = context.classifier
    cty_resolver = context.cty_resolver
    wavelog_client = context.wavelog_client
    qrz_client = context.qrz_client
    adif_handler = context.adif_handler
    wavelog_sync_manager = context.wavelog_sync_manager
    rotor = context.rotor
    sync_app_state(app, context)


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
    "context",
    "AppContext",
    "get_app_context",
    "sync_app_state",
    "sync_legacy_globals_from_context",
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
