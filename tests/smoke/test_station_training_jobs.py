from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.station import router
from backend.core.context import AppContext, install_app_context
from radio_control import config
from services.station_training import training_confirmation
from services.elecraft_station import StationActionError
from services.station_training_jobs import TrainingJobError, TrainingJobManager
import services.station_training_jobs as training_jobs


def preview(*, erase: bool = False, count: int = 2) -> dict:
    points = [
        {
            "sequence": index + 1,
            "band": "20m",
            "frequency_mhz": 14.05 + index * 0.02,
            "frequency_khz": round((14.05 + index * 0.02) * 1000),
            "route_id": "20m-flex-ant1-kat-ant2",
            "flex_tx_ant": "ANT1",
            "kat_antenna": 2,
            "eligible": True,
        }
        for index in range(count)
    ]
    return {
        "valid": True,
        "points": points,
        "required_confirmation": training_confirmation(points, erase=erase),
        "erase_plan": {"requested": erase},
    }


class FakeCoordinator:
    def __init__(self) -> None:
        self.elecraft = type(
            "FakeElecraft",
            (),
            {
                "antenna_policy": {"20m": 2},
                "kat500": type("FakeKat", (), {"clear_frequency_memories": lambda *_: True})(),
            },
        )()
        self.training_job_id = None
        self.calls: list[tuple] = []
        self.point_gate: asyncio.Event | None = None
        self.cancelled = False

    def training_execution_blockers(self, points, *, job_id=None):
        self.calls.append(("cached-preflight", len(points), job_id))
        return []

    def claim_training(self, job_id):
        self.calls.append(("claim", job_id))
        self.training_job_id = job_id

    def abandon_training_claim(self, job_id):
        self.calls.append(("abandon", job_id))
        if self.training_job_id == job_id:
            self.training_job_id = None

    async def fresh_training_execution_blockers(self, points, *, job_id):
        self.calls.append(("fresh-preflight", len(points), job_id))
        return []

    async def clear_training_memories(self, job_id, scopes):
        self.calls.append(("erase", job_id, scopes))
        return [{"band": item["band"], "kat_antenna": item["kat_antenna"]} for item in scopes]

    async def execute_training_point(self, job_id, point):
        self.calls.append(("point", job_id, point["sequence"]))
        if self.point_gate is not None:
            await self.point_gate.wait()
        if self.cancelled:
            return {
                "id": f"tx-{point['sequence']}",
                "state": "cancelled",
                "swr_before": None,
                "swr_after": None,
                "error": {"code": "tune-cancelled", "message": "Tune was cancelled"},
            }
        return {
            "id": f"tx-{point['sequence']}",
            "state": "succeeded",
            "swr_before": 2.1,
            "swr_after": 1.2,
            "error": None,
        }

    async def execute_swr_survey_point(self, job_id, point):
        self.calls.append(("survey-point", job_id, point["sequence"]))
        return {
            "id": f"survey-{point['sequence']}",
            "state": "succeeded",
            "swr_before": 1.4 if point["sequence"] == 1 else 1.8,
            "swr_after": None,
            "target_swr": 1.5,
            "memory_changed": False,
            "error": None,
        }

    async def cancel_training(self, job_id):
        self.calls.append(("cancel", job_id))
        self.cancelled = True
        if self.point_gate is not None:
            self.point_gate.set()

    async def release_training(self, job_id):
        self.calls.append(("release", job_id))
        if self.training_job_id == job_id:
            self.training_job_id = None


def create(manager: TrainingJobManager, plan: dict, **overrides):
    values = {
        "confirmation": plan["required_confirmation"],
        "operator_confirmed": False,
        "legal_operation_confirmed": True,
        "approved_load_confirmed": True,
        "digital_engine_inhibit_confirmed": True,
        "vendor_backup_confirmed": bool(plan["erase_plan"]["requested"]),
    }
    values.update(overrides)
    return manager.create_job(plan, **values)


