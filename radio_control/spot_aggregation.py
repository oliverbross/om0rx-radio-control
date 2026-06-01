"""Helpers for collapsing noisy repeated live spot rows."""

from __future__ import annotations

from typing import Any

from radio_control.spot_intelligence import extract_rbl_snr


def live_spot_key(spot: dict[str, Any]) -> str:
    """Return a stable key for a live spot row."""
    source = str(spot.get("spot_source") or "cluster").lower()
    callsign = str(spot.get("callsign") or "").upper()
    band = str(spot.get("band") or "").upper()
    mode = str(spot.get("mode") or "").upper()
    if source == "rbl":
        return f"rbl:{callsign}:{band}:{mode}"

    frequency = spot.get("frequency_mhz")
    if frequency is None:
        try:
            frequency = float(spot.get("frequency") or 0) / 1000.0
        except (TypeError, ValueError):
            frequency = 0
    return f"cluster:{callsign}:{round(float(frequency or 0), 3)}"


def _spotter_list(spot: dict[str, Any]) -> list[str]:
    values = spot.get("aggregate_spotters")
    if isinstance(values, list):
        spotters = [str(value) for value in values if value]
    else:
        spotters = []
    spotter = spot.get("spotter")
    if spotter and spotter not in spotters:
        spotters.append(str(spotter))
    return spotters


def _snr(spot: dict[str, Any]) -> float | None:
    value = spot.get("rbl_snr")
    if value is None:
        value = extract_rbl_snr(spot.get("comment"))
    if value is None:
        return None
    return float(value)


def initialize_live_aggregate(spot: dict[str, Any]) -> dict[str, Any]:
    """Populate live aggregation metadata on one spot."""
    key = live_spot_key(spot)
    spotters = _spotter_list(spot)
    timestamp = float(spot.get("timestamp") or 0)
    snr = _snr(spot)
    spot["aggregate_key"] = key
    spot["aggregate_count"] = int(spot.get("aggregate_count") or 1)
    spot["aggregate_spotters"] = spotters
    spot["aggregate_spotter_count"] = len(spotters)
    spot["aggregate_first_timestamp"] = float(spot.get("aggregate_first_timestamp") or timestamp)
    spot["aggregate_last_timestamp"] = float(spot.get("aggregate_last_timestamp") or timestamp)
    spot["aggregate_best_snr"] = snr if spot.get("aggregate_best_snr") is None else spot.get("aggregate_best_snr")
    return spot


def merge_live_spot(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge an incoming repeated spot into the existing visible row."""
    initialize_live_aggregate(existing)
    initialize_live_aggregate(incoming)

    spotters = _spotter_list(existing)
    for spotter in _spotter_list(incoming):
        if spotter not in spotters:
            spotters.append(spotter)

    first_ts = min(float(existing.get("aggregate_first_timestamp") or 0), float(incoming.get("timestamp") or 0))
    last_ts = max(float(existing.get("aggregate_last_timestamp") or 0), float(incoming.get("timestamp") or 0))
    best_snr_values = [
        value for value in [existing.get("aggregate_best_snr"), _snr(incoming)]
        if value is not None
    ]
    best_snr = max(best_snr_values) if best_snr_values else None
    count = int(existing.get("aggregate_count") or 1) + 1

    existing.update(incoming)
    existing["aggregate_key"] = incoming["aggregate_key"]
    existing["aggregate_count"] = count
    existing["aggregate_spotters"] = spotters
    existing["aggregate_spotter_count"] = len(spotters)
    existing["aggregate_first_timestamp"] = first_ts
    existing["aggregate_last_timestamp"] = last_ts
    existing["aggregate_best_snr"] = best_snr
    return existing


def upsert_live_spot(cache: list[dict[str, Any]], spot: dict[str, Any], max_len: int = 200) -> tuple[dict[str, Any], bool]:
    """Insert or merge a live spot in newest-first cache order."""
    initialize_live_aggregate(spot)
    key = spot["aggregate_key"]
    for index, existing in enumerate(cache):
        if existing.get("aggregate_key") == key or live_spot_key(existing) == key:
            merged = merge_live_spot(existing, spot)
            if index != 0:
                cache.pop(index)
                cache.insert(0, merged)
            return merged, True

    cache.insert(0, spot)
    if len(cache) > max_len:
        del cache[max_len:]
    return spot, False
