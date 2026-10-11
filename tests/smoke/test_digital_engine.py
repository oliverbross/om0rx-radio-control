"""Digital engine ownership tests never connect to the station."""
import asyncio
from datetime import datetime, timedelta, timezone
import os
import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from pathlib import Path

import _bootstrap  # noqa: F401
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import services.digital_engine as digital
import services.radio as radio
from radio_control.persistence import atomic_write_json, read_json_object
from radio_control import settings_store

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(digital, "STATE_PATH", tmp_path / "engine.json")
    monkeypatch.setattr(digital, "STATION_AUDIT_PATH", tmp_path / "station-audit.jsonl")
    instance = digital.DigitalEngineService()
    monkeypatch.setattr(digital, "_service", instance)
    monkeypatch.setattr(instance, "processes", lambda **kwargs: {"none": [], "wsjtz": [], "mshv_auto_dx": []})
    monkeypatch.setattr(instance, "_legacy", lambda: SimpleNamespace(send_bridge_command=lambda *args: {"success": True}, get_bridge_status=lambda: {"stats": {}}, get_wsjtz_engine_status=lambda: {"exe_exists": True}))
    monkeypatch.setattr(instance, "station_process_binding", lambda **_kwargs: {
        "provider": "mshv_auto_dx",
        "pid": 321,
        "process_identity": ["mshv.exe", "--om0rx", "20261004120000.000000+000"],
        "bridge_client_id": "MSHV-OM0RX-AUTO-DX",
        "bridge_address": "127.0.0.1",
        "bridge_port": 22370,
    })
    return instance


def create_test_permit(service, binding):
    """Issue a permit through the same epoch/generation contract as final readiness."""
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    service.station_client_generation = int(binding["native_generation"])
    return service.create_station_permit(
        binding,
        expected_epoch=service.station_authorization_epoch,
        native_generation=int(binding["native_generation"]),
    )


def test_runtime_mutable_inventory_includes_native_policy_catalogs():
    assert {
        "settings/database/award_hunting.json",
        "settings/database/dxpedition_watch.json",
        "settings/database/autodx_ignore.json",
        "settings/database/autodx_status_owner.json",
        "settings/database/lotw-users.txt",
        "settings/database/confirmed-dxcc.txt",
        "settings/database/status-colors.ini",
        "settings/database/us-states.txt",
    } <= digital.MSHV_MUTABLE_PATHS


def test_mshv_preflight_treats_award_hunting_sidecar_as_exact_mutable_path(
    service, tmp_path, monkeypatch,
):
    runtime = tmp_path / "runtime"
    immutable_paths = [
        "MSHV_OM0RX.exe",
        "settings/database/cty.dat",
        "settings/database/dxcc_numbers.dat",
        "om0rx-integration.patch",
        "om0rx-autodx-phase1.patch",
        "om0rx-wavelog-history-phase2.patch",
        "source-attestation.patch",
        "sqldrivers/qsqlite.dll",
    ]
    files = {}
    for index, relative in enumerate(immutable_paths):
        path = runtime / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"immutable-{index}".encode())
        files[relative] = service._file_sha256(path)

    award_sidecar = runtime / "settings/database/award_hunting.json"
    award_sidecar.write_text('{"schema":1}', encoding="utf-8")
    lock = json.loads((ROOT / "scripts/mshv/upstream-lock.json").read_text(encoding="utf-8"))
    manifest = {
        "schema": 1,
        "provider": "mshv_auto_dx",
        "udp_client_id": "MSHV-OM0RX-AUTO-DX",
        "station_interlock": True,
        "version": "test",
        "commit": lock["commit"],
        "capabilities": [
            "station_ready_v2", "station_permit_v1", "target_priority_v1",
            "autodx_runtime_config_v1", "wavelog_history_authority_v1",
            "wavelog_history_delta_v2",
        ],
        "inventory_excludes": ["om0rx-build.json"],
        "mutable_paths": sorted(digital.MSHV_MUTABLE_PATHS),
        "files": files,
        "file_count": len(files),
        "mutable_file_count": 1,
        "staged_file_count": len(files) + 1,
        "executable_sha256": files["MSHV_OM0RX.exe"],
        "cty_sha256": files["settings/database/cty.dat"],
        "dxcc_sha256": files["settings/database/dxcc_numbers.dat"],
        "patch_sha256": files["om0rx-integration.patch"],
        "autodx_phase1_patch_sha256": files["om0rx-autodx-phase1.patch"],
        "wavelog_history_phase2_patch_sha256": files["om0rx-wavelog-history-phase2.patch"],
        "source_diff_sha256": files["source-attestation.patch"],
    }
    (runtime / "om0rx-build.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))

    result = service.preflight("mshv_auto_dx")

    checks = result["prerequisites"]["checks"]
    assert result["success"] is True
    assert checks["inventory_policy"] is True
    assert checks["immutable_inventory_set"] is True
    assert checks["immutable_inventory_hashes"] is True
    assert "settings/database/award_hunting.json" not in manifest["files"]


def test_hash_cache_detects_atomic_runtime_replacement_with_same_size_and_mtime(service, tmp_path):
    artifact = tmp_path / "source-attestation.patch"
    artifact.write_bytes(b"old-attestation")
    original = artifact.stat()
    old_digest = service._file_sha256(artifact)

    replacement = tmp_path / "replacement.patch"
    replacement.write_bytes(b"new-attestation")
    os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
    os.replace(replacement, artifact)

    replaced = artifact.stat()
    assert replaced.st_size == original.st_size
    assert replaced.st_mtime_ns == original.st_mtime_ns
    assert replaced.st_ctime_ns != original.st_ctime_ns
    assert service._file_sha256(artifact) != old_digest


def test_missing_or_invalid_provider_fails_safe_to_none(service, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "disarm_planner", lambda reason: calls.append(reason) or {"enabled": False})
    result = service.select({"provider": "unknown"})
    assert result["selected_engine"] == "none"
    assert result["planner_owner"] == "none"
    assert digital.selected_provider() == "none"
    assert calls == ["digital-engine-disabled"]


def test_provider_selection_does_not_rewrite_app_settings(service, tmp_path, monkeypatch):
    app_settings_path = tmp_path / "local_settings.json"
    original = {
        "STATION_COORDINATOR_COMMISSIONED": True,
        "FLEX_ANTENNA_POLICY": {"40m": {"rx": "ANT1", "tx": "ANT1"}},
    }
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", app_settings_path)
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    atomic_write_json(app_settings_path, original)
    before = app_settings_path.read_bytes()
    monkeypatch.setattr(service, "disarm_planner", lambda reason: {"enabled": False, "reason": reason})

    result = service.select({"provider": "none"})

    assert result["selected_engine"] == "none"
    assert app_settings_path.read_bytes() == before
    assert read_json_object(app_settings_path)["STATION_COORDINATOR_COMMISSIONED"] is True


def test_none_selection_stops_every_engine_and_never_launches(service, monkeypatch):
    snapshots = iter([
        {"none": [], "wsjtz": [123], "mshv_auto_dx": [456]},
        {"none": [], "wsjtz": [], "mshv_auto_dx": []},
        {"none": [], "wsjtz": [], "mshv_auto_dx": []},
    ])
    last = {"none": [], "wsjtz": [], "mshv_auto_dx": []}
    monkeypatch.setattr(service, "processes", lambda **kwargs: next(snapshots, last))
    monkeypatch.setattr(service, "halt", lambda: {"success": True})
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    stopped = []
    monkeypatch.setattr(service, "_stop_processes", lambda pids: stopped.extend(pids))
    monkeypatch.setattr(service, "disarm_planner", lambda reason: {"enabled": False, "reason": reason})

    result = service.select({"provider": "none"})

    assert stopped == [123, 456]
    assert result["selected_engine"] == "none"
    assert result["running"] is False
    assert result["planner_owner"] == "none"


def test_managed_process_stop_forces_only_exact_identity_after_idle_grace_timeout(service, monkeypatch):
    pid = 123
    identity = (r"c:\managed\wsjt-z.exe", "wsjt-z.exe --rig-name OM0RX", "start-1")
    alive = {"value": True}
    calls = []
    idle_checks = []
    clock = {"value": 0.0}

    def processes(**_kwargs):
        service.process_identities = {pid: identity} if alive["value"] else {}
        return {
            "none": [],
            "wsjtz": [pid] if alive["value"] else [],
            "mshv_auto_dx": [],
        }

    def run(command, **_kwargs):
        calls.append(command)
        if "/F" in command:
            alive["value"] = False
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    def monotonic():
        clock["value"] += 1.0
        return clock["value"]

    monkeypatch.setattr(service, "processes", processes)
    monkeypatch.setattr(service, "_confirm_idle", lambda: idle_checks.append(True))
    monkeypatch.setattr(service, "_legacy", lambda: SimpleNamespace(get_bridge_status=lambda: {
        "stats": {"lastStatus": {
            "qsoState": "idle", "txEnabled": False, "transmitting": False,
        }}
    }))
    monkeypatch.setattr(digital.subprocess, "run", run)
    monkeypatch.setattr(digital.time, "monotonic", monotonic)
    monkeypatch.setattr(digital.time, "sleep", lambda _seconds: None)
    service.process_identities = {pid: identity}

    service._stop_processes([pid])

    assert calls == [
        ["taskkill.exe", "/PID", str(pid), "/T"],
        ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
    ]
    assert idle_checks == [True]
    assert alive["value"] is False


def test_managed_process_stop_refuses_force_when_heartbeat_not_idle(service, monkeypatch):
    pid = 123
    identity = (r"c:\managed\wsjt-z.exe", "wsjt-z.exe --rig-name OM0RX", "start-1")
    calls = []
    clock = {"value": 0.0}

    def processes(**_kwargs):
        service.process_identities = {pid: identity}
        return {"none": [], "wsjtz": [pid], "mshv_auto_dx": []}

    def run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    def monotonic():
        clock["value"] += 1.0
        return clock["value"]

    monkeypatch.setattr(service, "processes", processes)
    monkeypatch.setattr(service, "_confirm_idle", lambda: (_ for _ in ()).throw(AssertionError("physical idle must not be checked after active heartbeat")))
    monkeypatch.setattr(service, "_legacy", lambda: SimpleNamespace(get_bridge_status=lambda: {
        "stats": {"lastStatus": {
            "qsoState": "calling", "txEnabled": True, "transmitting": False,
        }}
    }))
    monkeypatch.setattr(digital.subprocess, "run", run)
    monkeypatch.setattr(digital.time, "monotonic", monotonic)
    monkeypatch.setattr(digital.time, "sleep", lambda _seconds: None)
    service.process_identities = {pid: identity}

    with pytest.raises(HTTPException, match="not idle"):
        service._stop_processes([pid])

    assert calls == [["taskkill.exe", "/PID", str(pid), "/T"]]


def test_managed_process_stop_refuses_force_after_identity_change(service, monkeypatch):
    pid = 123
    original = (r"c:\managed\wsjt-z.exe", "wsjt-z.exe --rig-name OM0RX", "start-1")
    changed = (r"c:\managed\wsjt-z.exe", "wsjt-z.exe --rig-name OM0RX", "start-2")
    calls = []
    clock = {"value": 0.0}

    def processes(**_kwargs):
        service.process_identities = {pid: original if clock["value"] < 9 else changed}
        return {"none": [], "wsjtz": [pid], "mshv_auto_dx": []}

    def run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    def monotonic():
        clock["value"] += 1.0
        return clock["value"]

    monkeypatch.setattr(service, "processes", processes)
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    monkeypatch.setattr(service, "_legacy", lambda: SimpleNamespace(get_bridge_status=lambda: {
        "stats": {"lastStatus": {
            "qsoState": "idle", "txEnabled": False, "transmitting": False,
        }}
    }))
    monkeypatch.setattr(digital.subprocess, "run", run)
    monkeypatch.setattr(digital.time, "monotonic", monotonic)
    monkeypatch.setattr(digital.time, "sleep", lambda _seconds: None)
    service.process_identities = {pid: original}

    with pytest.raises(HTTPException, match="identity changed"):
        service._stop_processes([pid])

    assert calls == [["taskkill.exe", "/PID", str(pid), "/T"]]


def test_start_none_is_explicit_disabled_noop(service, monkeypatch):
    monkeypatch.setattr(service, "_confirm_idle", lambda: (_ for _ in ()).throw(AssertionError("none must not probe radio")))
    monkeypatch.setattr(service, "disarm_planner", lambda reason: {"enabled": False, "reason": reason})
    result = service.select({"provider": "none"}, launch=True)
    assert result["success"] is False
    assert result["disabled"] is True
    assert result["running"] is False
    assert "disabled" in result["message"].lower()


def test_restart_endpoint_with_none_never_starts_an_engine(service, monkeypatch):
    monkeypatch.setattr(service, "halt", lambda: {"success": True})
    monkeypatch.setattr(service, "_confirm_idle", lambda: (_ for _ in ()).throw(HTTPException(409, "radio offline")))
    monkeypatch.setattr(service, "disarm_planner", lambda reason: {"enabled": False, "reason": reason})
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        response = client.post("/api/digital/restart", json={"engine": "none"})
    assert response.status_code == 200
    assert response.json()["selected_engine"] == "none"
    assert response.json()["running"] is False
    assert response.json()["disabled"] is True


def test_mshv_selection_disables_planner(service, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "_disable_planner", lambda: calls.append("disabled"))
    result = service.select({"provider": "mshv_auto_dx"})
    assert result["planner_owner"] == "mshv"
    assert result["capabilities"]["target_control"] is False
    assert calls == ["disabled"]
    with pytest.raises(HTTPException):
        digital.require_om0rx_planner()


def test_selecting_wsjtz_does_not_rearm_planner(service, monkeypatch):
    from services.ft8_service import get_ft8_service

    controller = get_ft8_service().automation_controller
    controller.settings.enabled = True
    calls = []
    monkeypatch.setattr(
        service,
        "disarm_planner",
        lambda reason: calls.append(reason) or {"enabled": False},
    )

    service.select({"provider": "wsjtz"})

    assert calls == ["wsjtz-provider-selected-disarmed"]


def test_startup_disarm_clears_and_persists_pending_targets(service, monkeypatch):
    from services.ft8_service import get_ft8_service

    ft8 = get_ft8_service()
    controller = ft8.automation_controller
    monkeypatch.setattr(controller, "target_store", None)
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "wsjtz"})
    target = controller.ingest_target({
        "message": "CQ A1AA JN88", "callsign": "A1AA", "band": "20m",
        "mode": "FT8", "source": "decoded", "heard": True,
        "snr": -10, "call_status": "New Call", "dxcc_status": "Confirmed",
    })
    assert target is not None
    persisted = []
    monkeypatch.setattr(controller, "_persist_target", lambda item: persisted.append(item.to_dict()))
    ft8.auto_call_enabled = True
    controller.settings.enabled = True

    state = service.disarm_planner("backend-startup-disarmed")

    assert state == {
        "enabled": False, "auto_call": False, "auto_cq": False,
        "targets": 0, "reason": "backend-startup-disarmed",
    }
    assert persisted and persisted[0]["state"] == "skipped"
    assert persisted[0]["reason"] == "backend-startup-disarmed"
    assert controller.settings.enabled is False
    assert controller.active_target_key is None


