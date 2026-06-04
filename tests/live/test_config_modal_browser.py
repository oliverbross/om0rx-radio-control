#!/usr/bin/env python3
"""Live browser smoke test for the configuration Database tab.

This diagnostic is intentionally outside the default smoke suite because it needs
a running local app, Playwright, and Chromium.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

import _bootstrap  # noqa: F401


BASE_URL = os.environ.get("OM0RX_LIVE_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
TIMEOUT_MS = int(os.environ.get("OM0RX_CONFIG_BROWSER_TIMEOUT_MS", "30000"))
HTTP_PROBE_TIMEOUT = int(os.environ.get("OM0RX_CONFIG_HTTP_PROBE_TIMEOUT", "10"))


def require_live_app() -> None:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/config", timeout=HTTP_PROBE_TIMEOUT) as response:
            if response.status >= 400:
                pytest.skip(f"Live app at {BASE_URL} returned HTTP {response.status}")
    except (OSError, urllib.error.URLError) as exc:
        pytest.skip(f"Live app is not reachable at {BASE_URL}: {exc}")


def mock_wsjtx_health_payload(trace_id: str = "spot-trace-123") -> dict:
    return {
        "success": True,
        "enabled": True,
        "status": "ok",
        "value": "ready",
        "detail": "mock WSJT health ready",
        "bridge": {
            "command_url": "http://127.0.0.1:8092/wsjtx/command",
            "stats": {"decodes": 12, "commandErrors": 0},
            "capabilities": {"start_target_qso": True},
            "timeline": [
                {
                    "ts": 1780557900000,
                    "age": "5s ago",
                    "direction": "out",
                    "type": "command",
                    "command": "start_target_qso",
                    "trace_id": trace_id,
                    "success": True,
                    "bytes": 188,
                    "payload": {
                        "call": "EA1TEST",
                        "grid": "IN80",
                        "mode": "FT8",
                        "traceId": trace_id,
                        "rxDf": 1500,
                        "txDf": 1500,
                    },
                },
                {
                    "ts": 1780557901000,
                    "age": "4s ago",
                    "direction": "in",
                    "type": "decode",
                    "message": "CQ EA1TEST IN80",
                    "mode": "FT8",
                    "dx_call": "EA1TEST",
                },
            ],
        },
        "timeline": [
            {
                "ts": 1780557900000,
                "age": "5s ago",
                "direction": "out",
                "type": "command",
                "command": "start_target_qso",
                "trace_id": trace_id,
                "success": True,
                "bytes": 188,
                "payload": {
                    "call": "EA1TEST",
                    "grid": "IN80",
                    "mode": "FT8",
                    "traceId": trace_id,
                    "rxDf": 1500,
                    "txDf": 1500,
                },
            },
            {
                "ts": 1780557901000,
                "age": "4s ago",
                "direction": "in",
                "type": "decode",
                "message": "CQ EA1TEST IN80",
                "mode": "FT8",
                "dx_call": "EA1TEST",
            },
        ],
        "processes": {"wsjtx": False, "decoder": True},
        "engine": {"mode": "patched"},
        "decode_fresh": True,
        "last_decode": {
            "message": "CQ EA1TEST IN80",
            "deltaFrequency": 1500,
        },
        "last_decode_age_ms": 1200,
        "client": {"id": "OM0RX-AUTO"},
        "last_seen_ms": 900,
        "validation": {
            "ready": True,
            "critical_ok": 3,
            "critical_total": 3,
            "failures": 0,
        },
        "checks": [
            {
                "id": "bridge",
                "label": "Bridge command API",
                "status": "ok",
                "detail": "mock bridge ready",
                "value": "127.0.0.1:8092",
            },
            {
                "id": "decode",
                "label": "Recent decode",
                "status": "ok",
                "detail": "mock decode is fresh",
                "value": "1s ago",
            },
        ],
    }


def mock_wsjtx_command_error_health_payload(trace_id: str = "spot-error-trace-789") -> dict:
    payload = mock_wsjtx_health_payload(trace_id)
    failed_event = {
        "ts": 1780557902000,
        "age": "2s ago",
        "direction": "out",
        "type": "command",
        "command": "start_target_qso",
        "trace_id": trace_id,
        "success": False,
        "error": "No WSJT-X client has been seen yet",
        "payload": {
            "call": "K1FAIL",
            "grid": "FN42",
            "mode": "FT8",
            "traceId": trace_id,
            "rxDf": 1240,
            "txDf": 1500,
        },
    }
    payload["bridge"]["stats"]["commandErrors"] = 1
    payload["bridge"]["timeline"] = [
        failed_event,
        {
            "ts": 1780557903000,
            "age": "1s ago",
            "direction": "in",
            "type": "decode",
            "message": "CQ EA1TEST IN80",
            "mode": "FT8",
            "dx_call": "EA1TEST",
        },
    ]
    payload["timeline"] = list(payload["bridge"]["timeline"])
    return payload


def test_config_database_tab_exposes_postgres_controls() -> None:
    require_live_app()
    playwright_api = pytest.importorskip(
        "playwright.sync_api",
        reason='Install browser diagnostics with: python -m pip install ".[browser]"',
    )
    sync_playwright = playwright_api.sync_playwright

    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                pytest.skip(
                    "Playwright Chromium is not installed. "
                    "Run: python -m playwright install chromium"
                )
            raise

        with browser:
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            page.goto(f"{BASE_URL}/?v=config-modal-browser-smoke", timeout=TIMEOUT_MS, wait_until="commit")
            page.locator("button", has_text="Config").first.click(timeout=TIMEOUT_MS)
            page.locator(".modal-content").wait_for(timeout=TIMEOUT_MS)

            database_tab = page.locator(".modal-tab", has_text="Database")
            assert database_tab.count() == 1
            database_tab.click(timeout=TIMEOUT_MS)

            for text in (
                "Local App Data Store",
                "Storage Backend",
                "PostgreSQL DSN",
                "Test PostgreSQL Connection",
                "Wavelog Source Database",
            ):
                assert page.locator(".modal-content", has_text=text).count() >= 1

            assert page.locator(".modal-content select").count() >= 1
            assert page.locator("input[placeholder*='dbname=om0rx_radio_control']").count() == 1
            assert not page_errors, "Browser page errors:\n" + "\n".join(page_errors)
            actionable_console_errors = [
                message
                for message in console_errors
                if "Error fetching service health: AbortError" not in message
            ]
            assert not actionable_console_errors, (
                "Browser console errors:\n" + "\n".join(actionable_console_errors)
            )


def test_wsjtx_spot_trace_button_opens_filtered_timeline() -> None:
    require_live_app()
    playwright_api = pytest.importorskip(
        "playwright.sync_api",
        reason='Install browser diagnostics with: python -m pip install ".[browser]"',
    )
    sync_playwright = playwright_api.sync_playwright

    trace_id = "spot-trace-click-456"
    console_errors: list[str] = []
    page_errors: list[str] = []

    def fulfill_json(route, payload: dict) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                pytest.skip(
                    "Playwright Chromium is not installed. "
                    "Run: python -m playwright install chromium"
                )
            raise

        with browser:
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.route(
                "**/api/wsjtx/health",
                lambda route: fulfill_json(route, mock_wsjtx_health_payload(trace_id)),
            )

            page.goto(f"{BASE_URL}/?v=wsjtx-trace-click-smoke", timeout=TIMEOUT_MS, wait_until="commit")
            page.wait_for_function("window.vueInstance && window.vueInstance.$nextTick", timeout=TIMEOUT_MS)
            page.evaluate(
                """async traceId => {
                    const vm = window.vueInstance;
                    vm.viewMode = 'spots';
                    vm.selectedSpot = {
                        callsign: 'EA1TEST',
                        band: '20m',
                        frequency_mhz: 14.074,
                        mode: 'FT8',
                        country: 'Spain',
                        cq: 14,
                        comment: 'mock trace smoke',
                        score: 100,
                    };
                    vm.selectedSpotExplain = {
                        call: { status: 'New Band' },
                        dxcc: { status: 'Confirmed', adif: 281 },
                        cty: { country: 'Spain' },
                        inputs: { band: '20m', mode: 'FT8' },
                    };
                    vm.selectedSpotActivityDetail = null;
                    vm.selectedSpotActivityLoading = false;
                    vm.spotExplainLoading = false;
                    vm.spotExplainError = '';
                    vm.wsjtxSpotPrepare = {
                        state: 'prepared',
                        message: 'EA1TEST prepared',
                        call: 'EA1TEST',
                        detail: 'WSJT target ready; TX remains disabled until explicitly armed',
                        traceId,
                        updatedAt: new Date().toISOString(),
                    };
                    await vm.$nextTick();
                }""",
                trace_id,
            )

            trace_button = page.locator(".wsjtx-spot-trace-btn", has_text=f"Trace {trace_id}")
            trace_button.wait_for(timeout=TIMEOUT_MS)
            trace_button.click(timeout=TIMEOUT_MS)

            page.locator(".modal-content").wait_for(timeout=TIMEOUT_MS)
            page.locator(".wsjtx-timeline-toolbar input[type='search']").wait_for(timeout=TIMEOUT_MS)
            filter_value = page.locator(".wsjtx-timeline-toolbar input[type='search']").input_value(
                timeout=TIMEOUT_MS
            )
            timeline_text = page.locator(".wsjtx-timeline-panel").inner_text(timeout=TIMEOUT_MS)
            normalized_timeline_text = timeline_text.lower()

            assert filter_value == trace_id
            assert "bridge timeline" in normalized_timeline_text
            assert f"trace {trace_id}" in normalized_timeline_text
            assert "start_target_qso ea1test ft8" in normalized_timeline_text
            assert "cq ea1test in80" not in normalized_timeline_text
            assert not page_errors, "Browser page errors:\n" + "\n".join(page_errors)
            actionable_console_errors = [
                message
                for message in console_errors
                if "Error fetching service health: AbortError" not in message
            ]
            assert not actionable_console_errors, (
                "Browser console errors:\n" + "\n".join(actionable_console_errors)
            )


def test_wsjtx_command_error_panel_filters_failed_trace() -> None:
    require_live_app()
    playwright_api = pytest.importorskip(
        "playwright.sync_api",
        reason='Install browser diagnostics with: python -m pip install ".[browser]"',
    )
    sync_playwright = playwright_api.sync_playwright

    trace_id = "spot-error-trace-789"
    console_errors: list[str] = []
    page_errors: list[str] = []

    def fulfill_json(route, payload: dict) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                pytest.skip(
                    "Playwright Chromium is not installed. "
                    "Run: python -m playwright install chromium"
                )
            raise

        with browser:
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.route(
                "**/api/wsjtx/health",
                lambda route: fulfill_json(route, mock_wsjtx_command_error_health_payload(trace_id)),
            )

            page.goto(f"{BASE_URL}/?v=wsjtx-command-error-smoke", timeout=TIMEOUT_MS, wait_until="commit")
            page.locator("button", has_text="Config").first.click(timeout=TIMEOUT_MS)
            page.locator(".modal-content").wait_for(timeout=TIMEOUT_MS)
            page.locator(".modal-tab", has_text="WSJT-X").click(timeout=TIMEOUT_MS)

            error_panel = page.locator(".wsjtx-command-error-panel")
            error_panel.wait_for(timeout=TIMEOUT_MS)
            error_text = error_panel.inner_text(timeout=TIMEOUT_MS).lower()
            assert "1 bridge command error" in error_text
            assert "start_target_qso k1fail ft8" in error_text
            assert "no wsjt-x client has been seen yet" in error_text

            error_panel.locator("button", has_text="Filter trace").click(timeout=TIMEOUT_MS)
            filter_value = page.locator(".wsjtx-timeline-toolbar input[type='search']").input_value(
                timeout=TIMEOUT_MS
            )
            timeline_text = page.locator(".wsjtx-timeline-panel").inner_text(timeout=TIMEOUT_MS).lower()

            assert filter_value == trace_id
            assert f"trace {trace_id}" in timeline_text
            assert "start_target_qso k1fail ft8" in timeline_text
            assert "no wsjt-x client has been seen yet" in timeline_text
            assert "cq ea1test in80" not in timeline_text
            assert not page_errors, "Browser page errors:\n" + "\n".join(page_errors)
            actionable_console_errors = [
                message
                for message in console_errors
                if "Error fetching service health: AbortError" not in message
            ]
            assert not actionable_console_errors, (
                "Browser console errors:\n" + "\n".join(actionable_console_errors)
            )


def test_wsjtx_auto_cq_and_answer_controls_send_bridge_commands() -> None:
    require_live_app()
    playwright_api = pytest.importorskip(
        "playwright.sync_api",
        reason='Install browser diagnostics with: python -m pip install ".[browser]"',
    )
    sync_playwright = playwright_api.sync_playwright

    console_errors: list[str] = []
    page_errors: list[str] = []
    captured: dict[str, dict] = {}

    def fulfill_json(route, payload: dict) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    def capture_json(route, key: str, response_payload: dict) -> None:
        captured[key] = route.request.post_data_json
        fulfill_json(route, response_payload)

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                pytest.skip(
                    "Playwright Chromium is not installed. "
                    "Run: python -m playwright install chromium"
                )
            raise

        with browser:
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.route(
                "**/api/wsjtx/health",
                lambda route: fulfill_json(route, mock_wsjtx_health_payload("auto-controls-trace")),
            )
            page.route(
                "**/api/wsjtx/free-text",
                lambda route: capture_json(
                    route,
                    "free_text",
                    {"success": True, "traceId": "auto-cq-trace"},
                ),
            )
            page.route(
                "**/api/wsjtx/reply",
                lambda route: capture_json(
                    route,
                    "reply",
                    {"success": True, "traceId": "auto-answer-trace"},
                ),
            )

            page.goto(f"{BASE_URL}/?v=wsjtx-auto-controls-smoke", timeout=TIMEOUT_MS, wait_until="commit")
            page.locator("button", has_text="Config").first.click(timeout=TIMEOUT_MS)
            page.locator(".modal-content").wait_for(timeout=TIMEOUT_MS)
            page.locator(".modal-tab", has_text="WSJT-X").click(timeout=TIMEOUT_MS)
            page.locator(".wsjtx-automation-panel").wait_for(timeout=TIMEOUT_MS)

            page.locator("input[placeholder='CQ OM0RX JN88']").fill("CQ OM0RX JN88", timeout=TIMEOUT_MS)
            page.locator("button", has_text="Queue Auto CQ").click(timeout=TIMEOUT_MS)
            page.locator(".wsjtx-health-message", has_text="loaded into WSJT").wait_for(timeout=TIMEOUT_MS)

            page.locator("input[placeholder='CQ EA1TEST IN80']").fill("CQ K1ABC FN42", timeout=TIMEOUT_MS)
            page.locator("input[placeholder='EA1TEST']").fill("K1ABC", timeout=TIMEOUT_MS)
            page.locator("input[placeholder='IN80']").fill("FN42", timeout=TIMEOUT_MS)
            page.locator("input[type='number'][min='200']").fill("1742", timeout=TIMEOUT_MS)
            page.locator("button", has_text="Process Auto Answer").click(timeout=TIMEOUT_MS)
            page.locator(".wsjtx-health-message", has_text="processed for K1ABC").wait_for(timeout=TIMEOUT_MS)

            assert captured["free_text"] == {"text": "CQ OM0RX JN88", "send": False}
            assert captured["reply"]["message"] == "CQ K1ABC FN42"
            assert captured["reply"]["call"] == "K1ABC"
            assert captured["reply"]["grid"] == "FN42"
            assert captured["reply"]["deltaFrequency"] == 1742
            assert captured["reply"]["mode"] == "FT8"
            assert "send" not in captured["reply"]
            assert not page_errors, "Browser page errors:\n" + "\n".join(page_errors)
            actionable_console_errors = [
                message
                for message in console_errors
                if "Error fetching service health: AbortError" not in message
            ]
            assert not actionable_console_errors, (
                "Browser console errors:\n" + "\n".join(actionable_console_errors)
            )


def test_config_wsjtx_preflight_start_shows_launch_result_without_real_engine() -> None:
    require_live_app()
    playwright_api = pytest.importorskip(
        "playwright.sync_api",
        reason='Install browser diagnostics with: python -m pip install ".[browser]"',
    )
    sync_playwright = playwright_api.sync_playwright

    console_errors: list[str] = []
    page_errors: list[str] = []
    calls = {"preflight": 0, "launch": 0, "logs": 0}

    def fulfill_json(route, payload: dict) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                pytest.skip(
                    "Playwright Chromium is not installed. "
                    "Run: python -m playwright install chromium"
                )
            raise

        with browser:
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            page.route(
                "**/api/wsjtx/health",
                lambda route: fulfill_json(
                    route,
                    {
                        "success": True,
                        "enabled": True,
                        "status": "ok",
                        "value": "ready",
                        "detail": "mock WSJT health ready",
                        "bridge": {
                            "command_url": "http://127.0.0.1:8092/wsjtx/command",
                            "stats": {"decodes": 12},
                            "capabilities": {"start_target_qso": True},
                            "timeline": [
                                {
                                    "ts": 1780557900000,
                                    "age": "5s ago",
                                    "direction": "out",
                                    "type": "command",
                                    "command": "start_target_qso",
                                    "trace_id": "spot-trace-123",
                                    "success": True,
                                    "bytes": 188,
                                    "payload": {
                                        "call": "EA1TEST",
                                        "grid": "IN80",
                                        "mode": "FT8",
                                        "traceId": "spot-trace-123",
                                        "rxDf": 1500,
                                        "txDf": 1500,
                                    },
                                },
                                {
                                    "ts": 1780557901000,
                                    "age": "4s ago",
                                    "direction": "in",
                                    "type": "decode",
                                    "message": "CQ EA1TEST IN80",
                                    "mode": "FT8",
                                    "dx_call": "EA1TEST",
                                },
                            ],
                        },
                        "timeline": [
                            {
                                "ts": 1780557900000,
                                "age": "5s ago",
                                "direction": "out",
                            "type": "command",
                            "command": "start_target_qso",
                            "trace_id": "spot-trace-123",
                            "success": True,
                                "bytes": 188,
                                "payload": {
                                    "call": "EA1TEST",
                                    "grid": "IN80",
                                "mode": "FT8",
                                "traceId": "spot-trace-123",
                                "rxDf": 1500,
                                    "txDf": 1500,
                                },
                            },
                            {
                                "ts": 1780557901000,
                                "age": "4s ago",
                                "direction": "in",
                                "type": "decode",
                                "message": "CQ EA1TEST IN80",
                                "mode": "FT8",
                                "dx_call": "EA1TEST",
                            },
                        ],
                        "processes": {"wsjtx": False, "decoder": True},
                        "engine": {"mode": "patched"},
                        "decode_fresh": True,
                        "last_decode": {
                            "message": "CQ EA1TEST IN80",
                            "deltaFrequency": 1500,
                        },
                        "last_decode_age_ms": 1200,
                        "client": {"id": "OM0RX-AUTO"},
                        "last_seen_ms": 900,
                        "validation": {
                            "ready": True,
                            "critical_ok": 3,
                            "critical_total": 3,
                            "failures": 0,
                        },
                        "checks": [
                            {
                                "id": "bridge",
                                "label": "Bridge command API",
                                "status": "ok",
                                "detail": "mock bridge ready",
                                "value": "127.0.0.1:8092",
                            },
                            {
                                "id": "decode",
                                "label": "Recent decode",
                                "status": "ok",
                                "detail": "mock decode is fresh",
                                "value": "1s ago",
                            },
                        ],
                    },
                ),
            )

            def preflight(route) -> None:
                calls["preflight"] += 1
                fulfill_json(
                    route,
                    {
                        "success": True,
                        "ready": True,
                        "rig_name": "OM0RX-AUTO",
                        "config_name": "OM0RX-AUTO",
                        "validation": {
                            "ready": True,
                            "critical_ok": 4,
                            "critical_total": 4,
                            "failures": 0,
                        },
                        "checks": [
                            {
                                "id": "profile",
                                "label": "WSJT profile",
                                "status": "ok",
                                "detail": "OM0RX-AUTO profile exists",
                                "value": "OM0RX-AUTO",
                            },
                            {
                                "id": "port",
                                "label": "Bridge port",
                                "status": "ok",
                                "detail": "command bridge is reachable",
                                "value": "8092",
                            },
                        ],
                    },
                )

            def launch(route) -> None:
                calls["launch"] += 1
                fulfill_json(
                    route,
                    {
                        "success": True,
                        "message": "mock launch complete",
                        "rig_name": "OM0RX-AUTO",
                        "config_name": "OM0RX-AUTO",
                        "pid": 43210,
                        "existing_pids": [],
                        "command": [
                            "C:\\fake\\wsjtx.exe",
                            "--rig-name",
                            "OM0RX-AUTO",
                            "--config",
                            "OM0RX-AUTO",
                        ],
                        "stdout_log": (
                            "C:\\Projects\\om0rx-radio-control\\logs\\"
                            "wsjt-x-om0rx-auto.out.log"
                        ),
                        "stderr_log": (
                            "C:\\Projects\\om0rx-radio-control\\logs\\"
                            "wsjt-x-om0rx-auto.err.log"
                        ),
                    },
                )

            def logs(route) -> None:
                calls["logs"] += 1
                fulfill_json(
                    route,
                    {
                        "success": True,
                        "rig_name": "OM0RX-AUTO",
                        "lines": 120,
                        "logs": {
                            "stdout": {
                                "path": (
                                    "C:\\Projects\\om0rx-radio-control\\logs\\"
                                    "wsjt-x-om0rx-auto.out.log"
                                ),
                                "exists": True,
                                "size": 44,
                                "modified": "2026-06-04T12:00:00+00:00",
                                "lines": ["mock stdout line 1", "mock stdout line 2"],
                                "text": "mock stdout line 1\nmock stdout line 2",
                                "truncated": False,
                            },
                            "stderr": {
                                "path": (
                                    "C:\\Projects\\om0rx-radio-control\\logs\\"
                                    "wsjt-x-om0rx-auto.err.log"
                                ),
                                "exists": True,
                                "size": 22,
                                "modified": "2026-06-04T12:00:00+00:00",
                                "lines": ["mock stderr line"],
                                "text": "mock stderr line",
                                "truncated": False,
                            },
                        },
                    },
                )

            page.route("**/api/wsjtx/launch-preflight", preflight)
            page.route("**/api/wsjtx/launch-patched-engine", launch)
            page.route("**/api/wsjtx/launch-logs**", logs)

            page.goto(f"{BASE_URL}/?v=config-wsjtx-launch-result-smoke", timeout=TIMEOUT_MS, wait_until="commit")
            page.locator("button", has_text="Config").first.click(timeout=TIMEOUT_MS)
            page.locator(".modal-content").wait_for(timeout=TIMEOUT_MS)
            page.locator(".modal-tab", has_text="WSJT-X").click(timeout=TIMEOUT_MS)
            page.locator(".wsjtx-timeline-panel").wait_for(timeout=TIMEOUT_MS)
            timeline_text = page.locator(".wsjtx-timeline-panel").inner_text(timeout=TIMEOUT_MS)
            page.locator("button", has_text="Preflight + Start").click(timeout=TIMEOUT_MS)

            panel = page.locator(".wsjtx-launch-result-panel")
            panel.wait_for(timeout=TIMEOUT_MS)
            panel_text = panel.inner_text(timeout=TIMEOUT_MS)
            normalized_panel_text = panel_text.lower()
            page.locator(".wsjtx-launch-log-viewer").wait_for(timeout=TIMEOUT_MS)
            log_text = page.locator(".wsjtx-launch-log-viewer").inner_text(timeout=TIMEOUT_MS)

            assert calls == {"preflight": 1, "launch": 1, "logs": 1}
            assert "bridge timeline" in timeline_text.lower()
            assert "start_target_qso EA1TEST FT8" in timeline_text
            assert "trace spot-trace-123" in timeline_text
            assert "CQ EA1TEST IN80" in timeline_text
            assert "engine launched: pid 43210" in normalized_panel_text
            assert "C:\\fake\\wsjtx.exe" in panel_text
            assert "wsjt-x-om0rx-auto.out.log" in panel_text
            assert "wsjt-x-om0rx-auto.err.log" in panel_text
            assert "mock stdout line 2" in log_text
            assert "mock stderr line" in log_text
            assert not page_errors, "Browser page errors:\n" + "\n".join(page_errors)
            actionable_console_errors = [
                message
                for message in console_errors
                if "Error fetching service health: AbortError" not in message
            ]
            assert not actionable_console_errors, (
                "Browser console errors:\n" + "\n".join(actionable_console_errors)
            )
