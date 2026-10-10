# MSHV upstream/safety-hook causality map

Scope: pinned upstream commit `d960ae22de78940c6be9d95bd4817d233d02ee39`
compared with the maintained OM0RX patch and the deployed source captured after
the 2026-10-04 single-burst incident.

This document deliberately separates upstream behavior from OM0RX integration
regressions. The correction strategy is to preserve upstream MSHV interaction
and sequencing and add fail-closed station authorization at the narrowest
possible boundary.

## Control-flow comparison

| Area | Pinned upstream behavior | OM0RX change | Observed consequence | Minimal correction |
|---|---|---|---|---|
| Decode-list double-click | Both decode lists connect `ListSelectedTextAll` to `HvTxW::DecListTextAll`. With `Double Click On Call Sets Auto Is On`, a valid FT8 message calls `SetDoubleClickFromAllAutoOn()` and immediately toggles Auto on. | No OM0RX hunk changed this path. | The RX-frequency-list message double-click arming Auto is original behavior, not an OM0RX regression. Apparent inconsistency came from the delayed Auto hook below. | Do not redesign decode-list interaction. Preserve upstream behavior and setting. Test both lists against upstream semantics. |
| Auto button | `HvTxW::auto_on()` synchronously toggles the state and button between `AUTO IS OFF` and `AUTO IS ON`. | Added an asynchronous final-only station request before changing state. While it runs the button remains `AUTO IS OFF`; pending or mismatched state returns silently. | A click appeared to do nothing for 7-8 seconds, encouraging repeated clicks. | Restore upstream `auto_on()` exactly. Acquire station authorization out of band; enforce it only at PTT-on. |
| AutoDX `StartAuto()` | AutoDX queues a target, calls `requestEnableAuto`, and `StartAuto()` immediately enables normal MSHV Auto sequencing. | Added the same asynchronous final-only gate and silent pending returns. | Queue/core/UI state could diverge; AutoDX could believe it handed ownership to MSHV while Auto remained off. | Restore upstream `StartAuto()` exactly. Authorization must not alter target ownership or desired Auto state. |
| Stop Auto | `StopAuto()` clears only MSHV Auto state and normal sequence counters. | Added global station-gate invalidation. | Safety authorization lifetime became coupled to ordinary UI state transitions and internal refreshes. | Restore upstream `StopAuto()`; clear diagnostics/permits through a separate integration hook without changing upstream state transitions. |
| Periodic provider telemetry | No periodic station-gate mutation. | The 2-second telemetry timer calls `StopAuto()`, invalidates authorization, requests a final check, and conditionally restarts Auto whenever AutoDX is enabled and approval is older than 3 seconds. | Auto sequencing is repeatedly interrupted; AutoDX desired state can be disabled on transient failure. | Make the timer telemetry-only. A separate non-mutating authorization prefetch may run while normal Auto is on, but must never call `StopAuto`, toggle AutoDX, clear targets, or mutate the queue. |
| PTT edge | `Main_Ms::SetRigTxRx(true)` keys the configured rig and upstream Auto continues across FT8 periods. | Added a permit check only when Auto or AutoDX is active. On expiry it calls `StopAuto`, disables AutoDX, stops TX, and unkeys. Permit is a reusable frequency/time flag valid for 30 seconds. | First FT8 burst succeeded, but the next same-period attempt occurred at/after 30-second expiry and forcibly stopped Auto. Direct/manual/Test PTT paths with both flags false remained ungated. | Put a single-use authorization check at the universal `HvRigControl::SetPtt(true, ...)` boundary. Reject only that rising edge when no permit exists; do not stop upstream Auto or AutoDX. Renew during RX so the next upstream slot proceeds normally. |
| One-burst sequence | Once Auto is on, upstream retries on the selected FT8 parity until its normal QSO/watchdog logic stops it. | Manual Auto receives one 30-second approval and has no renewal path. | Exactly one approximately 10.2-second burst, then no second same-parity burst. | Use a new single-use permit for each PTT edge, prefetched after unkey/while receiving. Expiry must skip a slot, not disarm the upstream sequence. |
| AutoDX band QSY | AutoDX stops Auto/clears the old queue, requests the band, waits 250 ms for Qt/CAT dispatch, then calls `onBandChangeComplete`. Desired AutoDX state remains enabled. | Added prepare/final station checks, but calls `m_autoDxerCore->setEnabled(false)` on a transient timeout/rejection and calls `StopAuto()` in integration code. | A transient station or CAT delay turns off effective AutoDX while the checkbox/persisted preference may disagree. | Keep prepare-before-QSY and final-after-readback as additive safety checks, but on failure cancel only the attempted route/target, report the reason, and return to upstream Listening. Never persist or mutate the operator's AutoDX preference. |
| External CAT frequency observation | Upstream forwards the observed dial frequency to AutoDX. | `ObserveRigFrequency` calls `StopAuto()` and invalidates authorization on unexpected changes. | Normal CAT updates can disrupt upstream Auto state. | Invalidate only the station permit on a route mismatch. Preserve upstream Auto state; the next PTT fails closed until a matching permit is acquired. |
| Backend two-phase contract | Not present upstream. | New prepare/final endpoint accepts any valid final request and does not correlate it with prepare. Native manual Auto calls final-only. | The advertised two-phase interlock is not enforced. | Issue an opaque prepare nonce and require it once at final; bind it to provider, managed process identity, bridge client, exact frequency/band/mode/route, and expiry. Reject replay/mismatch/stale final requests. |
| Empty AutoDX queue | Upstream stays `Listening`, leaves target empty, and does not transmit until an eligible target exists. | No causal OM0RX change established. | Operator interpreted the quiet state as a failure. | Preserve upstream behavior. Improve telemetry/documentation only; do not alter chase eligibility or synthesize targets. |
| Startup defaults | Upstream defaults AutoDX Enabled and US-only to true when keys are absent. | OM0RX packaging defaults both to false and supplies explicit operator settings. | Intentional integration safety difference, not the burst regression. | Retain fail-safe missing-config default false and explicit stored preferences; do not change an existing operator value. |

