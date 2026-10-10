from types import SimpleNamespace

from radio_control.station_policy import is_digital_radio_mode, resolve_amplifier_policy


def _settings():
    return SimpleNamespace(
        DIGITAL_KPA_POLICY="operate",
        STATION_AMPLIFIER_ALLOWED_BANDS=["20m", "40m"],
        STATION_AMPLIFIER_DRIVE_W={"20m": 25, "40m": 25},
        STATION_BAREFOOT_DRIVE_W={"20m": 65, "40m": 100},
        STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS=["40m"],
        STATION_DIGITAL_AMPLIFIER_DRIVE_W={"20m": 10, "40m": 15},
    )


def test_voice_and_cw_modes_keep_the_standard_band_policy():
    source = _settings()

    for mode in ("USB", "LSB", "CW", "CWU", "CWL", "FM", "NFM", "AM", "SAM"):
        policy = resolve_amplifier_policy(source, "20m", mode)
        assert policy.digital_mode is False
        assert policy.amplifier_allowed is True
        assert policy.amplifier_drive_w == 25
        assert policy.barefoot_drive_w == 65


def test_other_known_modes_use_independent_digital_allow_and_drive():
    source = _settings()

    assert is_digital_radio_mode("DIGU") is True
    assert is_digital_radio_mode("RTTY") is True
    assert is_digital_radio_mode("") is False

    barefoot = resolve_amplifier_policy(source, "20m", "DIGU")
    amplified = resolve_amplifier_policy(source, "40m", "DIGL")

    assert barefoot.amplifier_allowed is False
    assert barefoot.effective_mode == "standby"
    assert barefoot.amplifier_drive_w == 10
    assert barefoot.active_drive_w == 65
    assert barefoot.barefoot_drive_w == 65
    assert amplified.amplifier_allowed is True
    assert amplified.effective_mode == "operate"
    assert amplified.active_drive_w == 15


def test_digital_master_standby_overrides_the_per_band_allowlist():
    source = _settings()
    source.DIGITAL_KPA_POLICY = "standby"

    policy = resolve_amplifier_policy(source, "40m", "DIGU")

    assert policy.configured_mode == "standby"
    assert policy.amplifier_allowed is False
    assert policy.effective_mode == "standby"
    assert policy.amplifier_drive_w == 15
    assert policy.active_drive_w == 100
