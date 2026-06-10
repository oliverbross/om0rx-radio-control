"""Smoke tests for backend-owned Digital automation target control."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import _bootstrap  # noqa: F401
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from services.digital_automation import (
    DigitalAutomationController,
    DigitalAutomationSettings,
    current_band_plan_bands,
    payload_matches_need_filters,
    score_payload,
)
from services.wsjtx import WSJTXService, register_wsjtx_endpoints


class _FakeCtyResolver:
    def __init__(self, info):
        self.info = info

    def lookup(self, callsign):
        return self.info.get(callsign, {})


class _FakeQsoStatusStore:
    def __init__(
        self,
        *,
        call_flags=None,
        dxcc_overall=None,
        dxcc_bandmode=None,
        grid_flags=None,
    ):
        self._call_flags = call_flags or {}
        self._dxcc_overall = dxcc_overall or {}
        self._dxcc_bandmode = dxcc_bandmode or {}
        self._grid_flags = grid_flags or {}

    def call_flags(self, callsign, band, mode):
        return self._call_flags.get((callsign, band, mode), (False, False, True, True, False))

    def dxcc_overall(self, dxcc):
        return self._dxcc_overall.get(dxcc, (False, False))

    def dxcc_bandmode_flags(self, dxcc, band, mode):
        return self._dxcc_bandmode.get((dxcc, band, mode), (True, True, False))

    def grid_flags(self, grid, band, mode):
        return self._grid_flags.get((grid, band, mode), (False, False, False))


class _FakeTargetStore:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.saved = []

    def load_recent_targets(self, *, limit=250, max_age_hours=24):
        return self.rows[:limit]

    def upsert_target(self, target):
        self.saved.append(dict(target.to_dict() if hasattr(target, "to_dict") else target))


class _FakeWavelogClient:
    def __init__(self):
        self.logged = []

    async def log_qso(self, qso_data):
        self.logged.append(dict(qso_data))
        return {"success": True, "data": {"id": len(self.logged)}, "message": "logged"}


class _FakeAdifHandler:
    def __init__(self):
        self.saved = []

    def add_qso(self, qso_data):
        self.saved.append(dict(qso_data))
        return True


class _FakeCtyAll:
    def lookup(self, callsign):
        return {
            "country": "United States",
            "dxcc": 291,
            "continent": "NA",
            "cq": 5,
            "itu": 8,
        }


def test_goal_scoring_prioritises_dxcc_band_grid_mode_call():
    assert score_payload({"dxcc_status": "ATNO"}) == 1000
    assert score_payload({"dxcc_status": "C/New Band"}) == 800
    assert score_payload({"call_status": "New Call", "continent": "AS"}) == 750
    assert score_payload({"call_status": "New Band"}) == 650
    assert score_payload({"references": [{"type": "POTA", "id": "K-0001", "status": "needed"}]}) == 600
    assert score_payload({"needed": {"grid": True}}) == 500
    assert score_payload({"call_status": "New Mode"}) == 350
    assert score_payload({"call_status": "New Call"}) == 200
    assert score_payload({"call_status": "Confirmed", "dxcc_status": "Confirmed"}) == 0


def test_reference_targets_are_carried_but_filter_gated():
    payload = {
        "callsign": "K1POTA",
        "band": "20m",
        "mode": "FT8",
        "message": "CQ K1POTA FN42",
        "pota": "K-1234",
        "pota_status": "needed",
    }

    assert not payload_matches_need_filters(payload, DigitalAutomationSettings(need_reference=False))
    assert payload_matches_need_filters(payload, DigitalAutomationSettings(need_reference=True))

    controller = DigitalAutomationController(mycall="OM0RX", settings=DigitalAutomationSettings(need_reference=True))
    target = controller.ingest_target(payload)

    assert target is not None
    assert target.to_dict()["reference_items"] == [
        {"type": "POTA", "id": "K-1234", "status": "needed", "need_reason": ""}
    ]
    assert {"reference", "pota"}.issubset(target.need_reasons)


def test_wsjtz_filter_matrix_limits_continents_and_lotw():
    settings = DigitalAutomationSettings.from_operator_settings({
        "automation": {
            "filterMatrixEnabled": True,
            "filterNew": {"call": True},
            "filterNewOnBand": {"call": False, "grid": False},
            "filterContinents": {"NA": True, "SA": True, "EU": False, "AS": False, "AF": False, "OC": False, "AN": False},
            "lotwOnly": True,
        }
    })

    assert payload_matches_need_filters(
        {"call_status": "New Call", "continent": "NA", "lotw_member": True},
        settings,
    )
    assert not payload_matches_need_filters(
        {"call_status": "New Call", "continent": "EU", "lotw_member": True},
        settings,
    )
    assert not payload_matches_need_filters(
        {"call_status": "New Call", "continent": "NA", "lotw_member": False},
        settings,
    )


def test_wsjtz_filter_matrix_keeps_new_and_new_on_band_separate():
    settings = DigitalAutomationSettings.from_operator_settings({
        "automation": {
            "filterMatrixEnabled": True,
            "filterNew": {"grid": False},
            "filterNewOnBand": {"call": False, "grid": True},
            "filterContinents": {"NA": True, "SA": True, "EU": True, "AS": True, "AF": True, "OC": True, "AN": True},
        }
    })

    assert payload_matches_need_filters(
        {"needed_on_band": {"grid": True}, "continent": "EU"},
        settings,
    )
    assert not payload_matches_need_filters(
        {"needed": {"grid": True}, "continent": "EU"},
        settings,
    )


def test_controller_filters_disabled_modes_and_logged_duplicates():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "allowedModes": {"FT8": True, "FT4": False},
            "avoidLogged": True,
        }
    })

    assert controller.ingest_target({
        "callsign": "K1ABC",
        "band": "20m",
        "mode": "FT4",
        "call_status": "ATNO",
        "heard": True,
    }) is None
    assert controller.last_decision["reason"] == "mode-disabled"

    assert controller.ingest_target({
        "callsign": "K1ABC",
        "band": "20m",
        "mode": "FT8",
        "call_status": "Confirmed",
        "dxcc_status": "Confirmed",
        "heard": True,
    }) is None
    assert controller.last_decision["reason"] == "already-worked-call"


def test_controller_status_exposes_reason_panel_timeline_and_worked_flags():
    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "callsign": "E51ABC",
        "band": "20m",
        "mode": "FT8",
        "message": "CQ E51ABC BG08",
        "grid": "BG08",
        "heard": True,
        "call_status": "New Call",
        "dxcc_status": "ATNO",
    })

    assert target is not None
    selected = controller.next_target(auto_call_start_only=True, cq_only=True)
    status = controller.status()

    assert selected is not None
    assert status["reason_panel"]["target"]["call"] == "E51ABC"
    assert status["reason_panel"]["why_selected"] == "new-dxcc"
    assert status["event_timeline"][-1]["event"] == "selected"
    assert status["eligibility_summary"]["eligible"] >= 1
    assert status["active_target"]["worked_flags"]["new_dxcc"] is True
    assert status["active_target"]["worked_flags"]["new_call"] is True


def test_treat_73_as_cq_allows_non_direct_73_activity_to_seed_auto_call():
    disabled = DigitalAutomationController(
        mycall="OM0RX",
        settings=DigitalAutomationSettings(treat_73_as_cq=False),
    )
    assert disabled.ingest_target({
        "source": "decoded",
        "message": "EA1AA K1ABC 73",
        "band": "20m",
        "mode": "FT8",
        "heard": True,
        "call_status": "New Call",
        "dxcc_status": "ATNO",
    }) is None
    assert disabled.last_decision["reason"] == "not-auto-call-start-message"

    enabled = DigitalAutomationController(
        mycall="OM0RX",
        settings=DigitalAutomationSettings(treat_73_as_cq=True),
    )
    target = enabled.ingest_target({
        "source": "decoded",
        "message": "EA1AA K1ABC 73",
        "band": "20m",
        "mode": "FT8",
        "heard": True,
        "call_status": "New Call",
        "dxcc_status": "ATNO",
    })

    assert target is not None
    assert target.call == "EA1AA"
    assert enabled.next_target(auto_call_start_only=True, cq_only=True).call == "EA1AA"


def test_controller_ignores_calls_from_native_wsjtz_style_policy():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "ignoreList": "K1ABC\nK2ABC, k3abc",
            "autoCallCount": 7,
            "bandPlan": "06:20m,15m\n20:40m,80m",
            "allowedModes": {"FT8": True},
        }
    })

    assert controller.settings.max_attempts_per_target == 7
    assert controller.settings.band_plan == "06:20m,15m\n20:40m,80m"

    assert controller.ingest_target({
        "callsign": "k2abc",
        "band": "20m",
        "mode": "FT8",
        "call_status": "New Band",
        "heard": True,
    }) is None
    assert controller.last_decision["reason"] == "ignored-call"

    target = controller.ingest_target({
        "callsign": "K4ABC",
        "band": "20m",
        "mode": "FT8",
        "call_status": "New Band",
        "heard": True,
    })
    assert target is not None


def test_controller_requires_heard_spot_before_calling():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "spotHuntEnabled": True,
            "requireHeardBeforeCall": True,
            "allowedModes": {"FT8": True},
        }
    })

    spot = controller.ingest_target({
        "callsign": "DX1DX",
        "band": "20m",
        "mode": "FT8",
        "source": "spot",
        "dxcc_status": "ATNO",
    })

    assert spot is not None
    assert spot.state == "listening"
    assert controller.next_target() is None

    heard = controller.ingest_target({
        "message": "CQ DX1DX AA00",
        "callsign": "DX1DX",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -12,
        "dxcc_status": "ATNO",
    })

    assert heard is not None
    selected = controller.next_target()
    assert selected is not None
    assert selected.call == "DX1DX"
    assert selected.reason == "new-dxcc"


def test_controller_rejects_non_cq_decodes_as_auto_call_starters():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {"avoidLogged": True}})

    target = controller.ingest_target({
        "message": "OK1HEH F1ICS R-07",
        "callsign": "OK1HEH",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 12,
        "call_status": "ATNO",
        "dxcc_status": "ATNO",
    })

    assert target is None
    assert controller.last_decision["reason"] == "not-auto-call-start-message"


def test_current_band_plan_uses_utc_schedule_boundaries():
    plan = "05:20m,17m,15m,12m,10m\n20:30m,40m,80m,160m"

    assert current_band_plan_bands(plan, datetime(2026, 6, 5, 4, 59, tzinfo=timezone.utc)) == [
        "30m",
        "40m",
        "80m",
        "160m",
    ]
    assert current_band_plan_bands(plan, datetime(2026, 6, 5, 5, 0, tzinfo=timezone.utc)) == [
        "20m",
        "17m",
        "15m",
        "12m",
        "10m",
    ]
    assert current_band_plan_bands(plan, datetime(2026, 6, 5, 19, 59, tzinfo=timezone.utc)) == [
        "20m",
        "17m",
        "15m",
        "12m",
        "10m",
    ]
    assert current_band_plan_bands(plan, datetime(2026, 6, 5, 22, 41, tzinfo=timezone.utc)) == [
        "30m",
        "40m",
        "80m",
        "160m",
    ]
    assert current_band_plan_bands(plan, datetime(2026, 6, 6, 0, 39, tzinfo=timezone.utc)) == [
        "30m",
        "40m",
        "80m",
        "160m",
    ]


def test_auto_call_obeys_active_utc_band_plan_when_band_hopping_enabled():
    now = datetime(2026, 6, 5, 22, 41, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "bandHopping": True,
            "bandPlan": "05:20m,17m,15m,12m,10m\n20:30m,40m,80m,160m",
            "requireHeardBeforeCall": True,
            "avoidLogged": True,
            "treat73AsCQ": True,
        }
    })

    outside = controller.ingest_target({
        "message": "CQ A41KB LL93",
        "callsign": "A41KB",
        "band": "17m",
        "mode": "FT8",
        "source": "rbl",
        "heard": True,
        "snr": -4,
        "call_status": "Worked",
        "dxcc_status": "Worked",
        "needed": {"dxcc": True},
        "needed_on_band": {"band": True},
    })
    inside = controller.ingest_target({
        "message": "CQ XX9TXN OL62",
        "callsign": "XX9TXN",
        "band": "30m",
        "mode": "FT8",
        "source": "rbl",
        "heard": True,
        "snr": -7,
        "call_status": "New Call",
        "dxcc_status": "ATNO",
    })
    assert outside is not None
    assert inside is not None
    outside.last_heard_at = now
    outside.updated_at = now
    inside.last_heard_at = now
    inside.updated_at = now

    selected = controller.next_target(now=now, auto_call_start_only=True, cq_only=True)

    assert selected is not None
    assert selected.call == "XX9TXN"
    assert controller.last_decision["call"] == "XX9TXN"


def test_stale_heard_spot_is_not_called_hours_later():
    now = datetime(2026, 6, 5, 22, 41, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "bandHopping": True,
            "bandPlan": "20:30m,40m,80m,160m",
            "requireHeardBeforeCall": True,
            "avoidLogged": True,
        }
    })

    stale = controller.ingest_target({
        "message": "CQ A41KB LL93",
        "callsign": "A41KB",
        "band": "30m",
        "mode": "FT8",
        "source": "rbl",
        "heard": True,
        "snr": 1,
        "call_status": "Worked",
        "dxcc_status": "Worked",
        "needed": {"dxcc": True},
    })
    assert stale is not None
    stale.last_heard_at = now - timedelta(hours=6)
    stale.updated_at = stale.last_heard_at

    assert controller.next_target(now=now, auto_call_start_only=True, cq_only=True) is None
    assert stale.state == "expired"
    assert stale.reason == "heard-target-too-old"
    assert controller.last_decision["reason"] == "no-eligible-targets"


def test_fresh_decode_revives_expired_target_for_73_hunting():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "avoidLogged": True,
            "treat73AsCQ": True,
            "requireHeardBeforeCall": True,
        }
    })
    first = controller.ingest_target({
        "message": "CQ EA8ACW IL18",
        "callsign": "EA8ACW",
        "band": "30m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -3,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })
    assert first is not None
    first.sync_state("expired")
    first.reason = "decode-too-old"

    revived = controller.ingest_target({
        "message": "IQ0VT EA8ACW 73",
        "callsign": "EA8ACW",
        "band": "30m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -3,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    assert revived is first
    assert revived.state == "heard"
    selected = controller.next_target(auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "EA8ACW"


def test_treat_73_as_cq_allows_auto_call_selection():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "avoidLogged": True,
            "treat73AsCQ": True,
            "requireHeardBeforeCall": False,
        }
    })

    target = controller.ingest_target({
        "message": "EA1AA F4ABC 73",
        "callsign": "EA1AA",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 10,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    assert target is not None
    selected = controller.next_target(auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "EA1AA"


def test_raw_wsjtx_decode_row_is_normalized_before_auto_call_filter():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "avoidLogged": True,
            "requireHeardBeforeCall": False,
        }
    })

    target = controller.ingest_target({
        "message": "101130 -14 -0.2 1393 ~ CQ G7UAK IO84",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -14,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    assert target is not None
    assert target.call == "G7UAK"
    assert target.message == "CQ G7UAK IO84"
    selected = controller.next_target(auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "G7UAK"


def test_raw_wsjtx_73_row_is_eligible_when_treat_73_as_cq_enabled():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "avoidLogged": True,
            "treat73AsCQ": True,
            "requireHeardBeforeCall": False,
        }
    })

    target = controller.ingest_target({
        "message": "101145 -9 0.2 1337 ~ BA5AW PY1SX RR73",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -9,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    assert target is not None
    assert target.call == "BA5AW"
    assert target.message == "BA5AW PY1SX RR73"
    selected = controller.next_target(auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "BA5AW"


def test_treat_73_as_cq_disabled_keeps_73_lines_out_of_auto_call():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "avoidLogged": True,
            "treat73AsCQ": False,
            "requireHeardBeforeCall": False,
        }
    })

    target = controller.ingest_target({
        "message": "EA1AA F4ABC RR73",
        "callsign": "EA1AA",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 10,
        "call_status": "New Band",
        "dxcc_status": "Confirmed",
    })

    assert target is None
    assert controller.last_decision["reason"] == "not-auto-call-start-message"


def test_stale_command_sent_target_expires_and_rotates_to_next_candidate():
    controller = DigitalAutomationController(
        mycall="OM0RX",
        settings=DigitalAutomationSettings(dwell_seconds=120),
    )
    now = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    first = controller.ingest_target({
        "message": "CQ CS2TU IN61",
        "callsign": "CS2TU",
        "band": "15m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -18,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })
    second = controller.ingest_target({
        "message": "CQ A93MO LL56",
        "callsign": "A93MO",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -2,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    assert first is not None
    assert second is not None
    first.last_command_at = now - timedelta(seconds=121)
    first.last_attempt_at = first.last_command_at
    first.last_heard_at = first.last_command_at
    first.sync_state("calling", active_state="command_sent")
    controller.active_target_key = first.key
    controller.active_qso_state = "command_sent"
    second.last_heard_at = now
    second.updated_at = now

    selected = controller.next_target(now=now, auto_call_start_only=True, cq_only=True)

    assert selected is not None
    assert selected.key == second.key
    assert controller.active_target_key == second.key
    assert first.state == "backoff"
    assert first.active_state == "failed"
    assert first.reason == "stale-active-no-progress"
    assert first.backoff_until is not None


def test_fresh_heard_decode_does_not_keep_stale_command_sent_target_alive():
    controller = DigitalAutomationController(
        mycall="OM0RX",
        settings=DigitalAutomationSettings(dwell_seconds=120),
    )
    now = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    first = controller.ingest_target({
        "message": "CQ A61CK LL75",
        "callsign": "A61CK",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -14,
        "call_status": "New Band",
        "dxcc_status": "Confirmed",
    })
    second = controller.ingest_target({
        "message": "CQ EA3JEZ JN11",
        "callsign": "EA3JEZ",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -3,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    assert first is not None
    assert second is not None
    first.last_command_at = now - timedelta(seconds=121)
    first.last_attempt_at = first.last_command_at
    first.last_heard_at = now
    first.updated_at = now
    first.sync_state("calling", active_state="command_sent")
    controller.active_target_key = first.key
    controller.active_qso_state = "command_sent"

    selected = controller.next_target(now=now, auto_call_start_only=True, cq_only=True)

    assert selected is not None
    assert selected.key == second.key
    assert first.state == "backoff"
    assert first.active_state == "failed"
    assert first.reason == "stale-active-no-progress"
    assert controller.active_target_key == second.key


def test_unanswered_command_sent_target_uses_short_hunting_timeout():
    controller = DigitalAutomationController(
        mycall="OM0RX",
        settings=DigitalAutomationSettings(dwell_seconds=120),
    )
    now = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    first = controller.ingest_target({
        "message": "CQ UR3IGB KN79",
        "callsign": "UR3IGB",
        "band": "15m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -12,
        "call_status": "New Band",
        "dxcc_status": "Confirmed",
    })
    second = controller.ingest_target({
        "message": "CQ BG4KAT PM01",
        "callsign": "BG4KAT",
        "band": "15m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -16,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
        "continent": "AS",
    })

    assert first is not None
    assert second is not None
    first.last_command_at = now - timedelta(seconds=61)
    first.last_attempt_at = first.last_command_at
    first.last_heard_at = now
    first.updated_at = now
    first.sync_state("calling", active_state="command_sent")
    controller.active_target_key = first.key
    controller.active_qso_state = "command_sent"

    selected = controller.next_target(now=now, auto_call_start_only=True, cq_only=True)

    assert selected is not None
    assert selected.key == second.key
    assert first.reason == "stale-active-no-progress"
    assert first.state == "backoff"
    assert controller.active_target_key == second.key


def test_unanswered_command_sent_target_is_not_released_before_short_timeout():
    controller = DigitalAutomationController(
        mycall="OM0RX",
        settings=DigitalAutomationSettings(dwell_seconds=120),
    )
    now = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    first = controller.ingest_target({
        "message": "CQ UR3IGB KN79",
        "callsign": "UR3IGB",
        "band": "15m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -12,
        "call_status": "New Band",
        "dxcc_status": "Confirmed",
    })
    second = controller.ingest_target({
        "message": "CQ BG4KAT PM01",
        "callsign": "BG4KAT",
        "band": "15m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -16,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
        "continent": "AS",
    })

    assert first is not None
    assert second is not None
    first.last_command_at = now - timedelta(seconds=44)
    first.last_attempt_at = first.last_command_at
    first.last_heard_at = now
    first.updated_at = now
    first.sync_state("calling", active_state="command_sent")
    controller.active_target_key = first.key
    controller.active_qso_state = "command_sent"

    selected = controller.next_target(now=now, auto_call_start_only=True, cq_only=True)

    assert selected is None
    assert controller.active_target_key == first.key
    assert first.state == "calling"
    assert controller.last_decision["reason"] == "active-qso-in-progress"


def test_cluster_target_is_not_rejected_as_non_cq_decode():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "avoidLogged": True,
            "requireHeardBeforeCall": False,
        }
    })

    target = controller.ingest_target({
        "message": "Cluster spot",
        "callsign": "ZD9DX",
        "band": "20m",
        "mode": "FT8",
        "source": "cluster",
        "heard": False,
        "snr": 0,
        "call_status": "New Call",
        "dxcc_status": "ATNO",
        "score": 100,
    })

    assert target is not None
    selected = controller.next_target(auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "ZD9DX"


def test_selection_rechecks_worked_before_status_for_existing_target():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {"avoidLogged": True}})
    target = controller.ingest_target({
        "message": "CQ EA1EQ IN83",
        "callsign": "EA1EQ",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 12,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })
    assert target is not None

    target.call_status = "Worked"

    assert controller.next_target(auto_call_start_only=True) is None
    assert target.state == "skipped"
    assert target.reason == "already-worked-call"


def test_avoid_logged_allows_prior_work_when_band_or_mode_needed():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {"avoidLogged": True}})

    band_target = controller.ingest_target({
        "message": "CQ EA1EQ IN83",
        "callsign": "EA1EQ",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 12,
        "call_status": "New Band",
        "dxcc_status": "Confirmed",
    })
    mode_target = controller.ingest_target({
        "message": "CQ EA2EQ IN83",
        "callsign": "EA2EQ",
        "band": "20m",
        "mode": "FT4",
        "source": "decoded",
        "heard": True,
        "snr": 10,
        "call_status": "New Mode",
        "dxcc_status": "Confirmed",
    })

    assert band_target is not None
    assert mode_target is not None
    assert band_target.call_status == "New Band"
    assert mode_target.call_status == "New Mode"
    assert "band" in band_target.need_reasons
    assert "mode" in mode_target.need_reasons
    assert controller.status()["eligible_count"] == 2
    assert controller.last_decision["decision"] == "queued"


def test_prior_work_band_and_mode_slots_remain_available_when_avoid_logged_is_off():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {"avoidLogged": False}})

    band_target = controller.ingest_target({
        "message": "CQ EA1EQ IN83",
        "callsign": "EA1EQ",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 12,
        "call_status": "New Band",
        "dxcc_status": "Confirmed",
    })
    mode_target = controller.ingest_target({
        "message": "CQ EA2EQ IN83",
        "callsign": "EA2EQ",
        "band": "20m",
        "mode": "FT4",
        "source": "decoded",
        "heard": True,
        "snr": 10,
        "call_status": "New Mode",
        "dxcc_status": "Confirmed",
    })

    assert band_target is not None
    assert band_target.call_status == "New Band"
    assert "band" in band_target.need_reasons
    assert mode_target is not None
    assert mode_target.call_status == "New Mode"
    assert "mode" in mode_target.need_reasons
    assert controller.status()["eligible_count"] == 2


def test_spot_hunt_listens_for_unconfirmed_dxcc_before_calling():
    now = datetime(2026, 6, 5, 10, 15, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "enabled": True,
            "spotHuntEnabled": True,
            "avoidLogged": True,
            "bandPlan": "05:20m,17m,15m,12m,10m\n20:40m,80m",
            "spotListenSeconds": 30,
        }
    })

    spot = controller.ingest_target({
        "callsign": "M6OTU",
        "grid": "IO84",
        "band": "12m",
        "mode": "FT8",
        "source": "rbl",
        "frequency_mhz": 24.915,
        "call_status": "Worked",
        "dxcc_status": "Worked",
    })

    assert spot is not None
    assert spot.state == "listening"
    assert "dxcc" in spot.need_reasons
    assert controller.next_target(now=now, auto_call_start_only=True, cq_only=True) is None

    listen = controller.next_listen_target(now=now)
    assert listen is not None
    assert listen.call == "M6OTU"
    assert listen.dial_frequency == 24.915
    assert controller.listen_target_key == listen.key
    assert controller.next_target(now=now + timedelta(seconds=5), auto_call_start_only=True, cq_only=True) is None
    assert controller.last_decision["reason"] == "spot-listen-in-progress"

    heard = controller.ingest_target({
        "message": "CQ M6OTU IO84",
        "callsigns": "M6OTU",
        "callsign": "M6OTU",
        "grid": "IO84",
        "band": "12m",
        "mode": "FT8",
        "source": "wsjtx-decode-status",
        "heard": True,
        "snr": -9,
        "freq": 1346,
        "frequency_mhz": 24.915,
        "call_status": "Worked",
        "dxcc_status": "Worked",
    })

    assert heard is not None
    assert heard.heard is True
    assert controller.status()["listen_target"] is None
    selected = controller.next_target(now=now + timedelta(seconds=10), auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "M6OTU"
    assert selected.reason == "needed"


def test_spot_hunt_does_not_cross_band_when_band_hopping_disabled():
    now = datetime(2026, 6, 5, 10, 15, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "enabled": True,
            "spotHuntEnabled": True,
            "bandHopping": False,
            "currentBand": "20m",
            "allowedModes": {"FT8": True},
            "bandPlan": "05:20m,30m,17m,15m,12m,10m",
        }
    })

    controller.ingest_target({
        "callsign": "A61OK",
        "grid": "LL75",
        "band": "30m",
        "mode": "FT8",
        "source": "rbl",
        "frequency_mhz": 10.136,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    listen = controller.next_listen_target(now=now)

    assert listen is None
    assert controller.last_decision["reason"] == "no-spot-listen-targets"
    assert controller.last_decision["rejected"]["band-hopping-disabled"] == 1


def test_live_decoded_candidate_preempts_spot_listen_probe():
    now = datetime(2026, 6, 5, 10, 15, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "enabled": True,
            "spotHuntEnabled": True,
            "requireHeardBeforeCall": True,
            "treat73AsCQ": True,
            "bandPlan": "05:20m,17m,15m,12m,10m",
            "allowedModes": {"FT8": True},
        }
    })
    spot = controller.ingest_target({
        "callsign": "DX1DX",
        "grid": "AA00",
        "band": "12m",
        "mode": "FT8",
        "source": "rbl",
        "frequency_mhz": 24.915,
        "dxcc_status": "ATNO",
    })
    assert spot is not None
    assert controller.next_listen_target(now=now) is not None

    heard = controller.ingest_target({
        "message": "CQ R3KBY KO90",
        "callsign": "R3KBY",
        "grid": "KO90",
        "band": "20m",
        "mode": "FT8",
        "source": "wsjtx-decode-status",
        "heard": True,
        "snr": -9,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    assert heard is not None
    selected = controller.next_target(now=now + timedelta(seconds=5), auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "R3KBY"
    assert controller.listen_target_key is None
    assert controller.status()["listen_target"] is None
    assert controller.last_decision["reason"] != "spot-listen-in-progress"


def test_treat_73_candidate_preempts_spot_listen_probe():
    now = datetime(2026, 6, 5, 10, 15, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "enabled": True,
            "spotHuntEnabled": True,
            "requireHeardBeforeCall": True,
            "treat73AsCQ": True,
            "allowedModes": {"FT8": True},
        }
    })
    controller.ingest_target({
        "callsign": "DX1DX",
        "band": "12m",
        "mode": "FT8",
        "source": "rbl",
        "frequency_mhz": 24.915,
        "dxcc_status": "ATNO",
    })
    assert controller.next_listen_target(now=now) is not None

    heard = controller.ingest_target({
        "message": "EA1AA F4ABC RR73",
        "callsign": "EA1AA",
        "band": "20m",
        "mode": "FT8",
        "source": "wsjtx-decode-status",
        "heard": True,
        "snr": -12,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    assert heard is not None
    selected = controller.next_target(now=now + timedelta(seconds=5), auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "EA1AA"
    assert controller.listen_target_key is None


def test_spot_listen_respects_allowed_modes_after_mode_switching_off():
    now = datetime(2026, 6, 5, 22, 15, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "enabled": True,
            "spotHuntEnabled": True,
            "bandPlan": "20:30m,40m,80m,160m",
            "allowedModes": {"FT8": True},
        }
    })
    ft4 = controller.ingest_target({
        "callsign": "KD4JG",
        "band": "30m",
        "mode": "FT4",
        "source": "rbl",
        "frequency_mhz": 10.140,
        "dxcc_status": "ATNO",
    })
    assert ft4 is None
    assert controller.last_decision["reason"] == "mode-disabled"

    ft8 = controller.ingest_target({
        "callsign": "KD4JG",
        "band": "30m",
        "mode": "FT8",
        "source": "rbl",
        "frequency_mhz": 10.136,
        "dxcc_status": "ATNO",
    })
    assert ft8 is not None
    listen = controller.next_listen_target(now=now)
    assert listen is not None
    assert listen.mode == "FT8"


def test_disabled_mode_candidate_is_not_selected_for_auto_call():
    now = datetime(2026, 6, 5, 22, 15, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "enabled": True,
            "spotHuntEnabled": True,
            "allowedModes": {"FT8": True},
            "requireHeardBeforeCall": True,
        }
    })
    ft4 = controller.ingest_target({
        "message": "CQ LU1UG FF87",
        "callsign": "LU1UG",
        "grid": "FF87",
        "band": "40m",
        "mode": "FT4",
        "source": "wsjtx-decode-status",
        "heard": True,
        "snr": -9,
        "freq": 1500,
        "frequency_mhz": 7.047,
        "call_status": "New Call",
        "dxcc_status": "Worked",
    })
    assert ft4 is None
    assert controller.last_decision["reason"] == "mode-disabled"

    selected = controller.next_target(now=now, auto_call_start_only=True, cq_only=True)
    assert selected is None
    assert controller.active_target_key is None


def test_release_target_restores_selected_candidate_without_attempt():
    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "message": "CQ R3KBY KO90",
        "callsign": "R3KBY",
        "grid": "KO90",
        "band": "80m",
        "mode": "FT8",
        "source": "wsjtx-decode-status",
        "heard": True,
        "snr": -9,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })
    assert target is not None

    selected = controller.next_target(auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert controller.active_target_key == target.key

    released = controller.release_target(target.key, reason="bridge-command-failed")

    assert released is target
    assert controller.active_target_key is None
    assert controller.active_qso_state == "idle"
    assert target.state == "heard"
    assert target.active_state == "idle"
    assert target.attempts == 0
    assert controller.last_decision["reason"] == "bridge-command-failed"


def test_active_listen_probe_is_cleared_when_mode_becomes_disabled():
    now = datetime(2026, 6, 5, 22, 15, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "enabled": True,
            "spotHuntEnabled": True,
            "allowedModes": {"FT4": True},
        }
    })
    ft4 = controller.ingest_target({
        "callsign": "LU1UG",
        "band": "40m",
        "mode": "FT4",
        "source": "rbl",
        "frequency_mhz": 7.0468,
        "dxcc_status": "ATNO",
    })
    assert ft4 is not None
    assert controller.next_listen_target(now=now) is not None
    assert controller.listen_target_key == ft4.key

    controller.apply_operator_settings({
        "automation": {
            "allowedModes": {"FT8": True},
        }
    })

    assert controller.next_target(now=now + timedelta(seconds=5), auto_call_start_only=True, cq_only=True) is None
    assert controller.listen_target_key is None
    assert ft4.state == "skipped"
    assert ft4.reason == "mode-disabled"


def test_spot_hunt_probe_expires_when_not_heard():
    now = datetime(2026, 6, 5, 10, 15, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "enabled": True,
            "spotHuntEnabled": True,
            "bandPlan": "05:12m",
            "spotListenSeconds": 30,
        }
    })
    target = controller.ingest_target({
        "callsign": "P29ABC",
        "band": "12m",
        "mode": "FT8",
        "source": "cluster",
        "frequency_mhz": 24.915,
        "call_status": "New Call",
        "dxcc_status": "ATNO",
    })
    assert target is not None
    assert controller.next_listen_target(now=now) is not None

    assert controller.next_listen_target(now=now + timedelta(seconds=31)) is None
    assert target.state == "expired"
    assert target.reason == "spot-listen-not-heard"


def test_need_filters_can_limit_auto_call_to_dxcc_slots():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "needCall": False,
            "needDxcc": True,
            "needBand": False,
            "needMode": False,
            "needGrid": False,
        }
    })

    new_call = controller.ingest_target({
        "message": "CQ EA1EQ IN83",
        "callsign": "EA1EQ",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 12,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })
    atno = controller.ingest_target({
        "message": "CQ ZD9DX IE59",
        "callsign": "ZD9DX",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 8,
        "call_status": "New Call",
        "dxcc_status": "ATNO",
    })

    assert new_call is None
    assert atno is not None
    selected = controller.next_target(auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "ZD9DX"


def test_need_filters_can_limit_auto_call_to_grid_slots():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "needCall": False,
            "needDxcc": False,
            "needBand": False,
            "needMode": False,
            "needGrid": True,
        }
    })

    band_target = controller.ingest_target({
        "message": "CQ EA1EQ IN83",
        "callsign": "EA1EQ",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 12,
        "call_status": "New Band",
        "dxcc_status": "Confirmed",
    })
    grid_target = controller.ingest_target({
        "message": "CQ EA2EQ IN84",
        "callsign": "EA2EQ",
        "band": "10m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 11,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
        "needed": {"grid": True},
    })

    assert band_target is None
    assert grid_target is not None
    selected = controller.next_target(auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "EA2EQ"


def test_controller_records_attempts_and_backoff():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "maxAttemptsPerTarget": 2,
            "retryBackoffMinutes": 5,
        }
    })
    target = controller.ingest_target({
        "callsign": "DX2DX",
        "band": "15m",
        "mode": "FT8",
        "heard": True,
        "dxcc_status": "ATNO",
    })

    assert target is not None
    controller.record_attempt(target.key)
    backed_off = controller.record_attempt(target.key)

    assert backed_off is not None
    assert backed_off.state == "backoff"
    assert backed_off.backoff_until is not None
    assert backed_off.backoff_until > datetime.now(timezone.utc)
    assert controller.next_target() is None


def test_recent_attempt_is_not_reselected_during_dwell():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {"spotListenSeconds": 120}})
    target = controller.ingest_target({
        "callsign": "DX5DX",
        "band": "17m",
        "mode": "FT8",
        "heard": True,
        "dxcc_status": "ATNO",
    })

    assert target is not None
    controller.record_attempt(target.key)

    assert controller.next_target() is None


def test_auto_call_ignores_stale_decoded_cq_targets():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {"spotListenSeconds": 120}})
    now = datetime.now(timezone.utc)
    stale = controller.ingest_target({
        "callsign": "OLD1AA",
        "band": "40m",
        "mode": "FT8",
        "message": "CQ OLD1AA JO10",
        "heard": True,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })
    fresh = controller.ingest_target({
        "callsign": "NEW1AA",
        "band": "40m",
        "mode": "FT8",
        "message": "CQ NEW1AA JO20",
        "heard": True,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    assert stale is not None
    assert fresh is not None
    stale.last_heard_at = now - timedelta(seconds=50)
    stale.updated_at = stale.last_heard_at
    fresh.last_heard_at = now - timedelta(seconds=10)
    fresh.updated_at = fresh.last_heard_at

    selected = controller.next_target(now=now, auto_call_start_only=True, cq_only=True)

    assert selected is not None
    assert selected.call == "NEW1AA"


def test_auto_call_uses_shorter_freshness_window_for_ft4_cq_targets():
    controller = DigitalAutomationController(mycall="OM0RX")
    now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    target = controller.ingest_target({
        "message": "CQ DX4DX IN83",
        "callsign": "DX4DX",
        "band": "20m",
        "mode": "FT4",
        "source": "decoded",
        "heard": True,
        "dxcc_status": "ATNO",
    })

    assert target is not None
    target.last_heard_at = now - timedelta(seconds=25)
    target.updated_at = target.last_heard_at

    assert controller.next_target(now=now, auto_call_start_only=True, cq_only=True) is None


def test_decoded_target_preserves_source_slot_for_opposite_over_reply():
    controller = DigitalAutomationController(mycall="OM0RX")
    slot_start = datetime(2026, 6, 3, 6, 14, 15, tzinfo=timezone.utc)

    target = controller.ingest_target({
        "message": "CQ YU7GMN KN05",
        "callsign": "YU7GMN",
        "band": "40m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "timestamp": slot_start.isoformat(),
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })

    assert target is not None
    assert target.heard_slot_start_at == slot_start
    assert target.to_dict()["heard_slot_start_at"] == slot_start.isoformat()


def test_controller_marks_completed_qso_targets_done():
    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "callsign": "DX4DX",
        "band": "12m",
        "mode": "FT8",
        "heard": True,
        "dxcc_status": "ATNO",
    })

    assert target is not None
    assert controller.next_target() is not None
    completed = controller.mark_qso_complete("DX4DX", mode="FT8")

    assert len(completed) == 1
    assert completed[0].state == "done"
    assert controller.status()["eligible_count"] == 0


def test_controller_status_is_json_ready():
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.ingest_target({
        "callsign": "DX3DX",
        "band": "10m",
        "mode": "FT8",
        "heard": True,
        "call_status": "New Call",
    })

    status = controller.status()

    assert status["queue_length"] == 1
    assert status["targets"][0]["call"] == "DX3DX"
    assert status["settings"]["allowed_modes"] == ["FT4", "FT8"]


def test_controller_loads_persisted_targets_and_persists_state_changes():
    now = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)
    store = _FakeTargetStore(
        rows=[
            {
                "key": "E51ABC|20m|FT8",
                "call": "e51abc",
                "band": "20m",
                "mode": "ft8",
                "source": "decoded",
                "message": "CQ E51ABC BG08",
                "grid": "bg08",
                "call_status": "New Band",
                "dxcc_status": "ATNO",
                "score": 1000,
                "snr": -8,
                "audio_offset": 1240,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "last_heard_at": now.isoformat(),
                "heard": True,
                "attempts": 0,
                "state": "heard",
            }
        ]
    )

    controller = DigitalAutomationController(mycall="OM0RX", target_store=store)

    status = controller.status()
    assert status["persistence"]["enabled"] is True
    assert status["persistence"]["loaded_count"] == 1
    assert status["targets"][0]["call"] == "E51ABC"
    assert status["targets"][0]["grid"] == "BG08"

    selected = controller.next_target(now=now)
    assert selected is not None
    assert selected.call == "E51ABC"
    assert store.saved[-1]["state"] == "selected"

    controller.record_attempt(selected.key)
    assert store.saved[-1]["attempts"] == 1
    assert store.saved[-1]["state"] == "calling"


def test_controller_backoffs_persisted_active_target_on_restart():
    now = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)
    store = _FakeTargetStore(
        rows=[
            {
                "key": "HB9PAE|15m|FT8",
                "call": "HB9PAE",
                "band": "15m",
                "mode": "FT8",
                "source": "decoded",
                "message": "HB9PAE OM0RX JN88",
                "grid": "JN47",
                "call_status": "New Call",
                "dxcc_status": "Confirmed",
                "score": 750,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "last_heard_at": now.isoformat(),
                "last_attempt_at": now.isoformat(),
                "last_command_at": now.isoformat(),
                "heard": True,
                "attempts": 1,
                "state": "calling",
                "lifecycle": "command_sent",
                "active_state": "command_sent",
            }
        ]
    )

    controller = DigitalAutomationController(mycall="OM0RX", target_store=store)

    target = controller.targets["HB9PAE|15m|FT8"]
    assert controller.active_target_key is None
    assert controller.active_qso_state == "idle"
    assert target.state == "backoff"
    assert target.active_state == "failed"
    assert target.reason == "backend-restarted-active-target"
    assert target.backoff_until is not None
    assert store.saved[-1]["state"] == "backoff"


def test_controller_persists_ingested_targets():
    store = _FakeTargetStore()
    controller = DigitalAutomationController(mycall="OM0RX", target_store=store)

    target = controller.ingest_target({
        "message": "CQ DX3DX AA00",
        "callsign": "DX3DX",
        "band": "15m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 5,
        "call_status": "New Call",
    })

    assert target is not None
    assert store.saved[-1]["key"] == "DX3DX|15m|FT8"
    assert store.saved[-1]["state"] == "heard"


def test_controller_queues_multiple_direct_callers_without_overwrite():
    now = datetime.now(timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "avoidLogged": True,
            "requireHeardBeforeCall": True,
            "answerDirectCallers": True,
        }
    })

    first = controller.ingest_target({
        "message": "OM0RX K1ABC -12",
        "callsign": "K1ABC",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "timestamp": now.isoformat(),
        "call_status": "Confirmed",
        "dxcc_status": "Confirmed",
        "snr": -12,
    })
    second = controller.ingest_target({
        "message": "OM0RX JA1XYZ -08",
        "callsign": "JA1XYZ",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "timestamp": now.isoformat(),
        "call_status": "Worked",
        "dxcc_status": "Confirmed",
        "snr": -8,
    })

    assert first is not None
    assert second is not None
    assert first.direct_caller is True
    assert second.direct_caller is True
    assert controller.status()["queue_length"] == 2

    selected = controller.next_target(now=now, auto_call_start_only=True, cq_only=True)
    assert selected is not None
    assert selected.call == "JA1XYZ"
    assert selected.reason == "direct-caller"

    controller.mark_done(selected.key, reason="logged")
    next_selected = controller.next_target(now=now + timedelta(seconds=1), auto_call_start_only=True, cq_only=True)
    assert next_selected is not None
    assert next_selected.call == "K1ABC"


def test_controller_decision_log_explains_skip_queue_and_selection():
    controller = DigitalAutomationController(mycall="OM0RX")

    assert controller.ingest_target({
        "message": "CQ LOW1AA AA00",
        "callsign": "LOW1AA",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -35,
        "call_status": "New Call",
    }) is None

    target = controller.ingest_target({
        "message": "CQ E51ABC BG08",
        "callsign": "E51ABC",
        "grid": "BG08",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -8,
        "dxcc_status": "ATNO",
    })
    assert target is not None
    assert controller.next_target(auto_call_start_only=True, cq_only=True) is not None

    decisions = controller.status()["decision_log"]
    assert any(entry["reason"] == "below-min-signal" for entry in decisions)
    assert any(entry["decision"] == "queued" and entry["call"] == "E51ABC" for entry in decisions)
    assert any(entry["decision"] == "selected" and entry["call"] == "E51ABC" for entry in decisions)


def test_controller_attempt_records_idempotent_command_metadata():
    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "message": "CQ E51ABC BG08",
        "callsign": "E51ABC",
        "grid": "BG08",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -8,
        "dxcc_status": "ATNO",
    })
    assert target is not None
    selected = controller.next_target()
    assert selected is not None

    attempted = controller.record_attempt(selected.key)

    assert attempted is not None
    assert attempted.command_id.startswith("cmd-")
    assert attempted.target_id
    assert attempted.state == "calling"
    assert attempted.lifecycle == "command_sent"
    assert attempted.active_state == "command_sent"
    assert controller.status()["active_qso_state"] == "command_sent"


def test_controller_replay_harness_runs_decode_select_attempt_complete_flow():
    controller = DigitalAutomationController(mycall="OM0RX")
    results = controller.replay_events([
        {
            "type": "decode",
            "message": "CQ E51ABC BG08",
            "callsign": "E51ABC",
            "grid": "BG08",
            "band": "20m",
            "mode": "FT8",
            "snr": -8,
            "dxcc_status": "ATNO",
        },
        {"type": "select", "cq_only": True, "auto_call_start_only": True},
        {"type": "attempt", "key": "E51ABC|20m|FT8"},
        {"type": "logged", "call": "E51ABC", "band": "20m", "mode": "FT8"},
    ])

    assert [result["status"] for result in results] == ["queued", "selected", "updated", "completed"]
    assert controller.status()["eligible_count"] == 0
    assert controller.status()["active_qso_state"] == "completed"


def test_safe_automation_soak_completes_ten_targets_without_duplicate_wavelog_logs(monkeypatch, tmp_path):
    import services.ft8_service as ft8_service_module
    import services.qso_logging as qlog

    qlog._pending_dedupe_claims.clear()
    monkeypatch.setattr(qlog, "_dedupe_ledger_path", tmp_path / "qso_log_dedupe.json")
    monkeypatch.setattr(qlog, "_recent_wavelog_duplicate_entry", lambda qso_data: None)
    monkeypatch.setattr(qlog, "write_qso_to_postgres_read_cache", lambda qso_data: None)

    controller = DigitalAutomationController(
        mycall="OM0RX",
        settings=DigitalAutomationSettings(
            enabled=True,
            band_hopping=True,
            mode_switching=True,
            avoid_logged=True,
            treat_73_as_cq=True,
            auto_log_to_wavelog=True,
            max_attempts_per_target=5,
            dwell_seconds=30,
            band_plan="05:20m,17m,15m,12m,10m\n20:30m,40m,80m,160m",
        ),
    )
    fake_wavelog = _FakeWavelogClient()
    fake_adif = _FakeAdifHandler()
    wsjtx = WSJTXService()
    wsjtx.set_dependencies(fake_wavelog, None, None, cty_resolver=_FakeCtyAll(), adif_handler=fake_adif)
    monkeypatch.setattr(
        ft8_service_module,
        "get_ft8_service",
        lambda: SimpleNamespace(automation_controller=controller),
    )

    contacts = [
        ("K1TST", "20m", "FT8", 14.074, "FN42"),
        ("VE2TST", "17m", "FT8", 18.100, "FN35"),
        ("PY3TST", "15m", "FT8", 21.074, "GG40"),
        ("JA1TST", "12m", "FT8", 24.915, "PM95"),
        ("ZS6TST", "10m", "FT8", 28.074, "KG44"),
        ("VK2TST", "20m", "FT4", 14.080, "QF56"),
        ("LU1TST", "17m", "FT4", 18.104, "GF05"),
        ("EA8TST", "15m", "FT4", 21.140, "IL18"),
        ("9A1TST", "12m", "FT4", 24.919, "JN75"),
        ("DL2TST", "10m", "FT4", 28.180, "JO62"),
    ]
    selected_calls = []

    for index, (call, band, mode, frequency_mhz, grid) in enumerate(contacts):
        target = controller.ingest_target({
            "message": f"CQ {call} {grid}",
            "callsign": call,
            "grid": grid,
            "band": band,
            "mode": mode,
            "source": "decoded",
            "heard": True,
            "snr": -10 + index,
            "freq": 900 + index * 50,
            "frequency_mhz": frequency_mhz,
            "call_status": "New Call",
            "dxcc_status": "ATNO",
        })
        assert target is not None

        selected = controller.next_target(auto_call_start_only=True, cq_only=True)
        assert selected is not None
        assert selected.call == call
        selected_calls.append(selected.call)

        attempted = controller.record_attempt(selected.key)
        assert attempted is not None
        assert attempted.attempts == 1
        assert attempted.state == "calling"
        assert controller.handle_wsjtx_status({
            "dxCall": call,
            "band": band,
            "mode": mode,
            "tx": True,
        })["status"] == "calling"

        controller.transition_active_qso("reply_received", reason="soak-directed-reply", target=selected)
        controller.transition_active_qso("report_sent", reason="soak-report-sent", target=selected)
        controller.transition_active_qso("rr73_seen", reason="soak-rr73-seen", target=selected)

        qso_request = {
            "call": call,
            "mode": mode,
            "frequency_mhz": frequency_mhz,
            "grid": grid,
            "rst_sent": "-10",
            "rst_received": "-07",
            "date": "2026-06-06",
            "time_off": f"12:{index:02d}:00",
            "date_time": f"2026-06-06T12:{index:02d}:00+00:00",
        }
        first_log = asyncio.run(wsjtx.log_qso(qso_request))
        assert first_log["success"] is True
        assert not first_log.get("duplicate")
        assert controller.active_target_key is None
        assert controller.active_qso_state == "completed"
        assert controller.targets[selected.key].state == "done"

        duplicate_log = asyncio.run(wsjtx.log_qso(qso_request))
        assert duplicate_log["success"] is True
        assert duplicate_log["duplicate"] is True
        assert len(fake_wavelog.logged) == index + 1
        assert len(fake_adif.saved) == index + 1

    assert selected_calls == [call for call, *_ in contacts]
    assert len(set(selected_calls)) == 10
    assert len(fake_wavelog.logged) == 10
    assert len(fake_adif.saved) == 10
    assert {qso["band"] for qso in fake_wavelog.logged} == {"20m", "17m", "15m", "12m", "10m"}
    assert {qso["mode"] for qso in fake_wavelog.logged} == {"FT8", "FT4"}
    assert controller.status()["active_target"] is None
    assert controller.status()["eligible_count"] == 0


def test_wsjtx_status_tx_active_advances_active_qso_state():
    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "callsign": "E51ABC",
        "grid": "BG08",
        "band": "20m",
        "mode": "FT8",
        "message": "CQ E51ABC BG08",
        "dxcc_status": "ATNO",
        "frequency_mhz": 14.074,
        "heard": True,
    })
    assert target is not None
    selected = controller.next_target()
    assert selected is not None
    controller.record_attempt(selected.key)

    result = controller.handle_wsjtx_status({"dxCall": "E51ABC", "mode": "FT8", "band": "20m", "tx": True})

    assert result["status"] == "calling"
    assert controller.status()["active_qso_state"] == "calling"
    assert controller.status()["active_target"]["active_state"] == "calling"


def test_planner_tick_does_not_clear_live_attempt_while_waiting_for_reply():
    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "callsigns": "E51ABC",
        "callsign": "E51ABC",
        "grid": "BG08",
        "band": "20m",
        "mode": "FT8",
        "message": "CQ E51ABC BG08",
        "dxcc_status": "ATNO",
        "frequency_mhz": 14.074,
        "heard": True,
    })
    assert target is not None
    selected = controller.next_target(auto_call_start_only=True, cq_only=True)
    assert selected is not None
    attempted = controller.record_attempt(selected.key)
    assert attempted is not None

    assert controller.next_target(auto_call_start_only=True, cq_only=True) is None

    status = controller.status()
    assert status["active_target"]["call"] == "E51ABC"
    assert status["active_qso_state"] == "command_sent"
    assert status["last_decision"]["reason"] == "active-qso-in-progress"


def test_active_attempt_with_real_progress_is_not_released_by_dwell_timeout():
    now = datetime(2026, 6, 5, 12, 30, tzinfo=timezone.utc)
    controller = DigitalAutomationController(mycall="OM0RX")
    first = controller.ingest_target({
        "callsign": "OZ9TAN",
        "grid": "JO65",
        "band": "20m",
        "mode": "FT8",
        "message": "CQ OZ9TAN JO65",
        "dxcc_status": "ATNO",
        "frequency_mhz": 14.09,
        "heard": True,
        "timestamp": now.isoformat(),
    })
    second = controller.ingest_target({
        "callsign": "3G0Z",
        "grid": "FF06",
        "band": "20m",
        "mode": "FT8",
        "message": "CQ 3G0Z FF06",
        "dxcc_status": "ATNO",
        "frequency_mhz": 14.09,
        "heard": True,
        "timestamp": now.isoformat(),
    })
    assert first is not None
    assert second is not None

    selected = controller.next_target(now=now, auto_call_start_only=True, cq_only=True)
    assert selected is not None
    controller.record_attempt(selected.key)
    controller.record_attempt(selected.key)
    controller.transition_active_qso("reply_received", target=selected)

    late = controller.next_target(
        now=now + timedelta(minutes=4),
        auto_call_start_only=True,
        cq_only=True,
    )

    assert late is None
    assert controller.active_target_key == selected.key
    assert controller.targets[selected.key].state == "calling"
    assert controller.status()["active_target"]["call"] == selected.call
    assert controller.status()["last_decision"]["reason"] == "active-qso-in-progress"


def test_wsjtx_status_manual_dx_call_change_abandons_active_target():
    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "callsign": "E51ABC",
        "grid": "BG08",
        "band": "20m",
        "mode": "FT8",
        "message": "CQ E51ABC BG08",
        "dxcc_status": "ATNO",
        "frequency_mhz": 14.074,
        "heard": True,
    })
    assert target is not None
    selected = controller.next_target()
    assert selected is not None
    controller.record_attempt(selected.key)

    result = controller.handle_wsjtx_status({
        "dxCall": "K2MAN",
        "mode": "FT8",
        "band": "20m",
        "manual": True,
    })

    assert result["status"] == "abandoned"
    assert result["target"]["state"] == "backoff"
    assert result["decision"]["reason"] == "manual-dx-call-change"
    assert controller.status()["active_target"] is None
    assert controller.status()["active_qso_state"] == "failed"


def test_wsjtx_status_unrelated_dx_call_does_not_abandon_auto_qso():
    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "callsign": "E51ABC",
        "grid": "BG08",
        "band": "20m",
        "mode": "FT8",
        "message": "CQ E51ABC BG08",
        "dxcc_status": "ATNO",
        "frequency_mhz": 14.074,
        "heard": True,
    })
    assert target is not None
    selected = controller.next_target()
    assert selected is not None
    controller.record_attempt(selected.key)

    result = controller.handle_wsjtx_status({"dxCall": "K2MAN", "mode": "FT8", "band": "20m"})

    assert result["status"] == "observed"
    assert result["decision"]["reason"] == "stale-or-unrelated-dx-call"
    assert controller.status()["active_target"]["call"] == "E51ABC"
    assert controller.status()["active_qso_state"] == "command_sent"


def test_prepare_wsjtx_target_dry_run_does_not_send_bridge_command(monkeypatch):
    from backend.api import ft8 as ft8_api
    import services.wsjtx as wsjtx_module

    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({"automation": {"dryRun": True}})
    fake_ft8_service = SimpleNamespace(automation_controller=controller)
    monkeypatch.setattr(ft8_api, "get_ft8_service", lambda: fake_ft8_service)

    class FakeWsjtxService(WSJTXService):
        def send_bridge_command(self, command, payload=None):
            raise AssertionError("dry-run prepare must not send a bridge command")

    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: FakeWsjtxService())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(classifier=None, cty_resolver=None)))

    result = asyncio.run(
        ft8_api.prepare_wsjtx_automation_target(
            ft8_api.AutomationWsjtxPrepareTargetRequest(
                target={
                    "callsign": "E51ABC",
                    "grid": "BG08",
                    "band": "20m",
                    "mode": "FT8",
                    "source": "spot",
                    "frequency_mhz": 14.074,
                    "dxcc_status": "ATNO",
                    "score": 1000,
                },
                cq_only=False,
                auto_call_start_only=False,
            ),
            request,
        )
    )

    assert result["status"] == "dry-run"
    assert result["bridge"]["sent"] is False
    assert controller.status()["last_decision"]["decision"] == "dry-run"
    assert any(entry["decision"] == "dry-run" for entry in controller.status()["decision_log"])


def test_wsjtx_automation_tick_releases_target_when_bridge_fails(monkeypatch):
    import services.ft8_service as ft8_service_module
    import services.wsjtx as wsjtx_module

    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "message": "CQ R3KBY KO90",
        "callsign": "R3KBY",
        "grid": "KO90",
        "band": "80m",
        "mode": "FT8",
        "source": "wsjtx-decode-status",
        "heard": True,
        "snr": -9,
        "freq": 916,
        "frequency_mhz": 3.573,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })
    assert target is not None

    fake_ft8_service = SimpleNamespace(
        automation_controller=controller,
        set_tx_options=lambda **kwargs: None,
        get_stats=lambda: {},
    )
    monkeypatch.setattr(ft8_service_module, "get_ft8_service", lambda: fake_ft8_service)

    class FailingWsjtxService(WSJTXService):
        def send_bridge_command(self, command, payload=None):
            raise HTTPException(status_code=503, detail="bridge unavailable")

    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: FailingWsjtxService())

    app = FastAPI()
    register_wsjtx_endpoints(app)
    client = TestClient(app)

    response = client.post("/api/wsjtx/automation/tick", json={
        "automation": {
            "autoCall": True,
            "autoCQ": False,
            "cqOnly": True,
            "currentMode": "FT8",
            "modeSwitching": False,
            "enableTx": True,
        }
    })

    assert response.status_code == 503
    assert controller.active_target_key is None
    assert target.state == "heard"
    assert target.attempts == 0
    assert controller.last_decision["reason"] == "bridge-command-failed"


def test_wsjtx_automation_tick_sends_spot_probe_as_listen_only(monkeypatch):
    import services.ft8_service as ft8_service_module
    import services.wsjtx as wsjtx_module

    controller = DigitalAutomationController(mycall="OM0RX")
    controller.apply_operator_settings({
        "automation": {
            "enabled": True,
            "spotHuntEnabled": True,
            "bandPlan": "05:15m,12m",
            "spotListenSeconds": 30,
        }
    })
    spot = controller.ingest_target({
        "callsign": "TT1GD",
        "grid": "JK95",
        "band": "15m",
        "mode": "FT8",
        "source": "rbl",
        "frequency_mhz": 21.074,
        "call_status": "Worked",
        "dxcc_status": "Worked",
    })
    assert spot is not None
    assert spot.state == "listening"

    class FakeFt8Service:
        automation_controller = controller
        mode = "FT8"

        def set_tx_options(self, **kwargs):
            pass

        def get_stats(self):
            return {}

    monkeypatch.setattr(ft8_service_module, "get_ft8_service", lambda: FakeFt8Service())

    sent = []

    class FakeWsjtxService(WSJTXService):
        def send_bridge_command(self, command, payload=None):
            sent.append((command, payload))
            return {"success": True, "sent": command}

    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: FakeWsjtxService())

    app = FastAPI()
    register_wsjtx_endpoints(app)
    client = TestClient(app)

    response = client.post("/api/wsjtx/automation/tick", json={
        "automation": {
            "autoCall": True,
            "autoCQ": False,
            "cqOnly": True,
            "currentBand": "15m",
            "currentMode": "FT8",
            "bandHopping": True,
            "modeSwitching": False,
            "enableTx": True,
        }
    })

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "listening"
    assert body["reason"] == "spot-dxcc-listen-probe"
    assert sent[0][0] == "start_target_qso"
    target_payload = sent[0][1]["target"]
    assert target_payload["call"] == "TT1GD"
    assert target_payload["listenOnly"] is True
    assert target_payload["enableTx"] is False
    assert target_payload["generateMessages"] is False


def test_wsjtx_automation_tick_holds_new_target_after_safe_tx_deadline(monkeypatch):
    import services.ft8_service as ft8_service_module
    import services.wsjtx as wsjtx_module

    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "message": "CQ BG4KAT PM01",
        "callsign": "BG4KAT",
        "grid": "PM01",
        "band": "15m",
        "mode": "FT8",
        "source": "wsjtx-decode-status",
        "heard": True,
        "snr": -16,
        "freq": 1502,
        "frequency_mhz": 21.074,
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    })
    assert target is not None

    class FakeFt8Service:
        automation_controller = controller
        mode = "FT8"

        def set_tx_options(self, **kwargs):
            pass

        def get_stats(self):
            return {}

        def _live_cycle_state(self):
            return (15.0, 4.2, 12345, True)

        def _max_safe_late_start_seconds(self, mode=None):
            return 0.35

    monkeypatch.setattr(ft8_service_module, "get_ft8_service", lambda: FakeFt8Service())

    sent = []

    class FakeWsjtxService(WSJTXService):
        def send_bridge_command(self, command, payload=None):
            sent.append((command, payload))
            return {"success": True, "sent": command}

    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: FakeWsjtxService())

    app = FastAPI()
    register_wsjtx_endpoints(app)
    client = TestClient(app)

    response = client.post("/api/wsjtx/automation/tick", json={
        "automation": {
            "autoCall": True,
            "autoCQ": False,
            "cqOnly": True,
            "currentBand": "15m",
            "currentMode": "FT8",
            "bandHopping": True,
            "modeSwitching": False,
            "enableTx": True,
        }
    })

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "idle"
    assert body["reason"] == "tx-slot-too-late-for-new-target"
    assert sent == []
    assert controller.active_target_key is None
    assert controller.last_decision["reason"] == "tx-slot-too-late-for-new-target"


def test_controller_enriches_unknown_decode_from_local_status_cache():
    controller = DigitalAutomationController(
        mycall="OM0RX",
        settings=DigitalAutomationSettings(avoid_logged=False),
        qso_status_store=_FakeQsoStatusStore(
            call_flags={("E51ABC", "20m", "FT8"): (True, False, True, False, False)},
            dxcc_overall={191: (False, False)},
            dxcc_bandmode={(191, "20m", "FT8"): (True, True, False)},
            grid_flags={("BG08", "20m", "FT8"): (True, True, True)},
        ),
        cty_resolver=_FakeCtyResolver({
            "E51ABC": {
                "country": "North Cook Islands",
                "dxcc": 191,
                "continent": "OC",
                "cq": 32,
                "itu": 62,
            }
        }),
    )

    target = controller.ingest_target({
        "message": "CQ E51ABC BG08",
        "callsign": "E51ABC",
        "grid": "BG08",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -10,
    })

    assert target is not None
    assert target.call_status == "New Band"
    assert target.dxcc_status == "ATNO"
    assert "band" in target.need_reasons
    assert target.reason == "new-dxcc"
    assert target.score == 1000
    assert target.dxcc == 191
    assert target.country == "North Cook Islands"
    assert "qso-call-cache" in target.status_source
    assert "qso-dxcc-cache" in target.status_source


def test_controller_preserves_new_band_status_from_local_status_cache():
    controller = DigitalAutomationController(
        mycall="OM0RX",
        settings=DigitalAutomationSettings(avoid_logged=False),
        qso_status_store=_FakeQsoStatusStore(
            call_flags={("AD9GE", "20m", "FT8"): (True, True, True, False, False)},
            dxcc_overall={291: (True, True)},
            dxcc_bandmode={(291, "20m", "FT8"): (False, False, True)},
        ),
        cty_resolver=_FakeCtyResolver({
            "AD9GE": {
                "country": "United States",
                "dxcc": 291,
                "continent": "NA",
                "cq": 5,
                "itu": 8,
            }
        }),
    )

    target = controller.ingest_target({
        "message": "CQ AD9GE EM69",
        "callsign": "AD9GE",
        "grid": "EM69",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -14,
    })

    assert target is not None
    assert target.call_status == "New Band"
    assert target.dxcc_status == "Confirmed"
    assert "band" in target.need_reasons


def test_controller_treats_worked_decode_with_band_need_as_new_band():
    controller = DigitalAutomationController(
        mycall="OM0RX",
        settings=DigitalAutomationSettings(
            avoid_logged=True,
            filter_matrix_enabled=True,
            filter_new_call=False,
            filter_band_call=True,
            filter_band_grid=False,
        ),
    )

    target = controller.ingest_target({
        "message": "CQ YO3OBB KN34",
        "callsign": "YO3OBB",
        "grid": "KN34",
        "band": "20m",
        "mode": "FT8",
        "source": "wsjtx-decode-status",
        "heard": True,
        "snr": -9,
        "call_status": "Worked",
        "dxcc_status": "Confirmed",
        "needed": {"call": False},
        "needed_on_band": {"call": True, "mode": False},
    })

    assert target is not None
    assert target.call_status == "New Band"
    assert "band" in target.need_reasons
    assert controller.last_decision["decision"] == "queued"


def test_controller_blocks_worked_decode_from_local_status_cache_without_payload_status():
    controller = DigitalAutomationController(
        mycall="OM0RX",
        qso_status_store=_FakeQsoStatusStore(
            call_flags={("DL1ABC", "40m", "FT8"): (True, True, False, False, True)},
            dxcc_overall={230: (True, True)},
            dxcc_bandmode={(230, "40m", "FT8"): (False, False, True)},
        ),
        cty_resolver=_FakeCtyResolver({"DL1ABC": {"country": "Germany", "dxcc": 230}}),
    )

    target = controller.ingest_target({
        "message": "CQ DL1ABC JO62",
        "callsign": "DL1ABC",
        "band": "40m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": 5,
    })

    assert target is None
    assert controller.last_decision["reason"] == "already-worked-call"
    assert controller.last_decision["call_status"] == "Confirmed"


def test_prepare_next_wsjtx_endpoint_prepares_without_attempt_or_tx(monkeypatch):
    from backend.api import ft8 as ft8_api
    import services.wsjtx as wsjtx_module

    controller = DigitalAutomationController(mycall="OM0RX")
    queued = controller.ingest_target({
        "message": "CQ E51ABC BG08",
        "callsign": "E51ABC",
        "grid": "BG08",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -8,
        "frequency_mhz": 14.074,
        "call_status": "New Band",
        "dxcc_status": "ATNO",
    })
    assert queued is not None

    fake_ft8_service = SimpleNamespace(automation_controller=controller)
    monkeypatch.setattr(ft8_api, "get_ft8_service", lambda: fake_ft8_service)

    sent = []

    class FakeWsjtxService(WSJTXService):
        def send_bridge_command(self, command, payload=None):
            sent.append((command, payload))
            return {"success": True, "sent": command}

    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: FakeWsjtxService())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(classifier=None, cty_resolver=None)))

    result = asyncio.run(
        ft8_api.prepare_next_wsjtx_automation_target(
            ft8_api.AutomationWsjtxPrepareRequest(),
            request,
        )
    )

    assert result["status"] == "prepared"
    assert sent[0][0] == "start_target_qso"
    assert sent[0][1]["target"]["call"] == "E51ABC"
    assert sent[0][1]["target"]["enableTx"] is False
    assert queued.attempts == 0
    assert controller.active_target_key == queued.key


def test_controller_chooses_clear_wsjtx_tx_offset_from_recent_decodes():
    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target({
        "message": "CQ E51ABC BG08",
        "callsign": "E51ABC",
        "grid": "BG08",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -8,
        "freq": 1240,
        "frequency_mhz": 14.074,
        "call_status": "New Band",
        "dxcc_status": "ATNO",
    })
    assert target is not None
    for call, offset in (("EA1AAA", 1450), ("EA2BBB", 1500), ("EA3CCC", 1550)):
        controller.ingest_target({
            "message": f"CQ {call} IN80",
            "callsign": call,
            "grid": "IN80",
            "band": "20m",
            "mode": "FT8",
            "source": "decoded",
            "heard": True,
            "snr": -5,
            "freq": offset,
            "frequency_mhz": 14.074,
            "call_status": "New Call",
            "dxcc_status": "Confirmed",
        })

    plan = controller.choose_tx_audio_offset(target, preferred_hz=1500, guard_hz=90)

    assert plan["reason"] == "nearest-clear"
    assert plan["occupied"] == [1450, 1500, 1550]
    assert abs(plan["tx_df"] - 1500) >= 100
    assert all(abs(plan["tx_df"] - offset) >= 90 for offset in plan["occupied"])


def test_prepare_next_wsjtx_endpoint_uses_clear_tx_offset(monkeypatch):
    from backend.api import ft8 as ft8_api
    import services.wsjtx as wsjtx_module

    controller = DigitalAutomationController(mycall="OM0RX")
    queued = controller.ingest_target({
        "message": "CQ E51ABC BG08",
        "callsign": "E51ABC",
        "grid": "BG08",
        "band": "20m",
        "mode": "FT8",
        "source": "decoded",
        "heard": True,
        "snr": -8,
        "freq": 1230,
        "frequency_mhz": 14.074,
        "call_status": "New Band",
        "dxcc_status": "ATNO",
    })
    assert queued is not None
    for call, offset in (("EA1AAA", 1450), ("EA2BBB", 1500), ("EA3CCC", 1550)):
        controller.ingest_target({
            "message": f"CQ {call} IN80",
            "callsign": call,
            "grid": "IN80",
            "band": "20m",
            "mode": "FT8",
            "source": "decoded",
            "heard": True,
            "snr": -5,
            "freq": offset,
            "frequency_mhz": 14.074,
            "call_status": "New Call",
            "dxcc_status": "Confirmed",
        })

    fake_ft8_service = SimpleNamespace(automation_controller=controller)
    monkeypatch.setattr(ft8_api, "get_ft8_service", lambda: fake_ft8_service)

    sent = []

    class FakeWsjtxService(WSJTXService):
        def send_bridge_command(self, command, payload=None):
            sent.append((command, payload))
            return {"success": True, "sent": command}

    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: FakeWsjtxService())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(classifier=None, cty_resolver=None)))

    result = asyncio.run(
        ft8_api.prepare_next_wsjtx_automation_target(
            ft8_api.AutomationWsjtxPrepareRequest(),
            request,
        )
    )

    assert result["status"] == "prepared"
    assert result["tx_df_plan"]["occupied"] == [1450, 1500, 1550]
    assert result["wsjtx_target"]["txDf"] == result["tx_df_plan"]["tx_df"]
    assert result["wsjtx_target"]["enableTx"] is False
    assert sent[0][1]["target"]["txDf"] == result["tx_df_plan"]["tx_df"]
    assert all(abs(result["wsjtx_target"]["txDf"] - offset) >= 90 for offset in (1450, 1500, 1550))
    assert queued.attempts == 0


def test_prepare_selected_spot_wsjtx_endpoint_uses_automation_guardrails(monkeypatch):
    from backend.api import ft8 as ft8_api
    import services.wsjtx as wsjtx_module

    controller = DigitalAutomationController(mycall="OM0RX")
    fake_ft8_service = SimpleNamespace(automation_controller=controller)
    monkeypatch.setattr(ft8_api, "get_ft8_service", lambda: fake_ft8_service)

    sent = []

    class FakeWsjtxService(WSJTXService):
        def send_bridge_command(self, command, payload=None):
            sent.append((command, payload))
            return {"success": True, "sent": command}

    monkeypatch.setattr(wsjtx_module, "get_wsjtx_service", lambda: FakeWsjtxService())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(classifier=None, cty_resolver=None)))

    result = asyncio.run(
        ft8_api.prepare_wsjtx_automation_target(
            ft8_api.AutomationWsjtxPrepareTargetRequest(
                target={
                    "callsign": "P29ABC",
                    "grid": "QI30",
                    "band": "20m",
                    "mode": "FT8",
                    "source": "spot",
                    "frequency_mhz": 14.074,
                    "call_status": "New Band",
                    "dxcc_status": "ATNO",
                    "score": 125,
                },
                cq_only=False,
                auto_call_start_only=False,
            ),
            request,
        )
    )

    assert result["status"] == "prepared"
    assert sent[0][0] == "start_target_qso"
    assert sent[0][1]["target"]["call"] == "P29ABC"
    assert sent[0][1]["target"]["enableTx"] is False
    assert result["target"]["state"] == "selected"
    assert result["automation"]["active_target"]["call"] == "P29ABC"
    assert result["automation"]["active_target"]["attempts"] == 0


def test_batch_spot_candidates_queue_without_wsjtx_or_tx(monkeypatch):
    from backend.api import ft8 as ft8_api

    controller = DigitalAutomationController(mycall="OM0RX")
    fake_ft8_service = SimpleNamespace(automation_controller=controller)
    monkeypatch.setattr(ft8_api, "get_ft8_service", lambda: fake_ft8_service)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(classifier=None, cty_resolver=None)))

    result = asyncio.run(
        ft8_api.ingest_automation_targets(
            ft8_api.AutomationTargetsRequest(
                targets=[
                    {
                        "callsign": "P29ABC",
                        "grid": "QI30",
                        "band": "20m",
                        "mode": "FT8",
                        "source": "cluster",
                        "frequency_mhz": 14.074,
                        "call_status": "New Band",
                        "dxcc_status": "ATNO",
                        "score": 125,
                        "enableTx": True,
                    },
                    {
                        "callsign": "OM0RX",
                        "grid": "JN88",
                        "band": "20m",
                        "mode": "FT8",
                        "source": "cluster",
                        "frequency_mhz": 14.074,
                    },
                ],
                limit=10,
            ),
            request,
        )
    )

    assert result["status"] == "queued"
    assert result["queued_count"] == 1
    assert result["skipped_count"] == 1
    assert result["queued"][0]["call"] == "P29ABC"
    assert result["queued"][0]["state"] in {"queued", "listening"}
    assert result["automation"]["queue_length"] == 1
    assert result["automation"]["active_target"] is None


def test_planner_promote_and_skip_endpoints_do_not_select_or_tx(monkeypatch):
    from backend.api import ft8 as ft8_api

    controller = DigitalAutomationController(mycall="OM0RX")
    target = controller.ingest_target(
        {
            "callsign": "P29ABC",
            "grid": "QI30",
            "band": "20m",
            "mode": "FT8",
            "source": "spot",
            "frequency_mhz": 14.074,
            "call_status": "New Band",
            "dxcc_status": "ATNO",
            "score": 125,
        }
    )
    assert target is not None
    fake_ft8_service = SimpleNamespace(automation_controller=controller)
    monkeypatch.setattr(ft8_api, "get_ft8_service", lambda: fake_ft8_service)

    promoted = asyncio.run(
        ft8_api.promote_automation_target(
            ft8_api.AutomationTargetKeyRequest(key=target.key),
        )
    )
    assert promoted["status"] == "promoted"
    assert promoted["target"]["call"] == "P29ABC"
    assert promoted["automation"]["active_target"] is None

    skipped = asyncio.run(
        ft8_api.skip_automation_target(
            ft8_api.AutomationTargetKeyRequest(key=target.key, reason="operator-removed"),
        )
    )
    assert skipped["status"] == "skipped"
    assert skipped["target"]["state"] == "skipped"
    assert skipped["target"]["reason"] == "operator-removed"
    assert skipped["automation"]["active_target"] is None
