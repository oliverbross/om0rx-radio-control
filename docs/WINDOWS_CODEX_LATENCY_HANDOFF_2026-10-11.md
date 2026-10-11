# Windows station latency investigation and deployment

Status: source changes tested on macOS; Windows deployment and hardware timings pending.

## Findings and changes

- The Mac spot path previously always sent `set_receive_vfo`, `set_split`, then
  `set_frequency_mode`. Each can traverse the guarded remote route. xCat now
  omits the first two commands when A already owns RX/TX. Split/B exit still
  performs the required operations. This Mac change passes 57 Swift tests.
- The Python radio poll previously awaited full accessory route following.
  Serial verification/route preparation therefore suspended fresh radio
  observations. The follower now runs separately, at most once concurrently.
  No queue of obsolete targets is retained. Existing coordinator locks and
  route-generation/readback checks still govern all hardware operations.
- Shutdown waits for the active follower before stopping its devices.
- Command responses include `timing_ms` for command queue, execution and total.
  Coordinator logs include cumulative action-lock, radio-lock, receive proof,
  standby proof and radio-command stages. No credentials are logged.

The previously recorded 7.204 s transition is a historical baseline, not a
measurement of this new revision. A 12 s client timeout is not an optimization.

## Windows Codex instructions

1. Inspect both source and deployed controller checkouts. Preserve local work,
   agent configuration, commissioning, credentials, ports and band policies.
   Fetch branch `codex/latency-route-polling` from
   `oliverbross/om0rx-radio-control`. Review its diff from `90abbb4`.
2. Apply the runtime/coordinator changes and test additions to the canonical
   WindowsAgent equivalent if it still lives in the xCat migration checkout.
   Do not deploy the obsolete standalone source path accidentally. Report both
   source and deployed SHAs and the exact runtime path.
3. Run remote-agent, station-coordinator, station-policy, FLEX lifecycle,
   ownership and existing standalone WindowsAgent tests. Verify slow accessory
   following cannot block radio/MOX observations; route work remains serialized,
   superseded targets fail their normal checkpoints and shutdown awaits work.
4. Record baseline timings before replacement where practical. Restart only the
   established agent task, keeping a recoverable previous revision. Do not start
   a second controller. Check the configuration hash is unchanged.
5. Measure at least five receive-only transitions per category: same-band/same-
   mode; same-band/mode change; 40 m to 20 m and back; and split/B to a new simplex
   spot. Coordinate measurements with the operator's current activity. Never
   initiate PTT, TUNE-start or CWX for these tests.
6. For each transition record command receipt, command acknowledgement, first
   coherent RX/TX frequency/mode publication, and final confirmed KPA/KAT route.
   Report median/p95 separately for radio and accessory completion. Record the
   new `timing_ms` and `FLEX route timing` stages, not just total wall time.
7. Check no mixed frequency/mode is published, MOX/interlock stays live during
   accessory work, manual same-band RF power persists, allowed/prohibited amp
   bands remain respected, and no accessory routing occurs while transmitting.
   Exercise rapid successive targets and shutdown/restart during route work in
   offline tests before any hardware equivalent.
8. If radio confirmation still exceeds ~1 second on same-band simplex, use the
   stage timings to locate the remaining wait (lock queue, receive proof,
   standby readback or FLEX command). Inspect serial readback/poll contention and
   the FLEX snapshot command/response queue. Optimize the demonstrated wait;
   do not remove freshness checks or shorten verification deadlines blindly.
9. Record all timings, tests, residual failures, final state and deployment SHAs
   in this document and send the results back to the operator. Do not call point
   1 complete until a live before/after improvement has been demonstrated.

## Local evidence

- Focused Python agent/coordinator/policy/FLEX lifecycle suite: 149 passed.
- xCat Swift suite: 57 passed, including one-command simplex and split exit.
- Python correctness lint passed for the changed runtime/coordinator/tests.
- Broad macOS Python smoke run: 875 passed, 7 skipped, 5 failed, 2 errors.
  Failures include Windows `.exe`/PowerShell/.NET tooling, frontend route
  discovery, QSO store and Wavelog pagination checks. The broad suite is not
  green on this host; Windows must run its own complete gate. Those failures
  were not attributed to this change by a clean baseline comparison.
