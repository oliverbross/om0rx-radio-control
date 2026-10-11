# Windows Codex handoff — false 80 m amplifier-route rejection

## Objective

Correct the Windows Remote Station Agent so its active runtime uses the saved
per-band station policy. The live Mac client received
`amplifier-not-allowed: Amplifier operation is not allowed on this route` while
the radio was on 80 m and the authoritative Station configuration had
`80m amplifier allowed` enabled.

Do not weaken, skip, or force any safety interlock. The required result is no
false blocker on an aligned, allowed 80 m route, while genuinely disallowed or
mismatched routes remain blocked.

## Required starting point

1. Work in `oliverbross/om0rx-radio-control` on
   `codex/remote-agent-flex-spots`, not `main`.
2. Fetch and fast-forward to at least `303ed2a`.
3. Preserve uncommitted work. Do not reset or replace the credential-bearing
   `%APPDATA%\OM0RX Remote Station\agent.json`.
4. Confirm the shared controller owner is
   `python-remote-station-agent`; the legacy controller must remain refused by
   `Global\OM0RX.StationController`.

## Read-only diagnosis first

With the FLEX in receive and KPA500 in standby, collect the authenticated
`/api/v1/config` and `/api/v1/state` values without printing the bearer token.
Record:

- the actual configuration path and running process/commit;
- FLEX frequency, raw mode, TX antenna, freshness, MOX and interlock;
- resolved route band, FLEX antenna, KAT output and `amplifier_allowed`;
- configured standard and digital amplifier-allowed band lists;
- KPA500 and KAT500 band/readback, KAT amplifier-key state, route alignment,
  coordinator state, issues and `allowed_actions`.

Reproduce the policy calculation for the same raw frequency/mode directly
through `resolve_amplifier_policy`. Determine whether the discrepancy is caused
by a stale process/config, wrong config path, missing runtime reload, band/mode
normalization, stale route cache, or route construction using a different
policy source.

## Implementation requirements

- The route used by snapshot, `allowed_actions`, prepare-route and Operate must
  be built from the same active configuration and the same fresh FLEX
  frequency/mode.
- A saved configuration that requires restart must never be presented as the
  active policy before the runtime has adopted it. Expose pending-restart state
  explicitly if applicable.
- State must expose enough non-secret evidence to diagnose the decision:
  resolved policy band, raw radio mode, digital/standard profile, active
  allowed-band set, `amplifier_allowed`, config path/fingerprint, and precise
  inhibitors.
- A band change must invalidate stale route proof and align FLEX/KPA500/KAT500
  before Operate is advertised.
- If the KAT500 amplifier key line is open, reconnect and verify it only in
  confirmed receive with the KPA500 in verified standby and no device fault.
- Never advertise Operate while FLEX/KPA500/KAT500 bands or the configured
  antenna path disagree.
- Do not add a bypass, unconditional allow, retry loop that can key hardware,
  or fallback to a previous band.

## Regression coverage

Add deterministic tests for:

1. 80 m LSB/USB/CW with 80 m in the standard allow-list resolves
   `amplifier_allowed=true` and permits prepare-route/Operate after exact route
   verification.
2. 80 m digital mode uses the independent digital allow-list.
3. 20 m remains amplifier-disallowed under the current station configuration.
4. A stale prior-band route or verification proof cannot decide the new band.
5. Saved-versus-active config/restart behavior is explicit and consistent.
6. KPA/KAT band mismatch blocks Operate until safely aligned.
7. An open KAT amplifier key line is safely recovered before KPA Operate.
8. Tests never key PTT, TUNE, CWX, or emit RF.

Run the focused station-policy/coordinator/remote-agent suites, then the full
maintained gate and whitespace checks.

## Live acceptance

After code and offline tests pass, deploy through the existing guarded Remote
Station Agent workflow. Keep the radio in receive and do not invoke TUNE or
PTT. On 80 m, verify FLEX, KPA500 and KAT500 all report 80 m and the configured
path (`FLEX ANT1` to `KAT500 ANT2`) is confirmed. `allowed_actions` must include
`operate`; one operator-authorized `station_operate` must succeed, KPA500 must
report OPERATE, KAT amplifier key must report connected, and MOX must remain
false. Return to standby afterward.

Then verify the current 20 m policy remains barefoot: Operate is absent/rejected
with a precise policy reason. Report changed files, commit, test counts, active
config evidence, and before/after live state. Push the completed fix to
`codex/remote-agent-flex-spots`.

## Windows implementation and acceptance record — 2026-10-11

### Diagnosis

- Source branch starting point: `6c1d715b11ddb8aa96ffc5dd86294fee1add6bc6`.
- The migrated live controller was running from
  `C:\Projects\OM0RX-xCat\WindowsAgent` as
  `python-remote-station-agent`, launched by the existing
  `OM0RX Remote Station Agent` scheduled task.
