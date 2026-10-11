# Windows Codex handoff: RUMlog/xCat frequency rejection and FLEX `NOT_READY`

Copy the prompt below into Codex on the Windows station machine. Work from the
Git branch and exact commit reported with this document.

## Prompt for Codex on Windows

Investigate and fix the commissioned OM0RX Remote Station Agent issue described
below. Do not weaken transmit safety and do not issue RF-producing commands.

### Observed live failure on 2026-10-11

The macOS applications are communicating correctly:

- RUMlogNG has an established TCP connection to OM0RX-xCat at
  `127.0.0.1:15002`.
- OM0RX-xCat is listening on CAT port `15002` and RigCtlD port `14532`.
- CAT and RigCtlD readback both returned `7.217600 MHz`, `LSB`.
- Clicking AA3B at `3.862700 MHz` SSB in OM0RX-xCluster transferred the
  callsign, mode, and note `PAQP BER` into RUMlogNG.
- RUMlogNG's frequency remained `7.2176 MHz`. With Follow TRX enabled it read
  the unchanged frequency back from xCat after the tune was rejected.
- xCluster's Apple-event implementation uses RUMlogNG's documented kHz
  `frequency` and `txFrequency` properties. This is not an Apple-event unit or
  field-name defect.
- The RUMlogNG-to-xCat TCP socket was established at the time of diagnosis.
- xCat displayed FLEX `7.218 MHz LSB`, KPA500 `STBY`, KAT500 `ANT2`, route
  `40m`, and `ALARM 3`.
- The agent advisory was:
  `KPA500 reports 160m while FLEX is on 40m; KAT500 reports 160m while FLEX is on 40m; FLEX is not in a confirmed receive-ready state (NOT_READY)`.
- macOS unified logs showed repeated HTTP `409` responses from the remote
  command endpoint while the failed tune was being retried.

### Suspected control-flow defect

`RemoteStationRuntime` sends both `set_frequency_hz` and `set_mode` through
`StationCoordinator.execute_flex_route_change()`.

That method calls `_fresh_receive_state()` before putting the KPA500 into
verified standby or executing the receive-side FLEX mutation. The current
receive proof accepts only interlock `READY` or `RECEIVE`. The live radio
reported fresh `MOX=false` with interlock `NOT_READY`, so the command failed
with `flex-not-receiving` and HTTP 409.

This appears to create a recovery deadlock when FLEX and the Elecraft devices
are on different bands: the mismatch contributes to the non-ready state, but
the coordinator rejects the receive-only route change needed to put the
station back onto one verified route.

Relevant source locations:

- `remote_station/runtime.py`: `set_frequency_hz` and `set_mode`
- `services/elecraft_station.py`: `execute_flex_route_change()`,
  `_fresh_receive_state()`, `_prepare_route()`, and
  `follow_observed_radio_route()`
- `radio_control/flex_radio.py`: existing interpretation of receive/off
  interlock states, including `NOT_READY`
- `tests/smoke/test_station_coordinator.py`
- `tests/smoke/test_remote_station_agent.py`
- `docs/REMOTE_STATION_HANDOFF.md`

### Required investigation

1. Fetch the handoff branch and verify its exact SHA before editing. Preserve
   unrelated Windows work and local credential-bearing configuration.
2. Capture sanitized, read-only live evidence for FLEX connection and Maestro
   binding, active/TX slice, frequency, mode, MOX, TUNE/PTT, interlock state,
   RX/TX antenna, KPA500 state/band, KAT500 state/band/output, coordinator
   state, route state, and alarms.
3. Determine why FLEX reports `NOT_READY`. Distinguish a normal receive-idle
   state from an actual transmit/interlock fault. Do not assume that every
   `NOT_READY` state is safe.
4. Reproduce the rejection through the local command API or maintained test
   harness without transmitting. Confirm the exact error code and sequencing.
