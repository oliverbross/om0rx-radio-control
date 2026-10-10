"""Race/state tests for backend-owned DIGITAL FT8/FT4 automation."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np

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


def test_directed_report_preempts_stale_locator_already_transmitting():
    service = service_with_tx()
    asyncio.run(service.engage_target({"callsign": "RA9LL", "grid": "MO27", "mode": "FT8"}, source="manual_double_click"))
    qso = service.active_qsos["RA9LL"]
    qso.tx_count = 1
    service.tx_queue.clear()
    service.active_tx_message = "RA9LL OM0RX JN88"
    service.current_tx_message = "RA9LL OM0RX JN88"
    service.tx_in_progress = True

    asyncio.run(service._auto_sequence_handler(Decode("OM0RX RA9LL -11", snr=18, freq=2691)))

    assert service.tx_engine.aborted is True
    assert service._restart_tx_after_abort is True
    assert service.active_tx_message == "RA9LL OM0RX R+18"
    assert service.tx_queue == ["RA9LL OM0RX R+18"]
    assert service.active_qsos["RA9LL"].state == QSOState.SENDING_REPORT


def test_repeated_plain_report_does_not_rewrite_queued_roger_report():
    service = service_with_tx()
    asyncio.run(service.engage_target({"callsign": "RA9LL", "grid": "MO27", "mode": "FT8"}, source="manual_double_click"))
    asyncio.run(service._auto_sequence_handler(Decode("OM0RX RA9LL -11", snr=18, freq=2691)))
    service.tx_queue.clear()

    asyncio.run(service._auto_sequence_handler(Decode("OM0RX RA9LL -11", snr=8, freq=2691)))

    assert service.active_qsos["RA9LL"].my_report == "+18"
    assert service.tx_queue == ["RA9LL OM0RX R+18"]


def test_auto_call_collects_candidates_but_does_not_steal_manual_qso():
    service = service_with_tx()
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))
    active_attempt = service.active_attempt_id
    service.auto_call_enabled = True
    service.automation_controller.ingest_target({
        "callsign": "K3ZK",
        "band": "40m",
        "mode": "FT8",
        "message": "CQ K3ZK FN20",
        "source": "decoded",
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
        "message": "CQ K3ZK FN20",
        "source": "decoded",
        "heard": True,
        "dxcc_status": "ATNO",
    })

    asyncio.run(service._automation_tick())

    assert list(service.active_qsos) == ["K3ZK"]
    assert service.pending_tx_intent["source"] == "auto_call"
    assert service.tx_queue == ["K3ZK OM0RX JN88"]


def test_stop_tx_aborts_current_attempt_and_requires_rearm_before_reengage():
    service = service_with_tx()
    service.auto_call_enabled = True
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))

    service.abort_current_attempt()

    assert service.tx_engine.aborted is True
    assert service.active_qsos == {}
    assert service.active_attempt_id is None
    assert service.tx_queue == []
    assert service.tx_enabled is False
    assert service.auto_sequence is False
    assert service.tx_inhibit_reason == "user_abort"

    asyncio.run(service._auto_sequence_handler(Decode("OM0RX EA1AA -01", snr=9, freq=1706)))

    assert service.active_qsos == {}
    assert service.tx_queue == []


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
    ft8._live_cycle_state = lambda: (15.0, 0.3, 123, True)

    assert asyncio.run(ft8.transmit_queued_now_if_possible(force_current_slot=True)) is True
    assert ft8.tx_queue == []

    ft8_late = service_with_tx("FT8")
    ft8_late.tx_enabled = True
    asyncio.run(ft8_late.queue_tx_message("EA1AA OM0RX JN88"))
    ft8_late._live_cycle_state = lambda: (15.0, 0.5, 123, True)

    assert asyncio.run(ft8_late.transmit_queued_now_if_possible(force_current_slot=True)) is False
    assert ft8_late.tx_queue == ["EA1AA OM0RX JN88"]

    ft4 = service_with_tx("FT4")
    ft4.tx_enabled = True
    asyncio.run(ft4.queue_tx_message("EA1AA OM0RX JN88"))
    ft4._live_cycle_state = lambda: (7.5, 0.1, 123, True)

    assert asyncio.run(ft4.transmit_queued_now_if_possible(force_current_slot=True)) is True
    assert ft4.tx_queue == []

    ft4_late = service_with_tx("FT4")
    ft4_late.tx_enabled = True
    asyncio.run(ft4_late.queue_tx_message("EA1AA OM0RX JN88"))
    ft4_late._live_cycle_state = lambda: (7.5, 1.0, 123, True)

    assert asyncio.run(ft4_late.transmit_queued_now_if_possible(force_current_slot=True)) is False
    assert ft4_late.tx_queue == ["EA1AA OM0RX JN88"]


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


def test_manual_watchdog_expiry_clears_attempt_and_disarms_tx():
    service = service_with_tx()
    now = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
    service._now = lambda: now
    service.watchdog_cycles["FT8"] = 1
    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="manual_double_click"))
    service.tx_watchdog_started_at = now - timedelta(seconds=61)

    assert service._expire_watchdog_if_due() is True
    assert service.tx_enabled is False
    assert service.active_attempt_id is None
    assert service.active_qsos == {}
    assert service.tx_queue == []
    assert service.pending_tx_intent is None
    assert service.last_cancel_abort_reason == "watchdog-expired"


def test_transmitted_rr73_completes_qso_and_does_not_repeat_final_message():
    service = service_with_tx()
    calls = []

    async def fake_log(qso):
        calls.append(qso.their_call)
        qso.logged = True
        qso.log_status = "logged"

    service.enabled = True
    service._log_completed_qso = fake_log
    qso = QSOSession("EA1AA", "OM0RX", "JN88", state=QSOState.SENDING_RRR, frequency=21.074)
    service.active_qsos[qso.their_call] = qso
    service.active_attempt_id = qso.attempt_id
    service.tx_enabled = True
    service.auto_sequence = True
    service.active_tx_message = "EA1AA OM0RX RR73"
    service.tx_queue.append("EA1AA OM0RX RR73")

    asyncio.run(service.transmit_message("EA1AA OM0RX RR73", attempt_id=qso.attempt_id))

    assert calls == ["EA1AA"]
    assert service.stats["qso_completed"] == 1
    assert service.active_qsos == {}
    assert service.active_attempt_id is None
    assert service.active_tx_message is None
    assert service.tx_queue == []
    assert service.tx_watchdog_started_at is None


def test_backend_log_completed_qso_uses_started_at_timestamp(monkeypatch):
    import services.qso_logging as qlog

    captured = {}

    async def fake_log_qso(qso_request):
        captured["date_time"] = qso_request.date_time
        captured["callsign"] = qso_request.callsign
        return {"success": True, "message": "ok"}

    monkeypatch.setattr(qlog, "log_qso", fake_log_qso)

    service = service_with_tx()
    qso = QSOSession(
        "EA1AA",
        "OM0RX",
        "JN88",
        state=QSOState.COMPLETE,
        frequency=21.074,
        started_at=datetime(2026, 5, 27, 12, 34, 56, tzinfo=timezone.utc),
    )

    asyncio.run(service._log_completed_qso(qso))

    assert qso.log_status == "logged"
    assert captured["callsign"] == "EA1AA"
    assert captured["date_time"].startswith("2026-05-27T12:34:56")


def test_auto_call_limit_counts_repeated_unanswered_rf_attempts():
    service = service_with_tx()
    service.set_tx_options(auto_call=True, auto_call_limit=3)
    service.automation_controller.settings.max_attempts_per_target = 3

    asyncio.run(service.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT8"}, source="auto_call"))

    assert service.auto_call_remaining == 2

    asyncio.run(service._handle_tx_cycle())
    asyncio.run(service._handle_tx_cycle())
    asyncio.run(service._handle_tx_cycle())

    qso = service.active_qsos["EA1AA"]
    assert service.stats["transmitted_count"] == 3
    assert qso.tx_count == 3
    assert qso.rx_count == 0
    assert service.auto_call_remaining == 0

    asyncio.run(service._handle_tx_cycle())

    assert service.stats["transmitted_count"] == 3
    assert service.tx_enabled is True
    assert service.auto_call_enabled is True
    assert service.auto_call_remaining == 3
    assert service.active_qsos == {}
    assert service.tx_queue == []
    assert service.tx_status == "max call attempts reached; backed off EA1AA; searching next target"


def test_backend_logging_dedupe_survives_restart(monkeypatch, tmp_path):
    import services.qso_logging as qlog
    from services.qso_logging import QSORequest

    class FakeQRZ:
        async def lookup(self, _callsign):
            return {"success": False}

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
    monkeypatch.setattr(qlog, "qrz_client", FakeQRZ())

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


def test_outbox_pending_never_enters_wavelog_authoritative_read_cache(monkeypatch, tmp_path):
    import services.qso_logging as qlog
    from services.qso_logging import QSORequest

    class OfflineWavelog:
        async def log_qso(self, _qso):
            return {"success": False, "message": "offline"}

    class FakeAdif:
        def add_qso(self, _qso):
            return True

    class FakeOutbox:
        def enqueue(self, _qso, reason=""):
            return True

        def status(self):
            return {"queued": 1}

    authoritative_cache_writes = []
    monkeypatch.setattr(qlog, "_dedupe_ledger_path", tmp_path / "qso_log_dedupe.json")
    monkeypatch.setattr(qlog, "_pending_dedupe_claims", {})
    monkeypatch.setattr(qlog, "wavelog_client", OfflineWavelog())
    monkeypatch.setattr(qlog, "adif_handler", FakeAdif())
    monkeypatch.setattr(qlog, "qrz_client", None)
    monkeypatch.setattr(qlog, "get_qso_outbox", lambda: FakeOutbox())
    monkeypatch.setattr(
        qlog, "record_qso_in_local_read_cache",
        lambda qso: authoritative_cache_writes.append(dict(qso)),
    )

    request = QSORequest(
        callsign="OM1AA", frequency=14.074, band="20m", mode="FT8",
        date_time="2026-10-04T12:00:00+00:00",
        notes="Completed in built-in digital",
    )
    first = asyncio.run(qlog.log_qso(request))
    # Simulate restart: only the durable outbox/dedupe entry remains.
    qlog._pending_dedupe_claims.clear()
    second = asyncio.run(qlog.log_qso(request))

    assert first["outbox_queued"] is True
    assert first["wavelog"]["success"] is False
    assert second["duplicate"] is True
    assert second["dedupe"]["wavelog_success"] is False
    assert second["wavelog"]["success"] is False
    assert authoritative_cache_writes == []


def test_backend_logging_does_not_collapse_legitimate_repeat_across_seconds(monkeypatch, tmp_path):
    import services.qso_logging as qlog
    from services.qso_logging import QSORequest

    class FakeQRZ:
        async def lookup(self, _callsign):
            return {"success": False}

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
    monkeypatch.setattr(qlog, "_pending_dedupe_claims", {})
    monkeypatch.setattr(qlog, "wavelog_client", fake_wavelog)
    monkeypatch.setattr(qlog, "adif_handler", fake_adif)
    monkeypatch.setattr(qlog, "qrz_client", FakeQRZ())

    first = QSORequest(
        callsign="CT1EOZ",
        frequency=18.100,
        band="17m",
        mode="FT8",
        rst_sent="-15",
        rst_received="-15",
        date_time=datetime(2026, 6, 6, 12, 29, 59, tzinfo=timezone.utc).isoformat(),
    )
    second = QSORequest(
        callsign="CT1EOZ",
        frequency=18.1015,
        band="17m",
        mode="FT8",
        rst_sent="-15",
        rst_received="-15",
        date_time=datetime(2026, 6, 6, 12, 30, 1, tzinfo=timezone.utc).isoformat(),
    )

    first_result = asyncio.run(qlog.log_qso(first))
    qlog._pending_dedupe_claims.clear()
    second_result = asyncio.run(qlog.log_qso(second))

    assert first_result["success"] is True
    assert second_result.get("duplicate") is not True
    assert fake_wavelog.calls == 2
    assert fake_adif.calls == 2


def test_backend_logging_skips_when_recent_wavelog_row_exists(monkeypatch, tmp_path):
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
    monkeypatch.setattr(qlog, "_pending_dedupe_claims", {})
    class ExactReadback:
        def find_exact_qso(self, identity, station_id=1):
            assert identity["call"] == "M6OTU"
            return {"verified": True, "matches": [{
                "id": 123, "band": "12m", "mode": "FT8", "submode": "",
            }]}

    monkeypatch.setattr(qlog, "get_wavelog_log_service", lambda: ExactReadback())
    monkeypatch.setattr(qlog, "wavelog_client", fake_wavelog)
    monkeypatch.setattr(qlog, "adif_handler", fake_adif)
    monkeypatch.setattr(qlog, "qrz_client", None)

    result = asyncio.run(qlog.log_qso(QSORequest(
        callsign="M6OTU",
        frequency=24.915,
        band="12m",
        mode="FT8",
        rst_sent="-10",
        rst_received="-07",
        notes="Completed in built-in DIGITAL",
        date_time=datetime(2026, 6, 5, 10, 42, 16, tzinfo=timezone.utc).isoformat(),
    )))

    assert result["success"] is True
    assert result["duplicate"] is True
    assert fake_wavelog.calls == 0
    assert fake_adif.calls == 1
    assert result["adif_saved"] is True


def test_wavelog_exact_readback_requires_time_off_when_identity_supplies_it(monkeypatch):
    from services.wavelog_log import WavelogLogService

    class Cursor:
        def __init__(self, rows):
            self.rows = rows
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, *_args):
            return None
        def fetchall(self):
            return self.rows

    class Connection:
        def __init__(self, rows):
            self.rows = rows
        def cursor(self):
            return Cursor(self.rows)
        def close(self):
            return None

    expected_on = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
    expected_off = datetime(2026, 10, 4, 12, 0, 15, tzinfo=timezone.utc)
    base_row = {
        "id": 99, "time_on": expected_on.replace(tzinfo=None),
        "time_off": None, "callsign": "A1AA", "frequency_hz": 14_074_000,
        "band": "20m", "mode": "FT8", "submode": None,
        "station_callsign": "OM0RX", "station_id": 1,
    }
    service = WavelogLogService()
    monkeypatch.setattr(service, "_get_connection", lambda: Connection([base_row]))
    identity = {
        "call": "A1AA", "mode": "FT8", "station_callsign": "OM0RX",
        "frequency_hz": 14_074_000, "time_on_utc": expected_on,
        "time_off_utc": expected_off,
    }
    assert service.find_exact_qso(identity)["verified"] is False

    complete = {**base_row, "time_off": expected_off.replace(tzinfo=None)}
    monkeypatch.setattr(service, "_get_connection", lambda: Connection([complete]))
    assert service.find_exact_qso(identity)["verified"] is True

    mhz = {**complete, "frequency_hz": 14.074049}
    monkeypatch.setattr(service, "_get_connection", lambda: Connection([mhz]))
    assert service.find_exact_qso(identity)["verified"] is True

    outside_tolerance = {**complete, "frequency_hz": 14.074051}
    monkeypatch.setattr(service, "_get_connection", lambda: Connection([outside_tolerance]))
    assert service.find_exact_qso(identity)["verified"] is False

    monkeypatch.setattr(service, "_get_connection", lambda: Connection([complete, mhz]))
    ambiguous = service.find_exact_qso(identity)
    assert ambiguous["verified"] is False
    assert ambiguous["reason"] == "exact-match-ambiguous"


def test_qso_logging_enriches_missing_fields_from_qrz(monkeypatch):
    import services.qso_logging as qlog
    from services.qso_logging import QSORequest

    captured = {}

    class FakeQRZ:
        async def lookup(self, callsign):
            return {
                "success": True,
                "fname": "Example Operator",
                "grid": "IN80",
                "state": "MD",
                "country": "Spain",
                "cqzone": "14",
                "ituzone": "37",
                "email": f"{callsign.lower()}@example.invalid",
                "lotw": True,
            }

    class FakeWavelog:
        async def log_qso(self, qso):
            captured["wavelog"] = qso
            return {"success": True, "message": "ok"}

    class FakeAdif:
        def add_qso(self, qso):
            captured["adif"] = qso
            return True

    monkeypatch.setattr(qlog, "_dedupe_ledger_path", None)
    monkeypatch.setattr(qlog, "_dedupe_entry", lambda _key: None)
    monkeypatch.setattr(qlog, "_record_dedupe_entry", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(qlog, "qrz_client", FakeQRZ())
    monkeypatch.setattr(qlog, "wavelog_client", FakeWavelog())
    monkeypatch.setattr(qlog, "adif_handler", FakeAdif())
    monkeypatch.setattr(qlog, "qso_status_store", None)

    qso = QSORequest(
        callsign="EG53DMM",
        frequency=7.074,
        band="40m",
        mode="FT8",
        rst_sent="-12",
        rst_received="+02",
        date_time=datetime(2026, 6, 3, 1, 0, tzinfo=timezone.utc).isoformat(),
    )

    result = asyncio.run(qlog.log_qso(qso))

    assert result["success"] is True
    assert captured["wavelog"]["name"] == "Example Operator"
    assert captured["wavelog"]["gridsquare"] == "IN80"
    assert captured["wavelog"]["country"] == "Spain"
    assert captured["wavelog"]["cq_zone"] == 14
    assert captured["wavelog"]["itu_zone"] == 37
    assert captured["wavelog"]["lotw_member"] is True


def test_qso_logging_updates_hot_status_cache(monkeypatch):
    import services.qso_logging as qlog
    from services.qso_logging import QSORequest

    recorded = []

    class FakeWavelog:
        async def log_qso(self, _qso):
            return {"success": True, "message": "ok"}

    class FakeAdif:
        def add_qso(self, _qso):
            return True

    class FakeStatusStore:
        def record_qso(self, qso):
            recorded.append(dict(qso))
            return True

    class FakeCty:
        def lookup(self, callsign):
            return {"dxcc": 281, "country": "Spain"} if callsign == "EA1AA" else {}

    monkeypatch.setattr(qlog, "_dedupe_entry", lambda _key: None)
    monkeypatch.setattr(qlog, "_record_dedupe_entry", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(qlog, "qrz_client", None)
    monkeypatch.setattr(qlog, "wavelog_client", FakeWavelog())
    monkeypatch.setattr(qlog, "adif_handler", FakeAdif())
    monkeypatch.setattr(qlog, "cty_resolver", FakeCty())
    monkeypatch.setattr(qlog, "qso_status_store", FakeStatusStore())

    result = asyncio.run(qlog.log_qso(QSORequest(
        callsign="EA1AA",
        frequency=14.074,
        band="20m",
        mode="FT8",
        rst_sent="-10",
        rst_received="-07",
        gridsquare="IN80",
        date_time=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc).isoformat(),
    )))

    assert result["success"] is True
    assert recorded[0]["callsign"] == "EA1AA"
    assert recorded[0]["band"] == "20m"
    assert recorded[0]["mode"] == "FT8"
    assert recorded[0]["gridsquare"] == "IN80"
    assert recorded[0]["dxcc"] == 281


def test_qso_logging_writes_new_qso_to_postgres_read_cache(monkeypatch):
    import services.qso_logging as qlog

    captured = {}

    class FakeCursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            captured["query"] = query
            captured["params"] = params

    class FakeConnection:
        def __init__(self):
            self.cursor_obj = FakeCursor()
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True
            captured["committed"] = True

    monkeypatch.setattr(qlog, "should_use_postgres", lambda: True)
    monkeypatch.setattr(qlog, "connect_postgres", lambda: FakeConnection())
    monkeypatch.setattr(qlog, "cty_resolver", None)

    inserted = qlog.write_qso_to_postgres_read_cache({
        "callsign": "ea1aa",
        "frequency": 14.074,
        "band": "20m",
        "mode": "FT8",
        "rst_sent": "-10",
        "rst_received": "-07",
        "gridsquare": "IN80",
        "dxcc": 281,
        "date_time": datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc).isoformat(),
    })

    assert inserted is True
    assert "INSERT INTO qso_records" in captured["query"]
    assert "WHERE NOT EXISTS" in captured["query"]
    assert captured["query"].count("%s") == len(captured["params"])
    assert captured["params"][0] == "EA1AA"
    assert captured["params"][8] == "20m"
    assert captured["params"][24] == 281
    assert captured["committed"] is True


def test_qso_logging_skips_postgres_write_when_backend_disabled(monkeypatch):
    import services.qso_logging as qlog

    monkeypatch.setattr(qlog, "should_use_postgres", lambda: False)

    assert qlog.write_qso_to_postgres_read_cache({"callsign": "EA1AA"}) is False


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
    service._live_cycle_state = lambda: (7.5, 0.1, 123, True)

    assert asyncio.run(service.transmit_queued_now_if_possible(force_current_slot=True)) is True
    assert service.tx_queue == []

    late = service_with_tx("FT4")
    asyncio.run(late.engage_target({"callsign": "EA1AA", "grid": "IN83", "mode": "FT4"}, source="manual_double_click"))
    late._live_cycle_state = lambda: (7.5, 1.0, 123, True)

    assert asyncio.run(late.transmit_queued_now_if_possible(force_current_slot=True)) is False
    assert late.tx_queue == ["EA1AA OM0RX JN88"]


def test_timing_loop_does_not_miss_usable_tx_slot_after_half_second():
    service = service_with_tx("FT8")

    assert service._should_handle_cycle(100, 0.3, True) is True
    assert service._should_handle_cycle(100, 0.5, True) is False

    service.last_tx_slot = 100
    assert service._should_handle_cycle(100, 1.0, True) is False

    ft4 = service_with_tx("FT4")
    assert ft4._should_handle_cycle(101, 0.1, True) is True
    assert ft4._should_handle_cycle(101, 0.4, True) is False


def test_settings_enabled_without_auto_call_does_not_select_or_queue_candidate():
    service = service_with_tx()
    service.tx_enabled = True
    service.automation_controller.apply_operator_settings({"automation": {"enabled": True, "allowedModes": {"FT8": True}}})
    service.automation_controller.ingest_target({
        "callsign": "K3ZK",
        "band": "40m",
        "mode": "FT8",
        "message": "CQ K3ZK FN21",
        "heard": True,
        "dxcc_status": "ATNO",
    })

    asyncio.run(service._automation_tick())

    assert service.active_attempt_id is None
    assert service.tx_queue == []
    assert service.automation_status == "standby"


def test_decode_uses_previous_slot_window_even_when_loop_wakes_late():
    service = service_with_tx()
    service._now = lambda: datetime(2026, 5, 27, 12, 0, 11, 100000, tzinfo=timezone.utc)
    service._clock_offset_seconds = lambda: -1.1
    calls = []

    class Decoder:
        status = type("Status", (), {"available": True})()

        def decode_window(self, samples, *, sample_rate, window_start, mode):
            calls.append((samples.copy(), sample_rate, window_start, mode))
            return []

    service.rx_decoder = Decoder()
    audio = np.arange(service.decoder_sample_rate * 32, dtype=np.float32)

    asyncio.run(service._attempt_decode(audio))
    asyncio.run(service._attempt_decode(audio))

    assert len(calls) == 1
    samples, sample_rate, window_start, mode = calls[0]
    assert len(samples) == service.decoder_sample_rate * 15
    assert sample_rate == service.decoder_sample_rate
    assert mode == "FT8"
    assert window_start == datetime(2026, 5, 27, 11, 59, 45, tzinfo=timezone.utc)
    assert samples[0] == audio[-(service.decoder_sample_rate * 25)]
    assert samples[-1] == audio[-(service.decoder_sample_rate * 10) - 1]


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
