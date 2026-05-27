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

    def close(self):
        self.closed = True


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
