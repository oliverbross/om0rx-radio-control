#!/usr/bin/env python3
"""Smoke checks for the no-build frontend module contract."""

from pathlib import Path
import re

import _bootstrap  # noqa: F401


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = PROJECT_ROOT / "frontend"
APP_MAIN = FRONTEND / "js" / "app-main.js"
INDEX = FRONTEND / "index.html"
RADIO_CONTROLS = FRONTEND / "js" / "radio-controls.js"
DX_SPOTS = FRONTEND / "js" / "dx-spots.js"
COMPACT_RADIO_PARTIAL = FRONTEND / "templates" / "partials" / "compact-radio-controls.html"
SOURCE_MONITOR_PARTIAL = FRONTEND / "templates" / "partials" / "spots-source-monitor.html"
DX_SPOTS_TEMPLATE = FRONTEND / "templates" / "dx-spots.html"

REQUIRED_MODULES = {
    "js/config-modal.js": "RadioControlConfig",
    "js/solar-data.js": "RadioControlSolar",
    "js/wavelog-stats.js": "RadioControlWavelogStats",
}


def script_sources() -> list[str]:
    html = INDEX.read_text(encoding="utf-8")
    return re.findall(r'<script\s+src="([^"]+)"', html)


def test_required_modules_load_before_app_main():
    scripts = script_sources()
    assert "js/app-main.js" in scripts, "app-main.js is not loaded by index.html"
    app_main_index = scripts.index("js/app-main.js")

    missing = [script for script in REQUIRED_MODULES if script not in scripts]
    assert not missing, f"Missing frontend module script tags: {missing}"

    late = [script for script in REQUIRED_MODULES if scripts.index(script) > app_main_index]
    assert not late, f"Modules must load before app-main.js: {late}"


def test_required_modules_expose_expected_globals():
    for script, global_name in REQUIRED_MODULES.items():
        module_path = FRONTEND / script
        assert module_path.exists(), f"Missing module file: {script}"
        content = module_path.read_text(encoding="utf-8")
        assert f"window.{global_name}" in content, f"{script} does not expose window.{global_name}"
        assert "data:" in content, f"{script} does not define a data section"
        assert "methods:" in content, f"{script} does not define a methods section"


def test_app_main_merges_required_modules():
    content = APP_MAIN.read_text(encoding="utf-8")
    for global_name in REQUIRED_MODULES.values():
        assert f"window.{global_name}" in content, f"app-main.js does not check {global_name}"
        assert f"...window.{global_name}.data" in content, f"app-main.js does not merge {global_name}.data"
        assert f"...window.{global_name}.methods" in content, f"app-main.js does not merge {global_name}.methods"


def test_wavelog_stats_refresh_after_qso_contract():
    stats = (FRONTEND / "js" / "wavelog-stats.js").read_text(encoding="utf-8")
    app_main = APP_MAIN.read_text(encoding="utf-8")
    ft8_modal = (FRONTEND / "js" / "ft8-modal.js").read_text(encoding="utf-8")
    utils = (FRONTEND / "js" / "utils.js").read_text(encoding="utf-8")

    assert "setupWavelogStatisticsRefresh" in stats
    assert "60000" in stats
    assert "scheduleWavelogStatisticsRefresh('QSO logged', [0, 8000, 30000])" in stats
    assert "clearWavelogLookupCaches" in stats
    assert "await this.handleQsoLogged(qsoData)" in app_main
    assert "this.setupWavelogStatisticsRefresh()" in app_main
    assert "this.cleanupWavelogStatisticsRefresh()" in app_main
    assert "logged: Boolean(qso?.logged)" in ft8_modal
    assert "log_status: qso?.log_status || 'unknown'" in ft8_modal
    assert "!options.force" in utils


def test_obvious_frontend_junk_is_not_tracked():
    assert not (FRONTEND / "conosle.log").exists(), "frontend/conosle.log should not exist"


def test_rotator_frontend_resolution_contract():
    radio_controls = RADIO_CONTROLS.read_text(encoding="utf-8")
    app_main = APP_MAIN.read_text(encoding="utf-8")
    dx_spots = DX_SPOTS.read_text(encoding="utf-8")
    controls_template = (FRONTEND / "templates" / "controls-row3.html").read_text(encoding="utf-8")

    assert "buildRotorRequest" in radio_controls
    assert "resolveRotorTarget" in radio_controls
    assert "updateBeamingDisplay" in radio_controls
    assert "fetch('/api/rotor/resolve'" in radio_controls
    assert "data.source_label" in radio_controls
    assert "data.confidence" in radio_controls

    for field in ("beamingSourceLabel", "beamingConfidence", "beamingApproximate"):
        assert field in app_main, f"Missing frontend state field: {field}"
        assert field in controls_template, f"Missing beaming template field: {field}"

    assert "rotorAutoGoto(spot.callsign" in dx_spots
    assert "Promise.allSettled" in dx_spots
    assert "loadQRZProfile({ triggerRotor: true, includeHistory: false })" in dx_spots
    assert dx_spots.index("rotorAutoGoto(spot.callsign") < dx_spots.index("Promise.allSettled")


