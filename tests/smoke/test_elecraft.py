"""Smoke tests for the KPA500/KAT500 integration."""

import asyncio
import threading
import time

import _bootstrap  # noqa: F401
import pytest
from fastapi import HTTPException

from backend.api import elecraft as elecraft_api
from radio_control import elecraft as elecraft_module
from radio_control.elecraft import (
    ElecraftManager,
    KAT500,
    KPA500,
    band_from_frequency,
    build_station_path,
)


class FakeSerial:
    def __init__(self, responses=None, **_kwargs):
        self.responses = responses or {}
        self.writes = []
        self.pending = b""
        self.is_open = True

    @property
    def in_waiting(self):
        return len(self.pending)

    def write(self, payload):
        text = payload.decode("ascii")
        self.writes.append(text)
        response = self.responses.get(text)
        if response:
            self.pending += response.encode("ascii")
        return len(payload)

    def read(self, size=1):
        if not self.pending:
            return b""
        chunk, self.pending = self.pending[:size], self.pending[size:]
        return chunk

    def flush(self):
        return None

    def close(self):
        self.is_open = False


class FlushWouldBlockSerial(FakeSerial):
    """Model the Windows/VSPE failure where FlushFileBuffers never returns."""

    @property
    def out_waiting(self):
        return 0

    def flush(self):
        raise AssertionError("serial.flush() must not be used for command delivery")


def serial_factory_with(responses, holder):
    def factory(**kwargs):
        instance = FakeSerial(responses, **kwargs)
        holder.append(instance)
        return instance

    return factory


def test_serial_commands_do_not_use_unbounded_windows_flush():
    serial_port = FlushWouldBlockSerial({"^ON;": "^ON1;"})
    device = KPA500(
        "KPA500",
        "COM17",
        38400,
        serial_factory=lambda **_kwargs: serial_port,
    )

    assert device.query("^ON;", "^ON", response_pattern=r"\^ON[01];") == "^ON1;"
    assert device.write("^OS0;") is True
    assert serial_port.writes == ["^ON;", "^OS0;"]


def test_serial_output_queue_timeout_fails_closed_without_hanging():
    class StalledOutputSerial(FakeSerial):
        @property
        def out_waiting(self):
            return 4

    serial_port = StalledOutputSerial()
    device = KPA500(
        "KPA500",
        "COM17",
        38400,
        timeout=0.03,
        serial_factory=lambda **_kwargs: serial_port,
    )
    started = time.monotonic()

    assert device.query("^ON;", "^ON") is None

    assert time.monotonic() - started < 0.25
    assert "did not drain" in str(device.last_error)
    assert serial_port.is_open is False


def test_frequency_to_elecraft_band_codes_cover_hf_and_6m():
    assert band_from_frequency(1.84) == "160m"
    assert band_from_frequency(10.136) == "30m"
    assert band_from_frequency(14.074) == "20m"
    assert band_from_frequency(50.313) == "6m"
    assert band_from_frequency(144.2) is None


def test_station_path_keeps_flex_and_kat_antenna_stages_distinct():
    now = 1_800_000_000.0
    path = build_station_path(
        {
            "updated_at": now,
            "radio_band": "40m",
            "kpa500": {
                "enabled": True,
                "connected": True,
                "responsive": True,
                "observed_at": now,
                "power": True,
                "operate": True,
                "band": "40m",
                "fault": "00",
            },
            "kat500": {
                "enabled": True,
                "connected": True,
                "responsive": True,
                "observed_at": now,
                "power": True,
                "mode": "auto",
                "band": "40m",
                "frequency_khz": 7074,
                "antenna": 2,
                "tuning": False,
                "fault": "0",
                "bypass": False,
            },
        },
        {
            "connected": True,
            "known": True,
            "stale": False,
            "observed_at": now,
            "frequency": 7.074,
            "mode": "DIGU",
            "tx_ant": "ANT1",
            "mox": False,
        },
        antenna_policy={"40m": 2},
        antenna_names={"2": "40 m dipole"},
        flex_antenna_policy={"bands": {"40m": "ANT1"}},
        now=now,
    )

    assert path["alignment"] == "confirmed"
    assert path["state"] == "ready"
    assert path["route_label"] == "FLEX ANT1 → KPA500 → KAT500 → 40 m dipole"
    assert path["antenna"] == {
        "number": 2,
        "name": "40 m dipole",
        "label": "40 m dipole",
        "expected": 2,
        "observed": 2,
    }
    assert path["transmit_authorized"] is False


