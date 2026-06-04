import json

import pytest

import _bootstrap  # noqa: F401

from fastapi import HTTPException

from services.wsjtx import WSJTXService


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_wsjtx_target_builder_normalizes_cluster_ft2_spot():
    service = WSJTXService()

    target = service.build_target_from_spot({
        "callsign": " dl1abc ",
        "frequency_mhz": 14.084,
        "mode": "DIGI",
        "comment": "",
        "gridsquare": "jo62",
    })

    assert target["call"] == "DL1ABC"
    assert target["mode"] == "FT2"
    assert target["dialFrequency"] == 14_084_000
    assert target["trPeriod"] == 4
    assert target["grid"] == "JO62"
    assert target["txDf"] == 1500
    assert target["holdTxFreq"] is True
    assert target["enableTx"] is False


def test_wsjtx_target_builder_accepts_khz_frequency():
    service = WSJTXService()

    target = service.build_target_from_spot({
        "call": "K1ABC",
        "frequency": 7047.5,
        "comment": "FT4",
        "rxDf": 900,
        "txDf": 1600,
        "enableTx": "false",
    })

    assert target["mode"] == "FT4"
    assert target["dialFrequency"] == 7_047_500
    assert target["trPeriod"] == 7
    assert target["rxDf"] == 900
    assert target["txDf"] == 1600
    assert target["enableTx"] is False


def test_wsjtx_target_builder_accepts_nested_spot_options():
    service = WSJTXService()

    target = service.build_target_from_spot({
        "spot": {
            "callsign": "ea1aa",
            "frequency_mhz": 14.074,
            "mode": "FT8",
            "grid": "in80",
        },
        "options": {
            "txDf": 1600,
            "enableTx": True,
        },
    })

    assert target["call"] == "EA1AA"
    assert target["grid"] == "IN80"
    assert target["txDf"] == 1600
    assert target["enableTx"] is True


def test_wsjtx_target_builder_preserves_trace_id():
    service = WSJTXService()

    target = service.build_target_from_spot({
        "callsign": "ea1aa",
        "frequency_mhz": 14.074,
        "mode": "FT8",
        "traceId": "spot-123",
    })

    assert target["traceId"] == "spot-123"


def test_wsjtx_target_builder_generates_trace_id():
    service = WSJTXService()

    target = service.build_target_from_spot({
        "callsign": "ea1aa",
        "frequency_mhz": 14.074,
        "mode": "FT8",
    })

    assert target["traceId"].startswith("wsjtx-")
    assert len(target["traceId"]) > len("wsjtx-")


def test_wsjtx_send_bridge_command_adds_trace_to_target(monkeypatch):
    import services.wsjtx as wsjtx_module

    captured = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"success": True, "sent": captured["body"]["command"]})

    monkeypatch.setattr(wsjtx_module.urllib.request, "urlopen", fake_urlopen)

    result = WSJTXService().send_bridge_command("start_target_qso", {
        "target": {
            "call": "EA1AA",
            "mode": "FT8",
            "dialFrequency": 14_074_000,
        }
    })

    payload = captured["body"]["payload"]
    assert captured["body"]["command"] == "start_target_qso"
    assert payload["traceId"].startswith("wsjtx-")
    assert payload["target"]["traceId"] == payload["traceId"]
    assert result["traceId"] == payload["traceId"]


def test_wsjtx_target_builder_accepts_ranked_automation_target():
    service = WSJTXService()

    target = service.build_target_from_automation_target({
        "call": "e51abc",
        "mode": "FT8",
        "dial_frequency": 14_074_000,
        "audio_offset": 1234,
        "tx_df": 1700,
        "grid": "bg08",
        "call_status": "New Band",
        "dxcc_status": "ATNO",
        "score": 1000,
        "enableTx": True,
    })

    assert target["call"] == "E51ABC"
    assert target["mode"] == "FT8"
    assert target["dialFrequency"] == 14_074_000
    assert target["rxDf"] == 1234
    assert target["txDf"] == 1700
    assert target["grid"] == "BG08"
    assert target["enableTx"] is True
    assert target["traceId"].startswith("wsjtx-")