def test_compact_radio_controls_are_shared_and_persistent():
    row1 = (FRONTEND / "templates" / "controls-row1.html").read_text(encoding="utf-8")
    legacy_section = (FRONTEND / "controls-section.html").read_text(encoding="utf-8")
    partial = COMPACT_RADIO_PARTIAL.read_text(encoding="utf-8")
    radio_controls = RADIO_CONTROLS.read_text(encoding="utf-8")
    core = (FRONTEND / "js" / "core.js").read_text(encoding="utf-8")
    app_main = APP_MAIN.read_text(encoding="utf-8")

    include = "<!-- @include templates/partials/compact-radio-controls.html -->"
    assert include in row1
    assert include in legacy_section
    assert row1.count("compact-radio-row") == 0
    assert legacy_section.count("compact-radio-row") == 0

    for token in (
        "getRadioLayoutPreset()",
        "shouldShowCompactRotorControls()",
        "shouldShowMutedRotorCard()",
        "shouldShowCompactWinKeyer()",
        "shouldShowCompactWinKeyerMemories()",
        "compactLayoutClass()",
    ):
        assert token in partial

    for token in (
        "applyPresetPanelDefaults",
        "loadCompactPanelPrefs",
        "saveCompactPanelPrefs",
        "toggleCompactPanelPref",
        "om0rx.radio.compactPanelPrefs",
    ):
        assert token in radio_controls

    assert "compactPanelPrefs" in core
    assert "this.loadCompactPanelPrefs()" in app_main
    assert "RADIO_LAYOUT_PRESET: preset" in radio_controls
    assert "RADIO_SHOW_DETAILED_CONTROLS: this.configData.RADIO_SHOW_DETAILED_CONTROLS" in radio_controls


def test_spot_source_state_contract():
    dx_spots = DX_SPOTS.read_text(encoding="utf-8")
    source_monitor = SOURCE_MONITOR_PARTIAL.read_text(encoding="utf-8")
    styles = (FRONTEND / "main-styles.css").read_text(encoding="utf-8")

    assert "getSourceStateSummaryItems" in dx_spots
    assert "Cluster hidden" in dx_spots
    assert "RBL muted" in dx_spots
    assert "source-state-summary" in source_monitor
    assert "getSourceStateSummaryItems().length" in source_monitor
    assert "om0rx.spots.sourceMuted" in dx_spots
    assert ".source-state-pill" in styles
    assert ".source-state-warning" in styles


def test_visual_spots_map_contract():
    dx_spots = DX_SPOTS.read_text(encoding="utf-8")
    template = DX_SPOTS_TEMPLATE.read_text(encoding="utf-8")
    styles = (FRONTEND / "main-styles.css").read_text(encoding="utf-8")
    app_main = APP_MAIN.read_text(encoding="utf-8")

    for token in (
        "switchViewMode('visual')",
        "viewMode === 'visual'",
        "visual-spots-panel",
        "visual-polar-map",
        "visual-globe-canvas",
        "visualOverlayMode",
        "getVisualSpotItems()",
        "getVisualSpotStats()",
        "getVisualBandColor",
        "setVisualMapMode('globe')",
        "focusVisualSpot(item.spot)",
    ):
        assert token in template

    for token in (
        "visualSpotWindowMinutes",
        "visualSpotLatestOnly",
        "visualMapMode",
        "visualOverlayMode",
        "ensureVisualTopoFeatures",
        "drawVisualGlobe",
        "projectVisualGlobe",
        "buildVisualOverlayStats",
        "getVisualOverlaySummary",
        "startVisualGlobeDrag",
        "focusVisualGlobeClick",
        "gridToLatLon",
        "calculateDistanceKm",
        "calculateBearing",
        "getVisualSourceSpots",
        "getVisualSpotItems",
        "getVisualMapRadiusKm",
        "getVisualHomeGrid",
    ):
        assert token in dx_spots

    for token in (
        ".visual-map-layout",
        ".visual-polar-map",
        ".visual-globe-canvas",
        ".visual-globe-controls",
        ".visual-spot-marker",
        ".visual-spot-list",
    ):
        assert token in styles

    assert "this.setupVisualGlobeRefresh()" in app_main
    assert "this.cleanupVisualGlobeRefresh()" in app_main


if __name__ == "__main__":
    test_required_modules_load_before_app_main()
    test_required_modules_expose_expected_globals()
    test_app_main_merges_required_modules()
    test_wavelog_stats_refresh_after_qso_contract()
    test_obvious_frontend_junk_is_not_tracked()
    test_rotator_frontend_resolution_contract()
    test_compact_radio_controls_are_shared_and_persistent()
    test_spot_source_state_contract()
    test_visual_spots_map_contract()
    print("Frontend module contract smoke checks passed")
