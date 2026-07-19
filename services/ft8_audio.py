"""
FT8/FT4 Audio Processing
Handles audio capture, FFT analysis, and waterfall generation
"""

import numpy as np
from scipy import signal
from scipy.fft import fft, fftfreq
from typing import Optional, Tuple, List
from dataclasses import dataclass
import logging
from collections import deque

logger = logging.getLogger(__name__)

# Use numpy hamming window instead of scipy.signal.hamming (deprecated/removed)
hamming = np.hamming


@dataclass
class AudioConfig:
    """Audio configuration parameters"""
    sample_rate: int = 12000  # Hz
    fft_size: int = 2048
    waterfall_height: int = 100
    audio_buffer_seconds: int = 15  # FT8 cycle length


class FT8AudioProcessor:
    """Audio processor for FT8/FT4 signals"""
    
    # Audio frequency boundaries (Hz)
    FT8_FREQ_LOW = 200.0
    FT8_FREQ_HIGH = 2800.0
    FT4_FREQ_LOW = 200.0
    FT4_FREQ_HIGH = 2900.0
    
    # FT8/FT4 mode parameters
    FT8_SYMBOL_DURATION = 0.16  # seconds
    FT8_TONE_SPACING = 6.25     # Hz
    FT8_NUM_TONES = 8
    FT8_EXPECTED_SYMBOLS = 79
    
    FT4_SYMBOL_DURATION = 0.048  # seconds
    FT4_TONE_SPACING = 20.83      # Hz
    FT4_NUM_TONES = 4
    FT4_EXPECTED_SYMBOLS = 105
    
    # Butterworth filter order
    FILTER_ORDER = 4
    EXTRACTION_FILTER_ORDER = 6
    
    # FFT and processing parameters
    DEFAULT_FFT_SIZE = 2048
    WATERFALL_MAX_ROWS = 100
    SIGNAL_DETECTION_THRESHOLD_DB = -20.0
    NORMALIZED_MIN_MAGNITUDE = 1e-10
    DISPLAY_SCALE_FACTOR = 255
    
    # Spectrogram parameters
    SPECTROGRAM_NPERSEG = 512      # FFT window size for spectrogram
    SPECTROGRAM_NOVERLAP = 384     # Overlap between windows
    
    def __init__(self, mode: str = 'FT8', sample_rate: int = 12000):
        """
        Initialize audio processor
        
        Args:
            mode: 'FT8' or 'FT4'
            sample_rate: Audio sample rate in Hz
        """
        self.mode = mode
        self.sample_rate = sample_rate
        self.fft_size = self.DEFAULT_FFT_SIZE
        
        # Keep enough history to decode the previous slot even when the decode
        # loop wakes late in the current slot.
        buffer_seconds = 32 if mode == 'FT8' else 16
        self.buffer_size = sample_rate * buffer_seconds
        self.audio_buffer = deque(maxlen=self.buffer_size)
        
        # Waterfall data
        self.waterfall_data = []
        self.waterfall_max_rows = self.WATERFALL_MAX_ROWS
        
        # Bandpass filter
        self.design_bandpass_filter()
        
        logger.info(f"Initialized FT8AudioProcessor for {mode} at {sample_rate} Hz")
    
    def design_bandpass_filter(self):
        """Design bandpass filter for FT8/FT4"""
        if self.mode == 'FT8':
            lowcut = self.FT8_FREQ_LOW
            highcut = self.FT8_FREQ_HIGH
        else:  # FT4
            lowcut = self.FT4_FREQ_LOW
            highcut = self.FT4_FREQ_HIGH
        
        # Butterworth bandpass filter
        nyquist = self.sample_rate / 2
        low = lowcut / nyquist
        high = highcut / nyquist
        
        self.bp_b, self.bp_a = signal.butter(self.FILTER_ORDER, [low, high], btype='band')
        logger.debug(f"Designed bandpass filter: {lowcut}-{highcut} Hz")
    
    def add_audio_samples(self, samples: np.ndarray):
        """
        Add audio samples to the rolling buffer.
        
        Args:
            samples: Audio samples (mono, float32, -1.0 to 1.0)
        """
        self.audio_buffer.extend(samples)
    
    def process_audio_chunk(self, audio_chunk: np.ndarray) -> Optional[np.ndarray]:
        """
        Process audio chunk for waterfall display
        
        Args:
            audio_chunk: Audio samples
            
        Returns:
            FFT magnitude spectrum for waterfall
        """
        try:
            if len(audio_chunk) == 0:
                return None
            
            # Apply window function
            window = np.hamming(len(audio_chunk))
            windowed = audio_chunk * window
            
            # Compute FFT
            spectrum = fft(windowed, n=self.fft_size)
            
            # Get magnitude (dB)
            magnitude = np.abs(spectrum[:self.fft_size // 2])
            magnitude_db = 20 * np.log10(magnitude + self.NORMALIZED_MIN_MAGNITUDE)
            
            # Normalize for display
            magnitude_db = magnitude_db - np.min(magnitude_db)
            magnitude_db = magnitude_db / (np.max(magnitude_db) + self.NORMALIZED_MIN_MAGNITUDE) * self.DISPLAY_SCALE_FACTOR
            
            return magnitude_db.astype(np.uint8)
            
        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}")
            return None
    
    def generate_waterfall(self) -> List[List[int]]:
        """
        Generate waterfall display data
        
        Returns:
            2D array of waterfall data (time x frequency)
        """
        return self.waterfall_data[-self.waterfall_max_rows:]
    
    def update_waterfall(self, spectrum: np.ndarray):
        """Update waterfall with new spectrum data"""
        if spectrum is not None:
            self.waterfall_data.append(spectrum.tolist())
            
            # Keep only recent rows
            if len(self.waterfall_data) > self.waterfall_max_rows:
                self.waterfall_data.pop(0)
    
    def get_audio_buffer(self) -> np.ndarray:
        """Get current audio buffer as numpy array"""
        return np.array(self.audio_buffer, dtype=np.float32)
    
    def clear_buffer(self):
        """Clear audio buffer"""
        self.audio_buffer.clear()
        logger.debug("Audio buffer cleared")
    
    def apply_bandpass_filter(self, audio: np.ndarray) -> np.ndarray:
        """
        Apply bandpass filter to audio
        
        Args:
            audio: Input audio samples
            
        Returns:
            Filtered audio samples
        """
        try:
            filtered = signal.filtfilt(self.bp_b, self.bp_a, audio)
            return filtered
        except Exception as e:
            logger.error(f"Error applying bandpass filter: {e}")
            return audio
    
    def detect_signals(self, audio: np.ndarray, threshold_db: float = None) -> List[Tuple[float, float]]:
        """
        Detect FT8/FT4 signals in audio buffer
        
        Args:
            audio: Audio buffer
            threshold_db: Detection threshold in dB (uses default if None)
            
        Returns:
            List of (frequency, strength) tuples
        """
        if threshold_db is None:
            threshold_db = self.SIGNAL_DETECTION_THRESHOLD_DB
        
        signals = []
        
        try:
            # Apply bandpass filter
            filtered = self.apply_bandpass_filter(audio)
            
            # Compute spectrogram
            f, t, Sxx = signal.spectrogram(
                filtered,
                fs=self.sample_rate,
                window='hann',
                nperseg=self.SPECTROGRAM_NPERSEG,
                noverlap=self.SPECTROGRAM_NOVERLAP
            )
            
            # Convert to dB
            Sxx_db = 10 * np.log10(Sxx + self.NORMALIZED_MIN_MAGNITUDE)
            
            # Get frequency boundaries based on mode
            freq_low = self.FT8_FREQ_LOW if self.mode == 'FT8' else self.FT4_FREQ_LOW
            freq_high = self.FT8_FREQ_HIGH if self.mode == 'FT8' else self.FT4_FREQ_HIGH
            
            # Find peaks in frequency domain
            for freq_idx in range(len(f)):
                freq = f[freq_idx]
                
                # Skip out of band
                if freq < freq_low or freq > freq_high:
                    continue
                
                # Get time-averaged power at this frequency
                power = np.mean(Sxx_db[freq_idx, :])
                
                if power > threshold_db:
                    signals.append((freq, power))
            
            # Sort by strength
            signals.sort(key=lambda x: x[1], reverse=True)
            
            logger.debug(f"Detected {len(signals)} potential signals")
            return signals[:20]  # Return top 20
            
        except Exception as e:
            logger.error(f"Error detecting signals: {e}")
            return []
    
    def extract_signal(self, audio: np.ndarray, center_freq: float, bandwidth: float = 50.0) -> np.ndarray:
        """
        Extract a specific signal from audio buffer
        
        Args:
            audio: Audio buffer
            center_freq: Center frequency of signal (Hz)
            bandwidth: Bandwidth around center (Hz)
            
        Returns:
            Extracted signal audio
        """
        try:
            # Design narrow bandpass filter
            nyquist = self.sample_rate / 2
            low = (center_freq - bandwidth / 2) / nyquist
            high = (center_freq + bandwidth / 2) / nyquist
            
            # Ensure valid range
            low = max(0.01, min(0.99, low))
            high = max(0.01, min(0.99, high))
            
            if low >= high:
                return audio
            
            b, a = signal.butter(self.EXTRACTION_FILTER_ORDER, [low, high], btype='band')
            filtered = signal.filtfilt(b, a, audio)
            
            return filtered
            
        except Exception as e:
            logger.error(f"Error extracting signal at {center_freq} Hz: {e}")
            return audio
    
    def compute_snr(self, signal_audio: np.ndarray, noise_audio: np.ndarray) -> float:
        """
        Compute signal-to-noise ratio
        
        Args:
            signal_audio: Audio with signal
            noise_audio: Audio with noise only
            
        Returns:
            SNR in dB
        """
        try:
            signal_power = np.mean(signal_audio ** 2)
            noise_power = np.mean(noise_audio ** 2)
            
            if noise_power == 0:
                return 0.0
            
            snr = 10 * np.log10(signal_power / noise_power)
            return snr
            
        except Exception as e:
            logger.error(f"Error computing SNR: {e}")
            return 0.0
    
    def generate_tone_sequence(self, tones: np.ndarray, base_freq: float = 1000.0) -> np.ndarray:
        """
        Generate audio waveform from tone sequence
        
        Args:
            tones: Array of tone numbers (0-7 for FT8, 0-3 for FT4)
            base_freq: Base frequency in Hz
            
        Returns:
            Audio waveform samples
        """
        try:
            if self.mode == 'FT8':
                symbol_duration = self.FT8_SYMBOL_DURATION
                tone_spacing = self.FT8_TONE_SPACING
            else:  # FT4
                symbol_duration = self.FT4_SYMBOL_DURATION
                tone_spacing = self.FT4_TONE_SPACING
            
            # Calculate samples per symbol
            samples_per_symbol = int(self.sample_rate * symbol_duration)
            total_samples = samples_per_symbol * len(tones)
            
            # Generate waveform
            waveform = np.zeros(total_samples, dtype=np.float32)
            
            for i, tone in enumerate(tones):
                freq = base_freq + tone * tone_spacing
                t = np.arange(samples_per_symbol) / self.sample_rate
                
                # Generate sine wave with smooth transitions
                symbol_audio = np.sin(2 * np.pi * freq * t)
                
                # Apply Gaussian rise/fall to reduce clicks
                rise_samples = int(samples_per_symbol * 0.1)
                if rise_samples > 0:
                    rise = np.linspace(0, 1, rise_samples)
                    symbol_audio[:rise_samples] *= rise
                    symbol_audio[-rise_samples:] *= rise[::-1]
                
                # Add to waveform
                start_idx = i * samples_per_symbol
                end_idx = start_idx + samples_per_symbol
                waveform[start_idx:end_idx] = symbol_audio
            
            # Normalize
            if np.max(np.abs(waveform)) > 0:
                waveform = waveform / np.max(np.abs(waveform)) * 0.8
            
            logger.debug(f"Generated {len(tones)} tone sequence, {len(waveform)} samples")
            return waveform
            
        except Exception as e:
            logger.error(f"Error generating tone sequence: {e}")
            return np.zeros(1, dtype=np.float32)
    
    def decode_tone_sequence(self, audio: np.ndarray, base_freq: float = 1000.0) -> Optional[np.ndarray]:
        """
        Decode tone sequence from audio
        
        Args:
            audio: Audio waveform
            base_freq: Base frequency in Hz
            
        Returns:
            Array of detected tones or None
        """
        try:
            if self.mode == 'FT8':
                symbol_duration = self.FT8_SYMBOL_DURATION
                tone_spacing = self.FT8_TONE_SPACING
                num_tones = self.FT8_NUM_TONES
            else:  # FT4
                symbol_duration = self.FT4_SYMBOL_DURATION
                tone_spacing = self.FT4_TONE_SPACING
                num_tones = self.FT4_NUM_TONES
            
            samples_per_symbol = int(self.sample_rate * symbol_duration)
            num_symbols = len(audio) // samples_per_symbol
            
            tones = np.zeros(num_symbols, dtype=np.uint8)
            
            # Decode each symbol
            for i in range(num_symbols):
                start_idx = i * samples_per_symbol
                end_idx = start_idx + samples_per_symbol
                symbol_audio = audio[start_idx:end_idx]
                
                # Compute FFT for this symbol
                spectrum = fft(symbol_audio * np.hamming(len(symbol_audio)))
                freqs = fftfreq(len(symbol_audio), 1 / self.sample_rate)
                
                # Find strongest tone
                max_power = 0
                detected_tone = 0
                
                for tone_num in range(num_tones):
                    tone_freq = base_freq + tone_num * tone_spacing
                    
                    # Find closest frequency bin
                    freq_idx = np.argmin(np.abs(freqs - tone_freq))
                    power = np.abs(spectrum[freq_idx])
                    
                    if power > max_power:
                        max_power = power
                        detected_tone = tone_num
                
                tones[i] = detected_tone
            
            logger.debug(f"Decoded {len(tones)} tones from audio")
            return tones
            
        except Exception as e:
            logger.error(f"Error decoding tone sequence: {e}")
            return None
    
    def detect_ft8_signals_with_sync(self, audio: np.ndarray) -> List[Tuple[float, float, float]]:
        """
        Detect FT8 signals using Costas array synchronization
        
        Args:
            audio: Audio buffer to search
            
        Returns:
            List of (frequency, time_offset, sync_score) tuples
        """
        signals = []
        
        try:
            if self.mode != 'FT8':
                # Fall back to basic detection for FT4
                return [(f, s, 0.0) for f, s in self.detect_signals(audio)]
            
            # FT8 Costas sync array
            costas_pattern = np.array([3, 1, 4, 0, 6, 5, 2], dtype=np.uint8)
            
            # Search parameters
            freq_start = 200  # Hz
            freq_end = 2800  # Hz
            freq_step = 50  # Hz
            
            symbol_duration = 0.16  # seconds
            tone_spacing = 6.25  # Hz
            samples_per_symbol = int(self.sample_rate * symbol_duration)
            
            # Search over frequency range
            for center_freq in range(freq_start, freq_end, freq_step):
                # Try different time offsets
                max_offset_samples = int(self.sample_rate * 0.5)  # 0.5 seconds
                
                for time_offset in range(0, min(max_offset_samples, len(audio)), samples_per_symbol):
                    # Extract 7 symbols for Costas array
                    costas_audio = audio[time_offset:time_offset + 7 * samples_per_symbol]
                    
                    if len(costas_audio) < 7 * samples_per_symbol:
                        break
                    
                    # Decode 7 symbols
                    detected_tones = np.zeros(7, dtype=np.uint8)
                    
                    for i in range(7):
                        start_idx = i * samples_per_symbol
                        end_idx = start_idx + samples_per_symbol
                        symbol_audio = costas_audio[start_idx:end_idx]
                        
                        # FFT to find tone
                        spectrum = fft(symbol_audio * hamming(len(symbol_audio)))
                        freqs = fftfreq(len(symbol_audio), 1 / self.sample_rate)
                        
                        max_power = 0
                        detected_tone = 0
                        
                        for tone_num in range(8):
                            tone_freq = center_freq + tone_num * tone_spacing
                            freq_idx = np.argmin(np.abs(freqs - tone_freq))
                            power = np.abs(spectrum[freq_idx])
                            
                            if power > max_power:
                                max_power = power
                                detected_tone = tone_num
                        
                        detected_tones[i] = detected_tone
                    
                    # Compare with Costas pattern
                    matches = np.sum(detected_tones == costas_pattern)
                    sync_score = matches / 7.0
                    
                    # If good match, this is likely an FT8 signal
                    if sync_score > 0.6:  # At least 5/7 match
                        dt = time_offset / self.sample_rate
                        signals.append((center_freq, dt, sync_score))
                        logger.debug(f"FT8 signal detected at {center_freq} Hz, dt={dt:.2f}s, sync={sync_score:.2f}")
            
            # Sort by sync score
            signals.sort(key=lambda x: x[2], reverse=True)
            
            return signals[:10]  # Top 10 signals
            
        except Exception as e:
            logger.error(f"Error in Costas sync detection: {e}", exc_info=True)
            return []
