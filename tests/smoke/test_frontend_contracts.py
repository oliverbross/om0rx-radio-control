#!/usr/bin/env python3
"""Smoke checks for the frontend/backend API contract."""

import time
from pathlib import Path

import _bootstrap  # noqa: F401
from fastapi.testclient import TestClient

import backend.main
from backend.api import server_control
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
    "/api/wsjtx/health",
    "/api/wsjtx/automation/status",
    "/api/wsjtx/launch-logs",
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
    "/api/config/postgres/test",
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
    "/api/wsjtx/command",
    "/api/wsjtx/automation/settings",
    "/api/wsjtx/automation/tick",
    "/api/wsjtx/decode-status",
    "/api/wsjtx/halt-tx",
    "/api/wsjtx/free-text",
    "/api/wsjtx/configure",
    "/api/wsjtx/reply",
    "/api/wsjtx/start-target",
    "/api/wsjtx/start-target-from-spot",
    "/api/wsjtx/launch-patched-engine",
    "/api/wsjtx/launch-preflight",
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
    "/api/ft8/automation/targets",
    "/api/ft8/automation/next",
    "/api/ft8/automation/attempt",
    "/api/ft8/automation/promote",
    "/api/ft8/automation/skip",
    "/api/ft8/automation/wsjtx/prepare-next",
    "/api/ft8/automation/wsjtx/prepare-target",
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


def test_wsjtx_prepare_request_accepts_frontend_and_api_field_names():
    from backend.api.ft8 import AutomationWsjtxPrepareRequest

    frontend_shape = AutomationWsjtxPrepareRequest.model_validate({
        "cqOnly": False,
        "autoCallStartOnly": False,
    })
    api_shape = AutomationWsjtxPrepareRequest.model_validate({
        "cq_only": False,
        "auto_call_start_only": False,
    })

    assert frontend_shape.cq_only is False
    assert frontend_shape.auto_call_start_only is False
    assert api_shape.cq_only is False
    assert api_shape.auto_call_start_only is False


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
    assert_response_has_keys("GET", "/api/wsjtx/health", {"success", "enabled", "status", "bridge", "processes", "engine", "decode_fresh", "last_decode", "checks", "validation", "timeline"})
    assert_response_has_keys("GET", "/api/wsjtx/automation/status", {"success", "automation", "stats", "status_sources"})
    assert_response_has_keys("GET", "/api/wsjtx/launch-logs?rigName=OM0RX-AUTO&lines=5", {"success", "rig_name", "lines", "logs"})
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
    assert_response_has_keys(
        "POST",
        "/api/wsjtx/automation/settings",
        {"success", "source", "automation", "stats", "status_sources"},
        json={
            "source": "contract-test",
            "automation": {
                "autoCall": False,
                "autoCQ": False,
                "cqOnly": True,
                "minSignal": -24,
                "txDf": 1500,
            },
        },
    )
    assert_response_has_keys(
        "POST",
        "/api/wsjtx/automation/tick",
        {"success", "action", "reason", "automation", "stats", "status_sources"},
        json={
            "source": "contract-test",
            "automation": {
                "autoCall": False,
                "autoCQ": False,
                "cqOnly": True,
            },
        },
    )
    assert_response_has_keys(
        "POST",
        "/api/wsjtx/decode-status",
        {
            "success",
            "call",
            "band",
            "mode",
            "call_status",
            "dxcc_status",
            "automation_target",
            "automation_decision",
            "status_sources",
        },
        json={
            "call": "OK1ABC",
            "band": "20m",
            "mode": "FT8",
            "frequency_hz": 14074000,
        },
    )


def test_postgres_connection_test_contract(monkeypatch):
    monkeypatch.setattr(
        server_control,
        "test_connection",
        lambda dsn=None, timeout_seconds=5: {
            "database": "radio",
            "user": "om0rx",
            "server_addr": "127.0.0.1",
            "server_port": 5432,
            "server_version": "16-test",
            "elapsed_ms": 1.2,
        },
    )

    payload = assert_response_has_keys(
        "POST",
        "/api/config/postgres/test",
        {"success", "message", "details"},
        json={
            "config": {
                "POSTGRES_HOST": "127.0.0.1",
                "POSTGRES_PORT": 5432,
                "POSTGRES_DB": "radio",
                "POSTGRES_USER": "om0rx",
                "POSTGRES_PASSWORD": "secret",
            }
        },
    )
    assert payload["success"] is True
    assert payload["details"]["database"] == "radio"
    assert "secret" not in payload["message"]


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


