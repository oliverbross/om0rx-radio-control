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


def test_wsjtx_type5_datetime_guards_every_truncated_offset():
    payload = run_node_protocol_script(
        """
        import { WsjtxParser } from './bridge/wsjtx-parser.js';
        const string = value => {
          const text = Buffer.from(value); const field = Buffer.alloc(4 + text.length);
          field.writeUInt32BE(text.length, 0); text.copy(field, 4); return field;
        };
        const header = Buffer.alloc(12);
        header.writeUInt32BE(0xadbccbda, 0); header.writeUInt32BE(3, 4); header.writeUInt32BE(5, 8);
        const date = Buffer.alloc(17);
        date.writeBigInt64BE(2440588n, 0); date.writeUInt32BE(3600000, 8); date.writeUInt8(2, 12); date.writeInt32BE(3600, 13);
        const frequency = Buffer.alloc(8); frequency.writeBigInt64BE(14074000n);
        const full = Buffer.concat([header, string('MSHV-OM0RX-AUTO-DX'), date, string('EA1AA'), string('IN80'), frequency, string('FT8'), string('-10'), string('-07')]);
        const datetimeStart = header.length + string('MSHV-OM0RX-AUTO-DX').length;
        const parser = new WsjtxParser();
        const truncated = Array.from({length: 17}, (_, length) => parser.parse(full.subarray(0, datetimeStart + length)));
        const parsed = parser.parse(full);
        console.log(JSON.stringify({truncated, parsed}));
        """
    )
    assert all(item["type"] == "QSO_LOGGED" for item in payload["truncated"])
    assert all("dxCall" not in item and "dateTime" not in item for item in payload["truncated"])
    assert payload["parsed"]["dxCall"] == "EA1AA"
    assert payload["parsed"]["dateTime"] == "1970-01-01T00:00:00.000Z"


def test_wsjtx_parser_extracts_optional_om0rx_qso_state_from_status():
    payload = run_node_protocol_script(
        """
        import { QtStreamWriter, MESSAGE_TYPES } from './bridge/wsjtx-protocol.js';
        import { WsjtxParser } from './bridge/wsjtx-parser.js';
        const writer = new QtStreamWriter();
        writer.writeUInt32(0xadbccbda)
          .writeUInt32(3)
          .writeUInt32(MESSAGE_TYPES.STATUS)
          .writeByteArray('OM0RX-WSJT-Z')
          .writeUInt64(7074000)
          .writeByteArray('FT8')
          .writeByteArray('PA3DRI')
          .writeByteArray('-10')
          .writeByteArray('FT8')
          .writeBool(true)
          .writeBool(false)
          .writeBool(false)
          .writeUInt32(992)
          .writeUInt32(1450)
          .writeByteArray('OM0RX')
          .writeByteArray('JN88')
          .writeByteArray('JO21')
          .writeBool(false)
          .writeByteArray('')
          .writeBool(false)
          .writeUInt8(0)
          .writeUInt32(100)
          .writeUInt32(15)
          .writeByteArray('OM0RX-AUTO')
          .writeByteArray('PA3DRI OM0RX R-10')
          .writeByteArray('waiting_rrr');
        const parsed = new WsjtxParser().parse(writer.buffer());
        process.env.OM0RX_BRIDGE_TEST_MODE = '1';
        const bridge = await import('./bridge/sdc-bridge-server.js?state-contract');
        console.log(JSON.stringify({
          parsed,
          derived: bridge.__deriveWsjtxQsoStateForTest(parsed),
          fallback: bridge.__deriveWsjtxQsoStateForTest({ txEnabled: true, dxCall: 'PA3DRI' }),
          firstCall: bridge.__deriveWsjtxQsoStateForTest({
            txEnabled: true,
            dxCall: 'WD4OOZ',
            txMessage: 'WD4OOZ OM0RX JN88'
          }),
          report: bridge.__deriveWsjtxQsoStateForTest({
            txEnabled: true,
            dxCall: 'PA3DRI',
            txMessage: 'PA3DRI OM0RX R-10'
          })
        }));
        """
    )

    assert payload["parsed"]["type"] == "STATUS"
    assert payload["parsed"]["id"] == "OM0RX-WSJT-Z"
    assert payload["parsed"]["dxCall"] == "PA3DRI"
    assert payload["parsed"]["txMessage"] == "PA3DRI OM0RX R-10"
    assert payload["parsed"]["qsoState"] == "waiting_rrr"
    assert payload["derived"] == "waiting_rrr"
    assert payload["fallback"] == "calling"
    assert payload["firstCall"] == "calling"
    assert payload["report"] == "in_qso"


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
    assert "const nativeOwnsControl = selectedDigitalProvider === 'mshv_auto_dx'" in bridge
    assert "selectedDigitalProvider === 'mshv_auto_dx' && !['status', 'halt_tx'].includes(command)" in bridge
    assert "selectedDigitalProvider === 'mshv_auto_dx' && !['status', 'halt_tx', 'clear', 'replay', 'reply']" not in bridge
    assert "start_target_qso" in bridge
    assert "lastCommand" in bridge
    assert "commandErrors" in bridge
    assert "traceId: payload.traceId" in bridge
    assert "result.traceId = commandEntry.traceId" in bridge
    assert "timeline: wsjtxTimeline.slice(-25)" in bridge
    assert "scheduleLoggedQsoUpload" in bridge
    assert "loggedQsoCoalescer.accept" in bridge
    coalescer = (PROJECT_ROOT / "bridge" / "digital-provider.js").read_text(encoding="utf-8")
    assert "type === 'LOGGED_ADIF'" in coalescer
    assert "Type 5 is the only immediate completion receipt" in coalescer
    assert "setTimeout" not in coalescer
    assert "event_id: eventId" in bridge
    assert "station_callsign: eventIdentity.station_callsign" in bridge


