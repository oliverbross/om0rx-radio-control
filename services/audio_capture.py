"""
Audio Capture Service for FT8/FT4
Captures audio from FlexRadio DAX or system audio device
"""

import asyncio
import numpy as np
import logging
from typing import Optional, Callable
from dataclasses import dataclass
from services.sounddevice_loader import get_sounddevice, sounddevice_unavailable_reason

logger = logging.getLogger(__name__)

AUDIO_AVAILABLE = False


@dataclass
class AudioCaptureConfig:
    """Audio capture configuration"""
    device_name: Optional[str] = None
    device_index: Optional[int] = None
    sample_rate: int = 12000
    channels: int = 1
    blocksize: int = 1024


class AudioCaptureService:
    """
    Audio capture service
    Captures audio from FlexRadio DAX or system audio devices
    """
    
    def __init__(self, config: AudioCaptureConfig):
        """
        Initialize audio capture service
        
        Args:
            config: Audio capture configuration
        """
        self.config = config
        self.enabled = False
        self.stream = None
        self.callback: Optional[Callable] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Audio buffer for async processing
        self.audio_queue = asyncio.Queue(maxsize=100)
        
        logger.info(f"AudioCaptureService initialized: {config.sample_rate} Hz")
    
    def set_audio_callback(self, callback: Callable):
        """
        Set callback function for audio samples
        
        Args:
            callback: Function called with audio samples (np.ndarray)
        """
        self.callback = callback
    
    def start_capture(self) -> bool:
        """
        Start audio capture
        
        Returns:
            True if started successfully
        """
        if self.enabled:
            logger.warning("Audio capture already running")
            return True
        
        try:
            if get_sounddevice() is not None:
                return self._start_real_capture()
            else:
                logger.warning("%s - using simulated audio", sounddevice_unavailable_reason())
                return self._start_simulated_capture()
        except Exception as e:
            logger.error(f"Failed to start audio capture: {e}", exc_info=True)
            return False
    
    def stop_capture(self):
        """Stop audio capture"""
        if not self.enabled:
            return
        
        self.enabled = False
        
        sd = get_sounddevice()
        if self.stream is not None and sd is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error stopping audio stream: {e}")
        
        self.stream = None
        logger.info("Audio capture stopped")
    
    def _start_real_capture(self) -> bool:
        """Start real audio capture using sounddevice"""
        try:
            sd = get_sounddevice()
            if sd is None:
                logger.warning("%s - using simulated audio", sounddevice_unavailable_reason())
                return self._start_simulated_capture()

            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None

            # Find device
            device_index = self._resolve_device_index()
            if device_index is not None:
                self.config.device_index = device_index
            
            # Audio callback
            def audio_callback(indata, frames, time_info, status):
                if status:
                    logger.warning(f"Audio callback status: {status}")
                
                # Convert to mono if needed
                audio_data = np.array(indata[:, 0]) if indata.shape[1] > 1 else np.array(indata[:, 0])

                if self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._handle_audio_samples, audio_data)
                else:
                    self._handle_audio_samples(audio_data)
            
            # Validate device index
            if device_index is not None:
                try:
                    device_info = sd.query_devices(device_index)
                    logger.info(f"Opening audio device: [{device_index}] {device_info['name']}")
                except Exception as e:
                    logger.error(f"Invalid device index {device_index}: {e}")
                    logger.warning("Falling back to default device")
                    device_index = None
            
            # Open stream
            self.stream = sd.InputStream(
                device=device_index,
                channels=self.config.channels,
                samplerate=self.config.sample_rate,
                blocksize=self.config.blocksize,
                callback=audio_callback
            )
            
            self.stream.start()
            self.enabled = True
            
            # Log actual device being used
            actual_device = self.stream.device
            device_name = sd.query_devices(actual_device)['name'] if actual_device is not None else "default"
            logger.info(f"✅ Real audio capture started: [{actual_device}] {device_name} @ {self.config.sample_rate} Hz")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start real audio capture: {e}", exc_info=True)
            return False

    def _resolve_device_index(self) -> Optional[int]:
        """Resolve configured input device to a PortAudio device index."""
        device_index = self.config.device_index
        if device_index is not None or not self.config.device_name:
            return device_index

        device_str = str(self.config.device_name).strip()
        if device_str.lower() == "default" or device_str.lower().startswith("default:"):
            logger.info("Using default audio input device")
            return None

        try:
            if ":" in device_str:
                return int(device_str.split(":", 1)[0].strip())
            return int(device_str)
        except ValueError:
            pass

        sd = get_sounddevice()
        if sd is None:
            return None

        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        lowered = device_str.lower()

        if lowered in {"flexradio", "dax", "dax_rx", "dax_rx_1", "flexradio_dax_rx"}:
            preferred = []
            fallback = []
            for i, device in enumerate(devices):
                name = str(device["name"])
                name_l = name.lower()
                if device["max_input_channels"] <= 0:
                    continue
                if "dax audio rx 1" in name_l and "reserved" not in name_l:
                    host = hostapis[device["hostapi"]]["name"].lower()
                    score = 0
                    if "wasapi" in host:
                        score = 0
                    elif "wdm-ks" in host:
                        score = 1
                    elif "directsound" in host:
                        score = 2
                    else:
                        score = 3
                    preferred.append((score, i, name, host))
                elif "dax audio rx" in name_l and "reserved" not in name_l:
                    fallback.append((i, name))

            if preferred:
                _, index, name, host = sorted(preferred)[0]
                logger.info("Resolved FlexRadio DAX RX input to [%s] %s (%s)", index, name, host)
                return index
            if fallback:
                index, name = fallback[0]
                logger.info("Resolved FlexRadio DAX RX fallback input to [%s] %s", index, name)
                return index

        search_name = device_str.split(":", 1)[1].strip() if ":" in device_str else device_str
        search_l = search_name.lower()
        for i, device in enumerate(devices):
            if device["max_input_channels"] > 0 and search_l in str(device["name"]).lower():
                logger.info("Found audio input device: [%s] %s", i, device["name"])
                return i

        logger.warning("Audio input device '%s' not found; using default input", device_str)
        return None

    def _handle_audio_samples(self, samples: np.ndarray) -> None:
        """Queue and publish audio samples on the owning event loop."""
        try:
            self.audio_queue.put_nowait(samples)
        except asyncio.QueueFull:
            pass

        if self.callback:
            try:
                self.callback(samples)
            except Exception as e:
                logger.error(f"Error in audio callback: {e}")
    
    def _start_simulated_capture(self) -> bool:
        """Start simulated audio capture for testing"""
        self.enabled = True
        logger.info("Simulated audio capture started (no real audio)")
        
        # In real implementation, this would generate test tones
        # For now, we just generate silence
        asyncio.create_task(self._simulated_audio_loop())
        
        return True
    
    async def _simulated_audio_loop(self):
        """Generate simulated audio samples"""
        while self.enabled:
            # Generate silence or test signal
            samples = np.random.normal(0, 0.01, self.config.blocksize).astype(np.float32)
            
            # Queue samples
            try:
                await self.audio_queue.put(samples)
            except asyncio.QueueFull:
                pass
            
            # Call callback
            if self.callback:
                try:
                    self.callback(samples)
                except Exception as e:
                    logger.error(f"Error in simulated audio callback: {e}")
            
            # Sleep to simulate real-time rate
            await asyncio.sleep(self.config.blocksize / self.config.sample_rate)
    
    async def get_audio_samples(self) -> Optional[np.ndarray]:
        """
        Get audio samples from queue (async)
        
        Returns:
            Audio samples or None if queue is empty
        """
        try:
            return await asyncio.wait_for(self.audio_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return None
    
    @staticmethod
    def list_audio_devices() -> list:
        """
        List available audio devices
        
        Returns:
            List of device info dicts
        """
        sd = get_sounddevice()
        if sd is None:
            return []
        
        try:
            devices = sd.query_devices()
            device_list = []
            
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:  # Input device
                    device_list.append({
                        'index': i,
                        'name': device['name'],
                        'channels': device['max_input_channels'],
                        'sample_rate': int(device['default_samplerate'])
                    })
            
            return device_list
            
        except Exception as e:
            logger.error(f"Error listing audio devices: {e}")
            return []


# Singleton instance
_audio_capture_instance: Optional[AudioCaptureService] = None


def get_audio_capture_service(config: Optional[AudioCaptureConfig] = None) -> AudioCaptureService:
    """
    Get or create audio capture service singleton
    
    Args:
        config: Audio configuration (only used on first call)
        
    Returns:
        AudioCaptureService instance
    """
    global _audio_capture_instance
    
    if _audio_capture_instance is None:
        if config is None:
            config = AudioCaptureConfig()
        _audio_capture_instance = AudioCaptureService(config)
    
    return _audio_capture_instance
