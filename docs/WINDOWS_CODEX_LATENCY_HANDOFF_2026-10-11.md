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

## Phase 2: combined split exit and accessory stage profiling

Status: implemented locally; Windows deployment and hardware measurements pending.

Local phase-2 validation: 157 focused Python tests passed (agent, coordinator,
policy and FLEX lifecycle); 58 Swift tests passed; correctness lint and diff
checks passed; signed macOS release packaging passed. These are not Windows
deployment or physical latency acceptance results.

- New advertised command `tune_simplex` takes `frequency_hz` and `mode` and
  always targets VFO A. It selects A RX/TX and applies frequency/mode inside one
  existing `execute_flex_route_change` guard/socket lock, retaining the immediate
  `sub slice all` refresh. This replaces three guarded requests for split exit.
- Publication waits for confirmed A RX/TX ownership plus coherent frequency/mode;
  MOX/interlock remain live. Rejected/partial commands invalidate the cached route
  until a new poll instead of leaving a permanently pending success target.
- xCat uses the advertised capability for split/B exit; older agents retain the
  existing fallback. Already-simplex A retains `set_frequency_mode`.
- `Accessory route timing` logs cumulative monotonic stage milliseconds through
  receive proof, standby proof, fault/key checks, FLEX port verification, KPA band,
  KAT band/frequency/antenna, drive, final readbacks and final status refresh.
  Subtract consecutive values to identify each stage's cost. Failed/cancelled
  routes also log completed stages and total. No safety readbacks were removed.

### Windows Codex follow-up

1. Fetch the latest `codex/latency-route-polling` source branch. Review phase-2
   changes after `d54cd94`; port runtime, coordinator and regression tests into
   the actual canonical `C:\Projects\OM0RX-xCat\WindowsAgent` checkout. Keep
   all unrelated work, policy, configuration, credentials and commissioning.
2. Run the full established Windows gate and confirm command capability
   advertisement. Include invalid targets, early command rejection, failed
   RX/TX ownership proof, live MOX during pending publication, and legacy tuning.
3. Deploy only the existing agent task with a recoverable previous revision.
   Record source/canonical SHAs and unchanged configuration hash. Do not start
   a second hardware owner or initiate PTT, TUNE-start, CWX or RF.
4. Measure at least five split/B-to-simplex transitions through `tune_simplex`
   against the previous 3544/3935 ms publish median/p95. Do not benchmark the old
   three-command sequence accidentally. Report ACK, coherent publish and route
   times separately. Verify A actually owns RX/TX, no mixed state and no stuck
   pending target after failure. Retest already-simplex mode changes.
5. Measure five 40m/20m round trips and capture `Accessory route timing` stage
   data. Identify the largest measured stage(s); inspect serial poll contention
   and redundant refreshes there. Optimize only demonstrated redundancy while
   retaining current receive proof, exact device readbacks, fault handling,
   superseded-target checks, allowed amp bands and manual power behavior.
6. Report before/after median/p95 for accessories separately from FLEX, failed
   tests, final safe state and all SHAs here. Mac end-to-end UI acceptance remains
   a separate gate after the Windows deployment.

### Windows Phase 2 completion

Completed receive-only on 2026-10-11. The requested source tip
`b5ab3dcbd0dbd5223fa281ab1c3c1187aafb4fe5` was verified before work began.
The Phase 2 port was deployed to the canonical
`C:\Projects\OM0RX-xCat\WindowsAgent` checkout, then the measured accessory
redundancy was fixed in source commit
`f66e1adcd9019800f6b07ce2bf04925cc4937fb0` and canonical/deployed commit
`2fc10430281424a99802b82c4601e34e9113a441`. Only the existing
`OM0RX Remote Station Agent` scheduled task was restarted; the tray task stayed
running. The `agent.json` SHA-256 remained
`FFA28083E47DFDDBEE7A047140B5F2F0C934E03A6CA689DD6D1CE95C3A54FB47`.

