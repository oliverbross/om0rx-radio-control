import asyncio
import json
import time
from asyncio import run
from pathlib import Path

import _bootstrap  # noqa: F401
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from radio_control.elecraft import build_station_path
from remote_station.app import create_app
from remote_station.config import AgentConfigError, default_config_document, load_agent_config
from remote_station.runtime import (
    FLEX_POLL_IDLE_SECONDS,
    FLEX_SNAPSHOT_WINDOW_SECONDS,
    RemoteCommandError,
    RemoteStationRuntime,
)
from services.station_alarms import build_station_alarms
from services.elecraft_station import StationActionError

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
    assert config.kpa_enabled is True
    assert config.kat_enabled is True
    assert config.kpa_port == "COM17"
    assert config.kat_port == "COM15"
    assert config.kpa_baudrate == config.kat_baudrate == 38400
    assert config.follow_radio is True
    assert config.digital_kpa_policy == "operate"
    assert config.commissioned is False
    assert config.bind_host == "127.0.0.1"
    assert config.flex_station_name == "Maestro"


def test_public_config_never_exposes_control_token(tmp_path):
    config = _config(tmp_path)
    public = config.public_summary()
    assert TOKEN not in repr(public)
    assert "control_token" not in repr(public)


def test_authenticated_remote_config_update_is_validated_and_preserves_token(tmp_path):
    config = _config(tmp_path)
    client = TestClient(create_app(config, runtime=FakeRuntime()))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    public = client.get("/api/v1/config", headers=headers).json()["config"]
    public["policy"]["amplifier_drive_w"]["20m"] = 30
    public["policy"]["barefoot_drive_w"]["20m"] = 70
    public["policy"]["kat_antenna"]["20m"] = 2

    response = client.put("/api/v1/config", headers=headers, json={"config": public})

    assert response.status_code == 200
    assert response.json()["restart_required"] is True
    saved = json.loads(config.path.read_text(encoding="utf-8"))
    assert saved["server"]["control_token"] == TOKEN
    assert saved["station"]["amplifier_drive_w"]["20m"] == 30
    assert saved["station"]["barefoot_drive_w"]["20m"] == 70
    assert saved["station"]["kat_antenna_policy"]["20m"] == 2


def test_saved_config_is_explicitly_pending_until_runtime_restart(tmp_path):
    config = _config(tmp_path)
    runtime = RemoteStationRuntime(config)
    client = TestClient(create_app(config, runtime=runtime))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    before = client.get("/api/v1/config", headers=headers).json()
    updated = before["config"]
    updated["policy"]["amplifier_allowed_bands"] = ["80m"]

    response = client.put(
        "/api/v1/config",
        headers=headers,
        json={"config": updated},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["config_status"]["restart_required"] is True
    assert payload["restart_required"] is True
    assert payload["saved_config"]["policy"]["amplifier_allowed_bands"] == ["80m"]
    assert "80m" in payload["active_config"]["policy"]["amplifier_allowed_bands"]
    assert payload["active_config"]["policy"]["amplifier_allowed_bands"] != ["80m"]
    assert (
        payload["config_status"]["active_fingerprint"]
        != payload["config_status"]["saved_fingerprint"]
    )
    state = client.get("/api/v1/state", headers=headers).json()["state"]
    assert state["agent"]["config"]["restart_required"] is True
    assert TOKEN not in repr(payload)
    assert TOKEN not in repr(state)

    restarted = RemoteStationRuntime(load_agent_config(config.path))
    restarted_client = TestClient(
        create_app(restarted.config, runtime=restarted)
    )
    after = restarted_client.get("/api/v1/config", headers=headers).json()
    assert after["config_status"]["restart_required"] is False
    assert after["active_config"]["policy"]["amplifier_allowed_bands"] == ["80m"]


def test_remote_config_update_rejects_invalid_drive_without_changing_file(tmp_path):
    config = _config(tmp_path)
    client = TestClient(create_app(config, runtime=FakeRuntime()))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    public = client.get("/api/v1/config", headers=headers).json()["config"]
    before = config.path.read_text(encoding="utf-8")
    public["policy"]["amplifier_drive_w"]["20m"] = 0

    response = client.put("/api/v1/config", headers=headers, json={"config": public})

    assert response.status_code == 422
    assert config.path.read_text(encoding="utf-8") == before
    assert public["kpa500"]["enabled"] is True
    assert public["kat500"]["enabled"] is True
    assert public["policy"]["follow_radio"] is True


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
            "KPA500_ENABLED",
            "KAT500_ENABLED",
            "ELECRAFT_FOLLOW_RADIO",
            "DIGITAL_KPA_POLICY",
            "STATION_COORDINATOR_COMMISSIONED",
            "STATION_BAREFOOT_DRIVE_W",
        )
    }
    try:
        config.apply_to_radio_config()
        assert radio_config.KPA500_PORT == "COM17"
        assert radio_config.KAT500_PORT == "COM15"
        assert radio_config.KPA500_ENABLED is True
        assert radio_config.KAT500_ENABLED is True
        assert radio_config.ELECRAFT_FOLLOW_RADIO is True
        assert radio_config.DIGITAL_KPA_POLICY == "operate"
        assert radio_config.STATION_COORDINATOR_COMMISSIONED is False
        assert radio_config.STATION_BAREFOOT_DRIVE_W["40m"] == 100
    finally:
        for key, value in original.items():
            monkeypatch.setattr(radio_config, key, value)


