"""Backend-owned Digital mode automation controller.

The browser can render controls, but target ownership, queue priority, retry
state, duplicate protection, and dwell timing belong in the backend so they
survive UI reloads and coordinate decoded stations, spots, Wavelog status, and
radio state from one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dataclass_fields
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import re
from typing import Any, Iterable, Mapping, Optional

from radio_control.activity_references import (
    HUNTER_PROGRAMS,
    canonical_reference_program,
    extract_activity_references,
)
from radio_control.spot_classification import classify_call_status, classify_dxcc_status


logger = logging.getLogger(__name__)


SUPPORTED_AUTOMATION_MODES = {"FT8", "FT4", "FT2"}
CALL_RE = re.compile(r"^[A-Z0-9][A-Z0-9/]{2,}$")
GRID_RE = re.compile(r"^[A-R]{2}\d{2}([A-X]{2})?$")
NON_GRID_TOKENS = {"CQ", "DE", "QRZ", "RRR", "RR73", "73"}
DEFAULT_TX_AUDIO_HZ = 1500
TX_AUDIO_LOW_HZ = 300
TX_AUDIO_HIGH_HZ = 3000
TX_AUDIO_STEP_HZ = 50
TX_AUDIO_GUARD_HZ = 90
DECISION_LOG_LIMIT = 200
DIRECT_CALLER_SCORE = 99999
ATNO_SCORE = 10000
DXCC_WORKED_NOT_CONFIRMED_SCORE = 9000
DXCC_NEW_BAND_SCORE = 8000
NON_EU_NEW_CALL_SCORE = 7500
CALL_NEW_BAND_SCORE = 6500
REFERENCE_SCORE = 6000
GRID_SCORE = 5000
MODE_SCORE = 3500
NEW_CALL_SCORE = 2000
DXCC_SPOT_SILENCE_SECONDS = 300
DXCC_SPOT_FRESHNESS_SECONDS = 120
DXCC_HUNT_WATCHDOG_MINUTES = 20
DXCC_HUNT_COOLDOWN_MINUTES = 5
FAVORABLE_PROPAGATION_SCORE = 52
SPOT_HUNT_SOURCES = {"spot", "cluster", "rbl", "selected-spot", "dx-cluster", "reverse-beacon"}

TARGET_LIFECYCLE_STATES = {
    "candidate",
    "queued",
    "selected",
    "command_sent",
    "active",
    "in_progress",
    "completed",
    "logged",
    "failed",
    "backoff",
    "expired",
    "skipped",
    "ignored",
}

ACTIVE_QSO_STATES = {
    "idle",
    "candidate_selected",
    "command_sent",
    "waiting_for_tx",
    "calling",
    "in_qso",
    "waiting_rrr",
    "waiting_73",
    "reply_received",
    "report_sent",
    "rr73_seen",
    "logged",
    "completed",
    "blocked",
    "failed",
    "aborted",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) not in (None, ""):
            return mapping.get(key)
    return None


def _int(value: Any, default: int, *, low: Optional[int] = None, high: Optional[int] = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if low is not None:
        parsed = max(low, parsed)
    if high is not None:
        parsed = min(high, parsed)
    return parsed


def normalise_mode(mode: Any) -> str:
    value = str(mode or "FT8").strip().upper()
    return value if value in SUPPORTED_AUTOMATION_MODES else "FT8"


def normalise_status(status: Any) -> str:
    value = str(status or "").strip()
    if not value:
        return "Unknown"
    lower = value.lower()
    status_map = {
        "atno": "ATNO",
        "new call": "New Call",
        "new band": "New Band",
        "new mode": "New Mode",
        "new band+mode": "New Band+Mode",
        "new band/mode": "New Band+Mode",
        "worked": "Worked",
        "confirmed": "Confirmed",
        "unknown": "Unknown",
    }
    return status_map.get(lower, value)


def status_is_worked(status: Any) -> bool:
    return normalise_status(status).lower() in {"worked", "confirmed"}


def status_has_prior_call_work(status: Any, dxcc_status: Any = None) -> bool:
    value = normalise_status(status).lower()
    if value in {"worked", "confirmed"}:
        return True
    if value in {"new band", "new mode", "new band+mode"}:
        dxcc_value = normalise_status(dxcc_status).lower()
        return dxcc_value not in {"atno", "unknown"}
    return False


def worked_status_flags(
    call_status: Any,
    dxcc_status: Any,
    need_reasons: Iterable[str] = (),
    state: Any = "",
    backoff_until: Any = None,
) -> dict[str, Any]:
    """Expose explicit worked/needed flags for UI and operator diagnostics."""
    call_value = normalise_status(call_status)
    dxcc_value = normalise_status(dxcc_status)
    reasons = {
        str(reason).strip().lower()
        for reason in (need_reasons or [])
        if str(reason).strip()
    }
    status_text = f"{call_value} {dxcc_value}".lower()
    return {
        "call_status": call_value,
        "dxcc_status": dxcc_value,
        "call_worked": status_has_prior_call_work(call_value, dxcc_value),
        "call_confirmed": call_value == "Confirmed",
        "dxcc_worked": dxcc_value not in {"ATNO", "Unknown"},
        "dxcc_confirmed": dxcc_value == "Confirmed" or dxcc_value.startswith("C/"),
        "new_call": call_value == "New Call" or "call" in reasons,
        "new_dxcc": dxcc_value == "ATNO" or "dxcc" in reasons,
        "new_band": "new band" in status_text or "band" in reasons,
        "new_mode": "new mode" in status_text or "mode" in reasons,
        "new_grid": "grid" in reasons,
        "new_reference": "reference" in reasons,
        "worked_before": status_has_prior_call_work(call_value, dxcc_value) or dxcc_value == "Worked",
        "backoff": bool(backoff_until),
        "state": str(state or ""),
        "need_reasons": sorted(reasons),
    }


def canonical_call_status(status: Any, dxcc_status: Any = None) -> str:
    return normalise_status(status)


def slot_aware_call_status(
    status: Any,
    needed: Mapping[str, Any] | None,
    needed_on_band: Mapping[str, Any] | None,
) -> str:
    call_status = normalise_status(status)
    needed = needed or {}
    needed_on_band = needed_on_band or {}
    if _bool(needed.get("call")) or call_status == "New Call":
        return "New Call"

    band_needed = _bool(needed_on_band.get("call"))
    mode_needed = _bool(needed_on_band.get("mode") or needed_on_band.get("call_mode"))
    if band_needed and mode_needed:
        return "New Band+Mode"
    if band_needed:
        return "New Band"
    if mode_needed:
        return "New Mode"
    return call_status


def slot_aware_dxcc_status(
    status: Any,
    needed: Mapping[str, Any] | None,
    needed_on_band: Mapping[str, Any] | None,
) -> str:
    dxcc_status = normalise_status(status)
    needed = needed or {}
    needed_on_band = needed_on_band or {}
    if _bool(needed.get("dxcc")) or dxcc_status == "ATNO":
        return "ATNO"

    band_needed = _bool(needed_on_band.get("dxcc") or needed_on_band.get("dxcc_band"))
    mode_needed = _bool(needed_on_band.get("dxcc_mode"))
    if not (band_needed or mode_needed):
        return dxcc_status

    prefix = "C" if dxcc_status == "Confirmed" or dxcc_status.startswith("C/") else "W"
    if band_needed and mode_needed:
        return f"{prefix}/New Band+Mode"
    if band_needed:
        return f"{prefix}/New Band"
    return f"{prefix}/New Mode"


def source_is_spot_hunt(source: Any) -> bool:
    return str(source or "").strip().lower() in SPOT_HUNT_SOURCES


def payload_has_dxcc_hunt_interest(payload: Mapping[str, Any]) -> bool:
    """Return true for DXCC-level needs that justify cross-band WSJT hunting."""
    dxcc_status = normalise_status(payload.get("dxcc_status") or payload.get("dxccStatus"))
    status_text = dxcc_status.lower()
    status_source = str(payload.get("status_source") or payload.get("statusSource") or "").lower()
    needed = payload.get("needed") if isinstance(payload.get("needed"), Mapping) else {}
    needed_on_band = (
        payload.get("needed_on_band")
        if isinstance(payload.get("needed_on_band"), Mapping)
        else payload.get("neededOnBand")
        if isinstance(payload.get("neededOnBand"), Mapping)
        else {}
    )
    reasons = {
        str(reason).strip().lower()
        for reason in (payload.get("need_reasons") or payload.get("needed_reasons") or [])
        if str(reason).strip()
    }
    new_slot = (
        _bool(needed_on_band.get("dxcc") or needed_on_band.get("dxcc_band") or needed_on_band.get("dxcc_mode"))
        or "new band" in status_text
        or "new mode" in status_text
    )
    wavelog_authoritative = "qso-dxcc-cache" in status_source or "wavelog" in status_source
    if wavelog_authoritative and dxcc_status == "Confirmed" and not new_slot:
        return False
    if dxcc_status == "ATNO" or dxcc_status == "Worked" or _bool(needed.get("dxcc")):
        return True
    if new_slot:
        return True
    if "dxcc" in reasons:
        return True
    return False


def _favorable_propagation(target: "DigitalTarget") -> bool:
    """Require a positive propagation assessment before leaving the current band.

    A local decode is direct evidence and does not need an external forecast.
    External spots need at least FAIR conditions; missing or marginal forecasts
    stay queued for a later refresh instead of causing speculative band hops.
    """
    if target.heard:
        return True
    if target.propagation_score is not None:
        return target.propagation_score >= FAVORABLE_PROPAGATION_SCORE
    return target.propagation_label in {"FAIR", "GOOD", "EXCELLENT"}


def target_has_dxcc_hunt_interest(target: "DigitalTarget") -> bool:
    return payload_has_dxcc_hunt_interest(target.to_dict())


def needed_reference_hunt_items(
    payload: Mapping[str, Any],
    settings: Optional["DigitalAutomationSettings"] = None,
) -> list[dict[str, str]]:
    enabled_programs = set(settings.hunter_programs) if settings else set(HUNTER_PROGRAMS)
    return [
        item
        for item in normalise_reference_items(payload)
        if canonical_reference_program(item.get("type")) in enabled_programs and reference_is_needed(item)
    ]


def payload_has_reference_hunt_interest(
    payload: Mapping[str, Any],
    settings: Optional["DigitalAutomationSettings"] = None,
) -> bool:
    if settings and not settings.reference_hunter_enabled:
        return False
    return bool(needed_reference_hunt_items(payload, settings))


def target_has_reference_hunt_interest(
    target: "DigitalTarget",
    settings: Optional["DigitalAutomationSettings"] = None,
) -> bool:
    return payload_has_reference_hunt_interest(target.to_dict(), settings)


def payload_matches_hunter_spot_filters(
    payload: Mapping[str, Any],
    settings: "DigitalAutomationSettings",
) -> bool:
    """Apply the Filters-window snapshot captured when hunter mode is armed."""
    filters = settings.hunter_spot_filters or {}

    def selected(name: str) -> set[str]:
        raw = filters.get(name) or []
        if isinstance(raw, str):
            raw = [token.strip() for token in raw.split(",") if token.strip()]
        return {str(value).strip().upper() for value in raw if str(value).strip()}

    comparisons = (
        ("bands", str(payload.get("band") or "").upper()),
        ("modes", str(payload.get("mode") or "").upper()),
        ("continents", str(payload.get("continent") or payload.get("spotter_continent") or "").upper()),
        ("cqs", str(payload.get("cq_zone") or payload.get("cq") or "").upper()),
        ("callStatuses", str(payload.get("call_status") or "").upper()),
        ("dxccStatuses", str(payload.get("dxcc_status") or "").upper()),
        ("spotSources", str(payload.get("spot_source") or payload.get("source") or "").upper()),
        ("rblModes", str(payload.get("rbl_mode_group") or "").upper()),
    )
    for name, actual in comparisons:
        choices = selected(name)
        if choices and actual not in choices:
            return False

    call_filter = str(filters.get("callsign") or "").strip().upper()
    if call_filter and call_filter not in str(payload.get("callsign") or payload.get("call") or "").upper():
        return False

    specials = selected("specials")
    if specials:
        spot_specials = {
            token.strip().upper()
            for token in re.split(r"[,;]", str(payload.get("special") or payload.get("special_tags") or ""))
            if token.strip()
        }
        reference_programs = {
            canonical_reference_program(item.get("type")) for item in normalise_reference_items(payload)
        }
        aliases = {"WWBOTA": "BUNKER", "ARLHS": "LIGHTHOUSE"}
        reference_specials = {aliases.get(program, program) for program in reference_programs}
        if not (specials & (spot_specials | reference_specials)):
            return False

    try:
        spot_score = float(payload.get("priority_score", payload.get("spot_score", 0)) or 0)
    except (TypeError, ValueError):
        spot_score = 0
    if spot_score < settings.hunter_min_spot_score:
        return False

    try:
        rbl_snr = float(payload.get("rbl_snr", payload.get("snr", 0)) or 0)
        min_rbl_snr = float(filters.get("rblMinSnr") or 0)
    except (TypeError, ValueError):
        rbl_snr = min_rbl_snr = 0
    if min_rbl_snr and rbl_snr < min_rbl_snr:
        return False
    include_worked = _bool(filters.get("workedB4Include"), False)
    exclude_worked = _bool(filters.get("workedB4Exclude"), False)
    status_text = " ".join(
        str(payload.get(key) or "").lower()
        for key in ("call_status", "dxcc_status", "worked_before_date")
    )
    is_worked = bool(payload.get("worked_before_date")) or any(
        token in status_text for token in ("worked", "confirmed")
    )
    if include_worked != exclude_worked:
        if include_worked and not is_worked:
            return False
        if exclude_worked and is_worked:
            return False
    return True


def _prior_work_should_block(
    call_status: Any,
    dxcc_status: Any,
    reasons: Iterable[str],
    settings: "DigitalAutomationSettings",
    source: Any = "",
) -> bool:
    if not status_has_prior_call_work(call_status, dxcc_status):
        return False
    if _prior_work_has_enabled_slot_need(reasons, settings):
        return False
    return True


def current_band_plan_bands(band_plan: Any, now: Optional[datetime] = None) -> list[str]:
    """Return the active UTC band list from OM0RX's HH:band,band plan text."""
    entries: list[tuple[int, list[str]]] = []
    for raw_line in str(band_plan or "").replace(";", "\n").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        hour_text, band_text = line.split(":", 1)
        try:
            hour = int(hour_text.strip())
        except ValueError:
            continue
        if not 0 <= hour <= 23:
            continue
        bands = [
            token.strip().lower()
            for token in re.split(r"[,\s]+", band_text)
            if re.match(r"^\d{1,3}m$", token.strip().lower())
        ]
        if bands:
            entries.append((hour, bands))
    if not entries:
        return []
    now = now or utc_now()
    current_hour = now.astimezone(timezone.utc).hour
    selected = min(entries, key=lambda item: (current_hour - item[0]) % 24)
    return selected[1]


def _target_freshness_seconds(mode: Any) -> int:
    return 20 if normalise_mode(mode) == "FT4" else 45


def _message_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "to_dict"):
        return dict(message.to_dict())
    if isinstance(message, Mapping):
        return dict(message)
    return {
        "message": getattr(message, "message", ""),
        "snr": getattr(message, "snr", 0),
        "dt": getattr(message, "dt", 0),
        "freq": getattr(message, "freq", 0),
        "mode": getattr(message, "mode", "FT8"),
        "timestamp": getattr(message, "timestamp", None),
    }


def _message_tokens(text: str) -> list[str]:
    return [token.strip(";,<>").upper() for token in re.split(r"\s+", normalise_decode_message_text(text).strip()) if token.strip(";,<>")]


def normalise_grid_value(value: Any) -> str:
    grid = str(value or "").strip().upper().strip("<>,;")
    if not grid or grid in NON_GRID_TOKENS:
        return ""
    return grid[:4] if GRID_RE.match(grid) else ""


def normalise_decode_message_text(message: Any) -> str:
    """Strip WSJT display-row prefixes, leaving only the FT message text."""
    text = " ".join(str(message or "").strip().split())
    if not text:
        return ""
    match = re.match(
        r"^\d{4,6}\s+[+-]?\d+\s+[+-]?\d+(?:\.\d+)?\s+\d+\s+\S+\s+(.+)$",
        text,
    )
    if match:
        return match.group(1).strip()
    return text


def extract_callsign(payload: Mapping[str, Any], mycall: str = "") -> str:
    for key in ("callsign", "call", "dxcall", "their_call"):
        call = str(payload.get(key) or "").strip().upper()
        if call:
            return call

    mycall_upper = (mycall or "").upper()
    for token in _message_tokens(str(payload.get("message") or "")):
        if token in {"CQ", "QRZ", "DE", "RR73", "73"}:
            continue
        if token == mycall_upper or GRID_RE.match(token):
            continue
        if token.startswith(("+", "-")) or token.startswith("R+") or token.startswith("R-"):
            continue
        if CALL_RE.match(token) and any(char.isdigit() for char in token):
            return token
    return ""


def target_key(call: str, band: Any, mode: Any) -> str:
    return f"{str(call or '').upper()}|{str(band or '').strip()}|{normalise_mode(mode)}"


