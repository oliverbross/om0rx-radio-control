"""Publish portable-award metadata for the native MSHV planner.

The sidecar is advisory and read-only.  It correlates fresh POTA, SOTA and
WWFF activations with exact reference/band/mode history, while native MSHV
retains sole authority for local-decode gating, target selection and TX.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

import duckdb

from radio_control import config
from radio_control.activity_references import extract_activity_references, normalize_activity_reference
from radio_control.postgres_store import connect as connect_postgres
from radio_control.postgres_store import should_use_postgres
from radio_control.persistence import atomic_write_json, locked_file, read_json_object
from services.mshv_cluster_watch import band_for_frequency


SCHEMA_VERSION = 1
WATCH_RELATIVE_PATH = Path("settings/database/award_hunting.json")
AWARD_DELTA_PATH = Path(__file__).resolve().parents[1] / "logs/mshv_award_history_deltas.json"
SUPPORTED_PROGRAMS = {"POTA", "SOTA", "WWFF"}
CALL_RE = re.compile(r"^[A-Z0-9/]{3,16}$")


def _utc(value: datetime | None = None) -> datetime:
    value = value or datetime.now(UTC)
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if not value:
        return None
    try:
        return _utc(datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _normalize_call(value: Any) -> str:
    call = str(value or "").strip().upper()
    return call if CALL_RE.fullmatch(call) else ""


def _base_call(value: Any) -> str:
    """Collapse portable/prefix variants into one operator identity."""
    call = _normalize_call(value)
    if not call:
        return ""
    parts = [part for part in call.split("/") if part]
    candidates = [
        part for part in parts
        if any(ch.isalpha() for ch in part) and any(ch.isdigit() for ch in part)
        and part not in {"P", "M", "MM", "AM", "QRP"}
    ]
    if not candidates:
        return call
    # Prefix and portable suffixes are normally shorter than the licensed
    # callsign. Stable first-position tie-breaking keeps this deterministic.
    return max(candidates, key=len)


def _normalize_mode(value: Any) -> str:
    mode = str(value or "").strip().upper().replace(" ", "")
    return "FT8" if mode in {"FT8", "MFSK/FT8", "MFSK+FT8"} else mode


def _canonical_adif_mode(row: dict[str, Any]) -> str:
    return _normalize_mode(row.get("submode") or row.get("mode"))


def _normalize_band(value: Any) -> str:
    band = str(value or "").strip().lower().replace("meters", "m").replace("meter", "m")
    if band.isdigit():
        band += "m"
    return band


def _program_for_reference(program: Any, reference: Any) -> tuple[str, str]:
    program_text = str(program or "").strip().upper()
    if program_text == "PARKSNPEAKS":
        for candidate in ("SOTA", "WWFF", "POTA"):
            normalized = normalize_activity_reference(candidate, reference)
            if normalized[0]:
                return normalized
        return "", ""
    return normalize_activity_reference(program_text, reference)


def _history_key(program: str, reference: str, band: str = "", mode: str = "") -> tuple[str, str, str, str]:
    return (program.upper(), reference.upper(), _normalize_band(band), _normalize_mode(mode))


def build_reference_history_index(rows: Iterable[dict[str, Any]]) -> set[tuple[str, str, str, str]]:
    """Return exact portable award slots plus overall/band roll-ups."""
    index: set[tuple[str, str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        band = _normalize_band(row.get("band"))
        mode = _canonical_adif_mode(row)
        for item in extract_activity_references(row):
            normalized_program, normalized_reference = _program_for_reference(
                item.get("type"), item.get("reference_id"),
            )
            if normalized_program not in SUPPORTED_PROGRAMS:
                continue
            index.add(_history_key(normalized_program, normalized_reference))
            if band:
                index.add(_history_key(normalized_program, normalized_reference, band))
            if band and mode:
                index.add(_history_key(normalized_program, normalized_reference, band, mode))
    return index


def _award_delta_key(program: str, reference: str, band: str, mode: str) -> str:
    identity = {"program": program, "reference": reference, "band": band, "mode": mode}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def record_acknowledged_award_qso(
    qso_data: dict[str, Any], *, path: str | Path | None = None,
) -> dict[str, Any]:
    """Durably retain portable award slots until the canonical mirror catches up."""
    path = Path(path or AWARD_DELTA_PATH)
    band = _normalize_band(qso_data.get("band"))
    mode = _canonical_adif_mode(qso_data)
    if not band or not mode:
        return {"recorded": False, "reason": "award-slot-incomplete", "keys": []}
    identities = []
    for item in extract_activity_references(qso_data):
        program, reference = _program_for_reference(item.get("type"), item.get("reference_id"))
        if program in SUPPORTED_PROGRAMS:
            identities.append((program, reference))
    if not identities:
        return {"recorded": False, "reason": "no-supported-award-reference", "keys": []}

    now = _iso(datetime.now(UTC))
    with locked_file(path):
        journal = read_json_object(path)
        if journal and (journal.get("schema") != 1 or not isinstance(journal.get("records"), dict)):
            raise ValueError("Portable award delta journal is invalid")
        records = dict(journal.get("records") or {})
        keys: list[str] = []
        for program, reference in sorted(set(identities)):
            key = _award_delta_key(program, reference, band, mode)
            previous = records.get(key) if isinstance(records.get(key), dict) else {}
            records[key] = {
                "key": key,
                "program": program,
                "reference": reference,
                "band": band,
                "mode": mode,
                "source_authority": "wavelog_acknowledged",
                "first_acknowledged_utc": previous.get("first_acknowledged_utc") or now,
                "last_acknowledged_utc": now,
            }
            keys.append(key)
        atomic_write_json(path, {"schema": 1, "records": records}, backup=False)
    return {"recorded": True, "keys": keys}


def merge_award_history_deltas(
    history_rows: Iterable[dict[str, Any]],
    *,
    path: str | Path | None = None,
    retire_mirrored: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge durable acknowledgements and retire only exact mirrored slots."""
    rows = [dict(row) for row in history_rows if isinstance(row, dict)]
    path = Path(path or AWARD_DELTA_PATH)
    if not path.exists():
        return rows, {"valid": True, "pending": 0, "retired": 0, "path": str(path)}
    # Keep read/merge/retire under the same path lock.  Otherwise an
    # acknowledgement arriving between the initial read and retirement could
    # be overwritten and lost.
    with locked_file(path):
        journal = read_json_object(path)
        if journal.get("schema") != 1 or not isinstance(journal.get("records"), dict):
            return rows, {"valid": False, "pending": 0, "retired": 0, "path": str(path), "error": "journal-invalid"}

        mirror = build_reference_history_index(rows)
        remaining: dict[str, dict[str, Any]] = {}
        supplemental: list[dict[str, Any]] = []
        retired = 0
        for key, raw in journal["records"].items():
            if not isinstance(raw, dict):
                return rows, {"valid": False, "pending": 0, "retired": 0, "path": str(path), "error": "record-invalid"}
            program, reference = _program_for_reference(raw.get("program"), raw.get("reference"))
            band = _normalize_band(raw.get("band"))
            mode = _normalize_mode(raw.get("mode"))
            expected_key = _award_delta_key(program, reference, band, mode) if program and band and mode else ""
            if (
                not expected_key or key != expected_key or raw.get("key") != key
                or raw.get("source_authority") != "wavelog_acknowledged"
                or not _parse_time(raw.get("first_acknowledged_utc"))
            ):
                return rows, {"valid": False, "pending": 0, "retired": 0, "path": str(path), "error": "record-invalid"}
            exact = _history_key(program, reference, band, mode)
            if retire_mirrored and exact in mirror:
                retired += 1
                continue
            remaining[key] = raw
            field = {"POTA": "pota_ref", "SOTA": "sota_ref", "WWFF": "wwff_ref"}[program]
            supplemental.append({
                "band": band, "mode": mode, "submode": mode,
                field: reference, "sig": program, "sig_info": reference, "comment": "",
            })
        if retired:
            atomic_write_json(path, {"schema": 1, "records": remaining}, backup=False)
    return [*rows, *supplemental], {
        "valid": True,
        "pending": len(remaining),
        "retired": retired,
        "path": str(path),
    }


