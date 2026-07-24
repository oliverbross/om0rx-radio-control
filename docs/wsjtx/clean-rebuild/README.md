# WSJT-Z clean rebuild

This directory records the gated rebuild that starts from a pinned, clean
WSJT-Z source tree. The preserved customized build remains available only as a
behavior and rollback reference.

## Source identity

The pinned source is upstream tag `v2.0.14`, commit
`fa53f635462def9f37b54f63f18e407ecda2ba12`, tree
`2d23c72ddb826f18d21876ac7b6a89642ee0ef34`. It reports WSJT-X core version
`3.0.0` and WSJT-Z version `2.0.14`.

The `v3.0.2` title shown by the preserved customized executable is not an
upstream source identity: the old monolithic patch changed the core patch
number in `Versions.cmake`. The clean rebuild does not repeat that version
change.

## Milestone rules

1. Materialize the exact pinned source into `data/build/wsjt-z-clean/src`.
2. Keep that source pristine until the unmodified configure/build result is
   recorded.
3. If the local toolchain requires a compatibility patch, keep it isolated
   from functional patches and document why it is required.
4. Add one behavior at a time, with tests and a separately pushed milestone
   commit.
5. Never modify or delete `data/build/wsjt-z-om0rx`; it is the rollback and
   behavior reference.

## Prepare the source

```powershell
powershell -ExecutionPolicy Bypass -File scripts\wsjtz\prepare_clean_wsjtz.ps1
```

Use `-Force` only to discard and recreate the exact ignored clean-workspace
directory. The script refuses to remove any other path.

## Initial scope

The first production replacement contains stable band changing, the antenna
policy, display-only CS/DS, current-band DXCC priority, and essential logging
and safety. Cross-band cluster QSY and award-reference exceptions are later
work.

## Build-only compatibility patches

The pinned upstream tree does not configure on this Windows toolchain without
OmniRig COM installed, and it omits the FFTW threaded library while `jt9` calls
the threaded API. The first two patches address only those build conditions:

- `0001-build-allow-omnirig-off.patch`
- `0002-build-link-fftw-threads-on-windows.patch`

They do not change CAT/Hamlib behavior, band logic, decoding, automation, or
the user interface.

## Milestone 0 result

The clean baseline configured and built successfully after only the two
build-only compatibility patches. Artifact and toolchain hashes are recorded
in `build-lock.json`. A runtime smoke launch used the isolated
`OM0RX-WSJTZ-CLEAN` test profile; the launcher started no enrichment service
and rewrote no INI setting.

## Milestone 1 implementation

Patch `0100-band-qsy-transaction-tracing.patch` keeps the upstream band-change
path and adds correlated request/outcome diagnostics at its single CAT write
boundary. Backend automation now defaults to `wsjtz` as the dial-frequency
owner and refuses to issue a competing cross-frequency Flex tune. See
`band-control-acceptance.md` for the diagnostic contract and the deliberately
manual live-radio qualification.

## Milestone 2 implementation

The basic antenna mapping remains an external SmartSDR backend policy, so it
reacts to the frequency reported by the radio without becoming a second CAT
frequency owner. Its mapping, fail-closed TX behavior, deferred latest-band
semantics, and remaining production interlock are recorded in
`antenna-policy.md` and `milestone-2-lock.json`. Award-reference exceptions
remain deferred.

## Milestone 8 implementation

Patch `0600-direct-reply-lock.patch` gives a decoded message addressed to
OM0RX ownership of the reply slot whenever no QSO has progressed with another
station. It bypasses ordinary station filters, suppresses later CQ promotion
within the same decode batch, and queues a fallback reply for the first safe
non-transmitting opportunity. The LY3QR/YO3AUM incident and deployed artifact
identity are recorded in `milestone-8-lock.json`.

## Milestone 9 implementation

Patch `0700-log-race-and-decode-dedup.patch` rejects a backend transmit target
that matches the most recently logged call, band, and mode. The backend also
retires the active automation target as soon as WSJT-Z reports the logged QSO,
before potentially slow QRZ and Wavelog work. Decoder rows are deduplicated
before every output and automation path using UTC slot and decoded message,
while ignoring decoder-estimate and hidden AP-suffix differences. Verification
and the deployed artifact identity are recorded in `milestone-9-lock.json`.

## Milestone 10 implementation

Patch `0800-priority-watchdog-release.patch` makes the temporary 20-minute
DXCC watchdog strictly owned by the hunted call. It releases the override when
native Auto Call selects another station, when the DX target is abandoned, or
when the backend sends any non-priority target command. The ordinary configured
watchdog (currently two minutes) then becomes effective immediately.

## Milestone 11 implementation

The backend planner now retires contradictory persisted targets whose lifecycle
is still `calling` after WSJT-Z reports an idle, TX-disabled state for more than
the normal command-start grace. This applies before the 20-minute DXCC campaign
window so a command that never armed TX cannot block all other candidates.
When native Auto Call is visibly armed or transmitting for a different call,
the backend releases its old target without halting or altering the native QSO.
The recovery behavior and live-radio evidence are recorded in
`milestone-11-lock.json`.

## Milestone 12 implementation

Patch `0900-visible-filter-authority.patch` makes the visible native WSJT-Z
Filtering pane the policy source for backend automatic selection. Startup and
every operator filter change publish the complete filter matrix, continent
allow-list, LoTW-only flag, minimum signal, ignored calls, and selection
priority to the backend. The native target-command receiver independently
rejects non-direct automated targets excluded by its visible continent,
ignored-call, LoTW, or minimum-signal controls. Direct callers remain exempt so
OM0RX still answers a station calling it when no other QSO owns the slot.

The backend now preserves an explicitly empty continent selection and releases
an active non-direct target immediately when a new operator policy excludes it.
Automated target metadata carries continent, country, SNR, source, message, and
direct-caller identity to support the native fail-safe. The patch also corrects
the remote band-change guard to use WSJT-Z's visible `Band hopping` control
instead of the unrelated hidden WSPR control. Build identity and live policy
verification are recorded in `milestone-12-lock.json`.

## Milestone 13 implementation

Patch `1000-manual-tx-and-direct-preemption.patch` fixes two operator-control
and reply-priority regressions. A successful decode double-click now always
arms `Enable Tx`; the separate Quick Call preference can no longer leave a
manually selected station in prepare-only state. Direct-caller ownership now
distinguishes an unanswered outgoing Tx1 from a real exchange. A station that
addresses OM0RX may preempt the former, while an exchange that has reached the
report stage remains protected.

The PY1AX/LU6HOG incident, clean-build identity, and regression results are
recorded in `milestone-13-lock.json`.

## Milestone 14 implementation

Patch `1100-authoritative-worked-slot-veto.patch` makes the central CS/DS QSO
history authoritative over WSJT-Z's private ADIF history for automatic
selection. The classifier now reports an explicit exact callsign/band/mode
worked fact. A cached worked slot is rejected before native Auto Call
promotion; a late asynchronous result releases an unanswered automatic target
and its priority-watchdog ownership. Direct callers and progressed QSOs retain
their existing protection.

Generic `Worked` and `W/...` DXCC display states no longer arm the temporary
20-minute watchdog. ATNO and genuine new-band/new-mode DXCC opportunities
remain eligible. The 4L1FL 20m FT8 incident, live classification evidence, and
deployed artifact identity are recorded in `milestone-14-lock.json`.
