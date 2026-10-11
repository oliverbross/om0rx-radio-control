# Windows station latency investigation and deployment

Status: completed on Windows; final receive-only deployment and hardware timings recorded below.

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

## Windows execution record

Completed 2026-10-11 on the station Windows 10 host. The requested source tip
was verified as `54fae3e49d86e94133402fe933732f03bcd6cf8c`. The active controller
was not the standalone source checkout: the scheduled task launches
`C:\Projects\OM0RX-xCat\WindowsAgent\scripts\run_remote_agent.ps1` with
`C:\Projects\OM0RX-xCat\WindowsAgent\.venv\Scripts\python.exe`. The tray uses
the same canonical checkout. The source follow-up implementation is
`a09c133e57983b8c69bf7d442ab2025a05ca7fa6`; the final canonical deployed
WindowsAgent revision is `0116560033f64df34a0ee435e9d7ed8bce76aeb6`.

The agent configuration SHA-256 remained
`FFA28083E47DFDDBEE7A047140B5F2F0C934E03A6CA689DD6D1CE95C3A54FB47` across
both controlled task restarts. No policy, commissioning, credential, port,
VSPE or Tailscale setting was changed. The bearer token was used only inside
the authenticated local probe and was never printed or logged.

Five receive-only samples were taken in each category. Values are wall-clock
median/p95 in milliseconds from client request start. `Publish` is the first
coherent WebSocket frequency/mode state; `route` is final KPA/KAT alignment.

| Transition | Baseline ACK | Final ACK | Baseline publish | Final publish | Baseline route | Final route |
|---|---:|---:|---:|---:|---:|---:|
| Same band, same mode | 925 / 1320 | 697 / 821 | 6957 / 7683 | 970 / 1242 | 6957 / 7683 | 970 / 1242 |
| Same band, mode change | 983 / 1079 | 707 / 926 | 6828 / 7475 | 1086 / 1174 | 6828 / 7475 | 1086 / 1174 |
| 40 m to/from 20 m | 1023 / 1442 | 754 / 879 | 7758 / 8011 | 1150 / 1381 | 7838 / 8201 | 8585 / 9406 |
| Split/B to simplex | 2079 / 2525 | 3053 / 3519 | 7740 / 8443 | 3544 / 3935 | 7740 / 8443 | 3544 / 3935 |

The decisive change is that accessory readback no longer suspends FLEX polling:
same-band coherent publication fell from 6.96 seconds median to 0.97 seconds,
and cross-band radio publication fell from 7.76 seconds to 1.15 seconds while
the independently serialized accessory route completed later. Cross-band
accessory completion remains variable at roughly 5.5-9.4 seconds. Split exit
still uses three guarded commands and sometimes waits behind the in-flight
accessory transaction, explaining its roughly 3.05-second ACK median; the
route transaction is intentionally not cancelled or bypassed.

Final cumulative coordinator stage medians/p95s for `set_frequency_mode` were:

| Transition | Receive proof | Standby proof | FLEX command complete |
|---|---:|---:|---:|
| Same band, same mode | 200 / 326 | 338 / 503 | 655 / 818 |
| Same band, mode change | 85 / 334 | 288 / 484 | 622 / 923 |
| Cross band | 84 / 128 | 202 / 372 | 692 / 842 |
| Split final tune component | 253 / 311 | 440 / 641 | 746 / 1017 |

Command response `timing_ms` showed negligible queue time in the usual case,
with occasional 68-182 ms contention. The remaining same-band work is the
required fresh receive proof, exact standby readback, matching SmartSDR command
responses and coherent status publication. Holding the FLEX socket lock across
the coherent mode/tune/refresh sequence and skipping an already-matching mode
removed poll contention. A diagnostic attempt to omit the immediate slice
subscription refresh produced 50-51 second publication delays on this radio,
matching its periodic 60-second refresh boundary; that attempt was reverted.

No mixed frequency/mode pair was published in the final 20 samples. The 17 m
same-band series preserved 70 W drive throughout. The 40 m/20 m transitions
applied their configured 98 W/65 W barefoot policies only after band changes.
The prohibited 17 m amplifier route remained in standby. Route work stayed
serialized, superseded-target and shutdown-waits-for-in-flight-work regression
tests passed, and the native widget smoke test passed.

Final tests: 891 Python smoke tests passed; 213 canonical WindowsAgent tests
passed; 105 browser/widget contract tests passed; 105 MSHV offline safety tests
passed; focused source remote-agent/FLEX/coordinator tests passed 147; focused
canonical equivalents passed 134. Syntax/import, Ruff correctness, duplicate
route, PowerShell parser, JavaScript syntax, old-reference and whitespace gates
also passed.

Final live state was restored to 18.082500 MHz CW on 17 m with FLEX known and
fresh, MOX false, interlock READY, KPA500 standby at 0 W, KPA/KAT both on 17 m,
KAT antenna 1, recovery not required and zero alarms. No PTT, TUNE-start or CWX
command was sent and no RF was transmitted.
