"""Smoke tests for stable Flex TCP connection lifecycle."""

import socket
import time

import _bootstrap  # noqa: F401

from radio_control.flex_radio import FlexCtl


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


def test_idle_subscription_poll_keeps_existing_flex_socket_open():
    flex = FlexCtl("127.0.0.1", 4992)
    sock = IdleSocket()
    flex.sock = sock
    flex.last_resubscribe_time = time.time()

    assert flex.refresh_radio_state() is True
    assert flex.sock is sock
    assert sock.closed is False
    assert flex.last_state_changed == {}


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


def test_antenna_policy_falls_back_to_transmit_tx_antenna_command():
    flex = TxAntFallbackFlex()
    flex.current_rx_ant = "ANT2"
    flex.current_tx_ant = "ANT1"

    assert flex.enforce_antenna_policy(7.074, reason="test") is True

    assert "slice set 0 txant=ANT2" in flex.commands
    assert "transmit set tx_antenna=ANT2" in flex.commands
    assert flex.current_tx_ant == "ANT2"