def test_job_runs_points_and_reports_swr_results():
    async def exercise():
        coordinator = FakeCoordinator()
        manager = TrainingJobManager(coordinator)
        created = await create(manager, preview())
        await manager._tasks[created["id"]]
        return coordinator, manager.get_job(created["id"])

    coordinator, job = asyncio.run(exercise())

    assert job["state"] == "succeeded"
    assert job["progress_percent"] == 100
    assert job["completed_count"] == 2
    assert [item["swr_after"] for item in job["results"]] == [1.2, 1.2]
    assert [call[0] for call in coordinator.calls].count("point") == 2
    assert coordinator.calls[-1][0] == "release"
    assert [event["event"] for event in job["events"]] == [
        "job.queued",
        "job.started",
        "point.started",
        "point.completed",
        "point.started",
        "point.completed",
        "safe_state.confirmed",
        "job.finished",
    ]
    assert job["events"][-1]["job_state"] == "succeeded"
    assert plan_confirmation_not_logged(job)


def test_mixed_plan_runs_eligible_points_and_audits_policy_skips():
    async def exercise():
        coordinator = FakeCoordinator()
        manager = TrainingJobManager(coordinator)
        plan = preview()
        plan["points"][1].update(
            eligible=False,
            blocked_reasons=["Amplifier operation is prohibited by band policy"],
        )
        assert manager.cached_execution_blockers(plan) == []
        created = await create(manager, plan, operator_confirmed=True, confirmation="")
        await manager._tasks[created["id"]]
        return coordinator, manager.get_job(created["id"])

    coordinator, job = asyncio.run(exercise())

    assert job["state"] == "succeeded"
    assert job["requested_point_count"] == 2
    assert job["point_count"] == 1
    assert job["skipped_point_count"] == 1
    assert job["skipped_points"][0]["sequence"] == 2
    assert [call[1] for call in coordinator.calls if call[0] == "cached-preflight"] == [1]
    assert [call[1] for call in coordinator.calls if call[0] == "fresh-preflight"] == [1]
    assert [call[2] for call in coordinator.calls if call[0] == "point"] == [1]


def test_swr_survey_reports_only_points_above_target_for_followup_training():
    async def exercise():
        coordinator = FakeCoordinator()
        manager = TrainingJobManager(coordinator)
        created = await create(
            manager,
            preview(),
            operation="survey",
            operator_confirmed=True,
            confirmation="",
        )
        await manager._tasks[created["id"]]
        return coordinator, manager.get_job(created["id"])

    coordinator, job = asyncio.run(exercise())

    assert job["state"] == "succeeded"
    assert job["operation"] == "survey"
    assert [item["status"] for item in job["results"]] == [
        "within-target",
        "needs-training",
    ]
    assert [item["needs_training"] for item in job["results"]] == [False, True]
    assert [call[0] for call in coordinator.calls].count("survey-point") == 2


def plan_confirmation_not_logged(job: dict) -> bool:
    return "TRAIN " not in json.dumps(job["events"], sort_keys=True)


def test_transient_pre_carrier_flex_timeout_retries_point_once_and_continues():
    class TransientCoordinator(FakeCoordinator):
        def __init__(self):
            super().__init__()
            self.attempts: dict[int, int] = {}

        async def execute_training_point(self, job_id, point):
            sequence = int(point["sequence"])
            self.calls.append(("point", job_id, sequence))
            self.attempts[sequence] = self.attempts.get(sequence, 0) + 1
            if sequence == 1 and self.attempts[sequence] == 1:
                return {
                    "id": "tx-transient",
                    "state": "failed",
                    "step": "selecting-elecraft-route",
                    "progress": 60,
                    "error": {
                        "code": "flex-tx-proof-timeout",
                        "message": "Fresh FLEX TX state timed out",
                    },
                }
            return {
                "id": f"tx-{sequence}-attempt-{self.attempts[sequence]}",
                "state": "succeeded",
                "step": "complete",
                "progress": 100,
                "swr_before": 2.1,
                "swr_after": 1.2,
                "error": None,
            }

    async def exercise():
        coordinator = TransientCoordinator()
        manager = TrainingJobManager(coordinator)
        created = await create(manager, preview())
        await manager._tasks[created["id"]]
        return coordinator, manager.get_job(created["id"])

    coordinator, job = asyncio.run(exercise())

    assert job["state"] == "succeeded"
    assert job["completed_count"] == 2
    assert [call[2] for call in coordinator.calls if call[0] == "point"] == [1, 1, 2]
    assert job["results"][0]["attempt_count"] == 2
    assert job["results"][0]["attempts"][0]["error"]["code"] == (
        "flex-tx-proof-timeout"
    )
    assert any(event["event"] == "point.retry_scheduled" for event in job["events"])


