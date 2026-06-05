#!/usr/bin/env python3
"""Smoke checks for explicit service dependency state."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import _bootstrap  # noqa: F401

from services import background_tasks, radio
from services.digital_automation import DigitalAutomationController


async def noop_status(_payload):
    return None


async def noop_spots(_spots):
    return None


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
    assert service.wsjtx_ingested_decodes == 2
    assert len(service.wsjtx_seen_decode_keys) == 2
    assert {item["call"] for item in controller.status()["targets"]} == {"E51ABC", "EA1AA"}


if __name__ == "__main__":
    test_radio_control_dependency_state()
    test_background_task_dependency_state()
    print("Service dependency state smoke checks passed")
