"""FT8/FT4 receive decoder boundary.

This module keeps receive decoding behind one explicit boundary so unsupported
decode paths cannot leak placeholder messages into the operator UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import os
import subprocess
import tempfile
from typing import Iterable, Optional
import wave

import numpy as np


FT8_SAMPLE_RATE = 12000
FT8_WINDOW_SECONDS = 15
FT4_WINDOW_SECONDS = 7.5
FT8_WINDOW_SAMPLES = FT8_SAMPLE_RATE * FT8_WINDOW_SECONDS
FT4_WINDOW_SAMPLES = int(FT8_SAMPLE_RATE * FT4_WINDOW_SECONDS)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENDOR_DECODER_PATH = PROJECT_ROOT / "vendor" / "ft8_lib" / "decode_ft8.exe"
DECODE_LINE_RE = re.compile(
    r"^(?P<hms>\d{6})\s+"
    r"(?P<snr>[+-]?\d+(?:\.\d+)?)\s+"
    r"(?P<dt>[+-]?\d+(?:\.\d+)?)\s+"
    r"(?P<freq>\d+)\s+~\s+"
    r"(?P<message>.+?)\s*$"
)


class FT8DecoderUnavailable(RuntimeError):
    """Raised when raw-audio FT8 decoding is requested before a decoder exists."""


@dataclass(frozen=True)
class FT8DecodedMessage:
    """A decoded FT8 message from a single receive window."""

    timestamp: datetime
    message: str
    snr: float
    dt: float
    freq: float
    mode: str = "FT8"

    def to_dict(self) -> dict:
        slot_start = self.timestamp.isoformat()
        return {
            "timestamp": slot_start,
            "slot_start_utc": slot_start,
            "message": self.message,
            "snr": self.snr,
            "dt": self.dt,
            "freq": self.freq,
            "mode": self.mode,
        }


@dataclass(frozen=True)
class FT8RxDecoderStatus:
    """Current raw-audio decoder capability."""

    engine: str = "unbound"
    available: bool = False
    license: str = "n/a"
    sample_rate: int = FT8_SAMPLE_RATE
    window_seconds: int = FT8_WINDOW_SECONDS
    supported_modes: tuple[str, ...] = ("FT8",)
    reason: str = (
        "No raw-audio FT8/FT4 decoder binding is installed."
    )

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "available": self.available,
            "license": self.license,
            "sample_rate": self.sample_rate,
            "window_seconds": self.window_seconds,
            "supported_modes": list(self.supported_modes),
            "reason": self.reason,
        }


def normalise_decode_mode(mode: str = "FT8") -> str:
    mode_upper = str(mode or "FT8").upper()
    if mode_upper not in {"FT8", "FT4"}:
        raise ValueError("Built-in receive currently supports FT8 and FT4 only")
    return mode_upper


def decode_window_seconds(mode: str = "FT8") -> float:
    return FT4_WINDOW_SECONDS if normalise_decode_mode(mode) == "FT4" else float(FT8_WINDOW_SECONDS)


def decode_window_samples(mode: str = "FT8") -> int:
    return int(FT8_SAMPLE_RATE * decode_window_seconds(mode))


class FT8RxDecoder:
    """Interface for raw-audio FT8/FT4 decoders."""

    status = FT8RxDecoderStatus()

    def decode_window(
        self,
        samples: Iterable[float] | np.ndarray,
        *,
        sample_rate: int = FT8_SAMPLE_RATE,
        window_start: Optional[datetime] = None,
        mode: str = "FT8",
    ) -> list[FT8DecodedMessage]:
        sample_array = np.asarray(samples, dtype=np.float32)
        self.validate_window(sample_array, sample_rate, mode=mode)
        raise FT8DecoderUnavailable(self.status.reason)

    @staticmethod
    def validate_window(samples: np.ndarray, sample_rate: int, *, mode: str = "FT8") -> None:
        mode_upper = normalise_decode_mode(mode)
        if sample_rate != FT8_SAMPLE_RATE:
            raise ValueError(f"{mode_upper} decoder expects {FT8_SAMPLE_RATE} Hz audio, got {sample_rate} Hz")

        window_seconds = decode_window_seconds(mode_upper)
        expected_samples = decode_window_samples(mode_upper)
        min_samples = int(expected_samples * 0.9)
        max_samples = int(expected_samples * 1.1)
        if not min_samples <= len(samples) <= max_samples:
            raise ValueError(
                f"{mode_upper} decoder expects roughly {window_seconds:g}s of audio "
                f"({min_samples}-{max_samples} samples), got {len(samples)} samples"
            )


def get_ft8_rx_decoder_status() -> dict:
    """Return the current raw-audio FT8 decoder status."""

    return get_default_ft8_rx_decoder().status.to_dict()


class VendorFT8LibRxDecoder(FT8RxDecoder):
    """Decode FT8/FT4 windows by invoking the vendored MIT ft8_lib decoder executable."""

    def __init__(self, executable: Path = VENDOR_DECODER_PATH):
        self.executable = executable
        self.status = FT8RxDecoderStatus(
            engine="vendor.ft8_lib.decode_ft8",
            available=executable.exists(),
            license="MIT",
            supported_modes=("FT8", "FT4"),
            reason=(
                "Vendored ft8_lib decode_ft8 executable is available for FT8/FT4"
                if executable.exists()
                else f"Vendored ft8_lib decoder is not built: {executable}"
            ),
        )

    def decode_window(
        self,
        samples: Iterable[float] | np.ndarray,
        *,
        sample_rate: int = FT8_SAMPLE_RATE,
        window_start: Optional[datetime] = None,
        mode: str = "FT8",
    ) -> list[FT8DecodedMessage]:
        if not self.executable.exists():
            raise FT8DecoderUnavailable(self.status.reason)

        mode_upper = normalise_decode_mode(mode)
        sample_array = np.asarray(samples, dtype=np.float32)
        self.validate_window(sample_array, sample_rate, mode=mode_upper)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            self._write_wav(temp_path, sample_array, sample_rate)
            return self.decode_wav(temp_path, window_start=window_start, mode=mode_upper)
        finally:
            temp_path.unlink(missing_ok=True)

    def decode_wav(
        self,
        wav_path: Path,
        *,
        window_start: Optional[datetime] = None,
        mode: str = "FT8",
    ) -> list[FT8DecodedMessage]:
        if not self.executable.exists():
            raise FT8DecoderUnavailable(self.status.reason)

        mode_upper = normalise_decode_mode(mode)
        command = [str(self.executable)]
        if mode_upper == "FT4":
            command.append("-ft4")
        command.append(str(Path(wav_path).resolve()))
        env = os.environ.copy()
        for dll_dir in (Path(r"C:\msys64\ucrt64\bin"), Path(r"C:\msys64\mingw64\bin")):
            if dll_dir.exists() and str(dll_dir) not in env.get("PATH", ""):
                env["PATH"] = f"{dll_dir};{env.get('PATH', '')}"
        result = subprocess.run(
            command,
            cwd=str(self.executable.parent),
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return self._parse_decode_output(result.stdout, window_start=window_start, mode=mode_upper)

    @staticmethod
    def _write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
        clipped = np.clip(samples, -1.0, 1.0)
        pcm = (clipped * 32767.0).astype(np.int16)

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())

    @staticmethod
    def _parse_decode_output(
        output: str,
        *,
        window_start: Optional[datetime] = None,
        mode: str = "FT8",
    ) -> list[FT8DecodedMessage]:
        messages: list[FT8DecodedMessage] = []
        timestamp = window_start or datetime.now(timezone.utc)
        mode_upper = normalise_decode_mode(mode)

        for line in output.splitlines():
            match = DECODE_LINE_RE.match(line.strip())
            if not match:
                continue
            messages.append(
                FT8DecodedMessage(
                    timestamp=timestamp,
                    message=match.group("message").strip(),
                    snr=float(match.group("snr")),
                    dt=float(match.group("dt")),
                    freq=float(match.group("freq")),
                    mode=mode_upper,
                )
            )

        return messages


def get_default_ft8_rx_decoder() -> FT8RxDecoder:
    """Return the best available raw-audio FT8 decoder implementation."""

    if VENDOR_DECODER_PATH.exists():
        return VendorFT8LibRxDecoder(VENDOR_DECODER_PATH)
    return FT8RxDecoder()
