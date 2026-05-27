#!/usr/bin/env python3
"""Smoke tests for JSON-backed config saves."""

from pathlib import Path

import _bootstrap  # noqa: F401
from radio_control import settings_store
from radio_control.settings_store import save_config_updates


project_root = Path(__file__).resolve().parents[2]
config_path = project_root / "radio_control" / "config.py"


def test_config_save_uses_json_settings_without_touching_python_config(tmp_path, monkeypatch):
    app_settings_path = tmp_path / "app_settings.json"
    local_secrets_path = tmp_path / "local_secrets.json"
    original_config_text = config_path.read_text(encoding="utf-8")

    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", app_settings_path)
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", local_secrets_path)
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", tmp_path)

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
    assert app_settings_path.exists()
    assert local_secrets_path.exists()
