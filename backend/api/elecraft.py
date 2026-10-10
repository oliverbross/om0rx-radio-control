"""HTTP controls for the Elecraft amplifier/tuner integration."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.core.context import get_app_context
from radio_control.elecraft import get_elecraft_manager


router = APIRouter(prefix="/api/elecraft", tags=["elecraft"])


class PowerRequest(BaseModel):
    on: bool


class OperateRequest(BaseModel):
    operate: bool


class TunerModeRequest(BaseModel):
    mode: Literal["auto", "manual", "bypass"]


class AntennaRequest(BaseModel):
    antenna: int = Field(ge=1, le=3)


async def _run_device(name: str, method: str, *args):
    raise HTTPException(
        status_code=410,
        detail=(
            "Direct Elecraft mutations are retired; use the guarded station "
            "coordinator workflow"
        ),
    )


async def _status_payload(request: Request | None, refresh: bool) -> dict:
    manager = get_elecraft_manager()
    status_snapshot = await manager.refresh_status() if refresh else manager.snapshot()
    if request is not None and hasattr(manager, "station_path"):
        context = get_app_context(request)
        status_snapshot = {
            **status_snapshot,
            "path": manager.station_path(dict(getattr(context, "radio_snapshot", {}) or {})),
        }
    return {"success": True, "status": status_snapshot}


@router.get("/status")
async def status(refresh: bool = False, request: Request = None):
    return await _status_payload(request, refresh)


@router.get("/path")
async def station_path(request: Request, refresh: bool = False):
    """Return normalized, read-only path evidence for the station dashboard."""
    payload = await _status_payload(request, refresh)
    return {"success": True, "path": payload["status"]["path"]}


@router.post("/connect")
async def connect():
    raise HTTPException(
        status_code=410,
        detail=(
            "Direct Elecraft lifecycle changes are retired; restart or "
            "reconfigure through the guarded station workflow"
        ),
    )


@router.post("/disconnect")
async def disconnect():
    raise HTTPException(
        status_code=410,
        detail=(
            "Direct Elecraft lifecycle changes are retired; restart or "
            "reconfigure through the guarded station workflow"
        ),
    )


@router.post("/kpa500/power")
async def kpa500_power(request: PowerRequest):
    return await _run_device("kpa500", "set_power", request.on)


@router.post("/kpa500/operate")
async def kpa500_operate(request: OperateRequest):
    return await _run_device("kpa500", "set_operate", request.operate)


@router.post("/kat500/power")
async def kat500_power(request: PowerRequest):
    return await _run_device("kat500", "set_power", request.on)


@router.post("/kat500/mode")
async def kat500_mode(request: TunerModeRequest):
    return await _run_device("kat500", "set_mode", request.mode)


@router.post("/kat500/antenna")
async def kat500_antenna(request: AntennaRequest):
    return await _run_device("kat500", "set_antenna", request.antenna)


@router.post("/kat500/tune")
async def kat500_tune():
    return await _run_device("kat500", "tune")
