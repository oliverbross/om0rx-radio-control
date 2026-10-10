# OM0RX FLEX-8400 / KPA500 / KAT500 Commissioning Runbook

**Status:** Pre-commissioning; transmit controls remain locked  
**Station serial assignments:** KPA500 `COM17`, KAT500 `COM15` at 38,400 baud  
**Purpose:** Controlled evidence collection before the independent commissioning latch is enabled

This runbook does not authorize transmission. Stop whenever a prerequisite is
unknown, a readback disagrees with the expected route, or any device reports a
fault. The browser readiness report is advisory and cannot enable
commissioning.

## 1. Required people and equipment

- station owner or designated safety operator present at the equipment;
- suitable dummy load rated for the planned low-power test, or a specifically
  approved antenna/feed line;
- current KPA500 and KAT500 vendor utilities available for recovery;
- dated vendor-utility backups for both devices;
- physical access to remove drive/keying and power down the amplifier;
- a written mapping from each KAT output number to its real antenna, feed line,
  frequency limits, and power limit.

## 2. Hard stop conditions

Stop, remove the FLEX carrier, and leave the KPA500 in standby if any of these
occurs:

- FLEX MOX/TUNE or interlock state cannot be freshly confirmed;
- KPA500 operate/standby, band, or fault state is unknown;
- KAT500 band, frequency, output, tuning, or fault state is unknown;
- FLEX TX port and KAT output do not match the approved route profile;
- the digital engine owns CAT/PTT or has a pending transmit cycle;
- forward power appears when no supervised carrier is expected;
- SWR reaches the configured abort threshold or rises unexpectedly;
- serial replies become stale, partial, crossed, or inconsistent;
- the physical amplifier key-interrupt path does not behave as documented.

## 3. Before starting OM0RX

Record the following evidence:

1. Photograph and trace the RF path: FLEX output → KPA500 → KAT500 → each
   physical antenna/feed line.
2. Trace the keying/inhibit path, including FLEX TX1/TXREQ, KPA KEY IN, and the
   KAT PTT/key-interrupt relay.
3. In the official utilities, capture dated KPA500 and KAT500 backups plus
   screenshots of all configuration pages.
4. Record both serial numbers and firmware versions.
5. Close both Remote applications and both vendor utilities before OM0RX takes
   ownership of `COM17` and `COM15`.
6. Confirm the digital engine is stopped or explicitly inhibited and has no
   pending transmission.

## 4. Receive-only integrated validation

Keep `STATION_COORDINATOR_COMMISSIONED=false` and
`ELECRAFT_LEGACY_CONTROL_ENABLED=false` throughout this stage.

OM0RX startup recovery is intentionally fail-safe rather than electrically
silent: it may command FLEX TUNE/MOX off and KPA500 standby, then verify those
states. It must not prepare a route, select operate, tune, or store memory while
the commissioning latch is false.

1. Start OM0RX in a controlled maintenance window.
2. Confirm the station workflow shows **Commissioning locked**.
3. Confirm FLEX frequency, band, mode, TX port, MOX=false, and a receive-ready
   interlock state are fresh.
4. Confirm KPA500 identity, firmware, band, standby, and no-fault state.
5. Confirm KAT500 identity, firmware, AUTO/MAN/BYP mode, band, approximate
   frequency, selected output, idle tune state, and no-fault state.
6. Compare the full displayed route with the physical route map. FLEX ANT1 and
   KAT ANT1 are separate switching stages and must not be treated as the same
   connector.
7. Change only the FLEX receive frequency from the existing trusted control
   workflow while all station mutation controls remain locked; confirm the
   display becomes stale/mismatched rather than inventing alignment.
8. Observe at least 30 minutes of polling. Record disconnects, stale values,
   alarms, reply errors, and unexpected state changes.
9. Download an OM0RX semantic configuration snapshot and archive it with the
   vendor backups.

Receive-only validation passes only when the readiness report contains no
automated blocker and the physical route, key-interrupt, backup, and
digital-inhibit evidence have been confirmed.

## 5. Maintenance handoff validation

Do not run OM0RX and an Elecraft utility against the same COM port.

1. With FLEX confirmed in receive and KPA500 confirmed in standby, choose
   **Enter Maintenance**.
2. Confirm OM0RX reports Maintenance Mode and all route/transmit actions remain
   locked.
3. Open each official utility on its dedicated port and perform identification
   plus read-only inspection only.
4. Close both utilities completely.
5. Choose **Exit Maintenance**.
6. Confirm OM0RX re-identifies both devices, proves FLEX receive, KPA standby,
   KAT idle, and invalidates the previous route authorization.

Any failure to reacquire or verify a device is a failed test; do not bypass the
recovery lock.

## 6. Low-power supervised acceptance

This stage requires the dummy load or approved antenna to be physically
connected and the station owner to approve the frequency, route, and power.
Start with the configured bounded tune power (15–30 W; currently planned around
20 W), never full amplifier power.

For each approved route:

1. Verify the route by name and connector, then independently inspect the
   physical cable/load.
2. Confirm the digital engine is idle and the next transmit window is clear.
3. Prepare the route; confirm KPA standby during every relay change.
4. Verify FLEX frequency/TX port, KPA band/standby/no-fault, and KAT
   band/frequency/output/idle/no-fault by fresh readback.
5. Start one supervised non-storing tune.
6. Verify carrier power, reflected power, live SWR qualification, timeout, and
   cancellation behavior.
7. Accept and store memory only if the configured target is met and the final
   carrier-off/readback proof succeeds.
8. Cancel one deliberate test and verify FLEX TUNE and MOX turn off even if the
   browser is closed.
9. Record the result, route, power, SWR, device temperatures, alarms, and event
   timestamps.

Do not train a band sweep during initial commissioning. Validate isolated,
operator-approved points first.

## 7. Required acceptance cases

- FLEX stays on its approved TX port while KAT changes between two physically
  verified outputs.
- A route change during TX is rejected.
- KPA operate is rejected for any band or route mismatch.
- A good tune stores only after acceptance.
- A high-SWR or timed-out tune never stores.
- Cancel, browser loss, device disconnect, and stale telemetry all remove the
  carrier and leave the amplifier in standby.
- Maintenance releases and reacquires `COM17` and `COM15` without shared-port
  access.
- A backend restart returns the station to Unknown/locked until fresh recovery
  proof is complete.

## 8. Commissioning decision

The commissioning latch may be enabled only after:

- the browser readiness evaluation reports ready for the intended stage;
- every required human evidence item is recorded;
- the receive-only and low-power acceptance results are archived;
- route names, allowed bands, tune thresholds, and maximum powers are signed
  off by the station owner;
- a rollback test has succeeded.

The latch remains outside the ordinary web configuration API. Enabling it is a
deliberate deployment change followed by a controlled restart and fresh startup
recovery.

## 9. Rollback

1. Remove FLEX TUNE/MOX and physically remove amplifier keying if necessary.
2. Put the KPA500 in standby and power down when state cannot be confirmed.
3. Stop OM0RX Elecraft ownership.
4. Restore the documented pre-OM0RX COM/VSPE arrangement.
5. Restore dated vendor settings only if required and only through the official
   utilities.
6. Preserve OM0RX events, tune results, logs, and snapshots for diagnosis.
