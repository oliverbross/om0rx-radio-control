"""Read-only AutoDX status shaping plus future-event daily summaries.

No radio or native-engine control lives here. The persistence hooks run only
when a later telemetry/QSO event reaches the backend; importing this module
does not inspect or mutate a running station.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from radio_control.persistence import atomic_write_json, read_json_object


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "logs" / "mshv_autodx_daily_summaries.json"
_LOCK = RLock()

STATUS_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "selection_id": "",
    "target": None,
    "selection_reason": "",
    "selection_class": "",
    "selection_score": 0,
    "attempt": 0,
    "budget": {"call_window_seconds": 120, "max_consecutive_windows": 1, "total_seconds": 120, "elapsed_seconds": 0, "remaining_seconds": 0},
    "next_retry": {"call": "", "utc": None, "remaining_seconds": None},
    "band_dwell": {"minimum_seconds": 180, "elapsed_seconds": 0, "remaining_seconds": 0, "next_qsy_utc": None},
    "active_schedule": None,
    "skipped_reasons": [],
    "last_directed_caller": None,
    "audit": {"event_counter": 0, "last_event": None},
    "dxpedition_catalog": {"valid": False, "entries": 0, "mtime_utc": None, "expires_utc": None},
}


def normalize_status(value: Any, *, fresh: bool) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    result = {**STATUS_DEFAULTS, **raw}
    result["fresh"] = bool(fresh)
    result["reported"] = bool(raw)
    result["skipped_reasons"] = [
        str(item) for item in (result.get("skipped_reasons") or []) if str(item).strip()
    ][-20:]
    for key in ("budget", "next_retry", "band_dwell", "audit", "dxpedition_catalog"):
        nested = result.get(key) if isinstance(result.get(key), dict) else {}
        result[key] = {**STATUS_DEFAULTS[key], **nested}
    return result


def _day(value: Any = None) -> str:
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo:
                return parsed.astimezone(timezone.utc).date().isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).date().isoformat()


def _payload(path: Path) -> dict[str, Any]:
    value = read_json_object(path)
    if value.get("schema") != 1 or not isinstance(value.get("days"), dict):
        return {"schema": 1, "days": {}}
    return value


def record_selection(status: dict[str, Any], *, path: Path = SUMMARY_PATH) -> None:
    selection_id = str(status.get("selection_id") or "").strip()
    target = status.get("target") if isinstance(status.get("target"), dict) else {}
    call = str(target.get("call") or status.get("target_call") or "").strip().upper()
    schedule = status.get("active_schedule") if isinstance(status.get("active_schedule"), dict) else {}
    band = str(schedule.get("band") or target.get("band") or target.get("band_index") or "").strip().lower()
    if not selection_id or not call:
        return
    with _LOCK:
        payload = _payload(path)
        day = _day(status.get("selected_at") or status.get("timestamp"))
        row = payload["days"].setdefault(day, {
            "bands": {}, "targets": {}, "qsos": 0,
            "selection_ids": [], "qso_event_ids": [],
        })
        if selection_id in row["selection_ids"]:
            return
        row["selection_ids"].append(selection_id)
        row["targets"][call] = int(row["targets"].get(call, 0)) + 1
        if band:
            row["bands"][band] = int(row["bands"].get(band, 0)) + 1
        atomic_write_json(path, payload)


def record_qso(identity: dict[str, Any], *, path: Path = SUMMARY_PATH) -> None:
    event_id = str(identity.get("event_id") or "").strip().lower()
    if len(event_id) != 64:
        return
    with _LOCK:
        payload = _payload(path)
        day = _day(identity.get("last_acknowledged_utc"))
        row = payload["days"].setdefault(day, {
            "bands": {}, "targets": {}, "qsos": 0,
            "selection_ids": [], "qso_event_ids": [],
        })
        if event_id in row["qso_event_ids"]:
            return
        row["qso_event_ids"].append(event_id)
        row["qsos"] = int(row.get("qsos", 0)) + 1
        atomic_write_json(path, payload)


def daily_summaries(*, path: Path = SUMMARY_PATH, limit: int = 31) -> dict[str, Any]:
    with _LOCK:
        payload = _payload(path)
    days = [
        {"date": day, **row}
        for day, row in sorted(payload["days"].items(), reverse=True)[:max(1, min(limit, 366))]
    ]
    return {"success": True, "schema": 1, "days": days, "path": str(path)}
