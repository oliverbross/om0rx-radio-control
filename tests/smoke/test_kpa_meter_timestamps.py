"""KPA WS sample identity stays distinct from later status/readback traffic."""

import asyncio
import threading

import _bootstrap  # noqa: F401
import pytest

from radio_control import elecraft


class MeterSerial:
    def __init__(self, clock):
        self.clock = clock
        self.is_open = True
        self.pending = b""
        self.writes = []
        self.stop_event = None
        self.responses = {
            "^ON;": "^ON1;", "^OS;": "^OS1;", "^BN;": "^BN05;",
            "^FL;": "^FL00;", "^TM;": "^TM042;", "^VI;": "^VI500 025;",
            "^WS;": "^WS475 015;", "^RVM;": "^RVM01.23;",
        }

    @property
    def in_waiting(self):
        return len(self.pending)

    def write(self, payload):
        command = payload.decode("ascii")
        self.writes.append(command)
        self.clock["now"] = 199.0 if command == "^RVM;" else 105.0
        self.pending += (self.responses.get(command) or "").encode("ascii")
        if self.stop_event and command == "^VI;":
            self.stop_event.set()
        return len(payload)

    def read(self, size):
        result, self.pending = self.pending[:size], self.pending[size:]
        return result

    def flush(self):
        pass


@pytest.fixture
def meter_device(monkeypatch):
    clock = {"now": 100.0}
    serial = MeterSerial(clock)
    monkeypatch.setattr(elecraft.time, "time", lambda: clock["now"])
    device = elecraft.KPA500(
        "KPA500", "MOCK", 38400, serial_factory=lambda **_kwargs: serial, timeout=0.001
    )
    return device, serial, clock


@pytest.mark.parametrize("method", ["status", "meter_status"])
def test_ws_sample_time_is_its_query_completion_not_later_firmware(meter_device, method):
    device, serial, _clock = meter_device

    sample = getattr(device, method)()

    assert sample["output_power_w"] == 475
    assert sample["swr"] == 1.5
    assert sample["meter_complete"] is True
    assert sample["meter_sample_observed_at"] == 105.0
    assert sample["meter_observed_at"] == 105.0
    if method == "status":
        assert serial.writes[-1] == "^RVM;"
        assert sample["observed_at"] == device.last_seen == 199.0
    else:
        assert serial.writes == ["^WS;"]
        assert device.last_seen is None


@pytest.mark.parametrize("method", ["status", "meter_status"])
@pytest.mark.parametrize("response", [None, "^WS475;", "^WS475 1..5;"])
def test_failed_ws_read_has_no_reliable_timestamp(meter_device, method, response):
    device, serial, _clock = meter_device
    assert getattr(device, method)()["meter_complete"] is True
    serial.responses["^WS;"] = response

    sample = getattr(device, method)()

    assert sample["meter_sample_observed_at"] is None
    assert sample["meter_observed_at"] is None
    assert sample["meter_complete"] is False
    assert sample["swr_live"] is False
    assert sample["meter_error"]


@pytest.mark.parametrize("response", ["^WS475;", "^WS475 1..5;"])
def test_partial_query_result_is_not_stamped_as_a_valid_sample(meter_device, monkeypatch, response):
    device, _serial, _clock = meter_device
    monkeypatch.setattr(device, "query", lambda *_args, **_kwargs: response)

    sample = device.meter_status()

    assert sample["meter_sample_observed_at"] is None
    assert sample["meter_observed_at"] is None
    assert sample["meter_complete"] is False


def test_failed_firmware_query_does_not_invalidate_a_complete_ws_sample(meter_device):
    device, serial, _clock = meter_device
    serial.responses["^RVM;"] = None

    sample = device.status()

    assert "firmware" in sample["missing_fields"]
    assert sample["meter_complete"] is True
    assert sample["meter_sample_observed_at"] == 105.0
    assert sample["meter_observed_at"] == 105.0


@pytest.mark.parametrize("failure_path", ["status", "meters", "exception", "interrupted"])
def test_manager_failure_clears_cached_ws_identity(meter_device, monkeypatch, failure_path):
    device, serial, _clock = meter_device
    manager = elecraft.ElecraftManager(kpa500=device)
    try:
        initial = asyncio.run(manager.refresh_status())
        assert initial["kpa500"]["meter_sample_observed_at"] == 105.0
        serial.responses["^WS;"] = None
        if failure_path == "interrupted":
            serial.stop_event = manager._sync_requested
        elif failure_path == "exception":
            def fail():
                raise RuntimeError("Mock serial failure")
            monkeypatch.setattr(device, "meter_status", fail)
        operation = manager.refresh_status if failure_path in {"status", "interrupted"} else manager.refresh_meters

        failed = asyncio.run(operation())["kpa500"]

        assert failed["meter_sample_observed_at"] is None
        assert failed["meter_observed_at"] is None
        assert failed["meter_complete"] is False
        assert failed["swr_live"] is False
    finally:
        manager._executor.shutdown(wait=True)


