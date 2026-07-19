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
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from radio_control.persistence import atomic_write_json, read_json_object


logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_DIR = PROJECT_ROOT / "settings"
APP_SETTINGS_PATH = Path(os.environ.get("OM0RX_APP_SETTINGS_PATH", SETTINGS_DIR / "local_settings.json"))
LOCAL_SECRETS_PATH = Path(os.environ.get("OM0RX_LOCAL_SECRETS_PATH", SETTINGS_DIR / "local_secrets.json"))
RUNTIME_STATE_PATH = Path(os.environ.get("OM0RX_RUNTIME_STATE_PATH", SETTINGS_DIR / "runtime_state.json"))
LEGACY_TRACKED_SETTINGS_PATH = SETTINGS_DIR / "app_settings.json"
LEGACY_ROTOR_CONFIG_PATH = SETTINGS_DIR / "rotor_config.json"
LEGACY_FT8_CONFIG_PATH = PROJECT_ROOT / "logs" / "ft8_config.json"


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
    with _settings_lock:
        app_settings = load_app_settings()
        local_secrets = load_local_secrets()
        _validate_updates({**app_updates, **secret_updates})
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


def _validate_updates(updates: Dict[str, Any]) -> None:
    """Reject structurally unsafe settings before changing live configuration."""
    bool_keys = {
        key for key in ALLOWED_CONFIG_KEYS
        if key.endswith("_ENABLED") or key.endswith("_DEFAULT")
    } | {"FT8_AUTO_SEQUENCE", "REMOTE_CONTROL_ENABLED", "WSJTX_AUTO_LOG", "WSJTX_AUTO_ROTATE"}
    port_keys = {key for key in ALLOWED_CONFIG_KEYS if key.endswith("_PORT")}
    for key, value in updates.items():
        if key in bool_keys and not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        if key in port_keys and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535):
            raise ValueError(f"{key} must be an integer between 1 and 65535")
        if key in {"ROTOR_HOME_LAT"} and value is not None and not -90 <= float(value) <= 90:
            raise ValueError(f"{key} must be between -90 and 90")
        if key in {"ROTOR_HOME_LON"} and value is not None and not -180 <= float(value) <= 180:
            raise ValueError(f"{key} must be between -180 and 180")
        if key in SECRET_KEYS and value is not None and not isinstance(value, (str, dict, list)):
            raise ValueError(f"{key} has an invalid secret value")


def load_legacy_json(path: Path) -> Dict[str, Any]:
    """Read a legacy JSON settings file for one-time compatibility fallback."""
    return _read_json(path)
