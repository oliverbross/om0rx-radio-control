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