- Active configuration path:
  `C:\Users\Oliver\AppData\Roaming\OM0RX Remote Station\agent.json`.
  Its SHA-256 stayed
  `FFA28083E47DFDDBEE7A047140B5F2F0C934E03A6CA689DD6D1CE95C3A54FB47`
  before and after deployment. No credential value was printed or committed.
- The saved policy correctly allowed 80 m in both the standard and digital
  amplifier lists at 25 W. Direct `resolve_amplifier_policy` checks confirmed
  that 80 m LSB/USB/CW were allowed while 20 m USB/CW remained barefoot.
- Two defects combined in the field. The coordinator could read mutable global
  policy rather than the exact profile loaded by the agent, while the config
  API presented a newly saved profile as though it were already active. In
  addition, the observed-route follower stopped before a band change because
  KAT500 reported a stale tuning state and its amplifier-key relay was checked
  immediately after `AMPI0`, before the documented relay-settle interval.
- The operator's reported 14.015 MHz/CW state is 20 m, not 80 m. Before the
  fix FLEX resolved to 20 m while KPA500/KAT500 were still on 80 m, so the
  mismatch and amplifier rejection were genuine consequences of the stalled
  follower rather than an 80 m policy calculation.

### Implementation

- `AgentConfig` now supplies a frozen active policy snapshot and a non-secret
  fingerprint. Snapshot, allowed actions, route preparation and Operate all
  use that same active policy and fresh FLEX frequency/mode.
- Authenticated config/state responses distinguish saved from active policy,
  expose the active config path/fingerprints and report `restart_required`
  without exposing the bearer token.
- Route state exposes the standard/digital profile, active allow-list and
  precise policy inhibitors. A frequency/band/profile change invalidates old
  route verification before Operate can be advertised.
- KAT500 amplifier-key recovery remains fail-closed. It is attempted only
  after fresh FLEX receive/READY proof and exact KPA500 standby/no-fault
  readback. A stale KAT tune state is cancelled with `CT` (never started), RX
  and KPA safety are re-proved, and one `AMPI0` write is verified with bounded
  read-only relay-settle retries. No PTT, TUNE-start, CWX or fallback to a
  previous band was added.
- The canonical migrated Windows deployment is commit
  `196ac6d371463dfe2bc4ffaf10211ffd83d41ef1` on
  `OM0RX-xCat` branch `codex/windows-agent-migration`.

### Regression evidence

- Focused source policy/coordinator/remote-agent suites: **115 passed**.
- Complete maintained source gate: **886 Python smoke passed**, **105
  browser/widget passed**, **105 MSHV offline safety passed**; Python compile,
  backend import, duplicate-route scan, PowerShell parser, JavaScript syntax,
  Ruff correctness and Git whitespace checks also passed.
- Canonical standalone WindowsAgent suite: **208 passed**.
- Production Python 3.14/FastAPI 0.143 compile/import check: passed.
- Native WinForms station-widget telemetry smoke: **1 passed**.

### Guarded live acceptance

- Only the existing agent scheduled task was stopped and started. The tray
  task remained running. After restart the config active/saved fingerprint was
  `527aea31744b4ea5a9b45bfb00d668ddde73f1ef903725a7160898d223737202`
  with `restart_required=false`; startup recovery cleared.
- At the original **14.015 MHz/CW**, the follower corrected KPA500 and KAT500
  from 80 m to **20 m**, selected **KAT ANT1**, and reported a confirmed route,
  MOX false, interlock READY, KPA standby, output 0 W and zero alarms. The
  standard policy exposed `band-not-in-active-amplifier-allow-list`; Operate
  was absent exactly as required for the configured 20 m barefoot route.
- A guarded receive-only QSY to **3.550 MHz/CW** produced an exact 80 m route:
  FLEX ANT1, KPA500 80 m standby/no fault/0 W, KAT500 80 m ANT2 idle/no fault
  with amplifier key connected, confirmed alignment, zero alarms and Operate
  explicitly present.
- One operator-authorized `station_operate` succeeded. KPA500 reported
  OPERATE while MOX stayed false, interlock stayed READY, output stayed 0 W,
  KAT500 stayed on 80 m ANT2 with its key line connected, and alarms stayed
  zero. One `station_standby` then returned KPA500 to confirmed standby.
- The radio was restored to **14.015 MHz/CW**. Final state again showed the
  confirmed 20 m barefoot route described above. No PTT, TUNE-start or CWX was
  sent and no RF was transmitted.

## Follow-on deployment — atomic tune and persistent operator intent

The macOS xLog/xCat integration now prefers the Remote Station Agent command
`set_frequency_mode`, which applies frequency and mode as one guarded route
change. The same follow-on commit also changes station-following policy so an
explicit successful amplifier Operate request remains the operator's intent
until an explicit Standby request clears it.

Windows Codex should:

