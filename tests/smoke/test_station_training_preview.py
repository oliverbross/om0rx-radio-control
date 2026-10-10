from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.station import router
from backend.core.context import AppContext, install_app_context
from radio_control import config
from services.station_training import BAND_ORDER, TrainingPreviewRequest, build_training_preview


class NoHardwareDevice:
    def __getattribute__(self, name):
        if name.startswith("__"):
            return object.__getattribute__(self, name)
        raise AssertionError(f"training preview touched hardware attribute {name}")


class PreviewManager:
    antenna_policy = {"40m": 2, "20m": 1, "60m": 2}
    kpa500 = NoHardwareDevice()
    kat500 = NoHardwareDevice()


class PreviewCoordinator:
    elecraft = PreviewManager()


def configure_preview(monkeypatch):
    monkeypatch.setattr(
        config,
        "FLEX_ANTENNA_POLICY",
        {"enabled": True, "bands": {"40m": "ANT1", "20m": "ANT1", "60m": "ANT1"}},
    )
    monkeypatch.setattr(config, "KAT500_ANTENNA_NAMES", {"1": "Beam", "2": "Wire"})
    monkeypatch.setattr(config, "STATION_AMPLIFIER_ALLOWED_BANDS", ["40m", "20m"])
    monkeypatch.setattr(config, "STATION_TUNE_POWER_W", 20)
    monkeypatch.setattr(config, "STATION_TUNE_TIMEOUT_SECONDS", 30.0)
    monkeypatch.setattr(
        config,
        "FT8_OPERATOR_SETTINGS",
        {
            "frequencyPlan": [
                {"band": "40m", "ft8": 7.074},
                {"band": "20m", "ft8": 14.074},
                {"band": "60m", "ft8": 5.357},
            ]
        },
    )


def test_preview_builds_exact_routes_and_marks_prohibited_band(monkeypatch):
    configure_preview(monkeypatch)

    preview = build_training_preview(
        PreviewManager.antenna_policy,
        TrainingPreviewRequest(bands=("40m", "60m")),
    )

    assert preview["preview_only"] is True
    assert preview["execution_available"] is False
    assert preview["eligible_count"] == 1
    assert preview["blocked_count"] == 1
    assert preview["total_worst_case_seconds"] == 38.0
    assert preview["points"][0] == {
        "sequence": 1,
        "band": "40m",
        "frequency_mhz": 7.074,
        "frequency_khz": 7074,
        "route_id": "40m-flex-ant1-kat-ant2",
        "flex_tx_ant": "ANT1",
        "kat_antenna": 2,
        "antenna_name": "Wire",
        "amplifier_allowed": True,
        "eligible": True,
        "disposition": "preview-only",
        "blocked_reasons": [],
        "tune_power_w": 20,
        "worst_case_seconds": 38.0,
    }
    assert preview["points"][1]["amplifier_allowed"] is False
    assert preview["points"][1]["disposition"] == "blocked"


def test_invalid_or_unconfigured_routes_fail_closed(monkeypatch):
    configure_preview(monkeypatch)
    monkeypatch.setattr(config, "FLEX_ANTENNA_POLICY", {"enabled": True, "bands": {}})

    preview = build_training_preview(
        {},
        TrainingPreviewRequest(
            bands=("20m", "not-a-band"),
            frequency_points_mhz={"20m": (7.074,)},
        ),
    )

    assert preview["eligible_count"] == 0
    assert preview["points"][0]["eligible"] is False
    assert any("belongs to 40m" in reason for reason in preview["points"][0]["blocked_reasons"])
    assert preview["validation_errors"][0]["code"] == "unsupported-band"


def test_training_preview_api_is_read_only_and_bounded(monkeypatch):
    configure_preview(monkeypatch)
    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=PreviewCoordinator()))
    app.include_router(router)

    with TestClient(app) as client:
        default = client.get("/api/station/training/preview")
        custom = client.post(
            "/api/station/training/preview",
            json={"bands": ["20m"], "frequency_points_mhz": {"20m": [14.074]}},
        )
        rejected = client.post(
            "/api/station/training/preview",
            json={"bands": ["20m"], "frequency_points_mhz": {"20m": [14.074] * 21}},
        )

    assert default.status_code == 200
    assert custom.status_code == 200
    assert custom.json()["training_preview"]["points"][0]["frequency_khz"] == 14074
    assert rejected.status_code == 422


