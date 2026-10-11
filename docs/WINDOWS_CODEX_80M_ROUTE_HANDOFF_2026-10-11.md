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
