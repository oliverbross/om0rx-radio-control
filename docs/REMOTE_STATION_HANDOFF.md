# Remote Station Cross-Machine Handoff

This file is the shared coordination record for Codex work on the Windows
OM0RX Remote Station Agent and the macOS OM0RX-xCat client. Update it whenever
either machine changes code, configuration, or acceptance status, then commit
and push the update so the other machine can work from the same evidence.

Do not place bearer tokens, passwords, private keys, complete environment
dumps, or other credentials in this file, commits, terminal output, or issue
text.

## Safety boundary

Until physical commissioning is explicitly completed:

- Keep `station.commissioned` set to `false`.
- Keep the KPA500 in standby.
- Do not transmit RF.
- Do not send PTT, TUNE, CWX, OPERATE, RF-power, frequency, mode, antenna,
  split, RIT, or XIT writes.
- Do not suppress or cosmetically hide alarms. Resolve their source and retain
  fail-closed behavior.
- Stop and request an operator action if diagnosis requires changing a radio,
  amplifier, tuner, antenna, or station-control setting.

## Repository checkpoints

- Windows agent repository: `oliverbross/om0rx-radio-control`
- Windows agent baseline containing the remote agent: `12dc060`
- macOS client repository: `oliverbross/OM0RX-xCat`
- Tested macOS client baseline: `263cbd00c10e41dbe7d83d9485f4879af7ed30de`
- macOS installed application: OM0RX-xCat 0.3.0 build 3

Before starting work, fetch the relevant repository, confirm the exact branch
and SHA, and preserve unrelated working-tree changes. Code fixes must use a
`codex/` branch unless the operator explicitly directs otherwise.

## Station topology

- FLEX-8400 controlled by the Windows Remote Station Agent.
- KPA500 uses VSPE `COM17` at 38,400 baud.
- KAT500 uses VSPE `COM15` at 38,400 baud.
- Do not change the existing VSPE port arrangement.
- The agent is published privately with Tailscale Serve at
  `https://om0rx-win10.tail5abcc0.ts.net`.
- OM0RX-xCat exposes receive-only CAT to RUMlogNG at `127.0.0.1:15002`.
- RUMlogNG uses Kenwood TS-480 compatibility over TCP with Follow TRX enabled.

## macOS acceptance evidence — 2026-10-10

The macOS installation and receive-only data path are working:

- macOS 27.0.1 on Apple silicon satisfies the macOS 14 minimum.
- Tailscale shows the Mac and `om0rx-win10` online in the same tailnet.
- OM0RX-xCat authenticated successfully and connected its WebSocket state
  stream to the Windows agent.
- The `Allow CAT transmit and CW commands` switch is off.
- Automatic protocol-server startup is intentionally off during commissioning.
- OM0RX-xCat listens on `127.0.0.1:15002` and `127.0.0.1:14532`.
- RUMlogNG has an established TCP connection to port 15002.
- RUMlogNG and OM0RX-xCat both displayed approximately 21.0479 MHz CW during
  validation, proving the read-only CAT path.
- KPA500 was readable and remained `STBY`.
- KAT500 was readable as `ANT1`.
- No RF transmission or prohibited station-control write was performed.
- The complete OM0RX-xCat Swift suite passed: 26 tests, 0 failures, 6 suites.

## Windows-side blockers reported by macOS

OM0RX-xCat currently reports `ALARM 2` and will not accept the station as
healthy:

1. `FLEX reports INVALID`
2. `policy expects ANT1 on 15m`

The same state summary shows `Route 15m KAT ANT1`. The Windows investigation
must therefore inspect the FLEX antenna/port field and the KAT output field
independently rather than treating that route summary as proof that both are
valid. The station must remain uncommissioned while either route warning
exists. The Windows investigation below established that the two displayed
lines are the two halves of one warning message; the other counted item was
the intentional informational commissioning lock.

## Windows investigation checklist

