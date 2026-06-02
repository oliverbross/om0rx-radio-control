#!/usr/bin/env python3
"""Smoke checks for the frontend/backend API contract."""

import time
from pathlib import Path

import _bootstrap  # noqa: F401
from fastapi.testclient import TestClient

import backend.main
from backend.api import solar as solar_api
from activity_intelligence.repository import ActivityRepository
from activity_intelligence.services import ActivityIntelligenceService
import activity_intelligence.services as ai_services


backend.main.register_all_services()
app = backend.main.app
client = TestClient(app)


GET_ROUTES = [
    "/api/health",
    "/api/status",
    "/api/sync-status",
    "/api/config",
    "/api/rotor/status",
    "/api/rotor/config",
    "/api/rotor/auto/status",
    "/api/wsjtx/config",
    "/api/ft8/status",
    "/api/ft8/config",
    "/api/ft8/decoded",
    "/api/ft8/qsos",
    "/api/ft8/waterfall",
    "/api/ft8/automation/status",
    "/api/ft8/audio-devices",
    "/api/spots",
    "/api/spots/count",
    "/api/spots/explain/{callsign:path}",
    "/api/spots/recent",
    "/api/spots/callsign/{callsign}",
    "/api/spots/stats/band",
    "/api/spots/stats/mode",
    "/api/spots/stats/country",
    "/api/spots/special",
    "/api/spots/source-stats",
    "/api/cluster/rbl/status",
    "/api/cluster/rbl/profiles",
    "/api/activity-intelligence",
    "/api/activity-intelligence/reference",
    "/api/activity-intelligence/rbn",
    "/api/country/data",
    "/api/country/by-name/{name}",
    "/api/qrz/profile/{callsign:path}",
    "/api/qrz/history/{callsign:path}",
    "/api/qso/outbox/status",
    "/api/wavelog/contacts",
    "/api/wavelog-log/entries",
    "/api/wavelog-log/stats",
    "/api/wavelog-log/search/{callsign:path}",
    "/api/wavelog-log/sync-status",
    "/api/wavelog-log/statistics",
    "/api/wavelog-log/wp-statistics",
    "/api/solar",
    "/api/solar/health",
    "/logs/qso_log.adif",
]

POST_ROUTES = [
    "/api/frequency",
    "/api/mode",
    "/api/band",
    "/api/filter",
    "/api/volume",
    "/api/drive",
    "/api/tune_power",
    "/api/mic",
    "/api/monitor",
    "/api/agc_threshold",
    "/api/mox",
    "/api/tune",
    "/api/vox",
    "/api/breakin",
    "/api/step",
    "/api/agc",
    "/api/dsp",
    "/api/dsp_level",
    "/api/rit",
    "/api/xit",
    "/api/rx2",
    "/api/split",
    "/api/config",
    "/api/rotor/goto",
    "/api/rotor/direction",
    "/api/rotor/config",
    "/api/rotor/bearing",
    "/api/rotor/resolve",
    "/api/rotor/auto/bearing",
    "/api/rotor/auto/config",
    "/api/rotor/auto/goto",
    "/api/cluster/command",
    "/api/cluster/rbl",
    "/api/activity-intelligence/refresh",
    "/api/activity-intelligence/contest-context",
    "/api/cluster/reconnect",
    "/api/shutdown",
    "/api/restart",
    "/api/wsjtx/log-qso",
    "/api/wsjtx/auto-rotate",
    "/api/ft8/start",
    "/api/ft8/stop",
    "/api/ft8/config",
    "/api/ft8/transmit",
    "/api/ft8/cq",
    "/api/ft8/reply",
    "/api/ft8/send73",
    "/api/ft8/decoded/clear",
    "/api/ft8/automation/settings",
    "/api/ft8/automation/target",
    "/api/ft8/automation/next",
    "/api/ft8/automation/attempt",
    "/api/spots/add-to-radio",
    "/api/spots/filtered-search",
    "/api/qso/log",
    "/api/qso/outbox/retry",
    "/api/wavelog/private_lookup",
    "/api/wavelog/recent_qsos",
    "/api/wavelog-log/reset-sync",
    "/api/solar/refresh",
]

