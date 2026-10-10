"""Build the read-only DXpedition watch contract consumed by native MSHV.

This module deliberately does not select targets, tune the radio, or authorize
transmit.  Activity Intelligence is only a metadata authority: it exports a
bounded list of currently active DXpedition calls and aliases.  Native MSHV
remains responsible for accepting fresh, explicitly-FT8/FT4 cluster evidence,
performing CAT QSY, requiring a local decode, and returning to its normal dial.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from pathlib import Path
import re
from typing import Any, Iterable

from radio_control.persistence import atomic_write_json


SCHEMA_VERSION = 1
DEFAULT_SPOT_MAX_AGE_SECONDS = 120
DEFAULT_WATCH_MAX_AGE_SECONDS = 24 * 60 * 60
WATCH_RELATIVE_PATH = Path("settings/database/dxpedition_watch.json")
TRUSTED_DXPEDITION_SOURCES = {"NG3K_ADXO", "DXCAL_ICS"}
ALLOWED_MODES = {"FT8", "FT4"}
CALL_RE = re.compile(r"^[A-Z0-9/]{3,16}$")
BAND_RANGES_HZ = {
    "160m": (1_800_000, 2_000_000),
    "80m": (3_500_000, 4_000_000),
    "40m": (7_000_000, 7_300_000),
    "30m": (10_100_000, 10_150_000),
    "20m": (14_000_000, 14_350_000),
    "17m": (18_068_000, 18_168_000),
    "15m": (21_000_000, 21_450_000),
    "12m": (24_890_000, 24_990_000),
    "10m": (28_000_000, 29_700_000),
    "6m": (50_000_000, 54_000_000),
}


def _utc(value: datetime | None = None) -> datetime:
    value = value or datetime.now(UTC)
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _parse_boundary(value: Any, *, end: bool) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, date):
        return datetime.combine(value, time.max if end else time.min, tzinfo=UTC)
    text = str(value).strip()
    try:
        if len(text) == 10:
            parsed_date = date.fromisoformat(text)
            return datetime.combine(parsed_date, time.max if end else time.min, tzinfo=UTC)
        return _utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _normalize_call(value: Any) -> str:
    call = str(value or "").strip().upper()
    return call if CALL_RE.fullmatch(call) else ""


def _normalize_band(value: Any) -> str:
    text = str(value or "").strip().lower().replace("meters", "m").replace("meter", "m")
    if text.isdigit():
        text += "m"
    return text if text in BAND_RANGES_HZ else ""


def band_for_frequency(frequency_hz: int) -> str:
    for band, (low, high) in BAND_RANGES_HZ.items():
        if low <= frequency_hz <= high:
            return band
    return ""


def build_dxpedition_watch(
    rows: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    max_spot_age_seconds: int = DEFAULT_SPOT_MAX_AGE_SECONDS,
    watch_max_age_seconds: int = DEFAULT_WATCH_MAX_AGE_SECONDS,
    trusted_sources: set[str] | None = None,
) -> dict[str, Any]:
    """Normalize active ADXO/DX calendar rows into a deterministic sidecar."""
    current = _utc(now)
    max_age = max(15, min(int(max_spot_age_seconds), 600))
    watch_max_age = max(3600, min(int(watch_max_age_seconds), 7 * 24 * 60 * 60))
    allowed_sources = trusted_sources or TRUSTED_DXPEDITION_SOURCES
    entries: list[dict[str, Any]] = []
    seen_calls: set[str] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "UNKNOWN").strip().upper()
        source_id = str(row.get("source_id") or row.get("sourceId") or "").strip().upper()
        if source_id not in allowed_sources:
            continue
        start = _parse_boundary(row.get("start_date_utc") or row.get("startDateUtc"), end=False)
        end = _parse_boundary(row.get("end_date_utc") or row.get("endDateUtc"), end=True)
        in_window = (start is None or start <= current) and (end is None or current <= end)
        if status == "EXPIRED" or not in_window or (status not in {"ACTIVE", "UNKNOWN"} and start is None):
            continue

        primary = _normalize_call(row.get("callsign"))
        aliases = [
            call for call in dict.fromkeys(
                _normalize_call(value) for value in [primary, *(row.get("aliases") or [])]
            ) if call
        ]
        if not primary or not aliases:
            continue

        modes = [str(value).strip().upper() for value in row.get("modes") or [] if str(value).strip()]
        if modes and not (set(modes) & ALLOWED_MODES):
            continue
        bands = [band for band in dict.fromkeys(_normalize_band(value) for value in row.get("bands") or []) if band]

        # Prefer the first current source for an alias.  This prevents duplicate
        # ADXO/calendar records from multiplying native priority decisions.
        if any(alias in seen_calls for alias in aliases):
            continue
        seen_calls.update(aliases)
        entries.append({
            "callsign": primary,
            "aliases": aliases,
            "bands": bands,
            "modes": sorted(set(modes) & ALLOWED_MODES),
            "status": "ACTIVE" if status == "ACTIVE" or in_window else status,
            "start_utc": start.isoformat().replace("+00:00", "Z") if start else None,
            "end_utc": end.isoformat().replace("+00:00", "Z") if end else None,
            "source_id": source_id,
        })

    entries.sort(key=lambda item: (item["callsign"], item["source_id"]))
    return {
        "schema": SCHEMA_VERSION,
        "generated_at_utc": current.isoformat().replace("+00:00", "Z"),
        "watch_max_age_seconds": watch_max_age,
        "spot_max_age_seconds": max_age,
        "entries": entries,
    }


def write_dxpedition_watch(path: str | Path, rows: Iterable[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """Atomically publish a watchlist without touching radio/engine state."""
    payload = build_dxpedition_watch(rows, **kwargs)
    atomic_write_json(path, payload, backup=False)
    return payload


def publish_repository_dxpedition_watch(
    repository: Any, runtime_path: str | Path, **kwargs: Any,
) -> dict[str, Any]:
    """Publish only the repository's normalized, trusted DXpedition records.

    Call this after Activity Intelligence completes a successful source refresh.
    A failed refresh leaves the prior atomic file in place; native consumers
    reject it once ``watch_max_age_seconds`` expires.
    """
    rows = repository.active_dxpeditions(limit=500)
    target = Path(runtime_path) / WATCH_RELATIVE_PATH
    payload = write_dxpedition_watch(target, rows, **kwargs)
    return {"path": str(target), "watch": payload}


def classify_cluster_spot(
    spot: dict[str, Any], watch: dict[str, Any], *, now: datetime | None = None,
) -> dict[str, Any]:
    """Validate a live spot against the contract; this never commands MSHV."""
    current = _utc(now)
    if watch.get("schema") != SCHEMA_VERSION:
        return {"accepted": False, "reason": "watch-schema-invalid", "dedupe_key": "", "dxpedition": None}
    generated = _parse_boundary(watch.get("generated_at_utc"), end=False)
    watch_max_age = max(3600, min(int(watch.get("watch_max_age_seconds") or DEFAULT_WATCH_MAX_AGE_SECONDS), 7 * 24 * 60 * 60))
    if generated is None or generated > current or (current - generated).total_seconds() > watch_max_age:
        return {"accepted": False, "reason": "watch-stale", "dedupe_key": "", "dxpedition": None}
    call = _normalize_call(spot.get("callsign") or spot.get("dxcall"))
    mode = str(spot.get("mode") or "").strip().upper()
    try:
        frequency_hz = int(round(float(spot.get("frequency_hz") or 0)))
    except (TypeError, ValueError):
        frequency_hz = 0
    band = band_for_frequency(frequency_hz)
    timestamp = _parse_boundary(spot.get("timestamp_utc") or spot.get("timestamp"), end=False)
    max_age = max(15, min(int(watch.get("spot_max_age_seconds") or DEFAULT_SPOT_MAX_AGE_SECONDS), 600))

    reason = "accepted"
    if not call:
        reason = "invalid-callsign"
    elif mode not in ALLOWED_MODES:
        reason = "mode-not-explicit-ft8-ft4"
    elif not band:
        reason = "frequency-outside-supported-bands"
    elif timestamp is None or timestamp > current or (current - timestamp).total_seconds() > max_age:
        reason = "spot-stale"

    matched: dict[str, Any] | None = None
    if reason == "accepted":
        for entry in watch.get("entries") or []:
            aliases = {_normalize_call(value) for value in entry.get("aliases") or []}
            if call not in aliases:
                continue
            bands = {_normalize_band(value) for value in entry.get("bands") or []}
            modes = {str(value).strip().upper() for value in entry.get("modes") or []}
            if bands and band not in bands:
                reason = "dxpedition-band-mismatch"
                break
            if modes and mode not in modes:
                reason = "dxpedition-mode-mismatch"
                break
            matched = entry
            break
        if matched is None and reason == "accepted":
            reason = "not-known-dxpedition"

    # 100 Hz buckets keep simultaneous same-band off-frequency operations
    # distinct while merging harmless reporting precision differences.
    dedupe_key = f"{call}@{band}@{frequency_hz // 100}" if call and band and frequency_hz else ""
    return {
        "accepted": matched is not None and reason == "accepted",
        "reason": reason,
        "callsign": call,
        "band": band,
        "frequency_hz": frequency_hz,
        "dedupe_key": dedupe_key,
        "dxpedition": matched,
    }
