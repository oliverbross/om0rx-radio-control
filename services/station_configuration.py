"""Semantic, read-only station configuration snapshots and restore previews."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Mapping

from radio_control import config
from radio_control.settings_store import _validate_updates


SNAPSHOT_KEYS = (
    "KPA500_ENABLED",
    "KPA500_PORT",
    "KPA500_BAUDRATE",
    "KAT500_ENABLED",
    "KAT500_PORT",
    "KAT500_BAUDRATE",
    "ELECRAFT_FOLLOW_RADIO",
    "DIGITAL_KPA_POLICY",
    "FLEX_ANTENNA_POLICY",
    "KAT500_ANTENNA_POLICY",
    "KAT500_ANTENNA_NAMES",
    "STATION_AMPLIFIER_ALLOWED_BANDS",
    "STATION_AMPLIFIER_DRIVE_W",
    "STATION_BAREFOOT_DRIVE_W",
    "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS",
    "STATION_DIGITAL_AMPLIFIER_DRIVE_W",
    "STATION_ROUTE_VERIFY_TTL_SECONDS",
    "STATION_TUNE_POWER_W",
    "STATION_TUNE_TARGET_SWR",
    "STATION_TUNE_ABORT_SWR",
    "STATION_TUNE_TIMEOUT_SECONDS",
    "STATION_TELEMETRY_INTERVAL_SECONDS",
    "STATION_TELEMETRY_RETENTION_DAYS",
)

ROUTE_KEYS = {
    "DIGITAL_KPA_POLICY",
    "FLEX_ANTENNA_POLICY",
    "KAT500_ANTENNA_POLICY",
    "KAT500_ANTENNA_NAMES",
    "STATION_AMPLIFIER_ALLOWED_BANDS",
    "STATION_AMPLIFIER_DRIVE_W",
    "STATION_BAREFOOT_DRIVE_W",
    "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS",
    "STATION_DIGITAL_AMPLIFIER_DRIVE_W",
}
CONNECTION_KEYS = {
    "KPA500_ENABLED",
    "KPA500_PORT",
    "KPA500_BAUDRATE",
    "KAT500_ENABLED",
    "KAT500_PORT",
    "KAT500_BAUDRATE",
}
TUNE_KEYS = {
    "STATION_TUNE_POWER_W",
    "STATION_TUNE_TARGET_SWR",
    "STATION_TUNE_ABORT_SWR",
    "STATION_TUNE_TIMEOUT_SECONDS",
}


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def _settings() -> dict[str, Any]:
    return {
        key: _json_clone(getattr(config, key))
        for key in SNAPSHOT_KEYS
        if hasattr(config, key)
    }


def _device_summary(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(raw or {})
    return {
        key: copy.deepcopy(source.get(key))
        for key in (
            "enabled",
            "connected",
            "responsive",
            "port",
            "baudrate",
            "serial_number",
            "firmware",
            "observed_at",
            "quality",
            "missing_fields",
        )
        if key in source
    }


def build_configuration_snapshot(manager: Any) -> dict[str, Any]:
    settings = _settings()
    canonical = json.dumps(settings, sort_keys=True, separators=(",", ":"))
    status = manager.snapshot() if manager is not None else {}
    return {
        "schema_version": 1,
        "snapshot_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
        "created_at": datetime.now(UTC).isoformat(),
        "restorable": False,
        "settings": settings,
        "devices": {
            "kpa500": _device_summary(status.get("kpa500")),
            "kat500": _device_summary(status.get("kat500")),
        },
        "notes": [
            "Secrets, commissioning state, firmware images, and raw EEPROM data are excluded.",
            "Restore is preview-only until Maintenance Mode and hardware acceptance are complete.",
        ],
    }


def _change_class(key: str) -> str:
    if key in CONNECTION_KEYS:
        return "connection"
    if key in ROUTE_KEYS:
        return "route"
    if key in TUNE_KEYS:
        return "tune-safety"
    return "operational"


def preview_configuration_restore(
    proposed_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(proposed_snapshot, Mapping):
        raise ValueError("configuration snapshot must be an object")
    if int(proposed_snapshot.get("schema_version", 0) or 0) != 1:
        raise ValueError("unsupported configuration snapshot schema")
    proposed = proposed_snapshot.get("settings")
    if not isinstance(proposed, Mapping):
        raise ValueError("configuration snapshot settings must be an object")
    unknown = sorted(set(proposed) - set(SNAPSHOT_KEYS))
    if unknown:
        raise ValueError(f"configuration snapshot contains unsupported keys: {', '.join(unknown)}")
    candidate = {key: _json_clone(value) for key, value in proposed.items()}
    _validate_updates(candidate)
    current = _settings()
    changes = [
        {
            "key": key,
            "before": current.get(key),
            "after": candidate.get(key),
            "class": _change_class(key),
            "requires_maintenance": key in CONNECTION_KEYS or key in ROUTE_KEYS,
        }
        for key in SNAPSHOT_KEYS
        if key in candidate and current.get(key) != candidate.get(key)
    ]
    return {
        "schema_version": 1,
        "preview_only": True,
        "apply_available": False,
        "valid": True,
        "change_count": len(changes),
        "requires_maintenance": any(item["requires_maintenance"] for item in changes),
        "changes": changes,
        "excluded_keys": ["STATION_COORDINATOR_COMMISSIONED", "ELECRAFT_LEGACY_CONTROL_ENABLED"],
        "warnings": (
            ["Applying this preview is intentionally unavailable before hardware acceptance."]
            if changes
            else []
        ),
    }