1. Read `AGENTS.md` when present, `README.md`,
   `docs/REMOTE_STATION_AGENT.md`, and
   `docs/REMOTE_STATION_PROTOCOL_V1.md` completely.
2. Record the branch, SHA, working-tree state, installed version, service/task
   status, and redacted configuration.
3. Back up the non-secret configuration before changing it.
4. Confirm Tailscale Serve, HTTPS, the authenticated WebSocket stream, COM17,
   and COM15 are healthy.
5. Capture receive-only FLEX state: radio identity, GUI station binding,
   active and TX slices, frequency, mode, RX/TX antenna fields, interlock, and
   PTT state.
6. Trace the exact source of `FLEX reports INVALID`. Determine whether it is a
   genuine radio state, missing or stale telemetry, a Maestro binding problem,
   a parser defect, or an incorrect normalization rule.
7. Inspect the 15m band policy and compare the configured FLEX antenna, live
   FLEX antenna, configured KAT output, and live KAT output as four distinct
   values.
8. Apply only a configuration or software correction that requires no
   prohibited station-control write.
9. For a code defect, add regression coverage, run the complete maintained
   test suite, commit on a `codex/` branch, and push the branch.
10. Revalidate that FLEX is connected and bound correctly, KPA is `STBY`, KAT
    is readable, the route is truthfully confirmed, warning/critical alarm
    counts are zero, the expected commissioning information remains visible,
    and `commissioned` remains `false`.

## Windows findings and test record

Do not delete the macOS evidence or safety boundary.

- Timestamp (UTC): `2026-10-10T08:26:26.1537265Z` final live readback.
- Operator-visible Windows agent version: FastAPI application `1.0.0`,
  protocol `v1`; running scheduled agent was installed from clean branch
  `codex/windows-agent-install` at
  `8561c3b50b7e3e819b7aafcf85e901daf0151835`.
- Repository branch and SHA: fix branch
  `codex/fix-flex-route-validation`, based exactly on fetched `origin/main`
  `12fa0e6bf96853ae58b5dc7a78be696bf5990f54`; implementation commit
  `e6a9fe3ac39a4bc4d8011d8c961b6e8439489dad`. The exact pushed branch tip is
  reported to the operator because a commit cannot contain its own SHA.
- Initial service/task state: `OM0RX Remote Station Agent` was `Running`, last
  task result `0x41301` (still running), with no agent error. The agent was
  bound to `Maestro`, fresh, receive-only, and uncommissioned. The tray task
  did not exist initially.
- Root cause of `FLEX reports INVALID`: FLEX slice telemetry truthfully showed
  the bound transmit slice on `ANT1`, but a later generic transmit/interlock
  status line reported `tx_antenna=INVALID` and overwrote the driver's
  aggregate `current_tx_ant`. The runtime already selected the authoritative
  transmit slice for frequency and mode but passed only the unusable aggregate
  antenna value to station-path validation. The log reproduced alternating
  `INVALID -> ANT1` and `ANT1 -> INVALID` transitions through
  `2026-10-10 10:15:02` local time.
- Root cause of `policy expects ANT1 on 15m`: this was not a second physical or
  KAT500 fault. It is the second half of the single
  `flex-tx-port-mismatch` message, `FLEX reports INVALID; policy expects ANT1
  on 15m`. The second item in `ALARM 2` was the intentional informational
  `station-commissioning-required` alarm. Live policy values were independently
  confirmed as FLEX `ANT1` and KAT output `1`; KAT live readback was also
  `ANT1` on `15m`.
- Configuration changes: none. Read-only redacted verification confirmed
  loopback `127.0.0.1:8840`, FLEX station `Maestro`, COM17/COM15 at 38,400,
  15m FLEX policy `ANT1`, 15m KAT policy `1`, and
  `station.commissioned=false`. No token value was printed or committed, so no
  configuration backup was required.