def test_target_miss_is_recorded_and_later_points_continue():
    class TargetMissCoordinator(FakeCoordinator):
        async def execute_training_point(self, job_id, point):
            sequence = int(point["sequence"])
            self.calls.append(("point", job_id, sequence))
            if sequence == 1:
                return {
                    "id": "tx-target-miss",
                    "state": "failed",
                    "step": "measuring-swr",
                    "progress": 80,
                    "swr_before": None,
                    "swr_after": 1.51,
                    "error": {
                        "code": "tune-target-not-met",
                        "message": "Tuned SWR 1.51 is above the 1.50 target",
                    },
                }
            return {
                "id": f"tx-{sequence}",
                "state": "succeeded",
                "swr_before": 2.1,
                "swr_after": 1.2,
                "error": None,
            }

    async def exercise():
        coordinator = TargetMissCoordinator()
        manager = TrainingJobManager(coordinator)
        created = await create(manager, preview(count=3))
        await manager._tasks[created["id"]]
        return coordinator, manager.get_job(created["id"])

    coordinator, job = asyncio.run(exercise())

    assert job["state"] == "completed_with_failures"
    assert job["processed_count"] == 3
    assert job["completed_count"] == 2
    assert job["failed_point_count"] == 1
    assert job["progress_percent"] == 100
    assert [call[2] for call in coordinator.calls if call[0] == "point"] == [1, 2, 3]
    assert [result["status"] for result in job["results"]] == [
        "failed",
        "succeeded",
        "succeeded",
    ]
    assert "2 point(s) succeeded" in job["message"]
    assert any(event["event"] == "point.failed_continuing" for event in job["events"])
    assert job["events"][-1]["job_state"] == "completed_with_failures"


def test_point_watchdog_cancels_stalled_point_and_finishes_job(monkeypatch):
    class StalledCoordinator(FakeCoordinator):
        def __init__(self):
            super().__init__()
            self.point_cancelled = False

        async def execute_training_point(self, job_id, point):
            self.calls.append(("point", job_id, point["sequence"]))
            try:
                await asyncio.Event().wait()
            finally:
                self.point_cancelled = True

    monkeypatch.setattr(training_jobs, "MIN_POINT_WATCHDOG_SECONDS", 0.05)
    monkeypatch.setattr(training_jobs, "MAX_POINT_WATCHDOG_SECONDS", 0.05)
    monkeypatch.setattr(training_jobs, "POINT_WATCHDOG_GRACE_SECONDS", 0.0)

    async def exercise():
        coordinator = StalledCoordinator()
        manager = TrainingJobManager(coordinator)
        created = await create(manager, preview(count=2))
        await asyncio.wait_for(manager._tasks[created["id"]], timeout=1.0)
        return coordinator, manager.get_job(created["id"])

    coordinator, job = asyncio.run(exercise())

    assert coordinator.point_cancelled is True
    assert job["state"] == "failed"
    assert job["progress_percent"] == 50
    assert len(job["results"]) == 1
    assert job["results"][0]["error"]["code"] == "training-point-watchdog-timeout"
    assert job["results"][0]["step"] == "point-watchdog-timeout"
    assert coordinator.calls[-1][0] == "release"


def test_raised_point_error_is_preserved_as_failed_result_and_structured_event():
    class RaisingCoordinator(FakeCoordinator):
        async def execute_training_point(self, job_id, point):
            self.calls.append(("point", job_id, point["sequence"]))
            raise StationActionError(
                "kat-route-readback-failed",
                "KAT500 route readback failed",
            )

    async def exercise():
        coordinator = RaisingCoordinator()
        manager = TrainingJobManager(coordinator)
        created = await create(manager, preview(count=2))
        await manager._tasks[created["id"]]
        return coordinator, manager.get_job(created["id"])

    coordinator, job = asyncio.run(exercise())

    assert job["state"] == "failed"
    assert len(job["results"]) == 1
    assert job["results"][0]["status"] == "failed"
    assert job["results"][0]["error"] == {
        "code": "kat-route-readback-failed",
        "message": "KAT500 route readback failed",
    }
    failure = next(event for event in job["events"] if event["event"] == "point.failed")
    assert failure["point_sequence"] == 1
    assert failure["error"]["code"] == "kat-route-readback-failed"
    assert [call[2] for call in coordinator.calls if call[0] == "point"] == [1]


