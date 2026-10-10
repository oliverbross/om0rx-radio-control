import json
from asyncio import run
from pathlib import Path

import _bootstrap  # noqa: F401
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from remote_station.app import create_app
from remote_station.config import AgentConfigError, default_config_document, load_agent_config
from remote_station.runtime import RemoteCommandError, RemoteStationRuntime

TOKEN = "test-token-that-is-at-least-thirty-two-characters"


def _config(tmp_path: Path):
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(default_config_document(control_token=TOKEN)), encoding="utf-8")
    return load_agent_config(path)


class FakeRuntime:
    revision = 4

    def __init__(self):
        self.calls = []

    def snapshot(self):
        return {
            "protocol_version": 1,
            "agent": {"last_error": None},
            "radio": {"connected": True},
            "station": {"commissioned": False},
        }

    async def execute(self, request_id, command, arguments):
        self.calls.append((request_id, command, arguments))
        return {"success": True, "request_id": request_id, "replayed": False}


def test_clean_profile_uses_configurable_vspe_ports_and_keeps_tx_locked(tmp_path):
    config = _config(tmp_path)
    assert config.kpa_port == "COM17"
    assert config.kat_port == "COM15"
    assert config.kpa_baudrate == config.kat_baudrate == 38400
    assert config.commissioned is False
    assert config.bind_host == "127.0.0.1"
    assert config.flex_station_name == "Maestro"


def test_public_config_never_exposes_control_token(tmp_path):
    config = _config(tmp_path)
    public = config.public_summary()
    assert TOKEN not in repr(public)
    assert "control_token" not in repr(public)


def test_api_requires_bearer_token_and_forwards_idempotent_envelope(tmp_path):
    config = _config(tmp_path)
    runtime = FakeRuntime()
    client = TestClient(create_app(config, runtime=runtime))

    assert client.get("/api/v1/state").status_code == 401
    response = client.post(
        "/api/v1/commands",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={
            "request_id": "rumlog-0001",
            "command": "set_frequency_hz",
            "arguments": {"frequency_hz": 14_074_000},
        },
    )
    assert response.status_code == 200
    assert runtime.calls == [("rumlog-0001", "set_frequency_hz", {"frequency_hz": 14_074_000})]


def test_profile_applies_separate_policy_to_device_runtime(tmp_path, monkeypatch):
    from radio_control import config as radio_config

    config = _config(tmp_path)
    original = {
        key: getattr(radio_config, key)
        for key in (
            "KPA500_PORT",
            "KAT500_PORT",
            "STATION_COORDINATOR_COMMISSIONED",
            "STATION_BAREFOOT_DRIVE_W",
        )
    }
    try:
        config.apply_to_radio_config()
        assert radio_config.KPA500_PORT == "COM17"
        assert radio_config.KAT500_PORT == "COM15"
        assert radio_config.STATION_COORDINATOR_COMMISSIONED is False
        assert radio_config.STATION_BAREFOOT_DRIVE_W["40m"] == 100
    finally:
        for key, value in original.items():
            monkeypatch.setattr(radio_config, key, value)


def test_profile_refuses_non_loopback_binding(tmp_path):
    document = default_config_document(control_token=TOKEN)
    document["server"]["bind_host"] = "0.0.0.0"
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    try:
        load_agent_config(path)
    except AgentConfigError as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("A public bind must be rejected")


def test_profile_refuses_string_commissioning_flag(tmp_path):
    document = default_config_document(control_token=TOKEN)
    document["station"]["commissioned"] = "false"
    path = tmp_path / "ambiguous.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AgentConfigError, match="must be true or false"):
        load_agent_config(path)


def test_websocket_requires_authorization_header_and_rejects_url_token(tmp_path):
    config = _config(tmp_path)
    client = TestClient(create_app(config, runtime=FakeRuntime()))
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/api/v1/stream?access_token={TOKEN}"),
    ):
        pass
    with client.websocket_connect(
        "/api/v1/stream", headers={"Authorization": f"Bearer {TOKEN}"}
    ) as socket:
        message = socket.receive_json()
    assert message["type"] == "state"
    assert message["state"]["protocol_version"] == 1


class FakeFlex:
    bound_gui_client_handle = "0xabc"
    current_freq = 14.074
    current_mode = "DIGU"
    current_tx_slice_id = 0
    slice_id = 0

    def __init__(self):
        self.calls = []

    def tune_mhz(self, frequency):
        self.calls.append(("frequency", frequency))
        return True

    def set_mox(self, enabled):
        self.calls.append(("ptt", enabled))
        return True

    def _send(self, command):
        self.calls.append(("send", command))
        return True

    def get_slice_states(self):
        return [
            {
                "slice_id": 0,
                "index_letter": "A",
                "frequency": 14.074,
                "mode": "DIGU",
                "active": True,
                "transmit": self.current_tx_slice_id == 0,
                "in_use": True,
            },
            {
                "slice_id": 1,
                "index_letter": "B",
                "frequency": 14.08,
                "mode": "DIGU",
                "active": False,
                "transmit": self.current_tx_slice_id == 1,
                "in_use": True,
            },
        ]