def test_portion_profiles_generate_deterministic_kat_memory_points(monkeypatch):
    configure_preview(monkeypatch)

    first = build_training_preview(
        PreviewManager.antenna_policy,
        TrainingPreviewRequest(
            bands=("40m", "20m"),
            portions=("ssb", "cw", "data"),
            coverage="representative",
        ),
    )
    second = build_training_preview(
        PreviewManager.antenna_policy,
        TrainingPreviewRequest(
            bands=("40m", "20m"),
            portions=("data", "cw", "ssb"),
            coverage="representative",
        ),
    )

    assert first["execution_available"] is False
    assert first["portions"] == ["cw", "data", "ssb"]
    assert first["selection"] == {"mode": "multi", "bands": ["40m", "20m"]}
    assert first["points"] == second["points"]
    assert [point["frequency_mhz"] for point in first["points"][:3]] == [
        7.02,
        7.05,
        7.13,
    ]
    assert all(point["kat_memory_bin"]["bin_size_khz"] == 20 for point in first["points"])
    assert first["plot"]["x_axis"]["unit"] == "MHz"
    assert [segment["label"] for segment in first["plot"]["segments"][:3]] == [
        "CW",
        "Data",
        "SSB",
    ]


def test_full_bin_coverage_uses_official_kat_segment_sizes(monkeypatch):
    configure_preview(monkeypatch)
    monkeypatch.setattr(
        config,
        "FLEX_ANTENNA_POLICY",
        {
            "enabled": True,
            "bands": {"160m": "ANT1", "40m": "ANT1", "10m": "ANT1", "6m": "ANT1"},
        },
    )
    antenna_policy = {"160m": 2, "40m": 2, "10m": 1, "6m": 1}

    preview = build_training_preview(
        antenna_policy,
        TrainingPreviewRequest(
            bands=("160m", "40m", "10m", "6m"),
            portions=("cw",),
            coverage="full_bins",
        ),
    )

    sizes = {
        band: {
            point["kat_memory_bin"]["bin_size_khz"]
            for point in preview["points"]
            if point["band"] == band
        }
        for band in ("160m", "40m", "10m", "6m")
    }
    assert sizes == {"160m": {10}, "40m": {20}, "10m": {100}, "6m": {200}}
    assert preview["point_count"] <= 100
    assert preview["point_generation"]["bounded"] is True


def test_all_band_full_bin_plan_is_deterministically_bounded(monkeypatch):
    configure_preview(monkeypatch)
    monkeypatch.setattr(
        config,
        "FLEX_ANTENNA_POLICY",
        {"enabled": True, "bands": {band: "ANT1" for band in BAND_ORDER}},
    )
    antenna_policy = {band: 1 for band in BAND_ORDER}
    request = TrainingPreviewRequest(
        bands=BAND_ORDER,
        portions=("cw", "data", "ssb"),
        coverage="full_bins",
        erase_selected_memories=True,
    )

    first = build_training_preview(antenna_policy, request)
    second = build_training_preview(antenna_policy, request)

    assert first["point_count"] == 100
    assert first["points"] == second["points"]
    assert first["erase_plan"]["item_count"] == len(BAND_ORDER)
    assert first["execution_available"] is False
    assert first["valid"] is False
    assert [error["code"] for error in first["validation_errors"]].count("too-many-points") == 1


def test_explicit_points_override_profiles_and_erase_is_scope_only(monkeypatch):
    configure_preview(monkeypatch)

    preview = build_training_preview(
        PreviewManager.antenna_policy,
        TrainingPreviewRequest(
            bands=("40m",),
            frequency_points_mhz={"40m": (7.111, 7.155)},
            portions=("cw", "data", "ssb"),
            coverage="full_bins",
            erase_selected_memories=True,
        ),
    )

    assert [point["frequency_mhz"] for point in preview["points"]] == [7.111, 7.155]
    assert all(point["point_source"] == "explicit" for point in preview["points"])
    assert preview["erase_plan"] == {
        "requested": True,
        "preview_only": True,
        "execution_available": False,
        "scope": "selected-band-and-routed-kat-antenna",
        "item_count": 1,
        "items": [
            {
                "band": "40m",
                "band_code": "03",
                "kat_antenna": 2,
                "antenna_name": "Wire",
                "route_id": "40m-flex-ant1-kat-ant2",
                "scope_valid": True,
                "command_description": "Clear KAT500 frequency memories for 40m on ANT2 only",
            }
        ],
    }
    assert "command" not in preview["erase_plan"]["items"][0]


def test_enhanced_training_preview_api_contract(monkeypatch):
    configure_preview(monkeypatch)
    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=PreviewCoordinator()))
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/station/training/preview",
            json={
                "bands": ["40m"],
                "portions": ["cw", "data"],
                "coverage": "full_bins",
                "erase_selected_memories": True,
            },
        )
        invalid = client.post(
            "/api/station/training/preview",
            json={"bands": ["40m"], "portions": ["am"]},
        )

    assert response.status_code == 200
    plan = response.json()["training_preview"]
    assert plan["coverage"] == "full_bins"
    assert plan["erase_plan"]["requested"] is True
    assert plan["execution_available"] is False
    assert invalid.status_code == 422