def test_station_path_reports_mismatch_and_stale_evidence_without_authorizing_tx():
    now = 1_800_000_100.0
    path = build_station_path(
        {
            "updated_at": now,
            "radio_band": "40m",
            "kpa500": {
                "enabled": True,
                "connected": True,
                "responsive": True,
                "observed_at": now - 30,
                "band": "20m",
                "fault": "00",
            },
            "kat500": {
                "enabled": True,
                "connected": True,
                "responsive": True,
                "observed_at": now,
                "power": True,
                "mode": "auto",
                "band": "40m",
                "frequency_khz": 7074,
                "antenna": 1,
                "tuning": False,
                "fault": "0",
                "bypass": False,
            },
        },
        {
            "connected": True,
            "known": True,
            "observed_at": now,
            "frequency": 7.074,
            "mode": "DIGU",
            "tx_ant": "ANT1",
        },
        antenna_policy={"40m": 2},
        now=now,
    )

    assert path["state"] == "fault"
    assert path["alignment"] == "mismatch"
    assert {issue["code"] for issue in path["mismatches"]} == {"kat-antenna-mismatch"}
    assert "KPA500 status is stale" in path["unknown_reasons"]
    assert path["transmit_authorized"] is False


def test_station_path_rejects_wrong_flex_port_kat_frequency_fault_bypass_and_tx():
    now = 1_800_000_200.0
    path = build_station_path(
        {
            "updated_at": now,
            "radio_band": "20m",
            "kpa500": {
                "enabled": True,
                "connected": True,
                "responsive": True,
                "observed_at": now,
                "power": True,
                "operate": False,
                "band": "20m",
                "fault": "00",
            },
            "kat500": {
                "enabled": True,
                "connected": True,
                "responsive": True,
                "observed_at": now,
                "power": True,
                "mode": "bypass",
                "band": "20m",
                "frequency_khz": 7000,
                "antenna": 1,
                "tuning": False,
                "fault": "3",
                "bypass": True,
            },
        },
        {
            "connected": True,
            "known": True,
            "stale": False,
            "observed_at": now,
            "frequency": 14.074,
            "mode": "DIGU",
            "tx_ant": "ANT2",
            "mox": False,
            "interlock_state": "TRANSMITTING",
        },
        antenna_policy={"20m": 1},
        flex_antenna_policy={"bands": {"20m": "ANT1"}},
        now=now,
    )

    codes = {item["code"] for item in path["mismatches"]}
    assert path["alignment"] != "confirmed"
    assert "flex-tx-port-mismatch" in codes
    assert "kat-fault" in codes
    assert "FLEX transmitter is active; route changes are inhibited" in path["unknown_reasons"]


def test_control_disabled_observes_flex_without_writing_elecraft_devices():
    kpa_serials = []
    kat_serials = []
    manager = ElecraftManager(
        kpa500=KPA500("KPA500", "COM6", 38400, serial_factory=serial_factory_with({}, kpa_serials)),
        kat500=KAT500("KAT500", "COM11", 38400, serial_factory=serial_factory_with({}, kat_serials)),
        follow_radio=True,
        control_enabled=False,
    )

    asyncio.run(manager.sync_radio_state(7.074, "DIGU"))

    assert manager.last_frequency == 7.074
    assert manager.last_band == "40m"
    assert kpa_serials == []
    assert kat_serials == []
    manager._executor.shutdown(wait=True)


@pytest.mark.parametrize(
    ("frequency", "expected"),
    [
        (None, None),
        (1.8, "160m"),
        (2.0, "160m"),
        (2.001, None),
        (14.35, "20m"),
        (54.0, "6m"),
        (54.001, None),
    ],
)
def test_frequency_band_boundaries_are_inclusive(frequency, expected):
    assert band_from_frequency(frequency) == expected


def test_query_discards_stale_frames_and_skips_echoes_and_malformed_replies():
    serials = []
    device = KPA500(
        "KPA500",
        "COM6",
        38400,
        serial_factory=serial_factory_with(
            {"^OS;": "^OS;garbage;^BN05;^OS0;"},
            serials,
        ),
    )
    assert device.open() is True
    serials[0].pending = b"^OS1;"
    before = time.time()

    response = device.query("^OS;", "^OS", response_pattern=r"\^OS[01];")

    assert response == "^OS0;"
    assert serials[0].writes == ["^OS;"]
    assert device.last_error is None
    assert device.last_seen is not None
    assert device.last_seen >= before


def test_kpa500_commands_and_status_parsing():
    serials = []
    device = KPA500(
        "KPA500",
        "COM6",
        38400,
        serial_factory=serial_factory_with(
            {
                "^ON;": "^ON1;",
                "^OS;": "^OS;^OS1;",
                "^BN;": "^BN05;",
                "^FL;": "^FL00;",
                "^TM;": "^TM042;",
                "^VI;": "^VI500 025;",
                "^WS;": "^WS475 015;",
                "^RVM;": "^RVM01.23;",
            },
            serials,
        ),
    )

    assert device.set_band("20m") is True
    assert device.set_operate(False) is True
    assert device.clear_fault() is True
    status = device.status()

    assert serials[0].writes[:3] == ["^BN05;", "^OS0;", "^FLC;"]
    assert status["power"] is True
    assert status["operate"] is True
    assert status["band"] == "20m"
    assert status["output_power_w"] == 475
    assert status["swr"] == 1.5
    assert status["voltage"] == 50.0
    assert status["current"] == 2.5
    assert status["temperature_c"] == 42
    assert status["fault"] == "00"
    assert status["firmware"] == "01.23"
    assert status["_interrupted"] is False
    assert status["error"] is None


