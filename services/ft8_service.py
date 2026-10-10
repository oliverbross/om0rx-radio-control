"""
FT8/FT4 Service - Main Orchestrator
Coordinates decoding, encoding, QSO management, and auto-sequencing
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
from math import gcd
import re
import time
import uuid
import numpy as np
from scipy import signal

from services.ft8_audio import FT8AudioProcessor
from services.audio_capture import AudioCaptureService, AudioCaptureConfig
from services.ft8_rx_decoder import (
    decode_window_samples,
    decode_window_seconds,
    get_default_ft8_rx_decoder,
    get_ft8_rx_decoder_status,
    normalise_decode_mode,
)
from services.ft8_tx import FT8TxEngine, ntp_offset
from services.digital_automation import DigitalAutomationController, DigitalAutomationSettings, extract_callsign

logger = logging.getLogger(__name__)

SIGNAL_REPORT_RE = re.compile(r"^R?[+-]\d{1,2}$")
GRID_RE = re.compile(r"^[A-R]{2}\d{2}([A-X]{2})?$")
NON_GRID_TOKENS = {"CQ", "DE", "QRZ", "RRR", "RR73", "73"}
SUPPORTED_SPECIAL_SUBMODES = {"standard", "foxhound", "superfox"}
SUPPORTED_SPECIAL_ROLES = {"hound", "fox"}


class QSOState(Enum):
    """QSO State Machine States"""
    IDLE = "idle"
    CALLING_CQ = "calling_cq"
    WAITING_RESPONSE = "waiting_response"
    SENDING_REPORT = "sending_report"
    SENDING_RRR = "sending_rrr"
    SENDING_73 = "sending_73"
    COMPLETE = "complete"


@dataclass
class QSOSession:
    """Active QSO Session"""
    their_call: str
    my_call: str
    my_grid: str
    attempt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: QSOState = QSOState.IDLE
    status: str = "idle"
    their_grid: Optional[str] = None
    my_report: Optional[str] = None
    their_report: Optional[str] = None
    frequency: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_tx_time: Optional[datetime] = None
    last_rx_time: Optional[datetime] = None
    tx_count: int = 0
    rx_count: int = 0
    logged: bool = False
    log_result: Optional[dict] = None
    log_status: str = "not_logged"
    
    def to_dict(self) -> dict:
        return {
            'their_call': self.their_call,
            'my_call': self.my_call,
            'attempt_id': self.attempt_id,
            'state': self.state.value,
            'status': self.status,
            'their_grid': self.their_grid,
            'my_report': self.my_report,
            'their_report': self.their_report,
            'frequency': self.frequency,
            'started_at': self.started_at.isoformat(),
            'tx_count': self.tx_count,
            'rx_count': self.rx_count,
            'logged': self.logged,
            'log_result': self.log_result,
            'log_status': self.log_status,
        }


class FT8Service:
    """Main FT8/FT4 Service"""
    
    def __init__(
        self,
        mode: str = 'FT8',
        mycall: str = 'OM0RX',
        mygrid: str = 'JN88',
        audio_device: Optional[str] = None,
        audio_output: Optional[str] = None,
        audio_sample_rate: int = 12000,
        ptt_method: str = "CAT",
        ptt_device: Any = None,
    ):
        """
        Initialize FT8/FT4 service
        
        Args:
            mode: 'FT8' or 'FT4'
            mycall: Your callsign
            mygrid: Your grid square
            audio_device: Audio device name for capture (None = default)
        """
        self.mode = normalise_decode_mode(mode)
        self.mycall = mycall.upper()
        self.mygrid = mygrid.upper()
        self.audio_sample_rate = int(audio_sample_rate or 12000)
        self.decoder_sample_rate = 12000
        self.audio_output = audio_output
        self.ptt_method = str(ptt_method or "CAT").upper()
        self.ptt_device = ptt_device
        
        self.audio_processor = FT8AudioProcessor(self.mode, sample_rate=self.decoder_sample_rate)
        
        # Audio capture
        audio_config = AudioCaptureConfig(
            device_name=audio_device,
            sample_rate=self.audio_sample_rate,
            channels=1,
            blocksize=max(1024, int(self.audio_sample_rate * 0.1))
        )
        self.audio_capture = AudioCaptureService(audio_config)
        self.audio_capture.set_audio_callback(self._on_audio_samples)
        
        # State
        self.enabled = False
        self.tx_enabled = False
        self.auto_sequence = False
        self.rx_decode_enabled = False
        self.tx_capability_enabled = False
        self.rx_decoder = get_default_ft8_rx_decoder()
        if self.rx_decoder.status.available:
            self.rx_decode_enabled = True
        self.tx_engine = FT8TxEngine(
            audio_output=audio_output,
            output_sample_rate=self.audio_sample_rate,
            ptt_method=self.ptt_method,
        )
        self.tx_capability_enabled = self.tx_engine.status.available
        self.tx_audio_frequency = 1500
        self.tx_even_first = True
        self.watchdog_enabled = True
        self.watchdog_cycles = {"FT8": 2, "FT4": 2}
        self.tx_watchdog_started_at: Optional[datetime] = None
        self.tx_watchdog_counter = 0
        self.tx_inhibit_reason: Optional[str] = None
        self.last_cancel_abort_reason: Optional[str] = None
        self.auto_engage_paused_until: Optional[datetime] = None
        self.auto_call_cq_only = False
        self.active_tx_message: Optional[str] = None
        self.current_tx_message: Optional[str] = None
        self._restart_tx_after_abort = False
        self.last_tx_slot = None
        self.tx_status = "idle"
        self.automation_status = "idle"
        self.automation_last_error: Optional[str] = None
        self.automation_prepare_block_reason: Optional[str] = None
        self._time_sync_cache = {"ok": None, "status": "not checked"}
        self._time_sync_checked_at = 0.0
        self.auto_cq_enabled = False
        self.auto_call_enabled = False
        self.auto_cq_limit = 5
        self.auto_call_limit = 5
        self.auto_cq_remaining = 5
        self.auto_call_remaining = 5
        self.special_activity = {
            "enabled": False,
            "role": "hound",
            "submode": "standard",
            "superfox_otp": False,
            "superfox_verified": False,
            "call_only_after_decode": True,
            "return_to_standard_after_qso": True,
            "hound_tx_min": 1000,
            "hound_tx_max": 4000,
            "superfox_tx_min": 200,
            "superfox_tx_max": 3000,
        }
        target_store = None
        try:
            from radio_control.digital_target_store import get_digital_target_store

            target_store = get_digital_target_store()
        except Exception as exc:
            logger.debug("Digital target persistence not attached: %s", exc)
        operator_settings: Dict[str, Any] = {}
        try:
            from radio_control import config as app_config

            configured = getattr(app_config, "FT8_OPERATOR_SETTINGS", {})
            if isinstance(configured, dict):
                operator_settings = configured
        except Exception as exc:
            logger.debug("Digital automation startup settings unavailable: %s", exc)
        self.automation_controller = DigitalAutomationController(
            mycall=self.mycall,
            settings=DigitalAutomationSettings.from_operator_settings(operator_settings),
            target_store=target_store,
        )
        
        # Decoded messages
        self.decoded_messages: List[Dict[str, Any]] = []
        self.max_decoded = 100
        
        # Active QSOs
        self.active_qsos: Dict[str, QSOSession] = {}
        self.active_attempt_id: Optional[str] = None
        self.completed_attempt_ids: set[str] = set()
        
        # TX queue
        self.tx_queue: List[str] = []
        self.tx_message_attempt_ids: Dict[str, Optional[str]] = {}
        self.tx_in_progress = False
        self.pending_tx_intent: Optional[Dict[str, Any]] = None
        self.automation_decisions: List[Dict[str, Any]] = []
        
        # Timing
        self.cycle_start = datetime.now(timezone.utc)
        self.is_tx_cycle = False
        self.slot_is_tx = False
        self.cycle_duration = self._cycle_duration_seconds()
        self.cycle_position = 0.0
        self._last_decode_slot_start: Optional[datetime] = None
        self.started_at: Optional[datetime] = None
        
        # Statistics
        self.stats = {
            'decoded_count': 0,
            'transmitted_count': 0,
            'qso_completed': 0,
            'uptime': 0
        }
        
        # Callbacks
        self.on_message_decoded = None
        self.on_qso_complete = None
        self.on_tx_message = None
        self.on_audio_stream = None  # Callback for streaming audio to frontend
        self.on_automation_target_enrich = None
        
        # Audio streaming
        self.audio_stream_enabled = True  # Enable by default for the browser waterfall
        self.audio_stream_buffer = []
        self.audio_stream_interval = 0.5  # Send audio every 0.5 seconds
        
        # Background tasks
        self.decode_task = None
        self.timing_task = None
        self.audio_task = None
        self.automation_task = None
        
        logger.info(
            "FT8Service initialized: mode=%s mycall=%s mygrid=%s input_sample_rate=%s decoder_sample_rate=%s",
            self.mode,
            mycall,
            mygrid,
            self.audio_sample_rate,
            self.decoder_sample_rate,
        )

    def _record_decision(self, event: str, reason: str, **details: Any) -> None:
        active_qso = next(iter(getattr(self, "active_qsos", {}).values()), None)
        pending = getattr(self, "pending_tx_intent", None) or {}
        if getattr(self, "tx_in_progress", False):
            current_state = "tx_active"
        elif pending or getattr(self, "tx_queue", None):
            current_state = "tx_pending"
        elif active_qso:
            current_state = getattr(active_qso, "status", "") or getattr(getattr(active_qso, "state", None), "value", "target_engaged")
        else:
            current_state = "idle"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "reason": reason,
            "attempt_id": details.get("attempt_id", getattr(self, "active_attempt_id", None)),
            "mode": getattr(self, "mode", ""),
            "active_target": getattr(active_qso, "their_call", None),
            "current_state": current_state,
            "pending_tx_message": pending.get("message"),
            "pending_tx_slot": pending.get("scheduled_slot_utc"),
            "tx_active": bool(getattr(self, "tx_in_progress", False)),
            **details,
        }
        self.automation_decisions.append(entry)
        if len(self.automation_decisions) > 100:
            self.automation_decisions = self.automation_decisions[-100:]
        logger.info("DIGITAL decision: %s", entry)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _clock_offset_seconds(self) -> float:
        """Return NTP offset seconds to align FT8/FT4 slot timing."""
        sync = self._get_cached_time_sync()
        if not sync.get("ok"):
            return 0.0
        try:
            offset = float(sync.get("offset_ms", 0.0)) / 1000.0
        except (TypeError, ValueError):
            return 0.0
        # Ignore implausible values; the user should fix the OS clock in that case.
        if abs(offset) > 10.0:
            return 0.0
        return offset

    def _slot_now(self) -> datetime:
        return self._now() + timedelta(seconds=self._clock_offset_seconds())

    def _attempt_is_current(self, attempt_id: Optional[str]) -> bool:
        if not attempt_id:
            return True
        if not self.active_attempt_id:
            return False
        return attempt_id == self.active_attempt_id

    def _max_safe_late_start_seconds(self, mode: Optional[str] = None) -> float:
        return 0.35 if normalise_decode_mode(mode or self.mode) == "FT8" else 0.2

    def _pre_tx_key_window_seconds(self, mode: Optional[str] = None) -> float:
        return 2.0 if normalise_decode_mode(mode or self.mode) == "FT8" else 1.2

    def _protocol_tx_audio_seconds(self, mode: Optional[str] = None) -> float:
        # The vendored encoder writes a full slot WAV with protocol leading
        # silence. After trimming the quiet tail, the playable frames are
        # about 13.9s for FT8 and 6.35s for FT4.
        return 13.9 if normalise_decode_mode(mode or self.mode) == "FT8" else 6.35

    def _same_slot_playback_delay_seconds(self, mode: Optional[str] = None) -> float:
        # Use the scheduled playback path even for same-slot starts so Flex
        # DAX audio can move the radio from PTT_REQUESTED to TRANSMITTING
        # without spending the first half-second waiting for confirmation.
        return 0.0

    def _should_handle_cycle(self, cycle_number: int, cycle_position: float, is_tx_cycle: bool) -> bool:
        if self.last_tx_slot == cycle_number:
            return False
        if is_tx_cycle:
            return cycle_position <= self._max_safe_late_start_seconds()
        return cycle_position < 0.5

    def _should_prekey_next_tx_slot(self, cycle_number: int, cycle_position: float, slot_is_tx: bool) -> tuple[bool, float, int]:
        has_pending_message = bool(self.tx_queue or self.active_tx_message)
        if slot_is_tx or not self.tx_enabled or self.tx_in_progress or not has_pending_message:
            return False, 0.0, cycle_number
        next_cycle = cycle_number + 1
        if self.last_tx_slot == next_cycle:
            return False, 0.0, next_cycle
        remaining = max(0.0, float(self._cycle_duration_seconds()) - float(cycle_position))
        if remaining <= self._pre_tx_key_window_seconds():
            return True, remaining, next_cycle
        return False, remaining, next_cycle

    def _tx_message_priority(self, message: str) -> int:
        parts = self._message_tokens(str(message or "").upper())
        if len(parts) < 3:
            return 0
        last_token = parts[-1]
        if last_token == "73":
            return 4
        if last_token in {"RR73", "RRR"}:
            return 3
        if SIGNAL_REPORT_RE.match(last_token):
            return 2
        if GRID_RE.match(last_token):
            return 1
        return 0

    def _maybe_preempt_stale_tx(self, qso: Optional[QSOSession], next_message: str) -> None:
        if not self.tx_in_progress or qso is None:
            return
        current_message = self.current_tx_message or self.active_tx_message
        if not current_message or current_message == next_message:
            return
        current_qso = self._active_qso_for_tx_message(current_message)
        if current_qso is not qso:
            return
        if self._tx_message_priority(next_message) <= self._tx_message_priority(current_message):
            return
        self._restart_tx_after_abort = True
        self.tx_engine.abort()
        self.tx_status = f"switching TX to {next_message}"
        self._record_decision(
            "tx-preempted",
            "directed-reply-advanced-qso",
            current_message=current_message,
            next_message=next_message,
            attempt_id=qso.attempt_id,
        )

    def _schedule_preempted_tx_restart(self) -> None:
        if not self._restart_tx_after_abort:
            return
        self._restart_tx_after_abort = False
        if self.enabled and self.tx_enabled and self.tx_queue:
            asyncio.create_task(self.transmit_queued_now_if_possible(force_current_slot=True))

    def _watchdog_limit_seconds(self) -> int:
        mode = normalise_decode_mode(self.mode)
        return int(self.watchdog_cycles.get(mode, 0) or 0) * 60

    def _watchdog_is_active(self) -> bool:
        return bool(
            self.watchdog_enabled
            and self._watchdog_limit_seconds() > 0
            and self.tx_watchdog_started_at
            and self.active_attempt_id
        )

    def _start_attempt_watchdog(self) -> None:
        if self.watchdog_enabled and self._watchdog_limit_seconds() > 0 and self.tx_watchdog_started_at is None:
            self.tx_watchdog_started_at = self._now()

    def _expire_watchdog_if_due(self) -> bool:
        if not self._watchdog_is_active():
            return False
        assert self.tx_watchdog_started_at is not None
        if (self._now() - self.tx_watchdog_started_at).total_seconds() < self._watchdog_limit_seconds():
            return False
        keep_automation_armed = bool(self.auto_call_enabled and self.automation_controller.active_target_key)
        self._cancel_current_attempt(
            reason="watchdog-expired",
            backoff_active_target=True,
            disable_tx=not keep_automation_armed,
            pause_auto_engage=not keep_automation_armed,
            clear_inhibit=False,
        )
        self.tx_status = "watchdog expired; attempt aborted and target backed off"
        return True

    def _active_target_retry_count(self) -> int:
        active_key = self.automation_controller.active_target_key
        target = self.automation_controller.targets.get(active_key) if active_key else None
        if target:
            return int(target.attempts or 0)
        qso = next(iter(self.active_qsos.values()), None)
        return int(qso.tx_count or 0) if qso else 0

    def _backoff_targets_debug(self) -> list[dict[str, Any]]:
        now = self._now()
        backed_off = []
        for target in self.automation_controller.targets.values():
            if target.is_backed_off(now):
                backed_off.append({
                    "key": target.key,
                    "call": target.call,
                    "backoff_until": target.backoff_until.isoformat() if target.backoff_until else None,
                    "reason": target.reason,
                    "attempts": target.attempts,
                })
        return backed_off

    def _cancel_current_attempt(
        self,
        *,
        reason: str,
        backoff_active_target: bool,
        disable_tx: bool,
        pause_auto_engage: bool,
        clear_inhibit: bool = False,
        inhibit_reason: Optional[str] = None,
    ) -> None:
        self.last_cancel_abort_reason = reason
        self.tx_engine.abort()
        self.tx_queue.clear()
        self.tx_message_attempt_ids.clear()
        self.active_tx_message = None
        self.current_tx_message = None
        self._restart_tx_after_abort = False
        self.pending_tx_intent = None
        for qso in self.active_qsos.values():
            qso.status = "aborted"
        self.active_qsos.clear()
        self.active_attempt_id = None
        self.tx_watchdog_started_at = None
        if backoff_active_target:
            self.automation_controller.abandon_active_target(reason=reason)
        else:
            self.automation_controller.active_target_key = None
        if pause_auto_engage:
            self.auto_engage_paused_until = self._now() + timedelta(seconds=max(1.0, self._cycle_duration_seconds()))
        if clear_inhibit:
            self.tx_inhibit_reason = None
        if inhibit_reason:
            self.tx_inhibit_reason = inhibit_reason
        if disable_tx:
            self.tx_enabled = False
            self.auto_sequence = False
        self._record_decision("attempt-cancelled", reason)

    def _ptt_target(self) -> Any:
        """Return the object that owns DIGITAL CAT PTT."""
        if self.ptt_device is not None:
            return self.ptt_device
        from services.radio import get_radio_instance

        return get_radio_instance()

    def _cycle_duration_seconds(self) -> float:
        """Return the timing slot duration for the active digital mode."""
        return decode_window_seconds(self.mode)

    def _live_cycle_state(self) -> tuple[float, float, int, bool]:
        """Return live slot timing and whether the current slot is ours to TX."""
        cycle_duration = self._cycle_duration_seconds()
        now = self._slot_now()
        cycle_position = now.timestamp() % cycle_duration if cycle_duration else 0.0
        cycle_number = int(now.timestamp() // cycle_duration) if cycle_duration else 0
        is_even_cycle = (cycle_number % 2) == 0
        slot_is_tx = is_even_cycle if self.tx_even_first else not is_even_cycle
        return cycle_duration, cycle_position, cycle_number, bool(slot_is_tx)
    
    async def start(self):
        """Start FT8 service"""
        if self.enabled:
            logger.warning("FT8 service already running")
            return
        
        logger.info(f"Starting {self.mode} service...")
        
        # Start audio capture
        if not self.audio_capture.start_capture():
            logger.error("Failed to start audio capture")
            raise RuntimeError("Failed to start audio capture. Check the selected FT8 audio input device.")

        self.enabled = True
        self.started_at = datetime.now(timezone.utc)
        self.audio_processor.clear_buffer()
        self._last_decode_slot_start = None
        
        # Start background tasks
        self.timing_task = asyncio.create_task(self._timing_loop())
        self.decode_task = asyncio.create_task(self._decode_loop())
        self.automation_task = asyncio.create_task(self._automation_loop())
        self.audio_task = None
        
        logger.info(f"{self.mode} service started")
    
    async def stop(self):
        """Stop FT8 service"""
        if not self.enabled:
            return
        
        self.enabled = False
        self.started_at = None
        logger.info(f"Stopping {self.mode} service...")
        
        # Stop audio capture
        self.audio_capture.stop_capture()
        
        # Cancel background tasks
        if self.timing_task:
            self.timing_task.cancel()
        if self.decode_task:
            self.decode_task.cancel()
        if self.audio_task:
            self.audio_task.cancel()
        if self.automation_task:
            self.automation_task.cancel()
        
        # Wait for tasks to complete
        for task in [self.timing_task, self.decode_task, self.audio_task, self.automation_task]:
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info(f"{self.mode} service stopped")
    
    async def _timing_loop(self):
        """Main timing loop - manages TX/RX cycles"""
        try:
            while self.enabled:
                cycle_duration = self._cycle_duration_seconds()
                current_time = self._slot_now()
                
                epoch = current_time.timestamp()
                cycle_number = int(epoch // cycle_duration)
                cycle_position = epoch % cycle_duration
                is_even_cycle = (cycle_number % 2) == 0
                
                slot_is_tx = is_even_cycle if self.tx_even_first else not is_even_cycle
                self.cycle_duration = cycle_duration
                self.cycle_position = cycle_position
                self.slot_is_tx = bool(slot_is_tx)
                self.is_tx_cycle = bool(slot_is_tx and self.tx_enabled)

                should_prekey, prekey_delay, prekey_slot = self._should_prekey_next_tx_slot(
                    cycle_number,
                    cycle_position,
                    bool(slot_is_tx),
                )
                if should_prekey:
                    self.last_tx_slot = prekey_slot
                    try:
                        await self._handle_tx_cycle(playback_delay_seconds=prekey_delay)
                    except Exception as exc:
                        self.tx_status = f"pre-key TX failed: {exc}"
                        self.tx_enabled = False
                        logger.error("Digital pre-key TX failed; TX halted: %s", exc, exc_info=True)
                    await asyncio.sleep(0.1)
                    continue
                
                # Handle cycle transition. TX remains useful for a few seconds
                # after slot start; do not miss the whole slot if the loop
                # wakes slightly late.
                if self._should_handle_cycle(cycle_number, cycle_position, self.is_tx_cycle):
                    self.last_tx_slot = cycle_number
                    try:
                        if self.is_tx_cycle:
                            await self._handle_tx_cycle()
                        else:
                            await self._handle_rx_cycle()
                    except Exception as exc:
                        self.tx_status = f"cycle handler failed: {exc}"
                        self.tx_enabled = False
                        logger.error("Digital cycle handler failed; TX halted: %s", exc, exc_info=True)
                
                # Sleep until next check
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            logger.info("Timing loop cancelled")
        except Exception as e:
            logger.error(f"Error in timing loop: {e}", exc_info=True)
    
    async def _decode_loop(self):
        """Background decode loop"""
        try:
            last_stream_time = datetime.now(timezone.utc)
            
            while self.enabled:
                # Get audio buffer
                audio_buffer = self.audio_processor.get_audio_buffer()
                
                if len(audio_buffer) > 0:
                    # Process audio for waterfall only when a client wants it.
                    if self.audio_stream_enabled:
                        spectrum = self.audio_processor.process_audio_chunk(audio_buffer[-2048:])
                        if spectrum is not None:
                            self.audio_processor.update_waterfall(spectrum)
                    
                    # Stream audio to the frontend waterfall
                    if self.audio_stream_enabled and self.on_audio_stream:
                        now = datetime.now(timezone.utc)
                        if (now - last_stream_time).total_seconds() >= self.audio_stream_interval:
                            # Send recent audio chunk to frontend
                            chunk_size = int(self.audio_processor.sample_rate * self.audio_stream_interval)
                            audio_chunk = audio_buffer[-chunk_size:] if len(audio_buffer) >= chunk_size else audio_buffer
                            
                            if len(audio_chunk) > 0:
                                # Convert to list for JSON serialization
                                audio_data = audio_chunk.tolist() if isinstance(audio_chunk, np.ndarray) else list(audio_chunk)
                                await self.on_audio_stream(audio_data)
                            
                            last_stream_time = now
                    
                    buffer_duration = len(audio_buffer) / self.decoder_sample_rate
                    required_duration = self._cycle_duration_seconds()
                    
                    if self.rx_decode_enabled and buffer_duration >= required_duration:
                        await self._attempt_decode(audio_buffer)
                
                # Sleep between decode attempts
                await asyncio.sleep(0.2)  # Faster loop for audio streaming
                
        except asyncio.CancelledError:
            logger.info("Decode loop cancelled")
        except Exception as e:
            logger.error(f"Error in decode loop: {e}", exc_info=True)

    async def _automation_loop(self):
        """Backend execution loop for Digital target selection and queued TX."""
        try:
            while self.enabled:
                try:
                    await self._automation_tick()
                except Exception as exc:
                    self.automation_last_error = str(exc)
                    self.automation_status = f"error: {exc}"
                    logger.error("Digital automation tick failed: %s", exc, exc_info=True)
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            logger.info("Digital automation loop cancelled")

    async def _automation_tick(self):
        # Spot/DXCC hunting is executed by WSJT-Z through the always-on bridge
        # planner. The built-in TX engine must not arm from spot-hunt settings.
        if not self.auto_call_enabled:
            self.automation_status = "standby"
            return
        if self.tx_inhibit_reason:
            self.automation_status = f"tx-inhibited: {self.tx_inhibit_reason}"
            self._record_decision("automation-skip", "tx-inhibited", tx_inhibit_reason=self.tx_inhibit_reason)
            return
        if self.auto_engage_paused_until and self.auto_engage_paused_until > self._now():
            self.automation_status = "auto-engage-paused"
            self._record_decision(
                "automation-skip",
                "auto-engage-paused-after-cancel",
                paused_until=self.auto_engage_paused_until.isoformat(),
            )
            return
        self.auto_engage_paused_until = None
        if self._expire_watchdog_if_due():
            self._record_decision("attempt-expired", "watchdog-expired-before-automation-selection")
        if self.active_qsos:
            self.automation_status = "qso-active"
            self._record_decision("automation-skip", "active-qso-owned-by-backend", attempt_id=self.active_attempt_id)
            return
        if self.tx_queue or self.active_tx_message:
            self.automation_status = "tx-queue-pending"
            self._record_decision("automation-skip", "tx-queue-or-message-pending", active_message=self.active_tx_message)
            return
        target = self.automation_controller.next_target(
            cq_only=self.auto_call_cq_only,
            auto_call_start_only=self.auto_call_enabled,
        )
        if not target:
            self.automation_status = "no-eligible-targets"
            self._record_decision("automation-skip", "no-eligible-targets")
            return

        if not await self._automation_prepare_radio(target):
            block_reason = self.automation_prepare_block_reason or "radio-prepare-failed"
            self.automation_controller.release_target(
                target.key,
                reason=block_reason,
            )
            self._record_decision(
                "automation-skip",
                block_reason,
                call=target.call,
                owner=self.automation_controller.settings.dial_frequency_owner,
                target_frequency=target.dial_frequency,
            )
            return

        final_eligibility = self.automation_controller._target_eligibility(
            target,
            cq_only=self.auto_call_cq_only,
            auto_call_start_only=True,
        )
        if not final_eligibility.get("eligible"):
            self.automation_controller.release_target(
                target.key,
                reason="final-transmit-eligibility-failed",
            )
            self.automation_status = "blocked: final transmit eligibility failed"
            self._record_decision(
                "automation-skip",
                "final-transmit-eligibility-failed",
                call=target.call,
                eligibility_reasons=final_eligibility.get("reasons", []),
            )
            return

        if not self.tx_enabled:
            self.tx_enabled = True
            self.auto_sequence = True
        if not self.auto_call_enabled:
            self.automation_status = f"selected {target.call}; Auto Call disabled"
            self._record_decision("candidate-selected", "auto-call-disabled", call=target.call)
            return
        if self.auto_call_remaining <= 0:
            self.auto_call_remaining = self._auto_call_attempt_budget()

        self.automation_controller.record_attempt(target.key)
        message = await self.engage_target(
            {
                "callsign": target.call,
                "grid": target.grid,
                "mode": target.mode,
                "band": target.band,
                "frequency_mhz": target.dial_frequency,
                "freq": target.audio_offset,
                "slot_start_utc": target.heard_slot_start_at,
                "source": "auto_call",
            },
            source="auto_call",
            replace_active=True,
        )
        await self.transmit_queued_now_if_possible(force_current_slot=True)
        self.automation_status = f"queued {message}"
        self._record_decision("target-engaged", "auto-call-selected-target", call=target.call, message=message, attempt_id=self.active_attempt_id)

    async def _automation_prepare_radio(self, target) -> bool:
        self.automation_prepare_block_reason = None
        if target.mode and target.mode != self.mode:
            self.set_mode(target.mode)

        frequency = float(target.dial_frequency or 0)
        if frequency <= 0:
            return True

        from fastapi import HTTPException
        from services.radio import execute_station_route_change, get_radio_instance

        flex = get_radio_instance()
        if not flex:
            self.automation_status = f"selected {target.call}; radio unavailable"
            self.automation_prepare_block_reason = "radio-unavailable"
            return False
        current = float(getattr(flex, "current_freq", 0) or 0)
        if abs(current - frequency) <= 0.0005:
            return True

        owner = self.automation_controller.settings.dial_frequency_owner
        if owner == "wsjtz":
            self.automation_status = (
                f"blocked {target.call}; WSJT-Z owns dial frequency "
                f"({current:.6f} -> {frequency:.6f} MHz)"
            )
            logger.warning(
                "Digital automation QSY blocked: owner=%s call=%s current=%.6f target=%.6f",
                owner,
                target.call,
                current,
                frequency,
            )
            self.automation_prepare_block_reason = "dial-frequency-owner-blocked"
            return False

        def apply_digital_route() -> bool:
            return bool(flex.set_mode("DIGU") and flex.tune_mhz(frequency))

        try:
            tuned = await execute_station_route_change(
                "built-in-digital-frequency",
                apply_digital_route,
                allow_digital_owner=True,
            )
        except HTTPException:
            tuned = False
        if tuned:
            self.automation_status = f"radio tuned {frequency:.6f} MHz for {target.call}"
        else:
            self.automation_status = f"radio tune failed for {target.call}"
            self.automation_prepare_block_reason = "radio-tune-failed"
        return bool(tuned)

    def _auto_call_attempt_budget(self) -> int:
        configured = int(self.auto_call_limit or 0)
        max_attempts = int(self.automation_controller.settings.max_attempts_per_target or 1)
        return max(1, configured or max_attempts)
    
    async def _attempt_decode(self, audio_buffer: np.ndarray):
        """
        Attempt to decode FT8/FT4 signals from audio buffer

        Raw-audio decode is delegated to the selected decoder boundary. The
        default implementation is the vendored MIT ft8_lib decoder when built.
        """
        if not self.rx_decoder.status.available:
            return None

        try:
            now = self._slot_now()
            cycle_duration = self._cycle_duration_seconds()
            within_slot = now.timestamp() % cycle_duration
            current_cycle = int(now.timestamp() // cycle_duration)
            previous_cycle = current_cycle - 1
            previous_was_even = (previous_cycle % 2) == 0
            previous_slot_was_tx = previous_was_even if self.tx_even_first else not previous_was_even
            if self.tx_enabled and previous_slot_was_tx:
                return None

            slot_epoch = current_cycle * cycle_duration - cycle_duration
            slot_start = datetime.fromtimestamp(slot_epoch, timezone.utc)
            if self._last_decode_slot_start == slot_start:
                return None
            self._last_decode_slot_start = slot_start

            loop = asyncio.get_running_loop()
            window_samples = decode_window_samples(self.mode)
            end_offset = int(max(0.0, within_slot) * self.decoder_sample_rate)
            end_index = len(audio_buffer) - end_offset if end_offset > 0 else len(audio_buffer)
            start_index = end_index - window_samples
            if start_index < 0 or end_index > len(audio_buffer):
                return None
            decode_samples = audio_buffer[start_index:end_index]
            if len(decode_samples) < window_samples:
                return None

            messages = await loop.run_in_executor(
                None,
                lambda: self.rx_decoder.decode_window(
                    decode_samples,
                    sample_rate=self.decoder_sample_rate,
                    window_start=slot_start,
                    mode=self.mode,
                ),
            )
            for message in messages:
                await self._handle_decoded_message(message)
        except Exception as e:
            logger.error("Error attempting FT8 decode: %s", e, exc_info=True)
        return None
    
    def _on_audio_samples(self, samples: np.ndarray):
        """
        Callback for incoming audio samples
        
        Args:
            samples: Audio samples from capture device
        """
        processed = self._prepare_audio_for_decoder(samples)
        if len(processed) > 0:
            self.audio_processor.add_audio_samples(processed)

    def _prepare_audio_for_decoder(self, samples: np.ndarray) -> np.ndarray:
        """Convert capture-device audio into the decoder's 12 kHz mono stream."""
        sample_array = np.asarray(samples, dtype=np.float32).reshape(-1)
        if len(sample_array) == 0:
            return sample_array

        if self.audio_sample_rate == self.decoder_sample_rate:
            return sample_array

        divisor = gcd(self.audio_sample_rate, self.decoder_sample_rate)
        up = self.decoder_sample_rate // divisor
        down = self.audio_sample_rate // divisor
        resampled = signal.resample_poly(sample_array, up, down)
        return np.asarray(resampled, dtype=np.float32)
    
    async def _audio_processing_loop(self):
        """Process audio samples from queue"""
        try:
            while self.enabled:
                # Get audio samples from queue
                samples = await self.audio_capture.get_audio_samples()
                
                if samples is not None:
                    samples = self._prepare_audio_for_decoder(samples)
                    # Process for waterfall only when enabled.
                    if self.audio_stream_enabled and len(samples) >= 512:
                        spectrum = self.audio_processor.process_audio_chunk(samples)
                        if spectrum is not None:
                            self.audio_processor.update_waterfall(spectrum)
                
                await asyncio.sleep(0.05)  # 50ms
                
        except asyncio.CancelledError:
            logger.info("Audio processing loop cancelled")
        except Exception as e:
            logger.error(f"Error in audio processing loop: {e}", exc_info=True)
    
    async def _handle_decoded_message(self, message):
        """Handle a decoded message"""
        # Add to decoded list
        self.decoded_messages.append(message)
        if len(self.decoded_messages) > self.max_decoded:
            self.decoded_messages.pop(0)
        
        self.stats['decoded_count'] += 1
        self.automation_controller.ingest_target(await self._automation_payload_from_decode(message))
        
        logger.info(f"Decoded: {message.message} (SNR: {message.snr:.1f} dB)")
        self._backoff_active_target_if_busy_elsewhere(message)
        
        # Notify callback
        if self.on_message_decoded:
            await self.on_message_decoded(message)
        
        # Auto-sequence if enabled
        if self.auto_sequence:
            await self._auto_sequence_handler(message)
        if (
            not self.active_qsos
            and not self.tx_queue
            and not self.active_tx_message
            and (self.auto_call_enabled or self.automation_controller.settings.spot_hunt_enabled)
        ):
            await self._automation_tick()

    async def _automation_payload_from_decode(self, message) -> dict[str, Any]:
        """Build a Wavelog-enriched automation target from one decoded message."""
        payload = message.to_dict() if hasattr(message, "to_dict") else dict(message or {})
        payload.setdefault("source", "decoded")
        payload["heard"] = True
        payload.setdefault("mode", self.mode)
        call = extract_callsign(payload, self.mycall)
        if call and not payload.get("callsign"):
            payload["callsign"] = call

        grid = self._grid_from_message(payload.get("message") or "")
        if grid and not (payload.get("grid") or payload.get("gridsquare")):
            payload["grid"] = grid

        frequency = await self._current_radio_frequency_mhz()
        if frequency and not payload.get("base_frequency") and not payload.get("frequency_mhz"):
            payload["base_frequency"] = frequency
            payload["frequency_mhz"] = frequency
        if frequency and not payload.get("band"):
            try:
                from radio_control.spot_processor import band_from_khz

                payload["band"] = band_from_khz(frequency * 1000)
            except Exception:
                pass

        if (
            self.on_automation_target_enrich
            and (
                self.auto_call_enabled
                or self.automation_controller.settings.spot_hunt_enabled
                or self.automation_controller.settings.enabled
            )
        ):
            try:
                started = time.perf_counter()
                enriched = await self.on_automation_target_enrich(payload)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                if isinstance(enriched, dict):
                    payload = enriched
                if elapsed_ms > 250:
                    self._record_decision(
                        "automation-enrichment-slow",
                        "decoded-target-status-lookup",
                        call=call,
                        elapsed_ms=round(elapsed_ms, 1),
                        source=payload.get("source"),
                    )
            except Exception as exc:
                logger.debug("Decoded automation target enrichment failed: %s", exc, exc_info=True)
        return payload

    @staticmethod
    def _grid_from_message(text: str) -> str:
        for token in reversed(str(text or "").upper().replace(";", " ").split()):
            value = token.strip("<>,;")
            if value in NON_GRID_TOKENS:
                continue
            if GRID_RE.match(value):
                return value[:4]
        return ""

    def _backoff_active_target_if_busy_elsewhere(self, message: Any) -> None:
        if not self.auto_call_enabled or not self.active_qsos:
            return
        text = str(getattr(message, "message", "") or "").upper()
        parts = self._message_tokens(text)
        if len(parts) < 2 or parts[0] == "CQ" or self.mycall in parts:
            return
        for qso in list(self.active_qsos.values()):
            their_call = str(qso.their_call or "").upper()
            if not their_call or their_call not in parts:
                continue
            self._record_decision(
                "target-busy-observed",
                "active-qso-still-owned-by-backend",
                call=their_call,
                decoded_message=text,
            )
            return

    async def _current_radio_frequency_mhz(self) -> float:
        try:
            from services.radio import get_radio_instance

            flex = get_radio_instance()
            return float(getattr(flex, "current_freq", 0) or 0)
        except Exception:
            return 0.0
    
    async def _auto_sequence_handler(self, message):
        """Handle auto-sequencing logic"""
        if self.tx_inhibit_reason:
            self._record_decision("decode-ignored", "tx-inhibited", tx_inhibit_reason=self.tx_inhibit_reason)
            return
        msg_text = message.message.strip().upper()
        if self.active_tx_message and msg_text == self.active_tx_message.strip().upper():
            return
        for parts in self._message_clauses(msg_text):
            if len(parts) < 2 or self.mycall not in parts[:2]:
                continue

            their_call = self._extract_counterparty_call(" ".join(parts), parts)
            if not their_call:
                continue

            qso = self.active_qsos.get(their_call)
            if qso is None and 'CQ' in parts:
                continue

            if qso is None:
                active_parts = self._message_tokens(self.active_tx_message or "")
                if self.active_qsos and active_parts and active_parts[0] != "CQ":
                    self._record_decision("decode-ignored", "active-qso-prevents-tailend-steal", message=msg_text)
                    continue
                qso = QSOSession(
                    their_call=their_call,
                    my_call=self.mycall,
                    my_grid=self.mygrid,
                    state=QSOState.WAITING_RESPONSE,
                    status="target_engaged",
                    frequency=message.freq
                )
                self.active_qsos[their_call] = qso
                self.active_attempt_id = qso.attempt_id

            await self._update_qso_state(qso, message, parts=parts)
    
    async def _update_qso_state(self, qso: QSOSession, message, parts: Optional[list[str]] = None):
        """Update QSO state machine"""
        msg = message.message.strip().upper()
        parts = parts or self._best_clause_for_qso(msg, qso)
        if len(parts) < 2:
            return
        if self._extract_counterparty_call(" ".join(parts), parts) != qso.their_call:
            return
        if not self.active_attempt_id and self.active_qsos.get(qso.their_call) is qso:
            self.active_attempt_id = qso.attempt_id
        if qso.their_call not in self.active_qsos and not self.active_attempt_id:
            self.active_qsos[qso.their_call] = qso
            self.active_attempt_id = qso.attempt_id
        if not self._attempt_is_current(qso.attempt_id):
            self._record_decision("decode-ignored", "stale-attempt-reply", call=qso.their_call, attempt_id=qso.attempt_id, active_attempt_id=self.active_attempt_id)
            return

        now = self._now()
        qso.last_rx_time = now
        qso.rx_count += 1
        qso.status = "waiting_for_reply"
        if self.tx_capability_enabled:
            self.tx_enabled = True
            self.auto_sequence = True
            # A directed reply means the QSO is alive. Keep the watchdog from
            # killing the exchange while the other station is still answering.
            self.tx_watchdog_started_at = now
        
        last_token = parts[-1]
        if "RR73" in parts:
            qso.state = QSOState.SENDING_73
            qso.status = "tx_pending"
            self._record_decision("qso-advanced", "rr73-received-send-73", call=qso.their_call, attempt_id=qso.attempt_id)
            await self._queue_qso_message(qso, f"{qso.their_call} {qso.my_call} 73")
            return

        if "RRR" in parts:
            # Acknowledgment
            qso.state = QSOState.SENDING_73
            qso.status = "tx_pending"
            self._record_decision("qso-advanced", "rrr-received-send-73", call=qso.their_call, attempt_id=qso.attempt_id)
            await self._queue_qso_message(qso, f"{qso.their_call} {qso.my_call} 73")
            return

        if "73" in parts:
            # QSO complete
            qso.state = QSOState.COMPLETE
            qso.status = "completed"
            self._record_decision("qso-complete", "73-received", call=qso.their_call, attempt_id=qso.attempt_id)
            await self._complete_qso(qso)
            return

        if SIGNAL_REPORT_RE.match(last_token):
            self._apply_hound_reply_frequency(message)
            qso.their_report = last_token.lstrip("R")
            if last_token.startswith("R"):
                if qso.state in {QSOState.SENDING_73, QSOState.COMPLETE}:
                    self._record_decision("decode-ignored", "roger-report-after-final-state", call=qso.their_call, attempt_id=qso.attempt_id, report=last_token)
                    return
                qso.state = QSOState.SENDING_RRR
                qso.status = "tx_pending"
                self._record_decision("qso-advanced", "roger-report-received-send-rr73", call=qso.their_call, attempt_id=qso.attempt_id, report=last_token)
                await self._queue_qso_message(qso, f"{qso.their_call} {qso.my_call} RR73")
            else:
                if qso.state in {QSOState.SENDING_RRR, QSOState.SENDING_73, QSOState.COMPLETE}:
                    self._record_decision("decode-ignored", "plain-report-after-advanced-state", call=qso.their_call, attempt_id=qso.attempt_id, report=last_token)
                    return
                if not qso.my_report:
                    qso.my_report = self._signal_report_from_decode(message)
                qso.state = QSOState.SENDING_REPORT
                qso.status = "tx_pending"
                self._record_decision("qso-advanced", "report-received-send-roger-report", call=qso.their_call, attempt_id=qso.attempt_id, report=last_token, next_report=qso.my_report)
                await self._queue_qso_message(qso, f"{qso.their_call} {qso.my_call} R{qso.my_report}")
            return

        if GRID_RE.match(last_token):
            qso.their_grid = last_token[:4]
            qso.my_report = self._signal_report_from_decode(message)
            qso.state = QSOState.SENDING_REPORT
            qso.status = "tx_pending"
            self._record_decision("qso-advanced", "direct-call-grid-received-send-report", call=qso.their_call, attempt_id=qso.attempt_id, grid=qso.their_grid)
            await self._queue_qso_message(qso, f"{qso.their_call} {qso.my_call} {qso.my_report}")

    def _message_tokens(self, text: str) -> list[str]:
        return [
            token.strip(";,<>").upper()
            for token in str(text or "").replace(";", " ; ").split()
            if token.strip(";,<>")
        ]

    def _message_clauses(self, text: str) -> list[list[str]]:
        return [
            tokens
            for tokens in (self._message_tokens(clause) for clause in str(text or "").upper().split(";"))
            if tokens
        ]

    def _best_clause_for_qso(self, text: str, qso: QSOSession) -> list[str]:
        for parts in self._message_clauses(text):
            if self._extract_counterparty_call(" ".join(parts), parts) == qso.their_call:
                return parts
        return self._message_tokens(text)

    @staticmethod
    def _looks_like_callsign(token: str) -> bool:
        value = str(token or "").strip(";,<>").upper()
        if not re.match(r"^[A-Z0-9/]{3,12}$", value) or not re.search(r"\d", value):
            return False
        if GRID_RE.match(value) or SIGNAL_REPORT_RE.match(value):
            return False
        return value not in {"CQ", "RRR", "RR73", "73"}

    def _extract_counterparty_call(self, text: str, parts: list[str]) -> Optional[str]:
        if self.special_activity.get("enabled") and self.special_activity.get("role") == "hound":
            bracketed = re.search(r"<([^>]+)>", text)
            if bracketed:
                return bracketed.group(1).upper()
            if parts and parts[0] == self.mycall and len(parts) > 1:
                return parts[1]
        pair = parts[:2]
        if len(pair) < 2 or self.mycall not in pair:
            return None
        if pair[0] != self.mycall and self._looks_like_callsign(pair[0]):
            return parts[0]
        if pair[1] != self.mycall and self._looks_like_callsign(pair[1]):
            return parts[1]
        return None

    def _signal_report_from_decode(self, message) -> str:
        try:
            value = int(round(float(getattr(message, "snr", -15))))
        except (TypeError, ValueError):
            value = -15
        value = max(-30, min(30, value))
        sign = "+" if value >= 0 else "-"
        return f"{sign}{abs(value):02d}"

    def _target_heard_slot_timestamp(self, target: Dict[str, Any]) -> Any:
        for key in ("slot_start_utc", "heard_slot_start_at", "timestamp"):
            value = target.get(key)
            if value:
                return value
        return None

    def _target_heard_slot_iso(self, target: Dict[str, Any]) -> Optional[str]:
        value = self._target_heard_slot_timestamp(target)
        if isinstance(value, datetime):
            timestamp = value
        elif value:
            try:
                timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return str(value)
        else:
            return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).isoformat()

    def _desired_tx_cycle_parity(self) -> int:
        return 0 if self.tx_even_first else 1

    def _infer_tx_slot_from_target(self, target: Dict[str, Any]) -> None:
        """Use the decoded receive slot to choose the opposite TX slot."""
        timestamp = self._target_heard_slot_timestamp(target)
        if not timestamp:
            return
        try:
            if isinstance(timestamp, datetime):
                decoded_at = timestamp
            else:
                decoded_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if decoded_at.tzinfo is None:
                decoded_at = decoded_at.replace(tzinfo=timezone.utc)
            cycle_duration = self._cycle_duration_seconds()
            station_cycle = int(decoded_at.timestamp() // cycle_duration) if cycle_duration else 0
            station_was_even = (station_cycle % 2) == 0
            self.tx_even_first = not station_was_even
            self._record_decision(
                "tx-slot-selected",
                "opposite-heard-slot",
                heard_slot_utc=decoded_at.isoformat(),
                heard_cycle_parity=0 if station_was_even else 1,
                tx_cycle_parity=self._desired_tx_cycle_parity(),
            )
        except Exception:
            logger.debug("Unable to infer TX slot from target timestamp %r", timestamp, exc_info=True)

    def _next_tx_slot_start(self, desired_parity: Optional[int] = None) -> Optional[datetime]:
        cycle_duration = self._cycle_duration_seconds()
        if not cycle_duration:
            return None
        parity = self._desired_tx_cycle_parity() if desired_parity is None else int(desired_parity) % 2
        now = self._slot_now()
        now_timestamp = now.timestamp()
        cycle_number = int(now_timestamp // cycle_duration)
        cycle_position = now_timestamp % cycle_duration
        max_safe_late_start = self._max_safe_late_start_seconds()
        for offset in range(6):
            candidate_cycle = cycle_number + offset
            if candidate_cycle % 2 != parity:
                continue
            if offset == 0 and cycle_position > max_safe_late_start:
                continue
            return datetime.fromtimestamp(candidate_cycle * cycle_duration, timezone.utc)
        return datetime.fromtimestamp((cycle_number + 1) * cycle_duration, timezone.utc)

    def _next_tx_slot_iso(self, desired_parity: Optional[int] = None) -> Optional[str]:
        slot_start = self._next_tx_slot_start(desired_parity)
        return slot_start.isoformat() if slot_start else None

    async def engage_target(
        self,
        target: Dict[str, Any],
        *,
        source: str = "manual",
        replace_active: bool = True,
    ) -> str:
        """Atomically create or replace the active backend-owned QSO attempt."""
        payload = dict(target or {})
        call = extract_callsign(payload, self.mycall)
        if not call:
            raise RuntimeError("No workable callsign supplied for Digital engage")
        call = call.upper()
        if call == self.mycall:
            raise RuntimeError("Cannot engage own callsign")
        if not self.tx_capability_enabled:
            raise RuntimeError(self.tx_engine.status.reason)

        mode = normalise_decode_mode(payload.get("mode") or self.mode)
        if mode != self.mode:
            self.set_mode(mode)

        self._infer_tx_slot_from_target(payload)
        grid = self._grid_from_message(str(payload.get("grid") or payload.get("gridsquare") or ""))
        frequency = payload.get("frequency_mhz", payload.get("base_frequency", payload.get("frequency", 0)))
        try:
            frequency_mhz = float(frequency or 0)
        except (TypeError, ValueError):
            frequency_mhz = 0.0
        try:
            rx_audio_frequency = int(round(float(payload.get("freq", payload.get("audio_offset", 0)) or 0)))
        except (TypeError, ValueError):
            rx_audio_frequency = 0

        if replace_active:
            if self.tx_in_progress:
                self.tx_engine.abort()
            if self.active_qsos and call not in self.active_qsos:
                self.automation_controller.abandon_active_target(reason=f"replaced-by-{call}")
            self.tx_queue.clear()
            self.active_tx_message = None
            self.active_qsos.clear()

        if not source.startswith("auto"):
            self.tx_inhibit_reason = None
            self.auto_engage_paused_until = None
        self.enable_tx()
        self.auto_sequence = True
        qso = QSOSession(
            their_call=call,
            my_call=self.mycall,
            my_grid=self.mygrid,
            state=QSOState.WAITING_RESPONSE,
            status="target_engaged",
            their_grid=grid[:4] or None,
            frequency=frequency_mhz,
        )
        self.active_qsos[call] = qso
        self.active_attempt_id = qso.attempt_id
        self.tx_watchdog_started_at = None
        self._start_attempt_watchdog()
        message = f"{call} {self.mycall} {self.mygrid[:4]}".strip()
        await self.queue_tx_message(message, automation="auto_call" if source == "auto_call" else None, attempt_id=qso.attempt_id)
        self.pending_tx_intent = {
            "intent_id": str(uuid.uuid4()),
            "attempt_id": qso.attempt_id,
            "message": message,
            "call": call,
            "mode": self.mode,
            "band": payload.get("band") or "",
            "dial_frequency": frequency_mhz,
            "rx_audio_frequency": rx_audio_frequency,
            "audio_frequency": self.tx_audio_frequency,
            "source": source,
            "reason": "manual target selected" if source.startswith("manual") else "automation target selected",
            "scheduled_slot_utc": self._next_tx_slot_iso(),
            "tx_cycle_parity": self._desired_tx_cycle_parity(),
            "heard_slot_utc": self._target_heard_slot_iso(payload),
        }
        self.tx_status = f"queued {message}"
        qso.status = "tx_pending"
        self._record_decision("target-engaged", "backend-engage", source=source, call=call, message=message, attempt_id=qso.attempt_id)
        return message

    def _seed_qso_from_tx_message(self, message: str) -> None:
        parts = self._message_tokens(str(message or "").upper())
        if len(parts) < 2 or parts[0] == "CQ" or self.mycall not in parts[:3]:
            return

        their_call = self._extract_counterparty_call(" ".join(parts), parts)
        if not their_call:
            return

        qso = self.active_qsos.get(their_call)
        if qso is None:
            qso = QSOSession(
                their_call=their_call,
                my_call=self.mycall,
                my_grid=self.mygrid,
                state=QSOState.WAITING_RESPONSE,
                status="target_engaged",
            )
            self.active_qsos[their_call] = qso
            self.active_attempt_id = qso.attempt_id

        last_token = parts[-1]
        if last_token in {"73", "RR73"}:
            qso.state = QSOState.SENDING_73
        elif last_token == "RRR":
            qso.state = QSOState.SENDING_RRR
        elif GRID_RE.match(last_token):
            qso.state = QSOState.WAITING_RESPONSE
        elif SIGNAL_REPORT_RE.match(last_token):
            qso.my_report = last_token[1:] if last_token.startswith("R") else last_token
            qso.state = QSOState.SENDING_REPORT

    def _active_qso_for_tx_message(self, message: str) -> Optional[QSOSession]:
        parts = self._message_tokens(str(message or "").upper())
        if len(parts) < 2:
            return None
        their_call = self._extract_counterparty_call(" ".join(parts), parts)
        if not their_call:
            return None
        return self.active_qsos.get(their_call)

    async def _queue_qso_message(self, qso: QSOSession, message: str):
        if not self._attempt_is_current(qso.attempt_id):
            self._record_decision("tx-skipped", "stale-qso-attempt", call=qso.their_call, attempt_id=qso.attempt_id, active_attempt_id=self.active_attempt_id)
            return
        if self.active_tx_message == message and message in self.tx_queue:
            return
        self.tx_queue.clear()
        self.active_tx_message = None
        await self.queue_tx_message(message, attempt_id=qso.attempt_id)
        if self.enabled:
            asyncio.create_task(self.transmit_queued_now_if_possible(force_current_slot=True))

    def _apply_hound_reply_frequency(self, message) -> None:
        """Use Fox's calling frequency for Hound R+rpt replies where applicable."""
        if not self.special_activity.get("enabled") or self.special_activity.get("role") != "hound":
            return
        if self.special_activity.get("submode") != "foxhound":
            return
        try:
            frequency = int(round(float(getattr(message, "freq", 0) or 0)))
        except (TypeError, ValueError):
            frequency = 0
        if 300 <= frequency <= 900:
            self.tx_audio_frequency = frequency
    
    async def _complete_qso(self, qso: QSOSession):
        """Complete a QSO and log it"""
        if not self.active_attempt_id and self.active_qsos.get(qso.their_call) is qso:
            self.active_attempt_id = qso.attempt_id
        if not self._attempt_is_current(qso.attempt_id):
            self._record_decision("log-skipped", "stale-attempt-completion", call=qso.their_call, attempt_id=qso.attempt_id, active_attempt_id=self.active_attempt_id)
            return
        if qso.attempt_id in self.completed_attempt_ids:
            self._record_decision("log-skipped", "attempt-already-completed", call=qso.their_call, attempt_id=qso.attempt_id)
            return
        logger.info(f"QSO complete with {qso.their_call}")
        
        self.stats['qso_completed'] += 1
        self.completed_attempt_ids.add(qso.attempt_id)
        qso.status = "completed"
        self.automation_controller.mark_qso_complete(qso.their_call, mode=self.mode)
        if self.enabled and self.automation_controller.settings.auto_log_to_wavelog:
            await self._log_completed_qso(qso)
        
        # Notify callback
        if self.on_qso_complete:
            await self.on_qso_complete(qso)
        
        # Remove from active QSOs
        if qso.their_call in self.active_qsos:
            del self.active_qsos[qso.their_call]
        if self.active_attempt_id == qso.attempt_id:
            self.active_attempt_id = None
        if self.active_tx_message and qso.their_call in self.active_tx_message.upper().split():
            self.active_tx_message = None
            self.tx_queue.clear()
            self.tx_message_attempt_ids.clear()
        self.tx_watchdog_started_at = None
        if not self._automation_should_keep_tx_armed():
            self.tx_enabled = False
            self.auto_sequence = False
            self.tx_status = "QSO complete; TX disabled"

    async def _log_completed_qso(self, qso: QSOSession) -> None:
        """Log a completed Digital QSO through the canonical Wavelog/ADIF path."""
        try:
            from services.qso_logging import QSORequest, build_qso_dedupe_key, log_qso
            frequency = float(qso.frequency or 0)
            if not (1 <= frequency <= 100):
                try:
                    from services.radio import get_radio_instance
                    flex = get_radio_instance()
                    frequency = float(getattr(flex, "current_freq", 0) or 0)
                except Exception:
                    frequency = 0.0
            if not frequency:
                qso.log_result = {"success": False, "message": "Missing dial frequency for Digital QSO log"}
                qso.log_status = "skipped_missing_frequency"
                return
            try:
                from radio_control.spot_processor import band_from_khz
                band = band_from_khz(frequency * 1000)
            except Exception:
                band = ""
            qso_time = (qso.started_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
            qso_payload = {
                "callsign": qso.their_call,
                "frequency": frequency,
                "band": band,
                "mode": self.mode,
                "rst_sent": qso.my_report or "+00",
                "rst_received": qso.their_report or "+00",
                "gridsquare": qso.their_grid,
                "date_time": qso_time,
            }
            qso_key = build_qso_dedupe_key(qso_payload)
            qso_request = QSORequest(
                callsign=qso.their_call,
                frequency=frequency,
                band=band,
                mode=self.mode,
                rst_sent=qso.my_report or "+00",
                rst_received=qso.their_report or "+00",
                gridsquare=qso.their_grid,
                date_time=qso_time,
                notes="Completed in built-in DIGITAL",
                qso_key=qso_key,
            )
            result = await log_qso(qso_request)
            qso.logged = bool(result.get("success"))
            qso.log_result = result
            if result.get("duplicate"):
                qso.log_status = "duplicate_skipped"
            else:
                qso.log_status = "logged" if qso.logged else "queued_or_failed"
            self._record_decision("qso-logged" if qso.logged else "qso-log-fallback", qso.log_status, call=qso.their_call, attempt_id=qso.attempt_id)
        except Exception as exc:
            qso.logged = False
            qso.log_result = {"success": False, "message": str(exc)}
            qso.log_status = "failed"
            logger.error("Digital QSO backend logging failed for %s: %s", qso.their_call, exc, exc_info=True)

    def _automation_should_keep_tx_armed(self) -> bool:
        return bool(
            self.auto_cq_enabled
            or self.auto_call_enabled
        )
    
    async def _handle_tx_cycle(self, playback_delay_seconds: Optional[float] = None):
        """Handle TX cycle"""
        logger.debug("TX cycle started")

        if self.auto_cq_enabled and not self.tx_queue and not self.active_tx_message and self.auto_cq_remaining > 0:
            self.active_tx_message = f"CQ {self.mycall} {self.mygrid}"
            self.tx_queue.append(self.active_tx_message)
            self.auto_cq_remaining -= 1

        if self.tx_enabled and not self.tx_queue and self.active_tx_message:
            active_qso = self._active_qso_for_tx_message(self.active_tx_message)
            max_attempts = max(1, int(self.automation_controller.settings.max_attempts_per_target or 1))
            if active_qso and self.auto_call_enabled and active_qso.tx_count >= max_attempts and active_qso.rx_count == 0:
                self._cancel_current_attempt(
                    reason="max-call-attempts-expired",
                    backoff_active_target=True,
                    disable_tx=False,
                    pause_auto_engage=False,
                )
                self.auto_call_remaining = self._auto_call_attempt_budget()
                self.tx_status = f"max call attempts reached; backed off {active_qso.their_call}; searching next target"
                return
            if active_qso and self.auto_call_enabled and active_qso.rx_count == 0:
                if self.auto_call_remaining <= 0:
                    self._cancel_current_attempt(
                        reason="auto-call-attempt-budget-expired",
                        backoff_active_target=True,
                        disable_tx=False,
                        pause_auto_engage=False,
                    )
                    self.auto_call_remaining = self._auto_call_attempt_budget()
                    self.tx_status = f"auto-call attempt budget expired; backed off {active_qso.their_call}; searching next target"
                    return
                self.auto_call_remaining -= 1
            self.tx_queue.append(self.active_tx_message)
            if active_qso is not None:
                self.tx_message_attempt_ids[self.active_tx_message] = active_qso.attempt_id

        if len(self.tx_queue) > 0:
            if self.tx_in_progress:
                return
            message = self.tx_queue.pop(0)
            attempt_id = self.tx_message_attempt_ids.pop(message, None)
            if attempt_id is None:
                active_qso = self._active_qso_for_tx_message(message)
                attempt_id = active_qso.attempt_id if active_qso else None
            if not self._attempt_is_current(attempt_id):
                self._record_decision("tx-skipped", "stale-queued-intent", message=message, attempt_id=attempt_id, active_attempt_id=self.active_attempt_id)
                return
            self.active_tx_message = message
            try:
                self.tx_in_progress = True
                self.pending_tx_intent = None
                cycle_remaining = (
                    self._protocol_tx_audio_seconds() + 0.2
                    if playback_delay_seconds is not None
                    else float(self.cycle_duration or 0) - float(self.cycle_position or 0)
                )
                max_duration = min(
                    self._protocol_tx_audio_seconds(),
                    max(0.5, cycle_remaining - 0.2),
                )
                await self.transmit_message(
                    message,
                    max_duration_seconds=max_duration,
                    attempt_id=attempt_id,
                    playback_delay_seconds=(
                        playback_delay_seconds
                        if playback_delay_seconds is not None
                        else self._same_slot_playback_delay_seconds()
                    ),
                )
            except Exception as exc:
                if "aborted" in str(exc).lower():
                    self.tx_status = "switching TX message" if self._restart_tx_after_abort else "halted"
                else:
                    self.tx_status = f"TX failed: {exc}"
                if not self._restart_tx_after_abort:
                    self._cancel_current_attempt(
                        reason="tx-audio-failed",
                        backoff_active_target=True,
                        disable_tx=True,
                        pause_auto_engage=False,
                        inhibit_reason="tx_audio_failed",
                    )
                    self.tx_enabled = False
                logger.error("Digital TX failed; TX halted: %s", exc, exc_info=True)
            finally:
                self.tx_in_progress = False
                self._schedule_preempted_tx_restart()
    
    async def _handle_rx_cycle(self):
        """Handle RX cycle"""
        logger.debug("RX cycle started")
        
        # Clear audio buffer at start of RX
        # (Keep recent audio for decoding)
    
    async def transmit_message(
        self,
        message: str,
        max_duration_seconds: Optional[float] = None,
        attempt_id: Optional[str] = None,
        playback_delay_seconds: Optional[float] = None,
    ):
        """
        Transmit an FT8/FT4 message
        
        Args:
            message: Message text to transmit
        """
        if not self.tx_enabled:
            raise RuntimeError("TX is not enabled")
        if not self.tx_capability_enabled:
            raise RuntimeError(self.tx_engine.status.reason)
        if not self._attempt_is_current(attempt_id):
            self._record_decision("tx-skipped", "stale-attempt-before-audio", message=message, attempt_id=attempt_id, active_attempt_id=self.active_attempt_id)
            return

        mode = normalise_decode_mode(self.mode)
        limit = int(self.watchdog_cycles.get(mode, 2) or 0)
        active_qso = self._active_qso_for_tx_message(message)
        if self._expire_watchdog_if_due():
            return
        if active_qso is not None:
            self._start_attempt_watchdog()
        elif self.watchdog_enabled and limit > 0 and self.tx_watchdog_started_at:
            elapsed = (self._now() - self.tx_watchdog_started_at).total_seconds()
            if elapsed >= limit * 60:
                if self.auto_call_enabled and self.automation_controller.active_target_key:
                    self._cancel_current_attempt(
                        reason="watchdog-expired",
                        backoff_active_target=True,
                        disable_tx=False,
                        pause_auto_engage=False,
                    )
                    self.tx_status = "watchdog expired; attempt aborted and target backed off"
                    return
                self.tx_enabled = False
                self.tx_watchdog_started_at = None
                self.tx_status = f"watchdog halted after {limit} min {mode}"
                logger.warning(self.tx_status)
                return

        if not self.tx_enabled:
            if active_qso is not None and self.tx_capability_enabled:
                self.tx_enabled = True
                self.auto_sequence = True
            else:
                self.tx_enabled = False
                return

        if not message:
            self.tx_enabled = False
            return

        self.tx_status = f"transmitting {message}"
        if active_qso:
            active_qso.status = "tx_active"
        flex = self._ptt_target()
        loop = asyncio.get_running_loop()
        self.current_tx_message = message
        if playback_delay_seconds is not None:
            self._record_decision(
                "tx-prekeyed",
                "scheduled-playback-boundary",
                message=message,
                attempt_id=attempt_id,
                playback_delay_seconds=round(float(playback_delay_seconds), 3),
            )
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self.tx_engine.transmit(
                    message,
                    mode=mode,
                    audio_frequency=self.tx_audio_frequency,
                    flex=flex,
                    max_duration_seconds=max_duration_seconds,
                    playback_delay_seconds=playback_delay_seconds,
                ),
            )
        finally:
            if self.current_tx_message == message:
                self.current_tx_message = None
        if not self.tx_enabled:
            self.tx_status = "halted"
            return
        if not self._attempt_is_current(attempt_id):
            self._record_decision("tx-callback-ignored", "stale-attempt-after-audio", message=message, attempt_id=attempt_id, active_attempt_id=self.active_attempt_id)
            return
        self.tx_watchdog_counter += 1
        self.stats['transmitted_count'] += 1
        self.tx_status = f"sent {result.message}"
        if active_qso:
            active_qso.last_tx_time = self._now()
            active_qso.tx_count += 1
            active_qso.status = "waiting_for_reply"

        if self.on_tx_message:
            await self.on_tx_message(result.to_dict(), result.message)

        await self._complete_qso_after_final_tx(message, attempt_id=attempt_id)

    async def transmit_queued_now_if_possible(self, force_current_slot: bool = False) -> bool:
        """Transmit only when the current slot is still early enough to decode.

        FT8/FT4 frames are slot-synchronous. Starting several seconds into an
        over may still produce RF, but the other station will not decode it.
        ``force_current_slot`` means "try now if protocol-safe", not "send a
        truncated frame at any point in the slot".
        """
        if self.tx_in_progress or not self.tx_enabled or not self.tx_queue:
            return False

        cycle_duration, cycle_position, _cycle_number, slot_is_tx = self._live_cycle_state()
        self.cycle_duration = cycle_duration
        self.cycle_position = cycle_position
        self.slot_is_tx = bool(slot_is_tx)

        if not slot_is_tx:
            self.tx_status = "queued for next TX slot; current over is RX"
            self._record_decision("tx-scheduled", "current-slot-is-rx", pending=self.pending_tx_intent)
            return False

        mode = normalise_decode_mode(self.mode)
        max_safe_late_start = self._max_safe_late_start_seconds(mode)
        if cycle_position > max_safe_late_start:
            self.tx_status = f"queued for next TX slot; {cycle_position:.1f}s after slot start is too late"
            self._record_decision("tx-scheduled", "safe-start-deadline-missed", mode=mode, cycle_position=cycle_position, max_safe_late_start=max_safe_late_start, pending=self.pending_tx_intent)
            return False

        remaining = max(0.0, float(cycle_duration or 0) - float(cycle_position or 0))
        message = self.tx_queue.pop(0)
        attempt_id = self.tx_message_attempt_ids.pop(message, None)
        if attempt_id is None:
            active_qso = self._active_qso_for_tx_message(message)
            attempt_id = active_qso.attempt_id if active_qso else None
        if not self._attempt_is_current(attempt_id):
            self._record_decision("tx-skipped", "stale-queued-intent", message=message, attempt_id=attempt_id, active_attempt_id=self.active_attempt_id)
            return False
        self.active_tx_message = message
        try:
            self.tx_in_progress = True
            self.pending_tx_intent = None
            max_duration = min(self._protocol_tx_audio_seconds(mode), max(0.5, remaining - 0.2))
            self._record_decision("tx-started", "safe-slot-start", message=message, attempt_id=attempt_id, cycle_position=cycle_position)
            if attempt_id:
                await self.transmit_message(
                    message,
                    max_duration_seconds=max_duration,
                    attempt_id=attempt_id,
                    playback_delay_seconds=self._same_slot_playback_delay_seconds(mode),
                )
            else:
                await self.transmit_message(
                    message,
                    max_duration_seconds=max_duration,
                    playback_delay_seconds=self._same_slot_playback_delay_seconds(mode),
                )
            return True
        except Exception as exc:
            if "aborted" in str(exc).lower():
                self.tx_status = "switching TX message" if self._restart_tx_after_abort else "halted"
            else:
                self.tx_status = f"TX failed: {exc}"
            if not self._restart_tx_after_abort:
                self.tx_enabled = False
            logger.error("Immediate digital TX failed; TX halted: %s", exc, exc_info=True)
            return False
        finally:
            self.tx_in_progress = False
            self._schedule_preempted_tx_restart()

    async def _complete_qso_after_final_tx(self, message: str, attempt_id: Optional[str] = None) -> None:
        parts = self._message_tokens(str(message or "").upper())
        if len(parts) < 3 or parts[-1] not in {"73", "RR73"}:
            return
        their_call = self._extract_counterparty_call(" ".join(parts), parts)
        if not their_call:
            return
        qso = self.active_qsos.get(their_call)
        if qso and qso.state in {QSOState.SENDING_73, QSOState.SENDING_RRR} and self._attempt_is_current(attempt_id or qso.attempt_id):
            qso.state = QSOState.COMPLETE
            await self._complete_qso(qso)

    async def queue_tx_message(self, message: str, automation: Optional[str] = None, attempt_id: Optional[str] = None):
        """Add message to TX queue"""
        if not self.tx_capability_enabled:
            raise RuntimeError(self.tx_engine.status.reason)
        if not self._special_activity_allows_transmit():
            raise RuntimeError(self._special_activity_block_reason())
        parts = self._message_tokens(str(message or "").upper())
        their_call = self._extract_counterparty_call(" ".join(parts), parts) if parts else None
        qso = self.active_qsos.get(their_call) if their_call else None
        if qso is not None and not self.active_attempt_id:
            self.active_attempt_id = qso.attempt_id
        attempt_id = attempt_id or (qso.attempt_id if qso else self.active_attempt_id)
        if not self._attempt_is_current(attempt_id):
            self._record_decision("tx-skipped", "stale-queue-request", message=message, attempt_id=attempt_id, active_attempt_id=self.active_attempt_id)
            return
        if (
            qso is not None
            and len(parts) >= 3
            and parts[-1] not in {"RR73", "73", "RRR"}
            and GRID_RE.match(parts[-1])
            and qso.rx_count > 0
        ):
            # Once the other station has replied, never let an old Tx1 locator
            # message replace the required report/ack message for that QSO.
            self.tx_status = f"ignored stale locator message for active QSO with {qso.their_call}"
            return
        self._maybe_preempt_stale_tx(qso, message)
        self.active_tx_message = message
        self._seed_qso_from_tx_message(message)
        if qso is not None:
            self._start_attempt_watchdog()
        if message not in self.tx_queue:
            self.tx_queue.append(message)
            self.tx_message_attempt_ids[message] = attempt_id
            self.pending_tx_intent = {
                "message": message,
                "intent_id": str(uuid.uuid4()),
                "attempt_id": attempt_id,
                "call": their_call,
                "mode": self.mode,
                "band": "",
                "dial_frequency": 0,
                "audio_frequency": self.tx_audio_frequency,
                "source": automation or "manual",
                "reason": automation or "manual queue",
                "scheduled_slot_utc": self._next_tx_slot_iso(),
                "tx_cycle_parity": self._desired_tx_cycle_parity(),
            }
            if automation == "auto_call" and self.auto_call_remaining > 0:
                self.auto_call_remaining -= 1
            self._record_decision("tx-pending", "message-queued", message=message, attempt_id=attempt_id, automation=automation)
            logger.info(f"Queued for TX: {message}")

    def _special_activity_allows_transmit(self) -> bool:
        if not self.special_activity.get("enabled"):
            return True
        role = self.special_activity.get("role")
        submode = self.special_activity.get("submode")
        if role == "fox":
            return False
        if submode == "superfox":
            return bool(self.special_activity.get("superfox_verified"))
        return submode in {"standard", "foxhound"}

    def _special_activity_block_reason(self) -> str:
        role = self.special_activity.get("role")
        submode = self.special_activity.get("submode")
        if role == "fox":
            return "Built-in Digital automation supports hunting DXpeditions as Hound, not operating as Fox"
        if submode == "superfox":
            return "SuperFox automation requires a verified SuperFox decode before transmitting"
        return "Special activity automation is not available for this mode"

    def enable_tx(self) -> None:
        if not self.tx_capability_enabled:
            raise RuntimeError(self.tx_engine.status.reason)
        self.tx_inhibit_reason = None
        self.auto_engage_paused_until = None
        self.tx_enabled = True
        self.auto_sequence = True
        self.tx_watchdog_counter = 0
        self.tx_status = "enabled"

    def halt_tx(self) -> None:
        self._cancel_current_attempt(
            reason="halt-tx",
            backoff_active_target=True,
            disable_tx=True,
            pause_auto_engage=True,
            inhibit_reason="user_abort",
        )
        self.tx_status = "halted"

    def clear_current_qso(self) -> None:
        """Clear the active QSO attempt without turning Auto Call into Auto CQ."""
        self._cancel_current_attempt(
            reason="clear-qso",
            backoff_active_target=True,
            disable_tx=False,
            pause_auto_engage=True,
        )
        self.tx_status = "QSO cleared"

    def abort_current_attempt(self) -> None:
        """Hard safety stop for the current digital attempt and TX path."""
        self._cancel_current_attempt(
            reason="operator-aborted",
            backoff_active_target=True,
            disable_tx=True,
            pause_auto_engage=True,
            inhibit_reason="user_abort",
        )
        self.tx_status = "current attempt aborted; TX inhibited until re-armed"

    def extend_watchdog(self) -> Dict[str, Any]:
        mode = normalise_decode_mode(self.mode)
        seconds = int(self.watchdog_cycles.get(mode, 0) or 0) * 60
        if not self.watchdog_enabled or seconds <= 0:
            self.tx_status = "watchdog extension ignored; watchdog disabled"
            return {"extended": False, "seconds": 0, "stats": self.get_stats()}
        if not self._watchdog_is_active():
            self.tx_status = "watchdog extension ignored; no active QSO attempt"
            return {"extended": False, "seconds": 0, "stats": self.get_stats()}

        self.tx_watchdog_started_at += timedelta(seconds=seconds)
        minutes = max(1, seconds // 60)
        self.tx_status = f"watchdog extended by {minutes} min {mode}"
        return {"extended": True, "seconds": seconds, "stats": self.get_stats()}

    def set_tx_options(
        self,
        *,
        tx_audio_frequency: Optional[int] = None,
        tx_even_first: Optional[bool] = None,
        watchdog_ft8: Optional[int] = None,
        watchdog_ft4: Optional[int] = None,
        watchdog_enabled: Optional[bool] = None,
        auto_cq: Optional[bool] = None,
        auto_call: Optional[bool] = None,
        cq_only: Optional[bool] = None,
        auto_cq_limit: Optional[int] = None,
        auto_call_limit: Optional[int] = None,
        special_activity: Optional[Dict[str, Any]] = None,
    ) -> None:
        if special_activity is not None:
            self.set_special_activity(special_activity)
        if tx_audio_frequency is not None:
            low, high = self._tx_audio_limits()
            self.tx_audio_frequency = max(low, min(high, int(tx_audio_frequency)))
        if tx_even_first is not None:
            self.tx_even_first = bool(tx_even_first)
        if watchdog_enabled is not None:
            self.watchdog_enabled = bool(watchdog_enabled)
        if watchdog_ft8 is not None:
            self.watchdog_cycles["FT8"] = max(0, min(30, int(watchdog_ft8)))
        if watchdog_ft4 is not None:
            self.watchdog_cycles["FT4"] = max(0, min(30, int(watchdog_ft4)))
        if auto_cq is not None:
            self.auto_cq_enabled = bool(auto_cq)
        if auto_call or auto_cq:
            from services.digital_engine import require_om0rx_planner
            require_om0rx_planner()
        if auto_call is not None:
            self.auto_call_enabled = bool(auto_call)
        if cq_only is not None:
            self.auto_call_cq_only = bool(cq_only)
        if auto_cq_limit is not None:
            self.auto_cq_limit = max(0, min(99, int(auto_cq_limit)))
            self.auto_cq_remaining = self.auto_cq_limit
        if auto_call_limit is not None:
            self.auto_call_limit = max(0, min(99, int(auto_call_limit)))
            self.auto_call_remaining = self.auto_call_limit

    def _tx_audio_limits(self) -> tuple[int, int]:
        if self.special_activity.get("enabled") and self.special_activity.get("role") == "hound":
            if self.special_activity.get("submode") == "foxhound":
                return self._normalise_audio_limit_pair(
                    self.special_activity.get("hound_tx_min") or 1000,
                    self.special_activity.get("hound_tx_max") or 4000,
                    default_low=1000,
                    default_high=4000,
                )
            if self.special_activity.get("submode") == "superfox":
                return self._normalise_audio_limit_pair(
                    self.special_activity.get("superfox_tx_min") or 200,
                    self.special_activity.get("superfox_tx_max") or 3000,
                    default_low=200,
                    default_high=3000,
                )
        return (200, 3000)

    @staticmethod
    def _normalise_audio_limit_pair(low_value: Any, high_value: Any, *, default_low: int, default_high: int) -> tuple[int, int]:
        try:
            low = int(low_value)
        except (TypeError, ValueError):
            low = default_low
        try:
            high = int(high_value)
        except (TypeError, ValueError):
            high = default_high
        low = max(200, min(5000, low))
        high = max(200, min(5000, high))
        if low > high:
            low, high = high, low
        return low, high

    def set_special_activity(self, settings: Optional[Dict[str, Any]]) -> None:
        incoming = settings or {}
        submode = str(incoming.get("submode", self.special_activity.get("submode", "standard")) or "standard").lower()
        role = str(incoming.get("role", self.special_activity.get("role", "hound")) or "hound").lower()
        if submode not in SUPPORTED_SPECIAL_SUBMODES:
            submode = "standard"
        if role not in SUPPORTED_SPECIAL_ROLES:
            role = "hound"
        updated = {
            **self.special_activity,
            **incoming,
            "enabled": bool(incoming.get("enabled", self.special_activity.get("enabled", False))),
            "role": role,
            "submode": submode,
            "superfox_otp": bool(incoming.get("superfox_otp", incoming.get("superFoxOtp", incoming.get("otp", self.special_activity.get("superfox_otp", False))))),
            "superfox_verified": bool(incoming.get("superfox_verified", incoming.get("superFoxVerified", self.special_activity.get("superfox_verified", False)))),
            "call_only_after_decode": bool(incoming.get("call_only_after_decode", incoming.get("callOnlyAfterDecode", self.special_activity.get("call_only_after_decode", True)))),
            "return_to_standard_after_qso": bool(incoming.get("return_to_standard_after_qso", incoming.get("returnToStandardAfterQso", self.special_activity.get("return_to_standard_after_qso", True)))),
        }
        hound_low, hound_high = self._normalise_audio_limit_pair(
            incoming.get("hound_tx_min", incoming.get("houndTxMin", updated.get("hound_tx_min", 1000))),
            incoming.get("hound_tx_max", incoming.get("houndTxMax", updated.get("hound_tx_max", 4000))),
            default_low=1000,
            default_high=4000,
        )
        superfox_low, superfox_high = self._normalise_audio_limit_pair(
            incoming.get("superfox_tx_min", incoming.get("superFoxTxMin", updated.get("superfox_tx_min", 200))),
            incoming.get("superfox_tx_max", incoming.get("superFoxTxMax", updated.get("superfox_tx_max", 3000))),
            default_low=200,
            default_high=3000,
        )
        updated["hound_tx_min"] = hound_low
        updated["hound_tx_max"] = hound_high
        updated["superfox_tx_min"] = superfox_low
        updated["superfox_tx_max"] = superfox_high
        self.special_activity = updated
        low, high = self._tx_audio_limits()
        self.tx_audio_frequency = max(low, min(high, self.tx_audio_frequency))

    async def transmit_tune_tone(self, duration_seconds: float = 5.0):
        if not self.tx_capability_enabled:
            raise RuntimeError(self.tx_engine.status.reason)
        flex = self._ptt_target()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.tx_engine.tune_tone(
                audio_frequency=self.tx_audio_frequency,
                duration_seconds=duration_seconds,
                flex=flex,
            ),
        )
        self.tx_status = "tune tone sent"
        if self.on_tx_message:
            await self.on_tx_message(result.to_dict(), result.message)
        return result.to_dict()
    
    async def call_cq(self):
        """Initiate a CQ call"""
        message = f"CQ {self.mycall} {self.mygrid}"
        await self.queue_tx_message(message)
    
    async def reply_to_call(self, their_call: str, my_report: str = "R-15"):
        """Reply to a call"""
        message = f"{their_call} {self.mycall} {my_report}"
        await self.queue_tx_message(message)
    
    async def send_73(self, their_call: str):
        """Send 73"""
        message = f"{their_call} {self.mycall} 73"
        await self.queue_tx_message(message)

    async def queue_manual_tx_button(self, tx_id: int) -> str:
        """Queue a manual TX button message through the backend QSO state."""
        if int(tx_id) == 6:
            if self.active_attempt_id or self.active_qsos:
                raise RuntimeError("CQ manual TX is isolated to idle state; abort or complete the active QSO first")
            message = f"CQ {self.mycall} {self.mygrid[:4]}"
            await self.queue_tx_message(message)
            return message
        qso = next(iter(self.active_qsos.values()), None)
        if not qso or not self._attempt_is_current(qso.attempt_id):
            raise RuntimeError("No active backend QSO attempt for manual TX")
        report = qso.my_report or "-15"
        messages = {
            1: f"{qso.their_call} {self.mycall} {self.mygrid[:4]}",
            2: f"{qso.their_call} {self.mycall} {report}",
            3: f"{qso.their_call} {self.mycall} R{report}",
            4: f"{qso.their_call} {self.mycall} RR73",
            5: f"{qso.their_call} {self.mycall} 73",
        }
        message = messages.get(int(tx_id))
        if not message:
            raise RuntimeError(f"Unsupported TX button {tx_id}")
        await self._queue_qso_message(qso, message)
        return message
    
    def get_decoded_messages(self, limit: int = 50) -> List[Dict]:
        """Get recent decoded messages"""
        messages = self.decoded_messages[-limit:]
        return [msg.to_dict() if hasattr(msg, "to_dict") else msg for msg in messages]

    def clear_decoded_messages(self) -> None:
        """Clear decoded message history and receive-side display buffers."""
        self.decoded_messages.clear()
        self.audio_processor.clear_buffer()
        self._last_decode_slot_start = None
    
    def get_active_qsos(self) -> List[Dict]:
        """Get active QSO sessions"""
        return [qso.to_dict() for qso in self.active_qsos.values()]
    
    def get_waterfall_data(self) -> List[List[int]]:
        """Get waterfall display data"""
        if not self.audio_stream_enabled:
            return []
        return self.audio_processor.generate_waterfall()
    
    def get_stats(self) -> Dict:
        """Get service statistics"""
        uptime = 0
        now = datetime.now(timezone.utc)
        slot_now = self._slot_now()
        if self.enabled and self.started_at:
            uptime = int((now - self.started_at).total_seconds())

        watchdog_limit_seconds = self._watchdog_limit_seconds()
        watchdog_elapsed = 0
        watchdog_remaining = 0
        watchdog_active = self._watchdog_is_active()
        if watchdog_active and self.tx_watchdog_started_at and watchdog_limit_seconds > 0:
            watchdog_elapsed = max(0, int((now - self.tx_watchdog_started_at).total_seconds()))
            watchdog_remaining = max(0, watchdog_limit_seconds - watchdog_elapsed)

        cycle_duration = self._cycle_duration_seconds()
        live_cycle_position = slot_now.timestamp() % cycle_duration if cycle_duration else 0.0
        live_cycle = int(slot_now.timestamp() // cycle_duration) if cycle_duration else 0
        live_even_cycle = (live_cycle % 2) == 0
        live_slot_is_tx = live_even_cycle if self.tx_even_first else not live_even_cycle
        self.cycle_duration = cycle_duration
        self.cycle_position = live_cycle_position
        self.slot_is_tx = bool(live_slot_is_tx)
        tx_ptt_command_active = bool(getattr(self.tx_engine, "ptt_on", self.tx_in_progress))
        tx_radio_mox = None
        tx_radio_interlock = None
        tx_ptt_backend = getattr(self.ptt_device, "backend_name", "flex") if self.ptt_device is not None else "flex"
        tx_ptt_backend_error = getattr(self.ptt_device, "last_error", None) if self.ptt_device is not None else None
        tx_rf_active = bool(self.tx_in_progress)
        if self.ptt_method == "CAT":
            try:
                ptt_target = self._ptt_target()
                if ptt_target is not None:
                    poll_ptt = getattr(ptt_target, "poll_ptt", None)
                    if callable(poll_ptt):
                        tx_radio_mox = poll_ptt(max_age_seconds=0.75)
                    else:
                        tx_radio_mox_value = getattr(ptt_target, "current_mox", None)
                        tx_radio_mox = bool(tx_radio_mox_value) if tx_radio_mox_value is not None else None
                    tx_radio_interlock = str(getattr(ptt_target, "current_interlock_state", "") or "").upper() or None
            except Exception as exc:
                logger.debug("Unable to read radio TX state for FT8 status: %s", exc, exc_info=True)
            tx_rf_active = bool(tx_radio_mox or tx_radio_interlock == "TRANSMITTING")
        self.is_tx_cycle = bool((live_slot_is_tx and self.tx_enabled) or self.tx_in_progress)
        active_qso = next(iter(self.active_qsos.values()), None)
        if active_qso:
            if self.tx_in_progress:
                active_state = "tx_active"
            elif self.pending_tx_intent or self.tx_queue:
                active_state = "tx_pending"
            elif active_qso.state == QSOState.COMPLETE:
                active_state = "completed_logged" if active_qso.logged else "completed"
            else:
                active_state = active_qso.status or "waiting_for_reply"
        elif self.pending_tx_intent or self.tx_queue:
            active_state = "tx_pending"
        elif self.tx_status.startswith("current attempt aborted") or self.tx_status == "halted":
            active_state = "aborted_cancelled"
        else:
            active_state = "idle"

        tx_engine_status = self.tx_engine.status.to_dict()
        tx_engine_status.update({
            "last_audio_output_device": getattr(self.tx_engine, "last_audio_output_device", None),
            "last_audio_peak": getattr(self.tx_engine, "last_audio_peak", 0.0),
            "last_audio_rms": getattr(self.tx_engine, "last_audio_rms", 0.0),
        })

        return {
            **self.stats,
            'uptime': uptime,
            'mode': self.mode,
            'enabled': self.enabled,
            'tx_enabled': self.tx_enabled,
            'tx_armed': self.tx_enabled,
            'tx_inhibit': self.tx_inhibit_reason,
            'tx_inhibit_reason': self.tx_inhibit_reason,
            'auto_sequence': self.auto_sequence,
            'auto_call_enabled': self.auto_call_enabled,
            'auto_cq_enabled': self.auto_cq_enabled,
            'auto_call_cq_only': self.auto_call_cq_only,
            'active_qsos': len(self.active_qsos),
            'active_attempt_id': self.active_attempt_id,
            'active_target': active_qso.their_call if active_qso else None,
            'active_qso': active_qso.to_dict() if active_qso else None,
            'digital_state': active_state,
            'tx_queue_length': len(self.tx_queue),
            'is_tx_cycle': self.is_tx_cycle,
            'tx_in_progress': self.tx_in_progress,
            'tx_ptt_command_active': tx_ptt_command_active,
            'tx_radio_mox': tx_radio_mox,
            'tx_radio_interlock': tx_radio_interlock,
            'tx_rf_active': tx_rf_active,
            'tx_ptt_backend': tx_ptt_backend,
            'tx_ptt_backend_error': tx_ptt_backend_error,
            'slot_is_tx': self.slot_is_tx,
            'cycle_duration': cycle_duration,
            'cycle_position': live_cycle_position,
            'cycle_remaining': max(0.0, float(cycle_duration or 0) - float(live_cycle_position or 0)),
            'engine': 'ft8_lib',
            'engine_license': 'MIT',
            'decoder_status': 'available' if self.rx_decoder.status.available else 'unavailable',
            'rx_decoder': get_ft8_rx_decoder_status(),
            'rx_audio_capture': self.audio_capture.get_stats(),
            'tx_engine': tx_engine_status,
            'transmit_status': self.tx_status,
            'automation_status': self.automation_status,
            'automation_last_error': self.automation_last_error,
            'tx_audio_frequency': self.tx_audio_frequency,
            'tx_even_first': self.tx_even_first,
            'watchdog_cycles': self.watchdog_cycles,
            'watchdog_counter': self.tx_watchdog_counter,
            'watchdog_limit_seconds': watchdog_limit_seconds,
            'watchdog_started_at': self.tx_watchdog_started_at.isoformat() if self.tx_watchdog_started_at else None,
            'watchdog_active': watchdog_active,
            'watchdog_elapsed_seconds': watchdog_elapsed,
            'watchdog_remaining_seconds': watchdog_remaining,
            'active_tx_message': self.active_tx_message,
            'pending_message': (self.pending_tx_intent or {}).get("message") or self.active_tx_message,
            'pending_tx_intent': self.pending_tx_intent,
            'target_retry_count': self._active_target_retry_count(),
            'target_backoff_list': self._backoff_targets_debug(),
            'last_auto_call_decision_reason': (self.automation_decisions[-1]["reason"] if self.automation_decisions else None),
            'last_cancel_abort_reason': self.last_cancel_abort_reason,
            'auto_cq_remaining': self.auto_cq_remaining,
            'auto_call_remaining': self.auto_call_remaining,
            'special_activity': self.special_activity,
            'automation_controller': self.automation_controller.status(),
            'automation_decisions': self.automation_decisions[-20:],
            'time_sync': self._get_cached_time_sync(),
            'time_correction_seconds': self._clock_offset_seconds(),
            'capabilities': {
                'waterfall': True,
                'audio_stream': True,
                'rx_decode': self.rx_decoder.status.available,
                'tx': self.tx_capability_enabled,
                'message_encode': True,
                'foxhound_hound': True,
                'fox_mode': False,
                'superfox_rx': False,
                'superfox_tx': False,
            }
        }

    def _get_cached_time_sync(self) -> dict:
        now = datetime.now(timezone.utc).timestamp()
        if now - self._time_sync_checked_at > 300:
            self._time_sync_cache = ntp_offset(timeout=0.35)
            self._time_sync_checked_at = now
        return self._time_sync_cache
    
    def set_mode(self, mode: str) -> None:
        """Switch receive/transmit timing mode without recreating the service."""
        mode_upper = normalise_decode_mode(mode)
        if mode_upper == self.mode:
            return
        self.mode = mode_upper
        self.audio_processor = FT8AudioProcessor(self.mode, sample_rate=self.decoder_sample_rate)
        self._last_decode_slot_start = None
        self.last_tx_slot = None
        logger.info("Digital mode changed to %s", self.mode)

    def set_config(self, mycall: Optional[str] = None, mygrid: Optional[str] = None, mode: Optional[str] = None, operator_settings: Optional[Dict[str, Any]] = None):
        """Update configuration"""
        if mode:
            self.set_mode(mode)
        if mycall:
            self.mycall = mycall.upper()
            self.automation_controller.update_mycall(self.mycall)
        if mygrid:
            self.mygrid = mygrid.upper()
        if operator_settings:
            self.automation_controller.apply_operator_settings(operator_settings)
            special = operator_settings.get("specialActivity") or operator_settings.get("special_activity")
            if special:
                self.set_special_activity(special)
        
        logger.info(f"Config updated: {self.mycall}, {self.mygrid}")


# Global FT8 service instance
_ft8_service: Optional[FT8Service] = None


def get_ft8_service() -> FT8Service:
    """Get global FT8 service instance"""
    global _ft8_service
    if _ft8_service is None:
        _ft8_service = FT8Service()
    return _ft8_service


async def init_ft8_service(mode: str = 'FT8', mycall: str = 'OM0RX', mygrid: str = 'JN88',
                            audio_device: Optional[str] = None, audio_output: Optional[str] = None,
                            audio_sample_rate: int = 12000, ptt_method: str = "CAT",
                            ptt_device: Any = None):
    """Initialize FT8 service with optional audio device"""
    global _ft8_service
    
    # Parse audio device index from string like "23: DAX Audio RX 1..."
    device_to_use = None
    if audio_device and audio_device != 'default':
        try:
            # Try to extract device index if format is "X: Device Name"
            if ':' in audio_device:
                device_index = int(audio_device.split(':')[0].strip())
                device_to_use = str(device_index)
                logger.info(f"Using audio device index: {device_index}")
            else:
                device_to_use = audio_device
                logger.info(f"Using audio device: {audio_device}")
        except (ValueError, IndexError):
            device_to_use = audio_device
            logger.warning(f"Could not parse device index, using device name: {audio_device}")
    
    output_to_use = None
    if audio_output and audio_output != 'default':
        if ':' in audio_output:
            try:
                output_to_use = str(int(audio_output.split(':')[0].strip()))
            except (ValueError, IndexError):
                output_to_use = audio_output
        else:
            output_to_use = audio_output

    if _ft8_service is not None and _ft8_service.enabled:
        await _ft8_service.stop()

    _ft8_service = FT8Service(
        mode,
        mycall,
        mygrid,
        audio_device=device_to_use,
        audio_output=output_to_use,
        audio_sample_rate=audio_sample_rate,
        ptt_method=ptt_method,
        ptt_device=ptt_device,
    )
    return _ft8_service
