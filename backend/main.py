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
from services.radio import (
    configure_station_route_handler,
    configure_station_tx_guard,
    register_radio_endpoints,
    set_radio_instance,
)
from services.websocket import register_websocket_endpoint, broadcast_status, broadcast_spots
from services.background_tasks import (
    configure_background_tasks,
    start_background_tasks,
    stop_background_tasks,
    process_cluster_spot
)

# Import additional service modules for initialization
from services.qso_logging import init_qso_logging_clients, register_qso_logging_endpoints
from services.wsjtx import get_wsjtx_service, register_wsjtx_endpoints
from services.country_data import router as country_data_router

# === API Router Imports ===
from backend.api.health import router as health_router
from backend.api.server_control import router as server_control_router
from backend.api.rotor import router as rotor_router, set_rotor_service
from backend.api.spots import router as spots_router
from backend.api.cluster import router as cluster_router
from backend.api.solar import router as solar_router
from backend.api.wavelog_log import router as wavelog_log_router
from backend.api.ft8 import router as ft8_router
from backend.api.elecraft import router as elecraft_router
from backend.api.station import router as station_router
from backend.api.static_files import setup_static_files
from activity_intelligence.api import router as activity_intelligence_router
from activity_intelligence.services import get_activity_intelligence_service

# === Additional Imports for Initialization ===
from radio_control.flex_radio import FlexCtl
from radio_control import config
from radio_control.cluster_client import ClusterClient, ClusterManager
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

_services_registered = False

def register_all_services():
    """Register all service endpoints and functionality"""
    global _services_registered
    if _services_registered:
        return

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
    app.include_router(elecraft_router)
    app.include_router(station_router)
    app.include_router(activity_intelligence_router)
    
    # Register rotor router and set service instance
    from services.rotator import get_rotator_service
    set_rotor_service(get_rotator_service())
    app.include_router(rotor_router)

    # Setup static file serving
    setup_static_files(app)
    _services_registered = True


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
        clusters = [item for item in getattr(config, 'CLUSTERS', []) if item.get('enabled', False)]
        if clusters:
            context.cluster_client = ClusterManager(clusters)
        else:
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


async def warm_qso_status_cache():
    """Load the hot worked/confirmed sets without blocking application startup."""
    try:
        store = getattr(context.classifier, "qso_status_store", None) if context.classifier else None
        if not store or not hasattr(store, "diagnostics"):
            logging.info("WSJT-Z QSO status cache warmup skipped: no status store")
            return
        diagnostics = await asyncio.to_thread(store.diagnostics)
        if diagnostics.get("loaded"):
            logging.info(
                "✅ WSJT-Z QSO status cache warmed: calls=%s dxcc=%s",
                diagnostics.get("call_worked_count", 0),
                diagnostics.get("dxcc_worked_count", 0),
            )
        else:
            logging.warning("WSJT-Z QSO status cache warmup did not load: %s", diagnostics)
    except Exception as e:
        logging.error(f"❌ WSJT-Z QSO status cache warmup failed: {e}")