def test_idle_confirmation_uses_serialized_live_radio_readback(service, monkeypatch):
    calls = []

    class FakeFlex:
        def get_fresh_tx_state(self, **kwargs):
            calls.append(("read", kwargs))
            return {"confirmed": True, "mox": False, "interlock_state": "READY"}

    fake = FakeFlex()
    monkeypatch.setattr(radio, "get_radio_instance", lambda: fake)
    monkeypatch.setattr(
        radio,
        "run_radio_io_sync",
        lambda operation: calls.append(("locked", None)) or operation(),
    )
    service._legacy = lambda: SimpleNamespace(
        get_bridge_status=lambda: {"stats": {"lastStatus": {"transmitting": False}}}
    )

    service._confirm_idle()

    assert [name for name, _ in calls] == ["locked", "read"]


def test_mshv_selection_blocks_all_direct_planner_ingest_and_mutation(service):
    from services.digital_automation import DigitalAutomationController
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "wsjtz"})
    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "message": "CQ A1AA JN88", "callsign": "A1AA", "band": "20m", "mode": "FT8",
        "source": "decoded", "heard": True, "snr": -10, "call_status": "New Call", "dxcc_status": "Confirmed",
    })
    assert target is not None
    original = target.to_dict()
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    assert controller.ingest_decoded({"message": "CQ B1BB JN88", "mode": "FT8", "band": "20m"}) is None
    assert controller.ingest_spot({"callsign": "B1BB", "mode": "FT8", "band": "20m"}) is None
    assert controller.record_attempt(target.key) is None
    assert controller.promote_target(target.key) is None
    assert controller.skip_target(target.key) is None
    assert controller.handle_wsjtx_status({"transmitting": True})["status"] == "ignored"
    assert target.to_dict() == original


def test_switch_refuses_unconfirmed_tx_state(service, monkeypatch):
    monkeypatch.setattr(service, "processes", lambda **kwargs: {"wsjtz": [123], "mshv_auto_dx": []})
    monkeypatch.setattr(service, "halt", lambda: {"success": True})
    monkeypatch.setattr(
        radio,
        "get_radio_instance",
        lambda: SimpleNamespace(
            current_mox=None,
            get_fresh_tx_state=lambda **kwargs: {"confirmed": False, "mox": None},
        ),
    )
    with pytest.raises(HTTPException, match="confirmed idle"):
        service.select({"provider": "mshv_auto_dx"})
    assert digital.selected_provider() == "none"


def test_stop_never_kills_when_fresh_idle_proof_fails(service, monkeypatch):
    monkeypatch.setattr(service, "processes", lambda **kwargs: {"wsjtz": [123], "mshv_auto_dx": []})
    monkeypatch.setattr(service, "halt", lambda: {"success": True})
    monkeypatch.setattr(service, "_confirm_idle", lambda: (_ for _ in ()).throw(HTTPException(409, "not idle")))
    killed = []
    monkeypatch.setattr(service, "_stop_processes", lambda pids: killed.extend(pids))
    with pytest.raises(HTTPException, match="remains running"):
        service.stop()
    assert killed == []


