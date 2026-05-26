"""
JSON-backed runtime settings for station-local configuration.

The Python config module remains the defaults layer. UI-edited non-secret values
are stored in settings/app_settings.json, while credentials and secret-bearing
values are stored in settings/local_secrets.json, which is ignored by Git.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple


logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_DIR = PROJECT_ROOT / "settings"
APP_SETTINGS_PATH = SETTINGS_DIR / "app_settings.json"
LOCAL_SECRETS_PATH = SETTINGS_DIR / "local_secrets.json"


SECRET_KEYS = {
    "DB_HOST",
    "DB_NAME",
    "DB_USER",
    "DB_PASS",
    "CLUSTER_HOST",
    "CLUSTER_USER",
    "CLUSTER_PASS",
    "CLUSTERS",
    "WAVELOG_API_URL",
    "WAVELOG_API_KEY",
    "QRZ_USERNAME",
    "QRZ_PASSWORD",
}


ALLOWED_CONFIG_KEYS = {
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
    "DB_HOST",
    "DB_NAME",
    "DB_PASS",
    "DB_PORT",
    "DB_USER",
    "BACKEND_HOST",
    "BACKEND_PORT",
    "FLEX_ENABLED_DEFAULT",
    "FLEX_TCP_HOST",
    "FLEX_TCP_PORT",
    "FT8_AUDIO_INPUT",
    "FT8_AUDIO_OUTPUT",
    "FT8_AUTO_SEQUENCE",
    "FT8_ENABLED",
    "FT8_MODE",
    "FT8_MYCALL",
    "FT8_MYGRID",
    "FT8_NETWORK_SERVER",
    "FT8_PTT_METHOD",
    "FT8_SAMPLE_RATE",
    "FT8_TX_ENABLED",
    "FT8_USE_FLEXRADIO_AUDIO",
    "FT8_WATERFALL_HEIGHT",
    "LOG_LEVEL",
    "MY_STATION",
    "QRZ_ENABLED",
    "QRZ_PASSWORD",
    "QRZ_USERNAME",
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
    "WSJTX_UDP_MULTICAST",
    "WSJTX_UDP_PORT",
    "WSJTX_WS_PORT",
}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        logger.warning("Ignoring invalid JSON settings file %s: %s", path, exc)
        return {}

    if not isinstance(data, dict):
        logger.warning("Ignoring non-object JSON settings file %s", path)
        return {}

    return data


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_app_settings() -> Dict[str, Any]:
    """Return non-secret UI-edited settings."""
    return _read_json(APP_SETTINGS_PATH)


def load_local_secrets() -> Dict[str, Any]:
    """Return ignored local secret settings."""
    return _read_json(LOCAL_SECRETS_PATH)


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
            secret_updates[key] = value
        else:
            app_updates[key] = value

    return app_updates, secret_updates, rejected


def save_config_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Persist allowed config updates without modifying Python source files."""
    app_updates, secret_updates, rejected = split_config_updates(updates)

    app_settings = load_app_settings()
    local_secrets = load_local_secrets()

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
    return {
        key: getattr(config_module, key)
        for key in selected_keys
        if hasattr(config_module, key)
    }