def test_profile_applies_explicit_accessory_disable_and_digital_standby(tmp_path, monkeypatch):
    from radio_control import config as radio_config

    document = default_config_document(control_token=TOKEN)
    document["kpa500"]["enabled"] = False
    document["kat500"]["enabled"] = False
    document["station"]["follow_radio"] = False
    document["station"]["digital_kpa_policy"] = "standby"
    path = tmp_path / "accessories-disabled.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    config = load_agent_config(path)
    original = {
        key: getattr(radio_config, key)
        for key in (
            "KPA500_ENABLED",
            "KAT500_ENABLED",
            "ELECRAFT_FOLLOW_RADIO",
            "DIGITAL_KPA_POLICY",
        )
    }
    try:
        config.apply_to_radio_config()
        assert radio_config.KPA500_ENABLED is False
        assert radio_config.KAT500_ENABLED is False
        assert radio_config.ELECRAFT_FOLLOW_RADIO is False
        assert radio_config.DIGITAL_KPA_POLICY == "standby"
    finally:
        for key, value in original.items():
            monkeypatch.setattr(radio_config, key, value)


@pytest.mark.parametrize(
    ("section", "key", "expected"),
    (
        ("kpa500", "enabled", "kpa500.enabled=true"),
        ("kat500", "enabled", "kat500.enabled=true"),
        ("station", "follow_radio", "station.follow_radio=true"),
    ),
)
def test_commissioned_profile_requires_transmit_safety_components(
    tmp_path, section, key, expected
):
    document = default_config_document(control_token=TOKEN)
    document["station"]["commissioned"] = True
    document[section][key] = False
    path = tmp_path / f"commissioned-{section}-{key}.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AgentConfigError, match=expected):
        load_agent_config(path)


def test_commissioned_profile_requires_flex_antenna_policy(tmp_path):
    document = default_config_document(control_token=TOKEN)
    document["station"]["commissioned"] = True
    document["flex"]["antenna_policy"]["enabled"] = False
    path = tmp_path / "commissioned-flex-policy-disabled.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AgentConfigError, match="flex.antenna_policy.enabled=true"):
        load_agent_config(path)