def test_supervised_stop_resets_process_local_native_generation(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    service.station_client_generation = 8
    running = {"value": True}
    monkeypatch.setattr(
        service,
        "processes",
        lambda **kwargs: {
            "none": [], "wsjtz": [],
            "mshv_auto_dx": [123] if running["value"] else [],
        },
    )
    monkeypatch.setattr(service, "halt", lambda: {"success": True})
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    monkeypatch.setattr(service, "_stop_processes", lambda _pids: running.update(value=False))

    result = service.stop()

    assert result["success"] is True
    assert service.station_client_generation == -1
    begun, reason, _epoch = service.begin_station_preparation(1)
    assert begun is True
    assert reason == "prepare-authorization-begun"


def test_new_mshv_launch_resets_previous_process_generation(service, monkeypatch):
    import services.mshv_configuration as mshv_config
    service.station_client_generation = 9
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    monkeypatch.setattr(service, "_disable_planner", lambda: None)
    monkeypatch.setattr(service, "preflight", lambda provider: {
        "success": True,
        "provider": provider,
        "prerequisites": {"exe": str(ROOT / "fake-mshv.exe")},
    })
    monkeypatch.setattr(
        service,
        "processes",
        lambda **kwargs: {"none": [], "wsjtz": [], "mshv_auto_dx": []},
    )
    monkeypatch.setattr(digital.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(pid=456))
    monkeypatch.setattr(service, "_invalidate_process_scan", lambda: None)
    monkeypatch.setattr(service, "_wait_for_startup", lambda *args, **kwargs: {"ready": True})
    monkeypatch.setattr(service, "status", lambda: {"success": True, "selected_engine": "mshv_auto_dx"})
    monkeypatch.setattr(mshv_config, "stage_mshv_safe_startup", lambda: {
        "effective_enabled": True,
        "saved_preference": True,
        "requires_explicit_native_arm": False,
    })

    result = service.select({"provider": "mshv_auto_dx"}, launch=True)

    assert result["startup"] == {"ready": True}
    assert result["startup_safety"]["effective_enabled"] is True
    assert service.station_client_generation == -1
    audit = digital.STATION_AUDIT_PATH.read_text(encoding="utf-8")
    assert '"event":"native-generation-reset"' in audit
    assert '"reason":"mshv-process-launch"' in audit


def test_emergency_halt_reports_acceptance_separately_from_idle_proof(service, monkeypatch):
    service._legacy = lambda: SimpleNamespace(
        send_bridge_command=lambda *args: {"success": True},
        get_bridge_status=lambda: {"stats": {"lastStatus": {"transmitting": True}}},
    )
    monkeypatch.setattr(radio, "get_radio_instance", lambda: None)
    result = service.halt()
    assert result["success"] is True
    assert result["command_accepted"] is True
    assert result["bridge_command_accepted"] is True
    assert result["idle_confirmed"] is False
    assert "confirmed idle" in result["confirmation_error"]


def test_emergency_halt_endpoint_remains_available_with_mshv_ownership(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    service._legacy = lambda: SimpleNamespace(
        send_bridge_command=lambda *args: {"success": True},
        get_bridge_status=lambda: {"stats": {}},
        get_wsjtz_engine_status=lambda: {"exe_exists": True},
    )
    monkeypatch.setattr(radio, "get_radio_instance", lambda: None)
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        response = client.post("/api/digital/halt-tx")
    assert response.status_code == 200
    assert response.json()["command_accepted"] is True


def test_startup_readiness_requires_process_bridge_identity_and_fresh_mshv_heartbeat(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    selected_at = 100.0
    monkeypatch.setattr(service, "processes", lambda **kwargs: {"wsjtz": [], "mshv_auto_dx": [42]})
    service._legacy = lambda: SimpleNamespace(get_bridge_status=lambda: {
        "success": True,
        "provider": "mshv_auto_dx",
        "conflict": False,
        "client": {"id": "MSHV-OM0RX-AUTO-DX", "lastSeenMs": 100},
    })
    service.engine_state = {"provider": "mshv_auto_dx", "state": "receive"}
    service.engine_state_at = selected_at - 1
    assert service._startup_readiness("mshv_auto_dx", selected_at=selected_at)["ready"] is False
    service.engine_state_at = digital.time.monotonic()
    readiness = service._startup_readiness("mshv_auto_dx", selected_at=selected_at)
    assert readiness["ready"] is True
    assert readiness["bridge_healthy"] is True
    assert readiness["heartbeat_fresh"] is True


def test_station_identity_fresh_uses_native_heartbeat_cadence_margin(service):
    base = {
        "success": True,
        "provider": "mshv_auto_dx",
        "conflict": False,
        "client": {"id": "MSHV-OM0RX-AUTO-DX", "lastSeenMs": 19_999},
    }
    assert service.station_bridge_identity_fresh(base) is True
    assert service.station_bridge_identity_fresh({
        **base, "client": {**base["client"], "lastSeenMs": 20_000},
    }) is False
    assert service.station_bridge_identity_fresh({
        **base, "client": {**base["client"], "id": "WSJT-Z"},
    }) is False


def test_status_exposes_strict_station_identity_fresh_separately(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    monkeypatch.setattr(service, "processes", lambda **kwargs: {
        "none": [], "wsjtz": [], "mshv_auto_dx": [42],
    })
    service._legacy = lambda: SimpleNamespace(get_bridge_status=lambda: {
        "success": True, "provider": "mshv_auto_dx", "conflict": False,
        "client": {"id": "MSHV-OM0RX-AUTO-DX", "lastSeenMs": 19_500},
    })
    monkeypatch.setattr(service, "preflight", lambda _provider: {
        "prerequisites": {"version": "test", "manifest": {"station_interlock": True}},
    })

    result = service.status()

    assert result["station_identity_fresh"] is True
    assert result["station_identity_max_age_ms"] == 20_000


def test_start_waits_for_bounded_readiness_before_returning_status(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "wsjtz"})
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    monkeypatch.setattr(service, "preflight", lambda provider: {
        "success": True, "provider": provider, "prerequisites": {"exe_exists": True, "version": "test"}
    })
    monkeypatch.setattr(service, "processes", lambda **kwargs: {"wsjtz": [42], "mshv_auto_dx": []})
    waited = []
    monkeypatch.setattr(service, "_wait_for_startup", lambda provider, selected_at: waited.append((provider, selected_at)) or {"ready": True})
    service._legacy = lambda: SimpleNamespace(
        send_bridge_command=lambda *args: {"success": True},
        get_bridge_status=lambda: {"success": True, "provider": "wsjtz", "stats": {}},
    )
    response = service.select({"provider": "wsjtz"}, launch=True)
    assert waited and waited[0][0] == "wsjtz"
    assert response["running"] is True
    assert response["startup"] == {"ready": True}


def test_startup_timeout_returns_starting_when_exact_owned_process_remains_alive(service, monkeypatch):
    monkeypatch.setattr(digital, "STARTUP_CONFIRM_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(digital, "STARTUP_CONFIRM_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(service, "_startup_readiness", lambda *args, **kwargs: {
        "ready": False, "process_running": True, "bridge_healthy": False, "heartbeat_fresh": False,
    })
    result = service._wait_for_startup("mshv_auto_dx", selected_at=digital.time.monotonic())
    assert result["ready"] is False
    assert result["accepted"] is True
    assert result["starting"] is True


def test_startup_timeout_is_503_when_owned_process_exits(service, monkeypatch):
    monkeypatch.setattr(digital, "STARTUP_CONFIRM_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(digital, "STARTUP_CONFIRM_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(service, "_startup_readiness", lambda *args, **kwargs: {
        "ready": False, "process_running": False, "bridge_healthy": False, "heartbeat_fresh": False,
    })
    with pytest.raises(HTTPException) as exc:
        service._wait_for_startup("mshv_auto_dx", selected_at=digital.time.monotonic())
    assert exc.value.status_code == 503
    assert exc.value.detail["startup"]["process_running"] is False


def test_startup_timeout_is_503_when_other_managed_engine_or_bridge_conflicts(service, monkeypatch):
    monkeypatch.setattr(digital, "STARTUP_CONFIRM_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(digital, "STARTUP_CONFIRM_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(service, "_startup_readiness", lambda *args, **kwargs: {
        "ready": False,
        "process_running": True,
        "managed_conflict": True,
        "unmanaged_conflict": False,
        "bridge_conflict": True,
    })
    with pytest.raises(HTTPException) as exc:
        service._wait_for_startup("mshv_auto_dx", selected_at=digital.time.monotonic())
    assert exc.value.status_code == 503
    assert exc.value.detail["startup"]["managed_conflict"] is True


def test_start_endpoint_uses_202_for_alive_but_not_yet_ready_process(service, monkeypatch):
    monkeypatch.setattr(service, "select", lambda request, launch=False: {
        "success": True,
        "selected_engine": "mshv_auto_dx",
        "startup": {"ready": False, "accepted": True, "starting": True},
    })
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        response = client.post("/api/digital/start", json={"engine": "mshv_auto_dx"})
    assert response.status_code == 202
    assert response.json()["startup"]["ready"] is False


def test_restart_endpoint_uses_same_202_starting_contract(service, monkeypatch):
    monkeypatch.setattr(service, "stop", lambda: {"success": True})
    monkeypatch.setattr(service, "select", lambda request, launch=False: {
        "success": True,
        "selected_engine": "mshv_auto_dx",
        "startup": {"ready": False, "accepted": True, "starting": True},
    })
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        response = client.post("/api/digital/restart", json={"engine": "mshv_auto_dx"})
    assert response.status_code == 202
    assert response.json()["startup"]["starting"] is True


def test_wmic_process_rows_parse_identity_fields_without_blank_records():
    output = "\r\nNode,CommandLine,CreationDate,ExecutablePath,Name,ProcessId\r\n" \
             "OM0RX-WIN10,C:\\\\runtime\\\\MSHV_OM0RX.exe,20261004075703.170888+120," \
             "C:\\\\runtime\\\\MSHV_OM0RX.exe,MSHV_OM0RX.exe,2304\r\n\r\n"
    rows = digital.DigitalEngineService._parse_wmic_process_rows(output)
    assert rows == [{
        "Node": "OM0RX-WIN10",
        "CommandLine": "C:\\\\runtime\\\\MSHV_OM0RX.exe",
        "CreationDate": "20261004075703.170888+120",
        "ExecutablePath": "C:\\\\runtime\\\\MSHV_OM0RX.exe",
        "Name": "MSHV_OM0RX.exe",
        "ProcessId": "2304",
    }]


def test_process_scanner_uses_fast_wmic_snapshot_cache(monkeypatch):
    instance = digital.DigitalEngineService()
    calls = []
    output = "Node,CommandLine,CreationDate,ExecutablePath,Name,ProcessId\n" \
             "HOST,C:\\\\runtime\\\\MSHV_OM0RX.exe,stamp,C:\\\\runtime\\\\MSHV_OM0RX.exe,MSHV_OM0RX.exe,2304\n"

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(digital.subprocess, "run", fake_run)
    first = instance._scan_windows_process_rows()
    second = instance._scan_windows_process_rows()
    assert first == second
    assert len(calls) == 1
    assert calls[0][0] == "wmic.exe"
    assert instance._process_scan_backend == "wmic"


def test_force_process_scan_bypasses_a_fresh_ttl_snapshot(monkeypatch):
    instance = digital.DigitalEngineService()
    scans = []

    def fake_scan():
        scans.append(len(scans) + 1)
        return ([{"Name": f"scan-{scans[-1]}"}], "wmic")

    monkeypatch.setattr(instance, "_perform_windows_process_scan", fake_scan)
    assert instance._scan_windows_process_rows() == [{"Name": "scan-1"}]
    assert instance._scan_windows_process_rows(force_refresh=True) == [{"Name": "scan-2"}]
    assert scans == [1, 2]


def test_concurrent_force_process_scans_share_the_completed_refresh(monkeypatch):
    instance = digital.DigitalEngineService()
    entered = threading.Event()
    release = threading.Event()
    calls = []
    results = []

    def fake_scan():
        calls.append(1)
        entered.set()
        assert release.wait(2)
        return ([{"Name": "fresh"}], "wmic")

    monkeypatch.setattr(instance, "_perform_windows_process_scan", fake_scan)
    first = threading.Thread(
        target=lambda: results.append(instance._scan_windows_process_rows(force_refresh=True)),
    )
    second = threading.Thread(
        target=lambda: results.append(instance._scan_windows_process_rows(force_refresh=True)),
    )
    first.start()
    assert entered.wait(2)
    second.start()
    release.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert len(calls) == 1
    assert results == [[{"Name": "fresh"}], [{"Name": "fresh"}]]


def test_slow_background_refresh_never_blocks_cached_status_reads(monkeypatch):
    instance = digital.DigitalEngineService()
    instance._process_scan_rows = [{"Name": "cached"}]
    instance._process_scan_at = digital.time.monotonic() - 30
    instance._process_scan_backend = "wmic"
    entered = threading.Event()
    release = threading.Event()
    second_result = []

    def slow_scan():
        entered.set()
        assert release.wait(2)
        return ([{"Name": "fresh"}], "wmic")

    monkeypatch.setattr(instance, "_perform_windows_process_scan", slow_scan)
    assert instance._scan_windows_process_rows() == [{"Name": "cached"}]
    assert entered.wait(2)

    second = threading.Thread(
        target=lambda: second_result.append(instance._scan_windows_process_rows()),
    )
    second.start()
    second.join(0.25)
    assert not second.is_alive()
    assert second_result == [[{"Name": "cached"}]]

    release.set()
    deadline = digital.time.monotonic() + 2
    while instance._process_scan_refreshing and digital.time.monotonic() < deadline:
        digital.time.sleep(0.01)
    assert instance._process_scan_rows == [{"Name": "fresh"}]


def test_force_refresh_never_blocks_ordinary_cached_status_reads(monkeypatch):
    instance = digital.DigitalEngineService()
    instance._process_scan_rows = [{"Name": "cached"}]
    instance._process_scan_at = digital.time.monotonic() - 30
    instance._process_scan_backend = "wmic"
    entered = threading.Event()
    release = threading.Event()
    force_result = []

    def slow_scan():
        entered.set()
        assert release.wait(2)
        return ([{"Name": "forced"}], "wmic")

    monkeypatch.setattr(instance, "_perform_windows_process_scan", slow_scan)
    force = threading.Thread(
        target=lambda: force_result.append(
            instance._scan_windows_process_rows(force_refresh=True)
        ),
    )
    force.start()
    assert entered.wait(2)

    started = digital.time.monotonic()
    assert instance._scan_windows_process_rows() == [{"Name": "cached"}]
    assert digital.time.monotonic() - started < 0.25

    release.set()
    force.join(2)
    assert not force.is_alive()
    assert force_result == [[{"Name": "forced"}]]


def test_digital_engine_diagnostics_do_not_load_portaudio():
    probe = subprocess.run(
        [
            sys.executable, "-c",
            "import sys; import services.digital_engine; import services.radio; "
            "assert 'sounddevice' not in sys.modules; print('audio-free diagnostics')",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "audio-free diagnostics" in probe.stdout


def test_mshv_settings_hot_reload_while_running_and_preserve_partial_values(tmp_path, monkeypatch):
    import services.mshv_configuration as configuration

    runtime = tmp_path / "runtime"
    settings = runtime / "settings" / "autodx.ini"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        "[SpotSources]\nCallsign=OM0RX\nGrid=JN88\nMinSNR=-18\nUsOnlyFilter=false\n"
        "[GridChase]\nEnabled=true\nUSOnly=false\n"
        "[TargetPriority]\nNewDxcc=9000\nNewBandSlot=800\nNewGrid=450\nCallingMe=350\nCq=150\nSnrPerDb=8\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    saved = configuration.update_mshv_auto_dx_settings(
        {"target_priority": {"new_grid": 600}, "spot_sources_us_only": "false"},
        engine_running=True,
    )
    assert saved["engine_running"] is True
    assert saved["editable"] is True
    assert saved["restart_required_after_save"] is False
    assert "hot reload" in saved["message"]
    assert saved["target_priority"]["new_grid"] == 600
    assert saved["target_priority"]["new_dxcc"] == 9000
    assert saved["spot_sources_us_only"] is False
    assert saved["grid_chase_enabled"] is True
    assert saved["eligibility"]["random_worked_calls"] is False


def test_managed_mshv_start_preserves_persisted_autodx_master(tmp_path, monkeypatch):
    import services.mshv_configuration as configuration

    runtime = tmp_path / "runtime"
    settings = runtime / "settings" / "autodx.ini"
    settings.parent.mkdir(parents=True)
    settings.write_text("[AutoDx]\nEnabled=true\n", encoding="utf-8")
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")
    before = settings.read_bytes()

    staged = configuration.stage_mshv_safe_startup()
    observed = configuration.read_mshv_auto_dx_settings(engine_running=False)

    assert staged == {
        "effective_enabled": True,
        "saved_preference": True,
        "requires_explicit_native_arm": False,
    }
    assert settings.read_bytes() == before
    assert observed["auto_dx_enabled"] is True
    assert observed["auto_dx_saved_preference"] is True
    assert observed["auto_dx_startup_forced_off"] is False


@pytest.mark.parametrize(
    "auto_dx_enabled,band_switching_enabled",
    [(True, False), (False, True)],
)
def test_stopped_mshv_settings_keeps_native_master_independent_of_band_switching(
    tmp_path, monkeypatch, auto_dx_enabled, band_switching_enabled,
):
    import services.mshv_configuration as configuration

    runtime = tmp_path / "runtime"
    settings = runtime / "settings" / "autodx.ini"
    settings.parent.mkdir(parents=True)
    settings.write_text("[AutoDx]\nEnabled=false\n", encoding="utf-8")
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")

    saved = configuration.update_mshv_auto_dx_settings(
        {
            "enabled": auto_dx_enabled,
            "band_switching_enabled": band_switching_enabled,
        },
        engine_running=False,
    )

    assert saved["desired"]["enabled"] is auto_dx_enabled
    assert saved["auto_dx_enabled"] is auto_dx_enabled
    assert saved["band_switching_enabled"] is band_switching_enabled
    assert saved["auto_dx_startup_forced_off"] is False
    assert configuration.stage_mshv_safe_startup()["effective_enabled"] is auto_dx_enabled
    text = settings.read_text(encoding="utf-8")
    assert f"Enabled={'true' if auto_dx_enabled else 'false'}" in text
    sidecar = json.loads((tmp_path / "startup.json").read_text(encoding="utf-8"))
    assert sidecar == {"desired_enabled": auto_dx_enabled, "staged_off": False}


def test_mshv_settings_reject_zero_grid_and_ambiguous_boolean(tmp_path, monkeypatch):
    import services.mshv_configuration as configuration

    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(tmp_path / "runtime"))
    with pytest.raises(HTTPException, match="new_grid"):
        configuration.update_mshv_auto_dx_settings(
            {"target_priority": {"new_grid": 0}}, engine_running=False,
        )
    with pytest.raises(HTTPException, match="must be a boolean"):
        configuration.update_mshv_auto_dx_settings(
            {"target_priority": {"new_grid": 1}, "grid_chase_us_only": "perhaps"},
            engine_running=False,
        )
    with pytest.raises(HTTPException, match="min_snr"):
        configuration.update_mshv_auto_dx_settings(
            {"target_priority": {"new_grid": 1}, "min_snr": 1}, engine_running=False,
        )


def test_mshv_automation_timing_and_band_schedules_round_trip(tmp_path, monkeypatch):
    import services.mshv_configuration as configuration

    runtime = tmp_path / "runtime"
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")

    defaults = configuration.read_mshv_auto_dx_settings(engine_running=False)
    assert defaults["automation_timing"] == {
        "normal_call_seconds": 120,
        "quiet_band_seconds": 300,
        "target_heard_fresh_seconds": 60,
        "cross_band_verify_seconds": 60,
        "band_switch_cooldown_seconds": 120,
        "persist_new_dxcc_while_heard": True,
        "persist_new_band_slot_while_heard": True,
    }
    assert defaults["band_schedules"]["3"] == {
        "restricted": True, "start": "18:00", "end": "06:00",
    }
    assert defaults["band_schedules"]["4"]["restricted"] is True
    assert defaults["band_schedules"]["8"] == {
        "restricted": False, "start": "18:00", "end": "06:00",
    }

    saved = configuration.update_mshv_auto_dx_settings({
        "automation_timing": {
            "quiet_band_seconds": 420,
            "target_heard_fresh_seconds": 75,
            "cross_band_verify_seconds": 45,
            "band_switch_cooldown_seconds": 180,
            "persist_new_dxcc_while_heard": False,
            "persist_new_band_slot_while_heard": True,
        },
        "band_schedules": {
            "3": {"restricted": True, "start": "19:30", "end": "05:15"},
            "8": {"restricted": True, "start": "07:00", "end": "22:00"},
        },
    }, engine_running=False)
    assert saved["automation_timing"]["normal_call_seconds"] == 120
    assert saved["automation_timing"]["persist_new_dxcc_while_heard"] is False
    assert saved["band_schedules"]["3"] == {
        "restricted": True, "start": "19:30", "end": "05:15",
    }
    assert saved["band_schedules"]["8"] == {
        "restricted": True, "start": "07:00", "end": "22:00",
    }
    text = (runtime / "settings" / "autodx.ini").read_text(encoding="utf-8")
    assert "NormalCallSeconds" not in text
    assert "Band3Start=19:30" in text
    assert "Band8Restricted=true" in text


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"automation_timing": {"normal_call_seconds": 29}}, "Unknown automation_timing setting"),
        ({"automation_timing": {"quiet_band_seconds": 3601}}, "between 60 and 3600"),
        ({"automation_timing": {"persist_new_dxcc_while_heard": "maybe"}}, "must be a boolean"),
        ({"band_schedules": {"3": {"start": "6:00"}}}, "HH:mm local time"),
        ({"band_schedules": {"5": {"restricted": True}}}, "not allowed"),
    ],
)
def test_mshv_automation_timing_and_band_schedules_validate(tmp_path, monkeypatch, payload, match):
    import services.mshv_configuration as configuration

    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(tmp_path / "runtime"))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")
    with pytest.raises(HTTPException, match=match):
        configuration.update_mshv_auto_dx_settings(payload, engine_running=False)


def test_mshv_band_schedule_parity_normalizes_native_status_fields():
    import services.mshv_configuration as configuration

    desired = {
        key: {} for key, _ in configuration._PARITY_PATHS
    }
    desired["band_schedules"] = {
        "3": {"restricted": True, "start": "18:00", "end": "06:00"},
    }
    desired["spot_sources"] = {"dx_cluster": {}}
    effective = {
        "schema_version": 1,
        **{effective_key: desired[desired_key] for desired_key, effective_key in configuration._PARITY_PATHS},
        "band_schedules": {
            "3": {
                "band": "160m", "restricted": True,
                "start_local": "18:00", "end_local": "06:00", "open_now": True,
            },
        },
    }
    assert configuration._runtime_parity(desired, effective) == {
        "status": "match", "drift": [],
    }


def test_mshv_phase1_runtime_schema_round_trips_active_controls(tmp_path, monkeypatch):
    import services.mshv_configuration as configuration

    runtime = tmp_path / "runtime"
    settings = runtime / "settings" / "autodx.ini"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        "[AutoDx]\nEnabled=true\nModes=FT8\nATNOChaseType=3\nScarceThreshold=5\n"
        "[SpotSources]\nCallsign=OM0RX\nGrid=JN88\nMinSNR=-18\nUsOnlyFilter=false\n"
        "RbnEnabled=true\nRbnHost=telnet.reversebeacon.net\nRbnPort=7001\n"
        "PskEnabled=true\nPskPollInterval=120\nDxcEnabled=true\nUseDefaultDxClusterServers=false\n"
        "[GridChase]\nEnabled=true\nUSOnly=false\n"
        "[BandSwitching]\nEnabled=false\n"
        "[BandSelection]\nEnabledBands=3,4,6,7,8,9,10,11,12\n"
        "[DxClusterServers]\nCount=1\nServer0=Primary|cluster.example.net|7300|true\n"
        "[TargetPriority]\nNewDxcc=10000\nNewBandSlot=1000\nNewGrid=500\nCallingMe=400\nCq=200\nSnrPerDb=10\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")
    atomic_write_json(configuration.STARTUP_SAFETY_PATH, {"desired_enabled": False, "staged_off": False})

    observed = configuration.read_mshv_auto_dx_settings(
        engine_running=True,
        engine_state={
            "enabled": False,
            "autodx_config": {
                "schema_version": 1,
                "desired_enabled": True,
                "effective_enabled": False,
                "band_switching_enabled": False,
                "auto_dx_modes": ["FT8"],
            },
        },
    )
    assert observed["desired"]["enabled"] is True
    assert observed["effective"]["effective_enabled"] is False
    assert observed["auto_dx_modes"] == ["FT8"]
    assert observed["enabled_bands"] == [3, 4, 6, 7, 8, 9, 10, 11, 12]
    assert observed["band_switching_enabled"] is False
    assert observed["spot_sources"]["dx_cluster"]["servers"] == [
        {"name": "Primary", "host": "cluster.example.net", "port": 7300, "enabled": True},
    ]

    saved = configuration.update_mshv_auto_dx_settings(
        {
            "band_switching_enabled": True,
            "enabled_bands": [3, 4, 6, 7, 8, 9, 10, 11, 12],
            "auto_dx_modes": ["FT8"],
            "atno_chase_type": 1,
            "scarce_threshold": 7,
            "spot_sources": {
                "us_only": True,
                "rbn": {"enabled": False, "host": "rbn.example.net", "port": 7002},
                "psk_reporter": {"enabled": True, "poll_interval_seconds": 180},
                "dx_cluster": {
                    "enabled": True,
                    "use_default_servers": False,
                    "servers": [{"name": "Backup", "host": "dx.example.net", "port": 23, "enabled": True}],
                },
            },
        },
        engine_running=False,
    )
    assert saved["band_switching_enabled"] is True
    assert saved["atno_chase_type"] == 1
    assert saved["scarce_threshold"] == 7
    assert saved["spot_sources"]["us_only"] is True
    assert saved["spot_sources"]["rbn"]["enabled"] is False
    assert saved["spot_sources"]["dx_cluster"]["servers"][0]["host"] == "dx.example.net"
    assert saved["target_priority"]["new_dxcc"] == 10000


