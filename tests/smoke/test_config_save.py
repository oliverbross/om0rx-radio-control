#!/usr/bin/env python3
"""Smoke tests for JSON-backed config saves."""

from pathlib import Path
import json

import _bootstrap  # noqa: F401
import pytest
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
            "WINKEYER_PORT": "",
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


def test_disabled_winkeyer_allows_blank_serial_port(tmp_path, monkeypatch):
    app_settings_path = tmp_path / "app_settings.json"
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", app_settings_path)
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", tmp_path)

    save_config_updates({"WINKEYER_ENABLED": False, "WINKEYER_PORT": ""})

    saved = settings_store.load_app_settings()
    assert saved["WINKEYER_ENABLED"] is False
    assert saved["WINKEYER_PORT"] == ""


def test_enabled_winkeyer_requires_serial_port(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", tmp_path / "app_settings.json")
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", tmp_path)

    try:
        save_config_updates({"WINKEYER_ENABLED": True, "WINKEYER_PORT": ""})
    except ValueError as exc:
        assert str(exc) == "WINKEYER_PORT is required when WinKeyer is enabled"
    else:
        raise AssertionError("Enabled WinKeyer accepted an empty serial port")


def test_enabled_winkeyer_accepts_named_serial_port(tmp_path, monkeypatch):
    app_settings_path = tmp_path / "app_settings.json"
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", app_settings_path)
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", tmp_path)

    save_config_updates({"WINKEYER_ENABLED": True, "WINKEYER_PORT": "COM11"})

    saved = settings_store.load_app_settings()
    assert saved["WINKEYER_ENABLED"] is True
    assert saved["WINKEYER_PORT"] == "COM11"


def test_elecraft_serial_settings_and_antenna_policy_are_saved(tmp_path, monkeypatch):
    app_settings_path = tmp_path / "app_settings.json"
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", app_settings_path)
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", tmp_path)

    save_config_updates(
        {
            "KPA500_ENABLED": True,
            "KPA500_PORT": "COM16",
            "KPA500_BAUDRATE": 38400,
            "DIGITAL_KPA_POLICY": "standby",
            "KAT500_ENABLED": True,
            "KAT500_PORT": "COM14",
            "KAT500_BAUDRATE": 38400,
            "ELECRAFT_FOLLOW_RADIO": True,
            "KAT500_ANTENNA_POLICY": {"160m": 2, "20m": 1},
            "STATION_AMPLIFIER_DRIVE_W": {"160m": 25, "20m": 18},
            "STATION_BAREFOOT_DRIVE_W": {"160m": 30, "20m": 80},
            "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS": ["40m"],
            "STATION_DIGITAL_AMPLIFIER_DRIVE_W": {"40m": 15, "20m": 20},
        }
    )

    saved = settings_store.load_app_settings()
    assert saved["KPA500_PORT"] == "COM16"
    assert saved["DIGITAL_KPA_POLICY"] == "standby"
    assert saved["KAT500_PORT"] == "COM14"
    assert saved["ELECRAFT_FOLLOW_RADIO"] is True
    assert saved["KAT500_ANTENNA_POLICY"] == {"160m": 2, "20m": 1}
    assert saved["STATION_AMPLIFIER_DRIVE_W"] == {"160m": 25, "20m": 18}
    assert saved["STATION_BAREFOOT_DRIVE_W"] == {"160m": 30, "20m": 80}
    assert saved["STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS"] == ["40m"]
    assert saved["STATION_DIGITAL_AMPLIFIER_DRIVE_W"] == {"40m": 15, "20m": 20}


def test_amplifier_drive_policy_rejects_invalid_band_or_power(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", tmp_path / "app_settings.json")
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    with pytest.raises(ValueError, match="map supported amateur bands"):
        save_config_updates({"STATION_AMPLIFIER_DRIVE_W": {"20m": 0}})
    with pytest.raises(ValueError, match="map supported amateur bands"):
        save_config_updates({"STATION_AMPLIFIER_DRIVE_W": {"2m": 25}})
    with pytest.raises(ValueError, match="map supported amateur bands"):
        save_config_updates({"STATION_BAREFOOT_DRIVE_W": {"20m": 101}})
    with pytest.raises(ValueError, match="map supported amateur bands"):
        save_config_updates({"STATION_DIGITAL_AMPLIFIER_DRIVE_W": {"40m": 0}})


def test_amplifier_policy_canonicalizes_band_keys_and_skips_unchanged_writes(tmp_path, monkeypatch):
    app_settings_path = tmp_path / "app_settings.json"
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", app_settings_path)
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")

    first = save_config_updates({
        "STATION_AMPLIFIER_ALLOWED_BANDS": [" 20M", "40m", "20m"],
        "STATION_AMPLIFIER_DRIVE_W": {"20M": 27},
        "STATION_BAREFOOT_DRIVE_W": {" 20m ": 80},
    })
    second = save_config_updates({
        "STATION_AMPLIFIER_ALLOWED_BANDS": ["20m", "40m"],
        "STATION_AMPLIFIER_DRIVE_W": {"20m": 27},
        "STATION_BAREFOOT_DRIVE_W": {"20m": 80},
    })

    saved = settings_store.load_app_settings()
    assert saved["STATION_AMPLIFIER_ALLOWED_BANDS"] == ["40m", "20m"]
    assert saved["STATION_AMPLIFIER_DRIVE_W"] == {"20m": 27}
    assert saved["STATION_BAREFOOT_DRIVE_W"] == {"20m": 80}
    assert set(first["updated_keys"]) == {
        "STATION_AMPLIFIER_ALLOWED_BANDS",
        "STATION_AMPLIFIER_DRIVE_W",
        "STATION_BAREFOOT_DRIVE_W",
    }
    assert second["updated_keys"] == []


def test_elecraft_follow_radio_must_be_boolean(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", tmp_path / "app_settings.json")
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", tmp_path)

    try:
        save_config_updates({"ELECRAFT_FOLLOW_RADIO": "yes"})
    except ValueError as exc:
        assert str(exc) == "ELECRAFT_FOLLOW_RADIO must be a boolean"
    else:
        raise AssertionError("Elecraft follow-radio accepted a non-boolean value")


def test_digital_kpa_policy_rejects_implicit_or_unknown_states(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", tmp_path / "app_settings.json")
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    with pytest.raises(ValueError, match="operate or standby"):
        save_config_updates({"DIGITAL_KPA_POLICY": "auto"})


def test_partial_config_save_preserves_protected_commissioning_latch(tmp_path, monkeypatch):
    app_settings_path = tmp_path / "app_settings.json"
    app_settings_path.write_text(
        json.dumps(
            {
                "STATION_COORDINATOR_COMMISSIONED": True,
                "ROTOR_BANDS": {"20m": True},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", app_settings_path)
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", tmp_path)

    result = save_config_updates({"ROTOR_BANDS": {"20m": True, "40m": False}})

    saved = settings_store.load_app_settings()
    assert result["updated_keys"] == ["ROTOR_BANDS"]
    assert saved["STATION_COORDINATOR_COMMISSIONED"] is True
    assert saved["ROTOR_BANDS"] == {"20m": True, "40m": False}


def test_generic_config_save_rejects_commissioning_latch_mutation(tmp_path, monkeypatch):
    app_settings_path = tmp_path / "app_settings.json"
    app_settings_path.write_text(
        json.dumps({"STATION_COORDINATOR_COMMISSIONED": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", app_settings_path)
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", tmp_path)

    result = save_config_updates({"STATION_COORDINATOR_COMMISSIONED": False})

    assert result["updated_keys"] == []
    assert result["rejected_keys"] == ["STATION_COORDINATOR_COMMISSIONED"]
    assert settings_store.load_app_settings()["STATION_COORDINATOR_COMMISSIONED"] is True


def test_protected_commissioning_writer_is_narrow_and_audited(tmp_path, monkeypatch):
    app_settings_path = tmp_path / "app_settings.json"
    audit_path = tmp_path / "station_commissioning_audit.jsonl"
    app_settings_path.write_text(
        json.dumps({"STATION_COORDINATOR_COMMISSIONED": False, "ROTOR_BANDS": {"20m": True}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "APP_SETTINGS_PATH", app_settings_path)
    monkeypatch.setattr(settings_store, "LOCAL_SECRETS_PATH", tmp_path / "local_secrets.json")
    monkeypatch.setattr(settings_store, "COMMISSIONING_AUDIT_PATH", audit_path)
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", tmp_path)

    audit = settings_store.save_station_commissioning_latch(
        True,
        reason="supervised commissioning regression",
    )

    saved = settings_store.load_app_settings()
    assert saved == {
        "ROTOR_BANDS": {"20m": True},
        "STATION_COORDINATOR_COMMISSIONED": True,
    }
    assert audit["previous"] is False
    assert audit["value"] is True
    assert audit["changed"] is True
    persisted_audit = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert persisted_audit["reason"] == "supervised commissioning regression"
