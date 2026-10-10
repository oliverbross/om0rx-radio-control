"""Smoke tests for stable Flex TCP connection lifecycle."""

import socket
import time

import _bootstrap  # noqa: F401
import pytest

from radio_control import config as app_config
from radio_control.flex_radio import FlexCtl


@pytest.fixture(autouse=True)
def explicit_test_antenna_policy(monkeypatch):
    """Keep driver tests independent of live station policy and processes."""
    monkeypatch.setattr(app_config, "FLEX_ANTENNA_POLICY", FlexCtl.DEFAULT_ANTENNA_POLICY)
    monkeypatch.setattr(
        "services.digital_engine.backend_radio_control_allowed",
        lambda: True,
    )


class IdleSocket:
    def __init__(self):
        self.timeout = 1.0
        self.closed = False

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value

    def recv(self, _size):
        raise socket.timeout()

    def sendall(self, _data):
        return None

    def close(self):
        self.closed = True


class ScriptedSocket(IdleSocket):
    def __init__(self, chunks):
        super().__init__()
        self.chunks = list(chunks)

    def recv(self, _size):
        if not self.chunks:
            raise socket.timeout()
        chunk = self.chunks.pop(0)
        if isinstance(chunk, Exception):
            raise chunk
        return chunk


class RecordingScriptedSocket(ScriptedSocket):
    def __init__(self, chunks):
        super().__init__(chunks)
        self.sent = []

    def sendall(self, data):
        self.sent.append(data.decode("ascii"))


class RecordingFlex(FlexCtl):
    def __init__(self):
        super().__init__("127.0.0.1", 4992)
        self.commands = []
        self.current_mox = False
        self.current_interlock_state = "READY"

    def connect(self):
        if not self.sock:
            self.sock = IdleSocket()
        return True

    def _send(self, cmd: str) -> bool:
        self.commands.append(cmd)
        return True


class TxAntFallbackFlex(RecordingFlex):
    def _send(self, cmd: str) -> bool:
        self.commands.append(cmd)
        if " txant=" in cmd:
            return False
        return True


class SnapshotFlex(RecordingFlex):
    def _send_with_response(self, cmd: str):
        if cmd == "slice list":
            return True, "slice 0 RF_frequency=1.840000 rxant=ANT1 txant=ANT1 mode=DIGU"
        return True, ""


def test_add_spot_uses_argb_and_the_acknowledged_command_path():
    flex = RecordingFlex()

    assert flex.add_spot(
        10.116,
        "DL7PIA",
        "CW",
        "RUMlogNG Logbook",
        "OM0RX",
        "DX spot",
        lifetime=600,
        priority=2,
        color="#64D2FF",
        ts_epoch=1_791_630_000,
    ) is True

    assert flex.commands == [
        "spot add rx_freq=10.116000 callsign=DL7PIA mode=CW "
        "source=RUMlogNG\x7fLogbook spotter_callsign=OM0RX timestamp=1791630000 "
        "lifetime_seconds=600 priority=2 comment=DX\x7fspot color=#FF64D2FF"
    ]


def test_add_spot_propagates_a_radio_rejection(monkeypatch):
    flex = FlexCtl("127.0.0.1", 4992)
    monkeypatch.setattr(flex, "_send", lambda _command: False)

    assert flex.add_spot(14.025, "K1ABC", "CW", "RUMlogNG", "", "") is False


def test_idle_subscription_poll_keeps_existing_flex_socket_open():
    flex = FlexCtl("127.0.0.1", 4992)
    sock = IdleSocket()
    flex.sock = sock
    flex.last_resubscribe_time = time.time()

    assert flex.refresh_radio_state() is True
    assert flex.sock is sock
    assert sock.closed is False
    assert flex.last_state_changed == {}