Five actual `tune_simplex` split/B exits improved from a fresh legacy baseline
of 3078.826/3469.631 ms ACK median/p95 and 3531.103/3777.569 ms coherent
publish median/p95 to 845.975/938.478 ms ACK and 1239.536/1347.753 ms publish.
All five selected A as both RX and TX, published no mixed frequency/mode pair,
and completed their already-aligned route with the coherent publication. Five
already-simplex mode changes measured 904.022/1200.501 ms ACK and
1259.344/1694.125 ms publish, also with zero mixed pairs. An invalid 1 Hz
`tune_simplex` returned HTTP 422, left no pending target, and the command remained
advertised.

For the five 40 m/20 m accessory transitions, the pre-optimization external
median/p95 was 730.957/913.926 ms ACK, 1159.855/1225.919 ms radio publication,
and 9062.024/9816.273 ms final route. The corresponding final values were
699.660/977.312 ms, 1089.963/1440.899 ms, and 9129.133/9857.364 ms. This last
end-to-end route result is statistically flat at five samples rather than a
claimed speedup. Stage logging identified mandatory final device readbacks as
the largest accessory-only stage (1638.7 ms baseline median, 1666.7 ms final)
and an immediately repeated full status refresh as demonstrated redundancy
(530.6 ms baseline median). Guarded route work now signals priority over
background status telemetry and atomically publishes the already-complete,
exact KPA/KAT readbacks. The redundant publication stage fell to 0.2 ms median;
coordinator-internal total fell from 7056.6/7564.0 ms median/p95 to
6990.3/7483.6 ms. Receive proofs, exact final device readbacks, fault/key checks,
superseded-target checks, amplifier-band policy, and manual-drive behavior were
not removed or relaxed.

Final validation passed: 899 source smoke tests, 221 canonical WindowsAgent
tests, 120 focused source coordinator/Elecraft tests, 102 focused canonical
tests, 105 browser/widget contracts, 105 MSHV offline safety tests, and the
native Windows widget smoke test. The complete maintenance gate also passed
syntax compilation, backend import, Ruff correctness, duplicate-route scan,
PowerShell parsing, JavaScript syntax, old-reference scan, and whitespace check.

Final live state was restored to 18.082500 MHz CW on 17 m: FLEX known/fresh,
MOX false, interlock READY, KPA500 standby at 0 W, KPA/KAT both on 17 m, KAT
antenna 1, recovery false, and zero alarms. HTTPS/WebSocket operation remained
healthy. No PTT, TUNE-start, CWX, amplifier OPERATE, or RF transmission occurred.

## Phase 3 closure handoff — 2026-10-12

Point 1 is not closed: final accessory readiness still measures about nine
seconds. Phase 2 proves a redundant refresh was removed, not that every remaining
wait is necessary. Preserve exact proofs; do not silently relabel this as done.

Mac follow-up (installed locally): bridge telemetry now uses the Remote Agent's
observed snapshot rather than optimistic pending-write display values. xLog
requires observed matching frequency/mode plus simplex A RX/TX before success;
older spot completions cannot overwrite a newer selection. The timer includes
main-thread scheduling, not just network task execution. 29 xLog and 58 xCat
tests passed; both signed releases packaged and installed. A receive-only live
band-map JJ0PKS selection from B RX/A TX split confirmed 18.082500 MHz CW simplex
A in 2629 ms from the recorded spot event (1755 ms from task start). Local
read-only telemetry took 16–43 ms. This one sample is not a p95 or an external
xCluster-launcher acceptance test. No QSO was saved, no transmit/tune/operate
command was issued. The selection exercised normal automatic rotor targeting.

Both RustDesk and AnyDesk time out while attaching from the Mac control tool.
Windows Codex must perform the remaining hardware investigation:

1. Start from source `169106d` and canonical `2fc1043`, then fetch this branch's
   latest documentation. Preserve configuration and the single agent owner.