5. Trace whether frequency and mode are both rejected by the same preflight.

### Required implementation properties

Implement the smallest safe correction supported by the evidence. The desired
behavior is a narrowly scoped receive-route recovery, not a global addition of
`NOT_READY` to every accepted interlock set.

- A receive-side frequency or mode change may proceed only with fresh,
  authoritative proof that FLEX is connected and bound, telemetry is not
  stale, `MOX` is exactly `false`, and neither TUNE nor PTT/transmit is active.
- If the interlock is `NOT_READY`, proceed only when its observed reason is
  compatible with receive-side route recovery. Unknown, stale, transmitting,
  faulted, or contradictory state must remain blocked.
- Confirm KPA500 standby before any route mutation.
- Perform the receive-side change and then reconcile KPA500/KAT500/FLEX to the
  target band using the existing coordinator-owned route transaction.
- Verify exact FLEX frequency/mode/antenna and KPA/KAT band/output readback
  before reporting success.
- On any failure, remain fail-closed, keep the amplifier in standby, expose a
  precise error, and do not fabricate success to CAT/RigCtlD clients.
- Do not relax PTT, TUNE, CWX, Operate, RF-power, amplifier, tuner, or transmit
  preflights. They must continue to require their existing transmit-safe
  evidence.
- Avoid command retry storms. One rejected CAT command must not create
  overlapping route transactions.
- Keep RUMlogNG's existing Kenwood TS-480 loopback configuration and Follow
  TRX behavior unchanged.

If live evidence shows that `NOT_READY` is a genuine hardware or Maestro
interlock fault rather than a recoverable receive-idle state, do not bypass it.
Instead, identify the exact source, improve the operator-visible diagnostic,
and report the required physical/configuration correction.

### Regression coverage

Add tests that prove at least the following:

1. Fresh `MOX=false` plus a specifically recoverable `NOT_READY` state allows
   receive-only frequency/mode route recovery in the required safe sequence.
2. `MOX=true`, unknown MOX, stale/unconfirmed telemetry, a transmit state, or
   an unclassified/fault `NOT_READY` state remains blocked.
3. KPA500 standby failure blocks the FLEX mutation.
4. Failed FLEX or KAT/KPA readback leaves the route unverified and reports an
   error.
5. Existing `READY` and `RECEIVE` behavior remains unchanged.
6. PTT, TUNE, CWX, Operate, and other transmit-affecting commands remain
   fail-closed under `NOT_READY`.
7. A successful CAT `FA` frequency change and mode change return success only
   after the remote command is accepted, and the resulting radio snapshot
   persists rather than snapping back.
8. Repeated or concurrent CAT requests remain serialized and bounded.

Run the complete maintained Python smoke suite, focused coordinator/remote
agent tests, Node contract/UI tests where applicable, Ruff `F,E9`, Python
compile checks, and Git whitespace checks. Report exact pass/fail counts.

### Live acceptance boundary

Live acceptance must remain receive-only unless Oliver explicitly authorizes a
separate transmit test. Do not issue PTT-on, TUNE, CWX, Operate, or any command
that can produce RF. Keep KPA500 in verified standby. A permitted acceptance
test may perform one receive-only spot QSY and mode change, then verify:

- RUMlogNG retains the requested frequency and mode.
- xCat CAT/RigCtlD readback matches it.
- FLEX/Commander or Maestro shows the same receive frequency and mode.
- KPA500 and KAT500 report the correct target band/output.
- Coordinator route is confirmed and no warning/critical alarm remains.
- MOX remains false and no RF was transmitted.

### Deliverables

- Commit the fix and tests on a `codex/` branch.
- Add a dated evidence/result section to `docs/REMOTE_STATION_HANDOFF.md`.
- Never commit tokens, passwords, private keys, or local `agent.json` content.
- Push the branch and report the exact branch name and commit SHA to Oliver.
- Clearly separate offline test proof from live hardware acceptance.

