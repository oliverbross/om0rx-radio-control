#!/usr/bin/env python3
"""Smoke checks for explicit service dependency state."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import _bootstrap  # noqa: F401
import pytest

from services import background_tasks, radio
import services.digital_engine as digital_engine
from services.digital_automation import DigitalAutomationController


async def noop_status(_payload):
    return None


async def noop_spots(_spots):
    return None


@pytest.fixture(autouse=True)
def explicit_wsjtz_provider_for_legacy_planner_tests(tmp_path, monkeypatch):
    """Do not let the operator's live engine selection leak into smoke tests."""
    state_path = tmp_path / "digital_engine.json"
    monkeypatch.setattr(digital_engine, "STATE_PATH", state_path)
    digital_engine.atomic_write_json(state_path, {"provider": "wsjtz"})


def test_radio_control_dependency_state():
    sentinel_radio = object()
    original_flex = radio.radio_control_state.flex
    original_broadcast = radio.radio_control_state.broadcast_func
    try:
        state = radio.configure_radio_control(sentinel_radio, noop_status)

        assert state is radio.radio_control_state
        assert radio.get_radio_instance() is sentinel_radio
        assert radio.radio_control_state.broadcast_func is noop_status
    finally:
        radio.radio_control_state.flex = original_flex
        radio.radio_control_state.broadcast_func = original_broadcast


def test_sync_and_async_radio_io_share_one_thread_lock():
    events = []

    async def exercise():
        result = await radio.run_radio_io(lambda: events.append("async") or "ok")
        assert result == "ok"

    assert radio.run_radio_io_sync(lambda: events.append("sync") or 1) == 1
    asyncio.run(exercise())
    assert events == ["sync", "async"]


def test_cancelled_radio_io_waiter_never_executes_later():
    calls = []

    async def exercise():
        radio._radio_io_lock.acquire()
        try:
            task = asyncio.create_task(
                radio.run_radio_io(lambda: calls.append("late-tx-on") or True)
            )
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            radio._radio_io_lock.release()
        # Give the executor worker enough time to acquire the released lock and
        # observe the cancellation marker before it could run the operation.
        await asyncio.sleep(0.1)

    asyncio.run(exercise())
    assert calls == []


def test_radio_io_admission_timeout_never_executes_later():
    calls = []

    async def exercise():
        radio._radio_io_lock.acquire()
        try:
            with pytest.raises(TimeoutError):
                await radio.run_radio_io(
                    lambda: calls.append("late-command") or True,
                    timeout=0.05,
                )
        finally:
            radio._radio_io_lock.release()
        await asyncio.sleep(0.1)

    asyncio.run(exercise())
    assert calls == []


def test_background_task_dependency_state():
    context = SimpleNamespace(
        flex=None,
        dx_spots_cache=[],
        cluster_client=None,
        cluster_connected=False,
        cty_resolver=None,
        classifier=None,
        wavelog_sync_manager=None,
        sync_status={},
    )
    service = background_tasks.configure_background_tasks(context, noop_status, noop_spots)
    status = background_tasks.get_background_task_status()

    assert background_tasks.get_background_task_service() is service
    assert service.context is context
    assert status["total_tasks"] == 0
    assert status["running_tasks"] == 0


def test_wsjtx_decode_status_builds_automation_payload():
    payload = background_tasks.build_wsjtx_decode_automation_payload({
        "stats": {
            "lastStatus": {"dialFrequency": 10_136_000, "mode": "FT8"},
            "lastDecode": {
                "isNew": True,
                "time": 9_360_000,
                "deltaFrequency": 822,
                "snr": -21,
                "mode": "~",
                "message": "CQ 3A2MW JN33",
                "dialFrequency": 10_136_000,
                "ts": 12345,
            },
        }
    })

    assert payload is not None
    assert payload["source"] == "decoded"
    assert payload["decoder_source"] == "wsjtx"
    assert payload["message"] == "CQ 3A2MW JN33"
    assert payload["mode"] == "FT8"
    assert payload["band"] == "30m"
    assert payload["frequency_mhz"] == 10.136
    assert payload["dial_frequency"] == 10_136_000
    assert payload["freq"] == 822
    assert payload["audio_offset"] == 822
    assert payload["snr"] == -21