RETIRED_ROUTES = [
    ("GET", "/api/adif/sync"),
    ("GET", "/api/adif/stats"),
    ("GET", "/api/adif/qsos"),
    ("GET", "/api/adif/callsign/{callsign}"),
    ("GET", "/api/adif/band/{band}"),
    ("GET", "/api/adif/mode/{mode}"),
    ("GET", "/api/adif/date-range/{start_date}/{end_date}"),
    ("GET", "/api/adif/worked-before/{callsign}"),
    ("GET", "/api/adif/count"),
    ("GET", "/api/adif/all"),
    ("GET", "/api/qsos/duckdb"),
    ("GET", "/api/qsos/duckdb/by-call"),
]

WEBSOCKET_ROUTES = [
    "/ws/radio",
    "/api/ft8/ws",
]


def route_exists(method: str, path: str) -> bool:
    for route in app.routes:
        route_path = getattr(route, "path", None)
        route_methods = getattr(route, "methods", set()) or set()
        if route_path == path and method in route_methods:
            return True
    return False


def websocket_route_exists(path: str) -> bool:
    return any(getattr(route, "path", None) == path for route in app.routes)


def assert_response_has_keys(method: str, path: str, expected_keys: set[str], **kwargs) -> dict:
    response = client.request(method, path, **kwargs)
    assert response.status_code == 200, f"{method} {path} returned {response.status_code}: {response.text}"
    payload = response.json()
    missing = expected_keys - set(payload.keys())
    assert not missing, f"{method} {path} missing keys: {sorted(missing)}"
    return payload


def install_temp_activity_service(tmp_path):
    ai_services._service = ActivityIntelligenceService(repository=ActivityRepository(tmp_path / "activity_intelligence.duckdb"))


def test_frontend_routes_are_registered():
    missing = []
    for path in GET_ROUTES:
        if not route_exists("GET", path):
            missing.append(f"GET {path}")
    for path in POST_ROUTES:
        if not route_exists("POST", path):
            missing.append(f"POST {path}")
    for path in WEBSOCKET_ROUTES:
        if not websocket_route_exists(path):
            missing.append(f"WS {path}")

    assert not missing, "Missing frontend contract routes:\n" + "\n".join(missing)


def test_legacy_adif_duckdb_routes_are_retired():
    active = [
        f"{method} {path}"
        for method, path in RETIRED_ROUTES
        if route_exists(method, path)
    ]

    assert not active, "Retired ADIF/DuckDB routes are still registered:\n" + "\n".join(active)


def test_legacy_ft8_tx_routes_are_disabled_by_default(monkeypatch):
    import backend.api.ft8 as ft8_api

    monkeypatch.setattr(ft8_api.app_config, "FT8_LEGACY_TX_ROUTES_ENABLED", False, raising=False)

    checks = [
        ("POST", "/api/ft8/transmit", {"json": {"message": "CQ OM0RX JN88"}}),
        ("POST", "/api/ft8/cq", {}),
        ("POST", "/api/ft8/reply", {"json": {"their_call": "EA1AA", "report": "R-10"}}),
        ("POST", "/api/ft8/send73?their_call=EA1AA", {}),
    ]

    for method, path, kwargs in checks:
        response = client.request(method, path, **kwargs)
        assert response.status_code == 410, f"{method} {path} returned {response.status_code}: {response.text}"
        assert "deprecated and disabled" in response.text


