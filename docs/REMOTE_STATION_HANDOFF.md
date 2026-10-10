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

## Open Windows-side blockers

OM0RX-xCat currently reports `ALARM 2` and will not accept the station as
healthy:

1. `FLEX reports INVALID`
2. `policy expects ANT1 on 15m`

The same state summary shows `Route 15m KAT ANT1`. The Windows investigation
must therefore inspect the FLEX antenna/port field and the KAT output field
independently rather than treating that route summary as proof that both are
valid. The station must remain uncommissioned while either alarm exists.

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
    is readable, the route is truthfully confirmed, the alarm count is zero,
    and `commissioned` remains `false`.

## Windows findings and test record

The Windows Codex agent should replace the placeholders below and commit the
update. Do not delete the macOS evidence or safety boundary.

- Timestamp (UTC): _pending_
- Operator-visible Windows agent version: _pending_
- Repository branch and SHA: _pending_
- Initial service/task state: _pending_
- Root cause of `FLEX reports INVALID`: _pending_
- Root cause of `policy expects ANT1 on 15m`: _pending_
- Configuration changes: _pending_
- Code changes and branch: _pending_
- Tests run with exact pass/fail counts: _pending_
- Final FLEX state: _pending_
- Final KPA500 state: _pending_
- Final KAT500 state: _pending_
- Final route and alarm state: _pending_
- Final `commissioned` value: _pending_
- Confirmation that no RF or prohibited write occurred: _pending_
- Remaining operator action: _pending_

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
