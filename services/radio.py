"""
Radio Control Service - FastAPI Endpoints for FlexRadio Control

This module contains all radio control endpoints extracted from main.py,
including basic controls, TX controls, AGC/DSP controls, RIT/XIT controls,
and RX2/SPLIT controls.

The module can be imported and endpoints can be registered with a FastAPI app.
"""

import logging
from dataclasses import dataclass
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Any, Awaitable, Callable, Optional

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class RadioControlState:
    """Runtime dependencies for radio control endpoints."""

    flex: Any = None
    broadcast_func: Optional[Callable[[dict], Awaitable[None]]] = None


radio_control_state = RadioControlState()


def configure_radio_control(flex_instance=None, broadcast_func=None) -> RadioControlState:
    radio_control_state.flex = flex_instance
    if broadcast_func is not None:
        radio_control_state.broadcast_func = broadcast_func
    return radio_control_state


def get_radio_instance():
    return radio_control_state.flex


async def broadcast_status(data: dict):
    if radio_control_state.broadcast_func:
        await radio_control_state.broadcast_func(data)

# === Pydantic Models ===

class FrequencyRequest(BaseModel):
    frequency: float

class ModeRequest(BaseModel):
    mode: str

class BandRequest(BaseModel):
    band: str

class FilterRequest(BaseModel):
    filter_lo: int
    filter_hi: int

class SliderRequest(BaseModel):
    value: int

class ToggleRequest(BaseModel):
    enabled: bool

class AGCRequest(BaseModel):
    mode: str  # off, slow, med, fast

class DSPRequest(BaseModel):
    control: str  # nb, nr, anf, apf
    enabled: bool

class DSPLevelRequest(BaseModel):
    control: str  # nb_level, nr_level, anf_level, apf_level
    value: int  # 0-100

class RITXITRequest(BaseModel):
    enabled: bool
    freq_hz: Optional[int] = 0

class RX2Request(BaseModel):
    frequency: Optional[float] = None
    enabled: bool

class SplitRequest(BaseModel):
    enabled: bool
    tx_frequency: Optional[float] = None

class StepRequest(BaseModel):
    step_hz: int

# === Basic Controls ===

