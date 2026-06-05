import json
import asyncio
from types import SimpleNamespace

import pytest

import _bootstrap  # noqa: F401

from fastapi import HTTPException

from services.digital_automation import DigitalAutomationController
from services.wsjtx import WSJTXService, _normalise_wsjtx_automation_policy


class _FakeAdifWavelog:
    def __init__(self):
        self.adif_calls = []
        self.qso_calls = []

    async def submit_adif_string(self, adif_text):
        self.adif_calls.append(adif_text)
        return {"success": True, "message": "ok", "data": {"id": 123}}

    async def log_qso(self, qso):
        self.qso_calls.append(qso)
        return {"success": True, "message": "ok", "data": {"id": 456}}


class _FakeAdifBackup:
    def __init__(self):
        self.records = []

    def add_qso(self, qso):
        self.records.append(qso)
        return True


class _FakeQsoStatusStore:
    def __init__(self):
        self.records = []

    def record_qso(self, qso):
        self.records.append(dict(qso))
        return True


class _FakeCtyResolver:
    def lookup(self, callsign):
        if callsign == "EA1AA":
            return {"dxcc": 281, "continent": "EU"}
        return {}


@pytest.fixture(autouse=True)
def _disable_real_recent_wavelog_lookup(monkeypatch):
    import services.qso_logging as qlog

    monkeypatch.setattr(qlog, "_get_recent_qsos_from_duckdb", lambda _call, _limit: [])
    monkeypatch.setattr(qlog, "_get_recent_qsos_from_wavelog_db", lambda _call, _limit: [])


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


def test_wsjtx_logged_adif_is_submitted_to_wavelog_as_adif(monkeypatch, tmp_path):
    import services.qso_logging as qlog

    service = WSJTXService()
    wavelog = _FakeAdifWavelog()
    backup = _FakeAdifBackup()
    qso_status = _FakeQsoStatusStore()
    service.set_dependencies(
        wavelog,
        None,
        None,
        cty_resolver=_FakeCtyResolver(),
        adif_handler=backup,
        qso_status_store=qso_status,
    )
    monkeypatch.setattr(qlog, "_dedupe_ledger_path", tmp_path / "qso_log_dedupe.json")

    result = asyncio.run(service.log_qso({
        "source": "wsjtx-bridge",
        "adif_text": (
            "<call:5>EA1AA <gridsquare:4>IN80 <freq:6>14.074 "
            "<band:3>20m <mode:3>FT8 <qso_date:8>20260604 "
            "<time_on:6>112530 <rst_sent:3>-10 <rst_rcvd:3>-07 <eor>"
        ),
    }))

    assert result["success"] is True
    assert len(wavelog.adif_calls) == 1
    assert wavelog.qso_calls == []
    assert "<qso_date:8>20260604" in wavelog.adif_calls[0]
    assert backup.records[0]["callsign"] == "EA1AA"
    assert backup.records[0]["frequency"] == 14.074
    assert backup.records[0]["band"] == "20m"
    assert backup.records[0]["rst_sent"] == "-10"
    assert backup.records[0]["rst_received"] == "-07"
    assert backup.records[0]["date_time"] == "2026-06-04T11:25:30+00:00"
    assert backup.records[0]["dxcc"] == 281
    assert result["qso_data"]["gridsquare"] == "IN80"
    assert qso_status.records[0]["callsign"] == "EA1AA"
    assert qso_status.records[0]["band"] == "20m"
    assert qso_status.records[0]["mode"] == "FT8"
    assert qso_status.records[0]["gridsquare"] == "IN80"