- Code changes and branch: on `codex/fix-flex-route-validation`, the runtime
  now preserves canonical `rx_ant`/`tx_ant` fields and, only when the aggregate
  TX antenna is unusable, uses the bound transmit slice's valid
  `ANT1`/`ANT2`/`XVTR` readback. A different valid aggregate value remains
  visible and still fails closed. The branch also adds an interactive Windows
  tray controller with sanitized status, confirmed start/stop/restart task
  controls, log access, and tray-only quit. The installed tray task is
  `Running` in interactive session 1; no agent lifecycle control was exercised
  during this test. The existing agent task definition now points to this fix
  worktree for its next start, while the already-running process was left
  undisturbed on its recorded installed SHA.
- Tests run with exact pass/fail counts: final complete safe smoke suite
  `835 passed, 0 failed`; Node browser/widget contracts `105 passed, 0 failed`;
  focused remote-agent/tray subset `22 passed, 0 failed`; PowerShell parser
  `9 passed, 0 failed`; Ruff `F,E9` checks, Python compile, and Git whitespace
  checks passed. Preliminary isolated-worktree runs exposed missing local test
  dependencies/configuration (`12`, then `2`, then `1` failures); after using
  the normal project Python, ignored local test configuration, existing Node
  dependencies, and vendored decoder, the complete suite passed as above.
- Final FLEX state: connected, known, fresh, bound to `Maestro`, `21.04756 MHz`
  CW, active/TX slice `A`, RX `ANT1`, TX `ANT1`, MOX `false`, interlock
  `READY`.
- Final KPA500 state: connected, `15m`, `operate=false` (`STBY`).
- Final KAT500 state: connected, `15m`, antenna output `1` (`ANT1`).
- Final route and alarm state: route `confirmed`, zero mismatches, zero
  critical alarms, zero warning alarms, and one expected info alarm
  (`station-commissioning-required`). HTTPS returned 200, authenticated WSS
  returned a protocol-v1 state message, and Tailscale Serve 1.102.3 still maps
  the tailnet-only hostname to loopback port 8840.
- Final `commissioned` value: `false`.
- Confirmation that no RF or prohibited write occurred: confirmed. All station
  validation used authenticated GET/WSS reads, log inspection, or offline
  replay. MOX remained false and KPA remained in standby. Only the independent
  tray task was installed/started; the station-agent task was not stopped,
  started, or restarted.
- Remaining operator action: fetch the pushed branch/SHA on the Mac and repeat
  receive-only acceptance. The Windows agent task is prepared to load this
  branch at the next operator-approved maintenance restart; do not restart it
  merely for this handoff while the strict no-station-write boundary is in
  force.

## macOS receive-only acceptance — 2026-10-10

- Timestamp (UTC): `2026-10-10T09:46:33Z` final observation.
- Windows fix source verified: fetched
  `origin/codex/fix-flex-route-validation` at exactly
  `b6611064b11f8f5390c62bcdfa96d4958634b18e` before acceptance.
- Acceptance branch: `codex/mac-receive-only-acceptance`, created directly
  from that verified Windows branch tip.
- Authentication and stream: the already-running OM0RX-xCat process remained
  authenticated to `https://om0rx-win10.tail5abcc0.ts.net`; its activity view
  remained `Remote Station Agent connected`. The same process changed from
  the earlier `ALARM 2`/FLEX `INVALID` state to the current `ALARM 1` state,
  providing receive-only evidence that the authenticated WebSocket stream
  delivered the corrected live state without a client restart.
- FLEX state shown by OM0RX-xCat: VFO A `RX+TX`, approximately `21.048 MHz`,
  `CW`; VFO B inactive. The invalid FLEX route warning is absent.
- Raw-state correlation: the Windows authenticated state evidence above
  records the bound station as `Maestro`, active/transmit slice A, RX `ANT1`,
  TX `ANT1`, MOX `false`, and interlock `READY`. OM0RX-xCat 0.3 summarizes
  these fields rather than rendering the station name, both antenna fields,
  MOX, and interlock separately; the Mac acceptance therefore confirms their
  decoded route/alarm outcome, while the Windows record remains the direct
  raw-field evidence.
