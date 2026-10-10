from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.api.station as station_api
from backend.api.station import _stable_stream_value, _station_stream_payload, router
from backend.api.server_control import router as server_control_router
from backend.core.context import AppContext, install_app_context
from radio_control import config
import services.radio as radio
import services.elecraft_station as station_service
from services.elecraft_station import StationActionError, StationCoordinator


class FakeKPA:
    name = "KPA500"

    def __init__(self, calls: list[tuple], *, ignore_band: bool = False) -> None:
        self.calls = calls
        self.connected = True
        self.last_error = None
        self.operate = False
        self.band = "20m"
        self.ignore_band = ignore_band

    def set_operate(self, value: bool) -> bool:
        self.calls.append(("kpa.operate", value))
        self.operate = value
        return True

    def set_band(self, band: str) -> bool:
        self.calls.append(("kpa.band", band))
        if not self.ignore_band:
            self.band = band
        return True

    def readback(self) -> dict:
        self.calls.append(("kpa.readback",))
        return {
            "power": True,
            "operate": self.operate,
            "band": self.band,
            "fault": "00",
            "complete": True,
        }

    def read_operate(self) -> bool:
        self.calls.append(("kpa.read_operate",))
        return self.operate


class FakeKAT:
    name = "KAT500"

    def __init__(self, calls: list[tuple], tune_states: list[bool] | None = None) -> None:
        self.calls = calls
        self.connected = True
        self.last_error = None
        self.band = "20m"
        self.frequency_khz = 14074
        self.antenna = 2
        self.mode = "auto"
        self.fault = "0"
        self.amp_key_interrupted = False
        self.tune_states = list(tune_states or [True, False])
        self.forward_adc = 25

    def set_band(self, band: str) -> bool:
        self.calls.append(("kat.band", band))
        self.band = band
        return True

    def set_frequency(self, frequency_mhz: float) -> bool:
        self.calls.append(("kat.frequency", frequency_mhz))
        self.frequency_khz = round(frequency_mhz * 1000)
        return True

    def set_antenna(self, antenna: int) -> bool:
        self.calls.append(("kat.antenna", antenna))
        self.antenna = antenna
        return True

    def set_mode(self, mode: str) -> bool:
        self.calls.append(("kat.mode", mode))
        self.mode = mode
        return True

    def readback(self) -> dict:
        self.calls.append(("kat.readback",))
        return {
            "power": True,
            "mode": self.mode,
            "antenna": self.antenna,
            "band": self.band,
            "frequency_khz": self.frequency_khz,
            "tuning": False,
            "fault": self.fault,
            "bypass": False,
            "amp_key_interrupted": self.amp_key_interrupted,
            "complete": True,
        }

    def read_fault(self) -> str:
        self.calls.append(("kat.fault", self.fault))
        return self.fault

    def clear_fault(self) -> bool:
        self.calls.append(("kat.clear_fault",))
        self.fault = "0"
        return True

    def read_amp_key_interrupted(self) -> bool:
        self.calls.append(("kat.amp_key_interrupted", self.amp_key_interrupted))
        return self.amp_key_interrupted

    def set_amp_key_interrupted(self, value: bool) -> bool:
        self.calls.append(("kat.set_amp_key_interrupted", value))
        self.amp_key_interrupted = value
        return True

    def start_tune(self, *, store: bool = False) -> bool:
        self.calls.append(("kat.start_tune", store))
        return True

    def tune_status(self) -> bool:
        value = self.tune_states.pop(0) if self.tune_states else False
        self.calls.append(("kat.tune_status", value))
        return value

    def remote_telemetry(self) -> dict:
        self.calls.append(("kat.remote_telemetry",))
        return {**self.readback(), "swr": 1.2, "forward_adc": self.forward_adc}

    def store_memory(self, frequency_khz: int | None = None) -> bool:
        self.calls.append(("kat.store_memory", frequency_khz))
        return True

    def cancel_tune(self) -> bool:
        self.calls.append(("kat.cancel_tune",))
        return True

    def clear_frequency_memories(self, band: str, antenna: int) -> bool:
        self.calls.append(("kat.clear_frequency_memories", band, antenna))
        return True


class FakeManager:
    def __init__(self, calls: list[tuple], *, ignore_kpa_band: bool = False) -> None:
        self.calls = calls
        self.kpa500 = FakeKPA(calls, ignore_band=ignore_kpa_band)
        self.kat500 = FakeKAT(calls)
        self.antenna_policy = {"20m": 2}
        self.last_frequency = 14.074
        self._lock = asyncio.Lock()
        self.maintenance_suspended = False
        self.fail_reopen = False
        self.follow_radio = True

    async def _run_io(self, operation, *args):
        return operation(*args)

    async def refresh_status(self, *, maintenance_verification: bool = False) -> dict:
        self.calls.append(("manager.refresh", maintenance_verification))
        return self.snapshot()

    async def suspend_for_maintenance(self) -> dict:
        self.calls.append(("manager.suspend",))
        self.maintenance_suspended = True
        self.kpa500.connected = False
        self.kat500.connected = False
        return self.snapshot()

    async def reopen_for_maintenance_exit(self) -> dict:
        self.calls.append(("manager.reopen-identify",))
        if self.fail_reopen:
            raise RuntimeError("identity mismatch")
        self.kpa500.connected = True
        self.kat500.connected = True
        return self.snapshot()

    async def complete_maintenance_exit(self) -> dict:
        self.calls.append(("manager.resume-polling",))
        self.maintenance_suspended = False
        return self.snapshot()

    async def keep_maintenance_suspended(self) -> dict:
        self.calls.append(("manager.keep-suspended",))
        self.maintenance_suspended = True
        self.kpa500.connected = False
        self.kat500.connected = False
        return self.snapshot()

    def snapshot(self) -> dict:
        return {
            "maintenance_suspended": self.maintenance_suspended,
            "kpa500": {
                "enabled": True,
                "connected": self.kpa500.connected,
                "operate": self.kpa500.operate,
                "band": self.kpa500.band,
            },
            "kat500": {
                "enabled": True,
                "connected": self.kat500.connected,
                "band": self.kat500.band,
                "antenna": self.kat500.antenna,
                "frequency_khz": self.kat500.frequency_khz,
            },
        }

    def station_path(self, radio: dict) -> dict:
        confirmed = (
            radio.get("tx_ant") == "ANT1"
            and self.kpa500.band == "20m"
            and self.kat500.band == "20m"
            and self.kat500.antenna == 2
        )
        return {
            "alignment": "confirmed" if confirmed else "unknown",
            "mismatches": [],
            "unknown_reasons": [] if confirmed else ["Route has not been observed yet"],
        }


class FakeFlex:
    def __init__(self, calls: list[tuple], *, tx_confirmed: bool = True) -> None:
        self.calls = calls
        self.sock = object()
        self.current_tx_ant = "ANT1"
        self.current_mode = "USB"
        self.current_tunepower = 10
        self.current_rfpower = 50
        self.tx_confirmed = tx_confirmed
        self.tune_enabled = False
        self.current_freq = 14.074

    def get_fresh_tx_state(self, _timeout: float) -> dict:
        self.calls.append(("flex.tx_state",))
        return {
            "confirmed": self.tx_confirmed,
            "mox": self.tune_enabled,
            "interlock_state": "TRANSMITTING" if self.tune_enabled else "READY",
        }

    def enforce_antenna_policy(self, frequency_mhz: float, *, reason: str) -> bool:
        self.calls.append(("flex.route", frequency_mhz, reason))
        self.current_tx_ant = "ANT1"
        return True

    def get_current_levels(self, _timeout: float, *, apply_antenna_policy: bool) -> dict:
        self.calls.append(("flex.readback", apply_antenna_policy))
        return {
            "freq": self.current_freq,
            "mode": self.current_mode,
            "tx_ant": self.current_tx_ant,
            "rfpower": self.current_rfpower,
        }

    def tune_mhz(self, frequency_mhz: float) -> bool:
        self.calls.append(("flex.qsy", frequency_mhz))
        self.current_freq = frequency_mhz
        return True

    def set_tune_power(self, power: int) -> bool:
        self.calls.append(("flex.tune_power", power))
        self.current_tunepower = power
        return True

    def set_rf_power(self, power: int) -> bool:
        self.calls.append(("flex.rfpower", power))
        self.current_rfpower = power
        return True

    def set_tune(self, enabled: bool) -> bool:
        self.calls.append(("flex.tune", enabled))
        self.tune_enabled = enabled
        return True

    def set_mox(self, enabled: bool) -> bool:
        self.calls.append(("flex.mox", enabled))
        self.tune_enabled = enabled
        return True