def test_kpa500_transient_explicit_off_response_does_not_publish_stale_telemetry():
    serials = []
    device = KPA500(
        "KPA500",
        "COM6",
        38400,
        serial_factory=serial_factory_with({"^ON;": "^ON0;"}, serials),
        timeout=0.001,
    )

    status = device.status()

    assert status["connected"] is True
    assert status["responsive"] is True
    assert status["power"] is False
    assert status["operate"] is False
    assert status["quality"] == "good"
    assert status["missing_fields"] == []
    assert status["error"] is None
    assert serials[0].writes == ["^ON;"]


def test_kpa500_powered_off_no_response_remains_unknown_not_confirmed_off():
    serials = []
    device = KPA500(
        "KPA500",
        "COM6",
        38400,
        serial_factory=serial_factory_with({}, serials),
        timeout=0.001,
    )

    status = device.status()

    assert status["connected"] is True
    assert status["responsive"] is False
    assert status["power"] is None
    assert status["quality"] == "unknown"
    assert status["missing_fields"] == ["power"]
    assert serials[0].writes == ["^ON;"]


def test_kat500_commands_and_status_parsing():
    serials = []
    device = KAT500(
        "KAT500",
        "COM11",
        38400,
        serial_factory=serial_factory_with(
            {
                "PS;": "PS1;",
                "MD;": "MDA;",
                "AN;": "AN2;",
                "BN;": "BN04;",
                "F;": "F 10136;",
                "VFWD;": "VFWD 2048;",
                "VRFL;": "VRFL 128;",
                "VSWR;": "VSWR 1.27;",
                "TP;": "TP;TP0;",
                "FLT;": "FLT0;",
                "BYP;": "BYPN;",
                "AMPI;": "AMPI0;",
                "RV;": "RV02.12;",
            },
            serials,
        ),
    )

    assert device.set_frequency(10.136) is True
    assert device.set_antenna(2) is True
    assert device.set_mode("manual") is True
    status = device.status()

    assert serials[0].writes[:3] == ["F 10136;", "AN2;", "MDM;"]
    assert status["connected"] is True
    assert status["mode"] == "auto"
    assert status["antenna"] == 2
    assert status["band"] == "30m"
    assert status["frequency_khz"] == 10136
    assert status["forward_adc"] == 2048
    assert status["reflected_adc"] == 128
    assert status["swr"] == 1.27
    assert status["swr_live"] is True
    assert status["swr_observed_at"] is not None
    assert status["tuning"] is False
    assert status["fault"] == "0"
    assert status["bypass"] is False
    assert status["amp_key_interrupted"] is False
    assert status["power"] is True
    assert status["firmware"] == "02.12"
    assert status["_interrupted"] is False
    assert status["error"] is None


def test_manager_follows_flex_with_band_frequency_and_antenna_not_radio_mode():
    kpa_serials = []
    kat_serials = []
    manager = ElecraftManager(
        kpa500=KPA500("KPA500", "COM6", 38400, serial_factory=serial_factory_with({}, kpa_serials)),
        kat500=KAT500("KAT500", "COM11", 38400, serial_factory=serial_factory_with({}, kat_serials)),
        follow_radio=True,
        control_enabled=True,
    )
    manager._status = {
        "kpa500": {"band": "30m"},
        "kat500": {"band": "30m", "frequency_khz": 10120, "antenna": 2},
    }

    asyncio.run(manager.sync_radio_state(14.074, "DIGU"))

    assert kpa_serials[0].writes == ["^BN05;"]
    assert kat_serials[0].writes == ["BN05;", "F 14074;", "AN1;"]
    assert all(not command.startswith("MD") for command in kat_serials[0].writes)
    assert manager.last_radio_mode == "DIGU"
    assert manager.snapshot()["kpa500"]["band"] == "20m"
    assert manager.snapshot()["kat500"] == {
        "band": "20m",
        "frequency_khz": 14074,
        "antenna": 1,
    }