def test_wsjtx_logged_adif_marks_automation_target_complete(monkeypatch, tmp_path):
    import services.ft8_service as ft8_module
    import services.qso_logging as qlog

    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "message": "CQ CS2TU IN61",
        "callsign": "CS2TU",
        "band": "15m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -18,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })
    assert target is not None
    controller.active_target_key = target.key
    controller.record_attempt(target.key)
    assert controller.active_target_key == target.key

    service = WSJTXService()
    service.set_dependencies(
        _FakeAdifWavelog(),
        None,
        None,
        cty_resolver=_FakeCtyResolver(),
        adif_handler=_FakeAdifBackup(),
        qso_status_store=_FakeQsoStatusStore(),
    )
    monkeypatch.setattr(qlog, "_dedupe_ledger_path", tmp_path / "qso_log_dedupe.json")
    monkeypatch.setattr(
        ft8_module,
        "get_ft8_service",
        lambda: SimpleNamespace(automation_controller=controller),
    )

    result = asyncio.run(service.log_qso({
        "source": "wsjtx-bridge",
        "adif_text": (
            "<call:5>CS2TU <gridsquare:4>IN61 <freq:6>21.074 "
            "<band:3>15m <mode:3>FT8 <qso_date:8>20260605 "
            "<time_on:6>100515 <rst_sent:3>-18 <rst_rcvd:3>-24 <eor>"
        ),
    }))

    assert result["success"] is True
    assert controller.active_target_key is None
    assert target.state == "done"
    assert target.completion_reason == "wsjtx-logged-qso"


def test_wsjtx_logged_adif_duplicate_is_ignored(monkeypatch, tmp_path):
    import services.qso_logging as qlog

    service = WSJTXService()
    wavelog = _FakeAdifWavelog()
    backup = _FakeAdifBackup()
    qso_status = _FakeQsoStatusStore()
    service.set_dependencies(
        wavelog,
        None,
        None,
        cty_resolver=_FakeCtyResolver(),
        adif_handler=backup,
        qso_status_store=qso_status,
    )
    monkeypatch.setattr(qlog, "_dedupe_ledger_path", tmp_path / "qso_log_dedupe.json")

    payload = {
        "source": "wsjtx-bridge",
        "adif_text": (
            "<call:5>EA1AA <gridsquare:4>IN80 <freq:6>14.074 "
            "<band:3>20m <mode:3>FT8 <qso_date:8>20260604 "
            "<time_on:6>112530 <rst_sent:3>-10 <rst_rcvd:3>-07 <eor>"
        ),
    }

    first = asyncio.run(service.log_qso(payload))
    second = asyncio.run(service.log_qso(payload))

    assert first["success"] is True
    assert second["success"] is True
    assert second["duplicate"] is True
    assert len(wavelog.adif_calls) == 1
    assert len(backup.records) == 1
    assert qso_status.records[-1]["callsign"] == "EA1AA"


def test_wsjtx_logged_adif_duplicate_with_shifted_time_and_reports_is_ignored(monkeypatch, tmp_path):
    import services.qso_logging as qlog

    service = WSJTXService()
    wavelog = _FakeAdifWavelog()
    backup = _FakeAdifBackup()
    service.set_dependencies(
        wavelog,
        None,
        None,
        cty_resolver=_FakeCtyResolver(),
        adif_handler=backup,
    )
    monkeypatch.setattr(qlog, "_dedupe_ledger_path", tmp_path / "qso_log_dedupe.json")

    first = asyncio.run(service.log_qso({
        "source": "wsjtx-bridge",
        "adif_text": (
            "<call:5>EA1AA <gridsquare:4>IN80 <freq:6>14.074 "
            "<band:3>20m <mode:3>FT8 <qso_date:8>20260604 "
            "<time_on:6>112530 <rst_sent:3>-10 <rst_rcvd:3>-07 <eor>"
        ),
    }))
    second = asyncio.run(service.log_qso({
        "source": "wsjtx-bridge",
        "adif_text": (
            "<call:5>EA1AA <gridsquare:4>IN80 <freq:6>14.074 "
            "<band:3>20m <mode:3>FT8 <qso_date:8>20260604 "
            "<time_on:6>112830 <rst_sent:3>-13 <rst_rcvd:3>-12 <eor>"
        ),
    }))

    assert first["success"] is True
    assert second["success"] is True
    assert second["duplicate"] is True
    assert len(wavelog.adif_calls) == 1
    assert len(backup.records) == 1


