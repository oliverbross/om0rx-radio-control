"""Canonical per-band amplifier and FLEX drive policy.

This module is deliberately free of device I/O so the coordinator, digital
permit service, configuration API, and tests all resolve exactly the same
effective station policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


SUPPORTED_STATION_BANDS = (
    "160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m",
)
SUPPORTED_STATION_BAND_SET = frozenset(SUPPORTED_STATION_BANDS)
DEFAULT_AMPLIFIER_DRIVE_W = 25
DEFAULT_BAREFOOT_DRIVE_W = 25
STANDARD_RADIO_MODES = frozenset({
    "AM", "SAM", "FM", "NFM", "USB", "LSB", "CW", "CWU", "CWL",
})


def canonical_band(value: Any) -> str:
    """Return a supported lower-case band name, or an empty string."""
    band = str(value or "").strip().lower()
    return band if band in SUPPORTED_STATION_BAND_SET else ""


def canonical_band_list(values: Iterable[Any] | None) -> list[str]:
    """Normalize, de-duplicate, and order a station band selection."""
    selected = {canonical_band(value) for value in values or ()}
    selected.discard("")
    return [band for band in SUPPORTED_STATION_BANDS if band in selected]


def canonical_drive_map(values: Mapping[Any, Any] | None) -> dict[str, int]:
    """Normalize a partial band-to-watts map without inventing missing keys."""
    result: dict[str, int] = {}
    for raw_band, raw_power in dict(values or {}).items():
        band = canonical_band(raw_band)
        if not band or isinstance(raw_power, bool):
            continue
        try:
            power = int(raw_power)
        except (TypeError, ValueError):
            continue
        if 1 <= power <= 100:
            result[band] = power
    return {band: result[band] for band in SUPPORTED_STATION_BANDS if band in result}


def _configured_drive(source: Any, key: str, band: str, fallback: int) -> int:
    values = canonical_drive_map(getattr(source, key, {}) or {})
    return int(values.get(band, fallback))


def is_digital_radio_mode(value: Any) -> bool:
    """Return whether a known FLEX mode should use the digital RF profile.

    FLEX voice/CW modes retain the original station policy. Every other
    non-empty mode (including DIGU, DIGL, and RTTY) is treated as digital.
    An unavailable mode stays on the established standard profile rather than
    changing amplifier state from incomplete telemetry.
    """
    mode = str(value or "").strip().upper()
    return bool(mode and mode not in STANDARD_RADIO_MODES)


@dataclass(frozen=True)
class AmplifierBandPolicy:
    band: str
    radio_mode: str
    digital_mode: bool
    profile: str
    allowed_bands: tuple[str, ...]
    inhibitors: tuple[str, ...]
    configured_mode: str
    effective_mode: str
    amplifier_allowed: bool
    amplifier_drive_w: int
    barefoot_drive_w: int

    @property
    def active_drive_w(self) -> int:
        return self.amplifier_drive_w if self.effective_mode == "operate" else self.barefoot_drive_w

    def as_dict(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "radio_mode": self.radio_mode,
            "digital_mode": self.digital_mode,
            "profile": self.profile,
            "allowed_bands": list(self.allowed_bands),
            "inhibitors": list(self.inhibitors),
            "configured_kpa500": self.configured_mode,
            "kpa500": self.effective_mode,
            "amplifier_allowed": self.amplifier_allowed,
            "amplifier_drive_w": self.amplifier_drive_w,
            "barefoot_drive_w": self.barefoot_drive_w,
            "active_drive_w": self.active_drive_w,
        }


def resolve_amplifier_policy(
    source: Any,
    band: Any,
    radio_mode: Any = None,
) -> AmplifierBandPolicy:
    """Resolve the authoritative, mode-aware KPA and FLEX drive policy."""
    normalized_band = canonical_band(band)
    normalized_mode = str(radio_mode or "").strip().upper()
    digital_mode = is_digital_radio_mode(normalized_mode)
    standard_allowed_bands = canonical_band_list(
        getattr(source, "STATION_AMPLIFIER_ALLOWED_BANDS", ()) or ()
    )
    master_digital_mode = str(
        getattr(source, "DIGITAL_KPA_POLICY", "operate") or ""
    ).strip().lower()
    if master_digital_mode not in {"operate", "standby"}:
        master_digital_mode = "standby"

    if digital_mode:
        digital_allowed_bands = set(canonical_band_list(
            getattr(
                source,
                "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS",
                standard_allowed_bands,
            ) or ()
        ))
        configured_mode = master_digital_mode
        allowed_bands = digital_allowed_bands if configured_mode == "operate" else set()
    else:
        configured_mode = "operate"
        allowed_bands = set(standard_allowed_bands)
    amplifier_allowed = bool(normalized_band and normalized_band in allowed_bands)
    inhibitors: list[str] = []
    if not normalized_band:
        inhibitors.append("band-unresolved")
    elif configured_mode != "operate":
        inhibitors.append("digital-amplifier-policy-standby")
    elif normalized_band not in allowed_bands:
        inhibitors.append("band-not-in-active-amplifier-allow-list")
    effective_mode = (
        "operate" if configured_mode == "operate" and amplifier_allowed else "standby"
    )
    amplifier_drive_w = _configured_drive(
        source,
        "STATION_AMPLIFIER_DRIVE_W",
        normalized_band,
        DEFAULT_AMPLIFIER_DRIVE_W,
    )
    barefoot_drive_w = _configured_drive(
        source,
        "STATION_BAREFOOT_DRIVE_W",
        normalized_band,
        DEFAULT_BAREFOOT_DRIVE_W,
    )
    if digital_mode:
        digital_drive_w = _configured_drive(
            source,
            "STATION_DIGITAL_AMPLIFIER_DRIVE_W",
            normalized_band,
            amplifier_drive_w,
        )
        # Keep the existing barefoot setting when digital PA operation is not
        # allowed; this field is specifically the PA drive for digital modes.
        amplifier_drive_w = digital_drive_w
    return AmplifierBandPolicy(
        band=normalized_band,
        radio_mode=normalized_mode,
        digital_mode=digital_mode,
        profile="digital" if digital_mode else "standard",
        allowed_bands=tuple(
            band for band in SUPPORTED_STATION_BANDS if band in allowed_bands
        ),
        inhibitors=tuple(inhibitors),
        configured_mode=configured_mode,
        effective_mode=effective_mode,
        amplifier_allowed=amplifier_allowed,
        amplifier_drive_w=amplifier_drive_w,
        barefoot_drive_w=barefoot_drive_w,
    )
