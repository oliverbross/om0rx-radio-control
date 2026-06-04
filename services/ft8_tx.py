"""FT8/FT4 transmit engine.

This module owns the RF-adjacent parts of the built-in digital client:
message validation/encoding, audio playback, CAT PTT, tune tone, and NTP
offset diagnostics. It intentionally stays separate from RX decode code so
TX safety rules are easy to inspect.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import math
import os
import socket
import subprocess
import tempfile
import threading
import time
import wave
from typing import Any, Optional

import numpy as np
from scipy import signal
from services.sounddevice_loader import get_sounddevice, sounddevice_unavailable_reason
from services.soundcard_loader import get_soundcard, soundcard_unavailable_reason

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FT8_LIB_DIR = PROJECT_ROOT / "vendor" / "ft8_lib"
GEN_FT8_PATH = FT8_LIB_DIR / "gen_ft8.exe"
FT8_TX_SAMPLE_RATE = 12000
SUPPORTED_PTT_METHODS = ("CAT", "VOX")


@dataclass(frozen=True)
class FT8TxStatus:
    available: bool
    encoder: str
    audio_output: bool
    ptt_methods: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "encoder": self.encoder,
            "audio_output": self.audio_output,
            "ptt_methods": list(self.ptt_methods),
            "reason": self.reason,
        }


@dataclass
class FT8TransmitResult:
    message: str
    mode: str
    audio_frequency: int
    duration_seconds: float
    sample_rate: int
    ptt_method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "mode": self.mode,
            "audio_frequency": self.audio_frequency,
            "duration_seconds": self.duration_seconds,
            "sample_rate": self.sample_rate,
            "ptt_method": self.ptt_method,
        }


class FT8TxEngine:
    """Generate and play timed FT8/FT4 audio with optional CAT PTT."""

    def __init__(
        self,
        *,
        audio_output: Optional[str] = None,
        output_sample_rate: int = 12000,
        ptt_method: str = "CAT",
        level: float = 0.70,
    ) -> None:
        self.audio_output = audio_output
        self.output_sample_rate = int(output_sample_rate or 12000)
        self.ptt_method = str(ptt_method or "CAT").upper()
        self.level = max(0.05, min(float(level or 0.70), 1.0))
        self._abort_event = threading.Event()
        self._state_lock = threading.RLock()
        self._active_flex: Any = None
        self._ptt_on = False
        self.last_audio_output_device: Optional[str] = None
        self.last_audio_peak: float = 0.0
        self.last_audio_rms: float = 0.0

    @property
    def status(self) -> FT8TxStatus:
        if not GEN_FT8_PATH.exists():
            return FT8TxStatus(
                available=False,
                encoder="vendor.ft8_lib.gen_ft8",
                audio_output=self._audio_output_available(),
                ptt_methods=SUPPORTED_PTT_METHODS,
                reason=f"FT8/FT4 generator is not built: {GEN_FT8_PATH}",
            )
        if self.ptt_method not in SUPPORTED_PTT_METHODS:
            return FT8TxStatus(
                available=False,
                encoder="vendor.ft8_lib.gen_ft8",
                audio_output=self._audio_output_available(),
                ptt_methods=SUPPORTED_PTT_METHODS,
                reason=f"Unsupported built-in digital PTT method: {self.ptt_method}",
            )
        if not self._audio_output_available():
            return FT8TxStatus(
                available=False,
                encoder="vendor.ft8_lib.gen_ft8",
                audio_output=False,
                ptt_methods=SUPPORTED_PTT_METHODS,
                reason=(
                    f"{sounddevice_unavailable_reason()}; {soundcard_unavailable_reason()}, "
                    "so DAX TX audio cannot be opened"
                ),
            )
        return FT8TxStatus(
            available=True,
            encoder="vendor.ft8_lib.gen_ft8",
            audio_output=True,
            ptt_methods=SUPPORTED_PTT_METHODS,
            reason="FT8/FT4 encoder and audio output are available",
        )

    @staticmethod
    def _audio_output_available() -> bool:
        return get_sounddevice() is not None or get_soundcard() is not None

    def transmit(
        self,
        message: str,
        *,
        mode: str,
        audio_frequency: int,
        flex: Any = None,
        max_duration_seconds: Optional[float] = None,
        playback_delay_seconds: Optional[float] = None,
    ) -> FT8TransmitResult:
        status = self.status
        if not status.available:
            raise RuntimeError(status.reason)

        self._abort_event.clear()
        text = self._normalise_message(message)
        mode_upper = self._normalise_mode(mode)
        tx_freq = self._normalise_audio_frequency(audio_frequency)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            wav_path = Path(temp_file.name)

        try:
            self._generate_wav(text, wav_path, mode_upper, tx_freq)
            samples, sample_rate = self._read_wav(wav_path)
            samples = self._prepare_output_samples(samples, sample_rate)
            samples = self._trim_trailing_silence(samples)
            if max_duration_seconds is not None:
                max_samples = int(max(0.25, float(max_duration_seconds)) * self.output_sample_rate)
                if 0 < max_samples < len(samples):
                    samples = samples[:max_samples]
                    ramp = min(int(self.output_sample_rate * 0.02), len(samples) // 4)
                    if ramp:
                        envelope = np.linspace(1.0, 0.0, ramp, dtype=np.float32)
                        samples[-ramp:] *= envelope
            duration = len(samples) / float(self.output_sample_rate)
            self._with_ptt(
                lambda: self._play_samples(samples),
                flex,
                ptt_limit_seconds=duration + 1.25,
                playback_delay_seconds=playback_delay_seconds,
            )
            return FT8TransmitResult(
                message=text,
                mode=mode_upper,
                audio_frequency=tx_freq,
                duration_seconds=duration,
                sample_rate=self.output_sample_rate,
                ptt_method=self.ptt_method,
            )
        finally:
            wav_path.unlink(missing_ok=True)

    def tune_tone(
        self,
        *,
        audio_frequency: int,
        duration_seconds: float = 5.0,
        flex: Any = None,
    ) -> FT8TransmitResult:
        status = self.status
        if not status.available:
            raise RuntimeError(status.reason)

        self._abort_event.clear()
        tx_freq = self._normalise_audio_frequency(audio_frequency)
        duration = max(0.5, min(float(duration_seconds or 5.0), 15.0))
        sample_count = int(self.output_sample_rate * duration)
        t = np.arange(sample_count, dtype=np.float32) / float(self.output_sample_rate)
        samples = np.sin(2.0 * math.pi * tx_freq * t).astype(np.float32) * self.level
        ramp = min(int(self.output_sample_rate * 0.02), len(samples) // 4)
        if ramp:
            envelope = np.linspace(0.0, 1.0, ramp, dtype=np.float32)
            samples[:ramp] *= envelope
            samples[-ramp:] *= envelope[::-1]
        self.last_audio_peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
        self.last_audio_rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0

        self._with_ptt(lambda: self._play_samples(samples), flex, ptt_limit_seconds=duration + 1.25)
        return FT8TransmitResult(
            message="TUNE",
            mode="TUNE",
            audio_frequency=tx_freq,
            duration_seconds=duration,
            sample_rate=self.output_sample_rate,
            ptt_method=self.ptt_method,
        )

    def abort(self) -> None:
        """Stop any active digital audio playback and release CAT PTT."""
        self._abort_event.set()
        sd = get_sounddevice()
        if sd is not None:
            try:
                sd.stop()
            except Exception as exc:
                logger.debug("Unable to stop digital TX audio stream: %s", exc, exc_info=True)

        with self._state_lock:
            flex = self._active_flex
            ptt_on = self._ptt_on
            self._ptt_on = False
        if flex is not None and ptt_on:
            try:
                flex.set_mox(False)
            except Exception as exc:
                logger.error("Failed to force CAT PTT off during digital TX abort: %s", exc, exc_info=True)

    @property
    def ptt_on(self) -> bool:
        with self._state_lock:
            return bool(self._ptt_on)

    @staticmethod
    def _normalise_message(message: str) -> str:
        text = " ".join(str(message or "").upper().split())
        if not text:
            raise ValueError("Transmit message is required")
        if len(text) > 37:
            raise ValueError("Transmit message is too long for FT8/FT4")
        return text

    @staticmethod
    def _normalise_mode(mode: str) -> str:
        mode_upper = str(mode or "FT8").upper()
        if mode_upper not in {"FT8", "FT4"}:
            raise ValueError("Built-in TX currently supports FT8 and FT4 only")
        return mode_upper

    @staticmethod
    def _normalise_audio_frequency(audio_frequency: int) -> int:
        value = int(audio_frequency or 1500)
        if not 200 <= value <= 5000:
            raise ValueError("Audio TX frequency must be between 200 and 5000 Hz")
        return value

    def _generate_wav(self, message: str, wav_path: Path, mode: str, audio_frequency: int) -> None:
        command = [str(GEN_FT8_PATH), message, str(wav_path), str(audio_frequency)]
        if mode == "FT4":
            command.append("-ft4")

        env = os.environ.copy()
        for dll_dir in (Path(r"C:\msys64\ucrt64\bin"), Path(r"C:\msys64\mingw64\bin")):
            if dll_dir.exists() and str(dll_dir) not in env.get("PATH", ""):
                env["PATH"] = f"{dll_dir};{env.get('PATH', '')}"

        result = subprocess.run(
            command,
            cwd=str(FT8_LIB_DIR),
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown encoder error").strip()
            raise RuntimeError(f"FT8/FT4 encode failed: {detail}")
        if not wav_path.exists() or wav_path.stat().st_size < 1024:
            raise RuntimeError("FT8/FT4 encode failed: empty WAV output")

    @staticmethod
    def _read_wav(wav_path: Path) -> tuple[np.ndarray, int]:
        with wave.open(str(wav_path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            frames = wav_file.readframes(wav_file.getnframes())
        pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            pcm = pcm.reshape(-1, channels).mean(axis=1)
        return pcm, sample_rate

    def _prepare_output_samples(self, samples: np.ndarray, input_sample_rate: int) -> np.ndarray:
        output = np.asarray(samples, dtype=np.float32)
        if int(input_sample_rate) != self.output_sample_rate:
            divisor = math.gcd(int(input_sample_rate), self.output_sample_rate)
            output = signal.resample_poly(
                output,
                self.output_sample_rate // divisor,
                int(input_sample_rate) // divisor,
            ).astype(np.float32)
        peak = float(np.max(np.abs(output))) if len(output) else 0.0
        if peak > 0:
            output = output / peak * self.level
        output = np.clip(output, -1.0, 1.0).astype(np.float32)
        self.last_audio_peak = float(np.max(np.abs(output))) if len(output) else 0.0
        self.last_audio_rms = float(np.sqrt(np.mean(np.square(output)))) if len(output) else 0.0
        return output

    def _trim_trailing_silence(self, samples: np.ndarray) -> np.ndarray:
        """Keep protocol leading silence but do not hold PTT through the tail."""
        output = np.asarray(samples, dtype=np.float32)
        if output.size == 0:
            return output
        active = np.flatnonzero(np.abs(output) > 1e-4)
        if active.size == 0:
            return output
        tail_guard = int(self.output_sample_rate * 0.08)
        end = min(output.size, int(active[-1]) + tail_guard)
        return output[:end]

    def _play_samples(self, samples: np.ndarray) -> None:
        sd = get_sounddevice()
        if sd is None:
            self._play_samples_soundcard(samples)
            return
        candidates = self._resolve_output_device_indexes()
        last_error: Optional[Exception] = None
        for device_index in candidates:
            try:
                self.last_audio_output_device = str(device_index if device_index is not None else "default")
                logger.info(
                    "Playing digital TX audio: device=%s sample_rate=%s samples=%s",
                    device_index if device_index is not None else "default",
                    self.output_sample_rate,
                    len(samples),
                )
                sd.play(samples, samplerate=self.output_sample_rate, device=device_index, blocking=False)
                deadline = time.monotonic() + (len(samples) / float(self.output_sample_rate))
                while time.monotonic() < deadline:
                    if self._abort_event.is_set():
                        raise RuntimeError("Digital TX aborted")
                    time.sleep(0.02)
                sd.wait()
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Digital TX audio failed on device %s: %s",
                    device_index if device_index is not None else "default",
                    exc,
                )
                try:
                    sd.stop()
                except Exception:
                    pass
        if last_error:
            raise RuntimeError(f"Digital TX audio failed on all candidate output devices: {last_error}")
        raise RuntimeError("No digital TX audio output device is available")

    def _play_samples_soundcard(self, samples: np.ndarray) -> None:
        sc = get_soundcard()
        if sc is None:
            raise RuntimeError(f"{sounddevice_unavailable_reason()}; {soundcard_unavailable_reason()}")

        speakers = self._resolve_soundcard_speakers()
        if not speakers:
            raise RuntimeError("No soundcard audio output device is available")

        last_error: Optional[Exception] = None
        data = np.asarray(samples, dtype=np.float32).reshape(-1, 1)
        blocksize = max(512, min(4096, int(self.output_sample_rate * 0.1)))
        for speaker in speakers:
            try:
                self.last_audio_output_device = str(getattr(speaker, "name", "default"))
                logger.info(
                    "Playing digital TX audio via soundcard: device=%s sample_rate=%s samples=%s",
                    getattr(speaker, "name", "default"),
                    self.output_sample_rate,
                    len(samples),
                )
                with speaker.player(
                    samplerate=self.output_sample_rate,
                    channels=1,
                    blocksize=blocksize,
                ) as player:
                    for start in range(0, len(data), blocksize):
                        if self._abort_event.is_set():
                            raise RuntimeError("Digital TX aborted")
                        player.play(data[start:start + blocksize])
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Soundcard digital TX audio failed on device %s: %s",
                    getattr(speaker, "name", "default"),
                    exc,
                )
        if last_error:
            raise RuntimeError(f"Soundcard digital TX audio failed on all candidate devices: {last_error}")
        raise RuntimeError("No soundcard digital TX audio output device is available")

    def _wait_for_cat_mox(self, flex: Any, expected: bool, timeout: float = 1.2) -> bool:
        off_states = {"READY", "RECEIVE", "NOT_READY", "TIMEOUT", "TX_FAULT"}
        deadline = time.monotonic() + max(0.1, float(timeout))
        while time.monotonic() < deadline:
            interlock_state = str(getattr(flex, "current_interlock_state", "") or "").upper()
            if expected and interlock_state == "TRANSMITTING":
                return True
            if not expected and interlock_state in off_states:
                return True
            current = getattr(flex, "current_mox", None)
            if current is not None and bool(current) is expected:
                return True
            refresh = getattr(flex, "refresh_radio_state", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception as exc:
                    logger.debug("Digital CAT PTT MOX refresh failed: %s", exc, exc_info=True)
            current = getattr(flex, "current_mox", None)
            if current is not None and bool(current) is expected:
                return True
            interlock_state = str(getattr(flex, "current_interlock_state", "") or "").upper()
            if expected and interlock_state == "TRANSMITTING":
                return True
            if not expected and interlock_state in off_states:
                return True
            time.sleep(0.05)
        return False

    def _set_cat_ptt(
        self,
        flex: Any,
        enabled: bool,
        require_confirmation: bool = True,
        confirmation_timeout: float = 1.2,
    ) -> None:
        state = "ON" if enabled else "OFF"
        logger.info("Digital CAT PTT %s request", state)
        if not flex.set_mox(enabled):
            raise RuntimeError(f"CAT PTT {state} command failed")
        if require_confirmation and not self._wait_for_cat_mox(flex, enabled, timeout=confirmation_timeout):
            if enabled:
                try:
                    flex.set_mox(False)
                except Exception as exc:
                    logger.error("Failed to release CAT PTT after missing ON confirmation: %s", exc, exc_info=True)
            raise RuntimeError(f"CAT PTT {state} was not confirmed by radio MOX state")
        logger.info("Digital CAT PTT %s confirmed", state)

    def _sleep_until(self, deadline: float) -> None:
        while True:
            if self._abort_event.is_set():
                raise RuntimeError("Digital TX aborted")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.02, remaining))

    def _with_ptt(
        self,
        playback,
        flex: Any,
        ptt_limit_seconds: Optional[float] = None,
        playback_delay_seconds: Optional[float] = None,
    ) -> None:
        if self.ptt_method not in SUPPORTED_PTT_METHODS:
            raise RuntimeError(f"Unsupported built-in digital PTT method: {self.ptt_method}")
        use_cat = self.ptt_method == "CAT"
        ptt_on = False
        ptt_timer: Optional[threading.Timer] = None
        playback_deadline = None
        if playback_delay_seconds is not None:
            playback_deadline = time.monotonic() + max(0.0, float(playback_delay_seconds))

        def release_ptt_on_deadline() -> None:
            with self._state_lock:
                active = self._active_flex is flex and self._ptt_on
            if not active:
                return
            logger.warning("Digital CAT PTT deadline reached; releasing PTT while audio playback drains")
            try:
                self._set_cat_ptt(flex, False, require_confirmation=False)
                self._wait_for_cat_mox(flex, False, timeout=0.5)
            except Exception as exc:
                logger.error("Failed to release CAT PTT at digital TX deadline: %s", exc, exc_info=True)
            with self._state_lock:
                if self._active_flex is flex:
                    self._ptt_on = False

        try:
            if use_cat:
                if not flex:
                    raise RuntimeError("CAT PTT requested but Flex radio control is not available")
                if playback_deadline is not None:
                    pre_key_seconds = 1.7
                    self._sleep_until(playback_deadline - pre_key_seconds)
                confirmation_timeout = 1.2
                if playback_deadline is not None:
                    confirmation_timeout = max(0.25, min(1.2, playback_deadline - time.monotonic() - 0.05))
                self._set_cat_ptt(
                    flex,
                    True,
                    require_confirmation=True,
                    confirmation_timeout=confirmation_timeout,
                )
                ptt_on = True
                with self._state_lock:
                    self._active_flex = flex
                    self._ptt_on = True
                if ptt_limit_seconds is not None:
                    ptt_timer = threading.Timer(max(0.5, float(ptt_limit_seconds)), release_ptt_on_deadline)
                    ptt_timer.daemon = True
                    ptt_timer.start()
                if playback_deadline is None:
                    time.sleep(0.05)
            if self._abort_event.is_set():
                raise RuntimeError("Digital TX aborted")
            if playback_deadline is not None:
                self._sleep_until(playback_deadline)
            playback()
        finally:
            if ptt_timer is not None:
                ptt_timer.cancel()
            if use_cat and ptt_on:
                try:
                    self._set_cat_ptt(flex, False, require_confirmation=False)
                    if not self._wait_for_cat_mox(flex, False, timeout=1.0):
                        logger.warning("Digital CAT PTT OFF command sent but radio MOX off was not confirmed")
                except Exception as exc:
                    logger.error("Failed to release CAT PTT after digital TX: %s", exc, exc_info=True)
            with self._state_lock:
                if self._active_flex is flex:
                    self._active_flex = None
                self._ptt_on = False

    def _resolve_output_device_indexes(self) -> list[Optional[int]]:
        sd = get_sounddevice()
        if sd is None:
            return [None]
        device_str = str(self.audio_output or "").strip()
        if not device_str or device_str.lower() in {"default", "default:"}:
            return [None]

        devices = sd.query_devices()
        hostapis = sd.query_hostapis()

        def unique(values: list[Optional[int]]) -> list[Optional[int]]:
            result: list[Optional[int]] = []
            for value in values:
                if value not in result:
                    result.append(value)
            return result

        def dax_tx_candidates() -> list[int]:
            candidates = []
            for index, device in enumerate(devices):
                name = str(device["name"])
                name_l = name.lower()
                if device["max_output_channels"] <= 0:
                    continue
                is_dax_tx = "dax tx" in name_l or "dax audio tx" in name_l or "line out (dax audio tx" in name_l
                if not is_dax_tx or "reserved" in name_l:
                    continue
                host = str(hostapis[device["hostapi"]]["name"]).lower()
                # WDM-KS often exposes DAX as many-channel line-out devices and
                # can fail with PaError -9999. Prefer WASAPI, then DirectSound.
                host_score = 0 if "wasapi" in host else 1 if "directsound" in host else 2 if "mme" in host else 9
                exact_score = (
                    0 if name_l == "dax tx" or name_l.startswith("dax tx ") else
                    1 if name_l.startswith("dax audio tx") else
                    2
                )
                candidates.append((host_score, exact_score, index, name, host))
            return [index for _, _, index, _, _ in sorted(candidates)]

        try:
            if ":" in device_str:
                explicit_index = int(device_str.split(":", 1)[0].strip())
            else:
                explicit_index = int(device_str)
            try:
                device = devices[explicit_index]
                host = str(hostapis[device["hostapi"]]["name"]).lower()
                name = str(device["name"]).lower()
                if "wdm-ks" in host and ("dax tx" in name or "dax audio tx" in name or "line out (dax audio tx" in name):
                    return unique(dax_tx_candidates() + [explicit_index])
            except Exception:
                pass
            return [explicit_index]
        except ValueError:
            pass
        except IndexError:
            pass

        lowered = device_str.lower()
        if lowered in {"flexradio", "dax", "dax_tx", "dax_tx_1", "flexradio_dax_tx"}:
            candidates = dax_tx_candidates()
            if candidates:
                first = candidates[0]
                host = hostapis[devices[first]["hostapi"]]["name"]
                logger.info("Resolved FlexRadio DAX TX output to [%s] %s (%s)", first, devices[first]["name"], host)
                return candidates

        search_name = device_str.split(":", 1)[1].strip() if ":" in device_str else device_str
        search_l = search_name.lower()
        matched = []
        for index, device in enumerate(devices):
            if device["max_output_channels"] > 0 and search_l in str(device["name"]).lower():
                matched.append(index)
        if matched:
            return unique(matched)

        logger.warning("Audio output device '%s' not found; using default output", device_str)
        return [None]

    def _resolve_soundcard_speakers(self) -> list[Any]:
        sc = get_soundcard()
        if sc is None:
            return []
        try:
            speakers = list(sc.all_speakers())
        except Exception as exc:
            logger.warning("Unable to enumerate soundcard speakers: %s", exc)
            return []

        device_str = str(self.audio_output or "").strip()
        lowered = device_str.lower()

        def unique(devices: list[Any]) -> list[Any]:
            result: list[Any] = []
            names: set[str] = set()
            for device in devices:
                name = str(getattr(device, "name", ""))
                if name not in names:
                    result.append(device)
                    names.add(name)
            return result

        def dax_tx_candidates() -> list[Any]:
            preferred = []
            fallback = []
            for device in speakers:
                name_l = str(getattr(device, "name", "")).lower()
                if "reserved" in name_l:
                    continue
                if "dax audio tx" in name_l or "dax tx" in name_l:
                    score = (
                        0 if name_l == "dax tx (flexradio dax)" or name_l.startswith("dax tx ") else
                        1 if name_l.startswith("dax audio tx") else
                        2
                    )
                    preferred.append((score, device))
                elif "dax" in name_l and "tx" in name_l:
                    fallback.append(device)
            return [device for _, device in sorted(preferred, key=lambda item: item[0])] + fallback

        if not device_str or lowered in {"default", "default:"}:
            try:
                return [sc.default_speaker()]
            except Exception:
                return speakers[:1]

        if lowered in {"flexradio", "dax", "dax_tx", "dax_tx_1", "flexradio_dax_tx"}:
            candidates = dax_tx_candidates()
            if candidates:
                logger.info("Resolved soundcard FlexRadio DAX TX output to %s", candidates[0].name)
                return unique(candidates)

        search_name = device_str.split(":", 1)[1].strip() if ":" in device_str else device_str
        search_l = search_name.lower()
        matched = [device for device in speakers if search_l in str(getattr(device, "name", "")).lower()]
        if matched:
            return unique(matched)

        logger.warning("Soundcard output device '%s' not found; using default output", device_str)
        try:
            return [sc.default_speaker()]
        except Exception:
            return speakers[:1]

    def _resolve_output_device_index(self) -> Optional[int]:
        """Compatibility helper for tests and old callers."""
        return self._resolve_output_device_indexes()[0]


def ntp_offset(server: str = "pool.ntp.org", timeout: float = 1.5) -> dict[str, Any]:
    """Return local clock offset from an NTP server without changing system time."""
    packet = b"\x1b" + 47 * b"\0"
    start = time.time()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(packet, (server, 123))
            data, _ = sock.recvfrom(48)
        end = time.time()
        if len(data) < 48:
            raise RuntimeError("short NTP reply")
        seconds = int.from_bytes(data[40:44], "big") - 2208988800
        fraction = int.from_bytes(data[44:48], "big") / 2**32
        server_time = seconds + fraction
        midpoint = (start + end) / 2.0
        offset_ms = (server_time - midpoint) * 1000.0
        return {
            "ok": True,
            "server": server,
            "offset_ms": round(offset_ms, 2),
            "rtt_ms": round((end - start) * 1000.0, 2),
        }
    except Exception as exc:
        return {
            "ok": False,
            "server": server,
            "error": str(exc),
        }