- KPA500: OM0RX-xCat displayed `KPA STBY` throughout acceptance.
- KAT500: OM0RX-xCat displayed `KAT ANT1` throughout acceptance.
- Route: OM0RX-xCat displayed `Route 15m KAT ANT1`; the former FLEX
  `INVALID`/ANT1 policy mismatch is absent.
- Alarms: OM0RX-xCat displayed exactly `ALARM 1` with only `Station not
  commissioned; Station control is locked pending commissioning`. Correlated
  with the protocol-v1 alarm record above, acceptance is zero critical, zero
  warning, and exactly one informational
  `station-commissioning-required` alarm.
- Safety controls: `Allow CAT transmit and CW commands` remained off;
  automatic protocol-server startup remained off; Operate, Tune, and Cancel
  remained disabled. `commissioned=false` was not changed.
- Local consumers: OM0RX-xCat continued listening on `127.0.0.1:15002` and
  `127.0.0.1:14532`; RUMlogNG retained an established TCP connection to the
  CAT listener on port 15002.
- Credential boundary: a separate command-line state read was abandoned when
  macOS Keychain correctly withheld the credential from the diagnostic
  process. The bearer credential was not returned, printed, logged, copied,
  or committed; acceptance used the application's existing authenticated
  connection.
- Prohibited actions: no command endpoint request, CAT write, PTT, TUNE, CWX,
  frequency/mode/antenna change, RIT/XIT change, RF-power change, station
  action, application stop/restart, or other station-control write was
  performed.
- Result: **PASS for receive-only OM0RX-xCat acceptance**. This is not station
  commissioning or transmit authorization; the intentional commissioning
  information alarm must remain until physical commissioning is separately
  completed.

## Windows full-agent GUI implementation — 2026-10-10

- Branch: `codex/windows-agent-gui`, based on `main` at
  `ad1b0b7b36c7b1dc0284914fc5a84e45cf9e808f`. The exact pushed tip is
  reported to the operator after the commit because a commit cannot contain
  its own SHA.
- The remote-station tray now provides a complete local Settings window; the
  operator no longer needs PowerShell or direct JSON editing for routine
  configuration. It covers loopback server settings and masked token handling,
  FLEX connection/binding and antenna enforcement, KPA500/KAT500 enable and
  serial settings, per-band FLEX/KAT/PA/barefoot/digital policy, tuner limits,
  route-follow behavior, digital amplifier policy, and commissioning.
- Candidate settings are validated through the real Python configuration
  loader before an atomic replacement. The previous profile is retained as
  `agent.json.bak`. Save does not restart; Save-and-restart requires separate
  confirmation. Enabling commissioning requires typing `COMMISSION` and also
  requires KPA500, KAT500, follow-radio, and FLEX antenna enforcement to remain
  enabled.
- The tray details window and context menu now expose coordinator-backed
  Standby, Operate, Tune, and Cancel controls. Buttons follow the running
  coordinator's `allowed_actions`; Operate and Tune require confirmation.
  There is no raw local PTT button, and no guard or alarm is bypassed.
- The agent profile now supports explicit `kpa500.enabled`, `kat500.enabled`,
  `station.follow_radio`, and `station.digital_kpa_policy` settings while
  remaining backward-compatible with the existing JSON profile.
- Tests: complete Python smoke suite `843 passed, 0 failed`; Node UI/contract
  suite `105 passed, 0 failed`; focused remote-agent/tray suite `30 passed, 0
  failed`; settings WinForms load/build/validate/atomic-save smoke `1 passed, 0
  failed`; PowerShell parser `3 passed, 0 failed`; Ruff `F,E9`, Python compile,
  and Git whitespace checks passed. The maintained smoke suite was made
  independent of the operator-owned full-app follow-radio setting; no live
  configuration was changed by the tests.
- Read-only live check at `2026-10-10T10:42:46Z`: the station agent and tray
  tasks remained running; FLEX was connected and bound, MOX was false,
  interlock was `READY`, KPA500 was connected in STBY, and KAT500 was connected
  on ANT1. `station.commissioned` remained `false`.
