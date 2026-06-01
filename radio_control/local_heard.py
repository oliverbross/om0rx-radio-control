"""Correlate DX/RBL spots with stations decoded locally."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from services.digital_automation import extract_callsign


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _message_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "to_dict"):
        return dict(message.to_dict())
    if isinstance(message, Mapping):
        return dict(message)
    return {
        "timestamp": getattr(message, "timestamp", None),
        "message": getattr(message, "message", ""),
        "snr": getattr(message, "snr", None),
        "mode": getattr(message, "mode", ""),
    }


def decoded_call(message: Mapping[str, Any], mycall: str = "") -> str:
    return extract_callsign(message, mycall=mycall).upper()


def correlate_local_heard(
    spot: dict[str, Any],
    decoded_messages: Iterable[Any],
    *,
    mycall: str = "",
    window_seconds: int = 600,
) -> dict[str, Any]:
    """Annotate a spot if its callsign was decoded locally recently."""
    callsign = str(spot.get("callsign") or "").upper()
    if not callsign:
        return spot

    now = datetime.now(timezone.utc)
    best_match: dict[str, Any] | None = None
    best_timestamp: datetime | None = None

    for raw in decoded_messages or []:
        message = _message_dict(raw)
        if decoded_call(message, mycall=mycall) != callsign:
            continue
        decoded_at = _parse_timestamp(message.get("timestamp") or message.get("decoded_at") or message.get("time"))
        if decoded_at and (now - decoded_at).total_seconds() > window_seconds:
            continue
        if best_timestamp is not None and decoded_at is not None and decoded_at <= best_timestamp:
            continue
        best_match = message
        best_timestamp = decoded_at

    if best_match:
        spot["local_heard"] = True
        spot["local_heard_message"] = best_match.get("message", "")
        spot["local_heard_snr"] = best_match.get("snr")
        spot["local_heard_at"] = best_timestamp.isoformat() if best_timestamp else None
        spot["local_heard_mode"] = best_match.get("mode")
    else:
        spot.setdefault("local_heard", False)

    return spot
