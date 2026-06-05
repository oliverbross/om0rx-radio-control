"""Runtime regressions for backend-owned FT8 Auto Call behavior."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import _bootstrap  # noqa: F401

from services.ft8_service import FT8Service


class FakeTxEngine:
    def __init__(self):
        self.aborted = False
        self.abort_count = 0
        self.transmitted = []
        self.status = type("Status", (), {"available": True, "reason": "ok", "to_dict": lambda self: {"available": True}})()

    def abort(self):
        self.aborted = True
        self.abort_count += 1

    def transmit(self, message, **_kwargs):
        self.transmitted.append(message)
        return type("Result", (), {"message": message, "to_dict": lambda self: {"message": message}})()


class ClockedService(FT8Service):
    def __init__(self):
        super().__init__(mode="FT8", mycall="OM0RX", mygrid="JN88")
        self.clock = datetime(2026, 5, 27, 0, 0, 0, tzinfo=timezone.utc)
        self.tx_engine = FakeTxEngine()
        self.tx_capability_enabled = True
        self._live_slot_is_tx = False

    def _now(self):
        return self.clock

    def advance(self, seconds):
        self.clock += timedelta(seconds=seconds)

    def _live_cycle_state(self):
        return 15.0, 3.0, 123, self._live_slot_is_tx


def configure_auto_call(service):
    service.watchdog_cycles["FT8"] = 1
    service.set_tx_options(auto_cq=False, auto_call=True, cq_only=True, watchdog_ft8=1)
    service.enable_tx()
    service.automation_controller.settings.avoid_logged = True
    service.automation_controller.settings.require_heard_before_call = True


def add_candidate(service, call, *, status="ATNO"):
    return service.automation_controller.ingest_target({
        "callsign": call,
        "band": "20m",
        "mode": "FT8",
        "message": f"CQ {call} JN88",
        "freq": 1500,
        "heard": True,
        "call_status": status,
        "dxcc_status": status,
    })


def test_auto_call_watchdog_expires_target_backs_off_and_rotates_without_tx6_cq():
    service = ClockedService()
    configure_auto_call(service)
    add_candidate(service, "EA1AA", status="ATNO")
    add_candidate(service, "K3ZK", status="New Call")

    asyncio.run(service._automation_tick())
    attempt_a = service.active_attempt_id
    watchdog_a = service.tx_watchdog_started_at

    assert service.pending_tx_intent["call"] == "EA1AA"
    assert service.pending_tx_intent["source"] == "auto_call"
    assert service.tx_queue == ["EA1AA OM0RX JN88"]
    assert watchdog_a == service.clock
    assert all("CQ OM0RX" not in message for message in service.tx_queue)

    service.advance(61)
    asyncio.run(service._automation_tick())

    assert service.active_attempt_id != attempt_a
    assert service.pending_tx_intent["call"] == "K3ZK"
    assert service.tx_queue == ["K3ZK OM0RX JN88"]
    assert service.tx_watchdog_started_at == service.clock
    assert any(entry["call"] == "EA1AA" for entry in service.get_stats()["target_backoff_list"])
    assert all("CQ OM0RX" not in message for message in service.tx_queue)


def test_clear_qso_aborts_pending_attempt_and_does_not_reengage_immediately():
    service = ClockedService()
    configure_auto_call(service)
    add_candidate(service, "EA1AA")
    add_candidate(service, "K3ZK", status="New Call")
    asyncio.run(service._automation_tick())

    service.clear_current_qso()

    stats = service.get_stats()
    assert stats["digital_state"] != "tx_pending"
    assert service.active_attempt_id is None
    assert service.active_qsos == {}
    assert service.tx_queue == []
    assert service.pending_tx_intent is None
    assert service.active_tx_message is None

    asyncio.run(service._automation_tick())

    assert service.active_attempt_id is None
    assert service.tx_queue == []
    assert service.automation_status == "auto-engage-paused"


def test_abort_qso_stop_tx_is_hard_stop_with_user_abort_inhibit():
    service = ClockedService()
    configure_auto_call(service)
    add_candidate(service, "EA1AA")
    asyncio.run(service._automation_tick())
    service.tx_in_progress = True

    service.abort_current_attempt()

    assert service.tx_engine.aborted is True
    assert service.tx_engine.abort_count == 1
    assert service.tx_enabled is False
    assert service.tx_inhibit_reason == "user_abort"
    assert service.active_attempt_id is None
    assert service.pending_tx_intent is None
    assert service.tx_queue == []
    assert service.active_tx_message is None

    service.tx_in_progress = False
    asyncio.run(service._automation_tick())

    assert service.active_attempt_id is None
    assert service.automation_status == "tx-inhibited: user_abort"


def test_auto_call_idle_search_has_inactive_watchdog_and_never_queues_cq():
    service = ClockedService()
    configure_auto_call(service)

    asyncio.run(service._automation_tick())

    stats = service.get_stats()
    assert service.active_attempt_id is None
    assert service.pending_tx_intent is None
    assert service.tx_queue == []
    assert service.active_tx_message is None
    assert stats["watchdog_active"] is False
    assert stats["watchdog_started_at"] is None
    assert stats["watchdog_remaining_seconds"] == 0
    assert "CQ OM0RX JN88" not in service.tx_queue


def test_auto_call_avoid_logged_rejects_worked_before_band_slot():
    service = ClockedService()
    configure_auto_call(service)
    band_slot = add_candidate(service, "EA1EQ", status="New Band")
    usable = add_candidate(service, "K3ZK", status="New Call")

    assert band_slot is None
    assert usable is not None

    asyncio.run(service._automation_tick())

    assert service.pending_tx_intent["call"] == "K3ZK"
    assert service.tx_queue == ["K3ZK OM0RX JN88"]


def test_auto_call_does_not_start_from_someone_else_exchange_when_cq_only_is_off():
    service = ClockedService()
    configure_auto_call(service)
    service.auto_call_cq_only = False
    ignored = service.automation_controller.ingest_target({
        "callsign": "OK1HEH",
        "band": "20m",
        "mode": "FT8",
        "message": "OK1HEH F1ICS R-07",
        "freq": 1500,
        "heard": True,
        "call_status": "ATNO",
        "dxcc_status": "ATNO",
        "source": "decoded",
    })
    add_candidate(service, "K3ZK", status="New Call")

    assert ignored is None

    asyncio.run(service._automation_tick())

    assert service.pending_tx_intent["call"] == "K3ZK"
    assert service.tx_queue == ["K3ZK OM0RX JN88"]
    assert all("OK1HEH" not in message for message in service.tx_queue)


def test_live_auto_call_attempt_is_not_abandoned_when_target_is_heard_elsewhere():
    service = ClockedService()
    configure_auto_call(service)
    add_candidate(service, "OZ9TAN", status="ATNO")
    add_candidate(service, "3G0Z", status="New Call")
    asyncio.run(service._automation_tick())

    attempt_id = service.active_attempt_id
    active_qso = next(iter(service.active_qsos.values()))
    active_call = active_qso.their_call
    service._backoff_active_target_if_busy_elsewhere(
        SimpleNamespace(message=f"{active_call} MW0RX -09")
    )

    assert service.active_attempt_id == attempt_id
    assert active_call in service.active_qsos
    assert service.pending_tx_intent["call"] == active_call
    assert service.automation_controller.status()["active_target"]["call"] == active_call

    asyncio.run(service._automation_tick())

    assert service.active_attempt_id == attempt_id
    assert service.automation_status == "qso-active"
    assert service.pending_tx_intent["call"] == active_call
