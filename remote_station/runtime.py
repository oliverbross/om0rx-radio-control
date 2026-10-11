"""Hardware runtime and safety boundary for the remote-station agent."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import Any

from radio_control.elecraft import ElecraftManager, band_from_frequency
from radio_control.flex_radio import FlexCtl
from services.elecraft_station import StationActionError, StationCoordinator

from .config import AgentConfig

logger = logging.getLogger(__name__)
PROTOCOL_VERSION = 1
FLEX_SNAPSHOT_WINDOW_SECONDS = 0.2
FLEX_POLL_IDLE_SECONDS = 0.05
ATOMIC_ROUTE_CONFIRM_TIMEOUT_SECONDS = 60.0


class RemoteCommandError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RemoteStationRuntime:
    """Own FLEX and both serial devices without starting the full OM0RX app."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        flex_factory: Callable[[str, int, int], Any] = FlexCtl,
        elecraft_factory: Callable[[], Any] = ElecraftManager,
        coordinator_factory: Callable[..., Any] = StationCoordinator,
    ) -> None:
        self.config = config
        self._flex_factory = flex_factory
        self._elecraft_factory = elecraft_factory
        self._coordinator_factory = coordinator_factory
        self.flex: Any = None
        self.elecraft: Any = None
        self.coordinator: Any = None
        self.radio_snapshot: dict[str, Any] = {
            "connected": False,
            "known": False,
            "stale": True,
            "cw_speed": 25,
        }
        self.started_at = time.time()
        self.last_error: str | None = None
        self._poll_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._command_lock = asyncio.Lock()
        self._revision = 0
        self._last_radio_observation = 0.0
        self._pending_frequency_mode: dict[str, Any] | None = None
        self._active_config_fingerprint = config.fingerprint()
        self._saved_config_fingerprint = self._active_config_fingerprint
        self._idempotency: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()

    async def start(self) -> None:
        self.config.apply_to_radio_config()
        self.flex = self._flex_factory(
            self.config.flex_host,
            self.config.flex_port,
            self.config.flex_slice_id,
        )
        self.flex.preferred_station_name = self.config.flex_station_name
        await asyncio.to_thread(self.flex.connect)
        self.elecraft = self._elecraft_factory()
        await self.elecraft.start()
        self.coordinator = self._coordinator_factory(
            self.elecraft,
            lambda: self.flex,
            lambda: self.radio_snapshot,
            digital_guard=lambda: None,
            recovery_required=True,
            policy_source=self.config.station_policy_source(),
        )
        try:
            await self.coordinator.recover_safe_state()
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 - keep the API alive but TX locked
            self.last_error = f"Safe startup recovery remains unconfirmed: {exc}"
            logger.critical(self.last_error)
        self._stop_event.clear()
        self._poll_task = asyncio.create_task(self._poll_loop(), name="remote_station_radio_poll")
        self._revision += 1

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._poll_task
        self._poll_task = None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.coordinator:
            try:
                await self.coordinator.stop()
            except Exception as exc:  # noqa: BLE001 - continue device cleanup
                logger.critical("Remote station safe shutdown was not confirmed: %s", exc)
        if self.elecraft:
            await self.elecraft.stop()
        if self.flex:
            await asyncio.to_thread(self.flex.close)
        self.radio_snapshot = {
            **self.radio_snapshot,
            "connected": False,
            "known": False,
            "stale": True,
            "updated_at": time.time(),
        }
        self._revision += 1

    @property
    def revision(self) -> int:
        return self._revision

    def note_saved_config(self, config: AgentConfig) -> None:
        """Expose that a validated saved profile is pending process restart."""
        self._saved_config_fingerprint = config.fingerprint()
        self._revision += 1

    async def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                levels = await asyncio.to_thread(
                    partial(
                        self.flex.get_current_levels,
                        timeout=FLEX_SNAPSHOT_WINDOW_SECONDS,
                        apply_antenna_policy=False,
                    )
                )
                if levels:
                    route_ready = self._update_radio_snapshot(levels)
                    self.elecraft.observe_radio_tx_state(
                        self.radio_snapshot.get("mox"),
                        self.radio_snapshot.get("interlock_state"),
                    )
                    if route_ready:
                        await self.elecraft.sync_radio_state(
                            self.radio_snapshot.get("frequency"),
                            self.radio_snapshot.get("mode"),
                        )
                        try:
                            await self.coordinator.follow_observed_radio_route(
                                self.radio_snapshot.get("frequency")
                            )
                            self.last_error = None
                        except Exception as exc:  # noqa: BLE001 - keep healthy FLEX state visible
                            self.last_error = f"Accessory route follow failed: {exc}"
                            logger.warning(self.last_error)
                else:
                    age = time.time() - self._last_radio_observation
                    connected = bool(getattr(self.flex, "sock", None))
                    known = bool(
                        connected and self.radio_snapshot.get("known") is True and age <= 8.0
                    )
                    self.radio_snapshot = {
                        **self.radio_snapshot,
                        "connected": connected,
                        "known": known,
                        "stale": not known,
                        "updated_at": time.time(),
                    }
                self._revision += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect on any driver failure
                self.last_error = str(exc)
                self.radio_snapshot = {
                    **self.radio_snapshot,
                    "connected": False,
                    "known": False,
                    "stale": True,
                    "updated_at": time.time(),
                }
                self._revision += 1
                logger.warning("Remote station poll failed: %s", exc)
                try:
                    await asyncio.to_thread(self.flex.close)
                except Exception as close_exc:  # noqa: BLE001 - poll loop will retry
                    logger.debug("FLEX cleanup after poll failure also failed: %s", close_exc)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=FLEX_POLL_IDLE_SECONDS
                )
            except TimeoutError:
                pass

    def _update_radio_snapshot(self, levels: dict[str, Any]) -> bool:
        observed_at = time.time()
        self._last_radio_observation = observed_at
        mapping = {
            "freq": "frequency",
            "rfpower": "drive",
            "tunepower": "tune_power",
            "miclevel": "mic_level",
            "rx_ant": "rx_antenna",
            "tx_ant": "tx_antenna",
        }
        normalized = {mapping.get(key, key): value for key, value in levels.items()}
        # Keep the driver's canonical antenna keys for the station-path safety
        # evaluator while also publishing the descriptive API field names.
        for driver_key, api_key in (("rx_ant", "rx_antenna"), ("tx_ant", "tx_antenna")):
            if api_key in normalized:
                normalized[driver_key] = normalized[api_key]
        normalized.setdefault("frequency", getattr(self.flex, "current_freq", None))
        normalized.setdefault("mode", getattr(self.flex, "current_mode", None))
        normalized.setdefault("drive", getattr(self.flex, "current_rfpower", None))
        normalized.setdefault("mox", getattr(self.flex, "current_mox", None))
        normalized.setdefault(
            "interlock_state", getattr(self.flex, "current_interlock_state", None)
        )
        polled_frequency = normalized.get("frequency") if "freq" in levels else None
        polled_mode = normalized.get("mode") if "mode" in levels else None
        station_bound = bool(getattr(self.flex, "bound_gui_client_handle", None))
        normalized["station_name"] = self.config.flex_station_name
        normalized["station_bound"] = station_bound
        getter = getattr(self.flex, "get_slice_states", None)
        slices = getter() if callable(getter) else []
        vfos: dict[str, dict[str, Any]] = {}
        active_receive: dict[str, Any] | None = None
        transmit: dict[str, Any] | None = None
        normalized_slices: list[dict[str, Any]] = []
        for raw_slice in slices:
            item = dict(raw_slice)
            frequency = item.get("frequency")
            if frequency is not None:
                item["frequency_hz"] = round(float(frequency) * 1_000_000)
            letter = str(item.get("index_letter") or "").upper()
            if letter:
                vfos[letter] = item
            if item.get("active") is True and active_receive is None:
                active_receive = item
            if item.get("transmit") is True and transmit is None:
                transmit = item
            normalized_slices.append(item)
        active_receive = active_receive or vfos.get("A")
        transmit = transmit or active_receive
        if transmit and transmit.get("frequency") is not None:
            normalized["frequency"] = transmit["frequency"]
            normalized["mode"] = transmit.get("mode") or normalized.get("mode")
        # FLEX transmit/interlock telemetry can report tx_antenna=INVALID even
        # while the bound Maestro transmit slice has an authoritative ANT1/ANT2/
        # XVTR route. Use that slice only when the aggregate value is unusable;
        # a different valid aggregate value remains visible and fails policy
        # validation rather than being hidden.
        aggregate_tx_ant = str(normalized.get("tx_antenna") or "").strip().upper()
        slice_tx_ant = str((transmit or {}).get("tx_antenna") or "").strip().upper()
        valid_tx_antennas = {"ANT1", "ANT2", "XVTR"}
        if aggregate_tx_ant not in valid_tx_antennas and slice_tx_ant in valid_tx_antennas:
            normalized["tx_antenna"] = slice_tx_ant
            normalized["tx_ant"] = slice_tx_ant
        if normalized_slices:
            normalized.update(
                {
                    "slices": normalized_slices,
                    "vfos": vfos,
                    "active_receive": active_receive,
                    "transmit": transmit,
                }
            )
        known = normalized.get("frequency") is not None and station_bound
        candidate = {
            **self.radio_snapshot,
            **normalized,
            "connected": True,
            "known": known,
            "stale": not known,
            "model": "FLEX-8400",
            "observed_at": datetime.fromtimestamp(observed_at, tz=UTC).isoformat(),
            "updated_at": observed_at,
        }
        pending = self._pending_frequency_mode
        if pending is not None:
            target_frequency = float(pending["frequency"])
            target_mode = str(pending["mode"])
            observed_frequency = candidate.get("frequency")
            observed_mode = str(candidate.get("mode") or "").upper()
            polled_target_confirmed = (
                polled_frequency is not None
                and abs(float(polled_frequency) - target_frequency) <= 0.000001
                and str(polled_mode or "").upper() == target_mode
            )
            target_confirmed = polled_target_confirmed or (
                observed_frequency is not None
                and abs(float(observed_frequency) - target_frequency) <= 0.000001
                and observed_mode == target_mode
            )
            if target_confirmed:
                if polled_target_confirmed:
                    slice_id = int(pending["slice_id"])

                    def confirmed_slice(item: dict[str, Any]) -> dict[str, Any]:
                        updated = dict(item)
                        if int(updated.get("slice_id", -1)) == slice_id:
                            updated.update(
                                {
                                    "frequency": target_frequency,
                                    "frequency_hz": round(target_frequency * 1_000_000),
                                    "mode": target_mode,
                                }
                            )
                        return updated

                    candidate["frequency"] = target_frequency
                    candidate["mode"] = target_mode
                    if "slices" in candidate:
                        candidate["slices"] = [
                            confirmed_slice(item) for item in candidate["slices"]
                        ]
                    if "vfos" in candidate:
                        candidate["vfos"] = {
                            key: confirmed_slice(item)
                            for key, item in candidate["vfos"].items()
                        }
                    for key in ("active_receive", "transmit"):
                        if isinstance(candidate.get(key), dict):
                            candidate[key] = confirmed_slice(candidate[key])
                candidate.pop("route_change_pending", None)
                self._pending_frequency_mode = None
            else:
                # FLEX can acknowledge the mode before its slice-frequency
                # subscription reports the tune. Keep the last coherent route
                # visible until both values are observed together. Safety
                # telemetry above (especially MOX/interlock) remains live.
                for key in (
                    "frequency",
                    "mode",
                    "slices",
                    "vfos",
                    "active_receive",
                    "transmit",
                ):
                    if key in self.radio_snapshot:
                        candidate[key] = self.radio_snapshot[key]
                    else:
                        candidate.pop(key, None)
                age_seconds = max(0.0, observed_at - float(pending["started_at"]))
                candidate["route_change_pending"] = {
                    "frequency_hz": round(target_frequency * 1_000_000),
                    "mode": target_mode,
                    "vfo": pending["vfo"],
                    "age_seconds": round(age_seconds, 3),
                }
                if age_seconds > ATOMIC_ROUTE_CONFIRM_TIMEOUT_SECONDS:
                    candidate["known"] = False
                    candidate["stale"] = True
                    self.last_error = (
                        "FLEX atomic route change remains unconfirmed after "
                        f"{ATOMIC_ROUTE_CONFIRM_TIMEOUT_SECONDS:.0f} seconds"
                    )
                self.radio_snapshot = candidate
                return False
        self.radio_snapshot = candidate
        return True

    @staticmethod
    def _required_bool(arguments: dict[str, Any], name: str) -> bool:
        value = arguments.get(name)
        if type(value) is not bool:
            raise RemoteCommandError(
                "command-argument-invalid",
                f"{name} must be true or false",
                status_code=422,
            )
        return value

    @staticmethod
    def _required_int(arguments: dict[str, Any], name: str) -> int:
        value = arguments.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise RemoteCommandError(
                "command-argument-invalid",
                f"{name} must be an integer",
                status_code=422,
            )
        return value

    def snapshot(self) -> dict[str, Any]:
        station = self.coordinator.snapshot() if self.coordinator else None
        elecraft = self.elecraft.snapshot() if self.elecraft else None
        return copy.deepcopy(
            {
                "protocol_version": PROTOCOL_VERSION,
                "revision": self._revision,
                "agent": {
                    "started_at": self.started_at,
                    "uptime_seconds": max(0.0, time.time() - self.started_at),
                    "last_error": self.last_error,
                    "config": {
                        "path": str(self.config.path),
                        "active_fingerprint": self._active_config_fingerprint,
                        "saved_fingerprint": self._saved_config_fingerprint,
                        "restart_required": (
                            self._saved_config_fingerprint
                            != self._active_config_fingerprint
                        ),
                    },
                },
                "radio": self.radio_snapshot,
                "elecraft": elecraft,
                "station": station,
                "capabilities": {
                    "commands": [
                        "set_frequency_hz",
                        "set_frequency_mode",
                        "set_mode",
                        "set_ptt",
                        "set_rit",
                        "set_xit",
                        "set_split",
                        "set_receive_vfo",
                        "set_rf_power",
                        "set_cw_speed",
                        "send_cw",
                        "clear_cw",
                        "add_spot",
                        "station_standby",
                        "station_operate",
                        "station_tune",
                        "station_cancel",
                    ],
                    "ptt_requires_commissioning": True,
                    "raw_tune_on_available": False,
                },
            }
        )

    def _slice_for_vfo(
        self, arguments: dict[str, Any], *, default: str = "A"
    ) -> tuple[str, dict[str, Any]]:
        vfo = str(arguments.get("vfo") or default).strip().upper()
        if vfo not in {"A", "B"}:
            raise RemoteCommandError("vfo-invalid", "vfo must be A or B", status_code=422)
        if self.config.flex_station_name and not getattr(
            self.flex, "bound_gui_client_handle", None
        ):
            raise RemoteCommandError(
                "flex-station-unbound",
                f"FLEX station {self.config.flex_station_name!r} is not bound",
                status_code=503,
            )
        getter = getattr(self.flex, "get_slice_states", None)
        slices = getter() if callable(getter) else []
        for state in slices:
            if str(state.get("index_letter") or "").upper() == vfo:
                return vfo, state
        if vfo == "A":
            return vfo, {
                "slice_id": self.flex.slice_id,
                "index_letter": "A",
                "frequency": getattr(self.flex, "current_freq", None),
                "mode": getattr(self.flex, "current_mode", None),
            }
        raise RemoteCommandError(
            "vfo-unavailable",
            "FLEX slice B is not available for the bound station",
            status_code=409,
        )

    def _set_slice_offset(self, slice_id: int, kind: str, enabled: bool, offset_hz: int) -> bool:
        if not self.flex._send(f"slice set {slice_id} {kind}_on={'1' if enabled else '0'}"):
            return False
        return not enabled or self.flex._send(f"slice set {slice_id} {kind}_freq={offset_hz}")

    async def execute(
        self, request_id: str, command: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        fingerprint = hashlib.sha256(
            json.dumps(
                {"command": command, "arguments": arguments}, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        cached = self._idempotency.get(request_id)
        if cached:
            if cached[0] != fingerprint:
                raise RemoteCommandError(
                    "request-id-reused",
                    "The request ID was already used for different command content",
                    status_code=422,
                )
            return {**copy.deepcopy(cached[1]), "replayed": True}

        async with self._command_lock:
            cached = self._idempotency.get(request_id)
            if cached:
                if cached[0] != fingerprint:
                    raise RemoteCommandError(
                        "request-id-reused",
                        "The request ID was already used for different command content",
                        status_code=422,
                    )
                return {**copy.deepcopy(cached[1]), "replayed": True}
            result = await self._execute_once(command, arguments)
            self._revision += 1
            response = {
                "success": True,
                "request_id": request_id,
                "result": result,
                "state": self.snapshot(),
                "replayed": False,
            }
            self._idempotency[request_id] = (fingerprint, copy.deepcopy(response))
            self._idempotency.move_to_end(request_id)
            while len(self._idempotency) > 256:
                self._idempotency.popitem(last=False)
            return response

    async def _execute_once(self, command: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.flex or not self.coordinator:
            raise RemoteCommandError(
                "agent-not-ready", "Station hardware runtime is unavailable", status_code=503
            )
        normalized = str(command or "").strip().lower()
        try:
            if normalized == "add_spot":
                frequency_hz = self._required_int(arguments, "frequency_hz")
                if not 100_000 <= frequency_hz <= 60_000_000:
                    raise RemoteCommandError(
                        "spot-frequency-invalid",
                        "Spot frequency must be between 100 kHz and 60 MHz",
                        status_code=422,
                    )

                def text_argument(name: str, maximum: int, *, required: bool = False) -> str:
                    value = arguments.get(name, "")
                    if not isinstance(value, str):
                        raise RemoteCommandError(
                            "command-argument-invalid",
                            f"{name} must be text",
                            status_code=422,
                        )
                    value = value.strip()
                    if (required and not value) or len(value) > maximum or any(
                        ord(character) < 32 or ord(character) > 126 or character == "|"
                        for character in value
                    ):
                        raise RemoteCommandError(
                            "spot-text-invalid",
                            f"{name} contains invalid spot text",
                            status_code=422,
                        )
                    return value

                callsign = text_argument("callsign", 32, required=True).upper()
                if re.fullmatch(r"[A-Z0-9/.-]+", callsign) is None:
                    raise RemoteCommandError(
                        "spot-callsign-invalid", "Spot callsign is invalid", status_code=422
                    )
                mode = text_argument("mode", 16).upper()
                source = text_argument("source", 32) or "RUMlogNG"
                spotter = text_argument("spotter", 32).upper()
                comment = text_argument("comment", 96)
                timestamp = self._required_int(arguments, "timestamp")
                lifetime = self._required_int(arguments, "lifetime_seconds")
                priority = self._required_int(arguments, "priority")
                color = text_argument("color", 7).upper()
                if not 0 <= timestamp <= 4_102_444_800:
                    raise RemoteCommandError(
                        "spot-timestamp-invalid", "Spot timestamp is invalid", status_code=422
                    )
                if not 30 <= lifetime <= 86_400:
                    raise RemoteCommandError(
                        "spot-lifetime-invalid",
                        "Spot lifetime must be between 30 and 86400 seconds",
                        status_code=422,
                    )
                if not 1 <= priority <= 5:
                    raise RemoteCommandError(
                        "spot-priority-invalid", "Spot priority must be 1 through 5", status_code=422
                    )
                if re.fullmatch(r"#[0-9A-F]{6}", color) is None:
                    raise RemoteCommandError(
                        "spot-color-invalid", "Spot color must be #RRGGBB", status_code=422
                    )
                accepted = await asyncio.to_thread(
                    self.flex.add_spot,
                    frequency_hz / 1_000_000.0,
                    callsign,
                    mode,
                    source,
                    spotter,
                    comment,
                    lifetime,
                    priority,
                    color,
                    timestamp,
                )
                if accepted is not True:
                    raise RemoteCommandError(
                        "spot-add-rejected", "FLEX rejected the panadapter spot", status_code=503
                    )
                return {"accepted": True, "callsign": callsign, "frequency_hz": frequency_hz}
            if normalized == "set_frequency_hz":
                frequency_hz = self._required_int(arguments, "frequency_hz")
                frequency_mhz = frequency_hz / 1_000_000.0
                if not band_from_frequency(frequency_mhz):
                    raise RemoteCommandError(
                        "frequency-outside-policy",
                        "Frequency is outside the configured station bands",
                        status_code=422,
                    )
                vfo, slice_state = self._slice_for_vfo(arguments)
                slice_id = int(slice_state["slice_id"])
                await self.coordinator.execute_flex_route_change(
                    f"remote-frequency-{vfo.lower()}",
                    lambda: self.flex._send(f"slice tune {slice_id} {frequency_mhz:.6f}"),
                )
                return {"frequency_hz": frequency_hz, "vfo": vfo}
            if normalized == "set_frequency_mode":
                frequency_hz = self._required_int(arguments, "frequency_hz")
                frequency_mhz = frequency_hz / 1_000_000.0
                if not band_from_frequency(frequency_mhz):
                    raise RemoteCommandError(
                        "frequency-outside-policy",
                        "Frequency is outside the configured station bands",
                        status_code=422,
                    )
                mode = str(arguments.get("mode") or "").strip().upper()
                if not mode or len(mode) > 12 or not mode.replace("-", "").isalnum():
                    raise RemoteCommandError(
                        "mode-invalid", "Radio mode is invalid", status_code=422
                    )
                vfo, slice_state = self._slice_for_vfo(arguments)
                slice_id = int(slice_state["slice_id"])
                self._pending_frequency_mode = {
                    "frequency": frequency_mhz,
                    "mode": mode,
                    "vfo": vfo,
                    "slice_id": slice_id,
                    "started_at": time.time(),
                }
                self.radio_snapshot = {
                    **self.radio_snapshot,
                    "route_change_pending": {
                        "frequency_hz": frequency_hz,
                        "mode": mode,
                        "vfo": vfo,
                        "age_seconds": 0.0,
                    },
                }

                def apply_frequency_and_mode() -> bool:
                    mode_ok = self.flex._send(f"slice set {slice_id} mode={mode}")
                    if not mode_ok:
                        return False
                    frequency_ok = self.flex._send(
                        f"slice tune {slice_id} {frequency_mhz:.6f}"
                    )
                    if frequency_ok and self.flex._send("sub slice all"):
                        self.flex.last_resubscribe_time = time.time()
                    return bool(frequency_ok)

                await self.coordinator.execute_flex_route_change(
                    f"remote-frequency-mode-{vfo.lower()}",
                    apply_frequency_and_mode,
                )
                return {"frequency_hz": frequency_hz, "mode": mode, "vfo": vfo}
            if normalized == "set_mode":
                mode = str(arguments.get("mode") or "").strip().upper()
                if not mode or len(mode) > 12 or not mode.replace("-", "").isalnum():
                    raise RemoteCommandError(
                        "mode-invalid", "Radio mode is invalid", status_code=422
                    )
                vfo, slice_state = self._slice_for_vfo(arguments)
                slice_id = int(slice_state["slice_id"])
                await self.coordinator.execute_flex_route_change(
                    f"remote-mode-{vfo.lower()}",
                    lambda: self.flex._send(f"slice set {slice_id} mode={mode}"),
                )
                return {"mode": mode, "vfo": vfo}
            if normalized == "set_ptt":
                enabled = self._required_bool(arguments, "enabled")
                if enabled:
                    await self.coordinator.execute_raw_flex_tx(
                        "mox", lambda: self.flex._send("xmit 1")
                    )
                elif not await asyncio.to_thread(self.flex._send, "xmit 0"):
                    raise RemoteCommandError(
                        "ptt-off-rejected", "FLEX did not accept PTT off", status_code=503
                    )
                return {"ptt": enabled}
            if normalized in {"set_rit", "set_xit"}:
                enabled = self._required_bool(arguments, "enabled")
                offset_hz = self._required_int(arguments, "offset_hz")
                if not -9999 <= offset_hz <= 9999:
                    raise RemoteCommandError(
                        "offset-invalid",
                        "RIT/XIT offset must be between -9999 and 9999 Hz",
                        status_code=422,
                    )
                vfo, slice_state = self._slice_for_vfo(arguments)
                slice_id = int(slice_state["slice_id"])
                kind = "rit" if normalized == "set_rit" else "xit"
                operation = lambda: self._set_slice_offset(slice_id, kind, enabled, offset_hz)
                if normalized == "set_xit":
                    accepted = await self.coordinator.execute_flex_route_change(
                        f"remote-xit-{vfo.lower()}", operation
                    )
                else:
                    accepted = await asyncio.to_thread(operation)
                if accepted is not True:
                    raise RemoteCommandError(
                        "offset-command-rejected",
                        "FLEX rejected the RIT/XIT command",
                        status_code=503,
                    )
                return {"enabled": enabled, "offset_hz": offset_hz, "vfo": vfo}
            if normalized == "set_receive_vfo":
                vfo, slice_state = self._slice_for_vfo(arguments)
                slice_id = int(slice_state["slice_id"])
                await self.coordinator.execute_flex_route_change(
                    f"remote-receive-vfo-{vfo.lower()}",
                    lambda: self.flex._send(f"slice set {slice_id} active=1"),
                )
                return {"vfo": vfo}
            if normalized == "set_split":
                enabled = self._required_bool(arguments, "enabled")
                tx_frequency_hz = arguments.get("tx_frequency_hz")
                if tx_frequency_hz is not None:
                    tx_frequency_hz = self._required_int(arguments, "tx_frequency_hz")
                a_vfo, a_slice = self._slice_for_vfo({"vfo": "A"})
                target_vfo = "B" if enabled else a_vfo
                _, target_slice = self._slice_for_vfo({"vfo": target_vfo})
                tx_mhz = (
                    tx_frequency_hz / 1_000_000.0
                    if tx_frequency_hz is not None
                    else target_slice.get("frequency")
                )
                rx_mhz = a_slice.get("frequency")
                tx_band = band_from_frequency(float(tx_mhz)) if tx_mhz is not None else None
                rx_band = band_from_frequency(float(rx_mhz)) if rx_mhz is not None else None
                if enabled and (tx_band is None or rx_band is None or tx_band != rx_band):
                    raise RemoteCommandError(
                        "split-band-mismatch",
                        "Version 1 permits split only when VFO A and VFO B are on the same band",
                        status_code=422,
                    )
                target_slice_id = int(target_slice["slice_id"])

                def set_split() -> bool:
                    if (
                        enabled
                        and tx_frequency_hz is not None
                        and not self.flex._send(f"slice tune {target_slice_id} {float(tx_mhz):.6f}")
                    ):
                        return False
                    accepted = self.flex._send(f"slice set {target_slice_id} tx=1")
                    if accepted:
                        self.flex.current_tx_slice_id = target_slice_id
                        for state in getattr(self.flex, "slice_states", {}).values():
                            state["transmit"] = state.get("slice_id") == target_slice_id
                    return accepted

                await self.coordinator.execute_flex_route_change("remote-split", set_split)
                return {
                    "enabled": enabled,
                    "transmit_vfo": target_vfo,
                    "tx_frequency_hz": tx_frequency_hz,
                }
            if normalized == "set_cw_speed":
                words_per_minute = self._required_int(arguments, "words_per_minute")
                if not 5 <= words_per_minute <= 100:
                    raise RemoteCommandError(
                        "cw-speed-invalid",
                        "CW speed must be between 5 and 100 WPM",
                        status_code=422,
                    )
                if not await asyncio.to_thread(self.flex._send, f"cw wpm {words_per_minute}"):
                    raise RemoteCommandError(
                        "cw-speed-rejected", "FLEX rejected the CW speed", status_code=503
                    )
                self.radio_snapshot["cw_speed"] = words_per_minute
                return {"words_per_minute": words_per_minute}
            if normalized == "send_cw":
                text = str(arguments.get("text") or "")
                if (
                    not text.strip()
                    or len(text) > 128
                    or any(
                        ord(character) < 32 or ord(character) > 126 or character == "|"
                        for character in text
                    )
                ):
                    raise RemoteCommandError(
                        "cw-text-invalid",
                        "CW text must contain 1 through 128 printable ASCII characters without |",
                        status_code=422,
                    )
                await self.coordinator.execute_raw_flex_tx(
                    "cwx", lambda: self.flex._send(f"cwx send {text}")
                )
                return {"accepted": True}
            if normalized == "clear_cw":
                accepted = await asyncio.to_thread(self.flex._send, "cwx clear")
                unkeyed = await asyncio.to_thread(self.flex._send, "xmit 0")
                if not accepted or not unkeyed:
                    raise RemoteCommandError(
                        "cw-clear-rejected",
                        "FLEX did not confirm CW clear and receive state",
                        status_code=503,
                    )
                return {"accepted": True, "ptt": False}
            if normalized == "set_rf_power":
                watts = self._required_int(arguments, "watts")
                state = self.coordinator.snapshot()
                route = state.get("route") or {}
                expected = route.get("active_drive_w")
                if expected is None or watts != int(expected):
                    raise RemoteCommandError(
                        "rf-power-policy-mismatch",
                        f"RF power must match the active station policy ({expected!r} W)",
                    )
                await self.coordinator.follow_observed_radio_route(
                    self.radio_snapshot.get("frequency")
                )
                return {"watts": watts}
            action_map = {
                "station_standby": "standby",
                "station_operate": "operate",
                "station_tune": "tune",
                "station_cancel": "cancel",
            }
            action = action_map.get(normalized)
            if action:
                state = await self.coordinator.perform(action)
                return {"action": action, "station": state}
        except RemoteCommandError:
            raise
        except StationActionError as exc:
            raise RemoteCommandError(exc.code, exc.message, status_code=exc.status_code) from exc
        except (TypeError, ValueError) as exc:
            raise RemoteCommandError("command-argument-invalid", str(exc), status_code=422) from exc
        raise RemoteCommandError(
            "command-unsupported",
            f"Unsupported command: {normalized or 'unknown'}",
            status_code=404,
        )
