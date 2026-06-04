"""
Audio Capture Service for FT8/FT4
Captures audio from FlexRadio DAX or system audio device
"""

import asyncio
import numpy as np
import logging
import threading
from typing import Optional, Callable
from dataclasses import dataclass
from services.sounddevice_loader import get_sounddevice, sounddevice_unavailable_reason
from services.soundcard_loader import get_soundcard, soundcard_unavailable_reason

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
        self._capture_thread: Optional[threading.Thread] = None
        self.callback: Optional[Callable] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.backend = "stopped"
        self.actual_device_name: Optional[str] = None
        self.actual_sample_rate: Optional[int] = None
        self.samples_received = 0
        self.chunks_received = 0
        self.last_sample_rms = 0.0
        self.last_sample_peak = 0.0
        
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
            if get_soundcard() is not None:
                logger.warning("%s - using soundcard fallback", sounddevice_unavailable_reason())
                return self._start_soundcard_capture()
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
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)
        
        self.stream = None
        self._capture_thread = None
        self.backend = "stopped"
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
            self.backend = "sounddevice"
            
            # Log actual device being used
            actual_device = self.stream.device
            device_name = sd.query_devices(actual_device)['name'] if actual_device is not None else "default"
            self.actual_device_name = str(device_name)
            self.actual_sample_rate = int(self.config.sample_rate)
            logger.info(f"✅ Real audio capture started: [{actual_device}] {device_name} @ {self.config.sample_rate} Hz")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start real audio capture: {e}", exc_info=True)
            return False

    def _start_soundcard_capture(self) -> bool:
        """Start real audio capture using the soundcard fallback backend."""
        sc = get_soundcard()
        if sc is None:
            logger.warning("%s - using simulated audio", soundcard_unavailable_reason())
            return self._start_simulated_capture()

        try:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None

            microphone = self._resolve_soundcard_microphone()
            if microphone is None:
                logger.warning("No soundcard input device found - using simulated audio")
                return self._start_simulated_capture()

            self.enabled = True
            self.backend = "soundcard"
            self.actual_device_name = str(getattr(microphone, "name", "default"))
            self.actual_sample_rate = int(self.config.sample_rate)

            def capture_loop() -> None:
                logger.info(
                    "✅ Soundcard audio capture started: %s @ %s Hz",
                    getattr(microphone, "name", "default"),
                    self.config.sample_rate,
                )
                try:
                    with microphone.recorder(
                        samplerate=self.config.sample_rate,
                        channels=self.config.channels,
                        blocksize=self.config.blocksize,
                    ) as recorder:
                        while self.enabled:
                            data = recorder.record(numframes=self.config.blocksize)
                            audio_data = np.asarray(data, dtype=np.float32)
                            if audio_data.ndim > 1:
                                audio_data = audio_data[:, 0]
                            self._handle_audio_samples(audio_data.reshape(-1))
                except Exception as exc:
                    if self.enabled:
                        logger.error("Soundcard audio capture failed: %s", exc, exc_info=True)
                        self.enabled = False

            self._capture_thread = threading.Thread(
                target=capture_loop,
                name="ft8-soundcard-capture",
                daemon=True,
            )
            self._capture_thread.start()
            return True
        except Exception as exc:
            logger.error("❌ Failed to start soundcard audio capture: %s", exc, exc_info=True)
            self.enabled = False
            return False

    def _resolve_soundcard_microphone(self):
        sc = get_soundcard()
        if sc is None:
            return None

        try:
            microphones = sc.all_microphones(include_loopback=True)
        except Exception as exc:
            logger.warning("Unable to enumerate soundcard microphones: %s", exc)
            return None

        device_str = str(self.config.device_name or "").strip()
        lowered = device_str.lower()

        def eligible(device) -> bool:
            name_l = str(getattr(device, "name", "")).lower()
            return "reserved" not in name_l

        if not device_str or lowered == "default" or lowered.startswith("default:"):
            try:
                return sc.default_microphone()
            except Exception:
                return microphones[0] if microphones else None

        if lowered in {"flexradio", "dax", "dax_rx", "dax_rx_1", "flexradio_dax_rx"}:
            preferred = [
                device for device in microphones
                if eligible(device)
                and ("dax rx 1" in str(device.name).lower() or "dax audio rx 1" in str(device.name).lower())
            ]
            fallback = [
                device for device in microphones
                if eligible(device)
                and ("dax rx" in str(device.name).lower() or "dax audio rx" in str(device.name).lower())
            ]
            if preferred:
                logger.info("Resolved soundcard FlexRadio DAX RX input to %s", preferred[0].name)
                return preferred[0]
            if fallback:
                logger.info("Resolved soundcard FlexRadio DAX RX fallback input to %s", fallback[0].name)
                return fallback[0]

        search_name = device_str.split(":", 1)[1].strip() if ":" in device_str else device_str
        search_l = search_name.lower()
        for device in microphones:
            if search_l in str(getattr(device, "name", "")).lower():
                logger.info("Found soundcard audio input device: %s", device.name)
                return device

        logger.warning("Soundcard input device '%s' not found; using default input", device_str)
        try:
            return sc.default_microphone()
        except Exception:
            return microphones[0] if microphones else None

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
        sample_array = np.asarray(samples, dtype=np.float32).reshape(-1)
        self.samples_received += int(sample_array.size)
        self.chunks_received += 1
        if sample_array.size:
            self.last_sample_rms = float(np.sqrt(np.mean(np.square(sample_array))))
            self.last_sample_peak = float(np.max(np.abs(sample_array)))
        if self.callback:
            try:
                self.callback(sample_array)
            except Exception as e:
                logger.error(f"Error in audio callback: {e}")
            return

        try:
            self.audio_queue.put_nowait(sample_array)
        except asyncio.QueueFull:
            pass

    def get_stats(self) -> dict:
        """Return lightweight diagnostics for the active capture path."""
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "configured_device": self.config.device_name,
            "actual_device": self.actual_device_name,
            "sample_rate": self.actual_sample_rate or self.config.sample_rate,
            "chunks_received": self.chunks_received,
            "samples_received": self.samples_received,
            "queue_size": self.audio_queue.qsize(),
            "last_rms": round(self.last_sample_rms, 7),
            "last_peak": round(self.last_sample_peak, 7),
        }
    
    def _start_simulated_capture(self) -> bool:
        """Start simulated audio capture for testing"""
        self.enabled = True
        self.backend = "simulated"
        self.actual_device_name = "simulated"
        self.actual_sample_rate = int(self.config.sample_rate)
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
            self._handle_audio_samples(samples)
            
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
            sc = get_soundcard()
            if sc is None:
                return []
            try:
                devices = []
                for i, device in enumerate(sc.all_microphones(include_loopback=True)):
                    devices.append({
                        "index": i,
                        "name": getattr(device, "name", f"soundcard input {i}"),
                        "channels": 1,
                        "sample_rate": 48000,
                        "backend": "soundcard",
                    })
                return devices
            except Exception as e:
                logger.error(f"Error listing soundcard input devices: {e}")
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
