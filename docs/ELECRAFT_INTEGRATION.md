# Elecraft KPA500 and KAT500 integration

OM0RX Radio Control models the complete transmit path: FLEX TX port, KPA500,
KAT500, and the named KAT antenna output. Monitoring is always read-only. All
device-changing workflows go through the station coordinator, which is locked
by default until the installation is commissioned.

The configuration dialog has an **Elecraft** tab for ports, monitoring and
per-band KAT output policy. The main dashboard shows the end-to-end path,
guarded route/standby/operate/tune actions, transaction progress, and telemetry
history. Legacy direct device buttons remain disabled by default and are not
the normal operating path.

The coordinator will not act unless it can prove fresh FLEX receive state,
digital TX is idle, the complete route is known, and exact device readback
matches. A successful tune uses a non-storing KAT search first and stores the
memory only after the carrier is off and the measured SWR meets policy.

## Maintenance mode

Maintenance mode is a coordinator-owned safety workflow; it does not restart
the backend and there are no public raw serial connect/disconnect endpoints.
`POST /api/station/maintenance/enter` first cancels an active coordinated tune,
requires fresh FLEX receive proof, explicitly commands both TUNE and MOX off,
confirms KPA500 standby, invalidates route authorization, stops Elecraft
polling, and releases both serial ports. Read-only station state remains
available and reports `maintenance: true`; prepare, operate, tune, raw TX, and
QSY paths are locked.

`POST /api/station/maintenance/exit` reopens and identifies each configured
device, refreshes exact readback, and reconfirms FLEX receive, idle KAT state,
and KPA500 standby before polling or normal controls resume. Any failed proof
closes the ports again and leaves both maintenance and recovery locks active.
Maintenance mode does not implement firmware, reset, erase, or vendor backup
operations; it only provides a safe, explicit handoff to the official utility.

## Commissioning readiness

`GET /api/station/commissioning/readiness` evaluates cached station evidence
only. `POST` to the same endpoint adds five literal boolean operator
attestations for evaluation; it does not save them, query hardware, enable the
commissioning latch, or authorize RF. The dashboard distinguishes receive-only
readiness from a supervised low-power test and lists every remaining blocker.
There is intentionally no commissioning-enable web endpoint.

Use the [commissioning runbook](ELECRAFT_COMMISSIONING_RUNBOOK.md) for the
physical route/keying audit, vendor backups, receive-only observation,
maintenance handoff, low-power acceptance, stop conditions, and rollback.

## Direct connection

If the Elecraft Remote applications are closed, the defaults can use the
physical ports directly:

- KPA500: COM6 at 38400 baud
- KAT500: COM11 at 38400 baud

Enable each device in Configuration > Elecraft, save, and use **Connect / Retry**.

## Current migration/test endpoints

A Windows serial endpoint normally has one owner. VSPE currently exposes test
endpoints from the physical devices:

| Device | Physical source | Dedicated OM0RX test endpoint |
| --- | --- | --- |
| KPA500 | COM6, 38400 8-N-1 | COM17 |
| KAT500 | COM11, 38400 8-N-1 | COM15 |

COM17/COM15 were validated with documented GET commands only. Local OM0RX
settings are staged for those ports at the next controlled restart. Do not open
the Elecraft Remote programs on the same endpoints while OM0RX owns them.

1. Close both Elecraft Remote applications and confirm no other client owns the
   test endpoints.
2. Start the saved VSPE configuration.
3. Configure OM0RX for KPA500 COM17 and KAT500 COM15, both at 38,400 baud.
4. Leave `STATION_COORDINATOR_COMMISSIONED = False` for the receive-only pass.
5. Restart OM0RX in a controlled maintenance window and verify identity,
   firmware, faults, freshness, FLEX frequency, and displayed route only.
6. Complete the physical key-interrupt and antenna-policy checklist before any
   coordinated write or low-power tune test.

Never issue controls from multiple clients. Do not perform firmware updates,
bulk backup/restore, reset, or recovery over the normal OM0RX connection. Stop
OM0RX and use the official utility with exclusive access to the physical device.

For any commissioned write-capable session, OM0RX must be the only serial
writer. A VSPE splitter may remain temporarily for migration/read-only
comparison, but KPA500 Remote, KAT500 Remote, and the vendor utilities must be
closed before enabling the coordinator. Their independent writes cannot be
serialized with OM0RX and would invalidate route/operate/tune safety proofs.

VSPE documents the Virtual Splitter and its setup at
<https://eterlogic.com/help/vspe/DeviceSplitterPage.html> and
<https://eterlogic.com/help/vspe/Scenario_Splitter.html>.

## Frequency, radio mode, and tuner mode

Flex modulation mode (USB, CW, DIGU, and so on) is displayed and tracked, but
neither device accepts a radio modulation-mode command. KAT500 AUTO, MANUAL,
and BYPASS are tuner modes and are changed only by the explicit tuner controls;
a Flex mode change will never silently put the tuner into another operating
mode.