def test_wsjtx_adif_and_backend_completion_race_logs_once(monkeypatch, tmp_path):
    import services.qso_logging as qlog
    from services.qso_logging import QSORequest

    class SlowSharedWavelog:
        def __init__(self):
            self.adif_calls = []
            self.qso_calls = []

        async def submit_adif_string(self, adif_text):
            self.adif_calls.append(adif_text)
            await asyncio.sleep(0.05)
            return {"success": True, "message": "ok", "data": {"id": 123}}

        async def log_qso(self, qso):
            self.qso_calls.append(dict(qso))
            await asyncio.sleep(0.05)
            return {"success": True, "message": "ok", "data": {"id": 456}}

    wavelog = SlowSharedWavelog()
    wsjtx_backup = _FakeAdifBackup()
    backend_backup = _FakeAdifBackup()
    service = WSJTXService()
    service.set_dependencies(
        wavelog,
        None,
        None,
        cty_resolver=_FakeCtyResolver(),
        adif_handler=wsjtx_backup,
    )

    monkeypatch.setattr(qlog, "_dedupe_ledger_path", tmp_path / "qso_log_dedupe.json")
    monkeypatch.setattr(qlog, "_pending_dedupe_claims", {})
    monkeypatch.setattr(qlog, "wavelog_client", wavelog)
    monkeypatch.setattr(qlog, "adif_handler", backend_backup)
    monkeypatch.setattr(qlog, "qrz_client", None)

    async def run_race():
        return await asyncio.gather(
            service.log_qso({
                "source": "wsjtx-bridge",
                "adif_text": (
                    "<call:5>M6OTU <gridsquare:4>IO84 <freq:6>24.915 "
                    "<band:3>12m <mode:3>FT8 <qso_date:8>20260605 "
                    "<time_on:6>104216 <rst_sent:3>-10 <rst_rcvd:3>-07 <eor>"
                ),
            }),
            qlog.log_qso(QSORequest(
                callsign="M6OTU",
                frequency=24.915,
                band="12m",
                mode="FT8",
                rst_sent="-10",
                rst_received="-07",
                gridsquare="IO84",
                date_time="2026-06-05T10:43:00+00:00",
            )),
        )

    first, second = asyncio.run(run_race())

    assert first["success"] is True
    assert second["success"] is True
    assert first.get("duplicate") or second.get("duplicate")
    assert len(wavelog.adif_calls) + len(wavelog.qso_calls) == 1
    assert len(wsjtx_backup.records) + len(backend_backup.records) == 1


def test_wsjtx_logged_adif_skips_when_recent_wavelog_row_exists(monkeypatch, tmp_path):
    import services.qso_logging as qlog

    service = WSJTXService()
    wavelog = _FakeAdifWavelog()
    backup = _FakeAdifBackup()
    service.set_dependencies(
        wavelog,
        None,
        None,
        cty_resolver=_FakeCtyResolver(),
        adif_handler=backup,
    )
    monkeypatch.setattr(qlog, "_dedupe_ledger_path", tmp_path / "qso_log_dedupe.json")
    monkeypatch.setattr(qlog, "_pending_dedupe_claims", {})
    monkeypatch.setattr(qlog, "_get_recent_qsos_from_duckdb", lambda _call, _limit: [])
    monkeypatch.setattr(
        qlog,
        "_get_recent_qsos_from_wavelog_db",
        lambda _call, _limit: [{
            "call": "M6OTU",
            "qso_date": "20260605",
            "time_on": "104216",
            "band": "12m",
            "mode": "FT8",
        }],
    )

    result = asyncio.run(service.log_qso({
        "source": "wsjtx-bridge",
        "adif_text": (
            "<call:5>M6OTU <gridsquare:4>IO84 <freq:6>24.915 "
            "<band:3>12m <mode:3>FT8 <qso_date:8>20260605 "
            "<time_on:6>104300 <rst_sent:3>-10 <rst_rcvd:3>-07 <eor>"
        ),
    }))

    assert result["success"] is True
    assert result["duplicate"] is True
    assert wavelog.adif_calls == []
    assert backup.records == []


def test_wsjtx_log_qso_without_adif_uses_structured_wavelog_payload(monkeypatch, tmp_path):
    import services.qso_logging as qlog

    service = WSJTXService()
    wavelog = _FakeAdifWavelog()
    backup = _FakeAdifBackup()
    service.set_dependencies(wavelog, None, None, adif_handler=backup)
    monkeypatch.setattr(qlog, "_dedupe_ledger_path", tmp_path / "qso_log_dedupe.json")

    result = asyncio.run(service.log_qso({
        "call": "ea1aa",
        "frequency_hz": 14_074_000,
        "mode": "FT8",
        "grid": "IN80",
        "rst_sent": "-10",
        "rst_received": "-07",
    }))

    assert result["success"] is True
    assert wavelog.adif_calls == []
    assert len(wavelog.qso_calls) == 1
    assert wavelog.qso_calls[0]["callsign"] == "EA1AA"
    assert wavelog.qso_calls[0]["band"] == "20m"
    assert backup.records[0]["gridsquare"] == "IN80"


