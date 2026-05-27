"""Rotator target resolution and bearing diagnostics."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from radio_control.rotor_math import (
    get_band_from_frequency,
    grid_to_latlon,
    initial_bearing,
    latlon_to_grid,
    validate_coordinates,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RotorTarget:
    source: str
    label: str
    confidence: str
    grid: Optional[str]
    latitude: float
    longitude: float

    @property
    def approximate(self) -> bool:
        return self.confidence != "high"

    @property
    def auto_allowed(self) -> bool:
        return self.confidence in {"high", "medium"}


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _grid_target(value: Any, source: str, label: str, confidence: str) -> Optional[RotorTarget]:
    grid = _clean_text(value)
    if not grid:
        return None

    try:
        lat, lon = grid_to_latlon(grid)
    except ValueError as exc:
        logger.debug("Ignoring invalid rotor grid %s from %s: %s", grid, source, exc)
        return None

    return RotorTarget(
        source=source,
        label=label,
        confidence=confidence,
        grid=grid.strip().upper(),
        latitude=lat,
        longitude=lon,
    )


def _coordinate_target(
    lat_value: Any,
    lon_value: Any,
    source: str,
    label: str,
    confidence: str,
) -> Optional[RotorTarget]:
    if lat_value is None or lon_value is None:
        return None

    try:
        lat, lon = validate_coordinates(lat_value, lon_value)
        grid = latlon_to_grid(lat, lon, precision=6)
    except ValueError as exc:
        logger.debug("Ignoring invalid rotor coordinates from %s: %s", source, exc)
        return None

    return RotorTarget(
        source=source,
        label=label,
        confidence=confidence,
        grid=grid,
        latitude=lat,
        longitude=lon,
    )


def _spot_grid_confidence(req: Dict[str, Any]) -> tuple[str, str, str]:
    location_source = (_clean_text(req.get("location_source")) or "").lower()
    grid_source = (_clean_text(req.get("grid_source")) or "").lower()

    if "qrz" in grid_source or "qrz" in location_source:
        return "qrz_grid", "QRZ station grid", "high"
    if "wavelog" in grid_source or "wavelog" in location_source:
        return "wavelog_grid", "Wavelog station grid", "high"
    if "cty_exact" in location_source:
        return "cty_exact_grid", "cty.dat exact-call entity grid", "medium"
    if "cty" in location_source:
        return "cty_grid", "cty.dat entity centre grid", "low"
    return "request_grid", "station grid", "high"


def _build_candidates(req: Dict[str, Any]) -> list[RotorTarget]:
    candidates: list[RotorTarget] = []

    for key, source, label in (
        ("qrz_grid", "qrz_grid", "QRZ station grid"),
        ("qrz_gridsquare", "qrz_grid", "QRZ station grid"),
        ("wavelog_grid", "wavelog_grid", "Wavelog station grid"),
        ("wavelog_gridsquare", "wavelog_grid", "Wavelog station grid"),
    ):
        target = _grid_target(req.get(key), source, label, "high")
        if target:
            candidates.append(target)

    source, label, confidence = _spot_grid_confidence(req)
    target = _grid_target(req.get("gridsquare") or req.get("grid"), source, label, confidence)
    if target:
        candidates.append(target)

    for lat_key, lon_key, source, label, confidence in (
        ("qrz_latitude", "qrz_longitude", "qrz_coordinates", "QRZ station coordinates", "high"),
        ("wavelog_latitude", "wavelog_longitude", "wavelog_coordinates", "Wavelog station coordinates", "high"),
        ("latitude", "longitude", "request_coordinates", "station coordinates", confidence),
        ("cty_latitude", "cty_longitude", "cty_coordinates", "cty.dat entity centre", "low"),
    ):
        coord_confidence = confidence
        coord_source = source
        coord_label = label
        if source == "request_coordinates":
            location_source = (_clean_text(req.get("location_source")) or "").lower()
            if "cty_exact" in location_source:
                coord_source = "cty_exact_coordinates"
                coord_label = "cty.dat exact-call entity coordinates"
                coord_confidence = "medium"
            elif "cty" in location_source:
                coord_source = "cty_coordinates"
                coord_label = "cty.dat entity centre coordinates"
                coord_confidence = "low"

        target = _coordinate_target(
            req.get(lat_key),
            req.get(lon_key),
            coord_source,
            coord_label,
            coord_confidence,
        )
        if target:
            candidates.append(target)

    return candidates


def _resolve_band(freq_khz: Any, rotor_bands: Dict[str, Any]) -> tuple[Optional[str], bool, Optional[str]]:
    band = None
    if freq_khz not in (None, ""):
        try:
            band = get_band_from_frequency(float(freq_khz))
        except (TypeError, ValueError):
            return None, False, f"Invalid frequency_khz: {freq_khz!r}"

    if not band:
        return band, True, None

    if not rotor_bands:
        return band, True, None

    if band not in rotor_bands:
        return band, False, f"Band {band} not configured for rotor"

    enabled = bool(rotor_bands.get(band))
    if not enabled:
        return band, False, f"Rotor not enabled for band {band}"

    return band, True, None


def resolve_rotor_target(
    req: Dict[str, Any],
    home_lat: Any,
    home_lon: Any,
    rotor_bands: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve the best rotator target and return a diagnostic API payload."""
    rotor_bands = rotor_bands or {}

    try:
        home_lat_f, home_lon_f = validate_coordinates(home_lat, home_lon)
    except ValueError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "message": str(exc),
            "bearing": None,
            "short_path_bearing": None,
            "long_path_bearing": None,
        }

    band, band_enabled, band_message = _resolve_band(req.get("frequency_khz"), rotor_bands)
    candidates = _build_candidates(req)

    if not candidates:
        message = "Insufficient data to calculate bearing"
        return {
            "ok": False,
            "error": message,
            "message": message,
            "bearing": None,
            "short_path_bearing": None,
            "long_path_bearing": None,
            "band": band,
            "band_enabled": band_enabled,
            "band_message": band_message,
            "candidates": [],
        }

    target = candidates[0]
    bearing = initial_bearing(home_lat_f, home_lon_f, target.latitude, target.longitude)
    short_path = round(bearing, 1)
    long_path = round((bearing + 180) % 360, 1)

    auto_allowed = target.auto_allowed and band_enabled
    if not target.auto_allowed:
        message = f"Resolved approximate target from {target.label}; showing bearing only"
    elif not band_enabled:
        message = band_message or f"Rotor not enabled for band {band}"
    else:
        message = f"Resolved target from {target.label}"

    return {
        "ok": True,
        "bearing": short_path,
        "short_path_bearing": short_path,
        "long_path_bearing": long_path,
        "band": band,
        "band_enabled": band_enabled,
        "band_message": band_message,
        "callsign": req.get("callsign") or req.get("call"),
        "source": target.source,
        "source_label": target.label,
        "confidence": target.confidence,
        "approximate": target.approximate,
        "auto_allowed": auto_allowed,
        "target_grid": target.grid,
        "target_latitude": round(target.latitude, 6),
        "target_longitude": round(target.longitude, 6),
        "message": message,
        "candidates": [
            {
                "source": candidate.source,
                "confidence": candidate.confidence,
                "grid": candidate.grid,
                "approximate": candidate.approximate,
            }
            for candidate in candidates
        ],
    }
