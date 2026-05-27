"""Capture a 15-second FT8 RX WAV fixture from a local audio device."""

from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    import sounddevice as sd
except ImportError as exc:  # pragma: no cover - depends on local workstation setup
    raise SystemExit("sounddevice is not installed; install project dependencies first") from exc


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "ft8"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-devices", action="store_true", help="List input devices and exit")
    parser.add_argument("--device", help="Input device index or exact/partial device name")
    parser.add_argument("--name", default=None, help="Fixture file stem; defaults to UTC timestamp")
    parser.add_argument("--sample-rate", type=int, default=12000)
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--no-align-slot", action="store_true", help="Do not wait for the next FT8 15s UTC slot")
    parser.add_argument("--expected", action="append", default=[], help="Expected decoded message text")
    return parser.parse_args()


def list_input_devices() -> None:
    for index, device in enumerate(sd.query_devices()):
        if device.get("max_input_channels", 0) > 0:
            print(f"{index}: {device['name']} ({device['max_input_channels']} input channels)")


def resolve_device(device_query: str | None):
    if not device_query:
        return None

    if device_query.isdigit():
        return int(device_query)

    lowered = device_query.lower()
    matches = [
        index
        for index, device in enumerate(sd.query_devices())
        if device.get("max_input_channels", 0) > 0 and lowered in device["name"].lower()
    ]
    if not matches:
        raise SystemExit(f"No input audio device matched: {device_query}")
    if len(matches) > 1:
        raise SystemExit(f"Audio device query is ambiguous; matching indices: {matches}")
    return matches[0]


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def seconds_to_next_ft8_slot() -> float:
    now = datetime.now(timezone.utc)
    seconds = now.second + now.microsecond / 1_000_000
    return (15 - (seconds % 15)) % 15


def update_manifest(
    path: Path,
    sample_rate: int,
    seconds: float,
    expected: list[str],
    start_utc: datetime,
) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rel_path = path.relative_to(FIXTURE_DIR).as_posix()
    entry = {
        "file": rel_path,
        "sample_rate": sample_rate,
        "seconds": seconds,
        "start_utc": start_utc.isoformat(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "expected_messages": expected,
    }

    manifest["fixtures"] = [item for item in manifest["fixtures"] if item["file"] != rel_path]
    manifest["fixtures"].append(entry)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.list_devices:
        list_input_devices()
        return 0

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    device = resolve_device(args.device)
    frames = int(args.sample_rate * args.seconds)
    name = args.name or datetime.now(timezone.utc).strftime("ft8_%Y%m%d_%H%M%S")
    wav_path = FIXTURE_DIR / f"{name}.wav"

    if not args.no_align_slot:
        wait_seconds = seconds_to_next_ft8_slot()
        if wait_seconds > 0.05:
            print(f"Waiting {wait_seconds:.2f}s for next FT8 15s UTC slot")
            time.sleep(wait_seconds)

    start_utc = datetime.now(timezone.utc)
    print(f"Recording {args.seconds:.1f}s at {args.sample_rate} Hz from device {device or 'default'}")
    samples = sd.rec(frames, samplerate=args.sample_rate, channels=1, dtype="float32", device=device)
    sd.wait()
    mono = np.asarray(samples[:, 0], dtype=np.float32)

    write_wav(wav_path, mono, args.sample_rate)
    update_manifest(wav_path, args.sample_rate, args.seconds, args.expected, start_utc)
    print(f"Wrote {wav_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