def test_transmit_controls_bind_to_active_smartsdr_gui_client():
    flex = RecordingFlex()
    flex._record_basic_status_from_line(
        "S123|client 0xABC connected local_ptt=1 "
        "client_id=92377769-31EB-4483-824E-6A249E83B0A3 "
        "program=SmartSDR-Win station=OM0RX-WIN10"
    )

    assert flex.set_rf_power(90) is True
    assert flex.bound_gui_client_id == "92377769-31EB-4483-824E-6A249E83B0A3"
    assert flex.commands == [
        "sub client all",
        "client bind client_id=92377769-31EB-4483-824E-6A249E83B0A3",
        "slice set 0 tx=1",
        "transmit set rfpower=90",
    ]

    # A later MSHV/SmartSDR client transition can invalidate the radio-side
    # association even though our local flag is still true.  Every drive write
    # must establish the GUI binding again.
    flex.commands.clear()
    assert flex.set_rf_power(25) is True
    assert flex.commands == [
        "sub client all",
        "client bind client_id=92377769-31EB-4483-824E-6A249E83B0A3",
        "slice set 0 tx=1",
        "transmit set rfpower=25",
    ]


def test_preferred_maestro_station_owns_slice_a_b_and_preserves_tx_slice():
    flex = RecordingFlex()
    flex.preferred_station_name = "Maestro"
    flex._record_basic_status_from_line(
        "S123|client 0xABC connected client_id=MAESTRO-ID "
        "program=Maestro station=Maestro"
    )
    flex._record_basic_status_from_line(
        "S123|slice 0 in_use=1 RF_frequency=14.074000 client_handle=0xABC "
        "index_letter=A mode=DIGU active=1 tx=0"
    )
    flex._record_basic_status_from_line(
        "S123|slice 1 in_use=1 RF_frequency=14.080000 client_handle=0xABC "
        "index_letter=B mode=DIGU active=0 tx=1"
    )

    assert flex.bound_gui_client_id == "MAESTRO-ID"
    assert [item["index_letter"] for item in flex.get_slice_states()] == ["A", "B"]
    assert flex.current_tx_slice_id == 1
    assert flex.set_rf_power(25) is True
    assert "slice set 1 tx=1" in flex.commands
    assert "slice set 0 tx=1" not in flex.commands


def test_refresh_source_does_not_force_reconnect_on_no_messages():
    source = (  # keep this focused: a regression here causes SmartSDR client spam
        __import__("pathlib")
        .Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("radio_control", "flex_radio.py")
        .read_text(encoding="utf-8")
    )

    assert "forcing socket reconnect to refresh subscriptions" not in source
    assert "now - float(self.last_resubscribe_time or 0) > 60" in source


def test_om0rx_antenna_policy_maps_low_and_high_hf_bands():
    assert FlexCtl.desired_antennas_for_frequency(1.84)["rx"] == "ANT2"
    assert FlexCtl.desired_antennas_for_frequency(7.074)["tx"] == "ANT2"
    assert FlexCtl.desired_antennas_for_frequency(10.12)["rx"] == "ANT2"
    assert FlexCtl.desired_antennas_for_frequency(14.074)["tx"] == "ANT1"
    assert FlexCtl.desired_antennas_for_frequency(28.074)["rx"] == "ANT1"
    assert FlexCtl.desired_antennas_for_frequency(50.313) is None


def test_om0rx_antenna_policy_can_be_configured_per_band():
    policy = {
        "enabled": True,
        "bands": {
            "40m": "ANT1",
            "20m": {"rx": "ANT2", "tx": "ANT1"},
        },
    }

    assert FlexCtl.desired_antennas_for_frequency(7.074, policy) == {
        "band": "40m",
        "rx": "ANT1",
        "tx": "ANT1",
    }
    assert FlexCtl.desired_antennas_for_frequency(14.074, policy) == {
        "band": "20m",
        "rx": "ANT2",
        "tx": "ANT1",
    }
    assert FlexCtl.desired_antennas_for_frequency(7.074, {"enabled": False}) is None


def test_current_antenna_policy_is_resolved_at_each_request(monkeypatch):
    flex = RecordingFlex()
    assert flex.desired_antennas_for_current_config(1.84)["rx"] == "ANT2"

    live_policy = {
        "enabled": True,
        "bands": {band: "ANT1" for band in FlexCtl.BAND_RANGES},
    }
    monkeypatch.setattr(app_config, "FLEX_ANTENNA_POLICY", live_policy)

    assert flex.desired_antennas_for_current_config(1.84) == {
        "band": "160m",
        "rx": "ANT1",
        "tx": "ANT1",
    }


