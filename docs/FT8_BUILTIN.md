# Built-In Digital Client

This project keeps the Digital feature as a first-class built-in FT8/FT4 client. It must report honest capability state: RX decode is available only when the local decoder executable is present, and TX is available only when the local encoder/audio/PTT boundary is usable.

## Current Status

- UI shell: present as the separate Digital window at `/ft8.html`.
- Backend API shell: present under `/api/ft8`.
- Audio/waterfall path: present through the backend audio capture and waterfall processor.
- FT8/FT4 engine: MIT-compatible `ft8_lib` boundary, using local built tools where available.
- Live receive decode: enabled when `vendor/ft8_lib/decode_ft8.exe` is available.
- Radio transmit: enabled when `vendor/ft8_lib/gen_ft8.exe`, audio output, and CAT/VOX PTT are available.
- Auto-sequence QSOs: available behind explicit TX enablement, watchdog limits, and operator settings.
- Classic FT8 Fox/Hound hunting: Hound-side automation hooks are present.
- SuperFox hunting: settings and spot switching are present, but automated TX is blocked until a real SuperFox RX decoder verifies the Fox.

## Licensing Position

The project is MIT-licensed, so the built-in browser FT8 path uses the MIT `ft8_lib` bundle. GPL-derived WSJT-X/MSHV decoder bundles are not distributed as active project assets because that would change the licensing obligations for the whole project.

## Active Boundaries

### Frontend

- `frontend/js/ft8-engine.js` is the only FT8 engine boundary used by the modal.
- `frontend/js/ft8-modal.js` loads the engine dynamically and displays backend-reported capabilities.
- `frontend/ft8_ft8lib.js` wraps the MIT WebAssembly module.
- `frontend/ft8lib/` contains the MIT WebAssembly assets.

The frontend engine can initialize `ft8_lib` and exercise message-to-symbol/audio generation for future validation work. It deliberately returns no decoded messages until live decode is implemented and tested.

### Backend

- `services/ft8_service.py` owns service state, configuration, audio capture, waterfall output, and WebSocket updates.
- `services/ft8_rx_decoder.py` defines the raw-audio RX decoder contract. When `vendor/ft8_lib/decode_ft8.exe` is built, the backend can decode FT8 and FT4 receive windows through the vendored decoder.
- `services/ft8_tx.py` owns message waveform generation, audio output, and CAT/VOX PTT control.
- Classic Fox/Hound Hound operation uses the same normal FT8 transmit waveform with Hound-specific audio-frequency rules.
- SuperFox RX/TX capability is reported separately. The project must not treat normal FT8 decoding as a SuperFox decode.
- Backend status reports capability flags:
  - `waterfall: true`
  - `audio_stream: true`
  - `message_encode: true`
  - `rx_decode: true` when the vendored decoder executable is built; otherwise `false`
  - `tx: true` only when the transmit engine reports available
- `/api/ft8/transmit`, `/api/ft8/tx/enable`, `/api/ft8/tx/halt`, and `/api/ft8/tx/tune` are wired to the backend service.

## Retired Code

The previous implementation has been removed because it was misleading:

- `frontend/js/ft8-decoder.js` generated fake decoded messages.
- `services/ft8_protocol.py` was a homegrown protocol implementation without fixture-backed correctness.
- `frontend/mshv*` assets were removed from the project distribution.

## Next Implementation Steps

1. Capture known-good FT8 WAV fixtures with expected decode output.
2. Prove the selected MIT-compatible engine can decode fixtures in a repeatable smoke/integration test.
3. Improve decoder sensitivity until it approaches the WSJT-X oracle on local fixtures.
4. Move autonomous target selection from the browser into a backend Digital automation controller.
5. Add full integration tests for spot-driven hunt, decode-driven calling, completed QSO logging, and post-log Wavelog status refresh.

The priority remains correctness-first. Transmit exists, but fully autonomous operation should stay conservative until the backend controller owns target queues, dwell timing, duplicate checks, watchdog outcomes, and log verification.

## What Is Needed For Full RX

The browser `ft8_lib` wrapper exposes message packing/unpacking and audio generation, not raw-audio decode from live samples. The backend now uses the vendored MIT `ft8_lib` C decoder when `vendor/ft8_lib/decode_ft8.exe` has been built:

```powershell
.\scripts\maintenance\build_ft8_lib_decoder.ps1
```

This is self-contained and MIT-compatible, but it is currently less sensitive than WSJT-X on the first captured fixture. WSJT-X `jt9.exe` decoded 21 messages from the slot. The vendored `ft8_lib` decoder currently decodes 14. The application can use it for live RX, but the next quality pass should focus on sensitivity before calling it equivalent to WSJT-X.

Not preferred for this MIT project: importing GPL decoders such as PyFT8, WSJT-X, JTDX, or MSHV into the application distribution.

For local validation, capture a fixture from the same audio route the app will use:

```powershell
python .\scripts\maintenance\capture_ft8_fixture.py --list-devices
python .\scripts\maintenance\capture_ft8_fixture.py --device "DAX Audio RX" --name 20m_ft8_sample --expected "CQ EXAMPLE GRID"
```

Replace the `--expected` value with one or more messages confirmed from a trusted decoder for that same 15-second slot.

On this workstation, WSJT-X is configured with:

- Rig: FlexRadio 6xxx
- CAT network server: `127.0.0.1:5002`
- PTT method: CAT
- Mode: Data/Pkt
- Split operation: Fake It
- Audio input: `DAX Audio RX 1 (FlexRadio Systems DAX Audio)`, mono
- Audio output: `DAX Audio TX (FlexRadio Systems DAX TX)`, mono

On Windows with Python 3.14 or newer, the built-in service skips the optional
`sounddevice`/PortAudio import probe by default because affected PortAudio
builds can terminate the probe process during interpreter shutdown. The safe
`soundcard` fallback remains available. Set `FT8_ENABLE_SOUNDDEVICE_PROBE=1`
only for an explicitly supervised compatibility test; the existing
`FT8_DISABLE_SOUNDDEVICE=1` override continues to disable it on every runtime.

The first local RX fixture was captured from sounddevice index `74`, matching that WSJT-X input through Windows DirectSound:

```powershell
python .\scripts\maintenance\capture_ft8_fixture.py --device 74 --name wsjtx_dax_rx1_directsound_20260526_083558
python .\scripts\maintenance\validate_ft8_fixture_with_jt9.py --fixture wsjtx_dax_rx1_directsound_20260526_083558.wav
```

The validation script uses the locally installed WSJT-X `jt9.exe` only as a development oracle. The application must not depend on it for the final built-in client.