async def set_frequency(req: FrequencyRequest):
    """Set frequency"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.tune_mhz(req.frequency)
        if success:
            if broadcast_status:
                await broadcast_status({"frequency": req.frequency})
            return {"success": True, "frequency": req.frequency}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        logger.error(f"Set frequency error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def set_mode(req: ModeRequest):
    """Set mode"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_mode(req.mode)
        if success:
            if broadcast_status:
                await broadcast_status({"mode": req.mode})
            return {"success": True, "mode": req.mode}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        logger.error(f"Set mode error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def set_band(req: BandRequest):
    """Set band"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_band(req.band)
        if success:
            if broadcast_status:
                await broadcast_status({"band": req.band, "frequency": flex.current_freq})
            return {"success": True, "band": req.band}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        logger.error(f"Set band error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def set_filter(req: FilterRequest):
    """Set filter"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_filter_edges(req.filter_lo, req.filter_hi)
        if success:
            if broadcast_status:
                await broadcast_status({"filter_lo": req.filter_lo, "filter_hi": req.filter_hi})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        logger.error(f"Set filter error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def set_volume(req: SliderRequest):
    """Set volume"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_volume(req.value)
        if success:
            if broadcast_status:
                await broadcast_status({"volume": req.value})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def set_drive(req: SliderRequest):
    """Set drive (RF power)"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_rf_power(req.value)
        if success:
            if broadcast_status:
                await broadcast_status({"drive": req.value})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def set_tune_power(req: SliderRequest):
    """Set tune power"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_tune_power(req.value)
        if success:
            if broadcast_status:
                await broadcast_status({"tune_power": req.value})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def set_mic(req: SliderRequest):
    """Set mic level"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_mic_level(req.value)
        if success:
            if broadcast_status:
                await broadcast_status({"mic_level": req.value})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def set_monitor(req: SliderRequest):
    """Set monitor level (auto-enables monitor when > 0)"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_monitor(req.value, auto_enable=True)
        if success:
            if broadcast_status:
                await broadcast_status({"monitor": req.value})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def set_agc_threshold(req: SliderRequest):
    """Set AGC threshold"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_agc_threshold(req.value)
        if success:
            if broadcast_status:
                await broadcast_status({"agc_threshold": req.value})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === TX Controls ===

async def toggle_mox(req: ToggleRequest):
    """Toggle MOX"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_mox(req.enabled)
        if success:
            if broadcast_status:
                await broadcast_status({"mox": req.enabled})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def toggle_tune(req: ToggleRequest):
    """Toggle TUNE"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_tune(req.enabled)
        if success:
            if broadcast_status:
                await broadcast_status({"tune": req.enabled})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def toggle_vox(req: ToggleRequest):
    """Toggle VOX"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_vox(req.enabled)
        if success:
            if broadcast_status:
                await broadcast_status({"vox": req.enabled})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def toggle_breakin(req: ToggleRequest):
    """Toggle CW Break-In (QSK)"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_breakin(req.enabled)
        if success:
            if broadcast_status:
                await broadcast_status({"break_in": req.enabled})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def set_tuning_step(req: StepRequest):
    """Set tuning step in Hz"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_tuning_step(req.step_hz)
        if success:
            if broadcast_status:
                await broadcast_status({"step": req.step_hz})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === AGC Control ===

async def set_agc(req: AGCRequest):
    """Set AGC mode (off, slow, med, fast)"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex._send(f"slice set {flex.slice_id} agc_mode={req.mode}")
        if success:
            if broadcast_status:
                await broadcast_status({"agc_mode": req.mode})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === DSP Controls ===

async def set_dsp(req: DSPRequest):
    """Set DSP controls (NB, NR, ANF, APF)"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        value = "1" if req.enabled else "0"
        # Activate slice first (required for all slice parameter changes)
        flex._send(f"slice set {flex.slice_id} active=1")

        # Toggle the DSP on/off flag
        success = flex._send(f"slice set {flex.slice_id} {req.control}_on={value}")

        # When disabling, also reset the level to 0 (required by SmartSDR)
        # This mirrors the pattern used in set_monitor()
        if success and not req.enabled:
            flex._send(f"slice set {flex.slice_id} {req.control}_level=0")

        if success:
            if broadcast_status:
                await broadcast_status({f"{req.control}_enabled": req.enabled})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def set_dsp_level(req: DSPLevelRequest):
    """Set DSP level (nb_level, nr_level, anf_level, apf_level)"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_dsp_level(req.control, req.value)
        if success:
            if broadcast_status:
                await broadcast_status({req.control: req.value})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === RIT/XIT Controls ===

async def set_rit(req: RITXITRequest):
    """Set RIT enabled and frequency offset"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_rit(req.enabled, req.freq_hz or 0)
        if success:
            if broadcast_status:
                await broadcast_status({"rit_enabled": req.enabled, "rit_freq": req.freq_hz or 0})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def set_xit(req: RITXITRequest):
    """Set XIT enabled and frequency offset"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        success = flex.set_xit(req.enabled, req.freq_hz or 0)
        if success:
            if broadcast_status:
                await broadcast_status({"xit_enabled": req.enabled, "xit_freq": req.freq_hz or 0})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === RX2 Control ===

async def set_rx2(req: RX2Request):
    """Enable/disable RX2"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        # RX2 is typically slice 1
        if req.enabled:
            success = flex._send(f"slice create freq={req.frequency or 14.074}")
            if req.frequency:
                flex._send(f"slice set 1 RF_frequency={req.frequency:.6f}")
        else:
            success = flex._send("slice remove 1")

        if success:
            if broadcast_status:
                await broadcast_status({"rx2_enabled": req.enabled})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === SPLIT Control ===

async def set_split(req: SplitRequest):
    """Enable/disable SPLIT operation"""
    flex = get_radio_instance()
    if not flex:
        raise HTTPException(status_code=503, detail="Radio not initialized")

    try:
        if req.enabled:
            # Enable split - set TX frequency different from RX
            tx_freq = req.tx_frequency or (flex.current_freq + 0.005)  # Default: +5 kHz
            success = flex._send(f"slice set {flex.slice_id} tx_freq={tx_freq:.6f}")
            flex._send(f"slice set {flex.slice_id} split=1")
        else:
            success = flex._send(f"slice set {flex.slice_id} split=0")

        if success:
            if broadcast_status:
                await broadcast_status({"split_enabled": req.enabled})
            return {"success": True}
        raise HTTPException(status_code=400, detail="Command failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Endpoint Registration ===

def register_radio_endpoints(app, flex_instance=None, broadcast_func=None):
    """
    Register all radio control endpoints with a FastAPI app.

    Args:
        app: FastAPI application instance
        flex_instance: FlexCtl radio instance (optional, can be set later)
        broadcast_func: WebSocket broadcast function (optional, can be set later)
    """
    configure_radio_control(flex_instance, broadcast_func)

    # Register endpoints
    app.post("/api/frequency")(set_frequency)
    app.post("/api/mode")(set_mode)
    app.post("/api/band")(set_band)
    app.post("/api/filter")(set_filter)
    app.post("/api/volume")(set_volume)
    app.post("/api/drive")(set_drive)
    app.post("/api/tune_power")(set_tune_power)
    app.post("/api/mic")(set_mic)
    app.post("/api/monitor")(set_monitor)
    app.post("/api/agc_threshold")(set_agc_threshold)

    # TX Controls
    app.post("/api/mox")(toggle_mox)
    app.post("/api/tune")(toggle_tune)
    app.post("/api/vox")(toggle_vox)
    app.post("/api/breakin")(toggle_breakin)
    app.post("/api/step")(set_tuning_step)

    # AGC/DSP Controls
    app.post("/api/agc")(set_agc)
    app.post("/api/dsp")(set_dsp)
    app.post("/api/dsp_level")(set_dsp_level)

    # RIT/XIT Controls
    app.post("/api/rit")(set_rit)
    app.post("/api/xit")(set_xit)

    # RX2/SPLIT Controls
    app.post("/api/rx2")(set_rx2)
    app.post("/api/split")(set_split)

    logger.info("✅ Radio control endpoints registered")


def set_radio_instance(flex_instance):
    """Set the radio instance used by registered endpoints."""
    radio_control_state.flex = flex_instance


def set_broadcast_function(broadcast_func):
    """Set the broadcaster used by registered endpoints."""
    radio_control_state.broadcast_func = broadcast_func