def test_manager_retries_device_band_after_a_failed_write():
    class FlakyKPA:
        def __init__(self):
            self.attempts = 0

        def set_band(self, _band):
            self.attempts += 1
            return self.attempts > 1

    kpa = FlakyKPA()
    manager = ElecraftManager(kpa500=kpa, follow_radio=True, control_enabled=True)

    asyncio.run(manager.sync_radio_state(14.074, "DIGU"))
    asyncio.run(manager.sync_radio_state(14.074, "DIGU"))

    assert kpa.attempts == 2
    assert manager.last_kpa_band == "20m"


def test_manager_follow_is_idempotent_and_only_resends_material_frequency_changes():
    kpa_serials = []
    kat_serials = []
    manager = ElecraftManager(
        kpa500=KPA500("KPA500", "COM6", 38400, serial_factory=serial_factory_with({}, kpa_serials)),
        kat500=KAT500("KAT500", "COM11", 38400, serial_factory=serial_factory_with({}, kat_serials)),
        follow_radio=True,
        control_enabled=True,
    )

    asyncio.run(manager.sync_radio_state(14.074, "DIGU"))
    first_kpa_writes = list(kpa_serials[0].writes)
    first_kat_writes = list(kat_serials[0].writes)
    asyncio.run(manager.sync_radio_state(14.074, "USB"))
    asyncio.run(manager.sync_radio_state(14.0745, "USB"))

    assert kpa_serials[0].writes == first_kpa_writes
    assert kat_serials[0].writes == first_kat_writes
    assert manager.last_radio_mode == "USB"
    assert manager.last_frequency == 14.0745

    asyncio.run(manager.sync_radio_state(14.0751, "USB"))

    assert kpa_serials[0].writes == ["^BN05;"]
    assert kat_serials[0].writes == ["BN05;", "F 14074;", "AN1;", "F 14075;"]
    manager._executor.shutdown(wait=True)


@pytest.mark.parametrize("frequency", [None, 144.2])
def test_manager_does_not_follow_missing_or_out_of_band_radio_state(frequency):
    class RecordingDevice:
        def __init__(self):
            self.bands = []

        def set_band(self, band):
            self.bands.append(band)
            return True

    device = RecordingDevice()
    manager = ElecraftManager(kpa500=device, follow_radio=True)

    asyncio.run(manager.sync_radio_state(frequency, "DIGU"))

    assert device.bands == []
    assert manager.last_frequency is None
    assert manager.last_band is None
    manager._executor.shutdown(wait=True)


def test_manager_does_not_follow_when_follow_radio_is_disabled():
    class RecordingDevice:
        def __init__(self):
            self.bands = []

        def set_band(self, band):
            self.bands.append(band)
            return True

    device = RecordingDevice()
    manager = ElecraftManager(kpa500=device, follow_radio=False)

    asyncio.run(manager.sync_radio_state(14.074, "DIGU"))

    assert device.bands == []
    assert manager.last_frequency is None
    manager._executor.shutdown(wait=True)


def test_disconnect_closes_ports_clears_cached_status_and_requires_explicit_reconnect():
    serials = []
    device = KPA500(
        "KPA500",
        "COM6",
        38400,
        serial_factory=serial_factory_with({}, serials),
    )
    manager = ElecraftManager(kpa500=device)
    manager._status = {"updated_at": 123.0, "kpa500": {"power": True}}

    asyncio.run(manager.connect())
    status = asyncio.run(manager.disconnect())

    assert serials[0].is_open is False
    assert status["kpa500"] == {"enabled": True, "connected": False, "port": "COM6"}
    assert "updated_at" not in status
    assert device.write("^OS0;") is False
    assert device.last_error == "KPA500 connection is disabled"
    assert len(serials) == 1

    asyncio.run(manager.connect())
    assert len(serials) == 2
    assert device.connected is True
    asyncio.run(manager.disconnect())
    manager._executor.shutdown(wait=True)


def test_maintenance_lifecycle_stops_polling_releases_and_reidentifies_ports():
    kpa_serials = []
    kat_serials = []
    manager = ElecraftManager(
        kpa500=KPA500(
            "KPA500",
            "COM6",
            38400,
            serial_factory=serial_factory_with({"^RVM;": "^RVM01.54;"}, kpa_serials),
        ),
        kat500=KAT500(
            "KAT500",
            "COM11",
            38400,
            serial_factory=serial_factory_with({"I;": "KAT500;"}, kat_serials),
        ),
    )

    async def exercise():
        await manager.connect()
        old_poll = asyncio.create_task(asyncio.sleep(60))
        manager._poll_task = old_poll

        suspended = await manager.suspend_for_maintenance()
        assert old_poll.cancelled()
        assert manager._poll_task is None
        assert suspended["maintenance_suspended"] is True
        assert kpa_serials[0].is_open is False
        assert kat_serials[0].is_open is False

        await manager.reopen_for_maintenance_exit()
        assert kpa_serials[1].writes == ["^RVM;"]
        assert kat_serials[1].writes == [";;;", "I;"]
        assert manager._poll_task is None
        await manager.refresh_status()
        assert kpa_serials[1].writes == ["^RVM;"]
        assert kat_serials[1].writes == [";;;", "I;"]

        resumed = await manager.complete_maintenance_exit()
        assert resumed["maintenance_suspended"] is False
        assert manager._poll_task is not None
        await manager.stop()

    asyncio.run(exercise())
    manager._executor.shutdown(wait=True)


