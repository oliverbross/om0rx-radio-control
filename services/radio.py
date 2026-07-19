"""Validated, serialized FlexRadio command API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator


logger = logging.getLogger(__name__)
RadioMode = Literal["AM", "SAM", "FM", "NFM", "USB", "LSB", "CW", "DIGU", "DIGL", "RTTY"]
RadioBand = Literal["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]
AgcMode = Literal["off", "slow", "med", "fast"]
DspControl = Literal["nb", "nr", "anf", "apf"]
DspLevelControl = Literal["nb_level", "nr_level", "anf_level", "apf_level"]


@dataclass
class RadioControlState:
    flex: Any = None
    broadcast_func: Optional[Callable[[dict], Awaitable[None]]] = None


radio_control_state = RadioControlState()
_command_lock = asyncio.Lock()


def configure_radio_control(flex_instance=None, broadcast_func=None) -> RadioControlState:
    radio_control_state.flex = flex_instance
    if broadcast_func is not None:
        radio_control_state.broadcast_func = broadcast_func
    return radio_control_state


def get_radio_instance():
    return radio_control_state.flex


async def broadcast_status(data: dict) -> None:
    if radio_control_state.broadcast_func:
        await radio_control_state.broadcast_func(data)


class FrequencyRequest(BaseModel):
    frequency: float = Field(ge=0.01, le=6000)


class ModeRequest(BaseModel):
    mode: RadioMode


class BandRequest(BaseModel):
    band: RadioBand


class FilterRequest(BaseModel):
    filter_lo: int = Field(ge=-12000, le=12000)
    filter_hi: int = Field(ge=-12000, le=12000)

    @model_validator(mode="after")
    def validate_order(self):
        if self.filter_lo >= self.filter_hi:
            raise ValueError("filter_lo must be lower than filter_hi")
        return self


class SliderRequest(BaseModel):
    value: int = Field(ge=0, le=100)


class ToggleRequest(BaseModel):
    enabled: bool


class AGCRequest(BaseModel):
    mode: AgcMode


class DSPRequest(BaseModel):
    control: DspControl
    enabled: bool


class DSPLevelRequest(BaseModel):
    control: DspLevelControl
    value: int = Field(ge=0, le=100)


class RITXITRequest(BaseModel):
    enabled: bool
    freq_hz: int = Field(default=0, ge=-99999, le=99999)


class RX2Request(BaseModel):
    frequency: Optional[float] = Field(default=None, ge=0.01, le=6000)
    enabled: bool


class SplitRequest(BaseModel):
    enabled: bool
    tx_frequency: Optional[float] = Field(default=None, ge=0.01, le=6000)


class StepRequest(BaseModel):
    step_hz: int = Field(ge=1, le=100000)


def _require_radio():
    flex = get_radio_instance()
    if flex is None or getattr(flex, "sock", None) is None:
        # Test doubles and deferred-connect clients can still own a connect method.
        if flex is None:
            raise HTTPException(status_code=503, detail="Radio is unavailable")
    return flex


async def _run(operation: Callable[[], Any], *, timeout: float = 3.0) -> Any:
    """Run one blocking Flex operation without blocking or racing the event loop."""
    async with _command_lock:
        try:
            result = await asyncio.wait_for(asyncio.to_thread(operation), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=504, detail="Radio command timed out") from exc
        except HTTPException:
            raise
        except (ConnectionError, OSError) as exc:
            logger.warning("Radio connection error: %s", exc)
            raise HTTPException(status_code=503, detail="Radio connection failed") from exc
        except Exception as exc:
            logger.exception("Unexpected radio command failure")
            raise HTTPException(status_code=500, detail="Radio command failed") from exc
    if result is not True:
        raise HTTPException(status_code=409, detail="Radio rejected or did not acknowledge the command")
    return result


async def _simple(method_name: str, args: tuple[Any, ...], state: dict[str, Any]) -> dict[str, Any]:
    flex = _require_radio()
    method = getattr(flex, method_name)
    await _run(lambda: method(*args))
    await broadcast_status(state)
    return {"success": True, **state}


async def set_frequency(req: FrequencyRequest):
    return await _simple("tune_mhz", (req.frequency,), {"frequency": req.frequency})


async def set_mode(req: ModeRequest):
    return await _simple("set_mode", (req.mode,), {"mode": req.mode})


async def set_band(req: BandRequest):
    flex = _require_radio()
    await _run(lambda: flex.set_band(req.band))
    state = {"band": req.band, "frequency": getattr(flex, "current_freq", None)}
    await broadcast_status(state)
    return {"success": True, **state}


async def set_filter(req: FilterRequest):
    return await _simple("set_filter_edges", (req.filter_lo, req.filter_hi), {"filter_lo": req.filter_lo, "filter_hi": req.filter_hi})


async def set_volume(req: SliderRequest):
    return await _simple("set_volume", (req.value,), {"volume": req.value})


async def set_drive(req: SliderRequest):
    return await _simple("set_rf_power", (req.value,), {"drive": req.value})


async def set_tune_power(req: SliderRequest):
    return await _simple("set_tune_power", (req.value,), {"tune_power": req.value})


async def set_mic(req: SliderRequest):
    return await _simple("set_mic_level", (req.value,), {"mic_level": req.value})


async def set_monitor(req: SliderRequest):
    return await _simple("set_monitor", (req.value, True), {"monitor": req.value})


async def set_agc_threshold(req: SliderRequest):
    return await _simple("set_agc_threshold", (req.value,), {"agc_threshold": req.value})


async def toggle_mox(req: ToggleRequest):
    return await _simple("set_mox", (req.enabled,), {"mox": req.enabled})


async def toggle_tune(req: ToggleRequest):
    return await _simple("set_tune", (req.enabled,), {"tune": req.enabled})


async def toggle_vox(req: ToggleRequest):
    return await _simple("set_vox", (req.enabled,), {"vox": req.enabled})


async def toggle_breakin(req: ToggleRequest):
    return await _simple("set_breakin", (req.enabled,), {"break_in": req.enabled})


async def set_tuning_step(req: StepRequest):
    return await _simple("set_tuning_step", (req.step_hz,), {"step": req.step_hz})


async def set_agc(req: AGCRequest):
    flex = _require_radio()
    await _run(lambda: flex._send(f"slice set {flex.slice_id} agc_mode={req.mode}"))
    await broadcast_status({"agc_mode": req.mode})
    return {"success": True, "agc_mode": req.mode}


async def set_dsp(req: DSPRequest):
    flex = _require_radio()
    value = 1 if req.enabled else 0

    def operation() -> bool:
        if not flex._send(f"slice set {flex.slice_id} active=1"):
            return False
        if not flex._send(f"slice set {flex.slice_id} {req.control}_on={value}"):
            return False
        return req.enabled or flex._send(f"slice set {flex.slice_id} {req.control}_level=0")

    await _run(operation)
    await broadcast_status({f"{req.control}_enabled": req.enabled})
    return {"success": True}


async def set_dsp_level(req: DSPLevelRequest):
    return await _simple("set_dsp_level", (req.control, req.value), {req.control: req.value})


async def set_rit(req: RITXITRequest):
    return await _simple("set_rit", (req.enabled, req.freq_hz), {"rit_enabled": req.enabled, "rit_freq": req.freq_hz})


async def set_xit(req: RITXITRequest):
    return await _simple("set_xit", (req.enabled, req.freq_hz), {"xit_enabled": req.enabled, "xit_freq": req.freq_hz})


async def set_rx2(req: RX2Request):
    flex = _require_radio()

    def operation() -> bool:
        if not req.enabled:
            return flex._send("slice remove 1")
        frequency = req.frequency if req.frequency is not None else getattr(flex, "current_freq", None)
        if frequency is None or not flex._send(f"slice create freq={frequency:.6f}"):
            return False
        return req.frequency is None or flex._send(f"slice set 1 RF_frequency={req.frequency:.6f}")

    await _run(operation)
    await broadcast_status({"rx2_enabled": req.enabled})
    return {"success": True}


async def set_split(req: SplitRequest):
    flex = _require_radio()

    def operation() -> bool:
        if not req.enabled:
            return flex._send(f"slice set {flex.slice_id} split=0")
        current = getattr(flex, "current_freq", None)
        tx_frequency = req.tx_frequency if req.tx_frequency is not None else (current + 0.005 if current is not None else None)
        if tx_frequency is None or not flex._send(f"slice set {flex.slice_id} tx_freq={tx_frequency:.6f}"):
            return False
        return flex._send(f"slice set {flex.slice_id} split=1")

    await _run(operation)
    await broadcast_status({"split_enabled": req.enabled})
    return {"success": True}


def register_radio_endpoints(app, flex_instance=None, broadcast_func=None):
    configure_radio_control(flex_instance, broadcast_func)
    endpoints = {
        "/api/frequency": set_frequency, "/api/mode": set_mode, "/api/band": set_band,
        "/api/filter": set_filter, "/api/volume": set_volume, "/api/drive": set_drive,
        "/api/tune_power": set_tune_power, "/api/mic": set_mic, "/api/monitor": set_monitor,
        "/api/agc_threshold": set_agc_threshold, "/api/mox": toggle_mox, "/api/tune": toggle_tune,
        "/api/vox": toggle_vox, "/api/breakin": toggle_breakin, "/api/step": set_tuning_step,
        "/api/agc": set_agc, "/api/dsp": set_dsp, "/api/dsp_level": set_dsp_level,
        "/api/rit": set_rit, "/api/xit": set_xit, "/api/rx2": set_rx2, "/api/split": set_split,
    }
    for path, endpoint in endpoints.items():
        app.post(path)(endpoint)
    logger.info("Radio control endpoints registered")


def set_radio_instance(flex_instance):
    radio_control_state.flex = flex_instance
