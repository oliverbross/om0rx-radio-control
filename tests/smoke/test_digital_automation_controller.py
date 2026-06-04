"""Smoke tests for backend-owned Digital automation target control."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import _bootstrap  # noqa: F401

from services.digital_automation import DigitalAutomationController, score_payload
from services.wsjtx import WSJTXService


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

    new_band_target = controller.ingest_target({
        "callsign": "K2ABC",
        "band": "10m",
        "mode": "FT8",
        "call_status": "New Band",
        "dxcc_status": "Confirmed",
        "heard": True,
    })
    assert new_band_target is not None
    assert new_band_target.reason == "new-band-slot"


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

    target.call_status = "Worked"

    assert controller.next_target(auto_call_start_only=True) is None
    assert target.state == "skipped"
    assert target.reason == "already-worked-call"


def test_avoid_logged_allows_needed_band_and_mode_slots():
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
    assert controller.status()["eligible_count"] == 2


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
        "call_status": "New Band",
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


def test_controller_enriches_unknown_decode_from_local_status_cache():
    controller = DigitalAutomationController(
        mycall="OM0RX",
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
    assert target.reason == "new-dxcc"
    assert target.score == 1000
    assert target.dxcc == 191
    assert target.country == "North Cook Islands"
    assert "qso-call-cache" in target.status_source
    assert "qso-dxcc-cache" in target.status_source


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
            "call_status": "New Band",
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
            "call_status": "New Band",
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
