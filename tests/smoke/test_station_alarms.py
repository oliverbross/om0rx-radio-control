from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.station import router
from backend.core.context import AppContext, install_app_context
from services.station_alarms import build_station_alarms


def _state(**updates):
    state = {
        "generated_at": "2026-10-04T08:00:10+00:00",
        "commissioned": True,
        "recovery_required": False,
        "coordinator_state": "safe_rx",
        "transaction": None,
        "path": {
            "stages": [],
            "mismatches": [],
            "unknown_reasons": [],
        },
    }
    state.update(updates)
    return state


def test_faults_freshness_and_mismatch_are_normalized_and_deduplicated():
    state = _state(
        path={
            "stages": [
                {"id": "flex", "label": "FLEX-8400", "state": "stale", "stale": True, "observed_at": "2026-10-04T08:00:00+00:00", "age_seconds": 10},
                {"id": "kpa500", "label": "KPA500", "state": "fault", "observed_at": "2026-10-04T08:00:05+00:00", "age_seconds": 5},
            ],
            "mismatches": [
                {"code": "kpa-fault", "message": "KPA500 fault 04"},
                {"code": "kpa-fault", "message": "duplicate"},
                {"code": "kat-band-mismatch", "message": "KAT500 reports 40m while FLEX is on 20m"},
            ],
            "unknown_reasons": ["FLEX state is not fresh and confirmed"],
        },
    )
    result = build_station_alarms(state)

    assert result["status"] == "active"
    assert result["active_count"] == 3
    assert [item["code"] for item in result["items"]] == [
        "kpa-fault",
        "flex-telemetry-stale",
        "kat-band-mismatch",
    ]
    assert result["items"][0]["active"] is True
    assert result["items"][0]["status"] == "active"
    assert result["items"][0]["observed_at"] == "2026-10-04T08:00:05+00:00"


def test_temperature_and_voltage_require_explicit_thresholds():
    state = _state()
    devices = {
        "updated_at": "2026-10-04T08:00:00+00:00",
        "kpa500": {"temperature_c": 99, "voltage": 40},
    }

    assert build_station_alarms(state, elecraft_state=devices)["items"] == []
    alarms = build_station_alarms(
        state,
        elecraft_state=devices,
        thresholds={"kpa_temperature_max_c": 90, "kpa_voltage_min_v": 45},
    )
    assert {item["code"] for item in alarms["items"]} == {
        "kpa500-temperature-high",
        "kpa500-voltage-low",
    }
    assert all(item["age_seconds"] == 10 for item in alarms["items"])


def test_device_fault_and_path_fault_collapse_to_one_alarm():
    state = _state(
        issues=[{"code": "kpa-fault", "message": "KPA500 fault 04"}],
        path={
            "stages": [{"id": "kpa500", "state": "fault", "observed_at": 1}],
            "mismatches": [{"code": "kpa-fault", "message": "KPA500 fault 04"}],
            "unknown_reasons": [],
        },
    )
    result = build_station_alarms(
        state,
        elecraft_state={"kpa500": {"fault": "04", "observed_at": 1}},
    )

    assert result["active_count"] == 1
    assert result["items"][0]["code"] == "kpa-fault"
    assert result["items"][0]["source"] == "kpa500"


def test_failed_and_cancelled_tunes_keep_stable_error_codes():
    failed = build_station_alarms(
        _state(transaction={"kind": "tune", "state": "failed", "finished_at": "2026-10-04T08:00:09+00:00", "error": {"code": "tune-target-not-met", "message": "SWR remained high"}})
    )
    cancelled = build_station_alarms(
        _state(transaction={"kind": "tune", "state": "cancelled", "error": {"code": "tune-cancelled", "message": "Tune was cancelled"}})
    )

    assert failed["items"][0]["code"] == "tune-target-not-met"
    assert failed["items"][0]["severity"] == "critical"
    assert cancelled["items"][0]["code"] == "tune-cancelled"
    assert cancelled["items"][0]["severity"] == "warning"


def test_lifecycle_alarms_distinguish_lock_maintenance_and_recovery_severity():
    commissioning = build_station_alarms(
        _state(commissioned=False, coordinator_state="commissioning_locked")
    )
    maintenance = build_station_alarms(
        _state(maintenance=True, coordinator_state="maintenance")
    )
    recovery = build_station_alarms(
        _state(recovery_required=True, coordinator_state="recovery_required")
    )

    assert commissioning["items"][0]["code"] == "station-commissioning-required"
    assert commissioning["items"][0]["severity"] == "info"
    assert maintenance["items"][0]["severity"] == "warning"
    assert recovery["items"][0]["severity"] == "critical"


def test_get_alarms_endpoint_is_cached_and_get_only():
    class Coordinator:
        def __init__(self):
            self.snapshot_calls = 0

        def snapshot(self):
            self.snapshot_calls += 1
            return {"alarms": {"status": "clear", "active_count": 0, "items": []}}

    coordinator = Coordinator()
    app = FastAPI()
    app.include_router(router)
    install_app_context(app, AppContext(station_coordinator=coordinator))

    with TestClient(app) as client:
        response = client.get("/api/station/alarms")
        rejected = client.post("/api/station/alarms")

    assert response.status_code == 200
    assert response.json()["alarms"]["status"] == "clear"
    assert rejected.status_code == 405
    assert coordinator.snapshot_calls == 1