def test_profile_rejects_unknown_digital_kpa_policy(tmp_path):
    document = default_config_document(control_token=TOKEN)
    document["station"]["digital_kpa_policy"] = "automatic"
    path = tmp_path / "bad-digital-policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AgentConfigError, match="must be operate or standby"):
        load_agent_config(path)


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

    def add_spot(self, *arguments):
        self.calls.append(("spot", arguments))
        return True

    def close(self):
        self.calls.append(("close",))

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

    async def stop(self):
        self.calls.append("stop")


class FakeElecraft:
    async def stop(self):
        return None


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


def test_remote_flex_poll_is_fast_enough_for_live_monitoring():
    assert FLEX_SNAPSHOT_WINDOW_SECONDS <= 0.2
    assert FLEX_POLL_IDLE_SECONDS <= 0.05


def test_accessory_follow_does_not_block_radio_or_queue_obsolete_targets(tmp_path):
    async def scenario():
        runtime = _runtime(tmp_path)
        entered = asyncio.Event()
        release = asyncio.Event()
        followed = []

        async def slow_follow(frequency):
            followed.append(frequency)
            entered.set()
            await release.wait()

        runtime.coordinator.follow_observed_radio_route = slow_follow
        runtime._schedule_route_follow()
        await asyncio.wait_for(entered.wait(), 1)
        first = runtime._route_follow_task
        # The next radio observation remains publishable while accessories wait.
        runtime._update_radio_snapshot({"freq": 14.074, "mode": "DIGU", "mox": True})
        assert runtime.radio_snapshot["mox"] is True
        runtime.radio_snapshot["frequency"] = 7.195
        runtime._schedule_route_follow()
        assert runtime._route_follow_task is first
        assert followed == [14.074]
        release.set()
        await first
        runtime._schedule_route_follow()
        await runtime._route_follow_task
        assert followed == [14.074, 7.195]

    run(scenario())


def test_shutdown_waits_for_in_flight_route_follow(tmp_path):
    async def scenario():
        runtime = _runtime(tmp_path)
        runtime.elecraft = FakeElecraft()
        entered = asyncio.Event()
        release = asyncio.Event()

        async def slow_follow(_frequency):
            entered.set()
            await release.wait()

        runtime.coordinator.follow_observed_radio_route = slow_follow
        runtime._schedule_route_follow()
        await asyncio.wait_for(entered.wait(), 1)
        stopping = asyncio.create_task(runtime.stop())
        await asyncio.sleep(0)
        assert stopping.done() is False
        release.set()
        await asyncio.wait_for(stopping, 1)
        assert runtime._route_follow_task is None
        assert "stop" in runtime.coordinator.calls

    run(scenario())


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


def test_remote_frequency_and_mode_share_one_guarded_route_transaction(tmp_path):
    runtime = _runtime(tmp_path)
    result = run(
        runtime.execute(
            "xlog-frequency-mode-0001",
            "set_frequency_mode",
            {"frequency_hz": 3_698_000, "mode": "LSB", "vfo": "A"},
        )
    )

    assert result["result"] == {
        "frequency_hz": 3_698_000,
        "mode": "LSB",
        "vfo": "A",
    }
    assert runtime.coordinator.calls == ["remote-frequency-mode-a"]
    assert runtime.flex.calls == [
        ("send", "slice set 0 mode=LSB"),
        ("send", "slice tune 0 3.698000"),
        ("send", "sub slice all"),
    ]
    assert result["timing_ms"]["queue"] >= 0
    assert result["timing_ms"]["execution"] >= 0
    assert result["timing_ms"]["total"] >= result["timing_ms"]["execution"]
    assert result["state"]["radio"]["route_change_pending"] == {
        "frequency_hz": 3_698_000,
        "mode": "LSB",
        "vfo": "A",
        "age_seconds": pytest.approx(0.0, abs=0.05),
    }


def test_remote_frequency_mode_skips_redundant_mode_but_refreshes_subscription(tmp_path):
    runtime = _runtime(tmp_path)
    result = run(
        runtime.execute(
            "xlog-frequency-mode-unchanged-0001",
            "set_frequency_mode",
            {"frequency_hz": 14_080_000, "mode": "DIGU", "vfo": "A"},
        )
    )

    assert result["success"] is True
    assert runtime.flex.calls == [
        ("send", "slice tune 0 14.080000"),
        ("send", "sub slice all"),
    ]


