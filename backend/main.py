"""
FlexRadio Web Control - Main Application
Clean orchestrator that imports and registers all modular components
"""

import asyncio
import logging

# === Core Imports ===
from backend.core import (
    app,  # FastAPI app instance
    # Global state variables
    flex, websocket_clients, dx_spots_cache, db_connection,
    cluster_client, cluster_connected, classifier, cty_resolver,
    rotor, adif_sync_task, sync_status,
    # Core functions
    _load_rotor_config
)

# === Service Imports ===
from services.database import get_db_connection as init_db_connection
from services.radio import register_radio_endpoints, set_radio_instance, set_broadcast_function
from services.websocket import register_websocket_endpoint, broadcast_status, broadcast_spots
from services.background_tasks import (
    set_globals as set_background_globals,
    start_background_tasks,
    stop_background_tasks,
    process_cluster_spot
)

# Import additional service modules for initialization
from services.spots import get_spots_logger
from services.qso_logging import init_qso_logging_clients, register_qso_logging_endpoints
from services.adif import init_adif_service, register_adif_endpoints
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

# === Additional Imports for Initialization ===
from radio_control.dxbridge import FlexCtl
from radio_control import config
from radio_control.cluster_client import ClusterClient
from radio_control.classifier_api import get_classifier_api
from radio_control.cty_resolvers import CtyDatResolver
from radio_control.wavelog_duckdb_sync import init_wavelog_sync, periodic_wavelog_sync
from radio_control.rotor_api import RotorController
from radio_control.wavelog_api import WavelogClient
from radio_control.qrz_api import QRZClient
from radio_control.adif_handler import ADIFHandler

# === Module-level global variables ===
wavelog_client = None
qrz_client = None
adif_handler = None
wavelog_sync_manager = None


# === Service Registration ===

def register_all_services():
    """Register all service endpoints and functionality"""

    # Register radio control endpoints
    register_radio_endpoints(app, flex, broadcast_status)

    # Register WebSocket endpoint
    register_websocket_endpoint(app, flex, dx_spots_cache)

    # Register QSO logging endpoints (Wavelog, QRZ, ADIF)
    register_qso_logging_endpoints(app)

    # Register ADIF endpoints (QSO management and sync)
    register_adif_endpoints(app)

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
    
    # Register rotor router and set service instance
    from services.rotator import get_rotator_service
    set_rotor_service(get_rotator_service())
    app.include_router(rotor_router)

    # Setup static file serving
    setup_static_files(app)


# === Initialization Functions ===

def init_flex_radio():
    """Initialize FlexRadio connection"""
    global flex
    try:
        host = getattr(config, 'FLEX_TCP_HOST', '192.168.1.100')
        port = getattr(config, 'FLEX_TCP_PORT', 4992)
        slice_id = getattr(config, 'FLEX_SLICE_ID', 0)

        logging.info(f"Initializing FlexCtl: {host}:{port}, slice {slice_id}")
        flex = FlexCtl(host, port, slice_id)

        if flex.connect():
            logging.info("✅ FlexRadio connected successfully")
            set_radio_instance(flex)  # Update radio service
            return True
        else:
            logging.error("❌ FlexRadio connection failed")
            return False
    except Exception as e:
        logging.error(f"❌ FlexCtl initialization error: {e}")
        return False


def init_database():
    """Initialize database connection"""
    global db_connection
    try:
        db_connection = init_db_connection()
        if db_connection:
            logging.info("✅ Database connection initialized")
            return True
        else:
            logging.warning("⚠️ Database connection failed")
            return False
    except Exception as e:
        logging.error(f"❌ Database initialization error: {e}")
        return False


def init_cluster_client():
    """Initialize cluster client"""
    global cluster_client
    try:
        cluster_host = getattr(config, 'CLUSTER_HOST', 'localhost')
        cluster_port = getattr(config, 'CLUSTER_PORT', 7373)
        cluster_user = getattr(config, 'CLUSTER_USER', 'N0CALL')
        cluster_pass = getattr(config, 'CLUSTER_PASS', '')

        cluster_client = ClusterClient(cluster_host, cluster_port, cluster_user, cluster_pass)
        cluster_client.set_spot_callback(process_cluster_spot)

        # Start cluster in background
        asyncio.create_task(cluster_client.run())
        logging.info("✅ Cluster client started")
        return True
    except Exception as e:
        logging.error(f"❌ Cluster client initialization failed: {e}")
        return False


