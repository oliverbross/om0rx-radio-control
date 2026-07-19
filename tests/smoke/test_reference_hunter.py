from radio_control.activity_references import (
    extract_activity_references,
    reference_items_to_qso_fields,
)
from radio_control.wavelog_api import WavelogClient
from services.digital_automation import DigitalAutomationController, DigitalAutomationSettings


def _hunter_settings(**updates):
    automation = {
        "referenceHunterEnabled": True,
        "hunterPrograms": ["POTA", "SOTA", "IOTA", "WWFF", "WWBOTA", "ARLHS"],
        "hunterMinSpotScore": 50,
        "hunterSpotFilters": {
            "bands": ["40m"],
            "modes": ["FT8"],
            "spotSources": ["cluster"],
        },
    }
    automation.update(updates)
    return DigitalAutomationSettings.from_operator_settings({"automation": automation})


def _reference_spot(status="needed", reference="K-1234"):
    return {
        "callsign": "K1ABC",
        "band": "40m",
        "mode": "FT8",
        "source": "cluster",
        "spot_source": "cluster",
        "frequency_mhz": 7.074,
        "spot_score": 70,
        "propagation": {"score": 70, "label": "GOOD"},
        "call_status": "Worked",
        "dxcc_status": "Confirmed",
        "reference_items": [
            {
                "type": "POTA",
                "reference_id": reference,
                "status": status,
                "need_reason": "pota" if status == "needed" else "",
            }
        ],
    }


def test_extracts_requested_reference_programs_and_maps_adif_fields():
    cases = {
        "POTA K-1234": ("POTA", "K-1234"),
        "CQ SOTA OM/ZA-001": ("SOTA", "OM/ZA-001"),
        "IOTA EU-123": ("IOTA", "EU-123"),
        "WWFF OMFF-0123": ("WWFF", "OMFF-0123"),
        "WWBOTA B/OM-0123": ("WWBOTA", "B/OM-0123"),
        "ARLHS SVK-001 lighthouse": ("ARLHS", "SVK-001"),
    }
    for comment, expected in cases.items():
        references = extract_activity_references({"comment": comment, "special": comment})
        assert (references[0]["type"], references[0]["reference_id"]) == expected

    fields = reference_items_to_qso_fields(
        [
            {"type": "POTA", "id": "K-1234"},
            {"type": "WWFF", "id": "OMFF-0123"},
            {"type": "WWBOTA", "id": "B/OM-0123"},
        ]
    )
    assert fields == {
        "pota": "K-1234",
        "wwff": "OMFF-0123",
        "sig": "WWBOTA",
        "sig_info": "B/OM-0123",
    }

    adif = WavelogClient().build_adif_string(
        {
            "callsign": "K1ABC",
            "frequency": 7.074,
            "mode": "FT8",
            **fields,
        }
    ).upper()
    assert "<POTA_REF:6>K-1234" in adif
    assert "<WWFF_REF:9>OMFF-0123" in adif
    assert "<SIG:6>WWBOTA" in adif
    assert "<SIG_INFO:9>B/OM-0123" in adif


def test_worked_callsign_with_new_reference_is_hunted_after_decode():
    controller = DigitalAutomationController(mycall="OM0RX", settings=_hunter_settings())
    target = controller.ingest_target(_reference_spot())
    assert target is not None
    assert target.score_reason == "reference"
    assert controller.next_listen_target().call == "K1ABC"

    decoded = controller.ingest_target(
        {
            "callsign": "K1ABC",
            "band": "40m",
            "mode": "FT8",
            "source": "wsjtx-decode-status",
            "heard": True,
            "message": "CQ K1ABC FN31",
            "snr": -10,
            "call_status": "Worked",
            "dxcc_status": "Confirmed",
        }
    )
    assert decoded is not None
    assert decoded.reference_items[0]["id"] == "K-1234"
    assert controller.next_target(auto_call_start_only=True).call == "K1ABC"


def test_same_callsign_and_reference_is_rejected_before_qsy():
    controller = DigitalAutomationController(mycall="OM0RX", settings=_hunter_settings())
    assert controller.ingest_target(_reference_spot(status="worked")) is None
    assert controller.last_decision["reason"] == "spot-not-hunt-interest"


def test_filters_snapshot_and_score_gate_reference_hunts():
    controller = DigitalAutomationController(mycall="OM0RX", settings=_hunter_settings())
    assert controller.ingest_target({**_reference_spot(), "band": "20m"}) is None
    assert controller.ingest_target({**_reference_spot(), "spot_score": 49}) is None


def test_reference_hunter_api_persists_and_applies_settings(monkeypatch):
    from backend.api import ft8 as ft8_api

    controller = DigitalAutomationController(mycall="OM0RX")
    service = SimpleNamespace(automation_controller=controller)
    saved = {}
    monkeypatch.setattr(ft8_api, "get_ft8_service", lambda: service)
    monkeypatch.setattr(ft8_api, "save_config_updates", lambda updates: saved.update(updates))
    monkeypatch.setattr(ft8_api.app_config, "FT8_OPERATOR_SETTINGS", {}, raising=False)

    result = asyncio.run(
        ft8_api.update_reference_hunter_settings(
            ft8_api.ReferenceHunterSettingsRequest(
                enabled=True,
                programs=["POTA", "WWBOTA"],
                min_spot_score=60,
                hunt_watchdog_minutes=5,
                restore_watchdog_minutes=2,
                spot_filters={"bands": ["40m"], "modes": ["FT8"]},
            )
        )
    )

    assert result["enabled"] is True
    assert controller.settings.enabled is True
    assert controller.settings.require_heard_before_call is True
    assert controller.settings.hunter_programs == {"POTA", "WWBOTA"}
    assert controller.settings.hunter_min_spot_score == 60
    assert saved["FT8_OPERATOR_SETTINGS"]["automation"]["hunterWatchdogMinutes"] == 5
import asyncio
from types import SimpleNamespace
