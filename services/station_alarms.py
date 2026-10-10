"""Normalize cached station evidence into read-only operator alarms."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping


_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _source_from_code(code: str) -> str:
    prefix = code.split("-", 1)[0].lower()
    return {"flex": "flex", "kpa": "kpa500", "kat": "kat500"}.get(
        prefix, "station-coordinator"
    )


def _guidance(code: str, source: str) -> str:
    if "fault" in code:
        return f"Keep transmission inhibited and inspect the {source.upper()} fault readback/manual."
    if "disconnect" in code:
        return f"Check {source.upper()} power, cable, and configured connection before transmitting."
    if "stale" in code or "unknown" in code:
        return "Wait for fresh telemetry and verify the device connection before transmitting."
    if "mismatch" in code or "bypass" in code:
        return "Keep transmission inhibited; confirm the selected band, route, and antenna readbacks."
    if "temperature" in code:
        return "Place the amplifier in standby and check cooling and airflow."
    if "voltage" in code:
        return "Place the amplifier in standby and check the power supply before operating."
    if "tune" in code:
        return "Leave the amplifier in standby; inspect the route and tuner result before retrying."
    if "recovery" in code:
        return "Confirm FLEX receive and amplifier standby before enabling station control."
    if "commission" in code:
        return "Complete station commissioning before using coordinated transmit actions."
    if "maintenance" in code:
        return "Finish maintenance and obtain fresh readbacks before returning the station to service."
    return "Review the station path evidence and keep transmission inhibited until it is confirmed."


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> float | None:
    numeric = _number(value)
    if numeric is not None:
        return numeric
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def build_station_alarms(
    station_state: Mapping[str, Any],
    *,
    elecraft_state: Mapping[str, Any] | None = None,
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic alarms from cached state without polling or writing hardware."""
    path = dict(station_state.get("path") or {})
    devices = dict(elecraft_state or {})
    limits = dict(thresholds or {})
    generated_at = station_state.get("generated_at") or path.get("generated_at")
    generated_seconds = _timestamp(generated_at)
    alarms: dict[tuple[str, str], dict[str, Any]] = {}

    def add(
        code: str,
        severity: str,
        source: str,
        message: str,
        *,
        observed_at: Any = None,
        age_seconds: Any = None,
        guidance: str | None = None,
    ) -> None:
        normalized_code = str(code or "station-alarm").strip().lower().replace("_", "-")
        normalized_source = str(source or "station-coordinator").strip().lower()
        key = (normalized_code, normalized_source)
        normalized_age = _number(age_seconds)
        if normalized_age is None and generated_seconds is not None:
            observed_seconds = _timestamp(observed_at)
            if observed_seconds is not None:
                normalized_age = max(0.0, round(generated_seconds - observed_seconds, 3))
        candidate = {
            "code": normalized_code,
            "severity": severity if severity in _SEVERITY_ORDER else "warning",
            "source": normalized_source,
            "message": str(message),
            "status": "active",
            "active": True,
            "observed_at": observed_at,
            "age_seconds": normalized_age,
            "guidance": guidance or _guidance(normalized_code, normalized_source),
        }
        current = alarms.get(key)
        if current is None or _SEVERITY_ORDER[candidate["severity"]] < _SEVERITY_ORDER[current["severity"]]:
            alarms[key] = candidate

    stages = {str(item.get("id")): item for item in path.get("stages", []) if isinstance(item, dict)}
    for stage_id in ("flex", "kpa500", "kat500"):
        stage = stages.get(stage_id) or {}
        state = str(stage.get("state") or "").lower()
        if state == "disconnected":
            add(f"{stage_id}-disconnected", "critical", stage_id, f"{stage.get('label', stage_id)} is disconnected", observed_at=stage.get("observed_at"), age_seconds=stage.get("age_seconds"))
        elif state == "stale" or stage.get("stale") is True:
            add(f"{stage_id}-telemetry-stale", "warning", stage_id, f"{stage.get('label', stage_id)} telemetry is stale", observed_at=stage.get("observed_at"), age_seconds=stage.get("age_seconds"))
        elif state == "unknown":
            add(f"{stage_id}-state-unknown", "warning", stage_id, f"{stage.get('label', stage_id)} state is unknown", observed_at=stage.get("observed_at"), age_seconds=stage.get("age_seconds"))

    for device_id in ("kpa500", "kat500"):
        device = dict(devices.get(device_id) or {})
        if device.get("enabled") is True and device.get("connected") is False:
            add(f"{device_id}-disconnected", "critical", device_id, f"{device_id.upper()} is disconnected", observed_at=device.get("observed_at", devices.get("updated_at")))
        fault = str(device.get("fault") or "").strip()
        if fault and fault not in {"0", "00"}:
            fault_code = "kpa-fault" if device_id == "kpa500" else "kat-fault"
            add(fault_code, "critical", device_id, f"{device_id.upper()} fault {fault}", observed_at=device.get("observed_at", devices.get("updated_at")))

    for item in path.get("mismatches", []):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "station-path-mismatch")
        severity = "critical" if "fault" in code else "warning"
        source = _source_from_code(code)
        stage = stages.get(source) or {}
        add(code, severity, source, str(item.get("message") or "Station path mismatch"), observed_at=stage.get("observed_at"), age_seconds=stage.get("age_seconds"))

    for issue in station_state.get("issues", []):
        if isinstance(issue, dict):
            code = str(issue.get("code") or "station-issue")
            message = str(issue.get("message") or issue.get("detail") or code)
        else:
            code, message = "station-issue", str(issue)
        source = _source_from_code(code)
        severity = "critical" if "fault" in code or "recovery" in code else "warning"
        stage = stages.get(source) or {}
        add(code, severity, source, message, observed_at=stage.get("observed_at"), age_seconds=stage.get("age_seconds"))

    # Unknown reasons that do not merely restate a stage alarm retain a stable category.
    for message in path.get("unknown_reasons", []):
        text = str(message)
        lower = text.lower()
        if any(word in lower for word in ("disconnected", "status is stale", "state is not fresh")):
            continue
        if "transmitter is active" in lower:
            code, source = "flex-transmit-active", "flex"
        elif "tx antenna readback" in lower:
            code, source = "flex-route-unknown", "flex"
        elif "kpa500" in lower:
            code, source = "kpa500-state-unknown", "kpa500"
        elif "kat500" in lower:
            code, source = "kat500-state-unknown", "kat500"
        else:
            code, source = "station-path-unknown", "station-coordinator"
        add(code, "warning", source, text)

    coordinator_state = str(station_state.get("coordinator_state") or "").lower()
    if station_state.get("recovery_required") or "recovery" in coordinator_state:
        add("startup-recovery-required", "critical", "station-coordinator", "Safe startup recovery has not been confirmed")
    if station_state.get("commissioned") is False or "commissioning" in coordinator_state:
        add("station-commissioning-required", "info", "station-coordinator", "Station control is locked pending commissioning")
    if station_state.get("maintenance") is True or "maintenance" in coordinator_state:
        add("station-maintenance-active", "warning", "station-coordinator", "Station maintenance mode is active")

    transaction = station_state.get("transaction") or {}
    transaction_state = str(transaction.get("state") or "").lower()
    if transaction_state in {"failed", "error", "cancelled", "canceled"}:
        error = transaction.get("error") or {}
        kind = str(transaction.get("kind") or "station")
        code = str(error.get("code") or f"{kind}-{transaction_state}")
        severity = "critical" if transaction_state in {"failed", "error"} else "warning"
        add(code, severity, "station-coordinator", str(error.get("message") or f"{kind.title()} was {transaction_state}"), observed_at=transaction.get("finished_at"))

    kpa = dict(devices.get("kpa500") or {})
    observed_at = kpa.get("observed_at", devices.get("updated_at"))
    temperature = _number(kpa.get("temperature_c"))
    temperature_max = _number(limits.get("kpa_temperature_max_c"))
    if temperature is not None and temperature_max is not None and temperature >= temperature_max:
        add("kpa500-temperature-high", "critical", "kpa500", f"KPA500 temperature {temperature:g} °C meets or exceeds configured {temperature_max:g} °C limit", observed_at=observed_at)
    voltage = _number(kpa.get("voltage"))
    voltage_min = _number(limits.get("kpa_voltage_min_v"))
    voltage_max = _number(limits.get("kpa_voltage_max_v"))
    if voltage is not None and voltage_min is not None and voltage <= voltage_min:
        add("kpa500-voltage-low", "critical", "kpa500", f"KPA500 voltage {voltage:g} V meets or falls below configured {voltage_min:g} V limit", observed_at=observed_at)
    if voltage is not None and voltage_max is not None and voltage >= voltage_max:
        add("kpa500-voltage-high", "critical", "kpa500", f"KPA500 voltage {voltage:g} V meets or exceeds configured {voltage_max:g} V limit", observed_at=observed_at)

    ordered = sorted(alarms.values(), key=lambda item: (_SEVERITY_ORDER[item["severity"]], item["source"], item["code"]))
    counts = {severity: sum(item["severity"] == severity for item in ordered) for severity in _SEVERITY_ORDER}
    return {
        "schema_version": 1,
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "status": "active" if ordered else "clear",
        "active_count": len(ordered),
        "counts": counts,
        "items": ordered,
    }
