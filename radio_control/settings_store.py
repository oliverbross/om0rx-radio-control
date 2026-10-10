"""
JSON-backed runtime settings for station-local configuration.

The Python config module remains the defaults layer. UI-edited non-secret values
are stored in settings/app_settings.json, while credentials and secret-bearing
values are stored in settings/local_secrets.json, which is ignored by Git.
"""

from __future__ import annotations

import logging
import os
import threading
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from radio_control.persistence import atomic_write_json, durable_append_text, read_json_object
from radio_control.station_policy import canonical_band_list, canonical_drive_map


logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_DIR = PROJECT_ROOT / "settings"
APP_SETTINGS_PATH = Path(os.environ.get("OM0RX_APP_SETTINGS_PATH", SETTINGS_DIR / "local_settings.json"))
LOCAL_SECRETS_PATH = Path(os.environ.get("OM0RX_LOCAL_SECRETS_PATH", SETTINGS_DIR / "local_secrets.json"))
RUNTIME_STATE_PATH = Path(os.environ.get("OM0RX_RUNTIME_STATE_PATH", SETTINGS_DIR / "runtime_state.json"))
LEGACY_TRACKED_SETTINGS_PATH = SETTINGS_DIR / "app_settings.json"
LEGACY_ROTOR_CONFIG_PATH = SETTINGS_DIR / "rotor_config.json"
LEGACY_FT8_CONFIG_PATH = PROJECT_ROOT / "logs" / "ft8_config.json"
COMMISSIONING_AUDIT_PATH = SETTINGS_DIR / "station_commissioning_audit.jsonl"


SECRET_KEYS = {
    "DB_HOST",
    "DB_NAME",
    "DB_USER",
    "DB_PASS",
    "POSTGRES_DSN",
    "POSTGRES_HOST",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "CLUSTER_HOST",
    "CLUSTER_USER",
    "CLUSTER_PASS",
    "CLUSTERS",
    "WAVELOG_API_URL",
    "WAVELOG_API_KEY",
    "QRZ_USERNAME",
    "QRZ_PASSWORD",
    "CONTROL_TOKEN",
    "WSJTX_BRIDGE_TOKEN",
}

UNCHANGED_SECRET = "__OM0RX_SECRET_UNCHANGED__"
_settings_lock = threading.RLock()

# Commissioning is a safety latch, not an ordinary UI preference.  Keep it
# outside ALLOWED_CONFIG_KEYS so a stale full-form save cannot set or clear it.
PROTECTED_CONFIG_KEYS = {"STATION_COORDINATOR_COMMISSIONED"}