def test_reconfigure_is_blocked_while_manager_is_suspended_for_maintenance():
    manager = ElecraftManager()
    manager._maintenance_suspended = True

    with pytest.raises(RuntimeError, match="blocked during maintenance"):
        asyncio.run(manager.reconfigure())

    manager._executor.shutdown(wait=True)


def test_serial_write_error_closes_port_and_reports_actionable_permission_message():
    class PermissionDeniedSerial(FakeSerial):
        def write(self, _payload):
            raise PermissionError("Access is denied")

    serials = []

    def factory(**kwargs):
        instance = PermissionDeniedSerial(**kwargs)
        serials.append(instance)
        return instance

    device = KPA500("KPA500", "COM6", 38400, serial_factory=factory)

    assert device.set_operate(False) is False
    assert device.connected is False
    assert serials[0].is_open is False
    assert device.last_error == "COM6 is busy or access was denied (check VSPE/Elecraft Remote)"


def test_unconfigured_serial_port_returns_disconnected_status_without_opening():
    factory_calls = []
    device = KAT500(
        "KAT500",
        "",
        38400,
        serial_factory=lambda **kwargs: factory_calls.append(kwargs),
    )

    status = device.status()

    assert status["connected"] is False
    assert status["error"] == "KAT500 serial port is not configured"
    assert factory_calls == []


def test_overlapping_status_refreshes_share_one_hardware_pass():
    class SlowStatusDevice:
        connected = True
        port = "COM16"

        def __init__(self):
            self.calls = 0

        def status(self, _stop_event):
            self.calls += 1
            time.sleep(0.05)
            return {"enabled": True, "connected": True, "port": self.port}

    device = SlowStatusDevice()
    manager = ElecraftManager(kpa500=device)

    async def exercise():
        first, second = await asyncio.gather(manager.refresh_status(), manager.refresh_status())
        assert first == second

    asyncio.run(exercise())
    manager._executor.shutdown(wait=True)
    assert device.calls == 1


def test_route_status_queries_only_exact_route_fields():
    kpa_serials = []
    kat_serials = []
    kpa = KPA500(
        "KPA500",
        "COM6",
        38400,
        serial_factory=serial_factory_with(
            {"^OS;": "^OS0;", "^BN;": "^BN05;"}, kpa_serials
        ),
    )
    kat = KAT500(
        "KAT500",
        "COM11",
        38400,
        serial_factory=serial_factory_with(
            {"AN;": "AN2;", "BN;": "BN05;", "F;": "F 14074;"}, kat_serials
        ),
    )

    kpa_status = kpa.route_status()
    kat_status = kat.route_status()

    assert kpa_status["route_complete"] is True
    assert kpa_status["operate"] is False
    assert kpa_status["band"] == "20m"
    assert kpa_serials[0].writes == ["^OS;", "^BN;"]
    assert kat_status["route_complete"] is True
    assert kat_status["antenna"] == 2
    assert kat_status["band"] == "20m"
    assert kat_status["frequency_khz"] == 14074
    assert kat_serials[0].writes == [";;;", "AN;", "BN;", "F;"]


def test_manager_route_refresh_merges_only_fresh_route_proofs():
    class RouteDevice:
        connected = True
        io_enabled = True

        def __init__(self, result):
            self.result = result
            self.calls = 0

        def route_status(self):
            self.calls += 1
            return dict(self.result)

    kpa = RouteDevice(
        {"operate": False, "band": "40m", "route_complete": True, "observed_at": 10.0}
    )
    kat = RouteDevice(
        {
            "antenna": 2,
            "band": "40m",
            "frequency_khz": 7074,
            "route_complete": True,
            "observed_at": 11.0,
        }
    )
    manager = ElecraftManager(kpa500=kpa, kat500=kat)
    manager._status = {
        "kpa500": {"temperature_c": 33},
        "kat500": {"mode": "auto"},
    }

    status = asyncio.run(manager.refresh_route_status())

    assert kpa.calls == 1
    assert kat.calls == 1
    assert status["kpa500"]["temperature_c"] == 33
    assert status["kpa500"]["operate"] is False
    assert status["kpa500"]["band"] == "40m"
    assert status["kat500"]["mode"] == "auto"
    assert status["kat500"]["frequency_khz"] == 7074
    assert manager.last_kpa_band == "40m"
    assert manager.last_kat_band == "40m"
    assert manager.last_kat_frequency == 7.074
    manager._executor.shutdown(wait=True)