2. Capture at least ten receive-only cross-band transitions, with per-stage,
   per-device/query and lock-wait timings. Separate waiting for a lock from
   time waiting for serial replies. Include the gap from radio publication to
   route-task start and internal finish to published route readiness.
3. Inspect repeated KPA/KAT complete readbacks, receive proofs, wake delays and
   serial framing for demonstrable duplicate or idle work. Reuse observations
   only within a justified unchanged transaction; keep fresh checks around
   hardware mutations and final exact readbacks. Do not decrease timeouts,
   suppress unknown states or bypass guards just to obtain faster numbers.
4. Implement the largest demonstrated safe improvement; run the existing full
   maintenance/WindowsAgent/safety gates, plus regression tests for the changed
   scheduling/query behavior. Deploy only the existing task and remeasure the
   same matrix, separately reporting ACK, coherent radio and accessory readiness.
5. Test rapid supersession, split exit and mode changes, preserving manual drive
   and amp-band policy. Receive-only: no PTT, TUNE-start, CWX or OPERATE.
6. If the remaining cost cannot be safely reduced, provide individual stage
   measurements and the precise protocol/physical constraint, not merely
   "mandatory readback". Document the accepted residual bound as a limitation;
   do not claim completion without evidence. Record deployed SHAs, unchanged
   config hash, final safe state and before/after median/p95 in this file.

Read-only Mac probes: `scripts/probe_xcat_latency.py` queries only loopback
telemetry; `scripts/probe_xlog_activity.swift` reads only persisted tune events.
Neither sends radio commands or accesses account credentials.

### Phase 3 Windows closure record — 2026-10-12

Windows fetched and verified requested tip
`91e0902d4555910e44fa2ba747d6975b5fb5022f` before making changes. The existing
configuration, VSPE ports, credentials, station policy, commissioning state and
single agent owner were preserved. Only the existing `OM0RX Remote Station
Agent` scheduled task was restarted; the tray remained running. The canonical
deployment is `C:\Projects\OM0RX-xCat\WindowsAgent`. Its final deployed commit
is `9897d86323551fa3fa09c79b94f351a38cdcf92d`; the corresponding source work is
on `codex/latency-route-polling`. The `agent.json` SHA-256 remained
`FFA28083E47DFDDBEE7A047140B5F2F0C934E03A6CA689DD6D1CE95C3A54FB47` before
and after both controlled restarts.

The ten-transition 40 m/20 m receive-only baseline and final matrix were run
with the same four alternating targets. Values below are median/p95 in ms:

| Measurement | Phase 3 baseline | Final |
| --- | ---: | ---: |
| command ACK | 862.156 / 1063.939 | 748.920 / 1019.513 |
| coherent radio publication | 1228.312 / 1458.990 | 1200.818 / 1393.100 |
| aligned accessory readiness | 8914.953 / 9851.177 | 7821.788 / 8525.914 |
| coordinator follower total | 7811.6 / 8483.6 | 6476.2 / 7454.1 |
| route-critical accessory preflight | 1248.0 / 1517.4 | 176.2 / 207.9 |
| final KPA/KAT/FLEX proofs | 1676.6 / 1690.6 | 1270.2 / 1294.1 |

The first safe reduction replaces the follower's repeated full accessory
telemetry sweep with exact route-only GETs: KPA OPERATE/band and KAT
antenna/band/frequency. It reuses the just-published FLEX observation only when
it is at most one second old, exact for frequency/TX antenna, confirmed RX with
READY/RECEIVE interlock, and the new KPA proof says STBY. OPERATE, incomplete,
old or mismatched evidence still forces the direct FLEX preflight. The second
reduction starts final FLEX proof concurrently with the manager-protected
KPA/KAT exact readbacks. No proof was removed: the transaction still performs
ordered RX checks around mutations, KPA standby proof, KAT fault and key-line
checks, exact FLEX port/drive proof, supersession checks and complete final
KPA/KAT/FLEX verification.

