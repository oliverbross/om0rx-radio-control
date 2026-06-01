"""Smoke tests for backend-owned Digital automation target control."""

from datetime import datetime, timezone

import _bootstrap  # noqa: F401

from services.digital_automation import DigitalAutomationController, score_payload


def test_goal_scoring_prioritises_dxcc_band_grid_mode_call():
    assert score_payload({"dxcc_status": "ATNO"}) == 1000
    assert score_payload({"dxcc_status": "C/New Band"}) == 800
    assert score_payload({"call_status": "New Band"}) == 650
    assert score_payload({"needed": {"grid": True}}) == 500
    assert score_payload({"call_status": "New Mode"}) == 350
    assert score_payload({"call_status": "New Call"}) == 200
    assert score_payload({"call_status": "Confirmed", "dxcc_status": "Confirmed"}) == 0


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

    assert controller.ingest_target({
        "callsign": "K2ABC",
        "band": "10m",
        "mode": "FT8",
        "call_status": "New Band",
        "dxcc_status": "Confirmed",
        "heard": True,
    }) is None
    assert controller.last_decision["reason"] == "already-worked-call"


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

    target.call_status = "New Band"

    assert controller.next_target(auto_call_start_only=True) is None
    assert target.state == "skipped"
    assert target.reason == "already-worked-call"


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