def test_safe_frontend_read_contracts(tmp_path):
    install_temp_activity_service(tmp_path)
    solar_api._solar_cache["timestamp"] = time.time()
    solar_api._solar_cache["data"] = {
        "source": "contract-test",
        "updated": "now",
        "indices": {},
        "hf_conditions": {},
        "quality_levels": {},
    }

    assert_response_has_keys("GET", "/api/config", {"success", "config"})
    assert_response_has_keys("GET", "/api/status", {"connected", "cluster_connected"})
    assert_response_has_keys("GET", "/api/sync-status", {"syncing", "total_records"})
    assert_response_has_keys("GET", "/api/rotor/status", {"ok", "enabled"})
    assert_response_has_keys("GET", "/api/rotor/config", {"ok", "enabled", "host"})
    assert_response_has_keys("GET", "/api/rotor/auto/status", {"ok", "auto_enabled", "home_grid"})
    assert_response_has_keys("GET", "/api/ft8/status", {"enabled", "mode"})
    assert_response_has_keys("GET", "/api/ft8/config", {"mode", "mycall", "mygrid"})
    assert_response_has_keys("GET", "/api/ft8/decoded", {"messages"})
    assert_response_has_keys("GET", "/api/ft8/qsos", {"qsos"})
    assert_response_has_keys("GET", "/api/ft8/waterfall", {"waterfall"})
    assert_response_has_keys("GET", "/api/ft8/automation/status", {"settings", "targets", "last_decision"})
    assert_response_has_keys("GET", "/api/ft8/audio-devices", {"input", "output"})
    assert_response_has_keys("GET", "/api/spots", {"spots"})
    assert_response_has_keys("GET", "/api/spots/count", {"count"})
    assert_response_has_keys("GET", "/api/spots/recent?limit=5", {"spots"})
    assert_response_has_keys("GET", "/api/spots/callsign/OM0RX?limit=5", {"callsign", "count", "spots"})
    assert_response_has_keys("GET", "/api/spots/stats/band", {"ok", "data", "date_filter"})
    assert_response_has_keys("GET", "/api/spots/stats/mode", {"ok", "data", "date_filter"})
    assert_response_has_keys("GET", "/api/spots/stats/country?limit=5", {"ok", "data", "limit", "date_filter"})
    assert_response_has_keys("GET", "/api/spots/special?limit=5", {"ok", "data", "count"})
    assert_response_has_keys("GET", "/api/spots/source-stats", {"ok", "live", "all_time", "windows"})
    assert_response_has_keys("GET", "/api/cluster/rbl/status", {"ok", "enabled", "profile", "telemetry"})
    assert_response_has_keys("GET", "/api/cluster/rbl/profiles", {"ok", "default_profile", "profiles"})
    assert_response_has_keys("GET", "/api/activity-intelligence", {"ok", "sourceStatus", "sourceCatalog", "contestContext", "rbn"})
    assert_response_has_keys("GET", "/api/activity-intelligence/reference?q=", {"ok", "results"})
    assert_response_has_keys("GET", "/api/activity-intelligence/rbn", {"ok", "rbn"})
    assert_response_has_keys("GET", "/api/qso/outbox/status", {"success", "outbox"})
    assert_response_has_keys("GET", "/api/solar", {"source", "indices", "hf_conditions"})


def test_safe_frontend_post_contracts(tmp_path):
    install_temp_activity_service(tmp_path)
    assert_response_has_keys(
        "POST",
        "/api/spots/filtered-search",
        {"ok", "spots", "count"},
        json={"limit": 5},
    )
    assert_response_has_keys(
        "POST",
        "/api/cluster/command",
        {"success", "message"},
        json={"command": "sh/dx"},
    )
    assert_response_has_keys(
        "POST",
        "/api/cluster/rbl",
        {"success", "message", "profile", "telemetry"},
        json={"enabled": True, "modes": ["CW"], "profile": "dxspider"},
    )
    assert_response_has_keys(
        "POST",
        "/api/activity-intelligence/contest-context",
        {"ok", "contestContext"},
        json={"contestId": None},
    )
    assert_response_has_keys(
        "POST",
        "/api/cluster/reconnect",
        {"success", "message"},
    )


def test_activity_intelligence_frontend_static_contracts():
    root = Path(__file__).resolve().parents[2]
    template = (root / "frontend" / "templates" / "dx-spots.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "js" / "dx-spots.js").read_text(encoding="utf-8")
    styles = (root / "frontend" / "main-styles.css").read_text(encoding="utf-8")

    assert "activity-contest-banner" in template
    assert "setActivityContestContext" in template
    assert "activity-rbn-heatmap" in template
    assert "activity-source-strip" in template
    assert "getActivityContestBanner()" in script
    assert "getActivityRbnBandRows()" in script
    assert "getActivitySourceRows()" in script
    assert "activity-rbn-bar-row" in styles
    assert "activity-contest-banner" in styles
    assert "activity-source-row" in styles


if __name__ == "__main__":
    test_frontend_routes_are_registered()
    test_legacy_adif_duckdb_routes_are_retired()
    test_safe_frontend_read_contracts()
    test_safe_frontend_post_contracts()
    print("Frontend endpoint contract smoke checks passed")