def test_tune_mhz_enforces_om0rx_antenna_policy():
    flex = RecordingFlex()
    flex.current_rx_ant = "ANT1"
    flex.current_tx_ant = "ANT1"

    assert flex.tune_mhz(7.074) is True

    assert flex.commands == [
        "slice tune 0 7.074000",
        "slice set 0 active=1",
        "slice set 0 rxant=ANT2",
        "slice set 0 txant=ANT2",
    ]
    assert flex.current_rx_ant == "ANT2"
    assert flex.current_tx_ant == "ANT2"


def test_refresh_enforces_antenna_policy_after_external_wsjtz_qsy():
    flex = RecordingFlex()
    flex.sock = ScriptedSocket(
        [
            b"S123|slice 0 RF_frequency=10.120000 rxant=ANT1 txant=ANT1 mode=DIGU\r\n",
            socket.timeout(),
        ]
    )
    flex.last_resubscribe_time = time.time()

    assert flex.refresh_radio_state() is True

    assert "slice set 0 rxant=ANT2" in flex.commands
    assert "slice set 0 txant=ANT2" in flex.commands
    assert flex.current_rx_ant == "ANT2"
    assert flex.current_tx_ant == "ANT2"


def test_antenna_policy_defers_while_transmitting_then_applies_on_receive():
    flex = RecordingFlex()
    flex.current_rx_ant = "ANT1"
    flex.current_tx_ant = "ANT1"
    flex.current_mox = True
    flex.last_tx_active_time = time.time()

    assert flex.enforce_antenna_policy(7.074, reason="test") is False
    assert flex.commands == []
    assert flex._pending_antenna_policy_freq == 7.074

    flex.current_mox = False
    assert flex.enforce_antenna_policy(flex._pending_antenna_policy_freq, reason="receive") is True

    assert "slice set 0 rxant=ANT2" in flex.commands
    assert "slice set 0 txant=ANT2" in flex.commands


def test_antenna_policy_remains_blocked_until_explicit_receive_state():
    flex = RecordingFlex()
    flex.current_rx_ant = "ANT1"
    flex.current_tx_ant = "ANT1"
    flex.current_mox = True
    flex.last_tx_active_time = time.time() - 10

    assert flex.enforce_antenna_policy(1.84, reason="stale tx") is False
    assert flex.commands == []
    assert flex._pending_antenna_policy_freq == 1.84


def test_antenna_policy_fails_closed_when_tx_state_is_unknown():
    flex = RecordingFlex()
    flex.current_mox = None
    flex.current_interlock_state = None
    flex.current_rx_ant = "ANT1"
    flex.current_tx_ant = "ANT1"

    assert flex.enforce_antenna_policy(7.074, reason="unknown tx state") is False
    assert flex.commands == []
    assert flex._pending_antenna_policy_freq == 7.074


def test_multiple_deferred_band_changes_keep_only_latest_confirmed_frequency():
    flex = RecordingFlex()
    flex.current_mox = True
    flex.current_interlock_state = "TRANSMITTING"
    flex.current_rx_ant = "ANT2"
    flex.current_tx_ant = "ANT2"

    assert flex.enforce_antenna_policy(7.074, reason="first QSY during TX") is False
    assert flex.enforce_antenna_policy(14.074, reason="latest QSY during TX") is False
    assert flex.commands == []
    assert flex._pending_antenna_policy_freq == 14.074

    flex.current_mox = False
    flex.current_interlock_state = "READY"
    assert flex.enforce_antenna_policy(
        flex._pending_antenna_policy_freq,
        reason="confirmed receive",
    ) is True

    assert "slice set 0 rxant=ANT1" in flex.commands
    assert "slice set 0 txant=ANT1" in flex.commands
    assert not any("ANT2" in command for command in flex.commands)
    assert flex._pending_antenna_policy_freq is None


def test_antenna_policy_applies_on_antenna_update_without_frequency_field():
    flex = RecordingFlex()
    flex.current_freq = 1.84
    flex.current_rx_ant = "ANT2"
    flex.current_tx_ant = "ANT2"
    flex.sock = ScriptedSocket(
        [
            b"S123|slice 0 txant=ANT1 rxant=ANT1 ant_list=ANT1,ANT2 tx_ant_list=ANT1,ANT2\r\n",
            socket.timeout(),
        ]
    )
    flex.last_resubscribe_time = time.time()

    assert flex.refresh_radio_state() is True

    assert "slice set 0 rxant=ANT2" in flex.commands
    assert "slice set 0 txant=ANT2" in flex.commands