@pytest.mark.parametrize("response", ["^ON0;", None])
def test_full_status_without_power_clears_old_meter_identity(meter_device, response):
    device, serial, _clock = meter_device
    manager = elecraft.ElecraftManager(kpa500=device)
    try:
        asyncio.run(manager.refresh_meters())
        serial.responses["^ON;"] = response

        sample = asyncio.run(manager.refresh_status())["kpa500"]

        assert sample["meter_sample_observed_at"] is None
        assert sample["meter_observed_at"] is None
        assert sample["meter_complete"] is False
    finally:
        manager._executor.shutdown(wait=True)


def test_cache_merges_keep_power_and_true_sample_time_together(meter_device):
    device, _serial, _clock = meter_device
    manager = elecraft.ElecraftManager(kpa500=device)
    try:
        older = device.status()
        newer = {**older, "output_power_w": 510, "meter_sample_observed_at": 110.0,
                 "meter_observed_at": 110.0}
        manager._merge_meter_sample("kpa500", newer)
        manager._merge_meter_sample("kpa500", older)
        # Exercise both snapshot branches and coordinator-only state updates.
        blank_snapshot = manager.snapshot()["kpa500"]
        assert blank_snapshot["output_power_w"] == 510
        assert blank_snapshot["meter_sample_observed_at"] == 110.0
        assert blank_snapshot["meter_observed_at"] == 110.0
        manager._status = {"kpa500": older}
        manager.record_kpa_operate_readback(False)
        state = asyncio.run(manager.publish_verified_readbacks(
            {"power": True, "operate": False, "observed_at": 250.0}, {}
        ))["kpa500"]
        assert state["observed_at"] == 250.0
        assert state["output_power_w"] == 510
        assert state["meter_sample_observed_at"] == 110.0
        assert state["meter_observed_at"] == 110.0
        invalidated = asyncio.run(manager.publish_verified_readbacks(
            {"meter_complete": False, "meter_sample_observed_at": None}, {}
        ))["kpa500"]
        assert invalidated["meter_sample_observed_at"] is None
        assert invalidated["meter_observed_at"] is None
    finally:
        manager._executor.shutdown(wait=True)


def test_partial_merge_cannot_pair_old_power_with_a_new_timestamp(meter_device):
    device, _serial, _clock = meter_device
    manager = elecraft.ElecraftManager(kpa500=device)
    try:
        manager._merge_meter_sample("kpa500", device.meter_status())
        manager._merge_meter_sample("kpa500", {
            "meter_complete": True, "meter_sample_observed_at": 200.0,
            "meter_observed_at": 200.0,
        })

        sample = manager.snapshot()["kpa500"]

        assert sample["meter_sample_observed_at"] is None
        assert sample["meter_observed_at"] is None
        assert sample["meter_complete"] is False
    finally:
        manager._executor.shutdown(wait=True)


def test_late_full_status_does_not_replace_a_newer_fast_meter_sample(meter_device):
    device, _serial, _clock = meter_device
    older = device.status()
    newer = {**older, "output_power_w": 510, "meter_sample_observed_at": 110.0,
             "meter_observed_at": 110.0}
    started, release = threading.Event(), threading.Event()

    class SlowFullStatus:
        connected = True
        io_enabled = True
        port = "MOCK"

        def status(self, _stop_event):
            started.set()
            assert release.wait(2), "Mock full status was not released"
            return older

        def meter_status(self):
            return newer

    manager = elecraft.ElecraftManager(kpa500=SlowFullStatus())

    async def exercise():
        pending = asyncio.create_task(manager.refresh_status())
        try:
            assert await asyncio.to_thread(started.wait, 1)
            fast = await manager.refresh_meters()
            assert fast["kpa500"]["output_power_w"] == 510
        finally:
            release.set()
        return await pending

    try:
        result = asyncio.run(exercise())["kpa500"]
        assert result["output_power_w"] == 510
        assert result["meter_sample_observed_at"] == 110.0
        assert result["meter_observed_at"] == 110.0
    finally:
        release.set()
        manager._executor.shutdown(wait=True)