async def init_wavelog_sync_manager_background():
    """Initialize Wavelog sync after the API is allowed to start serving."""
    try:
        manager = await asyncio.to_thread(init_wavelog_sync)
        context.wavelog_sync_manager = manager
        logging.info("✅ Wavelog local read-cache sync initialized")
        sync_runtime_state()

        if context.background_task_service:
            from radio_control.wavelog_duckdb_sync import periodic_wavelog_sync

            async def delayed_periodic_wavelog_sync():
                await asyncio.sleep(180)
                await periodic_wavelog_sync()

            wavelog_task = asyncio.create_task(
                delayed_periodic_wavelog_sync(),
                name="periodic_wavelog_sync",
            )
            context.background_task_service.tasks.append(wavelog_task)
            logging.info("✅ Wavelog local read-cache periodic sync task scheduled")
    except Exception as e:
        logging.error(f"❌ Wavelog local sync initialization failed: {e}")


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

    # These independent startup probes are all blocking (database connect,
    # radio TCP connect, and CTY file parsing). Running them serially delayed
    # the first HTTP response by the sum of their timeouts.
    await asyncio.gather(
        asyncio.to_thread(init_database),
        asyncio.to_thread(init_flex_radio),
        asyncio.to_thread(init_cty_resolver),
    )
    sync_runtime_state()
    
    await init_classifier()  # Async
    # Initialize QSO logging service with clients and the hot worked/needed cache.
    init_qso_logging_clients(
        context.wavelog_client,
        context.qrz_client,
        context.adif_handler,
        context.cty_resolver,
        getattr(context.classifier, "qso_status_store", None) if context.classifier else None,
    )
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
    if context.background_task_service:
        context.background_task_service.tasks.append(
            asyncio.create_task(warm_qso_status_cache(), name="warm_qso_status_cache")
        )
    sync_runtime_state()

    init_cluster_client()
    if context.background_task_service:
        context.background_task_service.tasks.append(
            asyncio.create_task(
                init_wavelog_sync_manager_background(),
                name="init_wavelog_sync_manager",
            )
        )
    
    # Initialize rotator service (async)
    from services.rotator import get_rotator_service, init_rotator_service
    await init_rotator_service()

    # Initialize KPA500/KAT500 before radio polling begins so the first
    # authoritative Flex snapshot can immediately select their band/frequency.
    from radio_control.elecraft import get_elecraft_manager
    from radio_control.station_telemetry_store import StationTelemetryStore
    from services.elecraft_station import StationCoordinator
    from services.station_training_jobs import TrainingJobManager

    context.elecraft = get_elecraft_manager()
    context.station_telemetry = StationTelemetryStore()
    _, schema_result = await asyncio.gather(
        context.elecraft.start(),
        asyncio.to_thread(context.station_telemetry.ensure_schema),
    )
    if not schema_result.persisted:
        logging.warning("Station telemetry is degraded: %s", schema_result.reason)
    context.station_coordinator = StationCoordinator(
        context.elecraft,
        lambda: context.flex,
        lambda: context.radio_snapshot,
        telemetry=context.station_telemetry,
        recovery_required=True,
    )
    context.station_training_manager = TrainingJobManager(context.station_coordinator)
    try:
        await context.station_coordinator.recover_safe_state()
        logging.info("✅ Station startup recovery confirmed FLEX RX and KPA500 standby")
    except Exception as exc:
        logging.critical("Station controls locked: startup safe state is unconfirmed: %s", exc)
    configure_station_tx_guard(
        context.station_coordinator.execute_raw_flex_tx
    )
    configure_station_route_handler(
        context.station_coordinator.execute_flex_route_change
    )
    context.station_telemetry_task = asyncio.create_task(
        context.station_coordinator.telemetry_loop(),
        name="station_telemetry",
    )
    if context.background_task_service:
        context.background_task_service.tasks.append(context.station_telemetry_task)

    # Set up WSJT-X service dependencies (including adif_handler for local ADIF backup)
    wsjtx_service = get_wsjtx_service()
    wsjtx_service.set_dependencies(
        context.wavelog_client,
        context.qrz_client,
        get_rotator_service(),
        context.cty_resolver,
        context.adif_handler,
        getattr(context.classifier, "qso_status_store", None) if context.classifier else None,
    )

    # A service restart must never replay a persisted target or re-arm TX.
    # This runs before the automation/background loops are created; the
    # operator must explicitly enable automation again for the current session.
    from services.digital_engine import get_digital_engine_service
    startup_disarm = get_digital_engine_service().disarm_planner(
        "backend-startup-disarmed"
    )
    logging.info("Digital planner startup safety latch: %s", startup_disarm)

    sync_runtime_state()

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

    if context.station_training_manager:
        try:
            await context.station_training_manager.stop()
            logging.info("✅ Station training manager stopped")
        except Exception as e:
            logging.error(f"❌ Error stopping station training manager: {e}")

    if context.station_coordinator:
        try:
            await context.station_coordinator.stop()
            logging.info("✅ Station coordinator stopped")
        except Exception as e:
            logging.error(f"❌ Error stopping station coordinator: {e}")

    if context.flex:
        try:
            context.flex.close()
            logging.info("✅ FlexRadio connection closed")
        except Exception as e:
            logging.error(f"❌ Error closing FlexRadio: {e}")
    configure_station_tx_guard(None)
    configure_station_route_handler(None)

    if context.elecraft:
        try:
            await context.elecraft.stop()
            logging.info("✅ Elecraft connections closed")
        except Exception as e:
            logging.error(f"❌ Error closing Elecraft connections: {e}")


# === Application Lifespan ===

@asynccontextmanager
async def lifespan(_app):
    """Application startup/shutdown lifecycle."""
    digital_service = None
    try:
        await initialize_services()
        from services.digital_engine import get_digital_engine_service

        digital_service = get_digital_engine_service()
        digital_service.ensure_watchdog()
        yield
    finally:
        if digital_service and digital_service.watchdog_task:
            digital_service.watchdog_task.cancel()
            await asyncio.gather(digital_service.watchdog_task, return_exceptions=True)
        await cleanup_services()


register_all_services()
app.router.lifespan_context = lifespan


# === Main Entry Point ===

if __name__ == "__main__":
    import uvicorn

    # Start the server
    uvicorn.run(
        "backend.main:app",
        host=str(os.environ.get("BACKEND_HOST", getattr(config, "BACKEND_HOST", "127.0.0.1"))),
        port=int(os.environ.get("BACKEND_PORT", str(getattr(config, "BACKEND_PORT", 8080)))),
        reload=str(os.environ.get("APP_UVICORN_RELOAD", "0")).strip().lower() in {"1", "true", "yes", "on"},
        log_level="info"
    )
