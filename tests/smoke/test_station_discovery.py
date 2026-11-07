import socket

import pytest

from remote_station.station_discovery import discover_stations


class DiscoverySocket:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def sendall(self, data):
        self.commands.append(data)

    def settimeout(self, value):
        assert 0 < value <= 2.5

    def recv(self, _size):
        return next(self.chunks, b"")


def test_discovers_fragmented_multiple_gui_clients_without_binding_or_writes(monkeypatch):
    connection = DiscoverySocket(
        [
            b"V1.4\nS0|client 0x1 connected client_id=one program=SmartSDR-Maestro sta",
            b"tion=Maestro\nR1|0|\nS0|client 0x2 connected client_id=two program=SmartSDR-Win station=Oliver\x7fPC\n",
            b"S0|gui_client 0x3 connected client_id=three program=AetherSDR station=AetherSDR\n",
            b"S0|client 0x4 connected program=logger\n",
        ]
    )
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kw: connection)
    stations = discover_stations("radio", 4992)
    assert [item["station_name"] for item in stations] == ["AetherSDR", "Maestro", "Oliver PC"]
    assert stations[0]["program"] == "AetherSDR"
    assert connection.commands == [b"C1|sub client all\n"]


def test_disconnect_removes_old_station_and_updates_same_handle(monkeypatch):
    connection = DiscoverySocket(
        [
            b"S0|client 1 connected client_id=a station=old\n",
            b"S0|client 1 connected client_id=a station=new\n",
            b"S0|client 2 connected client_id=b station=gone\n",
            b"S0|client 2 disconnected\n",
        ]
    )
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kw: connection)
    assert [item["station_name"] for item in discover_stations("radio", 4992)] == ["new"]


def test_empty_radio_and_subscription_rejection(monkeypatch):
    monkeypatch.setattr(
        socket, "create_connection", lambda *_args, **_kw: DiscoverySocket([b"R1|0|\n"])
    )
    assert discover_stations("radio", 4992) == []
    monkeypatch.setattr(
        socket, "create_connection", lambda *_args, **_kw: DiscoverySocket([b"R1|50000001|bad\n"])
    )
    with pytest.raises(ValueError, match="rejected"):
        discover_stations("radio", 4992)


def test_response_is_bounded(monkeypatch):
    monkeypatch.setattr(
        socket, "create_connection", lambda *_args, **_kw: DiscoverySocket([b"x" * 262145])
    )
    with pytest.raises(ValueError, match="size limit"):
        discover_stations("radio", 4992)