def test_wsjtx_decode_status_ignores_non_new_decode():
    payload = background_tasks.build_wsjtx_decode_automation_payload({
        "stats": {
            "lastStatus": {"dialFrequency": 14_074_000, "mode": "FT8"},
            "lastDecode": {
                "isNew": False,
                "time": 10_000,
                "message": "CQ EA1AA IN80",
            },
        }
    })

    assert payload is None


def test_wsjtx_decode_ingest_feeds_automation_ranker(monkeypatch):
    import services.ft8_service as ft8_service_module
    import services.wsjtx as wsjtx_module

    class FakeCtyResolver:
        def lookup(self, callsign):
            if callsign == "E51ABC":
                return {"country": "South Cook Islands", "dxcc": 234, "continent": "OC", "cq": 32, "itu": 63}
            return {}

    class FakeQsoStatusStore:
        def call_flags(self, callsign, band, mode):
            return (False, False, True, True, False)

        def dxcc_overall(self, dxcc):
            return (False, False)

        def dxcc_bandmode_flags(self, dxcc, band, mode):
            return (True, True, False)

        def grid_flags(self, grid, band, mode):
            return (False, False, False)

    context = SimpleNamespace(
        flex=None,
        dx_spots_cache=[],
        cluster_client=None,
        cluster_connected=False,
        cty_resolver=FakeCtyResolver(),
        classifier=SimpleNamespace(qso_status_store=FakeQsoStatusStore()),
        wavelog_sync_manager=None,
        sync_status={},
    )
    background_tasks.configure_background_tasks(context, noop_status, noop_spots)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    controller = DigitalAutomationController(mycall="OM0RX")
    fake_ft8_service = SimpleNamespace(automation_controller=controller)
    fake_wsjtx_service = SimpleNamespace(
        get_bridge_status=lambda: {
            "success": True,
            "stats": {
                "lastDecodeAgeMs": 500,
                "lastStatus": {"dialFrequency": 14_074_000, "mode": "FT8"},
                "lastDecode": {
                    "isNew": True,
                    "time": 36_000_000,
                    "deltaFrequency": 1220,
                    "snr": -8,
                    "message": "CQ E51ABC BG08",
                    "dialFrequency": 14_074_000,
                    "ts": now_ms,
                },
            },
        }
    )
    monkeypatch.setattr(ft8_service_module, "get_ft8_service", lambda: fake_ft8_service)
    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: fake_wsjtx_service)

    target = asyncio.run(background_tasks.ingest_latest_wsjtx_decode_once())

    assert target is not None
    assert target["call"] == "E51ABC"
    assert target["mode"] == "FT8"
    assert target["band"] == "20m"
    assert target["source"] == "decoded"
    assert target["message"] == "CQ E51ABC BG08"
    assert controller.status()["eligible_count"] == 1


def test_wsjtx_decode_ingest_drains_recent_decode_buffer(monkeypatch):
    import services.ft8_service as ft8_service_module
    import services.wsjtx as wsjtx_module

    context = SimpleNamespace(
        flex=None,
        dx_spots_cache=[],
        cluster_client=None,
        cluster_connected=False,
        cty_resolver=None,
        classifier=None,
        wavelog_sync_manager=None,
        sync_status={},
    )
    service = background_tasks.configure_background_tasks(context, noop_status, noop_spots)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {"treat73AsCQ": True}})
    fake_ft8_service = SimpleNamespace(automation_controller=controller)
    fake_wsjtx_service = SimpleNamespace(
        get_bridge_status=lambda: {
            "success": True,
            "stats": {
                "lastDecodeAgeMs": 500,
                "lastStatus": {"dialFrequency": 14_074_000, "mode": "FT8"},
                "recentDecodes": [
                    {
                        "isNew": True,
                        "time": 36_000_000,
                        "deltaFrequency": 1220,
                        "snr": -8,
                        "message": "CQ E51ABC BG08",
                        "dialFrequency": 14_074_000,
                        "ts": now_ms,
                    },
                    {
                        "isNew": True,
                        "time": 36_015_000,
                        "deltaFrequency": 1420,
                        "snr": -5,
                        "message": "EA1AA K1ABC 73",
                        "dialFrequency": 14_074_000,
                        "ts": now_ms + 1,
                    },
                ],
            },
        }
    )
    monkeypatch.setattr(ft8_service_module, "get_ft8_service", lambda: fake_ft8_service)
    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: fake_wsjtx_service)

    target = asyncio.run(background_tasks.ingest_latest_wsjtx_decode_once())

    assert target is not None
    assert service.wsjtx_ingested_decodes == 1
    assert len(service.wsjtx_seen_decode_keys) == 2
    assert {item["call"] for item in controller.status()["targets"]} == {"E51ABC"}