def test_mshv_settings_parse_qt_quoted_csv_lists(tmp_path, monkeypatch):
    import services.mshv_configuration as configuration

    runtime = tmp_path / "runtime"
    settings = runtime / "settings" / "autodx.ini"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '[BandSelection]\nEnabledBands="3,4,6,7,8,9,10,11,12"\n'
        '[Eligibility]\nFilterContinents="AF,AN,AS,NA,OC,SA"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))

    observed = configuration.read_mshv_auto_dx_settings(engine_running=False)

    assert observed["enabled_bands"] == [3, 4, 6, 7, 8, 9, 10, 11, 12]
    assert observed["filter_continents"] == ["AF", "OC", "AS", "SA", "NA", "AN"]


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"auto_dx_modes": ["FT2"]}, "FT8 and FT4 only"),
        ({"enabled_bands": [5]}, "not allowed"),
        ({"spot_sources": {"rbn": {"host": "bad host"}}}, "host is invalid"),
        ({"spot_sources": {"dx_cluster": {"servers": [{}]}}}, "invalid name or host"),
    ],
)
def test_mshv_phase1_runtime_schema_rejects_dormant_or_unsafe_values(tmp_path, monkeypatch, payload, match):
    import services.mshv_configuration as configuration

    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(tmp_path / "runtime"))
    with pytest.raises(HTTPException, match=match):
        configuration.update_mshv_auto_dx_settings(payload, engine_running=False)


def test_mshv_phase1_rejects_conflicting_deprecated_us_only_alias(tmp_path, monkeypatch):
    import services.mshv_configuration as configuration

    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(tmp_path / "runtime"))
    with pytest.raises(HTTPException, match="conflicts"):
        configuration.update_mshv_auto_dx_settings(
            {
                "spot_sources_us_only": True,
                "spot_sources": {"us_only": False},
            },
            engine_running=False,
        )


def test_mshv_ft4_mode_is_active_on_read(tmp_path, monkeypatch):
    import services.mshv_configuration as configuration

    runtime = tmp_path / "runtime"
    settings = runtime / "settings" / "autodx.ini"
    settings.parent.mkdir(parents=True)
    settings.write_text("[AutoDx]\nEnabled=true\nModes=FT4\n", encoding="utf-8")
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    observed = configuration.read_mshv_auto_dx_settings(engine_running=False)
    assert observed["auto_dx_modes"] == ["FT4"]
    assert observed["desired"]["auto_dx_modes"] == ["FT4"]


def test_mshv_phase1_runtime_parity_detects_match_drift_and_unknown(tmp_path, monkeypatch):
    import services.mshv_configuration as configuration

    runtime = tmp_path / "runtime"
    settings = runtime / "settings" / "autodx.ini"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        "[AutoDx]\nEnabled=false\nModes=FT8\nATNOChaseType=3\nScarceThreshold=5\n"
        "[SpotSources]\nCallsign=OM0RX\nGrid=JN88\nMinSNR=-20\nUsOnlyFilter=false\n"
        "RbnEnabled=true\nRbnHost=telnet.reversebeacon.net\nRbnPort=7001\n"
        "PskEnabled=true\nPskPollInterval=120\nDxcEnabled=true\nUseDefaultDxClusterServers=false\n"
        "[GridChase]\nEnabled=true\nUSOnly=false\n"
        "[BandSwitching]\nEnabled=false\n"
        "[BandSelection]\nEnabledBands=3,4,6,7,8,9,10,11,12\n"
        "[DxClusterServers]\nCount=1\nServer0=Primary|cluster.example.net|7300|true\n"
        "[TargetPriority]\nNewDxcc=10000\nNewBandSlot=1000\nNewGrid=500\nCallingMe=400\nCq=200\nSnrPerDb=10\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")

    stopped = configuration.read_mshv_auto_dx_settings(engine_running=False)
    assert stopped["runtime_parity"]["status"] == "unknown"
    effective = json.loads(json.dumps(stopped["desired"]))
    effective["schema_version"] = 1
    effective["desired_enabled"] = effective.pop("enabled")
    effective["effective_enabled"] = False
    effective.pop("enabled_band_names")
    effective["spot_sources"]["dx_cluster"]["server_count"] = 1
    effective["us_states"]["known_calls"] = 7844
    effective["us_states"]["complete_slots"] = 337
    matched = configuration.read_mshv_auto_dx_settings(
        engine_running=True, engine_state={"autodx_config": effective},
    )
    assert matched["runtime_parity"] == {"status": "match", "drift": []}

    effective["min_snr"] = -12
    drifted = configuration.read_mshv_auto_dx_settings(
        engine_running=True, engine_state={"autodx_config": effective},
    )
    assert drifted["runtime_parity"]["status"] == "drift"
    assert drifted["runtime_parity"]["drift"] == ["min_snr"]

    unknown = configuration.read_mshv_auto_dx_settings(
        engine_running=True, engine_state={"autodx_config": {"schema_version": 1}},
    )
    assert unknown["runtime_parity"]["status"] == "unknown"
    assert "min_snr" in unknown["runtime_parity"]["missing"]


