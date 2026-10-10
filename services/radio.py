"""Validated, serialized FlexRadio command API."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
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
    station_tx_guard: Optional[Callable[[str, Callable[[], Any]], Awaitable[bool]]] = None
    station_route_handler: Optional[
        Callable[[str, Callable[[], Any]], Awaitable[bool]]
    ] = None


radio_control_state = RadioControlState()
_command_lock = asyncio.Lock()
_radio_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="flex-radio-io")
_radio_io_lock = threading.RLock()


def get_radio_command_lock() -> asyncio.Lock:
    """Return the process-wide lock used by all coordinated FLEX mutations."""
    return _command_lock


class RadioIODeadlineError(TimeoutError):
    """The operation could not safely enter the shared FLEX socket lane in time."""


def run_radio_io_sync(
    operation: Callable[[], Any],
    *,
    cancel_event: threading.Event | None = None,
    admission_deadline: float | None = None,
) -> Any:
    """Serialize every direct Flex socket operation, including worker threads.

    The background poller and digital-engine safety checks share one FlexCtl
    socket.  A plain ``asyncio.Lock`` cannot protect the synchronous safety
    checks that run in FastAPI worker threads, so the socket itself also needs
    a process-wide thread lock.
    """
    if admission_deadline is None:
        _radio_io_lock.acquire()
    else:
        remaining = admission_deadline - time.monotonic()
        if remaining <= 0 or not _radio_io_lock.acquire(timeout=remaining):
            raise RadioIODeadlineError("FLEX socket I/O admission timed out")
    try:
        # asyncio cancellation cannot stop a worker thread that is already
        # waiting for this lock. Recheck immediately before the operation so a
        # timed-out TX-on command can never run later when the lock is released.
        if cancel_event is not None and cancel_event.is_set():
            raise RadioIODeadlineError("FLEX socket I/O was cancelled before admission")
        if admission_deadline is not None and time.monotonic() >= admission_deadline:
            raise RadioIODeadlineError("FLEX socket I/O admission timed out")
        return operation()
    finally:
        _radio_io_lock.release()


async def run_radio_io(
    operation: Callable[[], Any],
    *,
    timeout: float | None = None,
) -> Any:
    """Run serialized FLEX I/O with cancellation-safe queue admission.

    A timed-out executor future may keep running in its worker thread.  The
    cooperative cancellation marker and absolute admission deadline prevent a
    queued mutation (especially TUNE/MOX on) from executing after its caller
    has already timed out and started fail-safe cleanup.
    """
    loop = asyncio.get_running_loop()
    cancel_event = threading.Event()
    deadline = time.monotonic() + timeout if timeout is not None else None
    future = loop.run_in_executor(
        _radio_executor,
        partial(
            run_radio_io_sync,
            operation,
            cancel_event=cancel_event,
            admission_deadline=deadline,
        ),
    )
    try:
        if timeout is None:
            return await future
        return await asyncio.wait_for(future, timeout=max(0.01, float(timeout)))
    except (asyncio.CancelledError, TimeoutError):
        cancel_event.set()
        future.cancel()
        raise


def configure_radio_control(flex_instance=None, broadcast_func=None) -> RadioControlState:
    radio_control_state.flex = flex_instance
    if broadcast_func is not None:
        radio_control_state.broadcast_func = broadcast_func
    return radio_control_state


def configure_station_tx_guard(
    callback: Optional[Callable[[str, Callable[[], Any]], Awaitable[bool]]],
) -> None:
    """Install the station-owned executor for raw FLEX TX-on commands."""
    radio_control_state.station_tx_guard = callback


def configure_station_route_handler(
    callback: Optional[Callable[..., Awaitable[bool]]],
) -> None:
    """Install the station-owned executor for FLEX route mutations."""
    radio_control_state.station_route_handler = callback


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


async def _run(
    operation: Callable[[], Any],
    *,
    timeout: float = 3.0,
) -> Any:
    """Run one blocking Flex operation without blocking or racing the event loop."""
    async with _command_lock:
        try:
            result = await asyncio.wait_for(run_radio_io(operation), timeout=timeout)
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


async def _simple(
    method_name: str,
    args: tuple[Any, ...],
    state: dict[str, Any],
) -> dict[str, Any]:
    flex = _require_radio()
    method = getattr(flex, method_name)
    await _run(lambda: method(*args))
    await broadcast_status(state)
    return {"success": True, **state}


async def _sync_elecraft(flex: Any) -> None:
    """Immediately mirror a successful OM0RX tune to the Elecraft chain."""
    try:
        from radio_control.elecraft import get_elecraft_manager

        await get_elecraft_manager().sync_radio_state(
            getattr(flex, "current_freq", None),
            getattr(flex, "current_mode", None),
        )
    except Exception:
        # The Flex command has already succeeded. Keep radio control usable and
        # let the background synchronizer retry an unavailable accessory.
        logger.exception("Could not immediately synchronize Elecraft devices")


async def set_frequency(req: FrequencyRequest):
    flex = _require_radio()
    await execute_station_route_change(
        "frequency",
        lambda: flex.tune_mhz(req.frequency),
    )
    result = {"success": True, "frequency": req.frequency}
    await broadcast_status({"frequency": req.frequency})
    await _sync_elecraft(_require_radio())
    return result


async def set_mode(req: ModeRequest):
    return await _simple("set_mode", (req.mode,), {"mode": req.mode})


async def set_band(req: BandRequest):
    flex = _require_radio()
    await execute_station_route_change("band", lambda: flex.set_band(req.band))
    await _sync_elecraft(flex)
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


async def _guarded_tx_on(
    action: str,
    method_name: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    handler = radio_control_state.station_tx_guard
    if handler is None:
        raise HTTPException(
            status_code=503,
            detail="Station transmit safety coordinator is unavailable",
        )
    flex = _require_radio()
    method = getattr(flex, method_name)
    try:
        result = await handler(action, lambda: method(True))
    except HTTPException:
        raise
    except Exception as exc:
        code = str(getattr(exc, "code", "station-tx-blocked"))
        message = str(getattr(exc, "message", str(exc)) or "Station transmit was blocked")
        status_code = int(getattr(exc, "status_code", 409) or 409)
        raise HTTPException(status_code=status_code, detail=f"{code}: {message}") from exc
    if result is not True:
        raise HTTPException(status_code=409, detail="Station rejected the transmit command")
    await broadcast_status(state)
    return {"success": True, **state}


async def execute_station_route_change(
    reason: str,
    operation: Callable[[], Any],
    *,
    allow_digital_owner: bool = False,
) -> bool:
    handler = radio_control_state.station_route_handler
    if handler is None:
        raise HTTPException(
            status_code=503,
            detail="Station route safety coordinator is unavailable",
        )
    try:
        result = await handler(
            reason,
            operation,
            allow_digital_owner=allow_digital_owner,
        )
    except HTTPException:
        raise
    except Exception as exc:
        code = str(getattr(exc, "code", "station-route-blocked"))
        message = str(getattr(exc, "message", str(exc)) or "Station route change was blocked")
        status_code = int(getattr(exc, "status_code", 409) or 409)
        raise HTTPException(status_code=status_code, detail=f"{code}: {message}") from exc
    if result is not True:
        raise HTTPException(status_code=409, detail="Station rejected the route change")
    return True


async def toggle_mox(req: ToggleRequest):
    if req.enabled:
        return await _guarded_tx_on("mox", "set_mox", {"mox": True})
    return await _simple("set_mox", (False,), {"mox": False})


async def toggle_tune(req: ToggleRequest):
    if req.enabled:
        raise HTTPException(
            status_code=410,
            detail="Raw TUNE-on is retired; use the guarded station tune workflow",
        )
    return await _simple("set_tune", (False,), {"tune": False})


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