def test_database_config_modal_exposes_postgres_controls():
    root = Path(__file__).resolve().parents[2]
    template = (root / "frontend" / "templates" / "modal-config.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "js" / "config-modal.js").read_text(encoding="utf-8")

    assert "Local App Data Store" in template
    assert "Storage Backend" in template
    assert "PostgreSQL DSN" in template
    assert "Test PostgreSQL Connection" in template
    assert "WSJTX_BRIDGE_COMMAND_URL" in template
    assert "WSJTX_BRIDGE_COMMAND_URL" in script
    assert "/api/config/postgres/test" in script
    assert "testPostgresConnection" in script


def test_wsjtx_target_action_frontend_static_contracts():
    root = Path(__file__).resolve().parents[2]
    template = (root / "frontend" / "templates" / "dx-spots.html").read_text(encoding="utf-8")
    section = (root / "frontend" / "dx-spots-section.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "js" / "dx-spots.js").read_text(encoding="utf-8")
    app_main = (root / "frontend" / "js" / "app-main.js").read_text(encoding="utf-8")
    config_modal = (root / "frontend" / "js" / "config-modal.js").read_text(encoding="utf-8")
    config_template = (root / "frontend" / "templates" / "modal-config.html").read_text(encoding="utf-8")
    config_section = (root / "frontend" / "modals-section.html").read_text(encoding="utf-8")
    controls_template = (root / "frontend" / "templates" / "controls-row1.html").read_text(encoding="utf-8")
    controls_section = (root / "frontend" / "controls-section.html").read_text(encoding="utf-8")
    compact_controls = (root / "frontend" / "templates" / "partials" / "compact-radio-controls.html").read_text(encoding="utf-8")
    index = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    visual_map = (root / "frontend" / "visual-map.html").read_text(encoding="utf-8")
    ft8_template = (root / "frontend" / "templates" / "modal-ft8.html").read_text(encoding="utf-8")
    ft8_modal = (root / "frontend" / "js" / "ft8-modal.js").read_text(encoding="utf-8")
    ft8_styles = (root / "frontend" / "ft8-modal.css").read_text(encoding="utf-8")

    assert "Prepare WSJT" in template
    assert "Arm WSJT" in template
    assert "Queue WSJT" in template
    assert "queueVisibleWsjtxCandidates(25)" in template
    assert "wsjtxCandidateQueue.message" in template
    assert "wsjtx-engine-strip" in template
    assert "getWsjtxEngineStatusText()" in template
    assert "getWsjtxEngineLogStatusText()" in template
    assert "getWsjtxEngineDecodeText()" in template
    assert "getWsjtxPlannerAutomationText()" in template
    assert "Check WSJT" in template
    assert "WSJT Planner" in template
    assert "toggleWsjtxPlannerPanel" in template
    assert "Prepare best" in template
    assert 'value="actionable"' in template
    assert 'value="heard"' in template
    assert 'value="backoff"' in template
    assert "prepareWsjtxPlannerTarget(target)" in template
    assert "promoteWsjtxPlannerTarget(target)" in template
    assert "skipWsjtxPlannerTarget(target)" in template
    assert "wsjtxSpotPrepare.message" in template
    assert "wsjtxSpotPrepare.traceId" in template
    assert "openWsjtxTraceInConfig(wsjtxSpotPrepare.traceId)" in template
    assert "copyWsjtxTraceToClipboard(wsjtxSpotPrepare.traceId)" in template
    assert "wsjtx-spot-trace-btn" in template
    assert "wsjtx-spot-trace-copy-btn" in template
    assert "getWsjtxSpotPrepareClass" in template
    assert "Prepare WSJT" in section
    assert "Arm WSJT" in section
    assert "Queue WSJT" in section
    assert "queueVisibleWsjtxCandidates(25)" in section
    assert "wsjtxCandidateQueue.message" in section
    assert "wsjtx-engine-strip" in section
    assert "getWsjtxEngineStatusText()" in section
    assert "getWsjtxEngineLogStatusText()" in section
    assert "getWsjtxEngineDecodeText()" in section
    assert "getWsjtxPlannerAutomationText()" in section
    assert "Check WSJT" in section
    assert "WSJT Planner" in section
    assert "toggleWsjtxPlannerPanel" in section
    assert "Prepare best" in section
    assert 'value="actionable"' in section
    assert 'value="heard"' in section
    assert 'value="backoff"' in section
    assert "prepareWsjtxPlannerTarget(target)" in section
    assert "promoteWsjtxPlannerTarget(target)" in section
    assert "skipWsjtxPlannerTarget(target)" in section
    assert "wsjtxSpotPrepare.message" in section
    assert "wsjtxSpotPrepare.traceId" in section
    assert "openWsjtxTraceInConfig(wsjtxSpotPrepare.traceId)" in section
    assert "copyWsjtxTraceToClipboard(wsjtxSpotPrepare.traceId)" in section
    assert "wsjtx-spot-trace-btn" in section
    assert "wsjtx-spot-trace-copy-btn" in section
    assert "getWsjtxSpotPrepareClass" in section
    assert "startWsjtxTargetFromSpot" in script
    assert "normalizeSpotFrequencyMhz" in script
    assert "setWsjtxSpotPrepareState" in script
    assert "buildWsjtxSpotTargetPayload" in script
    assert "getVisibleWsjtxCandidates" in script
    assert "queueVisibleWsjtxCandidates" in script
    assert "refreshWsjtxPlannerStatus" in script
    assert "refreshWsjtxEngineHealth" in script
    assert "setupWsjtxEngineHealthRefresh" in script
    assert "cleanupWsjtxEngineHealthRefresh" in script
    assert "getWsjtxEngineStatusText" in script
    assert "getWsjtxEngineLogStatusText" in script
    assert "getWsjtxEngineDecodeText" in script
    assert "getWsjtxPlannerAutomationText" in script
    assert "getWsjtxPlannerFilterText" in script
    assert "isWsjtxPlannerActionableTarget" in script
    assert "prepareBestWsjtxPlannerTarget" in script
    assert "prepareWsjtxPlannerTarget" in script
    assert "promoteWsjtxPlannerTarget" in script
    assert "skipWsjtxPlannerTarget" in script
    assert "extractWsjtxTraceId" in script
    assert "traceId: this.extractWsjtxTraceId(result)" in script
    assert "openWsjtxTraceInConfig" in script
    assert "this.wsjtxTimelineFilter = cleanTraceId" in script
    assert "this.showConfigDialog('wsjtx')" in script
    assert "getWsjtxSpotPrepareLabel" in script
    assert "/api/ft8/automation/wsjtx/prepare-target" in script
    assert "/api/ft8/automation/targets" in script
    assert "/api/ft8/automation/promote" in script
    assert "/api/ft8/automation/skip" in script
    assert "/api/wsjtx/arm-target-from-spot" in script
    assert "confirmArm" in script
    assert "wsjtx-config" in app_main
    assert "refreshWsjtxEngineHealth({ force: true })" in app_main
    assert "setupWsjtxEngineHealthRefresh" in app_main
    assert "showConfigDialog(initialTab = 'database')" in config_modal
    assert "WSJT Engine Health" in config_template
    assert "WSJT Engine Health" in config_section
    assert "wsjtx-health-checks" in config_template
    assert "wsjtx-health-checks" in config_section
    assert "wsjtx-timeline-panel" in config_template
    assert "wsjtx-timeline-panel" in config_section
    assert "wsjtx-timeline-toolbar" in config_template
    assert "wsjtx-timeline-toolbar" in config_section
    assert "wsjtx-command-error-panel" in config_template
    assert "wsjtx-command-error-panel" in config_section
    assert "wsjtxTimelineFilter" in config_template
    assert "wsjtxTimelineFilter" in config_section
    assert "Bridge timeline" in config_template
    assert "Bridge timeline" in config_section
    assert "Last decode" in config_template
    assert "Last decode" in config_section
    assert "Refresh WSJT" in config_template
    assert "Halt TX" in config_template
    assert "Test Prepare" in config_template
    assert "Self Test" in config_template
    assert "wsjtx-preflight-panel" in config_template
    assert "wsjtx-preflight-panel" in config_section
    assert "wsjtx-launch-result-panel" in config_template
    assert "wsjtx-launch-result-panel" in config_section
    assert "wsjtx-launch-log-viewer" in config_template
    assert "wsjtx-launch-log-viewer" in config_section
    assert "View logs" in config_template
    assert "View logs" in config_section
    assert "Preflight + Start" in config_template
    assert "Preflight + Start" in config_section
    assert "/api/wsjtx/health" in config_modal
    assert "/api/wsjtx/halt-tx" in config_modal
    assert "/api/wsjtx/launch-patched-engine" in config_modal
    assert "/api/wsjtx/launch-preflight" in config_modal
    assert "/api/wsjtx/launch-logs" in config_modal
    assert "launchPatchedWsjtxEngine" in config_modal
    assert "runWsjtxLaunchPreflight" in config_modal
    assert "loadWsjtxLaunchLogs" in config_modal
    assert "getWsjtxLaunchLogSections" in config_modal
    assert "wsjtxLaunchLogs" in config_modal
    assert "getWsjtxLaunchPayload" in config_modal
    assert "requireReady" in config_modal
    assert "testWsjtxLaunchPreflight" in config_modal
    assert "formatWsjtxPreflightSummary" in config_modal
    assert "wsjtxLaunchResult" in config_modal
    assert "getWsjtxLaunchResultClass" in config_modal
    assert "formatWsjtxLaunchSummary" in config_modal
    assert "formatWsjtxLaunchPids" in config_modal
    assert "formatWsjtxLaunchCommand" in config_modal
    assert "getWsjtxLaunchLogRows" in config_modal
    assert "getWsjtxReadinessChecks" in config_modal
    assert "formatWsjtxValidationSummary" in config_modal
    assert "getWsjtxCheckClass" in config_modal
    assert "formatWsjtxLastDecode" in config_modal
    assert "getWsjtxBridgeTimeline" in config_modal
    assert "hasWsjtxBridgeTimeline" in config_modal
    assert "clearWsjtxTimelineFilter" in config_modal
    assert "getWsjtxTimelineTraceId" in config_modal
    assert "copyWsjtxTraceToClipboard" in config_modal
    assert "getWsjtxCommandErrorSummary" in config_modal
    assert "focusWsjtxCommandErrorTrace" in config_modal
    assert "getWsjtxTimelineSearchText" in config_modal
    assert "formatWsjtxTimelineTitle" in config_modal
    assert "formatWsjtxTimelineDetail" in config_modal
    assert "getWsjtxTimelineClass" in config_modal
    assert "traceId" in config_modal
    assert "testWsjtxPrepareCommand" in config_modal
    assert "sendWsjtxAutoCqTest" in config_modal
    assert "sendWsjtxAutoAnswerTest" in config_modal
    assert "launchPatchedWsjtxEngine" in controls_template
    assert "WSJT-X" in controls_template
    assert "launchPatchedWsjtxEngine" in controls_section
    assert "WSJT-X" in controls_section
    assert "launchPatchedWsjtxEngine" in compact_controls
    assert "wsjtx-launch-button" in compact_controls
    assert "ft8WsjtxPersistenceLabel()" in ft8_template
    assert "ft8WsjtxPersistenceTitle()" in ft8_template
    assert "ft8-planner-db-badge" in ft8_template
    assert "ft8WsjtxPersistenceLabel" in ft8_modal
    assert "ft8WsjtxPersistenceClass" in ft8_modal
    assert "DB PostgreSQL" in ft8_modal
    assert ".ft8-planner-db-badge.postgres" in ft8_styles
    assert ".ft8-planner-db-badge.memory" in ft8_styles
    assert ".ft8-planner-db-badge.error" in ft8_styles
    assert "selectConfigTab" in config_modal
    assert "WSJT automation controls" in config_template
    assert "WSJT automation controls" in config_section
    assert "wsjtx-health-message" in config_template
    assert "wsjtx-health-message" in config_section
    assert "Queue Auto CQ" in config_template
    assert "Queue Auto CQ" in config_section
    assert "Process Auto Answer" in config_template
    assert "Process Auto Answer" in config_section
    assert "getWsjtxTimelineTraceId(event)" in config_template
    assert "getWsjtxTimelineTraceId(event)" in config_section
    assert "/api/wsjtx/free-text" in config_modal
    assert "/api/wsjtx/reply" in config_modal
    assert "20260604-wsjtx-launch-outbox-2" in index
    assert "20260604-wsjtx-launch-outbox-2" in visual_map
    assert "20260604-wsjtx-launch-outbox-2" in (root / "frontend" / "templates-loader.js").read_text(encoding="utf-8")


if __name__ == "__main__":
    test_frontend_routes_are_registered()
    test_legacy_adif_duckdb_routes_are_retired()
    test_safe_frontend_read_contracts()
    test_safe_frontend_post_contracts()
    print("Frontend endpoint contract smoke checks passed")
