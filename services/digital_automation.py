"""Backend-owned Digital mode automation controller.

The browser can render controls, but target ownership, queue priority, retry
state, duplicate protection, and dwell timing belong in the backend so they
survive UI reloads and coordinate decoded stations, spots, Wavelog status, and
radio state from one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping, Optional


SUPPORTED_AUTOMATION_MODES = {"FT8", "FT4"}
CALL_RE = re.compile(r"^[A-Z0-9][A-Z0-9/]{2,}$")
GRID_RE = re.compile(r"^[A-R]{2}\d{2}([A-X]{2})?$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


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


def status_has_prior_call_work(status: Any) -> bool:
    return normalise_status(status).lower() in {
        "worked",
        "confirmed",
        "new band",
        "new mode",
        "new band+mode",
    }


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
    return [token.strip("<>").upper() for token in re.split(r"\s+", text.strip()) if token]


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


@dataclass
class DigitalAutomationSettings:
    enabled: bool = False
    spot_hunt_enabled: bool = False
    band_hopping: bool = False
    mode_switching: bool = False
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
    priority: str = "last"
    band_plan: str = "05:20m,17m,15m,12m,10m\n20:30m,40m,80m,160m"

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
        self.band_hopping = _bool(automation.get("bandHopping", automation.get("band_hopping")), self.band_hopping)
        self.mode_switching = _bool(automation.get("modeSwitching", automation.get("mode_switching")), self.mode_switching)
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
            automation.get("maxAttemptsPerTarget", automation.get("max_attempts_per_target")),
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
        self.priority = str(automation.get("priority", self.priority) or self.priority)
        self.band_plan = str(automation.get("bandPlan", automation.get("band_plan", self.band_plan)) or self.band_plan)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "spot_hunt_enabled": self.spot_hunt_enabled,
            "band_hopping": self.band_hopping,
            "mode_switching": self.mode_switching,
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
            "priority": self.priority,
            "band_plan": self.band_plan,
        }


@dataclass
class DigitalTarget:
    key: str
    call: str
    band: str = ""
    mode: str = "FT8"
    source: str = "decoded"
    message: str = ""
    grid: str = ""
    country: str = ""
    call_status: str = "Unknown"
    dxcc_status: str = "Unknown"
    score: int = 0
    snr: Optional[float] = None
    audio_offset: Optional[int] = None
    dial_frequency: Optional[float] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    first_heard_at: Optional[datetime] = None
    last_heard_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    backoff_until: Optional[datetime] = None
    attempts: int = 0
    state: str = "queued"
    reason: str = ""
    heard: bool = False

    def is_backed_off(self, now: Optional[datetime] = None) -> bool:
        return bool(self.backoff_until and self.backoff_until > (now or utc_now()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "call": self.call,
            "band": self.band,
            "mode": self.mode,
            "source": self.source,
            "message": self.message,
            "grid": self.grid,
            "country": self.country,
            "call_status": self.call_status,
            "dxcc_status": self.dxcc_status,
            "score": self.score,
            "snr": self.snr,
            "audio_offset": self.audio_offset,
            "dial_frequency": self.dial_frequency,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "first_heard_at": _iso(self.first_heard_at),
            "last_heard_at": _iso(self.last_heard_at),
            "last_attempt_at": _iso(self.last_attempt_at),
            "backoff_until": _iso(self.backoff_until),
            "attempts": self.attempts,
            "state": self.state,
            "reason": self.reason,
            "heard": self.heard,
        }


class DigitalAutomationController:
    """Own target selection and retry state for the built-in Digital client."""

    def __init__(
        self,
        *,
        mycall: str = "OM0RX",
        settings: Optional[DigitalAutomationSettings] = None,
        max_targets: int = 250,
    ) -> None:
        self.mycall = str(mycall or "OM0RX").upper()
        self.settings = settings or DigitalAutomationSettings()
        self.max_targets = max_targets
        self.targets: dict[str, DigitalTarget] = {}
        self.active_target_key: Optional[str] = None
        self.last_decision: dict[str, Any] = {"decision": "idle", "reason": "controller initialised"}

    def apply_operator_settings(self, operator_settings: Optional[Mapping[str, Any]]) -> None:
        self.settings.apply_operator_settings(operator_settings or {})
        self.last_decision = {"decision": "settings-updated", "settings": self.settings.to_dict()}

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
        heard = _bool(incoming.get("heard"), str(incoming.get("source", "")).lower() == "decoded")
        return self._upsert_target(incoming, heard=heard)

    def _upsert_target(self, payload: Mapping[str, Any], *, heard: bool) -> Optional[DigitalTarget]:
        mode = normalise_mode(payload.get("mode"))
        if mode not in self.settings.allowed_modes:
            self.last_decision = {
                "decision": "skip",
                "reason": "mode-disabled",
                "mode": mode,
            }
            return None

        call = extract_callsign(payload, self.mycall)
        if not call or call == self.mycall:
            self.last_decision = {"decision": "skip", "reason": "no-workable-callsign"}
            return None

        snr = _float(payload.get("snr"))
        if heard and snr is not None and snr < self.settings.min_signal:
            self.last_decision = {
                "decision": "skip",
                "reason": "below-min-signal",
                "call": call,
                "snr": snr,
                "min_signal": self.settings.min_signal,
            }
            return None

        band = str(payload.get("band") or "").strip()
        key = target_key(call, band, mode)
        score = score_payload(payload)
        call_status = normalise_status(payload.get("call_status") or payload.get("callStatus"))
        dxcc_status = normalise_status(payload.get("dxcc_status") or payload.get("dxccStatus"))
        source = str(payload.get("source") or "decoded")
        message = str(payload.get("message") or "")
        if source == "decoded" and message and not _is_auto_call_start_message(message):
            self.last_decision = {
                "decision": "skip",
                "reason": "not-auto-call-start-message",
                "call": call,
                "band": band,
                "mode": mode,
                "message": message,
            }
            return None
        if self.settings.avoid_logged and status_has_prior_call_work(call_status):
            target = self.targets.get(key)
            if target and target.state not in {"selected", "calling"}:
                target.state = "skipped"
                target.reason = "already-worked-call"
                target.updated_at = utc_now()
            self.last_decision = {
                "decision": "skip",
                "reason": "already-worked-call",
                "call": call,
                "band": band,
                "mode": mode,
                "call_status": call_status,
                "dxcc_status": dxcc_status,
            }
            return None

        now = utc_now()
        target = self.targets.get(key)
        if not target:
            target = DigitalTarget(key=key, call=call, band=band, mode=mode)
            self.targets[key] = target
        target.source = source or target.source or "decoded"
        if message:
            target.message = message
        target.grid = str(payload.get("grid") or payload.get("gridsquare") or target.grid or "").upper()
        target.country = str(payload.get("country") or payload.get("dxcc_name") or target.country or "")
        target.call_status = call_status
        target.dxcc_status = dxcc_status
        target.score = max(target.score, score)
        target.snr = snr if snr is not None else target.snr
        target.audio_offset = _int(payload.get("freq", payload.get("audio_offset")), target.audio_offset or 0) or None
        target.dial_frequency = _float(payload.get("base_frequency", payload.get("frequency_mhz", payload.get("frequency"))))
        target.updated_at = now
        if heard:
            target.heard = True
            target.first_heard_at = target.first_heard_at or now
            target.last_heard_at = now
            if target.state in {"listening", "queued"}:
                target.state = "heard"
        elif target.state == "queued":
            target.state = "listening" if self.settings.require_heard_before_call else "queued"
        target.reason = self._target_reason(target)

        self._trim_targets()
        self.last_decision = {
            "decision": "queued",
            "call": call,
            "band": band,
            "mode": mode,
            "score": target.score,
            "state": target.state,
            "reason": target.reason,
        }
        return target

    def next_target(
        self,
        now: Optional[datetime] = None,
        *,
        cq_only: bool = False,
        auto_call_start_only: bool = False,
    ) -> Optional[DigitalTarget]:
        now = now or utc_now()
        candidates = []
        for target in self.targets.values():
            if target.state in {"done", "skipped"}:
                continue
            if self.settings.avoid_logged and status_has_prior_call_work(target.call_status):
                target.state = "skipped"
                target.reason = "already-worked-call"
                target.updated_at = now
                continue
            if auto_call_start_only and target.source != "spot" and not _is_auto_call_start_message(target.message):
                target.state = "skipped"
                target.reason = "not-auto-call-start-message"
                target.updated_at = now
                continue
            if cq_only and not _is_cq_message(target.message):
                continue
            if target.is_backed_off(now):
                continue
            if (
                target.last_attempt_at
                and (now - target.last_attempt_at).total_seconds() < self.settings.dwell_seconds
            ):
                continue
            if self.settings.require_heard_before_call and not target.heard:
                continue
            if target.score <= 0 and self.settings.avoid_logged:
                continue
            candidates.append(target)

        if not candidates:
            self.active_target_key = None
            self.last_decision = {"decision": "idle", "reason": "no-eligible-targets"}
            return None

        candidates.sort(
            key=lambda target: (
                target.score,
                target.snr if self.settings.priority == "signal" and target.snr is not None else 0,
                target.updated_at.timestamp(),
            ),
            reverse=True,
        )
        chosen = candidates[0]
        chosen.state = "selected"
        self.active_target_key = chosen.key
        self.last_decision = {
            "decision": "selected",
            "call": chosen.call,
            "band": chosen.band,
            "mode": chosen.mode,
            "score": chosen.score,
            "reason": chosen.reason,
        }
        return chosen

    def record_attempt(self, key: str) -> Optional[DigitalTarget]:
        target = self.targets.get(key)
        if not target:
            self.last_decision = {"decision": "skip", "reason": "attempt-target-missing", "key": key}
            return None
        now = utc_now()
        if (
            target.last_attempt_at
            and (now - target.last_attempt_at).total_seconds() > self.settings.retry_reset_minutes * 60
        ):
            target.attempts = 0
        target.attempts += 1
        target.last_attempt_at = now
        target.state = "calling"
        if target.attempts >= self.settings.max_attempts_per_target:
            target.state = "backoff"
            target.backoff_until = datetime.fromtimestamp(
                now.timestamp() + self.settings.retry_backoff_minutes * 60,
                timezone.utc,
            )
        self.last_decision = {
            "decision": "attempt-recorded",
            "key": key,
            "attempts": target.attempts,
            "state": target.state,
            "backoff_until": _iso(target.backoff_until),
        }
        return target

    def abandon_active_target(self, *, reason: str = "operator-aborted") -> Optional[DigitalTarget]:
        """Back off the currently selected/calling target without disabling automation."""
        if not self.active_target_key:
            self.last_decision = {"decision": "idle", "reason": "no-active-target-to-abandon"}
            return None
        target = self.targets.get(self.active_target_key)
        self.active_target_key = None
        if not target:
            self.last_decision = {"decision": "idle", "reason": "active-target-missing"}
            return None
        now = utc_now()
        target.state = "backoff"
        target.reason = reason
        target.updated_at = now
        target.backoff_until = datetime.fromtimestamp(
            now.timestamp() + self.settings.retry_backoff_minutes * 60,
            timezone.utc,
        )
        self.last_decision = {
            "decision": "abandoned",
            "key": target.key,
            "call": target.call,
            "reason": reason,
            "backoff_until": _iso(target.backoff_until),
        }
        return target

    def mark_done(self, key: str, *, reason: str = "qso-complete") -> Optional[DigitalTarget]:
        target = self.targets.get(key)
        if target:
            target.state = "done"
            target.reason = reason
            target.updated_at = utc_now()
            if self.active_target_key == key:
                self.active_target_key = None
            self.last_decision = {"decision": "done", "key": key, "reason": reason}
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
            target.state = "done"
            target.reason = reason
            target.updated_at = utc_now()
            completed.append(target)
            if self.active_target_key == target.key:
                self.active_target_key = None
        if completed:
            self.last_decision = {
                "decision": "done",
                "call": call_upper,
                "count": len(completed),
                "reason": reason,
            }
        return completed

    def status(self) -> dict[str, Any]:
        now = utc_now()
        active = self.targets.get(self.active_target_key) if self.active_target_key else None
        queue = sorted(
            self.targets.values(),
            key=lambda target: (target.score, target.updated_at.timestamp()),
            reverse=True,
        )
        return {
            "enabled": self.settings.enabled,
            "settings": self.settings.to_dict(),
            "active_target": active.to_dict() if active else None,
            "queue_length": len(self.targets),
            "eligible_count": sum(
                1
                for target in self.targets.values()
                if target.state not in {"done", "skipped"}
                and not target.is_backed_off(now)
                and not (self.settings.avoid_logged and status_has_prior_call_work(target.call_status))
                and (target.heard or not self.settings.require_heard_before_call)
                and (target.score > 0 or not self.settings.avoid_logged)
            ),
            "targets": [target.to_dict() for target in queue[:25]],
            "last_decision": self.last_decision,
        }

    def _target_reason(self, target: DigitalTarget) -> str:
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


def _is_cq_message(message: Any) -> bool:
    tokens = _message_tokens(str(message or ""))
    return bool(tokens and tokens[0] in {"CQ", "QRZ"})


def _is_auto_call_start_message(message: Any) -> bool:
    """Return true only for messages that may start a new Auto Call QSO."""
    return _is_cq_message(message)


def score_payload(payload: Mapping[str, Any]) -> int:
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

    if dxcc_status == "ATNO" or _bool(needed.get("dxcc")):
        return 1000
    if _bool(needed_on_band.get("dxcc")) or "new band" in dxcc_status.lower():
        return 800
    if _bool(needed_on_band.get("call")) or "new band" in call_status.lower():
        return 650
    if _bool(needed.get("grid")) or _bool(needed_on_band.get("grid")) or "grid" in status_text:
        return 500
    if _bool(needed.get("mode")) or _bool(needed_on_band.get("mode")) or "new mode" in status_text:
        return 350
    if _bool(needed.get("call")) or call_status == "New Call":
        return 200
    return 0