def test_fast_meter_refresh_does_not_advance_critical_status_freshness():
    kpa_serials = []
    kat_serials = []
    kpa = KPA500(
        "KPA500",
        "COM6",
        38400,
        serial_factory=serial_factory_with({"^WS;": "^WS023 014;"}, kpa_serials),
    )
    kat = KAT500(
        "KAT500",
        "COM11",
        38400,
        serial_factory=serial_factory_with(
            {
                "VFWD;": "VFWD 1024;",
                "VRFL;": "VRFL 64;",
                "VSWR;": "VSWR 1.31;",
            },
            kat_serials,
        ),
    )
    manager = ElecraftManager(kpa500=kpa, kat500=kat)
    manager._status = {
        "updated_at": 100.0,
        "kpa500": {"enabled": True, "connected": True, "observed_at": 90.0},
        "kat500": {"enabled": True, "connected": True, "observed_at": 91.0},
    }

    status = asyncio.run(manager.refresh_meters())

    assert status["updated_at"] == 100.0
    assert status["kpa500"]["observed_at"] == 90.0
    assert status["kat500"]["observed_at"] == 91.0
    assert kpa.last_seen is None
    assert kat.last_seen is None
    assert status["kpa500"]["output_power_w"] == 23
    assert status["kpa500"]["swr"] == 1.4
    assert status["kat500"]["swr"] == 1.31
    assert status["kat500"]["swr_live"] is True
    assert status["kat500"]["swr_valid"] is True
    manager._executor.shutdown(wait=True)


def test_kat_meter_retains_last_rf_qualified_swr_after_return_to_receive():
    class MeterKAT:
        connected = True
        io_enabled = True
        port = "COM11"

        def __init__(self):
            self.samples = iter(
                (
                    {
                        "forward_adc": 900,
                        "reflected_adc": 50,
                        "swr_sample": 1.22,
                        "swr": 1.22,
                        "swr_live": True,
                        "swr_observed_at": 200.0,
                        "meter_observed_at": 200.0,
                        "meter_complete": True,
                    },
                    {
                        "forward_adc": 0,
                        "reflected_adc": 0,
                        "swr_sample": 0.0,
                        "swr_live": False,
                        "meter_observed_at": 201.0,
                        "meter_complete": True,
                    },
                )
            )

        def meter_status(self):
            return next(self.samples)

    manager = ElecraftManager(kat500=MeterKAT())
    manager._status = {
        "updated_at": 100.0,
        "kpa500": {"enabled": False, "connected": False},
        "kat500": {"enabled": True, "connected": True, "observed_at": 99.0},
    }

    live = asyncio.run(manager.refresh_meters())
    idle = asyncio.run(manager.refresh_meters())

    assert live["kat500"]["swr"] == 1.22
    assert live["kat500"]["swr_live"] is True
    assert idle["kat500"]["swr"] == 1.22
    assert idle["kat500"]["swr_observed_at"] == 200.0
    assert idle["kat500"]["swr_sample"] == 0.0
    assert idle["kat500"]["swr_live"] is False
    assert idle["kat500"]["swr_valid"] is True
    assert idle["kat500"]["meter_observed_at"] == 201.0
    manager._executor.shutdown(wait=True)


def test_unchanged_radio_observation_does_not_interrupt_status_telemetry():
    class StatusDevice:
        connected = True
        port = "COM16"

        def __init__(self):
            self.stop_was_set = None
            self.bands = []

        def status(self, stop_event):
            time.sleep(0.02)
            self.stop_was_set = stop_event.is_set()
            return {
                "enabled": True,
                "connected": True,
                "port": self.port,
                "_interrupted": self.stop_was_set,
            }

        def set_band(self, band):
            self.bands.append(band)
            return True

    device = StatusDevice()
    manager = ElecraftManager(kpa500=device, control_enabled=True)
    manager.last_kpa_band = "20m"
    manager.last_band = "20m"
    manager.last_frequency = 14.074

    async def exercise():
        refresh = asyncio.create_task(manager.refresh_status())
        await asyncio.sleep(0)
        await manager.sync_radio_state(14.074, "DIGU")
        return await refresh

    status = asyncio.run(exercise())

    assert device.stop_was_set is False
    assert device.bands == []
    assert status["updated_at"] > 0
    manager._executor.shutdown(wait=True)