class MonitorFlex(FakeFlex):
    def __init__(self, calls: list[tuple]) -> None:
        super().__init__(calls)
        self.monitor_refresh_count = 0

    def refresh_tx_state_probe(self, _timeout: float, *, expect_transmitting: bool) -> dict:
        self.monitor_refresh_count += 1
        transmitting = self.tune_enabled
        return {
            "confirmed": transmitting is expect_transmitting,
            "mox": transmitting,
            "interlock_state": "TRANSMITTING" if transmitting else "READY",
        }

    def _new_tx_state_probe(self):
        raise AssertionError("training must not create a second FLEX TCP connection")


def build_station(
    monkeypatch: pytest.MonkeyPatch,
    *,
    commissioned: bool,
    tx_confirmed: bool = True,
    ignore_kpa_band: bool = False,
) -> tuple[StationCoordinator, list[tuple], FakeManager]:
    monkeypatch.setattr(config, "STATION_COORDINATOR_COMMISSIONED", commissioned)
    monkeypatch.setattr(
        config,
        "FLEX_ANTENNA_POLICY",
        {"enabled": True, "bands": {"20m": "ANT1"}},
    )
    monkeypatch.setattr(config, "KAT500_ANTENNA_NAMES", {"2": "40/20 m antenna"})
    monkeypatch.setattr(config, "STATION_AMPLIFIER_ALLOWED_BANDS", ["20m"])
    monkeypatch.setattr(config, "STATION_AMPLIFIER_DRIVE_W", {"20m": 25})
    monkeypatch.setattr(config, "STATION_BAREFOOT_DRIVE_W", {"20m": 25})
    calls: list[tuple] = []
    manager = FakeManager(calls, ignore_kpa_band=ignore_kpa_band)
    flex = FakeFlex(calls, tx_confirmed=tx_confirmed)
    radio = {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.074,
        "mox": False,
        "interlock_state": "READY",
        "tx_ant": "ANT1",
    }
    station = StationCoordinator(
        manager,
        lambda: flex,
        lambda: radio,
        digital_guard=lambda: None,
        radio_lock=asyncio.Lock(),
    )
    return station, calls, manager


def test_commissioning_lock_exposes_no_actions_and_rejects_write(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=False)

    assert station.snapshot()["allowed_actions"] == ["standby"]
    with pytest.raises(StationActionError, match="commissioned") as exc_info:
        asyncio.run(station.perform("prepare-route"))

    assert exc_info.value.code == "commissioning-required"
    assert calls == []


def test_station_stream_payload_combines_cached_devices_path_and_actions(monkeypatch):
    station, _calls, _manager = build_station(monkeypatch, commissioned=True)

    payload = _station_stream_payload(station)
    stable = _stable_stream_value(payload)

    assert payload["status"]["path"] == payload["station_state"]["path"]
    assert isinstance(payload["status"]["path"], dict)
    assert payload["station_state"]["allowed_actions"]
    assert "generated_at" not in stable["station_state"]
    assert _stable_stream_value(
        {"generated_at": "clock", "stages": [{"state": "ready", "age_seconds": 2}]}
    ) == {"stages": [{"state": "ready"}]}


def test_read_only_station_snapshot_uses_cached_digital_process_state(monkeypatch):
    station, _calls, _manager = build_station(monkeypatch, commissioned=True)
    station._uses_default_digital_guard = True
    refresh_modes = []

    def guard(*, force_refresh=True):
        refresh_modes.append(force_refresh)

    monkeypatch.setattr(station_service, "_default_digital_guard", guard)

    station.snapshot()
    station._assert_digital_idle()

    assert refresh_modes == [False, True]


def test_standby_is_available_while_uncommissioned_and_tx_state_unknown(monkeypatch):
    station, calls, manager = build_station(
        monkeypatch,
        commissioned=False,
        tx_confirmed=False,
    )
    manager.kpa500.operate = True

    state = asyncio.run(station.perform("standby"))

    assert state["transaction"]["state"] == "succeeded"
    assert manager.kpa500.operate is False
    assert ("kpa.operate", False) in calls
    assert not any(call[0] == "flex.tx_state" for call in calls)