def test_atomic_frequency_mode_publication_waits_for_coherent_flex_state(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._pending_frequency_mode = {
        "frequency": 7.195,
        "mode": "LSB",
        "vfo": "A",
        "slice_id": 0,
        "started_at": time.time(),
    }
    runtime.flex.current_freq = 7.185
    runtime.flex.current_mode = "LSB"
    runtime.flex.get_slice_states = lambda: [
        {
            "slice_id": 0,
            "index_letter": "A",
            "frequency": 7.185,
            "mode": "LSB",
            "active": True,
            "transmit": True,
            "in_use": True,
        }
    ]

    route_ready = runtime._update_radio_snapshot(
        {"freq": 7.185, "mode": "LSB", "mox": False, "interlock_state": "READY"}
    )

    assert route_ready is False
    assert runtime.radio_snapshot["frequency"] == 14.074
    assert runtime.radio_snapshot["mode"] == "DIGU"
    assert runtime.radio_snapshot["mox"] is False
    assert runtime.radio_snapshot["interlock_state"] == "READY"
    assert runtime.radio_snapshot["route_change_pending"]["frequency_hz"] == 7_195_000

    route_ready = runtime._update_radio_snapshot(
        {"freq": 7.195, "mode": "LSB", "mox": False, "interlock_state": "READY"}
    )

    assert route_ready is True
    assert runtime.radio_snapshot["frequency"] == 7.195
    assert runtime.radio_snapshot["mode"] == "LSB"
    assert runtime.radio_snapshot["transmit"]["frequency"] == 7.195
    assert runtime.radio_snapshot["transmit"]["mode"] == "LSB"
    assert runtime.radio_snapshot["vfos"]["A"]["frequency"] == 7.195
    assert runtime.radio_snapshot["vfos"]["A"]["mode"] == "LSB"
    assert "route_change_pending" not in runtime.radio_snapshot


def test_simplex_spot_uses_one_guard_and_waits_for_tx_ownership(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.flex.current_tx_slice_id = 1
    result = run(runtime.execute("simplex-0001", "tune_simplex", {
        "frequency_hz": 7_195_000, "mode": "LSB",
    }))
    assert result["success"] is True
    assert runtime.coordinator.calls == ["remote-simplex-a"]
    assert runtime.flex.calls == [
        ("send", "slice set 0 active=1"),
        ("send", "slice set 0 tx=1"),
        ("send", "slice set 0 mode=LSB"),
        ("send", "slice tune 0 7.195000"),
        ("send", "sub slice all"),
    ]
    # Matching frequency/mode must not hide an old B transmit slice.
    levels = {"freq": 7.195, "mode": "LSB", "mox": True}
    assert runtime._update_radio_snapshot(levels) is False
    assert runtime.radio_snapshot["mox"] is True
    runtime.flex.current_tx_slice_id = 0
    assert runtime._update_radio_snapshot(levels) is True
    assert runtime.radio_snapshot["transmit"]["index_letter"] == "A"


@pytest.mark.parametrize("failure", ["active=1", "tx=1", "mode=LSB", "7.195000"])
def test_simplex_spot_stops_on_first_rejected_command(tmp_path, failure):
    runtime = _runtime(tmp_path)
    def send(command):
        runtime.flex.calls.append(command)
        return failure not in command
    runtime.flex._send = send
    async def guarded(reason, operation):
        assert operation() is False
        raise StationActionError("flex-route-failed", "Rejected")
    runtime.coordinator.execute_flex_route_change = guarded
    with pytest.raises(RemoteCommandError):
        run(runtime.execute("simplex-rejected", "tune_simplex", {
            "frequency_hz": 7_195_000, "mode": "LSB",
        }))
    assert failure in runtime.flex.calls[-1]
    assert runtime._pending_frequency_mode is None
    assert runtime.radio_snapshot["stale"] is True


def test_simplex_invalid_target_never_enters_guard(tmp_path):
    runtime = _runtime(tmp_path)
    with pytest.raises(RemoteCommandError):
        run(runtime.execute("simplex-invalid", "tune_simplex", {
            "frequency_hz": 1, "mode": "LSB",
        }))
    assert runtime.coordinator.calls == []
    assert runtime.flex.calls == []


def test_remote_spot_command_adds_receive_only_flex_marker(tmp_path):
    runtime = _runtime(tmp_path)
    result = run(
        runtime.execute(
            "rumlog-spot-0001",
            "add_spot",
            {
                "frequency_hz": 14_074_000,
                "callsign": "K1ABC",
                "mode": "DIGU",
                "source": "RUMlogNG Logbook",
                "spotter": "OM0RX",
                "comment": "DX",
                "timestamp": 1_791_628_830,
                "lifetime_seconds": 900,
                "priority": 4,
                "color": "#30D158",
            },
        )
    )

    assert result["result"] == {
        "accepted": True,
        "callsign": "K1ABC",
        "frequency_hz": 14_074_000,
    }
    assert runtime.coordinator.calls == []
    assert runtime.flex.calls == [
        (
            "spot",
            (
                14.074,
                "K1ABC",
                "DIGU",
                "RUMlogNG Logbook",
                "OM0RX",
                "DX",
                900,
                4,
                "#30D158",
                1_791_628_830,
            ),
        )
    ]


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("frequency_hz", 0, "spot-frequency-invalid"),
        ("callsign", "BAD|CALL", "spot-text-invalid"),
        ("priority", 6, "spot-priority-invalid"),
        ("color", "blue", "spot-color-invalid"),
    ],
)
def test_remote_spot_command_rejects_invalid_arguments(tmp_path, field, value, code):
    runtime = _runtime(tmp_path)
    arguments = {
        "frequency_hz": 14_074_000,
        "callsign": "K1ABC",
        "mode": "DIGU",
        "source": "RUMlogNG",
        "spotter": "OM0RX",
        "comment": "",
        "timestamp": 1_791_628_830,
        "lifetime_seconds": 900,
        "priority": 4,
        "color": "#30D158",
    }
    arguments[field] = value

    with pytest.raises(RemoteCommandError) as error:
        run(runtime.execute(f"invalid-{field}", "add_spot", arguments))

    assert error.value.code == code
    assert runtime.flex.calls == []


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