def test_refresh_timestamp_changes_only_after_a_completed_hardware_pass(monkeypatch):
    class StatusDevice:
        connected = True
        port = "COM16"

        def status(self, _stop_event):
            return {
                "enabled": True,
                "connected": True,
                "port": self.port,
                "power": True,
                "_interrupted": False,
            }

    timestamps = iter((100.0, 200.0))
    monkeypatch.setattr(elecraft_module.time, "time", lambda: next(timestamps))
    monkeypatch.setattr(elecraft_module.config, "KPA500_ENABLED", True)
    monkeypatch.setattr(elecraft_module.config, "KAT500_ENABLED", False)
    manager = ElecraftManager(kpa500=StatusDevice())

    first = asyncio.run(manager.refresh_status())
    cached = manager.snapshot()
    second = asyncio.run(manager.refresh_status())

    assert first["updated_at"] == 100.0
    assert cached["updated_at"] == 100.0
    assert second["updated_at"] == 200.0
    assert first["kpa500"] == {
        "enabled": True,
        "connected": True,
        "port": "COM16",
        "power": True,
    }
    assert first["kat500"]["enabled"] is False
    assert "_interrupted" not in first["kpa500"]
    manager._executor.shutdown(wait=True)


def test_interrupted_refresh_preserves_last_completed_status_and_freshness():
    class InterruptedDevice:
        connected = True
        port = "COM16"

        def status(self, _stop_event):
            return {
                "enabled": True,
                "connected": True,
                "port": self.port,
                "power": False,
                "_interrupted": True,
            }

    manager = ElecraftManager(kpa500=InterruptedDevice())
    manager._status = {
        "following_radio": True,
        "radio_frequency": 14.074,
        "radio_mode": "DIGU",
        "radio_band": "20m",
        "kpa500": {"enabled": True, "connected": True, "port": "COM16", "power": True},
        "kat500": {"enabled": False, "connected": False, "port": "COM11"},
        "updated_at": 123.0,
    }

    status = asyncio.run(manager.refresh_status())

    assert status["updated_at"] == 123.0
    assert status["kpa500"]["power"] is True
    manager._executor.shutdown(wait=True)


def test_status_api_only_refreshes_hardware_when_explicitly_requested(monkeypatch):
    class FakeManager:
        def __init__(self):
            self.refreshes = 0

        def snapshot(self):
            return {"updated_at": 100.0}

        async def refresh_status(self):
            self.refreshes += 1
            return {"updated_at": 200.0}

    manager = FakeManager()
    monkeypatch.setattr(elecraft_api, "get_elecraft_manager", lambda: manager)

    cached = asyncio.run(elecraft_api.status(refresh=False))
    refreshed = asyncio.run(elecraft_api.status(refresh=True))

    assert cached == {"success": True, "status": {"updated_at": 100.0}}
    assert refreshed == {"success": True, "status": {"updated_at": 200.0}}
    assert manager.refreshes == 1


def test_direct_device_mutations_are_uniformly_retired():
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(elecraft_api._run_device("kpa500", "set_power", True))

    assert rejected.value.status_code == 410
    assert "coordinator" in rejected.value.detail

    for endpoint in (elecraft_api.connect, elecraft_api.disconnect):
        with pytest.raises(HTTPException) as lifecycle_rejected:
            asyncio.run(endpoint())

        assert lifecycle_rejected.value.status_code == 410
        assert "lifecycle" in lifecycle_rejected.value.detail


def test_station_path_prefers_fresh_radio_frequency_over_cached_manager_band():
    now = 1_800_000_300.0
    path = build_station_path(
        {
            "updated_at": now,
            "radio_band": "40m",
            "kpa500": {
                "enabled": True,
                "connected": True,
                "responsive": True,
                "observed_at": now,
                "power": True,
                "operate": False,
                "band": "40m",
                "fault": "00",
            },
            "kat500": {
                "enabled": True,
                "connected": True,
                "responsive": True,
                "observed_at": now,
                "power": True,
                "mode": "auto",
                "band": "40m",
                "frequency_khz": 7074,
                "antenna": 2,
                "tuning": False,
                "fault": "0",
            },
        },
        {
            "connected": True,
            "known": True,
            "stale": False,
            "observed_at": now,
            "frequency": 14.074,
            "mode": "DIGU",
            "tx_ant": "ANT1",
            "mox": False,
            "interlock_state": "READY",
        },
        antenna_policy={"20m": 1, "40m": 2},
        flex_antenna_policy={"bands": {"20m": "ANT1", "40m": "ANT2"}},
        now=now,
    )

    assert path["band"] == "20m"
    codes = {item["code"] for item in path["mismatches"]}
    assert "kpa-band-mismatch" in codes
    assert "kat-band-mismatch" in codes
    assert path["advisories"] == []