def test_pending_antenna_policy_retries_on_receive_poll_without_tx_update():
    flex = RecordingFlex()
    flex.current_rx_ant = "ANT1"
    flex.current_tx_ant = "ANT1"
    flex.current_mox = True
    flex.last_tx_active_time = time.time()

    assert flex.enforce_antenna_policy(1.84, reason="recent tx") is False
    assert flex.commands == []

    flex.current_mox = False
    flex.sock = ScriptedSocket([socket.timeout()])
    flex.last_resubscribe_time = time.time()

    assert flex.refresh_radio_state() is True

    assert "slice set 0 rxant=ANT2" in flex.commands
    assert "slice set 0 txant=ANT2" in flex.commands
    assert flex._pending_antenna_policy_freq is None


def test_refresh_parses_coalesced_interlock_records_in_order():
    flex = RecordingFlex()
    flex.current_mox = False
    flex.sock = ScriptedSocket([
        (
            b"S1|interlock state=PTT_REQUESTED\r\n"
            b"S1|interlock state=TRANSMITTING\r\n"
            b"S1|interlock state=UNKEY_REQUESTED\r\n"
            b"S1|interlock state=READY\r\n"
        ),
        socket.timeout(),
    ])
    flex.last_resubscribe_time = time.time()

    assert flex.refresh_radio_state() is True
    assert flex.current_interlock_state == "READY"
    assert flex.current_mox is False
    assert flex.last_state_changed["interlock_state"] == "READY"
    assert flex.last_tx_state_time > 0


def test_refresh_ignores_saved_band_power_rows_for_live_drive():
    flex = RecordingFlex()
    flex.current_rfpower = 25
    flex.sock = ScriptedSocket(
        [
            b"S1|transmit freq=1.840000 rfpower=90 tunepower=20\r\n"
            b"S1|transmit band 0 band_name=160 rfpower=90 tunepower=20\r\n"
            b"S1|transmit band 20 band_name=6 rfpower=0 tunepower=0\r\n"
        ]
    )
    flex.last_resubscribe_time = time.time()

    assert flex.refresh_radio_state() is True
    assert flex.current_rfpower == 90
    assert flex.last_state_changed["drive"] == 90


