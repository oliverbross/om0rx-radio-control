# FT8/FT4 Automation Review

Date: 2026-05-26

## Current State

The built-in digital window can receive spot selections, tune the radio, decode through the backend decoder boundary when available, classify decoded calls through the existing spot/Wavelog explanation API, queue FT8/FT4 transmit messages, run watchdog-limited TX cycles, and log completed QSOs through the existing QSO logging endpoint.

The implementation is not yet a complete autonomous operator. It has the foundations, but the automation policy still lives mostly in the frontend and needs to move into a backend controller before it can be considered reliable.

## Fixes Made During Review

- FT4 decode timing now uses 7.5 second slots instead of the FT8 15 second slot math.
- Digital cluster spot frequencies are normalized correctly. If a spot is near the standard FT8/FT4 dial frequency, the radio tunes to the standard dial and the station is tracked by audio offset.
- Spot-driven hunt now has an explicit listen window. Incoming spot targets are stored with expiry and only become callable after an actual decode of the target callsign.
- Spot pseudo rows are guarded so they do not immediately trigger Auto Call without hearing the station.
- WSJT-Z-style caller policy is now wired: directed callers can be handled separately from CQ stations, and the "apply filtering to callers" setting now affects automation decisions.
- Auto-ignore now has a real temporary ignore map with optional reset expiry, so repeated failed/queued targets do not immediately churn the auto-call loop.
- Auto-call priority now affects Digital message ordering for last decoded, strongest signal, or longest distance.
- Scheduled band/mode hopping now has a runtime timer, hop interval, UTC band-plan parsing, and optional FT8/FT4 switching.
- Band hopping now scores each in-window band/mode before moving. The default plan is `05:20m,17m,15m,12m,10m` and `20:30m,40m,80m,160m`; within that window it prefers active spot targets, needed decoded stations, CQ activity, stronger signals, and active bands over empty bands.
- The "Auto" TX frequency control now searches recent decoded offsets and chooses a free TX audio frequency in the configured wide/narrow range.
- Classic FT8 Fox/Hound Hound operation now has explicit settings and automation hooks. Incoming spots can switch Digital into Hound intent, Hound TX audio ranges use 1000-4000 Hz, and report replies can move to the Fox response audio frequency.
- SuperFox settings are present and persisted, including OTP fields and spot-driven switching, but SuperFox automation is blocked until a real SuperFox RX decoder verifies the Fox. This avoids transmitting in response to a mode the built-in decoder cannot yet decode.
- Added focused smoke coverage for FT4 timing and spot-hunt tuning/listen behavior.

## Important Gaps

1. Automation policy is split between frontend and backend.
   The browser currently decides whether a decoded station should be called. A fully autonomous system should make that decision in one backend controller so it keeps working if the UI refreshes, disconnects, or opens in another window.

2. Band hopping now runs in the Digital frontend, but it still belongs in the backend.
   The current timer can follow the UTC band plan and switch FT8/FT4, but a production autonomous system needs a backend scheduler that survives UI reloads and can combine UTC time, solar conditions, recent decode rate, and spot priority.

3. Spot queue management is still minimal.
   We need a prioritized target queue with dwell timers, expiry, retries, backoff, and clear reasons for skipping a target.

4. Needed-status decisions need one canonical scoring layer.
   The decoded-message UI currently derives needed flags from call/DXCC status text. The backend should use the same classifier used by spots, backed by Wavelog/DuckDB and CTY resolution, and return structured fields such as `new_dxcc`, `new_band`, `new_mode`, `new_grid`, and `duplicate_band_mode`.

5. QSO automation needs a more formal state machine.
   The current backend can progress reports/RRR/73, but it needs target ownership, retry limits, timeout transitions, duplicate protection, and log verification before moving to the next target.

6. FT4 decode capability must be validated with fixtures.
   Timing is now correct, but the vendored decoder path needs known-good FT4 audio fixtures before we can claim FT4 RX parity with FT8.

7. SuperFox requires a real decoder before full automation can be enabled.
   WSJT-X 2.7 SuperFox uses a new wide constant-envelope Fox waveform with OTP verification. Hound transmissions are normal FT8, but they must be gated by a decoded and verified SuperFox signal.

## Target Architecture

### Backend Digital Automation Controller

Create a backend service, separate from the UI, that owns:

- target ingestion from DX spots
- target ingestion from decoded CQ/caller messages
- target scoring and de-duplication
- band/mode scheduling
- radio tuning and dwell timing
- QSO state machine
- Wavelog logging and post-log cache refresh

The frontend should display state and send operator preferences, but it should not be the source of truth for automation decisions.

### Target Lifecycle

Recommended target states:

- `queued`: target accepted from spot/decode
- `tuning`: radio is moving to target band/mode/dial
- `listening`: waiting for target decode during dwell time
- `heard`: target decoded and eligible
- `calling`: transmit sequence active
- `in_qso`: report/RRR/73 exchange active
- `logging`: QSO completed, logging to Wavelog/outbox
- `done`: logged and cache refresh requested
- `skipped`: duplicate, expired, not heard, not needed, unsafe band, weak signal
- `failed`: timeout, TX error, log error

### Priority Score

Suggested priority order:

1. New DXCC / ATNO
2. New DXCC on band
3. New DXCC on mode
4. New band+mode slot
5. New grid
6. New call on band/mode
7. Strong CQ matching filters

Tie breakers:

- stronger SNR
- lower DT absolute value
- recent decode
- band currently rated usable by solar/HF conditions
- spot age

### Duplicate Protection

Before calling, the backend should query the canonical classification layer:

- skip if same call + band + mode already worked unless an explicit override is enabled
- skip if DXCC/band/mode goal is already confirmed and no other active goal matches
- skip if target is in ignore list or temporary backoff
- skip if another QSO is active or TX queue is not empty

### Band Hopping

Band hopping should be scheduler-driven:

- parse user UTC band windows
- combine with HF solar conditions
- measure recent decode count per band/mode
- prefer bands with needed targets
- dwell for a configured minimum time before switching
- never switch while a QSO or pending log is active

### Logging

Completed QSOs should:

- log through `/api/qso/log`
- fall back to the ADIF outbox on Wavelog failure
- refresh worked-status cache after success
- mark target as done only after log success or outbox queue success

## Recommended Next Implementation Step

Build `services/digital_automation.py` as the backend automation controller and move target scoring, spot queueing, duplicate checks, and dwell timers out of the browser. Keep the current frontend controls, but make them configure and monitor this backend service.
