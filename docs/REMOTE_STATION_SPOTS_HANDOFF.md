# OM0RX-xCat FLEX spots handoff

This branch adds the display-only `add_spot` command required by OM0RX-xCat
0.4. The Mac side listens to RUMlogNG N1MM-compatible spot UDP on loopback and
submits a validated request through the existing bearer-authenticated command
endpoint. The bearer token is never part of this document, a URL, or logs.

## Contract

The agent advertises `add_spot` in `capabilities.commands`. Its arguments are
`frequency_hz`, `callsign`, `mode`, `source`, `spotter`, `comment`, `timestamp`,
`lifetime_seconds`, `priority`, and `color`. The runtime validates their types,
bounds, printable ASCII content, and `#RRGGBB` colour syntax before calling the
existing `FlexCtl.add_spot` method.

`FlexCtl.add_spot` converts the client-facing `#RRGGBB` colour to the
SmartSDR Spot API's opaque `#AARRGGBB` form. A spot is reported as forwarded
only after the driver receives the matching zero-success radio response; a
socket write by itself is not success. This acknowledgement check is required
for truthful Maestro visibility diagnostics.

This command adds a SmartSDR panadapter marker only. It does not change
frequency, mode, route, antenna, RF power, PTT, TUNE, CWX, KPA state, KAT state,
or commissioning. It is therefore deliberately independent of the RF command
coordinator while remaining authenticated and idempotent.

## Windows agent steps

1. Fetch `codex/remote-agent-flex-spots` and verify the exact pushed SHA from
   the Mac Codex report.
2. Run `uv run --extra dev pytest -q tests/smoke/test_remote_station_agent.py`.
3. Install/update the Remote Station Agent using the repository's existing
   deployment instructions and restart it.
4. Confirm authenticated `/api/v1/state` includes `add_spot` under
   `state.capabilities.commands`; do not print the bearer token.
5. Leave the existing FLEX/KPA/KAT ports and station policy unchanged.
6. Coordinate a receive/display-only live test with the Mac. A RUMlog spot
   should appear on the FLEX panadapter; do not key or transmit RF.

Mac implementation and protocol detail are in OM0RX-xCat
`docs/REMOTE_AGENT_SPOTS.md` on branch `codex/rumlog-flex-spots`.

The live-state loop uses a 200 ms FLEX snapshot window and a 50 ms idle
interval, while reusing existing subscriptions instead of resubscribing on
every pass. This removes the previous approximately 1.55-second frequency
widget lag without changing station policy or sending a transmit command.

Follow-up live acceptance found that subscription status could be consumed
while the driver was waiting for the matching `slice list` response. The FLEX
cache was updated, but the poll returned no levels, so otherwise healthy state
aged to stale. The driver now returns freshly consumed cached values and keeps
an unchanged cache current after an acknowledged snapshot request. Repeated
poll coverage proves external frequency/mode changes remain visible without
subscription-command flooding.

## Remote configuration contract

The same branch also exposes the station's non-secret public configuration to
OM0RX-xCat:

- `GET /api/v1/config` returns the complete public `flex`, `kpa500`, `kat500`,
  and `policy` objects.
- Authenticated `PUT /api/v1/config` accepts
  `{ "config": <complete public configuration> }`.
- The update is validated using the normal agent configuration loader and is
  written atomically. The existing server bind settings and bearer token are
  preserved and are never returned to the Mac.
- A successful update returns `restart_required: true`. Restart the Windows
  Remote Station Agent before expecting new serial-port or policy values to
  become active.

The Mac **Station** tab edits KPA/KAT serial settings, FLEX station and antenna
policy, tune limits, commissioning, KAT antenna names, and per-band PA,
barefoot, digital-PA, drive-power, FLEX TX, and KAT-output rules. Do not use a
configuration save as a transmit test; after the controlled restart, verify
readback with MOX false and the KPA in standby.

## 2026-10-10 Mac acceptance and OPERATE follow-up

- Windows deployment \`b436936e0377122fad5e3d32afa7f3c6f69fe5c4\` remained
  continuously authenticated from OM0RX-xCat. Full Mac control mode remained
  enabled; automated acceptance did not key RF.
- The Mac Swift suite passed 35 tests in 7 suites. The installed 0.4.0 (6)
  application was validly signed.
- Eight discrete frequency changes measured agent-observation-to-Mac-receipt at
  155–5,088 ms (median 1,239 ms). Mac-receipt-to-SwiftUI Status/Monitor render
  was 35–94 ms (median 43 ms). Multi-second lag is therefore before the Mac
  render stage. Rapid Maestro tuning also reproduced temporary follow-route
  reconciliation delays before the route returned to confirmed.
- Six colour-category acceptance markers (\`N0GRY3\` through \`N0CYN3\`) and
  ongoing real RUMlog spots received acknowledged \`add_spot\` success. The Mac
  cannot inspect Maestro pixels; the Windows operator should confirm the six
  colours on the connected Maestro.
- OM0RX-xCat now displays both VFO A and VFO B at full 1 Hz precision in the
  compact station-monitor header whenever B is present. The KPA control is a
  single stateful toggle: standby shows **Operate**, operate shows **Standby**.
- A live **Operate** request reached the Windows coordinator but was rejected:
  \`FLEX RF drive is 65 W, expected 25 W\`. The station remained safe in KPA
  standby. Root cause was the command-response path consuming the subscribed
  live \`rfpower\` update without copying it into \`current_rfpower\`, so the
  immediate guarded readback compared the requested 25 W with the previous
  cached 65 W. \`FlexCtl._record_basic_status_from_line\` now updates the live
  drive cache while still ignoring saved \`transmit band\` preset rows.
- The focused Windows regression set passed 133 tests. Windows Codex must fetch
  the new exact branch tip reported by the Mac session, deploy it without
  replacing \`agent.json\`, restart the agent, and verify Standby → Operate →
  Standby with MOX off and no RF carrier.
