"""Spot classification rules for call and DXCC worked/confirmed status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


TRUE_VALUES = {"1", "Y", "YES", "TRUE", "T", "CONFIRMED", "WORKED"}


@dataclass(frozen=True)
class DxccDisplayStatus:
    """Frontend DXCC status plus optional priority tag."""

    status: str
    tag: str | None = None


def bool_value(value: Any) -> bool:
    """Normalize Wavelog/DuckDB truthy values to bool."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().upper() in TRUE_VALUES


def lookup_bool(data: Mapping[str, Any], *keys: str, default: bool = False) -> bool:
    """Read the first present boolean-like key from a Wavelog lookup payload."""
    for key in keys:
        if key in data and data[key] is not None:
            return bool_value(data[key])
    return default


def call_overall_from_lookup(data: Mapping[str, Any]) -> tuple[bool, bool]:
    """Extract call worked/confirmed flags from Wavelog private_lookup."""
    return (
        lookup_bool(data, "call_worked"),
        lookup_bool(data, "call_confirmed"),
    )


def call_bandmode_from_lookup(data: Mapping[str, Any]) -> tuple[bool, bool, bool]:
    """Extract call band/mode flags from Wavelog private_lookup."""
    band_worked = lookup_bool(data, "call_worked_band")
    bandmode_worked = lookup_bool(data, "call_worked_band_mode")
    bandmode_confirmed = lookup_bool(data, "call_confirmed_band_mode")

    new_band = not band_worked
    new_mode = band_worked and not bandmode_worked
    return new_band, new_mode, bandmode_confirmed


def dxcc_confirmation_from_lookup(data: Mapping[str, Any]) -> tuple[bool, bool, bool]:
    """Extract DXCC confirmation flags from Wavelog private_lookup.

    Wavelog private_lookup documents call worked fields, but DXCC fields are
    confirmation-only. True DXCC worked status must come from the synced QSO log.
    """
    return (
        lookup_bool(data, "dxcc_confirmed"),
        lookup_bool(data, "dxcc_confirmed_on_band"),
        lookup_bool(data, "dxcc_confirmed_on_band_mode"),
    )


def classify_call_status(
    worked: bool,
    new_band: bool,
    new_mode: bool,
    bandmode_confirmed: bool,
) -> str:
    """Return the display status for a callsign."""
    if not worked:
        return "New Call"
    if bandmode_confirmed:
        return "Confirmed"
    if new_band and new_mode:
        return "New Band+Mode"
    if new_band:
        return "New Band"
    if new_mode:
        return "New Mode"
    return "Worked"


def classify_dxcc_status(
    worked: bool,
    confirmed: bool,
    new_band: bool,
    new_mode: bool,
    bandmode_confirmed: bool,
) -> DxccDisplayStatus:
    """Return the display status and priority tag for a DXCC entity."""
    if not worked:
        return DxccDisplayStatus("ATNO", "ATNO")
    if bandmode_confirmed:
        return DxccDisplayStatus("Confirmed")

    prefix = "C" if confirmed else "W"
    if new_band and new_mode:
        return DxccDisplayStatus(f"{prefix}/New Band+Mode", "New band+mode")
    if new_band:
        return DxccDisplayStatus(f"{prefix}/New Band", "New band")
    if new_mode:
        return DxccDisplayStatus(f"{prefix}/New Mode", "New mode")

    return DxccDisplayStatus("Worked", "Need LoTW")
