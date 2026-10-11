"""Elecraft KPA500 and KAT500 serial control.

The two products use related but different ASCII command sets.  This module
keeps each serial stream serialized, exposes parsed status, and follows the
authoritative FlexRadio frequency without conflating radio modulation mode
with the KAT500's AUTO/MANUAL/BYPASS tuner mode.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from typing import Any, Callable, Optional

from radio_control import config


logger = logging.getLogger(__name__)

ELECRAFT_STATUS_STALE_AFTER_SECONDS = 15.0
RADIO_STATUS_STALE_AFTER_SECONDS = 8.0
ELECRAFT_METER_POLL_SECONDS = 0.35
ELECRAFT_METER_RX_TAIL_SECONDS = 1.0

BAND_CODES = {
    "160m": "00",
    "80m": "01",
    "60m": "02",
    "40m": "03",
    "30m": "04",
    "20m": "05",
    "17m": "06",
    "15m": "07",
    "12m": "08",
    "10m": "09",
    "6m": "10",
}

_MISSING = object()


def verify_exact_target(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    fields: Optional[tuple[str, ...] | list[str] | set[str]] = None,
) -> dict[str, Any]:
    """Compare safety-relevant readback without coercion or tolerances.

    Only explicitly expected fields are checked by default. This keeps extra
    telemetry from making a route transaction fail while ensuring that a
    missing value, a different type, or a different value never verifies.
    """
    checked_fields = tuple(fields) if fields is not None else tuple(expected)
    mismatches: list[dict[str, Any]] = []
    for field_name in checked_fields:
        expected_value = expected.get(field_name, _MISSING)
        actual_value = actual.get(field_name, _MISSING)
        missing_from = []
        if expected_value is _MISSING:
            missing_from.append("expected")
        if actual_value is _MISSING:
            missing_from.append("actual")
        if (
            missing_from
            or type(actual_value) is not type(expected_value)
            or actual_value != expected_value
        ):
            mismatches.append(
                {
                    "field": field_name,
                    "expected": None if expected_value is _MISSING else expected_value,
                    "actual": None if actual_value is _MISSING else actual_value,
                    "missing_from": missing_from,
                }
            )
    return {
        "verified": not mismatches,
        "fields": list(checked_fields),
        "mismatches": mismatches,
    }


def exact_target_matches(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    fields: Optional[tuple[str, ...] | list[str] | set[str]] = None,
) -> bool:
    """Return the boolean form of :func:`verify_exact_target`."""
    return bool(verify_exact_target(actual, expected, fields=fields)["verified"])


def _parse_tenths(value: str) -> float:
    """Parse Elecraft values that are either decimal or integer tenths."""
    return float(value) if "." in value else int(value) / 10


DEFAULT_KAT500_ANTENNAS = {
    "160m": 2,
    "80m": 2,
    "60m": 2,
    "40m": 2,
    "30m": 2,
    "20m": 1,
    "17m": 1,
    "15m": 1,
    "12m": 1,
    "10m": 1,
    "6m": 1,
}


def band_from_frequency(mhz: float | int | None) -> Optional[str]:
    """Return the amateur band containing *mhz*, or ``None``."""
    if mhz is None:
        return None
    value = float(mhz)
    from radio_control.flex_radio import FlexCtl

    return next(
        (
            band
            for band, (low, high) in FlexCtl.BAND_RANGES.items()
            if low <= value <= high
        ),
        None,
    )


def _timestamp_seconds(value: Any) -> Optional[float]:
    """Return an epoch timestamp from an epoch or ISO-8601 value."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _freshness(
    observed_at: Any,
    *,
    now: float,
    stale_after_seconds: float,
    explicitly_stale: bool = False,
) -> dict[str, Any]:
    observed_seconds = _timestamp_seconds(observed_at)
    age_seconds = None if observed_seconds is None else max(0.0, now - observed_seconds)
    stale = bool(
        explicitly_stale
        or age_seconds is None
        or age_seconds > stale_after_seconds
    )
    return {
        "observed_at": observed_at,
        "age_seconds": None if age_seconds is None else round(age_seconds, 3),
        "stale": stale,
    }


