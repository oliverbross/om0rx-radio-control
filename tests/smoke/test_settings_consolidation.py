#!/usr/bin/env python3
"""Smoke test consolidated settings persistence for rotor and FT8 config."""

from pathlib import Path

import _bootstrap  # noqa: F401
from fastapi.testclient import TestClient

import backend.main
import services.digital_engine as digital_engine
from radio_control.settings_store import APP_SETTINGS_PATH, LEGACY_FT8_CONFIG_PATH, LEGACY_ROTOR_CONFIG_PATH


def read_text(path: Path):
    return path.read_text(encoding="utf-8") if path.exists() else None


original_app_settings = read_text(APP_SETTINGS_PATH)
original_legacy_rotor = read_text(LEGACY_ROTOR_CONFIG_PATH)
original_legacy_ft8 = read_text(LEGACY_FT8_CONFIG_PATH)
original_selected_provider = digital_engine.selected_provider

try:
    # This legacy persistence smoke exercises the WSJT-Z-owned FT8 config
    # endpoint.  Never borrow or rewrite the operator's live provider choice.
    digital_engine.selected_provider = lambda: "wsjtz"
    backend.main.register_all_services()
    client = TestClient(backend.main.app)

    rotor_payload = {
        "home_grid": "JN88TQ",
        "home_lat": 48.17,
        "home_lon": 17.08,
        "bands": {"20m": True, "15m": True, "10m": True},
        "auto_enabled": True,
    }
    rotor_response = client.post("/api/rotor/auto/config", json=rotor_payload)
    assert rotor_response.status_code == 200, rotor_response.text
    assert rotor_response.json()["ok"] is True

    ft8_payload = {
        "mode": "FT8",
        "mycall": "OM0RX",
        "mygrid": "JN88",
        "auto_sequence": False,
        "tx_enabled": False,
        "networkServer": "192.168.0.199:4992",
        "pttMethod": "CAT",
        "audioInput": "flexradio",
        "audioOutput": "flexradio",
        "sampleRate": 48000,
        "waterfallHeight": 100,
        "useFlexRadioAudio": True,
    }
    ft8_response = client.post("/api/ft8/config", json=ft8_payload)
    assert ft8_response.status_code == 200, ft8_response.text
    assert ft8_response.json()["status"] == "updated"

    saved_settings = APP_SETTINGS_PATH.read_text(encoding="utf-8")
    assert '"ROTOR_HOME_GRID": "JN88TQ"' in saved_settings
    assert '"FT8_AUDIO_INPUT": "flexradio"' in saved_settings

    assert read_text(LEGACY_ROTOR_CONFIG_PATH) == original_legacy_rotor
    assert read_text(LEGACY_FT8_CONFIG_PATH) == original_legacy_ft8

    print("✅ Rotor and FT8 config persist through settings/app_settings.json")
finally:
    digital_engine.selected_provider = original_selected_provider
    if original_app_settings is None:
        APP_SETTINGS_PATH.unlink(missing_ok=True)
    else:
        APP_SETTINGS_PATH.write_text(original_app_settings, encoding="utf-8")