ALLOWED_CONFIG_KEYS = {
    "ACTIVITY_INTELLIGENCE",
    "ADIF_LOG_PATH",
    "CLUSTER_ENABLED",
    "CLUSTER_HOST",
    "CLUSTER_PASS",
    "CLUSTER_PORT",
    "CLUSTER_USER",
    "CLUSTERS",
    "COLORS",
    "CORS_ALLOWED_ORIGINS",
    "CTY_CSV_PATH",
    "CTY_DAT_PATH",
    "DATABASE_BACKEND",
    "DB_HOST",
    "DB_NAME",
    "DB_PASS",
    "DB_PORT",
    "DB_USER",
    "BACKEND_HOST",
    "BACKEND_PORT",
    "FLEX_ENABLED_DEFAULT",
    "FLEX_ANTENNA_POLICY",
    "FLEX_TCP_HOST",
    "FLEX_TCP_PORT",
    "ELECRAFT_FOLLOW_RADIO",
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
    "KPA500_ENABLED",
    "KPA500_PORT",
    "KPA500_BAUDRATE",
    "DIGITAL_KPA_POLICY",
    "KAT500_ENABLED",
    "KAT500_PORT",
    "KAT500_BAUDRATE",
    "KAT500_ANTENNA_POLICY",
    "KAT500_ANTENNA_NAMES",
    "FT8_AUDIO_INPUT",
    "FT8_AUDIO_OUTPUT",
    "FT8_AUTO_SEQUENCE",
    "FT8_ENABLED",
    "FT8_MODE",
    "FT8_MYCALL",
    "FT8_MYGRID",
    "FT8_HAMLIB_MODEL",
    "FT8_HAMLIB_RIG_PATH",
    "FT8_HAMLIB_RIGCTL_PATH",
    "FT8_HAMLIB_TIMEOUT_SECONDS",
    "FT8_NETWORK_SERVER",
    "FT8_OPERATOR_SETTINGS",
    "FT8_PTT_METHOD",
    "FT8_RIG_BACKEND",
    "FT8_SAMPLE_RATE",
    "FT8_TX_ENABLED",
    "FT8_USE_FLEXRADIO_AUDIO",
    "FT8_WATERFALL_HEIGHT",
    "LOG_LEVEL",
    "MY_STATION",
    "POSTGRES_DSN",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "QRZ_ENABLED",
    "QRZ_PASSWORD",
    "QRZ_USERNAME",
    "RADIO_SHOW_DETAILED_CONTROLS",
    "RADIO_LAYOUT_PRESET",
    "RBL_COMMAND_PROFILE",
    "RBL_COMMAND_PROFILES",
    "RBL_ALERT_RULES",
    "ROTOR_AUTO_DELAY_SEC",
    "ROTOR_AUTO_ENABLED",
    "ROTOR_BANDS",
    "ROTOR_ENABLED",
    "ROTOR_HOME_GRID",
    "ROTOR_HOME_LAT",
    "ROTOR_HOME_LON",
    "ROTOR_HOST",
    "ROTOR_PORT",
    "ROTOR_PROTOCOL",
    "ROTOR_TIMEOUT_SEC",
    "ROTOR_TYPE",
    "SDR_UDP_HOST",
    "SDR_UDP_PORT",
    "SPECIAL_PRESET",
    "UDP_ENABLED_DEFAULT",
    "WAVELOG_API_KEY",
    "WAVELOG_API_URL",
    "WAVELOG_ENABLED",
    "WAVELOG_STATION_ID",
    "WAVELOG_SYNC_INTERVAL",
    "WINKEYER_BAUDRATE",
    "WINKEYER_DEFAULT_WPM",
    "WINKEYER_ENABLED",
    "WINKEYER_MEMORIES",
    "WINKEYER_PORT",
    "WSJTX_AUTO_LOG",
    "WSJTX_AUTO_ROTATE",
    "WSJTX_ENABLED",
    "WSJTX_BRIDGE_COMMAND_URL",
    "WSJTX_UDP_MULTICAST",
    "WSJTX_UDP_PORT",
    "WSJTX_WS_PORT",
    "CONTROL_TOKEN",
    "REMOTE_CONTROL_ENABLED",
    "WSJTX_BRIDGE_TOKEN",
}


def _read_json(path: Path) -> Dict[str, Any]:
    return read_json_object(path, quarantine_corrupt=True)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    atomic_write_json(path, data, backup=True)


def load_app_settings() -> Dict[str, Any]:
    """Return non-secret UI-edited settings."""
    migrate_legacy_tracked_settings()
    return _read_json(APP_SETTINGS_PATH)


def load_local_secrets() -> Dict[str, Any]:
    """Return ignored local secret settings."""
    return _read_json(LOCAL_SECRETS_PATH)


def load_runtime_state() -> Dict[str, Any]:
    return _read_json(RUNTIME_STATE_PATH)


def migrate_legacy_tracked_settings() -> bool:
    """One-time migration from the formerly tracked station settings file."""
    if APP_SETTINGS_PATH.exists() or not LEGACY_TRACKED_SETTINGS_PATH.exists():
        return False
    legacy = _read_json(LEGACY_TRACKED_SETTINGS_PATH)
    if not legacy:
        return False
    app_values, secret_values, _ = split_config_updates(legacy)
    runtime_values: Dict[str, Any] = {}
    operator = app_values.get("FT8_OPERATOR_SETTINGS")
    if isinstance(operator, dict) and isinstance(operator.get("automation"), dict):
        automation = dict(operator["automation"])
        for key in ("autoCQRemaining", "autoCallRemaining", "lastHopAt", "lastHopKey"):
            if key in automation:
                runtime_values[key] = automation.pop(key)
        operator = {**operator, "automation": automation}
        app_values["FT8_OPERATOR_SETTINGS"] = operator
    if app_values:
        _write_json(APP_SETTINGS_PATH, app_values)
    if secret_values:
        secrets = _read_json(LOCAL_SECRETS_PATH)
        secrets.update(secret_values)
        _write_json(LOCAL_SECRETS_PATH, secrets)
    if runtime_values:
        _write_json(RUNTIME_STATE_PATH, {"ft8_automation": runtime_values})
    logger.info("Migrated legacy tracked settings into station-local stores")
    return True


