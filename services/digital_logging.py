"""Durable provisional type-5 receipts; type-12 is the canonical write event.

Type 5 is never promoted to Wavelog by itself. It is an operational receipt
that survives restarts and raises an alert if authoritative type-12 ADIF does
not arrive. A type-12 event may retire exactly one matching receipt only after
the canonical log write has been durably accepted.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from fastapi import HTTPException

from radio_control.persistence import atomic_write_json, locked_file, read_json_object

PROVISIONAL_PATH = Path(__file__).resolve().parents[1] / "logs/digital_provisional_qsos.json"
STALE_SECONDS = 60
PAIR_SECONDS = 5
PAIR_FREQUENCY_HZ = 100


def provisional_records() -> dict:
    return read_json_object(PROVISIONAL_PATH).get("records", {})


def _utc(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _adif_identity(request: dict) -> dict:
    from scripts.digital.export_history import parse_adif

    rows = list(parse_adif(str(request.get("adif_text") or "")))
    if len(rows) != 1:
        raise HTTPException(400, "Logged ADIF event must contain exactly one complete QSO")
    row = rows[0]
    mode = str(row.get("SUBMODE") or row.get("MODE") or request.get("mode") or "").upper()
    date = "".join(character for character in str(row.get("QSO_DATE") or "") if character.isdigit())[:8]
    # Type-5 is emitted at completion, so correlate it to authoritative
    # TIME_OFF when present. TIME_ON remains part of the canonical Wavelog
    # delta identity in mshv_history.py.
    clock = "".join(character for character in str(
        row.get("TIME_OFF") or row.get("TIME_ON") or ""
    ) if character.isdigit())
    if len(clock) == 4:
        clock += "00"
    try:
        when = datetime.strptime(date + clock[:6], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        when = _utc(request.get("date_time"))
    frequency_hz = request.get("frequency_hz")
    if row.get("FREQ"):
        try:
            frequency_hz = float(row["FREQ"]) * 1_000_000
        except ValueError:
            pass
    return {
        "provider": str(request.get("provider") or ""),
        "station_callsign": str(request.get("station_callsign") or row.get("STATION_CALLSIGN") or "").upper(),
        "client_id": str(request.get("client_id") or ""),
        "event_id": str(request.get("event_id") or "").lower(),
        "call": str(row.get("CALL") or request.get("call") or "").upper(),
        "mode": mode,
        "frequency_hz": frequency_hz,
        "when": when,
    }


def _provisional_key(request: dict) -> str:
    event_id = str(request.get("event_id") or "").strip().lower()
    if event_id:
        return event_id
    identity = {field: request.get(field) for field in (
        "provider", "station_callsign", "call", "mode", "frequency_hz",
        "time_on", "time_off", "date_time",
    )}
    identity["call"] = str(identity.get("call") or "").upper()
    identity["mode"] = str(identity.get("mode") or "").upper()
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _pair_candidates(records: dict, identity: dict, now: datetime) -> list[str]:
    event_id = str(identity.get("event_id") or "").lower()
    if event_id and event_id in records:
        value = records[event_id]
        if all((
            str(value.get("provider") or "") == identity["provider"],
            str(value.get("station_callsign") or "").upper() == identity["station_callsign"],
            str(value.get("client_id") or "") == identity["client_id"],
        )):
            return [event_id]
    candidates: list[str] = []
    for key, value in records.items():
        if str(value.get("provider") or "") != identity["provider"]:
            continue
        if str(value.get("station_callsign") or "").upper() != identity["station_callsign"]:
            continue
        if str(value.get("client_id") or "") != identity["client_id"]:
            continue
        if str(value.get("call") or "").upper() != identity["call"]:
            continue
        if str(value.get("mode") or "").upper() != identity["mode"]:
            continue
        left = value.get("frequency_hz")
        right = identity.get("frequency_hz")
        if left and right and abs(float(left) - float(right)) > PAIR_FREQUENCY_HZ:
            continue
        pending_time = _utc(value.get("date_time"))
        if pending_time and identity.get("when"):
            if abs((pending_time - identity["when"]).total_seconds()) > PAIR_SECONDS:
                continue
        else:
            received = _utc(value.get("received_utc"))
            if not received or abs((now - received).total_seconds()) > PAIR_SECONDS:
                continue
        candidates.append(key)
    return candidates


def provisional_health(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    records = provisional_records()
    stale = []
    for key, row in records.items():
        received = _utc(row.get("received_utc"))
        if received and (now - received).total_seconds() > STALE_SECONDS:
            stale.append({"key": key, **row})
    return {
        "pending_authoritative_adif": len(records),
        "stale_pending": len(stale),
        "action_required": "Reconcile against authoritative MSHV ADIF or enable Logged ADIF UDP reporting" if stale else None,
        "records": list(records.values()),
        "stale_records": stale,
    }


async def log_digital_qso(request, logger_service):
    event_type = str(request.get("event_type") or "").upper()
    if event_type == "QSO_LOGGED":
        if not str(request.get("call") or "").strip():
            raise HTTPException(400, "Missing provisional callsign")
        key = _provisional_key(request)
        with locked_file(PROVISIONAL_PATH):
            records = provisional_records()
            previous = records.get(key, {})
            records[key] = {
                **request,
                "event_id": str(request.get("event_id") or key),
                "lifecycle_state": "type5_received",
                "received_utc": previous.get("received_utc") or datetime.now(timezone.utc).isoformat(),
                "last_seen_utc": datetime.now(timezone.utc).isoformat(),
                "receipt_count": int(previous.get("receipt_count", 0)) + 1,
            }
            atomic_write_json(PROVISIONAL_PATH, {"schema": 1, "records": records})
        return {"success": True, "provisional_queued": True, "message": "QSO receipt saved; waiting for authoritative ADIF", "provisional_key": key}

    if event_type != "LOGGED_ADIF":
        raise HTTPException(400, "Digital log event must be QSO_LOGGED or LOGGED_ADIF")
    identity = _adif_identity(request)
    now = datetime.now(timezone.utc)
    with locked_file(PROVISIONAL_PATH):
        records = provisional_records()
        candidates = _pair_candidates(records, identity, now)
        for key in candidates:
            records[key] = {**records[key], "lifecycle_state": "type12_paired"}
        if candidates:
            atomic_write_json(PROVISIONAL_PATH, {"schema": 1, "records": records})

    # This journal transition must be durable before the logger can enqueue an
    # offline outbox record.  A crash after enqueue can then be reconstructed,
    # and a crash before enqueue remains a visible inhibited/pending QSO.
    staged = {"pending": False, "reason": "not-mshv-provider"}
    if str(request.get("provider") or "") == "mshv_auto_dx":
        from services.mshv_history import stage_pending_delta
        try:
            staged = stage_pending_delta(request)
        except ValueError as exc:
            raise HTTPException(400, f"Invalid authoritative MSHV ADIF: {exc}") from exc
        if not staged.get("pending") and not staged.get("already_acknowledged"):
            raise HTTPException(409, staged.get("reason") or "Unable to durably stage MSHV QSO")

    result = await logger_service.log_qso(request)
    wavelog_result = result.get("wavelog") if isinstance(result.get("wavelog"), dict) else {}
    dedupe_result = result.get("dedupe") if isinstance(result.get("dedupe"), dict) else {}
    acknowledged = bool(
        wavelog_result.get("success")
        or dedupe_result.get("wavelog_success") is True
        or (result.get("readback_verified") is True and result.get("readback_identity_exact") is True)
    )
    pending_outbox = bool(result.get("success") and result.get("outbox_queued"))
    delta = {"recorded": False, "reason": "wavelog-not-durably-acknowledged"}
    if acknowledged:
        common_delta = wavelog_result.get("mshv_history_delta")
        if isinstance(common_delta, dict):
            delta = common_delta
        else:
            from services.mshv_history import record_acknowledged_delta
            delta = record_acknowledged_delta(request, result)
    elif pending_outbox:
        from services.mshv_history import record_pending_delta
        delta = record_pending_delta(request, result)
    if len(candidates) == 1 and not acknowledged:
        with locked_file(PROVISIONAL_PATH):
            current = provisional_records()
            if candidates[0] in current:
                current[candidates[0]]["lifecycle_state"] = "pending" if pending_outbox else "submitted"
                atomic_write_json(PROVISIONAL_PATH, {"schema": 1, "records": current})
    upgraded_key = None
    if acknowledged and len(candidates) == 1:
        upgraded_key = candidates[0]
        with locked_file(PROVISIONAL_PATH):
            current = provisional_records()
            current.pop(upgraded_key, None)
            atomic_write_json(PROVISIONAL_PATH, {"schema": 1, "records": current})
    return {
        **result,
        "provisional_upgrade": "matched" if upgraded_key else (
            "pending-outbox" if pending_outbox else ("ambiguous" if len(candidates) > 1 else "not-found")
        ),
        "provisional_key": upgraded_key,
        "provisional_candidates": len(candidates),
        "history_delta": delta,
        "history_pending_staged": staged,
    }


def acknowledge_outbox_resolution(adif_text: str) -> dict:
    """Resolve MSHV pending history/provisional state after Wavelog replay."""
    from services.mshv_history import acknowledge_outbox_delta

    delta = acknowledge_outbox_delta(adif_text)
    if not delta.get("recorded"):
        return {"history_delta": delta, "provisional_upgrade": "not-found"}
    request = {"event_type": "LOGGED_ADIF", "adif_text": adif_text}
    from radio_control.qso_outbox import QSOOutbox
    fields = QSOOutbox._adif_fields(adif_text)
    request.update({
        "provider": fields.get("app_om0rx_provider") or "",
        "station_callsign": fields.get("app_om0rx_station") or "",
        "client_id": fields.get("app_om0rx_client_id") or "",
        "event_id": fields.get("app_om0rx_event_id") or "",
    })
    identity = _adif_identity(request)
    now = datetime.now(timezone.utc)
    with locked_file(PROVISIONAL_PATH):
        records = provisional_records()
        candidates = _pair_candidates(records, identity, now)
        upgraded_key = candidates[0] if len(candidates) == 1 else None
        if upgraded_key:
            records.pop(upgraded_key, None)
            atomic_write_json(PROVISIONAL_PATH, {"schema": 1, "records": records})
    return {
        "history_delta": delta,
        "provisional_upgrade": "matched" if upgraded_key else (
            "ambiguous" if len(candidates) > 1 else "not-found"
        ),
        "provisional_key": upgraded_key,
        "provisional_candidates": len(candidates),
    }


async def reconcile_provisional(logger_service):
    """Recover one-to-one stale receipts only from MSHV's private live log.

    WSJT-Z ADIF is explicitly audit-only for this migration and can never feed
    production logging through this recovery path.
    """
    from services.digital_engine import ROOT, selected_provider
    from scripts.digital.export_history import parse_adif, serialize_records

    provider = selected_provider()
    if provider != "mshv_auto_dx":
        raise HTTPException(409, "WSJT ADIF is audit-only; provisional recovery requires authoritative UDP Logged ADIF")
    source = Path(os.environ.get("OM0RX_MSHV_RUNTIME", ROOT / "data/build/mshv-auto-dx/runtime")) / "log/mshvlog.adi"
    if not source.is_file():
        raise HTTPException(409, "Authoritative MSHV ADIF unavailable; pending receipts preserved")
    records = provisional_records()
    identities: dict[str, list[dict]] = {key: [] for key in records}
    text = await asyncio.to_thread(source.read_text, encoding="utf-8-sig")
    now = datetime.now(timezone.utc)
    for row in parse_adif(text):
        adif_text = serialize_records([row])
        # Recovery must retain the original type-5 correlation identity. Do
        # not synthesize an event/client/station identity from a native log.
        # Force the narrow call/time/frequency matcher first, then attach only
        # the already-durable metadata for the one provisional receipt.
        for key, provisional in records.items():
            payload = {
                "provider": provisional.get("provider") or provider,
                "station_callsign": provisional.get("station_callsign") or "",
                "client_id": provisional.get("client_id") or "",
                "event_id": provisional.get("event_id") or "",
                "call": row.get("CALL"),
                "mode": row.get("SUBMODE") or row.get("MODE"),
                "frequency_hz": provisional.get("frequency_hz"),
                "date_time": provisional.get("date_time"),
                "event_type": "LOGGED_ADIF",
                "adif_text": adif_text,
                "async_upload": True,
                "source": "mshv-provisional-recovery",
            }
            identity = _adif_identity(payload)
            identity["event_id"] = ""  # require content match, not key-only match
            if key in _pair_candidates({key: provisional}, identity, now):
                identities.setdefault(key, []).append(payload)
    recovered = 0
    ambiguous = 0
    for key, payloads in identities.items():
        if len(payloads) != 1:
            ambiguous += int(len(payloads) > 1)
            continue
        result = await log_digital_qso(payloads[0], logger_service)
        if result.get("provisional_upgrade") == "matched":
            recovered += 1
    health = provisional_health()
    return {"success": True, "recovered": recovered, "ambiguous": ambiguous, "remaining": health["pending_authoritative_adif"], **health}