def test_bridge_denial_does_not_commit_selection(service, monkeypatch):
    monkeypatch.setattr(service, "_legacy", lambda: SimpleNamespace(send_bridge_command=lambda *args: {"success": False}))
    with pytest.raises(HTTPException, match="acknowledge"):
        service.select({"provider": "mshv_auto_dx"})
    assert digital.selected_provider() == "none"


def test_station_ready_fails_closed_without_selected_mshv(service):
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        response = client.post("/api/digital/station-ready", json={"provider": "mshv_auto_dx", "request_id": "one", "band": "20m", "frequency_hz": 14074000, "authorization_generation": 1})
    assert response.json()["ready"] is False


def test_node_pairs_interleaved_qsos_and_blocks_mshv_target_command():
    script = """
      import {LoggedQsoCoalescer, plannerOwnerForProvider, providerForClient} from './bridge/digital-provider.js';
      process.env.OM0RX_BRIDGE_TEST_MODE='1';
      const bridge=await import('./bridge/sdc-bridge-server.js');
      const uploads=[]; const c=new LoggedQsoCoalescer(x=>uploads.push(x.dxCall),20);
      const a={dxCall:'A1AA',mode:'FT8',dialFrequency:14074000};
      const b={...a,dxCall:'B1BB'};
      c.accept('QSO_LOGGED',a); c.accept('QSO_LOGGED',b);
      c.accept('LOGGED_ADIF',a); c.accept('LOGGED_ADIF',a);
      await new Promise(resolve=>setTimeout(resolve,40));
      c.accept('LOGGED_ADIF',b);
      bridge.__dispatchWsjtxCommandForTest('select_provider',{provider:'mshv_auto_dx'});
      const denied=bridge.__dispatchWsjtxCommandForTest('start_target_qso',{});
      console.log(JSON.stringify({
        uploads,
        denied,
        mshv:providerForClient('MSHV-OM0RX-AUTO-DX'),
        plannerOwners:['none','wsjtz','mshv_auto_dx'].map(plannerOwnerForProvider),
      }));
      c.reset();
    """
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout.splitlines()[-1])
    # Every type5 receipt is durable immediately; type12 later upgrades the
    # same QSO with authoritative ADIF. Repeated type12 is suppressed.
    assert data["uploads"] == ["A1AA", "B1BB", "A1AA", "B1BB"]
    assert data["denied"]["success"] is False
    assert data["mshv"] == "mshv_auto_dx"
    assert data["plannerOwners"] == ["none", "om0rx", "mshv"]


def test_canonical_history_is_deterministic_and_prefers_wavelog():
    from scripts.digital.export_history import create_snapshot, parse_adif
    adif = "<CALL:4>A1AA <QSO_DATE:8>20261001 <TIME_ON:4>1200 <BAND:3>20m <MODE:4>MFSK <SUBMODE:3>FT4 <NAME:3>A<B <EOR>"
    supplemental = list(parse_adif(adif))
    canonical = [{**supplemental[0], "NAME": "Canonical", "DXCC": "291"}]
    first, report = create_snapshot([("postgres-wavelog-mirror", canonical), ("adif", supplemental)], "OM0RX")
    second, _ = create_snapshot([("postgres-wavelog-mirror", canonical), ("adif", supplemental)], "OM0RX")
    assert first == second
    assert report["total_records"] == 1
    assert report["duplicates_merged"] == 1
    assert report["by_mode"] == {"FT4": 1}
    assert "<NAME:9>Canonical" in first
    assert "<TIME_ON:6>120000" in first


def test_truncated_history_is_rejected_before_output():
    from scripts.digital.export_history import parse_adif
    with pytest.raises(ValueError):
        list(parse_adif("<CALL:9>A1"))


