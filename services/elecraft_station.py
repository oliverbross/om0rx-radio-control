"""Safety coordinator for the FLEX-8400, KPA500, and KAT500 station path.

All state-changing entry points fail closed unless the installation has been
explicitly commissioned.  The coordinator owns multi-device transactions;
callers must never reproduce these command sequences in an HTTP or UI layer.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Optional

from radio_control import config
from radio_control.elecraft import ElecraftManager, band_from_frequency, verify_exact_target
from radio_control.station_telemetry_store import StationEvent, StationSnapshot, TuneResult
from radio_control.station_policy import resolve_amplifier_policy
from services.radio import get_radio_command_lock, run_radio_io
from services.station_alarms import build_station_alarms


logger = logging.getLogger(__name__)
AMP_KEY_RELAY_SETTLE_SECONDS = 0.05
AMP_KEY_VERIFY_ATTEMPTS = 3
KAT_TUNE_CANCEL_SETTLE_SECONDS = 0.1
KAT_TUNE_CANCEL_VERIFY_ATTEMPTS = 10
OBSERVED_ROUTE_REUSE_MAX_AGE_SECONDS = 1.0

RECEIVE_INTERLOCK_STATES = {"READY", "RECEIVE"}
EXTERNAL_RX_WAIT_SECONDS = 20.0
EXTERNAL_RX_RETRY_CODES = {
    "flex-not-receiving",
    "flex-tx-proof-timeout",
    "flex-tx-state-unconfirmed",
}

KPA500_FAULT_DESCRIPTIONS = {
    "09": "REFL HI",
}


class StationActionError(RuntimeError):
    """A rejected or failed station transaction with an operator-facing code."""

    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _default_digital_guard(*, force_refresh: bool = True) -> Any:
    """Return the built-in digital service only when no TX intent is armed."""
    from services.digital_engine import backend_radio_control_allowed, selected_provider

    provider = selected_provider()
    if not backend_radio_control_allowed(force_refresh=force_refresh):
        raise StationActionError(
            "digital-engine-owns-radio",
            "The active external digital engine owns radio and transmit control",
        )
    if provider != "wsjtz":
        return None

    from services.ft8_service import get_ft8_service

    service = get_ft8_service()
    pending = bool(
        getattr(service, "tx_enabled", False)
        or getattr(service, "tx_in_progress", False)
        or getattr(service, "tx_queue", None)
        or getattr(service, "active_tx_message", None)
        or getattr(service, "pending_tx_intent", None)
        or getattr(service, "active_attempt_id", None)
        or getattr(service, "auto_call_enabled", False)
        or getattr(service, "auto_cq_enabled", False)
    )
    if pending:
        raise StationActionError(
            "digital-tx-armed",
            "Digital transmission is armed or pending; halt/disarm it before station routing",
        )
    return service


@dataclass(frozen=True)
class RouteTarget:
    route_id: str
    band: str
    frequency_mhz: float
    flex_tx_ant: str
    kat_antenna: int
    antenna_name: str
    radio_mode: str = ""
    digital_mode: bool = False
    policy_profile: str = "standard"
    amplifier_allowed_bands: tuple[str, ...] = ()
    amplifier_inhibitors: tuple[str, ...] = ()
    amplifier_allowed: bool = True
    amplifier_drive_w: int = 25
    barefoot_drive_w: int = 25
    configured_kpa500: str = "operate"
    kpa500: str = "operate"
    active_drive_w: int = 25

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.route_id,
            "band": self.band,
            "frequency_mhz": self.frequency_mhz,
            "flex_tx_ant": self.flex_tx_ant,
            "kat_antenna": self.kat_antenna,
            "antenna_name": self.antenna_name,
            "radio_mode": self.radio_mode,
            "digital_mode": self.digital_mode,
            "policy_profile": self.policy_profile,
            "amplifier_allowed_bands": list(self.amplifier_allowed_bands),
            "amplifier_inhibitors": list(self.amplifier_inhibitors),
            "amplifier_allowed": self.amplifier_allowed,
            "amplifier_drive_w": self.amplifier_drive_w,
            "barefoot_drive_w": self.barefoot_drive_w,
            "configured_kpa500": self.configured_kpa500,
            "kpa500": self.kpa500,
            "active_drive_w": self.active_drive_w,
        }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _flex_policy_tx_antenna(frequency_mhz: float, source: Any = config) -> Optional[str]:
    policy = getattr(source, "FLEX_ANTENNA_POLICY", {}) or {}
    if policy.get("enabled") is False:
        return None
    band = band_from_frequency(frequency_mhz)
    entry = (policy.get("bands") or {}).get(band)
    if isinstance(entry, dict):
        value = entry.get("tx") or entry.get("txAnt") or entry.get("antenna")
    else:
        value = entry
    clean = str(value or "").strip().upper()
    return clean or None


class StationCoordinator:
    """Own safe, serialized station-level route and tune transactions."""

    def __init__(
        self,
        elecraft: ElecraftManager,
        flex_provider: Callable[[], Any],
        radio_snapshot_provider: Callable[[], dict[str, Any]],
        *,
        telemetry: Any = None,
        digital_guard: Optional[Callable[[], Any]] = None,
        radio_lock: Optional[asyncio.Lock] = None,
        recovery_required: bool = False,
        policy_source: Any = None,
    ) -> None:
        self.elecraft = elecraft
        self.flex_provider = flex_provider
        self.radio_snapshot_provider = radio_snapshot_provider
        self.telemetry = telemetry
        self._uses_default_digital_guard = digital_guard is None
        self.digital_guard = digital_guard or _default_digital_guard
        self.radio_lock = radio_lock or get_radio_command_lock()
        self.policy_source = policy_source or config
        self._action_lock = asyncio.Lock()
        self._cancel_event = asyncio.Event()
        self._active_task: Optional[asyncio.Task] = None
        self._transaction: Optional[dict[str, Any]] = None
        self._route_verified: Optional[dict[str, Any]] = None
        self._stopped = False
        self._recovery_required = bool(recovery_required)
        self._maintenance = False
        self._training_job_id: Optional[str] = None
        self._training_tx_monitor: Any = None
        self._training_tx_monitor_job_id: Optional[str] = None
        self._training_original_kat_mode: Optional[str] = None
        self._last_follow_attempt: Optional[tuple[str, int, str, int, int, bool]] = None
        self._last_follow_attempt_at = 0.0
        self._follow_generation = 0
        self._follow_inflight_target: Optional[tuple[str, int, str, int, int, bool]] = None
        # Operator intent is deliberately separate from the instantaneous KPA
        # readback. Route changes temporarily force standby, but only an
        # explicit Standby command clears the request to operate.
        self._manual_operate_requested = False

    @property
    def commissioned(self) -> bool:
        return bool(self._policy_value("STATION_COORDINATOR_COMMISSIONED", False))

    def _policy_value(self, name: str, default: Any) -> Any:
        """Read immutable runtime policy first, then non-profile defaults."""
        if hasattr(self.policy_source, name):
            return getattr(self.policy_source, name)
        return getattr(config, name, default)

    @property
    def busy(self) -> bool:
        return bool(
            self._action_lock.locked()
            or (self._active_task and not self._active_task.done())
        )

    @property
    def maintenance(self) -> bool:
        return self._maintenance

    @property
    def training_job_id(self) -> Optional[str]:
        return self._training_job_id

    def _radio_snapshot(self) -> dict[str, Any]:
        return dict(self.radio_snapshot_provider() or {})

    @staticmethod
    def _transmit_route_observation(radio: dict[str, Any]) -> tuple[Any, Any, Any]:
        """Return authoritative TX frequency, mode, and observation time.

        ``frequency``/``freq`` historically describe the active receive slice.
        In split operation the station route belongs to the slice marked TX.
        Prefer that slice (or the driver's explicit TX fields) and retain the
        legacy fields only as the simplex fallback.
        """
        transmit = radio.get("transmit")
        if isinstance(transmit, dict) and transmit.get("frequency") is not None:
            return (
                transmit.get("frequency"),
                transmit.get("mode") or radio.get("tx_mode") or radio.get("mode"),
                transmit.get("updated_at", radio.get("updated_at", radio.get("observed_at"))),
            )
        tx_frequency = radio.get("tx_frequency")
        if tx_frequency is not None:
            return (
                tx_frequency,
                radio.get("tx_mode") or radio.get("mode"),
                radio.get("updated_at", radio.get("observed_at")),
            )
        return (
            radio.get("frequency", radio.get("freq")),
            radio.get("mode"),
            radio.get("updated_at", radio.get("observed_at")),
        )

    def _route_for_frequency(
        self,
        frequency: Any,
        radio_mode: Any = None,
    ) -> Optional[RouteTarget]:
        try:
            frequency_mhz = float(frequency)
        except (TypeError, ValueError):
            return None
        band = band_from_frequency(frequency_mhz)
        if not band:
            return None
        flex_tx_ant = _flex_policy_tx_antenna(frequency_mhz, self.policy_source)
        if not flex_tx_ant:
            return None
        antenna = int(self.elecraft.antenna_policy.get(band, 0) or 0)
        if antenna not in {1, 2, 3}:
            return None
        names = self._policy_value("KAT500_ANTENNA_NAMES", {}) or {}
        name = str(names.get(str(antenna), names.get(antenna, f"KAT ANT{antenna}"))).strip()
        name = name or f"KAT ANT{antenna}"
        amplifier_policy = resolve_amplifier_policy(self.policy_source, band, radio_mode)
        return RouteTarget(
            route_id=f"{band}-flex-{flex_tx_ant.lower()}-kat-ant{antenna}",
            band=band,
            frequency_mhz=frequency_mhz,
            flex_tx_ant=flex_tx_ant,
            kat_antenna=antenna,
            antenna_name=name,
            radio_mode=amplifier_policy.radio_mode,
            digital_mode=amplifier_policy.digital_mode,
            policy_profile=amplifier_policy.profile,
            amplifier_allowed_bands=amplifier_policy.allowed_bands,
            amplifier_inhibitors=amplifier_policy.inhibitors,
            amplifier_allowed=amplifier_policy.amplifier_allowed,
            amplifier_drive_w=amplifier_policy.amplifier_drive_w,
            barefoot_drive_w=amplifier_policy.barefoot_drive_w,
            configured_kpa500=amplifier_policy.configured_mode,
            kpa500=amplifier_policy.effective_mode,
            active_drive_w=amplifier_policy.active_drive_w,
        )

    def _route_for_snapshot(self, radio: dict[str, Any]) -> Optional[RouteTarget]:
        frequency, mode, _observed_at = self._transmit_route_observation(radio)
        if frequency is None:
            frequency = self.elecraft.last_frequency
        route = self._route_for_frequency(frequency, mode)
        if self._route_verified and (
            route is None
            or self._route_verified.get("route_id") != route.route_id
            or self._route_verified.get("frequency_khz")
            != round(route.frequency_mhz * 1000)
            or self._route_verified.get("digital_mode", False) is not route.digital_mode
        ):
            self._route_verified = None
        return route

    def _require_fresh_route(self) -> RouteTarget:
        radio = self._radio_snapshot()
        frequency, _mode, _observed_at = self._transmit_route_observation(radio)
        if (
            radio.get("connected") is not True
            or radio.get("known") is not True
            or radio.get("stale") is not False
            or frequency is None
        ):
            raise StationActionError(
                "flex-route-state-unconfirmed",
                "A fresh, known FLEX frequency is required before station routing",
            )
        route = self._route_for_snapshot(radio)
        if route is None:
            raise StationActionError(
                "route-unresolved",
                "No complete route matches the current FLEX frequency",
            )
        return route

    def _recent_receive_route_observation(self, route: RouteTarget) -> bool:
        """Return whether the shared FLEX poll is a just-observed RX route proof.

        This proof is used only to avoid immediately repeating the same FLEX
        levels transaction at the start of automatic route following.  The
        guarded transaction still performs its independent ordered RX proof and
        exact FLEX route proof before any accessory route mutation.
        """
        radio = self._radio_snapshot()
        frequency, _mode, observed_at = self._transmit_route_observation(radio)
        try:
            if isinstance(observed_at, str):
                observed_seconds = datetime.fromisoformat(observed_at).timestamp()
            else:
                observed_seconds = float(observed_at)
            age = time.time() - observed_seconds
            frequency_khz = round(float(frequency) * 1000)
        except (TypeError, ValueError, OverflowError):
            return False
        interlock = str(radio.get("interlock_state") or "").upper()
        return bool(
            0 <= age <= OBSERVED_ROUTE_REUSE_MAX_AGE_SECONDS
            and radio.get("connected") is True
            and radio.get("known") is True
            and radio.get("stale") is False
            and radio.get("mox") is False
            and interlock in RECEIVE_INTERLOCK_STATES
            and frequency_khz == round(route.frequency_mhz * 1000)
            and str(radio.get("tx_ant") or "").upper() == route.flex_tx_ant
        )

    def _route_verification_is_fresh(self, route: Optional[RouteTarget]) -> bool:
        if not self._route_verified or not route:
            return False
        ttl = float(self._policy_value("STATION_ROUTE_VERIFY_TTL_SECONDS", 10.0))
        return bool(
            self._route_verified.get("route_id") == route.route_id
            and self._route_verified.get("frequency_khz")
            == round(route.frequency_mhz * 1000)
            and self._route_verified.get("digital_mode", False) is route.digital_mode
            and time.time() - float(self._route_verified.get("verified_at", 0)) <= ttl
        )

    def _cached_operate_route_proof(self, route: Optional[RouteTarget]) -> Optional[dict[str, Any]]:
        """Return a recent exact standby-route proof without touching hardware.

        The Elecraft manager already performs complete readbacks every five
        seconds.  Repeating every KPA/KAT query on a button press made OPERATE
        slow enough to collide with the next FT8 slot.  Reuse only a complete,
        recent, exact readback; anything stale or incomplete falls back to the
        full guarded route-preparation transaction.
        """
        if route is None:
            return None
        radio = self._radio_snapshot()
        frequency, _mode, _observed_at = self._transmit_route_observation(radio)
        state = self.elecraft.snapshot()
        kpa = state.get("kpa500") or {}
        kat = state.get("kat500") or {}
        max_age = float(self._policy_value("STATION_OPERATE_CACHE_MAX_AGE_SECONDS", 15.0))
        now = time.time()

        def recent(device: dict[str, Any]) -> bool:
            observed_at = device.get("observed_at", state.get("updated_at"))
            try:
                age = now - float(observed_at)
            except (TypeError, ValueError):
                return False
            return bool(
                0 <= age <= max_age
                and device.get("connected") is True
                and device.get("responsive", True) is True
                and not device.get("missing_fields")
                and device.get("quality", "good") == "good"
            )

        try:
            radio_frequency_khz = round(float(frequency) * 1000)
        except (TypeError, ValueError):
            return None
        interlock = str(radio.get("interlock_state") or "").upper()
        if not (
            radio.get("connected") is True
            and radio.get("known") is True
            and radio.get("stale") is False
            and radio.get("mox") is False
            and interlock in RECEIVE_INTERLOCK_STATES
            and radio_frequency_khz == round(route.frequency_mhz * 1000)
            and str(radio.get("tx_ant") or "").upper() == route.flex_tx_ant
            and recent(kpa)
            and recent(kat)
        ):
            return None

        kpa_verification = verify_exact_target(
            kpa,
            {
                "power": True,
                "operate": False,
                "band": route.band,
                "fault": "00",
            },
        )
        kat_verification = verify_exact_target(
            kat,
            {
                "power": True,
                "band": route.band,
                "antenna": route.kat_antenna,
                "frequency_khz": round(route.frequency_mhz * 1000),
                "tuning": False,
                "fault": "0",
                "amp_key_interrupted": False,
            },
        )
        if (
            not kpa_verification["verified"]
            or not kat_verification["verified"]
            or kat.get("mode") not in {"auto", "manual"}
        ):
            return None
        try:
            observed_drive = int(radio.get("drive"))
        except (TypeError, ValueError):
            observed_drive = None
        return {
            "route_id": route.route_id,
            "frequency_mhz": route.frequency_mhz,
            "frequency_khz": round(route.frequency_mhz * 1000),
            "verified_at": now,
            "verified_at_iso": _utc_now(),
            "kpa_operate": False,
            "flex_tx_ant": route.flex_tx_ant,
            "kat_antenna": route.kat_antenna,
            "flex_drive_w": observed_drive,
            "digital_mode": route.digital_mode,
            "source": "recent-manager-readback",
        }

    def _adopt_cached_operate_route(self, route: RouteTarget) -> bool:
        proof = self._cached_operate_route_proof(route)
        if proof is None:
            return False
        self._route_verified = proof
        return True

    def _path_issues(self, path: dict[str, Any]) -> list[dict[str, str]]:
        issues = [
            {
                "code": str(item.get("code") or "path-mismatch"),
                "message": str(item.get("message") or "Station path mismatch"),
            }
            for item in path.get("mismatches", [])
        ]
        issues.extend(
            {"code": "path-unknown", "message": str(message)}
            for message in path.get("unknown_reasons", [])
        )
        return issues

    def snapshot(self) -> dict[str, Any]:
        radio = self._radio_snapshot()
        path = self.elecraft.station_path(radio)
        route = self._route_for_snapshot(radio)
        active = bool(self._active_task and not self._active_task.done())
        verified = self._route_verification_is_fresh(route)
        issues = self._path_issues(path)
        digital_ready = True
        external_digital_owner = False
        try:
            # This is a read-only UI snapshot emitted four times per second.
            # Reuse the process scanner's stale-while-refresh cache here;
            # state-changing actions still force a fresh exact process scan.
            self._assert_digital_idle(force_refresh=False)
        except StationActionError as exc:
            digital_ready = False
            external_digital_owner = exc.code == "digital-engine-owns-radio"
            issues.append({"code": exc.code, "message": exc.message})
        except Exception:
            digital_ready = False
            issues.append(
                {
                    "code": "digital-state-unconfirmed",
                    "message": "Digital transmit state could not be confirmed idle",
                }
            )

        if self._maintenance:
            coordinator_state = (
                "maintenance_recovery_required"
                if self._recovery_required
                else "maintenance"
            )
            issues.append(
                {
                    "code": "station-maintenance-active",
                    "message": "Station maintenance mode is active; transmit and route controls are locked",
                }
            )
        elif self._recovery_required:
            coordinator_state = "recovery_required"
            issues.append(
                {
                    "code": "startup-recovery-required",
                    "message": "FLEX receive and KPA500 standby must be confirmed",
                }
            )
        elif not self.commissioned:
            coordinator_state = "commissioning_locked"
        elif active:
            coordinator_state = str((self._transaction or {}).get("state") or "busy")
        elif not digital_ready and not external_digital_owner:
            coordinator_state = "blocked"
        elif path.get("alignment") == "unknown":
            coordinator_state = "unknown"
        elif path.get("alignment") == "mismatch":
            coordinator_state = "mismatch"
        elif verified:
            coordinator_state = "route_verified"
        else:
            coordinator_state = "safe_rx"

        allowed_actions: list[str] = []
        elecraft_state = self.elecraft.snapshot()
        kpa = elecraft_state.get("kpa500") or {}
        kat = elecraft_state.get("kat500") or {}
        if self._maintenance:
            allowed_actions.append("exit-maintenance")
        elif not active and kpa.get("enabled") and kpa.get("connected"):
            allowed_actions.append("standby")
        interlock = str(radio.get("interlock_state") or "").upper()
        receive_ready = bool(
            radio.get("connected")
            and radio.get("known") is True
            and radio.get("stale") is False
            and radio.get("mox") is False
            and interlock in RECEIVE_INTERLOCK_STATES
        )
        kpa_fault = str(kpa.get("fault") or "").strip()
        kat_fault = str(kat.get("fault") or "").strip()
        if (
            self.commissioned
            and not self._maintenance
            and not self._recovery_required
            and not active
            and receive_ready
            and kpa.get("enabled")
            and kpa.get("connected")
            and kpa.get("operate") is False
            and kat.get("enabled")
            and kat.get("connected")
            and kat.get("tuning") is False
            and (kpa_fault not in {"", "00"} or kat_fault not in {"", "0"})
        ):
            allowed_actions.append("clear-faults")
        if (
            self.commissioned
            and not self._maintenance
            and not self._recovery_required
            and (digital_ready or external_digital_owner)
            and not active
            and route
        ):
            if radio.get("connected") and not radio.get("stale") and radio.get("mox") is False:
                allowed_actions.append("prepare-route")
                if (
                    receive_ready
                    and route.amplifier_allowed
                    and kpa.get("enabled")
                    and kpa.get("connected")
                    and kat.get("enabled")
                    and kat.get("connected")
                ):
                    allowed_actions.append("operate")
                    blocking_issues = [
                        issue
                        for issue in issues
                        if issue.get("code") != "digital-engine-owns-radio"
                    ]
                    if verified and digital_ready and not blocking_issues:
                        allowed_actions.append("tune")
        if active and (self._transaction or {}).get("kind") == "tune":
            allowed_actions.append("cancel")

        state = {
            "schema_version": 1,
            "generated_at": _utc_now(),
            "commissioned": self.commissioned,
            "maintenance": self._maintenance,
            "training_job_id": self._training_job_id,
            "maintenance_enter_available": bool(
                not self._maintenance and not active and not self._stopped
            ),
            "recovery_required": self._recovery_required,
            "coordinator_state": coordinator_state,
            "allowed_actions": allowed_actions,
            "route": route.as_dict() if route else None,
            "route_verified": verified,
            "route_verification": dict(self._route_verified) if self._route_verified else None,
            "path": path,
            "issues": issues,
            "transaction": dict(self._transaction) if self._transaction else None,
        }
        state["alarms"] = build_station_alarms(
            state,
            elecraft_state=elecraft_state,
            thresholds={
                "kpa_temperature_max_c": getattr(config, "KPA500_TEMPERATURE_MAX_C", None),
                "kpa_voltage_min_v": getattr(config, "KPA500_VOLTAGE_MIN_V", None),
                "kpa_voltage_max_v": getattr(config, "KPA500_VOLTAGE_MAX_V", None),
            },
        )
        return state

    async def refresh_snapshot(self) -> dict[str, Any]:
        if not self._maintenance:
            await self.elecraft.refresh_status()
        state = self.snapshot()
        await self.capture_telemetry(state)
        return state

    async def stop(self) -> None:
        self._stopped = True
        self._cancel_event.set()
        task = self._active_task
        carrier_off_confirmed = await self._force_carrier_off()
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._active_task = None
        standby_confirmed = await self._request_fail_safe_standby()
        self._route_verified = None
        if not carrier_off_confirmed or not standby_confirmed:
            unsafe_parts = []
            if not carrier_off_confirmed:
                unsafe_parts.append("FLEX receive state")
            if not standby_confirmed:
                unsafe_parts.append("KPA500 standby")
            raise StationActionError(
                "unsafe-shutdown-unconfirmed",
                f"Could not confirm {' and '.join(unsafe_parts)} during station shutdown",
                status_code=503,
            )

    async def recover_safe_state(self) -> dict[str, Any]:
        """Establish a fail-safe state before normal controls become available."""
        async with self._action_lock:
            self._require_not_maintenance()
            async with self.radio_lock:
                carrier_off_confirmed = await self._force_carrier_off()
                standby_confirmed = await self._request_fail_safe_standby()
                self._route_verified = None
                self._recovery_required = not (
                    carrier_off_confirmed and standby_confirmed
                )
                if self._recovery_required:
                    raise StationActionError(
                        "startup-recovery-unconfirmed",
                        "Startup could not confirm FLEX receive and KPA500 standby",
                        status_code=503,
                    )
        return self.snapshot()

    def _require_commissioned(self) -> None:
        if not self.commissioned:
            raise StationActionError(
                "commissioning-required",
                "Station control is locked until the installation is commissioned",
            )

    def _require_recovered(self) -> None:
        if self._recovery_required:
            raise StationActionError(
                "startup-recovery-required",
                "Station controls remain locked until safe startup recovery is confirmed",
                status_code=503,
            )

    def _require_not_maintenance(self) -> None:
        if self._maintenance:
            raise StationActionError(
                "station-maintenance-active",
                "Station controls are locked while maintenance mode is active",
                status_code=423,
            )

    def _require_operational(self) -> None:
        self._require_not_maintenance()
        self._require_recovered()

    def _require_no_training(self) -> None:
        if self._training_job_id:
            raise StationActionError(
                "station-training-active",
                f"ATU training job {self._training_job_id} owns station control",
                status_code=423,
            )

    def _assert_digital_idle(self, *, force_refresh: bool = True) -> Any:
        if self._uses_default_digital_guard:
            return _default_digital_guard(force_refresh=force_refresh)
        return self.digital_guard()

    def _manual_amplifier_owner_bypass(self) -> bool:
        """Allow RX-only KPA routing while an external digital engine is attached.

        MSHV remains the owner of CAT frequency, mode, and PTT.  The manual
        amplifier path may still be prepared or switched to OPERATE between
        transmissions; the transaction's repeated fresh-RX checks remain the
        authority.  Every other digital guard failure (including armed TX)
        stays blocking.
        """
        try:
            self._assert_digital_idle()
        except StationActionError as exc:
            if exc.code == "digital-engine-owns-radio":
                return True
            raise
        return False

    @asynccontextmanager
    async def _external_digital_control_lease(self, required: bool, reason: str):
        """Create a short fail-closed quiet window around manual station writes.

        Revoking outstanding permits prevents a native client waiting on the
        backend radio lock from keying after the coordinator starts.  A fresh
        RX proof before yielding plus the proof immediately before ``^OS1``
        cover a permit consumed just before this lease was acquired.
        """
        if not required:
            yield
            return
        from services.digital_engine import get_digital_engine_service

        service = get_digital_engine_service()
        try:
            token = service.acquire_station_control_lease(reason)
        except RuntimeError as exc:
            raise StationActionError(
                "station-control-lease-unavailable",
                "A digital station-control transition is already active",
                status_code=423,
            ) from exc
        try:
            # A native digital client can have consumed its last permit and
            # armed the next timed PTT edge immediately before this lease is
            # acquired. Revoking authorizations prevents every later edge,
            # but cannot retract that already-consumed edge. Wait through the
            # one outstanding slot instead of making the operator race the FT8
            # clock with repeated button presses.
            await self._wait_for_external_receive_window()
            yield
        finally:
            if not service.release_station_control_lease(token):
                logger.critical("Could not release digital station-control lease")

    async def _wait_for_external_receive_window(
        self,
        *,
        timeout: float = EXTERNAL_RX_WAIT_SECONDS,
    ) -> dict[str, Any]:
        """Wait for a freshly proved RX slot while a digital lease is held.

        Only receive/transmit timing failures are retried. Disconnects,
        unknown routes, and every other safety failure remain immediate and
        fail closed.
        """
        deadline = time.monotonic() + max(0.1, float(timeout))
        last_error: Optional[StationActionError] = None
        while True:
            try:
                return await self._fresh_receive_state()
            except StationActionError as exc:
                if exc.code not in EXTERNAL_RX_RETRY_CODES:
                    raise
                last_error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                message = (
                    "The external digital engine did not provide a confirmed "
                    "receive window for the amplifier state change"
                )
                raise StationActionError(
                    "external-digital-rx-window-timeout",
                    message,
                    status_code=503,
                ) from last_error
            await asyncio.sleep(min(0.25, remaining))

    @asynccontextmanager
    async def configuration_update(self, *, route_affecting: bool):
        """Serialize a guarded live configuration update with station actions."""
        async with self._action_lock:
            self._require_operational()
            if self._active_task and not self._active_task.done():
                raise StationActionError(
                    "station-busy",
                    "Station configuration cannot change during an active station transaction",
                )
            if not route_affecting:
                yield
                return
            async with self.radio_lock:
                external_owner = self._manual_amplifier_owner_bypass()
                async with self._external_digital_control_lease(
                    external_owner,
                    "station-configuration-update",
                ):
                    await self._fresh_receive_state()
                    if not await self._request_fail_safe_standby():
                        raise StationActionError(
                            "kpa-standby-not-confirmed",
                            "KPA500 standby could not be confirmed before reconfiguration",
                            status_code=503,
                        )
                    yield

    def invalidate_route(self) -> None:
        """Invalidate any prior authorization evidence after configuration changes."""
        self._route_verified = None

    def _assert_follow_current(self, generation: int, route: RouteTarget) -> None:
        """Reject a follower transaction superseded by a newer observed route."""
        current = self._route_for_snapshot(self._radio_snapshot())
        if (
            generation != self._follow_generation
            or current is None
            or current.route_id != route.route_id
            or round(current.frequency_mhz * 1000)
            != round(route.frequency_mhz * 1000)
            or current.digital_mode is not route.digital_mode
        ):
            raise StationActionError(
                "observed-route-superseded",
                "Observed FLEX route changed while the Station Profile was being applied",
            )

    def _observed_route_needs_follow(
        self,
        route: RouteTarget,
        radio: dict[str, Any],
        *,
        include_drive: bool = True,
        include_kat_frequency: bool = True,
    ) -> bool:
        """Return whether cached hardware evidence differs from a FLEX route.

        This is deliberately stricter than the path display.  A KAT frequency
        inside the same amateur band is acceptable evidence for a passive RF
        path, but it is not enough to select the correct KAT frequency memory.
        Drive alone does not launch a full multi-device follow transaction;
        transmit preflight and manual OPERATE own the final exact drive value.
        """
        state = self.elecraft.snapshot()
        kpa = state.get("kpa500") or {}
        kat = state.get("kat500") or {}
        # Drive is part of the station route, not a digital-engine setting.
        # Compare against the physical amplifier state so a manually selected
        # OPERATE route is not repeatedly knocked back to standby, while a
        # standby/barefoot path follows its configured per-band power for
        # SmartSDR, WSJT, MSHV, CW, and SSB alike.
        expected_drive = (
            route.amplifier_drive_w
            if kpa.get("operate") is True and route.amplifier_allowed
            else route.barefoot_drive_w
        )
        try:
            observed_drive = int(radio.get("drive"))
        except (TypeError, ValueError):
            observed_drive = None
        return bool(
            kpa.get("band") != route.band
            or (kpa.get("operate") is True and not route.amplifier_allowed)
            or kat.get("band") != route.band
            or (
                include_kat_frequency
                and kat.get("frequency_khz") != round(route.frequency_mhz * 1000)
            )
            or kat.get("antenna") != route.kat_antenna
            or str(radio.get("tx_ant") or "").upper() != route.flex_tx_ant
            or (
                include_drive
                and observed_drive is not None
                and observed_drive != expected_drive
            )
        )

    async def follow_observed_radio_route(self, frequency: float | None) -> bool:
        """Safely apply an externally observed FLEX route while remaining in RX.

        ``ElecraftManager.sync_radio_state`` is observation-only in production;
        its retired direct-write path is intentionally disabled.  This method
        supplies the coordinator-owned replacement for SmartSDR/CAT changes:
        it requires commissioned, fresh receive state, puts the amplifier in
        standby, applies the complete route and verifies exact readback.  It
        never enables MOX or TUNE.  A manual OPERATE selection is restored
        after verification when the target route still permits amplification.
        """
        if not bool(getattr(self.elecraft, "follow_radio", True)) or not self.commissioned:
            return False
        if self._maintenance or self._recovery_required or self._stopped or self.busy:
            return False

        radio = self._radio_snapshot()
        observed_frequency, observed_mode, _observed_at = (
            self._transmit_route_observation(radio)
        )
        if observed_frequency is None:
            observed_frequency = frequency
        route = self._route_for_frequency(observed_frequency, observed_mode)
        if route is None:
            return False
        try:
            observed_khz = round(float(observed_frequency) * 1000)
        except (TypeError, ValueError):
            return False
        topology_needs_follow = self._observed_route_needs_follow(
            route,
            radio,
            include_drive=False,
            include_kat_frequency=False,
        )
        any_needs_follow = self._observed_route_needs_follow(
            route,
            radio,
            include_drive=False,
        )
        if (
            radio.get("connected") is not True
            or radio.get("known") is not True
            or radio.get("stale") is not False
            or radio.get("mox") is not False
            or observed_khz != round(route.frequency_mhz * 1000)
            or not any_needs_follow
        ):
            return False

        target = (
            route.band,
            round(route.frequency_mhz * 1000),
            route.flex_tx_ant,
            route.kat_antenna,
            route.active_drive_w,
            route.digital_mode,
        )
        if self.busy and self._follow_inflight_target == target:
            return False
        now = time.monotonic()
        if self._last_follow_attempt == target and now - self._last_follow_attempt_at < 3.0:
            return False
        self._follow_generation += 1
        follow_generation = self._follow_generation
        self._follow_inflight_target = target
        self._last_follow_attempt = target
        self._last_follow_attempt_at = now
        follow_started = time.monotonic()
        follow_stages: dict[str, float] = {}

        def follow_stage(name: str) -> None:
            follow_stages[name] = round((time.monotonic() - follow_started) * 1000, 1)

        try:
            async with self._action_lock:
                follow_stage("action_lock_acquired_ms")
                self._require_no_training()
                self._require_commissioned()
                self._require_operational()
                if self._stopped:
                    return False
                if self._active_task and not self._active_task.done():
                    return False
                async with self.radio_lock:
                    follow_stage("radio_lock_acquired_ms")
                    self._assert_follow_current(follow_generation, route)
                    current_route = self._require_fresh_route()
                    current_radio = self._radio_snapshot()
                    # The follower may wait behind an Elecraft poll or another
                    # action. Re-evaluate the mismatch after acquiring both
                    # locks; a transient/old device snapshot must never cause
                    # a now-aligned KPA to be dropped into standby.
                    topology_needs_follow = self._observed_route_needs_follow(
                        current_route,
                        current_radio,
                        include_drive=False,
                        include_kat_frequency=False,
                    )
                    any_needs_follow = self._observed_route_needs_follow(
                        current_route,
                        current_radio,
                        include_drive=False,
                    )
                    if not any_needs_follow:
                        return False
                    if topology_needs_follow:
                        # Confirm the exact passive accessory route without
                        # repeating meters, firmware, voltage, and other idle
                        # telemetry.  A just-published FLEX RX observation can
                        # be reused while KPA standby is freshly proven; an
                        # OPERATE, old, incomplete, or mismatched observation
                        # still forces a direct FLEX preflight before any write.
                        route_refresh = getattr(
                            self.elecraft, "refresh_route_status", None
                        )
                        if callable(route_refresh):
                            await route_refresh()
                        else:
                            await self.elecraft.refresh_status()
                        follow_stage("accessory_preflight_ms")
                        self._assert_follow_current(follow_generation, current_route)
                        current_route = self._require_fresh_route()
                        observed_kpa = self.elecraft.snapshot().get("kpa500") or {}
                        reuse_flex_observation = bool(
                            observed_kpa.get("route_complete") is True
                            and observed_kpa.get("operate") is False
                            and self._recent_receive_route_observation(current_route)
                        )
                        if not reuse_flex_observation:
                            current_route = await self._refresh_route_for_action()
                        follow_stage("flex_preflight_ms")
                        self._assert_follow_current(follow_generation, current_route)
                        current_radio = self._radio_snapshot()
                        topology_needs_follow = self._observed_route_needs_follow(
                            current_route,
                            current_radio,
                            include_drive=False,
                            include_kat_frequency=False,
                        )
                        any_needs_follow = self._observed_route_needs_follow(
                            current_route,
                            current_radio,
                            include_drive=True,
                        )
                        if not any_needs_follow:
                            logger.info(
                                "Ignored transient cached station-route mismatch "
                                "after fresh hardware confirmation on %s",
                                current_route.band,
                            )
                            return False
                    observed_kpa = self.elecraft.snapshot().get("kpa500") or {}
                    if observed_kpa.get("operate") is True:
                        self._manual_operate_requested = True
                        if not topology_needs_follow:
                            # The station path is unchanged; only the KAT's
                            # advisory frequency-memory address differs.  Do
                            # not start a relay transaction or alter the
                            # operator-selected amplifier mode for a
                            # same-band QSY.  The KAT remains in AUTO and the
                            # exact memory address is refreshed after an
                            # explicit Standby selection.
                            logger.info(
                                "Deferred same-band KAT frequency follow to %d kHz "
                                "while KPA500 remains in operator-selected OPERATE",
                                round(current_route.frequency_mhz * 1000),
                            )
                            return False
                    observed_band = str(observed_kpa.get("band") or "").strip().lower()
                    band_changed = observed_band != current_route.band.lower()
                    same_verified_target = bool(
                        self._route_verified
                        and self._route_verified.get("route_id")
                        == current_route.route_id
                        and self._route_verified.get("frequency_khz")
                        == round(current_route.frequency_mhz * 1000)
                        and self._route_verified.get("digital_mode", False)
                        is current_route.digital_mode
                    )
                    if (
                        topology_needs_follow
                        and same_verified_target
                        and observed_kpa.get("operate") is True
                    ):
                        # The FLEX route itself has not changed since the last
                        # successful exact verification. Do not let a periodic
                        # accessory/status anomaly turn an operating amplifier
                        # off. The path remains visibly unconfirmed and every
                        # transmit preflight still fails closed until readback
                        # agrees again; explicit Prepare Route remains available
                        # when the operator actually wants hardware rewritten.
                        logger.warning(
                            "Refusing automatic standby on unchanged verified "
                            "route %s while KPA500 is in OPERATE",
                            current_route.route_id,
                        )
                        return False
                    restore_operate = bool(
                        self._manual_operate_requested and current_route.amplifier_allowed
                    )
                    preserve_operate = bool(
                        restore_operate and observed_kpa.get("operate") is True
                    )
                    # A selected digital engine may be armed for a future slot even
                    # though the authoritative FLEX readback is presently RX.  The
                    # route has to follow that engine's observed CAT QSY *before*
                    # its next transmission; treating future TX intent as a reason
                    # to leave KPA/KAT on the previous band is both unusable and
                    # unsafe.  This bypasses only the ownership/armed-intent guard.
                    # _prepare_route still proves fresh RX before and throughout
                    # the transaction, forces KPA standby, and verifies every
                    # FLEX/KPA/KAT route readback without enabling TX.
                    await self._prepare_route(
                        route=current_route,
                        allow_digital_owner=True,
                        follow_generation=follow_generation,
                        # A current-band Maestro override belongs to the
                        # operator. Apply configured drive only when the band
                        # changes; same-band frequency/mode changes preserve it.
                        preserve_observed_drive=not band_changed,
                        preserve_kpa_operate=preserve_operate,
                    )
                    follow_stage("route_prepared_ms")
                    if restore_operate and not preserve_operate:
                        self._assert_follow_current(follow_generation, current_route)
                        await self._operate(
                            route=current_route,
                            allow_digital_owner=True,
                            preserve_observed_drive=not band_changed,
                        )
        finally:
            if follow_generation == self._follow_generation:
                self._follow_inflight_target = None
            follow_stage("total_ms")
            logger.info(
                "Accessory follow timing route=%s cumulative_ms=%s",
                route.route_id,
                follow_stages,
            )
        logger.info(
            "Safely followed observed FLEX route to %s at %d kHz "
            "(operate_restored=%s)",
            route.band,
            round(route.frequency_mhz * 1000),
            restore_operate,
        )
        return True

    async def execute_raw_flex_tx(
        self,
        action: str,
        operation: Callable[[], Any],
    ) -> bool:
        """Authorize and execute one raw FLEX TX-on command atomically.

        The coordinator always acquires locks in action-then-radio order and
        keeps both through the actual MOX/TUNE command.  This prevents the
        authorization readbacks from becoming stale between preflight and TX.
        """
        normalized = str(action or "").strip().lower()
        if normalized not in {"mox", "tune", "cwx"}:
            raise StationActionError(
                "raw-flex-tx-action-invalid",
                f"Unsupported raw FLEX transmit action: {normalized or 'unknown'}",
            )

        async with self._action_lock:
            self._require_no_training()
            self._require_commissioned()
            self._require_operational()
            if self._stopped:
                raise StationActionError(
                    "station-stopped",
                    "Station control is stopping or stopped",
                    status_code=503,
                )
            if self._active_task and not self._active_task.done():
                raise StationActionError(
                    "station-tune-active",
                    "A coordinated station tune is already running",
                )

            async with self.radio_lock:
                try:
                    self._assert_digital_idle()
                    route = self._require_fresh_route()
                    await self._fresh_receive_state()
                    await self._fresh_flex_route(route)

                    kpa = self.elecraft.kpa500
                    kat = self.elecraft.kat500
                    if kpa is None or kat is None:
                        raise StationActionError(
                            "station-device-missing",
                            "KPA500 and KAT500 are required before FLEX transmit can be enabled",
                        )

                    kpa_status, kat_status = await asyncio.gather(
                        self._device_readback(kpa),
                        self._device_readback(kat),
                    )
                    kpa_expected: dict[str, Any] = {
                        "power": True,
                        "band": route.band,
                        "fault": "00",
                    }
                    if normalized == "tune":
                        kpa_expected["operate"] = False
                    kpa_verification = verify_exact_target(kpa_status, kpa_expected)
                    kat_verification = verify_exact_target(
                        kat_status,
                        {
                            "power": True,
                            "band": route.band,
                            "antenna": route.kat_antenna,
                            "frequency_khz": round(route.frequency_mhz * 1000),
                            "tuning": False,
                            "fault": "0",
                        },
                    )
                    mismatches = [
                        f"KPA500 {item['field']} is {item['actual']!r}, expected {item['expected']!r}"
                        for item in kpa_verification["mismatches"]
                    ]
                    mismatches.extend(
                        f"KAT500 {item['field']} is {item['actual']!r}, expected {item['expected']!r}"
                        for item in kat_verification["mismatches"]
                    )
                    if type(kpa_status.get("operate")) is not bool:
                        mismatches.append("KPA500 operate state is not confirmed")
                    if kat_status.get("mode") not in {"auto", "manual"}:
                        mismatches.append(
                            f"KAT500 mode is {kat_status.get('mode')!r}, expected AUTO or MANUAL"
                        )
                    if mismatches:
                        raise StationActionError(
                            "route-readback-mismatch",
                            "; ".join(mismatches),
                        )

                    result = await asyncio.wait_for(run_radio_io(operation), timeout=3.0)
                    if result is not True:
                        raise StationActionError(
                            "flex-tx-command-rejected",
                            "FLEX rejected the transmit command",
                            status_code=503,
                        )
                    return True
                except StationActionError:
                    raise
                except Exception as exc:
                    raise StationActionError(
                        "raw-flex-tx-preflight-failed",
                        f"Raw FLEX transmit safety checks failed: {exc}",
                        status_code=503,
                    ) from exc

    async def execute_flex_route_change(
        self,
        reason: str,
        operation: Callable[[], Any],
        *,
        allow_digital_owner: bool = False,
        target_frequency_mhz: float | None = None,
        target_mode: str | None = None,
    ) -> bool:
        """Apply a guarded FLEX route mutation while the radio is in receive.

        A same-band frequency change does not alter the RF topology.  When the
        KPA is already in a freshly confirmed, fault-free OPERATE state and the
        destination route still permits amplification, preserve the operator's
        explicit selection.  Unknown destinations, band changes, policy
        changes, or incomplete accessory evidence retain the fail-safe standby
        behaviour.
        """
        started = time.monotonic()
        stages: dict[str, float] = {}
        async with self._action_lock:
            stages["action_lock_ms"] = (time.monotonic() - started) * 1000
            self._require_no_training()
            self._require_operational()
            if self._stopped:
                raise StationActionError(
                    "station-stopped",
                    "Station control is stopping or stopped",
                    status_code=503,
                )
            if self._active_task and not self._active_task.done():
                raise StationActionError(
                    "station-busy",
                    "A station transaction is already running",
                )
            async with self.radio_lock:
                stages["radio_lock_ms"] = (time.monotonic() - started) * 1000
                if not allow_digital_owner:
                    self._assert_digital_idle()
                await self._fresh_receive_state()
                stages["receive_confirmed_ms"] = (time.monotonic() - started) * 1000
                preserve_operate = False
                if target_frequency_mhz is not None:
                    current_route = self._require_fresh_route()
                    target_route = self._route_for_frequency(
                        target_frequency_mhz,
                        target_mode if target_mode is not None else current_route.radio_mode,
                    )
                    if (
                        target_route is not None
                        and target_route.route_id == current_route.route_id
                        and target_route.amplifier_allowed
                    ):
                        kpa = self.elecraft.kpa500
                        kat = self.elecraft.kat500
                        if kpa is not None and kat is not None:
                            kpa_status, kat_status = await asyncio.gather(
                                self._device_readback(kpa),
                                self._device_readback(kat),
                            )
                            preserve_operate = bool(
                                verify_exact_target(
                                    kpa_status,
                                    {
                                        "power": True,
                                        "operate": True,
                                        "band": current_route.band,
                                        "fault": "00",
                                    },
                                )["verified"]
                                and verify_exact_target(
                                    kat_status,
                                    {
                                        "power": True,
                                        "band": current_route.band,
                                        "antenna": current_route.kat_antenna,
                                        "tuning": False,
                                        "fault": "0",
                                    },
                                )["verified"]
                            )
                if preserve_operate:
                    self._manual_operate_requested = True
                    stages["operate_preserved_ms"] = (time.monotonic() - started) * 1000
                    logger.info(
                        "Preserving operator-selected KPA500 OPERATE for same-band "
                        "FLEX route change reason=%s target=%.6f MHz",
                        reason,
                        target_frequency_mhz,
                    )
                else:
                    if not await self._request_fail_safe_standby():
                        raise StationActionError(
                            "kpa-standby-not-confirmed",
                            "KPA500 standby could not be confirmed before changing route",
                            status_code=503,
                        )
                    stages["standby_confirmed_ms"] = (time.monotonic() - started) * 1000
                self._route_verified = None
                try:
                    result = await asyncio.wait_for(run_radio_io(operation), timeout=3.0)
                except BaseException:
                    if preserve_operate:
                        await self._request_fail_safe_standby()
                    raise
                if result is not True:
                    if preserve_operate:
                        await self._request_fail_safe_standby()
                    raise StationActionError(
                        "flex-route-command-rejected",
                        f"FLEX rejected route change: {reason}",
                        status_code=503,
                    )
                stages["command_complete_ms"] = (time.monotonic() - started) * 1000
                logger.info("FLEX route timing reason=%s cumulative_ms=%s", reason,
                            {key: round(value, 1) for key, value in stages.items()})
                return True

    async def _claim_training_tx_monitor(self, job_id: str) -> None:
        """Reuse the primary FLEX socket as the job's sole TCP connection."""
        if (
            self._training_tx_monitor is not None
            and self._training_tx_monitor_job_id == job_id
            and getattr(self._training_tx_monitor, "sock", None) is not None
        ):
            return
        self._release_training_tx_monitor()
        flex = self.flex_provider()
        refresh = getattr(flex, "refresh_tx_state_probe", None) if flex is not None else None
        if not callable(refresh):
            # Test doubles and alternate providers retain the legacy one-shot
            # proof path. The production FlexCtl always supplies this refresh.
            return
        state = await run_radio_io(
            lambda: refresh(
                1.5,
                expect_transmitting=False,
            ),
            timeout=2.0,
        )
        if state.get("confirmed") is not True:
            raise StationActionError(
                "flex-tx-monitor-unconfirmed",
                "The existing FLEX interlock subscription could not be confirmed",
                status_code=503,
            )
        self._training_tx_monitor = flex
        self._training_tx_monitor_job_id = job_id
        logger.info("ATU training claimed existing FLEX TCP connection job=%s", job_id)

    def _release_training_tx_monitor(self) -> None:
        job_id = self._training_tx_monitor_job_id
        self._training_tx_monitor = None
        self._training_tx_monitor_job_id = None
        if job_id:
            logger.info("ATU training released existing FLEX TCP connection job=%s", job_id)

    async def _fresh_tx_state(self, *, expect_transmitting: bool) -> dict[str, Any]:
        flex = self.flex_provider()
        if flex is None or not getattr(flex, "sock", None):
            raise StationActionError("flex-disconnected", "FLEX control connection is unavailable")
        try:
            monitor = self._training_tx_monitor
            persistent_refresh = getattr(flex, "refresh_tx_state_probe", None)
            persistent_monitor_required = bool(
                self._training_job_id
                and callable(persistent_refresh)
            )
            if persistent_monitor_required and (
                monitor is None
                or self._training_tx_monitor_job_id != self._training_job_id
                or getattr(monitor, "sock", None) is None
            ):
                raise StationActionError(
                    "flex-tx-monitor-disconnected",
                    "The single FLEX training interlock connection was lost; training stopped",
                    status_code=503,
                )
            if (
                monitor is not None
                and self._training_tx_monitor_job_id == self._training_job_id
                and getattr(monitor, "sock", None) is not None
            ):
                state = await run_radio_io(
                    lambda: monitor.refresh_tx_state_probe(
                        1.5,
                        expect_transmitting=expect_transmitting,
                    ),
                    timeout=2.0,
                )
            elif callable(persistent_refresh):
                # The normal station workflow performs several consecutive
                # safety proofs. Reuse the primary subscribed socket and its
                # ordered subscription acknowledgement instead of creating a
                # burst of short-lived FLEX clients. Besides avoiding radio
                # connection churn, this keeps every proof in the same
                # serialized I/O lane as normal status polling.
                state = await run_radio_io(
                    lambda: persistent_refresh(
                        1.5,
                        expect_transmitting=expect_transmitting,
                    ),
                    timeout=2.0,
                )
            else:
                # Alternate providers and older test doubles can retain the
                # independent one-shot proof contract.
                state = await run_radio_io(
                    lambda: flex.get_fresh_tx_state(1.5),
                    timeout=3.0,
                )
        except TimeoutError as exc:
            raise StationActionError("flex-tx-proof-timeout", "Fresh FLEX TX state timed out") from exc
        return state

    async def _fresh_receive_state(self) -> dict[str, Any]:
        state = await self._fresh_tx_state(expect_transmitting=False)
        if not state.get("confirmed"):
            raise StationActionError(
                "flex-tx-state-unconfirmed",
                "FLEX receive/transmit state could not be freshly confirmed",
            )
        interlock = str(state.get("interlock_state") or "").upper()
        if state.get("mox") is not False or interlock not in RECEIVE_INTERLOCK_STATES:
            raise StationActionError(
                "flex-not-receiving",
                f"FLEX is not in a confirmed receive-ready state ({interlock or 'unknown'})",
            )
        return state

    async def _fresh_transmit_state(self) -> dict[str, Any]:
        state = await self._fresh_tx_state(expect_transmitting=True)
        interlock = str(state.get("interlock_state") or "").upper()
        if not state.get("confirmed") or not (
            state.get("mox") is True or interlock == "TRANSMITTING"
        ):
            raise StationActionError(
                "tune-carrier-unconfirmed",
                "FLEX tune carrier could not be freshly confirmed",
            )
        return state

    async def _fresh_flex_route(self, route: RouteTarget) -> dict[str, Any]:
        flex = self.flex_provider()
        if flex is None:
            raise StationActionError("flex-disconnected", "FLEX control connection is unavailable")
        levels = await self._bounded_flex_io(
            lambda: flex.get_current_levels(0.8, apply_antenna_policy=False),
            timeout=3.0,
            code="flex-route-proof-timeout",
            message="Fresh FLEX frequency and antenna readback timed out",
        )
        frequency, _mode, _observed_at = self._transmit_route_observation(levels)
        try:
            frequency_khz = round(float(frequency) * 1000)
        except (TypeError, ValueError) as exc:
            raise StationActionError(
                "flex-frequency-unconfirmed",
                "Fresh FLEX frequency readback is unavailable",
            ) from exc
        tx_ant = str(levels.get("tx_ant") or "").upper()
        mismatches = []
        if frequency_khz != round(route.frequency_mhz * 1000):
            mismatches.append(
                f"FLEX frequency is {frequency_khz} kHz, expected {round(route.frequency_mhz * 1000)} kHz"
            )
        if tx_ant != route.flex_tx_ant:
            mismatches.append(f"FLEX TX port is {tx_ant or 'unknown'}")
        if mismatches:
            raise StationActionError("flex-route-readback-mismatch", "; ".join(mismatches))
        return {**levels, "frequency_khz": frequency_khz, "tx_ant": tx_ant}

    async def _refresh_route_for_action(self) -> RouteTarget:
        """Refresh FLEX route evidence inside the guarded action transaction.

        The browser status request and the background FLEX poll are independent
        readers.  A button press must not fail merely because their cached
        snapshot crossed the short freshness threshold just before the action.
        Read the route directly here, publish that observation into the shared
        snapshot, and keep all later exact route/RX checks in place.
        """
        flex = self.flex_provider()
        if flex is None or not getattr(flex, "sock", None):
            raise StationActionError(
                "flex-disconnected",
                "FLEX control connection is unavailable",
                status_code=503,
            )
        levels = await self._bounded_flex_io(
            lambda: flex.get_current_levels(0.8, apply_antenna_policy=False),
            timeout=3.0,
            code="flex-route-proof-timeout",
            message="Fresh FLEX route readback timed out",
        )
        frequency, mode, _observed_at = self._transmit_route_observation(levels)
        route = self._route_for_frequency(frequency, mode)
        if route is None:
            raise StationActionError(
                "route-unresolved",
                "No complete route matches the fresh FLEX frequency readback",
            )
        tx_ant = str(levels.get("tx_ant") or "").upper()
        if not tx_ant:
            raise StationActionError(
                "flex-route-state-unconfirmed",
                "Fresh FLEX TX antenna readback is unavailable",
            )

        # The production provider returns AppContext.radio_snapshot and test
        # providers return their mutable fixture dictionary.  Updating it here
        # closes the browser/background-poll race for subsequent cached proof
        # checks; the exact hardware readbacks below remain authoritative.
        shared_snapshot = self.radio_snapshot_provider()
        if isinstance(shared_snapshot, dict):
            shared_snapshot.update(
                connected=True,
                known=True,
                stale=False,
                observed_at=_utc_now(),
                frequency=float(frequency),
                mode=mode,
                tx_ant=tx_ant,
            )
            if levels.get("tx_frequency") is not None:
                shared_snapshot["tx_frequency"] = levels["tx_frequency"]
            if levels.get("tx_mode") is not None:
                shared_snapshot["tx_mode"] = levels["tx_mode"]
            for key in ("slices", "vfos", "active_receive", "transmit"):
                if key in levels:
                    value = levels[key]
                    if isinstance(value, dict):
                        value = dict(value)
                    elif isinstance(value, list):
                        value = [dict(item) for item in value]
                    shared_snapshot[key] = value
            level_mapping = {
                "rfpower": "drive",
                "tunepower": "tune_power",
                "mox": "mox",
                "interlock_state": "interlock_state",
            }
            for source, target in level_mapping.items():
                if source in levels:
                    shared_snapshot[target] = levels[source]
        return route

    async def _route_for_action(self) -> RouteTarget:
        """Use a fresh cached route, refreshing only an expired FLEX snapshot."""
        try:
            return self._require_fresh_route()
        except StationActionError as exc:
            if exc.code != "flex-route-state-unconfirmed":
                raise
        return await self._refresh_route_for_action()

    async def _bounded_flex_io(
        self,
        operation: Callable[[], Any],
        *,
        timeout: float,
        code: str,
        message: str,
    ) -> Any:
        """Bound shared-socket admission and prevent timed-out late mutations."""
        try:
            return await run_radio_io(operation, timeout=timeout)
        except TimeoutError as exc:
            raise StationActionError(code, message, status_code=503) from exc

    async def _device_call(
        self,
        device: Any,
        method: str,
        *args: Any,
        allow_false: bool = False,
    ) -> Any:
        operation = getattr(device, method, None)
        if operation is None:
            raise StationActionError(
                "device-capability-missing",
                f"{getattr(device, 'name', 'Device')} does not support {method}",
                status_code=503,
            )
        started = time.monotonic()
        async with self.elecraft._lock:
            acquired_at = time.monotonic()
            result = await self.elecraft._run_io(operation, *args)
        finished = time.monotonic()
        logger.info(
            "Elecraft device call timing device=%s method=%s manager_lock_wait_ms=%.1f "
            "io_ms=%.1f total_ms=%.1f",
            getattr(device, "name", "Device"),
            method,
            (acquired_at - started) * 1000,
            (finished - acquired_at) * 1000,
            (finished - started) * 1000,
        )
        if result is None or (result is False and not allow_false):
            raise StationActionError(
                "device-command-failed",
                getattr(device, "last_error", None)
                or f"{getattr(device, 'name', 'Device')} rejected {method}",
                status_code=503,
            )
        return result

    async def _device_readback(self, device: Any) -> dict[str, Any]:
        method = "readback" if hasattr(device, "readback") else "status"
        args: tuple[Any, ...] = () if method == "readback" else (None,)
        result = await self._device_call(device, method, *args)
        if (
            not isinstance(result, dict)
            or not getattr(device, "connected", False)
            or result.get("complete") is not True
        ):
            raise StationActionError(
                "device-readback-unconfirmed",
                f"{getattr(device, 'name', 'Device')} did not return confirmed readback",
                status_code=503,
            )
        return result

    async def _device_value(self, device: Any, method: str) -> Any:
        """Read a scalar device value, preserving valid ``False`` values."""
        return await self._device_call(device, method, allow_false=True)

    async def _clear_kat_fault_in_receive(self, kat: Any) -> None:
        """Clear a latched KAT500 fault only inside a confirmed-RX transaction.

        In particular, KAT500 fault 3 can latch when an exciter is near the
        tuner's safe relay-switch limit while the amplifier key line is
        interrupted.  Leaving that fault latched makes the guarded OPERATE
        workflow impossible even after RF has stopped.  Callers prove RX
        immediately before this helper; exact readback below must then confirm
        the clear before route verification can continue.
        """
        fault = str(await self._device_value(kat, "read_fault") or "").strip()
        if fault in {"", "0"}:
            return
        self._transaction_step("clearing-tuner-fault", 35)
        await self._device_call(kat, "clear_fault")
        cleared = str(await self._device_value(kat, "read_fault") or "").strip()
        if cleared != "0":
            raise StationActionError(
                "kat-fault-not-cleared",
                f"KAT500 fault {cleared or fault} could not be cleared in receive",
                status_code=503,
            )

    async def _clear_kpa_fault_for_explicit_operate(
        self,
        kpa: Any,
        kat: Any,
    ) -> bool:
        """Clear one latched KPA fault only for an explicit guarded OPERATE.

        A KPA fault can remain latched after the underlying RF condition has
        ended.  Fault clear is nevertheless a write, so require fresh receive,
        powered standby, an idle tuner, and an exact zero-output meter before
        issuing it.  The caller invalidates any prior route proof when this
        returns ``True`` and then performs the normal exact route preparation.
        """
        await self._fresh_receive_state()
        fault = str(await self._device_value(kpa, "read_fault") or "").strip()
        if fault == "00":
            return False

        await self._require_accessory_fault_clear_safe(kpa, kat, fault)

        # Re-prove receive immediately before the serialized KPA write.  The
        # outer action/radio locks remain held across this entire operation.
        await self._fresh_receive_state()
        await self._device_call(kpa, "clear_fault")
        cleared_status = await self._device_readback(kpa)
        cleared_fault = str(cleared_status.get("fault") or "").strip()
        if cleared_fault != "00":
            description = KPA500_FAULT_DESCRIPTIONS.get(cleared_fault)
            decoded = f": {description}" if description else ""
            raise StationActionError(
                "kpa-fault-not-cleared",
                f"KPA500 fault {cleared_fault or fault}{decoded} remains active after fault clear.",
            )
        return True

    async def _require_accessory_fault_clear_safe(
        self,
        kpa: Any,
        kat: Any,
        fault: str,
    ) -> None:
        """Prove the shared no-RF state required before either fault clear."""
        await self._fresh_receive_state()
        kpa_status = await self._device_readback(kpa)
        kat_status = await self._device_readback(kat)
        meter = await self._device_call(kpa, "meter_status")
        output_power = meter.get("output_power_w") if isinstance(meter, dict) else None
        safe_to_clear = bool(
            getattr(kpa, "connected", False)
            and getattr(kat, "connected", False)
            and kpa_status.get("power") is True
            and kpa_status.get("operate") is False
            and kat_status.get("tuning") is False
            and isinstance(meter, dict)
            and meter.get("meter_complete") is True
            and not isinstance(output_power, bool)
            and output_power == 0
        )
        if not safe_to_clear:
            raise StationActionError(
                "accessory-fault-clear-unsafe",
                f"Accessory fault {fault or 'unknown'} cannot be cleared unless both accessories "
                "are connected, the amplifier is powered and in standby, the tuner is idle, "
                "KPA500 output is 0 W, and the radio is in receive",
            )

    async def _clear_accessory_faults(self) -> None:
        """Clear latched KPA/KAT faults without enabling RF or amplifier operate."""
        kpa = self.elecraft.kpa500
        kat = self.elecraft.kat500
        if kpa is None or kat is None:
            raise StationActionError(
                "station-device-missing",
                "KPA500 and KAT500 are required",
            )

        await self._fresh_receive_state()
        kpa_fault = str(await self._device_value(kpa, "read_fault") or "").strip()
        kat_fault = str(await self._device_value(kat, "read_fault") or "").strip()
        if kpa_fault == "00" and kat_fault == "0":
            return

        await self._require_accessory_fault_clear_safe(
            kpa,
            kat,
            kpa_fault if kpa_fault != "00" else kat_fault,
        )
        if kpa_fault != "00":
            await self._fresh_receive_state()
            await self._device_call(kpa, "clear_fault")
            cleared_status = await self._device_readback(kpa)
            cleared_fault = str(cleared_status.get("fault") or "").strip()
            if cleared_fault != "00":
                description = KPA500_FAULT_DESCRIPTIONS.get(cleared_fault)
                decoded = f": {description}" if description else ""
                raise StationActionError(
                    "kpa-fault-not-cleared",
                    f"KPA500 fault {cleared_fault or kpa_fault}{decoded} remains active after fault clear.",
                )
        if kat_fault != "0":
            await self._fresh_receive_state()
            await self._clear_kat_fault_in_receive(kat)
        self._route_verified = None

    async def _ensure_kat_amp_key_connected_in_receive(
        self,
        kat: Any,
        kpa: Any,
        *,
        fault_confirmed_clear: bool = False,
    ) -> None:
        """Reconnect and verify the KAT amplifier-key relay in a safe state.

        A cleared KAT fault can leave the physical key interrupt open.  The
        KPA will then accept OPERATE while never keying, which looks like a
        successful action but produces zero amplifier output.  Releasing the
        documented AMPI relay is safe only after fresh FLEX receive proof and
        exact KPA standby/no-fault readback.
        """
        if not fault_confirmed_clear:
            fault = str(await self._device_value(kat, "read_fault") or "").strip()
            if fault != "0":
                raise StationActionError(
                    "kat-fault-active",
                    f"KAT500 fault {fault or 'unknown'} prevents amplifier key-line reconnect",
                )
        interrupted = await self._device_value(kat, "read_amp_key_interrupted")
        if interrupted is False:
            return
        if interrupted is not True:
            raise StationActionError(
                "kat-key-interrupt-unknown",
                "KAT500 amplifier key-interrupt state could not be confirmed",
                status_code=503,
            )

        # The expensive complete KPA readback is needed only when AMPI is
        # actually open and a physical relay write will be performed.  A
        # healthy AMPI0 path returns above after two focused KAT queries.
        await self._fresh_receive_state()
        kpa_status = await self._device_readback(kpa)
        kpa_safe = verify_exact_target(
            kpa_status,
            {"power": True, "operate": False, "fault": "00"},
        )
        if not kpa_safe["verified"]:
            raise StationActionError(
                "kpa-standby-not-confirmed",
                "KPA500 standby/no-fault readback is required before reconnecting its key line",
            )
        fault = str(await self._device_value(kat, "read_fault") or "").strip()
        if fault != "0":
            raise StationActionError(
                "kat-fault-active",
                f"KAT500 fault {fault or 'unknown'} prevents amplifier key-line reconnect",
            )
        tuning = await self._device_value(kat, "tune_status")
        if tuning is True:
            self._transaction_step("cancelling-stale-tuner-state", 40)
            await self._device_call(kat, "cancel_tune")
            for _attempt in range(KAT_TUNE_CANCEL_VERIFY_ATTEMPTS):
                await asyncio.sleep(KAT_TUNE_CANCEL_SETTLE_SECONDS)
                tuning = await self._device_value(kat, "tune_status")
                if tuning is False:
                    break
            if tuning is not False:
                raise StationActionError(
                    "kat-tune-cancel-not-confirmed",
                    "KAT500 did not confirm idle after the receive-only cancel request",
                    status_code=503,
                )
            # Cancellation can take until the end of the current tuning step.
            # Re-prove receive and KPA standby immediately before touching K23.
            await self._fresh_receive_state()
            kpa_status = await self._device_readback(kpa)
            kpa_safe = verify_exact_target(
                kpa_status,
                {"power": True, "operate": False, "fault": "00"},
            )
            if not kpa_safe["verified"]:
                raise StationActionError(
                    "kpa-standby-not-confirmed",
                    "KPA500 standby/no-fault readback changed while cancelling KAT500 tune",
                )
            fault = str(await self._device_value(kat, "read_fault") or "").strip()
            if fault != "0":
                raise StationActionError(
                    "kat-fault-active",
                    f"KAT500 fault {fault or 'unknown'} prevents amplifier key-line reconnect",
                )
        elif tuning is not False:
            raise StationActionError(
                "kat-tune-state-unknown",
                "KAT500 tuning state must be confirmed idle before reconnecting its key line",
                status_code=503,
            )
        self._transaction_step("reconnecting-amplifier-key", 45)
        await self._fresh_receive_state()
        await self._device_call(kat, "set_amp_key_interrupted", False)
        # Elecraft documents that K23 may take a few milliseconds to move
        # after AMPI0.  Verify the single guarded write with bounded read-only
        # retries rather than immediately treating the old relay state as a
        # failure and flooding the follower with another route transaction.
        for _attempt in range(AMP_KEY_VERIFY_ATTEMPTS):
            await asyncio.sleep(AMP_KEY_RELAY_SETTLE_SECONDS)
            if await self._device_value(kat, "read_amp_key_interrupted") is False:
                return
        raise StationActionError(
            "kat-key-interrupt-not-cleared",
            "KAT500 did not reconnect the amplifier key line",
            status_code=503,
        )

    def _start_transaction(self, kind: str, route: Optional[RouteTarget]) -> dict[str, Any]:
        self._transaction = {
            "id": uuid.uuid4().hex,
            "kind": kind,
            "state": "running",
            "step": "starting",
            "progress": 0,
            "started_at": _utc_now(),
            "finished_at": None,
            "route_id": route.route_id if route else None,
            "error": None,
        }
        return self._transaction

    def _transaction_step(self, step: str, progress: int) -> None:
        if self._transaction:
            self._transaction["step"] = step
            self._transaction["progress"] = max(0, min(100, int(progress)))

    def _finish_transaction(self, state: str, error: Optional[StationActionError] = None) -> None:
        if not self._transaction:
            return
        self._transaction.update(
            {
                "state": state,
                "progress": 100 if state == "succeeded" else self._transaction.get("progress", 0),
                "finished_at": _utc_now(),
                "error": (
                    {"code": error.code, "message": error.message}
                    if error
                    else None
                ),
            }
        )

    async def _bounded_cancel_standby_cleanup(self, action: str) -> None:
        """Finish cancellation cleanup before releasing the station locks.

        ``asyncio.wait_for`` cancels the route/operate coroutine on timeout.
        ``CancelledError`` is a ``BaseException`` on supported Python versions,
        so the ordinary failure handlers do not run.  Keep this cleanup inline
        and bounded: callers still hold the action/radio locks, preventing a
        replacement transaction from overlapping the fail-safe standby proof.
        A second cancellation is deliberately not swallowed.
        """
        try:
            confirmed = await asyncio.wait_for(
                self._request_fail_safe_standby(),
                timeout=6.0,
            )
        except TimeoutError:
            logger.error(
                "Timed out requesting KPA500 fail-safe standby after cancelled %s",
                action,
            )
            return
        except Exception:
            logger.error(
                "Could not complete KPA500 fail-safe standby after cancelled %s",
                action,
                exc_info=True,
            )
            return
        if not confirmed:
            logger.error(
                "KPA500 fail-safe standby was not confirmed after cancelled %s",
                action,
            )

    async def _record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.telemetry is None:
            return
        try:
            transaction = payload.get("transaction") or self._transaction or {}
            severity = "info"
            if str(transaction.get("state") or "").lower() in {"failed", "error"}:
                severity = "error"
            elif str(transaction.get("state") or "").lower() in {"cancelled", "canceled"}:
                severity = "warning"
            event = StationEvent(
                occurred_at=datetime.now(UTC),
                event_type=event_type,
                severity=severity,
                source="station-coordinator",
                details=payload,
                correlation_id=transaction.get("id"),
            )
            await asyncio.to_thread(self.telemetry.record_event, event)
        except Exception:
            logger.warning("Could not record station event %s", event_type, exc_info=True)

    async def _record_tune_result(
        self,
        route: RouteTarget,
        *,
        swr_before: Optional[float],
        swr_after: Optional[float],
    ) -> None:
        if self.telemetry is None or not self._transaction:
            return
        try:
            started_at = datetime.fromisoformat(str(self._transaction["started_at"]))
            finished_value = self._transaction.get("finished_at") or _utc_now()
            completed_at = datetime.fromisoformat(str(finished_value))
            result = TuneResult(
                transaction_id=str(self._transaction["id"]),
                started_at=started_at,
                completed_at=completed_at,
                outcome=str(self._transaction.get("state") or "unknown"),
                source="station-coordinator",
                route_id=route.route_id,
                frequency_hz=round(route.frequency_mhz * 1_000_000),
                swr_before=swr_before,
                swr_after=swr_after,
                details=dict(self._transaction),
            )
            await asyncio.to_thread(self.telemetry.record_tune_result, result)
        except Exception:
            logger.warning("Could not record station tune result", exc_info=True)

    async def capture_telemetry(self, state: Optional[dict[str, Any]] = None) -> None:
        """Persist one normalized cached observation without touching hardware."""
        if self.telemetry is None:
            return
        station_state = state or self.snapshot()
        elecraft_state = self.elecraft.snapshot()
        radio = self._radio_snapshot()
        kpa = elecraft_state.get("kpa500") or {}
        kat = elecraft_state.get("kat500") or {}
        metrics: dict[str, float | int | bool | None] = {
            "radio.frequency_mhz": radio.get("frequency"),
            "radio.drive_w": radio.get("drive"),
            "radio.tune_power_w": radio.get("tune_power"),
            "kpa.output_power_w": kpa.get("output_power_w"),
            "kpa.swr": kpa.get("swr"),
            "kpa.temperature_c": kpa.get("temperature_c"),
            "kpa.voltage_v": kpa.get("voltage"),
            "kpa.current_a": kpa.get("current"),
            "kat.swr": kat.get("swr"),
        }
        units = {
            "radio.frequency_mhz": "MHz",
            "radio.drive_w": "W",
            "radio.tune_power_w": "W",
            "kpa.output_power_w": "W",
            "kpa.temperature_c": "degC",
            "kpa.voltage_v": "V",
            "kpa.current_a": "A",
        }
        path = station_state.get("path") or {}
        quality = "good"
        if radio.get("stale") or path.get("alignment") == "unknown":
            quality = "stale"
        elif station_state.get("issues"):
            quality = "degraded"
        snapshot = StationSnapshot(
            observed_at=datetime.now(UTC),
            received_at=datetime.now(UTC),
            source="station-coordinator",
            quality=quality,
            stale_after_seconds=float(
                getattr(config, "STATION_TELEMETRY_INTERVAL_SECONDS", 5.0)
            ) * 2.5,
            state=station_state,
            metrics=metrics,
            units=units,
        )
        try:
            await asyncio.to_thread(self.telemetry.record_snapshot, snapshot)
        except Exception:
            logger.warning("Could not record station snapshot", exc_info=True)

    async def telemetry_loop(self) -> None:
        """Capture cached telemetry periodically and prune only bounded raw data."""
        interval = max(
            1.0,
            min(60.0, float(getattr(config, "STATION_TELEMETRY_INTERVAL_SECONDS", 5.0))),
        )
        next_prune = 0.0
        while not self._stopped:
            try:
                await self.capture_telemetry()
                now = time.monotonic()
                if self.telemetry is not None and now >= next_prune:
                    retention_days = int(
                        getattr(config, "STATION_TELEMETRY_RETENTION_DAYS", 7)
                    )
                    await asyncio.to_thread(
                        self.telemetry.prune_raw_data,
                        telemetry_days=retention_days,
                        snapshot_days=retention_days,
                    )
                    next_prune = now + 24 * 60 * 60
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Station telemetry loop degraded", exc_info=True)
            await asyncio.sleep(interval)

    async def perform(self, action: str) -> dict[str, Any]:
        normalized = str(action or "").strip().lower()
        self._require_operational()
        if normalized == "cancel":
            return await self.cancel()
        self._require_no_training()
        if normalized not in {"standby"}:
            self._require_commissioned()
        async with self._action_lock:
            self._require_operational()
            if self._active_task and not self._active_task.done():
                raise StationActionError("station-busy", "A station transaction is already running")
            if normalized == "tune":
                await self._start_tune()
            elif normalized == "standby":
                self._manual_operate_requested = False
                await self._standby()
            else:
                async with self.radio_lock:
                    external_owner = self._manual_amplifier_owner_bypass()
                    async with self._external_digital_control_lease(
                        external_owner,
                        f"manual-{normalized}",
                    ):
                        if normalized == "prepare-route":
                            route = await self._route_for_action()
                            await self._prepare_route(
                                route=route,
                                allow_digital_owner=external_owner,
                            )
                        elif normalized == "clear-faults":
                            await self._clear_accessory_faults()
                        elif normalized == "operate":
                            # OPERATE is one atomic coordinator action.  Do not
                            # require browser clients to prepare the route in a
                            # separate request: background route following can
                            # invalidate that short-lived proof between the two
                            # calls.  Keep both preparation and operate under
                            # the same action/radio locks and digital-control
                            # lease, while retaining every existing RX and
                            # exact-readback safety check.
                            for attempt in range(2):
                                try:
                                    route = await self._route_for_action()
                                    if not route.amplifier_allowed:
                                        raise StationActionError(
                                            "amplifier-not-allowed",
                                            "Amplifier operation is not allowed on this route",
                                        )
                                    kpa = self.elecraft.kpa500
                                    kat = self.elecraft.kat500
                                    if kpa is None or kat is None:
                                        raise StationActionError(
                                            "station-device-missing",
                                            "KPA500 and KAT500 are required",
                                        )
                                    if await self._clear_kpa_fault_for_explicit_operate(kpa, kat):
                                        # Clearing a latched fault changes one
                                        # of the exact route proof fields.  The
                                        # full KPA/KAT/FLEX proof must be
                                        # rebuilt before OPERATE can continue.
                                        self._route_verified = None
                                    if (
                                        not self._route_verification_is_fresh(route)
                                        and not self._adopt_cached_operate_route(route)
                                    ):
                                        await self._prepare_route(
                                            route=route,
                                            allow_digital_owner=external_owner,
                                        )
                                    await self._operate(
                                        route=route,
                                        allow_digital_owner=external_owner,
                                    )
                                    self._manual_operate_requested = True
                                    break
                                except StationActionError as exc:
                                    retry_receive_collision = bool(
                                        external_owner
                                        and attempt == 0
                                        and exc.code in EXTERNAL_RX_RETRY_CODES
                                    )
                                    if not retry_receive_collision:
                                        raise
                                    logger.info(
                                        "Manual KPA500 OPERATE crossed a pre-armed digital "
                                        "TX edge (%s); waiting for RX and retrying under "
                                        "the same control lease",
                                        exc.code,
                                    )
                                    await self._wait_for_external_receive_window()
                        else:
                            raise StationActionError(
                                "unknown-action",
                                f"Unknown station action: {normalized}",
                                status_code=404,
                            )
        return self.snapshot()

    async def prepare_external_digital_route(
        self,
        frequency_mhz: float,
        *,
        amplifier_operate: bool,
    ) -> dict[str, Any]:
        """Prepare a provider-owned digital route after its CAT QSY is observed.

        The digital-engine endpoint authenticates provider ownership and request
        phase before calling this method. All normal radio/device readback and
        commissioning interlocks still apply; only the expected owner check is
        skipped to avoid rejecting the selected external engine itself.
        """
        self._require_no_training()
        self._require_commissioned()
        self._require_operational()
        async with self._action_lock:
            self._require_operational()
            if self._active_task and not self._active_task.done():
                raise StationActionError("station-busy", "A station transaction is already running")
            async with self.radio_lock:
                radio = self._radio_snapshot()
                if (
                    radio.get("connected") is not True
                    or radio.get("known") is not True
                    or radio.get("stale") is not False
                ):
                    raise StationActionError(
                        "flex-route-state-unconfirmed",
                        "A fresh, known FLEX route is required before digital routing",
                    )
                route = self._route_for_frequency(radio.get("frequency"), "DIGU")
                if route is None:
                    raise StationActionError(
                        "route-unresolved",
                        "No complete digital route matches the current FLEX frequency",
                    )
                if round(route.frequency_mhz * 1000) != round(float(frequency_mhz) * 1000):
                    raise StationActionError(
                        "external-route-frequency-mismatch",
                        "Observed FLEX frequency does not match the digital-engine request",
                    )
                await self._prepare_route(route=route, allow_digital_owner=True)
                if amplifier_operate:
                    await self._operate(route=route, allow_digital_owner=True)
        return self.snapshot()

    async def ensure_external_digital_standby(self) -> dict[str, Any]:
        """Confirm KPA standby for an authenticated external digital prepare.

        The caller has already authenticated the managed provider and proved
        fresh FLEX receive state.  Avoid running the broader manual standby
        transaction (and its full KPA/KAT refresh) when an exact fresh KPA
        readback already proves the requested state.  If OPERATE is observed,
        this method still owns the hardware write and verifies the result.
        """
        self._require_no_training()
        self._require_commissioned()
        self._require_operational()
        async with self._action_lock:
            self._require_operational()
            if self._active_task and not self._active_task.done():
                raise StationActionError(
                    "station-busy", "A station transaction is already running"
                )
            kpa = self.elecraft.kpa500
            if kpa is None:
                raise StationActionError("kpa-disabled", "KPA500 is not configured")
            readback = await self._device_readback(kpa)
            expected = {
                "power": True,
                "operate": False,
                "fault": "00",
            }
            verification = verify_exact_target(readback, expected)
            if not verification["verified"]:
                mismatched_fields = {
                    str(item.get("field") or "")
                    for item in verification.get("mismatches", [])
                }
                if mismatched_fields - {"operate"}:
                    raise StationActionError(
                        "kpa-standby-readback-invalid",
                        "Fresh KPA500 readback is not healthy enough to request standby",
                        status_code=503,
                    )
                await self._device_call(kpa, "set_operate", False)
                readback = await self._device_readback(kpa)
                verification = verify_exact_target(readback, expected)
                if not verification["verified"]:
                    raise StationActionError(
                        "kpa-standby-not-confirmed",
                        "KPA500 exact readback did not confirm standby",
                        status_code=503,
                    )
            self._route_verified = None
        return self.snapshot()

    async def enter_maintenance(self) -> dict[str, Any]:
        """Safely release Elecraft serial ports without restarting services."""
        async with self._action_lock:
            self._require_no_training()
            if self._maintenance:
                return self.snapshot()
            if self._stopped:
                raise StationActionError(
                    "station-stopped",
                    "Station control is stopping or stopped",
                    status_code=503,
                )

            task = self._active_task
            if task and not task.done():
                if (self._transaction or {}).get("kind") != "tune":
                    raise StationActionError(
                        "station-busy",
                        "A station transaction is already running",
                    )
                self._cancel_event.set()
                self._transaction_step(
                    "cancelling-for-maintenance",
                    int((self._transaction or {}).get("progress", 0)),
                )
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
                except asyncio.TimeoutError:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                if self._active_task and not self._active_task.done():
                    raise StationActionError(
                        "maintenance-tune-cancel-failed",
                        "The active tune could not be stopped for maintenance",
                        status_code=503,
                    )

            async with self.radio_lock:
                try:
                    self._assert_digital_idle()
                    await self._fresh_receive_state()
                    carrier_off_confirmed = await self._force_carrier_off()
                    standby_confirmed = await self._request_fail_safe_standby()
                    self._route_verified = None
                    if not carrier_off_confirmed or not standby_confirmed:
                        self._recovery_required = True
                        raise StationActionError(
                            "maintenance-safe-state-unconfirmed",
                            "FLEX receive and KPA500 standby must be confirmed before maintenance",
                            status_code=503,
                        )
                    await self.elecraft.suspend_for_maintenance()
                    self._maintenance = True
                    self._recovery_required = False
                except StationActionError:
                    raise
                except Exception as exc:
                    self._recovery_required = True
                    self._maintenance = True
                    try:
                        await self.elecraft.keep_maintenance_suspended()
                    except Exception:
                        logger.error(
                            "Could not finish releasing Elecraft ports after maintenance entry failed",
                            exc_info=True,
                        )
                    raise StationActionError(
                        "maintenance-entry-failed",
                        f"Could not release the Elecraft serial ports: {exc}",
                        status_code=503,
                    ) from exc
        state = self.snapshot()
        await self._record_event("station.maintenance_entered", {"state": state})
        return state

    async def exit_maintenance(self) -> dict[str, Any]:
        """Reclaim, identify, and verify devices before unlocking controls."""
        async with self._action_lock:
            if not self._maintenance:
                raise StationActionError(
                    "station-maintenance-inactive",
                    "Station maintenance mode is not active",
                )
            async with self.radio_lock:
                try:
                    await self.elecraft.reopen_for_maintenance_exit()
                    if not await self._force_carrier_off():
                        raise StationActionError(
                            "maintenance-flex-rx-unconfirmed",
                            "FLEX receive state could not be confirmed after maintenance",
                            status_code=503,
                        )
                    if not await self._request_fail_safe_standby():
                        raise StationActionError(
                            "maintenance-kpa-standby-unconfirmed",
                            "KPA500 standby could not be confirmed after maintenance",
                            status_code=503,
                        )

                    kpa = self.elecraft.kpa500
                    kat = self.elecraft.kat500
                    if kpa is not None:
                        kpa_state = await self._device_readback(kpa)
                        if kpa_state.get("operate") is not False:
                            raise StationActionError(
                                "maintenance-kpa-standby-unconfirmed",
                                "KPA500 exact readback did not confirm standby",
                                status_code=503,
                            )
                    if kat is not None:
                        kat_state = await self._device_readback(kat)
                        if kat_state.get("tuning") is not False:
                            raise StationActionError(
                                "maintenance-kat-state-unconfirmed",
                                "KAT500 exact readback did not confirm an idle tuner",
                                status_code=503,
                            )

                    await self.elecraft.refresh_status(maintenance_verification=True)
                    self._route_verified = None
                    self._recovery_required = False
                    self._maintenance = False
                    await self.elecraft.complete_maintenance_exit()
                except Exception as exc:
                    self._route_verified = None
                    self._recovery_required = True
                    self._maintenance = True
                    try:
                        await self.elecraft.keep_maintenance_suspended()
                    except Exception:
                        logger.error(
                            "Could not close Elecraft ports after failed maintenance exit",
                            exc_info=True,
                        )
                    if isinstance(exc, StationActionError):
                        raise
                    raise StationActionError(
                        "maintenance-exit-verification-failed",
                        f"Maintenance exit verification failed: {exc}",
                        status_code=503,
                    ) from exc
        state = self.snapshot()
        await self._record_event("station.maintenance_exited", {"state": state})
        return state

    async def _standby(self) -> None:
        route = self._route_for_snapshot(self._radio_snapshot())
        transaction = self._start_transaction("standby", route)
        try:
            kpa = self.elecraft.kpa500
            if kpa is None:
                raise StationActionError("kpa-disabled", "KPA500 is not configured")
            self._transaction_step("requesting-standby", 40)
            await self._device_call(kpa, "set_operate", False)
            readback = await self._device_readback(kpa)
            if readback.get("operate") is not False:
                raise StationActionError("kpa-standby-not-confirmed", "KPA500 standby readback failed")
            self._route_verified = None
            await self.elecraft.refresh_status()
            self._finish_transaction("succeeded")
            await self._record_event("station.standby", {"transaction": dict(transaction)})
        except StationActionError as exc:
            await self._request_fail_safe_standby()
            self._finish_transaction("failed", exc)
            raise
        except asyncio.CancelledError:
            error = StationActionError(
                "standby-cancelled",
                "KPA500 standby transaction was cancelled before completion",
                status_code=503,
            )
            self._finish_transaction("failed", error)
            raise
        except Exception as exc:
            error = StationActionError(
                "standby-failed",
                f"Unexpected KPA500 standby failure: {exc}",
                status_code=500,
            )
            await self._request_fail_safe_standby()
            self._finish_transaction("failed", error)
            raise error from exc

    async def _set_and_verify_flex_drive(
        self,
        route: RouteTarget,
        power_w: int,
        *,
        label: str,
    ) -> int:
        """Set an exact FLEX drive value in confirmed RX and verify readback."""
        flex = self.flex_provider()
        if flex is None or not callable(getattr(flex, "set_rf_power", None)):
            raise StationActionError(
                "flex-drive-control-unavailable",
                "FLEX RF drive control is unavailable",
                status_code=503,
            )
        await self._fresh_receive_state()
        drive_set = await self._bounded_flex_io(
            lambda: flex.set_rf_power(int(power_w)),
            timeout=3.0,
            code="flex-drive-command-timeout",
            message=f"FLEX {label} drive command timed out",
        )
        if drive_set is not True:
            raise StationActionError(
                "flex-drive-command-rejected",
                f"FLEX rejected the {int(power_w)} W {label} drive setting",
                status_code=503,
            )
        await self._fresh_receive_state()
        drive_readback = await self._fresh_flex_route(route)
        try:
            observed_drive = int(drive_readback.get("rfpower"))
        except (TypeError, ValueError) as exc:
            raise StationActionError(
                "flex-drive-readback-unconfirmed",
                "FLEX RF drive readback is unavailable",
                status_code=503,
            ) from exc
        if observed_drive != int(power_w):
            raise StationActionError(
                "flex-drive-readback-mismatch",
                f"FLEX RF drive is {observed_drive} W, expected {int(power_w)} W",
                status_code=503,
            )
        return observed_drive

    async def _set_flex_drive_for_operate(
        self,
        route: RouteTarget,
        power_w: int,
    ) -> int:
        """Set amplifier drive and require fresh radio readback before OPERATE."""
        flex = self.flex_provider()
        if flex is None or not callable(getattr(flex, "set_rf_power", None)):
            raise StationActionError(
                "flex-drive-control-unavailable",
                "FLEX RF drive control is unavailable",
                status_code=503,
            )
        drive_set = await self._bounded_flex_io(
            lambda: flex.set_rf_power(int(power_w)),
            timeout=3.0,
            code="flex-drive-command-timeout",
            message="FLEX amplifier drive command timed out",
        )
        if drive_set is not True:
            raise StationActionError(
                "flex-drive-command-rejected",
                f"FLEX rejected the {int(power_w)} W amplifier drive setting",
                status_code=503,
            )

        # A command ACK means only that the radio accepted the request.  It is
        # not evidence that the transmitter is using that drive value.  Prove
        # RX again, then query subscribed radio state before the KPA key line
        # can be armed.  This prevents the previous drive from being used at
        # the leading edge of the next PTT transmission.
        await self._fresh_receive_state()
        drive_readback = await self._fresh_flex_route(route)
        try:
            observed_drive = int(drive_readback.get("rfpower"))
        except (TypeError, ValueError) as exc:
            raise StationActionError(
                "flex-drive-readback-unconfirmed",
                "FLEX RF drive readback is unavailable",
                status_code=503,
            ) from exc
        if observed_drive != int(power_w):
            raise StationActionError(
                "flex-drive-readback-mismatch",
                f"FLEX RF drive is {observed_drive} W, expected {int(power_w)} W",
                status_code=503,
            )
        return observed_drive

    async def _final_route_readbacks(
        self,
        kpa: Any,
        kat: Any,
        route: RouteTarget,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Collect independent final proofs in one bounded observation window.

        FLEX uses a transport independent from the manager-protected KPA/KAT
        serial reads.  Starting all three together retains every exact final
        readback while overlapping the FLEX proof with the serial proofs and
        reducing the interval in which an external route change could split
        the evidence.
        """
        kpa_status, kat_status, levels = await asyncio.gather(
            self._device_readback(kpa),
            self._device_readback(kat),
            self._fresh_flex_route(route),
        )
        return kpa_status, kat_status, levels

    async def _prepare_route(
        self,
        *,
        route: Optional[RouteTarget] = None,
        reuse_transaction: bool = False,
        allow_digital_owner: bool = False,
        follow_generation: Optional[int] = None,
        preserve_observed_drive: bool = False,
        preserve_kpa_operate: bool = False,
    ) -> RouteTarget:
        route = route or self._require_fresh_route()
        if not reuse_transaction:
            self._start_transaction("prepare-route", route)
        kpa_safety_engaged = False
        control_io_started = False
        started = time.monotonic()
        stages: dict[str, float] = {}

        def timed_stage(name: str) -> None:
            stages[name] = round((time.monotonic() - started) * 1000, 1)

        try:
            begin_control_io = getattr(self.elecraft, "begin_control_io", None)
            if callable(begin_control_io):
                begin_control_io()
                control_io_started = True
            self._transaction_step("confirming-receive", 10)
            if not allow_digital_owner:
                self._assert_digital_idle()
            await self._fresh_receive_state()
            timed_stage("receive_confirmed_ms")
            if follow_generation is not None:
                self._assert_follow_current(follow_generation, route)
            flex = self.flex_provider()
            kpa = self.elecraft.kpa500
            kat = self.elecraft.kat500
            if kpa is None or kat is None:
                raise StationActionError(
                    "elecraft-route-incomplete",
                    "Both KPA500 and KAT500 must be configured for the amplified route",
                )

            kpa_safety_engaged = True
            if preserve_kpa_operate:
                self._transaction_step("preserving-amplifier-operate", 25)
                kpa_before = await self._device_readback(kpa)
                kpa_ready = verify_exact_target(
                    kpa_before,
                    {"power": True, "operate": True, "fault": "00"},
                )
                if not kpa_ready["verified"]:
                    raise StationActionError(
                        "kpa-operate-readback-unconfirmed",
                        "KPA500 must freshly confirm powered, fault-free OPERATE "
                        "before preserving operator intent across a route change",
                    )
                if not hasattr(kpa, "set_standby_on_band_change") or not hasattr(
                    kpa, "read_standby_on_band_change"
                ):
                    raise StationActionError(
                        "kpa-band-change-policy-unavailable",
                        "KPA500 band-change mode preservation is unavailable",
                    )
                await self._device_call(kpa, "set_standby_on_band_change", False)
                stay_standby = await self._device_value(
                    kpa, "read_standby_on_band_change"
                )
                if stay_standby is not False:
                    raise StationActionError(
                        "kpa-band-change-policy-unconfirmed",
                        "KPA500 did not confirm OPERATE-preserving band-change mode",
                    )
                timed_stage("operate_preserved_ms")
            else:
                self._transaction_step("amplifier-standby", 25)
                await self._device_call(kpa, "set_operate", False)
                kpa_standby = await self._device_readback(kpa)
                if follow_generation is not None:
                    self._assert_follow_current(follow_generation, route)
                if kpa_standby.get("operate") is not False:
                    raise StationActionError(
                        "kpa-standby-not-confirmed",
                        "KPA500 did not confirm standby",
                    )
                timed_stage("standby_confirmed_ms")

            # A KAT fault is latched by firmware and otherwise blocks the
            # exact route proof forever.  We are in fresh receive with KPA in
            # standby, so this is the safe point to clear and verify it.
            await self._clear_kat_fault_in_receive(kat)
            timed_stage("kat_fault_checked_ms")
            await self._ensure_kat_amp_key_connected_in_receive(
                kat,
                kpa,
                fault_confirmed_clear=True,
            )
            timed_stage("kat_key_connected_ms")

            self._transaction_step("selecting-flex-port", 40)
            flex_ok = await self._bounded_flex_io(
                lambda: flex.enforce_antenna_policy(
                    route.frequency_mhz,
                    reason="station coordinator route preparation",
                ),
                timeout=3.0,
                code="flex-route-command-timeout",
                message="FLEX antenna route selection timed out",
            )
            if not flex_ok:
                raise StationActionError("flex-route-failed", "FLEX antenna policy was not applied")
            if follow_generation is not None:
                self._assert_follow_current(follow_generation, route)
            await self._fresh_flex_route(route)
            timed_stage("flex_port_verified_ms")
            if follow_generation is not None:
                self._assert_follow_current(follow_generation, route)

            self._transaction_step("selecting-elecraft-route", 60)
            await self._fresh_receive_state()
            await self._device_call(kpa, "set_band", route.band)
            timed_stage("kpa_band_ms")
            await self._fresh_receive_state()
            await self._device_call(kat, "set_band", route.band)
            timed_stage("kat_band_ms")
            await self._fresh_receive_state()
            await self._device_call(kat, "set_frequency", route.frequency_mhz)
            timed_stage("kat_frequency_ms")
            await self._fresh_receive_state()
            await self._device_call(kat, "set_antenna", route.kat_antenna)
            timed_stage("kat_antenna_ms")

            self._transaction_step("setting-barefoot-drive", 72)
            if preserve_observed_drive:
                drive_readback = await self._fresh_flex_route(route)
                try:
                    observed_drive = int(drive_readback.get("rfpower"))
                except (TypeError, ValueError) as exc:
                    raise StationActionError(
                        "flex-drive-readback-unconfirmed",
                        "FLEX RF drive readback is unavailable",
                        status_code=503,
                    ) from exc
            else:
                target_drive = (
                    route.amplifier_drive_w
                    if preserve_kpa_operate
                    else route.barefoot_drive_w
                )
                observed_drive = await self._set_and_verify_flex_drive(
                    route,
                    target_drive,
                    label="amplifier" if preserve_kpa_operate else "barefoot",
                )
            if follow_generation is not None:
                self._assert_follow_current(follow_generation, route)

            self._transaction_step("verifying-readback", 80)
            timed_stage("drive_verified_ms")
            kpa_status, kat_status, levels = await self._final_route_readbacks(
                kpa,
                kat,
                route,
            )
            timed_stage("final_readbacks_ms")
            if follow_generation is not None:
                self._assert_follow_current(follow_generation, route)
            kpa_verification = verify_exact_target(
                kpa_status,
                {
                    "power": True,
                    "operate": preserve_kpa_operate,
                    "band": route.band,
                    "fault": "00",
                },
            )
            kat_verification = verify_exact_target(
                kat_status,
                {
                    "power": True,
                    "band": route.band,
                    "antenna": route.kat_antenna,
                    "frequency_khz": round(route.frequency_mhz * 1000),
                    "tuning": False,
                    "fault": "0",
                    "amp_key_interrupted": False,
                },
            )
            mismatches = [
                f"KPA500 {item['field']} is {item['actual']!r}, expected {item['expected']!r}"
                for item in kpa_verification["mismatches"]
            ]
            mismatches.extend(
                f"KAT500 {item['field']} is {item['actual']!r}, expected {item['expected']!r}"
                for item in kat_verification["mismatches"]
            )
            if kat_status.get("mode") not in {"auto", "manual"}:
                mismatches.append(
                    f"KAT500 mode is {kat_status.get('mode')!r}, expected AUTO or MANUAL"
                )
            observed_flex_tx = str(levels.get("tx_ant") or "").upper()
            if observed_flex_tx != route.flex_tx_ant:
                mismatches.append(f"FLEX TX port is {observed_flex_tx or 'unknown'}")
            if mismatches:
                raise StationActionError("route-readback-mismatch", "; ".join(mismatches))

            self._route_verified = {
                "route_id": route.route_id,
                "frequency_mhz": route.frequency_mhz,
                "frequency_khz": round(route.frequency_mhz * 1000),
                "verified_at": time.time(),
                "verified_at_iso": _utc_now(),
                "kpa_operate": preserve_kpa_operate,
                "flex_tx_ant": observed_flex_tx,
                "kat_antenna": int(kat_status["antenna"]),
                "flex_drive_w": observed_drive,
                "digital_mode": route.digital_mode,
            }
            if not reuse_transaction:
                self._finish_transaction("succeeded")
            await self._record_event(
                "station.route_prepared",
                {"route": route.as_dict(), "readback": dict(self._route_verified)},
            )
            publish_readbacks = getattr(self.elecraft, "publish_verified_readbacks", None)
            if callable(publish_readbacks):
                await publish_readbacks(kpa_status, kat_status)
            else:
                await self.elecraft.refresh_status()
            timed_stage("status_published_ms")
            return route
        except StationActionError as exc:
            self._route_verified = None
            if kpa_safety_engaged:
                await self._request_fail_safe_standby()
            if not reuse_transaction:
                self._finish_transaction("failed", exc)
            raise
        except asyncio.CancelledError:
            error = StationActionError(
                "route-preparation-cancelled",
                "Route preparation was cancelled before completion",
                status_code=503,
            )
            self._route_verified = None
            if not reuse_transaction:
                self._finish_transaction("cancelled", error)
            if kpa_safety_engaged:
                await self._bounded_cancel_standby_cleanup("route preparation")
            raise
        except Exception as exc:
            error = StationActionError(
                "route-preparation-failed",
                f"Unexpected route preparation failure: {exc}",
                status_code=500,
            )
            self._route_verified = None
            if kpa_safety_engaged:
                await self._request_fail_safe_standby()
            if not reuse_transaction:
                self._finish_transaction("failed", error)
            raise error from exc
        finally:
            if control_io_started:
                self.elecraft.end_control_io()
            timed_stage("total_ms")
            logger.info("Accessory route timing route=%s cumulative_ms=%s", route.route_id, stages)

    async def _operate(
        self,
        *,
        route: Optional[RouteTarget] = None,
        allow_digital_owner: bool = False,
        preserve_observed_drive: bool = False,
    ) -> None:
        route = route or self._require_fresh_route()
        transaction = self._start_transaction("operate", route)
        try:
            if not allow_digital_owner:
                self._assert_digital_idle()
            await self._fresh_receive_state()
            if not self._route_verification_is_fresh(route):
                raise StationActionError(
                    "route-verification-required",
                    "Prepare and verify the current route before enabling the amplifier",
                )
            if not route.amplifier_allowed:
                raise StationActionError("amplifier-not-allowed", "Amplifier operation is not allowed on this route")
            kpa = self.elecraft.kpa500
            kat = self.elecraft.kat500
            if kpa is None or kat is None:
                raise StationActionError("station-device-missing", "KPA500 and KAT500 are required")

            # The KAT can latch a fault and leave AMPI open after a previous
            # transmission.  Recover it only in freshly confirmed receive and
            # with an exact KPA standby/no-fault readback.  Never bypass an
            # active fault while RF is present.
            self._transaction_step("checking-amplifier-key", 45)
            await self._clear_kat_fault_in_receive(kat)
            await self._ensure_kat_amp_key_connected_in_receive(
                kat,
                kpa,
                fault_confirmed_clear=True,
            )

            self._transaction_step("setting-flex-drive", 70)
            if preserve_observed_drive:
                drive_readback = await self._fresh_flex_route(route)
                try:
                    observed_drive = int(drive_readback.get("rfpower"))
                except (TypeError, ValueError) as exc:
                    raise StationActionError(
                        "flex-drive-readback-unconfirmed",
                        "FLEX RF drive readback is unavailable",
                        status_code=503,
                    ) from exc
            else:
                observed_drive = await self._set_flex_drive_for_operate(
                    route,
                    route.amplifier_drive_w,
                )

            # Recheck the two KAT interlocks after the FLEX write and its
            # readback.  If either changed, fail safe to standby rather than
            # reporting OPERATE with an electrically open key line.
            kat_fault = str(await self._device_value(kat, "read_fault") or "").strip()
            if kat_fault != "0":
                raise StationActionError(
                    "kat-fault-active",
                    f"KAT500 fault {kat_fault or 'unknown'} prevents amplifier operation",
                )
            if await self._device_value(kat, "read_amp_key_interrupted") is not False:
                raise StationActionError(
                    "kat-key-interrupted",
                    "KAT500 amplifier key line is still interrupted",
                )

            self._transaction_step("enabling-amplifier", 90)
            await self._device_call(kpa, "set_operate", True)
            operate_readback = await self._device_call(kpa, "read_operate")
            if operate_readback is not True:
                raise StationActionError("kpa-operate-not-confirmed", "KPA500 operate readback failed")
            if self._route_verified is not None:
                self._route_verified["flex_drive_w"] = observed_drive
                self._route_verified["kpa_operate"] = True
            cache_update = getattr(self.elecraft, "record_kpa_operate_readback", None)
            if callable(cache_update):
                cache_update(True)
            else:
                await self.elecraft.refresh_status()
            self._finish_transaction("succeeded")
            await self._record_event("station.operate", {"transaction": dict(transaction)})
        except StationActionError as exc:
            await self._request_fail_safe_standby()
            self._finish_transaction("failed", exc)
            raise
        except asyncio.CancelledError:
            error = StationActionError(
                "operate-cancelled",
                "Amplifier operate was cancelled before completion",
                status_code=503,
            )
            self._route_verified = None
            self._finish_transaction("cancelled", error)
            await self._bounded_cancel_standby_cleanup("amplifier operate")
            raise
        except Exception as exc:
            error = StationActionError(
                "operate-failed",
                f"Unexpected amplifier operate failure: {exc}",
                status_code=500,
            )
            await self._request_fail_safe_standby()
            self._finish_transaction("failed", error)
            raise error from exc

    async def _start_tune(self) -> None:
        route = self._require_fresh_route()
        if not self._route_verification_is_fresh(route):
            raise StationActionError(
                "route-verification-required",
                "Prepare and verify the route immediately before tuning",
            )
        self._cancel_event = asyncio.Event()
        self._start_transaction("tune", route)
        self._active_task = asyncio.create_task(
            self._run_tune(route),
            name=f"station_tune_{self._transaction['id']}",
        )

    async def _run_tune(self, route: RouteTarget) -> None:
        flex = self.flex_provider()
        kpa = self.elecraft.kpa500
        kat = self.elecraft.kat500
        original_tune_power = getattr(flex, "current_tunepower", None) if flex else None
        carrier_started = False
        swr_before_value: Optional[float] = None
        swr_value: Optional[float] = None
        digital_service = None
        prior_tx_inhibit = None
        radio_lock_acquired = False
        try:
            await self.radio_lock.acquire()
            radio_lock_acquired = True
            if not flex or not kpa or not kat:
                raise StationActionError("station-device-missing", "FLEX, KPA500, and KAT500 are required")
            digital_service = self._assert_digital_idle()
            if digital_service is not None:
                prior_tx_inhibit = getattr(digital_service, "tx_inhibit_reason", None)
                digital_service.tx_inhibit_reason = "station-coordinator-tune"
            self._transaction_step("confirming-receive", 5)
            await self._fresh_receive_state()
            self._transaction_step("rechecking-route", 15)
            prepared_route = await self._prepare_route(route=route, reuse_transaction=True)
            if (
                prepared_route.route_id != route.route_id
                or round(prepared_route.frequency_mhz * 1000)
                != round(route.frequency_mhz * 1000)
            ):
                raise StationActionError(
                    "route-changed",
                    "FLEX frequency or route changed after the tune transaction started",
                )

            tune_power = int(self._policy_value("STATION_TUNE_POWER_W", 20))
            tune_power = max(15, min(30, tune_power))
            self._transaction_step("arming-tuner", 30)
            if hasattr(kat, "start_tune"):
                await self._device_call(kat, "start_tune")
            else:
                raise StationActionError(
                    "nonstoring-tune-unavailable",
                    "KAT500 non-storing tune capability is unavailable",
                    status_code=503,
                )

            self._transaction_step("starting-low-power-carrier", 40)
            await self._fresh_receive_state()
            await self._fresh_flex_route(route)
            tune_power_ok = await self._bounded_flex_io(
                lambda: flex.set_tune_power(tune_power),
                timeout=3.0,
                code="flex-tune-power-timeout",
                message="FLEX tune-power command timed out",
            )
            if not tune_power_ok:
                raise StationActionError("flex-tune-power-failed", "FLEX tune power was not accepted")
            tune_started = await self._bounded_flex_io(
                lambda: flex.set_tune(True),
                timeout=3.0,
                code="flex-tune-start-timeout",
                message="FLEX tune-carrier command timed out",
            )
            if not tune_started:
                raise StationActionError("flex-tune-start-failed", "FLEX tune carrier did not start")
            carrier_started = True
            await self._fresh_transmit_state()

            timeout_seconds = float(
                self._policy_value("STATION_TUNE_TIMEOUT_SECONDS", 30.0)
            )
            deadline = time.monotonic() + max(5.0, min(60.0, timeout_seconds))
            saw_tuning = False
            stable_idle_polls = 0
            while time.monotonic() < deadline:
                if self._cancel_event.is_set():
                    raise StationActionError("tune-cancelled", "Tune was cancelled")
                self._transaction_step("tuning", 55 if not saw_tuning else 70)
                if hasattr(kat, "tune_status"):
                    tuning = await self._device_value(kat, "tune_status")
                else:
                    tuning = (await self._device_readback(kat)).get("tuning")
                if tuning is True:
                    saw_tuning = True
                    stable_idle_polls = 0
                elif tuning is False:
                    if saw_tuning:
                        break
                    # A low-SWR/bypass match can finish before the first TP
                    # poll observes TP1. Two stable idle reads allow the final
                    # on-carrier RF/SWR/fault/route proof below to decide it.
                    stable_idle_polls += 1
                    if stable_idle_polls >= 2:
                        break
                else:
                    stable_idle_polls = 0
                await asyncio.sleep(0.25)
            else:
                raise StationActionError("tune-timeout", "KAT500 tune timed out")

            final_status = await self._device_call(kat, "remote_telemetry")
            await self._fresh_transmit_state()
            await self._fresh_flex_route(route)
            final_verification = verify_exact_target(
                final_status,
                {
                    "tuning": False,
                    "fault": "0",
                    "band": route.band,
                    "antenna": route.kat_antenna,
                    "frequency_khz": round(route.frequency_mhz * 1000),
                },
            )
            if (
                not final_verification["verified"]
                or final_status.get("mode") not in {"auto", "manual"}
            ):
                details = "; ".join(
                    f"{item['field']}={item['actual']!r}, expected {item['expected']!r}"
                    for item in final_verification["mismatches"]
                )
                if final_status.get("mode") not in {"auto", "manual"}:
                    details = (
                        f"{details}; " if details else ""
                    ) + f"mode={final_status.get('mode')!r}, expected AUTO or MANUAL"
                raise StationActionError("tune-readback-mismatch", details)
            swr = final_status.get("swr")
            try:
                swr_value = float(swr)
            except (TypeError, ValueError) as exc:
                raise StationActionError("tune-swr-unknown", "No valid tuned SWR was returned") from exc
            abort_swr = float(self._policy_value("STATION_TUNE_ABORT_SWR", 3.0))
            target_swr = float(self._policy_value("STATION_TUNE_TARGET_SWR", 1.5))
            try:
                forward_adc = int(final_status.get("forward_adc"))
            except (TypeError, ValueError) as exc:
                raise StationActionError(
                    "tune-rf-unconfirmed",
                    "KAT500 forward-power evidence is unavailable",
                ) from exc
            if forward_adc <= 0:
                raise StationActionError(
                    "tune-rf-unconfirmed",
                    "KAT500 did not observe forward RF during the SWR measurement",
                )
            if swr_value < 1.0:
                raise StationActionError(
                    "tune-swr-unconfirmed",
                    f"Tuned SWR {swr_value:.2f} is not a valid on-carrier measurement",
                )
            if swr_value > abort_swr:
                raise StationActionError(
                    "tune-swr-unsafe",
                    f"Tuned SWR {swr_value:.2f} exceeds the {abort_swr:.2f} stop limit",
                )
            if swr_value > target_swr:
                raise StationActionError(
                    "tune-target-not-met",
                    f"Tuned SWR {swr_value:.2f} is above the {target_swr:.2f} target",
                )

            try:
                candidate_before = float(final_status.get("bypass_swr"))
                if candidate_before >= 1.0:
                    swr_before_value = candidate_before
            except (TypeError, ValueError):
                swr_before_value = None

            if not await self._force_carrier_off():
                raise StationActionError(
                    "carrier-off-unconfirmed",
                    "FLEX tune carrier could not be switched off; tuner memory was not stored",
                )
            await self._fresh_flex_route(route)
            carrier_started = False

            if self._cancel_event.is_set():
                raise StationActionError("tune-cancelled", "Tune was cancelled")

            self._transaction_step("storing-memory", 90)
            await self._device_call(kat, "store_memory", round(route.frequency_mhz * 1000))
            if self._transaction is not None:
                self._transaction["swr_before"] = swr_before_value
                self._transaction["swr_after"] = swr_value
            self._finish_transaction("succeeded")
            await self._record_event(
                "station.tune_completed",
                {
                    "route": route.as_dict(),
                    "swr": swr_value,
                    "tune_power_w": tune_power,
                    "transaction": dict(self._transaction or {}),
                },
            )
        except StationActionError as exc:
            if self._transaction is not None:
                self._transaction["swr_before"] = swr_before_value
                self._transaction["swr_after"] = swr_value
            state = "cancelled" if exc.code == "tune-cancelled" else "failed"
            self._finish_transaction(state, exc)
            await self._record_event(
                f"station.tune_{state}",
                {"route": route.as_dict(), "transaction": dict(self._transaction or {})},
            )
        except asyncio.CancelledError:
            error = StationActionError("tune-cancelled", "Tune task was cancelled")
            if self._transaction is not None:
                self._transaction["swr_before"] = swr_before_value
                self._transaction["swr_after"] = swr_value
            self._finish_transaction("cancelled", error)
            raise
        except Exception as exc:
            logger.exception("Unexpected station tune failure")
            error = StationActionError("tune-failed", str(exc), status_code=500)
            if self._transaction is not None:
                self._transaction["swr_before"] = swr_before_value
                self._transaction["swr_after"] = swr_value
            self._finish_transaction("failed", error)
        finally:
            if carrier_started:
                await self._force_carrier_off()
            if kat and self._cancel_event.is_set() and hasattr(kat, "cancel_tune"):
                try:
                    await self._device_call(kat, "cancel_tune")
                except Exception:
                    logger.warning("KAT500 tune cancel was not confirmed", exc_info=True)
            if flex and original_tune_power is not None:
                try:
                    await self._bounded_flex_io(
                        lambda: flex.set_tune_power(int(original_tune_power)),
                        timeout=3.0,
                        code="flex-tune-power-restore-timeout",
                        message="Restoring the prior FLEX tune power timed out",
                    )
                except Exception:
                    logger.error("Could not restore FLEX tune power", exc_info=True)
            try:
                await self._request_fail_safe_standby()
            finally:
                if (
                    digital_service is not None
                    and getattr(digital_service, "tx_inhibit_reason", None)
                    == "station-coordinator-tune"
                ):
                    digital_service.tx_inhibit_reason = prior_tx_inhibit
                if radio_lock_acquired and self.radio_lock.locked():
                    self.radio_lock.release()
                self._active_task = None
            await self._record_tune_result(
                route,
                swr_before=swr_before_value,
                swr_after=swr_value,
            )

    async def _ensure_survey_manual_mode(self) -> None:
        """Prevent AUTO retuning while retaining recalled KAT memory settings."""
        kat = self.elecraft.kat500
        if kat is None:
            raise StationActionError("kat-disconnected", "KAT500 is unavailable")
        state = await self._device_readback(kat)
        mode = str(state.get("mode") or "").lower()
        if mode not in {"auto", "manual"}:
            raise StationActionError(
                "survey-kat-mode-invalid",
                "KAT500 must start an SWR survey in AUTO or MANUAL mode",
            )
        if self._training_original_kat_mode is None:
            self._training_original_kat_mode = mode
        if mode != "manual":
            await self._device_call(kat, "set_mode", "manual")
            state = await self._device_readback(kat)
            if state.get("mode") != "manual":
                raise StationActionError(
                    "survey-manual-mode-unconfirmed",
                    "KAT500 MANUAL mode could not be confirmed before the SWR carrier",
                    status_code=503,
                )

    async def _restore_training_kat_mode(self) -> bool:
        original = self._training_original_kat_mode
        self._training_original_kat_mode = None
        if original not in {"auto", "manual"}:
            return True
        kat = self.elecraft.kat500
        if kat is None:
            return False
        try:
            state = await self._device_readback(kat)
            if state.get("mode") != original:
                await self._device_call(kat, "set_mode", original)
                state = await self._device_readback(kat)
            return state.get("mode") == original
        except Exception:
            logger.error("Could not restore KAT500 mode after SWR survey", exc_info=True)
            return False

    async def _run_swr_survey(self, route: RouteTarget) -> None:
        """Measure the recalled KAT match without tuning or storing memory."""
        flex = self.flex_provider()
        kpa = self.elecraft.kpa500
        kat = self.elecraft.kat500
        original_tune_power = getattr(flex, "current_tunepower", None) if flex else None
        carrier_started = False
        measured_swr: Optional[float] = None
        digital_service = None
        prior_tx_inhibit = None
        radio_lock_acquired = False
        try:
            await self.radio_lock.acquire()
            radio_lock_acquired = True
            if not flex or not kpa or not kat:
                raise StationActionError(
                    "station-device-missing",
                    "FLEX, KPA500, and KAT500 are required",
                )
            digital_service = self._assert_digital_idle()
            if digital_service is not None:
                prior_tx_inhibit = getattr(digital_service, "tx_inhibit_reason", None)
                digital_service.tx_inhibit_reason = "station-coordinator-swr-survey"

            self._transaction_step("confirming-receive", 5)
            await self._fresh_receive_state()
            self._transaction_step("rechecking-route", 15)
            prepared_route = await self._prepare_route(route=route, reuse_transaction=True)
            if prepared_route.route_id != route.route_id:
                raise StationActionError("route-changed", "Station route changed during SWR survey")

            self._transaction_step("survey-manual-mode", 30)
            await self._ensure_survey_manual_mode()
            await self._fresh_receive_state()
            await self._fresh_flex_route(route)

            tune_power = max(
                15,
                min(30, int(self._policy_value("STATION_TUNE_POWER_W", 20))),
            )
            self._transaction_step("starting-survey-carrier", 45)
            tune_power_ok = await self._bounded_flex_io(
                lambda: flex.set_tune_power(tune_power),
                timeout=3.0,
                code="flex-tune-power-timeout",
                message="FLEX survey-power command timed out",
            )
            if not tune_power_ok:
                raise StationActionError(
                    "flex-tune-power-failed",
                    "FLEX survey power was not accepted",
                )
            survey_started = await self._bounded_flex_io(
                lambda: flex.set_tune(True),
                timeout=3.0,
                code="flex-survey-start-timeout",
                message="FLEX survey-carrier command timed out",
            )
            if not survey_started:
                raise StationActionError(
                    "flex-survey-start-failed",
                    "FLEX survey carrier did not start",
                )
            carrier_started = True
            await self._fresh_transmit_state()
            await asyncio.sleep(0.4)

            self._transaction_step("measuring-swr", 70)
            status = await self._device_call(kat, "remote_telemetry")
            await self._fresh_transmit_state()
            await self._fresh_flex_route(route)
            verification = verify_exact_target(
                status,
                {
                    "mode": "manual",
                    "tuning": False,
                    "fault": "0",
                    "band": route.band,
                    "antenna": route.kat_antenna,
                    "frequency_khz": round(route.frequency_mhz * 1000),
                },
            )
            if not verification["verified"]:
                details = "; ".join(
                    f"{item['field']}={item['actual']!r}, expected {item['expected']!r}"
                    for item in verification["mismatches"]
                )
                raise StationActionError("survey-readback-mismatch", details)
            try:
                measured_swr = float(status.get("swr"))
                forward_adc = int(status.get("forward_adc"))
            except (TypeError, ValueError) as exc:
                raise StationActionError(
                    "survey-swr-unconfirmed",
                    "KAT500 did not return qualified live SWR evidence",
                ) from exc
            if measured_swr < 1.0 or forward_adc <= 0:
                raise StationActionError(
                    "survey-swr-unconfirmed",
                    "KAT500 SWR or forward-power evidence is not valid",
                )
            abort_swr = float(self._policy_value("STATION_TUNE_ABORT_SWR", 3.0))
            if measured_swr >= abort_swr:
                raise StationActionError(
                    "survey-swr-unsafe",
                    f"Measured SWR {measured_swr:.2f} reached the {abort_swr:.2f} stop limit",
                )

            if not await self._force_carrier_off():
                raise StationActionError(
                    "carrier-off-unconfirmed",
                    "FLEX survey carrier could not be switched off",
                    status_code=503,
                )
            carrier_started = False
            target_swr = float(self._policy_value("STATION_TUNE_TARGET_SWR", 1.5))
            if self._transaction is not None:
                self._transaction.update(
                    swr_before=measured_swr,
                    swr_after=None,
                    target_swr=target_swr,
                    tune_power_w=tune_power,
                    memory_changed=False,
                )
            self._finish_transaction("succeeded")
            await self._record_event(
                "station.swr_survey_completed",
                {
                    "route": route.as_dict(),
                    "swr": measured_swr,
                    "target_swr": target_swr,
                    "transaction": dict(self._transaction or {}),
                },
            )
        except StationActionError as exc:
            if self._transaction is not None:
                self._transaction.update(swr_before=measured_swr, swr_after=None)
            state = "cancelled" if exc.code == "tune-cancelled" else "failed"
            self._finish_transaction(state, exc)
            await self._record_event(
                f"station.swr_survey_{state}",
                {"route": route.as_dict(), "transaction": dict(self._transaction or {})},
            )
        except asyncio.CancelledError:
            error = StationActionError("tune-cancelled", "SWR survey was cancelled")
            if self._transaction is not None:
                self._transaction.update(swr_before=measured_swr, swr_after=None)
            self._finish_transaction("cancelled", error)
            raise
        except Exception as exc:
            logger.exception("Unexpected station SWR survey failure")
            error = StationActionError("survey-failed", str(exc), status_code=500)
            if self._transaction is not None:
                self._transaction.update(swr_before=measured_swr, swr_after=None)
            self._finish_transaction("failed", error)
        finally:
            if carrier_started:
                await self._force_carrier_off()
            if flex and original_tune_power is not None:
                try:
                    await self._bounded_flex_io(
                        lambda: flex.set_tune_power(int(original_tune_power)),
                        timeout=3.0,
                        code="flex-tune-power-restore-timeout",
                        message="Restoring the prior FLEX tune power timed out",
                    )
                except Exception:
                    logger.error("Could not restore FLEX tune power after survey", exc_info=True)
            try:
                await self._request_fail_safe_standby()
            finally:
                if (
                    digital_service is not None
                    and getattr(digital_service, "tx_inhibit_reason", None)
                    == "station-coordinator-swr-survey"
                ):
                    digital_service.tx_inhibit_reason = prior_tx_inhibit
                if radio_lock_acquired and self.radio_lock.locked():
                    self.radio_lock.release()
                self._active_task = None
            await self._record_tune_result(
                route,
                swr_before=measured_swr,
                swr_after=None,
            )

    def claim_training(self, job_id: str) -> None:
        """Reserve station control for one server-owned ATU training job."""
        clean_id = str(job_id or "").strip()
        if not clean_id:
            raise StationActionError("training-job-invalid", "Training job id is required")
        if self._training_job_id and self._training_job_id != clean_id:
            raise StationActionError(
                "station-training-active",
                f"ATU training job {self._training_job_id} already owns station control",
                status_code=423,
            )
        if self.busy:
            raise StationActionError("station-busy", "A station transaction is already running")
        self._require_commissioned()
        self._require_operational()
        if self._stopped:
            raise StationActionError(
                "station-stopped",
                "Station control is stopping or stopped",
                status_code=503,
            )
        self._release_training_tx_monitor()
        self._training_original_kat_mode = None
        self._training_job_id = clean_id

    def abandon_training_claim(self, job_id: str) -> None:
        """Drop a preflight-only claim before a training task has started."""
        if self._training_job_id == job_id and not (
            self._active_task and not self._active_task.done()
        ):
            self._release_training_tx_monitor()
            self._training_original_kat_mode = None
            self._training_job_id = None

    def _training_point_route(self, point: dict[str, Any]) -> RouteTarget:
        try:
            frequency_mhz = float(point.get("frequency_mhz"))
        except (TypeError, ValueError) as exc:
            raise StationActionError(
                "training-frequency-invalid",
                "Training point has no valid MHz frequency",
                status_code=422,
            ) from exc
        route = self._route_for_frequency(frequency_mhz)
        if route is None:
            raise StationActionError(
                "training-route-unresolved",
                f"No exact route policy exists for {frequency_mhz:.6f} MHz",
                status_code=422,
            )
        expected = {
            "band": route.band,
            "route_id": route.route_id,
            "flex_tx_ant": route.flex_tx_ant,
            "kat_antenna": route.kat_antenna,
        }
        mismatches = [
            f"{field}={point.get(field)!r}, expected {value!r}"
            for field, value in expected.items()
            if point.get(field) != value
        ]
        if round(frequency_mhz * 1000) != point.get("frequency_khz"):
            mismatches.append(
                f"frequency_khz={point.get('frequency_khz')!r}, "
                f"expected {round(frequency_mhz * 1000)!r}"
            )
        if point.get("eligible") is not True or not route.amplifier_allowed:
            mismatches.append("point is not preview-eligible under station band policy")
        if mismatches:
            raise StationActionError(
                "training-route-policy-mismatch",
                "; ".join(mismatches),
                status_code=422,
            )
        return route

    def training_execution_blockers(
        self,
        points: list[dict[str, Any]],
        *,
        job_id: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """Return cached, non-mutating execution blockers for a preview."""
        blockers: list[dict[str, str]] = []

        def add(code: str, message: str) -> None:
            if not any(item["code"] == code for item in blockers):
                blockers.append({"code": code, "message": message})

        if not self.commissioned:
            add("commissioning-required", "The station coordinator is not commissioned")
        if self._recovery_required:
            add("startup-recovery-required", "Startup safe-state recovery is not confirmed")
        if self._maintenance:
            add("station-maintenance-active", "Station maintenance mode is active")
        if self._stopped:
            add("station-stopped", "Station control is stopping or stopped")
        radio = self._radio_snapshot()
        if (
            radio.get("connected") is not True
            or radio.get("known") is not True
            or radio.get("stale") is not False
        ):
            add("flex-state-unconfirmed", "A fresh, known FLEX connection is required")
        if radio.get("mox") is not False:
            add("flex-receive-required", "FLEX cached state must explicitly confirm receive")
        if self._training_job_id and self._training_job_id != job_id:
            add("station-training-active", f"Training job {self._training_job_id} is active")
        if (self._active_task and not self._active_task.done()) or (
            self._action_lock.locked() and self._training_job_id != job_id
        ):
            add("station-busy", "A station transaction is already running")
        try:
            self._assert_digital_idle()
        except StationActionError as exc:
            add(exc.code, exc.message)
        except Exception:
            add("digital-state-unconfirmed", "Digital engine idle state is not confirmed")
        kpa = self.elecraft.kpa500
        kat = self.elecraft.kat500
        if kpa is None or kat is None:
            add("station-device-missing", "KPA500 and KAT500 are both required")
        else:
            try:
                cached = self.elecraft.snapshot()
                cached_kpa = cached.get("kpa500") or {}
                cached_kat = cached.get("kat500") or {}
                if cached_kpa.get("connected") is not True:
                    add("kpa-disconnected", "KPA500 is not connected")
                if cached_kpa.get("operate") is not False:
                    add("kpa-standby-required", "KPA500 cached state is not standby")
                if cached_kat.get("connected") is not True:
                    add("kat-disconnected", "KAT500 is not connected")
                if cached_kat.get("tuning") is True:
                    add("kat-idle-required", "KAT500 cached state reports an active tune")
            except Exception:
                add("elecraft-state-unconfirmed", "Cached Elecraft state is unavailable")
            if not hasattr(kat, "start_tune") or not hasattr(kat, "store_memory"):
                add(
                    "training-tune-capability-missing",
                    "KAT500 non-storing tune and explicit memory store are required",
                )
        if not points:
            add("training-points-empty", "At least one preview-valid point is required")
        if len(points) > 100:
            add("training-points-limit", "Training is limited to 100 points")
        for point in points[:100]:
            try:
                self._training_point_route(point)
            except StationActionError as exc:
                add(exc.code, exc.message)
        return blockers

    async def fresh_training_execution_blockers(
        self,
        points: list[dict[str, Any]],
        *,
        job_id: str,
    ) -> list[dict[str, str]]:
        """Add fresh FLEX/KPA/KAT readback blockers without changing hardware."""
        blockers = self.training_execution_blockers(points, job_id=job_id)
        if blockers:
            return blockers
        try:
            await self._claim_training_tx_monitor(job_id)
            async with self._action_lock:
                async with self.radio_lock:
                    self._assert_digital_idle()
                    await self._fresh_receive_state()
                    kpa = self.elecraft.kpa500
                    kat = self.elecraft.kat500
                    if kpa is None or kat is None:
                        raise StationActionError(
                            "station-device-missing",
                            "KPA500 and KAT500 are both required",
                        )
                    kpa_status, kat_status = await asyncio.gather(
                        self._device_readback(kpa),
                        self._device_readback(kat),
                    )
                    kpa_check = verify_exact_target(
                        kpa_status,
                        {"power": True, "operate": False, "fault": "00"},
                    )
                    if not kpa_check["verified"]:
                        raise StationActionError(
                            "kpa-standby-required",
                            "Fresh KPA500 readback must confirm powered, fault-free standby",
                        )
                    if kat_status.get("tuning") is not False or kat_status.get("fault") != "0":
                        raise StationActionError(
                            "kat-idle-required",
                            "Fresh KAT500 readback must confirm idle and fault-free",
                        )
                    if kat_status.get("mode") not in {"auto", "manual"}:
                        raise StationActionError(
                            "kat-mode-invalid",
                            "KAT500 must be in AUTO or MANUAL mode",
                        )
        except StationActionError as exc:
            blockers.append({"code": exc.code, "message": exc.message})
        except Exception as exc:
            blockers.append(
                {
                    "code": "training-preflight-failed",
                    "message": f"Fresh station preflight failed: {exc}",
                }
            )
        return blockers

    async def clear_training_memories(
        self,
        job_id: str,
        scopes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Clear only explicit band+routed-antenna frequency memories."""
        if self._training_job_id != job_id:
            raise StationActionError("training-job-not-owner", "Training job does not own station")
        cleared: list[dict[str, Any]] = []
        async with self._action_lock:
            self._require_commissioned()
            self._require_operational()
            self._assert_digital_idle()
            async with self.radio_lock:
                await self._fresh_receive_state()
                if not await self._request_fail_safe_standby():
                    raise StationActionError(
                        "kpa-standby-not-confirmed",
                        "KPA500 standby is required before selective memory erase",
                        status_code=503,
                    )
                kat = self.elecraft.kat500
                if kat is None or not hasattr(kat, "clear_frequency_memories"):
                    raise StationActionError(
                        "selective-memory-clear-unavailable",
                        "KAT500 selective memory clear is unavailable",
                        status_code=503,
                    )
                for scope in scopes:
                    band = str(scope.get("band") or "").strip().lower()
                    antenna = scope.get("kat_antenna")
                    route = self._route_for_frequency(scope.get("frequency_mhz"))
                    if (
                        route is None
                        or route.band != band
                        or antenna not in {1, 2, 3}
                        or route.kat_antenna != antenna
                    ):
                        raise StationActionError(
                            "training-erase-scope-invalid",
                            "Erase scope must match the exact routed band and ANT1/ANT2/ANT3",
                            status_code=422,
                        )
                    await self._device_call(kat, "clear_frequency_memories", band, antenna)
                    cleared.append({"band": band, "kat_antenna": antenna})
        return cleared

    async def execute_training_point(
        self,
        job_id: str,
        point: dict[str, Any],
    ) -> dict[str, Any]:
        """QSY, prepare, tune, and explicitly store one preview-validated point."""
        if self._training_job_id != job_id:
            raise StationActionError("training-job-not-owner", "Training job does not own station")
        route = self._training_point_route(point)
        async with self._action_lock:
            self._require_commissioned()
            self._require_operational()
            self._assert_digital_idle()
            if self._active_task and not self._active_task.done():
                raise StationActionError("station-busy", "A station transaction is already running")
            async with self.radio_lock:
                await self._fresh_receive_state()
                if not await self._request_fail_safe_standby():
                    raise StationActionError(
                        "kpa-standby-not-confirmed",
                        "KPA500 standby is required before training QSY",
                        status_code=503,
                    )
                flex = self.flex_provider()
                if flex is None or not hasattr(flex, "tune_mhz"):
                    raise StationActionError(
                        "flex-qsy-unavailable",
                        "FLEX frequency control is unavailable",
                        status_code=503,
                    )
                self._route_verified = None
                qsy_ok = await self._bounded_flex_io(
                    lambda: flex.tune_mhz(route.frequency_mhz),
                    timeout=3.0,
                    code="flex-route-command-timeout",
                    message=f"FLEX training QSY to {route.frequency_mhz:.6f} MHz timed out",
                )
                if qsy_ok is not True:
                    raise StationActionError(
                        "flex-route-command-rejected",
                        f"FLEX rejected training QSY to {route.frequency_mhz:.6f} MHz",
                        status_code=503,
                    )
                await self._fresh_flex_route(route)

            self._cancel_event = asyncio.Event()
            self._start_transaction("tune", route)
            if self._transaction is not None:
                self._transaction.update(training_job_id=job_id, operation="train")
            self._active_task = asyncio.current_task()
            await self._run_tune(route)
            result = dict(self._transaction or {})

        carrier_off = await self._force_carrier_off()
        standby = await self._request_fail_safe_standby()
        if not carrier_off or not standby:
            self._recovery_required = True
            error = StationActionError(
                "training-safe-state-unconfirmed",
                "FLEX carrier-off and KPA500 standby could not both be confirmed",
                status_code=503,
            )
            self._finish_transaction("failed", error)
            result = dict(self._transaction or {})
        return result

    async def execute_swr_survey_point(
        self,
        job_id: str,
        point: dict[str, Any],
    ) -> dict[str, Any]:
        """Measure one preview-validated point without tuning or storing memory."""
        if self._training_job_id != job_id:
            raise StationActionError("training-job-not-owner", "Training job does not own station")
        route = self._training_point_route(point)
        async with self._action_lock:
            self._require_commissioned()
            self._require_operational()
            self._assert_digital_idle()
            if self._active_task and not self._active_task.done():
                raise StationActionError("station-busy", "A station transaction is already running")
            async with self.radio_lock:
                await self._fresh_receive_state()
                if not await self._request_fail_safe_standby():
                    raise StationActionError(
                        "kpa-standby-not-confirmed",
                        "KPA500 standby is required before an SWR survey QSY",
                        status_code=503,
                    )
                flex = self.flex_provider()
                if flex is None or not hasattr(flex, "tune_mhz"):
                    raise StationActionError(
                        "flex-qsy-unavailable",
                        "FLEX frequency control is unavailable",
                        status_code=503,
                    )
                self._route_verified = None
                qsy_ok = await self._bounded_flex_io(
                    lambda: flex.tune_mhz(route.frequency_mhz),
                    timeout=3.0,
                    code="flex-route-command-timeout",
                    message=f"FLEX survey QSY to {route.frequency_mhz:.6f} MHz timed out",
                )
                if qsy_ok is not True:
                    raise StationActionError(
                        "flex-route-command-rejected",
                        f"FLEX rejected survey QSY to {route.frequency_mhz:.6f} MHz",
                        status_code=503,
                    )
                await self._fresh_flex_route(route)

            self._cancel_event = asyncio.Event()
            self._start_transaction("swr-survey", route)
            if self._transaction is not None:
                self._transaction.update(training_job_id=job_id, operation="survey")
            self._active_task = asyncio.current_task()
            await self._run_swr_survey(route)
            result = dict(self._transaction or {})

        carrier_off = await self._force_carrier_off()
        standby = await self._request_fail_safe_standby()
        if not carrier_off or not standby:
            self._recovery_required = True
            error = StationActionError(
                "survey-safe-state-unconfirmed",
                "FLEX carrier-off and KPA500 standby could not both be confirmed",
                status_code=503,
            )
            self._finish_transaction("failed", error)
            result = dict(self._transaction or {})
        return result

    async def cancel_training(self, job_id: str) -> None:
        if self._training_job_id != job_id:
            raise StationActionError("training-job-not-owner", "Training job does not own station")
        self._cancel_event.set()
        kat = self.elecraft.kat500
        carrier_off = await self._force_carrier_off()
        active_kind = str((self._transaction or {}).get("kind") or "")
        if active_kind != "swr-survey" and kat is not None and hasattr(kat, "cancel_tune"):
            try:
                await self._device_call(kat, "cancel_tune")
            except StationActionError:
                logger.warning("Immediate KAT500 training cancel was not confirmed")
        standby = await self._request_fail_safe_standby()
        if not carrier_off or not standby:
            self._recovery_required = True
            raise StationActionError(
                "training-cancel-safe-state-unconfirmed",
                "Training cancel could not confirm FLEX carrier-off and KPA500 standby",
                status_code=503,
            )

    async def release_training(self, job_id: str) -> None:
        """Release training ownership only after re-establishing fail-safe state."""
        if self._training_job_id != job_id:
            return
        carrier_off = False
        standby = False
        kat_mode_restored = False
        try:
            try:
                carrier_off = await self._force_carrier_off()
            except Exception:
                logger.error("Could not confirm FLEX carrier-off while releasing training", exc_info=True)
            try:
                standby = await self._request_fail_safe_standby()
            except Exception:
                logger.error("Could not confirm KPA500 standby while releasing training", exc_info=True)
            kat_mode_restored = await self._restore_training_kat_mode()
        finally:
            self._route_verified = None
            self._release_training_tx_monitor()
            self._training_job_id = None
        if not carrier_off or not standby or not kat_mode_restored:
            self._recovery_required = True
            raise StationActionError(
                "training-release-safe-state-unconfirmed",
                "Training ended without confirmed FLEX carrier-off, KPA500 standby, or KAT mode restore",
                status_code=503,
            )

    async def _force_carrier_off(self) -> bool:
        flex = self.flex_provider()
        if flex is None:
            return False
        for attempt in range(2):
            try:
                tune_off = await run_radio_io(
                    lambda: flex.set_tune(False),
                    timeout=2.0,
                )
                mox_off = await run_radio_io(
                    lambda: flex.set_mox(False),
                    timeout=2.0,
                )
                if not tune_off or not mox_off:
                    logger.error("FLEX rejected the TUNE-off or MOX-off command")
                    continue
                await self._fresh_receive_state()
                return True
            except Exception:
                logger.error(
                    "Could not independently confirm FLEX tune carrier off (attempt %s)",
                    attempt + 1,
                    exc_info=True,
                )
        return False

    async def _request_fail_safe_standby(self) -> bool:
        kpa = self.elecraft.kpa500
        if kpa is None:
            return True
        for attempt in range(2):
            try:
                await self._device_call(kpa, "set_operate", False)
                readback = await self._device_readback(kpa)
                if readback.get("operate") is False:
                    return True
                logger.error("KPA500 did not confirm fail-safe standby")
            except Exception:
                logger.error(
                    "Could not request KPA500 fail-safe standby (attempt %s)",
                    attempt + 1,
                    exc_info=True,
                )
        return False

    async def cancel(self) -> dict[str, Any]:
        task = self._active_task
        if not task or task.done() or (self._transaction or {}).get("kind") != "tune":
            raise StationActionError("no-active-tune", "There is no active tune to cancel")
        self._cancel_event.set()
        self._transaction_step("cancelling", int((self._transaction or {}).get("progress", 0)))
        carrier_off_confirmed = await self._force_carrier_off()
        kat = self.elecraft.kat500
        if kat is not None and hasattr(kat, "cancel_tune"):
            try:
                await self._device_call(kat, "cancel_tune")
            except StationActionError:
                logger.warning("Immediate KAT500 cancel failed; tune task will still time out safely")
        if not carrier_off_confirmed:
            raise StationActionError(
                "carrier-off-unconfirmed",
                "Tune cancellation was requested, but FLEX receive state could not be confirmed",
                status_code=503,
            )
        return self.snapshot()