def test_fresh_tx_state_requires_post_subscription_observation(monkeypatch):
    flex = RecordingFlex()
    probe = RecordingFlex()
    probe.last_tx_state_time = 1
    monkeypatch.setattr(
        probe,
        "connect_tx_state_probe",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(flex, "_new_tx_state_probe", lambda: probe)

    stale = flex.get_fresh_tx_state(timeout=0.01)

    assert stale["confirmed"] is False
    assert probe.sock is None


def test_fresh_tx_state_accepts_new_ready_subscription_status(monkeypatch):
    flex = RecordingFlex()
    probe = RecordingFlex()

    def connect_tx_state_probe(*_args, **_kwargs):
        probe.current_mox = False
        probe.current_interlock_state = "READY"
        probe.last_tx_state_time = time.time()
        return True

    monkeypatch.setattr(probe, "connect_tx_state_probe", connect_tx_state_probe)
    monkeypatch.setattr(flex, "_new_tx_state_probe", lambda: probe)

    fresh = flex.get_fresh_tx_state(timeout=0.01)

    assert fresh["confirmed"] is True
    assert fresh["mox"] is False
    assert fresh["interlock_state"] == "READY"
    assert probe.sock is None


def test_minimal_tx_probe_subscribes_only_to_tx_and_requires_ack_and_status(monkeypatch):
    flex = FlexCtl("127.0.0.1", 4992)
    sock = ScriptedSocket(
        [
            b"V3.4.24.33766\r\nH12345678\r\n",
            b"R1001|00000000|\r\nS0|interlock state=READY tx_allowed=1\r\n",
        ]
    )
    monkeypatch.setattr(flex._socket_mod, "create_connection", lambda *_args, **_kwargs: sock)
    requested_at = time.time()

    assert flex.connect_tx_state_probe(0.5, requested_at=requested_at) is True
    assert sock.closed is False
    assert flex.current_mox is False
    assert flex.current_interlock_state == "READY"
    assert flex.last_tx_state_time >= requested_at


def test_minimal_tx_probe_fails_closed_without_fresh_interlock_status(monkeypatch):
    flex = FlexCtl("127.0.0.1", 4992)
    sock = ScriptedSocket(
        [
            b"V3.4.24.33766\r\n",
            b"R1001|00000000|\r\n",
            socket.timeout(),
        ]
    )
    monkeypatch.setattr(flex._socket_mod, "create_connection", lambda *_args, **_kwargs: sock)

    assert flex.connect_tx_state_probe(0.01, requested_at=time.time()) is False
    assert flex.current_interlock_state is None
    assert flex.current_mox is None


def test_persistent_tx_monitor_reuses_one_connection_for_multiple_proofs(monkeypatch):
    flex = FlexCtl("127.0.0.1", 4992)
    sock = RecordingScriptedSocket(
        [
            b"V3.4.24.33766\r\nH12345678\r\n",
            b"R1001|00000000|\r\nS0|interlock state=READY tx_allowed=1\r\n",
            b"R1002|00000000|\r\n",
            b"R1003|00000000|\r\nS0|interlock state=TRANSMITTING\r\n",
        ]
    )
    connection_count = 0

    def create_connection(*_args, **_kwargs):
        nonlocal connection_count
        connection_count += 1
        return sock

    monkeypatch.setattr(flex._socket_mod, "create_connection", create_connection)
    assert flex.connect_tx_state_probe(0.5, requested_at=time.time()) is True
    existing_timeout = sock.gettimeout()
    receive = flex.refresh_tx_state_probe(0.5, expect_transmitting=False)
    transmit = flex.refresh_tx_state_probe(0.5, expect_transmitting=True)

    assert connection_count == 1
    assert receive["confirmed"] is True
    assert receive["mox"] is False
    assert transmit["confirmed"] is True
    assert transmit["mox"] is True
    assert len([wire for wire in sock.sent if "sub tx all" in wire]) == 3
    assert sock.gettimeout() == existing_timeout


def test_refresh_radio_state_has_bounded_drain_under_continuous_status():
    flex = RecordingFlex()
    chunks = [b"S1|meter 24 value=12.0\r\n" for _ in range(1000)]
    sock = ScriptedSocket(chunks)
    flex.sock = sock
    flex.last_resubscribe_time = time.time()

    started = time.monotonic()
    assert flex.refresh_radio_state() is True
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert sock.chunks


def test_refresh_preserves_fragmented_interlock_record_across_polls():
    flex = RecordingFlex()
    flex.sock = ScriptedSocket([b"S1|interlock state=TRANSM", socket.timeout()])
    flex.last_resubscribe_time = time.time()

    assert flex.refresh_radio_state() is True
    assert flex.current_interlock_state == "READY"

    flex.sock = ScriptedSocket([b"ITTING\r\n", socket.timeout()])
    assert flex.refresh_radio_state() is True
    assert flex.current_interlock_state == "TRANSMITTING"
    assert flex.current_mox is True


def test_snapshot_status_poll_enforces_antenna_policy_on_current_band():
    flex = SnapshotFlex()
    flex.sock = ScriptedSocket([socket.timeout()])

    levels = flex.get_current_levels(timeout=0.05)

    assert levels["freq"] == 1.84
    assert "slice set 0 rxant=ANT2" in flex.commands
    assert "slice set 0 txant=ANT2" in flex.commands
    assert flex.current_rx_ant == "ANT2"
    assert flex.current_tx_ant == "ANT2"


def test_snapshot_poll_reuses_recent_flex_subscriptions():
    flex = SnapshotFlex()
    sock = RecordingScriptedSocket([TimeoutError()])
    flex.sock = sock
    flex.last_resubscribe_time = time.time()

    flex.get_current_levels(timeout=0.01, apply_antenna_policy=False)

    assert not any("sub slice all" in wire or "sub tx all" in wire for wire in sock.sent)


def test_antenna_policy_falls_back_to_transmit_tx_antenna_command():
    flex = TxAntFallbackFlex()
    flex.current_rx_ant = "ANT2"
    flex.current_tx_ant = "ANT1"

    assert flex.enforce_antenna_policy(7.074, reason="test") is True

    assert "slice set 0 txant=ANT2" in flex.commands
    assert "transmit set tx_antenna=ANT2" in flex.commands
    assert flex.current_tx_ant == "ANT2"
