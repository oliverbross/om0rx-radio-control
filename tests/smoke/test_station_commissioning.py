from __future__ import annotations

import copy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.station import router
from backend.core.context import AppContext, install_app_context
from radio_control import config as runtime_config
from services.station_commissioning import build_commissioning_readiness


def fixtures(band: str = "20m") -> tuple[dict, dict, dict, dict]:
    antenna = 1
    route = {
        "band": band,
        "flex_tx_ant": "ANT1",
        "kat_antenna": antenna,
        "antenna_name": "Tribander",
    }
    path = {
        "generated_at": "2026-10-04T06:00:00+00:00",
        "alignment": "confirmed",
        "band": band,
        "mismatches": [],
        "unknown_reasons": [],
        "stages": [
            {"id": "flex", "state": "ready", "confirmed": True, "stale": False},
            {"id": "kpa500", "state": "standby", "confirmed": True, "stale": False},
            {"id": "kat500", "state": "auto", "confirmed": True, "stale": False},
        ],
    }
    coordinator = {
        "generated_at": "2026-10-04T06:00:00+00:00",
        "commissioned": False,
        "maintenance": False,
        "recovery_required": False,
        "coordinator_state": "commissioning_locked",
        "transaction": None,
        "route": route,
        "path": path,
    }
    elecraft = {
        "following_radio": True,
        "radio_band": band,
        "kpa500": {
            "enabled": True,
            "connected": True,
            "responsive": True,
            "stale": False,
            "power": True,
            "operate": False,
            "band": band,
            "fault": "00",
        },
        "kat500": {
            "enabled": True,
            "connected": True,
            "responsive": True,
            "stale": False,
            "power": True,
            "mode": "auto",
            "band": band,
            "antenna": antenna,
            "tuning": False,
            "fault": "0",
            "bypass": False,
        },
    }
    evidence = {
        "physical_key_interrupt_verified": True,
        "antenna_routes_names_verified": True,
        "vendor_backups_captured": True,
        "dummy_load_or_approved_antenna_connected": True,
        "digital_engine_inhibit_verified": True,
    }
    config = {
        "STATION_COORDINATOR_COMMISSIONED": False,
        "FLEX_ANTENNA_POLICY": {"enabled": True, "bands": {band: "ANT1"}},
        "KAT500_ANTENNA_POLICY": {band: antenna},
        "KAT500_ANTENNA_NAMES": {str(antenna): "Tribander"},
        "STATION_AMPLIFIER_ALLOWED_BANDS": [band],
        "STATION_TUNE_POWER_W": 20,
        "ELECRAFT_FOLLOW_RADIO": True,
        "ELECRAFT_LEGACY_CONTROL_ENABLED": False,
    }
    return coordinator, elecraft, evidence, config


def test_complete_cached_and_operator_evidence_is_ready_without_enabling_commissioning():
    coordinator, elecraft, evidence, config = fixtures()

    report = build_commissioning_readiness(coordinator, elecraft, evidence, config)

    assert report["read_only"] is True
    assert report["commissioning_enabled"] is False
    assert report["disposition"] == "ready-for-low-power-test"
    assert report["ready_for_receive_only"] is True
    assert report["ready_for_low_power_test"] is True
    assert report["blockers"] == []
    assert report["passed_count"] == report["check_count"]
    assert report["counts"]["operator_evidence_passed"] == 5


def test_enabled_commissioning_latch_is_reported_as_consistent_and_ready():
    coordinator, elecraft, evidence, config = fixtures()
    coordinator["commissioned"] = True
    coordinator["coordinator_state"] = "safe_rx"
    config["STATION_COORDINATOR_COMMISSIONED"] = True

    report = build_commissioning_readiness(coordinator, elecraft, evidence, config)

    assert report["commissioning_enabled"] is True
    assert report["ready_for_receive_only"] is True
    assert report["ready_for_low_power_test"] is True
    commissioning_check = next(
        item for item in report["checks"]
        if item["code"] == "commissioning-state-consistent"
    )
    assert commissioning_check["passed"] is True
    assert commissioning_check["message"] == (
        "The independent commissioning latch is enabled"
    )


def test_mismatched_commissioning_latch_fails_closed():
    coordinator, elecraft, evidence, config = fixtures()
    coordinator["commissioned"] = True

    report = build_commissioning_readiness(coordinator, elecraft, evidence, config)

    assert report["commissioning_enabled"] is False
    assert report["ready_for_receive_only"] is False
    assert report["ready_for_low_power_test"] is False
    blocker = next(
        item for item in report["blockers"]
        if item["code"] == "commissioning-state-consistent"
    )
    assert blocker["message"] == "The commissioning latch state is inconsistent"