class FakeCoordinator:
    def __init__(self):
        self.calls = []

    def snapshot(self):
        return {"route": {"active_drive_w": 25}, "commissioned": True}

    async def execute_flex_route_change(self, reason, operation):
        self.calls.append(reason)
        return operation()

    async def execute_raw_flex_tx(self, action, operation):
        self.calls.append(action)
        return operation()

    async def follow_observed_radio_route(self, frequency):
        self.calls.append(("follow", frequency))
        return True


def _runtime(tmp_path):
    runtime = RemoteStationRuntime(_config(tmp_path))
    runtime.flex = FakeFlex()
    runtime.coordinator = FakeCoordinator()
    runtime.radio_snapshot = {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.074,
        "mode": "DIGU",
        "mox": False,
    }
    return runtime


def test_remote_frequency_command_is_guarded_and_idempotent(tmp_path):
    runtime = _runtime(tmp_path)
    first = run(
        runtime.execute(
            "rumlog-frequency-0001",
            "set_frequency_hz",
            {"frequency_hz": 14_080_000},
        )
    )
    second = run(
        runtime.execute(
            "rumlog-frequency-0001",
            "set_frequency_hz",
            {"frequency_hz": 14_080_000},
        )
    )
    assert first["replayed"] is False
    assert second["replayed"] is True
    assert first["state"]["revision"] == runtime.revision == 1
    assert runtime.coordinator.calls == ["remote-frequency-a"]
    assert runtime.flex.calls == [("send", "slice tune 0 14.080000")]


def test_remote_radio_write_fails_closed_until_named_station_is_bound(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.flex.bound_gui_client_handle = None

    with pytest.raises(RemoteCommandError) as error:
        run(
            runtime.execute(
                "rumlog-frequency-unbound-0001",
                "set_frequency_hz",
                {"frequency_hz": 14_080_000},
            )
        )

    assert error.value.code == "flex-station-unbound"
    assert error.value.status_code == 503
    assert runtime.coordinator.calls == []
    assert runtime.flex.calls == []


def test_remote_ptt_rejects_truthy_strings(tmp_path):
    runtime = _runtime(tmp_path)
    try:
        run(runtime.execute("rumlog-ptt-0001", "set_ptt", {"enabled": "false"}))
    except RemoteCommandError as exc:
        assert exc.code == "command-argument-invalid"
        assert exc.status_code == 422
    else:
        raise AssertionError("A non-boolean PTT value must be rejected")
    assert runtime.flex.calls == []


def test_radio_snapshot_is_stale_until_frequency_is_known(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.flex.current_freq = None
    runtime.flex.get_slice_states = list
    runtime._update_radio_snapshot({"mode": "USB"})
    assert runtime.radio_snapshot["connected"] is True
    assert runtime.radio_snapshot["known"] is False
    assert runtime.radio_snapshot["stale"] is True

    runtime._update_radio_snapshot({"freq": 14.074, "mode": "DIGU"})
    assert runtime.radio_snapshot["known"] is True
    assert runtime.radio_snapshot["stale"] is False


def test_split_uses_flex_slice_b_as_transmit_vfo(tmp_path):
    runtime = _runtime(tmp_path)
    result = run(
        runtime.execute(
            "rumlog-split-0001",
            "set_split",
            {"enabled": True, "tx_frequency_hz": 14_082_000},
        )
    )
    assert result["result"]["transmit_vfo"] == "B"
    assert runtime.coordinator.calls == ["remote-split"]
    assert runtime.flex.calls == [
        ("send", "slice tune 1 14.082000"),
        ("send", "slice set 1 tx=1"),
    ]
    assert runtime.flex.current_tx_slice_id == 1


def test_cw_send_uses_atomic_station_transmit_guard(tmp_path):
    runtime = _runtime(tmp_path)
    result = run(
        runtime.execute(
            "rumlog-cw-0001",
            "send_cw",
            {"text": "CQ TEST"},
        )
    )
    assert result["result"]["accepted"] is True
    assert runtime.coordinator.calls == ["cwx"]
    assert runtime.flex.calls == [("send", "cwx send CQ TEST")]


def test_cross_band_split_and_command_delimiters_are_rejected(tmp_path):
    runtime = _runtime(tmp_path)
    with pytest.raises(RemoteCommandError, match="same band"):
        run(
            runtime.execute(
                "rumlog-split-0002",
                "set_split",
                {"enabled": True, "tx_frequency_hz": 7_074_000},
            )
        )
    with pytest.raises(RemoteCommandError, match="printable ASCII"):
        run(
            runtime.execute(
                "rumlog-cw-0002",
                "send_cw",
                {"text": "CQ|xmit 1"},
            )
        )
    assert runtime.flex.calls == []
