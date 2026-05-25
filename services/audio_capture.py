"""
Audio Capture Service for FT8/FT4
Captures audio from FlexRadio DAX or system audio device
"""

import asyncio
import numpy as np
import logging
from typing import Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import sounddevice for real audio capture
try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
    logger.info("sounddevice library available for audio capture")
except ImportError:
    AUDIO_AVAILABLE = False
    logger.warning("sounddevice not available - using simulated audio")


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
            if AUDIO_AVAILABLE:
                return self._start_real_capture()
            else:
                return self._start_simulated_capture()
        except Exception as e:
            logger.error(f"Failed to start audio capture: {e}", exc_info=True)
            return False
    
    def stop_capture(self):
        """Stop audio capture"""
        if not self.enabled:
            return
        
        self.enabled = False
        
        if self.stream is not None and AUDIO_AVAILABLE:
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
            # Find device
            device_index = self.config.device_index
            
            # Try to parse device_name as index if it's a number string or "index: name" format
            if self.config.device_name and device_index is None:
                device_str = str(self.config.device_name).strip()
                
                # Handle "default" keyword
                if device_str.lower() == 'default' or device_str.startswith('default:'):
                    device_index = None
                    logger.info(f"Using default audio device")
                else:
                    try:
                        # Try to extract index from "123: Device Name" format
                        if ':' in device_str:
                            device_index = int(device_str.split(':')[0].strip())
                            logger.info(f"Extracted device index {device_index} from '{device_str}'")
                        else:
                            # Try to parse as plain integer
                            device_index = int(device_str)
                        
                        logger.info(f"Using audio device index: {device_index}")
                    except ValueError:
                        # Search for device by name
                        search_name = device_str.split(':', 1)[1].strip() if ':' in device_str else device_str
                        devices = sd.query_devices()
                        for i, device in enumerate(devices):
                            if search_name.lower() in device['name'].lower():
                                device_index = i
                                logger.info(f"Found audio device: {device['name']} (index {i})")
                                break
                        
                        if device_index is None:
                            logger.warning(f"Device '{device_str}' not found, using default")
                            device_index = None
            
            # Audio callback
            def audio_callback(indata, frames, time_info, status):
                if status:
                    logger.warning(f"Audio callback status: {status}")
                
                # Convert to mono if needed
                audio_data = np.array(indata[:, 0]) if indata.shape[1] > 1 else np.array(indata[:, 0])
                
                # Queue for async processing
                try:
                    self.audio_queue.put_nowait(audio_data)
                except asyncio.QueueFull:
                    pass  # Drop samples if queue is full
                
                # Call callback if set
                if self.callback:
                    try:
                        self.callback(audio_data)
                    except Exception as e:
                        logger.error(f"Error in audio callback: {e}")
            
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
        if not AUDIO_AVAILABLE:
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