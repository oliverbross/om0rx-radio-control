"""
FT8/FT4 API Endpoints
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Optional, List
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ft8", tags=["ft8"])

# Try to import sounddevice for audio device enumeration
try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    logger.warning("sounddevice not installed - audio device enumeration unavailable")
    AUDIO_AVAILABLE = False


# === Request/Response Models ===

class FT8Config(BaseModel):
    """FT8 configuration"""
    mode: str = 'FT8'  # 'FT8' or 'FT4'
    mycall: str
    mygrid: str
    auto_sequence: bool = False
    tx_enabled: bool = False
    networkServer: Optional[str] = '192.168.0.199:4992'
    pttMethod: Optional[str] = 'CAT'
    audioInput: Optional[str] = 'default'
    audioOutput: Optional[str] = 'default'
    sampleRate: Optional[int] = 12000
    waterfallHeight: Optional[int] = 100
    useFlexRadioAudio: Optional[bool] = True


FT8_FIELD_TO_CONFIG_KEY = {
    "mode": "FT8_MODE",
    "mycall": "FT8_MYCALL",
    "mygrid": "FT8_MYGRID",
    "auto_sequence": "FT8_AUTO_SEQUENCE",
    "tx_enabled": "FT8_TX_ENABLED",
    "networkServer": "FT8_NETWORK_SERVER",
    "pttMethod": "FT8_PTT_METHOD",
    "audioInput": "FT8_AUDIO_INPUT",
    "audioOutput": "FT8_AUDIO_OUTPUT",
    "sampleRate": "FT8_SAMPLE_RATE",
    "waterfallHeight": "FT8_WATERFALL_HEIGHT",
    "useFlexRadioAudio": "FT8_USE_FLEXRADIO_AUDIO",
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
        "pttMethod": getattr(app_config, "FT8_PTT_METHOD", "CAT"),
        "audioInput": getattr(app_config, "FT8_AUDIO_INPUT", "default"),
        "audioOutput": getattr(app_config, "FT8_AUDIO_OUTPUT", "default"),
        "sampleRate": getattr(app_config, "FT8_SAMPLE_RATE", 12000),
        "waterfallHeight": getattr(app_config, "FT8_WATERFALL_HEIGHT", 100),
        "useFlexRadioAudio": getattr(app_config, "FT8_USE_FLEXRADIO_AUDIO", True),
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


class TransmitRequest(BaseModel):
    """TX message request"""
    message: str


class ReplyRequest(BaseModel):
    """Reply to call request"""
    their_call: str
    report: str = "R-15"


# === API Endpoints ===

@router.get("/status")
async def get_status():
    """Get FT8 service status"""
    service = get_ft8_service()
    return service.get_stats()


@router.post("/start")
async def start_service(config: FT8Config):
    """Start FT8 service"""
    try:
        logger.info(f"Starting FT8 service with audio device: {config.audioInput}")
        
        # Initialize service with audio device configuration
        service = await init_ft8_service(
            mode=config.mode,
            mycall=config.mycall,
            mygrid=config.mygrid,
            audio_device=config.audioInput
        )
        
        service.auto_sequence = config.auto_sequence
        service.tx_enabled = config.tx_enabled
        
        await service.start()
        
        logger.info(f"✅ FT8 service started successfully")
        return {"status": "started", "mode": config.mode}
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
        # Update service
        service = get_ft8_service()
        service.set_config(mycall=config.mycall, mygrid=config.mygrid)
        service.auto_sequence = config.auto_sequence
        service.tx_enabled = config.tx_enabled
        
        config_payload = config.dict()
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


@router.post("/transmit")
async def transmit_message(request: TransmitRequest):
    """Queue a message for transmission"""
    try:
        service = get_ft8_service()
        await service.queue_tx_message(request.message)
        return {"status": "queued", "message": request.message}
    except Exception as e:
        logger.error(f"Error queueing message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cq")
async def call_cq():
    """Call CQ"""
    try:
        service = get_ft8_service()
        await service.call_cq()
        return {"status": "queued"}
    except Exception as e:
        logger.error(f"Error calling CQ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reply")
async def reply_to_call(request: ReplyRequest):
    """Reply to a call"""
    try:
        service = get_ft8_service()
        await service.reply_to_call(request.their_call, request.report)
        return {"status": "queued"}
    except Exception as e:
        logger.error(f"Error replying to call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send73")
async def send_73(their_call: str):
    """Send 73"""
    try:
        service = get_ft8_service()
        await service.send_73(their_call)
        return {"status": "queued"}
    except Exception as e:
        logger.error(f"Error sending 73: {e}", exc_info=True)
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
                    'data': {'message': message}
                })
            except Exception as e:
                logger.error(f"Error sending TX notification: {e}")
        
        async def on_audio_stream(audio_data):
            """Stream audio data to frontend for client-side decoding"""
            try:
                await websocket.send_json({
                    'type': 'audio_stream',
                    'data': audio_data
                })
            except Exception as e:
                logger.error(f"Error sending audio stream: {e}")
        
        # Register callbacks
        service.on_message_decoded = on_message_decoded
        service.on_qso_complete = on_qso_complete
        service.on_tx_message = on_tx_message
        service.on_audio_stream = on_audio_stream  # Enable audio streaming
        
        # Periodic status updates
        while True:
            try:
                # Send waterfall update
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
        service.on_message_decoded = None
        service.on_qso_complete = None
        service.on_tx_message = None
        service.on_audio_stream = None


@router.get("/audio-devices")
async def get_audio_devices():
    """Get available audio input/output devices"""
    if not AUDIO_AVAILABLE:
        return {"input": [], "output": [], "error": "sounddevice not installed"}
    
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


def register_ft8_endpoints(app):
    """Register FT8 endpoints with FastAPI app"""
    app.include_router(router)
    logger.info("FT8 API endpoints registered")