def test_operator_evidence_is_distinct_from_automated_receive_only_checks():
    coordinator, elecraft, _evidence, config = fixtures()

    report = build_commissioning_readiness(coordinator, elecraft, {}, config)

    assert report["disposition"] == "receive-only"
    assert report["ready_for_receive_only"] is True
    assert report["ready_for_low_power_test"] is False
    assert report["counts"]["operator_evidence_total"] == 5
    assert report["counts"]["operator_evidence_passed"] == 0
    assert {item["source"] for item in report["blockers"]} == {"operator-evidence"}
    assert {item["code"] for item in report["blockers"]} == {
        "physical-key-interrupt-verified",
        "antenna-routes-names-verified",
        "vendor-backups-captured",
        "dummy-load-or-approved-antenna-connected",
        "digital-engine-inhibit-verified",
    }


def test_60m_remains_blocked_even_when_accidentally_allowlisted():
    coordinator, elecraft, evidence, config = fixtures("60m")
    config["STATION_AMPLIFIER_ALLOWED_BANDS"] = ["60m"]

    report = build_commissioning_readiness(coordinator, elecraft, evidence, config)

    assert report["ready_for_receive_only"] is True
    assert report["ready_for_low_power_test"] is False
    blocker = next(
        item for item in report["blockers"] if item["code"] == "band-eligible-for-low-power-test"
    )
    assert blocker["detail"] == "60m is prohibited for this workflow"


def test_missing_or_ambiguous_cache_fails_closed():
    coordinator, elecraft, evidence, config = fixtures()
    coordinator["path"]["stages"][0].pop("stale")
    elecraft["kpa500"]["operate"] = None
    evidence["physical_key_interrupt_verified"] = 1

    report = build_commissioning_readiness(coordinator, elecraft, evidence, config)

    assert report["ready_for_receive_only"] is False
    assert report["ready_for_low_power_test"] is False
    codes = {item["code"] for item in report["blockers"]}
    assert "flex-receive-cache-fresh" in codes
    assert "kpa500-standby-confirmed" in codes
    assert "physical-key-interrupt-verified" in codes


def test_evaluator_does_not_call_devices_or_mutate_any_input():
    coordinator, elecraft, evidence, config = fixtures()
    originals = copy.deepcopy((coordinator, elecraft, evidence, config))

    class ExplodingDevice:
        def __getattribute__(self, name):
            raise AssertionError(f"readiness evaluator touched hardware attribute {name}")

    coordinator["device"] = ExplodingDevice()
    elecraft["kpa500_device"] = ExplodingDevice()

    first = build_commissioning_readiness(coordinator, elecraft, evidence, config)
    second = build_commissioning_readiness(coordinator, elecraft, evidence, config)

    assert first == second
    assert originals == (
        {key: value for key, value in coordinator.items() if key != "device"},
        {key: value for key, value in elecraft.items() if key != "kpa500_device"},
        evidence,
        config,
    )


def test_route_policy_and_configured_power_are_low_power_blockers_only():
    coordinator, elecraft, evidence, config = fixtures()
    config["KAT500_ANTENNA_NAMES"] = {"1": "KAT ANT1"}
    config["STATION_TUNE_POWER_W"] = 25

    report = build_commissioning_readiness(coordinator, elecraft, evidence, config)

    assert report["ready_for_receive_only"] is True
    assert report["ready_for_low_power_test"] is False
    assert {item["code"] for item in report["blockers"]} >= {
        "route-configured",
        "low-power-limit-configured",
    }


def test_readiness_api_is_cached_preview_only_and_has_no_enable_route(monkeypatch):
    coordinator_state, elecraft_state, evidence, config = fixtures()
    for key, value in config.items():
        monkeypatch.setattr(runtime_config, key, value)

    class CachedManager:
        def snapshot(self):
            return copy.deepcopy(elecraft_state)

    class CachedCoordinator:
        elecraft = CachedManager()

        def snapshot(self):
            return copy.deepcopy(coordinator_state)

    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=CachedCoordinator()))
    app.include_router(router)

    with TestClient(app) as client:
        baseline = client.get("/api/station/commissioning/readiness")
        evaluated = client.post(
            "/api/station/commissioning/readiness",
            json=evidence,
        )
        no_enable = client.post("/api/station/commissioning/enable")

    assert baseline.status_code == 200
    assert baseline.json()["readiness"]["ready_for_receive_only"] is True
    assert baseline.json()["readiness"]["ready_for_low_power_test"] is False
    assert evaluated.status_code == 200
    assert evaluated.json()["readiness"]["ready_for_low_power_test"] is True
    assert evaluated.json()["readiness"]["commissioning_enabled"] is False
    assert no_enable.status_code == 404


def test_readiness_api_rejects_coerced_or_extra_evidence_fields():
    coordinator_state, elecraft_state, _evidence, _config = fixtures()

    class CachedManager:
        def snapshot(self):
            return elecraft_state

    class CachedCoordinator:
        elecraft = CachedManager()

        def snapshot(self):
            return coordinator_state

    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=CachedCoordinator()))
    app.include_router(router)

    with TestClient(app) as client:
        coerced = client.post(
            "/api/station/commissioning/readiness",
            json={"physical_key_interrupt_verified": "true"},
        )
        extra = client.post(
            "/api/station/commissioning/readiness",
            json={"commissioning_enabled": True},
        )

    assert coerced.status_code == 422
    assert extra.status_code == 422