def test_radio_snapshot_retains_station_path_antenna_keys(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._update_radio_snapshot(
        {"freq": 14.074, "mode": "DIGU", "rx_ant": "ANT1", "tx_ant": "ANT1"}
    )

    assert runtime.radio_snapshot["rx_antenna"] == "ANT1"
    assert runtime.radio_snapshot["tx_antenna"] == "ANT1"
    assert runtime.radio_snapshot["rx_ant"] == "ANT1"
    assert runtime.radio_snapshot["tx_ant"] == "ANT1"


def test_radio_snapshot_uses_bound_transmit_slice_when_aggregate_tx_ant_is_invalid(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.flex.current_tx_slice_id = 1
    slices = runtime.flex.get_slice_states()
    slices[0]["tx_antenna"] = "ANT1"
    slices[1]["tx_antenna"] = "ANT1"
    runtime.flex.get_slice_states = lambda: slices

    runtime._update_radio_snapshot(
        {"freq": 14.074, "mode": "DIGU", "rx_ant": "ANT1", "tx_ant": "INVALID"}
    )

    assert runtime.radio_snapshot["frequency"] == 14.08
    assert runtime.radio_snapshot["transmit"]["index_letter"] == "B"
    assert runtime.radio_snapshot["tx_antenna"] == "ANT1"
    assert runtime.radio_snapshot["tx_ant"] == "ANT1"


def test_radio_snapshot_publishes_split_route_from_transmit_slice(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.flex.get_slice_states = lambda: [
        {
            "slice_id": 0,
            "index_letter": "A",
            "frequency": 24.940,
            "mode": "USB",
            "active": True,
            "transmit": False,
            "in_use": True,
            "tx_antenna": "ANT1",
        },
        {
            "slice_id": 1,
            "index_letter": "B",
            "frequency": 24.945,
            "mode": "USB",
            "active": False,
            "transmit": True,
            "in_use": True,
            "tx_antenna": "ANT1",
        },
    ]

    runtime._update_radio_snapshot(
        {
            "freq": 24.940,
            "mode": "USB",
            "tx_ant": "ANT1",
            "mox": False,
            "interlock_state": "READY",
        }
    )

    assert runtime.radio_snapshot["rx_frequency"] == 24.940
    assert runtime.radio_snapshot["tx_frequency"] == 24.945
    assert runtime.radio_snapshot["frequency"] == 24.945
    assert runtime.radio_snapshot["active_receive"]["index_letter"] == "A"
    assert runtime.radio_snapshot["transmit"]["index_letter"] == "B"


def test_radio_snapshot_does_not_hide_valid_aggregate_tx_route_mismatch(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.flex.current_tx_slice_id = 1
    slices = runtime.flex.get_slice_states()
    slices[1]["tx_antenna"] = "ANT1"
    runtime.flex.get_slice_states = lambda: slices

    runtime._update_radio_snapshot(
        {"freq": 14.074, "mode": "DIGU", "rx_ant": "ANT1", "tx_ant": "ANT2"}
    )

    assert runtime.radio_snapshot["tx_antenna"] == "ANT2"
    assert runtime.radio_snapshot["tx_ant"] == "ANT2"


def test_live_15m_shape_clears_false_route_warning_but_keeps_commissioning_info(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.flex.current_tx_slice_id = 1
    slices = runtime.flex.get_slice_states()
    slices[0].update(tx_antenna="ANT1", rx_antenna="ANT1")
    slices[1].update(tx_antenna="ANT1", rx_antenna="ANT1", frequency=21.049, mode="CW")
    runtime.flex.get_slice_states = lambda: slices
    runtime._update_radio_snapshot(
        {
            "freq": 21.049,
            "mode": "CW",
            "rx_ant": "ANT1",
            "tx_ant": "INVALID",
            "mox": False,
            "interlock_state": "RECEIVE",
        }
    )

    now = time.time()
    elecraft = {
        "updated_at": now,
        "kpa500": {
            "enabled": True,
            "connected": True,
            "responsive": True,
            "power": True,
            "operate": False,
            "band": "15m",
            "fault": "00",
            "observed_at": now,
        },
        "kat500": {
            "enabled": True,
            "connected": True,
            "responsive": True,
            "power": True,
            "mode": "auto",
            "antenna": 1,
            "band": "15m",
            "frequency_khz": 21049,
            "tuning": False,
            "fault": "00",
            "observed_at": now,
        },
    }
    path = build_station_path(
        elecraft,
        runtime.radio_snapshot,
        antenna_policy={"15m": 1},
        flex_antenna_policy={"bands": {"15m": {"tx": "ANT1"}}},
        now=now,
    )
    alarms = build_station_alarms(
        {
            "generated_at": path["generated_at"],
            "commissioned": False,
            "coordinator_state": "commissioning_locked",
            "recovery_required": False,
            "path": path,
        },
        elecraft_state=elecraft,
    )

    assert path["alignment"] == "confirmed"
    assert path["mismatches"] == []
    assert path["transmit_authorized"] is False
    assert alarms["active_count"] == 1
    assert alarms["counts"] == {"critical": 0, "warning": 0, "info": 1}
    assert alarms["items"][0]["code"] == "station-commissioning-required"


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