def test_station_path_treats_same_band_kat_memory_frequency_as_advisory():
    now = 1_800_000_300.0
    path = build_station_path(
        {
            "updated_at": now,
            "radio_band": "40m",
            "kpa500": {
                "enabled": True,
                "connected": True,
                "responsive": True,
                "observed_at": now,
                "power": True,
                "operate": False,
                "band": "40m",
                "fault": "00",
            },
            "kat500": {
                "enabled": True,
                "connected": True,
                "responsive": True,
                "observed_at": now,
                "power": True,
                "mode": "auto",
                "band": "40m",
                "frequency_khz": 7016,
                "antenna": 2,
                "tuning": False,
                "fault": "0",
            },
        },
        {
            "connected": True,
            "known": True,
            "stale": False,
            "observed_at": now,
            "frequency": 7.074,
            "mode": "DIGU",
            "tx_ant": "ANT1",
            "mox": False,
            "interlock_state": "READY",
        },
        antenna_policy={"40m": 2},
        flex_antenna_policy={"bands": {"40m": "ANT1"}},
        now=now,
    )

    assert path["alignment"] == "confirmed"
    assert path["mismatches"] == []
    assert path["stages"][2]["confirmed"] is True
    assert {item["code"] for item in path["advisories"]} == {
        "kat-frequency-selection-different"
    }
    assert path["tx_ant"] == "ANT1"
    assert path["interlock_state"] == "READY"


def test_band_sync_interrupts_slow_status_telemetry():
    class InterruptibleStatusDevice:
        connected = True
        port = "COM16"

        def __init__(self):
            self.started = threading.Event()
            self.bands = []

        def status(self, stop_event):
            self.started.set()
            assert stop_event.wait(1.0)
            return {
                "enabled": True,
                "connected": True,
                "port": self.port,
                "_interrupted": True,
            }

        def set_band(self, band):
            self.bands.append(band)
            return True

    device = InterruptibleStatusDevice()
    manager = ElecraftManager(kpa500=device, control_enabled=True)

    async def exercise():
        refresh = asyncio.create_task(manager.refresh_status())
        assert await asyncio.to_thread(device.started.wait, 1.0)
        await asyncio.wait_for(manager.sync_radio_state(10.12, "CW"), timeout=0.5)
        await refresh

    asyncio.run(exercise())
    manager._executor.shutdown(wait=True)
    assert device.bands == ["30m"]


def test_control_io_priority_is_reference_counted():
    manager = ElecraftManager()

    manager.begin_control_io()
    manager.begin_control_io()
    assert manager._sync_requested.is_set()

    manager.end_control_io()
    assert manager._sync_requested.is_set()
    manager.end_control_io()
    assert not manager._sync_requested.is_set()
    manager._executor.shutdown(wait=True)


def test_verified_readbacks_publish_without_a_second_serial_poll():
    class Device:
        connected = True

    manager = ElecraftManager(kpa500=Device(), kat500=Device())
    manager.last_band = "40m"
    manager.last_frequency = 7.074
    manager.last_radio_mode = "DIGU"
    manager._status = {
        "kpa500": {"port": "COM17", "temperature_c": 31},
        "kat500": {"port": "COM15", "swr": 1.2},
    }
    kpa = {
        "power": True,
        "operate": False,
        "band": "40m",
        "fault": "00",
        "complete": True,
    }
    kat = {
        "power": True,
        "mode": "auto",
        "antenna": 2,
        "band": "40m",
        "frequency_khz": 7074,
        "tuning": False,
        "fault": "0",
        "bypass": False,
        "amp_key_interrupted": False,
        "complete": True,
    }

    snapshot = asyncio.run(manager.publish_verified_readbacks(kpa, kat))

    assert snapshot["kpa500"]["band"] == "40m"
    assert snapshot["kpa500"]["temperature_c"] == 31
    assert snapshot["kat500"]["frequency_khz"] == 7074
    assert snapshot["kat500"]["swr"] == 1.2
    assert manager.last_kpa_band == "40m"
    assert manager.last_kat_band == "40m"
    assert manager.last_kat_frequency == 7.074
    assert manager.last_kat_antenna == 2
    manager._executor.shutdown(wait=True)


def test_radio_band_command_immediately_synchronizes_elecraft(monkeypatch):
    from radio_control import elecraft
    from services import radio

    class FakeFlex:
        sock = object()
        current_freq = 21.074
        current_mode = "DIGU"

        def set_band(self, band):
            assert band == "20m"
            self.current_freq = 14.074
            return True

    class FakeManager:
        def __init__(self):
            self.calls = []

        async def sync_radio_state(self, frequency, mode):
            self.calls.append((frequency, mode))

    manager = FakeManager()
    flex = FakeFlex()
    monkeypatch.setattr(elecraft, "get_elecraft_manager", lambda: manager)
    radio.configure_radio_control(flex)

    async def route_handler(_reason, operation, **_kwargs):
        return operation()

    monkeypatch.setattr(radio.radio_control_state, "station_route_handler", route_handler)

    result = asyncio.run(radio.set_band(radio.BandRequest(band="20m")))

    assert result["success"] is True
    assert manager.calls == [(14.074, "DIGU")]
    radio.configure_radio_control(None)
