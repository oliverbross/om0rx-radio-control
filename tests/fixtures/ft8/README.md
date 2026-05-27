# FT8 RX Fixtures

Place known-good 15-second mono WAV captures here when validating raw-audio FT8 decode.

Capture requirements:

- Sample rate: 12000 Hz.
- Duration: one FT8 receive slot, roughly 15 seconds.
- Audio: radio/DAX receive audio, not microphone room audio.
- Mode: USB on a normal FT8 watering-hole frequency.
- System clock: synchronized before capture.

Use `scripts/maintenance/capture_ft8_fixture.py` to create a local capture from a selected audio device. Fixtures are intentionally not bundled yet because the project does not currently ship a raw-audio decoder binding.
