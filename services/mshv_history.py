"""Attested Wavelog history snapshot and acknowledged MSHV live deltas.

Wavelog is the only authority.  Native MSHV history/tracker files are derived
offline from an attested canonical export.  Completed type-12 events queued in
the offline outbox remain pending and do not affect worked-history novelty.
They move to the acknowledged delta journal only after Wavelog accepts the
outbox replay (or independently reports the QSO as a duplicate).
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from threading import Event, RLock
import time
from typing import Any

from radio_control.persistence import atomic_write_json, locked_file, read_json_object


logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DELTA_PATH = ROOT / "logs" / "mshv_wavelog_history_deltas.json"
CANONICAL_SOURCE = "wavelog_postgres"
PRODUCTION_POLICY = "Wavelog sole authority; WSJT inputs diagnostic only; FT8/FT4 only"
HASH_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
HISTORY_STATUS_CACHE_TTL_SECONDS = 8.0
_HISTORY_STATUS_CACHE_LOCK = RLock()
_HISTORY_STATUS_COMPUTE_LOCK = RLock()
_HISTORY_STATUS_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_HISTORY_STATUS_FLIGHTS: dict[tuple[str, str], dict[str, Any]] = {}
_HASH_CACHE: dict[Path, tuple[int, int, int, str]] = {}


def runtime_path() -> Path:
    return Path(os.environ.get("OM0RX_MSHV_RUNTIME", ROOT / "data/build/mshv-auto-dx/runtime"))


def _sha(path: Path) -> str:
    stat = path.stat()
    signature = (stat.st_size, stat.st_mtime_ns, getattr(stat, "st_ctime_ns", 0))
    cached = _HASH_CACHE.get(path)
    if cached and cached[:3] == signature:
        return cached[3]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _HASH_CACHE[path] = (*signature, digest)
    return digest


def _utc(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _integer_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _band_from_hz(value: Any) -> str:
    try:
        hz = float(value)
    except (TypeError, ValueError):
        return ""
    if hz < 1000:
        hz *= 1_000_000
    for low, high, band in (
        (1_800_000, 2_000_000, "160m"), (3_500_000, 4_000_000, "80m"),
        (5_300_000, 5_500_000, "60m"), (7_000_000, 7_300_000, "40m"),
        (10_100_000, 10_150_000, "30m"), (14_000_000, 14_350_000, "20m"),
        (18_068_000, 18_168_000, "17m"), (21_000_000, 21_450_000, "15m"),
        (24_890_000, 24_990_000, "12m"), (28_000_000, 29_700_000, "10m"),
        (50_000_000, 54_000_000, "6m"),
    ):
        if low <= hz < high:
            return band
    return ""


def _strict_adif_date(value: Any) -> str:
    digits = "".join(c for c in str(value or "") if c.isdigit())
    if len(digits) != 8:
        return ""
    try:
        datetime.strptime(digits, "%Y%m%d")
    except ValueError:
        return ""
    return digits


def _strict_adif_time(value: Any) -> str:
    digits = "".join(c for c in str(value or "") if c.isdigit())
    if len(digits) != 6:
        return ""
    try:
        datetime.strptime(digits, "%H%M%S")
    except ValueError:
        return ""
    return digits


def _valid_mshv_identity(identity: dict[str, Any]) -> bool:
    return bool(
        str(identity.get("provider") or "").strip()
        and str(identity.get("station_callsign") or "").upper() == "OM0RX"
        and str(identity.get("client_id") or "").strip()
        and HASH_RE.fullmatch(str(identity.get("event_id") or ""))
        and str(identity.get("call") or "").strip()
        and _strict_adif_date(identity.get("qso_date"))
        and _strict_adif_time(identity.get("time_on"))
        and _strict_adif_time(identity.get("time_off"))
        and str(identity.get("mode") or "").upper() in {"FT8", "FT4"}
        and _positive_int(identity.get("frequency_hz"))
        and str(identity.get("band") or "").lower() == _band_from_hz(identity.get("frequency_hz"))
    )


def _delta_journal(path: Path | None = None, *, strict: bool = False) -> dict[str, Any]:
    path = path or DELTA_PATH
    payload = read_json_object(path)
    if path.exists() and not payload:
        if strict:
            raise ValueError("Acknowledged Wavelog delta journal is unreadable")
        return {"schema": 1, "next_sequence": 1, "records": {}, "pending": {}}
    if payload and payload.get("schema") != 1:
        if strict:
            raise ValueError("Acknowledged Wavelog delta journal schema is invalid")
        return {"schema": 1, "next_sequence": 1, "records": {}, "pending": {}}
    records = payload.get("records", {})
    pending = payload.get("pending", {})
    if not isinstance(records, dict) or not isinstance(pending, dict):
        if strict:
            raise ValueError("Wavelog delta records are invalid")
        return {"schema": 1, "next_sequence": 1, "records": {}, "pending": {}}
    try:
        next_sequence = int(payload.get("next_sequence", 1))
    except (TypeError, ValueError):
        next_sequence = 0
    if next_sequence < 1:
        if strict:
            raise ValueError("Wavelog delta sequence is invalid")
        next_sequence = 1
    return {"schema": 1, "next_sequence": next_sequence, "records": records, "pending": pending}


def _delta_records(path: Path | None = None, *, strict: bool = False) -> dict[str, dict[str, Any]]:
    return _delta_journal(path, strict=strict)["records"]


def _tracker_delta_ledger(path: Path) -> tuple[set[str], str | None]:
    """Read the tracker-owned idempotency ledger without mutating SQLite.

    The ledger row and worked-status mutations are committed in the same native
    transaction.  It is therefore the recovery authority when MSHV crashes
    after that commit but before the JSON cursor is durably replaced.
    """
    if not path.is_file():
        return set(), "tracker-missing"
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1.0) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wavelog_applied_deltas'"
            ).fetchone()
            if not table:
                return set(), "wavelog-delta-ledger-missing"
            rows = connection.execute(
                "SELECT delta_key FROM wavelog_applied_deltas ORDER BY rowid"
            ).fetchall()
    except (sqlite3.Error, OSError) as exc:
        return set(), f"wavelog-delta-ledger-unreadable:{type(exc).__name__}"
    keys = {str(row[0] or "").lower() for row in rows}
    if any(not HASH_RE.fullmatch(key) for key in keys):
        return set(), "wavelog-delta-ledger-invalid"
    return keys, None


def _adif_delta_identity(request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    from scripts.digital.export_history import parse_adif

    rows = list(parse_adif(str(request.get("adif_text") or "")))
    if len(rows) != 1:
        raise ValueError("Authoritative MSHV delta must contain exactly one ADIF QSO")
    row = rows[0]
    def app(name: str) -> str:
        return str(row.get(f"APP_OM0RX_{name}") or "").strip()
    mode = str(row.get("SUBMODE") or row.get("MODE") or request.get("mode") or "").upper()
    frequency_value = row.get("FREQ") or request.get("frequency_hz")
    try:
        numeric_frequency = float(frequency_value)
        frequency_hz = int(round(numeric_frequency * (1_000_000 if numeric_frequency < 1000 else 1)))
    except (TypeError, ValueError):
        frequency_hz = 0
    identity = {
        "station_callsign": str(request.get("station_callsign") or app("STATION") or row.get("STATION_CALLSIGN") or "OM0RX").upper(),
        "call": str(row.get("CALL") or request.get("call") or "").upper(),
        "qso_date": _strict_adif_date(row.get("QSO_DATE")),
        "time_on": _strict_adif_time(row.get("TIME_ON")),
        "band": str(row.get("BAND") or _band_from_hz(row.get("FREQ") or request.get("frequency_hz"))).lower(),
        "frequency_hz": frequency_hz,
        "mode": mode,
        "grid": str(row.get("GRIDSQUARE") or "").upper(),
        "time_off": _strict_adif_time(row.get("TIME_OFF")),
        "provider": str(request.get("provider") or app("PROVIDER") or "mshv_auto_dx").lower(),
        "client_id": str(request.get("client_id") or app("CLIENT_ID") or ""),
        "event_id": str(request.get("event_id") or app("EVENT_ID") or "").lower(),
        "wavelog_id": _integer_or_zero(request.get("wavelog_id")),
    }
    required = {name: identity[name] for name in (
        "station_callsign", "call", "qso_date", "time_on", "time_off",
        "frequency_hz", "band", "mode",
    )}
    if not all(required.values()) or mode not in {"FT8", "FT4"}:
        raise ValueError("Authoritative MSHV delta identity is incomplete or outside FT8/FT4")
    key_override = str(request.get("delta_key") or "").strip().lower()
    key = key_override if HASH_RE.fullmatch(key_override) else hashlib.sha256(
        json.dumps(required, sort_keys=True).encode()
    ).hexdigest()
    return key, identity


def _wavelog_result_id(result: dict[str, Any]) -> int:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    for value in (
        data.get("id"), data.get("qso_id"), data.get("lastid"),
        result.get("wavelog_id"), result.get("readback_wavelog_id"),
    ):
        if _positive_int(value):
            return int(value)
    return 0


def record_successful_wavelog_upload(
    qso_data: dict[str, Any], result: dict[str, Any], *,
    adif_text: str, path: Path | None = None,
) -> dict[str, Any]:
    """Publish one successful provider-neutral FT8/FT4 upload to Phase 2.

    Native MSHV type-12 events retain their pre-upload QSO identity so an
    existing pending record is promoted in place. Other providers use the
    immutable Wavelog row id, or their canonical event id, as the exactly-once
    delta key.
    """
    if not result.get("success"):
        return {"recorded": False, "reason": "wavelog-not-durably-acknowledged"}
    mode = str(qso_data.get("submode") or qso_data.get("mode") or "").upper()
    if mode not in {"FT8", "FT4"}:
        return {"recorded": False, "reason": "not-ft8-ft4"}
    provider = str(qso_data.get("provider") or "wavelog").strip().lower()
    wavelog_id = _wavelog_result_id(result)
    event_id = str(qso_data.get("event_id") or "").strip().lower()
    if not HASH_RE.fullmatch(event_id):
        if not wavelog_id:
            return {"recorded": False, "reason": "wavelog-row-event-identity-missing"}
        event_id = hashlib.sha256(f"wavelog-row:{wavelog_id}".encode()).hexdigest()
    request = {
        "adif_text": adif_text,
        "provider": provider,
        "station_callsign": str(qso_data.get("station_callsign") or "OM0RX").upper(),
        "client_id": str(qso_data.get("client_id") or f"wavelog-upload:{provider}"),
        "event_id": event_id,
        "wavelog_id": wavelog_id,
    }
    if provider != "mshv_auto_dx":
        request["delta_key"] = event_id
    return record_acknowledged_delta(request, {"wavelog": result}, path=path)


def stage_pending_delta(
    request: dict[str, Any], *, path: Path | None = None, reconstructed: bool = False,
) -> dict[str, Any]:
    """Durably stage a canonical type-12 before any outbox enqueue can occur."""
    path = path or DELTA_PATH
    key, identity = _adif_delta_identity(request)
    if identity.get("provider") != "mshv_auto_dx":
        return {"pending": False, "reason": "not-mshv-provider"}
    if not _valid_mshv_identity(identity):
        return {"pending": False, "reason": "mshv-pending-correlation-incomplete", "delta_key": key}
    adif_text = str(request.get("adif_text") or "")
    now = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_file(path):
        journal = _delta_journal(path, strict=True)
        if key in journal["records"]:
            return {"pending": False, "already_acknowledged": True, "delta_key": key}
        previous = journal["pending"].get(key, {})
        if previous and (
            previous.get("event_id") != identity.get("event_id")
            or previous.get("client_id") != identity.get("client_id")
            or previous.get("station_callsign") != identity.get("station_callsign")
        ):
            return {"pending": False, "reason": "mshv-pending-correlation-conflict", "delta_key": key}
        journal["pending"][key] = {
            "key": key,
            **identity,
            "source_authority": "wavelog_outbox_pending",
            "lifecycle_state": "pending",
            "adif_sha256": hashlib.sha256(adif_text.encode()).hexdigest(),
            "adif_text": adif_text,
            "first_queued_utc": previous.get("first_queued_utc") or now,
            "last_queued_utc": now,
            "receipt_count": int(previous.get("receipt_count", 0)) + 1,
            "reconstructed_from_outbox": bool(previous.get("reconstructed_from_outbox") or reconstructed),
        }
        atomic_write_json(path, journal)
    invalidate_history_status_cache()
    return {"pending": True, "delta_key": key, "duplicate_receipt": bool(previous)}


def _seal_delta(row: dict[str, Any], previous_hash: str) -> dict[str, Any]:
    sealed = {**row, "previous_hash": previous_hash}
    sealed["entry_hash"] = hashlib.sha256(
        json.dumps(sealed, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return sealed


def record_acknowledged_delta(
    request: dict[str, Any], result: dict[str, Any], *, path: Path | None = None,
) -> dict[str, Any]:
    """Record a type-12 only after Wavelog has actually acknowledged it."""
    wavelog = result.get("wavelog") if isinstance(result.get("wavelog"), dict) else {}
    dedupe = result.get("dedupe") if isinstance(result.get("dedupe"), dict) else {}
    acknowledged = bool(
        wavelog.get("success")
        or dedupe.get("wavelog_success") is True
        or (result.get("readback_verified") is True and result.get("readback_identity_exact") is True)
    )
    if not acknowledged:
        return {"recorded": False, "reason": "wavelog-not-durably-acknowledged"}
    path = path or DELTA_PATH
    key, identity = _adif_delta_identity(request)
    if not _valid_mshv_identity(identity):
        return {"recorded": False, "reason": "mshv-acknowledged-identity-invalid", "delta_key": key}
    now = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_file(path):
        journal = _delta_journal(path, strict=True)
        records = journal["records"]
        previous = records.get(key, {})
        if previous:
            return {"recorded": True, "delta_key": key, "duplicate_receipt": True}
        sequence = journal["next_sequence"]
        previous_hash = "0" * 64 if sequence == 1 else next(
            row["entry_hash"] for row in records.values() if row.get("sequence") == sequence - 1
        )
        records[key] = _seal_delta({
            "key": key,
            **identity,
            "provider": str(request.get("provider") or "mshv_auto_dx"),
            "source_authority": "wavelog_acknowledged",
            "adif_sha256": hashlib.sha256(str(request.get("adif_text") or "").encode()).hexdigest(),
            "first_acknowledged_utc": previous.get("first_acknowledged_utc") or now,
            "last_acknowledged_utc": now,
            "receipt_count": int(previous.get("receipt_count", 0)) + 1,
            "sequence": sequence,
            "outcome": "duplicate" if result.get("duplicate") else "wavelog",
            "lifecycle_state": (
                "readback_verified" if result.get("readback_verified") is True else "acknowledged"
            ),
        }, previous_hash)
        journal["next_sequence"] = sequence + 1
        journal["pending"].pop(key, None)
        atomic_write_json(path, journal)
    invalidate_history_status_cache()
    from services.mshv_observability import SUMMARY_PATH, record_qso
    record_qso(
        {**records[key], "last_acknowledged_utc": now},
        path=SUMMARY_PATH if path.resolve() == DELTA_PATH.resolve() else path.with_name("mshv_autodx_daily_summaries.json"),
    )
    return {"recorded": True, "delta_key": key, "duplicate_receipt": bool(previous)}


def record_pending_delta(
    request: dict[str, Any], result: dict[str, Any], *, path: Path | None = None,
) -> dict[str, Any]:
    """Journal an outbox item without advancing Wavelog-derived novelty."""
    if not (result.get("success") and result.get("outbox_queued")):
        return {"pending": False, "reason": "not-outbox-pending"}
    return stage_pending_delta(request, path=path)


def acknowledge_outbox_delta(adif_text: str, *, path: Path | None = None) -> dict[str, Any]:
    """Promote one queued MSHV delta after successful outbox replay."""
    path = path or DELTA_PATH
    try:
        key, identity = _adif_delta_identity({"adif_text": adif_text})
    except ValueError:
        return {"recorded": False, "reason": "not-an-mshv-ft8-ft4-pending-record"}
    now = datetime.now(timezone.utc).isoformat()
    if identity.get("provider") != "mshv_auto_dx":
        return {"recorded": False, "reason": "not-an-mshv-outbox-record"}
    reconstructed = False
    with locked_file(path):
        journal = _delta_journal(path, strict=True)
        pending = journal["pending"].get(key)
        if not pending:
            if not _valid_mshv_identity(identity):
                return {"recorded": False, "mshv_pending_found": False, "reason": "outbox-reconstruction-identity-incomplete", "delta_key": key}
            pending = {
                "key": key, **identity,
                "source_authority": "wavelog_outbox_pending",
                "lifecycle_state": "pending",
                "adif_sha256": hashlib.sha256(adif_text.encode()).hexdigest(),
                "adif_text": adif_text,
                "first_queued_utc": now,
                "last_queued_utc": now,
                "receipt_count": 1,
                "reconstructed_from_outbox": True,
            }
            journal["pending"][key] = pending
            reconstructed = True
        previous = journal["records"].get(key, {})
        if previous:
            journal["pending"].pop(key, None)
            atomic_write_json(path, journal)
            invalidate_history_status_cache()
            return {"recorded": True, "delta_key": key, "duplicate_receipt": True}
        sequence = journal["next_sequence"]
        previous_hash = "0" * 64 if sequence == 1 else next(
            row["entry_hash"] for row in journal["records"].values() if row.get("sequence") == sequence - 1
        )
        journal["records"][key] = _seal_delta({
            "key": key,
            **identity,
            "provider": pending.get("provider") or "mshv_auto_dx",
            "source_authority": "wavelog_acknowledged",
            "adif_sha256": pending.get("adif_sha256") or hashlib.sha256(adif_text.encode()).hexdigest(),
            "first_acknowledged_utc": previous.get("first_acknowledged_utc") or now,
            "last_acknowledged_utc": now,
            "receipt_count": int(previous.get("receipt_count", 0)) + 1,
            "sequence": sequence,
            "outcome": "outbox-replay",
            "lifecycle_state": "acknowledged",
        }, previous_hash)
        journal["next_sequence"] = sequence + 1
        journal["pending"].pop(key, None)
        atomic_write_json(path, journal)
    invalidate_history_status_cache()
    from services.mshv_observability import SUMMARY_PATH, record_qso
    record_qso(
        {**journal["records"][key], "last_acknowledged_utc": now},
        path=SUMMARY_PATH if path.resolve() == DELTA_PATH.resolve() else path.with_name("mshv_autodx_daily_summaries.json"),
    )
    return {"recorded": True, "mshv_pending_found": True, "delta_key": key, "duplicate_receipt": bool(previous), "pending_reconstructed": reconstructed}


def reconcile_source_backed_pending(
    *, runtime: Path | None = None, delta_path: Path | None = None, apply: bool = False,
) -> dict[str, Any]:
    """Preview or promote legacy pending rows proven by the attested source.

    This is deliberately explicit and offline-oriented. It never uses native
    MSHV logs as evidence and never contacts Wavelog. Event id is preferred;
    otherwise every canonical QSO field (including TIME_OFF and exact
    frequency) must match uniquely. Ambiguous rows remain pending.
    """
    production_paths = runtime is None and delta_path is None
    runtime = (runtime or runtime_path()).resolve()
    delta_path = delta_path or DELTA_PATH
    marker = read_json_object(runtime / "history-import.json")
    source = Path(str(marker.get("source") or ""))
    expected_hash = str(marker.get("canonical_sha256") or "").lower()
    if not source.is_file() or not HASH_RE.fullmatch(expected_hash) or _sha(source) != expected_hash:
        return {"success": False, "applied": False, "reason": "attested-canonical-source-unavailable-or-diverged"}
    if marker.get("canonical_source") != CANONICAL_SOURCE or marker.get("applied") is not True:
        return {"success": False, "applied": False, "reason": "canonical-source-not-attested"}

    from scripts.digital.export_history import parse_adif

    def source_identity(row: dict[str, Any]) -> dict[str, Any]:
        frequency_hz = 0
        try:
            frequency_hz = int(round(float(row.get("FREQ") or 0) * 1_000_000))
        except (TypeError, ValueError):
            pass
        return {
            "station_callsign": str(row.get("STATION_CALLSIGN") or "OM0RX").upper(),
            "call": str(row.get("CALL") or "").upper(),
            "qso_date": _strict_adif_date(row.get("QSO_DATE")),
            "time_on": _strict_adif_time(row.get("TIME_ON")),
            "time_off": _strict_adif_time(row.get("TIME_OFF")),
            "band": str(row.get("BAND") or _band_from_hz(frequency_hz)).lower(),
            "mode": str(row.get("SUBMODE") or row.get("MODE") or "").upper(),
            "frequency_hz": frequency_hz,
            "event_id": str(row.get("APP_OM0RX_EVENT_ID") or "").lower(),
            "provider": str(row.get("APP_OM0RX_PROVIDER") or "").lower(),
            "client_id": str(row.get("APP_OM0RX_CLIENT_ID") or ""),
        }

    source_rows = [source_identity(row) for row in parse_adif(source.read_text(encoding="utf-8"))]
    journal = _delta_journal(delta_path, strict=True)
    promotable: list[str] = []
    ambiguous: list[dict[str, Any]] = []
    proof_by_key: dict[str, str] = {}
    canonical_fields = (
        "station_callsign", "call", "qso_date", "time_on", "time_off",
        "band", "mode", "frequency_hz",
    )
    for key, row in journal["pending"].items():
        if not _valid_mshv_identity(row):
            continue
        event_matches = [candidate for candidate in source_rows if candidate["event_id"] == row.get("event_id")]
        if event_matches:
            matches = event_matches
            proof = "app-om0rx-event-id"
        else:
            matches = []
            for candidate in source_rows:
                # An authoritative row carrying another event id cannot be
                # reinterpreted through the weaker fallback identity.
                if candidate["event_id"]:
                    continue
                if not all(candidate[name] == row.get(name) for name in canonical_fields):
                    continue
                if candidate["provider"] and candidate["provider"] != row.get("provider"):
                    continue
                if candidate["client_id"] and candidate["client_id"] != row.get("client_id"):
                    continue
                matches.append(candidate)
            proof = "canonical-qso-identity"
        if len(matches) == 1:
            promotable.append(key)
            proof_by_key[key] = proof
        elif len(matches) > 1:
            ambiguous.append({"key": key, "reason": "ambiguous-canonical-match", "candidate_count": len(matches)})
    promoted: list[str] = []
    promoted_qsos: list[dict[str, Any]] = []
    if apply:
        # Recheck the attested bytes and journal under the journal lock before
        # changing lifecycle state; no synthetic readback flag is created.
        with locked_file(delta_path):
            if _sha(source) != expected_hash:
                return {"success": False, "applied": False, "reason": "attested-canonical-source-diverged-during-apply"}
            current = _delta_journal(delta_path, strict=True)
            for key in promotable:
                pending = current["pending"].get(key)
                original = journal["pending"].get(key)
                if not pending or pending.get("adif_sha256") != original.get("adif_sha256"):
                    continue
                sequence = current["next_sequence"]
                previous_hash = "0" * 64 if sequence == 1 else next(
                    item["entry_hash"] for item in current["records"].values()
                    if item.get("sequence") == sequence - 1
                )
                now = datetime.now(timezone.utc).isoformat()
                record = _seal_delta({
                    "key": key,
                    **{name: pending.get(name) for name in (
                        "station_callsign", "call", "qso_date", "time_on", "time_off",
                        "band", "frequency_hz", "mode", "grid", "provider", "client_id",
                        "event_id", "wavelog_id",
                    )},
                    "source_authority": "wavelog_acknowledged",
                    "adif_sha256": pending.get("adif_sha256"),
                    "first_acknowledged_utc": now,
                    "last_acknowledged_utc": now,
                    "receipt_count": 1,
                    "sequence": sequence,
                    "outcome": "source-reconciled",
                    "lifecycle_state": "acknowledged",
                    "reconciliation_proof": proof_by_key[key],
                    "canonical_sha256": expected_hash,
                }, previous_hash)
                current["records"][key] = record
                current["pending"].pop(key, None)
                current["next_sequence"] = sequence + 1
                promoted.append(key)
                parsed_pending = list(parse_adif(str(pending.get("adif_text") or "")))
                if len(parsed_pending) == 1:
                    promoted_qsos.append({
                        str(name).lower(): value for name, value in parsed_pending[0].items()
                    })
            if promoted:
                atomic_write_json(delta_path, current)
        if promoted:
            from services.mshv_observability import SUMMARY_PATH, record_qso
            summary_path = (
                SUMMARY_PATH if delta_path.resolve() == DELTA_PATH.resolve()
                else delta_path.with_name("mshv_autodx_daily_summaries.json")
            )
            for key in promoted:
                record_qso(current["records"][key], path=summary_path)
            invalidate_history_status_cache()
            if production_paths:
                try:
                    from services.mshv_award_hunting import republish_after_authoritative_history_change

                    republish_after_authoritative_history_change(
                        "wavelog-source-reconciled", acknowledged_qsos=promoted_qsos,
                    )
                except Exception:
                    logger.warning("Unable to refresh MSHV award sidecar after source reconciliation", exc_info=True)
    return {
        "success": True, "applied": bool(apply), "source": str(source),
        "promotable_count": len(promotable), "promotable_keys": promotable,
        "promoted_count": len(promoted), "promoted_keys": promoted,
        "ambiguous_count": len(ambiguous), "ambiguous": ambiguous,
    }


def _path_signature(path: Path) -> tuple[str, int, int, int] | tuple[str, None]:
    try:
        stat = path.stat()
    except OSError:
        return str(path), None
    return (
        str(path), stat.st_size, stat.st_mtime_ns,
        getattr(stat, "st_ctime_ns", 0),
    )


def _history_status_signature(runtime: Path, delta_path: Path) -> tuple[Any, ...]:
    """Cheaply identify every mutable input used by history verification."""
    marker_path = runtime / "history-import.json"
    marker = read_json_object(marker_path)
    source_value = str(marker.get("source") or "")
    source = Path(source_value) if source_value else runtime / ".missing-canonical-source"
    tracker = runtime / "settings/database/worked.db"
    paths = (
        marker_path,
        runtime / "log/mshvlog.edim",
        runtime / "log/mshvlog.adi",
        tracker,
        tracker.with_name(tracker.name + "-wal"),
        runtime / "settings/database/wavelog_delta_state.json",
        delta_path,
        source,
        source.with_suffix(source.suffix + ".report.json"),
    )
    return tuple(_path_signature(path) for path in paths)


def _cache_key(runtime: Path, delta_path: Path) -> tuple[str, str]:
    return str(runtime.resolve()), str(delta_path.resolve())


def _serve_fresh_cached(payload: dict[str, Any], validated_monotonic: float) -> dict[str, Any]:
    """Render a fresh cache hit with truthful response-time age metadata."""
    served = deepcopy(payload)
    elapsed = max(0.0, time.monotonic() - validated_monotonic)
    snapshot = served.get("snapshot")
    if isinstance(snapshot, dict) and isinstance(snapshot.get("age_seconds"), (int, float)):
        snapshot["age_seconds"] = max(0.0, float(snapshot["age_seconds"]) + elapsed)
    served["generated_at"] = datetime.now(timezone.utc).isoformat()
    return served


def _serve_stale_cached(payload: dict[str, Any]) -> dict[str, Any]:
    # Preserve the last successful generated_at. Consumers already fail closed
    # when it exceeds max_age_seconds; refreshing it here would extend trust
    # without a completed authority validation.
    return deepcopy(payload)


def invalidate_history_status_cache() -> None:
    """Invalidate verified snapshots after an in-process journal mutation."""
    with _HISTORY_STATUS_CACHE_LOCK:
        _HISTORY_STATUS_CACHE.clear()


def history_status_etag(payload: dict[str, Any]) -> str:
    """Return a stable validator for semantic history content."""
    semantic = deepcopy(payload)
    semantic.pop("generated_at", None)
    snapshot = semantic.get("snapshot")
    if isinstance(snapshot, dict):
        snapshot.pop("age_seconds", None)
    canonical = json.dumps(semantic, sort_keys=True, separators=(",", ":"))
    return '"' + hashlib.sha256(canonical.encode()).hexdigest() + '"'


def history_status(
    *, runtime: Path | None = None, delta_path: Path | None = None,
    now: datetime | None = None, cache_ttl_seconds: float | None = None,
) -> dict[str, Any]:
    """Return a fully verified history snapshot with keyed single-flight caching.

    Production callers use a short cache. Explicit fixture paths and explicit
    clocks remain uncached unless a TTL is requested, preserving deterministic
    verification tests and maintenance commands.
    """
    use_default_paths = runtime is None and delta_path is None and now is None
    runtime = (runtime or runtime_path()).resolve()
    delta_path = (delta_path or DELTA_PATH).resolve()
    ttl = (
        HISTORY_STATUS_CACHE_TTL_SECONDS if cache_ttl_seconds is None and use_default_paths
        else max(0.0, float(cache_ttl_seconds or 0.0))
    )
    key = _cache_key(runtime, delta_path)
    signature = _history_status_signature(runtime, delta_path)
    current_monotonic = time.monotonic()
    cached: dict[str, Any] | None = None
    cached_inputs_unchanged = False
    flight: dict[str, Any] | None = None
    owner = False

    if ttl > 0:
        with _HISTORY_STATUS_CACHE_LOCK:
            cached = _HISTORY_STATUS_CACHE.get(key)
            cached_inputs_unchanged = bool(cached and cached["signature"] == signature)
            if (
                cached_inputs_unchanged
                and current_monotonic - cached["validated_monotonic"] < ttl
            ):
                return _serve_fresh_cached(cached["payload"], cached["validated_monotonic"])
            flight = _HISTORY_STATUS_FLIGHTS.get(key)
            if flight is not None:
                if cached_inputs_unchanged:
                    return _serve_stale_cached(cached["payload"])
            else:
                flight = {
                    "event": Event(), "payload": None, "error": None,
                    "stale": False,
                }
                _HISTORY_STATUS_FLIGHTS[key] = flight
                owner = True

    if ttl > 0 and not owner:
        assert flight is not None
        flight["event"].wait()
        if flight["error"] is not None:
            raise flight["error"]
        if flight["stale"]:
            return _serve_stale_cached(flight["payload"])
        return _serve_fresh_cached(flight["payload"], flight["validated_monotonic"])

    try:
        # Different cache keys can still reference the same mutable SQLite and
        # journal inputs. Preserve the original cross-file serialization while
        # ensuring identical callers share one computation instead of queueing
        # and repeating it.
        with _HISTORY_STATUS_COMPUTE_LOCK:
            result: dict[str, Any] | None = None
            stable_signature: tuple[Any, ...] | None = None
            for _attempt in range(2):
                before_signature = _history_status_signature(runtime, delta_path)
                validation_now = now or datetime.now(timezone.utc)
                candidate = _history_status_unlocked(
                    runtime=runtime, delta_path=delta_path, now=validation_now,
                )
                after_signature = _history_status_signature(runtime, delta_path)
                if before_signature == after_signature:
                    result = candidate
                    stable_signature = after_signature
                    break
            if result is None or stable_signature is None:
                raise RuntimeError("History authority inputs changed during validation")
        generated = now or datetime.now(timezone.utc)
        payload = {**result, "generated_at": generated.isoformat(), "max_age_seconds": 10}
        validated_monotonic = time.monotonic()
        if ttl > 0:
            with _HISTORY_STATUS_CACHE_LOCK:
                _HISTORY_STATUS_CACHE[key] = {
                    "payload": deepcopy(payload),
                    "signature": stable_signature,
                    "validated_monotonic": validated_monotonic,
                }
                assert flight is not None
                flight["payload"] = deepcopy(payload)
                flight["validated_monotonic"] = validated_monotonic
        return payload
    except BaseException as exc:
        if ttl > 0:
            with _HISTORY_STATUS_CACHE_LOCK:
                assert flight is not None
                cached = _HISTORY_STATUS_CACHE.get(key)
                current_signature = _history_status_signature(runtime, delta_path)
                cached_inputs_unchanged = bool(
                    cached and cached["signature"] == current_signature
                )
                if cached_inputs_unchanged:
                    flight["payload"] = deepcopy(cached["payload"])
                    flight["validated_monotonic"] = cached["validated_monotonic"]
                    flight["stale"] = True
                else:
                    flight["error"] = exc
            if cached_inputs_unchanged:
                return _serve_stale_cached(flight["payload"])
        raise
    finally:
        if ttl > 0 and owner:
            with _HISTORY_STATUS_CACHE_LOCK:
                assert flight is not None
                flight["event"].set()
                _HISTORY_STATUS_FLIGHTS.pop(key, None)


def _history_status_unlocked(
    *, runtime: Path | None = None, delta_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    runtime = (runtime or runtime_path()).resolve()
    delta_path = delta_path or DELTA_PATH
    now = now or datetime.now(timezone.utc)
    marker_path = runtime / "history-import.json"
    marker = read_json_object(marker_path)
    reasons: list[str] = []
    warnings: list[str] = []
    if not marker:
        return {
            "schema": 1, "status": "blocked-diverged", "authority": "wavelog",
            "historical_novelty_allowed": False,
            "reasons": ["attested-wavelog-snapshot-missing"],
            "snapshot": None, "deltas": {"count": len(_delta_records(delta_path))},
        }

    required_identity = {
        "schema": marker.get("schema") == 1,
        "provider": marker.get("provider") == "mshv_auto_dx",
        "applied": marker.get("applied") is True,
        "canonical_source": marker.get("canonical_source") == CANONICAL_SOURCE,
        "production_policy": marker.get("production_policy") == PRODUCTION_POLICY,
        "station": str(marker.get("station_callsign") or "").upper() == "OM0RX",
        "coverage": marker.get("tracker_coverage_verified") is True,
        "record_counts": int(marker.get("records") or -1) > 0 and marker.get("records") == marker.get("native_records"),
    }
    reasons.extend(f"snapshot-{name}-invalid" for name, valid in required_identity.items() if not valid)
    canonical_hash = str(marker.get("canonical_sha256") or "").lower()
    if not HASH_RE.fullmatch(canonical_hash) or canonical_hash != str(marker.get("adif_sha256") or "").lower():
        reasons.append("snapshot-canonical-hash-invalid")

    stores = {
        "native": (runtime / "log/mshvlog.edim", str(marker.get("native_sha256") or "").lower()),
        "adif": (runtime / "log/mshvlog.adi", str(marker.get("adif_sha256") or "").lower()),
    }
    store_checks: dict[str, bool] = {}
    for name, (path, expected) in stores.items():
        valid = bool(HASH_RE.fullmatch(expected)) and path.is_file() and _sha(path) == expected
        store_checks[name] = valid
        if not valid:
            warnings.append(f"derived-{name}-evolved-from-snapshot")
    tracker_path = runtime / "settings/database/worked.db"
    tracker_expected = str(marker.get("tracker_sha256") or "").lower()
    tracker_actual = _sha(tracker_path) if tracker_path.is_file() else ""
    tracker_baseline = bool(HASH_RE.fullmatch(tracker_expected)) and tracker_actual == tracker_expected

    source = Path(str(marker.get("source") or ""))
    source_available = source.is_file()
    source_matches = source_available and _sha(source) == canonical_hash
    if source_available and not source_matches:
        reasons.append("canonical-source-hash-drift")
    provenance_hash = str(marker.get("provenance_report_sha256") or "").lower()
    if not HASH_RE.fullmatch(provenance_hash):
        reasons.append("snapshot-provenance-not-embedded")
    provenance_path = source.with_suffix(source.suffix + ".report.json")
    if source_available:
        provenance_matches = provenance_path.is_file() and _sha(provenance_path) == provenance_hash
        if not provenance_matches:
            reasons.append("canonical-provenance-diverged")
    else:
        provenance_matches = None
    if not source_available:
        # Temporary source/Wavelog outage is allowed only for a self-contained,
        # previously attested snapshot.  No network lookup is required here.
        source_matches = bool(HASH_RE.fullmatch(provenance_hash))

    imported = _utc(marker.get("imported_utc"))
    age_seconds = max(0.0, (now - imported).total_seconds()) if imported else None
    if imported is None:
        reasons.append("snapshot-import-time-invalid")

    delta_journal_error = None
    journal = {"next_sequence": 1, "records": {}, "pending": {}}
    try:
        journal = _delta_journal(delta_path, strict=True)
        deltas = journal["records"]
        pending_deltas = journal["pending"]
    except ValueError as exc:
        deltas = {}
        pending_deltas = {}
        delta_journal_error = str(exc)
        reasons.append("acknowledged-delta-journal-invalid")
    delta_invalid = [
        key for key, row in deltas.items()
        if not isinstance(row, dict)
        or not _valid_mshv_identity(row)
        or row.get("key") != key
        or not HASH_RE.fullmatch(str(key))
        or row.get("source_authority") != "wavelog_acknowledged"
        or not str(row.get("provider") or "").strip()
        or str(row.get("station_callsign") or "").upper() != "OM0RX"
        or not str(row.get("client_id") or "").strip()
        or not HASH_RE.fullmatch(str(row.get("event_id") or ""))
        or str(row.get("mode") or "").upper() not in {"FT8", "FT4"}
        or not HASH_RE.fullmatch(str(row.get("adif_sha256") or ""))
        or not _positive_int(row.get("receipt_count"))
        or not _positive_int(row.get("sequence"))
        or not str(row.get("call") or "").strip()
        or not str(row.get("qso_date") or "").isdigit()
        or len(str(row.get("qso_date") or "")) != 8
        or not str(row.get("time_on") or "").isdigit()
        or len(str(row.get("time_on") or "")) != 6
        or not str(row.get("time_off") or "").isdigit()
        or len(str(row.get("time_off") or "")) != 6
        or str(row.get("band") or "").lower() not in {
            "160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m",
        }
        or not _positive_int(row.get("frequency_hz"))
        or str(row.get("band") or "").lower() != _band_from_hz(row.get("frequency_hz"))
        or _utc(row.get("first_acknowledged_utc")) is None
        or _utc(row.get("last_acknowledged_utc")) is None
        or row.get("outcome") not in {"wavelog", "outbox-replay", "duplicate", "source-reconciled"}
        or row.get("lifecycle_state") not in {"acknowledged", "readback_verified"}
    ]
    ordered_deltas = sorted(deltas.values(), key=lambda row: _integer_or_zero(row.get("sequence")))
    expected_previous = "0" * 64
    for expected_sequence, row in enumerate(ordered_deltas, 1):
        entry_hash = str(row.get("entry_hash") or "")
        content = {key: value for key, value in row.items() if key != "entry_hash"}
        calculated = hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if (_integer_or_zero(row.get("sequence")) != expected_sequence
                or row.get("previous_hash") != expected_previous
                or not HASH_RE.fullmatch(entry_hash)
                or entry_hash != calculated):
            delta_invalid.append(str(row.get("key") or f"sequence-{expected_sequence}"))
        expected_previous = entry_hash
    if journal.get("next_sequence") != len(ordered_deltas) + 1:
        delta_invalid.append("next-sequence")
    delta_invalid = sorted(set(delta_invalid))
    if delta_invalid:
        reasons.append("unacknowledged-live-delta")
    pending_invalid = [
        key for key, row in pending_deltas.items()
        if not isinstance(row, dict)
        or not _valid_mshv_identity(row)
        or row.get("key") != key
        or not HASH_RE.fullmatch(str(key))
        or row.get("source_authority") != "wavelog_outbox_pending"
        or row.get("lifecycle_state") != "pending"
        or row.get("provider") != "mshv_auto_dx"
        or str(row.get("station_callsign") or "").upper() != "OM0RX"
        or not str(row.get("client_id") or "").strip()
        or not HASH_RE.fullmatch(str(row.get("event_id") or ""))
        or not str(row.get("call") or "").strip()
        or str(row.get("mode") or "").upper() not in {"FT8", "FT4"}
        or not _positive_int(row.get("frequency_hz"))
        or str(row.get("band") or "").lower() not in {
            "160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m",
        }
        or not HASH_RE.fullmatch(str(row.get("adif_sha256") or ""))
        or _utc(row.get("first_queued_utc")) is None
        or _utc(row.get("last_queued_utc")) is None
    ]
    if pending_invalid:
        reasons.append("pending-outbox-identity-invalid")
    active_deltas = {
        key: row for key, row in deltas.items()
        if imported is None or (_utc(row.get("first_acknowledged_utc")) or datetime.min.replace(tzinfo=timezone.utc)) > imported
    }
    active_keys = set(active_deltas)
    active_sequences = sorted(_integer_or_zero(row.get("sequence")) for row in active_deltas.values())
    delta_base_sequence = (active_sequences[0] - 1) if active_sequences else max(
        (_integer_or_zero(row.get("sequence")) for row in ordered_deltas), default=0,
    )
    state_path = runtime / "settings/database/wavelog_delta_state.json"
    state = read_json_object(state_path)
    state_keys = set(str(key) for key in state.get("applied_keys", [])) if isinstance(state.get("applied_keys"), list) else set()
    ledger_keys, ledger_error = _tracker_delta_ledger(tracker_path)
    if ledger_error:
        reasons.append(f"derived-tracker-{ledger_error}")

    # Report the exact recoverable crash boundary, but never repair it from a
    # GET/status path. Applying recovery is reserved for the explicit,
    # stopped-engine reconciliation POST.
    active_order = [row.get("key") for row in ordered_deltas if row.get("key") in active_keys]
    ledger_prefix = set(active_order[:len(ledger_keys)]) == ledger_keys
    recovery_available = bool(
        not ledger_error and ledger_keys != state_keys and ledger_prefix
        and state_keys.issubset(ledger_keys)
    )
    if recovery_available:
        warnings.append("delta-state-recovery-available-via-stopped-engine-post")

    state_valid = bool(
        state.get("schema") == 1
        and state.get("snapshot_generation") == canonical_hash
        and state_keys.issubset(active_keys)
        and state_keys == ledger_keys
        and (not ledger_error)
        and ledger_prefix
        and str(state.get("tracker_sha256") or "").lower() == tracker_actual
        and _integer_or_zero(state.get("last_sequence")) == max(
            (_integer_or_zero(active_deltas[key].get("sequence")) for key in state_keys),
            default=delta_base_sequence,
        )
    )
    tracker_valid = tracker_baseline if not state_keys else state_valid
    store_checks["tracker"] = tracker_valid
    if not tracker_valid:
        reasons.append("derived-tracker-diverged")

    valid = not reasons and source_matches
    status = ("offline-attested" if valid and not source_available
              else ("healthy" if valid else "blocked-diverged"))
    return {
        "schema": 1,
        "status": status,
        "authority": "wavelog",
        "historical_novelty_allowed": valid,
        "outage_policy": "last-attested-snapshot-plus-acknowledged-deltas" if valid else "block-historical-novelty",
        "reasons": reasons,
        "warnings": warnings,
        "derived_logs_policy": {
            "authoritative": False,
            "used_for_historical_novelty": False,
            "recovery_eligible": False,
            "reason": "MSHV native/ADIF logs may lead Wavelog while uploads are pending",
        },
        "snapshot": {
            "schema": marker.get("schema"),
            "station_callsign": marker.get("station_callsign"),
            "station_id": marker.get("configured_station_id"),
            "records": marker.get("records"),
            "canonical_sha256": canonical_hash,
            "imported_utc": marker.get("imported_utc"),
            "age_seconds": age_seconds,
            "source_available": source_available,
            "source_matches": source_matches,
            "provenance_matches": provenance_matches,
            "store_checks": store_checks,
            "generation": canonical_hash,
            "delta_state": {
                "path": str(state_path),
                "valid": state_valid,
                "applied": len(state_keys),
                "last_sequence": state.get("last_sequence", 0),
                "recovery_available": recovery_available,
                "ledger_applied": len(ledger_keys),
            },
            "backup": marker.get("backup"),
            "idempotent_rebuild": True,
        },
        "deltas": {
            "schema": 1,
            "base_sequence": delta_base_sequence,
            "count": len(active_deltas),
            "total_journal_records": len(deltas),
            "invalid": delta_invalid,
            "pending_invalid": sorted(pending_invalid),
            "journal_error": delta_journal_error,
            "pending_outbox": len(pending_deltas),
            "pending_keys": sorted(pending_deltas),
            "pending_records": [
                {
                    "key": key,
                    "call": str(row.get("call") or "").upper(),
                    "band": str(row.get("band") or "").lower(),
                    "frequency_hz": _integer_or_zero(row.get("frequency_hz")),
                    "mode": str(row.get("mode") or "").upper(),
                    "grid": str(row.get("grid") or "").upper(),
                    "qso_date": str(row.get("qso_date") or ""),
                    "time_on": str(row.get("time_on") or ""),
                    "time_off": str(row.get("time_off") or ""),
                    "provider": str(row.get("provider") or ""),
                    "client_id": str(row.get("client_id") or ""),
                    "event_id": str(row.get("event_id") or ""),
                }
                for key, row in sorted(pending_deltas.items())
                if isinstance(row, dict)
            ],
            "latest_acknowledged_utc": max(
                (str(row.get("last_acknowledged_utc") or "") for row in active_deltas.values()),
                default=None,
            ),
            "acknowledged_records": [
                {
                    **row,
                    "lifecycle_state": "native_applied" if row.get("key") in ledger_keys
                    else row.get("lifecycle_state"),
                }
                for row in sorted(
                    active_deltas.values(), key=lambda item: _integer_or_zero(item.get("sequence")),
                )
            ],
        },
    }
