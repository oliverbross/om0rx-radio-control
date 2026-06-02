#!/usr/bin/env python3
"""Live browser smoke test for the visual DX spot globe.

This diagnostic is intentionally outside the default smoke suite because it needs
a running local app, Playwright, Chromium, and live or recent spot data.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

import pytest

import _bootstrap  # noqa: F401


BASE_URL = os.environ.get("OM0RX_LIVE_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
TIMEOUT_MS = int(os.environ.get("OM0RX_VISUAL_BROWSER_TIMEOUT_MS", "60000"))
STATE_POLL_MS = 1000

PLOTTED_RE = re.compile(r"(\d+)\s+plotted", re.IGNORECASE)
PATHS_RE = re.compile(r"(\d+)\s+paths", re.IGNORECASE)
SOURCE_COUNTS_RE = re.compile(r"(\d+)\s+cluster\s*/\s*(\d+)\s+RBL", re.IGNORECASE)
ZOOM_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)x", re.IGNORECASE)

VISUAL_STATE_SCRIPT = """
() => ({
  stats: Array.from(document.querySelectorAll('.visual-stat-pill'))
    .map((el) => el.textContent.trim()),
  quickFilters: Array.from(document.querySelectorAll('.visual-quick-filter-btn')).map((el) => ({
    text: el.textContent.replace(/\\s+/g, ' ').trim(),
    active: el.classList.contains('active')
  })),
  sourceText: document.querySelector('.source-diagnostics-strip')?.textContent
    .replace(/\\s+/g, ' ').trim() || '',
  emptyVisible: Array.from(document.querySelectorAll('.visual-empty-state'))
    .some((el) => el.offsetParent !== null),
  canvasCount: document.querySelectorAll('canvas.visual-globe-canvas').length,
  zoomLabel: document.querySelector('.visual-zoom-pill')?.textContent.trim() || ''
})
"""


def get_json(path: str) -> dict[str, Any]:
    request = urllib.request.Request(f"{BASE_URL}{path}", method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def require_live_app() -> None:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/", timeout=5) as response:
            if response.status >= 400:
                pytest.skip(f"Live app at {BASE_URL} returned HTTP {response.status}")
    except (OSError, urllib.error.URLError) as exc:
        pytest.skip(f"Live app is not reachable at {BASE_URL}: {exc}")


def recent_source_counts() -> dict[str, int]:
    try:
        data = get_json("/api/spots/source-stats")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        pytest.skip(f"Cannot read live source stats from {BASE_URL}: {exc}")

    windows = data.get("windows") or []
    one_hour = next((item for item in windows if item.get("minutes") == 60), None)
    if one_hour is None:
        live = data.get("live") or {}
        one_hour = {
            "total": live.get("total", 0),
            "cluster": live.get("cluster", 0),
            "rbl": live.get("rbl", 0),
        }

    return {
        "total": int(one_hour.get("total") or 0),
        "cluster": int(one_hour.get("cluster") or 0),
        "rbl": int(one_hour.get("rbl") or 0),
    }


def parse_visual_state(state: dict[str, Any]) -> dict[str, int | float | str | bool]:
    stats = " ".join(state.get("stats") or [])
    source = state.get("sourceText") or ""
    combined = f"{stats} {source}"
    plotted_match = PLOTTED_RE.search(stats)
    paths_match = PATHS_RE.search(stats)
    source_match = SOURCE_COUNTS_RE.search(combined)
    zoom_match = ZOOM_RE.search(state.get("zoomLabel") or "")

    return {
        "plotted": int(plotted_match.group(1)) if plotted_match else 0,
        "paths": int(paths_match.group(1)) if paths_match else 0,
        "cluster": int(source_match.group(1)) if source_match else 0,
        "rbl": int(source_match.group(2)) if source_match else 0,
        "zoom": float(zoom_match.group(1)) if zoom_match else 1.0,
        "empty": bool(state.get("emptyVisible")),
        "canvas_count": int(state.get("canvasCount") or 0),
    }


def wait_for_visual_state(
    page: Any,
    *,
    min_plotted: int,
    timeout_ms: int = TIMEOUT_MS,
) -> dict[str, Any]:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_state = page.evaluate(VISUAL_STATE_SCRIPT)
        parsed = parse_visual_state(last_state)
        if (
            parsed["canvas_count"] >= 3
            and parsed["plotted"] >= min_plotted
            and not parsed["empty"]
        ):
            return last_state
        page.wait_for_timeout(STATE_POLL_MS)

    raise AssertionError(f"Visual globe did not reach plotted state. Last state: {last_state}")


def click_source_filter(page: Any, label: str) -> None:
    strip = page.locator(".source-diagnostics-strip")
    strip.wait_for(timeout=TIMEOUT_MS)
    strip.locator("button", has_text=label).first.click(timeout=TIMEOUT_MS)


def open_visual_map(page: Any) -> None:
    page.locator("button.view-mode-btn", has_text="Map").click(timeout=TIMEOUT_MS)
    page.wait_for_selector("canvas.visual-globe-canvas", timeout=TIMEOUT_MS)
    page.locator(".visual-globe-controls").wait_for(timeout=TIMEOUT_MS)


def assert_source_mode(state: dict[str, Any], *, cluster: bool, rbl: bool) -> None:
    parsed = parse_visual_state(state)
    if cluster:
        assert parsed["cluster"] > 0, f"Expected visible cluster spots. State: {state}"
    else:
        assert parsed["cluster"] == 0, f"Cluster spots leaked into non-cluster view. State: {state}"

    if rbl:
        assert parsed["rbl"] > 0, f"Expected visible RBL spots. State: {state}"
    else:
        assert parsed["rbl"] == 0, f"RBL spots leaked into cluster-only view. State: {state}"


def assert_no_browser_errors(console_errors: list[str], page_errors: list[str]) -> None:
    benign_console_fragments = (
        "Error fetching service health: AbortError",
    )
    actionable_console_errors = [
        message
        for message in console_errors
        if not any(fragment in message for fragment in benign_console_fragments)
    ]
    assert not page_errors, "Browser page errors:\n" + "\n".join(page_errors)
    assert not actionable_console_errors, (
        "Browser console errors:\n" + "\n".join(actionable_console_errors)
    )


def test_visual_globe_source_modes_and_deep_zoom() -> None:
    require_live_app()
    source_counts = recent_source_counts()
    if source_counts["cluster"] <= 0 or source_counts["rbl"] <= 0:
        pytest.skip(
            "Visual browser source-mode smoke needs both cluster and RBL spots in the latest "
            f"1h window. Current counts: {source_counts}"
        )

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
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            page.goto(f"{BASE_URL}/?v=visual-browser-smoke", wait_until="domcontentloaded")
            open_visual_map(page)

            click_source_filter(page, "Cluster only")
            cluster_state = wait_for_visual_state(page, min_plotted=1)
            assert_source_mode(cluster_state, cluster=True, rbl=False)

            click_source_filter(page, "All sources")
            all_sources_state = wait_for_visual_state(page, min_plotted=2)
            assert_source_mode(all_sources_state, cluster=True, rbl=True)

            click_source_filter(page, "RBL only")
            rbl_state = wait_for_visual_state(page, min_plotted=1)
            assert_source_mode(rbl_state, cluster=False, rbl=True)

            page.locator(".visual-globe-controls button", has_text="Reset").click(
                timeout=TIMEOUT_MS
            )
            zoom_in = page.locator(".visual-globe-controls button[title='Zoom in']")
            for _ in range(18):
                zoom_in.click(timeout=TIMEOUT_MS)
            deep_zoom_state = wait_for_visual_state(page, min_plotted=1)
            deep_zoom = parse_visual_state(deep_zoom_state)
            assert deep_zoom["zoom"] >= 8.0, f"Expected deep zoom >= 8x. State: {deep_zoom_state}"
            assert deep_zoom["paths"] > 0, (
                f"Expected path rendering to survive deep zoom. State: {deep_zoom_state}"
            )

            assert_no_browser_errors(console_errors, page_errors)
