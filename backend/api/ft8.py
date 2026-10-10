"""
FT8/FT4 API Endpoints
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Optional
import logging
import asyncio
from radio_control import config as app_config
from radio_control.settings_store import (
    LEGACY_FT8_CONFIG_PATH,
    load_app_settings,
    load_legacy_json,
    save_config_updates,
)

from services.ft8_service import get_ft8_service, init_ft8_service
from services.sounddevice_loader import get_sounddevice, sounddevice_unavailable_reason
from services.soundcard_loader import get_soundcard, soundcard_unavailable_reason

logger = logging.getLogger(__name__)

def require_ft8_mutation_owner(request: Request):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        from services.digital_engine import require_om0rx_planner
        require_om0rx_planner()


router = APIRouter(prefix="/api/ft8", tags=["ft8"], dependencies=[Depends(require_ft8_mutation_owner)])

# Historical route namespace: these endpoints now power the built-in DIGITAL
# client. They are mode-aware through FT8Service/normalise_decode_mode and are
# used for both FT8 and FT4 automation.
#
# The older free-form TX routes (/transmit, /reply, /send73) are disabled by
# default because they do not carry attempt ids. Enable the compatibility flag
# only for external tooling that has been audited against the backend owner.


def _legacy_tx_routes_enabled() -> bool:
    return bool(getattr(app_config, "FT8_LEGACY_TX_ROUTES_ENABLED", False))


def _raise_legacy_tx_disabled(route: str) -> None:
    raise HTTPException(
        status_code=410,
        detail=(
            f"{route} is deprecated and disabled. Use /api/ft8/automation/engage "
            "or /api/ft8/tx/manual so DIGITAL TX remains owned by the backend "
            "attempt state machine."
        ),
    )

# === Request/Response Models ===

class FT8Config(BaseModel):
    """FT8 configuration"""
    mode: str = 'FT8'  # 'FT8' or 'FT4'
    mycall: str
    mygrid: str
    auto_sequence: bool = False
    tx_enabled: bool = False
    networkServer: Optional[str] = '192.168.0.199:4992'
    rigBackend: Optional[str] = 'auto'
    hamlibRigctlPath: Optional[str] = None
    hamlibModel: Optional[int] = None
    hamlibRigPath: Optional[str] = None
    hamlibTimeoutSeconds: Optional[float] = None
    pttMethod: Optional[str] = 'CAT'
    audioInput: Optional[str] = 'default'
    audioOutput: Optional[str] = 'default'
    sampleRate: Optional[int] = 12000
    waterfallHeight: Optional[int] = 100
    waterfallEnabled: Optional[bool] = True
    useFlexRadioAudio: Optional[bool] = True
    operatorSettings: Optional[dict[str, Any]] = None


FT8_FIELD_TO_CONFIG_KEY = {
    "mode": "FT8_MODE",
    "mycall": "FT8_MYCALL",
    "mygrid": "FT8_MYGRID",
    "auto_sequence": "FT8_AUTO_SEQUENCE",
    "tx_enabled": "FT8_TX_ENABLED",
    "networkServer": "FT8_NETWORK_SERVER",
    "rigBackend": "FT8_RIG_BACKEND",
    "hamlibRigctlPath": "FT8_HAMLIB_RIGCTL_PATH",
    "hamlibModel": "FT8_HAMLIB_MODEL",
    "hamlibRigPath": "FT8_HAMLIB_RIG_PATH",
    "hamlibTimeoutSeconds": "FT8_HAMLIB_TIMEOUT_SECONDS",
    "pttMethod": "FT8_PTT_METHOD",
    "audioInput": "FT8_AUDIO_INPUT",
    "audioOutput": "FT8_AUDIO_OUTPUT",
    "sampleRate": "FT8_SAMPLE_RATE",
    "waterfallHeight": "FT8_WATERFALL_HEIGHT",
    "waterfallEnabled": "FT8_WATERFALL_ENABLED",
    "useFlexRadioAudio": "FT8_USE_FLEXRADIO_AUDIO",
    "operatorSettings": "FT8_OPERATOR_SETTINGS",
}

CONFIG_KEY_TO_FT8_FIELD = {value: key for key, value in FT8_FIELD_TO_CONFIG_KEY.items()}


def _ft8_defaults():
    return {
        "mode": getattr(app_config, "FT8_MODE", "FT8"),
        "mycall": getattr(app_config, "FT8_MYCALL", "OM0RX"),
        "mygrid": getattr(app_config, "FT8_MYGRID", "JN88"),
        "auto_sequence": getattr(app_config, "FT8_AUTO_SEQUENCE", False),
        "tx_enabled": getattr(app_config, "FT8_TX_ENABLED", False),
        "networkServer": getattr(app_config, "FT8_NETWORK_SERVER", "192.168.0.199:4992"),
        "rigBackend": getattr(app_config, "FT8_RIG_BACKEND", "auto"),
        "hamlibRigctlPath": getattr(app_config, "FT8_HAMLIB_RIGCTL_PATH", ""),
        "hamlibModel": getattr(app_config, "FT8_HAMLIB_MODEL", 23005),
        "hamlibRigPath": getattr(app_config, "FT8_HAMLIB_RIG_PATH", ""),
        "hamlibTimeoutSeconds": getattr(app_config, "FT8_HAMLIB_TIMEOUT_SECONDS", 3.0),
        "pttMethod": getattr(app_config, "FT8_PTT_METHOD", "CAT"),
        "audioInput": getattr(app_config, "FT8_AUDIO_INPUT", "default"),
        "audioOutput": getattr(app_config, "FT8_AUDIO_OUTPUT", "default"),
        "sampleRate": getattr(app_config, "FT8_SAMPLE_RATE", 12000),
        "waterfallHeight": getattr(app_config, "FT8_WATERFALL_HEIGHT", 100),
        "waterfallEnabled": getattr(app_config, "FT8_WATERFALL_ENABLED", True),
        "useFlexRadioAudio": getattr(app_config, "FT8_USE_FLEXRADIO_AUDIO", True),
        "operatorSettings": getattr(app_config, "FT8_OPERATOR_SETTINGS", {}),
    }


def _config_to_ft8_payload(config_values: dict):
    payload = _ft8_defaults()
    for config_key, value in config_values.items():
        field = CONFIG_KEY_TO_FT8_FIELD.get(config_key)
        if field:
            payload[field] = value
    return payload


def _ft8_payload_to_config(payload: dict):
    return {
        config_key: payload[field]
        for field, config_key in FT8_FIELD_TO_CONFIG_KEY.items()
        if field in payload
    }


def _normalise_audio_config(config: FT8Config) -> FT8Config:
    """Prefer Flex DAX when the Digital config asks to use FlexRadio audio."""
    if not bool(config.useFlexRadioAudio):
        return config

    updates: dict[str, Any] = {}
    if not config.audioInput or str(config.audioInput).strip().lower().startswith("default"):
        updates["audioInput"] = "flexradio"
    if not config.audioOutput or str(config.audioOutput).strip().lower().startswith("default"):
        updates["audioOutput"] = "flexradio"
    if not config.sampleRate or int(config.sampleRate or 0) < 48000:
        updates["sampleRate"] = 48000
    if updates:
        config = config.model_copy(update=updates)
    return config


def _host_from_server(server: str | None) -> str:
    value = str(server or "").strip()
    if not value:
        return ""
    if value.startswith("[") and "]" in value:
        return value[1:value.index("]")]
    return value.rsplit(":", 1)[0] if ":" in value else value


def _build_digital_ptt_device(config: FT8Config):
    if str(config.pttMethod or "CAT").upper() != "CAT":
        return None
    backend = str(config.rigBackend or "auto").strip().lower()
    if backend in {"", "auto", "direct", "flex", "smartsdr"}:
        if backend == "auto":
            logger.info("Using direct Flex DIGITAL PTT backend in auto mode")
        return None
    if backend not in {"hamlib", "rigctl"}:
        logger.warning("Unknown FT8 rig backend %r; using direct Flex CAT fallback", config.rigBackend)
        return None

    from radio_control.hamlib_rig import create_hamlib_rig

    model = config.hamlibModel or getattr(app_config, "FT8_HAMLIB_MODEL", 23005)
    rig_path = str(config.hamlibRigPath or getattr(app_config, "FT8_HAMLIB_RIG_PATH", "") or "").strip()
    if not rig_path:
        network_host = _host_from_server(config.networkServer)
        if int(model or 0) in range(23005, 23013) and network_host in {"127.0.0.1", "localhost", "::1"}:
            rig_path = str(getattr(app_config, "FLEX_TCP_HOST", "") or "").strip()
        else:
            rig_path = str(config.networkServer or "").strip()
    device = create_hamlib_rig(
        rigctl_path=config.hamlibRigctlPath or getattr(app_config, "FT8_HAMLIB_RIGCTL_PATH", ""),
        model=model,
        rig_path=rig_path,
        timeout_seconds=float(config.hamlibTimeoutSeconds or getattr(app_config, "FT8_HAMLIB_TIMEOUT_SECONDS", 3.0) or 3.0),
    )
    if device is not None:
        logger.info("Using Hamlib DIGITAL PTT backend: model=%s rig_path=%s", model, rig_path)
    elif backend in {"hamlib", "rigctl"}:
        raise RuntimeError("Hamlib DIGITAL PTT backend was requested but rigctl or rig path is not available")
    return device


def _load_legacy_ft8_config():
    legacy_data = load_legacy_json(LEGACY_FT8_CONFIG_PATH)
    if not legacy_data:
        return {}

    config_updates = _ft8_payload_to_config(legacy_data)
    if config_updates:
        save_config_updates(config_updates)
        for key, value in config_updates.items():
            setattr(app_config, key, value)
        logger.info("Migrated legacy FT8 config keys to app settings: %s", sorted(config_updates))

    return legacy_data


async def _enrich_automation_target(target: dict[str, Any], request: Request) -> dict[str, Any]:
    """Fill missing target CTY/Wavelog status before it enters automation state."""
    enriched = dict(target or {})
    callsign = str(enriched.get("callsign") or enriched.get("call") or "").strip().upper()
    if not callsign:
        return enriched
    enriched["callsign"] = callsign

    call_status = str(enriched.get("call_status") or enriched.get("callStatus") or "").strip()
    dxcc_status = str(enriched.get("dxcc_status") or enriched.get("dxccStatus") or "").strip()
    has_status = call_status and call_status.lower() != "unknown" and dxcc_status and dxcc_status.lower() != "unknown"

    try:
        from radio_control.spot_processor import band_from_khz
        from radio_control.spot_classification import classify_call_status, classify_dxcc_status
        from services.digital_status import call_status_from_recent_qsos

        frequency_value = enriched.get("frequency_khz") or enriched.get("frequency") or enriched.get("frequency_mhz") or 0
        try:
            frequency = float(frequency_value or 0)
        except (TypeError, ValueError):
            frequency = 0
        frequency_khz = frequency * 1000 if 0 < frequency < 1000 else frequency
        band = enriched.get("band") or (band_from_khz(frequency_khz) if frequency_khz else None)
        mode = str(enriched.get("mode") or "FT8").upper()
        if band:
            enriched["band"] = band
        enriched["mode"] = mode

        cty_resolver = getattr(request.app.state, "cty_resolver", None)
        cty_info = cty_resolver.lookup(callsign) if cty_resolver else {}
        if cty_info:
            enriched.setdefault("country", cty_info.get("entity") or cty_info.get("country") or "")
            enriched.setdefault("dxcc", cty_info.get("dxcc"))
            enriched.setdefault("continent", cty_info.get("continent") or cty_info.get("cont") or "")
            enriched.setdefault("cq_zone", cty_info.get("cq") or cty_info.get("cq_zone") or "")
            enriched.setdefault("itu_zone", cty_info.get("itu") or cty_info.get("itu_zone") or "")

        classifier = getattr(request.app.state, "classifier", None)
        if not classifier:
            return enriched

        if not has_status:
            source = str(enriched.get("source") or "").strip().lower()
            qso_status_store = getattr(classifier, "qso_status_store", None)
            local_call_flags = None
            if qso_status_store and hasattr(qso_status_store, "call_flags"):
                local_call_flags = await asyncio.to_thread(qso_status_store.call_flags, callsign, band, mode)
            if local_call_flags is not None:
                call_worked, call_confirmed, call_new_band, call_new_mode, call_bandmode_confirmed = local_call_flags
            else:
                call_worked, call_confirmed, call_new_band, call_new_mode, call_bandmode_confirmed = (
                    await classifier.call_status_flags(callsign, band, mode)
                )
            needed = dict(enriched.get("needed") or {})
            needed_on_band = dict(enriched.get("needed_on_band") or enriched.get("neededOnBand") or {})
            needed["call"] = bool(needed.get("call") or not call_worked)
            needed_on_band["call"] = bool(needed_on_band.get("call") or call_new_band)
            needed_on_band["mode"] = bool(needed_on_band.get("mode") or call_new_mode)
            enriched["needed"] = needed
            enriched["needed_on_band"] = needed_on_band
            enriched["call_status"] = classify_call_status(
                call_worked,
                call_new_band,
                call_new_mode,
                call_bandmode_confirmed,
            )
            recent_call_status = None
            if source != "decoded":
                recent_call_status = await call_status_from_recent_qsos(callsign, band, mode)
            if recent_call_status:
                enriched["call_status"] = recent_call_status

            dxcc = enriched.get("dxcc") or cty_info.get("dxcc")
            if dxcc is not None:
                if source == "decoded" and qso_status_store:
                    dxcc_overall = await asyncio.to_thread(qso_status_store.dxcc_overall, dxcc)
                    dxcc_bandmode = await asyncio.to_thread(qso_status_store.dxcc_bandmode_flags, dxcc, band, mode)
                else:
                    dxcc_overall = await classifier.dxcc_overall(
                        dxcc,
                        callsign=callsign,
                        allow_unconfirmed_fallback=False,
                    )
                    dxcc_bandmode = await classifier.dxcc_bandmode_flags(
                        dxcc,
                        band,
                        mode,
                        callsign=callsign,
                        allow_unconfirmed_fallback=False,
                    )
                if dxcc_overall is not None and dxcc_bandmode is not None:
                    dxcc_worked, dxcc_confirmed = dxcc_overall
                    dxcc_new_band, dxcc_new_mode, dxcc_bandmode_confirmed = dxcc_bandmode
                    dxcc_display = classify_dxcc_status(
                        dxcc_worked,
                        dxcc_confirmed,
                        dxcc_new_band,
                        dxcc_new_mode,
                        dxcc_bandmode_confirmed,
                    )
                    enriched["dxcc_status"] = dxcc_display.status
                    enriched["dxcc_tag"] = dxcc_display.tag
                else:
                    enriched.setdefault("dxcc_status", "Unknown")

        grid = str(enriched.get("grid") or enriched.get("gridsquare") or "").strip().upper()
        if grid and hasattr(classifier, "grid_flags"):
            grid_flags = await classifier.grid_flags(grid, band or "", mode)
            if grid_flags is not None:
                new_grid, new_grid_band, new_grid_mode = grid_flags
                needed = dict(enriched.get("needed") or {})
                needed_on_band = dict(enriched.get("needed_on_band") or enriched.get("neededOnBand") or {})
                needed["grid"] = bool(needed.get("grid") or new_grid)
                needed_on_band["grid"] = bool(needed_on_band.get("grid") or new_grid_band or new_grid_mode)
                enriched["needed"] = needed
                enriched["needed_on_band"] = needed_on_band
    except Exception as exc:
        logger.debug("Unable to enrich automation target %s: %s", callsign, exc, exc_info=True)
    return enriched


def _configure_automation_status_sources(service: Any, request: Request) -> None:
    """Give the automation controller fast local status sources from app state."""
    classifier = getattr(request.app.state, "classifier", None)
    qso_status_store = getattr(classifier, "qso_status_store", None) if classifier else None
    cty_resolver = getattr(request.app.state, "cty_resolver", None)
    controller = getattr(service, "automation_controller", None)
    if controller and hasattr(controller, "set_status_sources"):
        controller.set_status_sources(
            qso_status_store=qso_status_store,
            cty_resolver=cty_resolver,
        )


class TransmitRequest(BaseModel):
    """TX message request"""
    message: str
    tx_audio_frequency: Optional[int] = 1500
    tx_even_first: Optional[bool] = True
    watchdog_ft8: Optional[int] = 2
    watchdog_ft4: Optional[int] = 2
    watchdog_enabled: Optional[bool] = True
    auto_cq: Optional[bool] = False
    auto_call: Optional[bool] = False
    cq_only: Optional[bool] = False
    auto_cq_limit: Optional[int] = None
    auto_call_limit: Optional[int] = None
    replace: Optional[bool] = False
    abandon: Optional[bool] = False
    immediate: Optional[bool] = False
    specialActivity: Optional[dict[str, Any]] = None


class ReplyRequest(BaseModel):
    """Reply to call request"""
    their_call: str
    report: str = "R-15"


class TxControlRequest(BaseModel):
    tx_audio_frequency: Optional[int] = 1500
    tx_even_first: Optional[bool] = True
    watchdog_ft8: Optional[int] = 2
    watchdog_ft4: Optional[int] = 2
    watchdog_enabled: Optional[bool] = True
    auto_cq: Optional[bool] = False
    auto_call: Optional[bool] = False
    cq_only: Optional[bool] = False
    auto_cq_limit: Optional[int] = 5
    auto_call_limit: Optional[int] = 5
    immediate: Optional[bool] = False
    specialActivity: Optional[dict[str, Any]] = None


class ManualTxRequest(BaseModel):
    tx_id: int
    immediate: Optional[bool] = False


class TuneToneRequest(BaseModel):
    tx_audio_frequency: Optional[int] = 1500
    duration_seconds: Optional[float] = 5.0


class AutomationSettingsRequest(BaseModel):
    operatorSettings: dict[str, Any]


class ReferenceHunterSettingsRequest(BaseModel):
    enabled: bool
    programs: list[str] = Field(default_factory=lambda: ["POTA", "SOTA", "IOTA", "WWFF", "WWBOTA", "ARLHS"])
    min_spot_score: int = Field(default=50, ge=0, le=100)
    hunt_watchdog_minutes: int = Field(default=5, ge=1, le=60)
    restore_watchdog_minutes: int = Field(default=2, ge=1, le=60)
    spot_filters: dict[str, Any] = Field(default_factory=dict)


class AutomationTargetRequest(BaseModel):
    target: dict[str, Any]


class AutomationTargetsRequest(BaseModel):
    targets: list[dict[str, Any]] = Field(default_factory=list)
    limit: int = Field(default=25, ge=1, le=100)
    source: Optional[str] = "spot"


class AutomationReplayRequest(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=1000)


class AutomationEngageRequest(BaseModel):
    source: Optional[str] = "manual_double_click"
    decode_id: Optional[str] = None
    call: Optional[str] = None
    callsign: Optional[str] = None
    grid: Optional[str] = None
    mode: Optional[str] = None
    band: Optional[str] = None
    dial_hz: Optional[int] = None
    frequency_mhz: Optional[float] = None
    rx_audio_hz: Optional[int] = None
    tx_audio_hz: Optional[int] = None
    freq: Optional[float] = None
    timestamp: Optional[str] = None
    message: Optional[str] = None
    replace_active: Optional[bool] = True
    reason: Optional[str] = None
    target: Optional[dict[str, Any]] = None


class AutomationAttemptRequest(BaseModel):
    key: str


class AutomationTargetKeyRequest(BaseModel):
    key: str
    reason: Optional[str] = None


class AutomationWsjtxPrepareRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cq_only: bool = Field(default=True, alias="cqOnly")
    auto_call_start_only: bool = Field(default=True, alias="autoCallStartOnly")
    tx_df: Optional[int] = None
    hold_tx_freq: bool = True
    override_eligibility: bool = False


class AutomationWsjtxPrepareTargetRequest(AutomationWsjtxPrepareRequest):
    target: dict[str, Any]


# === API Endpoints ===

@router.get("/status")
async def get_status():
    """Get FT8 service status"""
    service = get_ft8_service()
    return service.get_stats()


@router.post("/start")
async def start_service(config: FT8Config, request: Request):
    """Start FT8 service"""
    try:
        config = _normalise_audio_config(config)
        logger.info(f"Starting FT8 service with audio device: {config.audioInput}")
        ptt_device = _build_digital_ptt_device(config)
        
        # Initialize service with audio device configuration
        service = await init_ft8_service(
            mode=config.mode,
            mycall=config.mycall,
            mygrid=config.mygrid,
            audio_device=config.audioInput,
            audio_output=config.audioOutput,
            audio_sample_rate=config.sampleRate or 12000,
            ptt_method=config.pttMethod or "CAT",
            ptt_device=ptt_device,
        )
        service.on_automation_target_enrich = lambda target: _enrich_automation_target(target, request)
        _configure_automation_status_sources(service, request)
        service.set_config(mycall=config.mycall, mygrid=config.mygrid, mode=config.mode, operator_settings=config.operatorSettings)
        service.audio_stream_enabled = bool(config.waterfallEnabled)
        
        service.auto_sequence = False
        service.tx_enabled = False
        
        await service.start()
        
        logger.info("✅ FT8 service started successfully")
        return {
            "status": "started",
            "mode": config.mode,
            "audioInput": config.audioInput,
            "sampleRate": config.sampleRate,
            "stats": service.get_stats(),
        }
    except Exception as e:
        logger.error(f"❌ Error starting FT8 service: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_service():
    """Stop FT8 service"""
    try:
        service = get_ft8_service()
        await service.stop()
        return {"status": "stopped"}
    except Exception as e:
        logger.error(f"Error stopping FT8 service: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_config(config: FT8Config):
    """Update FT8 configuration"""
    try:
        config = _normalise_audio_config(config)
        # Update service
        service = get_ft8_service()
        service.set_config(mycall=config.mycall, mygrid=config.mygrid, mode=config.mode, operator_settings=config.operatorSettings)
        service.audio_stream_enabled = bool(config.waterfallEnabled)
        service.auto_sequence = bool(config.auto_sequence)
        
        config_payload = config.model_dump()
        config_payload["auto_sequence"] = False
        config_payload["tx_enabled"] = False
        config_updates = _ft8_payload_to_config(config_payload)
        save_config_updates(config_updates)
        for key, value in config_updates.items():
            setattr(app_config, key, value)

        logger.info("✅ FT8 configuration saved to app settings")
        
        return {"status": "updated"}
    except Exception as e:
        logger.error(f"Error updating config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_config():
    """Get FT8 configuration"""
    try:
        app_settings = load_app_settings()
        if any(key in app_settings for key in CONFIG_KEY_TO_FT8_FIELD):
            return _config_to_ft8_payload(app_settings)

        legacy_config = _load_legacy_ft8_config()
        if legacy_config:
            return {**_ft8_defaults(), **legacy_config}

        logger.info("Using default FT8 configuration")
        return _ft8_defaults()
    except Exception as e:
        logger.error(f"Error loading config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decoded")
async def get_decoded_messages(limit: int = 50):
    """Get decoded messages"""
    service = get_ft8_service()
    messages = service.get_decoded_messages(limit)
    return {"messages": messages}


@router.post("/decoded/clear")
async def clear_decoded_messages():
    """Clear backend decoded-message history."""
    service = get_ft8_service()
    service.clear_decoded_messages()
    return {"status": "cleared", "messages": []}


@router.get("/qsos")
async def get_active_qsos():
    """Get active QSO sessions"""
    service = get_ft8_service()
    qsos = service.get_active_qsos()
    return {"qsos": qsos}


@router.get("/waterfall")
async def get_waterfall():
    """Get waterfall data"""
    service = get_ft8_service()
    waterfall = service.get_waterfall_data()
    return {"waterfall": waterfall}


@router.get("/automation/status")
async def get_automation_status():
    """Get backend-owned Digital automation queue and decision state."""
    service = get_ft8_service()
    return service.automation_controller.status()


@router.post("/automation/settings")
async def update_automation_settings(request: AutomationSettingsRequest):
    """Update backend Digital automation controller settings."""
    from services.digital_engine import require_om0rx_planner
    require_om0rx_planner()
    service = get_ft8_service()
    service.automation_controller.apply_operator_settings(request.operatorSettings)
    return {"status": "updated", "automation": service.automation_controller.status()}


@router.post("/automation/reference-hunter")
async def update_reference_hunter_settings(request: ReferenceHunterSettingsRequest):
    """Arm/disarm reference hunting and persist the Filters snapshot."""
    from services.digital_engine import require_om0rx_planner
    require_om0rx_planner()
    service = get_ft8_service()
    automation_update = {
        "referenceHunterEnabled": request.enabled,
        "hunterPrograms": request.programs,
        "hunterMinSpotScore": request.min_spot_score,
        "hunterWatchdogMinutes": request.hunt_watchdog_minutes,
        "hunterRestoreWatchdogMinutes": request.restore_watchdog_minutes,
        "hunterSpotFilters": request.spot_filters,
    }
    if request.enabled:
        automation_update.update({
            "enabled": True,
            "spotHuntEnabled": True,
            "bandHopping": True,
            "requireHeardBeforeCall": True,
            "needReference": True,
        })
    service.automation_controller.apply_operator_settings({"automation": automation_update})

    operator_settings = dict(getattr(app_config, "FT8_OPERATOR_SETTINGS", {}) or {})
    automation = dict(operator_settings.get("automation") or {})
    automation.update(automation_update)
    operator_settings["automation"] = automation
    save_config_updates({"FT8_OPERATOR_SETTINGS": operator_settings})
    setattr(app_config, "FT8_OPERATOR_SETTINGS", operator_settings)
    return {
        "status": "updated",
        "enabled": service.automation_controller.settings.reference_hunter_enabled,
        "automation": service.automation_controller.status(),
    }


@router.post("/automation/target")
async def ingest_automation_target(target_request: AutomationTargetRequest, request: Request):
    """Ingest an enriched decoded station or spot into the backend target queue."""
    service = get_ft8_service()
    _configure_automation_status_sources(service, request)
    enriched = await _enrich_automation_target(target_request.target, request)
    target = service.automation_controller.ingest_target(enriched)
    return {
        "status": "queued" if target else "ignored",
        "target": target.to_dict() if target else None,
        "automation": service.automation_controller.status(),
    }


@router.post("/automation/targets")
async def ingest_automation_targets(targets_request: AutomationTargetsRequest, request: Request):
    """Batch queue digital spot candidates without preparing WSJT-X or enabling TX."""
    service = get_ft8_service()
    _configure_automation_status_sources(service, request)
    queued: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    limit = max(1, min(int(targets_request.limit or 25), 100))

    for raw_target in (targets_request.targets or [])[:limit]:
        target_payload = dict(raw_target or {})
        target_payload.setdefault("source", targets_request.source or "spot")
        target_payload["enableTx"] = False
        try:
            enriched = await _enrich_automation_target(target_payload, request)
            target = service.automation_controller.ingest_target(enriched)
        except Exception as exc:
            callsign = str(target_payload.get("callsign") or target_payload.get("call") or "").upper()
            skipped.append({"call": callsign, "reason": str(exc), "status": "error"})
            logger.debug("Digital target batch ingest failed for %s: %s", callsign, exc, exc_info=True)
            continue

        if target:
            queued.append(target.to_dict())
        else:
            decision = dict(service.automation_controller.last_decision or {})
            skipped.append(
                {
                    "call": str(target_payload.get("callsign") or target_payload.get("call") or "").upper(),
                    "reason": decision.get("reason", "target-not-eligible"),
                    "status": "ignored",
                    "decision": decision,
                }
            )

    return {
        "status": "queued" if queued else "idle",
        "queued_count": len(queued),
        "skipped_count": len(skipped),
        "queued": queued,
        "skipped": skipped,
        "automation": service.automation_controller.status(),
    }


@router.post("/automation/replay")
async def replay_automation_events(replay_request: AutomationReplayRequest):
    """Replay recorded automation events through the planner without radio TX."""
    service = get_ft8_service()
    events = (replay_request.events or [])[: max(1, min(int(replay_request.limit or 100), 1000))]
    results = service.automation_controller.replay_events(events)
    return {
        "status": "replayed",
        "count": len(results),
        "results": results,
        "automation": service.automation_controller.status(),
    }


@router.post("/automation/next")
async def select_next_automation_target():
    """Select the next eligible target without transmitting."""
    service = get_ft8_service()
    target = service.automation_controller.next_target()
    return {
        "status": "selected" if target else "idle",
        "target": target.to_dict() if target else None,
        "automation": service.automation_controller.status(),
    }


@router.post("/automation/attempt")
async def record_automation_attempt(request: AutomationAttemptRequest):
    """Record an automation call attempt and apply retry/backoff rules."""
    service = get_ft8_service()
    target = service.automation_controller.record_attempt(request.key)
    return {
        "status": "updated" if target else "missing",
        "target": target.to_dict() if target else None,
        "automation": service.automation_controller.status(),
    }


@router.post("/automation/promote")
async def promote_automation_target(request: AutomationTargetKeyRequest):
    """Promote a target to the top of the backend planner without preparing WSJT-X."""
    service = get_ft8_service()
    target = service.automation_controller.promote_target(request.key)
    return {
        "status": "promoted" if target else "missing",
        "target": target.to_dict() if target else None,
        "automation": service.automation_controller.status(),
    }


@router.post("/automation/skip")
async def skip_automation_target(request: AutomationTargetKeyRequest):
    """Remove a target from the active planner queue without deleting history."""
    service = get_ft8_service()
    target = service.automation_controller.skip_target(
        request.key,
        reason=request.reason or "operator-removed",
    )
    return {
        "status": "skipped" if target else "missing",
        "target": target.to_dict() if target else None,
        "automation": service.automation_controller.status(),
    }


def _send_wsjtx_prepare_for_automation_target(target: Any, prepare_request: AutomationWsjtxPrepareRequest) -> dict[str, Any]:
    """Prepare a ranked Digital target in patched WSJT-X without enabling TX."""
    from services.wsjtx import get_wsjtx_service

    wsjtx_service = get_wsjtx_service()
    service = get_ft8_service()
    target_payload = target.to_dict()
    target_payload.update(
        {
            "enableTx": False,
            "generateMessages": True,
            "holdTxFreq": bool(prepare_request.hold_tx_freq),
        }
    )
    if prepare_request.tx_df is not None:
        target_payload["txDf"] = int(prepare_request.tx_df)
        tx_df_plan = {
            "tx_df": int(prepare_request.tx_df),
            "reason": "operator-specified",
            "occupied": [],
        }
    else:
        controller = getattr(service, "automation_controller", None)
        tx_df_plan = (
            controller.choose_tx_audio_offset(target)
            if controller and hasattr(controller, "choose_tx_audio_offset")
            else {"tx_df": 1500, "reason": "default", "occupied": []}
        )
        target_payload["txDf"] = int(tx_df_plan["tx_df"])

    wsjtx_target = wsjtx_service.build_target_from_automation_target(target_payload)
    wsjtx_target["enableTx"] = False
    policy = wsjtx_service.assess_target_policy(wsjtx_target, target_payload, action="prepare")
    if not policy["eligible"] and not bool(prepare_request.override_eligibility):
        return {
            "status": "blocked",
            "target": target.to_dict(),
            "wsjtx_target": wsjtx_target,
            "policy": policy,
            "tx_df_plan": tx_df_plan,
        }

    controller = getattr(service, "automation_controller", None)
    if controller and getattr(controller.settings, "dry_run", False):
        controller._set_decision({
            "decision": "dry-run",
            "reason": "would-prepare-wsjtx-target",
            "call": target.call,
            "band": target.band,
            "mode": target.mode,
            "score": target.score,
            "need_reasons": sorted(target.need_reasons),
        })
        return {
            "status": "dry-run",
            "target": target.to_dict(),
            "wsjtx_target": wsjtx_target,
            "policy": policy,
            "tx_df_plan": tx_df_plan,
            "bridge": {
                "success": True,
                "dry_run": True,
                "sent": False,
                "command": "start_target_qso",
            },
        }

    result = wsjtx_service.send_bridge_command("start_target_qso", {"target": wsjtx_target})
    return {
        "status": "prepared",
        "target": target.to_dict(),
        "wsjtx_target": wsjtx_target,
        "policy": policy,
        "tx_df_plan": tx_df_plan,
        "bridge": result,
    }


@router.post("/automation/wsjtx/prepare-next")
async def prepare_next_wsjtx_automation_target(prepare_request: AutomationWsjtxPrepareRequest, request: Request):
    """Prepare the next ranked target in patched WSJT-X without arming TX."""
    service = get_ft8_service()
    _configure_automation_status_sources(service, request)
    target = service.automation_controller.next_target(
        cq_only=bool(prepare_request.cq_only),
        auto_call_start_only=bool(prepare_request.auto_call_start_only),
    )
    if not target:
        return {
            "status": "idle",
            "reason": "no-eligible-targets",
            "automation": service.automation_controller.status(),
        }

    result = _send_wsjtx_prepare_for_automation_target(target, prepare_request)
    result["automation"] = service.automation_controller.status()
    return result


@router.post("/automation/wsjtx/prepare-target")
async def prepare_wsjtx_automation_target(prepare_request: AutomationWsjtxPrepareTargetRequest, request: Request):
    """Prepare a selected spot through backend ranker/Wavelog guardrails without arming TX."""
    service = get_ft8_service()
    _configure_automation_status_sources(service, request)
    target_payload = dict(prepare_request.target or {})
    target_payload.setdefault("source", "spot")
    target_payload["enableTx"] = False
    enriched = await _enrich_automation_target(target_payload, request)
    target = service.automation_controller.ingest_target(enriched)
    if not target:
        return {
            "status": "ignored",
            "reason": service.automation_controller.last_decision.get("reason", "target-not-eligible"),
            "enriched_target": enriched,
            "automation": service.automation_controller.status(),
        }

    result = _send_wsjtx_prepare_for_automation_target(target, prepare_request)
    if result.get("status") != "prepared":
        result["enriched_target"] = enriched
        result["automation"] = service.automation_controller.status()
        return result

    target.sync_state("selected")
    service.automation_controller.active_target_key = target.key
    service.automation_controller._set_decision(
        {
            "decision": "selected",
            "call": target.call,
            "band": target.band,
            "mode": target.mode,
            "score": target.score,
            "reason": target.reason,
            "source": "selected-spot",
        }
    )
    result["target"] = target.to_dict()
    result["enriched_target"] = enriched
    result["automation"] = service.automation_controller.status()
    return result


@router.post("/automation/engage")
async def engage_automation_target(engage_request: AutomationEngageRequest, request: Request):
    """Atomically engage a decoded/manual target in the backend QSO state machine."""
    try:
        service = get_ft8_service()
        _configure_automation_status_sources(service, request)
        target = dict(engage_request.target or {})
        direct_fields = engage_request.model_dump(exclude={"target"}, exclude_none=True)
        target.update(direct_fields)
        if engage_request.dial_hz and not target.get("frequency_mhz"):
            target["frequency_mhz"] = float(engage_request.dial_hz) / 1_000_000
        if engage_request.rx_audio_hz is not None and target.get("freq") is None:
            target["freq"] = engage_request.rx_audio_hz
        tx_audio_hz = engage_request.tx_audio_hz if engage_request.tx_audio_hz is not None else target.get("tx_audio_hz")
        if tx_audio_hz is not None:
            service.set_tx_options(tx_audio_frequency=int(tx_audio_hz))

        enriched = await _enrich_automation_target(target, request)
        source = str(engage_request.source or enriched.get("source") or "manual_double_click")
        message = await service.engage_target(
            enriched,
            source=source,
            replace_active=bool(engage_request.replace_active),
        )
        asyncio.create_task(service.transmit_queued_now_if_possible(force_current_slot=True))
        stats = service.get_stats()
        return {
            "accepted": True,
            "status": "engaged",
            "active_call": enriched.get("callsign") or enriched.get("call"),
            "stage": "calling",
            "next_tx_message": message,
            "scheduled_slot_utc": (stats.get("pending_tx_intent") or {}).get("scheduled_slot_utc"),
            "will_tx_now": bool(
                stats.get("slot_is_tx")
                and stats.get("cycle_position", 99) <= (0.35 if stats.get("mode") == "FT8" else 0.2)
            ),
            "reason": service.tx_status,
            "stats": stats,
            "automation": service.automation_controller.status(),
        }
    except Exception as e:
        logger.error("Error engaging Digital target: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/automation/abort-current")
async def abort_current_automation_attempt():
    """Abort the current attempt using the backend automation semantics."""
    return await abort_current_attempt()


@router.post("/transmit")
async def transmit_message(request: TransmitRequest):
    """Deprecated compatibility route for legacy free-form transmission."""
    if not _legacy_tx_routes_enabled():
        _raise_legacy_tx_disabled("/api/ft8/transmit")

    try:
        service = get_ft8_service()
        if not service.active_attempt_id:
            raise HTTPException(status_code=409, detail="Legacy free-form TX requires an active backend attempt")
        raise HTTPException(
            status_code=410,
            detail="Legacy free-form TX is not accepted; select a backend-owned TX button via /api/ft8/tx/manual",
        )
    except Exception as e:
        logger.error(f"Error queueing message: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tx/enable")
async def enable_tx(request: TxControlRequest):
    """Arm built-in FT8/FT4 TX. Operator action required."""
    try:
        service = get_ft8_service()
        service.set_tx_options(
            tx_audio_frequency=request.tx_audio_frequency,
            tx_even_first=request.tx_even_first,
            watchdog_ft8=request.watchdog_ft8,
            watchdog_ft4=request.watchdog_ft4,
            watchdog_enabled=request.watchdog_enabled,
            auto_cq=request.auto_cq,
            auto_call=request.auto_call,
            cq_only=request.cq_only,
            auto_cq_limit=request.auto_cq_limit,
            auto_call_limit=request.auto_call_limit,
            special_activity=request.specialActivity,
        )
        service.enable_tx()
        if request.immediate:
            asyncio.create_task(service.transmit_queued_now_if_possible(force_current_slot=True))
        return {"status": "enabled", "stats": service.get_stats()}
    except Exception as e:
        logger.error("Error enabling FT8 TX: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tx/halt")
async def halt_tx():
    """Immediately halt built-in FT8/FT4 TX and clear the TX queue."""
    try:
        service = get_ft8_service()
        service.halt_tx()
        return {"status": "halted", "stats": service.get_stats()}
    except Exception as e:
        logger.error("Error halting FT8 TX: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tx/clear-qso")
async def clear_current_qso():
    """Clear the active backend QSO attempt and pending TX without scheduling replacement work."""
    try:
        service = get_ft8_service()
        service.clear_current_qso()
        return {"status": "cleared", "stats": service.get_stats()}
    except Exception as e:
        logger.error("Error clearing FT8 QSO: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tx/manual")
async def manual_tx(request: ManualTxRequest):
    """Queue a manual TX-button override through the backend QSO owner."""
    try:
        service = get_ft8_service()
        service.enable_tx()
        message = await service.queue_manual_tx_button(request.tx_id)
        if request.immediate:
            asyncio.create_task(service.transmit_queued_now_if_possible(force_current_slot=True))
        return {"status": "queued", "message": message, "stats": service.get_stats()}
    except Exception as e:
        logger.error("Error queueing manual Digital TX: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tx/abort-current")
async def abort_current_attempt():
    """Abort the current call attempt but keep Digital automation running."""
    try:
        service = get_ft8_service()
        service.abort_current_attempt()
        return {"status": "aborted", "stats": service.get_stats()}
    except Exception as e:
        logger.error("Error aborting current FT8 attempt: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tx/watchdog/extend")
async def extend_tx_watchdog():
    """Extend the active FT8/FT4 TX watchdog by one configured watchdog period."""
    try:
        service = get_ft8_service()
        return service.extend_watchdog()
    except Exception as e:
        logger.error("Error extending FT8 TX watchdog: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tx/tune")
async def tune_tone(request: TuneToneRequest):
    """Transmit a short digital audio tune tone with the selected PTT method."""
    try:
        service = get_ft8_service()
        service.set_tx_options(tx_audio_frequency=request.tx_audio_frequency)
        result = await service.transmit_tune_tone(duration_seconds=request.duration_seconds or 5.0)
        return {"status": "sent", "result": result}
    except Exception as e:
        logger.error("Error sending FT8 tune tone: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cq")
async def call_cq():
    """Deprecated compatibility CQ route."""
    if not _legacy_tx_routes_enabled():
        _raise_legacy_tx_disabled("/api/ft8/cq")

    try:
        service = get_ft8_service()
        service.enable_tx()
        message = await service.queue_manual_tx_button(6)
        asyncio.create_task(service.transmit_queued_now_if_possible(force_current_slot=True))
        return {"status": "queued", "message": message, "stats": service.get_stats()}
    except Exception as e:
        logger.error(f"Error calling CQ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reply")
async def reply_to_call(request: ReplyRequest):
    """Deprecated compatibility reply route."""
    if not _legacy_tx_routes_enabled():
        _raise_legacy_tx_disabled("/api/ft8/reply")

    try:
        raise HTTPException(
            status_code=410,
            detail="Legacy reply is not accepted; use /api/ft8/automation/engage and backend auto-sequencing",
        )
    except Exception as e:
        logger.error(f"Error replying to call: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send73")
async def send_73(their_call: str):
    """Deprecated compatibility final-73 route."""
    if not _legacy_tx_routes_enabled():
        _raise_legacy_tx_disabled("/api/ft8/send73")

    try:
        raise HTTPException(
            status_code=410,
            detail="Legacy send73 is not accepted; backend QSO state decides final 73/RR73",
        )
    except Exception as e:
        logger.error(f"Error sending 73: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


# === WebSocket Endpoint ===

@router.websocket("/ws")
async def ft8_websocket(websocket: WebSocket):
    """WebSocket for real-time FT8 updates"""
    await websocket.accept()
    logger.info("FT8 WebSocket connected")
    
    try:
        service = get_ft8_service()
        
        # Send initial state
        await websocket.send_json({
            'type': 'status',
            'data': service.get_stats()
        })
        
        # Set up callbacks
        async def on_message_decoded(message):
            try:
                await websocket.send_json({
                    'type': 'decoded',
                    'data': message.to_dict()
                })
            except Exception as e:
                logger.error(f"Error sending decoded message: {e}")
        
        async def on_qso_complete(qso):
            try:
                await websocket.send_json({
                    'type': 'qso_complete',
                    'data': qso.to_dict()
                })
            except Exception as e:
                logger.error(f"Error sending QSO complete: {e}")
        
        async def on_tx_message(audio, message):
            try:
                await websocket.send_json({
                    'type': 'transmitting',
                    'data': {'message': message, 'result': audio}
                })
            except Exception as e:
                logger.error(f"Error sending TX notification: {e}")
        
        async def on_audio_stream(audio_data):
            """Stream audio data to the frontend waterfall."""
            try:
                await websocket.send_json({
                    'type': 'audio_stream',
                    'data': audio_data
                })
            except Exception as e:
                logger.error(f"Error sending audio stream: {e}")
        
        def register_callbacks(target_service):
            target_service.on_message_decoded = on_message_decoded
            target_service.on_qso_complete = on_qso_complete
            target_service.on_tx_message = on_tx_message
            target_service.on_audio_stream = on_audio_stream

        def clear_callbacks(target_service):
            if target_service.on_message_decoded is on_message_decoded:
                target_service.on_message_decoded = None
            if target_service.on_qso_complete is on_qso_complete:
                target_service.on_qso_complete = None
            if target_service.on_tx_message is on_tx_message:
                target_service.on_tx_message = None
            if target_service.on_audio_stream is on_audio_stream:
                target_service.on_audio_stream = None

        # Register callbacks. The FT8 service may be replaced by /start, so the
        # loop below rebinds when the global service instance changes.
        register_callbacks(service)
        
        # Periodic status updates
        while True:
            try:
                current_service = get_ft8_service()
                if current_service is not service:
                    clear_callbacks(service)
                    service = current_service
                    register_callbacks(service)

                if service.audio_stream_enabled:
                    waterfall = service.get_waterfall_data()
                    await websocket.send_json({
                        'type': 'waterfall',
                        'data': waterfall
                    })
                
                # Send status update
                await websocket.send_json({
                    'type': 'status',
                    'data': service.get_stats()
                })
                
                # Send active QSOs
                qsos = service.get_active_qsos()
                await websocket.send_json({
                    'type': 'qsos',
                    'data': qsos
                })
                
                await asyncio.sleep(1.0)
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}", exc_info=True)
                break
    
    except WebSocketDisconnect:
        logger.info("FT8 WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in FT8 WebSocket: {e}", exc_info=True)
    finally:
        # Clean up callbacks
        try:
            clear_callbacks(service)
        except Exception:
            pass


@router.get("/audio-devices")
async def get_audio_devices():
    """Get available audio input/output devices"""
    sd = get_sounddevice()
    if sd is None:
        sc = get_soundcard()
        if sc is None:
            return {
                "input": [],
                "output": [],
                "error": f"{sounddevice_unavailable_reason()}; {soundcard_unavailable_reason()}",
            }
        try:
            input_devices = [
                f"{idx}: {getattr(device, 'name', f'soundcard input {idx}')}"
                for idx, device in enumerate(sc.all_microphones(include_loopback=True))
            ]
            output_devices = [
                f"{idx}: {getattr(device, 'name', f'soundcard output {idx}')}"
                for idx, device in enumerate(sc.all_speakers())
            ]
            return {
                "input": input_devices,
                "output": output_devices,
                "backend": "soundcard",
                "warning": sounddevice_unavailable_reason(),
            }
        except Exception as e:
            logger.error("Error querying soundcard audio devices: %s", e, exc_info=True)
            return {"input": [], "output": [], "error": str(e), "backend": "soundcard"}
    
    try:
        devices = sd.query_devices()
        
        input_devices = []
        output_devices = []
        
        for idx, device in enumerate(devices):
            device_name = device['name']
            
            if device['max_input_channels'] > 0:
                input_devices.append(f"{idx}: {device_name}")
            
            if device['max_output_channels'] > 0:
                output_devices.append(f"{idx}: {device_name}")
        
        return {
            "input": input_devices,
            "output": output_devices
        }
    except Exception as e:
        logger.error(f"Error querying audio devices: {e}", exc_info=True)
        return {"input": [], "output": [], "error": str(e)}


@router.get("/time-sync")
async def get_time_sync():
    """Check local clock offset against NTP without changing the system clock."""
    from services.ft8_tx import ntp_offset
    return ntp_offset()


def register_ft8_endpoints(app):
    """Register FT8 endpoints with FastAPI app"""
    app.include_router(router)
    logger.info("FT8 API endpoints registered")