- The read-only check also recorded a current receive-only route warning: FLEX
  had been moved to 20m while KPA500/KAT500 still reported 15m. This is not the
  former FLEX `INVALID` defect. Automatic accessory route following is
  intentionally inactive while uncommissioned; the GUI exposes the guarded
  commissioning workflow, and a commissioned restart/follow transaction must
  align and verify the hardware before transmit is authorized.
- Final read-only check at `2026-10-10T10:44:37Z`: FLEX was again on 15m with
  ANT1, the KPA500/KAT500 remained on 15m, the route was `confirmed`, and alarm
  counts were zero critical, zero warning, and one expected commissioning
  information item. This state change was observed only; this session sent no
  command to produce it. MOX remained false and the KPA500 remained in STBY.
- Safety confirmation: no agent restart, station-control request, CAT write,
  PTT, TUNE, CWX, frequency/mode/antenna/RF-power write, or RF transmission was
  performed during implementation or testing. The bearer token was neither
  printed nor committed.
- Post-push Windows installation: only the independent `OM0RX Remote Station
  Tray` task was stopped, re-registered from this branch, and started so the
  Settings GUI is available immediately. The `OM0RX Remote Station Agent`
  process ID and creation time were unchanged across that operation. Its
  scheduled-task definition was then updated, without restarting the running
  process, to load this branch and the existing dedicated virtual environment
  on its next deliberate restart. Therefore **Save and restart agent** in the
  GUI will load the complete new configuration model. No station action was
  invoked.

## Windows transmit enablement — 2026-10-10

- At the operator's explicit instruction, `station.commissioned` was changed
  from `false` to `true`. The complete candidate configuration passed the real
  agent validator before atomic replacement; the prior credential-bearing
  configuration was retained only in the local AppData backup and was not
  printed or committed.
- The `OM0RX Remote Station Agent` task was deliberately restarted once so the
  commissioning change and `codex/windows-agent-gui` runtime took effect.
- Final authenticated readback at `2026-10-10T10:52:34Z`: commissioned `true`,
  coordinator `safe_rx`, recovery not required, route `confirmed`, no issues,
  zero alarms, FLEX bound on 20m CW with ANT1, MOX `false`, interlock `READY`,
  KPA500 connected in STBY on 20m, and KAT500 connected on 20m ANT1.
- The active 20m policy is barefoot: amplifier eligibility `false`, configured
  active drive 65 W, and FLEX readback 65 W. Therefore KPA Operate is correctly
  unavailable on this band, while the authenticated PTT/CW command path is
  commissioned and available through the coordinator. Other bands continue to
  use their configured PA eligibility and drive tables.
- No PTT-on, TUNE, CWX, or RF transmission was issued as part of enablement.
  Startup performed its designed receive/standby recovery and automatic route
  synchronization before the final state was accepted.

## Windows console-free settings and station widget — 2026-10-10

- Settings now launches from the tray with the PowerShell host window hidden,
  leaving only the normal Windows settings form visible.
- A compact station widget starts with the tray and can be reopened with
  **Show station widget**. It is movable, resizable, always-on-top by default,
  and persists position, size, and topmost preference locally without storing
  credentials.
- The read-only widget displays FLEX frequency/mode/RX-TX/interlock, VFO A/B,
  RF drive and route; KPA500 state/band/measured output/SWR/temperature/voltage/
  current/fault/firmware; KAT500 mode/band/antenna/tuning/SWR/forward-reflected
  ADC/bypass/key-interrupt/fault/firmware; alarms and commissioning.
- Transmit telemetry is labelled according to its authority: KPA500 output is
  shown as measured watts when the amplifier is operating; barefoot operation
  shows the FLEX requested power as `~N W SET`, never as a fabricated measured
  antenna output. SWR is marked `LIVE` only for a live or valid hardware sample
  and `LAST` otherwise.