def test_wsjtx_policy_allows_new_needed_digital_target():
    service = WSJTXService()
    payload = {
        "callsign": "EA1AA",
        "frequency_mhz": 14.074,
        "mode": "FT8",
        "call_status": "New Band",
        "dxcc_status": "Confirmed",
        "score": 65,
    }
    target = service.build_target_from_spot(payload)

    policy = service.assess_target_policy(target, payload, action="arm")

    assert policy["eligible"] is True
    assert policy["action"] == "arm"
    assert policy["slot"]["period"] == 15


def test_wsjtx_policy_blocks_already_worked_without_new_slot():
    service = WSJTXService()
    payload = {
        "callsign": "EA1AA",
        "frequency_mhz": 14.074,
        "mode": "FT8",
        "call_status": "Worked",
        "dxcc_status": "Confirmed",
        "score": 0,
    }
    target = service.build_target_from_spot(payload)

    policy = service.assess_target_policy(target, payload, action="arm")

    assert policy["eligible"] is False
    assert "already worked/confirmed" in " ".join(policy["reasons"])


def test_wsjtx_target_builder_rejects_non_wsjtx_modes():
    service = WSJTXService()

    with pytest.raises(HTTPException) as exc:
        service.build_target_from_spot({
            "callsign": "K1ABC",
            "frequency_khz": 14025,
            "mode": "CW",
        })

    assert exc.value.status_code == 400


def test_wsjtx_health_identifies_patched_engine(monkeypatch):
    import services.wsjtx as wsjtx_module

    service = WSJTXService()
    monkeypatch.setattr(
        service,
        "get_bridge_status",
        lambda: {
            "success": True,
            "enabled": True,
            "client": {
                "id": "WSJT-X - OM0RX-AUTO - test",
                "lastSeenMs": 1200,
            },
        },
    )
    monkeypatch.setattr(
        wsjtx_module,
        "_visible_process_names",
        lambda names: {name.lower(): name.lower() in {"wsjtx.exe", "jt9.exe"} for name in names},
    )

    health = service.get_health()

    assert health["status"] == "ok"
    assert health["value"] == "OM0RX engine"
    assert health["extended_target_supported"] is True
    assert health["processes"]["wsjtx"] is True
    assert health["processes"]["decoder"] is True
    checks = {check["id"]: check for check in health["checks"]}
    assert checks["bridge"]["status"] == "ok"
    assert checks["client"]["status"] == "ok"
    assert checks["profile"]["status"] == "ok"
    assert checks["extended-target"]["status"] == "ok"
    assert health["validation"]["critical_ok"] <= health["validation"]["critical_total"]


def test_wsjtx_health_allows_normal_heartbeat_gap(monkeypatch):
    import services.wsjtx as wsjtx_module

    service = WSJTXService()
    monkeypatch.setattr(
        service,
        "get_bridge_status",
        lambda: {
            "success": True,
            "enabled": True,
            "client": {
                "id": "WSJT-X - OM0RX-AUTO",
                "lastSeenMs": 18_000,
            },
        },
    )
    monkeypatch.setattr(
        wsjtx_module,
        "_visible_process_names",
        lambda names: {name.lower(): name.lower() in {"wsjtx.exe", "jt9.exe"} for name in names},
    )

    health = service.get_health()

    assert health["status"] == "ok"
    assert health["client_fresh"] is True
    checks = {check["id"]: check for check in health["checks"]}
    assert checks["client"]["status"] == "ok"


def test_wsjtx_health_reports_stale_client_as_check_warning(monkeypatch):
    import services.wsjtx as wsjtx_module

    service = WSJTXService()
    monkeypatch.setattr(
        service,
        "get_bridge_status",
        lambda: {
            "success": True,
            "enabled": True,
            "client": {
                "id": "WSJT-X - OM0RX-AUTO",
                "lastSeenMs": 95_000,
            },
            "stats": {
                "lastDecode": {"message": "CQ TEST JN88"},
                "lastDecodeAgeMs": 120_000,
                "decodes": 12,
            },
        },
    )
    monkeypatch.setattr(
        wsjtx_module,
        "_visible_process_names",
        lambda names: {name.lower(): False for name in names},
    )

    health = service.get_health()
    checks = {check["id"]: check for check in health["checks"]}

    assert health["status"] == "warn"
    assert checks["bridge"]["status"] == "ok"
    assert checks["client"]["status"] == "warn"
    assert checks["decode"]["status"] == "warn"
    assert health["validation"]["ready"] is False


