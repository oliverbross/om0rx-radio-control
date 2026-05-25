"""
FT8/FT4 Service - Main Orchestrator
Coordinates decoding, encoding, QSO management, and auto-sequencing
"""

import asyncio
import logging
import concurrent.futures
from typing import Optional, List, Dict, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

from services.ft8_protocol import FT8Protocol, FT8Message
from services.ft8_audio import FT8AudioProcessor
from services.audio_capture import AudioCaptureService, AudioCaptureConfig, get_audio_capture_service
from services.ft8_validation import FT8Validator

logger = logging.getLogger(__name__)


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
    state: QSOState = QSOState.IDLE
    their_grid: Optional[str] = None
    my_report: Optional[str] = None
    their_report: Optional[str] = None
    frequency: float = 0.0
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_tx_time: Optional[datetime] = None
    last_rx_time: Optional[datetime] = None
    tx_count: int = 0
    rx_count: int = 0
    
    def to_dict(self) -> dict:
        return {
            'their_call': self.their_call,
            'my_call': self.my_call,
            'state': self.state.value,
            'their_grid': self.their_grid,
            'my_report': self.my_report,
            'their_report': self.their_report,
            'frequency': self.frequency,
            'started_at': self.started_at.isoformat(),
            'tx_count': self.tx_count,
            'rx_count': self.rx_count
        }


