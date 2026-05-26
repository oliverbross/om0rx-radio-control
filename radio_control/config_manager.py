# config_manager.py - Configuration management utilities

import importlib
from radio_control.settings_store import public_config_from_module, save_config_updates


def _config_path():
    """Resolve the JSON settings path used for persisted app settings."""
    from radio_control.settings_store import APP_SETTINGS_PATH

    return str(APP_SETTINGS_PATH)


def _read_config_values():
    """Read all configuration values from the active config module."""
    from radio_control import config as _cfg

    return public_config_from_module(_cfg)



def _update_config_file(updates: dict):
    """Persist configuration with the JSON settings store."""
    result = save_config_updates(updates)

    from radio_control import config as _cfg

    importlib.reload(_cfg)
    return result["app_settings_path"]