def load_runtime_settings() -> Dict[str, Any]:
    """Return the merged JSON settings layer, with local secrets winning."""
    settings = load_app_settings()
    settings.update(load_local_secrets())
    return settings


def split_config_updates(updates: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], list[str]]:
    """Split incoming settings into app settings, local secrets, and rejected keys."""
    app_updates: Dict[str, Any] = {}
    secret_updates: Dict[str, Any] = {}
    rejected: list[str] = []

    for key, value in updates.items():
        if key not in ALLOWED_CONFIG_KEYS:
            rejected.append(key)
            continue

        if key in SECRET_KEYS:
            if value == UNCHANGED_SECRET:
                continue
            secret_updates[key] = value
        else:
            app_updates[key] = value

    return app_updates, secret_updates, rejected


def save_config_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Persist allowed config updates without modifying Python source files."""
    if not isinstance(updates, dict):
        raise ValueError("Configuration update must be an object")
    app_updates, secret_updates, rejected = split_config_updates(updates)
    normalized = normalize_config_updates({**app_updates, **secret_updates})
    app_updates = {key: normalized[key] for key in app_updates}
    secret_updates = {key: normalized[key] for key in secret_updates}
    with _settings_lock:
        app_settings = load_app_settings()
        local_secrets = load_local_secrets()
        operator = app_updates.get("FT8_OPERATOR_SETTINGS")
        if isinstance(operator, dict) and isinstance(operator.get("automation"), dict):
            automation = dict(operator["automation"])
            runtime_values = {
                key: automation.pop(key)
                for key in ("autoCQRemaining", "autoCallRemaining", "lastHopAt", "lastHopKey")
                if key in automation
            }
            if runtime_values:
                runtime_state = load_runtime_state()
                runtime_state["ft8_automation"] = {
                    **runtime_state.get("ft8_automation", {}),
                    **runtime_values,
                }
                _write_json(RUNTIME_STATE_PATH, runtime_state)
            app_updates["FT8_OPERATOR_SETTINGS"] = {**operator, "automation": automation}
        missing = object()
        app_updates = {
            key: value
            for key, value in app_updates.items()
            if app_settings.get(key, missing) != value
        }
        secret_updates = {
            key: value
            for key, value in secret_updates.items()
            if local_secrets.get(key, missing) != value
        }
        app_settings.update(app_updates)
        local_secrets.update(secret_updates)

        if app_updates:
            _write_json(APP_SETTINGS_PATH, app_settings)
        if secret_updates:
            _write_json(LOCAL_SECRETS_PATH, local_secrets)

    return {
        "app_settings_path": str(APP_SETTINGS_PATH),
        "local_secrets_path": str(LOCAL_SECRETS_PATH),
        "app_settings_keys": sorted(app_updates),
        "local_secret_keys": sorted(secret_updates),
        "rejected_keys": sorted(rejected),
        "updated_keys": sorted([*app_updates.keys(), *secret_updates.keys()]),
    }


def public_config_from_module(config_module: Any, keys: Iterable[str] | None = None) -> Dict[str, Any]:
    """Build a serializable config dictionary from the active config module."""
    selected_keys = keys or sorted(ALLOWED_CONFIG_KEYS)
    public = {
        key: getattr(config_module, key)
        for key in selected_keys
        if key not in SECRET_KEYS and hasattr(config_module, key)
    }
    for key in sorted(SECRET_KEYS):
        public[f"{key}_CONFIGURED"] = bool(getattr(config_module, key, None))
    public["SECRET_UNCHANGED_SENTINEL"] = UNCHANGED_SECRET
    return public


def save_station_commissioning_latch(commissioned: bool, *, reason: str) -> Dict[str, Any]:
    """Persist the protected commissioning latch with an append-only audit entry.

    This deliberately narrow writer is the only supported path for changing
    ``STATION_COORDINATOR_COMMISSIONED``.  Ordinary configuration and digital
    provider saves merge around the protected value and cannot alter it.
    """
    if not isinstance(commissioned, bool):
        raise ValueError("commissioned must be a boolean")
    audit_reason = str(reason or "").strip()
    if not audit_reason:
        raise ValueError("A commissioning latch change requires an audit reason")

    with _settings_lock:
        app_settings = load_app_settings()
        previous = app_settings.get("STATION_COORDINATOR_COMMISSIONED")
        changed = previous is not commissioned
        if changed:
            app_settings["STATION_COORDINATOR_COMMISSIONED"] = commissioned
            _write_json(APP_SETTINGS_PATH, app_settings)
        audit = {
            "timestamp": datetime.now(UTC).isoformat(),
            "setting": "STATION_COORDINATOR_COMMISSIONED",
            "previous": previous,
            "value": commissioned,
            "changed": changed,
            "reason": audit_reason,
            "settings_path": str(APP_SETTINGS_PATH),
        }
        durable_append_text(
            COMMISSIONING_AUDIT_PATH,
            json.dumps(audit, sort_keys=True, ensure_ascii=False) + "\n",
        )

    logger.warning(
        "Station commissioning latch persisted: previous=%r value=%r changed=%s reason=%s",
        previous,
        commissioned,
        changed,
        audit_reason,
    )
    return audit


def _validate_updates(updates: Dict[str, Any]) -> None:
    """Reject structurally unsafe settings before changing live configuration."""
    bool_keys = {
        key for key in ALLOWED_CONFIG_KEYS
        if key.endswith("_ENABLED") or key.endswith("_DEFAULT")
    } | {
        "ELECRAFT_FOLLOW_RADIO",
        "FT8_AUTO_SEQUENCE",
        "REMOTE_CONTROL_ENABLED",
        "WSJTX_AUTO_LOG",
        "WSJTX_AUTO_ROTATE",
    }
    port_keys = {
        key for key in ALLOWED_CONFIG_KEYS
        if key.endswith("_PORT") and key not in {"WINKEYER_PORT", "KPA500_PORT", "KAT500_PORT"}
    }
    for key, value in updates.items():
        if key in bool_keys and not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        if key in port_keys and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535):
            raise ValueError(f"{key} must be an integer between 1 and 65535")
        if key in {"WINKEYER_PORT", "KPA500_PORT", "KAT500_PORT"} and value is not None and not isinstance(value, str):
            raise ValueError(f"{key} must be a serial port name")
        if key in {"KPA500_BAUDRATE", "KAT500_BAUDRATE"} and value not in {4800, 9600, 19200, 38400}:
            raise ValueError(f"{key} must be 4800, 9600, 19200, or 38400")
        if key == "DIGITAL_KPA_POLICY" and value not in {"operate", "standby"}:
            raise ValueError("DIGITAL_KPA_POLICY must be operate or standby")
        if key == "STATION_ROUTE_VERIFY_TTL_SECONDS" and not 1 <= float(value) <= 60:
            raise ValueError("STATION_ROUTE_VERIFY_TTL_SECONDS must be between 1 and 60")
        if key in {"STATION_AMPLIFIER_ALLOWED_BANDS", "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS"}:
            valid_bands = {"160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"}
            if not isinstance(value, list) or any(str(item).strip().lower() not in valid_bands for item in value):
                raise ValueError(f"{key} must be a list of supported amateur bands")
        if key in {"STATION_AMPLIFIER_DRIVE_W", "STATION_BAREFOOT_DRIVE_W", "STATION_DIGITAL_AMPLIFIER_DRIVE_W"}:
            valid_bands = {"160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"}
            if (
                not isinstance(value, dict)
                or any(str(band).strip().lower() not in valid_bands for band in value)
                or any(isinstance(power, bool) or not isinstance(power, int) or not 1 <= power <= 100 for power in value.values())
            ):
                raise ValueError(f"{key} must map supported amateur bands to integer watts from 1 to 100")
        if key == "STATION_TUNE_POWER_W" and (
            isinstance(value, bool) or not isinstance(value, int) or not 15 <= value <= 30
        ):
            raise ValueError("STATION_TUNE_POWER_W must be an integer between 15 and 30")
        if key == "STATION_TUNE_TARGET_SWR" and not 1 <= float(value) <= 3:
            raise ValueError("STATION_TUNE_TARGET_SWR must be between 1 and 3")
        if key == "STATION_TUNE_ABORT_SWR" and not 1.5 <= float(value) <= 5:
            raise ValueError("STATION_TUNE_ABORT_SWR must be between 1.5 and 5")
        if key == "STATION_TUNE_TIMEOUT_SECONDS" and not 5 <= float(value) <= 60:
            raise ValueError("STATION_TUNE_TIMEOUT_SECONDS must be between 5 and 60")
        if key == "STATION_TELEMETRY_INTERVAL_SECONDS" and not 1 <= float(value) <= 60:
            raise ValueError("STATION_TELEMETRY_INTERVAL_SECONDS must be between 1 and 60")
        if key == "STATION_TELEMETRY_RETENTION_DAYS" and (
            isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 365
        ):
            raise ValueError("STATION_TELEMETRY_RETENTION_DAYS must be an integer between 1 and 365")
        if key in {"ROTOR_HOME_LAT"} and value is not None and not -90 <= float(value) <= 90:
            raise ValueError(f"{key} must be between -90 and 90")
        if key in {"ROTOR_HOME_LON"} and value is not None and not -180 <= float(value) <= 180:
            raise ValueError(f"{key} must be between -180 and 180")
        if key in SECRET_KEYS and value is not None and not isinstance(value, (str, dict, list)):
            raise ValueError(f"{key} has an invalid secret value")

    if updates.get("WINKEYER_ENABLED") is True and not str(updates.get("WINKEYER_PORT") or "").strip():
        raise ValueError("WINKEYER_PORT is required when WinKeyer is enabled")
    for prefix in ("KPA500", "KAT500"):
        if updates.get(f"{prefix}_ENABLED") is True and not str(updates.get(f"{prefix}_PORT") or "").strip():
            raise ValueError(f"{prefix}_PORT is required when {prefix} is enabled")

    policy = updates.get("KAT500_ANTENNA_POLICY")
    if policy is not None:
        if not isinstance(policy, dict) or any(value not in {1, 2, 3} for value in policy.values()):
            raise ValueError("KAT500_ANTENNA_POLICY values must be antenna numbers 1, 2, or 3")

    antenna_names = updates.get("KAT500_ANTENNA_NAMES")
    if antenna_names is not None:
        if not isinstance(antenna_names, dict):
            raise ValueError("KAT500_ANTENNA_NAMES must be an object")
        allowed = {"1", "2", "3", 1, 2, 3}
        if any(key not in allowed for key in antenna_names):
            raise ValueError("KAT500_ANTENNA_NAMES keys must be 1, 2, or 3")
        if any(not isinstance(value, str) or not value.strip() for value in antenna_names.values()):
            raise ValueError("KAT500_ANTENNA_NAMES values must be non-empty names")


def normalize_config_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and canonicalize settings before comparison or persistence."""
    if not isinstance(updates, dict):
        raise ValueError("Configuration update must be an object")
    _validate_updates(updates)
    normalized = dict(updates)
    for key in ("STATION_AMPLIFIER_ALLOWED_BANDS", "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS"):
        if key in normalized:
            normalized[key] = canonical_band_list(normalized[key])
    for key in ("STATION_AMPLIFIER_DRIVE_W", "STATION_BAREFOOT_DRIVE_W", "STATION_DIGITAL_AMPLIFIER_DRIVE_W"):
        if key in normalized:
            normalized[key] = canonical_drive_map(normalized[key])
    return normalized


def load_legacy_json(path: Path) -> Dict[str, Any]:
    """Read a legacy JSON settings file for one-time compatibility fallback."""
    return _read_json(path)
