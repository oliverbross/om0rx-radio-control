"""Band-training plan construction.

Plan construction remains pure and never touches station hardware.  Execution
is owned by :mod:`services.station_training_jobs` and the station coordinator;
the preview includes the exact typed confirmation that the execution API will
derive again server-side.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any, Iterable, Mapping

from radio_control import config
from radio_control.elecraft import BAND_CODES, band_from_frequency
from radio_control.flex_radio import FlexCtl


BAND_ORDER = ("160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m")
MAX_TRAINING_POINTS = 100
POINT_OVERHEAD_SECONDS = 8.0
PORTION_ORDER = ("cw", "data", "ssb")
PORTION_LABELS = {"cw": "CW", "data": "Data", "ssb": "SSB"}

# Region 1-oriented operating portions used only to construct an operator
# preview. They neither assert transmit authority nor change the radio. The
# existing amplifier allow-list and route checks still fail closed per point.
BAND_PORTIONS_MHZ: dict[str, dict[str, tuple[float, float]]] = {
    "160m": {"cw": (1.810, 1.838), "data": (1.838, 1.843), "ssb": (1.843, 2.000)},
    "80m": {"cw": (3.500, 3.580), "data": (3.580, 3.600), "ssb": (3.600, 3.800)},
    "60m": {"cw": (5.3515, 5.354), "data": (5.354, 5.358), "ssb": (5.358, 5.3665)},
    "40m": {"cw": (7.000, 7.040), "data": (7.040, 7.060), "ssb": (7.060, 7.200)},
    "30m": {"cw": (10.100, 10.130), "data": (10.130, 10.150)},
    "20m": {"cw": (14.000, 14.070), "data": (14.070, 14.112), "ssb": (14.112, 14.350)},
    "17m": {"cw": (18.068, 18.095), "data": (18.095, 18.111), "ssb": (18.111, 18.168)},
    "15m": {"cw": (21.000, 21.070), "data": (21.070, 21.149), "ssb": (21.149, 21.450)},
    "12m": {"cw": (24.890, 24.915), "data": (24.915, 24.930), "ssb": (24.930, 24.990)},
    "10m": {"cw": (28.000, 28.070), "data": (28.070, 28.190), "ssb": (28.225, 29.700)},
    "6m": {"cw": (50.000, 50.100), "data": (50.100, 50.300), "ssb": (50.300, 52.000)},
}

KAT_MEMORY_SEGMENTS = (
    (0.0, 3.0, 10, "Below 3 MHz"),
    (3.0, 26.0, 20, "3–26 MHz"),
    (26.0, 38.0, 100, "26–38 MHz"),
    (38.0, 60.0, 200, "38–60 MHz"),
)


@dataclass(frozen=True)
class TrainingPreviewRequest:
    bands: tuple[str, ...] = ()
    frequency_points_mhz: Mapping[str, tuple[float, ...]] | None = None
    portions: tuple[str, ...] = ()
    coverage: str = "representative"
    erase_selected_memories: bool = False


def _normalized_portions(values: Iterable[str]) -> tuple[list[str], list[str]]:
    requested = {str(value or "").strip().lower() for value in values}
    invalid = sorted(value for value in requested if value not in PORTION_ORDER)
    return [portion for portion in PORTION_ORDER if portion in requested], invalid


def _kat_memory_segment(frequency_mhz: float) -> tuple[float, float, int, str] | None:
    for low_mhz, high_mhz, size_khz, label in KAT_MEMORY_SEGMENTS:
        if low_mhz <= frequency_mhz < high_mhz:
            return low_mhz, high_mhz, size_khz, label
    return None


def _kat_memory_bin(frequency_mhz: float) -> dict[str, Any] | None:
    """Describe the official KAT500 frequency-memory bin for a point."""
    segment = _kat_memory_segment(frequency_mhz)
    if segment is None:
        return None
    low_mhz, high_mhz, size_khz, label = segment
    frequency_khz = frequency_mhz * 1000.0
    bin_start_khz = floor(frequency_khz / size_khz) * size_khz
    return {
        "segment_label": label,
        "segment_domain_mhz": [low_mhz, high_mhz],
        "bin_size_khz": size_khz,
        "bin_start_khz": bin_start_khz,
        "bin_end_khz": bin_start_khz + size_khz - 1,
        "bin_id": f"{bin_start_khz}-{bin_start_khz + size_khz - 1}kHz",
    }


def _representative_frequency(low_mhz: float, high_mhz: float) -> float:
    return round((low_mhz + high_mhz) / 2.0, 6)


def _full_bin_frequencies(low_mhz: float, high_mhz: float) -> list[float]:
    """Return one deterministic in-portion point for every overlapping bin."""
    frequencies: list[float] = []
    cursor_mhz = low_mhz
    while cursor_mhz < high_mhz:
        segment = _kat_memory_segment(cursor_mhz)
        if segment is None:
            break
        _, segment_high_mhz, size_khz, _ = segment
        size_mhz = size_khz / 1000.0
        first_bin = floor((cursor_mhz * 1000.0 + 1e-7) / size_khz)
        segment_end_mhz = min(high_mhz, segment_high_mhz)
        last_bin = floor(((segment_end_mhz * 1000.0) - 1e-7) / size_khz)
        for bin_number in range(first_bin, last_bin + 1):
            bin_low_mhz = bin_number * size_mhz
            bin_high_mhz = bin_low_mhz + size_mhz
            overlap_low = max(low_mhz, cursor_mhz, bin_low_mhz)
            overlap_high = min(high_mhz, segment_end_mhz, bin_high_mhz)
            if overlap_low < overlap_high:
                frequencies.append(_representative_frequency(overlap_low, overlap_high))
        cursor_mhz = segment_end_mhz
    return frequencies


def _portion_frequency_points(
    band: str,
    portions: Iterable[str],
    coverage: str,
) -> list[tuple[float, tuple[str, ...]]]:
    """Generate ordered points and collapse portions sharing a KAT bin."""
    by_bin: dict[tuple[int, int], dict[str, Any]] = {}
    for portion in portions:
        domain = BAND_PORTIONS_MHZ.get(band, {}).get(portion)
        if domain is None:
            continue
        frequencies = (
            _full_bin_frequencies(*domain)
            if coverage == "full_bins"
            else [_representative_frequency(*domain)]
        )
        for frequency_mhz in frequencies:
            memory_bin = _kat_memory_bin(frequency_mhz)
            if memory_bin is None:
                continue
            key = (memory_bin["bin_start_khz"], memory_bin["bin_size_khz"])
            current = by_bin.get(key)
            if current is None:
                by_bin[key] = {"frequency_mhz": frequency_mhz, "portions": [portion]}
            elif portion not in current["portions"]:
                current["portions"].append(portion)
    return [(item["frequency_mhz"], tuple(item["portions"])) for _, item in sorted(by_bin.items())]


def _configured_default_frequencies() -> dict[str, float]:
    defaults = {band: float(frequency) for band, frequency in FlexCtl.DEFAULT_BAND_FREQS.items()}
    operator = getattr(config, "FT8_OPERATOR_SETTINGS", {}) or {}
    plan = operator.get("frequencyPlan") if isinstance(operator, dict) else None
    if isinstance(plan, list):
        for entry in plan:
            if not isinstance(entry, dict):
                continue
            band = str(entry.get("band") or "").strip().lower()
            try:
                frequency = float(entry.get("ft8"))
            except (TypeError, ValueError):
                continue
            if band in BAND_ORDER and band_from_frequency(frequency) == band:
                defaults[band] = frequency
    return defaults


def _flex_port_for_band(band: str) -> str | None:
    policy = getattr(config, "FLEX_ANTENNA_POLICY", {}) or {}
    if policy.get("enabled") is False:
        return None
    entry = (policy.get("bands") or {}).get(band)
    if isinstance(entry, dict):
        entry = entry.get("tx") or entry.get("txAnt") or entry.get("antenna")
    port = str(entry or "").strip().upper()
    return port or None


def _selected_bands(requested: Iterable[str], known: set[str]) -> list[str]:
    normalized = []
    for value in requested:
        band = str(value or "").strip().lower()
        if band and band not in normalized:
            normalized.append(band)
    if normalized:
        return normalized
    return [band for band in BAND_ORDER if band in known]


def training_confirmation(points: Iterable[Mapping[str, Any]], *, erase: bool) -> str:
    """Return the deterministic operator confirmation for an exact route set."""
    routes: list[str] = []
    for point in points:
        band = str(point.get("band") or "").strip().upper()
        antenna = point.get("kat_antenna")
        if not band or antenna not in {1, 2, 3}:
            continue
        route = f"{band} ANT{antenna}"
        if route not in routes:
            routes.append(route)
    prefix = "ERASE AND TRAIN" if erase else "TRAIN"
    return f"{prefix} {', '.join(routes)}" if routes else prefix


def build_training_preview(
    antenna_policy: Mapping[str, Any],
    request: TrainingPreviewRequest | None = None,
) -> dict[str, Any]:
    """Build a bounded, deterministic training preview without hardware I/O."""
    request = request or TrainingPreviewRequest()
    defaults = _configured_default_frequencies()
    supplied_points = request.frequency_points_mhz or {}
    known_bands = set(defaults) | set(antenna_policy) | set(supplied_points)
    bands = _selected_bands(request.bands, known_bands)
    portions, invalid_portions = _normalized_portions(request.portions)
    requested_coverage = str(request.coverage or "representative").strip().lower()
    coverage = (
        requested_coverage
        if requested_coverage in {"representative", "full_bins"}
        else "representative"
    )
    allowed_bands = {
        str(value).strip().lower()
        for value in (getattr(config, "STATION_AMPLIFIER_ALLOWED_BANDS", []) or [])
    }
    antenna_names = getattr(config, "KAT500_ANTENNA_NAMES", {}) or {}
    tune_power_w = max(15, min(30, int(getattr(config, "STATION_TUNE_POWER_W", 20))))
    timeout_seconds = max(
        5.0,
        min(60.0, float(getattr(config, "STATION_TUNE_TIMEOUT_SECONDS", 30.0))),
    )
    point_seconds = timeout_seconds + POINT_OVERHEAD_SECONDS

    errors: list[dict[str, Any]] = [
        {
            "code": "unsupported-portion",
            "portion": portion,
            "message": f"{portion or 'blank'} is not one of cw, data, or ssb",
        }
        for portion in invalid_portions
    ]
    if requested_coverage not in {"representative", "full_bins"}:
        errors.append(
            {
                "code": "unsupported-coverage",
                "value": request.coverage,
                "message": "coverage must be representative or full_bins",
            }
        )
    points: list[dict[str, Any]] = []
    plot_segments: list[dict[str, Any]] = []
    erase_items: list[dict[str, Any]] = []
    requested_count = 0
    for band in bands:
        if band not in BAND_ORDER:
            errors.append(
                {
                    "code": "unsupported-band",
                    "band": band,
                    "message": f"{band or 'blank'} is not a supported amateur band",
                }
            )
            continue

        flex_tx_ant = _flex_port_for_band(band)
        try:
            kat_antenna = int(antenna_policy.get(band, 0) or 0)
        except (TypeError, ValueError):
            kat_antenna = 0
        antenna_name = str(
            antenna_names.get(str(kat_antenna), antenna_names.get(kat_antenna, ""))
            or f"KAT ANT{kat_antenna}"
        ).strip()
        route_errors = []
        if not flex_tx_ant:
            route_errors.append("FLEX TX port policy is missing")
        if kat_antenna not in {1, 2, 3}:
            route_errors.append("KAT antenna policy is missing or invalid")
        route_id = (
            f"{band}-flex-{flex_tx_ant.lower()}-kat-ant{kat_antenna}"
            if flex_tx_ant and kat_antenna in {1, 2, 3}
            else None
        )
        erase_items.append(
            {
                "band": band,
                "band_code": BAND_CODES[band],
                "kat_antenna": kat_antenna if kat_antenna in {1, 2, 3} else None,
                "antenna_name": antenna_name if kat_antenna in {1, 2, 3} else None,
                "route_id": route_id,
                "scope_valid": kat_antenna in {1, 2, 3},
                "command_description": (
                    f"Clear KAT500 frequency memories for {band} on ANT{kat_antenna} only"
                    if kat_antenna in {1, 2, 3}
                    else f"Cannot define a KAT500 erase scope for {band} without a routed antenna"
                ),
            }
        )
        for portion in portions:
            domain = BAND_PORTIONS_MHZ.get(band, {}).get(portion)
            if domain:
                plot_segments.append(
                    {
                        "band": band,
                        "portion": portion,
                        "label": PORTION_LABELS[portion],
                        "domain_mhz": list(domain),
                    }
                )

        raw_points = supplied_points.get(band)
        generated_points: list[tuple[Any, tuple[str, ...]]] = []
        if raw_points:
            generated_points = [(frequency, ()) for frequency in raw_points]
        elif portions:
            generated_points = _portion_frequency_points(band, portions, coverage)
        elif band in defaults:
            generated_points = [(defaults[band], ())]
        if not generated_points:
            unavailable = [
                portion for portion in portions if portion not in BAND_PORTIONS_MHZ.get(band, {})
            ]
            errors.append(
                {
                    "code": "portion-unavailable" if unavailable else "frequency-unconfigured",
                    "band": band,
                    "portions": unavailable,
                    "message": (
                        f"None of the selected portions is available on {band}"
                        if unavailable
                        else f"No preview frequency is configured for {band}"
                    ),
                }
            )
            continue
        requested_count += len(generated_points)
        if requested_count > MAX_TRAINING_POINTS:
            remaining = MAX_TRAINING_POINTS - len(points)
            if not any(error["code"] == "too-many-points" for error in errors):
                errors.append(
                    {
                        "code": "too-many-points",
                        "band": band,
                        "requested_count": requested_count,
                        "maximum_points": MAX_TRAINING_POINTS,
                        "message": (
                            f"Training previews are limited to {MAX_TRAINING_POINTS} points; "
                            "the displayed plan is deterministically truncated"
                        ),
                    }
                )
            generated_points = generated_points[: max(0, remaining)]

        for raw_frequency, point_portions in generated_points:
            try:
                frequency_mhz = float(raw_frequency)
            except (TypeError, ValueError):
                errors.append(
                    {
                        "code": "invalid-frequency",
                        "band": band,
                        "value": raw_frequency,
                        "message": f"{raw_frequency!r} is not a valid MHz frequency",
                    }
                )
                continue
            observed_band = band_from_frequency(frequency_mhz)
            point_errors = list(route_errors)
            if observed_band != band:
                point_errors.append(
                    f"{frequency_mhz:.6f} MHz belongs to {observed_band or 'no supported band'}"
                )
            amplifier_allowed = band in allowed_bands
            blocked_reasons = list(point_errors)
            if not amplifier_allowed:
                blocked_reasons.append("Amplifier operation is prohibited by band policy")
            eligible = not blocked_reasons
            point = {
                "sequence": len(points) + 1,
                "band": band,
                "frequency_mhz": frequency_mhz,
                "frequency_khz": round(frequency_mhz * 1000),
                "route_id": route_id,
                "flex_tx_ant": flex_tx_ant,
                "kat_antenna": kat_antenna if kat_antenna in {1, 2, 3} else None,
                "antenna_name": antenna_name if kat_antenna in {1, 2, 3} else None,
                "amplifier_allowed": amplifier_allowed,
                "eligible": eligible,
                "disposition": "preview-only" if eligible else "blocked",
                "blocked_reasons": blocked_reasons,
                "tune_power_w": tune_power_w,
                "worst_case_seconds": point_seconds if eligible else 0.0,
            }
            # Preserve the exact v1 point object for callers that only provide
            # bands/default frequencies. Enhanced requests receive KAT bin and
            # portion provenance needed to render and audit an auto-setup.
            if raw_points or portions or request.coverage != "representative":
                point.update(
                    portions=list(point_portions),
                    portion_labels=[PORTION_LABELS[value] for value in point_portions],
                    point_source="explicit" if raw_points else coverage,
                    kat_memory_bin=_kat_memory_bin(frequency_mhz),
                )
            points.append(point)

    eligible_count = sum(1 for point in points if point["eligible"])
    blocked_count = len(points) - eligible_count
    selected_domains = [segment["domain_mhz"] for segment in plot_segments]
    plot_domain = (
        [
            min(domain[0] for domain in selected_domains),
            max(domain[1] for domain in selected_domains),
        ]
        if selected_domains
        else (
            [
                min(point["frequency_mhz"] for point in points),
                max(point["frequency_mhz"] for point in points),
            ]
            if points
            else None
        )
    )
    generation_sources = {
        "explicit"
        if supplied_points.get(band)
        else (coverage if portions else "configured-default")
        for band in bands
        if band in BAND_ORDER
    }
    required_confirmation = training_confirmation(
        (point for point in points if point["eligible"]),
        erase=bool(request.erase_selected_memories),
    )
    return {
        "schema_version": 2,
        "preview_only": True,
        "execution_available": False,
        "selection": {"mode": "single" if len(bands) == 1 else "multi", "bands": bands},
        "portions": portions,
        "coverage": coverage,
        "valid": not errors and bool(points),
        "tune_power_w": tune_power_w,
        "tune_timeout_seconds": timeout_seconds,
        "point_overhead_seconds": POINT_OVERHEAD_SECONDS,
        "point_count": len(points),
        "eligible_count": eligible_count,
        "blocked_count": blocked_count,
        "execution_point_count": eligible_count,
        "skipped_point_count": blocked_count,
        "total_worst_case_seconds": sum(point["worst_case_seconds"] for point in points),
        "validation_errors": errors,
        "required_confirmation": required_confirmation,
        "points": points,
        "point_generation": {
            "source": next(iter(generation_sources)) if len(generation_sources) == 1 else "mixed",
            "deterministic": True,
            "bounded": True,
            "maximum_points": MAX_TRAINING_POINTS,
        },
        "memory_segments": [
            {
                "domain_mhz": [low_mhz, high_mhz],
                "bin_size_khz": size_khz,
                "label": f"{label} / {size_khz} kHz bins",
            }
            for low_mhz, high_mhz, size_khz, label in KAT_MEMORY_SEGMENTS
        ],
        "erase_plan": {
            "requested": bool(request.erase_selected_memories),
            "preview_only": True,
            "execution_available": False,
            "scope": "selected-band-and-routed-kat-antenna",
            "item_count": len(erase_items),
            "items": erase_items,
        },
        "plot": {
            "x_axis": {"key": "frequency_mhz", "label": "Frequency", "unit": "MHz"},
            "y_axis": {"key": "band", "label": "Band"},
            "domain_mhz": plot_domain,
            "segments": plot_segments,
        },
        "safety_notes": [
            "This is a calculation only; no radio or Elecraft command is issued.",
            "The erase plan describes scope only; no KAT500 memory is erased.",
            "Execution remains unavailable until physical commissioning and hardware acceptance.",
            "Each future execution point must repeat fresh RX, route, RF, SWR, and carrier-off proofs.",
        ],
    }