def build_award_hunting_watch(
    activations: Iterable[dict[str, Any]],
    *,
    history_rows: Iterable[dict[str, Any]] = (),
    now: datetime | None = None,
    max_activation_age_seconds: int = 900,
    watch_max_age_seconds: int = 3600,
    enabled_programs: Iterable[str] = SUPPORTED_PROGRAMS,
    history_authoritative: bool = True,
    history_authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, bounded activation-to-award-gap contract."""
    current = _utc(now)
    max_age = max(60, min(int(max_activation_age_seconds), 86400))
    watch_age = max(300, min(int(watch_max_age_seconds), 86400))
    enabled = {str(program).strip().upper() for program in enabled_programs} & SUPPORTED_PROGRAMS
    history = build_reference_history_index(history_rows)
    newest_by_operation: dict[str, dict[str, Any]] = {}

    for activation in activations:
        if not isinstance(activation, dict):
            continue
        if str(activation.get("type") or "ACTIVE_SPOT").upper() != "ACTIVE_SPOT":
            continue
        call = _normalize_call(activation.get("activator_call") or activation.get("callsign"))
        base_call = _base_call(call)
        if not call or not base_call:
            continue
        seen = _parse_time(activation.get("last_seen_utc") or activation.get("spotted_at_utc"))
        if seen is None or seen > current or (current - seen).total_seconds() > max_age:
            continue
        expires = _parse_time(activation.get("expires_utc") or activation.get("end_utc"))
        if expires is not None and expires < current:
            continue
        mode = _canonical_adif_mode(activation)
        if mode and mode != "FT8":
            continue
        mode = "FT8"
        try:
            frequency_hz = int(round(float(activation.get("frequency_khz") or 0) * 1000.0))
        except (TypeError, ValueError):
            frequency_hz = 0
        band = band_for_frequency(frequency_hz) if frequency_hz else _normalize_band(activation.get("band"))
        if not band:
            continue
        source_id = str(activation.get("source_id") or "").strip().upper()
        for raw_reference in activation.get("references") or []:
            program, reference = _program_for_reference(activation.get("program"), raw_reference)
            if program not in enabled:
                continue
            slot_key = f"{program}:{reference}@{band}@{mode}"
            operation_key = f"{base_call}|{slot_key}"
            overall_key = _history_key(program, reference)
            band_key = _history_key(program, reference, band)
            band_mode_key = _history_key(program, reference, band, mode)
            entry = {
                "callsign": call,
                "base_call": base_call,
                "program": program,
                "reference": reference,
                "band": band,
                "mode": mode,
                "frequency_hz": frequency_hz,
                "spotted_at_utc": _iso(seen),
                "expires_at_utc": _iso(expires) if expires else None,
                "source_id": source_id,
                "confidence": 1.0 if frequency_hz and source_id.startswith(program) else 0.9,
                "slot_key": slot_key,
                "history_status": "authoritative" if history_authoritative else "unavailable",
                "gaps": {
                    # Unknown history fails closed.  A native planner must not
                    # turn a database outage into repeated award QSOs.
                    "new_reference": history_authoritative and overall_key not in history,
                    "new_reference_on_band": history_authoritative and band_key not in history,
                    "new_reference_on_band_mode": history_authoritative and band_mode_key not in history,
                },
            }
            previous = newest_by_operation.get(operation_key)
            if previous is None or entry["spotted_at_utc"] > previous["spotted_at_utc"]:
                newest_by_operation[operation_key] = entry

    entries = sorted(
        newest_by_operation.values(),
        key=lambda item: (item["base_call"], item["program"], item["reference"], item["band"], item["mode"]),
    )
    return {
        "schema": SCHEMA_VERSION,
        "generated_at_utc": _iso(current),
        "watch_max_age_seconds": watch_age,
        "max_activation_age_seconds": max_age,
        "history_authoritative": bool(history_authoritative),
        "history_authority": history_authority or {
            "status": "authoritative" if history_authoritative else "unavailable",
        },
        "enabled_programs": sorted(enabled),
        "activations": entries,
    }


def _portable_history_rows(qso_db_path: str | Path | None = None) -> tuple[list[dict[str, Any]], bool]:
    columns = (
        "band", "mode", "submode", "pota_ref", "sota_ref", "wwff_ref",
        "sig", "sig_info", "comment",
    )
    sql = f"SELECT {', '.join(columns)} FROM qso_records WHERE " + " OR ".join(
        f"coalesce({name}, '') <> ''" for name in columns[3:]
    )
    try:
        if qso_db_path is None and should_use_postgres():
            with connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
        else:
            path = Path(qso_db_path) if qso_db_path is not None else config.DATA_DIR / "qso_log.duckdb"
            if not path.exists():
                return [], False
            conn = duckdb.connect(str(path), read_only=True)
            try:
                rows = conn.execute(sql).fetchall()
            finally:
                conn.close()
    except Exception:
        # Missing legacy columns must never prevent publication.  The safe
        # result treats slots as needed until the canonical QSO cache exists.
        return [], False
    return [dict(zip(columns, row, strict=True)) for row in rows], True


def write_award_hunting_watch(
    path: str | Path, activations: Iterable[dict[str, Any]], **kwargs: Any,
) -> dict[str, Any]:
    path = Path(path)
    payload = build_award_hunting_watch(activations, **kwargs)
    existing = read_json_object(path)
    if existing.get("schema") == SCHEMA_VERSION:
        comparable_existing = {key: value for key, value in existing.items() if key != "generated_at_utc"}
        comparable_payload = {key: value for key, value in payload.items() if key != "generated_at_utc"}
        generated = _parse_time(existing.get("generated_at_utc"))
        renewal_seconds = max(60, int(payload["watch_max_age_seconds"]) // 2)
        if (
            comparable_existing == comparable_payload
            and generated is not None
            and (_utc(kwargs.get("now")) - generated).total_seconds() < renewal_seconds
        ):
            return existing
    atomic_write_json(path, payload, backup=False)
    return payload


def publish_repository_award_hunting_watch(
    repository: Any,
    runtime_path: str | Path,
    *,
    qso_db_path: str | Path | None = None,
    history_attestation: dict[str, Any] | None = None,
    additional_history_rows: Iterable[dict[str, Any]] = (),
    award_delta_path: str | Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    runtime = Path(runtime_path)
    target = runtime / WATCH_RELATIVE_PATH
    if history_attestation is None:
        try:
            from services.mshv_history import history_status

            history_attestation = history_status(runtime=runtime)
        except Exception as exc:
            history_attestation = {
                "status": "unavailable",
                "historical_novelty_allowed": False,
                "reasons": [f"attestation-error:{type(exc).__name__}"],
            }
    generated = _parse_time(history_attestation.get("generated_at"))
    max_age = max(1, int(history_attestation.get("max_age_seconds") or 10))
    now = _utc(kwargs.get("now"))
    attestation_fresh = bool(
        generated is not None
        and generated <= now
        and (now - generated).total_seconds() <= max_age
    )
    deltas = history_attestation.get("deltas") if isinstance(history_attestation.get("deltas"), dict) else {}
    history_rows, cache_available = _portable_history_rows(qso_db_path)
    history_rows, award_deltas = merge_award_history_deltas(
        history_rows,
        path=award_delta_path,
        retire_mirrored=cache_available,
    )
    history_rows.extend(row for row in additional_history_rows if isinstance(row, dict))
    history_authoritative = bool(
        cache_available
        and attestation_fresh
        and history_attestation.get("historical_novelty_allowed") is True
        and history_attestation.get("status") in {"healthy", "offline-attested"}
        and not deltas.get("invalid")
        and not deltas.get("pending_invalid")
        and not deltas.get("journal_error")
        and award_deltas.get("valid") is True
    )
    authority_summary = {
        "status": history_attestation.get("status") or "unavailable",
        "fresh": attestation_fresh,
        "cache_available": cache_available,
        "snapshot_generation": (
            (history_attestation.get("snapshot") or {}).get("generation")
            if isinstance(history_attestation.get("snapshot"), dict) else None
        ),
        "acknowledged_delta_count": int(deltas.get("count") or 0),
        "pending_outbox_count": int(deltas.get("pending_outbox") or 0),
        "latest_acknowledged_utc": deltas.get("latest_acknowledged_utc"),
        "award_delta_pending": int(award_deltas.get("pending") or 0),
        "award_delta_retired": int(award_deltas.get("retired") or 0),
        "award_delta_journal_valid": award_deltas.get("valid") is True,
        "reasons": [
            *list(history_attestation.get("reasons") or []),
            *([] if award_deltas.get("valid") is True else [str(award_deltas.get("error") or "award-delta-journal-invalid")]),
        ],
    }
    payload = write_award_hunting_watch(
        target,
        repository.portable_activations(limit=1000),
        history_rows=history_rows,
        history_authoritative=history_authoritative,
        history_authority=authority_summary,
        **kwargs,
    )
    return {"path": str(target), "watch": payload}


def invalidate_award_hunting_watch(
    runtime_path: str | Path, *, reason: str, now: datetime | None = None,
) -> dict[str, Any] | None:
    """Fail closed before an authoritative history generation changes."""
    target = Path(runtime_path) / WATCH_RELATIVE_PATH
    payload = read_json_object(target)
    if payload.get("schema") != SCHEMA_VERSION:
        return None
    current = _utc(now)
    invalidated = {
        **payload,
        "generated_at_utc": _iso(current),
        "history_authoritative": False,
        "history_authority": {"status": "invalidated", "fresh": True, "reasons": [reason]},
        "activations": [
            {
                **entry,
                "history_status": "unavailable",
                "gaps": {
                    "new_reference": False,
                    "new_reference_on_band": False,
                    "new_reference_on_band_mode": False,
                },
            }
            for entry in payload.get("activations") or []
            if isinstance(entry, dict)
        ],
    }
    atomic_write_json(target, invalidated, backup=False)
    return invalidated


def republish_after_authoritative_history_change(
    reason: str, *, acknowledged_qso: dict[str, Any] | None = None,
    acknowledged_qsos: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Invalidate then rebuild after a Wavelog acknowledgement/reconciliation."""
    from activity_intelligence.services import get_activity_intelligence_service
    from services.mshv_configuration import read_mshv_auto_dx_settings, runtime_path

    runtime = runtime_path()
    invalidate_award_hunting_watch(runtime, reason=reason)
    supplemental = [row for row in acknowledged_qsos if isinstance(row, dict)]
    if acknowledged_qso:
        supplemental.append(acknowledged_qso)
    try:
        service = get_activity_intelligence_service()
        policy = read_mshv_auto_dx_settings(engine_running=False)["reference_hunting"]
        enabled_programs = [
            program for program in ("POTA", "SOTA", "WWFF")
            if policy.get(f"{program.lower()}_enabled", True)
        ] if policy.get("enabled", True) else []
        return publish_repository_award_hunting_watch(
            service.repository,
            runtime,
            qso_db_path=service.qso_db_path if service._explicit_qso_db_path else None,
            additional_history_rows=supplemental,
            max_activation_age_seconds=policy["max_activation_age_seconds"],
            enabled_programs=enabled_programs,
        )
    except Exception as exc:
        return {"path": str(runtime / WATCH_RELATIVE_PATH), "invalidated": True, "error": str(exc)}
