"""Safety-gated station coordinator and read-only telemetry API."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StrictBool, field_validator

from backend.core.context import get_app_context
from radio_control import config
from services.elecraft_station import StationActionError
from services.station_commissioning import build_commissioning_readiness
from services.station_configuration import (
    build_configuration_snapshot,
    preview_configuration_restore,
)
from services.station_training import TrainingPreviewRequest, build_training_preview
from services.station_training_jobs import TrainingJobError


router = APIRouter(prefix="/api/station", tags=["station"])
StationAction = Literal["prepare-route", "standby", "operate", "tune", "cancel"]

_STREAM_VOLATILE_KEYS = frozenset(
    {
        "age_seconds",
        "generated_at",
        "observed_at",
        "updated_at",
    }
)
_WIDGET_PREFERENCES_PATH = Path(__file__).resolve().parents[2] / "settings" / "station_widget.json"
_WIDGET_PREFERENCES_LOCK = asyncio.Lock()


class TrainingPreviewBody(BaseModel):
    bands: list[str] = Field(default_factory=list, max_length=11)
    frequency_points_mhz: dict[str, list[float]] = Field(default_factory=dict)
    portions: list[Literal["cw", "data", "ssb"]] = Field(default_factory=list, max_length=3)
    coverage: Literal["representative", "full_bins"] = "representative"
    erase_selected_memories: StrictBool = False

    @field_validator("frequency_points_mhz")
    @classmethod
    def validate_points(cls, value: dict[str, list[float]]) -> dict[str, list[float]]:
        if sum(len(points) for points in value.values()) > 100:
            raise ValueError("training preview cannot exceed 100 frequency points")
        if any(len(points) > 20 for points in value.values()):
            raise ValueError("each band is limited to 20 frequency points")
        return value


class TrainingJobCreateBody(TrainingPreviewBody):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["train", "survey"] = "train"
    operator_confirmed: StrictBool = False
    typed_confirmation: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
        validation_alias=AliasChoices("typed_confirmation", "confirmation"),
    )
    legal_operation_confirmed: StrictBool = False
    approved_load_confirmed: StrictBool = False
    digital_engine_inhibit_confirmed: StrictBool = False
    vendor_backup_confirmed: StrictBool = Field(
        default=False,
        validation_alias=AliasChoices("vendor_backup_confirmed", "backup_confirmed"),
    )


class ConfigurationRestorePreviewBody(BaseModel):
    snapshot: dict[str, Any]


class CommissioningEvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    physical_key_interrupt_verified: StrictBool = False
    antenna_routes_names_verified: StrictBool = False
    vendor_backups_captured: StrictBool = False
    dummy_load_or_approved_antenna_connected: StrictBool = False
    digital_engine_inhibit_verified: StrictBool = False


class WidgetPreferencesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orientation: Literal["horizontal", "vertical"] | None = None
    width: int | None = Field(default=None, ge=300, le=1800)
    height: int | None = Field(default=None, ge=180, le=1100)


def _default_widget_preferences() -> dict[str, Any]:
    return {
        "orientation": "horizontal",
        "sizes": {
            "horizontal": {"width": 1120, "height": 250},
            "vertical": {"width": 430, "height": 690},
        },
    }


def _load_widget_preferences() -> dict[str, Any]:
    defaults = _default_widget_preferences()
    try:
        payload = json.loads(_WIDGET_PREFERENCES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return defaults
    orientation = payload.get("orientation")
    if orientation in {"horizontal", "vertical"}:
        defaults["orientation"] = orientation
    sizes = payload.get("sizes") if isinstance(payload.get("sizes"), dict) else {}
    for name in ("horizontal", "vertical"):
        size = sizes.get(name) if isinstance(sizes.get(name), dict) else {}
        width = size.get("width")
        height = size.get("height")
        if isinstance(width, int) and isinstance(height, int) and 300 <= width <= 1800 and 180 <= height <= 1100:
            defaults["sizes"][name] = {"width": width, "height": height}
    return defaults


def _save_widget_preferences(preferences: dict[str, Any]) -> None:
    _WIDGET_PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _WIDGET_PREFERENCES_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(preferences, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(_WIDGET_PREFERENCES_PATH)


def _coordinator(request: Request):
    coordinator = get_app_context(request).station_coordinator
    if coordinator is None:
        raise HTTPException(status_code=503, detail="Station coordinator is unavailable")
    return coordinator


def _telemetry(request: Request):
    telemetry = get_app_context(request).station_telemetry
    if telemetry is None:
        raise HTTPException(status_code=503, detail="Station telemetry is unavailable")
    return telemetry


def _training_manager(request: Request):
    manager = get_app_context(request).station_training_manager
    if manager is None:
        raise HTTPException(status_code=503, detail="Station training service is unavailable")
    return manager


def _stable_stream_value(value: Any) -> Any:
    """Remove clock-only fields so unchanged station state is not re-sent."""
    if isinstance(value, dict):
        return {
            key: _stable_stream_value(item)
            for key, item in value.items()
            if key not in _STREAM_VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_stable_stream_value(item) for item in value]
    return value


def _station_stream_payload(coordinator: Any) -> dict[str, Any]:
    state = coordinator.snapshot()
    status = coordinator.elecraft.snapshot()
    return {
        "status": {**status, "path": state.get("path")},
        "station_state": state,
    }


async def _station_event_stream(request: Request, coordinator: Any):
    fingerprint: str | None = None
    last_keepalive = time.monotonic()
    yield "retry: 1000\n\n"
    while not await request.is_disconnected():
        payload = _station_stream_payload(coordinator)
        stable_payload = _stable_stream_value(payload)
        current = json.dumps(stable_payload, sort_keys=True, separators=(",", ":"), default=str)
        if current != fingerprint:
            fingerprint = current
            encoded = json.dumps(payload, separators=(",", ":"), default=str)
            yield f"event: station\ndata: {encoded}\n\n"
            last_keepalive = time.monotonic()
        elif time.monotonic() - last_keepalive >= 15.0:
            yield ": keepalive\n\n"
            last_keepalive = time.monotonic()
        await asyncio.sleep(0.25)


def _time_range(
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime]:
    resolved_end = end or datetime.now(UTC)
    resolved_start = start or resolved_end - timedelta(hours=24)
    if resolved_start.tzinfo is None:
        resolved_start = resolved_start.replace(tzinfo=UTC)
    if resolved_end.tzinfo is None:
        resolved_end = resolved_end.replace(tzinfo=UTC)
    if resolved_end <= resolved_start:
        raise HTTPException(status_code=422, detail="end must be after start")
    if resolved_end - resolved_start > timedelta(days=31):
        raise HTTPException(status_code=422, detail="station history range cannot exceed 31 days")
    return resolved_start, resolved_end


@router.get("/widget-preferences")
async def widget_preferences():
    return {"success": True, "preferences": _load_widget_preferences()}


@router.put("/widget-preferences")
async def save_widget_preferences(body: WidgetPreferencesBody):
    if (body.width is None) != (body.height is None):
        raise HTTPException(status_code=422, detail="width and height must be supplied together")
    async with _WIDGET_PREFERENCES_LOCK:
        preferences = _load_widget_preferences()
        if body.orientation is not None:
            preferences["orientation"] = body.orientation
        if body.width is not None and body.height is not None:
            orientation = body.orientation or preferences["orientation"]
            preferences["sizes"][orientation] = {"width": body.width, "height": body.height}
        _save_widget_preferences(preferences)
    return {"success": True, "preferences": preferences}


@router.get("/state")
async def station_state(request: Request, refresh: bool = False):
    coordinator = _coordinator(request)
    state = await coordinator.refresh_snapshot() if refresh else coordinator.snapshot()
    return {"success": True, "station_state": state}


@router.get("/stream")
async def station_stream(request: Request):
    """Push cached station changes without repeatedly repainting the widget."""
    coordinator = _coordinator(request)
    return StreamingResponse(
        _station_event_stream(request, coordinator),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/path")
async def station_path(request: Request, refresh: bool = False):
    coordinator = _coordinator(request)
    state = await coordinator.refresh_snapshot() if refresh else coordinator.snapshot()
    return {"success": True, "path": state["path"]}


@router.get("/alarms")
async def station_alarms(request: Request):
    """Return normalized alarms from the cached coordinator snapshot only."""
    state = _coordinator(request).snapshot()
    return {"success": True, "alarms": state["alarms"]}


@router.get("/capabilities")
async def station_capabilities(request: Request):
    coordinator = _coordinator(request)
    training_manager = get_app_context(request).station_training_manager
    kpa = coordinator.elecraft.kpa500
    kat = coordinator.elecraft.kat500
    return {
        "success": True,
        "commissioned": coordinator.commissioned,
        "actions": ["prepare-route", "standby", "operate", "tune", "cancel"],
        "kpa500": {
            "configured": kpa is not None,
            "exact_readback": bool(kpa and hasattr(kpa, "readback")),
        },
        "kat500": {
            "configured": kat is not None,
            "exact_readback": bool(kat and hasattr(kat, "readback")),
            "nonstoring_tune": bool(kat and hasattr(kat, "start_tune")),
            "explicit_memory_store": bool(kat and hasattr(kat, "store_memory")),
            "selective_memory_clear_protocol": bool(
                kat and hasattr(kat, "clear_frequency_memories")
            ),
        },
        "atu_auto_setup": {
            "preview": True,
            "single_or_multi_band": True,
            "segment_aware": True,
            "swr_plot": True,
            "swr_survey": bool(training_manager),
            "profile_history": True,
            "execution": training_manager is not None,
            "single_active_job": True,
            "maximum_points": 100,
            "active_job_id": training_manager.active_job_id if training_manager else None,
            "create_endpoint": "/api/station/training/jobs",
            "list_endpoint": "/api/station/training/jobs",
            "job_endpoint": "/api/station/training/jobs/{job_id}",
            "cancel_endpoint": "/api/station/training/jobs/{job_id}/cancel",
            "memory_clear_endpoint": bool(
                training_manager and kat and hasattr(kat, "clear_frequency_memories")
            ),
        },
        "maintenance": {
            "active": bool(coordinator.snapshot().get("maintenance")),
            "enter_endpoint": "/api/station/maintenance/enter",
            "exit_endpoint": "/api/station/maintenance/exit",
            "firmware_update": False,
            "bulk_backup_restore": False,
            "official_utility_required": True,
        },
        "configuration": {
            "snapshot": True,
            "restore_preview": True,
            "restore_apply": False,
        },
        "commissioning": {
            "readiness_evaluation": True,
            "receive_only": True,
            "low_power_test": True,
            "enable_from_web": False,
        },
    }


def _training_preview(coordinator, body: TrainingPreviewBody | None = None):
    request = TrainingPreviewRequest(
        bands=tuple(body.bands) if body else (),
        frequency_points_mhz=(
            {
                str(band).strip().lower(): tuple(points)
                for band, points in body.frequency_points_mhz.items()
            }
            if body
            else None
        ),
        portions=tuple(body.portions) if body else (),
        coverage=body.coverage if body else "representative",
        erase_selected_memories=body.erase_selected_memories if body else False,
    )
    return build_training_preview(coordinator.elecraft.antenna_policy, request)


def _decorate_training_preview(request: Request, preview: dict[str, Any]) -> dict[str, Any]:
    manager = get_app_context(request).station_training_manager
    if manager is None:
        blockers = [
            {
                "code": "training-service-unavailable",
                "message": "Station training execution service is unavailable",
            }
        ]
    else:
        blockers = manager.cached_execution_blockers(preview)
    preview["execution_available"] = bool(manager is not None and not blockers)
    preview["execution_blockers"] = blockers
    preview["create_job_endpoint"] = "/api/station/training/jobs"
    preview["erase_plan"]["execution_available"] = bool(
        preview["execution_available"]
        and preview["erase_plan"]["requested"]
        and manager is not None
        and hasattr(
            getattr(getattr(manager.coordinator, "elecraft", None), "kat500", None),
            "clear_frequency_memories",
        )
    )
    return preview


@router.get("/training/preview")
async def default_training_preview(request: Request):
    preview = _training_preview(_coordinator(request))
    return {"success": True, "training_preview": _decorate_training_preview(request, preview)}


@router.post("/training/preview")
async def custom_training_preview(body: TrainingPreviewBody, request: Request):
    preview = _training_preview(_coordinator(request), body)
    return {
        "success": True,
        "training_preview": _decorate_training_preview(request, preview),
    }


def _training_job_error(exc: TrainingJobError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "execution_blockers": exc.blockers,
        },
    )


@router.post("/training/jobs", status_code=202)
async def create_training_job(body: TrainingJobCreateBody, request: Request):
    coordinator = _coordinator(request)
    preview = _training_preview(coordinator, body)
    preview = _decorate_training_preview(request, preview)
    try:
        job = await _training_manager(request).create_job(
            preview,
            operation=body.operation,
            operator_confirmed=body.operator_confirmed,
            confirmation=body.typed_confirmation or "",
            legal_operation_confirmed=body.legal_operation_confirmed,
            approved_load_confirmed=body.approved_load_confirmed,
            digital_engine_inhibit_confirmed=body.digital_engine_inhibit_confirmed,
            vendor_backup_confirmed=body.vendor_backup_confirmed,
        )
    except TrainingJobError as exc:
        raise _training_job_error(exc) from exc
    return {"success": True, "training_job": job}


@router.get("/training/jobs")
async def list_training_jobs(request: Request):
    manager = _training_manager(request)
    return {
        "success": True,
        "active_job_id": manager.active_job_id,
        "training_jobs": manager.list_jobs(),
    }


@router.get("/training/jobs/active")
async def get_active_training_job(request: Request):
    return {
        "success": True,
        "training_job": _training_manager(request).get_active_job(),
    }


@router.get("/training/jobs/{job_id}")
async def get_training_job(job_id: str, request: Request):
    try:
        job = _training_manager(request).get_job(job_id)
    except TrainingJobError as exc:
        raise _training_job_error(exc) from exc
    return {"success": True, "training_job": job}


@router.post("/training/jobs/{job_id}/cancel")
async def cancel_training_job(job_id: str, request: Request):
    try:
        job = await _training_manager(request).cancel_job(job_id)
    except TrainingJobError as exc:
        raise _training_job_error(exc) from exc
    return {"success": True, "training_job": job}


@router.get("/configuration/snapshot")
async def configuration_snapshot(request: Request):
    """Export a cached, semantic station configuration without live device I/O."""
    coordinator = _coordinator(request)
    return {
        "success": True,
        "configuration_snapshot": build_configuration_snapshot(coordinator.elecraft),
    }


@router.post("/configuration/restore-preview")
async def configuration_restore_preview(
    body: ConfigurationRestorePreviewBody,
    request: Request,
):
    """Validate and diff a snapshot; intentionally provides no apply operation."""
    _coordinator(request)
    try:
        preview = preview_configuration_restore(body.snapshot)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "restore_preview": preview}


def _commissioning_report(coordinator, evidence: dict[str, bool]) -> dict[str, Any]:
    return build_commissioning_readiness(
        coordinator.snapshot(),
        coordinator.elecraft.snapshot(),
        evidence,
        station_config=config,
    )


@router.get("/commissioning/readiness")
async def commissioning_readiness(request: Request):
    """Evaluate cached readiness with no hardware I/O or persisted attestation."""
    report = _commissioning_report(_coordinator(request), {})
    return {"success": True, "readiness": report}


@router.post("/commissioning/readiness")
async def evaluate_commissioning_evidence(
    body: CommissioningEvidenceBody,
    request: Request,
):
    """Preview readiness using five explicit operator attestations only."""
    report = _commissioning_report(
        _coordinator(request),
        body.model_dump(),
    )
    return {"success": True, "readiness": report}


@router.post("/actions/{action}")
async def station_action(action: StationAction, request: Request):
    coordinator = _coordinator(request)
    try:
        state = await coordinator.perform(action)
    except StationActionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"{exc.code}: {exc.message}",
        ) from exc
    return {"success": True, "station_state": state}


@router.post("/maintenance/enter")
async def enter_station_maintenance(request: Request):
    coordinator = _coordinator(request)
    try:
        state = await coordinator.enter_maintenance()
    except StationActionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"{exc.code}: {exc.message}",
        ) from exc
    return {"success": True, "station_state": state}


@router.post("/maintenance/exit")
async def exit_station_maintenance(request: Request):
    coordinator = _coordinator(request)
    try:
        state = await coordinator.exit_maintenance()
    except StationActionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"{exc.code}: {exc.message}",
        ) from exc
    return {"success": True, "station_state": state}


@router.get("/telemetry")
async def station_telemetry(
    request: Request,
    metric: str,
    start: datetime | None = None,
    end: datetime | None = None,
    bucket_seconds: int | None = Query(default=None, ge=1, le=86400),
    limit: int = Query(default=1000, ge=1, le=5000),
):
    resolved_start, resolved_end = _time_range(start, end)
    result = await asyncio.to_thread(
        _telemetry(request).query_telemetry,
        metric,
        resolved_start,
        resolved_end,
        bucket_seconds=bucket_seconds,
        limit=limit,
    )
    return {
        "success": True,
        "available": result.available,
        "reason": result.reason,
        "records": result.records,
    }


@router.get("/events")
async def station_events(
    request: Request,
    start: datetime | None = None,
    end: datetime | None = None,
    event_type: str | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
):
    resolved_start, resolved_end = _time_range(start, end)
    result = await asyncio.to_thread(
        _telemetry(request).query_events,
        resolved_start,
        resolved_end,
        event_type=event_type,
        limit=limit,
    )
    return {
        "success": True,
        "available": result.available,
        "reason": result.reason,
        "records": result.records,
    }


@router.get("/tunes")
async def station_tunes(
    request: Request,
    start: datetime | None = None,
    end: datetime | None = None,
    route_id: str | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
):
    resolved_start, resolved_end = _time_range(start, end)
    result = await asyncio.to_thread(
        _telemetry(request).query_tune_results,
        resolved_start,
        resolved_end,
        route_id=route_id,
        limit=limit,
    )
    return {
        "success": True,
        "available": result.available,
        "reason": result.reason,
        "records": result.records,
    }