def test_type5_is_provisional_and_type12_submits_complete_adif_once(tmp_path, monkeypatch):
    import services.digital_logging as logging
    import services.mshv_history as history
    monkeypatch.setattr(logging, "PROVISIONAL_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(history, "DELTA_PATH", tmp_path / "deltas.json")
    submitted = []
    async def log(request):
        submitted.append(request)
        return {"success": True, "wavelog": {"success": True}}
    event_id = "a" * 64
    payload = {
        "call": "A1AA", "mode": "FT4", "provider": "mshv_auto_dx",
        "station_callsign": "OM0RX", "client_id": "MSHV-OM0RX-AUTO-DX",
        "event_id": event_id, "frequency_hz": 14080000,
        "date_time": "2026-10-04T12:00:15+00:00",
    }
    receipt = asyncio.run(logging.log_digital_qso({**payload, "event_type": "QSO_LOGGED"}, SimpleNamespace(log_qso=log)))
    assert receipt["provisional_queued"] and not submitted
    adif = "<CALL:4>A1AA <MODE:3>FT4 <QSO_DATE:8>20261004 <TIME_ON:6>120000 <TIME_OFF:6>120015 <FREQ:5>14.08 <GRIDSQUARE:6>JN88AA <DXCC:3>291 <EOR>"
    asyncio.run(logging.log_digital_qso({**payload, "event_type": "LOGGED_ADIF", "adif_text": adif}, SimpleNamespace(log_qso=log)))
    assert len(submitted) == 1 and submitted[0]["adif_text"] == adif
    assert not logging.provisional_records()


def test_type12_does_not_clear_ambiguous_provisional_receipts(tmp_path, monkeypatch):
    import services.digital_logging as logging
    import services.mshv_history as history
    monkeypatch.setattr(logging, "PROVISIONAL_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(history, "DELTA_PATH", tmp_path / "deltas.json")
    submitted = []
    async def log(request):
        submitted.append(request)
        return {"success": True, "wavelog": {"success": True}}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    base = {
        "call": "A1AA", "mode": "FT8", "provider": "mshv_auto_dx",
        "station_callsign": "OM0RX", "client_id": "MSHV-OM0RX-AUTO-DX",
        "frequency_hz": 14074000, "event_type": "QSO_LOGGED",
    }
    asyncio.run(logging.log_digital_qso({**base, "event_id": "b" * 64, "date_time": (now - timedelta(seconds=4)).isoformat()}, SimpleNamespace(log_qso=log)))
    asyncio.run(logging.log_digital_qso({**base, "event_id": "c" * 64, "date_time": (now + timedelta(seconds=4)).isoformat()}, SimpleNamespace(log_qso=log)))
    adif_time = now.strftime("%Y%m%d%H%M%S")
    adif = f"<CALL:4>A1AA <MODE:3>FT8 <QSO_DATE:8>{adif_time[:8]} <TIME_ON:6>{adif_time[8:]} <TIME_OFF:6>{adif_time[8:]} <FREQ:6>14.074 <EOR>"
    result = asyncio.run(logging.log_digital_qso({**base, "event_id": "d" * 64, "event_type": "LOGGED_ADIF", "adif_text": adif}, SimpleNamespace(log_qso=log)))
    assert result["provisional_upgrade"] == "ambiguous"
    assert len(logging.provisional_records()) == 2
    assert len(submitted) == 1


def test_forensics_crosses_midnight_and_never_supplements_production():
    from scripts.digital.export_history import create_snapshot
    canonical = {"CALL": "A1AA", "QSO_DATE": "20261004", "TIME_ON": "000030", "MODE": "FT8", "BAND": "20m", "FREQ": "14.074", "_SOURCE_ID": "1"}
    prior = {**canonical, "QSO_DATE": "20261003", "TIME_ON": "235930"}
    absent = {**canonical, "CALL": "B1BB"}
    audit = []
    text, report = create_snapshot([("postgres-wavelog-mirror", [canonical]), ("adif", [prior, absent])], "OM0RX", audit_output=audit)
    assert report["total_records"] == 1
    assert report["reconciliation"]["likely_duplicate"] == 1
    assert "B1BB" not in text
    assert [entry["record"]["CALL"] for entry in audit if entry["classification"] == "genuinely_absent"] == ["B1BB"]


def test_only_digital_scope_band_frequency_mismatches_block_migration():
    from scripts.digital.export_history import create_snapshot
    rows = [
        {"_SOURCE_ID": "144533", "CALL": "FS/W1NA", "QSO_DATE": "20250621", "TIME_ON": "212621", "MODE": "SSB", "BAND": "17m", "FREQ": "1.815"},
        {"_SOURCE_ID": "148686", "CALL": "DL0SOP", "QSO_DATE": "20250724", "TIME_ON": "174440", "MODE": "CW", "BAND": "20m", "FREQ": "7.015064"},
        {"_SOURCE_ID": "171175", "CALL": "ON3QRP", "QSO_DATE": "20260527", "TIME_ON": "231128", "MODE": "FT8", "BAND": "40m", "FREQ": "1.84"},
    ]
    _, report = create_snapshot([("postgres-wavelog-mirror", rows)], "OM0RX")
    assert report["migration_eligible"] is False
    assert report["canonical_band_frequency_mismatch_count"] == 3
    assert {item["wavelog_primary_ids"][0] for item in report["canonical_band_frequency_mismatches"]} == {"144533", "148686", "171175"}
    assert report["migration_scope_band_frequency_mismatch_count"] == 1
    assert report["migration_scope_band_frequency_mismatches"][0]["wavelog_primary_ids"] == ["171175"]


def test_all_mode_mismatches_are_reported_but_do_not_block_digital_migration_scope():
    from scripts.digital.export_history import create_snapshot
    rows = [
        {"_SOURCE_ID": "144533", "CALL": "FS/W1NA", "QSO_DATE": "20250621", "TIME_ON": "212621", "MODE": "SSB", "BAND": "17m", "FREQ": "1.815"},
        {"_SOURCE_ID": "148686", "CALL": "DL0SOP", "QSO_DATE": "20250724", "TIME_ON": "174440", "MODE": "CW", "BAND": "20m", "FREQ": "7.015064"},
    ]
    _, report = create_snapshot([("postgres-wavelog-mirror", rows)], "OM0RX")
    assert report["migration_eligible"] is True
    assert report["canonical_band_frequency_mismatch_count"] == 2
    assert report["migration_scope_band_frequency_mismatch_count"] == 0


@pytest.mark.parametrize("changes,classification", [({"CALL": "A1AA/P"}, "ambiguous"), ({"FREQ": "14.079"}, "likely_duplicate"), ({"FREQ": "14.0791"}, "ambiguous"), ({"FREQ": ""}, "likely_duplicate"), ({"BAND": "40m"}, "ambiguous")])
def test_forensic_portable_frequency_and_band_cases(changes, classification):
    from scripts.digital.export_history import create_snapshot
    row = {"CALL": "A1AA", "QSO_DATE": "20261004", "TIME_ON": "120000", "MODE": "FT8", "BAND": "20m", "FREQ": "14.074"}
    other = {**row, "TIME_ON": "120100", **changes}
    audit = []
    create_snapshot([("postgres-wavelog-mirror", [row]), ("adif", [other])], "OM0RX", audit_output=audit)
    assert audit[0]["classification"] == classification


def test_repeated_near_contacts_are_ambiguous():
    from scripts.digital.export_history import create_snapshot
    row = {"CALL": "A1AA", "QSO_DATE": "20261004", "TIME_ON": "120000", "MODE": "FT8", "BAND": "20m"}
    audit = []
    _, report = create_snapshot([("postgres-wavelog-mirror", [row, {**row, "TIME_ON": "120200"}]), ("adif", [{**row, "TIME_ON": "120100"}])], "OM0RX", audit_output=audit)
    assert report["reconciliation"]["ambiguous"] == 1


def test_utc_datetime_normalization_and_wrong_station_rejection():
    from datetime import datetime, timezone, timedelta
    from scripts.digital.export_history import utc_log_datetime, normalize
    assert utc_log_datetime(datetime(2026, 10, 4, 12)).hour == 12
    assert utc_log_datetime(datetime(2026, 10, 4, 12, tzinfo=timezone(timedelta(hours=2)))).hour == 10
    assert normalize({"STATION_CALLSIGN": "OTHER"}, "OM0RX") is None


def test_station_readback_does_not_trust_command_ack():
    desired = {"rx": "ANT1", "tx": "ANT1"}
    levels = {"mox": False, "interlock_state": "READY", "rx_ant": "ANT2", "tx_ant": "ANT1"}
    assert digital.verify_station_readback(levels, desired) == "radio-antenna-readback-mismatch"
    levels["rx_ant"] = "ANT1"
    status = {
        "connected": True,
        "responsive": True,
        "missing_fields": [],
        "power": True,
        "band": "40m",
        "fault": "0",
        "operate": True,
        "output_power_w": 0,
        "current": 0,
    }
    assert digital.verify_station_readback(levels, desired, {"kpa500": {"status": status, "band": "20m"}}) == "kpa500-readback-not-ready"
    status["band"] = "20m"
    assert digital.verify_station_readback(levels, desired, {"kpa500": {"status": status, "band": "20m"}}) is None


def test_barefoot_kpa_policy_requires_exact_standby_and_zero_tx_readback():
    levels = {"mox": False, "interlock_state": "READY", "rx_ant": "ANT1", "tx_ant": "ANT1"}
    status = {
        "connected": True, "responsive": True, "missing_fields": [],
        "power": True, "band": "40m", "fault": "00",
        "operate": False, "output_power_w": 0, "current": 0,
    }
    expected = {"status": status, "band": "40m", "operate": False}
    assert digital.verify_station_readback(levels, {"rx": "ANT1", "tx": "ANT1"}, {"kpa500": expected}) is None
    for changes in (
        {"operate": True}, {"fault": "01"}, {"output_power_w": 1}, {"current": .1},
    ):
        bad = {**status, **changes}
        assert digital.verify_station_readback(
            levels,
            {"rx": "ANT1", "tx": "ANT1"},
            {"kpa500": {**expected, "status": bad}},
        ) == "kpa500-fault-or-transmit-readback"


def test_station_readback_rejects_incomplete_or_bypass_kat_state():
    levels = {
        "mox": False,
        "interlock_state": "READY",
        "rx_ant": "ANT1",
        "tx_ant": "ANT1",
    }
    status = {
        "connected": True,
        "responsive": True,
        "missing_fields": [],
        "power": True,
        "band": "40m",
        "mode": "auto",
        "antenna": 2,
        "frequency_khz": 7074,
        "tuning": False,
        "fault": "0",
    }
    expected = {
        "status": status,
        "band": "40m",
        "antenna": 2,
        "frequency_khz": 7074,
    }

    assert digital.verify_station_readback(
        levels,
        {"rx": "ANT1", "tx": "ANT1"},
        {"kat500": expected},
    ) is None
    for changes in (
        {"mode": "bypass"},
        {"fault": "2"},
        {"missing_fields": ["fault"]},
    ):
        bad = {**status, **changes}
        assert digital.verify_station_readback(
            levels,
            {"rx": "ANT1", "tx": "ANT1"},
            {"kat500": {**expected, "status": bad}},
        ) is not None


def test_station_ready_requires_two_phase_and_fresh_target_readback(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    from radio_control import config as radio_config
    monkeypatch.setattr(radio_config, "KPA500_ENABLED", False)
    monkeypatch.setattr(radio_config, "KAT500_ENABLED", False)
    calls = []
    class FakeFlex:
        current_mox = False
        sock = object()
        pending_external_frequency = None
        pending_external_frequency_until = 0
        rfpower = 25
        def desired_antennas_for_current_config(self, mhz):
            return {"rx": "ANT1", "tx": "ANT1"}
        def enforce_antenna_policy(self, mhz, reason=""):
            calls.append(("policy", mhz, reason))
            return True
        def get_current_levels(self, timeout=.5, *, apply_antenna_policy=True):
            calls.append(("read", apply_antenna_policy))
            # TX fields on the long-lived socket may be absent.  The endpoint
            # must use the independent fresh subscription below instead.
            return {"freq": 14.074, "mode": "DIGU", "rx_ant": "ANT1", "tx_ant": "ANT1", "rfpower": self.rfpower}
        def set_rf_power(self, power):
            self.rfpower = int(power)
            calls.append(("rfpower", self.rfpower))
            return True
        def get_fresh_tx_state(self, timeout=1.5):
            calls.append(("fresh_tx", timeout))
            return {"confirmed": True, "mox": False, "interlock_state": "READY"}
    fake = FakeFlex()
    monkeypatch.setattr(radio, "get_radio_instance", lambda: fake)
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        invalid = client.post("/api/digital/station-ready", json={"provider": "mshv_auto_dx", "request_id": "one", "band": "20m", "frequency_hz": 14074000, "authorization_generation": 1})
        prepare = client.post("/api/digital/station-ready", json={"provider": "mshv_auto_dx", "request_id": "one", "phase": "prepare", "band": "20m", "frequency_hz": 14074000, "authorization_generation": 1})
        delayed_revoke = client.post("/api/digital/station-audit", json={"provider": "mshv_auto_dx", "event": "authorization-invalidated", "reason": "delayed-test-revoke", "authorization_generation": 1})
        final_only = client.post("/api/digital/station-ready", json={"provider": "mshv_auto_dx", "request_id": "missing", "phase": "final", "band": "20m", "frequency_hz": 14074000, "authorization_generation": 1})
        final = client.post("/api/digital/station-ready", json={"provider": "mshv_auto_dx", "request_id": "two", "phase": "final", "band": "20m", "frequency_hz": 14074000, "authorization_generation": 1, "prepare_nonce": prepare.json().get("prepare_nonce")})
        replay = client.post("/api/digital/station-ready", json={"provider": "mshv_auto_dx", "request_id": "three", "phase": "final", "band": "20m", "frequency_hz": 14074000, "authorization_generation": 1, "prepare_nonce": prepare.json().get("prepare_nonce")})
    assert invalid.json()["ready"] is False
    assert prepare.json()["ready"] is True and prepare.json()["transmit_ready"] is False
    assert delayed_revoke.json()["reason"] == "native-invalidation-already-observed"
    assert final_only.json()["reason"] == "prepare-nonce-missing-or-replayed"
    assert final.json()["ready"] is True and final.json()["transmit_ready"] is True
    assert final.json()["permit_nonce"]
    assert replay.json()["reason"] == "prepare-nonce-missing-or-replayed"
    assert all(entry[1] is False for entry in calls if entry[0] == "read")


def test_bridge_identity_loss_between_prepare_and_final_is_audited_by_stage(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    from radio_control import config as radio_config
    monkeypatch.setattr(radio_config, "KPA500_ENABLED", False)
    monkeypatch.setattr(radio_config, "KAT500_ENABLED", False)

    class FakeFlex:
        current_mox = False
        sock = object()
        pending_external_frequency = None
        pending_external_frequency_until = 0
        def desired_antennas_for_current_config(self, _mhz):
            return {"rx": "ANT1", "tx": "ANT1"}
        def enforce_antenna_policy(self, _mhz, reason=""):
            return True
        def get_current_levels(self, **_kwargs):
            return {"freq": 14.074, "mode": "DIGU", "rx_ant": "ANT1", "tx_ant": "ANT1", "rfpower": 25}
        def get_fresh_tx_state(self, **_kwargs):
            return {"confirmed": True, "mox": False, "interlock_state": "READY"}

    monkeypatch.setattr(radio, "get_radio_instance", lambda: FakeFlex())
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    original_binding = service.station_process_binding
    calls = {"count": 0}

    def binding_then_loss(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return original_binding(**kwargs)
        raise HTTPException(409, "fresh exact MSHV bridge identity is unavailable")

    monkeypatch.setattr(service, "station_process_binding", binding_then_loss)
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        prepare = client.post("/api/digital/station-ready", json={
            "provider": "mshv_auto_dx", "request_id": "bridge-prepare",
            "phase": "prepare", "band": "20m", "frequency_hz": 14074000,
            "authorization_generation": 1,
        })
        final = client.post("/api/digital/station-ready", json={
            "provider": "mshv_auto_dx", "request_id": "bridge-final",
            "phase": "final", "band": "20m", "frequency_hz": 14074000,
            "authorization_generation": 1,
            "prepare_nonce": prepare.json().get("prepare_nonce"),
        })

    assert prepare.json()["ready"] is True
    assert final.json()["ready"] is False
    assert final.json()["reason"] == "station-preparation-failed"
    assert final.json()["failure_stage"] == "bind-process-client"
    audit = digital.STATION_AUDIT_PATH.read_text(encoding="utf-8")
    assert '"event":"station-ready-failed"' in audit
    assert '"failure_stage":"bind-process-client"' in audit


def test_station_ready_keeps_disallowed_band_barefoot_then_final_route(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    from backend.core import context
    from radio_control import config as radio_config
    import radio_control.elecraft as elecraft

    monkeypatch.setattr(radio_config, "KPA500_ENABLED", True)
    monkeypatch.setattr(radio_config, "KAT500_ENABLED", True)
    monkeypatch.setattr(radio_config, "DIGITAL_KPA_POLICY", "operate")
    monkeypatch.setattr(radio_config, "STATION_AMPLIFIER_ALLOWED_BANDS", ["20m"])
    monkeypatch.setattr(radio_config, "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS", ["40m"])
    monkeypatch.setattr(
        radio_config,
        "STATION_DIGITAL_AMPLIFIER_DRIVE_W",
        {"20M": 10},
    )
    monkeypatch.setattr(radio_config, "STATION_BAREFOOT_DRIVE_W", {"20M": 25})
    monkeypatch.setattr(radio_config, "KAT500_ANTENNA_POLICY", {"20m": 2})
    events = []

    class FakeFlex:
        current_mox = False
        sock = object()
        pending_external_frequency = None
        pending_external_frequency_until = 0
        def desired_antennas_for_current_config(self, _mhz):
            return {"rx": "ANT1", "tx": "ANT1"}
        def enforce_antenna_policy(self, _mhz, reason=""):
            events.append(("flex-policy", reason))
            return True
        def get_current_levels(self, **_kwargs):
            return {"freq": 14.074, "mode": "DIGU", "rx_ant": "ANT1", "tx_ant": "ANT1", "rfpower": 25}
        def get_fresh_tx_state(self, **_kwargs):
            return {"confirmed": True, "mox": False, "interlock_state": "READY"}

    class FakeCoordinator:
        async def ensure_external_digital_standby(self):
            events.append(("coordinator", "external-standby"))
        async def prepare_external_digital_route(self, mhz, amplifier_operate):
            events.append(("external-route", mhz, amplifier_operate))

    class FakeManager:
        antenna_policy = {"20m": 2}
        def snapshot(self):
            return {
                "updated_at": digital.time.time(),
                "kpa500": {
                    "connected": True, "responsive": True, "missing_fields": [],
                    "power": True, "band": "20m", "fault": "00",
                    "operate": False, "output_power_w": 0, "current": 0,
                },
                "kat500": {
                    "connected": True, "responsive": True, "missing_fields": [],
                    "power": True, "band": "20m", "mode": "auto", "antenna": 2,
                    "frequency_khz": 14074, "tuning": False, "fault": "0",
                },
            }
        async def refresh_status(self):
            events.append(("accessory", "refresh"))
            return self.snapshot()

    monkeypatch.setattr(radio, "get_radio_instance", lambda: FakeFlex())
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    monkeypatch.setattr(context, "station_coordinator", FakeCoordinator())
    monkeypatch.setattr(elecraft, "get_elecraft_manager", lambda: FakeManager())
    app = FastAPI()
    digital.register_digital_endpoints(app)
    service.engine_state = {"provider": "mshv_auto_dx", "state": "Idle", "enabled": True}
    service.engine_state_at = digital.time.monotonic()
    with TestClient(app) as client:
        prepare = client.post("/api/digital/station-ready", json={
            "provider": "mshv_auto_dx", "request_id": "order-prepare",
            "phase": "prepare", "band": "20m", "frequency_hz": 14074000,
            "authorization_generation": 1,
        })
        final = client.post("/api/digital/station-ready", json={
            "provider": "mshv_auto_dx", "request_id": "order-final",
            "phase": "final", "band": "20m", "frequency_hz": 14074000,
            "authorization_generation": 1,
            "prepare_nonce": prepare.json().get("prepare_nonce"),
        })
        consumed = client.post("/api/digital/station-permit/consume", json={
            "provider": "mshv_auto_dx",
            "permit_nonce": final.json().get("permit_nonce"),
            "frequency_hz": 14074000,
            "mode": "DIGU",
            "path": "disallowed-band-regression",
            "authorization_generation": 1,
        })

    assert prepare.json()["ready"] is True
    assert final.json()["transmit_ready"] is True
    assert final.json()["station_policy"]["kpa500"] == "standby"
    assert final.json()["station_policy"]["configured_kpa500"] == "operate"
    assert final.json()["station_policy"]["amplifier_allowed"] is False
    assert final.json()["station_policy"]["amplifier_drive_w"] == 10
    assert final.json()["station_policy"]["active_drive_w"] == 25
    assert consumed.json()["success"] is True
    assert consumed.json()["reason"] == "permit-consumed"
    standby_index = events.index(("coordinator", "external-standby"))
    route_index = events.index(("external-route", 14.074, False))
    refresh_index = events.index(("accessory", "refresh"))
    assert standby_index < route_index < refresh_index


@pytest.mark.parametrize("interruption", ["clear", "newer-generation", "provider-change", "halt"])
def test_final_readiness_cannot_mint_permit_after_authorization_interruption(
    service, monkeypatch, interruption,
):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    from radio_control import config as radio_config
    monkeypatch.setattr(radio_config, "KPA500_ENABLED", False)
    monkeypatch.setattr(radio_config, "KAT500_ENABLED", False)

    class FakeFlex:
        current_mox = False
        sock = object()
        pending_external_frequency = None
        pending_external_frequency_until = 0
        def desired_antennas_for_current_config(self, _mhz):
            return {"rx": "ANT1", "tx": "ANT1"}
        def enforce_antenna_policy(self, _mhz, reason=""):
            return True
        def get_current_levels(self, **_kwargs):
            return {
                "freq": 14.074, "mode": "DIGU",
                "rx_ant": "ANT1", "tx_ant": "ANT1",
            }
        def get_fresh_tx_state(self, **_kwargs):
            return {"confirmed": True, "mox": False, "interlock_state": "READY"}
        def set_mox(self, enabled):
            assert enabled is False
            return True

    monkeypatch.setattr(radio, "get_radio_instance", lambda: FakeFlex())
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    app = FastAPI()
    digital.register_digital_endpoints(app)
    consumed = threading.Event()
    resume = threading.Event()
    original_consume = service.consume_station_preparation

    def consume_then_pause(*args, **kwargs):
        result = original_consume(*args, **kwargs)
        assert result[0] is True
        consumed.set()
        assert resume.wait(5)
        return result

    monkeypatch.setattr(service, "consume_station_preparation", consume_then_pause)
    with TestClient(app) as client:
        prepare = client.post("/api/digital/station-ready", json={
            "provider": "mshv_auto_dx", "request_id": "prepare",
            "phase": "prepare", "band": "20m", "frequency_hz": 14074000,
            "authorization_generation": 10,
        })
        assert prepare.json()["ready"] is True
        result = {}
        worker = threading.Thread(target=lambda: result.setdefault(
            "response", client.post("/api/digital/station-ready", json={
                "provider": "mshv_auto_dx", "request_id": "final",
                "phase": "final", "band": "20m", "frequency_hz": 14074000,
                "authorization_generation": 10,
                "prepare_nonce": prepare.json()["prepare_nonce"],
            })), daemon=True)
        worker.start()
        assert consumed.wait(5)
        if interruption == "clear":
            service.clear_station_authorizations("barrier-test-clear")
        elif interruption == "newer-generation":
            assert service.apply_native_invalidation("barrier-test-newer", 11)[0] is True
        elif interruption == "provider-change":
            digital.atomic_write_json(digital.STATE_PATH, {"provider": "none"})
        else:
            halted = service.halt()
            assert halted["command_accepted"] is True
        resume.set()
        worker.join(10)
        assert not worker.is_alive()

    payload = result["response"].json()
    assert payload["ready"] is False
    assert payload["transmit_ready"] is False
    assert "permit_nonce" not in payload
    assert not service.station_permits


def test_slow_process_refresh_never_blocks_emergency_halt(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    binding = {
        "provider": "mshv_auto_dx", "pid": 321,
        "process_identity": ["mshv.exe", "--om0rx", "20261004120000.000000+000"],
        "bridge_client_id": "MSHV-OM0RX-AUTO-DX",
        "bridge_address": "127.0.0.1", "bridge_port": 22370,
        "frequency_hz": 7074000, "band": "40m", "mode": "DIGU",
        "rx_ant": "ANT1", "tx_ant": "ANT1",
        "kpa_policy": "standby", "kat_antenna": 2,
        "native_generation": 8,
    }
    service.station_client_generation = 8
    entered_scan = threading.Event()
    release_scan = threading.Event()

    def slow_process_binding(**_kwargs):
        entered_scan.set()
        assert release_scan.wait(5)
        return {key: binding[key] for key in (
            "provider", "pid", "process_identity", "bridge_client_id",
            "bridge_address", "bridge_port",
        )}

    monkeypatch.setattr(service, "station_process_binding", slow_process_binding)
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)

    class FakeFlex:
        def set_mox(self, enabled):
            assert enabled is False
            return True

    monkeypatch.setattr(radio, "get_radio_instance", lambda: FakeFlex())
    monkeypatch.setattr(radio, "run_radio_io_sync", lambda operation: operation())
    outcome = {}

    def issue_permit():
        try:
            service.create_station_permit(
                binding, expected_epoch=service.station_authorization_epoch,
                native_generation=8,
            )
        except Exception as exc:
            outcome["error"] = exc

    worker = threading.Thread(target=issue_permit, daemon=True)
    worker.start()
    assert entered_scan.wait(5)
    started = time.monotonic()
    halted = service.halt()
    elapsed = time.monotonic() - started
    assert halted["command_accepted"] is True
    assert halted["idle_confirmed"] is True
    assert elapsed < .25
    release_scan.set()
    worker.join(5)
    assert not worker.is_alive()
    assert isinstance(outcome.get("error"), RuntimeError)
    assert not service.station_permits


def test_station_authorization_nonces_are_expiring_single_use_and_binding_bound(service):
    binding = {
        "provider": "mshv_auto_dx", "pid": 321,
        "process_identity": ["mshv.exe", "--om0rx", "20261004120000.000000+000"],
        "bridge_client_id": "MSHV-OM0RX-AUTO-DX",
        "bridge_address": "127.0.0.1", "bridge_port": 22370,
        "frequency_hz": 7074000, "band": "40m", "mode": "DIGU",
        "rx_ant": "ANT1", "tx_ant": "ANT1",
        "kpa_policy": "standby", "kat_antenna": 2,
        "native_generation": 7,
    }
    nonce, _ = service.create_station_preparation(binding)
    assert service.consume_station_preparation(nonce, binding) == (True, "station-prepared", 0, 7)
    assert service.consume_station_preparation(nonce, binding) == (False, "prepare-nonce-missing-or-replayed", None, None)

    mismatch_nonce, _ = service.create_station_preparation(binding)
    changed = {**binding, "pid": 999}
    assert service.consume_station_preparation(mismatch_nonce, changed) == (False, "prepare-nonce-binding-mismatch", None, None)

    expired_nonce, _ = service.create_station_preparation(binding)
    service.station_preparations[expired_nonce]["expires_at"] = 0
    assert service.consume_station_preparation(expired_nonce, binding) == (False, "prepare-nonce-expired", None, None)

    permit, _ = create_test_permit(service, binding)
    assert service.consume_station_permit(permit, binding) == (True, "permit-consumed")
    assert service.consume_station_permit(permit, binding) == (False, "permit-replayed")


def test_station_control_lease_revokes_permits_and_inhibits_new_authorizations(service):
    binding = {
        "provider": "mshv_auto_dx", "pid": 321,
        "process_identity": ["mshv.exe", "--om0rx", "20261004120000.000000+000"],
        "bridge_client_id": "MSHV-OM0RX-AUTO-DX",
        "bridge_address": "127.0.0.1", "bridge_port": 22370,
        "frequency_hz": 7074000, "band": "40m", "mode": "DIGU",
        "rx_ant": "ANT1", "tx_ant": "ANT1",
        "kpa_policy": "standby", "rf_drive_w": 25, "kat_antenna": 2,
        "native_generation": 7,
    }
    permit, _ = create_test_permit(service, binding)

    token = service.acquire_station_control_lease("manual-operate-test")

    assert service.station_control_inhibit() == "manual-operate-test"
    assert service.consume_station_permit(permit, binding) == (
        False, "station-control-inhibited",
    )
    assert service.begin_station_preparation(8)[0:2] == (
        False, "station-control-inhibited",
    )
    with pytest.raises(RuntimeError, match="station control is inhibited"):
        service.create_station_preparation(binding)
    assert service.release_station_control_lease("wrong-token") is False
    assert service.release_station_control_lease(token) is True
    assert service.station_control_inhibit() is None


def test_prepare_retires_old_permit_and_delayed_matching_invalidation_cannot_revoke_new_generation(service):
    binding = {
        "provider": "mshv_auto_dx", "pid": 321,
        "process_identity": ["mshv.exe", "--om0rx", "20261004120000.000000+000"],
        "bridge_client_id": "MSHV-OM0RX-AUTO-DX",
        "bridge_address": "127.0.0.1", "bridge_port": 22370,
        "frequency_hz": 7074000, "band": "40m", "mode": "DIGU",
        "rx_ant": "ANT1", "tx_ant": "ANT1",
        "kpa_policy": "standby", "kat_antenna": 2,
        "native_generation": 42,
    }
    old_permit, _ = create_test_permit(service, {**binding, "native_generation": 41})
    begun, reason, epoch = service.begin_station_preparation(42)
    assert (begun, reason) == (True, "prepare-authorization-begun")
    assert service.consume_station_permit(
        old_permit, {**binding, "native_generation": 41},
    ) == (False, "permit-revoked")
    preparation, _ = service.create_station_preparation(
        binding,
        expected_epoch=epoch,
        native_generation=42,
    )

    # Models the async native invalidation POST arriving after the immediate
    # prepare request.  Same-generation notification is already represented by
    # begin_station_preparation and must not clear its newly issued nonce.
    applied, delayed_reason = service.apply_native_invalidation(
        "delayed-native-revoke", 42,
    )
    assert applied is False
    assert delayed_reason == "native-invalidation-already-observed"
    assert service.consume_station_preparation(preparation, binding) == (
        True, "station-prepared", epoch, 42,
    )

    # A genuinely newer Stop/QSY generation remains authoritative.
    next_preparation, _ = service.create_station_preparation(binding)
    applied, _ = service.apply_native_invalidation("newer-native-stop", 43)
    assert applied is True
    assert service.consume_station_preparation(next_preparation, binding) == (
        False, "prepare-nonce-missing-or-replayed", None, None,
    )


def test_station_permit_consume_endpoint_is_authoritative_and_fail_closed(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    from radio_control import config as radio_config
    monkeypatch.setattr(radio_config, "KPA500_ENABLED", False)
    monkeypatch.setattr(radio_config, "KAT500_ENABLED", False)
    monkeypatch.setattr(radio_config, "DIGITAL_KPA_POLICY", "standby")
    monkeypatch.setattr(radio_config, "KAT500_ANTENNA_POLICY", {"40m": 2})
    monkeypatch.setattr(radio_config, "STATION_BAREFOOT_DRIVE_W", {"40M": 25})

    class FakeFlex:
        sock = object()
        levels = {
            "freq": 7.074, "mode": "DIGU",
            "rx_ant": "ANT1", "tx_ant": "ANT1", "rfpower": 25,
        }
        def desired_antennas_for_current_config(self, _mhz):
            return {"rx": "ANT1", "tx": "ANT1"}
        def get_current_levels(self, **_kwargs):
            return dict(self.levels)
        def get_fresh_tx_state(self, **_kwargs):
            return {"confirmed": True, "mox": False, "interlock_state": "READY"}

    fake = FakeFlex()
    monkeypatch.setattr(radio, "get_radio_instance", lambda: fake)
    service.engine_state = {"provider": "mshv_auto_dx", "state": "Idle", "enabled": False}
    service.engine_state_at = digital.time.monotonic()
    binding = {
        **service.station_process_binding(),
        "frequency_hz": 7074000, "band": "40m", "mode": "DIGU",
        "rx_ant": "ANT1", "tx_ant": "ANT1",
        "kpa_policy": "standby", "rf_drive_w": 25, "kat_antenna": 2,
        "native_generation": 7,
    }
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        permit, _ = create_test_permit(service, binding)
        accepted = client.post("/api/digital/station-permit/consume", json={
            "provider": "mshv_auto_dx", "permit_nonce": permit,
            "frequency_hz": 7074000, "mode": "DIGU", "path": "test", "authorization_generation": 7,
        })
        replay = client.post("/api/digital/station-permit/consume", json={
            "provider": "mshv_auto_dx", "permit_nonce": permit,
            "frequency_hz": 7074000, "mode": "DIGU", "path": "test", "authorization_generation": 7,
        })
        drift_permit, _ = create_test_permit(service, binding)
        fake.levels["mode"] = "USB"
        drift = client.post("/api/digital/station-permit/consume", json={
            "provider": "mshv_auto_dx", "permit_nonce": drift_permit,
            "frequency_hz": 7074000, "mode": "DIGU", "path": "test", "authorization_generation": 7,
        })
        fake.levels["mode"] = "DIGU"
        drive_permit, _ = create_test_permit(service, binding)
        fake.levels["rfpower"] = 80
        drive_drift = client.post("/api/digital/station-permit/consume", json={
            "provider": "mshv_auto_dx", "permit_nonce": drive_permit,
            "frequency_hz": 7074000, "mode": "DIGU", "path": "test", "authorization_generation": 7,
        })
        fake.levels["rfpower"] = 25
        revoked_permit, _ = create_test_permit(service, binding)
        service.clear_station_authorizations("halt-between-permit-and-edge")
        revoked = client.post("/api/digital/station-permit/consume", json={
            "provider": "mshv_auto_dx", "permit_nonce": revoked_permit,
            "frequency_hz": 7074000, "mode": "DIGU", "path": "test", "authorization_generation": 7,
        })

    assert accepted.json()["success"] is True
    assert accepted.json()["reason"] == "permit-consumed"
    assert accepted.json()["latency_ms"] < digital.STATION_PTT_CONSUME_TIMEOUT_SECONDS * 1000
    assert replay.json()["reason"] == "permit-replayed"
    assert drift.json()["reason"] == "radio-mode-readback-mismatch"
    assert drive_drift.json()["reason"] == "radio-rfpower-readback-mismatch"
    assert revoked.json()["reason"] == "permit-revoked"


def test_station_permit_consume_rejects_process_or_client_binding_drift(service):
    original = service.station_process_binding()
    binding = {
        **original,
        "frequency_hz": 7074000, "band": "40m", "mode": "DIGU",
        "rx_ant": "ANT1", "tx_ant": "ANT1",
        "kpa_policy": "standby", "rf_drive_w": 25, "kat_antenna": 2,
        "native_generation": 11,
    }
    permit, _ = create_test_permit(service, binding)
    changed = {**binding, "bridge_port": binding["bridge_port"] + 1}
    assert service.consume_station_permit(permit, changed) == (
        False, "permit-binding-mismatch",
    )


def test_station_permit_consume_rejects_accessory_drift(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    from radio_control import config as radio_config
    from radio_control import elecraft
    monkeypatch.setattr(radio_config, "KPA500_ENABLED", True)
    monkeypatch.setattr(radio_config, "KAT500_ENABLED", True)
    monkeypatch.setattr(radio_config, "DIGITAL_KPA_POLICY", "standby")
    monkeypatch.setattr(radio_config, "KAT500_ANTENNA_POLICY", {"40m": 2})
    monkeypatch.setattr(radio_config, "STATION_BAREFOOT_DRIVE_W", {"40M": 25})

    class FakeFlex:
        sock = object()
        def desired_antennas_for_current_config(self, _mhz):
            return {"rx": "ANT1", "tx": "ANT1"}
        def get_current_levels(self, **_kwargs):
            return {"freq": 7.074, "mode": "DIGU", "rx_ant": "ANT1", "tx_ant": "ANT1", "rfpower": 25}
        def get_fresh_tx_state(self, **_kwargs):
            return {"confirmed": True, "mox": False, "interlock_state": "READY"}

    accessory = {
        "updated_at": digital.time.time(),
        "kpa500": {
            "connected": True, "responsive": True, "missing_fields": [],
            "power": True, "band": "40m", "fault": "00", "operate": False,
            "output_power_w": 0, "current": 0,
        },
        "kat500": {
            "connected": True, "responsive": True, "missing_fields": [],
            "power": True, "band": "40m", "mode": "auto", "antenna": 2,
            "frequency_khz": 7074, "tuning": False, "fault": "0",
        },
    }
    monkeypatch.setattr(radio, "get_radio_instance", lambda: FakeFlex())
    monkeypatch.setattr(elecraft, "get_elecraft_manager", lambda: SimpleNamespace(snapshot=lambda: accessory))
    service.engine_state = {"provider": "mshv_auto_dx", "state": "Idle", "enabled": False}
    service.engine_state_at = digital.time.monotonic()
    binding = {
        **service.station_process_binding(),
        "frequency_hz": 7074000, "band": "40m", "mode": "DIGU",
        "rx_ant": "ANT1", "tx_ant": "ANT1",
        "kpa_policy": "standby", "rf_drive_w": 25, "kat_antenna": 2,
        "native_generation": 11,
    }
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        kpa_permit, _ = create_test_permit(service, binding)
        accessory["kpa500"]["operate"] = True
        kpa_drift = client.post("/api/digital/station-permit/consume", json={
            "provider": "mshv_auto_dx", "permit_nonce": kpa_permit,
            "frequency_hz": 7074000, "mode": "DIGU", "authorization_generation": 11,
        })
        accessory["kpa500"]["operate"] = False
        kat_permit, _ = create_test_permit(service, binding)
        accessory["kat500"]["frequency_khz"] = 7100
        kat_drift = client.post("/api/digital/station-permit/consume", json={
            "provider": "mshv_auto_dx", "permit_nonce": kat_permit,
            "frequency_hz": 7074000, "mode": "DIGU", "authorization_generation": 11,
        })

    assert kpa_drift.json()["reason"] == "kpa500-fault-or-transmit-readback"
    assert kat_drift.json()["reason"] == "kat500-frequency-antenna-or-tuning-readback"


def test_station_ready_fresh_tx_probe_overrides_stale_snapshot_tx_fields(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    from radio_control import config as radio_config
    monkeypatch.setattr(radio_config, "KPA500_ENABLED", False)
    monkeypatch.setattr(radio_config, "KAT500_ENABLED", False)
    class FakeFlex:
        current_mox = False
        sock = object()
        pending_external_frequency = None
        pending_external_frequency_until = 0
        rfpower = 25
        def desired_antennas_for_current_config(self, mhz):
            return {"rx": "ANT1", "tx": "ANT1"}
        def enforce_antenna_policy(self, mhz, reason=""):
            return True
        def get_current_levels(self, timeout=.5, *, apply_antenna_policy=True):
            return {"mox": True, "interlock_state": "TRANSMITTING", "freq": 7.074, "mode": "DIGU", "rx_ant": "ANT1", "tx_ant": "ANT1", "rfpower": self.rfpower}
        def set_rf_power(self, power):
            self.rfpower = int(power)
            return True
        def get_fresh_tx_state(self, timeout=1.5):
            return {"confirmed": True, "mox": False, "interlock_state": "READY"}
    monkeypatch.setattr(radio, "get_radio_instance", lambda: FakeFlex())
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        prepare = client.post("/api/digital/station-ready", json={"provider": "mshv_auto_dx", "request_id": "fresh", "phase": "prepare", "band": "40m", "frequency_hz": 7074000, "authorization_generation": 1})
        final = client.post("/api/digital/station-ready", json={"provider": "mshv_auto_dx", "request_id": "fresh-final", "phase": "final", "band": "40m", "frequency_hz": 7074000, "authorization_generation": 1, "prepare_nonce": prepare.json().get("prepare_nonce")})
    assert prepare.json()["ready"] is True
    assert final.json()["transmit_ready"] is True


def test_station_ready_fails_closed_when_fresh_tx_probe_is_unconfirmed(service, monkeypatch):
    digital.atomic_write_json(digital.STATE_PATH, {"provider": "mshv_auto_dx"})
    from radio_control import config as radio_config
    monkeypatch.setattr(radio_config, "KPA500_ENABLED", False)
    monkeypatch.setattr(radio_config, "KAT500_ENABLED", False)
    class FakeFlex:
        current_mox = False
        sock = object()
        pending_external_frequency = None
        pending_external_frequency_until = 0
        def desired_antennas_for_current_config(self, mhz):
            return {"rx": "ANT1", "tx": "ANT1"}
        def enforce_antenna_policy(self, mhz, reason=""):
            return True
        def get_current_levels(self, timeout=.5, *, apply_antenna_policy=True):
            return {"freq": 7.074, "mode": "DIGU", "rx_ant": "ANT1", "tx_ant": "ANT1"}
        def get_fresh_tx_state(self, timeout=1.5):
            return {"confirmed": False, "mox": None, "interlock_state": None}
    monkeypatch.setattr(radio, "get_radio_instance", lambda: FakeFlex())
    monkeypatch.setattr(service, "_confirm_idle", lambda: None)
    app = FastAPI()
    digital.register_digital_endpoints(app)
    with TestClient(app) as client:
        response = client.post("/api/digital/station-ready", json={"provider": "mshv_auto_dx", "request_id": "missing", "phase": "prepare", "band": "40m", "frequency_hz": 7074000, "authorization_generation": 1})
    assert response.json()["ready"] is False
    assert response.json()["reason"] == "radio-fresh-tx-state-unavailable"


def test_golden_mshv_identity_routes_halt_and_local_multicast_source_is_allowed():
    script = """
      process.env.OM0RX_BRIDGE_TEST_MODE='1';
      const bridge=await import('./bridge/sdc-bridge-server.js');
      const {localSourceAllowed,providerForClient}=await import('./bridge/digital-provider.js');
      bridge.__resetWsjtxBridgeDiagnosticsForTest();
      bridge.__dispatchWsjtxCommandForTest('select_provider',{provider:'mshv_auto_dx'});
      const id=Buffer.from('MSHV-OM0RX-AUTO-DX'); const packet=Buffer.alloc(16+id.length);
      packet.writeUInt32BE(0xadbccbda,0);packet.writeUInt32BE(3,4);packet.writeUInt32BE(0,8);packet.writeUInt32BE(id.length,12);id.copy(packet,16);
      let routed='';
      const accepted=bridge.__attachDigitalClientForTest(packet,{address:'127.0.0.1',port:12345},(bytes)=>{routed=bytes.toString('utf8',16,16+bytes.readUInt32BE(12));return {success:true};});
      const halt=bridge.__dispatchWsjtxCommandForTest('halt_tx',{});
      const local=localSourceAllowed('192.168.0.2',{Ethernet:[{address:'192.168.0.2'}]});
      const remote=localSourceAllowed('192.168.0.99',{Ethernet:[{address:'192.168.0.2'}]});
      const nearMiss=providerForClient('MSHV');
      console.log(JSON.stringify({accepted,routed,halt,local,remote,nearMiss}));
    """
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout.splitlines()[-1])
    assert data["accepted"] and data["halt"]["success"]
    assert data["routed"] == "MSHV-OM0RX-AUTO-DX"
    assert data["local"] and not data["remote"]
    assert data["nearMiss"] is None
