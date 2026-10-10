"""Pure commissioning-readiness evaluation for the station RF path.

This module deliberately consumes snapshots and configuration values only.  It
does not poll a device, change a setting, persist operator evidence, or enable
the station coordinator's commissioning latch.
"""

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_OPERATOR_EVIDENCE = (
    (
        "physical_key_interrupt_verified",
        "physical-key-interrupt-verified",
        "The physical key/PTT interrupt has been tested and verified",
    ),
    (
        "antenna_routes_names_verified",
        "antenna-routes-names-verified",
        "Antenna names and the complete FLEX/KPA500/KAT500 routes have been verified",
    ),
    (
        "vendor_backups_captured",
        "vendor-backups-captured",
        "Vendor configuration backups have been captured",
    ),
    (
        "dummy_load_or_approved_antenna_connected",
        "dummy-load-or-approved-antenna-connected",
        "A dummy load or specifically approved antenna is connected",
    ),
    (
        "digital_engine_inhibit_verified",
        "digital-engine-inhibit-verified",
        "Digital-engine transmit inhibit has been independently verified",
    ),
)

# 60 m is intentionally unavailable to the amplifier commissioning workflow,
# even if it is accidentally added to the general amplifier allowlist.
COMMISSIONING_PROHIBITED_BANDS = frozenset({"60m"})
_RECEIVE = "receive-only"
_LOW_POWER = "low-power-test"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _config_value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _stage(path: Mapping[str, Any], stage_id: str) -> Mapping[str, Any]:
    for item in path.get("stages", ()) or ():
        if isinstance(item, Mapping) and item.get("id") == stage_id:
            return item
    return {}


def _fault_clear(value: Any) -> bool:
    return str(value if value is not None else "").strip() in {"0", "00"}


def _normal_band(value: Any) -> str:
    return str(value or "").strip().lower()