def target_identity(call: str, band: Any, mode: Any, source: Any = "", grid: Any = "") -> str:
    raw = "|".join(
        [
            str(call or "").upper(),
            str(band or "").strip(),
            normalise_mode(mode),
            str(source or "").strip().lower(),
            str(grid or "").strip().upper()[:4],
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def command_identity(target_id: str, attempts: int = 0) -> str:
    raw = f"{target_id}|{int(attempts or 0) + 1}"
    return f"cmd-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def message_is_directed_to_mycall(message: Any, mycall: str) -> bool:
    tokens = _message_tokens(str(message or ""))
    mycall_upper = str(mycall or "").strip().upper()
    if not tokens or not mycall_upper:
        return False
    if tokens[0] == mycall_upper:
        return len(tokens) >= 2 and CALL_RE.match(tokens[1]) is not None
    if len(tokens) >= 2 and tokens[1] == mycall_upper and CALL_RE.match(tokens[0]):
        return True
    if tokens[0] == "CQ" and len(tokens) >= 3 and tokens[1] == mycall_upper:
        return CALL_RE.match(tokens[2]) is not None
    return False


def _normalise_filter_continents(value: Any) -> set[str]:
    valid = {"EU", "AF", "OC", "AS", "SA", "NA", "AN"}
    aliases = {
        "EUROPE": "EU",
        "AFRICA": "AF",
        "OCEANIA": "OC",
        "ASIA": "AS",
        "SOUTH AMERICA": "SA",
        "S. AMERICA": "SA",
        "S_AMERICA": "SA",
        "SOUTH_AMERICA": "SA",
        "NORTH AMERICA": "NA",
        "N. AMERICA": "NA",
        "N_AMERICA": "NA",
        "NORTH_AMERICA": "NA",
        "ANTARCTICA": "AN",
    }
    if isinstance(value, Mapping):
        values = [key for key, enabled in value.items() if _bool(enabled)]
    elif isinstance(value, str):
        values = value.replace(",", "\n").splitlines()
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        values = list(value)
    else:
        return set()
    continents: set[str] = set()
    for item in values:
        token = str(item or "").strip().upper()
        token = aliases.get(token, token)
        if token in valid:
            continents.add(token)
    return continents


@dataclass
class DigitalAutomationSettings:
    enabled: bool = False
    spot_hunt_enabled: bool = False
    reference_hunter_enabled: bool = False
    hunter_programs: set[str] = field(
        default_factory=lambda: {"POTA", "SOTA", "IOTA", "WWFF", "WWBOTA", "ARLHS"}
    )
    hunter_min_spot_score: int = 50
    hunter_watchdog_minutes: int = 5
    hunter_restore_watchdog_minutes: int = 2
    hunter_spot_filters: dict[str, Any] = field(default_factory=dict)
    band_hopping: bool = False
    mode_switching: bool = False
    current_band: str = ""
    allowed_modes: set[str] = field(default_factory=lambda: {"FT8", "FT4"})
    min_signal: int = -30
    dwell_seconds: int = 120
    hop_interval_seconds: int = 120
    max_attempts_per_target: int = 3
    retry_backoff_minutes: int = 10
    retry_reset_minutes: int = 60
    avoid_logged: bool = True
    require_heard_before_call: bool = True
    auto_log_to_wavelog: bool = True
    treat_73_as_cq: bool = False
    need_call: bool = True
    need_dxcc: bool = True
    need_band: bool = True
    need_mode: bool = True
    need_grid: bool = True
    need_reference: bool = False
    filter_matrix_enabled: bool = False
    filter_new_call: bool = False
    filter_new_dxcc: bool = False
    filter_new_continent: bool = False
    filter_new_grid: bool = False
    filter_new_cq_zone: bool = False
    filter_new_itu_zone: bool = False
    filter_band_call: bool = True
    filter_band_dxcc: bool = False
    filter_band_continent: bool = False
    filter_band_grid: bool = True
    filter_band_cq_zone: bool = False
    filter_band_itu_zone: bool = False
    filter_continents: set[str] = field(default_factory=lambda: {"EU", "AF", "OC", "AS", "SA", "NA", "AN"})
    filter_lotw_only: bool = False
    answer_direct_callers: bool = True
    dry_run: bool = False
    priority: str = "last"
    band_plan: str = "05:20m,17m,15m,12m,10m\n20:30m,40m,80m,160m"
    ignored_calls: set[str] = field(default_factory=set)

    @classmethod
    def from_operator_settings(cls, operator_settings: Optional[Mapping[str, Any]]) -> "DigitalAutomationSettings":
        settings = cls()
        settings.apply_operator_settings(operator_settings or {})
        return settings

    def apply_operator_settings(self, operator_settings: Mapping[str, Any]) -> None:
        automation = operator_settings.get("automation") if isinstance(operator_settings, Mapping) else None
        if not isinstance(automation, Mapping):
            automation = operator_settings

        allowed_raw = automation.get("allowedModes") or automation.get("allowed_modes") or {}
        if isinstance(allowed_raw, Mapping):
            allowed = {
                str(mode).upper()
                for mode, enabled in allowed_raw.items()
                if _bool(enabled) and str(mode).upper() in SUPPORTED_AUTOMATION_MODES
            }
            if allowed:
                self.allowed_modes = allowed
        elif isinstance(allowed_raw, Iterable) and not isinstance(allowed_raw, (str, bytes)):
            allowed = {str(mode).upper() for mode in allowed_raw if str(mode).upper() in SUPPORTED_AUTOMATION_MODES}
            if allowed:
                self.allowed_modes = allowed

        self.enabled = _bool(automation.get("enabled"), self.enabled)
        self.spot_hunt_enabled = _bool(
            automation.get("spotHuntEnabled", automation.get("spot_hunt_enabled")),
            self.spot_hunt_enabled,
        )
        self.reference_hunter_enabled = _bool(
            automation.get("referenceHunterEnabled", automation.get("reference_hunter_enabled")),
            self.reference_hunter_enabled,
        )
        programs_raw = automation.get("hunterPrograms", automation.get("hunter_programs"))
        if isinstance(programs_raw, Mapping):
            programs = {
                canonical_reference_program(program)
                for program, enabled in programs_raw.items()
                if _bool(enabled)
            }
            self.hunter_programs = {program for program in programs if program in HUNTER_PROGRAMS}
        elif isinstance(programs_raw, Iterable) and not isinstance(programs_raw, (str, bytes)):
            programs = {canonical_reference_program(program) for program in programs_raw}
            self.hunter_programs = {program for program in programs if program in HUNTER_PROGRAMS}
        self.hunter_min_spot_score = _int(
            automation.get("hunterMinSpotScore", automation.get("hunter_min_spot_score")),
            self.hunter_min_spot_score,
            low=0,
            high=100,
        )
        self.hunter_watchdog_minutes = _int(
            automation.get("hunterWatchdogMinutes", automation.get("hunter_watchdog_minutes")),
            self.hunter_watchdog_minutes,
            low=1,
            high=60,
        )
        self.hunter_restore_watchdog_minutes = _int(
            automation.get("hunterRestoreWatchdogMinutes", automation.get("hunter_restore_watchdog_minutes")),
            self.hunter_restore_watchdog_minutes,
            low=1,
            high=60,
        )
        hunter_filters = automation.get("hunterSpotFilters", automation.get("hunter_spot_filters"))
        if isinstance(hunter_filters, Mapping):
            self.hunter_spot_filters = dict(hunter_filters)
        self.band_hopping = _bool(automation.get("bandHopping", automation.get("band_hopping")), self.band_hopping)
        self.mode_switching = _bool(automation.get("modeSwitching", automation.get("mode_switching")), self.mode_switching)
        current_band = str(automation.get("currentBand", automation.get("current_band", self.current_band)) or "").strip().lower()
        if re.match(r"^\d{1,3}m$", current_band):
            self.current_band = current_band
        self.min_signal = _int(automation.get("minSignal", automation.get("min_signal")), self.min_signal, low=-40, high=30)
        self.dwell_seconds = _int(
            automation.get("spotListenSeconds", automation.get("dwell_seconds")),
            self.dwell_seconds,
            low=15,
            high=3600,
        )
        self.hop_interval_seconds = _int(
            automation.get("hopIntervalSeconds", automation.get("hop_interval_seconds")),
            self.hop_interval_seconds,
            low=30,
            high=7200,
        )
        self.max_attempts_per_target = _int(
            automation.get(
                "maxAttemptsPerTarget",
                automation.get(
                    "max_attempts_per_target",
                    automation.get(
                        "autoCallCount",
                        automation.get("autoCallLimit", automation.get("auto_call_limit")),
                    ),
                ),
            ),
            self.max_attempts_per_target,
            low=1,
            high=20,
        )
        self.retry_backoff_minutes = _int(
            automation.get("retryBackoffMinutes", automation.get("retry_backoff_minutes")),
            self.retry_backoff_minutes,
            low=1,
            high=1440,
        )
        self.retry_reset_minutes = _int(
            automation.get("retryResetMinutes", automation.get("retry_reset_minutes")),
            self.retry_reset_minutes,
            low=5,
            high=10080,
        )
        self.avoid_logged = _bool(automation.get("avoidLogged", automation.get("avoid_logged")), self.avoid_logged)
        self.require_heard_before_call = _bool(
            automation.get("requireHeardBeforeCall", automation.get("require_heard_before_call")),
            self.require_heard_before_call,
        )
        self.auto_log_to_wavelog = _bool(
            automation.get("autoLogToWavelog", automation.get("auto_log_to_wavelog")),
            self.auto_log_to_wavelog,
        )
        self.treat_73_as_cq = _bool(
            automation.get("treat73AsCQ", automation.get("treat_73_as_cq")),
            self.treat_73_as_cq,
        )
        self.need_call = _bool(automation.get("needCall", automation.get("need_call")), self.need_call)
        self.need_dxcc = _bool(automation.get("needDxcc", automation.get("need_dxcc")), self.need_dxcc)
        self.need_band = _bool(automation.get("needBand", automation.get("need_band")), self.need_band)
        self.need_mode = _bool(automation.get("needMode", automation.get("need_mode")), self.need_mode)
        self.need_grid = _bool(automation.get("needGrid", automation.get("need_grid")), self.need_grid)
        self.need_reference = _bool(
            automation.get("needReference", automation.get("need_reference")),
            self.need_reference,
        )
        self.filter_matrix_enabled = _bool(
            automation.get("filterMatrixEnabled", automation.get("filter_matrix_enabled")),
            self.filter_matrix_enabled,
        )
        filter_new = automation.get("filterNew", automation.get("filter_new"))
        if isinstance(filter_new, Mapping):
            self.filter_new_call = _bool(filter_new.get("call"), self.filter_new_call)
            self.filter_new_dxcc = _bool(filter_new.get("dxcc"), self.filter_new_dxcc)
            self.filter_new_continent = _bool(filter_new.get("continent"), self.filter_new_continent)
            self.filter_new_grid = _bool(filter_new.get("grid"), self.filter_new_grid)
            self.filter_new_cq_zone = _bool(filter_new.get("cqZone", filter_new.get("cq_zone")), self.filter_new_cq_zone)
            self.filter_new_itu_zone = _bool(filter_new.get("ituZone", filter_new.get("itu_zone")), self.filter_new_itu_zone)
        filter_band = automation.get("filterNewOnBand", automation.get("filter_new_on_band"))
        if isinstance(filter_band, Mapping):
            self.filter_band_call = _bool(filter_band.get("call"), self.filter_band_call)
            self.filter_band_dxcc = _bool(filter_band.get("dxcc"), self.filter_band_dxcc)
            self.filter_band_continent = _bool(filter_band.get("continent"), self.filter_band_continent)
            self.filter_band_grid = _bool(filter_band.get("grid"), self.filter_band_grid)
            self.filter_band_cq_zone = _bool(filter_band.get("cqZone", filter_band.get("cq_zone")), self.filter_band_cq_zone)
            self.filter_band_itu_zone = _bool(filter_band.get("ituZone", filter_band.get("itu_zone")), self.filter_band_itu_zone)
        continents = _normalise_filter_continents(
            automation.get("filterContinents", automation.get("filter_continents", automation.get("continents")))
        )
        if continents:
            self.filter_continents = continents
        self.filter_lotw_only = _bool(
            automation.get("lotwOnly", automation.get("lotw_only")),
            self.filter_lotw_only,
        )
        self.answer_direct_callers = _bool(
            automation.get("answerDirectCallers", automation.get("answer_direct_callers")),
            self.answer_direct_callers,
        )
        self.dry_run = _bool(automation.get("dryRun", automation.get("dry_run")), self.dry_run)
        self.priority = str(automation.get("priority", self.priority) or self.priority)
        self.band_plan = str(automation.get("bandPlan", automation.get("band_plan", self.band_plan)) or self.band_plan)
        ignored_raw = automation.get("ignoreList", automation.get("ignore_list", automation.get("ignoredCalls")))
        if isinstance(ignored_raw, str):
            ignored = {
                token.strip().upper()
                for token in ignored_raw.replace(",", "\n").splitlines()
                if token.strip()
            }
            self.ignored_calls = ignored
        elif isinstance(ignored_raw, Iterable) and not isinstance(ignored_raw, (str, bytes)):
            self.ignored_calls = {str(token).strip().upper() for token in ignored_raw if str(token).strip()}
        if self.reference_hunter_enabled:
            # Hunter mode owns its own safety defaults.  It listens first and
            # enables the existing backend planner so it also works headless.
            self.enabled = True
            self.spot_hunt_enabled = True
            self.band_hopping = True
            self.require_heard_before_call = True
            self.need_reference = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "spot_hunt_enabled": self.spot_hunt_enabled,
            "reference_hunter_enabled": self.reference_hunter_enabled,
            "hunter_programs": sorted(self.hunter_programs),
            "hunter_min_spot_score": self.hunter_min_spot_score,
            "hunter_watchdog_minutes": self.hunter_watchdog_minutes,
            "hunter_restore_watchdog_minutes": self.hunter_restore_watchdog_minutes,
            "hunter_spot_filters": dict(self.hunter_spot_filters),
            "band_hopping": self.band_hopping,
            "mode_switching": self.mode_switching,
            "current_band": self.current_band,
            "allowed_modes": sorted(self.allowed_modes),
            "min_signal": self.min_signal,
            "dwell_seconds": self.dwell_seconds,
            "hop_interval_seconds": self.hop_interval_seconds,
            "max_attempts_per_target": self.max_attempts_per_target,
            "retry_backoff_minutes": self.retry_backoff_minutes,
            "retry_reset_minutes": self.retry_reset_minutes,
            "avoid_logged": self.avoid_logged,
            "require_heard_before_call": self.require_heard_before_call,
            "auto_log_to_wavelog": self.auto_log_to_wavelog,
            "treat_73_as_cq": self.treat_73_as_cq,
            "need_call": self.need_call,
            "need_dxcc": self.need_dxcc,
            "need_band": self.need_band,
            "need_mode": self.need_mode,
            "need_grid": self.need_grid,
            "need_reference": self.need_reference,
            "filter_matrix_enabled": self.filter_matrix_enabled,
            "filter_new": {
                "call": self.filter_new_call,
                "dxcc": self.filter_new_dxcc,
                "continent": self.filter_new_continent,
                "grid": self.filter_new_grid,
                "cq_zone": self.filter_new_cq_zone,
                "itu_zone": self.filter_new_itu_zone,
            },
            "filter_new_on_band": {
                "call": self.filter_band_call,
                "dxcc": self.filter_band_dxcc,
                "continent": self.filter_band_continent,
                "grid": self.filter_band_grid,
                "cq_zone": self.filter_band_cq_zone,
                "itu_zone": self.filter_band_itu_zone,
            },
            "filter_continents": sorted(self.filter_continents),
            "filter_lotw_only": self.filter_lotw_only,
            "answer_direct_callers": self.answer_direct_callers,
            "dry_run": self.dry_run,
            "priority": self.priority,
            "band_plan": self.band_plan,
            "ignored_calls": sorted(self.ignored_calls),
        }


@dataclass
class DigitalTarget:
    key: str
    call: str
    target_id: str = ""
    command_id: str = ""
    band: str = ""
    mode: str = "FT8"
    source: str = "decoded"
    message: str = ""
    grid: str = ""
    country: str = ""
    dxcc: Optional[int] = None
    continent: str = ""
    cq_zone: str = ""
    itu_zone: str = ""
    call_status: str = "Unknown"
    dxcc_status: str = "Unknown"
    status_source: str = ""
    need_reasons: set[str] = field(default_factory=set)
    reference_items: list[dict[str, str]] = field(default_factory=list)
    score: int = 0
    spot_score: int = 0
    score_reason: str = ""
    score_trace: dict[str, Any] = field(default_factory=dict)
    snr: Optional[float] = None
    audio_offset: Optional[int] = None
    dial_frequency: Optional[float] = None
    propagation_score: Optional[float] = None
    propagation_label: str = ""
    propagation_confidence: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    first_heard_at: Optional[datetime] = None
    last_heard_at: Optional[datetime] = None
    heard_slot_start_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    backoff_until: Optional[datetime] = None
    attempts: int = 0
    state: str = "queued"
    lifecycle: str = "queued"
    active_state: str = "idle"
    reason: str = ""
    skip_reason: str = ""
    completion_reason: str = ""
    heard: bool = False
    direct_caller: bool = False
    last_command_at: Optional[datetime] = None
    command_ack_at: Optional[datetime] = None
    origin_band: str = ""
    origin_mode: str = ""
    origin_dial_frequency: Optional[float] = None
    return_command_at: Optional[datetime] = None
    campaign_started_at: Optional[datetime] = None
    campaign_expires_at: Optional[datetime] = None
    campaign_count: int = 0

    def is_backed_off(self, now: Optional[datetime] = None) -> bool:
        return bool(self.backoff_until and self.backoff_until > (now or utc_now()))

    def sync_state(self, state: Optional[str] = None, *, active_state: Optional[str] = None) -> None:
        if state:
            self.state = state
            if state in TARGET_LIFECYCLE_STATES:
                self.lifecycle = state
            elif state == "done":
                self.lifecycle = "completed"
            elif state == "calling":
                self.lifecycle = "active"
            elif state == "heard":
                self.lifecycle = "queued"
        if active_state:
            self.active_state = active_state if active_state in ACTIVE_QSO_STATES else self.active_state

    def to_dict(self) -> dict[str, Any]:
        worked_flags = worked_status_flags(
            self.call_status,
            self.dxcc_status,
            self.need_reasons,
            self.state,
            self.backoff_until,
        )
        return {
            "key": self.key,
            "call": self.call,
            "target_id": self.target_id,
            "command_id": self.command_id,
            "band": self.band,
            "mode": self.mode,
            "source": self.source,
            "message": self.message,
            "grid": self.grid,
            "country": self.country,
            "dxcc": self.dxcc,
            "continent": self.continent,
            "cq_zone": self.cq_zone,
            "itu_zone": self.itu_zone,
            "call_status": self.call_status,
            "dxcc_status": self.dxcc_status,
            "status_source": self.status_source,
            "need_reasons": sorted(self.need_reasons),
            "reference_items": [dict(item) for item in self.reference_items],
            "references": [dict(item) for item in self.reference_items],
            "score": self.score,
            "spot_score": self.spot_score,
            "score_reason": self.score_reason,
            "score_trace": dict(self.score_trace),
            "snr": self.snr,
            "audio_offset": self.audio_offset,
            "dial_frequency": self.dial_frequency,
            "propagation_score": self.propagation_score,
            "propagation_label": self.propagation_label,
            "propagation_confidence": self.propagation_confidence,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "first_heard_at": _iso(self.first_heard_at),
            "last_heard_at": _iso(self.last_heard_at),
            "heard_slot_start_at": _iso(self.heard_slot_start_at),
            "last_attempt_at": _iso(self.last_attempt_at),
            "backoff_until": _iso(self.backoff_until),
            "attempts": self.attempts,
            "state": self.state,
            "lifecycle": self.lifecycle,
            "active_state": self.active_state,
            "reason": self.reason,
            "skip_reason": self.skip_reason,
            "completion_reason": self.completion_reason,
            "heard": self.heard,
            "direct_caller": self.direct_caller,
            "last_command_at": _iso(self.last_command_at),
            "command_ack_at": _iso(self.command_ack_at),
            "origin_band": self.origin_band,
            "origin_mode": self.origin_mode,
            "origin_dial_frequency": self.origin_dial_frequency,
            "return_command_at": _iso(self.return_command_at),
            "campaign_started_at": _iso(self.campaign_started_at),
            "campaign_expires_at": _iso(self.campaign_expires_at),
            "campaign_count": self.campaign_count,
            "worked_flags": worked_flags,
            "classification_breakdown": worked_flags,
        }


class DigitalAutomationController:
    """Own target selection and retry state for the built-in Digital client."""

    def __init__(
        self,
        *,
        mycall: str = "OM0RX",
        settings: Optional[DigitalAutomationSettings] = None,
        max_targets: int = 250,
        qso_status_store: Any = None,
        cty_resolver: Any = None,
        target_store: Any = None,
    ) -> None:
        self.mycall = str(mycall or "OM0RX").upper()
        self.settings = settings or DigitalAutomationSettings()
        self.max_targets = max_targets
        self.qso_status_store = qso_status_store
        self.cty_resolver = cty_resolver
        self.target_store = target_store
        self.persistence_loaded_count = 0
        self.persistence_error: Optional[str] = None
        self.targets: dict[str, DigitalTarget] = {}
        self.active_target_key: Optional[str] = None
        self.listen_target_key: Optional[str] = None
        self.pending_return_command: Optional[dict[str, Any]] = None
        self.last_decision: dict[str, Any] = {"decision": "idle", "reason": "controller initialised"}
        self.decision_log: list[dict[str, Any]] = []
        self.active_qso_state = "idle"
        self._load_persisted_targets()

    def _set_decision(self, decision: Mapping[str, Any]) -> dict[str, Any]:
        entry = {
            "timestamp": utc_now().isoformat(),
            "active_target": self.active_target_key,
            "active_qso_state": self.active_qso_state,
            **dict(decision),
        }
        self.last_decision = entry
        self.decision_log.append(entry)
        if len(self.decision_log) > DECISION_LOG_LIMIT:
            self.decision_log = self.decision_log[-DECISION_LOG_LIMIT:]
        return entry

    def _target_eligibility(
        self,
        target: DigitalTarget,
        now: Optional[datetime] = None,
        *,
        cq_only: bool = False,
        auto_call_start_only: bool = False,
    ) -> dict[str, Any]:
        now = now or utc_now()
        reasons: list[str] = []
        eligible = True

        def reject(reason: str) -> None:
            nonlocal eligible
            eligible = False
            reasons.append(reason)

        if target.state in {"done", "skipped", "expired"}:
            reject(target.state)
        if target.is_backed_off(now):
            reject("backoff")
        if (
            target.heard
            and target.last_heard_at
            and (now - target.last_heard_at).total_seconds() > _target_freshness_seconds(target.mode)
        ):
            reject("heard-target-too-old")
        if (
            not target.direct_caller
            and self.settings.avoid_logged
            and _prior_work_should_block(
                target.call_status,
                target.dxcc_status,
                target.need_reasons,
                self.settings,
                target.source,
            )
        ):
            reject("already-worked-call")
        if (
            auto_call_start_only
            and target.source in {"decoded", "wsjtx-decode-status"}
            and not target.direct_caller
            and not _is_auto_call_start_message(target.message, treat_73_as_cq=self.settings.treat_73_as_cq)
        ):
            reject("not-auto-call-start-message")
        if (
            cq_only
            and target.source in {"decoded", "wsjtx-decode-status"}
            and not target.direct_caller
            and not _is_auto_call_start_message(target.message, treat_73_as_cq=self.settings.treat_73_as_cq)
        ):
            reject("cq-only-non-cq")
        if target.is_backed_off(now):
            reject("backoff")
        if (
            target.last_attempt_at
            and (now - target.last_attempt_at).total_seconds() < self.settings.dwell_seconds
        ):
            reject("dwell")
        if self.settings.require_heard_before_call and not target.heard:
            reject("require-heard")
        if target.score <= 0 and self.settings.avoid_logged:
            reject("worked-or-unneeded")
        if target.score > 0 and not target.direct_caller and not payload_matches_need_filters(target.to_dict(), self.settings):
            reject("not-needed-by-filter")

        return {
            "eligible": eligible,
            "reasons": list(dict.fromkeys(reasons)),
            "call": target.call,
            "band": target.band,
            "mode": target.mode,
            "state": target.state,
            "score": target.score,
            "score_reason": target.score_reason,
            "score_trace": dict(target.score_trace),
            "heard": target.heard,
            "direct_caller": target.direct_caller,
            "source": target.source,
            "attempts": target.attempts,
            "worked_flags": worked_status_flags(
                target.call_status,
                target.dxcc_status,
                target.need_reasons,
                target.state,
                target.backoff_until,
            ),
        }

    def _eligibility_summary(
        self,
        now: Optional[datetime] = None,
        *,
        cq_only: bool = False,
        auto_call_start_only: bool = False,
    ) -> dict[str, Any]:
        now = now or utc_now()
        rejected: dict[str, int] = {}
        examples: dict[str, list[dict[str, Any]]] = {}
        eligible = 0
        for target in self.targets.values():
            item = self._target_eligibility(
                target,
                now,
                cq_only=cq_only,
                auto_call_start_only=auto_call_start_only,
            )
            if item["eligible"]:
                eligible += 1
                continue
            for reason in item["reasons"] or ["unknown"]:
                rejected[reason] = rejected.get(reason, 0) + 1
                bucket = examples.setdefault(reason, [])
                if len(bucket) < 3:
                    bucket.append({
                        "call": target.call,
                        "band": target.band,
                        "mode": target.mode,
                        "score": target.score,
                        "state": target.state,
                    })
        return {
            "eligible": eligible,
            "rejected": rejected,
            "examples": examples,
        }

    def _active_target_can_yield_to_direct_reply(self, active: Optional[DigitalTarget]) -> bool:
        if not active or active.direct_caller:
            return False
        if self.active_qso_state in {"idle", "completed", "logged", "failed", "aborted"}:
            return True
        one_sided_states = {"candidate_selected", "command_sent", "waiting_for_tx", "calling"}
        return self.active_qso_state in one_sided_states and active.active_state in one_sided_states

    def _reason_panel(self, active: Optional[DigitalTarget], listening: Optional[DigitalTarget], now: datetime) -> dict[str, Any]:
        target = active or listening
        target_dict = target.to_dict() if target else None
        panel = {
            "state": self.active_qso_state,
            "target": target_dict,
            "active_target_key": self.active_target_key,
            "listen_target_key": self.listen_target_key,
            "last_decision": self.last_decision,
            "last_cancel_or_abort_reason": self._last_cancel_or_abort_reason(),
            "eligibility": self._eligibility_summary(now, cq_only=True, auto_call_start_only=True),
            "why_not_tx": self._why_not_tx_rows(now, active=active),
            "priority_trace": self._priority_trace(now),
        }
        if target:
            panel["current_target_eligibility"] = self._target_eligibility(
                target,
                now,
                cq_only=True,
                auto_call_start_only=True,
            )
            panel["why_selected"] = target.reason or self._target_reason(target)
            if target.state in {"calling", "selected", "heard"}:
                panel["why_not_tx_now"] = "active-qso-owned-by-backend" if active else ""
            elif listening:
                panel["why_not_tx_now"] = "listen-only-spot-probe"
            else:
                panel["why_not_tx_now"] = panel["current_target_eligibility"].get("reasons") or ""
        else:
            panel["why_selected"] = ""
            panel["why_not_tx_now"] = self.last_decision.get("reason", "idle")
        return panel

    def _why_not_tx_rows(
        self,
        now: datetime,
        *,
        active: Optional[DigitalTarget],
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for target in self._ordered_targets()[: max(1, limit)]:
            eligibility = self._target_eligibility(
                target,
                now,
                cq_only=True,
                auto_call_start_only=True,
            )
            reason_text = self._why_not_tx_text(target, eligibility, active=active)
            rows.append({
                "call": target.call,
                "band": target.band,
                "mode": target.mode,
                "source": target.source,
                "state": target.state,
                "action": self._why_not_tx_action(target, eligibility, active=active),
                "reason": reason_text,
                "reason_codes": eligibility.get("reasons") or [],
                "score": target.score,
                "score_reason": target.score_reason,
                "score_trace": dict(target.score_trace),
                "call_status": target.call_status,
                "dxcc_status": target.dxcc_status,
                "heard": target.heard,
                "direct_caller": target.direct_caller,
                "need_reasons": sorted(target.need_reasons),
                "updated_at": _iso(target.updated_at),
                "last_heard_at": _iso(target.last_heard_at),
            })
        seen = {(row.get("call"), row.get("band"), row.get("mode"), row.get("reason")) for row in rows}
        for entry in reversed(self.decision_log[-limit:]):
            if len(rows) >= limit:
                break
            if str(entry.get("decision") or "") not in {"skip", "hold", "idle", "selected", "expired"}:
                continue
            row = self._decision_why_not_tx_row(entry)
            key = (row.get("call"), row.get("band"), row.get("mode"), row.get("reason"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
        return rows

    def _decision_why_not_tx_row(self, entry: Mapping[str, Any]) -> dict[str, Any]:
        decision = str(entry.get("decision") or "")
        reason = str(entry.get("reason") or "")
        blockers = [str(item) for item in (entry.get("blockers") or []) if str(item)]
        if decision == "selected":
            text = f"selected: {entry.get('score_reason') or reason or 'eligible'}"
            action = "selected"
        elif reason == "active-qso-in-progress":
            text = f"blocked: active QSO with {entry.get('call') or '-'}"
            action = "blocked"
        elif reason == "not-needed-by-filter":
            text = f"blocked: {blockers[0]}" if blockers else "blocked: not needed by filters"
            action = "blocked"
        elif reason == "require-heard":
            text = "waiting: target not heard"
            action = "waiting"
        elif decision == "idle":
            text = f"waiting: {reason or 'idle'}"
            action = "waiting"
        elif decision == "expired":
            text = f"blocked: {reason or 'expired'}"
            action = "blocked"
        else:
            text = f"blocked: {reason or decision or 'unknown'}"
            action = "blocked"
        return {
            "call": str(entry.get("call") or entry.get("decision") or "-"),
            "band": str(entry.get("band") or ""),
            "mode": str(entry.get("mode") or ""),
            "source": str(entry.get("source") or "decision-log"),
            "state": str(entry.get("state") or entry.get("active_qso_state") or ""),
            "action": action,
            "reason": text,
            "reason_codes": [reason] if reason else [],
            "score": _int(entry.get("score"), 0),
            "score_reason": str(entry.get("score_reason") or ""),
            "score_trace": dict(entry.get("score_trace") or {}),
            "call_status": str(entry.get("call_status") or ""),
            "dxcc_status": str(entry.get("dxcc_status") or ""),
            "heard": _bool(entry.get("heard"), False),
            "direct_caller": _bool(entry.get("direct_caller"), False),
            "need_reasons": list(entry.get("need_reasons") or []),
            "updated_at": str(entry.get("timestamp") or ""),
            "last_heard_at": "",
        }

    def _priority_trace(self, now: Optional[datetime] = None, limit: int = 40) -> list[dict[str, Any]]:
        now = now or utc_now()
        rows: list[dict[str, Any]] = []
        for target in self.targets.values():
            eligibility = self._target_eligibility(
                target,
                now,
                cq_only=True,
                auto_call_start_only=True,
            )
            rows.append({
                "call": target.call,
                "band": target.band,
                "mode": target.mode,
                "score": target.score,
                "score_reason": target.score_reason,
                "score_trace": dict(target.score_trace),
                "eligible": bool(eligibility.get("eligible")),
                "reasons": eligibility.get("reasons") or [],
                "state": target.state,
                "source": target.source,
                "heard": target.heard,
                "direct_caller": target.direct_caller,
                "updated_at": _iso(target.updated_at),
            })
        rows.sort(
            key=lambda row: (
                1 if row.get("direct_caller") else 0,
                1 if row.get("eligible") else 0,
                _int(row.get("score"), 0),
                str(row.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return rows[: max(1, limit)]

    def _why_not_tx_action(
        self,
        target: DigitalTarget,
        eligibility: Mapping[str, Any],
        *,
        active: Optional[DigitalTarget],
    ) -> str:
        if active and active.key == target.key:
            return "active"
        if active and active.key != target.key:
            return "blocked"
        if target.direct_caller and eligibility.get("eligible"):
            return "selected"
        if eligibility.get("eligible"):
            return "selected" if target.state == "selected" else "candidate"
        reasons = set(eligibility.get("reasons") or [])
        if "require-heard" in reasons:
            return "waiting"
        return "blocked"

    def _why_not_tx_text(
        self,
        target: DigitalTarget,
        eligibility: Mapping[str, Any],
        *,
        active: Optional[DigitalTarget],
    ) -> str:
        if active and active.key != target.key:
            return f"blocked: active QSO with {active.call}"
        if active and active.key == target.key:
            return f"active: {self.active_qso_state}"
        if target.direct_caller and eligibility.get("eligible"):
            return "selected: reply-to-us"
        if eligibility.get("eligible"):
            if target.score_reason:
                return f"selected: {target.score_reason}"
            return "selected: eligible"

        reasons = list(eligibility.get("reasons") or [])
        if not reasons:
            return "blocked: unknown"
        if "require-heard" in reasons:
            return "waiting: target not heard"
        if "mode-disabled" in reasons:
            return "blocked: mode disabled"
        if "outside-active-band-plan" in reasons:
            return "blocked: outside active band plan"
        if "not-auto-call-start-message" in reasons:
            return "blocked: not CQ/73 start message"
        if "cq-only-non-cq" in reasons:
            return "blocked: CQ-only filter"
        if "dwell" in reasons:
            return "waiting: dwell timer"
        if "backoff" in reasons:
            return "waiting: retry backoff"
        if "already-worked-call" in reasons or "worked-or-unneeded" in reasons:
            if normalise_status(target.dxcc_status) == "Confirmed":
                return "blocked: DXCC already confirmed"
            return "blocked: already worked"
        if "not-needed-by-filter" in reasons:
            blockers = payload_need_filter_blockers(target.to_dict(), self.settings)
            return f"blocked: {blockers[0]}" if blockers else "blocked: not needed by filters"
        return f"blocked: {reasons[0]}"

    def _last_cancel_or_abort_reason(self) -> str:
        for entry in reversed(self.decision_log):
            reason = str(entry.get("reason") or "")
            decision = str(entry.get("decision") or "")
            if "abort" in reason or "cancel" in reason or decision in {"abandoned", "skipped"}:
                return reason or decision
        return ""

    def _event_timeline(self, limit: int = 20) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for entry in self.decision_log[-max(1, limit):]:
            events.append({
                "timestamp": entry.get("timestamp"),
                "event": entry.get("decision"),
                "reason": entry.get("reason"),
                "state": entry.get("state") or entry.get("active_qso_state"),
                "call": entry.get("call"),
                "band": entry.get("band"),
                "mode": entry.get("mode"),
                "score": entry.get("score"),
                "attempts": entry.get("attempts"),
                "target_key": entry.get("key") or entry.get("active_target"),
                "rejected": entry.get("rejected"),
                "rejected_examples": entry.get("rejected_examples"),
                "candidate_count": entry.get("candidate_count"),
                "candidate_order": entry.get("candidate_order"),
            })
        return events

    def transition_active_qso(
        self,
        state: str,
        *,
        reason: str = "",
        target: Optional[DigitalTarget] = None,
    ) -> str:
        if state not in ACTIVE_QSO_STATES:
            state = "failed"
            reason = reason or "invalid-active-qso-state"
        self.active_qso_state = state
        if target:
            target.sync_state(active_state=state)
            target.updated_at = utc_now()
            self._persist_target(target)
        self._set_decision({
            "decision": "active-qso-state",
            "reason": reason or state,
            "state": state,
            "call": target.call if target else None,
            "key": target.key if target else None,
        })
        return state

    def set_status_sources(self, *, qso_status_store: Any = None, cty_resolver: Any = None) -> None:
        """Attach fast local worked-status and CTY lookup sources."""
        self.qso_status_store = qso_status_store
        self.cty_resolver = cty_resolver

    def set_target_store(self, target_store: Any = None, *, reload: bool = True) -> None:
        """Attach optional persistence for target queue state."""
        self.target_store = target_store
        self.persistence_error = None
        if reload:
            self._load_persisted_targets()

    def apply_operator_settings(self, operator_settings: Optional[Mapping[str, Any]]) -> None:
        self.settings.apply_operator_settings(operator_settings or {})
        self._set_decision({"decision": "settings-updated", "settings": self.settings.to_dict()})

    def update_mycall(self, mycall: str) -> None:
        if mycall:
            self.mycall = mycall.upper()

    def ingest_decoded(self, message: Any) -> Optional[DigitalTarget]:
        payload = _message_dict(message)
        payload.setdefault("source", "decoded")
        return self._upsert_target(payload, heard=True)

    def ingest_spot(self, spot: Mapping[str, Any]) -> Optional[DigitalTarget]:
        payload = dict(spot)
        payload.setdefault("source", "spot")
        return self._upsert_target(payload, heard=False)

    def ingest_target(self, payload: Mapping[str, Any]) -> Optional[DigitalTarget]:
        incoming = dict(payload)
        source = str(incoming.get("source", "")).lower()
        heard = _bool(incoming.get("heard"), source in {"decoded", "wsjtx-decode-status"})
        return self._upsert_target(incoming, heard=heard)

    def _upsert_target(self, payload: Mapping[str, Any], *, heard: bool) -> Optional[DigitalTarget]:
        payload = dict(payload)
        if "message" in payload:
            payload["message"] = normalise_decode_message_text(payload.get("message"))
        mode = normalise_mode(payload.get("mode"))
        if mode not in self.settings.allowed_modes:
            self._set_decision({
                "decision": "skip",
                "reason": "mode-disabled",
                "mode": mode,
            })
            return None

        call = extract_callsign(payload, self.mycall)
        if not call or call == self.mycall:
            self._set_decision({"decision": "skip", "reason": "no-workable-callsign"})
            return None
        if call in self.settings.ignored_calls:
            self._set_decision({
                "decision": "skip",
                "reason": "ignored-call",
                "call": call,
            })
            return None

        snr = _float(payload.get("snr"))
        if heard and snr is not None and snr < self.settings.min_signal:
            self._set_decision({
                "decision": "skip",
                "reason": "below-min-signal",
                "call": call,
                "snr": snr,
                "min_signal": self.settings.min_signal,
            })
            return None

        band = str(payload.get("band") or "").strip()
        payload = self._enrich_payload_from_local_status(payload, call=call, band=band, mode=mode)
        key = target_key(call, band, mode)
        existing_target = self.targets.get(key)
        if existing_target and not normalise_reference_items(payload) and existing_target.reference_items:
            # A WSJT-Z decode normally contains no award metadata.  Carry the
            # reference from the spot probe into the decoded target/QSO.
            payload["reference_items"] = [dict(item) for item in existing_target.reference_items]
        score_info = score_payload_trace(payload)
        score = _int(score_info.get("score"), 0)
        raw_call_status = normalise_status(payload.get("call_status") or payload.get("callStatus"))
        dxcc_status = normalise_status(payload.get("dxcc_status") or payload.get("dxccStatus"))
        call_status = canonical_call_status(raw_call_status, dxcc_status)
        need_reasons = payload_need_reasons(payload)
        source = str(payload.get("source") or "decoded").strip().lower()
        prior_work_source = (
            existing_target.source
            if existing_target and source in {"decoded", "wsjtx-decode-status"}
            else source
        )
        message = str(payload.get("message") or "")
        direct_caller = message_is_directed_to_mycall(message, self.mycall)
        reference_hunt_interest = (
            payload_has_reference_hunt_interest(payload, self.settings)
            and (
                (existing_target is not None and source in {"decoded", "wsjtx-decode-status"})
                or payload_matches_hunter_spot_filters(payload, self.settings)
            )
        )
        if direct_caller and self.settings.answer_direct_callers:
            source = "incoming"
            if score < DIRECT_CALLER_SCORE:
                score_info = {
                    "score": DIRECT_CALLER_SCORE,
                    "reason": "reply-to-us",
                    "label": f"reply-to-us={DIRECT_CALLER_SCORE}",
                    "base": score_info,
                }
            score = max(score, DIRECT_CALLER_SCORE)
        if (
            source in {"decoded", "wsjtx-decode-status"}
            and message
            and not direct_caller
            and not _is_auto_call_start_message(message, treat_73_as_cq=self.settings.treat_73_as_cq)
        ):
            self._set_decision({
                "decision": "skip",
                "reason": "not-auto-call-start-message",
                "call": call,
                "band": band,
                "mode": mode,
                "message": message,
            })
            return None
        if (
            not direct_caller
            and source_is_spot_hunt(source)
            and not payload_has_dxcc_hunt_interest({**payload, "need_reasons": list(need_reasons)})
            and not reference_hunt_interest
        ):
            self._set_decision({
                "decision": "skip",
                "reason": (
                    "spot-not-hunt-interest"
                    if self.settings.reference_hunter_enabled
                    else "spot-not-dxcc-hunt-interest"
                ),
                "call": call,
                "band": band,
                "mode": mode,
                "call_status": call_status,
                "dxcc_status": dxcc_status,
                "source": source,
            })
            return None
        if (
            not direct_caller
            and self.settings.avoid_logged
            and _prior_work_should_block(call_status, dxcc_status, need_reasons, self.settings, prior_work_source)
        ):
            target = existing_target
            if target and target.state not in {"selected", "calling"}:
                target.sync_state("skipped")
                target.reason = "already-worked-call"
                target.skip_reason = "already-worked-call"
                target.updated_at = utc_now()
                self._persist_target(target)
            self._set_decision({
                "decision": "skip",
                "reason": "already-worked-call",
                "call": call,
                "band": band,
                "mode": mode,
                "call_status": call_status,
                "dxcc_status": dxcc_status,
            })
            return None
        if not direct_caller and score > 0 and not payload_matches_need_filters(payload, self.settings):
            blockers = payload_need_filter_blockers(payload, self.settings)
            target = self.targets.get(key)
            if target and target.state not in {"selected", "calling"}:
                target.sync_state("skipped")
                target.reason = "not-needed-by-filter"
                target.skip_reason = "not-needed-by-filter"
                target.updated_at = utc_now()
                self._persist_target(target)
            self._set_decision({
                "decision": "skip",
                "reason": "not-needed-by-filter",
                "call": call,
                "band": band,
                "mode": mode,
                "call_status": call_status,
                "dxcc_status": dxcc_status,
                "blockers": blockers,
                "score": score,
                "score_reason": str(score_info.get("reason") or ""),
                "score_trace": dict(score_info),
                "source": source,
            })
            return None

        now = utc_now()
        target = existing_target
        if not target:
            target = DigitalTarget(key=key, call=call, band=band, mode=mode)
            self.targets[key] = target
        grid = normalise_grid_value(payload.get("grid") or payload.get("gridsquare") or "")
        if not target.target_id:
            target.target_id = target_identity(call, band, mode, source, grid)
        # Once WSJT-Z actually decodes a spotted station, local RF evidence owns
        # the target. This also prevents the hopping schedule from suppressing a
        # priority DXCC that is demonstrably present on the current band.
        target.source = source or target.source or "decoded"
        if message:
            target.message = message
        target.grid = grid or normalise_grid_value(target.grid)
        target.country = str(payload.get("country") or payload.get("dxcc_name") or target.country or "")
        target.dxcc = _optional_int(payload.get("dxcc"), target.dxcc)
        target.continent = str(payload.get("continent") or target.continent or "")
        target.cq_zone = str(payload.get("cq_zone") or payload.get("cq") or target.cq_zone or "")
        target.itu_zone = str(payload.get("itu_zone") or payload.get("itu") or target.itu_zone or "")
        target.call_status = call_status
        target.dxcc_status = dxcc_status
        target.status_source = str(payload.get("status_source") or payload.get("statusSource") or target.status_source or "")
        target.reference_items = normalise_reference_items(payload) or target.reference_items
        target.need_reasons = need_reasons
        if direct_caller:
            target.need_reasons.add("direct")
        else:
            target.need_reasons.discard("direct")
        if target.direct_caller and not direct_caller:
            target.score = score
            target.score_reason = str(score_info.get("reason") or "")
            target.score_trace = dict(score_info)
        elif score >= target.score or not target.score_reason:
            target.score_reason = str(score_info.get("reason") or "")
            target.score_trace = dict(score_info)
        target.score = score if target.direct_caller and not direct_caller else max(target.score, score)
        target.spot_score = _int(
            payload.get("priority_score", payload.get("spot_score", target.spot_score)),
            target.spot_score,
            low=0,
            high=100,
        )
        target.snr = snr if snr is not None else target.snr
        target.audio_offset = _int(payload.get("freq", payload.get("audio_offset")), target.audio_offset or 0) or None
        target.dial_frequency = _float(payload.get("base_frequency", payload.get("frequency_mhz", payload.get("frequency"))))
        propagation = payload.get("propagation") if isinstance(payload.get("propagation"), Mapping) else {}
        target.propagation_score = _float(
            propagation.get("score", payload.get("propagation_score", target.propagation_score))
        )
        target.propagation_label = str(
            propagation.get("label", payload.get("propagation_label", target.propagation_label)) or ""
        ).strip().upper()
        target.propagation_confidence = str(
            propagation.get("confidence", payload.get("propagation_confidence", target.propagation_confidence)) or ""
        ).strip().lower()
        target.updated_at = now
        if heard:
            heard_slot = _datetime(payload.get("slot_start_utc") or payload.get("timestamp"))
            target.heard = True
            target.first_heard_at = target.first_heard_at or now
            target.last_heard_at = now
            if heard_slot:
                target.heard_slot_start_at = heard_slot
            if target.state in {"listening", "queued", "expired"} or (
                target.state == "backoff" and not target.is_backed_off(now)
            ):
                target.sync_state("heard")
                target.backoff_until = None
            if self.listen_target_key == target.key:
                self.listen_target_key = None
        elif target.state == "expired" or (target.state == "backoff" and not target.is_backed_off(now)):
            target.backoff_until = None
            target.completion_reason = ""
            target.sync_state("listening" if self.settings.require_heard_before_call else "queued", active_state="idle")
        elif target.state == "queued":
            target.sync_state("listening" if self.settings.require_heard_before_call else "queued")
        target.direct_caller = bool(direct_caller)
        target.reason = self._target_reason(target)

        self._trim_targets()
        self._persist_target(target)
        self._set_decision({
            "decision": "queued",
            "call": call,
            "band": band,
            "mode": mode,
            "score": target.score,
            "score_reason": target.score_reason,
            "score_trace": dict(target.score_trace),
            "state": target.state,
            "reason": target.reason,
            "source": target.source,
            "direct_caller": target.direct_caller,
            "need_reasons": sorted(target.need_reasons),
            "queue_position": self._queue_position(target.key),
            "attempts": target.attempts,
        })
        return target

    def _enrich_payload_from_local_status(
        self,
        payload: dict[str, Any],
        *,
        call: str,
        band: str,
        mode: str,
    ) -> dict[str, Any]:
        """Apply fast local CTY/QSO status cache data before target ranking."""
        enriched = dict(payload)
        status_sources: list[str] = []

        if self.cty_resolver and call:
            try:
                cty_info = self.cty_resolver.lookup(call) or {}
            except Exception as exc:
                logger.debug("Digital CTY lookup failed for %s: %s", call, exc)
                cty_info = {}
            if cty_info:
                enriched.setdefault("country", cty_info.get("entity") or cty_info.get("country") or "")
                enriched.setdefault("dxcc", cty_info.get("dxcc"))
                enriched.setdefault("continent", cty_info.get("continent") or cty_info.get("cont") or "")
                enriched.setdefault("cq_zone", cty_info.get("cq") or cty_info.get("cq_zone") or "")
                enriched.setdefault("itu_zone", cty_info.get("itu") or cty_info.get("itu_zone") or "")
                status_sources.append("cty")

        store = self.qso_status_store
        if not store:
            needed = enriched.get("needed") if isinstance(enriched.get("needed"), Mapping) else {}
            needed_on_band = (
                enriched.get("needed_on_band")
                if isinstance(enriched.get("needed_on_band"), Mapping)
                else enriched.get("neededOnBand")
                if isinstance(enriched.get("neededOnBand"), Mapping)
                else {}
            )
            enriched["call_status"] = slot_aware_call_status(enriched.get("call_status"), needed, needed_on_band)
            enriched["dxcc_status"] = slot_aware_dxcc_status(enriched.get("dxcc_status"), needed, needed_on_band)
            if status_sources and not enriched.get("status_source"):
                enriched["status_source"] = ",".join(status_sources)
            return enriched

        try:
            if hasattr(store, "call_flags"):
                flags = store.call_flags(call, band, mode)
                if flags is not None:
                    worked, _confirmed, new_band, new_mode, bandmode_confirmed = flags
                    needed = dict(enriched.get("needed") or {})
                    needed_on_band = dict(enriched.get("needed_on_band") or enriched.get("neededOnBand") or {})
                    needed["call"] = not worked
                    needed_on_band["call"] = bool(new_band)
                    needed_on_band["mode"] = bool(new_mode)
                    enriched["needed"] = needed
                    enriched["needed_on_band"] = needed_on_band
                    enriched["call_status"] = classify_call_status(
                        worked,
                        new_band,
                        new_mode,
                        bandmode_confirmed,
                    )
                    status_sources.append("qso-call-cache")

            dxcc = _optional_int(enriched.get("dxcc"), None)
            if dxcc is not None and hasattr(store, "dxcc_overall"):
                overall = store.dxcc_overall(dxcc)
                bandmode = store.dxcc_bandmode_flags(dxcc, band, mode) if hasattr(store, "dxcc_bandmode_flags") else None
                if overall is not None and bandmode is not None:
                    worked, confirmed = overall
                    new_band, new_mode, bandmode_confirmed = bandmode
                    needed = dict(enriched.get("needed") or {})
                    needed_on_band = dict(enriched.get("needed_on_band") or enriched.get("neededOnBand") or {})
                    needed["dxcc"] = not worked
                    needed_on_band["dxcc"] = bool(new_band)
                    needed_on_band["dxcc_mode"] = bool(new_mode)
                    enriched["needed"] = needed
                    enriched["needed_on_band"] = needed_on_band
                    display = classify_dxcc_status(
                        worked,
                        confirmed,
                        new_band,
                        new_mode,
                        bandmode_confirmed,
                    )
                    enriched["dxcc_status"] = display.status
                    if display.tag:
                        enriched["dxcc_tag"] = display.tag
                    status_sources.append("qso-dxcc-cache")

            grid = normalise_grid_value(enriched.get("grid") or enriched.get("gridsquare") or "")
            if grid and hasattr(store, "grid_flags"):
                grid_flags = store.grid_flags(grid, band, mode)
                if grid_flags is not None:
                    new_grid, new_grid_band, new_grid_mode = grid_flags
                    needed = dict(enriched.get("needed") or {})
                    needed_on_band = dict(enriched.get("needed_on_band") or enriched.get("neededOnBand") or {})
                    needed["grid"] = bool(needed.get("grid") or new_grid)
                    needed_on_band["grid"] = bool(
                        needed_on_band.get("grid") or new_grid_band or new_grid_mode
                    )
                    enriched["needed"] = needed
                    enriched["needed_on_band"] = needed_on_band
                    status_sources.append("qso-grid-cache")
        except Exception as exc:
            logger.debug("Digital QSO status enrichment failed for %s: %s", call, exc, exc_info=True)

        needed = enriched.get("needed") if isinstance(enriched.get("needed"), Mapping) else {}
        needed_on_band = (
            enriched.get("needed_on_band")
            if isinstance(enriched.get("needed_on_band"), Mapping)
            else enriched.get("neededOnBand")
            if isinstance(enriched.get("neededOnBand"), Mapping)
            else {}
        )
        enriched["call_status"] = slot_aware_call_status(enriched.get("call_status"), needed, needed_on_band)
        enriched["dxcc_status"] = slot_aware_dxcc_status(enriched.get("dxcc_status"), needed, needed_on_band)

        existing_source = str(enriched.get("status_source") or enriched.get("statusSource") or "").strip()
        if status_sources and not existing_source:
            enriched["status_source"] = ",".join(dict.fromkeys(status_sources))
        return enriched

    def _revalidate_target_need(self, target: DigitalTarget) -> None:
        """Refresh authoritative worked/confirmed state before selection or retry."""
        if not self.qso_status_store:
            return
        payload = self._enrich_payload_from_local_status(
            target.to_dict(),
            call=target.call,
            band=target.band,
            mode=target.mode,
        )
        target.call_status = canonical_call_status(payload.get("call_status"), payload.get("dxcc_status"))
        target.dxcc_status = normalise_status(payload.get("dxcc_status"))
        target.need_reasons = payload_need_reasons(payload)
        score_info = score_payload_trace(payload)
        target.score = _int(score_info.get("score"), 0)
        target.score_reason = str(score_info.get("reason") or "")
        target.score_trace = dict(score_info)
        target.status_source = str(payload.get("status_source") or target.status_source or "")
        target.reason = self._target_reason(target)

    def next_target(
        self,
        now: Optional[datetime] = None,
        *,
        cq_only: bool = False,
        auto_call_start_only: bool = False,
    ) -> Optional[DigitalTarget]:
        now = now or utc_now()
        listening = self._active_listen_target(now)
        active = self.targets.get(self.active_target_key) if self.active_target_key else None
        if active and active.state not in {"done", "skipped", "expired", "backoff"}:
            direct_override = self._best_direct_caller(now, exclude_key=active.key)
            if direct_override and self._active_target_can_yield_to_direct_reply(active):
                active.sync_state("backoff")
                active.reason = "overridden-by-direct-reply"
                active.backoff_until = now + timedelta(seconds=max(15, self.settings.dwell_seconds))
                active.updated_at = now
                self._persist_target(active)
                self.active_target_key = None
                self.active_qso_state = "idle"
                self._set_decision({
                    "decision": "override",
                    "reason": "direct-reply-emergency",
                    "call": direct_override.call,
                    "band": direct_override.band,
                    "mode": direct_override.mode,
                    "overrode": active.call,
                    "score": direct_override.score,
                    "score_reason": direct_override.score_reason,
                    "score_trace": dict(direct_override.score_trace),
                    "priority_trace": self._priority_trace(now),
                })
                active = None
            elif direct_override and self.active_qso_state not in {"idle", "completed", "logged", "failed", "aborted"}:
                self._set_decision({
                    "decision": "hold",
                    "reason": "active-qso-protects-against-direct-reply",
                    "call": active.call,
                    "band": active.band,
                    "mode": active.mode,
                    "direct_reply": direct_override.call,
                    "state": active.state,
                    "active_state": active.active_state,
                    "priority_trace": self._priority_trace(now),
                })
                return None
        if active and active.state not in {"done", "skipped", "expired", "backoff"}:
            if self._expire_stale_active_target(active, now):
                active = None
            else:
                self._set_decision({
                    "decision": "hold",
                    "reason": "active-qso-in-progress",
                    "call": active.call,
                    "band": active.band,
                    "mode": active.mode,
                    "state": active.state,
                    "active_state": active.active_state,
                    "attempts": active.attempts,
                    "priority_trace": self._priority_trace(now),
                })
                return None
        active_bands = current_band_plan_bands(self.settings.band_plan, now) if self.settings.band_hopping else []
        candidates = []
        rejected: dict[str, int] = {}
        rejected_examples: dict[str, list[dict[str, Any]]] = {}

        def reject(reason: str, target: Optional[DigitalTarget] = None) -> None:
            rejected[reason] = rejected.get(reason, 0) + 1
            if not target:
                return
            bucket = rejected_examples.setdefault(reason, [])
            if len(bucket) >= 5:
                return
            bucket.append({
                "call": target.call,
                "band": target.band,
                "mode": target.mode,
                "score": target.score,
                "score_reason": target.score_reason,
                "score_trace": dict(target.score_trace),
                "state": target.state,
                "source": target.source,
                "call_status": target.call_status,
                "dxcc_status": target.dxcc_status,
                "need_reasons": sorted(target.need_reasons),
                "heard": target.heard,
                "direct_caller": target.direct_caller,
            })

        for target in self.targets.values():
            self._revalidate_target_need(target)
            if target.state == "backoff" and not target.is_backed_off(now):
                if target.campaign_count >= self.settings.max_attempts_per_target:
                    reset_at = target.last_attempt_at + timedelta(minutes=self.settings.retry_reset_minutes) if target.last_attempt_at else now
                    if now < reset_at:
                        reject("campaign-limit", target)
                        continue
                    target.campaign_count = 0
                    target.attempts = 0
                target.sync_state("heard" if target.heard else "queued", active_state="idle")
                target.backoff_until = None
            if target.state in {"done", "skipped", "expired", "backoff"}:
                reject(target.state, target)
                continue
            if target.mode not in self.settings.allowed_modes:
                reject("mode-disabled", target)
                continue
            if (
                active_bands
                and target.band
                and target.band.lower() not in active_bands
                and not target.direct_caller
                and source_is_spot_hunt(target.source)
            ):
                reject("outside-active-band-plan", target)
                continue
            if (
                not target.direct_caller
                and self.settings.avoid_logged
                and _prior_work_should_block(
                    target.call_status,
                    target.dxcc_status,
                    target.need_reasons,
                    self.settings,
                    target.source,
                )
            ):
                target.sync_state("skipped")
                target.reason = "already-worked-call"
                target.skip_reason = "already-worked-call"
                target.updated_at = now
                self._persist_target(target)
                self._set_decision({
                    "decision": "skip",
                    "reason": "already-worked-call",
                    "call": target.call,
                    "band": target.band,
                    "mode": target.mode,
                    "call_status": target.call_status,
                    "dxcc_status": target.dxcc_status,
                })
                reject("already-worked-call", target)
                continue
            if (
                auto_call_start_only
                and target.source in {"decoded", "wsjtx-decode-status"}
                and not target.direct_caller
                and not _is_auto_call_start_message(target.message, treat_73_as_cq=self.settings.treat_73_as_cq)
            ):
                target.sync_state("skipped")
                target.reason = "not-auto-call-start-message"
                target.skip_reason = "not-auto-call-start-message"
                target.updated_at = now
                reject("not-auto-call-start-message", target)
                continue
            if auto_call_start_only and target.source in {"decoded", "wsjtx-decode-status"}:
                last_heard_at = target.last_heard_at or target.updated_at
                max_age_seconds = _target_freshness_seconds(target.mode)
                if (now - last_heard_at).total_seconds() > max_age_seconds:
                    target.sync_state("expired")
                    target.reason = "decode-too-old"
                    target.updated_at = now
                    self._persist_target(target)
                    self._set_decision({
                        "decision": "expired",
                        "reason": "decode-too-old",
                        "call": target.call,
                        "band": target.band,
                        "mode": target.mode,
                    })
                    reject("decode-too-old", target)
                    continue
            if auto_call_start_only and target.heard and target.last_heard_at:
                max_age_seconds = _target_freshness_seconds(target.mode)
                if (now - target.last_heard_at).total_seconds() > max_age_seconds:
                    target.sync_state("expired")
                    target.reason = "heard-target-too-old"
                    target.updated_at = now
                    self._persist_target(target)
                    self._set_decision({
                        "decision": "expired",
                        "reason": "heard-target-too-old",
                        "call": target.call,
                        "band": target.band,
                        "mode": target.mode,
                        "source": target.source,
                    })
                    reject("heard-target-too-old", target)
                    continue
            if (
                cq_only
                and target.source in {"decoded", "wsjtx-decode-status"}
                and not target.direct_caller
                and not _is_auto_call_start_message(target.message, treat_73_as_cq=self.settings.treat_73_as_cq)
            ):
                reject("cq-only-non-cq", target)
                continue
            if target.score > 0 and not target.direct_caller and not payload_matches_need_filters(target.to_dict(), self.settings):
                blockers = payload_need_filter_blockers(target.to_dict(), self.settings)
                target.sync_state("skipped")
                target.reason = "not-needed-by-filter"
                target.skip_reason = "not-needed-by-filter"
                target.updated_at = now
                self._persist_target(target)
                self._set_decision({
                    "decision": "skip",
                    "reason": "not-needed-by-filter",
                    "call": target.call,
                    "band": target.band,
                    "mode": target.mode,
                    "call_status": target.call_status,
                    "dxcc_status": target.dxcc_status,
                    "blockers": blockers,
                    "score": target.score,
                    "score_reason": target.score_reason,
                    "score_trace": dict(target.score_trace),
                    "source": target.source,
                })
                reject("not-needed-by-filter", target)
                continue
            if target.is_backed_off(now):
                reject("backoff", target)
                continue
            if (
                target.last_attempt_at
                and (now - target.last_attempt_at).total_seconds() < self.settings.dwell_seconds
            ):
                reject("dwell", target)
                continue
            if self.settings.require_heard_before_call and not target.heard:
                reject("require-heard", target)
                continue
            if target.score <= 0 and self.settings.avoid_logged:
                reject("worked-or-unneeded", target)
                continue
            candidates.append(target)

        if not candidates:
            if listening:
                listen_started = listening.last_command_at or listening.updated_at
                remaining = max(
                    0,
                    int(self.settings.dwell_seconds - (now - listen_started).total_seconds()),
                ) if listen_started else self.settings.dwell_seconds
                self._set_decision({
                    "decision": "hold",
                    "reason": "spot-listen-in-progress",
                    "call": listening.call,
                    "band": listening.band,
                    "mode": listening.mode,
                    "remaining_seconds": remaining,
                    "rejected": rejected,
                    "rejected_examples": rejected_examples,
                    "priority_trace": self._priority_trace(now),
                })
                return None
            if self.active_target_key and self.active_target_key not in self.targets:
                self.active_target_key = None
                self.active_qso_state = "idle"
            self._set_decision({
                "decision": "idle",
                "reason": "no-eligible-targets",
                "rejected": rejected,
                "rejected_examples": rejected_examples,
                "priority_trace": self._priority_trace(now),
            })
            return None

        candidates.sort(
            key=lambda target: (
                1 if target.direct_caller else 0,
                target.score,
                target.snr if self.settings.priority == "signal" and target.snr is not None else 0,
                target.updated_at.timestamp(),
            ),
            reverse=True,
        )
        chosen = candidates[0]
        chosen.sync_state("selected", active_state="candidate_selected")
        chosen.updated_at = now
        if self.listen_target_key and self.listen_target_key != chosen.key:
            self.listen_target_key = None
        self.active_target_key = chosen.key
        self.active_qso_state = "candidate_selected"
        self._persist_target(chosen)
        self._set_decision({
            "decision": "selected",
            "call": chosen.call,
            "band": chosen.band,
            "mode": chosen.mode,
            "score": chosen.score,
            "score_reason": chosen.score_reason,
            "score_trace": dict(chosen.score_trace),
            "reason": chosen.reason,
            "source": chosen.source,
            "direct_caller": chosen.direct_caller,
            "need_reasons": sorted(chosen.need_reasons),
            "queue_position": 1,
            "attempts": chosen.attempts,
            "candidate_count": len(candidates),
            "candidate_order": [
                {
                    "call": candidate.call,
                    "band": candidate.band,
                    "mode": candidate.mode,
                    "score": candidate.score,
                    "score_reason": candidate.score_reason,
                    "score_trace": dict(candidate.score_trace),
                    "reason": candidate.reason,
                    "source": candidate.source,
                    "direct_caller": candidate.direct_caller,
                    "need_reasons": sorted(candidate.need_reasons),
                }
                for candidate in candidates[:25]
            ],
            "priority_trace": self._priority_trace(now),
            "rejected": rejected,
            "rejected_examples": rejected_examples,
        })
        return chosen

    def _best_direct_caller(self, now: datetime, *, exclude_key: str = "") -> Optional[DigitalTarget]:
        direct_targets = [
            target
            for target in self.targets.values()
            if target.key != exclude_key
            and target.direct_caller
            and target.heard
            and target.last_heard_at
            and (now - target.last_heard_at).total_seconds() <= _target_freshness_seconds(target.mode)
            and target.state not in {"done", "skipped", "expired", "backoff"}
            and not target.is_backed_off(now)
            and target.mode in self.settings.allowed_modes
        ]
        if not direct_targets:
            return None
        direct_targets.sort(
            key=lambda target: (
                target.score,
                target.snr if self.settings.priority == "signal" and target.snr is not None else 0,
                target.updated_at.timestamp(),
            ),
            reverse=True,
        )
        return direct_targets[0]

    def _expire_stale_active_target(self, target: DigitalTarget, now: datetime) -> bool:
        if target.campaign_expires_at:
            if target.active_state in {
                "in_qso", "waiting_rrr", "waiting_73", "reply_received",
                "report_sent", "rr73_seen", "logged", "completed",
            }:
                return False
            if now < target.campaign_expires_at:
                return False
            target.sync_state("backoff", active_state="failed")
            target.reason = "dxcc-hunt-watchdog-expired"
            target.completion_reason = "dxcc-hunt-watchdog-expired"
            target.backoff_until = now + timedelta(minutes=DXCC_HUNT_COOLDOWN_MINUTES)
            target.campaign_started_at = None
            target.campaign_expires_at = None
            target.updated_at = now
            self.active_target_key = None
            self.active_qso_state = "idle"
            self._queue_return_to_origin(target, reason=target.reason)
            self._persist_target(target)
            self._set_decision({
                "decision": "cooldown",
                "reason": target.reason,
                "call": target.call,
                "campaign_count": target.campaign_count,
                "backoff_until": _iso(target.backoff_until),
            })
            return True

        protected_states = {
            "reply_received",
            "report_sent",
            "rr73_seen",
            "logged",
            "completed",
        }
        if target.active_state in protected_states:
            return False
        if target.active_state not in {"candidate_selected", "command_sent", "waiting_for_tx", "calling"}:
            return False
        if target.active_state == "candidate_selected":
            progress_sources = (
                target.last_command_at,
                target.last_attempt_at,
                target.updated_at,
                target.last_heard_at,
            )
        else:
            # A fresh decode from the same station is not QSO progress once we have
            # started calling. Only command/attempt activity, or a real QSO state
            # transition above, can keep the active attempt alive.
            progress_sources = (
                target.last_command_at,
                target.last_attempt_at,
                target.updated_at if not target.last_command_at and not target.last_attempt_at else None,
            )
        markers = [marker for marker in progress_sources if marker is not None]
        if not markers:
            return False
        last_progress_at = max(markers)
        stale_after = max(30, int(self.settings.dwell_seconds or 0))
        if target.active_state in {"command_sent", "waiting_for_tx", "calling"}:
            # Hunting should not sit on a one-sided call for the full spot-listen
            # dwell. Replies advance the target into protected states above.
            stale_after = max(45, min(stale_after, 60))
        if (now - last_progress_at).total_seconds() < stale_after:
            return False
        target.sync_state("backoff", active_state="failed")
        target.reason = "stale-active-no-progress"
        target.completion_reason = "stale-active-no-progress"
        target.backoff_until = now + timedelta(minutes=max(1, int(self.settings.retry_backoff_minutes or 1)))
        target.updated_at = now
        self.active_target_key = None
        self.active_qso_state = "idle"
        self._persist_target(target)
        self._set_decision({
            "decision": "expired",
            "reason": "stale-active-no-progress",
            "call": target.call,
            "band": target.band,
            "mode": target.mode,
            "state": target.state,
            "active_state": target.active_state,
            "attempts": target.attempts,
            "backoff_until": target.backoff_until.isoformat(),
        })
        return True

    def next_listen_target(self, now: Optional[datetime] = None) -> Optional[DigitalTarget]:
        """Select an unheard external digital spot for a temporary listen-only QSY."""
        now = now or utc_now()
        if not self.settings.enabled or not self.settings.spot_hunt_enabled:
            self._set_decision({
                "decision": "idle",
                "reason": "spot-hunt-disabled",
            })
            return None

        active = self.targets.get(self.active_target_key) if self.active_target_key else None
        if active and active.state not in {"done", "skipped", "expired", "backoff"}:
            if self._expire_stale_active_target(active, now):
                active = None
            else:
                self._set_decision({
                    "decision": "hold",
                    "reason": "active-qso-in-progress",
                    "call": active.call,
                    "band": active.band,
                    "mode": active.mode,
                    "state": active.state,
                })
                return None
        listening = self._active_listen_target(now)
        if listening:
            self._set_decision({
                "decision": "hold",
                "reason": "spot-listen-in-progress",
                "call": listening.call,
                "band": listening.band,
                "mode": listening.mode,
            })
            return None

        active_bands = current_band_plan_bands(self.settings.band_plan, now)
        candidates = []
        rejected: dict[str, int] = {}

        def reject(reason: str) -> None:
            rejected[reason] = rejected.get(reason, 0) + 1

        for target in self._ordered_targets():
            self._revalidate_target_need(target)
            if not source_is_spot_hunt(target.source):
                reject("not-spot-source")
                continue
            if target.heard:
                reject("already-heard")
                continue
            if target.updated_at and (now - target.updated_at).total_seconds() > DXCC_SPOT_FRESHNESS_SECONDS:
                target.sync_state("expired")
                target.reason = "spot-too-old"
                target.completion_reason = "spot-too-old"
                self._persist_target(target)
                reject("spot-too-old")
                continue
            if target.state == "backoff" and not target.is_backed_off(now):
                if target.campaign_count >= self.settings.max_attempts_per_target:
                    reset_at = target.last_attempt_at + timedelta(minutes=self.settings.retry_reset_minutes) if target.last_attempt_at else now
                    if now < reset_at:
                        reject("campaign-limit")
                        continue
                    target.campaign_count = 0
                    target.attempts = 0
                target.sync_state("heard" if target.heard else "queued", active_state="idle")
                target.backoff_until = None
            if target.state in {"done", "skipped", "expired", "backoff"}:
                reject(target.state)
                continue
            if target.mode not in self.settings.allowed_modes:
                reject("mode-disabled")
                continue
            if target.is_backed_off(now):
                reject("backoff")
                continue
            dxcc_hunt = target_has_dxcc_hunt_interest(target)
            reference_hunt = target_has_reference_hunt_interest(target, self.settings)
            if not (dxcc_hunt or reference_hunt):
                reject("spot-not-hunt-interest")
                continue
            if reference_hunt and not payload_matches_hunter_spot_filters(target.to_dict(), self.settings):
                reject("hunter-filter")
                continue
            if target.score <= 0:
                reject("worked-or-unneeded")
                continue
            if self.settings.avoid_logged and _prior_work_should_block(
                target.call_status,
                target.dxcc_status,
                target.need_reasons,
                self.settings,
                target.source,
            ):
                reject("already-worked-call")
                continue
            if not payload_matches_need_filters(target.to_dict(), self.settings):
                reject("not-needed-by-filter")
                continue
            if active_bands and target.band and target.band not in active_bands and not reference_hunt:
                reject("outside-active-band-plan")
                continue
            if (
                not self.settings.band_hopping
                and self.settings.current_band
                and target.band
                and target.band != self.settings.current_band
            ):
                reject("band-hopping-disabled")
                continue
            if not target.dial_frequency:
                reject("missing-frequency")
                continue
            if not _favorable_propagation(target):
                reject("unfavorable-propagation")
                continue
            if (
                target.last_command_at
                and (now - target.last_command_at).total_seconds() < self.settings.dwell_seconds
            ):
                reject("dwell")
                continue
            candidates.append(target)

        if not candidates:
            self._set_decision({
                "decision": "idle",
                "reason": "no-spot-listen-targets",
                "rejected": rejected,
                "active_bands": active_bands,
            })
            return None

        chosen = candidates[0]
        chosen.sync_state("listening")
        chosen.last_command_at = now
        chosen.updated_at = now
        self.listen_target_key = chosen.key
        self._persist_target(chosen)
        self._set_decision({
            "decision": "listen-selected",
            "reason": "spot-reference-listen-probe" if target_has_reference_hunt_interest(chosen, self.settings) else "spot-dxcc-listen-probe",
            "call": chosen.call,
            "band": chosen.band,
            "mode": chosen.mode,
            "score": chosen.score,
            "source": chosen.source,
            "dial_frequency": chosen.dial_frequency,
            "need_reasons": sorted(chosen.need_reasons),
            "active_bands": active_bands,
        })
        return chosen

    def _active_listen_target(self, now: Optional[datetime] = None) -> Optional[DigitalTarget]:
        now = now or utc_now()
        if not self.listen_target_key:
            return None
        target = self.targets.get(self.listen_target_key)
        if not target:
            self.listen_target_key = None
            return None
        if target.heard:
            self.listen_target_key = None
            return None
        if target.state in {"done", "skipped", "expired", "backoff"}:
            self.listen_target_key = None
            return None
        if target.mode not in self.settings.allowed_modes:
            target.sync_state("skipped")
            target.reason = "mode-disabled"
            target.skip_reason = "mode-disabled"
            target.updated_at = now
            self.listen_target_key = None
            self._persist_target(target)
            self._set_decision({
                "decision": "skip",
                "reason": "mode-disabled",
                "call": target.call,
                "band": target.band,
                "mode": target.mode,
            })
            return None
        listen_started = target.last_command_at or target.updated_at
        listen_timeout = max(15, self.settings.dwell_seconds)
        if target_has_dxcc_hunt_interest(target) or target_has_reference_hunt_interest(target, self.settings):
            listen_timeout = max(90, min(120, self.settings.dwell_seconds))
            if target.last_command_at and target.updated_at > target.last_command_at + timedelta(seconds=15):
                listen_timeout = DXCC_SPOT_SILENCE_SECONDS
        if listen_started and (now - listen_started).total_seconds() >= listen_timeout:
            target.sync_state("expired")
            target.reason = "spot-listen-not-heard"
            target.completion_reason = "spot-listen-not-heard"
            target.updated_at = now
            self.listen_target_key = None
            self._queue_return_to_origin(target, reason="spot-listen-not-heard")
            self._persist_target(target)
            self._set_decision({
                "decision": "expired",
                "reason": "spot-listen-not-heard",
                "call": target.call,
                "band": target.band,
                "mode": target.mode,
                "listen_timeout_seconds": listen_timeout,
            })
            return None
        return target

    def set_target_origin(
        self,
        key: str,
        *,
        band: Any = "",
        mode: Any = "",
        dial_frequency: Any = None,
    ) -> Optional[DigitalTarget]:
        target = self.targets.get(key)
        if not target:
            return None
        target.origin_band = str(band or target.origin_band or "").strip().lower()
        target.origin_mode = normalise_mode(mode) if mode else (target.origin_mode or target.mode)
        parsed_frequency = _float(dial_frequency)
        if parsed_frequency is not None and parsed_frequency > 0:
            target.origin_dial_frequency = parsed_frequency
        target.updated_at = utc_now()
        self._persist_target(target)
        return target

    def _queue_return_to_origin(self, target: DigitalTarget, *, reason: str) -> None:
        if target.return_command_at:
            return
        if not (target.origin_dial_frequency or target.origin_band):
            return
        self.pending_return_command = {
            "reason": reason,
            "call": target.call,
            "target_key": target.key,
            "band": target.origin_band,
            "mode": target.origin_mode or target.mode,
            "dial_frequency": target.origin_dial_frequency,
        }

    def pending_return_to_origin(self) -> Optional[dict[str, Any]]:
        return dict(self.pending_return_command) if self.pending_return_command else None

    def mark_return_command_sent(self, key: Any = None) -> None:
        command = self.pending_return_command
        self.pending_return_command = None
        target_key = str(key or (command or {}).get("target_key") or "")
        target = self.targets.get(target_key)
        if target:
            target.return_command_at = utc_now()
            target.updated_at = target.return_command_at
            self._persist_target(target)
        self._set_decision({
            "decision": "return-command-sent",
            "reason": (command or {}).get("reason", "return-to-origin"),
            "call": (command or {}).get("call"),
            "band": (command or {}).get("band"),
            "mode": (command or {}).get("mode"),
        })

    def prepare_command(self, key: str) -> Optional[str]:
        """Reserve a stable command id before transport so WSJT-Z sees the same id we persist."""
        target = self.targets.get(key)
        if not target:
            return None
        ordinal = max(target.attempts, target.campaign_count)
        target.command_id = command_identity(
            target.target_id or target_identity(target.call, target.band, target.mode),
            ordinal,
        )
        target.updated_at = utc_now()
        self._persist_target(target)
        return target.command_id

    def record_attempt(self, key: str, *, command_id: Optional[str] = None) -> Optional[DigitalTarget]:
        target = self.targets.get(key)
        if not target:
            self._set_decision({"decision": "skip", "reason": "attempt-target-missing", "key": key})
            return None
        now = utc_now()
        if (
            target.last_attempt_at
            and (now - target.last_attempt_at).total_seconds() > self.settings.retry_reset_minutes * 60
        ):
            target.attempts = 0
        target.attempts += 1
        target.last_attempt_at = now
        target.command_id = command_id or target.command_id or command_identity(
            target.target_id or target_identity(target.call, target.band, target.mode),
            target.attempts - 1,
        )
        target.last_command_at = now
        target.state = "calling"
        target.lifecycle = "command_sent"
        target.sync_state(active_state="command_sent")
        self.active_qso_state = "command_sent"
        if target_has_dxcc_hunt_interest(target):
            target.campaign_count += 1
            target.campaign_started_at = now
            target.campaign_expires_at = now + timedelta(minutes=DXCC_HUNT_WATCHDOG_MINUTES)
            target.backoff_until = None
        self._set_decision({
            "decision": "attempt-recorded",
            "key": key,
            "call": target.call,
            "command_id": target.command_id,
            "attempts": target.attempts,
            "state": target.state,
            "backoff_until": _iso(target.backoff_until),
            "campaign_count": target.campaign_count,
            "campaign_expires_at": _iso(target.campaign_expires_at),
        })
        self._persist_target(target)
        return target

    def promote_target(self, key: str) -> Optional[DigitalTarget]:
        """Move a queued target to the top of the planner without starting TX."""
        target = self.targets.get(key)
        if not target:
            self._set_decision({"decision": "skip", "reason": "promote-target-missing", "key": key})
            return None
        max_score = max((existing.score for existing in self.targets.values()), default=target.score)
        target.score = max(target.score, max_score + 1)
        if target.state in {"done", "skipped", "backoff"}:
            target.sync_state("heard" if target.heard else "listening")
            target.backoff_until = None
        target.updated_at = utc_now()
        self._set_decision({
            "decision": "promoted",
            "key": key,
            "call": target.call,
            "score": target.score,
            "state": target.state,
            "queue_position": self._queue_position(target.key),
        })
        self._persist_target(target)
        return target

    def skip_target(self, key: str, *, reason: str = "operator-removed") -> Optional[DigitalTarget]:
        """Remove a target from the active planner queue while preserving history."""
        target = self.targets.get(key)
        if not target:
            self._set_decision({"decision": "skip", "reason": "skip-target-missing", "key": key})
            return None
        target.sync_state("skipped")
        target.reason = reason
        target.skip_reason = reason
        target.updated_at = utc_now()
        if self.active_target_key == key:
            self.active_target_key = None
            self.active_qso_state = "idle"
        self._set_decision({
            "decision": "skipped",
            "key": key,
            "call": target.call,
            "reason": reason,
        })
        self._persist_target(target)
        return target

    def release_target(self, key: str, *, reason: str = "target-released") -> Optional[DigitalTarget]:
        """Release a selected target that never became a real TX attempt."""
        target = self.targets.get(key)
        if not target:
            self._set_decision({"decision": "release", "reason": "release-target-missing", "key": key})
            return None
        if self.active_target_key == key:
            self.active_target_key = None
            self.active_qso_state = "idle"
        target.sync_state("heard" if target.heard else "queued", active_state="idle")
        target.lifecycle = "queued"
        target.reason = reason
        target.skip_reason = ""
        target.updated_at = utc_now()
        self._set_decision({
            "decision": "release",
            "reason": reason,
            "call": target.call,
            "band": target.band,
            "mode": target.mode,
            "state": target.state,
        })
        self._persist_target(target)
        return target

    def choose_tx_audio_offset(
        self,
        target: DigitalTarget,
        *,
        preferred_hz: int = DEFAULT_TX_AUDIO_HZ,
        guard_hz: int = TX_AUDIO_GUARD_HZ,
        low_hz: int = TX_AUDIO_LOW_HZ,
        high_hz: int = TX_AUDIO_HIGH_HZ,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Pick a clear WSJT transmit audio offset near the operator default.

        WSJT-Z's `setFreeFreq(...)` avoids transmitting on top of recently
        decoded signals. This is the backend equivalent for prepared WSJT
        targets: it inspects recent decodes on the same band/mode and selects a
        stable offset that is at least `guard_hz` away when possible.
        """
        now = now or utc_now()
        preferred = _int(preferred_hz, DEFAULT_TX_AUDIO_HZ, low=low_hz, high=high_hz)
        occupied = self.occupied_audio_offsets(
            target,
            now=now,
            max_age_seconds=45 if normalise_mode(target.mode) == "FT4" else 90,
        )

        candidates = [preferred]
        for spread in range(TX_AUDIO_STEP_HZ, high_hz - low_hz + TX_AUDIO_STEP_HZ, TX_AUDIO_STEP_HZ):
            for candidate in (preferred + spread, preferred - spread):
                if low_hz <= candidate <= high_hz and candidate not in candidates:
                    candidates.append(candidate)

        def closest_distance(candidate: int) -> int:
            if not occupied:
                return high_hz
            return min(abs(candidate - offset) for offset in occupied)

        for candidate in candidates:
            if closest_distance(candidate) >= guard_hz:
                return {
                    "tx_df": candidate,
                    "preferred_df": preferred,
                    "occupied": occupied,
                    "guard_hz": guard_hz,
                    "reason": "preferred-clear" if candidate == preferred else "nearest-clear",
                }

        fallback = max(candidates, key=closest_distance)
        return {
            "tx_df": fallback,
            "preferred_df": preferred,
            "occupied": occupied,
            "guard_hz": guard_hz,
            "reason": "least-occupied",
        }

    def occupied_audio_offsets(
        self,
        target: DigitalTarget,
        *,
        now: Optional[datetime] = None,
        max_age_seconds: int = 90,
    ) -> list[int]:
        """Return recent RX audio offsets for the same band/mode/dial context."""
        now = now or utc_now()
        offsets: set[int] = set()
        for other in self.targets.values():
            if other is target:
                continue
            if normalise_mode(other.mode) != normalise_mode(target.mode):
                continue
            if target.band and other.band and other.band != target.band:
                continue
            if target.dial_frequency and other.dial_frequency:
                if abs(float(other.dial_frequency) - float(target.dial_frequency)) > 0.001:
                    continue
            heard_at = other.last_heard_at or other.updated_at
            if heard_at and (now - heard_at).total_seconds() > max_age_seconds:
                continue
            offset = _int(other.audio_offset, 0, low=0, high=5000)
            if TX_AUDIO_LOW_HZ <= offset <= TX_AUDIO_HIGH_HZ:
                offsets.add(offset)
        return sorted(offsets)

    def abandon_active_target(self, *, reason: str = "operator-aborted") -> Optional[DigitalTarget]:
        """Back off the currently selected/calling target without disabling automation."""
        if not self.active_target_key:
            self._set_decision({"decision": "idle", "reason": "no-active-target-to-abandon"})
            return None
        target = self.targets.get(self.active_target_key)
        self.active_target_key = None
        if not target:
            self.active_qso_state = "idle"
            self._set_decision({"decision": "idle", "reason": "active-target-missing"})
            return None
        now = utc_now()
        target.sync_state("backoff", active_state="failed")
        target.reason = reason
        target.updated_at = now
        target.backoff_until = datetime.fromtimestamp(
            now.timestamp() + (
                DXCC_HUNT_COOLDOWN_MINUTES if target_has_dxcc_hunt_interest(target)
                else self.settings.retry_backoff_minutes
            ) * 60,
            timezone.utc,
        )
        target.campaign_started_at = None
        target.campaign_expires_at = None
        self.active_qso_state = "failed"
        self._set_decision({
            "decision": "abandoned",
            "key": target.key,
            "call": target.call,
            "reason": reason,
            "backoff_until": _iso(target.backoff_until),
        })
        self._persist_target(target)
        return target

    def handle_wsjtx_status(self, status: Mapping[str, Any]) -> dict[str, Any]:
        """Apply WSJT-X status changes and pause automation on manual override signals."""
        payload = dict(status or {})
        active = self.targets.get(self.active_target_key) if self.active_target_key else None
        manual_override = _bool(payload.get("manual") or payload.get("operatorAction") or payload.get("operator_action"), False)
        dx_call = str(payload.get("dxCall") or payload.get("dx_call") or payload.get("call") or "").strip().upper()
        if active and manual_override and dx_call and dx_call not in {active.call, self.mycall}:
            target = self.abandon_active_target(reason="manual-dx-call-change")
            return {"status": "abandoned", "target": target.to_dict() if target else None, "decision": self.last_decision}

        if active and manual_override:
            target = self.abandon_active_target(reason="manual-operator-action")
            return {"status": "abandoned", "target": target.to_dict() if target else None, "decision": self.last_decision}

        if active and _bool(payload.get("tune") or payload.get("tuning"), False):
            target = self.abandon_active_target(reason="manual-tune-active")
            return {"status": "abandoned", "target": target.to_dict() if target else None, "decision": self.last_decision}

        if active and dx_call and dx_call not in {active.call, self.mycall}:
            self._set_decision({
                "decision": "status-observed",
                "reason": "stale-or-unrelated-dx-call",
                "call": active.call,
                "reported_dx_call": dx_call,
                "state": active.state,
            })
            return {"status": "observed", "target": active.to_dict(), "decision": self.last_decision}

        mode = str(payload.get("mode") or "").strip().upper()
        if active and mode and normalise_mode(mode) != active.mode:
            target = self.abandon_active_target(reason="manual-mode-change")
            return {"status": "abandoned", "target": target.to_dict() if target else None, "decision": self.last_decision}

        band = str(payload.get("band") or "").strip()
        if active and band and active.band and band != active.band:
            target = self.abandon_active_target(reason="manual-band-change")
            return {"status": "abandoned", "target": target.to_dict() if target else None, "decision": self.last_decision}

        frequency_mhz = _frequency_mhz_from_status(payload)
        if active and frequency_mhz and active.dial_frequency and abs(frequency_mhz - float(active.dial_frequency)) > 0.003:
            if active.last_command_at and (utc_now() - active.last_command_at).total_seconds() < 10:
                self._set_decision({
                    "decision": "awaiting-command-ack",
                    "reason": "wsjtz-frequency-settle",
                    "call": active.call,
                    "command_id": active.command_id,
                })
                return {"status": "pending", "target": active.to_dict(), "decision": self.last_decision}
            target = self.abandon_active_target(reason="manual-frequency-change")
            return {"status": "abandoned", "target": target.to_dict() if target else None, "decision": self.last_decision}

        if active and (dx_call == active.call or (
            frequency_mhz and active.dial_frequency and abs(frequency_mhz - float(active.dial_frequency)) <= 0.003
        )):
            if not active.command_ack_at:
                active.command_ack_at = utc_now()
                active.updated_at = active.command_ack_at
                self._persist_target(active)

        # The custom heartbeat is useful only after the ordinary status fields
        # confirm that it still describes our active target. Otherwise a stale
        # non-empty qsoState could bypass every manual-override safety check.
        heartbeat_state = normalise_wsjtz_qso_state(payload)
        busy_heartbeat_states = {"calling", "in_qso", "waiting_rrr", "waiting_73", "transmitting", "tx"}
        has_tx_enabled = "txEnabled" in payload or "tx_enabled" in payload
        tx_enabled = _bool(payload.get("txEnabled") or payload.get("tx_enabled"), False)
        if not active and heartbeat_state in busy_heartbeat_states and not dx_call and has_tx_enabled and not tx_enabled:
            self.transition_active_qso("idle", reason="invalid-wsjtz-busy-status")
            return {
                "status": "idle",
                "target": None,
                "decision": self.last_decision,
                "qso_state": "idle",
            }
        if heartbeat_state:
            if active and heartbeat_state == "logged":
                completed = self.mark_done(active.key, reason="wsjtz-heartbeat-logged")
                return {
                    "status": "logged",
                    "target": completed.to_dict() if completed else active.to_dict(),
                    "decision": self.last_decision,
                    "qso_state": heartbeat_state,
                }
            self.transition_active_qso(
                heartbeat_state,
                reason="wsjtz-heartbeat",
                target=active,
            )
            return {
                "status": heartbeat_state,
                "target": active.to_dict() if active else None,
                "decision": self.last_decision,
                "qso_state": heartbeat_state,
            }

        if not active:
            self._set_decision({"decision": "status-observed", "reason": "no-active-target"})
            return {"status": "idle", "decision": self.last_decision}

        if _bool(payload.get("tx") or payload.get("txEnabled") or payload.get("transmitting"), False):
            self.transition_active_qso("calling", reason="wsjtx-status-tx-active", target=active)
            return {"status": "calling", "target": active.to_dict(), "decision": self.last_decision}

        return {"status": "observed", "target": active.to_dict(), "decision": self.last_decision}

    def mark_done(self, key: str, *, reason: str = "qso-complete") -> Optional[DigitalTarget]:
        target = self.targets.get(key)
        if target:
            target.sync_state("done", active_state="completed")
            target.reason = reason
            target.completion_reason = reason
            target.campaign_started_at = None
            target.campaign_expires_at = None
            target.updated_at = utc_now()
            if self.active_target_key == key:
                self.active_target_key = None
                self.active_qso_state = "completed"
            self._queue_return_to_origin(target, reason=reason)
            self._set_decision({
                "decision": "done",
                "key": key,
                "call": target.call,
                "reason": reason,
            })
            self._persist_target(target)
        return target

    def mark_qso_complete(
        self,
        call: str,
        *,
        band: Optional[str] = None,
        mode: Optional[str] = None,
        reason: str = "qso-complete",
    ) -> list[DigitalTarget]:
        call_upper = str(call or "").upper()
        mode_upper = normalise_mode(mode) if mode else None
        completed: list[DigitalTarget] = []
        for target in self.targets.values():
            if target.call != call_upper:
                continue
            if band and target.band != band:
                continue
            if mode_upper and target.mode != mode_upper:
                continue
            target.sync_state("done", active_state="completed")
            target.reason = reason
            target.completion_reason = reason
            target.campaign_started_at = None
            target.campaign_expires_at = None
            target.updated_at = utc_now()
            completed.append(target)
            if self.active_target_key == target.key:
                self.active_target_key = None
                self.active_qso_state = "completed"
            self._queue_return_to_origin(target, reason=reason)
            self._persist_target(target)
        if completed:
            self._set_decision({
                "decision": "done",
                "call": call_upper,
                "count": len(completed),
                "reason": reason,
            })
        return completed

    def replay_events(self, events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Replay recorded automation events through the planner for safe tests."""
        results: list[dict[str, Any]] = []
        for index, raw_event in enumerate(events or []):
            event = dict(raw_event or {})
            event_type = str(event.get("type") or event.get("event") or "").strip().lower()
            try:
                if event_type in {"decode", "decoded", "target", "spot", "incoming"}:
                    payload = dict(event.get("target") or event.get("payload") or event)
                    if event_type in {"decode", "decoded", "incoming"}:
                        payload.setdefault("source", "decoded")
                        payload.setdefault("heard", True)
                    elif event_type == "spot":
                        payload.setdefault("source", "spot")
                    target = self.ingest_target(payload)
                    results.append({
                        "index": index,
                        "event": event_type,
                        "status": "queued" if target else "ignored",
                        "target": target.to_dict() if target else None,
                        "decision": self.last_decision,
                    })
                elif event_type in {"next", "select"}:
                    target = self.next_target(
                        cq_only=_bool(event.get("cq_only"), False),
                        auto_call_start_only=_bool(event.get("auto_call_start_only"), False),
                    )
                    results.append({
                        "index": index,
                        "event": event_type,
                        "status": "selected" if target else "idle",
                        "target": target.to_dict() if target else None,
                        "decision": self.last_decision,
                    })
                elif event_type == "attempt":
                    target = self.record_attempt(str(event.get("key") or ""))
                    results.append({
                        "index": index,
                        "event": event_type,
                        "status": "updated" if target else "missing",
                        "target": target.to_dict() if target else None,
                        "decision": self.last_decision,
                    })
                elif event_type == "status":
                    outcome = self.handle_wsjtx_status(dict(event.get("status") or event.get("payload") or event))
                    results.append({
                        "index": index,
                        "event": event_type,
                        **outcome,
                    })
                elif event_type in {"complete", "logged"}:
                    completed = self.mark_qso_complete(
                        str(event.get("call") or event.get("callsign") or ""),
                        band=event.get("band"),
                        mode=event.get("mode"),
                        reason=event_type,
                    )
                    results.append({
                        "index": index,
                        "event": event_type,
                        "status": "completed" if completed else "missing",
                        "targets": [target.to_dict() for target in completed],
                        "decision": self.last_decision,
                    })
                elif event_type == "skip":
                    target = self.skip_target(str(event.get("key") or ""), reason=str(event.get("reason") or "replay-skip"))
                    results.append({
                        "index": index,
                        "event": event_type,
                        "status": "skipped" if target else "missing",
                        "target": target.to_dict() if target else None,
                        "decision": self.last_decision,
                    })
                else:
                    self._set_decision({
                        "decision": "skip",
                        "reason": "unknown-replay-event",
                        "event": event_type,
                    })
                    results.append({
                        "index": index,
                        "event": event_type,
                        "status": "ignored",
                        "decision": self.last_decision,
                    })
            except Exception as exc:
                self._set_decision({
                    "decision": "skip",
                    "reason": "replay-event-error",
                    "event": event_type,
                    "error": str(exc),
                })
                results.append({
                    "index": index,
                    "event": event_type,
                    "status": "error",
                    "error": str(exc),
                    "decision": self.last_decision,
                })
        return results

    def status(self) -> dict[str, Any]:
        now = utc_now()
        active = self.targets.get(self.active_target_key) if self.active_target_key else None
        listening = self._active_listen_target(now)
        queue = self._ordered_targets()
        return {
            "enabled": self.settings.enabled,
            "settings": self.settings.to_dict(),
            "active_target": active.to_dict() if active else None,
            "listen_target": listening.to_dict() if listening else None,
            "pending_return": self.pending_return_to_origin(),
            "active_qso_state": self.active_qso_state,
            "qso_state": self.active_qso_state,
            "queue_length": len(self.targets),
            "eligible_count": sum(
                1
                for target in self.targets.values()
                if target.state not in {"done", "skipped", "expired"}
                and not target.is_backed_off(now)
                and not (
                    not target.direct_caller
                    and self.settings.avoid_logged
                    and _prior_work_should_block(
                        target.call_status,
                        target.dxcc_status,
                        target.need_reasons,
                        self.settings,
                        target.source,
                    )
                )
                and (target.direct_caller or target.score <= 0 or payload_matches_need_filters(target.to_dict(), self.settings))
                and (target.heard or not self.settings.require_heard_before_call)
                and (target.score > 0 or not self.settings.avoid_logged)
            ),
            "targets": [target.to_dict() for target in queue[:25]],
            "last_decision": self.last_decision,
            "decision_log": self.decision_log[-50:],
            "event_timeline": self._event_timeline(20),
            "reason_panel": self._reason_panel(active, listening, now),
            "eligibility_summary": self._eligibility_summary(now, cq_only=True, auto_call_start_only=True),
            "persistence": {
                "enabled": bool(self.target_store),
                "loaded_count": self.persistence_loaded_count,
                "error": self.persistence_error,
            },
        }

    def _load_persisted_targets(self) -> None:
        if not self.target_store:
            self.persistence_loaded_count = 0
            return
        try:
            rows = self.target_store.load_recent_targets(limit=self.max_targets)
        except Exception as exc:
            self.persistence_error = str(exc)
            logger.warning("Digital target persistence load failed: %s", exc)
            return

        loaded = 0
        for row in rows:
            target = _target_from_mapping(row)
            if not target:
                continue
            self._normalise_loaded_target(target)
            self.targets[target.key] = target
            loaded += 1
        self.persistence_loaded_count = loaded
        self.persistence_error = None

    def _normalise_loaded_target(self, target: DigitalTarget) -> None:
        active_states = {"candidate_selected", "command_sent", "waiting_for_tx", "calling"}
        active_lifecycles = {"selected", "command_sent", "active", "in_progress"}
        loaded_as_active = (
            target.active_state in active_states
            or target.lifecycle in active_lifecycles
            or target.state in {"selected", "calling"}
        )
        if not loaded_as_active:
            return
        target.sync_state("backoff", active_state="failed")
        target.reason = "backend-restarted-active-target"
        target.completion_reason = target.completion_reason or "backend-restarted-active-target"
        target.backoff_until = utc_now() + timedelta(minutes=max(1, int(self.settings.retry_backoff_minutes or 1)))
        target.updated_at = utc_now()
        self._persist_target(target)

    def _persist_target(self, target: DigitalTarget) -> None:
        if not self.target_store:
            return
        try:
            self.target_store.upsert_target(target)
        except Exception as exc:
            self.persistence_error = str(exc)
            logger.debug("Digital target persistence save failed for %s: %s", target.key, exc)

    def _target_reason(self, target: DigitalTarget) -> str:
        if target.direct_caller:
            return "direct-caller"
        if normalise_status(target.dxcc_status) == "ATNO":
            return "new-dxcc"
        status_text = f"{target.call_status} {target.dxcc_status}".lower()
        if "new band" in status_text:
            return "new-band-slot"
        if "grid" in status_text:
            return "new-grid"
        if "new mode" in status_text:
            return "new-mode"
        if normalise_status(target.call_status) == "New Call":
            return "new-call"
        if target.score > 0:
            return "needed"
        return "no-current-goal"

    def _ordered_targets(self) -> list[DigitalTarget]:
        return sorted(
            self.targets.values(),
            key=lambda target: (
                1 if target.direct_caller else 0,
                target.score,
                target.snr if self.settings.priority == "signal" and target.snr is not None else 0,
                target.updated_at.timestamp(),
            ),
            reverse=True,
        )

    def _queue_position(self, key: str) -> Optional[int]:
        for index, target in enumerate(self._ordered_targets(), start=1):
            if target.key == key:
                return index
        return None

    def _trim_targets(self) -> None:
        if len(self.targets) <= self.max_targets:
            return
        removable = sorted(
            self.targets.values(),
            key=lambda target: (
                0 if target.state in {"done", "skipped", "backoff"} else 1,
                target.score,
                target.updated_at.timestamp(),
            ),
        )
        while len(self.targets) > self.max_targets and removable:
            target = removable.pop(0)
            if target.key == self.active_target_key:
                continue
            self.targets.pop(target.key, None)


def _float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _optional_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _status_unknown(value: Any) -> bool:
    return normalise_status(value).lower() in {"", "unknown", "-"}


def normalise_wsjtz_qso_state(payload: Mapping[str, Any]) -> str:
    raw = _first_present(
        payload,
        "qso_state",
        "qsoState",
        "wsjtz_qso_state",
        "wsjtzQsoState",
        "om0rx_qso_state",
        "om0rxQsoState",
    )
    state = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": "",
        "none": "",
        "idle": "idle",
        "ready": "idle",
        "calling": "calling",
        "tx": "calling",
        "transmitting": "calling",
        "in_qso": "in_qso",
        "inqso": "in_qso",
        "active": "in_qso",
        "waiting_rrr": "waiting_rrr",
        "wait_rrr": "waiting_rrr",
        "waiting_for_rrr": "waiting_rrr",
        "waiting_73": "waiting_73",
        "wait_73": "waiting_73",
        "waiting_for_73": "waiting_73",
        "logged": "logged",
        "log": "logged",
        "blocked": "blocked",
        "paused": "blocked",
    }
    return aliases.get(state, state if state in ACTIVE_QSO_STATES else "")


def _is_cq_message(message: Any) -> bool:
    tokens = _message_tokens(str(message or ""))
    return bool(tokens and tokens[0] in {"CQ", "QRZ"})


def _is_73_message(message: Any) -> bool:
    tokens = _message_tokens(str(message or ""))
    return bool(tokens and tokens[-1:] and tokens[-1] in {"73", "RR73"})


def _is_auto_call_start_message(message: Any, *, treat_73_as_cq: bool = False) -> bool:
    """Return true only for messages that may start a new Auto Call QSO.

    A third-party 73/RR73 proves activity, but it is not an invitation to call.
    Keep the legacy option argument for settings compatibility while refusing
    to let it weaken transmit eligibility.
    """
    _ = treat_73_as_cq
    return _is_cq_message(message)


def _reference_from_values(ref_type: Any, ref_id: Any, status: Any = None, need_reason: Any = None) -> Optional[dict[str, str]]:
    ref_type_text = canonical_reference_program(ref_type)
    ref_id_text = str(ref_id or "").strip().upper()
    if not ref_type_text or not ref_id_text:
        return None
    return {
        "type": ref_type_text,
        "id": ref_id_text,
        "status": str(status or "unknown").strip().lower() or "unknown",
        "need_reason": str(need_reason or "").strip(),
    }


def reference_is_needed(reference: Mapping[str, Any]) -> bool:
    status = str(reference.get("status") or "").strip().lower()
    reason = str(reference.get("need_reason") or "").strip().lower()
    return status in {"needed", "new", "new reference", "unworked", "unknown-needed"} or bool(reason)


def normalise_reference_items(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    raw_items = payload.get("reference_items") or payload.get("references") or []
    if isinstance(raw_items, str):
        try:
            parsed = json.loads(raw_items)
        except (TypeError, ValueError):
            parsed = [
                {"reference_id": token.strip()}
                for token in re.split(r"[\s,;]+", raw_items)
                if token.strip()
            ]
        raw_items = parsed
    if isinstance(raw_items, Mapping):
        raw_items = [raw_items]

    items: list[dict[str, str]] = []
    for raw in raw_items or []:
        if isinstance(raw, Mapping):
            item = _reference_from_values(
                raw.get("type") or raw.get("reference_type") or raw.get("referenceType") or raw.get("kind"),
                raw.get("id") or raw.get("reference_id") or raw.get("referenceId") or raw.get("ref"),
                raw.get("status") or raw.get("reference_status") or raw.get("referenceStatus"),
                raw.get("need_reason") or raw.get("reference_need_reason") or raw.get("referenceNeedReason"),
            )
        else:
            item = _reference_from_values("CUSTOM", raw)
        if item:
            items.append(item)

    for ref_type in ("pota", "sota", "iota", "wwff", "wwbota", "bunker", "arlhs", "lighthouse", "county", "state", "province"):
        value = payload.get(ref_type) or payload.get(f"{ref_type}_reference") or payload.get(f"{ref_type}Reference")
        status = payload.get(f"{ref_type}_status") or payload.get(f"{ref_type}Status")
        reason = payload.get(f"{ref_type}_need_reason") or payload.get(f"{ref_type}NeedReason")
        if isinstance(value, (list, tuple, set)):
            for ref_id in value:
                item = _reference_from_values(ref_type, ref_id, status, reason)
                if item:
                    items.append(item)
        else:
            item = _reference_from_values(ref_type, value, status, reason)
            if item:
                items.append(item)

    for extracted in extract_activity_references(payload):
        item = _reference_from_values(
            extracted.get("type"),
            extracted.get("reference_id") or extracted.get("id"),
            extracted.get("status"),
            extracted.get("need_reason"),
        )
        if item:
            items.append(item)

    deduped: dict[tuple[str, str], dict[str, str]] = {}
    for item in items:
        key = (item["type"], item["id"])
        existing = deduped.get(key)
        if not existing:
            deduped[key] = item
            continue
        if str(existing.get("status") or "").lower() in {"", "unknown"} and str(item.get("status") or "").lower() not in {"", "unknown"}:
            existing["status"] = item["status"]
        if not existing.get("need_reason") and item.get("need_reason"):
            existing["need_reason"] = item["need_reason"]
    return list(deduped.values())


def score_payload_trace(payload: Mapping[str, Any]) -> dict[str, Any]:
    call_status = normalise_status(payload.get("call_status") or payload.get("callStatus"))
    dxcc_status = normalise_status(payload.get("dxcc_status") or payload.get("dxccStatus"))
    status_text = f"{call_status} {dxcc_status}".lower()
    needed = payload.get("needed") if isinstance(payload.get("needed"), Mapping) else {}
    needed_on_band = (
        payload.get("needed_on_band")
        if isinstance(payload.get("needed_on_band"), Mapping)
        else payload.get("neededOnBand")
        if isinstance(payload.get("neededOnBand"), Mapping)
        else {}
    )

    def result(score: int, reason: str) -> dict[str, Any]:
        return {
            "score": score,
            "reason": reason,
            "label": f"{reason}={score}",
            "call_status": call_status,
            "dxcc_status": dxcc_status,
        }

    if dxcc_status == "ATNO" or _bool(needed.get("dxcc")):
        return result(ATNO_SCORE, "ATNO")
    if dxcc_status == "Worked":
        return result(DXCC_WORKED_NOT_CONFIRMED_SCORE, "DXCC worked-not-confirmed")
    if _bool(needed_on_band.get("dxcc")) or "new band" in dxcc_status.lower():
        return result(DXCC_NEW_BAND_SCORE, "DXCC new band")
    if call_status == "New Call":
        continent = str(payload.get("continent") or "").strip().upper()
        if continent and continent != "EU":
            return result(NON_EU_NEW_CALL_SCORE, "non-EU new call")
    if _bool(needed_on_band.get("call")) or "new band" in call_status.lower():
        return result(CALL_NEW_BAND_SCORE, "new band")
    if any(reference_is_needed(item) for item in normalise_reference_items(payload)):
        return result(REFERENCE_SCORE, "reference")
    if _bool(needed.get("grid")) or _bool(needed_on_band.get("grid")) or "grid" in status_text:
        return result(GRID_SCORE, "grid")
    if _bool(needed.get("mode")) or _bool(needed_on_band.get("mode")) or "new mode" in status_text:
        return result(MODE_SCORE, "new mode")
    if _bool(needed.get("call")) or call_status == "New Call":
        return result(NEW_CALL_SCORE, "new call")
    return result(0, "worked-or-unneeded")


def score_payload(payload: Mapping[str, Any]) -> int:
    return _int(score_payload_trace(payload).get("score"), 0)


def payload_need_reasons(payload: Mapping[str, Any]) -> set[str]:
    call_status = normalise_status(payload.get("call_status") or payload.get("callStatus"))
    dxcc_status = normalise_status(payload.get("dxcc_status") or payload.get("dxccStatus"))
    status_text = f"{call_status} {dxcc_status}".lower()
    needed = payload.get("needed") if isinstance(payload.get("needed"), Mapping) else {}
    needed_on_band = (
        payload.get("needed_on_band")
        if isinstance(payload.get("needed_on_band"), Mapping)
        else payload.get("neededOnBand")
        if isinstance(payload.get("neededOnBand"), Mapping)
        else {}
    )
    reasons = {
        str(reason).strip().lower()
        for reason in (payload.get("need_reasons") or payload.get("needed_reasons") or [])
        if str(reason).strip()
    }
    references = normalise_reference_items(payload)

    if dxcc_status == "ATNO" or _bool(needed.get("dxcc")):
        reasons.add("dxcc")
    if dxcc_status == "Worked":
        reasons.add("dxcc")
    if (
        _bool(needed_on_band.get("dxcc"))
        or _bool(needed_on_band.get("call"))
        or "new band" in dxcc_status.lower()
        or "new band" in call_status.lower()
    ):
        reasons.add("band")
    if _bool(needed.get("grid")) or _bool(needed_on_band.get("grid")) or "grid" in status_text:
        reasons.add("grid")
    if _bool(needed.get("mode")) or _bool(needed_on_band.get("mode")) or "new mode" in status_text:
        reasons.add("mode")
    if _bool(needed.get("continent")):
        reasons.add("continent")
    if _bool(needed_on_band.get("continent")):
        reasons.add("band_continent")
    if _bool(needed.get("cq_zone")) or _bool(needed.get("cqZone")):
        reasons.add("cq_zone")
    if _bool(needed_on_band.get("cq_zone")) or _bool(needed_on_band.get("cqZone")):
        reasons.add("band_cq_zone")
    if _bool(needed.get("itu_zone")) or _bool(needed.get("ituZone")):
        reasons.add("itu_zone")
    if _bool(needed_on_band.get("itu_zone")) or _bool(needed_on_band.get("ituZone")):
        reasons.add("band_itu_zone")
    if _bool(needed.get("call")) or call_status == "New Call":
        reasons.add("call")
    for item in references:
        if reference_is_needed(item):
            reasons.add("reference")
            ref_type = str(item.get("type") or "").strip().lower()
            if ref_type:
                reasons.add(ref_type)
    return reasons


def payload_matches_need_filters(payload: Mapping[str, Any], settings: DigitalAutomationSettings) -> bool:
    """Return whether a decoded/spot target matches the enabled hunting reasons."""
    return not payload_need_filter_blockers(payload, settings)


def payload_need_filter_blockers(payload: Mapping[str, Any], settings: DigitalAutomationSettings) -> list[str]:
    """Return operator-readable reasons why a payload does not match need filters."""
    blockers: list[str] = []
    if settings.filter_matrix_enabled:
        continent = str(payload.get("continent") or "").strip().upper()
        if settings.filter_continents and continent and continent not in settings.filter_continents:
            continent_name = {
                "EU": "Europe",
                "AF": "Africa",
                "OC": "Oceania",
                "AS": "Asia",
                "SA": "South America",
                "NA": "North America",
                "AN": "Antarctica",
            }.get(continent, continent)
            blockers.append(f"{continent_name} filter")
        if settings.filter_continents and len(settings.filter_continents) < 7 and not continent:
            blockers.append("continent unknown")
        if settings.filter_lotw_only:
            lotw_value = _first_present(payload, "lotw_member", "lotwMember", "lotw", "lotw_user", "lotwUser")
            if not _bool(lotw_value):
                blockers.append("LoTW-only filter")
        if blockers:
            return blockers

        call_status = normalise_status(payload.get("call_status") or payload.get("callStatus"))
        dxcc_status = normalise_status(payload.get("dxcc_status") or payload.get("dxccStatus"))
        needed = payload.get("needed") if isinstance(payload.get("needed"), Mapping) else {}
        needed_on_band = (
            payload.get("needed_on_band")
            if isinstance(payload.get("needed_on_band"), Mapping)
            else payload.get("neededOnBand")
            if isinstance(payload.get("neededOnBand"), Mapping)
            else {}
        )
        reasons = payload_need_reasons(payload)
        selected_matches = [
            settings.need_reference and bool(needed_reference_hunt_items(payload, settings)),
            settings.filter_new_call and ("call" in reasons or call_status == "New Call" or _bool(needed.get("call"))),
            settings.filter_new_dxcc and ("dxcc" in reasons or dxcc_status in {"ATNO", "Worked"} or _bool(needed.get("dxcc"))),
            settings.filter_new_continent and ("continent" in reasons or _bool(needed.get("continent"))),
            settings.filter_new_grid and ("grid" in reasons or _bool(needed.get("grid"))),
            settings.filter_new_cq_zone and ("cq_zone" in reasons or "cq" in reasons or _bool(needed.get("cq_zone")) or _bool(needed.get("cqZone"))),
            settings.filter_new_itu_zone and ("itu_zone" in reasons or "itu" in reasons or _bool(needed.get("itu_zone")) or _bool(needed.get("ituZone"))),
            settings.filter_band_call and (_bool(needed_on_band.get("call")) or "new band" in call_status.lower()),
            settings.filter_band_dxcc and (_bool(needed_on_band.get("dxcc")) or "new band" in dxcc_status.lower()),
            settings.filter_band_continent and (_bool(needed_on_band.get("continent")) or "band_continent" in reasons),
            settings.filter_band_grid and _bool(needed_on_band.get("grid")),
            settings.filter_band_cq_zone and (_bool(needed_on_band.get("cq_zone")) or _bool(needed_on_band.get("cqZone")) or "band_cq_zone" in reasons),
            settings.filter_band_itu_zone and (_bool(needed_on_band.get("itu_zone")) or _bool(needed_on_band.get("ituZone")) or "band_itu_zone" in reasons),
        ]
        if any(selected_matches):
            return []
        if dxcc_status == "Confirmed" and not (_bool(needed_on_band.get("dxcc")) or "new band" in dxcc_status.lower()):
            blockers.append("DXCC already confirmed")
        elif call_status == "Confirmed" and dxcc_status == "Confirmed":
            blockers.append("call and DXCC already confirmed")
        else:
            blockers.append("not selected by filter matrix")
        return blockers

    enabled_filters = {
        "call": settings.need_call,
        "dxcc": settings.need_dxcc,
        "band": settings.need_band,
        "mode": settings.need_mode,
        "grid": settings.need_grid,
        "reference": settings.need_reference,
        "pota": settings.need_reference,
        "sota": settings.need_reference,
        "iota": settings.need_reference,
        "wwff": settings.need_reference,
        "wwbota": settings.need_reference,
        "bunker": settings.need_reference,
        "arlhs": settings.need_reference,
        "lighthouse": settings.need_reference,
        "county": settings.need_reference,
        "state": settings.need_reference,
        "province": settings.need_reference,
        "award": settings.need_reference,
    }
    if not any(enabled_filters.values()):
        return ["all need filters disabled"]
    reasons = payload_need_reasons(payload)
    if any(enabled_filters.get(reason, False) for reason in reasons):
        return []
    dxcc_status = normalise_status(payload.get("dxcc_status") or payload.get("dxccStatus"))
    call_status = normalise_status(payload.get("call_status") or payload.get("callStatus"))
    if dxcc_status == "Confirmed":
        return ["DXCC already confirmed"]
    if call_status == "Confirmed":
        return ["call already confirmed"]
    return ["not needed by filters"]


def _need_reasons_match_filters(reasons: Iterable[str], settings: DigitalAutomationSettings) -> bool:
    if settings.filter_matrix_enabled:
        enabled_filters = {
            "call": settings.filter_new_call or settings.filter_band_call,
            "dxcc": settings.filter_new_dxcc or settings.filter_band_dxcc,
            "band": any(
                (
                    settings.filter_band_call,
                    settings.filter_band_dxcc,
                    settings.filter_band_continent,
                    settings.filter_band_grid,
                    settings.filter_band_cq_zone,
                    settings.filter_band_itu_zone,
                )
            ),
            "continent": settings.filter_new_continent or settings.filter_band_continent,
            "grid": settings.filter_new_grid or settings.filter_band_grid,
            "cq": settings.filter_new_cq_zone or settings.filter_band_cq_zone,
            "cq_zone": settings.filter_new_cq_zone or settings.filter_band_cq_zone,
            "itu": settings.filter_new_itu_zone or settings.filter_band_itu_zone,
            "itu_zone": settings.filter_new_itu_zone or settings.filter_band_itu_zone,
            "reference": settings.need_reference,
            "pota": settings.need_reference,
            "sota": settings.need_reference,
            "iota": settings.need_reference,
            "wwff": settings.need_reference,
            "wwbota": settings.need_reference,
            "bunker": settings.need_reference,
            "arlhs": settings.need_reference,
            "lighthouse": settings.need_reference,
            "county": settings.need_reference,
            "state": settings.need_reference,
            "province": settings.need_reference,
            "award": settings.need_reference,
        }
        return any(enabled_filters.get(str(reason).strip().lower(), False) for reason in reasons)

    enabled_filters = {
        "call": settings.need_call,
        "dxcc": settings.need_dxcc,
        "band": settings.need_band,
        "mode": settings.need_mode,
        "grid": settings.need_grid,
        "reference": settings.need_reference,
        "pota": settings.need_reference,
        "sota": settings.need_reference,
        "iota": settings.need_reference,
        "wwff": settings.need_reference,
        "wwbota": settings.need_reference,
        "bunker": settings.need_reference,
        "arlhs": settings.need_reference,
        "lighthouse": settings.need_reference,
        "county": settings.need_reference,
        "state": settings.need_reference,
        "province": settings.need_reference,
        "award": settings.need_reference,
    }
    return any(enabled_filters.get(str(reason).strip().lower(), False) for reason in reasons)


def _prior_work_has_enabled_slot_need(reasons: Iterable[str], settings: DigitalAutomationSettings) -> bool:
    """Worked/confirmed calls may still be eligible for non-call slot needs."""
    slot_reasons = {
        "dxcc",
        "band",
        "mode",
        "grid",
        "continent",
        "cq_zone",
        "itu_zone",
        "band_continent",
        "band_cq_zone",
        "band_itu_zone",
        "reference",
        "pota",
        "sota",
        "iota",
        "wwff",
        "wwbota",
        "bunker",
        "arlhs",
        "lighthouse",
        "county",
        "state",
        "province",
        "award",
    }
    non_call_reasons = {
        str(reason).strip().lower()
        for reason in reasons
        if str(reason).strip().lower() in slot_reasons
    }
    return _need_reasons_match_filters(non_call_reasons, settings)


def _frequency_mhz_from_status(payload: Mapping[str, Any]) -> Optional[float]:
    value = _first_present(
        payload,
        "dialFrequency",
        "dial_frequency",
        "frequency_hz",
        "frequency",
        "frequency_mhz",
    )
    parsed = _float(value)
    if parsed is None or parsed <= 0:
        return None
    if parsed >= 1_000_000:
        return parsed / 1_000_000.0
    if parsed >= 1000:
        return parsed / 1000.0
    return parsed


def _target_from_mapping(row: Mapping[str, Any]) -> Optional[DigitalTarget]:
    data = dict(row or {})
    call = str(data.get("call") or data.get("callsign") or "").strip().upper()
    mode = normalise_mode(data.get("mode"))
    band = str(data.get("band") or "").strip()
    key = str(data.get("key") or target_key(call, band, mode)).strip()
    if not key or not call:
        return None
    source = str(data.get("source") or "decoded")
    grid = normalise_grid_value(data.get("grid") or "")
    raw_reasons = data.get("need_reasons") or data.get("needed_reasons") or []
    if isinstance(raw_reasons, str):
        raw_reasons = [token.strip() for token in raw_reasons.replace(",", "\n").splitlines()]

    fields = {field.name for field in dataclass_fields(DigitalTarget)}
    cleaned = {name: data.get(name) for name in fields if name in data}
    cleaned.update({
        "key": key,
        "call": call,
        "target_id": str(data.get("target_id") or target_identity(call, band, mode, source, grid)),
        "command_id": str(data.get("command_id") or ""),
        "band": band,
        "mode": mode,
        "source": source,
        "message": str(data.get("message") or ""),
        "country": str(data.get("country") or ""),
        "continent": str(data.get("continent") or ""),
        "cq_zone": str(data.get("cq_zone") or ""),
        "itu_zone": str(data.get("itu_zone") or ""),
        "status_source": str(data.get("status_source") or ""),
        "reference_items": normalise_reference_items(data),
        "call_status": canonical_call_status(data.get("call_status"), data.get("dxcc_status")),
        "dxcc_status": normalise_status(data.get("dxcc_status")),
        "need_reasons": {
            str(reason).strip().lower()
            for reason in raw_reasons
            if str(reason).strip()
        },
        "score": _int(data.get("score"), 0),
        "spot_score": _int(data.get("spot_score"), 0, low=0, high=100),
        "attempts": _int(data.get("attempts"), 0, low=0),
        "campaign_count": _int(data.get("campaign_count"), 0, low=0),
        "state": str(data.get("state") or "queued"),
        "lifecycle": str(data.get("lifecycle") or data.get("state") or "queued"),
        "active_state": str(data.get("active_state") or "idle"),
        "reason": str(data.get("reason") or ""),
        "skip_reason": str(data.get("skip_reason") or ""),
        "completion_reason": str(data.get("completion_reason") or ""),
        "heard": _bool(data.get("heard"), False),
        "direct_caller": _bool(data.get("direct_caller"), False),
    })

    for name in (
        "created_at",
        "updated_at",
        "first_heard_at",
        "last_heard_at",
        "heard_slot_start_at",
        "last_attempt_at",
        "backoff_until",
        "last_command_at",
        "return_command_at",
        "command_ack_at",
        "campaign_started_at",
        "campaign_expires_at",
    ):
        cleaned[name] = _datetime(cleaned.get(name))

    cleaned["created_at"] = cleaned.get("created_at") or utc_now()
    cleaned["updated_at"] = cleaned.get("updated_at") or cleaned["created_at"]
    cleaned["dxcc"] = _optional_int(cleaned.get("dxcc"), None)
    cleaned["snr"] = _float(cleaned.get("snr"))
    cleaned["audio_offset"] = _optional_int(cleaned.get("audio_offset"), None)
    cleaned["dial_frequency"] = _float(cleaned.get("dial_frequency"))
    cleaned["propagation_score"] = _float(cleaned.get("propagation_score"))
    cleaned["origin_dial_frequency"] = _float(cleaned.get("origin_dial_frequency"))
    cleaned["grid"] = normalise_grid_value(cleaned.get("grid") or "")

    return DigitalTarget(**cleaned)
