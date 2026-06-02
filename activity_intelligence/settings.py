"""Settings helpers for Activity Intelligence."""

from __future__ import annotations

from typing import Any

from radio_control import config


DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "enrichExistingSpots": True,
    "showPriorityScore": True,
    "autoSortByPriority": False,
    "keepRawPayloadsDays": 14,
    "showSourceAttribution": True,
    "dxpeditions": {
        "enabled": True,
        "ng3kAdxoEnabled": True,
        "ng3kPollHours": 12,
        "dxcalIcsEnabled": True,
        "upcomingWindowDays": 30,
    },
    "contests": {
        "enabled": True,
        "wa7bnmEnabled": True,
        "wa7bnmFeedPollHours": 6,
        "wa7bnmDetailParsingEnabled": False,
        "localContestDefinitionsPath": "config/contest_definitions.yaml",
        "showRunningContestBanner": True,
    },
    "propagation": {
        "enabled": True,
        "swpcEnabled": True,
        "lowerPriorityWhenPoor": True,
        "showReasonTooltips": True,
        "useRbnEvidence": True,
    },
    "portable": {
        "enabled": True,
        "pota": {
            "enabled": True,
            "useUndocumentedApi": True,
            "activeSpotIntervalSeconds": 60,
            "scheduleIntervalSeconds": 600,
        },
        "sota": {"enabled": True, "activeSpotIntervalSeconds": 60, "alertsIntervalSeconds": 300},
        "wwff": {"enabled": True, "minRefreshSeconds": 30},
        "parksnpeaks": {"enabled": True, "spotsIntervalSeconds": 60, "alertsIntervalSeconds": 300},
    },
    "rbn": {
        "enabled": True,
        "ingestFromExistingCluster": True,
        "directTelnet": False,
        "directTelnetHost": "telnet.reversebeacon.net",
        "directTelnetPort": 7000,
        "directFt8TelnetHost": "telnet.reversebeacon.net",
        "directFt8TelnetPort": 7001,
        "ownCallOnlyProcessing": True,
        "stationCalls": [],
        "rawRetentionDays": 30,
        "aggregateRetentionMonths": 24,
    },
    "spotPriority": {
        "base": 20,
        "dxpeditionActive": 30,
        "dxpeditionUpcomingWithin24h": 10,
        "portableActive": 20,
        "portableScheduledNow": 15,
        "contestActiveBandMode": 10,
        "neededAtno": 40,
        "neededBandSlot": 25,
        "neededModeSlot": 20,
        "newPortableReference": 25,
        "propagationExcellent": 15,
        "propagationGood": 10,
        "propagationFair": 0,
        "propagationMarginal": -8,
        "propagationPoor": -15,
        "rbnSameRegionEvidence": 8,
        "duplicate": -35,
        "staleSpotPerMinuteAfter10": -1,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_settings() -> dict[str, Any]:
    """Return activity-intelligence settings with local overrides applied."""
    override = getattr(config, "ACTIVITY_INTELLIGENCE", None)
    if override is None:
        override = getattr(config, "_app_settings", {}).get("activityIntelligence", {})
    if not isinstance(override, dict):
        override = {}
    settings = _deep_merge(DEFAULTS, override)
    configured_calls = settings.get("rbn", {}).get("stationCalls") or []
    if not configured_calls:
        station_call = getattr(config, "MY_STATION", "")
        if station_call:
            settings["rbn"]["stationCalls"] = [station_call]
    return settings