def init_cty_resolver():
    """Initialize CTY resolver"""
    global cty_resolver
    try:
        dat_path = getattr(config, 'CTY_DAT_PATH', None)
        csv_path = getattr(config, 'CTY_CSV_PATH', None)
        ignore_suffixes = getattr(config, 'CTY_IGNORE_SUFFIXES', [])
        cty_resolver = CtyDatResolver(dat_path, csv_path=csv_path, ignore_suffixes=ignore_suffixes)
        logging.info("✅ CTY resolver loaded")
        return True
    except Exception as e:
        logging.error(f"❌ CTY resolver failed: {e}")
        return False


async def init_classifier():
    """Initialize Wavelog API classifier"""
    global classifier
    try:
        # Initialize in both local scope AND in backend.core
        import backend.core
        classifier = await get_classifier_api(wavelog_client)
        backend.core.classifier = classifier  # Update the one in backend.core too!
        logging.info("✅ API-based classifier initialized")
        return True
    except Exception as e:
        logging.error(f"❌ Classifier initialization failed: {e}")
        return False


def init_rotator():
    """Initialize rotator controller"""
    global rotor
    try:
        rotor_enabled = getattr(config, 'ROTOR_ENABLED', False)
        if rotor_enabled:
            rotor_host = getattr(config, 'ROTOR_HOST', '192.168.0.198')
            rotor_port = getattr(config, 'ROTOR_PORT', 4001)
            rotor_protocol = getattr(config, 'ROTOR_PROTOCOL', 'DCU-1')
            rotor_timeout = getattr(config, 'ROTOR_TIMEOUT_SEC', 2.5)

            rotor = RotorController(rotor_host, rotor_port, rotor_protocol, rotor_timeout)
            logging.info(f"✅ Rotator initialized: {rotor_host}:{rotor_port} ({rotor_protocol})")
            return True
        else:
            logging.info("ℹ️ Rotator disabled in config")
            return True
    except Exception as e:
        logging.error(f"❌ Rotator initialization failed: {e}")
        return False


def init_wavelog_sync_manager():
    """Initialize Wavelog→DuckDB sync manager"""
    global wavelog_sync_manager, adif_sync_task
    import backend.core
    try:
        wavelog_sync_manager = init_wavelog_sync()
        # CRITICAL: Also set in backend.core namespace (used by periodic_wavelog_sync)
        backend.core.wavelog_sync_manager = wavelog_sync_manager
        logging.info("✅ Wavelog→DuckDB sync initialized")
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
    global wavelog_client, qrz_client, adif_handler, cty_resolver
    wavelog_client = WavelogClient()
    qrz_client = QRZClient()
    adif_handler = ADIFHandler()

    # Initialize services
    init_database()
    init_flex_radio()
    init_cty_resolver()  # Initialize before QSO logging
    
    # Initialize QSO logging service with clients (after cty_resolver)
    init_qso_logging_clients(wavelog_client, qrz_client, adif_handler, cty_resolver)
    
    await init_classifier()  # Async
    init_cluster_client()
    init_rotator()
    init_wavelog_sync_manager()
    
    # Initialize rotator service (async)
    from services.rotator import init_rotator_service
    await init_rotator_service()

    # Set up WSJT-X service dependencies (including adif_handler for local ADIF backup)
    wsjtx_service = get_wsjtx_service()
    wsjtx_service.set_dependencies(wavelog_client, qrz_client, rotor, cty_resolver, adif_handler)

    # Set up background task globals
    set_background_globals(
        flex, websocket_clients, dx_spots_cache, cluster_client, cluster_connected,
        cty_resolver, classifier, wavelog_sync_manager, sync_status,
        broadcast_status, broadcast_spots
    )

    # Set app state for API endpoints
    app.state.flex = flex
    app.state.sync_status = sync_status
    app.state.dx_spots_cache = dx_spots_cache
    app.state.websocket_clients = websocket_clients
    app.state.cluster_client = cluster_client

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
    if wavelog_client:
        try:
            await wavelog_client.close_session()
            logging.info("✅ Wavelog HTTP session closed")
        except Exception as e:
            logging.error(f"❌ Error closing Wavelog session: {e}")

    if flex:
        try:
            flex.close()
            logging.info("✅ FlexRadio connection closed")
        except Exception as e:
            logging.error(f"❌ Error closing FlexRadio: {e}")


# === Application Event Handlers ===

@app.on_event("startup")
async def on_startup():
    """Application startup event"""
    await initialize_services()


@app.on_event("shutdown")
async def on_shutdown():
    """Application shutdown event"""
    await cleanup_services()


# === Main Entry Point ===

if __name__ == "__main__":
    import uvicorn

    # Register all services
    register_all_services()

    # Start the server
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
