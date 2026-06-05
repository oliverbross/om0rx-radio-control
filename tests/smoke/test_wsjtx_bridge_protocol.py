"""Smoke checks for WSJT-X bridge command packet construction."""

import json
import subprocess
from pathlib import Path

import _bootstrap  # noqa: F401
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.wsjtx as wsjtx_module


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_node_protocol_script(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_wsjtx_reply_packet_matches_qdatastream_header():
    payload = run_node_protocol_script(
        """
        import { buildReply, MESSAGE_TYPES } from './bridge/wsjtx-protocol.js';
        const packet = buildReply({
          id: 'WSJT-X',
          time: '123456',
          snr: -12,
          deltaTime: 0.7,
          deltaFrequency: 1500,
          mode: 'FT8',
          message: 'CQ EA1AA IN80',
          lowConfidence: false,
          modifiers: 0
        });
        console.log(JSON.stringify({
          magic: packet.readUInt32BE(0),
          schema: packet.readUInt32BE(4),
          type: packet.readUInt32BE(8),
          idLength: packet.readUInt32BE(12),
          id: packet.toString('utf8', 16, 22),
          size: packet.length,
          replyType: MESSAGE_TYPES.REPLY
        }));
        """
    )

    assert payload["magic"] == 0xADBCCBDA
    assert payload["schema"] == 3
    assert payload["type"] == payload["replyType"] == 4
    assert payload["idLength"] == 6
    assert payload["id"] == "WSJT-X"
    assert payload["size"] > 50


def test_wsjtx_custom_target_command_uses_reserved_extension_type():
    payload = run_node_protocol_script(
        """
        import { buildOm0rxStartTargetQso, MESSAGE_TYPES } from './bridge/wsjtx-protocol.js';
        const packet = buildOm0rxStartTargetQso({
          id: 'WSJT-X',
          target: {
            call: 'E51ABC',
            grid: 'BG08',
            mode: 'FT8',
            dialFrequency: 14074000,
            rxDf: 1240,
            txDf: 1500
          }
        });
        const idLength = packet.readUInt32BE(12);
        const payloadOffset = 16 + idLength;
        const jsonLength = packet.readUInt32BE(payloadOffset);
        const jsonText = packet.toString('utf8', payloadOffset + 4, payloadOffset + 4 + jsonLength);
        console.log(JSON.stringify({
          magic: packet.readUInt32BE(0),
          schema: packet.readUInt32BE(4),
          type: packet.readUInt32BE(8),
          extensionType: MESSAGE_TYPES.OM0RX_START_TARGET_QSO,
          target: JSON.parse(jsonText).target
        }));
        """
    )

    assert payload["magic"] == 0xADBCCBDA
    assert payload["schema"] == 3
    assert payload["type"] == payload["extensionType"] == 17
    assert payload["target"]["call"] == "E51ABC"
    assert payload["target"]["mode"] == "FT8"


def test_wsjtx_parser_extracts_logged_adif_fields():
    payload = run_node_protocol_script(
        """
        import { QtStreamWriter, MESSAGE_TYPES } from './bridge/wsjtx-protocol.js';
        import { WsjtxParser } from './bridge/wsjtx-parser.js';
        const writer = new QtStreamWriter();
        writer.writeUInt32(0xadbccbda)
          .writeUInt32(3)
          .writeUInt32(MESSAGE_TYPES.LOGGED_ADIF)
          .writeByteArray('WSJT-X')
          .writeByteArray('<adif_ver:5>3.1.0 <eoh> <call:5>EA1AA <gridsquare:4>IN80 <freq:6>14.074 <mode:3>FT8 <rst_sent:3>-10 <rst_rcvd:3>-07 <eor>');
        const parsed = new WsjtxParser().parse(writer.buffer());
        console.log(JSON.stringify(parsed));
        """
    )

    assert payload["type"] == "LOGGED_ADIF"
    assert payload["id"] == "WSJT-X"
    assert payload["dxCall"] == "EA1AA"
    assert payload["dxGrid"] == "IN80"
    assert payload["mode"] == "FT8"
    assert payload["dialFrequency"] == 14074000
    assert payload["reportSent"] == "-10"
    assert payload["reportReceived"] == "-07"


def test_wsjtx_bridge_server_exposes_command_timeline_contract():
    bridge = (PROJECT_ROOT / "bridge" / "sdc-bridge-server.js").read_text(encoding="utf-8")

    assert "OM0RX_BRIDGE_TEST_MODE" in bridge
    assert "getWsjtxStatusSnapshot" in bridge
    assert "__dispatchWsjtxCommandForTest" in bridge
    assert "__getWsjtxStatusForTest" in bridge
    assert "WSJTX_TIMELINE_LIMIT" in bridge
    assert "wsjtxTimeline" in bridge
    assert "addWsjtxTimeline" in bridge
    assert "WSJTX_RECENT_DECODE_LIMIT" in bridge
    assert "wsjtxRecentDecodes" in bridge
    assert "recentDecodes: wsjtxRecentDecodes.slice(-50)" in bridge
    assert "commandCapabilities" in bridge
    assert "start_target_qso" in bridge
    assert "lastCommand" in bridge
    assert "commandErrors" in bridge
    assert "traceId: payload.traceId" in bridge
    assert "result.traceId = commandEntry.traceId" in bridge
    assert "timeline: wsjtxTimeline.slice(-25)" in bridge
    assert "scheduleLoggedQsoUpload" in bridge
    assert "messageType === 'LOGGED_ADIF'" in bridge
    assert "clearTimeout(pendingQsoLoggedUploadTimer)" in bridge
    assert "}, 1500);" in bridge


def test_wsjtx_halt_tx_endpoint_accepts_empty_body(monkeypatch):
    app = FastAPI()
    calls = []

    class FakeWsjtxService:
        def send_bridge_command(self, command, payload):
            calls.append((command, payload))
            return {"success": True, "command": command, "payload": payload}

    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: FakeWsjtxService())
    wsjtx_module.register_wsjtx_endpoints(app)

    response = TestClient(app).post("/api/wsjtx/halt-tx")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert calls == [("halt_tx", {"autoOnly": False})]