- Validation: complete Python smoke suite `846 passed, 0 failed`; focused
  remote-agent/tray suite `33 passed, 0 failed`; PowerShell parser `4 passed, 0
  failed`; station-widget WinForms transmit-telemetry smoke `1 passed, 0
  failed`; Ruff `F,E9`, Python compile, and Git whitespace checks passed.
- Implementation and offline validation issued no station-control command,
  PTT, TUNE, CWX, or RF transmission and did not restart the commissioned
  station agent.
- Windows installation at `2026-10-10T11:02:03Z`: only the tray task was
  restarted. The station-agent process ID and creation time were unchanged.
  The widget process launched with a hidden PowerShell host, exposed a visible
  responding `OM0RX Station Monitor` window, and the tray and agent tasks both
  remained running. Final readback remained commissioned `true`, coordinator
  `safe_rx`, route `confirmed`, zero alarms, MOX `false`, interlock `READY`, and
  KPA500 STBY. No station-control write or RF transmission occurred.

## Windows exclusive controller ownership — 2026-10-11

The operator confirmed that the legacy **OM0RX Radio Control Agent** and the
newer **OM0RX Remote Station Agent** were running concurrently on Windows.
Stopping the legacy agent immediately resolved the Maestro interlock errors,
conflicting station-route state, and RUMlogNG/OM0RX-xCat spot-frequency
failures. This supersedes the earlier receive-route-interlock theory; no
interlock relaxation is requested or justified by this incident.

The legacy .NET agent currently prevents only another copy of itself with the
mutex `OM0RX.RadioControl.Agent`. The Python remote station agent does not
participate in that mutex, so the two controller families can still collide.
They require one shared Windows-wide controller-ownership mutex plus clear
startup migration and conflict diagnostics. The remote tray and station widget
are allowed control surfaces and must not be classified as competing station
controllers.

The complete corrected Windows prompt, safety constraints, regression matrix,
and acceptance procedure are in
[`WINDOWS_CODEX_EXCLUSIVE_CONTROLLER_HANDOFF_2026-10-11.md`](WINDOWS_CODEX_EXCLUSIVE_CONTROLLER_HANDOFF_2026-10-11.md).

### Offline implementation and pre-deployment evidence

- Starting point was verified exactly as
  `e6f78bd4401617d615d3ff3a0c46a2aa84d12c05` on
  `codex/remote-agent-flex-spots`; the working tree was clean before editing.
- Live inventory found the Python Remote Station Agent task, remote tray, and
  widget running. The old legacy `Om0rxAgent.exe` UI also remained open from
  Explorer, although its supervised backend had already been stopped and no
  listener remained on 8080/8091/8092. The FLEX TCP owners were SmartSDR DAX,
  SmartSDR CAT, and the Python remote agent. The legacy HKCU Run value was
  absent; the remote controller and allowed tray scheduled tasks were present.
- Both controller families now acquire the same Windows kernel mutex,
  `Global\OM0RX.StationController`, before the Python runtime or legacy
  supervisor can open/start station resources. Conflict exit code 73 is
  distinct and actionable. The named mutex is authoritative; a small atomic
  `%LOCALAPPDATA%\OM0RX\station-controller-owner.json` record contains only
  controller family, PID, executable path, UTC start time, and launch source.
  Stale metadata never blocks ownership, and abandoned mutex recovery is
  reported without bypassing normal startup safety validation.
- The remote tray and widget do not acquire controller ownership. The tray
  reads the sanitized owner record only when the agent API is unavailable.
  Scheduled-task conflict exit 73 is absorbed by the launcher after one log
  entry so Task Scheduler does not repeat the failure five times.
- The remote installer refuses a dual-startup configuration unless the
  operator explicitly supplies `-DisableLegacyStartup`; that switch backs up
  and removes only the legacy HKCU Run value. A separate restore script refuses
  to restore it while the remote controller task is enabled. The legacy
  installer and GUI startup toggle likewise refuse while the remote controller
  task is enabled. Shortcuts, settings, application data, and the allowed
  remote tray task are retained.
