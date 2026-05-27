"""FT8 raw-audio RX decoder contract tests."""

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pytest

import _bootstrap  # noqa: F401
from services.ft8_rx_decoder import (
    FT4_WINDOW_SAMPLES,
    FT8_SAMPLE_RATE,
    FT8_WINDOW_SAMPLES,
    FT8DecoderUnavailable,
    FT8RxDecoder,
    VENDOR_DECODER_PATH,
    VendorFT8LibRxDecoder,
    get_ft8_rx_decoder_status,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_MANIFEST = ROOT / "tests" / "fixtures" / "ft8" / "manifest.json"


def test_rx_decoder_status_is_explicit():
    status = get_ft8_rx_decoder_status()

    assert status["engine"] in {"unbound", "vendor.ft8_lib.decode_ft8"}
    assert status["available"] is VENDOR_DECODER_PATH.exists()
    assert status["sample_rate"] == FT8_SAMPLE_RATE
    assert status["window_seconds"] == 15
    assert "FT8" in status["supported_modes"]


def test_rx_decoder_validates_ft8_window_shape_before_decode():
    decoder = FT8RxDecoder()
    samples = np.zeros(FT8_WINDOW_SAMPLES, dtype=np.float32)

    with pytest.raises(FT8DecoderUnavailable):
        decoder.decode_window(samples, sample_rate=FT8_SAMPLE_RATE, window_start=datetime.now(timezone.utc))


def test_rx_decoder_rejects_wrong_sample_rate():
    decoder = FT8RxDecoder()
    samples = np.zeros(FT8_WINDOW_SAMPLES, dtype=np.float32)

    with pytest.raises(ValueError, match="12000 Hz"):
        decoder.decode_window(samples, sample_rate=48000)


def test_rx_decoder_rejects_wrong_duration():
    decoder = FT8RxDecoder()
    samples = np.zeros(FT8_SAMPLE_RATE, dtype=np.float32)

    with pytest.raises(ValueError, match="roughly 15s"):
        decoder.decode_window(samples, sample_rate=FT8_SAMPLE_RATE)


def test_rx_decoder_accepts_ft4_window_shape_before_decode():
    decoder = FT8RxDecoder()
    samples = np.zeros(FT4_WINDOW_SAMPLES, dtype=np.float32)

    with pytest.raises(FT8DecoderUnavailable):
        decoder.decode_window(samples, sample_rate=FT8_SAMPLE_RATE, mode="FT4")


def test_vendor_decoder_parses_ft4_mode():
    decoded = VendorFT8LibRxDecoder._parse_decode_output(
        "120000 -10 0.2 1500 ~ CQ OM0RX JN88\n",
        mode="FT4",
    )

    assert len(decoded) == 1
    assert decoded[0].mode == "FT4"


def test_vendor_decoder_decodes_captured_fixture_when_built():
    if not VENDOR_DECODER_PATH.exists():
        pytest.skip("vendor ft8_lib decoder executable has not been built")

    manifest = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
    fixture = manifest["fixtures"][0]
    fixture_path = FIXTURE_MANIFEST.parent / fixture["file"]
    decoder = VendorFT8LibRxDecoder(VENDOR_DECODER_PATH)

    decoded = decoder.decode_wav(fixture_path)
    decoded_messages = {message.message for message in decoded}
    expected_messages = fixture.get("ft8_lib_expected_messages", fixture["expected_messages"])

    assert len(decoded) >= len(expected_messages)
    for expected in expected_messages:
        assert expected in decoded_messages