Per-query profiling over the final ten transitions found these total-time
median/p95 values in ms (query lock wait was 0.0 ms maximum unless noted):

- KPA500: `^ON` 18.0/50.8, `^OS` 15.6/50.8, `^BN` 15.6/51.0,
  `^FL` 15.5/50.8, `^TM` 15.7/50.6, `^VI` 15.6/50.5, `^WS`
  15.5/25.8 and `^RVM` 15.6/50.9.
- KAT500: `PS` 18.0/50.9, `MD` 15.6/50.7, `AN` 15.6/51.0, `BN`
  15.6/50.6, `F` 15.6/50.9, `VFWD` 15.3/15.8, `VRFL` 16.0/51.2,
  `VSWR` 15.3/51.4, `TP` 15.4/50.9, `FLT` 15.8/51.2, `BYP`
  15.4/50.5, `AMPI` 15.8/51.3 and `RV` 15.4/50.7. Only `AMPI` saw
  a device-lock wait, 50.2 ms maximum, when it met another KAT read.

Action and radio-lock waits were 0.0/0.0 ms median/p95. Manager-lock waits for
route setters and fault/key reads were 0.0 ms (0.1 ms worst p95); the final KAT
readback waited 90.2/140.1 ms behind the KPA readback by design. Radio
publication-to-scheduling was 0.6/0.7 ms and route-task schedule wait was
0.1/0.1 ms. Completion increments the stream revision synchronously; observed
finish-to-WebSocket availability was inside the stream's 250 ms cadence
(derived median about 62 ms, worst positive sample 238 ms).

The final coordinator stage deltas, median/p95 ms, were: RX proof 227.8/260.3;
standby proof 131.7/233.5; KAT fault 35.0/53.5; KAT key relay 52.1/102.5;
FLEX antenna command plus exact route proof 1048.8/1400.8; KPA band
378.9/418.0; KAT band 210.9/404.0; KAT frequency 244.9/403.8; KAT antenna
324.0/540.7; drive set plus post-write RX/route/drive proof 2474.2/2951.7;
and concurrent final proofs 1270.2/1294.1. Publication itself was 0.3/0.3 ms.

This is the accepted residual bound. Further material reduction would require
removing or reusing evidence across a hardware mutation: the approximately
1.05 s FLEX antenna proof, approximately 2.47 s drive command plus post-write
RX/route/drive proof, repeated receive barriers before each relay-setting write,
or the complete final device/radio proof. Doing so would weaken protection
against an external Maestro QSY, PTT/interlock transition, delayed relay change
or stale drive, so no timeout or safety proof was reduced.

Live follow-up also passed five combined split-B-to-simplex exits at
847.219/2933.099 ms ACK and 1211.168/3341.716 ms coherent publication, and five
same-band mode changes at 702.259/864.957 ms ACK and 1177.368/1263.568 ms
publication. All fifteen follow-up samples plus both ten-transition matrices
published zero mixed frequency/mode pairs. Rapid supersession, manual-drive
preservation and amplifier-band policy regression coverage passed offline.

Final gates on the final source commit passed: 904 Python smoke tests, 105
browser/widget tests, 105 MSHV safety tests and every maintenance syntax/import/
Ruff/duplicate-route/reference/whitespace check. The final canonical agent suite
passed 226 tests, the focused source coordinator/Elecraft gate passed 125 tests,
the focused canonical gate passed 107 tests, and the native Windows widget
smoke test passed.

The station was restored to 18.082500 MHz CW on 17 m with FLEX known/fresh,
MOX false, interlock READY, KPA500 STBY at 0 W, KPA/KAT both on 17 m, KAT
antenna 1, recovery false and zero alarms. No PTT, TUNE-start, CWX, OPERATE or RF
transmission occurred during Phase 3.