def build_commissioning_readiness(
    coordinator_snapshot: Mapping[str, Any] | None,
    elecraft_snapshot: Mapping[str, Any] | None,
    operator_evidence: Mapping[str, Any] | None,
    station_config: Any = None,
) -> dict[str, Any]:
    """Build a deterministic, fail-closed readiness report from cached evidence.

    ``station_config`` may be a mapping or a config module/object.  Omitting it
    reads the application's already-loaded config module; no value is changed.
    All operator evidence must be the literal boolean ``True``.  Truthy strings
    and numbers intentionally do not satisfy an attestation.
    """
    if station_config is None:
        from radio_control import config as station_config

    coordinator = _mapping(coordinator_snapshot)
    elecraft = _mapping(elecraft_snapshot)
    evidence = _mapping(operator_evidence)
    path = _mapping(coordinator.get("path"))
    route = _mapping(coordinator.get("route"))
    kpa = _mapping(elecraft.get("kpa500"))
    kat = _mapping(elecraft.get("kat500"))
    flex_stage = _stage(path, "flex")
    kpa_stage = _stage(path, "kpa500")
    kat_stage = _stage(path, "kat500")

    checks: list[dict[str, Any]] = []

    def add_check(
        code: str,
        passed: bool,
        message: str,
        *,
        source: str,
        required_for: tuple[str, ...],
        detail: str | None = None,
    ) -> None:
        item: dict[str, Any] = {
            "code": code,
            "source": source,
            "passed": bool(passed),
            "required_for": list(required_for),
            "message": message,
        }
        if detail:
            item["detail"] = detail
        checks.append(item)

    config_commissioned = _config_value(
        station_config, "STATION_COORDINATOR_COMMISSIONED", None
    )
    snapshot_commissioned = coordinator.get("commissioned")
    commissioning_locked = config_commissioned is False and snapshot_commissioned is False
    commissioning_enabled = config_commissioned is True and snapshot_commissioned is True
    commissioning_state_consistent = commissioning_locked or commissioning_enabled
    add_check(
        "commissioning-state-consistent",
        commissioning_state_consistent,
        (
            "The independent commissioning latch remains disabled"
            if commissioning_locked
            else (
                "The independent commissioning latch is enabled"
                if commissioning_enabled
                else "The commissioning latch state is inconsistent"
            )
        ),
        source="automated-cache",
        required_for=(_RECEIVE, _LOW_POWER),
        detail=(
            "Config and the coordinator snapshot must explicitly agree on the commissioned state"
        ),
    )

    coordinator_available = bool(coordinator and path)
    add_check(
        "coordinator-cache-available",
        coordinator_available,
        "A cached coordinator path snapshot is available",
        source="automated-cache",
        required_for=(_RECEIVE, _LOW_POWER),
    )

    transaction = _mapping(coordinator.get("transaction"))
    transaction_state = str(transaction.get("state") or "").strip().lower()
    coordinator_state = str(coordinator.get("coordinator_state") or "").strip().lower()
    coordinator_safe = bool(
        coordinator.get("maintenance") is False
        and coordinator.get("recovery_required") is False
        and transaction_state not in {"running", "pending", "started", "tuning"}
        and coordinator_state in {"commissioning_locked", "safe_rx", "route_verified"}
    )
    add_check(
        "coordinator-safe-state",
        coordinator_safe,
        "The cached coordinator state is idle, out of maintenance, and recovery-complete",
        source="automated-cache",
        required_for=(_RECEIVE, _LOW_POWER),
        detail=f"Cached coordinator state: {coordinator_state or 'unknown'}",
    )

    flex_receive = bool(
        flex_stage.get("confirmed") is True
        and flex_stage.get("stale") is False
        and str(flex_stage.get("state") or "").strip().lower() == "ready"
    )
    add_check(
        "flex-receive-cache-fresh",
        flex_receive,
        "The cached FLEX state is fresh, confirmed, and receiving",
        source="automated-cache",
        required_for=(_RECEIVE, _LOW_POWER),
    )

    kpa_fresh = bool(
        kpa.get("enabled") is True
        and kpa.get("connected") is True
        and kpa.get("responsive") is True
        and kpa.get("stale") is not True
        and kpa_stage.get("confirmed") is True
        and kpa_stage.get("stale") is False
        and _fault_clear(kpa.get("fault"))
    )
    add_check(
        "kpa500-cache-fresh",
        kpa_fresh,
        "KPA500 cached telemetry is connected, responsive, fresh, and fault-free",
        source="automated-cache",
        required_for=(_RECEIVE, _LOW_POWER),
    )

    kpa_standby = bool(
        kpa.get("power") is True
        and kpa.get("operate") is False
        and str(kpa_stage.get("state") or "").strip().lower() == "standby"
    )
    add_check(
        "kpa500-standby-confirmed",
        kpa_standby,
        "KPA500 is explicitly reported powered and in standby",
        source="automated-cache",
        required_for=(_RECEIVE, _LOW_POWER),
    )

    kat_fresh = bool(
        kat.get("enabled") is True
        and kat.get("connected") is True
        and kat.get("responsive") is True
        and kat.get("stale") is not True
        and kat_stage.get("confirmed") is True
        and kat_stage.get("stale") is False
        and _fault_clear(kat.get("fault"))
    )
    add_check(
        "kat500-cache-fresh",
        kat_fresh,
        "KAT500 cached telemetry is connected, responsive, fresh, and fault-free",
        source="automated-cache",
        required_for=(_RECEIVE, _LOW_POWER),
    )

    kat_idle = bool(
        kat.get("power") is True
        and kat.get("tuning") is False
        and kat.get("bypass") is False
        and str(kat.get("mode") or "").strip().lower() in {"auto", "manual"}
    )
    add_check(
        "kat500-idle-confirmed",
        kat_idle,
        "KAT500 is powered, idle, and not bypassed",
        source="automated-cache",
        required_for=(_RECEIVE, _LOW_POWER),
    )

    route_band = _normal_band(route.get("band") or path.get("band") or elecraft.get("radio_band"))
    flex_port = str(route.get("flex_tx_ant") or "").strip().upper()
    try:
        kat_antenna = int(route.get("kat_antenna") or 0)
    except (TypeError, ValueError):
        kat_antenna = 0
    antenna_names = _mapping(_config_value(station_config, "KAT500_ANTENNA_NAMES", {}))
    configured_antenna_name = str(
        antenna_names.get(str(kat_antenna)) or antenna_names.get(kat_antenna) or ""
    ).strip()
    antenna_name = str(
        route.get("antenna_name")
        or configured_antenna_name
        or ""
    ).strip()
    flex_policy = _mapping(_config_value(station_config, "FLEX_ANTENNA_POLICY", {}))
    flex_bands = _mapping(flex_policy.get("bands"))
    flex_entry = flex_bands.get(route_band)
    if isinstance(flex_entry, Mapping):
        configured_flex_port = str(
            flex_entry.get("tx") or flex_entry.get("txAnt") or flex_entry.get("antenna") or ""
        ).strip().upper()
    else:
        configured_flex_port = str(flex_entry or "").strip().upper()
    kat_policy = _mapping(_config_value(station_config, "KAT500_ANTENNA_POLICY", {}))
    try:
        configured_kat_antenna = int(kat_policy.get(route_band) or 0)
    except (TypeError, ValueError):
        configured_kat_antenna = 0
    route_configured = bool(
        route_band
        and flex_policy.get("enabled") is not False
        and flex_port
        and flex_port == configured_flex_port
        and kat_antenna in {1, 2, 3}
        and kat_antenna == configured_kat_antenna
        and antenna_name
        and antenna_name == configured_antenna_name
        and antenna_name.upper() not in {f"KAT ANT{kat_antenna}", f"ANT{kat_antenna}"}
    )
    add_check(
        "route-configured",
        route_configured,
        "The current route has matching FLEX/KAT policy and a site-specific antenna name",
        source="automated-cache",
        required_for=(_LOW_POWER,),
    )

    path_aligned = bool(
        path.get("alignment") == "confirmed"
        and not (path.get("mismatches") or [])
        and not (path.get("unknown_reasons") or [])
        and flex_receive
        and kpa_stage.get("confirmed") is True
        and kat_stage.get("confirmed") is True
    )
    add_check(
        "cached-path-aligned",
        path_aligned,
        "The cached end-to-end RF path is aligned with no unknowns or mismatches",
        source="automated-cache",
        required_for=(_LOW_POWER,),
    )

    allowed_bands = {
        _normal_band(value)
        for value in (
            _config_value(station_config, "STATION_AMPLIFIER_ALLOWED_BANDS", ()) or ()
        )
        if _normal_band(value)
    }
    band_eligible = bool(
        route_band
        and route_band in allowed_bands
        and route_band not in COMMISSIONING_PROHIBITED_BANDS
    )
    add_check(
        "band-eligible-for-low-power-test",
        band_eligible,
        "The current band is eligible for a low-power amplifier test",
        source="automated-cache",
        required_for=(_LOW_POWER,),
        detail=(
            "60m is prohibited for this workflow"
            if route_band in COMMISSIONING_PROHIBITED_BANDS
            else f"Cached band: {route_band or 'unknown'}"
        ),
    )

    tune_power = _config_value(station_config, "STATION_TUNE_POWER_W", None)
    try:
        tune_power_w = float(tune_power)
    except (TypeError, ValueError):
        tune_power_w = 0.0
    low_power_configured = 0 < tune_power_w <= 20
    add_check(
        "low-power-limit-configured",
        low_power_configured,
        "Configured tune power is positive and no greater than 20 W",
        source="automated-cache",
        required_for=(_LOW_POWER,),
        detail=f"Configured tune power: {tune_power!r} W",
    )

    follow_radio = bool(
        _config_value(station_config, "ELECRAFT_FOLLOW_RADIO", None) is True
        and elecraft.get("following_radio") is True
    )
    add_check(
        "follow-radio-enabled",
        follow_radio,
        "Config and cached manager state both confirm follow-radio mode",
        source="automated-cache",
        required_for=(_LOW_POWER,),
    )

    legacy_disabled = _config_value(
        station_config, "ELECRAFT_LEGACY_CONTROL_ENABLED", None
    ) is False
    add_check(
        "legacy-direct-control-disabled",
        legacy_disabled,
        "Legacy direct Elecraft writes remain disabled",
        source="automated-cache",
        required_for=(_LOW_POWER,),
    )

    for key, code, message in REQUIRED_OPERATOR_EVIDENCE:
        add_check(
            code,
            evidence.get(key) is True,
            message,
            source="operator-evidence",
            required_for=(_LOW_POWER,),
            detail=f"Required evidence field: {key}",
        )

    blockers = [
        {
            "code": item["code"],
            "source": item["source"],
            "required_for": item["required_for"],
            "message": item["message"],
            **({"detail": item["detail"]} if "detail" in item else {}),
        }
        for item in checks
        if not item["passed"]
    ]
    warnings: list[dict[str, Any]] = []
    expected_evidence_keys = {item[0] for item in REQUIRED_OPERATOR_EVIDENCE}
    unexpected_evidence = sorted(str(key) for key in evidence if key not in expected_evidence_keys)
    if unexpected_evidence:
        warnings.append(
            {
                "code": "unrecognized-operator-evidence",
                "source": "operator-evidence",
                "message": "Unrecognized evidence fields were ignored",
                "fields": unexpected_evidence,
            }
        )

    def tier_ready(tier: str) -> bool:
        return all(item["passed"] for item in checks if tier in item["required_for"])

    ready_for_receive_only = tier_ready(_RECEIVE)
    ready_for_low_power_test = ready_for_receive_only and tier_ready(_LOW_POWER)
    if ready_for_low_power_test:
        disposition = "ready-for-low-power-test"
    elif ready_for_receive_only:
        disposition = "receive-only"
    else:
        disposition = "blocked"

    automated = [item for item in checks if item["source"] == "automated-cache"]
    attestations = [item for item in checks if item["source"] == "operator-evidence"]
    passed_count = sum(item["passed"] for item in checks)
    return {
        "schema_version": 1,
        "read_only": True,
        "commissioning_enabled": commissioning_enabled,
        "disposition": disposition,
        "ready_for_receive_only": ready_for_receive_only,
        "ready_for_low_power_test": ready_for_low_power_test,
        "current_band": route_band or None,
        "source_generated_at": coordinator.get("generated_at") or path.get("generated_at"),
        "check_count": len(checks),
        "passed_count": passed_count,
        "counts": {
            "total": len(checks),
            "passed": passed_count,
            "failed": len(checks) - passed_count,
            "automated_total": len(automated),
            "automated_passed": sum(item["passed"] for item in automated),
            "operator_evidence_total": len(attestations),
            "operator_evidence_passed": sum(item["passed"] for item in attestations),
            "blockers": len(blockers),
            "warnings": len(warnings),
        },
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "safety_notes": [
            "This report is advisory and cannot enable commissioning or authorize transmission.",
            "All automated results come from cached snapshots; no device was queried.",
            "Low-power readiness expires with the underlying cached station evidence.",
        ],
    }
