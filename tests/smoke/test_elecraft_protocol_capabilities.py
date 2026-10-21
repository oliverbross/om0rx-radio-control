"""Focused protocol tests for coordinator-facing Elecraft capabilities."""

from typing import Any, Optional

import _bootstrap  # noqa: F401

from radio_control import elecraft as elecraft_module
from radio_control.elecraft import (
    KAT500,
    KPA500,
    exact_target_matches,
    verify_exact_target,
)


class ScriptedDevice:
    def _setup_script(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.commands: list[str | bytes] = []
        self.last_seen = None
        self.last_error = None

    def write(self, command: str | bytes) -> bool:
        self.commands.append(command)
        return True

    def query(
        self,
        command: str,
        prefix: str,
        *,
        timeout: Optional[float] = None,
        response_pattern: Optional[str] = None,
    ) -> Optional[str]:
        del prefix, timeout, response_pattern
        self.commands.append(command)
        response = self.responses.get(command)
        self.last_seen = 1_700_000_000.0 if response is not None else self.last_seen
        self.last_error = None if response is not None else f"No response to {command}"
        return response


class ScriptedKPA(ScriptedDevice, KPA500):
    def __init__(self, responses: dict[str, str]) -> None:
        KPA500.__init__(self, "KPA500", "TEST", 38400)
        self._setup_script(responses)


class ScriptedKAT(ScriptedDevice, KAT500):
    def __init__(self, responses: dict[str, str]) -> None:
        KAT500.__init__(self, "KAT500", "TEST", 38400)
        self._setup_script(responses)


def test_kpa_readback_queries_only_critical_fields() -> None:
    device = ScriptedKPA(
        {
            "^ON;": "^ON1;",
            "^OS;": "^OS0;",
            "^BN;": "^BN05;",
            "^FL;": "^FL00;",
        }
    )

    readback = device.readback()

    assert device.commands == ["^ON;", "^OS;", "^BN;", "^FL;"]
    assert readback == {
        "power": True,
        "operate": False,
        "band": "20m",
        "fault": "00",
        "observed_at": 1_700_000_000.0,
        "missing_fields": [],
        "complete": True,
        "error": None,
    }


def test_kpa_transient_explicit_off_readback_stops_after_power_query() -> None:
    device = ScriptedKPA({"^ON;": "^ON0;"})

    assert device.readback()["operate"] is False
    assert device.commands == ["^ON;"]


def test_kpa_no_response_off_state_fails_closed_as_unknown() -> None:
    device = ScriptedKPA({})

    readback = device.readback()

    assert readback["power"] is None
    assert readback["complete"] is False
    assert readback["missing_fields"] == ["power"]
    assert device.commands == ["^ON;"]


def test_kpa_band_change_policy_uses_documented_operate_preservation_command() -> None:
    device = ScriptedKPA({"^BC;": "^BC0;"})

    assert device.set_standby_on_band_change(False) is True
    assert device.read_standby_on_band_change() is False
    assert device.commands == ["^BC0;", "^BC;"]


def test_kat_tune_lifecycle_uses_documented_commands() -> None:
    device = ScriptedKAT({"TP;": "TP1;"})

    assert device.start_tune() is True
    assert device.start_tune(store=True) is True
    assert device.cancel_tune() is True
    assert device.tune_status() is True
    assert device.store_memory() is True
    assert device.store_memory(14_074) is True
    assert device.tune() is True
    assert device.store_memory(0) is False
    assert device.store_memory(True) is False
    assert device.commands == ["FTNS;", "FT;", "CT;", "TP;", "SM;", "SM 14074;", "T;"]


def test_kat_selective_frequency_memory_clear_requires_exact_scope() -> None:
    device = ScriptedKAT({})

    assert device.clear_frequency_memories("40m", 2) is True
    assert device.clear_frequency_memories("20M", 0) is True
    assert device.clear_frequency_memories("not-a-band", 2) is False
    assert device.clear_frequency_memories("40m", 4) is False
    assert device.clear_frequency_memories("40m", True) is False
    assert device.commands == ["EM032;", "EM050;"]


def test_kat_readback_is_focused_on_coordinator_critical_fields(monkeypatch: Any) -> None:
    monkeypatch.setattr(elecraft_module.time, "sleep", lambda _seconds: None)
    device = ScriptedKAT(
        {
            "PS;": "PS1;",
            "MD;": "MDA;",
            "AN;": "AN2;",
            "BN;": "BN03;",
            "F;": "F 7074;",
            "TP;": "TP0;",
            "FLT;": "FLT0;",
            "BYP;": "BYPN;",
            "AMPI;": "AMPI0;",
        }
    )

    readback = device.readback()

    assert device.commands == [";;;", "PS;", "MD;", "AN;", "BN;", "F;", "TP;", "FLT;", "BYP;", "AMPI;"]
    assert readback["complete"] is True
    assert readback["missing_fields"] == []
    assert readback["amp_key_interrupted"] is False
    assert "capacitor_mask" not in readback


def test_kat_remote_telemetry_includes_critical_readback(monkeypatch: Any) -> None:
    monkeypatch.setattr(elecraft_module.time, "sleep", lambda _seconds: None)
    device = ScriptedKAT(
        {
            "PS;": "PS1;",
            "MD;": "MDM;",
            "AN;": "AN2;",
            "BN;": "BN04;",
            "F;": "F 10136;",
            "TP;": "TP0;",
            "FLT;": "FLT0;",
            "BYP;": "BYPN;",
            "AMPI;": "AMPI0;",
            "C;": "C06;",
            "L;": "L20;",
            "SIDE;": "SIDEA;",
            "VFWD;": "VFWD 2048;",
            "VRFL;": "VRFL 128;",
            "VSWR;": "VSWR 1.27;",
            "VSWRB;": "VSWRB 2.11;",
            "FX;": "FX 10136;",
            "FY;": "FY 10120-10139;",
            "SN;": "SN 12345;",
            "RV;": "RV02.12;",
        }
    )

    readback = device.remote_telemetry()

    assert readback["power"] is True
    assert readback["mode"] == "manual"
    assert readback["antenna"] == 2
    assert readback["band"] == "30m"
    assert readback["frequency_khz"] == 10136
    assert readback["tuning"] is False
    assert readback["fault"] == "0"
    assert readback["bypass"] is False
    assert readback["amp_key_interrupted"] is False
    assert readback["capacitor_mask"] == "06"
    assert readback["inductor_mask"] == "20"
    assert readback["network_side"] == "antenna"
    assert readback["forward_adc"] == 2048
    assert readback["reflected_adc"] == 128
    assert readback["swr"] == 1.27
    assert readback["bypass_swr"] == 2.11
    assert readback["frequency_source_khz"] == 10136
    assert readback["frequency_range_khz"] == [10120, 10139]
    assert readback["serial_number"] == "12345"
    assert readback["firmware"] == "02.12"
    assert readback["missing_fields"] == []
    assert readback["telemetry_missing"] == []
    assert readback["complete"] is True


def test_exact_verification_rejects_missing_mismatched_and_coerced_values() -> None:
    actual = {"power": True, "antenna": 2, "band": "20m"}

    assert exact_target_matches(actual, {"power": True, "antenna": 2}) is True
    result = verify_exact_target(
        actual,
        {"power": 1, "antenna": 1, "mode": "manual"},
    )

    assert result["verified"] is False
    assert [item["field"] for item in result["mismatches"]] == [
        "power",
        "antenna",
        "mode",
    ]
    assert result["mismatches"][0]["actual"] is True
    assert result["mismatches"][2]["missing_from"] == ["actual"]


def test_destructive_kat_maintenance_is_not_exposed() -> None:
    for method_name in ("reset", "factory_reset", "erase_memory", "firmware_write", "raw_command"):
        assert not hasattr(KAT500, method_name)

    # Selective per-band memory clearing is the only exposed erase-like
    # operation; there is no EEINIT/configuration-reset capability.
    assert hasattr(KAT500, "clear_frequency_memories")