## Incident mapping

- The selected call and audio frequency (`GB26WTC`, 237 Hz) prove the upstream
  decode-list selection path ran.
- The full station-readiness probe sequence immediately before PTT indicates
  the successful burst did not bypass the station endpoint.
- The 30-second OM0RX approval window and the absence of manual renewal explain
  why upstream Auto produced only one period.
- The lack of button feedback was introduced by the asynchronous code added to
  upstream `auto_on()`.
- The conditional PTT check is still a separate P0: upstream Test PTT and any
  direct/manual path with Auto and AutoDX both false can bypass it.

## Minimal implementation boundary

1. Restore upstream `HvTxW::auto_on`, `StartAuto`, and `StopAuto` observable
   behavior; explicit Stop additionally invalidates only the integration permit.
2. Remove all periodic calls that stop/restart Auto or disable AutoDX.
3. Keep station route preparation around AutoDX QSY, but make failure cancel the
   attempted route only and leave upstream desired state intact.
4. Add a correlated backend prepare/final transaction.
5. Prefetch one single-use PTT permit while upstream is receiving and whenever
   upstream Auto becomes active or a prior PTT ends.
6. Consume the permit only at the universal rig PTT-on boundary. Without one,
   reject that edge and preserve upstream Auto/AutoDX/queue state so a later
   slot can proceed after authorization succeeds.
7. Invalidate permits on route/process/client/frequency changes and emergency
   halt, without changing upstream control-flow state.
8. Add structured audit events without changing button labels or original
   interaction semantics.

No live MSHV or RF test is permitted until the minimal patch is independently
reviewed, cleanly rebuilt from the pinned source, attested, and then separately
authorized for deployment.

## Implemented remediation (pending independent review)

- `auto_on()` and `StartAuto()` once again update the original UI/core state
  synchronously. Decode-list handlers and upstream AutoDX queue/eligibility code
  are unchanged.
- The provider timer performs telemetry and non-mutating RX permit prefetch only.
- Transient station/CAT rejection does not call `StopAuto()` or persist
  `AutoDX Enabled=false`; the affected route remains TX-inhibited.
- Prepare/final uses a one-time bound nonce. Final issues a one-use PTT permit.
- `HvRigControl::SetPtt_p(true, ...)`, the shared CAT/RTS/DTR boundary, obtains
  the backend's bounded authoritative atomic consume result before every actual
  rising edge. Rejection, revocation, drift or timeout returns before hardware
  output without changing upstream Auto/AutoDX/target/queue state.
- Explicit Stop/Halt/QSY invalidates authorization. Generation-aware requests
  prevent an old in-flight reply from overwriting a newer route request.
- Differential contracts A-H and native fake-backend tests cover synchronous UI
  behavior, non-destructive renewal/failure, exact two-phase correlation,
  single-use permits, a 7.2-second accessory response, and three consecutive
  permit-consumption cycles (without claiming an end-to-end RF QSO test).
