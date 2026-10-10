"""In-memory, single-owner ATU training job orchestration.

This layer owns job state only.  Every hardware operation is delegated to the
commissioned :class:`StationCoordinator`, which serializes FLEX and Elecraft
I/O and re-establishes carrier-off/KPA-standby on every exit path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from services.elecraft_station import StationActionError
from services.station_training import MAX_TRAINING_POINTS


logger = logging.getLogger(__name__)
TERMINAL_STATES = {"succeeded", "completed_with_failures", "failed", "cancelled"}
RETRYABLE_PRE_CARRIER_ERRORS = {
    "flex-tx-proof-timeout",
    "flex-tx-state-unconfirmed",
}
RECOVERABLE_POINT_ERRORS = {
    # A valid on-carrier result above the configured target is local to this
    # frequency/antenna. The coordinator has already forced carrier-off and
    # confirmed amplifier standby before returning the failed transaction.
    "tune-target-not-met",
}
PRE_CARRIER_STEPS = {
    "training-qsy-preflight",
    "confirming-receive",
    "rechecking-route",
    "amplifier-standby",
    "selecting-flex-port",
    "selecting-elecraft-route",
    "verifying-readback",
    "arming-tuner",
}
MAX_POINT_ATTEMPTS = 2
MAX_JOB_EVENTS = 250
POINT_WATCHDOG_GRACE_SECONDS = 12.0
MIN_POINT_WATCHDOG_SECONDS = 20.0
MAX_POINT_WATCHDOG_SECONDS = 75.0


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class TrainingJobError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        blockers: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.blockers = blockers or []


class TrainingJobManager:
    """Run at most one bounded ATU training plan at a time."""

    def __init__(self, coordinator: Any, *, history_limit: int = 25) -> None:
        self.coordinator = coordinator
        self.history_limit = max(1, int(history_limit))
        self._jobs: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _safe_error(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        return {
            "code": str(value.get("code") or "training-error"),
            "message": str(value.get("message") or "Training operation failed"),
        }

    @staticmethod
    def _point_watchdog_seconds(point: dict[str, Any]) -> float:
        """Cap one point beyond its planner budget without allowing a UI hang."""
        try:
            planned = float(point.get("worst_case_seconds") or 0.0)
        except (TypeError, ValueError):
            planned = 0.0
        return max(
            MIN_POINT_WATCHDOG_SECONDS,
            min(MAX_POINT_WATCHDOG_SECONDS, planned + POINT_WATCHDOG_GRACE_SECONDS),
        )

    def _record_job_event(
        self,
        job: dict[str, Any],
        event: str,
        *,
        level: str = "info",
        **fields: Any,
    ) -> dict[str, Any]:
        """Append and log one bounded, secret-free training diagnostic event."""
        events = job.setdefault("events", [])
        record = {
            "sequence": int(job.get("event_sequence") or 0) + 1,
            "occurred_at": _utc_now(),
            "event": str(event),
            "job_id": str(job.get("id") or ""),
        }
        allowed = {
            "job_state",
            "step",
            "point_sequence",
            "frequency_mhz",
            "attempt",
            "duration_ms",
            "transaction_id",
            "swr_before",
            "swr_after",
            "error",
            "completed_count",
            "processed_count",
            "failed_point_count",
            "point_count",
            "requested_point_count",
            "skipped_point_count",
        }
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "error":
                value = self._safe_error(value)
            record[key] = value
        job["event_sequence"] = record["sequence"]
        events.append(record)
        if len(events) > MAX_JOB_EVENTS:
            del events[:-MAX_JOB_EVENTS]
        log_method = getattr(logger, level, logger.info)
        log_method("ATU_TRAINING_EVENT %s", json.dumps(record, sort_keys=True))
        return record

    @property
    def active_job_id(self) -> str | None:
        for job_id, job in reversed(self._jobs.items()):
            if job["state"] not in TERMINAL_STATES:
                return job_id
        return None

    @staticmethod
    def _eligible_points(preview: dict[str, Any]) -> list[dict[str, Any]]:
        """Return only server-previewed points that policy allows to transmit."""
        return [
            point
            for point in list(preview.get("points") or [])
            if point.get("eligible") is True
        ]

    def cached_execution_blockers(self, preview: dict[str, Any]) -> list[dict[str, str]]:
        blockers: list[dict[str, str]] = []
        if preview.get("valid") is not True:
            blockers.append(
                {
                    "code": "training-preview-invalid",
                    "message": "The server-derived training preview is not valid",
                }
            )
        points = self._eligible_points(preview)
        blockers.extend(self.coordinator.training_execution_blockers(points))
        return blockers

    def list_jobs(self) -> list[dict[str, Any]]:
        return [deepcopy(job) for job in reversed(self._jobs.values())]

    def get_active_job(self) -> dict[str, Any] | None:
        job_id = self.active_job_id
        return deepcopy(self._jobs[job_id]) if job_id else None

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(str(job_id))
        if job is None:
            raise TrainingJobError(
                "training-job-not-found",
                f"Training job {job_id} was not found",
                status_code=404,
            )
        return deepcopy(job)

    @staticmethod
    def _request_blockers(
        preview: dict[str, Any],
        *,
        operation: str,
        operator_confirmed: bool,
        confirmation: str,
        legal_operation_confirmed: bool,
        approved_load_confirmed: bool,
        digital_engine_inhibit_confirmed: bool,
        vendor_backup_confirmed: bool,
    ) -> list[dict[str, str]]:
        blockers: list[dict[str, str]] = []
        preview_points = list(preview.get("points") or [])
        points = TrainingJobManager._eligible_points(preview)
        if preview.get("valid") is not True or not preview_points:
            blockers.append(
                {
                    "code": "training-preview-invalid",
                    "message": "A non-empty, validation-error-free server preview is required",
                }
            )
        if not points or len(points) > MAX_TRAINING_POINTS:
            blockers.append(
                {
                    "code": "training-points-ineligible",
                    "message": "The plan must contain at least one eligible point and at most 100 executable points",
                }
            )
        legacy_confirmation_valid = bool(
            confirmation and confirmation == preview.get("required_confirmation")
        )
        if not operator_confirmed and not legacy_confirmation_valid:
            blockers.append(
                {
                    "code": "operator-confirmation-required",
                    "message": "The final Yes/No RF confirmation was not accepted",
                }
            )
        if operation == "survey" and bool((preview.get("erase_plan") or {}).get("requested")):
            blockers.append(
                {
                    "code": "survey-erase-not-allowed",
                    "message": "An SWR survey cannot erase tuner memories",
                }
            )
        attestations = (
            (legal_operation_confirmed, "legal-operation-unconfirmed", "Legal operation is not confirmed"),
            (approved_load_confirmed, "approved-load-unconfirmed", "Approved antenna or load is not confirmed"),
            (
                digital_engine_inhibit_confirmed,
                "digital-engine-inhibit-unconfirmed",
                "Digital engine inhibit is not confirmed",
            ),
        )
        for confirmed, code, message in attestations:
            if not confirmed:
                blockers.append({"code": code, "message": message})
        erase_requested = bool((preview.get("erase_plan") or {}).get("requested"))
        if erase_requested and not vendor_backup_confirmed:
            blockers.append(
                {
                    "code": "vendor-backup-unconfirmed",
                    "message": "A vendor utility backup is required before selective erase",
                }
            )
        return blockers

    async def create_job(
        self,
        preview: dict[str, Any],
        *,
        operation: str = "train",
        operator_confirmed: bool = False,
        confirmation: str = "",
        legal_operation_confirmed: bool,
        approved_load_confirmed: bool,
        digital_engine_inhibit_confirmed: bool,
        vendor_backup_confirmed: bool,
    ) -> dict[str, Any]:
        operation = str(operation or "train").strip().lower()
        if operation not in {"train", "survey"}:
            raise TrainingJobError(
                "training-operation-invalid",
                "Training operation must be train or survey",
                status_code=422,
            )
        blockers = self._request_blockers(
            preview,
            operation=operation,
            operator_confirmed=operator_confirmed,
            confirmation=confirmation,
            legal_operation_confirmed=legal_operation_confirmed,
            approved_load_confirmed=approved_load_confirmed,
            digital_engine_inhibit_confirmed=digital_engine_inhibit_confirmed,
            vendor_backup_confirmed=vendor_backup_confirmed,
        )
        if blockers:
            logger.warning(
                "ATU_TRAINING_PREFLIGHT_BLOCKED %s",
                json.dumps(
                    {
                        "occurred_at": _utc_now(),
                        "blocker_codes": [str(item.get("code") or "unknown") for item in blockers],
                    },
                    sort_keys=True,
                ),
            )
            raise TrainingJobError(
                "training-request-blocked",
                "Training request did not satisfy every execution requirement",
                status_code=422,
                blockers=blockers,
            )

        async with self._lock:
            active_id = self.active_job_id
            if active_id:
                raise TrainingJobError(
                    "training-job-active",
                    f"Training job {active_id} is already active",
                    status_code=409,
                    blockers=[
                        {
                            "code": "training-job-active",
                            "message": f"Training job {active_id} is already active",
                        }
                    ],
                )

            job_id = uuid.uuid4().hex
            executable_points = self._eligible_points(preview)
            skipped_points = [
                deepcopy(point)
                for point in list(preview.get("points") or [])
                if point.get("eligible") is not True
            ]
            try:
                self.coordinator.claim_training(job_id)
                live_blockers = await self.coordinator.fresh_training_execution_blockers(
                    executable_points,
                    job_id=job_id,
                )
            except StationActionError as exc:
                live_blockers = [{"code": exc.code, "message": exc.message}]
            except Exception as exc:
                live_blockers = [
                    {
                        "code": "training-preflight-failed",
                        "message": f"Training preflight failed: {exc}",
                    }
                ]
            if live_blockers:
                self.coordinator.abandon_training_claim(job_id)
                raise TrainingJobError(
                    "training-preflight-blocked",
                    "Live station preflight blocked training",
                    status_code=409,
                    blockers=live_blockers,
                )

            now = _utc_now()
            points = deepcopy(executable_points)
            job = {
                "schema_version": 1,
                "id": job_id,
                "state": "queued",
                "operation": operation,
                "step": "queued",
                "created_at": now,
                "started_at": None,
                "finished_at": None,
                "cancel_requested": False,
                "point_count": len(points),
                "requested_point_count": len(list(preview.get("points") or [])),
                "skipped_point_count": len(skipped_points),
                "skipped_points": skipped_points,
                "completed_count": 0,
                "processed_count": 0,
                "failed_point_count": 0,
                "current_sequence": None,
                "current_frequency_mhz": None,
                "progress_percent": 0,
                "erase_requested": bool(preview["erase_plan"]["requested"]),
                "erase_results": [],
                "points": points,
                "results": [],
                "error": None,
                "execution_blockers": [],
                "event_sequence": 0,
                "events": [],
            }
            self._jobs[job_id] = job
            self._record_job_event(
                job,
                "job.queued",
                job_state="queued",
                step="queued",
                point_count=len(points),
                requested_point_count=job["requested_point_count"],
                skipped_point_count=job["skipped_point_count"],
            )
            while len(self._jobs) > self.history_limit:
                oldest_id = next(iter(self._jobs))
                self._jobs.pop(oldest_id, None)
                self._tasks.pop(oldest_id, None)
                self._cancel_events.pop(oldest_id, None)
            cancel_event = asyncio.Event()
            self._cancel_events[job_id] = cancel_event
            task = asyncio.create_task(
                self._run_job(job_id),
                name=f"station_training_{job_id}",
            )
            self._tasks[job_id] = task
            return deepcopy(job)

    def _erase_scopes(self, job: dict[str, Any]) -> list[dict[str, Any]]:
        scopes: list[dict[str, Any]] = []
        for point in job["points"]:
            scope = {
                "band": point["band"],
                "kat_antenna": point["kat_antenna"],
                "frequency_mhz": point["frequency_mhz"],
            }
            if not any(
                item["band"] == scope["band"]
                and item["kat_antenna"] == scope["kat_antenna"]
                for item in scopes
            ):
                scopes.append(scope)
        return scopes

    async def _run_job(self, job_id: str) -> None:
        job = self._jobs[job_id]
        cancel_event = self._cancel_events[job_id]
        job.update(state="running", step="preflight", started_at=_utc_now())
        self._record_job_event(
            job,
            "job.started",
            job_state="running",
            step="preflight",
            point_count=job["point_count"],
        )
        try:
            if job["erase_requested"]:
                job["step"] = "selective-memory-erase"
                self._record_job_event(
                    job,
                    "erase.started",
                    job_state="running",
                    step=job["step"],
                )
                job["erase_results"] = await self.coordinator.clear_training_memories(
                    job_id,
                    self._erase_scopes(job),
                )
                self._record_job_event(
                    job,
                    "erase.completed",
                    job_state="running",
                    step=job["step"],
                )

            for point in job["points"]:
                if cancel_event.is_set():
                    job["state"] = "cancelled"
                    job["step"] = "cancelled"
                    break
                sequence = int(point["sequence"])
                job["current_sequence"] = sequence
                job["current_frequency_mhz"] = point["frequency_mhz"]
                job["step"] = "training-point"
                transaction: dict[str, Any] = {}
                attempts: list[dict[str, Any]] = []
                point_started = time.monotonic()
                for attempt in range(1, MAX_POINT_ATTEMPTS + 1):
                    attempt_started = time.monotonic()
                    self._record_job_event(
                        job,
                        "point.started" if attempt == 1 else "point.retry_started",
                        job_state="running",
                        step="training-point",
                        point_sequence=sequence,
                        frequency_mhz=point["frequency_mhz"],
                        attempt=attempt,
                    )
                    try:
                        executor = (
                            self.coordinator.execute_swr_survey_point
                            if job["operation"] == "survey"
                            else self.coordinator.execute_training_point
                        )
                        watchdog_seconds = self._point_watchdog_seconds(point)
                        transaction = await asyncio.wait_for(
                            executor(job_id, point),
                            timeout=watchdog_seconds,
                        )
                    except asyncio.TimeoutError:
                        logger.error(
                            "ATU training point watchdog expired job=%s sequence=%s frequency=%s",
                            job_id,
                            sequence,
                            point["frequency_mhz"],
                        )
                        transaction = {
                            "state": "failed",
                            "step": "point-watchdog-timeout",
                            "progress": 0,
                            "error": {
                                "code": "training-point-watchdog-timeout",
                                "message": (
                                    "The point exceeded its bounded execution time; "
                                    "the run was stopped and fail-safe cleanup was requested"
                                ),
                            },
                        }
                    except StationActionError as exc:
                        transaction = {
                            "state": "failed",
                            "step": "training-qsy-preflight",
                            "progress": 0,
                            "error": {"code": exc.code, "message": exc.message},
                        }
                    except Exception as exc:
                        logger.exception(
                            "Unexpected ATU training point exception job=%s sequence=%s",
                            job_id,
                            sequence,
                        )
                        transaction = {
                            "state": "failed",
                            "step": "training-qsy-preflight",
                            "progress": 0,
                            "error": {
                                "code": "training-point-exception",
                                "message": str(exc),
                            },
                        }
                    attempt_duration_ms = round((time.monotonic() - attempt_started) * 1000)
                    attempt_summary = {
                        "attempt": attempt,
                        "state": str(transaction.get("state") or "failed"),
                        "step": str(transaction.get("step") or "unknown"),
                        "duration_ms": attempt_duration_ms,
                        "transaction_id": transaction.get("id"),
                        "error": self._safe_error(transaction.get("error")),
                    }
                    attempts.append(attempt_summary)
                    if attempt_summary["state"] == "succeeded":
                        break
                    error_code = str((attempt_summary.get("error") or {}).get("code") or "")
                    retryable = (
                        attempt < MAX_POINT_ATTEMPTS
                        and error_code in RETRYABLE_PRE_CARRIER_ERRORS
                        and attempt_summary["step"] in PRE_CARRIER_STEPS
                        and not cancel_event.is_set()
                    )
                    self._record_job_event(
                        job,
                        "point.retry_scheduled" if retryable else "point.attempt_failed",
                        level="warning",
                        job_state="running",
                        step=attempt_summary["step"],
                        point_sequence=sequence,
                        frequency_mhz=point["frequency_mhz"],
                        attempt=attempt,
                        duration_ms=attempt_duration_ms,
                        transaction_id=attempt_summary["transaction_id"],
                        error=attempt_summary["error"],
                    )
                    if not retryable:
                        break
                    await asyncio.sleep(0.35)
                state = str(transaction.get("state") or "failed")
                result = {
                    "sequence": sequence,
                    "band": point["band"],
                    "frequency_mhz": point["frequency_mhz"],
                    "route_id": point["route_id"],
                    "status": state,
                    "swr_before": transaction.get("swr_before"),
                    "swr_after": transaction.get("swr_after"),
                    "transaction_id": transaction.get("id"),
                    "error": transaction.get("error"),
                    "step": transaction.get("step"),
                    "progress": transaction.get("progress"),
                    "attempt_count": len(attempts),
                    "attempts": attempts,
                    "duration_ms": round((time.monotonic() - point_started) * 1000),
                }
                if job["operation"] == "survey" and state == "succeeded":
                    measured = transaction.get("swr_before")
                    target = float(transaction.get("target_swr") or 1.5)
                    result["target_swr"] = target
                    result["needs_training"] = bool(
                        isinstance(measured, (int, float)) and float(measured) > target
                    )
                    result["status"] = (
                        "needs-training" if result["needs_training"] else "within-target"
                    )
                job["results"].append(result)
                job["processed_count"] += 1
                job["progress_percent"] = round(
                    job["processed_count"] * 100 / job["point_count"]
                )
                if state == "succeeded":
                    job["completed_count"] += 1
                    self._record_job_event(
                        job,
                        "point.completed",
                        job_state="running",
                        step=str(transaction.get("step") or "complete"),
                        point_sequence=sequence,
                        frequency_mhz=point["frequency_mhz"],
                        attempt=len(attempts),
                        duration_ms=result["duration_ms"],
                        transaction_id=transaction.get("id"),
                        swr_before=transaction.get("swr_before"),
                        swr_after=transaction.get("swr_after"),
                        completed_count=job["completed_count"],
                        point_count=job["point_count"],
                    )
                    continue
                if state == "cancelled" or cancel_event.is_set():
                    job["state"] = "cancelled"
                    job["step"] = "cancelled"
                else:
                    point_error = transaction.get("error") or {
                        "code": "training-point-failed",
                        "message": f"Training point {sequence} failed",
                    }
                    error_code = str(point_error.get("code") or "")
                    if error_code in RECOVERABLE_POINT_ERRORS:
                        job["failed_point_count"] += 1
                        self._record_job_event(
                            job,
                            "point.failed_continuing",
                            level="warning",
                            job_state="running",
                            step=str(transaction.get("step") or "failed"),
                            point_sequence=sequence,
                            frequency_mhz=point["frequency_mhz"],
                            attempt=len(attempts),
                            duration_ms=result["duration_ms"],
                            transaction_id=transaction.get("id"),
                            error=point_error,
                            completed_count=job["completed_count"],
                            processed_count=job["processed_count"],
                            failed_point_count=job["failed_point_count"],
                            point_count=job["point_count"],
                        )
                        continue
                    job["state"] = "failed"
                    job["step"] = "failed"
                    job["error"] = point_error
                    self._record_job_event(
                        job,
                        "point.failed",
                        level="error",
                        job_state="failed",
                        step=str(transaction.get("step") or "failed"),
                        point_sequence=sequence,
                        frequency_mhz=point["frequency_mhz"],
                        attempt=len(attempts),
                        duration_ms=result["duration_ms"],
                        transaction_id=transaction.get("id"),
                        error=job["error"],
                        completed_count=job["completed_count"],
                        point_count=job["point_count"],
                    )
                break
            else:
                if job["failed_point_count"]:
                    failed_count = job["failed_point_count"]
                    job.update(
                        state="completed_with_failures",
                        step="complete-with-failures",
                        progress_percent=100,
                        message=(
                            f"Training completed: {job['completed_count']} point(s) succeeded "
                            f"and {failed_count} point(s) did not meet the target."
                        ),
                    )
                else:
                    job.update(state="succeeded", step="complete", progress_percent=100)
        except asyncio.CancelledError:
            cancel_event.set()
            job.update(
                state="cancelled",
                step="cancelled",
                error={"code": "training-task-cancelled", "message": "Training task was cancelled"},
            )
        except StationActionError as exc:
            state = "cancelled" if cancel_event.is_set() else "failed"
            job.update(
                state=state,
                step=state,
                error={"code": exc.code, "message": exc.message},
            )
        except Exception as exc:
            logger.exception("Unexpected ATU training job failure")
            job.update(
                state="failed",
                step="failed",
                error={"code": "training-job-failed", "message": str(exc)},
            )
        finally:
            try:
                await self.coordinator.release_training(job_id)
                self._record_job_event(
                    job,
                    "safe_state.confirmed",
                    job_state=job["state"],
                    step="release-training",
                )
            except StationActionError as exc:
                job.update(
                    state="failed",
                    step="safe-state-unconfirmed",
                    error={"code": exc.code, "message": exc.message},
                )
                self._record_job_event(
                    job,
                    "safe_state.failed",
                    level="error",
                    job_state="failed",
                    step="safe-state-unconfirmed",
                    error=job["error"],
                )
            job["current_sequence"] = None
            job["finished_at"] = _utc_now()
            self._record_job_event(
                job,
                "job.finished",
                level=(
                    "error"
                    if job["state"] == "failed"
                    else "warning"
                    if job["state"] == "completed_with_failures"
                    else "info"
                ),
                job_state=job["state"],
                step=job["step"],
                completed_count=job["completed_count"],
                processed_count=job["processed_count"],
                failed_point_count=job["failed_point_count"],
                point_count=job["point_count"],
                error=job.get("error"),
            )

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        async with self._lock:
            job = self._jobs.get(str(job_id))
            if job is None:
                raise TrainingJobError(
                    "training-job-not-found",
                    f"Training job {job_id} was not found",
                    status_code=404,
                )
            if job["state"] in TERMINAL_STATES:
                return deepcopy(job)
            job["cancel_requested"] = True
            job["state"] = "cancelling"
            job["step"] = "cancelling"
            self._record_job_event(
                job,
                "job.cancel_requested",
                level="warning",
                job_state="cancelling",
                step="cancelling",
                completed_count=job["completed_count"],
                point_count=job["point_count"],
            )
            self._cancel_events[job_id].set()
        try:
            await self.coordinator.cancel_training(job_id)
        except StationActionError as exc:
            job["error"] = {"code": exc.code, "message": exc.message}
            if exc.status_code >= 500:
                job["state"] = "failed"
        return deepcopy(job)

    async def stop(self) -> None:
        active_id = self.active_job_id
        if not active_id:
            return
        await self.cancel_job(active_id)
        task = self._tasks.get(active_id)
        if task and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=10.0)
            except asyncio.TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