def test_external_digital_standby_is_idempotent_on_exact_fresh_readback(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.operate = False

    state = asyncio.run(station.ensure_external_digital_standby())

    assert state["route_verified"] is False
    assert calls.count(("kpa.readback",)) == 1
    assert ("kpa.operate", False) not in calls


def test_cancelled_standby_transaction_is_not_left_running(monkeypatch):
    station, _calls, _manager = build_station(monkeypatch, commissioned=True)

    async def scenario():
        entered = asyncio.Event()

        async def blocked_readback(_device):
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(station, "_device_readback", blocked_readback)
        task = asyncio.create_task(station.perform("standby"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return station.snapshot()["transaction"]

    transaction = asyncio.run(scenario())

    assert transaction["state"] == "failed"
    assert transaction["error"]["code"] == "standby-cancelled"


def test_cancelled_prepare_at_first_rx_proof_retires_without_hardware_cleanup(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)

    async def scenario():
        entered = asyncio.Event()

        async def blocked_receive_proof():
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(station, "_fresh_receive_state", blocked_receive_proof)
        task = asyncio.create_task(station.perform("prepare-route"))
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return station.snapshot()["transaction"]

    transaction = asyncio.run(scenario())

    assert transaction["state"] == "cancelled"
    assert transaction["finished_at"] is not None
    assert transaction["error"]["code"] == "route-preparation-cancelled"
    assert calls == []


def test_cancelled_prepare_after_route_mutation_retires_and_confirms_standby(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)

    async def scenario():
        entered = asyncio.Event()

        async def blocked_route_proof(_route):
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(station, "_fresh_flex_route", blocked_route_proof)
        task = asyncio.create_task(station.perform("prepare-route"))
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return station.snapshot()

    state = asyncio.run(scenario())

    assert state["transaction"]["state"] == "cancelled"
    assert state["transaction"]["finished_at"] is not None
    assert state["transaction"]["error"]["code"] == "route-preparation-cancelled"
    assert state["route_verified"] is False
    assert ("flex.route", 14.074, "station coordinator route preparation") in calls
    assert calls.count(("kpa.operate", False)) == 2
    assert calls[-2:] == [("kpa.operate", False), ("kpa.readback",)]
    assert manager.kpa500.operate is False


def test_cancelled_operate_retires_and_returns_kpa_to_standby(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    asyncio.run(station.perform("prepare-route"))
    calls.clear()
    original_device_call = station._device_call

    async def scenario():
        entered = asyncio.Event()

        async def block_after_operate(device, method, *args, **kwargs):
            if (
                device is manager.kpa500
                and method == "read_operate"
                and manager.kpa500.operate
            ):
                entered.set()
                await asyncio.Event().wait()
            return await original_device_call(device, method, *args, **kwargs)

        monkeypatch.setattr(station, "_device_call", block_after_operate)
        task = asyncio.create_task(station.perform("operate"))
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return station.snapshot()

    state = asyncio.run(scenario())

    assert state["transaction"]["state"] == "cancelled"
    assert state["transaction"]["finished_at"] is not None
    assert state["transaction"]["error"]["code"] == "operate-cancelled"
    assert state["route_verified"] is False
    assert calls.index(("kpa.operate", True)) < calls.index(("kpa.operate", False))
    assert manager.kpa500.operate is False


def test_startup_recovery_forces_tune_mox_off_and_kpa_standby(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=False)
    station._recovery_required = True
    manager.kpa500.operate = True
    flex = station.flex_provider()
    flex.tune_enabled = True

    state = asyncio.run(station.recover_safe_state())

    assert state["recovery_required"] is False
    assert manager.kpa500.operate is False
    assert ("flex.tune", False) in calls
    assert ("flex.mox", False) in calls
    assert ("kpa.operate", False) in calls


def test_route_change_confirms_standby_before_flex_mutation(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=False)
    manager.kpa500.operate = True

    def qsy():
        calls.append(("flex.qsy", 7.074))
        return True

    assert asyncio.run(station.execute_flex_route_change("test-qsy", qsy)) is True
    assert manager.kpa500.operate is False
    assert calls.index(("kpa.operate", False)) < calls.index(("flex.qsy", 7.074))


def test_external_flex_band_change_safely_follows_kpa_and_kat_in_receive(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    monkeypatch.setattr(config, "STATION_BAREFOOT_DRIVE_W", {"20m": 65})
    manager.kpa500.band = "12m"
    manager.kat500.band = "12m"
    manager.kat500.frequency_khz = 24915
    manager.kat500.antenna = 1

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is True
    assert manager.kpa500.band == "20m"
    assert manager.kpa500.operate is False
    assert manager.kat500.band == "20m"
    assert manager.kat500.frequency_khz == 14074
    assert manager.kat500.antenna == 2
    assert calls.index(("flex.tx_state",)) < calls.index(("kpa.operate", False))
    assert calls.index(("kpa.operate", False)) < calls.index(("kpa.band", "20m"))
    assert ("flex.rfpower", 65) in calls
    assert calls.index(("kpa.operate", False)) < calls.index(("flex.rfpower", 65))
    assert not any(call[0] in {"flex.tune", "flex.mox"} for call in calls)


def test_external_flex_route_follow_corrects_barefoot_power_only_drift(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    monkeypatch.setattr(config, "STATION_BAREFOOT_DRIVE_W", {"20m": 70})
    station.radio_snapshot_provider = lambda: {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.074,
        "mox": False,
        "interlock_state": "READY",
        "tx_ant": "ANT1",
        "drive": 50,
    }

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is True
    assert manager.kpa500.operate is False
    assert ("flex.rfpower", 70) in calls
    assert not any(call[0] == "kpa.operate" for call in calls)


def test_switching_to_disallowed_digital_profile_forces_pa_standby(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    monkeypatch.setattr(config, "DIGITAL_KPA_POLICY", "operate")
    monkeypatch.setattr(config, "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS", ["40m"])
    monkeypatch.setattr(config, "STATION_DIGITAL_AMPLIFIER_DRIVE_W", {"20m": 10})
    manager.kpa500.operate = True
    flex = station.flex_provider()
    flex.current_mode = "DIGU"
    flex.current_rfpower = 25
    radio = station.radio_snapshot_provider()
    radio.update(mode="DIGU", drive=25)

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is True
    assert manager.kpa500.operate is False
    assert ("kpa.operate", False) in calls
    assert ("flex.rfpower", 25) in calls


def test_external_owner_route_follow_corrects_power_only_drift_in_receive(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)
    station.radio_snapshot_provider = lambda: {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.074,
        "mox": False,
        "interlock_state": "READY",
        "tx_ant": "ANT1",
        "drive": 50,
    }

    def external_owner_guard():
        raise StationActionError(
            "digital-engine-owns-radio",
            "The active external digital engine owns radio and transmit control",
        )

    station.digital_guard = external_owner_guard

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is True
    assert ("flex.rfpower", 25) in calls


def test_external_flex_route_follow_accepts_operate_drive_without_forcing_standby(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.operate = True
    station.radio_snapshot_provider = lambda: {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.074,
        "mox": False,
        "interlock_state": "READY",
        "tx_ant": "ANT1",
        "drive": 25,
    }

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is False
    assert manager.kpa500.operate is True
    assert calls == []


def test_obsolete_follow_mismatch_is_rechecked_before_standby(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.operate = True
    manager.kpa500.band = "12m"
    station.flex_provider().current_rfpower = 25
    original_require = station._require_fresh_route

    def settle_before_locked_recheck():
        manager.kpa500.band = "20m"
        return original_require()

    station._require_fresh_route = settle_before_locked_recheck

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is False
    assert manager.kpa500.operate is True
    assert not any(call[0] == "kpa.operate" for call in calls)


def test_cached_topology_mismatch_is_confirmed_fresh_before_dropping_operate(
    monkeypatch,
):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.operate = True
    station.flex_provider().current_rfpower = 25
    manager.kpa500.band = "12m"

    async def refresh_settles_transient(*, maintenance_verification: bool = False):
        calls.append(("manager.refresh", maintenance_verification))
        manager.kpa500.band = "20m"
        return manager.snapshot()

    manager.refresh_status = refresh_settles_transient

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is False
    assert manager.kpa500.operate is True
    assert ("manager.refresh", False) in calls
    assert not any(call[0] == "kpa.operate" for call in calls)


def test_cached_flex_antenna_mismatch_is_refreshed_before_dropping_operate(
    monkeypatch,
):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.operate = True
    station.flex_provider().current_rfpower = 25
    radio = {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.074,
        "mox": False,
        "interlock_state": "READY",
        "tx_ant": "",
        "drive": 25,
    }
    station.radio_snapshot_provider = lambda: radio

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is False
    assert radio["tx_ant"] == "ANT1"
    assert manager.kpa500.operate is True
    assert ("flex.readback", False) in calls
    assert not any(call[0] == "kpa.operate" for call in calls)


def test_unchanged_verified_route_never_automatically_drops_operate(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.operate = True
    manager.kpa500.band = "12m"
    station.flex_provider().current_rfpower = 25
    station._route_verified = {
        "route_id": "20m-flex-ant1-kat-ant2",
        "frequency_khz": 14074,
        "verified_at": time.time() - 60,
        "kpa_operate": True,
    }

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is False
    assert manager.kpa500.operate is True
    assert ("manager.refresh", False) in calls
    assert not any(call[0] == "kpa.operate" for call in calls)


def test_external_flex_drive_drift_is_corrected_without_dropping_operate(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.operate = True
    flex = station.flex_provider()
    flex.current_rfpower = 90
    station.radio_snapshot_provider = lambda: {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.074,
        "mox": False,
        "interlock_state": "READY",
        "tx_ant": "ANT1",
        "drive": 90,
    }

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is True
    assert manager.kpa500.operate is True
    assert flex.current_rfpower == 25
    assert ("flex.rfpower", 25) in calls
    assert not any(call[0] == "kpa.operate" for call in calls)


def test_external_flex_frequency_follow_restores_manual_operate(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.operate = True
    manager.kat500.frequency_khz = 14074
    flex = station.flex_provider()
    flex.current_freq = 14.080
    flex.current_rfpower = 25
    station.radio_snapshot_provider = lambda: {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.080,
        "mox": False,
        "interlock_state": "READY",
        "tx_ant": "ANT1",
        "drive": 25,
    }

    followed = asyncio.run(station.follow_observed_radio_route(14.080))

    assert followed is True
    assert manager.kpa500.operate is True
    assert manager.kat500.frequency_khz == 14080
    assert calls.index(("kpa.operate", False)) < calls.index(
        ("kat.frequency", 14.080)
    )
    assert calls.index(("kat.frequency", 14.080)) < calls.index(
        ("kpa.operate", True)
    )


def test_external_flex_follow_keeps_standby_when_route_prohibits_amplifier(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    monkeypatch.setattr(config, "STATION_AMPLIFIER_ALLOWED_BANDS", [])
    manager.kpa500.operate = True
    manager.kat500.frequency_khz = 14074
    flex = station.flex_provider()
    flex.current_freq = 14.080
    station.radio_snapshot_provider = lambda: {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.080,
        "mox": False,
        "interlock_state": "READY",
        "tx_ant": "ANT1",
        "drive": 25,
    }

    followed = asyncio.run(station.follow_observed_radio_route(14.080))

    assert followed is True
    assert manager.kpa500.operate is False
    assert ("kpa.operate", True) not in calls


def test_external_flex_band_follow_routes_while_digital_tx_is_armed_but_radio_is_rx(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.band = "12m"
    manager.kat500.band = "12m"
    manager.kat500.frequency_khz = 24915
    manager.kat500.antenna = 1

    def armed_guard():
        raise StationActionError("digital-tx-armed", "Digital TX is armed")

    station.digital_guard = armed_guard

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is True
    assert manager.kpa500.operate is False
    assert manager.kpa500.band == "20m"
    assert manager.kat500.band == "20m"
    assert manager.kat500.frequency_khz == 14074
    assert calls.index(("flex.tx_state",)) < calls.index(("kpa.operate", False))
    assert not any(call[0] in {"flex.tune", "flex.mox"} for call in calls)


def test_external_flex_band_follow_refuses_writes_without_confirmed_receive(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.band = "12m"
    manager.kat500.band = "12m"
    station.radio_snapshot_provider = lambda: {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.074,
        "mox": True,
        "interlock_state": "TRANSMITTING",
        "tx_ant": "ANT1",
    }

    followed = asyncio.run(station.follow_observed_radio_route(14.074))

    assert followed is False
    assert manager.kpa500.band == "12m"
    assert manager.kat500.band == "12m"
    assert calls == []


def test_superseded_observed_route_terminalizes_then_new_route_replaces_it(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kpa500.band = "12m"
    manager.kat500.band = "12m"
    manager.kat500.frequency_khz = 24915
    manager.kat500.antenna = 1
    flex = station.flex_provider()
    radio = {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 14.074,
        "mox": False,
        "interlock_state": "READY",
        "tx_ant": "ANT1",
        "drive": 50,
    }
    station.radio_snapshot_provider = lambda: radio
    original_enforce = flex.enforce_antenna_policy

    def superseding_enforce(frequency_mhz: float, *, reason: str) -> bool:
        applied = original_enforce(frequency_mhz, reason=reason)
        radio["frequency"] = 14.080
        flex.current_freq = 14.080
        return applied

    flex.enforce_antenna_policy = superseding_enforce
    with pytest.raises(StationActionError) as exc_info:
        asyncio.run(station.follow_observed_radio_route(14.074))

    assert exc_info.value.code == "observed-route-superseded"
    stale = station.snapshot()["transaction"]
    assert stale["state"] == "failed"
    assert stale["finished_at"] is not None
    assert stale["error"]["code"] == "observed-route-superseded"
    assert manager.kpa500.operate is False

    flex.enforce_antenna_policy = original_enforce
    assert asyncio.run(station.follow_observed_radio_route(14.080)) is True
    current = station.snapshot()["transaction"]
    assert current["state"] == "succeeded"
    assert current["finished_at"] is not None
    assert manager.kat500.frequency_khz == 14080
    assert calls.count(("flex.route", 14.074, "station coordinator route preparation")) == 1
    assert calls.count(("flex.route", 14.080, "station coordinator route preparation")) == 1


def test_amplifier_allowlist_blocks_operate_on_prohibited_band(monkeypatch):
    monkeypatch.setattr(config, "STATION_COORDINATOR_COMMISSIONED", True)
    monkeypatch.setattr(config, "STATION_AMPLIFIER_ALLOWED_BANDS", ["20m"])
    monkeypatch.setattr(
        config,
        "FLEX_ANTENNA_POLICY",
        {"enabled": True, "bands": {"60m": "ANT1"}},
    )
    calls: list[tuple] = []
    manager = FakeManager(calls)
    manager.antenna_policy["60m"] = 2
    manager.kpa500.band = "60m"
    manager.kat500.band = "60m"
    manager.kat500.frequency_khz = 5357
    radio_state = {
        "connected": True,
        "known": True,
        "stale": False,
        "frequency": 5.357,
        "mox": False,
        "interlock_state": "READY",
        "tx_ant": "ANT1",
    }
    station = StationCoordinator(
        manager,
        lambda: FakeFlex(calls),
        lambda: radio_state,
        digital_guard=lambda: None,
        radio_lock=asyncio.Lock(),
    )
    route = station._require_fresh_route()
    station._route_verified = {
        "route_id": route.route_id,
        "frequency_khz": round(route.frequency_mhz * 1000),
        "verified_at": time.time(),
    }

    assert route.amplifier_allowed is False
    with pytest.raises(StationActionError) as exc_info:
        asyncio.run(station.perform("operate"))
    assert exc_info.value.code == "amplifier-not-allowed"


def test_prepare_route_keeps_flex_and_kat_antenna_stages_distinct(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)

    state = asyncio.run(station.perform("prepare-route"))

    assert state["route_verified"] is True
    assert state["route"]["flex_tx_ant"] == "ANT1"
    assert state["route"]["kat_antenna"] == 2
    assert calls.index(("kpa.operate", False)) < calls.index(("kat.antenna", 2))
    assert ("flex.readback", False) in calls


def test_prepare_route_reuses_primary_flex_tx_subscription(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)
    flex = MonitorFlex(calls)
    station.flex_provider = lambda: flex

    state = asyncio.run(station.perform("prepare-route"))

    assert state["route_verified"] is True
    assert flex.monitor_refresh_count >= 5
    assert flex.sock is not None


def test_prepare_route_clears_latched_kat_fault_only_after_receive_and_standby(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kat500.fault = "3"

    state = asyncio.run(station.perform("prepare-route"))

    assert state["route_verified"] is True
    assert manager.kat500.fault == "0"
    assert ("kat.clear_fault",) in calls
    assert calls.index(("flex.tx_state",)) < calls.index(("kpa.operate", False))
    assert calls.index(("kpa.operate", False)) < calls.index(("kat.clear_fault",))


def test_prepare_route_reconnects_kat_amp_key_only_in_receive_with_kpa_standby(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kat500.amp_key_interrupted = True

    state = asyncio.run(station.perform("prepare-route"))

    assert state["route_verified"] is True
    assert manager.kat500.amp_key_interrupted is False
    assert ("kat.set_amp_key_interrupted", False) in calls
    assert calls.index(("flex.tx_state",)) < calls.index(("kpa.operate", False))
    assert calls.index(("kpa.operate", False)) < calls.index(
        ("kat.set_amp_key_interrupted", False)
    )


def test_guarded_operate_and_standby_actions_toggle_kpa_with_exact_readback(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)

    asyncio.run(station.perform("prepare-route"))
    operated = asyncio.run(station.perform("operate"))

    assert operated["transaction"]["state"] == "succeeded"
    assert manager.kpa500.operate is True
    assert operated["route"]["amplifier_drive_w"] == 25
    assert ("flex.rfpower", 25) in calls
    assert calls.index(("flex.rfpower", 25)) < calls.index(("kpa.operate", True))
    assert ("kpa.operate", True) in calls

    stood_by = asyncio.run(station.perform("standby"))

    assert stood_by["transaction"]["state"] == "succeeded"
    assert manager.kpa500.operate is False
    assert calls[-2:] == [("kpa.readback",), ("manager.refresh", False)]


def test_operate_atomically_prepares_unverified_route_before_switching_kpa(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)

    operated = asyncio.run(station.perform("operate"))

    assert operated["transaction"]["state"] == "succeeded"
    assert manager.kpa500.operate is True
    assert ("flex.route", 14.074, "station coordinator route preparation") in calls
    assert calls.index(("kpa.operate", False)) < calls.index(("flex.rfpower", 25))
    assert calls.index(("flex.rfpower", 25)) < calls.index(("kpa.operate", True))


def test_operate_reuses_recent_exact_path_without_repreparing_route(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    original_snapshot = manager.snapshot

    def recent_complete_snapshot():
        state = original_snapshot()
        observed_at = time.time()
        state["updated_at"] = observed_at
        state["kpa500"].update(
            power=True,
            responsive=True,
            operate=False,
            band="20m",
            fault="00",
            observed_at=observed_at,
            missing_fields=[],
            quality="good",
        )
        state["kat500"].update(
            power=True,
            responsive=True,
            mode="auto",
            band="20m",
            antenna=2,
            frequency_khz=14074,
            tuning=False,
            fault="0",
            amp_key_interrupted=False,
            observed_at=observed_at,
            missing_fields=[],
            quality="good",
        )
        return state

    manager.snapshot = recent_complete_snapshot

    assert "operate" in station.snapshot()["allowed_actions"]
    operated = asyncio.run(station.perform("operate"))

    assert operated["transaction"]["state"] == "succeeded"
    assert manager.kpa500.operate is True
    assert ("flex.rfpower", 25) in calls
    assert ("kpa.operate", True) in calls
    assert ("kpa.read_operate",) in calls
    assert not any(
        call[0] in {"flex.route", "kpa.band", "kat.band", "kat.frequency", "kat.antenna"}
        for call in calls
    )


def test_operate_recovers_latched_kat_fault_and_key_interrupt_in_receive(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    asyncio.run(station.perform("prepare-route"))
    calls.clear()
    manager.kat500.fault = "2"
    manager.kat500.amp_key_interrupted = True

    operated = asyncio.run(station.perform("operate"))

    assert operated["transaction"]["state"] == "succeeded"
    assert manager.kat500.fault == "0"
    assert manager.kat500.amp_key_interrupted is False
    assert manager.kpa500.operate is True
    assert calls.index(("kat.clear_fault",)) < calls.index(
        ("kat.set_amp_key_interrupted", False)
    )
    assert calls.index(("kat.set_amp_key_interrupted", False)) < calls.index(
        ("kpa.operate", True)
    )


def test_operate_requires_fresh_flex_drive_readback_before_kpa(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    asyncio.run(station.perform("prepare-route"))
    calls.clear()
    flex = station.flex_provider()
    flex.current_rfpower = 88

    def accept_without_applying(power: int) -> bool:
        calls.append(("flex.rfpower", power))
        return True

    flex.set_rf_power = accept_without_applying

    with pytest.raises(StationActionError) as exc_info:
        asyncio.run(station.perform("operate"))

    assert exc_info.value.code == "flex-drive-readback-mismatch"
    assert manager.kpa500.operate is False
    assert ("kpa.operate", True) not in calls


def test_operate_refreshes_an_expired_flex_snapshot_inside_the_action(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    asyncio.run(station.perform("prepare-route"))
    radio = station.radio_snapshot_provider()
    radio.update(known=False, stale=True, observed_at=None)
    calls.clear()

    operated = asyncio.run(station.perform("operate"))

    assert operated["transaction"]["state"] == "succeeded"
    assert manager.kpa500.operate is True
    assert radio["known"] is True
    assert radio["stale"] is False
    assert radio["frequency"] == 14.074
    assert ("flex.readback", False) in calls
    assert ("kpa.operate", True) in calls


def test_prepare_applies_barefoot_drive_then_operate_applies_pa_drive(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)
    monkeypatch.setattr(config, "DIGITAL_KPA_POLICY", "operate")
    monkeypatch.setattr(config, "STATION_BAREFOOT_DRIVE_W", {"20M": 80})
    monkeypatch.setattr(config, "STATION_AMPLIFIER_DRIVE_W", {"20M": 27})

    prepared = asyncio.run(station.perform("prepare-route"))
    operated = asyncio.run(station.perform("operate"))

    assert prepared["route"]["barefoot_drive_w"] == 80
    assert operated["route"]["amplifier_drive_w"] == 27
    assert operated["route"]["configured_kpa500"] == "operate"
    assert operated["route"]["kpa500"] == "operate"
    assert operated["route"]["active_drive_w"] == 27
    assert ("flex.rfpower", 80) in calls
    assert ("flex.rfpower", 27) in calls
    assert calls.index(("flex.rfpower", 80)) < calls.index(("flex.rfpower", 27))
    assert calls.index(("flex.rfpower", 27)) < calls.index(("kpa.operate", True))


def test_route_uses_independent_digital_band_and_drive_policy(monkeypatch):
    station, _calls, _manager = build_station(monkeypatch, commissioned=True)
    monkeypatch.setattr(config, "DIGITAL_KPA_POLICY", "operate")
    monkeypatch.setattr(config, "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS", ["40m"])
    monkeypatch.setattr(
        config,
        "STATION_DIGITAL_AMPLIFIER_DRIVE_W",
        {"20m": 10, "40m": 15},
    )
    radio = station.radio_snapshot_provider()

    radio["mode"] = "USB"
    standard = station._route_for_snapshot(radio)
    radio["mode"] = "DIGU"
    digital = station._route_for_snapshot(radio)

    assert standard is not None
    assert standard.digital_mode is False
    assert standard.amplifier_allowed is True
    assert standard.active_drive_w == 25
    assert digital is not None
    assert digital.digital_mode is True
    assert digital.amplifier_allowed is False
    assert digital.kpa500 == "standby"
    assert digital.amplifier_drive_w == 10
    assert digital.active_drive_w == 25


def test_external_digital_owner_allows_manual_rx_only_operate(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)

    def external_owner_guard():
        raise StationActionError(
            "digital-engine-owns-radio",
            "The active external digital engine owns radio and transmit control",
        )

    station.digital_guard = external_owner_guard
    assert station.snapshot()["allowed_actions"] == ["standby", "prepare-route"]

    prepared = asyncio.run(station.perform("prepare-route"))
    assert "operate" in prepared["allowed_actions"]
    assert "tune" not in prepared["allowed_actions"]

    operated = asyncio.run(station.perform("operate"))

    assert operated["transaction"]["state"] == "succeeded"
    assert manager.kpa500.operate is True
    assert calls.index(("flex.rfpower", 25)) < calls.index(("kpa.operate", True))


def test_external_digital_owner_waits_through_active_slot_before_operate(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    flex = station.flex_provider()
    states = iter(
        [
            {"confirmed": True, "mox": True, "interlock_state": "TRANSMITTING"},
            {"confirmed": True, "mox": False, "interlock_state": "READY"},
        ]
    )
    original = flex.get_fresh_tx_state

    def sequenced_tx_state(timeout):
        calls.append(("flex.tx_state",))
        try:
            return next(states)
        except StopIteration:
            return original(timeout)

    flex.get_fresh_tx_state = sequenced_tx_state

    def external_owner_guard():
        raise StationActionError(
            "digital-engine-owns-radio",
            "The active external digital engine owns radio and transmit control",
        )

    class LeaseService:
        def __init__(self):
            self.acquired = []
            self.released = []

        def acquire_station_control_lease(self, reason):
            self.acquired.append(reason)
            return "lease-token"

        def release_station_control_lease(self, token):
            self.released.append(token)
            return True

    lease_service = LeaseService()
    station.digital_guard = external_owner_guard
    monkeypatch.setattr(
        "services.digital_engine.get_digital_engine_service",
        lambda: lease_service,
    )

    operated = asyncio.run(station.perform("operate"))

    assert operated["transaction"]["state"] == "succeeded"
    assert manager.kpa500.operate is True
    assert lease_service.acquired == ["manual-operate"]
    assert lease_service.released == ["lease-token"]


def test_external_digital_owner_retries_prearmed_tx_collision_during_operate(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    flex = station.flex_provider()
    proof_count = 0

    def collide_once_during_route_prepare(_timeout):
        nonlocal proof_count
        proof_count += 1
        calls.append(("flex.tx_state",))
        # The lease's two initial proofs succeed. The first transaction then
        # crosses a PTT edge; every later proof is RX after that slot ends.
        if proof_count == 4:
            return {
                "confirmed": True,
                "mox": True,
                "interlock_state": "TRANSMITTING",
            }
        return {"confirmed": True, "mox": False, "interlock_state": "READY"}

    flex.get_fresh_tx_state = collide_once_during_route_prepare

    def external_owner_guard():
        raise StationActionError(
            "digital-engine-owns-radio",
            "The active external digital engine owns radio and transmit control",
        )

    class LeaseService:
        def acquire_station_control_lease(self, _reason):
            return "lease-token"

        def release_station_control_lease(self, _token):
            return True

    station.digital_guard = external_owner_guard
    monkeypatch.setattr(
        "services.digital_engine.get_digital_engine_service",
        lambda: LeaseService(),
    )

    operated = asyncio.run(station.perform("operate"))

    assert operated["transaction"]["state"] == "succeeded"
    assert manager.kpa500.operate is True
    assert proof_count > 4
    assert calls.count(("kpa.operate", False)) >= 2


def test_unknown_flex_tx_state_blocks_before_any_device_write(monkeypatch):
    station, calls, _manager = build_station(
        monkeypatch,
        commissioned=True,
        tx_confirmed=False,
    )

    with pytest.raises(StationActionError) as exc_info:
        asyncio.run(station.perform("prepare-route"))

    assert exc_info.value.code == "flex-tx-state-unconfirmed"
    assert not any(call[0] in {"kpa.operate", "kpa.band", "kat.band", "kat.antenna"} for call in calls)


def test_armed_digital_tx_blocks_before_any_device_or_flex_probe(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)

    def blocked_guard():
        raise StationActionError("digital-tx-armed", "Digital TX is armed")

    station.digital_guard = blocked_guard
    assert station.snapshot()["allowed_actions"] == ["standby"]
    with pytest.raises(StationActionError) as exc_info:
        asyncio.run(station.perform("prepare-route"))

    assert exc_info.value.code == "digital-tx-armed"
    assert calls == []


def test_readback_mismatch_fails_and_requests_standby(monkeypatch):
    station, calls, manager = build_station(
        monkeypatch,
        commissioned=True,
        ignore_kpa_band=True,
    )
    manager.kpa500.band = "40m"

    with pytest.raises(StationActionError) as exc_info:
        asyncio.run(station.perform("prepare-route"))

    assert exc_info.value.code == "route-readback-mismatch"
    assert ("kpa.operate", False) in calls
    assert calls[-1] == ("kpa.readback",)
    assert manager.kpa500.operate is False
    assert station.snapshot()["route_verified"] is False


def test_tune_stores_only_after_good_swr_and_leaves_amplifier_standby(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)

    async def exercise_tune() -> None:
        await station.perform("prepare-route")
        await station.perform("tune")
        task = station._active_task
        assert task is not None
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(exercise_tune())

    assert station.snapshot()["transaction"]["state"] == "succeeded"
    assert ("kat.start_tune", False) in calls
    assert ("kat.store_memory", 14074) in calls
    assert calls.index(("flex.tune", False)) < calls.index(("kat.store_memory", 14074))
    assert manager.kpa500.operate is False


def test_training_point_qsy_uses_exact_route_and_existing_tune_transaction(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    point = {
        "sequence": 1,
        "band": "20m",
        "frequency_mhz": 14.1,
        "frequency_khz": 14100,
        "route_id": "20m-flex-ant1-kat-ant2",
        "flex_tx_ant": "ANT1",
        "kat_antenna": 2,
        "eligible": True,
    }

    async def exercise():
        station.claim_training("job-1")
        blockers = await station.fresh_training_execution_blockers(
            [point],
            job_id="job-1",
        )
        result = await station.execute_training_point("job-1", point)
        await station.release_training("job-1")
        return blockers, result

    blockers, result = asyncio.run(exercise())

    assert blockers == []
    assert result["state"] == "succeeded"
    assert result["swr_after"] == 1.2
    assert calls.index(("kpa.operate", False)) < calls.index(("flex.qsy", 14.1))
    assert ("kat.frequency", 14.1) in calls
    assert ("kat.store_memory", 14100) in calls
    assert not any(call == ("kpa.operate", True) for call in calls)
    assert manager.kpa500.operate is False


def test_training_reuses_primary_flex_connection_for_entire_job(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)
    flex = MonitorFlex(calls)
    station.flex_provider = lambda: flex
    point = {
        "sequence": 1,
        "band": "20m",
        "frequency_mhz": 14.1,
        "frequency_khz": 14100,
        "route_id": "20m-flex-ant1-kat-ant2",
        "flex_tx_ant": "ANT1",
        "kat_antenna": 2,
        "eligible": True,
    }

    async def exercise():
        station.claim_training("job-monitor")
        assert await station.fresh_training_execution_blockers([point], job_id="job-monitor") == []
        result = await station.execute_training_point("job-monitor", point)
        await station.release_training("job-monitor")
        return result

    result = asyncio.run(exercise())

    assert result["state"] == "succeeded"
    assert flex.monitor_refresh_count > 3
    assert flex.sock is not None


def test_swr_survey_uses_manual_mode_and_never_tunes_or_stores(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    point = {
        "sequence": 1,
        "band": "20m",
        "frequency_mhz": 14.1,
        "frequency_khz": 14100,
        "route_id": "20m-flex-ant1-kat-ant2",
        "flex_tx_ant": "ANT1",
        "kat_antenna": 2,
        "eligible": True,
    }

    async def exercise():
        station.claim_training("job-survey")
        assert await station.fresh_training_execution_blockers([point], job_id="job-survey") == []
        result = await station.execute_swr_survey_point("job-survey", point)
        await station.release_training("job-survey")
        return result

    result = asyncio.run(exercise())

    assert result["state"] == "succeeded"
    assert result["kind"] == "swr-survey"
    assert result["swr_before"] == 1.2
    assert result["swr_after"] is None
    assert result["memory_changed"] is False
    assert ("kat.mode", "manual") in calls
    assert ("kat.mode", "auto") in calls
    assert not any(call[0] == "kat.start_tune" for call in calls)
    assert not any(call[0] == "kat.store_memory" for call in calls)
    assert manager.kat500.mode == "auto"


def test_training_memory_clear_rejects_all_antenna_scope(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)

    async def exercise():
        station.claim_training("job-erase")
        with pytest.raises(StationActionError) as exc_info:
            await station.clear_training_memories(
                "job-erase",
                [{"band": "20m", "kat_antenna": 0, "frequency_mhz": 14.074}],
            )
        await station.release_training("job-erase")
        return exc_info.value

    error = asyncio.run(exercise())

    assert error.code == "training-erase-scope-invalid"
    assert not any(call[0] == "kat.clear_frequency_memories" for call in calls)


def test_fast_tune_completion_does_not_hold_carrier_until_timeout(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kat500.tune_states = [False, False]

    async def exercise_tune() -> None:
        await station.perform("prepare-route")
        await station.perform("tune")
        task = station._active_task
        assert task is not None
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(exercise_tune())

    assert station.snapshot()["transaction"]["state"] == "succeeded"
    assert ("kat.store_memory", 14074) in calls
    assert calls.count(("kat.tune_status", False)) == 2


def test_cancel_tune_forces_carrier_off_and_never_stores(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kat500.tune_states = [True] * 20

    async def exercise_cancel() -> None:
        await station.perform("prepare-route")
        await station.perform("tune")
        task = station._active_task
        assert task is not None
        for _ in range(100):
            if ("flex.tune", True) in calls:
                break
            await asyncio.sleep(0.01)
        await station.perform("cancel")
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(exercise_cancel())

    assert station.snapshot()["transaction"]["state"] == "cancelled"
    assert ("flex.tune", False) in calls
    assert ("kat.cancel_tune",) in calls
    assert not any(call[0] == "kat.store_memory" for call in calls)
    assert manager.kpa500.operate is False


def test_idle_or_stale_swr_without_forward_rf_is_never_stored(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kat500.forward_adc = 0

    async def exercise_tune() -> None:
        await station.perform("prepare-route")
        await station.perform("tune")
        task = station._active_task
        assert task is not None
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(exercise_tune())

    transaction = station.snapshot()["transaction"]
    assert transaction["state"] == "failed"
    assert transaction["error"]["code"] == "tune-rf-unconfirmed"
    assert not any(call[0] == "kat.store_memory" for call in calls)
    assert ("flex.tune", False) in calls


def test_station_api_maps_coordinator_error_without_direct_device_access(monkeypatch):
    station, _calls, _manager = build_station(monkeypatch, commissioned=False)
    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=station))
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post("/api/station/actions/prepare-route")

    assert response.status_code == 409
    assert response.json()["detail"].startswith("commissioning-required:")


def test_maintenance_entry_proves_safe_state_then_releases_ports(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    route = station._require_fresh_route()
    station._route_verified = {
        "route_id": route.route_id,
        "frequency_khz": round(route.frequency_mhz * 1000),
        "verified_at": time.time(),
    }
    manager.kpa500.operate = True

    state = asyncio.run(station.enter_maintenance())

    assert state["maintenance"] is True
    assert state["coordinator_state"] == "maintenance"
    assert state["allowed_actions"] == ["exit-maintenance"]
    assert state["route_verified"] is False
    assert manager.kpa500.connected is False
    assert manager.kat500.connected is False
    assert calls.index(("flex.tx_state",)) < calls.index(("flex.tune", False))
    assert calls.index(("flex.mox", False)) < calls.index(("kpa.operate", False))
    assert calls.index(("kpa.readback",)) < calls.index(("manager.suspend",))


def test_maintenance_blocks_station_tx_and_qsy_paths(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)
    asyncio.run(station.enter_maintenance())
    calls.clear()

    for operation in (
        lambda: station.perform("prepare-route"),
        lambda: station.perform("operate"),
        lambda: station.perform("tune"),
        lambda: station.execute_raw_flex_tx("mox", lambda: True),
        lambda: station.execute_flex_route_change("maintenance-qsy", lambda: True),
    ):
        with pytest.raises(StationActionError) as exc_info:
            asyncio.run(operation())
        assert exc_info.value.code == "station-maintenance-active"

    assert calls == []


def test_maintenance_exit_reidentifies_and_verifies_before_unlocking(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    asyncio.run(station.enter_maintenance())
    calls.clear()

    state = asyncio.run(station.exit_maintenance())

    assert state["maintenance"] is False
    assert state["recovery_required"] is False
    assert state["coordinator_state"] == "safe_rx"
    assert calls[0] == ("manager.reopen-identify",)
    assert ("flex.tune", False) in calls
    assert ("flex.mox", False) in calls
    assert calls.index(("kpa.readback",)) < calls.index(("manager.refresh", True))
    assert calls.index(("kat.readback",)) < calls.index(("manager.refresh", True))
    assert calls[-1] == ("manager.resume-polling",)
    assert manager.maintenance_suspended is False


def test_failed_maintenance_exit_keeps_ports_released_and_controls_blocked(monkeypatch):
    station, _calls, manager = build_station(monkeypatch, commissioned=True)
    asyncio.run(station.enter_maintenance())
    manager.fail_reopen = True

    with pytest.raises(StationActionError) as exc_info:
        asyncio.run(station.exit_maintenance())

    assert exc_info.value.code == "maintenance-exit-verification-failed"
    state = station.snapshot()
    assert state["maintenance"] is True
    assert state["recovery_required"] is True
    assert state["coordinator_state"] == "maintenance_recovery_required"
    assert manager.maintenance_suspended is True
    assert manager.kpa500.connected is False
    assert manager.kat500.connected is False


def test_startup_recovery_cannot_reclaim_devices_during_maintenance(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)
    asyncio.run(station.enter_maintenance())
    calls.clear()

    with pytest.raises(StationActionError) as exc_info:
        asyncio.run(station.recover_safe_state())

    assert exc_info.value.code == "station-maintenance-active"
    assert calls == []


def test_maintenance_entry_cancels_active_tune_without_lock_deadlock(monkeypatch):
    station, calls, manager = build_station(monkeypatch, commissioned=True)
    manager.kat500.tune_states = [True] * 100

    async def exercise():
        await station.perform("prepare-route")
        await station.perform("tune")
        tune_task = station._active_task
        assert tune_task is not None
        for _ in range(100):
            if ("flex.tune", True) in calls:
                break
            await asyncio.sleep(0.01)
        state = await asyncio.wait_for(station.enter_maintenance(), timeout=2.0)
        await asyncio.gather(tune_task, return_exceptions=True)
        return state

    state = asyncio.run(exercise())

    assert state["maintenance"] is True
    assert state["transaction"]["state"] == "cancelled"
    assert ("kat.cancel_tune",) in calls
    assert not any(call[0] == "kat.store_memory" for call in calls)
    assert calls[-1] == ("manager.suspend",)


def test_station_maintenance_api_uses_only_coordinator_lifecycle(monkeypatch):
    station, _calls, _manager = build_station(monkeypatch, commissioned=True)
    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=station))
    app.include_router(router)

    with TestClient(app) as client:
        entered = client.post("/api/station/maintenance/enter")
        manager_refreshes_before = sum(call[0] == "manager.refresh" for call in _calls)
        state = client.get("/api/station/state?refresh=true")
        manager_refreshes_after = sum(call[0] == "manager.refresh" for call in _calls)
        exited = client.post("/api/station/maintenance/exit")

    assert entered.status_code == 200
    assert entered.json()["station_state"]["maintenance"] is True
    assert state.json()["station_state"]["coordinator_state"] == "maintenance"
    assert manager_refreshes_after == manager_refreshes_before
    assert exited.status_code == 200
    assert exited.json()["station_state"]["maintenance"] is False


def test_station_configuration_reconfigure_is_blocked_during_maintenance(monkeypatch):
    station, _calls, _manager = build_station(monkeypatch, commissioned=True)
    asyncio.run(station.enter_maintenance())
    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=station))
    app.include_router(server_control_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/config",
            json={"config": {"ELECRAFT_FOLLOW_RADIO": False}},
        )

    assert response.status_code == 423
    assert "maintenance mode" in response.json()["detail"]


def test_station_configuration_skips_guard_and_reconfigure_for_unchanged_values(monkeypatch):
    import backend.api.server_control as server_control
    import radio_control.elecraft as elecraft

    station, calls, _manager = build_station(monkeypatch, commissioned=True)
    monkeypatch.setattr(config, "ELECRAFT_FOLLOW_RADIO", True)
    saved = []
    reconfigured = []
    monkeypatch.setattr(
        server_control,
        "save_config_updates",
        lambda updates: saved.append(dict(updates)) or {
            "updated_keys": [], "app_settings_keys": [], "local_secret_keys": [],
            "rejected_keys": [],
        },
    )
    monkeypatch.setattr(
        elecraft,
        "get_elecraft_manager",
        lambda: type("Manager", (), {"reconfigure": lambda self: reconfigured.append(True)})(),
    )
    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=station))
    app.include_router(server_control_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/config",
            json={"config": {"ELECRAFT_FOLLOW_RADIO": True}},
        )

    assert response.status_code == 200
    assert response.json()["updated_keys"] == []
    assert saved == [{"ELECRAFT_FOLLOW_RADIO": True}]
    assert reconfigured == []
    assert calls == []


def test_digital_kpa_policy_change_is_guarded_as_a_route_change(monkeypatch):
    import backend.api.server_control as server_control

    station, calls, _manager = build_station(monkeypatch, commissioned=True)
    monkeypatch.setattr(config, "DIGITAL_KPA_POLICY", "operate")
    monkeypatch.setattr(
        server_control,
        "save_config_updates",
        lambda updates: {
            "updated_keys": sorted(updates),
            "app_settings_keys": sorted(updates),
            "local_secret_keys": [],
            "rejected_keys": [],
        },
    )
    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=station))
    app.include_router(server_control_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/config",
            json={"config": {"DIGITAL_KPA_POLICY": "standby"}},
        )

    assert response.status_code == 200
    assert config.DIGITAL_KPA_POLICY == "standby"
    assert ("kpa.operate", False) in calls
    assert calls.index(("flex.tx_state",)) < calls.index(("kpa.operate", False))


def test_station_configuration_rolls_back_persistence_and_live_config_on_reconfigure_failure(monkeypatch):
    import backend.api.server_control as server_control
    import radio_control.elecraft as elecraft

    station, _calls, _manager = build_station(monkeypatch, commissioned=True)
    monkeypatch.setattr(config, "ELECRAFT_FOLLOW_RADIO", True)
    persisted = []

    def fake_save(updates):
        persisted.append(dict(updates))
        return {
            "updated_keys": sorted(updates),
            "app_settings_keys": sorted(updates),
            "local_secret_keys": [],
            "rejected_keys": [],
        }

    class FailingManager:
        calls = 0

        async def reconfigure(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("serial reopen failed")

    failing_manager = FailingManager()
    monkeypatch.setattr(server_control, "save_config_updates", fake_save)
    monkeypatch.setattr(elecraft, "get_elecraft_manager", lambda: failing_manager)
    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=station))
    app.include_router(server_control_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/config",
            json={"config": {"ELECRAFT_FOLLOW_RADIO": False}},
        )

    assert response.status_code == 500
    assert config.ELECRAFT_FOLLOW_RADIO is True
    assert persisted == [
        {"ELECRAFT_FOLLOW_RADIO": False},
        {"ELECRAFT_FOLLOW_RADIO": True},
    ]
    assert failing_manager.calls == 2


@pytest.mark.parametrize(
    ("endpoint", "method_name", "action"),
    [
        (radio.toggle_mox, "set_mox", "mox"),
    ],
)
def test_raw_flex_guard_runs_only_for_tx_on(
    monkeypatch,
    endpoint,
    method_name,
    action,
):
    calls: list[tuple] = []

    class RawFlex:
        sock = object()

        def __getattr__(self, name):
            if name != method_name:
                raise AttributeError(name)

            def command(enabled):
                calls.append((name, enabled))
                return True

            return command

    async def guard(received_action, operation):
        calls.append(("guard", received_action))
        return operation()

    monkeypatch.setattr(radio.radio_control_state, "flex", RawFlex())
    monkeypatch.setattr(radio.radio_control_state, "station_tx_guard", guard)

    asyncio.run(endpoint(radio.ToggleRequest(enabled=True)))
    asyncio.run(endpoint(radio.ToggleRequest(enabled=False)))

    assert calls == [
        ("guard", action),
        (method_name, True),
        (method_name, False),
    ]


def test_raw_cwx_send_uses_atomic_station_preflight(monkeypatch):
    station, calls, _manager = build_station(monkeypatch, commissioned=True)
    sent = []

    assert asyncio.run(
        station.execute_raw_flex_tx("cwx", lambda: sent.append("CQ TEST") or True)
    ) is True

    assert sent == ["CQ TEST"]
    assert ("flex.readback", False) in calls
    assert ("kpa.readback",) in calls
    assert ("kat.readback",) in calls


@pytest.mark.parametrize(
    ("endpoint", "method_name"),
    [
        (radio.toggle_mox, "set_mox"),
    ],
)
def test_coordinator_refusal_prevents_raw_flex_tx_on(
    monkeypatch,
    endpoint,
    method_name,
):
    station, calls, _manager = build_station(monkeypatch, commissioned=False)
    flex = station.flex_provider()
    monkeypatch.setattr(radio.radio_control_state, "flex", flex)
    monkeypatch.setattr(
        radio.radio_control_state,
        "station_tx_guard",
        station.execute_raw_flex_tx,
    )

    with pytest.raises(HTTPException):
        asyncio.run(endpoint(radio.ToggleRequest(enabled=True)))

    assert ("flex.mox", True) not in calls
    assert ("flex.tune", True) not in calls
    assert not any(call[0] == method_name for call in calls)


def test_raw_flex_tune_on_is_retired_but_tune_off_remains_available(monkeypatch):
    calls: list[tuple] = []

    class RawFlex:
        sock = object()

        def set_tune(self, enabled):
            calls.append(("set_tune", enabled))
            return True

    monkeypatch.setattr(radio.radio_control_state, "flex", RawFlex())

    with pytest.raises(HTTPException) as rejected:
        asyncio.run(radio.toggle_tune(radio.ToggleRequest(enabled=True)))
    assert rejected.value.status_code == 410
    assert calls == []

    result = asyncio.run(radio.toggle_tune(radio.ToggleRequest(enabled=False)))
    assert result["tune"] is False
    assert calls == [("set_tune", False)]


def test_widget_preferences_persist_layout_and_per_orientation_size(tmp_path, monkeypatch):
    preferences_path = tmp_path / "station_widget.json"
    monkeypatch.setattr(station_api, "_WIDGET_PREFERENCES_PATH", preferences_path)
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        initial = client.get("/api/station/widget-preferences")
        assert initial.status_code == 200
        assert initial.json()["preferences"]["orientation"] == "horizontal"

        saved = client.put(
            "/api/station/widget-preferences",
            json={"orientation": "vertical", "width": 430, "height": 690},
        )
        assert saved.status_code == 200
        assert saved.json()["preferences"]["sizes"]["vertical"] == {"width": 430, "height": 690}
        assert preferences_path.exists()

        restored = client.get("/api/station/widget-preferences")
        assert restored.json()["preferences"]["orientation"] == "vertical"
        assert restored.json()["preferences"]["sizes"]["vertical"] == {"width": 430, "height": 690}

        incomplete = client.put(
            "/api/station/widget-preferences",
            json={"orientation": "vertical", "width": 430},
        )
        assert incomplete.status_code == 422
