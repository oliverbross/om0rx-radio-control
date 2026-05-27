"""Smoke tests for rotator bearing resolution and command safety."""

import asyncio

import _bootstrap  # noqa: F401

from radio_control import config
from radio_control.rotor_api import RotorController
from radio_control.rotor_math import (
    calculate_bearing_for_station,
    grid_to_latlon,
    latlon_to_grid,
)
from services.rotator import RotatorService
from services.rotator_resolution import resolve_rotor_target


def test_maidenhead_validation_rejects_impossible_grids():
    for grid in ("ZZ99", "JN88YZ"):
        try:
            grid_to_latlon(grid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{grid} should be rejected")


def test_coordinate_fallback_accepts_numeric_strings_and_bounds_grid_edges():
    bearing = calculate_bearing_for_station(
        48.17,
        17.08,
        station_lat="49.0",
        station_lon="18.0",
    )
    assert bearing is not None

    assert latlon_to_grid(90, 180, precision=2) == "RR"


def test_azimuth_normalization_wraps_360_to_north():
    rotor = RotorController("127.0.0.1", 4001)
    assert rotor.clamp_azimuth(360) == 0
    assert rotor.clamp_azimuth(721) == 1
    assert rotor.clamp_azimuth(-1) == 359


def test_resolver_prioritizes_station_grid_over_cty_entity_data():
    result = resolve_rotor_target(
        {
            "callsign": "K1ABC",
            "frequency_khz": 14074,
            "qrz_grid": "CN87",
            "gridsquare": "JN88TQ",
            "latitude": 48.17,
            "longitude": 17.08,
            "location_source": "cty_prefix",
        },
        48.17,
        17.08,
        {"20m": True},
    )

    assert result["ok"] is True
    assert result["source"] == "qrz_grid"
    assert result["confidence"] == "high"
    assert result["auto_allowed"] is True


def test_resolver_reports_approximate_cty_target_without_auto_permission():
    result = resolve_rotor_target(
        {
            "callsign": "RA1ABC",
            "frequency_khz": 14074,
            "gridsquare": "KO59",
            "latitude": 59.9,
            "longitude": 30.3,
            "location_source": "cty_prefix",
        },
        48.17,
        17.08,
        {"20m": True},
    )

    assert result["ok"] is True
    assert result["source"] == "cty_grid"
    assert result["confidence"] == "low"
    assert result["approximate"] is True
    assert result["auto_allowed"] is False


def test_empty_band_config_does_not_block_known_band():
    result = resolve_rotor_target(
        {"frequency_khz": 14074, "qrz_grid": "CN87"},
        48.17,
        17.08,
        {},
    )

    assert result["band"] == "20m"
    assert result["band_enabled"] is True


def test_disabled_band_blocks_auto_permission_but_keeps_bearing():
    result = resolve_rotor_target(
        {"frequency_khz": 14074, "qrz_grid": "CN87"},
        48.17,
        17.08,
        {"20m": False},
    )

    assert result["ok"] is True
    assert result["band_enabled"] is False
    assert result["auto_allowed"] is False
    assert result["bearing"] is not None


class FakeRotor:
    def __init__(self):
        self.targets = []

    async def goto_azimuth(self, azimuth):
        self.targets.append(azimuth)
        return {"ok": True, "target": azimuth}


def test_auto_goto_moves_only_when_resolution_is_auto_allowed():
    original = {
        "ROTOR_AUTO_ENABLED": getattr(config, "ROTOR_AUTO_ENABLED", False),
        "ROTOR_HOME_LAT": getattr(config, "ROTOR_HOME_LAT", None),
        "ROTOR_HOME_LON": getattr(config, "ROTOR_HOME_LON", None),
        "ROTOR_BANDS": getattr(config, "ROTOR_BANDS", None),
    }

    try:
        config.ROTOR_AUTO_ENABLED = True
        config.ROTOR_HOME_LAT = 48.17
        config.ROTOR_HOME_LON = 17.08
        config.ROTOR_BANDS = {"20m": True}

        service = RotatorService()
        fake_rotor = FakeRotor()
        service.rotor = fake_rotor

        approximate = asyncio.run(service.rotor_auto_goto({
            "callsign": "RA1ABC",
            "frequency_khz": 14074,
            "gridsquare": "KO59",
            "location_source": "cty_prefix",
        }))
        assert approximate["ok"] is False
        assert fake_rotor.targets == []

        precise = asyncio.run(service.rotor_auto_goto({
            "callsign": "K1ABC",
            "frequency_khz": 14074,
            "qrz_grid": "CN87",
        }))
        assert precise["ok"] is True
        assert len(fake_rotor.targets) == 1
    finally:
        for key, value in original.items():
            setattr(config, key, value)
