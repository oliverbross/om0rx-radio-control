#!/usr/bin/env python3
"""Smoke test that config saves do not modify Python source files."""

from pathlib import Path
import importlib
import os

import _bootstrap  # noqa: F401
from radio_control import config
from radio_control.settings_store import (
    APP_SETTINGS_PATH,
    LOCAL_SECRETS_PATH,
    save_config_updates,
)


project_root = Path(__file__).resolve().parents[2]
config_path = project_root / "radio_control" / "config.py"


def read_text_if_exists(path: Path):
    return path.read_text(encoding="utf-8") if path.exists() else None


original_config_text = config_path.read_text(encoding="utf-8")
original_app_settings = read_text_if_exists(APP_SETTINGS_PATH)
original_local_secrets = read_text_if_exists(LOCAL_SECRETS_PATH)
original_winkeyer_enabled = getattr(config, "WINKEYER_ENABLED", None)
original_qrz_username = getattr(config, "QRZ_USERNAME", None)

try:
    result = save_config_updates(
        {
            "WINKEYER_ENABLED": False,
            "QRZ_USERNAME": "SMOKE_TEST_USER",
            "UNSUPPORTED_TEST_KEY": "ignored",
        }
    )

    assert config_path.read_text(encoding="utf-8") == original_config_text
    assert "WINKEYER_ENABLED" in result["app_settings_keys"]
    assert "QRZ_USERNAME" in result["local_secret_keys"]
    assert "UNSUPPORTED_TEST_KEY" in result["rejected_keys"]

    if "WINKEYER_ENABLED" not in os.environ:
        importlib.reload(config)
        assert config.WINKEYER_ENABLED is False
    if "QRZ_USERNAME" not in os.environ:
        importlib.reload(config)
        assert config.QRZ_USERNAME == "SMOKE_TEST_USER"

    print("✅ Config save uses JSON settings and leaves radio_control/config.py unchanged")
finally:
    if original_app_settings is None:
        APP_SETTINGS_PATH.unlink(missing_ok=True)
    else:
        APP_SETTINGS_PATH.write_text(original_app_settings, encoding="utf-8")

    if original_local_secrets is None:
        LOCAL_SECRETS_PATH.unlink(missing_ok=True)
    else:
        LOCAL_SECRETS_PATH.write_text(original_local_secrets, encoding="utf-8")

    if original_winkeyer_enabled is not None:
        setattr(config, "WINKEYER_ENABLED", original_winkeyer_enabled)
    if original_qrz_username is not None:
        setattr(config, "QRZ_USERNAME", original_qrz_username)