def test_wsjtx_duplicate_log_response_still_updates_status_cache():
    class DuplicateWavelog(_FakeAdifWavelog):
        async def submit_adif_string(self, adif_text):
            self.adif_calls.append(adif_text)
            return {"success": False, "message": "Duplicate QSO"}

    service = WSJTXService()
    wavelog = DuplicateWavelog()
    qso_status = _FakeQsoStatusStore()
    service.set_dependencies(
        wavelog,
        None,
        None,
        cty_resolver=_FakeCtyResolver(),
        qso_status_store=qso_status,
    )

    result = asyncio.run(service.log_qso({
        "adif_text": (
            "<call:5>EA1AA <gridsquare:4>IN80 <freq:6>14.074 "
            "<band:3>20m <mode:3>FT8 <qso_date:8>20260604 <time_on:6>112530 <eor>"
        ),
    }))

    assert result["success"] is True
    assert result["duplicate"] is True
    assert qso_status.records[0]["callsign"] == "EA1AA"
    assert qso_status.records[0]["dxcc"] == 281


def test_wsjtx_native_automation_policy_maps_wsjtz_controls():
    policy = _normalise_wsjtx_automation_policy({
        "source": "native-test",
        "automation": {
            "autoCall": True,
            "autoCQ": False,
            "cqOnly": True,
            "minSignal": -27,
            "autoCallLimit": 7,
            "autoCQLimit": 3,
            "watchdogFT8": 2,
            "watchdogFT4": 1,
            "hopIntervalSeconds": 180,
            "txDf": 1570,
            "txEvenFirst": True,
            "bandHopping": True,
            "bandPlan": "06:20m,15m\n20:40m,80m",
            "modeSwitching": True,
            "treat73AsCQ": True,
            "autoLogToWavelog": False,
            "needCall": False,
            "needDxcc": True,
            "needBand": False,
            "needMode": True,
            "needGrid": False,
            "priority": "Signal strength",
            "ignoreList": "K1ABC\nK2ABC",
        },
    })

    automation = policy["operatorSettings"]["automation"]
    tx_options = policy["txOptions"]

    assert policy["source"] == "native-test"
    assert automation["enabled"] is True
    assert automation["spotHuntEnabled"] is True
    assert automation["bandHopping"] is True
    assert automation["modeSwitching"] is True
    assert automation["treat73AsCQ"] is True
    assert automation["autoLogToWavelog"] is False
    assert automation["needCall"] is False
    assert automation["needDxcc"] is True
    assert automation["needBand"] is False
    assert automation["needMode"] is True
    assert automation["needGrid"] is False
    assert automation["minSignal"] == -27
    assert automation["autoCallCount"] == 7
    assert automation["autoCQCount"] == 3
    assert automation["hopIntervalSeconds"] == 180
    assert automation["priority"] == "signal"
    assert automation["bandPlan"] == "06:20m,15m\n20:40m,80m"
    assert automation["ignoreList"] == "K1ABC\nK2ABC"
    assert tx_options["auto_call"] is True
    assert tx_options["auto_cq"] is False
    assert tx_options["cq_only"] is True
    assert tx_options["tx_audio_frequency"] == 1570
    assert tx_options["tx_even_first"] is True
    assert tx_options["watchdog_ft8"] == 2
    assert tx_options["watchdog_ft4"] == 1


def test_wsjtx_native_automation_policy_clamps_signal_and_counts():
    policy = _normalise_wsjtx_automation_policy({
        "autoCall": True,
        "minSignal": -99,
        "autoCallLimit": 200,
        "autoCQLimit": -4,
    })

    automation = policy["operatorSettings"]["automation"]

    assert automation["minSignal"] == -40
    assert automation["autoCallCount"] == 99
    assert automation["autoCQCount"] == 0


def test_wsjtx_native_automation_policy_allows_clearing_ignore_list():
    policy = _normalise_wsjtx_automation_policy({"automation": {"ignoreList": ""}})

    assert policy["operatorSettings"]["automation"]["ignoreList"] == ""


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