def test_wsjtx_planner_runs_automatically_when_idle(monkeypatch):
    import services.ft8_service as ft8_service_module
    import services.wsjtx as wsjtx_module

    context = SimpleNamespace(classifier=None, cty_resolver=None)
    service = background_tasks.configure_background_tasks(context, noop_status, noop_spots)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {
        "enabled": True, "spotHuntEnabled": True, "bandHopping": True,
    }})
    monkeypatch.setattr(
        ft8_service_module,
        "get_ft8_service",
        lambda: SimpleNamespace(automation_controller=controller),
    )
    monkeypatch.setattr(
        wsjtx_module,
        "get_wsjtx_service",
        lambda: SimpleNamespace(get_bridge_status=lambda: {
            "stats": {"lastStatus": {"mode": "FT8", "band": "20m", "qsoState": "idle"}},
        }),
    )
    posted = []
    monkeypatch.setattr(
        background_tasks,
        "_post_wsjtx_planner_tick",
        lambda payload: posted.append(payload) or {"success": True, "action": "idle"},
    )

    result = asyncio.run(background_tasks.run_wsjtx_automation_planner_once())

    assert result["action"] == "idle"
    assert posted[0]["automation"]["autoCall"] is True
    assert posted[0]["automation"]["watchdogFT8"] == 2
    assert service.wsjtx_planner_last_error is None


def test_wsjtx_planner_defers_priority_until_current_qso_finishes(monkeypatch):
    import services.ft8_service as ft8_service_module
    import services.wsjtx as wsjtx_module

    context = SimpleNamespace(classifier=None, cty_resolver=None)
    background_tasks.configure_background_tasks(context, noop_status, noop_spots)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {"enabled": True}})
    monkeypatch.setattr(
        ft8_service_module,
        "get_ft8_service",
        lambda: SimpleNamespace(automation_controller=controller),
    )
    monkeypatch.setattr(
        wsjtx_module,
        "get_wsjtx_service",
        lambda: SimpleNamespace(get_bridge_status=lambda: {
            "stats": {
                "lastStatus": {"mode": "FT8", "band": "20m", "qsoState": "in_qso"},
                "lastStatusAgeMs": 1_000,
            },
        }),
    )
    monkeypatch.setattr(
        background_tasks,
        "_post_wsjtx_planner_tick",
        lambda _payload: (_ for _ in ()).throw(AssertionError("planner must defer")),
    )

    result = asyncio.run(background_tasks.run_wsjtx_automation_planner_once())

    assert result == {"success": True, "action": "deferred", "reason": "finish-current-qso"}


def test_wsjtx_planner_ignores_stale_busy_status_and_resumes(monkeypatch):
    import services.ft8_service as ft8_service_module
    import services.wsjtx as wsjtx_module

    context = SimpleNamespace(classifier=None, cty_resolver=None)
    background_tasks.configure_background_tasks(context, noop_status, noop_spots)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {"enabled": True, "bandHopping": True}})
    controller.transition_active_qso("calling", reason="old-wsjtz-heartbeat")
    monkeypatch.setattr(
        ft8_service_module,
        "get_ft8_service",
        lambda: SimpleNamespace(automation_controller=controller),
    )
    monkeypatch.setattr(
        wsjtx_module,
        "get_wsjtx_service",
        lambda: SimpleNamespace(get_bridge_status=lambda: {
            "stats": {
                "lastStatus": {
                    "mode": "FT8",
                    "band": "20m",
                    "qsoState": "calling",
                    "txEnabled": False,
                    "transmitting": True,
                },
                "lastStatusAgeMs": 180_000,
            },
        }),
    )
    posted = []
    monkeypatch.setattr(
        background_tasks,
        "_post_wsjtx_planner_tick",
        lambda payload: posted.append(payload) or {"success": True, "action": "idle"},
    )

    result = asyncio.run(background_tasks.run_wsjtx_automation_planner_once())

    assert result["action"] == "idle"
    assert posted
    assert controller.active_qso_state == "idle"
    assert controller.last_decision["reason"] == "stale-wsjtx-status"


if __name__ == "__main__":
    test_radio_control_dependency_state()
    test_background_task_dependency_state()
    print("Service dependency state smoke checks passed")