def test_missing_attestation_and_confirmation_fail_before_station_claim():
    async def exercise():
        coordinator = FakeCoordinator()
        manager = TrainingJobManager(coordinator)
        plan = preview()
        with pytest.raises(TrainingJobError) as exc_info:
            await create(
                manager,
                plan,
                confirmation="TRAIN SOMETHING ELSE",
                approved_load_confirmed=False,
            )
        return coordinator, exc_info.value

    coordinator, error = asyncio.run(exercise())

    assert error.status_code == 422
    assert {item["code"] for item in error.blockers} == {
        "operator-confirmation-required",
        "approved-load-unconfirmed",
    }
    assert coordinator.calls == []


def test_selective_erase_is_scoped_and_requires_vendor_backup():
    async def exercise():
        coordinator = FakeCoordinator()
        manager = TrainingJobManager(coordinator)
        plan = preview(erase=True)
        with pytest.raises(TrainingJobError) as exc_info:
            await create(manager, plan, vendor_backup_confirmed=False)
        created = await create(manager, plan)
        await manager._tasks[created["id"]]
        return coordinator, exc_info.value, manager.get_job(created["id"])

    coordinator, error, job = asyncio.run(exercise())

    assert error.blockers[0]["code"] == "vendor-backup-unconfirmed"
    erase_call = next(call for call in coordinator.calls if call[0] == "erase")
    assert erase_call[2] == [
        {"band": "20m", "kat_antenna": 2, "frequency_mhz": 14.05}
    ]
    assert job["erase_results"] == [{"band": "20m", "kat_antenna": 2}]


def test_single_active_job_and_cancel_are_enforced():
    async def exercise():
        coordinator = FakeCoordinator()
        coordinator.point_gate = asyncio.Event()
        manager = TrainingJobManager(coordinator)
        plan = preview(count=1)
        first = await create(manager, plan)
        await asyncio.sleep(0)
        with pytest.raises(TrainingJobError) as exc_info:
            await create(manager, plan)
        cancelling = await manager.cancel_job(first["id"])
        await manager._tasks[first["id"]]
        return manager, first["id"], cancelling, exc_info.value

    manager, job_id, cancelling, error = asyncio.run(exercise())

    assert error.code == "training-job-active"
    assert cancelling["state"] == "cancelling"
    assert manager.get_job(job_id)["state"] == "cancelled"


def test_training_jobs_api_exposes_active_job_and_cancel(monkeypatch):
    monkeypatch.setattr(
        config,
        "FLEX_ANTENNA_POLICY",
        {"enabled": True, "bands": {"20m": "ANT1"}},
    )
    monkeypatch.setattr(config, "STATION_AMPLIFIER_ALLOWED_BANDS", ["20m"])
    coordinator = FakeCoordinator()
    coordinator.point_gate = asyncio.Event()
    manager = TrainingJobManager(coordinator)
    app = FastAPI()
    install_app_context(
        app,
        AppContext(
            station_coordinator=coordinator,
            station_training_manager=manager,
        ),
    )
    app.include_router(router)

    with TestClient(app) as client:
        created = client.post(
            "/api/station/training/jobs",
            json={
                "bands": ["20m"],
                "frequency_points_mhz": {"20m": [14.074]},
                "typed_confirmation": "TRAIN 20M ANT2",
                "operator_confirmed": True,
                "legal_operation_confirmed": True,
                "approved_load_confirmed": True,
                "digital_engine_inhibit_confirmed": True,
            },
        )
        job_id = created.json()["training_job"]["id"]
        active = client.get("/api/station/training/jobs/active")
        listed = client.get("/api/station/training/jobs")
        cancelled = client.post(f"/api/station/training/jobs/{job_id}/cancel")
        final = None
        for _ in range(50):
            final = client.get(f"/api/station/training/jobs/{job_id}")
            if final.json()["training_job"]["state"] == "cancelled":
                break
            time.sleep(0.01)

    assert created.status_code == 202
    assert active.status_code == 200
    assert active.json()["training_job"]["id"] == job_id
    assert listed.json()["active_job_id"] == job_id
    assert cancelled.status_code == 200
    assert final is not None
    assert final.json()["training_job"]["state"] == "cancelled"
