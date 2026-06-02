"""
FlexRadio Web Control - Main Application
Clean orchestrator that imports and registers all modular components
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

# === Core Imports ===
from backend.core import (
    app,  # FastAPI app instance
    context,
    # Core functions
    _load_rotor_config,
    sync_app_state,
    sync_legacy_globals_from_context,
)

# === Service Imports ===
from services.database import get_db_connection as init_db_connection
from services.radio import register_radio_endpoints, set_radio_instance
from services.websocket import register_websocket_endpoint, broadcast_status, broadcast_spots
from services.background_tasks import (
    configure_background_tasks,
    start_background_tasks,
    stop_background_tasks,
    process_cluster_spot
)

# Import additional service modules for initialization
from services.qso_logging import init_qso_logging_clients, register_qso_logging_endpoints
from services.rotator import init_rotator_service
from services.wsjtx import get_wsjtx_service, register_wsjtx_endpoints
from services.country_data import load_country_data, router as country_data_router

# === API Router Imports ===
from backend.api.health import router as health_router
from backend.api.server_control import router as server_control_router
from backend.api.rotor import router as rotor_router, set_rotor_service
from backend.api.spots import router as spots_router
from backend.api.cluster import router as cluster_router
from backend.api.solar import router as solar_router
from backend.api.wavelog_log import router as wavelog_log_router
from backend.api.ft8 import router as ft8_router
from backend.api.static_files import setup_static_files
from activity_intelligence.api import router as activity_intelligence_router
from activity_intelligence.services import get_activity_intelligence_service

# === Additional Imports for Initialization ===
from radio_control.dxbridge import FlexCtl
from radio_control import config
from radio_control.cluster_client import ClusterClient
from radio_control.classifier_api import get_classifier_api
from radio_control.cty_resolvers import CtyDatResolver
from radio_control.wavelog_duckdb_sync import init_wavelog_sync
from radio_control.wavelog_api import WavelogClient
from radio_control.qrz_api import QRZClient
from radio_control.adif_handler import ADIFHandler

# === Compatibility aliases while routes migrate to context ===
wavelog_client = context.wavelog_client
qrz_client = context.qrz_client
adif_handler = context.adif_handler
wavelog_sync_manager = context.wavelog_sync_manager


def sync_runtime_state():
    """Synchronize compatibility globals and legacy app.state attributes."""
    global wavelog_client, qrz_client, adif_handler, wavelog_sync_manager

    wavelog_client = context.wavelog_client
    qrz_client = context.qrz_client
    adif_handler = context.adif_handler
    wavelog_sync_manager = context.wavelog_sync_manager
    sync_app_state(app, context)
    sync_legacy_globals_from_context()


# === Service Registration ===

def register_all_services():
    """Register all service endpoints and functionality"""

    # Register radio control endpoints
    register_radio_endpoints(app, context.flex, broadcast_status)

    # Register WebSocket endpoint
    context.websocket_manager = register_websocket_endpoint(
        app,
        context.flex,
        context.dx_spots_cache,
        context.websocket_clients,
    )
    sync_runtime_state()

    # Register QSO logging endpoints (Wavelog, QRZ, ADIF)
    register_qso_logging_endpoints(app)

    # Register WSJT-X endpoints
    register_wsjtx_endpoints(app)

    # Register API routers
    app.include_router(health_router)
    app.include_router(server_control_router)
    app.include_router(spots_router)
    app.include_router(country_data_router)
    app.include_router(cluster_router)
    app.include_router(solar_router)
    app.include_router(wavelog_log_router)
    app.include_router(ft8_router)
    app.include_router(activity_intelligence_router)
    
    # Register rotor router and set service instance
    from services.rotator import get_rotator_service
    set_rotor_service(get_rotator_service())
    app.include_router(rotor_router)

    # Setup static file serving
    setup_static_files(app)


# === Initialization Functions ===

def init_flex_radio():
    """Initialize FlexRadio connection"""
    try:
        host = getattr(config, 'FLEX_TCP_HOST', '192.168.1.100')
        port = getattr(config, 'FLEX_TCP_PORT', 4992)
        slice_id = getattr(config, 'FLEX_SLICE_ID', 0)

        logging.info(f"Initializing FlexCtl: {host}:{port}, slice {slice_id}")
        context.flex = FlexCtl(host, port, slice_id)

        if context.flex.connect():
            logging.info("✅ FlexRadio connected successfully")
            set_radio_instance(context.flex)  # Update radio service
            sync_runtime_state()
            return True
        else:
            logging.error("❌ FlexRadio connection failed")
            return False
    except Exception as e:
        logging.error(f"❌ FlexCtl initialization error: {e}")
        return False


def init_database():
    """Initialize database connection"""
    try:
        context.db_connection = init_db_connection()
        if context.db_connection:
            logging.info("✅ Database connection initialized")
            sync_runtime_state()
            return True
        else:
            logging.warning("⚠️ Database connection failed")
            return False
    except Exception as e:
        logging.error(f"❌ Database initialization error: {e}")
        return False


def init_cluster_client():
    """Initialize cluster client"""
    try:
        cluster_host = getattr(config, 'CLUSTER_HOST', 'localhost')
        cluster_port = getattr(config, 'CLUSTER_PORT', 7373)
        cluster_user = getattr(config, 'CLUSTER_USER', 'N0CALL')
        cluster_pass = getattr(config, 'CLUSTER_PASS', '')

        context.cluster_client = ClusterClient(cluster_host, cluster_port, cluster_user, cluster_pass)
        context.cluster_client.set_spot_callback(process_cluster_spot)

        # Start cluster in background
        asyncio.create_task(context.cluster_client.run())
        logging.info("✅ Cluster client started")
        sync_runtime_state()
        return True
    except Exception as e:
        logging.error(f"❌ Cluster client initialization failed: {e}")
        return False


def init_cty_resolver():
    """Initialize CTY resolver"""
    try:
        dat_path = getattr(config, 'CTY_DAT_PATH', None)
        csv_path = getattr(config, 'CTY_CSV_PATH', None)
        ignore_suffixes = getattr(config, 'CTY_IGNORE_SUFFIXES', [])
        context.cty_resolver = CtyDatResolver(
            dat_path,
            csv_path=csv_path,
            ignore_suffixes=ignore_suffixes,
        )
        logging.info("✅ CTY resolver loaded")
        sync_runtime_state()
        return True
    except Exception as e:
        logging.error(f"❌ CTY resolver failed: {e}")
        return False


async def init_classifier():
    """Initialize Wavelog API classifier"""
    try:
        context.classifier = await get_classifier_api(context.wavelog_client)
        logging.info("✅ API-based classifier initialized")
        sync_runtime_state()
        return True
    except Exception as e:
        logging.error(f"❌ Classifier initialization failed: {e}")
        return False


def init_wavelog_sync_manager():
    """Initialize the Wavelog→DuckDB read-cache sync manager."""
    try:
        context.wavelog_sync_manager = init_wavelog_sync()
        logging.info("✅ Wavelog→DuckDB read-cache sync initialized")
        sync_runtime_state()
        return True
    except Exception as e:
        logging.error(f"❌ Wavelog→DuckDB sync initialization failed: {e}")
        return False


# === Main Application Setup ===

async def initialize_services():
    """Initialize all services on startup"""
    logging.info("🚀 Starting FlexRadio Web Control Backend v2.0")

    # Load rotor configuration
    _load_rotor_config()

    # Initialize logging clients
    context.wavelog_client = WavelogClient()
    context.qrz_client = QRZClient()
    context.adif_handler = ADIFHandler()
    sync_runtime_state()

    # Initialize services
    init_database()
    init_flex_radio()
    init_cty_resolver()  # Initialize before QSO logging
    
    # Initialize QSO logging service with clients (after cty_resolver)
    init_qso_logging_clients(
        context.wavelog_client,
        context.qrz_client,
        context.adif_handler,
        context.cty_resolver,
    )
    
    await init_classifier()  # Async
    try:
        context.activity_intelligence = get_activity_intelligence_service()
        logging.info("✅ Activity Intelligence initialized")
    except Exception as e:
        logging.error(f"❌ Activity Intelligence initialization failed: {e}")
    context.background_task_service = configure_background_tasks(
        context,
        broadcast_status,
        broadcast_spots,
    )
    sync_runtime_state()

    init_cluster_client()
    init_wavelog_sync_manager()
    
    # Initialize rotator service (async)
    from services.rotator import get_rotator_service, init_rotator_service
    await init_rotator_service()

    # Set up WSJT-X service dependencies (including adif_handler for local ADIF backup)
    wsjtx_service = get_wsjtx_service()
    wsjtx_service.set_dependencies(
        context.wavelog_client,
        context.qrz_client,
        get_rotator_service(),
        context.cty_resolver,
        context.adif_handler,
    )

    sync_runtime_state()

    # Register all service endpoints and routers
    register_all_services()

    # Start background tasks
    await start_background_tasks()


async def cleanup_services():
    """Clean up services on shutdown"""
    logging.info("⏹️ Shutting down services...")

    # Stop background tasks
    await stop_background_tasks()

    # Close connections
    if context.wavelog_client:
        try:
            await context.wavelog_client.close_session()
            logging.info("✅ Wavelog HTTP session closed")
        except Exception as e:
            logging.error(f"❌ Error closing Wavelog session: {e}")

    if context.flex:
        try:
            context.flex.close()
            logging.info("✅ FlexRadio connection closed")
        except Exception as e:
            logging.error(f"❌ Error closing FlexRadio: {e}")


# === Application Lifespan ===

@asynccontextmanager
async def lifespan(_app):
    """Application startup/shutdown lifecycle."""
    await initialize_services()
    try:
        yield
    finally:
        await cleanup_services()


app.router.lifespan_context = lifespan


# === Main Entry Point ===

if __name__ == "__main__":
    import uvicorn

    # Start the server
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("BACKEND_PORT", "8080")),
        reload=True,
        log_level="info"
    )
