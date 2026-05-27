"""Race/state tests for backend-owned DIGITAL FT8/FT4 automation."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401

from services.ft8_service import FT8Service, QSOSession, QSOState


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class FakeTxEngine:
    def __init__(self):
        self.aborted = False
        self.status = type("Status", (), {"available": True, "reason": "ok", "to_dict": lambda self: {"available": True}})()

    def abort(self):
        self.aborted = True

    def transmit(self, message, **_kwargs):
        return type("Result", (), {"message": message, "to_dict": lambda self: {"message": message}})()


class Decode:
    def __init__(self, message, *, snr=10, freq=1500, mode="FT8", timestamp="2026-05-27T00:00:00+00:00"):
        self.message = message
        self.snr = snr
        self.freq = freq
        self.mode = mode
        self.timestamp = timestamp

    def to_dict(self):
        return {
            "message": self.message,
            "snr": self.snr,
            "freq": self.freq,
            "mode": self.mode,
            "timestamp": self.timestamp,
        }


def service_with_tx(mode="FT8"):
    service = FT8Service(mode=mode, mycall="OM0RX", mygrid="JN88")
    service.tx_engine = FakeTxEngine()
    service.tx_capability_enabled = True
    return service


def test_manual_target_b_replaces_pending_target_a_atomically():
    service = service_with_tx()

    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))
    attempt_a = service.active_attempt_id
    asyncio.run(service.engage_target({"callsign": "K3ZK", "grid": "FN21", "mode": "FT8"}, source="manual_double_click"))

    assert attempt_a != service.active_attempt_id
    assert list(service.active_qsos) == ["K3ZK"]
    assert service.tx_queue == ["K3ZK OM0RX JN88"]
    assert service.pending_tx_intent["call"] == "K3ZK"
    assert service.pending_tx_intent["attempt_id"] == service.active_attempt_id
    assert all("EA1AA" not in message for message in service.tx_queue)


def test_engaging_new_target_invalidates_old_attempt_tx_and_callbacks():
    service = service_with_tx()
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))
    old_attempt = service.active_attempt_id
    asyncio.run(service.engage_target({"callsign": "K3ZK", "grid": "FN21", "mode": "FT8"}, source="manual_double_click"))

    asyncio.run(service.queue_tx_message("EA1AA OM0RX R+10", attempt_id=old_attempt))
    asyncio.run(service.transmit_message("EA1AA OM0RX R+10", attempt_id=old_attempt))

    assert service.active_attempt_id != old_attempt
    assert service.tx_queue == ["K3ZK OM0RX JN88"]
    assert any(decision["reason"].startswith("stale-") for decision in service.automation_decisions)


def test_directed_report_before_tx_replaces_stale_locator_with_report_reply():
    service = service_with_tx()
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))

    asyncio.run(service._auto_sequence_handler(Decode("OM0RX EA1AA -01", snr=13, freq=1706)))

    assert service.tx_queue == ["EA1AA OM0RX R+13"]
    assert service.active_qsos["EA1AA"].state == QSOState.SENDING_REPORT
    assert "EA1AA OM0RX JN88" not in service.tx_queue


def test_auto_call_collects_candidates_but_does_not_steal_manual_qso():
    service = service_with_tx()
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))
    active_attempt = service.active_attempt_id
    service.auto_call_enabled = True
    service.automation_controller.ingest_target({
        "callsign": "K3ZK",
        "band": "40m",
        "mode": "FT8",
        "heard": True,
        "dxcc_status": "ATNO",
    })

    asyncio.run(service._automation_tick())

    assert service.active_attempt_id == active_attempt
    assert list(service.active_qsos) == ["EA1AA"]
    assert service.tx_queue == ["EA1AA OM0RX JN88"]
    assert service.automation_status == "qso-active"


def test_auto_call_backend_engages_candidate_without_browser_tx_queue():
    service = service_with_tx()
    service.auto_call_enabled = True
    service.tx_enabled = True
    service._live_cycle_state = lambda: (15.0, 3.0, 123, False)
    service.automation_controller.apply_operator_settings({"automation": {"enabled": True, "allowedModes": {"FT8": True}}})
    service.automation_controller.ingest_target({
        "callsign": "K3ZK",
        "band": "40m",
        "mode": "FT8",
        "heard": True,
        "dxcc_status": "ATNO",
    })

    asyncio.run(service._automation_tick())

    assert list(service.active_qsos) == ["K3ZK"]
    assert service.pending_tx_intent["source"] == "auto_call"
    assert service.tx_queue == ["K3ZK OM0RX JN88"]


def test_stop_tx_aborts_current_attempt_but_later_reply_can_reengage_when_automation_armed():
    service = service_with_tx()
    service.auto_call_enabled = True
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))

    service.abort_current_attempt()

    assert service.tx_engine.aborted is True
    assert service.active_qsos == {}
    assert service.active_attempt_id is None
    assert service.tx_queue == []
    assert service.tx_enabled is True
    assert service.auto_sequence is True

    asyncio.run(service._auto_sequence_handler(Decode("OM0RX EA1AA -01", snr=9, freq=1706)))

    assert list(service.active_qsos) == ["EA1AA"]
    assert service.tx_queue == ["EA1AA OM0RX R+09"]


def test_abort_invalidates_all_pending_tx_for_attempt():
    service = service_with_tx()
    service.auto_call_enabled = True
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))
    old_attempt = service.active_attempt_id

    service.abort_current_attempt()
    asyncio.run(service.queue_tx_message("EA1AA OM0RX R+10", attempt_id=old_attempt))

    assert service.active_attempt_id is None
    assert service.pending_tx_intent is None
    assert service.tx_queue == []
    assert service.tx_message_attempt_ids == {}


def test_late_slot_cutoff_is_mode_specific_for_ft8_and_ft4():
    ft8 = service_with_tx("FT8")
    ft8.tx_enabled = True
    asyncio.run(ft8.queue_tx_message("EA1AA OM0RX JN88"))
    ft8._live_cycle_state = lambda: (15.0, 2.0, 123, True)

    assert asyncio.run(ft8.transmit_queued_now_if_possible(force_current_slot=True)) is False
    assert ft8.tx_queue == ["EA1AA OM0RX JN88"]

    ft4 = service_with_tx("FT4")
    ft4.tx_enabled = True
    asyncio.run(ft4.queue_tx_message("EA1AA OM0RX JN88"))
    ft4._live_cycle_state = lambda: (7.5, 0.5, 123, True)

    assert asyncio.run(ft4.transmit_queued_now_if_possible(force_current_slot=True)) is False
    assert ft4.tx_queue == ["EA1AA OM0RX JN88"]


def test_duplicate_rr73_or_73_completion_does_not_log_twice():
    service = service_with_tx()
    qso = QSOSession("EA1AA", "OM0RX", "JN88", state=QSOState.SENDING_73, status="waiting_for_reply")
    service.active_qsos[qso.their_call] = qso
    service.active_attempt_id = qso.attempt_id

    asyncio.run(service._complete_qso(qso))
    asyncio.run(service._complete_qso(qso))

    assert service.stats["qso_completed"] == 1
    assert qso.attempt_id in service.completed_attempt_ids


def test_stale_decode_and_log_callbacks_are_ignored():
    service = service_with_tx()
    qso = QSOSession("EA1AA", "OM0RX", "JN88", state=QSOState.WAITING_RESPONSE)
    stale_attempt = qso.attempt_id
    service.active_qsos["K3ZK"] = QSOSession("K3ZK", "OM0RX", "JN88")
    service.active_attempt_id = service.active_qsos["K3ZK"].attempt_id

    asyncio.run(service._update_qso_state(qso, Decode("OM0RX EA1AA -01", snr=11)))
    asyncio.run(service._complete_qso(qso))

    assert service.active_attempt_id != stale_attempt
    assert qso.state == QSOState.WAITING_RESPONSE
    assert service.stats["qso_completed"] == 0
    assert any(decision["reason"] in {"stale-attempt-reply", "stale-attempt-completion"} for decision in service.automation_decisions)


def test_backend_logging_is_idempotent_for_one_attempt():
    service = service_with_tx()
    service.enabled = True
    calls = []

    async def fake_log(qso):
        calls.append(qso.attempt_id)
        qso.logged = True
        qso.log_status = "logged"
        qso.log_result = {"success": True}

    service._log_completed_qso = fake_log
    qso = QSOSession("EA1AA", "OM0RX", "JN88", state=QSOState.SENDING_73, frequency=10.136)
    service.active_qsos[qso.their_call] = qso
    service.active_attempt_id = qso.attempt_id

    asyncio.run(service._complete_qso(qso))
    asyncio.run(service._complete_qso(qso))

    assert calls == [qso.attempt_id]
    assert service.stats["qso_completed"] == 1


def test_backend_logging_dedupe_survives_restart(monkeypatch, tmp_path):
    import services.qso_logging as qlog
    from services.qso_logging import QSORequest

    class FakeWavelog:
        def __init__(self):
            self.calls = 0

        async def log_qso(self, _qso):
            self.calls += 1
            return {"success": True, "message": "ok"}

    class FakeAdif:
        def __init__(self):
            self.calls = 0

        def add_qso(self, _qso):
            self.calls += 1
            return True

    fake_wavelog = FakeWavelog()
    fake_adif = FakeAdif()
    monkeypatch.setattr(qlog, "_dedupe_ledger_path", tmp_path / "qso_log_dedupe.json")
    monkeypatch.setattr(qlog, "wavelog_client", fake_wavelog)
    monkeypatch.setattr(qlog, "adif_handler", fake_adif)

    qso = QSORequest(
        callsign="EA1AA",
        frequency=10.136,
        band="30m",
        mode="FT8",
        rst_sent="R+10",
        rst_received="+01",
        date_time=datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc).isoformat(),
    )
    first = asyncio.run(qlog.log_qso(qso))
    # Simulate backend restart: in-memory attempt ids are gone, persistent ledger remains.
    second = asyncio.run(qlog.log_qso(qso))

    assert first["success"] is True
    assert second["duplicate"] is True
    assert fake_wavelog.calls == 1
    assert fake_adif.calls == 1


def test_backend_logging_dedupe_handles_missing_and_corrupt_file(monkeypatch, tmp_path):
    import services.qso_logging as qlog

    ledger_path = tmp_path / "qso_log_dedupe.json"
    monkeypatch.setattr(qlog, "_dedupe_ledger_path", ledger_path)

    assert qlog._dedupe_entry("missing") is None

    ledger_path.write_text("{not-json", encoding="utf-8")
    assert qlog._dedupe_entry("corrupt") is None

    qlog._record_dedupe_entry(
        "stable-key",
        {
            "callsign": "EA1AA",
            "frequency": 10.136,
            "band": "30m",
            "mode": "FT8",
            "date_time": "2026-05-27T12:00:00+00:00",
            "rst_sent": "R+10",
            "rst_received": "+01",
        },
        {"wavelog": {"success": True}, "adif_saved": True, "outbox_queued": False},
    )

    assert qlog._dedupe_entry("stable-key")["callsign"] == "EA1AA"
    assert not ledger_path.with_suffix(".json.tmp").exists()


def test_ft4_uses_same_backend_engage_path_with_ft4_timing():
    service = service_with_tx("FT4")

    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT4"}, source="manual_double_click"))

    assert service.mode == "FT4"
    assert service._cycle_duration_seconds() == 7.5
    assert list(service.active_qsos) == ["EA1AA"]
    assert service.pending_tx_intent["mode"] == "FT4"


def test_ft4_manual_tx_uses_mode_specific_cutoff():
    service = service_with_tx("FT4")
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT4"}, source="manual_double_click"))
    service._live_cycle_state = lambda: (7.5, 0.5, 123, True)

    assert asyncio.run(service.transmit_queued_now_if_possible(force_current_slot=True)) is False
    assert service.tx_queue == ["EA1AA OM0RX JN88"]


def test_clear_decoded_history_does_not_clear_active_qso_attempt():
    service = service_with_tx()
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))
    active_attempt = service.active_attempt_id
    service.decoded_messages.append(Decode("CQ K3ZK FN21"))

    service.clear_decoded_messages()

    assert service.decoded_messages == []
    assert service.active_attempt_id == active_attempt
    assert list(service.active_qsos) == ["EA1AA"]


def test_frontend_double_click_and_tx_buttons_use_backend_only_contract():
    modal = read_text("frontend/js/ft8-modal.js")
    template = read_text("frontend/templates/modal-ft8.html")

    assert "@dblclick.stop=\"ft8EngageQso(msg)\"" in template
    assert "'/api/ft8/automation/engage'" in modal
    assert "'/api/ft8/tx/manual'" in modal
    assert "'/api/ft8/transmit'" not in modal
    assert "'/api/qso/log'" not in modal
    assert "ft8MaybeAdvanceActiveQso" not in modal
    assert "ft8LogCompletedQso" not in modal
    assert "ft8QueueTxMessage" not in modal
    assert "Manual TX queued by backend" in modal
    assert "queue_message:" not in modal
    assert "activeAttemptId" in modal
    assert "pendingTxIntent" in modal
    assert "automationDecisions" in modal


def test_debug_panel_and_mode_aware_legacy_namespace_are_documented():
    api = read_text("backend/api/ft8.py")
    template = read_text("frontend/templates/modal-ft8.html")
    service = read_text("services/ft8_service.py")

    assert "Historical route namespace" in api
    assert "used for both FT8 and FT4 automation" in api
    assert "ft8-debug-strip" in template
    assert "State: {{ ft8.digitalState }}" in template
    assert "Attempt: {{ ft8.activeAttemptId.slice(0, 8) }}" in template
    assert "DIGITAL decision" in service
    assert "automation_decisions" in service
    assert '"mode": getattr(self, "mode", "")' in service
    assert '"active_target": getattr(active_qso, "their_call", None)' in service
    assert '"current_state": current_state' in service
    assert '"pending_tx_message": pending.get("message")' in service
    assert '"pending_tx_slot": pending.get("scheduled_slot_utc")' in service
    assert '"tx_active": bool(getattr(self, "tx_in_progress", False))' in service


def test_spots_db_lock_warning_is_frontend_degraded_not_retry_storm():
    spots_api = read_text("backend/api/spots.py")
    dx_spots = read_text("frontend/js/dx-spots.js")
    template = read_text("frontend/templates/dx-spots.html")

    assert '"warning": "spots database is locked by another process"' in spots_api
    assert "filteredSearchWarning" in dx_spots
    assert "filteredSearchRetryAfter = Date.now() + 30000" in dx_spots
    assert "this.lastSearchFilter = filterCriteria" in dx_spots
    assert "Showing live cached spots until the database is available" in template


def test_manual_tx_endpoint_is_backend_owned_and_cq_is_idle_only():
    service = service_with_tx()
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))

    try:
        asyncio.run(service.queue_manual_tx_button(6))
    except RuntimeError as exc:
        assert "idle state" in str(exc)
    else:
        raise AssertionError("CQ manual TX replaced an active QSO")

    assert list(service.active_qsos) == ["EA1AA"]
    assert service.tx_queue == ["EA1AA OM0RX JN88"]