def build_station_path(
    elecraft_status: dict[str, Any],
    radio_status: Optional[dict[str, Any]] = None,
    *,
    antenna_policy: Optional[dict[str, int]] = None,
    antenna_names: Optional[dict[int | str, str]] = None,
    flex_antenna_policy: Optional[dict[str, Any]] = None,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Build a read-only, evidence-based view of the complete RF path.

    This contract reports alignment but never authorizes transmission. A later
    safety coordinator can require stricter, freshly queried evidence for
    state-changing transactions without teaching the UI to infer readiness.
    """
    current_time = time.time() if now is None else float(now)
    radio = dict(radio_status or {})
    kpa = dict(elecraft_status.get("kpa500") or {})
    kat = dict(elecraft_status.get("kat500") or {})
    policy = dict(antenna_policy or DEFAULT_KAT500_ANTENNAS)
    flex_policy = dict(flex_antenna_policy or {})
    names = {str(key): str(value) for key, value in (antenna_names or {}).items() if value}

    radio_frequency = radio.get("frequency", elecraft_status.get("radio_frequency"))
    # A fresh radio frequency is stronger evidence than the Elecraft manager's
    # cached last-band value.  Prefer it so a recent QSY cannot be presented as
    # an aligned old-band path while the accessory snapshot catches up.
    radio_band = band_from_frequency(radio_frequency) or elecraft_status.get("radio_band")
    radio_mode = radio.get("mode", elecraft_status.get("radio_mode"))
    radio_freshness = _freshness(
        radio.get("observed_at"),
        now=current_time,
        stale_after_seconds=RADIO_STATUS_STALE_AFTER_SECONDS,
        explicitly_stale=bool(radio.get("stale")),
    )
    radio_connected = bool(radio.get("connected"))
    radio_known = bool(radio.get("known", radio_connected and radio_frequency is not None))
    radio_confirmed = bool(
        radio_connected and radio_known and radio_band and not radio_freshness["stale"]
    )
    radio_state = (
        "disconnected"
        if not radio_connected
        else "unknown"
        if not radio_known or not radio_band
        else "stale"
        if radio_freshness["stale"]
        else "transmitting"
        if radio.get("mox") is True
        or str(radio.get("interlock_state") or "").strip().upper() == "TRANSMITTING"
        else "ready"
    )
    flex_port_value = radio.get("tx_ant")
    flex_port = str(flex_port_value) if flex_port_value else "TX port unknown"
    flex_band_policy = (flex_policy.get("bands") or {}).get(radio_band)
    if isinstance(flex_band_policy, dict):
        expected_flex_port = (
            flex_band_policy.get("tx")
            or flex_band_policy.get("txAnt")
            or flex_band_policy.get("antenna")
        )
    else:
        expected_flex_port = flex_band_policy
    expected_flex_port = str(expected_flex_port or "").strip().upper() or None

    status_observed_at = elecraft_status.get("updated_at")

    def accessory_freshness(device_status: dict[str, Any]) -> dict[str, Any]:
        return _freshness(
            device_status.get("observed_at", status_observed_at),
            now=current_time,
            stale_after_seconds=ELECRAFT_STATUS_STALE_AFTER_SECONDS,
            explicitly_stale=bool(device_status.get("stale")),
        )

    expected_antenna = policy.get(str(radio_band)) if radio_band else None
    expected_antenna = int(expected_antenna) if expected_antenna in {1, 2, 3} else None
    selected_antenna = kat.get("antenna")
    selected_antenna = int(selected_antenna) if selected_antenna in {1, 2, 3} else None
    antenna_number = selected_antenna
    antenna_name = names.get(str(antenna_number)) if antenna_number else None
    antenna_label = antenna_name or (
        f"KAT ANT{antenna_number}" if antenna_number else "KAT antenna unknown"
    )

    mismatches: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    unknown_reasons: list[str] = []

    interlock_state = str(radio.get("interlock_state") or "").strip().upper()
    if radio.get("mox") is True or interlock_state == "TRANSMITTING":
        unknown_reasons.append("FLEX transmitter is active; route changes are inhibited")
    if expected_flex_port and not flex_port_value:
        unknown_reasons.append("FLEX TX antenna readback is unavailable")
    elif expected_flex_port and str(flex_port_value).upper() != expected_flex_port:
        mismatches.append(
            {
                "code": "flex-tx-port-mismatch",
                "message": (
                    f"FLEX reports {flex_port_value}; policy expects {expected_flex_port} "
                    f"on {radio_band}"
                ),
            }
        )

    kpa_enabled = bool(kpa.get("enabled"))
    kpa_connected = bool(kpa.get("connected"))
    kpa_freshness = accessory_freshness(kpa)
    kpa_responsive = bool(kpa.get("responsive", kpa.get("observed_at") is not None))
    kpa_fault = str(kpa.get("fault") or "").strip()
    kpa_faulted = bool(kpa_fault and kpa_fault not in {"0", "00"})
    kpa_required = ["power"] if kpa.get("power") is not True else ["power", "operate", "band", "fault"]
    kpa_missing = sorted(
        {
            field_name
            for field_name in kpa_required
            if field_name not in kpa or kpa.get(field_name) is None
        }
        | (set(kpa.get("missing_fields") or []) & set(kpa_required))
    )
    if not kpa_enabled:
        kpa_state = "disabled"
        kpa_confirmed = False
        unknown_reasons.append("KPA500 monitoring is disabled")
    elif not kpa_connected:
        kpa_state = "disconnected"
        kpa_confirmed = False
        unknown_reasons.append("KPA500 is disconnected")
    elif not kpa_responsive:
        kpa_state = "unknown"
        kpa_confirmed = False
        unknown_reasons.append("KPA500 has not returned a confirmed status response")
    elif kpa_freshness["stale"]:
        kpa_state = "stale"
        kpa_confirmed = False
        unknown_reasons.append("KPA500 status is stale")
    elif kpa_missing:
        kpa_state = "unknown"
        kpa_confirmed = False
        unknown_reasons.append(f"KPA500 is missing: {', '.join(kpa_missing)}")
    elif kpa_faulted:
        kpa_state = "fault"
        kpa_confirmed = False
        mismatches.append({"code": "kpa-fault", "message": f"KPA500 fault {kpa_fault}"})
    elif radio_band and kpa.get("band") and kpa.get("band") != radio_band:
        kpa_state = "mismatch"
        kpa_confirmed = False
        mismatches.append(
            {
                "code": "kpa-band-mismatch",
                "message": f"KPA500 reports {kpa.get('band')} while FLEX is on {radio_band}",
            }
        )
    elif kpa.get("power") is False:
        kpa_state = "off"
        kpa_confirmed = True
    elif kpa.get("operate") is True:
        kpa_state = "operate"
        kpa_confirmed = True
    else:
        kpa_state = "standby"
        kpa_confirmed = True

    kat_enabled = bool(kat.get("enabled"))
    kat_connected = bool(kat.get("connected"))
    kat_freshness = accessory_freshness(kat)
    kat_responsive = bool(kat.get("responsive", kat.get("observed_at") is not None))
    kat_required = ["power"] if kat.get("power") is not True else [
        "power", "mode", "antenna", "band", "frequency_khz", "tuning", "fault"
    ]
    kat_missing = sorted(
        {
            field_name
            for field_name in kat_required
            if field_name not in kat or kat.get(field_name) is None
        }
        | (set(kat.get("missing_fields") or []) & set(kat_required))
    )
    if not kat_enabled:
        kat_state = "disabled"
        kat_confirmed = False
        unknown_reasons.append("KAT500 monitoring is disabled")
    elif not kat_connected:
        kat_state = "disconnected"
        kat_confirmed = False
        unknown_reasons.append("KAT500 is disconnected")
    elif not kat_responsive:
        kat_state = "unknown"
        kat_confirmed = False
        unknown_reasons.append("KAT500 has not returned a confirmed status response")
    elif kat_freshness["stale"]:
        kat_state = "stale"
        kat_confirmed = False
        unknown_reasons.append("KAT500 status is stale")
    elif kat_missing:
        kat_state = "unknown"
        kat_confirmed = False
        unknown_reasons.append(f"KAT500 is missing: {', '.join(kat_missing)}")
    elif str(kat.get("fault") or "0") not in {"0", "00"}:
        kat_state = "fault"
        kat_confirmed = False
        mismatches.append(
            {
                "code": "kat-fault",
                "message": f"KAT500 fault {kat.get('fault')}",
            }
        )
    elif str(kat.get("mode") or "").lower() == "bypass":
        kat_state = "bypass"
        kat_confirmed = False
        mismatches.append(
            {
                "code": "kat-bypass",
                "message": "KAT500 matching network is bypassed",
            }
        )
    elif radio_band and kat.get("band") and kat.get("band") != radio_band:
        kat_state = "mismatch"
        kat_confirmed = False
        mismatches.append(
            {
                "code": "kat-band-mismatch",
                "message": f"KAT500 reports {kat.get('band')} while FLEX is on {radio_band}",
            }
        )
    elif expected_antenna and selected_antenna and selected_antenna != expected_antenna:
        kat_state = "mismatch"
        kat_confirmed = False
        mismatches.append(
            {
                "code": "kat-antenna-mismatch",
                "message": (
                    f"KAT500 reports ANT{selected_antenna}; policy expects "
                    f"ANT{expected_antenna} on {radio_band}"
                ),
            }
        )
    elif kat.get("power") is False:
        kat_state = "off"
        kat_confirmed = True
    elif kat.get("tuning") is True:
        kat_state = "tuning"
        kat_confirmed = False
        unknown_reasons.append("KAT500 is tuning")
    else:
        kat_state = str(kat.get("mode") or "ready")
        kat_confirmed = True

    # KAT500 ``F;`` reports the tuner setting's selected/last-RF frequency,
    # not an independent live dial-frequency measurement.  A difference
    # inside the same amateur band is therefore useful route-preparation
    # evidence, but it must not make a passive receive-only path look failed.
    # State-changing coordinator transactions still require exact post-write
    # readback before any tune or transmit action is allowed.
    try:
        radio_frequency_khz = (
            round(float(radio_frequency) * 1000) if radio_frequency is not None else None
        )
        kat_frequency_khz = (
            int(kat["frequency_khz"]) if kat.get("frequency_khz") is not None else None
        )
    except (TypeError, ValueError):
        radio_frequency_khz = None
        kat_frequency_khz = None
    if (
        kat_confirmed
        and radio_band
        and kat.get("band") == radio_band
        and radio_frequency_khz is not None
        and kat_frequency_khz is not None
        and kat_frequency_khz != radio_frequency_khz
    ):
        advisories.append(
            {
                "code": "kat-frequency-selection-different",
                "message": (
                    f"KAT500 memory selection reports {kat_frequency_khz} kHz while FLEX is "
                    f"at {radio_frequency_khz} kHz; route preparation must update and verify "
                    "it before transmit"
                ),
            }
        )

    if not radio_confirmed:
        unknown_reasons.insert(0, "FLEX state is not fresh and confirmed")

    if mismatches:
        alignment = "mismatch"
    elif unknown_reasons:
        alignment = "unknown"
    else:
        alignment = "confirmed"

    if mismatches or kpa_faulted:
        overall_state = "fault"
    elif alignment == "unknown":
        overall_state = "unknown"
    elif kpa_enabled and kpa_state in {"standby", "off"}:
        overall_state = "standby"
    elif kat_enabled and kat_state == "off":
        overall_state = "standby"
    elif radio.get("mox") is True:
        overall_state = "transmitting"
    else:
        overall_state = "ready"

    frequency_label = (
        f"{float(radio_frequency):.6f} MHz" if radio_frequency is not None else "Frequency unknown"
    )
    route_label = (
        f"FLEX {flex_port} → KPA500 → KAT500 → {antenna_label}"
        if kpa_enabled and kat_enabled
        else f"FLEX {flex_port} → KAT500 → {antenna_label}"
        if kat_enabled
        else f"FLEX {flex_port} → KPA500"
        if kpa_enabled
        else f"FLEX {flex_port}"
    )

    return {
        "schema_version": 1,
        "generated_at": datetime.fromtimestamp(current_time, tz=timezone.utc).isoformat(),
        "state": overall_state,
        "alignment": alignment,
        "transmit_authorized": False,
        "authorization_note": "Read-only path evidence; not a transmit authorization",
        "frequency": radio_frequency,
        "frequency_label": frequency_label,
        "band": radio_band,
        "mode": radio_mode,
        "rf_power_w": radio.get("drive"),
        "tx_ant": flex_port_value,
        "interlock_state": interlock_state or None,
        "mox": radio.get("mox"),
        "route_label": route_label,
        "antenna": {
            "number": antenna_number,
            "name": antenna_name,
            "label": antenna_label,
            "expected": expected_antenna,
            "observed": selected_antenna,
        },
        "stages": [
            {
                "id": "flex",
                "label": "FLEX-8400",
                "state": radio_state,
                "confirmed": radio_confirmed,
                "detail": f"{frequency_label} · {radio_band or 'band unknown'} · {radio_mode or 'mode unknown'} · {flex_port}",
                **radio_freshness,
            },
            {
                "id": "kpa500",
                "label": "KPA500",
                "state": kpa_state,
                "confirmed": kpa_confirmed,
                "detail": f"{kpa.get('band') or 'band unknown'} · {kpa_state}",
                "quality": kpa.get("quality", "unknown"),
                "missing_fields": kpa_missing,
                **kpa_freshness,
            },
            {
                "id": "kat500",
                "label": "KAT500",
                "state": kat_state,
                "confirmed": kat_confirmed,
                "detail": f"{kat.get('band') or 'band unknown'} · {kat.get('mode') or 'mode unknown'} · {antenna_label}",
                "quality": kat.get("quality", "unknown"),
                "missing_fields": kat_missing,
                **kat_freshness,
            },
            {
                "id": "antenna",
                "label": antenna_label,
                "state": "selected" if antenna_number else "unknown",
                "confirmed": bool(kat_confirmed and antenna_number),
                "detail": f"KAT500 output {antenna_number}" if antenna_number else "No output confirmed",
                "observed_at": kat_freshness["observed_at"],
                "age_seconds": kat_freshness["age_seconds"],
                "stale": kat_freshness["stale"],
            },
        ],
        "mismatches": mismatches,
        "advisories": advisories,
        "unknown_reasons": unknown_reasons,
    }


def _serial_factory(**kwargs):
    try:
        import serial
    except ImportError as exc:  # pragma: no cover - installation failure path
        raise RuntimeError("pyserial is not installed") from exc
    return serial.Serial(**kwargs)


class SerialCommandDevice:
    """Small semicolon-framed ASCII serial transport with response matching."""

    def __init__(
        self,
        name: str,
        port: str,
        baudrate: int,
        *,
        serial_factory: Callable[..., Any] = _serial_factory,
        timeout: float = 0.35,
    ) -> None:
        self.name = name
        self.port = str(port or "")
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)
        self.serial_factory = serial_factory
        self.serial: Any = None
        self.lock = threading.RLock()
        self.last_error: Optional[str] = None
        self.last_seen: Optional[float] = None
        self.io_enabled = True
        self.retired = False

    @property
    def connected(self) -> bool:
        return bool(self.serial is not None and getattr(self.serial, "is_open", True))

    def open(self) -> bool:
        with self.lock:
            if self.retired or not self.io_enabled:
                self.last_error = f"{self.name} connection is disabled"
                return False
            if self.connected:
                return True
            if not self.port:
                self.last_error = f"{self.name} serial port is not configured"
                return False
            try:
                self.serial = self.serial_factory(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=8,
                    parity="N",
                    stopbits=1,
                    timeout=0.05,
                    write_timeout=self.timeout,
                    xonxoff=False,
                    rtscts=False,
                    dsrdtr=False,
                )
                self.last_error = None
                return True
            except Exception as exc:
                self.serial = None
                self.last_error = self._friendly_error(exc)
                logger.warning("%s connection failed on %s: %s", self.name, self.port, exc)
                return False

    def close(self) -> None:
        with self.lock:
            serial_port, self.serial = self.serial, None
            if serial_port is not None:
                try:
                    serial_port.close()
                except Exception:
                    logger.debug("Could not close %s serial port", self.name, exc_info=True)

    def resume(self) -> None:
        with self.lock:
            if not self.retired:
                self.io_enabled = True

    def suspend(self) -> None:
        with self.lock:
            self.io_enabled = False
            self.close()

    def retire(self) -> None:
        with self.lock:
            self.retired = True
            self.io_enabled = False
            self.close()

    def write(self, command: str | bytes) -> bool:
        with self.lock:
            if not self.open():
                return False
            try:
                payload = command if isinstance(command, bytes) else command.encode("ascii")
                self.serial.write(payload)
                self.serial.flush()
                self.last_error = None
                return True
            except Exception as exc:
                self.last_error = self._friendly_error(exc)
                self.close()
                return False

    def query(
        self,
        command: str,
        prefix: str,
        *,
        timeout: Optional[float] = None,
        response_pattern: Optional[str] = None,
        update_last_seen: bool = True,
    ) -> Optional[str]:
        """Send a GET and return the first matching semicolon-framed response."""
        with self.lock:
            if not self.open():
                return None
            try:
                # VSPE mirrors traffic from the other client. Discard old
                # complete frames so a stale Remote-app reply cannot be
                # mistaken for the answer to this GET.
                waiting = int(getattr(self.serial, "in_waiting", 0) or 0)
                if waiting:
                    self.serial.read(waiting)
                self.serial.write(command.encode("ascii"))
                self.serial.flush()
                deadline = time.monotonic() + (timeout or self.timeout)
                pending = ""
                wanted = prefix.upper()
                while time.monotonic() < deadline:
                    waiting = int(getattr(self.serial, "in_waiting", 0) or 0)
                    chunk = self.serial.read(max(1, waiting))
                    if not chunk:
                        continue
                    pending += chunk.decode("ascii", errors="ignore")
                    while ";" in pending:
                        token, pending = pending.split(";", 1)
                        response = token.strip() + ";"
                        prefix_matches = token.strip().upper().startswith(wanted)
                        shape_matches = response_pattern is None or re.fullmatch(
                            response_pattern,
                            response,
                            re.IGNORECASE,
                        )
                        if prefix_matches and shape_matches:
                            if update_last_seen:
                                self.last_seen = time.time()
                            self.last_error = None
                            return response
                self.last_error = f"No {prefix} response from {self.name}"
                return None
            except Exception as exc:
                self.last_error = self._friendly_error(exc)
                self.close()
                return None

    def _friendly_error(self, exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        lowered = text.lower()
        if "access is denied" in lowered or "permission" in lowered:
            return f"{self.port} is busy or access was denied (check VSPE/Elecraft Remote)"
        if "cannot find" in lowered or "no such file" in lowered:
            return f"{self.port} was not found"
        return text


class KPA500(SerialCommandDevice):
    def identify(self) -> bool:
        # Powered-on firmware has no identify command; firmware revision is a
        # safe discriminator.  An off unit still has a bootloader on the port.
        return bool(self.query("^RVM;", "^RVM", timeout=0.8))

    def set_band(self, band: str) -> bool:
        code = BAND_CODES.get(band)
        return bool(code and self.write(f"^BN{code};"))

    def set_operate(self, operate: bool) -> bool:
        return self.write(f"^OS{1 if operate else 0};")

    def set_power(self, on: bool) -> bool:
        if on:
            # KPA500 bootloader power-on is the single uppercase character P.
            return self.write(b"P")
        return self.write("^ON0;")

    def read_power(self) -> Optional[bool]:
        """Read logical power state from the documented ``^ON`` query."""
        response = self.query("^ON;", "^ON", response_pattern=r"\^ON[01];")
        return None if response is None else response.upper().startswith("^ON1")

    def read_operate(self) -> Optional[bool]:
        """Read OPERATE/STANDBY state from the documented ``^OS`` query."""
        response = self.query("^OS;", "^OS", response_pattern=r"\^OS[01];")
        return None if response is None else response.upper().startswith("^OS1")

    def read_band(self) -> Optional[str]:
        """Read the KPA500 band, returning a known amateur-band label."""
        response = self.query("^BN;", "^BN", response_pattern=r"\^BN\d{2};")
        if response is None:
            return None
        code = response[3:5]
        return next((name for name, value in BAND_CODES.items() if value == code), code)

    def read_fault(self) -> Optional[str]:
        """Read the current KPA500 fault code without clearing it."""
        response = self.query("^FL;", "^FL", response_pattern=r"\^FL[^;]+;")
        return None if response is None else response[3:-1]

    def meter_status(self) -> dict[str, Any]:
        """Read only the fast KPA power/SWR meter without refreshing state age."""
        with self.lock:
            response = self.query(
                "^WS;",
                "^WS",
                response_pattern=r"\^WS\s*\d+\s+[\d.]+;",
                update_last_seen=False,
            )
            observed_at = time.time() if response else None
            result: dict[str, Any] = {
                "meter_observed_at": observed_at,
                "meter_complete": False,
                "meter_error": None if response else self.last_error,
            }
            match = re.search(r"\^WS\s*(\d+)\s+([\d.]+)", response or "", re.I)
            if match:
                output_power = int(match.group(1))
                raw_swr = match.group(2)
                result.update(
                    output_power_w=output_power,
                    swr=0.0 if raw_swr == "000" else _parse_tenths(raw_swr),
                    swr_live=output_power > 0 and raw_swr != "000",
                    meter_complete=True,
                )
            return result

    def readback(self) -> dict[str, Any]:
        """Return a fresh, focused readback for a coordinator transaction."""
        with self.lock:
            power = self.read_power()
            result: dict[str, Any] = {"power": power}
            if power is False:
                # Preserve an explicit/transient ^ON0 response when firmware
                # supplies one, but do not rely on it as the normal OFF case:
                # documented powered-off behavior is no response.
                result["operate"] = False
                missing_fields: list[str] = []
            elif power is True:
                result.update(
                    operate=self.read_operate(),
                    band=self.read_band(),
                    fault=self.read_fault(),
                )
                missing_fields = [
                    key for key in ("operate", "band", "fault") if result[key] is None
                ]
            else:
                missing_fields = ["power"]
            result.update(
                observed_at=self.last_seen,
                missing_fields=missing_fields,
                complete=not missing_fields,
                error=self.last_error,
            )
            return result

    def verify_target(
        self,
        expected: dict[str, Any],
        *,
        fields: Optional[tuple[str, ...] | list[str] | set[str]] = None,
    ) -> dict[str, Any]:
        """Read the device and compare the selected fields exactly."""
        readback = self.readback()
        return {**verify_exact_target(readback, expected, fields=fields), "readback": readback}

    def status(self, stop_event: Optional[threading.Event] = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "enabled": True,
            "connected": self.connected,
            "port": self.port,
            "baudrate": self.baudrate,
            "error": self.last_error,
        }
        if not self.open():
            result["connected"] = False
            result["error"] = self.last_error
            return result

        power = self.query("^ON;", "^ON", response_pattern=r"\^ON[01];")
        result["connected"] = self.connected
        if power:
            result["power"] = power.upper().startswith("^ON1")
            result["responsive"] = True
        else:
            # A transport can be open even when the device is absent or a
            # splitter is attached to the wrong endpoint. Do not turn a lack
            # of evidence into a confirmed powered-off state.
            result["power"] = None
            result["responsive"] = False
            result["quality"] = "unknown"
            result["observed_at"] = self.last_seen
            result["missing_fields"] = ["power"]
            result["error"] = self.last_error
            return result
        if result["power"] is False:
            # An explicit/transient ^ON0 was observed. Powered-firmware
            # telemetry is unavailable, so further queries only add timeouts.
            result["operate"] = False
            result["observed_at"] = self.last_seen
            result["missing_fields"] = []
            result["quality"] = "good"
            result["error"] = None
            return result

        queries = {
            "operate": ("^OS;", "^OS", r"\^OS[01];"),
            "band": ("^BN;", "^BN", r"\^BN\d{2};"),
            "fault": ("^FL;", "^FL", r"\^FL[^;]+;"),
            "temperature_c": ("^TM;", "^TM", r"\^TM\s*\d+;"),
            "volts_amps": ("^VI;", "^VI", r"\^VI\s*[\d.]+\s+[\d.]+;"),
            "power_swr": ("^WS;", "^WS", r"\^WS\s*\d+\s+[\d.]+;"),
            "firmware": ("^RVM;", "^RVM", r"\^RVM[^;]+;"),
        }
        responses: dict[str, Optional[str]] = {}
        interrupted = False
        for key, (command, prefix, pattern) in queries.items():
            if stop_event and stop_event.is_set():
                interrupted = True
                break
            responses[key] = self.query(command, prefix, response_pattern=pattern)
        missing_fields = [key for key in queries if key not in responses or not responses[key]]
        if responses.get("operate"):
            result["operate"] = responses["operate"].upper().startswith("^OS1")
        if responses.get("band"):
            code = responses["band"][3:5]
            result["band"] = next((name for name, value in BAND_CODES.items() if value == code), code)
        if responses.get("fault"):
            result["fault"] = responses["fault"][3:-1]
        if responses.get("temperature_c"):
            match = re.search(r"\^TM\s*(\d+)", responses["temperature_c"], re.I)
            if match:
                result["temperature_c"] = int(match.group(1))
        if responses.get("volts_amps"):
            match = re.search(r"\^VI\s*([\d.]+)\s+([\d.]+)", responses["volts_amps"], re.I)
            if match:
                result["voltage"] = _parse_tenths(match.group(1))
                result["current"] = _parse_tenths(match.group(2))
        if responses.get("power_swr"):
            match = re.search(r"\^WS\s*(\d+)\s+([\d.]+)", responses["power_swr"], re.I)
            if match:
                output_power = int(match.group(1))
                raw_swr = match.group(2)
                result["output_power_w"] = output_power
                result["swr"] = 0.0 if raw_swr == "000" else _parse_tenths(raw_swr)
                result["swr_live"] = output_power > 0 and raw_swr != "000"
                result["meter_observed_at"] = self.last_seen
                result["meter_complete"] = True
        if responses.get("firmware"):
            result["firmware"] = responses["firmware"][4:-1]
        result["_interrupted"] = interrupted
        result["responsive"] = True
        result["observed_at"] = self.last_seen
        result["missing_fields"] = missing_fields
        result["quality"] = "degraded" if missing_fields else "good"
        result["error"] = self.last_error
        return result


class KAT500(SerialCommandDevice):
    MODE_TO_COMMAND = {"bypass": "B", "manual": "M", "auto": "A"}

    def identify(self) -> bool:
        # Wake sleeping firmware before issuing the documented identify query.
        self.write(";;;")
        time.sleep(0.12)
        response = self.query("I;", "KAT500", timeout=0.8)
        return bool(response and response.upper().startswith("KAT500"))

    def set_band(self, band: str) -> bool:
        code = BAND_CODES.get(band)
        return bool(code and self.write(f"BN{code};"))

    def set_frequency(self, mhz: float) -> bool:
        return self.write(f"F {round(float(mhz) * 1000):d};")

    def set_antenna(self, antenna: int) -> bool:
        return antenna in {1, 2, 3} and self.write(f"AN{antenna};")

    def set_mode(self, mode: str) -> bool:
        code = self.MODE_TO_COMMAND.get(str(mode).lower())
        return bool(code and self.write(f"MD{code};"))

    def set_power(self, on: bool) -> bool:
        return self.write(f"PS{1 if on else 0};")

    def tune(self) -> bool:
        """Start the legacy full tune, which stores the resulting match."""
        return self.write("T;")

    def start_tune(self, *, store: bool = False) -> bool:
        """Start a full tune; default to the documented non-storing variant."""
        return self.write("FT;" if store else "FTNS;")

    def cancel_tune(self) -> bool:
        """Request cancellation at the end of the current tuning step."""
        return self.write("CT;")

    def tune_status(self) -> Optional[bool]:
        """Return ``True`` while a full search tune is in progress."""
        response = self.query("TP;", "TP", response_pattern=r"TP[01];")
        return None if response is None else response.upper().startswith("TP1")

    def store_memory(self, frequency_khz: Optional[int] = None) -> bool:
        """Store the current matching network, optionally for an exact kHz."""
        if frequency_khz is None:
            return self.write("SM;")
        if isinstance(frequency_khz, bool) or not isinstance(frequency_khz, int):
            return False
        if not 1 <= frequency_khz <= 99999:
            return False
        return self.write(f"SM {frequency_khz};")

    def clear_frequency_memories(self, band: str, antenna: int) -> bool:
        """Clear one band's KAT frequency memories for an explicit antenna.

        This is the narrowly scoped documented ``EMbba;`` operation.  It is
        intentionally separate from tune/store and accepts neither an omitted
        antenna nor a factory/configuration reset.  Callers must provide the
        band and antenna they have already presented to, and confirmed with,
        the operator.  Antenna 0 means every antenna on the selected band and
        therefore still has to be requested explicitly.
        """
        code = BAND_CODES.get(str(band).strip().lower())
        if isinstance(antenna, bool) or not isinstance(antenna, int):
            return False
        if code is None or antenna not in {0, 1, 2, 3}:
            return False
        return self.write(f"EM{code}{antenna};")

    def _wake(self) -> None:
        """Wake sleeping firmware without changing tuner state."""
        self.write(";;;")
        time.sleep(0.1)

    def read_power(self) -> Optional[bool]:
        response = self.query("PS;", "PS", response_pattern=r"PS[01];")
        return None if response is None else response.upper().startswith("PS1")

    def read_mode(self) -> Optional[str]:
        response = self.query("MD;", "MD", response_pattern=r"MD[AMB];")
        if response is None:
            return None
        return {"A": "auto", "M": "manual", "B": "bypass"}.get(response[2:3].upper())

    def read_antenna(self) -> Optional[int]:
        response = self.query("AN;", "AN", response_pattern=r"AN[0-3];")
        return None if response is None else int(response[2])

    def read_band(self) -> Optional[str]:
        response = self.query("BN;", "BN", response_pattern=r"BN\d{2};")
        if response is None:
            return None
        code = response[2:4]
        return next((name for name, value in BAND_CODES.items() if value == code), code)

    def read_frequency_khz(self) -> Optional[int]:
        response = self.query("F;", "F ", response_pattern=r"F\s+\d+;")
        match = re.search(r"F\s+(\d+)", response or "", re.IGNORECASE)
        return int(match.group(1)) if match else None

    def read_fault(self) -> Optional[str]:
        response = self.query("FLT;", "FLT", response_pattern=r"FLT[0-4];")
        return None if response is None else response[3:-1]

    def clear_fault(self) -> bool:
        """Clear the current KAT500 fault using the documented FLTC command."""
        return self.write("FLTC;")

    def read_amp_key_interrupted(self) -> Optional[bool]:
        """Read the documented KAT500 amplifier-key interrupt relay state.

        ``AMPI0`` means the key line is connected and ``AMPI1`` means the
        tuner is deliberately preventing the amplifier from being keyed.
        OPERATE on the KPA500 is only an armed state, so this independent
        readback is required before claiming the amplifier can key.
        """
        response = self.query("AMPI;", "AMPI", response_pattern=r"AMPI[01];")
        return None if response is None else response.upper().startswith("AMPI1")

    def set_amp_key_interrupted(self, interrupted: bool) -> bool:
        """Set the documented key-interrupt relay to interrupted/connected."""
        return self.write(f"AMPI{1 if interrupted else 0};")

    def read_bypass(self) -> Optional[bool]:
        response = self.query("BYP;", "BYP", response_pattern=r"BYP[BN];")
        return None if response is None else response.upper().startswith("BYPB")

    def meter_status(self) -> dict[str, Any]:
        """Read RF-coupler meters and qualify SWR with forward-RF evidence.

        KAT500 VSWR is retained by the firmware after RF ends.  Publishing it
        as a new receive-time measurement is misleading, so an idle sample
        carries the ADCs and ``swr_live=False`` but does not replace the last
        RF-qualified SWR cached by :class:`ElecraftManager`.
        """
        with self.lock:
            queries = {
                "forward_adc": ("VFWD;", "VFWD", r"VFWD\s+\d+;"),
                "reflected_adc": ("VRFL;", "VRFL", r"VRFL\s+\d+;"),
                "swr_sample": ("VSWR;", "VSWR ", r"VSWR\s+[\d.]+;"),
            }
            responses = {
                key: self.query(
                    command,
                    prefix,
                    response_pattern=pattern,
                    update_last_seen=False,
                )
                for key, (command, prefix, pattern) in queries.items()
            }
            result: dict[str, Any] = {
                "meter_observed_at": time.time() if any(responses.values()) else None,
                "meter_complete": all(responses.values()),
                "meter_missing_fields": [
                    key for key, response in responses.items() if response is None
                ],
                "meter_error": None if all(responses.values()) else self.last_error,
            }
            for key in ("forward_adc", "reflected_adc"):
                match = re.search(r"\s+(\d+)", responses[key] or "")
                if match:
                    result[key] = int(match.group(1))
            match = re.search(r"\s+([\d.]+)", responses["swr_sample"] or "")
            if match:
                result["swr_sample"] = float(match.group(1))
            live = bool(result.get("forward_adc", 0) > 0 and "swr_sample" in result)
            result["swr_live"] = live
            if live:
                result["swr"] = result["swr_sample"]
                result["swr_observed_at"] = result["meter_observed_at"]
            return result

    def readback(self) -> dict[str, Any]:
        """Return a fresh, focused readback for a coordinator transaction."""
        with self.lock:
            self._wake()
            result: dict[str, Any] = {
                "power": self.read_power(),
                "mode": self.read_mode(),
                "antenna": self.read_antenna(),
                "band": self.read_band(),
                "frequency_khz": self.read_frequency_khz(),
                "tuning": self.tune_status(),
                "fault": self.read_fault(),
                "bypass": self.read_bypass(),
                "amp_key_interrupted": self.read_amp_key_interrupted(),
            }
            critical_fields = (
                "power",
                "mode",
                "antenna",
                "band",
                "frequency_khz",
                "tuning",
                "fault",
                "bypass",
                "amp_key_interrupted",
            )
            missing_fields = [key for key in critical_fields if result.get(key) is None]
            result.update(
                observed_at=self.last_seen,
                missing_fields=missing_fields,
                complete=not missing_fields,
                error=self.last_error,
            )
            return result

    def remote_telemetry(self) -> dict[str, Any]:
        """Return KAT Remote-style operational telemetry using public GETs."""
        with self.lock:
            result = self.readback()
            telemetry_queries = {
                "capacitor_mask": ("C;", "C", r"C[0-9A-F]{2};"),
                "inductor_mask": ("L;", "L", r"L[0-9A-F]{2};"),
                "network_side": ("SIDE;", "SIDE", r"SIDE[AT];"),
                "forward_adc": ("VFWD;", "VFWD", r"VFWD\s+\d+;"),
                "reflected_adc": ("VRFL;", "VRFL", r"VRFL\s+\d+;"),
                "swr": ("VSWR;", "VSWR ", r"VSWR\s+[\d.]+;"),
                "bypass_swr": ("VSWRB;", "VSWRB ", r"VSWRB\s+[\d.]+;"),
                "frequency_source_khz": ("FX;", "FX ", r"FX\s+\d+;"),
                "frequency_range_khz": ("FY;", "FY ", r"FY\s+\d+-\d+;"),
                "serial_number": ("SN;", "SN ", r"SN\s+[^;]+;"),
                "firmware": ("RV;", "RV", r"RV[^;]+;"),
            }
            telemetry = {
                key: self.query(command, prefix, response_pattern=pattern)
                for key, (command, prefix, pattern) in telemetry_queries.items()
            }
            if telemetry["capacitor_mask"]:
                result["capacitor_mask"] = telemetry["capacitor_mask"][1:-1].upper()
            if telemetry["inductor_mask"]:
                result["inductor_mask"] = telemetry["inductor_mask"][1:-1].upper()
            if telemetry["network_side"]:
                result["network_side"] = {
                    "A": "antenna",
                    "T": "transmitter",
                }[telemetry["network_side"][4:5].upper()]
            for key in ("forward_adc", "reflected_adc", "frequency_source_khz"):
                match = re.search(r"\s+(\d+)", telemetry[key] or "")
                if match:
                    result[key] = int(match.group(1))
            for key in ("swr", "bypass_swr"):
                match = re.search(r"\s+([\d.]+)", telemetry[key] or "")
                if match:
                    parsed = float(match.group(1))
                    if key == "swr":
                        result["swr_sample"] = parsed
                    else:
                        result[key] = parsed
            result["swr_live"] = bool(
                result.get("forward_adc", 0) > 0 and "swr_sample" in result
            )
            if result["swr_live"]:
                result["swr"] = result["swr_sample"]
                result["swr_observed_at"] = self.last_seen
            if telemetry["frequency_range_khz"]:
                match = re.search(r"(\d+)-(\d+)", telemetry["frequency_range_khz"])
                if match:
                    result["frequency_range_khz"] = [int(match.group(1)), int(match.group(2))]
            if telemetry["serial_number"]:
                result["serial_number"] = telemetry["serial_number"][2:-1].strip()
            if telemetry["firmware"]:
                result["firmware"] = telemetry["firmware"][2:-1]
            result.update(
                observed_at=self.last_seen,
                telemetry_missing=[key for key, response in telemetry.items() if response is None],
                error=self.last_error,
            )
            return result

    def verify_target(
        self,
        expected: dict[str, Any],
        *,
        fields: Optional[tuple[str, ...] | list[str] | set[str]] = None,
    ) -> dict[str, Any]:
        """Read the device and compare the selected fields exactly."""
        readback = self.readback()
        return {**verify_exact_target(readback, expected, fields=fields), "readback": readback}

    def status(self, stop_event: Optional[threading.Event] = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "enabled": True,
            "connected": self.connected,
            "port": self.port,
            "baudrate": self.baudrate,
            "error": self.last_error,
        }
        if not self.open():
            result["connected"] = False
            result["error"] = self.last_error
            return result

        result["connected"] = self.connected
        self.write(";;;")
        time.sleep(0.1)
        queries = {
            "power": ("PS;", "PS", r"PS[01];"),
            "mode": ("MD;", "MD", r"MD[AMB];"),
            "antenna": ("AN;", "AN", r"AN[0-3];"),
            "band": ("BN;", "BN", r"BN\d{2};"),
            "frequency": ("F;", "F ", r"F\s+\d+;"),
            "forward_adc": ("VFWD;", "VFWD", r"VFWD\s+\d+;"),
            "reflected_adc": ("VRFL;", "VRFL", r"VRFL\s+\d+;"),
            "swr": ("VSWR;", "VSWR ", r"VSWR\s+[\d.]+;"),
            "tuning": ("TP;", "TP", r"TP[01];"),
            "fault": ("FLT;", "FLT", r"FLT[0-4];"),
            "bypass": ("BYP;", "BYP", r"BYP[BN];"),
            "amp_key_interrupted": ("AMPI;", "AMPI", r"AMPI[01];"),
            "firmware": ("RV;", "RV", r"RV[^;]+;"),
        }
        responses: dict[str, Optional[str]] = {}
        interrupted = False
        for key, (command, prefix, pattern) in queries.items():
            if stop_event and stop_event.is_set():
                interrupted = True
                break
            responses[key] = self.query(command, prefix, response_pattern=pattern)
        missing_fields = [key for key in queries if key not in responses or not responses[key]]
        if responses.get("power"):
            result["power"] = responses["power"].upper().startswith("PS1")
        if responses.get("mode"):
            result["mode"] = {"A": "auto", "M": "manual", "B": "bypass"}.get(
                responses["mode"][2:3].upper(), "unknown"
            )
        if responses.get("antenna"):
            match = re.search(r"AN([0-3])", responses["antenna"], re.I)
            if match:
                result["antenna"] = int(match.group(1))
        if responses.get("band"):
            code = responses["band"][2:4]
            result["band"] = next((name for name, value in BAND_CODES.items() if value == code), code)
        if responses.get("frequency"):
            match = re.search(r"F\s+(\d+)", responses["frequency"], re.I)
            if match:
                result["frequency_khz"] = int(match.group(1))
        for key in ("forward_adc", "reflected_adc"):
            match = re.search(r"\s+(\d+)", responses.get(key) or "")
            if match:
                result[key] = int(match.group(1))
        if responses.get("swr"):
            match = re.search(r"VSWR\s+([\d.]+)", responses["swr"], re.I)
            if match:
                result["swr_sample"] = float(match.group(1))
        result["swr_live"] = bool(
            result.get("forward_adc", 0) > 0 and "swr_sample" in result
        )
        if result["swr_live"]:
            result["swr"] = result["swr_sample"]
            result["swr_observed_at"] = self.last_seen
        result["meter_observed_at"] = self.last_seen
        result["meter_complete"] = all(
            responses.get(key) for key in ("forward_adc", "reflected_adc", "swr")
        )
        if responses.get("tuning"):
            result["tuning"] = responses["tuning"].upper().startswith("TP1")
        if responses.get("fault"):
            result["fault"] = responses["fault"][3:-1]
        if responses.get("bypass"):
            result["bypass"] = responses["bypass"].upper().startswith("BYPB")
        if responses.get("amp_key_interrupted"):
            result["amp_key_interrupted"] = responses["amp_key_interrupted"].upper().startswith(
                "AMPI1"
            )
        if responses.get("firmware"):
            result["firmware"] = responses["firmware"][2:-1]
        result["_interrupted"] = interrupted
        result["responsive"] = bool(responses) and len(missing_fields) < len(queries)
        result["observed_at"] = self.last_seen
        result["missing_fields"] = missing_fields
        result["quality"] = (
            "unknown"
            if not result["responsive"]
            else "degraded"
            if missing_fields
            else "good"
        )
        result["error"] = self.last_error
        return result


@dataclass
class ElecraftManager:
    """Own both serial devices and synchronize them with FlexRadio state."""

    kpa500: Optional[KPA500] = None
    kat500: Optional[KAT500] = None
    follow_radio: bool = True
    control_enabled: bool = False
    antenna_policy: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_KAT500_ANTENNAS))
    last_frequency: Optional[float] = None
    last_radio_mode: Optional[str] = None
    last_band: Optional[str] = None
    last_kpa_band: Optional[str] = None
    last_kat_band: Optional[str] = None
    last_kat_frequency: Optional[float] = None
    last_kat_antenna: Optional[int] = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _status_refresh_task: Optional[asyncio.Task] = None
    _sync_requested: threading.Event = field(default_factory=threading.Event)
    _sync_waiters: int = 0
    _executor: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(max_workers=2, thread_name_prefix="elecraft-io"),
        repr=False,
    )
    _poll_task: Optional[asyncio.Task] = None
    _meter_poll_task: Optional[asyncio.Task] = None
    _status: dict[str, Any] = field(default_factory=dict)
    _meter_cache: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {"kpa500": {}, "kat500": {}}
    )
    _radio_transmitting: bool = False
    _meter_poll_until: float = 0.0
    _lifecycle_generation: int = 0
    _maintenance_suspended: bool = False

    async def _run_io(self, operation: Callable[..., Any], *args: Any) -> Any:
        """Run serial work independently of slow database/network workers."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, partial(operation, *args))

    def begin_control_io(self) -> None:
        """Give a guarded coordinator transaction priority over telemetry polls."""
        self._sync_waiters += 1
        self._sync_requested.set()

    def end_control_io(self) -> None:
        """Release coordinator priority without disturbing another waiter."""
        self._sync_waiters = max(0, self._sync_waiters - 1)
        if self._sync_waiters == 0:
            self._sync_requested.clear()

    def _build_from_config(self) -> None:
        self.follow_radio = bool(getattr(config, "ELECRAFT_FOLLOW_RADIO", True))
        # Legacy per-device writes are intentionally retired. All station
        # changes must pass through the coordinator's interlocks/readback.
        self.control_enabled = False
        policy = getattr(config, "KAT500_ANTENNA_POLICY", DEFAULT_KAT500_ANTENNAS)
        self.antenna_policy = {
            band: int((policy or {}).get(band, antenna))
            for band, antenna in DEFAULT_KAT500_ANTENNAS.items()
        }
        if bool(getattr(config, "KPA500_ENABLED", False)):
            self.kpa500 = KPA500(
                "KPA500",
                str(getattr(config, "KPA500_PORT", "COM6")),
                int(getattr(config, "KPA500_BAUDRATE", 38400)),
            )
        if bool(getattr(config, "KAT500_ENABLED", False)):
            self.kat500 = KAT500(
                "KAT500",
                str(getattr(config, "KAT500_PORT", "COM11")),
                int(getattr(config, "KAT500_BAUDRATE", 38400)),
            )

    async def start(self) -> None:
        self._build_from_config()
        await self.connect()
        self._start_polling()

    async def stop(self) -> None:
        await self._stop_polling()
        await self.disconnect()

    def _start_polling(self) -> None:
        if self._maintenance_suspended:
            return
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(
                self._poll_loop(),
                name="elecraft_status_poll",
            )
        if self._meter_poll_task is None or self._meter_poll_task.done():
            self._meter_poll_task = asyncio.create_task(
                self._meter_poll_loop(),
                name="elecraft_meter_poll",
            )

    async def _stop_polling(self) -> None:
        tasks = [task for task in (self._poll_task, self._meter_poll_task) if task]
        self._poll_task = None
        self._meter_poll_task = None
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def connect(self) -> dict[str, Any]:
        async with self._lock:
            self._lifecycle_generation += 1
            if self.kpa500:
                self.kpa500.resume()
                await self._run_io(self.kpa500.open)
            if self.kat500:
                self.kat500.resume()
                await self._run_io(self.kat500.open)
        return self.snapshot()

    async def suspend_for_maintenance(self) -> dict[str, Any]:
        """Stop background I/O and release both serial ports.

        This lifecycle primitive is intentionally coordinator-facing.  HTTP
        routes must not expose it directly because the coordinator first has
        to prove FLEX receive and KPA500 standby.
        """
        self._maintenance_suspended = True
        await self._stop_polling()
        return await self.disconnect()

    async def reopen_for_maintenance_exit(self) -> dict[str, Any]:
        """Open and identify configured devices without restarting polling."""
        if not self._maintenance_suspended:
            raise RuntimeError("Elecraft manager is not suspended for maintenance")
        async with self._lock:
            self._lifecycle_generation += 1
            devices = tuple(device for device in (self.kpa500, self.kat500) if device)
            for device in devices:
                device.resume()
                if not await self._run_io(device.open):
                    raise RuntimeError(
                        device.last_error or f"{device.name} serial port could not be opened"
                    )
                if not await self._run_io(device.identify):
                    raise RuntimeError(
                        device.last_error or f"{device.name} identity could not be confirmed"
                    )
        return self.snapshot()

    async def complete_maintenance_exit(self) -> dict[str, Any]:
        """Resume polling only after coordinator safety verification succeeds."""
        self._maintenance_suspended = False
        self._start_polling()
        return self.snapshot()

    async def keep_maintenance_suspended(self) -> dict[str, Any]:
        """Close any reopened ports after a failed maintenance-exit proof."""
        self._maintenance_suspended = True
        await self._stop_polling()
        return await self.disconnect()

    async def disconnect(self) -> dict[str, Any]:
        task = self._status_refresh_task
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._status_refresh_task = None
        async with self._lock:
            self._lifecycle_generation += 1
            if self.kpa500:
                await self._run_io(self.kpa500.suspend)
            if self.kat500:
                await self._run_io(self.kat500.suspend)
            self._status = {}
            self._meter_cache = {"kpa500": {}, "kat500": {}}
            self._radio_transmitting = False
            self._meter_poll_until = 0.0
        return self.snapshot()

    async def reconfigure(self) -> dict[str, Any]:
        if self._maintenance_suspended:
            raise RuntimeError("Elecraft reconfiguration is blocked during maintenance")
        task = self._status_refresh_task
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._status_refresh_task = None
        async with self._lock:
            self._lifecycle_generation += 1
            if self.kpa500:
                await self._run_io(self.kpa500.retire)
            if self.kat500:
                await self._run_io(self.kat500.retire)
            self.kpa500 = None
            self.kat500 = None
            self.last_band = None
            self.last_frequency = None
            self.last_radio_mode = None
            self.last_kpa_band = None
            self.last_kat_band = None
            self.last_kat_frequency = None
            self.last_kat_antenna = None
            self._status = {}
            self._meter_cache = {"kpa500": {}, "kat500": {}}
            self._radio_transmitting = False
            self._meter_poll_until = 0.0
            self._build_from_config()
            if self.kpa500:
                await self._run_io(self.kpa500.open)
            if self.kat500:
                await self._run_io(self.kat500.open)
        return self.snapshot()

    def observe_radio_tx_state(
        self,
        mox: bool | None,
        interlock_state: str | None = None,
    ) -> None:
        """Select fast GET-only meter sampling from authoritative FLEX state."""
        interlock = str(interlock_state or "").strip().upper()
        active = bool(mox is True or interlock == "TRANSMITTING")
        was_active = self._radio_transmitting
        self._radio_transmitting = active
        if active:
            self._meter_poll_until = max(
                self._meter_poll_until,
                time.monotonic() + ELECRAFT_METER_RX_TAIL_SECONDS,
            )
        elif was_active:
            # A short tail captures the KPA's documented 000/000 receive
            # state while retaining the last RF-qualified KAT SWR.
            self._meter_poll_until = (
                time.monotonic() + ELECRAFT_METER_RX_TAIL_SECONDS
            )

    async def sync_radio_state(self, frequency: float | None, mode: str | None) -> None:
        if frequency is None:
            return
        frequency = float(frequency)
        band = band_from_frequency(frequency)
        if band is None:
            return
        if not self.follow_radio:
            return
        # Observing the authoritative radio is always safe and keeps the
        # dashboard current. Device writes remain behind an explicit migration
        # switch until the station coordinator enforces TX/interlock/readback.
        self.last_band = band
        self.last_frequency = frequency
        self.last_radio_mode = str(mode or "") or None
        if not self.control_enabled:
            return
        antenna = int(self.antenna_policy.get(band, 1))
        needs_kpa_band = bool(self.kpa500 and band != self.last_kpa_band)
        needs_kat_band = bool(self.kat500 and band != self.last_kat_band)
        needs_kat_frequency = bool(
            self.kat500
            and (
                self.last_kat_frequency is None
                or abs(frequency - self.last_kat_frequency) >= 0.001
            )
        )
        needs_kat_antenna = bool(
            self.kat500 and antenna != self.last_kat_antenna
        )
        if not any(
            (
                needs_kpa_band,
                needs_kat_band,
                needs_kat_frequency,
                needs_kat_antenna,
            )
        ):
            return
        # Signal before waiting for the manager lock. Slow telemetry passes see
        # this flag between GETs and yield the serial ports to the band change.
        self._sync_waiters += 1
        self._sync_requested.set()
        try:
            async with self._lock:
                if self.kpa500 and band != self.last_kpa_band:
                    if await self._run_io(self.kpa500.set_band, band):
                        self.last_kpa_band = band
                        if self._status.get("kpa500"):
                            self._status["kpa500"]["band"] = band
                        logger.info("KPA500 followed Flex to %s", band)
                    else:
                        logger.warning("KPA500 did not accept Flex band %s; will retry", band)
                if self.kat500:
                    if band != self.last_kat_band:
                        if await self._run_io(self.kat500.set_band, band):
                            self.last_kat_band = band
                            if self._status.get("kat500"):
                                self._status["kat500"]["band"] = band
                            logger.info("KAT500 followed Flex to %s", band)
                        else:
                            logger.warning("KAT500 did not accept Flex band %s; will retry", band)
                    if self.last_kat_frequency is None or abs(frequency - self.last_kat_frequency) >= 0.001:
                        if await self._run_io(self.kat500.set_frequency, frequency):
                            self.last_kat_frequency = frequency
                            if self._status.get("kat500"):
                                self._status["kat500"]["frequency_khz"] = round(frequency * 1000)
                        else:
                            logger.warning("KAT500 did not accept Flex frequency %.6f; will retry", frequency)
                    if antenna != self.last_kat_antenna:
                        if await self._run_io(self.kat500.set_antenna, antenna):
                            self.last_kat_antenna = antenna
                            if self._status.get("kat500"):
                                self._status["kat500"]["antenna"] = antenna
                            logger.info("KAT500 selected ANT%d for %s", antenna, band)
                        else:
                            logger.warning("KAT500 did not accept ANT%d for %s; will retry", antenna, band)
                self.last_band = band
                self.last_frequency = frequency
                self.last_radio_mode = str(mode or "") or None
        finally:
            self._sync_waiters -= 1
            if self._sync_waiters == 0:
                self._sync_requested.clear()

    @staticmethod
    def _merge_kat_meter_cache(
        previous: dict[str, Any],
        sample: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge a sample without overwriting the last RF-qualified SWR."""
        merged = dict(previous)
        for key in (
            "forward_adc",
            "reflected_adc",
            "swr_sample",
            "swr_live",
            "meter_observed_at",
            "meter_complete",
            "meter_missing_fields",
            "meter_error",
        ):
            if key in sample:
                merged[key] = sample[key]
        if sample.get("swr_live") is True and sample.get("swr") is not None:
            merged["swr"] = sample["swr"]
            merged["swr_observed_at"] = sample.get(
                "swr_observed_at", sample.get("meter_observed_at")
            )
        merged["swr_valid"] = merged.get("swr") is not None
        return merged

    def _merge_meter_sample(self, device_name: str, sample: dict[str, Any]) -> None:
        if device_name == "kat500":
            self._meter_cache[device_name] = self._merge_kat_meter_cache(
                self._meter_cache.get(device_name) or {},
                sample,
            )
            return
        merged = dict(self._meter_cache.get(device_name) or {})
        for key in (
            "output_power_w",
            "swr",
            "swr_live",
            "meter_observed_at",
            "meter_complete",
            "meter_error",
        ):
            if key in sample:
                merged[key] = sample[key]
        self._meter_cache[device_name] = merged

    async def refresh_meters(self) -> dict[str, Any]:
        """Run one bounded GET-only meter pass without changing state age."""
        if self._maintenance_suspended:
            return self.snapshot()
        async with self._lock:
            kpa_device = self.kpa500
            kat_device = self.kat500
            lifecycle_generation = self._lifecycle_generation
        device_tasks = []
        if kpa_device and hasattr(kpa_device, "meter_status"):
            device_tasks.append(
                ("kpa500", kpa_device, self._run_io(kpa_device.meter_status))
            )
        if kat_device and hasattr(kat_device, "meter_status"):
            device_tasks.append(
                ("kat500", kat_device, self._run_io(kat_device.meter_status))
            )
        if not device_tasks:
            return self.snapshot()
        device_results = await asyncio.gather(
            *(task for _, _, task in device_tasks),
            return_exceptions=True,
        )
        async with self._lock:
            if lifecycle_generation != self._lifecycle_generation:
                return self.snapshot()
            for (name, device, _), result in zip(
                device_tasks, device_results, strict=True
            ):
                current = self.kpa500 if name == "kpa500" else self.kat500
                if (
                    device is current
                    and getattr(device, "io_enabled", True)
                    and isinstance(result, dict)
                ):
                    self._merge_meter_sample(name, result)
            return self.snapshot()

    async def refresh_status(
        self,
        *,
        maintenance_verification: bool = False,
    ) -> dict[str, Any]:
        if self._maintenance_suspended and not maintenance_verification:
            return self.snapshot()
        # All callers share one in-flight hardware pass. A plain lock would
        # queue a new full pass for every browser/background request.
        task = self._status_refresh_task
        if task is None or task.done():
            task = asyncio.create_task(self._refresh_status_pass())
            self._status_refresh_task = task
        try:
            return await asyncio.shield(task)
        finally:
            if task.done() and self._status_refresh_task is task:
                self._status_refresh_task = None

    async def publish_verified_readbacks(
        self,
        kpa_status: dict[str, Any],
        kat_status: dict[str, Any],
    ) -> dict[str, Any]:
        """Publish coordinator readbacks without immediately polling twice.

        The coordinator has already obtained complete, fresh readbacks from both
        devices and compared every route-critical field. Reusing that evidence
        avoids a redundant full status pass while retaining the normal periodic
        poll as an independent subsequent observation.
        """
        async with self._lock:
            now = time.time()
            current_kpa = dict(self._status.get("kpa500") or {})
            current_kat = dict(self._status.get("kat500") or {})
            current_kpa.update(kpa_status)
            current_kat.update(kat_status)
            current_kpa.update(
                enabled=True,
                connected=bool(self.kpa500 and self.kpa500.connected),
                responsive=True,
                quality="good",
                error=None,
            )
            current_kat.update(
                enabled=True,
                connected=bool(self.kat500 and self.kat500.connected),
                responsive=True,
                quality="good",
                error=None,
            )
            self.last_kpa_band = kpa_status.get("band")
            self.last_kat_band = kat_status.get("band")
            frequency_khz = kat_status.get("frequency_khz")
            self.last_kat_frequency = (
                float(frequency_khz) / 1000 if frequency_khz is not None else None
            )
            self.last_kat_antenna = kat_status.get("antenna")
            self._status = {
                **self._status,
                "following_radio": self.follow_radio,
                "control_enabled": self.control_enabled,
                "radio_frequency": self.last_frequency,
                "radio_mode": self.last_radio_mode,
                "radio_band": self.last_band,
                "kpa500": current_kpa,
                "kat500": current_kat,
                "updated_at": now,
            }
            return self.snapshot()

    async def _refresh_status_pass(self) -> dict[str, Any]:
        # The independent serial devices can be queried in parallel. Do not
        # hold the manager lock during telemetry: Flex synchronization can set
        # _sync_requested and interrupt this pass between device commands.
        async with self._lock:
            kpa_enabled = bool(getattr(config, "KPA500_ENABLED", False))
            kat_enabled = bool(getattr(config, "KAT500_ENABLED", False))
            kpa_device = self.kpa500
            kat_device = self.kat500
            lifecycle_generation = self._lifecycle_generation
        device_tasks = []
        if kpa_device:
            device_tasks.append(("kpa", self._run_io(kpa_device.status, self._sync_requested)))
        if kat_device:
            device_tasks.append(("kat", self._run_io(kat_device.status, self._sync_requested)))
        device_results = await asyncio.gather(*(task for _, task in device_tasks))
        results = {
            name: result
            for (name, _), result in zip(device_tasks, device_results, strict=True)
        }
        async with self._lock:
            # A settings save may have replaced either device while these
            # reads were in flight. Never publish incomplete or retired data.
            interrupted = any(result.pop("_interrupted", False) for result in results.values())
            if (
                interrupted
                or lifecycle_generation != self._lifecycle_generation
                or kpa_device is not self.kpa500
                or kat_device is not self.kat500
                or (kpa_device is not None and not getattr(kpa_device, "io_enabled", True))
                or (kat_device is not None and not getattr(kat_device, "io_enabled", True))
            ):
                return self.snapshot()
            kpa = results.get("kpa") or {
                "enabled": kpa_enabled,
                "connected": False,
                "port": str(getattr(config, "KPA500_PORT", "COM6")),
            }
            kat = results.get("kat") or {
                "enabled": kat_enabled,
                "connected": False,
                "port": str(getattr(config, "KAT500_PORT", "COM11")),
            }
            self._status = {
                "following_radio": self.follow_radio,
                "control_enabled": self.control_enabled,
                "radio_frequency": self.last_frequency,
                "radio_mode": self.last_radio_mode,
                "radio_band": self.last_band,
                "kpa500": kpa,
                "kat500": kat,
                "updated_at": time.time(),
            }
            if kpa.get("meter_observed_at") is not None:
                self._merge_meter_sample("kpa500", kpa)
            if kat.get("meter_observed_at") is not None:
                self._merge_meter_sample("kat500", kat)
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        if self._status:
            snapshot = {
                **self._status,
                "following_radio": self.follow_radio,
                "control_enabled": self.control_enabled,
                "radio_frequency": self.last_frequency,
                "radio_mode": self.last_radio_mode,
                "radio_band": self.last_band,
                "maintenance_suspended": self._maintenance_suspended,
            }
            snapshot["kpa500"] = {
                **(snapshot.get("kpa500") or {}),
                **(self._meter_cache.get("kpa500") or {}),
            }
            snapshot["kat500"] = {
                **(snapshot.get("kat500") or {}),
                **(self._meter_cache.get("kat500") or {}),
            }
            return snapshot
        snapshot = {
            "following_radio": self.follow_radio,
            "control_enabled": self.control_enabled,
            "radio_frequency": self.last_frequency,
            "radio_mode": self.last_radio_mode,
            "radio_band": self.last_band,
            "maintenance_suspended": self._maintenance_suspended,
            "kpa500": {
                "enabled": self.kpa500 is not None,
                "connected": bool(self.kpa500 and self.kpa500.connected),
                "port": self.kpa500.port if self.kpa500 else getattr(config, "KPA500_PORT", "COM6"),
            },
            "kat500": {
                "enabled": self.kat500 is not None,
                "connected": bool(self.kat500 and self.kat500.connected),
                "port": self.kat500.port if self.kat500 else getattr(config, "KAT500_PORT", "COM11"),
            },
        }
        snapshot["kpa500"].update(self._meter_cache.get("kpa500") or {})
        snapshot["kat500"].update(self._meter_cache.get("kat500") or {})
        return snapshot

    def record_kpa_operate_readback(self, operate: bool) -> None:
        """Publish a coordinator-confirmed OS readback without a full poll.

        OPERATE/STANDBY changes are confirmed with the KPA500's dedicated
        ``^OS;`` query.  Updating that one cached field lets the station widget
        reflect the switch immediately while the normal complete poll continues
        to refresh the remaining telemetry.
        """
        if not self._status:
            return
        kpa = dict(self._status.get("kpa500") or {})
        kpa["operate"] = bool(operate)
        kpa["connected"] = True
        missing = [field for field in (kpa.get("missing_fields") or []) if field != "operate"]
        kpa["missing_fields"] = missing
        if not missing:
            kpa["quality"] = "good"
        self._status = {**self._status, "kpa500": kpa}

    def station_path(self, radio_status: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Return a read-only description of current end-to-end path evidence."""
        antenna_names = getattr(config, "KAT500_ANTENNA_NAMES", {}) or {}
        return build_station_path(
            self.snapshot(),
            radio_status,
            antenna_policy=self.antenna_policy,
            antenna_names=antenna_names,
            flex_antenna_policy=getattr(config, "FLEX_ANTENNA_POLICY", {}) or {},
        )

    async def _poll_loop(self) -> None:
        while not self._maintenance_suspended:
            try:
                await self.refresh_status()
                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Elecraft status poll failed")
                await asyncio.sleep(3.0)

    async def _meter_poll_loop(self) -> None:
        """Poll only fast GET meters while FLEX reports transmit activity."""
        while not self._maintenance_suspended:
            try:
                active = bool(
                    self._radio_transmitting
                    or time.monotonic() < self._meter_poll_until
                )
                if active:
                    await self.refresh_meters()
                    await asyncio.sleep(ELECRAFT_METER_POLL_SECONDS)
                else:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Elecraft meter poll failed")
                await asyncio.sleep(ELECRAFT_METER_POLL_SECONDS)


_manager = ElecraftManager()


def get_elecraft_manager() -> ElecraftManager:
    return _manager