def test_wsjtx_frontend_logged_adif_handler_is_display_only():
    handler = (PROJECT_ROOT / "frontend" / "js" / "wsjtx-handler.js").read_text(encoding="utf-8")
    start = handler.index("function handleWsjtxLoggedAdif")
    end = handler.index("/**", start + 1)
    body = handler[start:end]

    assert "logQsoToWavelog(data)" not in body
    assert "display-only" in body


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


def test_wsjtx_decode_status_returns_native_decode_enrichment(monkeypatch):
    app = FastAPI()

    class FakeQsoStatusStore:
        _loaded_at = 1
        call_worked = set()
        call_confirmed = set()
        call_band_worked = set()
        call_mode_worked = set()
        call_bandmode_worked = set()
        call_bandmode_confirmed = set()

    app.state.classifier = type("FakeClassifier", (), {"qso_status_store": FakeQsoStatusStore()})()
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
    assert payload["call"] == "E51ABC"
    assert payload["call_status"] == "New Call"
    assert payload["worked_same_band_mode"] is False
    assert payload["needed"]["call"] is True
    assert payload.get("automation_target") is None


def test_wsjtx_decode_status_reports_new_band_for_worked_call_on_other_band(monkeypatch):
    app = FastAPI()

    class FakeQsoStatusStore:
        _loaded_at = 1
        call_worked = {"AD9GE"}
        call_confirmed = {"AD9GE"}
        call_band_worked = {("AD9GE", "10m")}
        call_mode_worked = {("AD9GE", "FT8")}
        call_bandmode_worked = {("AD9GE", "10m", "FT8")}
        call_bandmode_confirmed = set()

    app.state.classifier = type("FakeClassifier", (), {"qso_status_store": FakeQsoStatusStore()})()
    wsjtx_module.register_wsjtx_endpoints(app)

    response = TestClient(app).post(
        "/api/wsjtx/decode-status",
        json={
            "call": "AD9GE",
            "grid": "EM69",
            "band": "20m",
            "mode": "FT8",
            "frequency_hz": 14074000,
            "audioOffset": 847,
            "snr": -14,
            "message": "CQ AD9GE EM69",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["call_status"] == "New Band"
    assert payload["worked_same_band_mode"] is False
    assert payload["needed_on_band"]["call"] is True
    assert payload.get("automation_target") is None


def test_wsjtx_decode_status_marks_exact_worked_band_mode(monkeypatch):
    app = FastAPI()

    class FakeQsoStatusStore:
        _loaded_at = 1
        call_worked = {"4L1FL"}
        call_confirmed = set()
        call_band_worked = {("4L1FL", "20m")}
        call_mode_worked = {("4L1FL", "FT8")}
        call_bandmode_worked = {("4L1FL", "20m", "FT8")}
        call_bandmode_confirmed = set()

    app.state.classifier = type("FakeClassifier", (), {"qso_status_store": FakeQsoStatusStore()})()
    wsjtx_module.register_wsjtx_endpoints(app)

    response = TestClient(app).post(
        "/api/wsjtx/decode-status",
        json={
            "call": "4L1FL",
            "grid": "LN21",
            "band": "20m",
            "mode": "FT8",
            "frequency_hz": 14074000,
            "audioOffset": 543,
            "snr": -10,
            "message": "CQ 4L1FL LN21",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["call_status"] == "Worked"
    assert payload["worked_same_band_mode"] is True


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


def test_type5_and_type12_share_stable_station_client_completion_event_id():
    payload = run_node_protocol_script(
        """
        process.env.OM0RX_BRIDGE_TEST_MODE = '1';
        const bridge = await import('./bridge/sdc-bridge-server.js?shared-event-id');
        const common = {
          dxCall: 'EA1AA', stationCallsign: 'OM0RX', clientId: 'MSHV-OM0RX-AUTO-DX',
          dialFrequency: 14074000, mode: 'FT8', timeOff: '2026-10-04T12:00:45.000Z'
        };
        const type5 = bridge.__buildLoggedQsoUploadForTest({...common, eventType:'QSO_LOGGED'});
        const type12 = bridge.__buildLoggedQsoUploadForTest({
          ...common, eventType:'LOGGED_ADIF', timeOn:'2026-10-04T12:00:00.000Z',
          adifText:'<call:5>EA1AA <freq:6>14.074 <mode:3>FT8 <qso_date:8>20261004 <time_on:6>120000 <time_off:6>120045 <eor>'
        });
        const otherClient = bridge.__buildLoggedQsoUploadForTest({...common, clientId:'OTHER'});
        console.log(JSON.stringify({type5, type12, otherClient}));
        """
    )
    assert payload["type5"]["event_id"] == payload["type12"]["event_id"]
    assert payload["type5"]["event_id"] != payload["otherClient"]["event_id"]
    assert payload["type12"]["station_callsign"] == "OM0RX"
    assert payload["type12"]["client_id"] == "MSHV-OM0RX-AUTO-DX"


def test_bridge_retry_queue_is_atomic_and_surfaces_persistence_failure(tmp_path):
    good = tmp_path / "pending.jsonl"
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("file", encoding="utf-8")
    payload = run_node_protocol_script(
        f"""
        process.env.OM0RX_BRIDGE_TEST_MODE = '1';
        process.env.OM0RX_BRIDGE_TEST_PERSIST = '1';
        process.env.WSJTX_LOGGED_QSO_PENDING_PATH = {json.dumps(str(good))};
        const bridge = await import('./bridge/sdc-bridge-server.js?durable-retry-good');
        const qso = {{provider:'mshv_auto_dx', station_callsign:'OM0RX', client_id:'MSHV-OM0RX-AUTO-DX', event_id:'{'a' * 64}', call:'EA1AA', mode:'FT8', frequency_hz:14074000, time_on:'2026-10-04T12:00:00Z', time_off:'2026-10-04T12:00:45Z'}};
        const queued = bridge.__enqueueLoggedQsoUploadForTest(qso, 'offline');
        console.log(JSON.stringify({{queued, count:bridge.__loggedQsoQueueForTest().length}}));
        """
    )
    assert payload == {"queued": True, "count": 1}
    assert good.read_text(encoding="utf-8").strip()

    failed = run_node_protocol_script(
        f"""
        process.env.OM0RX_BRIDGE_TEST_MODE = '1';
        process.env.OM0RX_BRIDGE_TEST_PERSIST = '1';
        process.env.WSJTX_LOGGED_QSO_PENDING_PATH = {json.dumps(str(blocker / 'pending.jsonl'))};
        const bridge = await import('./bridge/sdc-bridge-server.js?durable-retry-fail');
        const qso = {{provider:'mshv_auto_dx', station_callsign:'OM0RX', client_id:'MSHV-OM0RX-AUTO-DX', event_id:'{'b' * 64}', call:'EA1BB', mode:'FT8', frequency_hz:14074000, time_on:'2026-10-04T12:01:00Z', time_off:'2026-10-04T12:01:45Z'}};
        const queued = bridge.__enqueueLoggedQsoUploadForTest(qso, 'offline');
        console.log(JSON.stringify({{queued, count:bridge.__loggedQsoQueueForTest().length}}));
        """
    )
    assert failed == {"queued": False, "count": 0}


def test_bridge_corrupt_retry_queue_is_preserved_and_blocks_overwrite(tmp_path):
    pending = tmp_path / "pending.jsonl"
    original = '{"payload":{"call":"A1AA","event_id":"' + ("a" * 64) + '"}}\n{not-json}\n'
    pending.write_text(original, encoding="utf-8")
    payload = run_node_protocol_script(
        f"""
        process.env.OM0RX_BRIDGE_TEST_MODE = '1';
        process.env.OM0RX_BRIDGE_TEST_PERSIST = '1';
        process.env.WSJTX_LOGGED_QSO_PENDING_PATH = {json.dumps(str(pending))};
        const bridge = await import('./bridge/sdc-bridge-server.js?durable-retry-corrupt');
        const loaded = bridge.__loadLoggedQsoQueueForTest();
        const qso = {{provider:'mshv_auto_dx', station_callsign:'OM0RX', client_id:'MSHV-OM0RX-AUTO-DX', event_id:'{'b' * 64}', call:'EA1BB', mode:'FT8', frequency_hz:14074000, time_on:'2026-10-04T12:01:00Z', time_off:'2026-10-04T12:01:45Z'}};
        const queued = bridge.__enqueueLoggedQsoUploadForTest(qso, 'offline');
        console.log(JSON.stringify({{loaded, queued, count:bridge.__loggedQsoQueueForTest().length}}));
        """
    )
    assert payload["loaded"]["count"] == 0
    assert payload["loaded"]["fault"].startswith("retry-queue-load-failed:")
    assert payload["queued"] is False
    assert payload["count"] == 0
    assert pending.read_text(encoding="utf-8") == original


def test_wsjtx_bridge_logged_qso_result_event_contract():
    payload = run_node_protocol_script(
        """
        process.env.OM0RX_BRIDGE_TEST_MODE = '1';
        const bridge = await import('./bridge/sdc-bridge-server.js?logged-qso-result-contract');
        const event = bridge.__buildLoggedQsoResultEventForTest({
          call: 'EA1AA',
          grid: 'IN80',
          frequency_hz: 14074000,
          mode: 'FT8',
          rst_sent: '-10',
          rst_received: '-07'
        }, {
          success: true,
          statusCode: 200,
          result: {
            success: true,
            wavelog: { success: true, message: 'Logged' },
            qso_data: {
              callsign: 'EA1AA',
              frequency: 14.074,
              mode: 'FT8',
              gridsquare: 'IN80',
              rst_sent: '-10',
              rst_received: '-07',
              country: 'Spain'
            }
          }
        });
        console.log(JSON.stringify(event));
        """
    )

    assert payload["type"] == "wsjtx_log_result"
    assert payload["source"] == "wsjtx"
    assert payload["success"] is True
    assert payload["status"] == "success"
    assert payload["backend_uploaded"] is True
    assert payload["qso_data"]["callsign"] == "EA1AA"
    assert payload["qso_data"]["frequency"] == 14.074
    assert payload["qso_data"]["rst_received"] == "-07"


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