1. Preserve `%APPDATA%\OM0RX Remote Station\agent.json` and any uncommitted
   work. Fetch `origin/codex/remote-agent-flex-spots` and fast-forward the
   existing deployment checkout to the latest commit on that branch.
2. Run the focused station-policy, coordinator and remote-agent suites before
   restarting the existing `OM0RX Remote Station Agent` scheduled task. Do not
   start a second controller process.
3. Confirm `/api/v1/state` advertises `set_frequency_mode`. From xLog, select a
   receive-only cluster spot and verify the new frequency and mode arrive in
   one state transition, with MOX false throughout.
4. On an amplifier-allowed band, explicitly request Operate once. Verify it
   remains requested across same-band retunes and is restored after a safe
   route transition away from and back to an allowed band. A prohibited band
   must remain in verified standby; it must not erase the stored operator
   intent.
5. Change RF power manually on Maestro, retune within the same band, and verify
   the observed value is preserved. Then change bands and verify only that
   transition applies the destination band's configured default.
6. Finish in receive, explicitly request Standby, and report commit, test
   counts and redacted before/after state. Do not invoke PTT, TUNE-start or CWX
   and do not emit RF during this acceptance.

## Windows follow-on completion — 2026-10-11

Windows fetched and verified follow-on source commit
`3366f92dc6f6d001e8c25df9629d29546db16842`. Live acceptance exposed two
additional defects in the new combined command: FLEX could publish the mode
before its frequency subscription caught up, and a long-lived cached slice
could override the fresh ordered `slice list` readback. CW also required mode
to be applied before the final tune so the requested dial frequency was not
shifted by the CW pitch.

The source fix is commit `7b8a9491355658367da8cd9de2fe8edfceb3df78`
on `codex/remote-agent-flex-spots`. It keeps the last coherent route visible
until both requested values have matching readback, continues publishing MOX
and interlock safety state during that window, pauses accessory route following,
fails stale after a bounded timeout, applies mode before frequency, and requests
one slice subscription refresh per explicit combined command. The refresh is
not sent by the polling loop. The corresponding deployed OM0RX-xCat Windows
controller is commit `c49dfd32d174507b2104d0946b9172a0f4475fe4` on
`codex/windows-agent-migration`.

### Final regression evidence

- Focused station-policy/coordinator/remote-agent suites: **117 passed**.
- Complete maintained source gate: **888 Python smoke passed**, **105
  browser/widget passed**, and **105 MSHV offline safety passed**. Python
  compile, backend import, duplicate-route scan, PowerShell parsing, JavaScript
  syntax, Ruff correctness, old-project reference scan and Git whitespace
  checks also passed.
- Canonical standalone WindowsAgent suite: **210 passed**.
- Production Python/FastAPI 0.143 compile/import check: passed.
- Native WinForms station-widget telemetry smoke: **1 passed**.

### Final guarded live evidence

- Only the existing `OM0RX Remote Station Agent` scheduled task was restarted;
  the tray task remained running and no duplicate controller was created. The
  deployed source was exactly
  `c49dfd32d174507b2104d0946b9172a0f4475fe4`. The configuration SHA-256 stayed
  `FFA28083E47DFDDBEE7A047140B5F2F0C934E03A6CA689DD6D1CE95C3A54FB47`;
  policy, commissioning, VSPE ports, Tailscale and credentials were unchanged.
- A WebSocket-observed combined transition from **7.185 MHz/CW** to
  **7.195 MHz/LSB** published the old coherent pair with a pending marker and
  then the complete new pair after **7.204 seconds**. No mixed frequency/mode
  pair appeared. MOX stayed false, radio state stayed known/non-stale after
  confirmation, and alarms were zero.
- On allowed 40 m, one explicit Operate request set the configured **25 W**
  drive and KPA500 OPERATE with 0 W output. It remained requested across a
  same-band retune. A transition to prohibited 20 m forced confirmed KPA500
  standby, aligned KPA/KAT to 20 m with KAT ANT1, applied the 65 W barefoot
  default and did not erase intent. Returning to 40 m restored KPA500 OPERATE,
  aligned both accessories to 40 m/KAT ANT2 and retained 25 W. Explicit
  Standby then cleared the intent.
- A manual Maestro change to **30 W** at 7.195 MHz/LSB was observed without an
  agent power command. A same-band retune to **7.190 MHz/LSB** preserved 30 W.
  Moving to **14.015 MHz/CW** applied the configured 20 m barefoot default of
  65 W; returning to **7.195 MHz/LSB** applied the configured 40 m barefoot
  default of 98 W. Each route settled with matching KPA/KAT bands and antenna,
  recovery clear and zero alarms.
- Final state was **7.195 MHz/LSB**, FLEX drive **98 W**, MOX false, interlock
  READY, KPA500 40 m standby at 0 W, KAT500 40 m ANT2, recovery clear and zero
  alarms. PTT, TUNE-start and CWX were never invoked, and no RF was transmitted.