- Cross-language regression coverage proves legacy-first refusal,
  Python-first refusal, duplicate-family refusal, clean release, abandoned
  recovery, stale-metadata tolerance, exactly-one-winner launch races,
  tray/widget non-ownership, startup migration detection, and scheduled-task
  retry suppression. Focused controller/remote-agent/tray tests passed 58 with
  one dependency deprecation warning and zero failures. Both .NET controller
  projects built with zero warnings and zero errors; the active legacy binary
  was not stopped for offline compilation, so its build was directed to an
  isolated temporary output.
- The complete maintained gate passed: 876 Python smoke tests, 105 browser and
  widget tests, and 105 MSHV offline safety tests. Python compile, Ruff, backend
  import, duplicate-route scan, PowerShell/JavaScript syntax, old-reference
  scan, and Git whitespace checks all passed.
- Pre-deployment live state remained receive-safe: FLEX connected, known,
  fresh, and Maestro-bound; MOX false; interlock READY; KPA500 in standby at
  0 W; KAT500 readable; route confirmed; zero alarms; recovery not required.
  No controller was stopped before the operator explicitly authorized the
  replacement, and no PTT, TUNE, CWX, Operate, or RF command was issued.

### Authorized live replacement and refusal acceptance

- Oliver explicitly authorized stopping and replacing the old controller
  processes. The inactive legacy UI process PID 6968 was identity-checked,
  stopped, and replaced with the guarded Release build. Its supervised backend
  already had zero listeners on 8080/8091/8092; no legacy station process was
  stopped by this step.
- The Python Remote Station Agent was then restarted once through its existing
  scheduled task to deploy exact code commit
  `4b4e25faf06d2d3797b1539d775de26e2bff3209`. The task action now identifies
  its launch source as `scheduled-task`. The old station-agent PID 11748 was
  replaced by PID 7928; the owner record reports
  `python-remote-station-agent`, PID 7928, and `scheduled-task`, exactly matching
  the 8840 listener. The credential-bearing configuration SHA-256 remained
  `568A7355581A7E60F3882641B5C253D73DBB4E9DDDA46189F940114987868B3A`.
- The rebuilt real legacy `Om0rxAgent.exe` was launched once with its normal
  project/port arguments plus non-interactive acceptance mode. It exited with
  the required code 73 before creating a legacy process, backend listener, or
  supervisor. Exactly one sanitized conflict was written to the existing
  legacy log. The Python PID, process start time, owner family, and owner PID
  were unchanged across the refusal.
- After the refusal, the only established FLEX TCP owners were SmartSDR DAX,
  SmartSDR CAT, and Python PID 7928. The remote tray and widget each remained a
  single running instance. Port 8840 retained three established client
  connections. A separate authenticated read-only WebSocket observation ran
  continuously for 16.0 seconds and received 41 state messages without a
  disconnect or unsafe state.
- Final station evidence: FLEX connected, known, fresh, and Maestro-bound on
  7.058600 MHz; MOX false; interlock READY; KPA500 standby on 40 m at 0 W;
  KAT500 readable on 40 m ANT2; route confirmed; zero alarms; recovery not
  required. The Windows side cannot inspect RUMlogNG's local Mac CAT socket,
  so the retained authenticated client connections are Windows-side continuity
  evidence; Mac may independently confirm its CAT readback without a write.
- The legacy HKCU Run entry remains absent. The remote controller and allowed
  tray tasks are both running. No PTT-on, TUNE, CWX, Operate, frequency/mode/
  antenna write, or RF transmission was issued. The controlled restart used
  only the agent's existing receive/standby startup recovery.

## Handoff protocol

After each bounded change:

1. Pull or fetch before editing and resolve divergence without overwriting the
   other machine's work.
2. Add a dated evidence entry or update the Windows findings above.
3. Never commit generated credentials or local configuration containing the
   bearer token.
4. Commit and push the code plus this handoff record together.
5. Report the pushed branch and exact SHA to the operator. The other machine
   should fetch that SHA before continuing acceptance work.