def test_wsjtx_health_preserves_bridge_command_errors_and_failed_timeline(monkeypatch):
    import services.wsjtx as wsjtx_module

    service = WSJTXService()
    failed_event = {
        "ts": 1780557900000,
        "direction": "out",
        "type": "command",
        "command": "start_target_qso",
        "traceId": "trace-failed-command",
        "success": False,
        "error": "No WSJT-X client has been seen yet",
        "payload": {
            "call": "K1FAIL",
            "grid": "FN42",
            "mode": "FT8",
            "traceId": "trace-failed-command",
            "rxDf": 1240,
            "txDf": 1500,
        },
    }
    monkeypatch.setattr(
        service,
        "get_bridge_status",
        lambda: {
            "success": True,
            "enabled": True,
            "client": {
                "id": "WSJT-X - OM0RX-AUTO",
                "lastSeenMs": 1200,
            },
            "stats": {
                "commands": 3,
                "commandErrors": 1,
                "lastCommand": failed_event,
                "lastCommandAgeMs": 2500,
                "lastDecode": {"message": "CQ EA1TEST IN80"},
                "lastDecodeAgeMs": 3000,
                "decodes": 12,
            },
            "timeline": [
                {
                    "ts": 1780557890000,
                    "direction": "in",
                    "type": "decode",
                    "message": "CQ EA1TEST IN80",
                    "mode": "FT8",
                    "dxCall": "EA1TEST",
                },
                failed_event,
            ],
        },
    )
    monkeypatch.setattr(
        wsjtx_module,
        "_visible_process_names",
        lambda names: {name.lower(): name.lower() == "jt9.exe" for name in names},
    )

    health = service.get_health()

    assert health["bridge"]["stats"]["commandErrors"] == 1
    assert health["bridge"]["last_command"]["traceId"] == "trace-failed-command"
    failed = health["timeline"][-1]
    assert failed["command"] == "start_target_qso"
    assert failed["success"] is False
    assert failed["trace_id"] == "trace-failed-command"
    assert failed["error"] == "No WSJT-X client has been seen yet"
    assert failed["dx_call"] == "K1FAIL"
    assert failed["dx_grid"] == "FN42"
    assert failed["mode"] == "FT8"
    assert failed["rx_df"] == 1240
    assert failed["tx_df"] == 1500


def test_wsjtx_patched_engine_launcher_dry_run(monkeypatch, tmp_path):
    import services.wsjtx as wsjtx_module

    script = tmp_path / "run_om0rx_wsjtx.ps1"
    build_root = tmp_path / "build"
    build_root.mkdir()
    exe = build_root / "wsjtx.exe"
    decoder = build_root / "jt9.exe"
    script.write_text("Write-Host ok", encoding="utf-8")
    exe.write_text("", encoding="utf-8")
    decoder.write_text("", encoding="utf-8")

    monkeypatch.setattr(wsjtx_module, "PATCHED_ENGINE_RUN_SCRIPT", script)
    monkeypatch.setattr(wsjtx_module, "PATCHED_ENGINE_BUILD_ROOT", build_root)
    monkeypatch.setattr(wsjtx_module, "PATCHED_ENGINE_MSYS_ROOT", tmp_path)
    monkeypatch.setattr(wsjtx_module.platform, "system", lambda: "Windows")
    (tmp_path / "mingw64" / "bin").mkdir(parents=True)
    (tmp_path / "usr" / "bin").mkdir(parents=True)

    result = WSJTXService().launch_patched_engine({"dryRun": True, "rigName": "OM0RX-TEST"})

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["rig_name"] == "OM0RX-TEST"
    assert result["engine"]["exe_exists"] is True
    assert "--rig-name" in result["command"]


