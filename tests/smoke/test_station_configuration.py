from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.station import router
from backend.core.context import AppContext, install_app_context
from radio_control import config
from services.station_configuration import (
    build_configuration_snapshot,
    preview_configuration_restore,
)


class CachedManager:
    def snapshot(self):
        return {
            "kpa500": {
                "enabled": True,
                "connected": True,
                "port": "COM17",
                "firmware": "1.54",
                "operate": True,
            },
            "kat500": {
                "enabled": True,
                "connected": True,
                "port": "COM15",
                "firmware": "2.16",
                "frequency_khz": 7074,
            },
        }


class Coordinator:
    elecraft = CachedManager()


def test_snapshot_is_semantic_cached_and_excludes_live_or_secret_state(monkeypatch):
    monkeypatch.setattr(config, "KPA500_PORT", "COM17")
    monkeypatch.setattr(config, "KAT500_PORT", "COM15")

    snapshot = build_configuration_snapshot(CachedManager())

    assert snapshot["schema_version"] == 1
    assert snapshot["restorable"] is False
    assert snapshot["settings"]["KPA500_PORT"] == "COM17"
    assert snapshot["devices"]["kpa500"]["firmware"] == "1.54"
    assert "operate" not in snapshot["devices"]["kpa500"]
    assert "frequency_khz" not in snapshot["devices"]["kat500"]
    assert "STATION_COORDINATOR_COMMISSIONED" not in snapshot["settings"]


def test_restore_preview_classifies_route_and_tune_changes(monkeypatch):
    monkeypatch.setattr(config, "STATION_TUNE_POWER_W", 20)
    monkeypatch.setattr(config, "KAT500_ANTENNA_POLICY", {"20m": 1})
    snapshot = build_configuration_snapshot(CachedManager())
    snapshot["settings"]["STATION_TUNE_POWER_W"] = 25
    snapshot["settings"]["KAT500_ANTENNA_POLICY"] = {"20m": 2}

    preview = preview_configuration_restore(snapshot)

    assert preview["preview_only"] is True
    assert preview["apply_available"] is False
    assert preview["change_count"] == 2
    assert preview["requires_maintenance"] is True
    assert {item["class"] for item in preview["changes"]} == {"route", "tune-safety"}


def test_restore_preview_rejects_commissioning_or_invalid_power(monkeypatch):
    snapshot = build_configuration_snapshot(CachedManager())
    snapshot["settings"]["STATION_COORDINATOR_COMMISSIONED"] = True
    with pytest.raises(ValueError, match="unsupported keys"):
        preview_configuration_restore(snapshot)

    snapshot = build_configuration_snapshot(CachedManager())
    snapshot["settings"]["STATION_TUNE_POWER_W"] = 100
    with pytest.raises(ValueError, match="between 15 and 30"):
        preview_configuration_restore(snapshot)


def test_configuration_api_exports_and_previews_without_an_apply_route(monkeypatch):
    monkeypatch.setattr(config, "KPA500_PORT", "COM17")
    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=Coordinator()))
    app.include_router(router)

    with TestClient(app) as client:
        exported = client.get("/api/station/configuration/snapshot")
        snapshot = exported.json()["configuration_snapshot"]
        snapshot["settings"]["STATION_TUNE_POWER_W"] = 25
        previewed = client.post(
            "/api/station/configuration/restore-preview",
            json={"snapshot": snapshot},
        )
        no_apply = client.post(
            "/api/station/configuration/restore",
            json={"snapshot": snapshot},
        )

    assert exported.status_code == 200
    assert exported.json()["configuration_snapshot"]["restorable"] is False
    assert previewed.status_code == 200
    assert previewed.json()["restore_preview"]["apply_available"] is False
    assert no_apply.status_code == 404


def test_configuration_restore_preview_api_rejects_unsafe_keys():
    snapshot = build_configuration_snapshot(CachedManager())
    snapshot["settings"]["STATION_COORDINATOR_COMMISSIONED"] = True
    app = FastAPI()
    install_app_context(app, AppContext(station_coordinator=Coordinator()))
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/station/configuration/restore-preview",
            json={"snapshot": snapshot},
        )

    assert response.status_code == 422
    assert "unsupported keys" in response.json()["detail"]