def test_wsjtx_decode_status_ingests_native_decode_into_automation(monkeypatch):
    import services.ft8_service as ft8_service_module
    from services.digital_automation import DigitalAutomationController

    app = FastAPI()
    fake_controller = DigitalAutomationController(mycall="OM0RX")

    class FakeQsoStatusStore:
        def call_flags(self, callsign, band, mode):
            return (False, False, True, True, False)

        def dxcc_overall(self, dxcc):
            return (False, False)

        def dxcc_bandmode_flags(self, dxcc, band, mode):
            return (True, True, False)

        def grid_flags(self, grid, band, mode):
            return (True, True, True)

    app.state.classifier = type("FakeClassifier", (), {"qso_status_store": FakeQsoStatusStore()})()
    fake_ft8_service = type(
        "FakeFt8Service",
        (),
        {
            "mode": "FT8",
            "automation_controller": fake_controller,
        },
    )()
    monkeypatch.setattr(ft8_service_module, "get_ft8_service", lambda: fake_ft8_service)
    wsjtx_module.register_wsjtx_endpoints(app)

    response = TestClient(app).post(
        "/api/wsjtx/decode-status",
        json={
            "call": "E51ABC",
            "grid": "BG08",
            "band": "20m",
            "mode": "FT8",
            "frequency_hz": 14074000,
            "audioOffset": 822,
            "snr": -9,
            "message": "CQ E51ABC BG08",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["automation_target"]["call"] == "E51ABC"
    assert payload["automation_target"]["heard"] is True
    assert payload["automation_decision"]["decision"] == "queued"

    selected = fake_controller.next_target(auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "E51ABC"


def test_wsjtx_bridge_logged_qso_upload_payload_prefers_adif_fields():
    payload = run_node_protocol_script(
        """
        process.env.OM0RX_BRIDGE_TEST_MODE = '1';
        const bridge = await import('./bridge/sdc-bridge-server.js?logged-qso-payload-contract');
        const upload = bridge.__buildLoggedQsoUploadForTest({
          dxCall: 'EA1AA',
          dxGrid: 'IN80',
          dialFrequency: 14074000,
          mode: 'FT8',
          txRst: '-10',
          rxRst: '-07',
          adifText: '<call:5>EA1AA <gridsquare:4>IN80 <freq:6>14.074 <mode:3>FT8 <rst_sent:3>-10 <rst_rcvd:3>-07 <eor>'
        });
        console.log(JSON.stringify(upload));
        """
    )

    assert payload["call"] == "EA1AA"
    assert payload["frequency_hz"] == 14074000
    assert payload["mode"] == "FT8"
    assert payload["grid"] == "IN80"
    assert payload["rst_sent"] == "-10"
    assert payload["rst_received"] == "-07"
    assert payload["adif_text"].startswith("<call:5>EA1AA")
    assert payload["source"] == "wsjtx-bridge"


def test_wsjtx_bridge_failed_command_status_contract():
    payload = run_node_protocol_script(
        """
        process.env.OM0RX_BRIDGE_TEST_MODE = '1';
        const bridge = await import('./bridge/sdc-bridge-server.js?failed-command-contract');
        bridge.__resetWsjtxBridgeDiagnosticsForTest();
        const result = bridge.__dispatchWsjtxCommandForTest('start_target_qso', {
          traceId: 'bridge-failed-trace',
          target: {
            call: 'K1FAIL',
            grid: 'FN42',
            mode: 'FT8',
            rxDf: 1240,
            txDf: 1500,
            traceId: 'bridge-failed-trace'
          }
        });
        const status = bridge.__getWsjtxStatusForTest();
        console.log(JSON.stringify({
          result,
          commandErrors: status.stats.commandErrors,
          commands: status.stats.commands,
          lastCommand: status.stats.lastCommand,
          lastCommandAgeMsType: typeof status.stats.lastCommandAgeMs,
          timeline: status.timeline
        }));
        """
    )

    assert payload["result"]["success"] is False
    assert payload["result"]["traceId"] == "bridge-failed-trace"
    assert payload["commandErrors"] == 1
    assert payload["commands"] == 1
    assert payload["lastCommand"]["command"] == "start_target_qso"
    assert payload["lastCommand"]["success"] is False
    assert payload["lastCommand"]["traceId"] == "bridge-failed-trace"
    assert payload["lastCommand"]["error"] == "WSJT-X UDP listener is not running"
    assert payload["lastCommand"]["payload"]["call"] == "K1FAIL"
    assert payload["lastCommand"]["payload"]["grid"] == "FN42"
    assert payload["lastCommand"]["payload"]["mode"] == "FT8"
    assert payload["lastCommandAgeMsType"] == "number"
    assert len(payload["timeline"]) == 1
    assert payload["timeline"][0]["traceId"] == "bridge-failed-trace"
    assert payload["timeline"][0]["success"] is False
    assert payload["timeline"][0]["error"] == "WSJT-X UDP listener is not running"