def test_wsjtx_launch_preflight_uses_dry_run_and_port_checks(monkeypatch):
    import services.wsjtx as wsjtx_module

    service = WSJTXService()
    monkeypatch.setattr(
        service,
        "get_bridge_status",
        lambda: {
            "success": True,
            "enabled": True,
            "client": {
                "id": "WSJT-X - OM0RX-AUTO",
                "lastSeenMs": 1200,
            },
            "stats": {
                "lastDecode": {"message": "CQ E51ABC BG08"},
                "lastDecodeAgeMs": 5000,
                "decodes": 42,
            },
        },
    )
    monkeypatch.setattr(
        service,
        "launch_patched_engine",
        lambda req: {
            "success": True,
            "dry_run": req.get("dryRun") is True,
            "message": "Patched WSJT engine launcher prerequisites are available",
        },
    )
    monkeypatch.setattr(
        wsjtx_module,
        "_tcp_endpoint_check",
        lambda host, port, timeout_seconds=1.0: {"ok": True, "host": host, "port": port},
    )
    monkeypatch.setattr(
        wsjtx_module,
        "_visible_process_names",
        lambda names: {name.lower(): name.lower() in {"wsjtx.exe", "jt9.exe"} for name in names},
    )

    result = service.get_launch_preflight({"rigName": "OM0RX-AUTO", "configName": "OM0RX-AUTO"})
    checks = {check["id"]: check for check in result["checks"]}

    assert result["ready"] is True
    assert result["launcher"]["dry_run"] is True
    assert checks["launcher-dry-run"]["status"] == "ok"
    assert checks["command-status-http"]["status"] == "ok"
    assert checks["command-port"]["status"] == "ok"
    assert checks["websocket-port"]["status"] == "ok"
    assert checks["udp-reporting"]["status"] == "ok"


def test_wsjtx_patched_engine_launcher_invokes_script(monkeypatch, tmp_path):
    import services.wsjtx as wsjtx_module

    script = tmp_path / "run_om0rx_wsjtx.ps1"
    build_root = tmp_path / "build"
    build_root.mkdir()
    (build_root / "wsjtx.exe").write_text("", encoding="utf-8")
    (build_root / "jt9.exe").write_text("", encoding="utf-8")
    script.write_text("Write-Host ok", encoding="utf-8")
    (tmp_path / "mingw64" / "bin").mkdir(parents=True)
    (tmp_path / "usr" / "bin").mkdir(parents=True)
    calls = []

    class Process:
        pid = 12345

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return Process()

    monkeypatch.setattr(wsjtx_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(wsjtx_module, "PATCHED_ENGINE_RUN_SCRIPT", script)
    monkeypatch.setattr(wsjtx_module, "PATCHED_ENGINE_BUILD_ROOT", build_root)
    monkeypatch.setattr(wsjtx_module, "PATCHED_ENGINE_MSYS_ROOT", tmp_path)
    monkeypatch.setattr(wsjtx_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(wsjtx_module, "_patched_engine_process_ids", lambda rig_name, test_mode=False: [])
    monkeypatch.setattr(wsjtx_module.subprocess, "Popen", fake_popen)

    result = WSJTXService().launch_patched_engine({"rigName": "OM0RX-LIVE", "configName": "OM0RX-LIVE"})

    assert result["success"] is True
    assert result["pid"] == 12345
    assert calls
    command = calls[0][0]
    assert command[0] == str(build_root / "wsjtx.exe")
    assert "--rig-name" in command
    assert "OM0RX-LIVE" in command


def test_wsjtx_patched_engine_launcher_skips_existing_instance(monkeypatch, tmp_path):
    import services.wsjtx as wsjtx_module

    script = tmp_path / "run_om0rx_wsjtx.ps1"
    build_root = tmp_path / "build"
    build_root.mkdir()
    (build_root / "wsjtx.exe").write_text("", encoding="utf-8")
    (build_root / "jt9.exe").write_text("", encoding="utf-8")
    script.write_text("Write-Host ok", encoding="utf-8")
    (tmp_path / "mingw64" / "bin").mkdir(parents=True)
    (tmp_path / "usr" / "bin").mkdir(parents=True)

    monkeypatch.setattr(wsjtx_module, "PATCHED_ENGINE_RUN_SCRIPT", script)
    monkeypatch.setattr(wsjtx_module, "PATCHED_ENGINE_BUILD_ROOT", build_root)
    monkeypatch.setattr(wsjtx_module, "PATCHED_ENGINE_MSYS_ROOT", tmp_path)
    monkeypatch.setattr(wsjtx_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(wsjtx_module, "_patched_engine_process_ids", lambda rig_name, test_mode=False: [777])

    result = WSJTXService().launch_patched_engine({"rigName": "OM0RX-LIVE"})

    assert result["success"] is True
    assert result["already_running"] is True
    assert result["existing_pids"] == [777]