class FT8Service:
    """Main FT8/FT4 Service"""
    
    def __init__(self, mode: str = 'FT8', mycall: str = 'OM0RX', mygrid: str = 'JN88', 
                 audio_device: Optional[str] = None):
        """
        Initialize FT8/FT4 service
        
        Args:
            mode: 'FT8' or 'FT4'
            mycall: Your callsign
            mygrid: Your grid square
            audio_device: Audio device name for capture (None = default)
        """
        self.mode = mode
        self.mycall = mycall.upper()
        self.mygrid = mygrid.upper()
        
        # Protocol and audio processors
        self.protocol = FT8Protocol(mode)
        self.audio_processor = FT8AudioProcessor(mode)
        
        # Audio capture
        audio_config = AudioCaptureConfig(
            device_name=audio_device,
            sample_rate=12000,
            channels=1,
            blocksize=1024
        )
        self.audio_capture = get_audio_capture_service(audio_config)
        self.audio_capture.set_audio_callback(self._on_audio_samples)
        
        # State
        self.enabled = False
        self.tx_enabled = False
        self.auto_sequence = False
        
        # Decoded messages
        self.decoded_messages: List[FT8Message] = []
        self.max_decoded = 100
        
        # Active QSOs
        self.active_qsos: Dict[str, QSOSession] = {}
        
        # TX queue
        self.tx_queue: List[str] = []
        
        # Timing
        self.cycle_start = datetime.utcnow()
        self.is_tx_cycle = False
        
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
        
        # Audio streaming
        self.audio_stream_enabled = True  # Enable by default for client-side decoding
        self.audio_stream_buffer = []
        self.audio_stream_interval = 0.5  # Send audio every 0.5 seconds
        
        # Background tasks
        self.decode_task = None
        self.timing_task = None
        self.audio_task = None
        
        logger.info(f"FT8Service initialized: {mode}, {mycall}, {mygrid}")
    
    async def start(self):
        """Start FT8 service"""
        if self.enabled:
            logger.warning("FT8 service already running")
            return
        
        self.enabled = True
        logger.info(f"Starting {self.mode} service...")
        
        # Start audio capture
        if not self.audio_capture.start_capture():
            logger.error("Failed to start audio capture")
            self.enabled = False
            return
        
        # Start background tasks
        self.timing_task = asyncio.create_task(self._timing_loop())
        self.decode_task = asyncio.create_task(self._decode_loop())
        self.audio_task = asyncio.create_task(self._audio_processing_loop())
        
        logger.info(f"{self.mode} service started")
    
    async def stop(self):
        """Stop FT8 service"""
        if not self.enabled:
            return
        
        self.enabled = False
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
        
        # Wait for tasks to complete
        for task in [self.timing_task, self.decode_task, self.audio_task]:
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info(f"{self.mode} service stopped")
    
    async def _timing_loop(self):
        """Main timing loop - manages TX/RX cycles"""
        try:
            cycle_duration = 15 if self.mode == 'FT8' else 7.5  # seconds
            
            while self.enabled:
                current_time = datetime.utcnow()
                
                # Calculate time within cycle
                seconds = current_time.second + current_time.microsecond / 1000000.0
                cycle_position = seconds % cycle_duration
                
                # Determine if we're in TX or RX cycle
                # Even cycles (0-15, 30-45): RX
                # Odd cycles (15-30, 45-60): TX
                cycle_number = int(seconds / cycle_duration)
                is_even_cycle = (cycle_number % 2) == 0
                
                # Update TX/RX state
                self.is_tx_cycle = not is_even_cycle and self.tx_enabled
                
                # Handle cycle transition
                if cycle_position < 0.5:  # Just started a new cycle
                    if self.is_tx_cycle:
                        await self._handle_tx_cycle()
                    else:
                        await self._handle_rx_cycle()
                
                # Sleep until next check
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            logger.info("Timing loop cancelled")
        except Exception as e:
            logger.error(f"Error in timing loop: {e}", exc_info=True)
    
    async def _decode_loop(self):
        """Background decode loop"""
        try:
            last_stream_time = datetime.utcnow()
            
            while self.enabled:
                # Get audio buffer
                audio_buffer = self.audio_processor.get_audio_buffer()
                
                if len(audio_buffer) > 0:
                    # Process audio for waterfall
                    spectrum = self.audio_processor.process_audio_chunk(audio_buffer[-2048:])
                    if spectrum is not None:
                        self.audio_processor.update_waterfall(spectrum)
                    
                    # Stream audio to frontend for client-side decoding
                    if self.audio_stream_enabled and self.on_audio_stream:
                        now = datetime.utcnow()
                        if (now - last_stream_time).total_seconds() >= self.audio_stream_interval:
                            # Send recent audio chunk to frontend
                            chunk_size = int(self.audio_processor.sample_rate * self.audio_stream_interval)
                            audio_chunk = audio_buffer[-chunk_size:] if len(audio_buffer) >= chunk_size else audio_buffer
                            
                            if len(audio_chunk) > 0:
                                # Convert to list for JSON serialization
                                audio_data = audio_chunk.tolist() if isinstance(audio_chunk, np.ndarray) else list(audio_chunk)
                                await self.on_audio_stream(audio_data)
                            
                            last_stream_time = now
                    
                    # Attempt decoding if we have enough audio (server-side backup)
                    buffer_duration = len(audio_buffer) / self.audio_processor.sample_rate
                    required_duration = 12.64 if self.mode == 'FT8' else 4.48
                    
                    if buffer_duration >= required_duration:
                        await self._attempt_decode(audio_buffer)
                
                # Sleep between decode attempts
                await asyncio.sleep(0.2)  # Faster loop for audio streaming
                
        except asyncio.CancelledError:
            logger.info("Decode loop cancelled")
        except Exception as e:
            logger.error(f"Error in decode loop: {e}", exc_info=True)
    
    async def _attempt_decode(self, audio_buffer: np.ndarray):
        """
        Attempt to decode FT8/FT4 signals from audio buffer
        
        Offloads CPU-intensive signal detection and decoding to thread pool
        to prevent blocking the async event loop
        """
        try:
            loop = asyncio.get_event_loop()
            
            # Use thread pool for CPU-intensive detection
            if self.mode == 'FT8':
                # Detect signals in thread pool
                signals = await loop.run_in_executor(
                    None,
                    self.audio_processor.detect_ft8_signals_with_sync,
                    audio_buffer
                )
                
                for freq, dt, sync_score in signals:
                    # Extract signal at detected frequency and time
                    time_offset_samples = int(dt * self.audio_processor.sample_rate)
                    signal_start = time_offset_samples
                    signal_end = signal_start + int(12.64 * self.audio_processor.sample_rate)
                    
                    if signal_end > len(audio_buffer):
                        continue
                    
                    signal_audio = audio_buffer[signal_start:signal_end]
                    signal_audio = self.audio_processor.extract_signal(signal_audio, freq)
                    
                    # Decode tone sequence in thread pool
                    tones = await loop.run_in_executor(
                        None,
                        self.audio_processor.decode_tone_sequence,
                        signal_audio,
                        freq
                    )
                    
                    if tones is not None and len(tones) >= self.audio_processor.FT8_EXPECTED_SYMBOLS:
                        # Estimate SNR from sync score
                        snr = -5.0 + sync_score * 20.0  # Rough estimate
                        
                        # Decode symbols to message
                        message = self.protocol.decode_symbols(tones[:self.audio_processor.FT8_EXPECTED_SYMBOLS], snr, dt, freq)
                        
                        if message:
                            await self._handle_decoded_message(message)
            else:
                # FT4: Use basic detection in thread pool
                signals = await loop.run_in_executor(
                    None,
                    self.audio_processor.detect_signals,
                    audio_buffer
                )
                
                for freq, strength in signals:
                    signal_audio = self.audio_processor.extract_signal(audio_buffer, freq)
                    
                    # Decode tone sequence in thread pool
                    tones = await loop.run_in_executor(
                        None,
                        self.audio_processor.decode_tone_sequence,
                        signal_audio,
                        freq
                    )
                    
                    if tones is not None:
                        snr = strength
                        dt = 0.0
                        message = self.protocol.decode_symbols(tones, snr, dt, freq)
                        
                        if message:
                            await self._handle_decoded_message(message)
                        
        except Exception as e:
            logger.error(f"Error attempting decode: {e}", exc_info=True)
    
    def _on_audio_samples(self, samples: np.ndarray):
        """
        Callback for incoming audio samples
        
        Args:
            samples: Audio samples from capture device
        """
        # Add to audio processor buffer
        self.audio_processor.add_audio_samples(samples)
    
    async def _audio_processing_loop(self):
        """Process audio samples from queue"""
        try:
            while self.enabled:
                # Get audio samples from queue
                samples = await self.audio_capture.get_audio_samples()
                
                if samples is not None:
                    # Process for waterfall
                    if len(samples) >= 512:
                        spectrum = self.audio_processor.process_audio_chunk(samples)
                        if spectrum is not None:
                            self.audio_processor.update_waterfall(spectrum)
                
                await asyncio.sleep(0.05)  # 50ms
                
        except asyncio.CancelledError:
            logger.info("Audio processing loop cancelled")
        except Exception as e:
            logger.error(f"Error in audio processing loop: {e}", exc_info=True)
    
    async def _handle_decoded_message(self, message: FT8Message):
        """Handle a decoded message"""
        # Add to decoded list
        self.decoded_messages.append(message)
        if len(self.decoded_messages) > self.max_decoded:
            self.decoded_messages.pop(0)
        
        self.stats['decoded_count'] += 1
        
        logger.info(f"Decoded: {message.message} (SNR: {message.snr:.1f} dB)")
        
        # Notify callback
        if self.on_message_decoded:
            await self.on_message_decoded(message)
        
        # Auto-sequence if enabled
        if self.auto_sequence:
            await self._auto_sequence_handler(message)
    
    async def _auto_sequence_handler(self, message: FT8Message):
        """Handle auto-sequencing logic"""
        msg_text = message.message.strip().upper()
        parts = msg_text.split()
        
        if len(parts) < 2:
            return
        
        # Check if message is for us
        if self.mycall not in parts:
            return
        
        # Extract other callsign
        their_call = parts[0] if parts[0] != self.mycall else parts[1] if len(parts) > 1 else None
        
        if not their_call:
            return
        
        # Get or create QSO session
        qso = self.active_qsos.get(their_call)
        
        if qso is None and 'CQ' in parts:
            # Don't auto-reply to CQs unless configured
            return
        
        if qso:
            # Update existing QSO
            await self._update_qso_state(qso, message)
        else:
            # Someone is calling us
            if self.mycall == parts[1]:  # "XX OM0RX ..."
                qso = QSOSession(
                    their_call=their_call,
                    my_call=self.mycall,
                    my_grid=self.mygrid,
                    state=QSOState.IDLE,
                    frequency=message.freq
                )
                self.active_qsos[their_call] = qso
                await self._update_qso_state(qso, message)
    
    async def _update_qso_state(self, qso: QSOSession, message: FT8Message):
        """Update QSO state machine"""
        msg = message.message.strip().upper()
        
        # Parse message type
        if any(x in msg for x in ['R-', 'R+', '+', '-']):
            # Signal report
            qso.their_report = msg.split()[-1]
            
            if qso.state == QSOState.WAITING_RESPONSE:
                # Send our report back
                qso.state = QSOState.SENDING_REPORT
                report_msg = f"{qso.their_call} {qso.my_call} R-15"
                await self.queue_tx_message(report_msg)
                
        elif 'RRR' in msg or 'RR73' in msg:
            # Acknowledgment
            qso.state = QSOState.SENDING_73
            msg_73 = f"{qso.their_call} {qso.my_call} 73"
            await self.queue_tx_message(msg_73)
            
        elif '73' in msg:
            # QSO complete
            qso.state = QSOState.COMPLETE
            await self._complete_qso(qso)
    
    async def _complete_qso(self, qso: QSOSession):
        """Complete a QSO and log it"""
        logger.info(f"QSO complete with {qso.their_call}")
        
        self.stats['qso_completed'] += 1
        
        # Notify callback
        if self.on_qso_complete:
            await self.on_qso_complete(qso)
        
        # Remove from active QSOs
        if qso.their_call in self.active_qsos:
            del self.active_qsos[qso.their_call]
    
    async def _handle_tx_cycle(self):
        """Handle TX cycle"""
        logger.debug("TX cycle started")
        
        # Check if we have messages to transmit
        if len(self.tx_queue) > 0:
            message = self.tx_queue.pop(0)
            await self.transmit_message(message)
    
    async def _handle_rx_cycle(self):
        """Handle RX cycle"""
        logger.debug("RX cycle started")
        
        # Clear audio buffer at start of RX
        # (Keep recent audio for decoding)
    
    async def transmit_message(self, message: str):
        """
        Transmit an FT8/FT4 message
        
        Args:
            message: Message text to transmit
        """
        try:
            logger.info(f"Transmitting: {message}")
            
            # Encode message to tones
            tones = self.protocol.encode_message(message)
            
            if tones is None:
                logger.error(f"Failed to encode message: {message}")
                return
            
            # Generate audio waveform
            audio = self.audio_processor.generate_tone_sequence(tones, base_freq=1200.0)
            
            # Send to radio (via callback)
            if self.on_tx_message:
                await self.on_tx_message(audio, message)
            
            self.stats['transmitted_count'] += 1
            
        except Exception as e:
            logger.error(f"Error transmitting message: {e}", exc_info=True)
    
    async def queue_tx_message(self, message: str):
        """Add message to TX queue"""
        if message not in self.tx_queue:
            self.tx_queue.append(message)
            logger.info(f"Queued for TX: {message}")
    
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
    
    def get_decoded_messages(self, limit: int = 50) -> List[Dict]:
        """Get recent decoded messages"""
        messages = self.decoded_messages[-limit:]
        return [msg.to_dict() for msg in messages]
    
    def get_active_qsos(self) -> List[Dict]:
        """Get active QSO sessions"""
        return [qso.to_dict() for qso in self.active_qsos.values()]
    
    def get_waterfall_data(self) -> List[List[int]]:
        """Get waterfall display data"""
        return self.audio_processor.generate_waterfall()
    
    def get_stats(self) -> Dict:
        """Get service statistics"""
        return {
            **self.stats,
            'mode': self.mode,
            'enabled': self.enabled,
            'tx_enabled': self.tx_enabled,
            'auto_sequence': self.auto_sequence,
            'active_qsos': len(self.active_qsos),
            'tx_queue_length': len(self.tx_queue),
            'is_tx_cycle': self.is_tx_cycle
        }
    
    def set_config(self, mycall: Optional[str] = None, mygrid: Optional[str] = None):
        """Update configuration"""
        if mycall:
            self.mycall = mycall.upper()
        if mygrid:
            self.mygrid = mygrid.upper()
        
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
                            audio_device: Optional[str] = None):
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
    
    _ft8_service = FT8Service(mode, mycall, mygrid, audio_device=device_to_use)
    return _ft8_service